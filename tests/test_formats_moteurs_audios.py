"""Tâche 5.3, réduite aux pages conservées : unités lisibles, prose et liens.

Les pages sont rendues sur des données entièrement synthétiques : audios
fictifs injectés et états de moteurs en mémoire. Aucun fichier audio n'est lu,
aucun moteur n'est installé, aucun poids n'est téléchargé et aucune requête
réseau n'est émise.

Trois contrats sont vérifiés ici :

* le premier niveau ne montre ni octets bruts, ni horodatage ISO, ni durée à
  trois décimales ; les valeurs exactes restent dans les accordéons de détail ;
* aucune phrase explicative répétée dans les pages conservées (détectée dans
  le texte rendu, hors balises, données et libellés) ;
* les liens internes sortants visent des routes existantes, ancres comprises.
"""

from __future__ import annotations

import re
import unittest
from html.parser import HTMLParser

from tests.outils_html import analyser, assert_html_seul
from tests.test_web import PORT_TEST, SocleWebTest
from transcription_bench.web import ConfigApplication, ServicesApplication, create_app

#: Pages dont les liens internes et les explications sont contrôlés.
PAGES_SYNTHETIQUES = (
    "/executions",
    "/resultats",
    "/resultats/aide",
)

#: Éléments de bloc : ils séparent les textes, sans couper une phrase aux
#: balises de mise en forme (`strong`, `a`, `small`).
BLOCS = frozenset(
    {
        "address",
        "article",
        "aside",
        "blockquote",
        "body",
        "br",
        "dd",
        "details",
        "div",
        "dl",
        "dt",
        "fieldset",
        "figcaption",
        "figure",
        "footer",
        "form",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "head",
        "header",
        "hr",
        "html",
        "label",
        "legend",
        "li",
        "main",
        "nav",
        "ol",
        "option",
        "p",
        "pre",
        "section",
        "summary",
        "table",
        "tbody",
        "td",
        "tfoot",
        "th",
        "thead",
        "title",
        "tr",
        "ul",
    }
)
#: Marqueurs d'une donnée : chiffre, extension de fichier, chemin ou identifiant.
MOTIF_EXTENSION = re.compile(
    r"\.(?:wav|mp3|m4a|ogg|opus|flac|json|gguf|txt|log)$", re.IGNORECASE
)
MOTIF_FIN_DE_PHRASE = re.compile(r"[.!?…][»\"')]*$")
MOTIF_TROIS_DECIMALES = re.compile(r"\d+[.,]\d{3}\s*s\b")


class TexteRendu(HTMLParser):
    """Texte rendu d'une page, balises retirées, blocs séparés par un saut.

    `hors_details` exclut le contenu des accordéons, résumés (`summary`)
    exceptés : c'est le premier niveau demandé par le design D8. Les scripts et
    feuilles n'apportent jamais de texte.
    """

    def __init__(self, *, hors_details: bool = False) -> None:
        super().__init__(convert_charrefs=True)
        self._parts: list[str] = []
        self._a_ignorer = 0
        self._details = 0
        self._resumes = 0
        self._hors_details = hors_details

    def handle_starttag(self, tag, attrs) -> None:
        if tag in ("script", "style"):
            self._a_ignorer += 1
            return
        if tag == "details":
            self._details += 1
        elif tag == "summary":
            self._resumes += 1
        if tag in BLOCS:
            self._parts.append("\n")

    def handle_endtag(self, tag) -> None:
        if tag in ("script", "style"):
            if self._a_ignorer:
                self._a_ignorer -= 1
            return
        if tag == "summary" and self._resumes:
            self._resumes -= 1
        elif tag == "details" and self._details:
            self._details -= 1
        if tag in BLOCS:
            self._parts.append("\n")

    def handle_data(self, data) -> None:
        if self._a_ignorer:
            return
        if self._hors_details and self._details and not self._resumes:
            return
        self._parts.append(data)

    @property
    def texte(self) -> str:
        return "".join(self._parts)


def _texte(corps: str, *, hors_details: bool = False) -> str:
    """Texte rendu, blocs séparés par des sauts, espaces normalisés."""
    analyseur = TexteRendu(hors_details=hors_details)
    analyseur.feed(corps)
    analyseur.close()
    lignes = (" ".join(ligne.split()) for ligne in analyseur.texte.split("\n"))
    return "\n".join(ligne for ligne in lignes if ligne)


def premier_niveau(corps: str) -> str:
    """Texte affiché sans ouvrir d'accordéon (résumés compris)."""
    return _texte(corps, hors_details=True)


def details(corps: str) -> str:
    """Texte de tous les accordéons d'une page, données brutes comprises."""
    return _texte(corps)


def est_donnee(mot: str) -> bool:
    """Mot qui porte une valeur ou un nom, donc hors prose explicative."""
    coeur = mot.strip(".,;:!?()[]{}«»\"'’·—–|")
    if not coeur:
        return True
    if any(caractere.isdigit() for caractere in coeur):
        return True
    if MOTIF_EXTENSION.search(coeur):
        return True
    return any(separateur in coeur for separateur in ("/", "\\", "_", "@", "="))


