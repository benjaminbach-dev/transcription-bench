"""Tests de l'aide locale et du regroupement des explications (tâches 1.2, 2.3 et 3.3).

L'aide est servie par la route GET fixe `/resultats/aide` et liée depuis les
écrans de résultats. Les tests rendent aussi le gabarit directement dans le
contexte de l'application, vérifient les conventions et l'échappement de « < »,
sans requête réseau ni écriture dans les résultats.

La tâche 2.3 vérifie sur les pages réellement rendues qu'aucune phrase
explicative de huit mots ou plus n'est répétée d'une carte ou d'un audio à
l'autre, et que les états, marques et informations factices ou partielles
restent visibles localement. Le découpage en blocs et en phrases s'appuie sur
`html.parser` : le texte transcrit et le code sont des données, jamais de la
prose, et sont donc exclus.
"""

from __future__ import annotations

import html
import os
import re
import unittest
from collections import Counter
from html.parser import HTMLParser
from unittest.mock import patch

from flask import render_template

from tests.test_comparaison_resultats import EMPREINTE_A, resultat_empreinte
from tests.test_consultation_resultats import (
    IDENTIFIANT,
    IDENTIFIANT_ANCIEN,
    ecrire_execution,
    execution_complete,
    run_json,
)
from tests.test_web import SocleWebTest
from transcription_bench.consultation_resultats import LIBELLES_TRI
from transcription_bench.resultats import (
    ETAT_INTERROMPUE,
    STATUT_NON_TRAITE,
    STATUT_OK,
)

#: Éléments qui bornent un bloc de texte : une phrase ne traverse jamais une
#: cellule, un paragraphe ou un titre, comme à l'écran.
BLOCS_TEXTE = frozenset(
    {
        "article",
        "body",
        "br",
        "dd",
        "details",
        "div",
        "dl",
        "dt",
        "footer",
        "h1",
        "h2",
        "h3",
        "h4",
        "header",
        "li",
        "p",
        "section",
        "summary",
        "table",
        "td",
        "th",
        "tr",
        "ul",
    }
)
#: Données techniques et textes transcrits : jamais comptés comme prose.
ELEMENTS_DONNEES = frozenset({"pre", "code", "script", "style"})
#: Nombre minimal de mots d'une phrase explicative suivie par ce contrôle.
MOTS_MINIMUM = 8
LONGUEUR_EMPREINTE = "d" * 64
IDENTIFIANT_LOT = "20240104-050607-8899aabb"


class _TexteDesBlocs(HTMLParser):
    """Texte visible d'une page, borné par les blocs et sans données brutes."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.morceaux: list[str] = []
        self.donnees = 0

    def handle_starttag(self, tag: str, attrs: list) -> None:
        if tag in ELEMENTS_DONNEES:
            self.donnees += 1
        elif tag in BLOCS_TEXTE:
            self.morceaux.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in ELEMENTS_DONNEES:
            self.donnees -= 1
        elif tag in BLOCS_TEXTE:
            self.morceaux.append("\n")

    def handle_data(self, data: str) -> None:
        if not self.donnees:
            self.morceaux.append(data)


def texte_visible(corps: str) -> str:
    """Texte des blocs d'une page, sans balisage ni données techniques."""
    analyseur = _TexteDesBlocs()
    analyseur.feed(corps)
    return "".join(analyseur.morceaux)


def phrases_longues(corps: str) -> list[str]:
    """Phrases explicatives de huit mots ou plus, dans l'ordre du document."""
    phrases: list[str] = []
    texte = re.sub(r"[ \t\r\f\v]+", " ", texte_visible(corps))
    for ligne in texte.split("\n"):
        for morceau in re.split(r"(?<=[.!?])\s+", ligne):
            phrase = " ".join(morceau.split())
            if len(phrase.split()) >= MOTS_MINIMUM:
                phrases.append(phrase)
    return phrases


def repetitions(corps: str) -> dict[str, int]:
    """Phrases longues rendues plus d'une fois sur une même page."""
    comptes = Counter(phrases_longues(corps))
    return {phrase: nombre for phrase, nombre in comptes.items() if nombre > 1}


