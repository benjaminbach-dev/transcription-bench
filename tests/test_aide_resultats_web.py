"""Tests de rendu de l'aide locale préparée (tâche 1.2).

Le gabarit `aide_resultats.html` étend `base.html`, mais aucune route ne
l'expose encore : la tâche 3.3 ajoutera `/resultats/aide`. Ces tests le rendent
directement dans le contexte de l'application, vérifient les conventions et
l'échappement de « < », sans requête réseau.
"""

from __future__ import annotations

import html
import os
import unittest
from unittest.mock import patch

from flask import render_template

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

    def test_aide_non_routée_ni_liée_avant_tache_3_3(self) -> None:
        reponse = self.client.get("/resultats", base_url=self.base_url())
        self.assertEqual(reponse.status_code, 200)
        corps = reponse.get_data(as_text=True)
        self.assertNotIn("/resultats/aide", corps)
        self.assertNotIn("/resultats/aide", self.rendre_aide())

        # La route fixe relève de la tâche 3.3 : seule la route dynamique du
        # détail existe pour l'instant et répond 404 pour cet identifiant.
        self.assertEqual(
            self.client.get("/resultats/aide", base_url=self.base_url()).status_code,
            404,
        )


if __name__ == "__main__":
    unittest.main()