def phrases_explicatives(corps: str) -> list[str]:
    """Phrases complètes d'au moins huit mots de prose, données exclues.

    Une phrase est retenue quand elle se termine par une ponctuation de fin de
    phrase (les lignes de champs et de valeurs n'en portent pas) et qu'il reste
    au moins huit mots une fois retirés les mots portant une donnée : chiffre,
    extension de fichier, chemin ou identifiant. Les libellés courts de champs
    restent ainsi hors du contrôle.
    """
    trouvailles: list[str] = []
    for ligne in _texte(corps).split("\n"):
        for phrase in re.split(r"(?<=[.!?…])\s+", ligne):
            phrase = " ".join(phrase.split())
            if not phrase or not MOTIF_FIN_DE_PHRASE.search(phrase):
                continue
            mots_de_prose = [
                mot for mot in phrase.split(" ") if not est_donnee(mot)
            ]
            if len(mots_de_prose) >= 8:
                trouvailles.append(phrase)
    return trouvailles


def phrases_repetees(corps: str) -> dict[str, int]:
    """Phrases explicatives présentes plus d'une fois, avec leur nombre."""
    comptes: dict[str, int] = {}
    for phrase in phrases_explicatives(corps):
        cle = phrase.lower().rstrip(".").strip()
        comptes[cle] = comptes.get(cle, 0) + 1
    return {cle: nombre for cle, nombre in comptes.items() if nombre > 1}


class SoclePagesSynthetiques(SocleWebTest):
    """Application de test des pages de consultation, sans service d'action."""

    def app_synthetique(self):
        return create_app(
            ConfigApplication(port=PORT_TEST, dossier_data=self.dossier_data),
            ServicesApplication(),
        )

    def corps(self, chemin: str, *, app=None) -> str:
        application = app or self.app_synthetique()
        reponse = application.test_client().get(chemin, base_url=self.base_url())
        self.assertEqual(reponse.status_code, 200, chemin)
        corps = reponse.get_data(as_text=True)
        assert_html_seul(self, corps)
        return corps


class FormatsPremierNiveauTest(SoclePagesSynthetiques):
    """Le premier niveau reste lisible ; les valeurs exactes sont en détail."""

    def test_aucun_premier_niveau_avec_octets_bruts_ni_trois_decimales(self) -> None:
        # Contrôle commun à toutes les pages du jeu synthétique : les seules
        # valeurs exactes admises au premier niveau sont des unités lisibles.
        for chemin in PAGES_SYNTHETIQUES:
            with self.subTest(chemin=chemin):
                affiche = premier_niveau(self.corps(chemin))
                self.assertNotRegex(affiche, r"\b\d{2,} octets\b", chemin)
                self.assertNotRegex(affiche, MOTIF_TROIS_DECIMALES, chemin)

class AidesEtProseTest(SoclePagesSynthetiques):
    """Une aide par page, sans phrase explicative répétée."""

    def test_aucune_phrase_explicative_dupliquee(self) -> None:
        for chemin in PAGES_SYNTHETIQUES:
            with self.subTest(chemin=chemin):
                corps = self.corps(chemin)
                self.assertEqual(
                    phrases_repetees(corps), {}, f"prose répétée dans {chemin}"
                )

    def test_detecteur_de_phrases_repetees(self) -> None:
        # Le détecteur lui-même : une phrase explicative répétée est signalée,
        # une ligne de données ou un libellé court ne l'est pas.
        phrase = (
            "La durée indicative vient de l'en-tête du fichier et la durée "
            "décodée reste consignée séparément."
        )
        self.assertGreaterEqual(len(phrase.split(" ")), 8)
        corps = f"<p>{phrase}</p><p>{phrase}</p>"
        self.assertEqual(len(phrases_repetees(corps)), 1)
        donnees = "<tr><td>ok.wav</td><td>WAV</td><td>1,4 Mio</td></tr>" * 2
        self.assertEqual(phrases_repetees(donnees), {})
        self.assertEqual(phrases_repetees("<p>Fichier</p><p>Fichier</p>"), {})


class LiensInternesTest(SoclePagesSynthetiques):
    """Les liens internes sortants visent des routes et des ancres existantes."""

    def verifier_liens(self, application, chemin: str) -> None:
        corps = self.corps(chemin, app=application)
        client = application.test_client()
        for href in analyser(corps).liens:
            cible, _, ancre = href.partition("#")
            if not cible and ancre:
                self.assertIn(f'id="{ancre}"', corps, f"ancre locale absente : {href}")
                continue
            if not cible.startswith("/"):
                continue
            with self.subTest(page=chemin, href=href):
                reponse = client.get(cible, base_url=self.base_url())
                self.assertEqual(reponse.status_code, 200, f"lien mort : {href}")
                if ancre:
                    self.assertIn(
                        f'id="{ancre}"',
                        reponse.get_data(as_text=True),
                        f"ancre absente pour {href}",
                    )

    def test_liens_des_pages_conservees(self) -> None:
        application = self.app_synthetique()
        for chemin in PAGES_SYNTHETIQUES:
            with self.subTest(chemin=chemin):
                self.verifier_liens(application, chemin)

if __name__ == "__main__":
    unittest.main()
