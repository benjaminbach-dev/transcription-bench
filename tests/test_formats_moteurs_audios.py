"""Tâche 5.3 : unités lisibles, aides uniques et liens de Moteurs/Audios.

Les pages sont rendues sur des données entièrement synthétiques : audios
fictifs injectés et états de moteurs en mémoire. Aucun fichier audio n'est lu,
aucun moteur n'est installé, aucun poids n'est téléchargé et aucune requête
réseau n'est émise.

Trois contrats sont vérifiés ici :

* le premier niveau ne montre ni octets bruts, ni horodatage ISO, ni durée à
  trois décimales ; les valeurs exactes restent dans les accordéons de détail ;
* une seule aide par page, au format des autres pages, sans phrase explicative
  répétée (détectée dans le texte rendu, hors balises, données et libellés) ;
* les liens internes sortants visent des routes existantes, ancres comprises.
"""

from __future__ import annotations

import re
import threading
import unittest
from html.parser import HTMLParser
from types import SimpleNamespace

from tests.outils_html import analyser, assert_html_seul
from tests.test_web import PORT_TEST, SocleWebTest
from transcription_bench.audios import AudioListe
from transcription_bench.moteurs import (
    ETAT_ECHEC,
    ETAT_NON_INSTALLE,
    ETAT_PRET,
    EtatMoteur,
)
from transcription_bench.operations import TYPE_INSTALLATION
from transcription_bench.web import ConfigApplication, create_app

DELAI = 5.0
#: Pages dont les liens internes et les explications sont contrôlés.
PAGES_SYNTHETIQUES = (
    "/audios",
    "/moteurs",
    "/moteurs/engine-pret/journal",
    "/moteurs/factice/journal",
    "/executions",
    "/modeles",
    "/resultats",
    "/resultats/aide",
)

#: Deux dates synthétiques : l'une complète, l'autre sans marqueur de fuseau.
DATE_INSTALLATION = "2026-10-25T12:00:00+02:00"
DATE_ECHEC = "2026-10-24T08:30:00+02:00"

AUDIOS_SYNTHETIQUES = (
    AudioListe(
        nom="entretien court.wav",
        format="wav",
        taille_octets=1_500_000,
        duree_indicative=0.5,
    ),
    AudioListe(
        nom="consultation longue.wav",
        format="wav",
        taille_octets=3_221_225_472,
        duree_indicative=3725.0,
    ),
    AudioListe(
        nom="reunion.wav",
        format="wav",
        taille_octets=97_250_000,
        duree_indicative=97.25,
    ),
    AudioListe(
        nom="illisible.wav",
        format="wav",
        taille_octets=None,
        duree_indicative=None,
        erreur="lecture impossible",
    ),
)

ETATS_MOTEURS = (
    EtatMoteur(
        identifiant="factice",
        nom="Moteur factice",
        etat=ETAT_PRET,
        factice=True,
        note=(
            "Moteur factice : aucune installation, aucun modèle et aucune "
            "inférence réelle. Textes et mesures sont simulés et ne représentent "
            "aucun PC."
        ),
    ),
    EtatMoteur(
        identifiant="engine-pret",
        nom="Moteur de test engine-pret",
        etat=ETAT_PRET,
        installable=True,
        date_installation=DATE_INSTALLATION,
        versions=(("sys", None),),
    ),
    EtatMoteur(
        identifiant="engine-echec",
        nom="Moteur de test engine-echec",
        etat=ETAT_ECHEC,
        installable=True,
        note="Résolution des dépendances impossible hors ligne.",
    ),
    EtatMoteur(
        identifiant="engine-non-installe",
        nom="Moteur de test engine-non-installe",
        etat=ETAT_NON_INSTALLE,
        installable=True,
        note=(
            "Verrou de dépendances non validé sur PC (jalon 0) : aucune "
            "installation n'est proposée."
        ),
    ),
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
MOTIF_HORODATAGE_ISO = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}")


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


