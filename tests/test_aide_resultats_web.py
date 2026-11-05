"""Tests de l'aide locale et du regroupement des explications (tâches 1.2 et 3.3).

L'aide est servie par la route GET fixe `/resultats/aide` et liée depuis les
écrans de résultats. Les tests rendent aussi le gabarit directement dans le
contexte de l'application, vérifient les conventions et l'échappement de « < »,
sans requête réseau ni écriture dans les résultats.
"""

from __future__ import annotations

import html
import os
import unittest
from unittest.mock import patch

from flask import render_template

from tests.test_consultation_resultats import (
    IDENTIFIANT,
    IDENTIFIANT_ANCIEN,
    execution_complete,
)
from tests.test_web import SocleWebTest


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
        ):
            self.assertIn(phrase, aide_html)



if __name__ == "__main__":
    unittest.main()