class AideResultatsWebTest(SocleWebTest):
    """Rendu du gabarit d'aide et distinction avec les formats détaillés."""

    def test_formats_jinja_ne_reactivent_pas_le_debug_par_environnement(self) -> None:
        with patch.dict(os.environ, {"FLASK_DEBUG": "1"}):
            app = self.construire_app()
        self.assertFalse(app.debug)
        self.assertFalse(app.jinja_env.auto_reload)

    def rendre_aide(self) -> str:
        with self.app.test_request_context("/", base_url=self.base_url()):
            corps = render_template("aide_resultats.html")
        self.verifier_html_seul(corps)
        return corps

    def test_aide_preparee_avec_conventions_et_exemples_reels(self) -> None:
        corps = self.rendre_aide()
        texte = html.unescape(corps)

        self.assertIn("Comprendre les indicateurs", texte)
        self.assertIn("100 × temps CPU", texte)
        self.assertIn("processeurs logiques consignés", texte)
        self.assertIn("RAM totale consignée", texte)
        self.assertIn("Le pic est cumulatif", texte)
        self.assertIn("chargement du modèle", texte)
        self.assertIn("hyperthreading", texte)
        self.assertIn("quotas système", texte)
        self.assertIn("ni une garantie de rapidité ou de fluidité", texte)
        self.assertIn("indisponible", texte)
        self.assertIn("jamais ramené à 100 %", texte)
        self.assertIn("sans réécrire ses fichiers", texte)
        # Exemples produits par les mêmes fonctions que les futurs écrans.
        self.assertIn("1 min 37 s", texte)
        self.assertIn("2,4 Go", texte)
        self.assertIn("16 Go", texte)
        self.assertIn("15 %", texte)
        self.assertIn("< 0,1 s", texte)
        self.assertIn("< 0,1 Mo", texte)
        self.assertIn("< 1 %", texte)

    def test_petites_valeurs_positives_echappees_sans_markup(self) -> None:
        corps = self.rendre_aide()

        self.assertIn("&lt; 0,1 s", corps)
        self.assertIn("&lt; 0,1 Mo", corps)
        self.assertIn("&lt; 1 %", corps)
        self.assertNotIn("< 0,1 s", corps)
        self.assertNotIn("< 0,1 Mo", corps)
        self.assertNotIn("< 1 %", corps)

    def test_macros_premier_niveau_distinctes_des_formats_detailles(self) -> None:
        with self.app.test_request_context("/", base_url=self.base_url()):
            modele = self.app.jinja_env.from_string(
                '{% import "formats.html" as f %}'
                "{{ f.duree_premier_niveau(97) }}|{{ f.duree(97) }}|"
                "{{ f.memoire_premier_niveau(2400000000) }}|"
                "{{ f.octets(2400000000) }}|"
                "{{ f.pourcentage_premier_niveau(0.4) }}"
            )
            corps = modele.render()

        self.assertEqual(
            html.unescape(corps),
            "1 min 37 s|97.000 s|2,4 Go|2400000000 octets|< 1 %",
        )

    def test_route_fixe_aide_sans_identifiant(self) -> None:
        reponse = self.client.get("/resultats/aide", base_url=self.base_url())
        self.assertEqual(reponse.status_code, 200)
        corps = reponse.get_data(as_text=True)
        self.verifier_html_seul(corps)

        # Route fixe, distincte de la route dynamique du détail : elle ne lit
        # aucun résultat et ne crée ni modifie aucun fichier.
        self.assertIn("Comprendre les indicateurs", html.unescape(corps))
        self.assertFalse(self.dossier_data.exists())
        self.assertNotIn("/resultats/aide", self.rendre_aide())

    def test_aide_liée_depuis_les_ecrans_de_resultats(self) -> None:
        execution_complete(self.dossier_data)
        execution_complete(self.dossier_data, IDENTIFIANT_ANCIEN)
        comparaison = (
            f"/resultats/comparaison/{'c' * 64}"
            f"?transcription={IDENTIFIANT}:1&transcription={IDENTIFIANT_ANCIEN}:1"
        )
        chemins = (
            "/resultats",
            "/resultats/comparaison",
            f"/resultats/{IDENTIFIANT}",
            comparaison,
        )
        for chemin in chemins:
            with self.subTest(chemin=chemin):
                reponse = self.client.get(chemin, base_url=self.base_url())
                self.assertEqual(reponse.status_code, 200, chemin)
                self.assertIn('href="/resultats/aide"', reponse.get_data(as_text=True))


    def test_aide_explique_une_fois_les_limites_du_contexte_ordinateur(self) -> None:
        """Section « Contexte de l'ordinateur » : D4 et exigence de limites."""
        texte = html.unescape(self.rendre_aide())

        # Chaque limite demandée est expliquée, une seule fois par page.
        for attendu in (
            "Le CPU total inclut les autres programmes de l'ordinateur",
            "estimation du système à un instant donné",
            "le minimum resté pendant la transcription",
            "ressources visibles par le système",
            "capacité matérielle garantie",
            "garantie de confort d'usage",
            "Le relevé après chargement et le relevé après audio",
            "le contexte de cet essai",
            "preuve de performance sur un autre ordinateur",
            "ordinateur partagé ou virtualisé",
        ):
            with self.subTest(attendu=attendu):
                self.assertEqual(texte.count(attendu), 1, attendu)

        # Le texte complet vit ici : la phrase courte du bloc n'y est pas
        # recopiée, et aucune promesse positive n'est ajoutée.
        self.assertNotIn("Les limites de ces valeurs sont détaillées", texte)
        for interdit in (
            "marge restante de",
            "ordinateur fluide",
            "garantit la fluidité",
            "garantie de performance sur un autre",
            "propre au modèle",
        ):
            with self.subTest(interdit=interdit):
                self.assertNotIn(interdit, texte)

    def test_explications_regroupees_dans_l_aide(self) -> None:
        execution_complete(self.dossier_data, IDENTIFIANT)
        execution_complete(self.dossier_data, IDENTIFIANT_ANCIEN)
        comparaison = (
            f"/resultats/comparaison/{'c' * 64}"
            f"?transcription={IDENTIFIANT}:1"
            f"&transcription={IDENTIFIANT_ANCIEN}:1"
        )

        comparaison_html = html.unescape(
            self.client.get(
                comparaison,
                base_url=self.base_url(),
            ).get_data(as_text=True)
        )
        detail_html = html.unescape(
            self.client.get(
                f"/resultats/{IDENTIFIANT}", base_url=self.base_url()
            ).get_data(as_text=True)
        )
        aide_html = html.unescape(
            self.client.get("/resultats/aide", base_url=self.base_url())
            .get_data(as_text=True)
        )

        # Les explications générales ne sont plus répétées avant les textes.
        for page in (comparaison_html, detail_html):
            for phrase in (
                "JSON complet",
                "NaN",
                "n'exclut aucune transcription",
                "Aucune de ces absences n'est remplacée par zéro",
                "Le nom du processeur est informatif",
            ):
                self.assertNotIn(phrase, page)
        # Elles sont regroupées dans l'aide locale.
        for phrase in (
            "empreinte SHA-256",
            "JSON complet",
            "NaN",
            "n'exclut aucune transcription",
            "aucune inférence",
            "score global",
            "Le nom du processeur est informatif",
            "Aucune de ces absences n'est remplacée par zéro",
            "meilleur temps",
            "64 sélections",
            "conserve les cases cochées",
        ):
            self.assertIn(phrase, aide_html)

    def ecrire_deux_cartes_et_un_lot(self) -> None:
        """Deux essais du même audio (deux cartes) puis un lot de deux audios."""
        machine = run_json()["machine"]
        for identifiant, temps, pic, ram in (
            (IDENTIFIANT, 1.0, 2048, machine["ram_totale_octets"]),
            (IDENTIFIANT_ANCIEN, 2.0, 4096, 32_000_000_000),
        ):
            # Essais observés (marque SYNTHÉTIQUE seule) : les distinctions de
            # temps et de RAM s'appliquent, contrairement aux mesures simulées.
            # La RAM totale diffère : une mention locale reste visible par carte.
            marques = {"factice": False, "synthetique": True, "mesures_simulees": False}
            run = run_json(
                identifiant,
                machine={**machine, "ram_totale_octets": ram},
                **marques,
            )
            ecrire_execution(
                self.dossier_data,
                run,
                (
                    resultat_empreinte(
                        run,
                        run["audios"][0],
                        EMPREINTE_A,
                        duree_transcription=temps,
                        mesures_extra={"pic_memoire_octets": pic},
                        **marques,
                    ),
                ),
            )
        lot = run_json(
            IDENTIFIANT_LOT,
            audios=(("a.wav", STATUT_OK), ("b.wav", STATUT_OK)),
        )
        ecrire_execution(
            self.dossier_data,
            lot,
            (
                resultat_empreinte(lot, lot["audios"][0], LONGUEUR_EMPREINTE),
                resultat_empreinte(lot, lot["audios"][1], LONGUEUR_EMPREINTE),
            ),
        )

    def pages_du_cas_courant(self) -> dict[str, str]:
        """Pages rendues du cas courant : listes, comparaison et détail de lot."""
        self.ecrire_deux_cartes_et_un_lot()
        chemins = {
            "/resultats": {},
            "/resultats/comparaison": {},
            "/resultats/aide": {},
            f"/resultats/{IDENTIFIANT_LOT}": {},
            f"/resultats/comparaison/{EMPREINTE_A}": {
                "query_string": [
                    ("transcription", f"{IDENTIFIANT}:1"),
                    ("transcription", f"{IDENTIFIANT_ANCIEN}:1"),
                ]
            },
        }
        pages: dict[str, str] = {}
        for chemin, options in chemins.items():
            options.setdefault("base_url", self.base_url())
            reponse = self.client.get(chemin, **options)
            self.assertEqual(reponse.status_code, 200, chemin)
            pages[chemin] = html.unescape(reponse.get_data(as_text=True))
        return pages

    def test_aucune_phrase_longue_repete_d_une_carte_a_l_autre(self) -> None:
        # Jeu du cas courant : deux cartes de comparaison, un détail de lot de
        # deux audios et les listes correspondantes.
        for chemin, corps in self.pages_du_cas_courant().items():
            with self.subTest(chemin=chemin):
                self.assertEqual(repetitions(corps), {}, chemin)

    def test_distinctions_proches_des_valeurs_sans_synthese_de_vainqueur(self) -> None:
        pages = self.pages_du_cas_courant()
        comparaison = pages[f"/resultats/comparaison/{EMPREINTE_A}"]

        # Libellés courts près des valeurs, égalités comprises, sans phrase de
        # synthèse désignant un modèle ni distinction de CPU.
        self.assertEqual(comparaison.count("meilleur temps"), 1)
        self.assertEqual(comparaison.count("meilleure RAM"), 1)
        self.assertNotIn("Plus rapide :", comparaison)
        self.assertNotIn("Moins de RAM :", comparaison)
        self.assertNotIn("meilleur CPU", comparaison)

    def test_marques_et_infos_factices_ou_partielles_restent_locales(self) -> None:
        pages = self.pages_du_cas_courant()
        detail = pages[f"/resultats/{IDENTIFIANT_LOT}"]

        # Une marque visible par audio, sans explication générale répétée.
        self.assertEqual(detail.count("Marques de cette transcription"), 2)
        self.assertEqual(detail.count("Texte et mesures simulés"), 2)
        self.assertNotIn("sans modèle ni inférence réelle", detail)
        # Les mesures simulées restent signalées une seule fois par page.
        for chemin in ("/resultats", "/resultats/comparaison"):
            self.assertEqual(pages[chemin].count("sans distinction de performance"), 1)
        # Une mention de matériel reste locale à chaque carte, son explication
        # générale n'apparaît qu'une fois sur la page.
        comparaison = pages[f"/resultats/comparaison/{EMPREINTE_A}"]
        self.assertEqual(comparaison.count("Matériel différent sur RAM totale"), 2)
        self.assertEqual(comparaison.count("sans preuve d'identité des machines"), 1)

        # Un lot interrompu reste partiel et ses états restent visibles.
        run = run_json(
            "20240105-060708-99aabbcc",
            etat=ETAT_INTERROMPUE,
            audios=(("a.wav", STATUT_OK), ("b.wav", STATUT_NON_TRAITE)),
        )
        ecrire_execution(
            self.dossier_data, run, (resultat_empreinte(run, run["audios"][0]),)
        )
        reponse = self.client.get(
            "/resultats/20240105-060708-99aabbcc", base_url=self.base_url()
        )
        partiel = html.unescape(reponse.get_data(as_text=True))
        self.assertIn("résultats partiels", partiel)
        self.assertIn("résultat partiel", partiel)
        self.assertIn("Audio non traité", partiel)

    def test_libelles_de_tri_partages_et_aide_liee_une_seule_fois(self) -> None:
        pages = self.pages_du_cas_courant()
        # L'aide ne se lie pas elle-même ; chaque écran de résultats la lie une fois.
        self.assertEqual(pages["/resultats/aide"].count('href="/resultats/aide"'), 0)
        for chemin, corps in pages.items():
            if chemin == "/resultats/aide":
                continue
            with self.subTest(chemin=chemin):
                self.assertEqual(corps.count('href="/resultats/aide"'), 1)
        for chemin in ("/resultats", "/resultats/comparaison"):
            for libelle in LIBELLES_TRI.values():
                self.assertIn(libelle, pages[chemin])


if __name__ == "__main__":
    unittest.main()