class ResumesDeDetails(HTMLParser):
    """Résumés d'accordéons d'une page, dans l'ordre du document."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.resumes: list[str] = []
        self._capture = 0

    def handle_starttag(self, tag, attrs) -> None:
        if tag == "summary":
            self._capture += 1
            if self._capture == 1:
                self.resumes.append("")

    def handle_endtag(self, tag) -> None:
        if tag == "summary" and self._capture:
            self._capture -= 1

    def handle_data(self, data) -> None:
        if self._capture:
            self.resumes[-1] += data


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


def resumes(corps: str) -> list[str]:
    """Résumés d'accordéons d'une page."""
    analyseur = ResumesDeDetails()
    analyseur.feed(corps)
    analyseur.close()
    return analyseur.resumes


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


class MoteursSynthetiques:
    """Inventaire, journaux et déclarations en mémoire, sans aucune E/S."""

    def __init__(
        self,
        etats: tuple[EtatMoteur, ...] = ETATS_MOTEURS,
        journaux: dict[str, tuple[str, ...]] | None = None,
    ) -> None:
        self._etats = tuple(etats)
        self._journaux = dict(journaux or {})

    def inventaire(self) -> tuple[EtatMoteur, ...]:
        return self._etats

    def declaration(self, identifiant: str):
        for etat in self._etats:
            if etat.identifiant == identifiant:
                return SimpleNamespace(
                    identifiant=etat.identifiant, nom=etat.nom, factice=etat.factice
                )
        raise KeyError(identifiant)

    def lire_journal(self, identifiant: str) -> tuple[str, ...]:
        return self._journaux.get(identifiant, ())

    def verifier_installable(self, identifiant: str):
        raise AssertionError("aucune installation ne doit être sollicitée par un GET")


class SoclePagesSynthetiques(SocleWebTest):
    """Application de test sur audios et moteurs synthétiques."""

    def app_synthetique(self, **options):
        options.setdefault("moteurs", MoteursSynthetiques())
        options.setdefault(
            "lister_audios", lambda donnees: AUDIOS_SYNTHETIQUES
        )
        return create_app(
            ConfigApplication(port=PORT_TEST, dossier_data=self.dossier_data),
            self.services(**options),
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

    def test_audios_tailles_lisibles_sans_octets_bruts(self) -> None:
        corps = self.corps("/audios")
        affiche = premier_niveau(corps)

        self.assertIn("1,4 Mio", affiche)  # 1 500 000 octets
        self.assertIn("3 Gio", affiche)  # 3 221 225 472 octets
        self.assertIn("92,7 Mio", affiche)  # 97 250 000 octets
        self.assertIn("taille inconnue", affiche)
        self.assertNotIn("octets", affiche, "octets bruts au premier niveau")
        self.assertNotRegex(affiche, r"\b\d{4,}\b", "valeur brute au premier niveau")
        self.assertNotRegex(affiche, MOTIF_TROIS_DECIMALES)

    def test_audios_durees_avec_le_formateur_commun(self) -> None:
        affiche = premier_niveau(self.corps("/audios"))

        self.assertIn("0,5 s", affiche)
        self.assertIn("1 min 37 s", affiche)
        self.assertIn("1 h 2 min", affiche)
        self.assertIn("inconnue", affiche)
        self.assertNotIn("0.50 s", affiche, "décimales non françaises conservées")
        self.assertNotRegex(affiche, MOTIF_TROIS_DECIMALES)
        # Aucune durée positive n'est arrondie à zéro.
        self.assertNotIn(" 0 s", affiche)

    def test_audios_valeurs_exactes_conservees_en_detail(self) -> None:
        corps = self.corps("/audios")

        self.assertIn("Tailles exactes des fichiers et dossier d'entrée", resumes(corps))
        self.assertIn("1500000 octets", details(corps))
        self.assertIn("3221225472 octets", details(corps))
        # L'audio sans taille connue ne devient jamais « 0 octet ».
        self.assertIn("illisible.wav\ntaille inconnue", details(corps))

    def test_moteurs_date_courte_et_horodatage_brut_en_detail(self) -> None:
        corps = self.corps("/moteurs")
        affiche = premier_niveau(corps)

        self.assertNotRegex(affiche, MOTIF_HORODATAGE_ISO)
        self.assertNotIn("octets", affiche)
        self.assertNotRegex(affiche, MOTIF_TROIS_DECIMALES)
        self.assertIn("Installé le 25/10/2026 12:00", details(corps))
        self.assertIn(f"horodatage consigné : {DATE_INSTALLATION}", details(corps))

    def test_aucun_premier_niveau_avec_octets_bruts_ni_trois_decimales(self) -> None:
        # Contrôle commun à toutes les pages du jeu synthétique : les seules
        # valeurs exactes admises au premier niveau sont des unités lisibles.
        for chemin in PAGES_SYNTHETIQUES:
            with self.subTest(chemin=chemin):
                affiche = premier_niveau(self.corps(chemin))
                self.assertNotRegex(affiche, r"\b\d{2,} octets\b", chemin)
                self.assertNotRegex(affiche, MOTIF_TROIS_DECIMALES, chemin)

    def test_date_hors_format_non_inventee(self) -> None:
        # Un horodatage consigné non ISO ne devient pas une date inventée ; la
        # valeur brute reste affichée, faute d'interprétation possible.
        etats = (
            EtatMoteur(
                identifiant="engine-date",
                nom="Moteur de test engine-date",
                etat=ETAT_PRET,
                date_installation="date-hors-format",
            ),
        )
        corps = self.corps(
            "/moteurs", app=self.app_synthetique(moteurs=MoteursSynthetiques(etats))
        )

        self.assertIn("date non consignée", details(corps))
        self.assertIn("horodatage consigné : date-hors-format", details(corps))

    def test_aucune_installation_demandee_par_un_get(self) -> None:
        # Le service lève à toute sollicitation : rendre les pages prouve qu'un
        # GET ne vérifie ni ne lance aucune installation.
        application = self.app_synthetique()
        for chemin in ("/moteurs", "/moteurs/engine-pret/journal"):
            with self.subTest(chemin=chemin):
                self.corps(chemin, app=application)


class AidesEtProseTest(SoclePagesSynthetiques):
    """Une aide par page, sans phrase explicative répétée."""

    def test_une_seule_aide_par_page(self) -> None:
        for chemin in ("/audios", "/moteurs"):
            with self.subTest(chemin=chemin):
                aides = [
                    resume
                    for resume in resumes(self.corps(chemin))
                    if resume.startswith("Aide :")
                ]
                self.assertEqual(len(aides), 1, aides)

    def test_aide_au_format_des_autres_pages(self) -> None:
        # Même forme qu'Exécutions : un accordéon « Aide : … » dont chaque
        # paragraphe porte un intitulé en gras.
        for chemin in ("/audios", "/moteurs", "/executions"):
            with self.subTest(chemin=chemin):
                corps = self.corps(chemin)
                aides = [
                    resume
                    for resume in resumes(corps)
                    if resume.startswith("Aide :")
                ]
                self.assertEqual(len(aides), 1, aides)
                bloc = corps[corps.index(f"<summary>{aides[0]}") :]
                bloc = bloc[: bloc.index("</details>")]
                paragraphes = re.findall(r"<p [^>]*><strong>", bloc)
                self.assertGreaterEqual(
                    len(paragraphes), 2, "aide sans paragraphe thématique"
                )

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


class LimitationsFacticesTest(SoclePagesSynthetiques):
    """Les limitations hors ligne restent visibles, sans nouvelle promesse."""

    def test_moteur_factice_et_simulation_visibles_sans_ouvrir_un_detail(self) -> None:
        affiche = premier_niveau(self.corps("/moteurs"))

        self.assertIn("FACTICE", affiche)
        self.assertIn(
            "Textes et mesures sont simulés et ne représentent aucun PC.", affiche
        )
        self.assertIn(
            "Le serveur de développement reste réservé au moteur factice, "
            "sans moteur réel ni poids.",
            affiche,
        )
        self.assertIn(
            "Le lancement du serveur n'installe aucun moteur", affiche
        )

    def test_journal_factice_reste_explicite(self) -> None:
        affiche = premier_niveau(self.corps("/moteurs/factice/journal"))

        self.assertIn(
            "Le moteur factice ne s'installe pas", affiche
        )


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

    def test_liens_des_pages_de_moteurs_et_d_audios(self) -> None:
        application = self.app_synthetique()
        for chemin in PAGES_SYNTHETIQUES:
            with self.subTest(chemin=chemin):
                self.verifier_liens(application, chemin)

    def test_lien_vers_l_operation_en_cours_avec_ancre(self) -> None:
        liberation = threading.Event()
        self.addCleanup(liberation.set)
        self.creneau.demarrer(
            TYPE_INSTALLATION,
            lambda travailleur: liberation.wait(DELAI),
            cible="engine-pret",
        )
        try:
            application = self.app_synthetique()
            corps = self.corps("/moteurs", app=application)

            self.assertIn('href="/executions#operation"', corps)
            executions = self.corps("/executions", app=application)
            self.assertIn('id="operation"', executions)
            self.verifier_liens(application, "/moteurs")
        finally:
            liberation.set()
            thread = self.creneau.thread_travailleur
            if thread is not None:
                thread.join(DELAI)

    def test_lien_entrant_vers_moteurs_depuis_modeles(self) -> None:
        # Sans moteur installé, Modèles renvoie vers Moteurs (lien croisé).
        corps = self.corps(
            "/modeles", app=self.app_synthetique(moteurs=MoteursSynthetiques(()))
        )

        self.assertIn('href="/moteurs"', corps)


if __name__ == "__main__":
    unittest.main()
