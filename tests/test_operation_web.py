"""Tests de la page d'opération et des mutations de l'interface sous verrou.

La page ne doit rien démarrer, le travail de fond ne dépend d'aucun contexte de
requête et les mutations courtes passent par le créneau : acceptées au repos,
refusées en 409 pendant une opération et en 503 après le passage à l'arrêt.
"""

from __future__ import annotations

import threading
import unittest
from pathlib import Path

from tests.test_web import SocleWebTest
from transcription_bench.operations import ETAT_EN_COURS, ETAT_LIBRE

DELAI = 5.0


class PageOperationTest(SocleWebTest):
    def setUp(self) -> None:
        super().setUp()
        self.demarre = threading.Event()
        self.fin = threading.Event()
        self.addCleanup(self.liberer_travail)

    def liberer_travail(self) -> None:
        self.fin.set()
        thread = self.creneau.thread_travailleur
        if thread is not None:
            thread.join(DELAI)

    def demarrer_operation(
        self,
        lignes: tuple[str, ...] = ("Préparation",),
        type_operation: str = "execution",
        cible: str = "audio.wav",
    ) -> None:
        def travail(travailleur) -> None:
            for ligne in lignes:
                travailleur.journaliser(ligne)
            self.demarre.set()
            if not self.fin.wait(DELAI):
                raise AssertionError("le test n'a pas libéré le travail de fond")

        self.creneau.demarrer(type_operation, travail, cible=cible)
        self.assertTrue(self.demarre.wait(DELAI), "le travail de fond n'a pas démarré")

    def page(self) -> str:
        reponse = self.client.get("/operation", base_url=self.base_url())
        self.assertEqual(reponse.status_code, 200)
        corps = reponse.get_data(as_text=True)
        self.verifier_html_seul(corps)
        return corps

    def test_page_libre_par_defaut(self) -> None:
        reponse = self.client.get("/operation", base_url=self.base_url())
        corps = reponse.get_data(as_text=True)

        self.assertEqual(reponse.status_code, 200)
        self.assertIn("État", corps)
        self.assertIn("libre", corps)
        self.assertIn("Aucune opération enregistrée depuis le démarrage.", corps)
        self.assertIn('href="/operation"', corps)
        self.assertIn("Actualiser", corps)
        self.assertNotIn("Set-Cookie", reponse.headers)
        self.verifier_html_seul(corps)

    def test_page_sans_effet_de_bord_ni_thread(self) -> None:
        self.page()

        self.assertEqual(self.creneau.instantane().etat, ETAT_LIBRE)
        self.assertIsNone(self.creneau.thread_travailleur)
        self.assertFalse(self.dossier_data.exists())

    def test_page_pendant_une_operation_montre_etat_journal_et_cible(self) -> None:
        self.demarrer_operation(lignes=("Étape 1 : préparation", "Étape 2 : chargement"))
        corps = self.page()

        self.assertIn("en cours", corps)
        self.assertIn("exécution", corps)
        self.assertIn("audio.wav", corps)
        self.assertIn("Étape 1 : préparation", corps)
        self.assertIn("Étape 2 : chargement", corps)
        self.assertIn("Début", corps)
        self.assertNotIn("arrêt demandé", corps)

    def test_page_apres_operation_montre_l_issue_et_les_horodatages(self) -> None:
        self.demarrer_operation()
        self.fin.set()
        thread = self.creneau.thread_travailleur
        self.assertIsNotNone(thread)
        thread.join(DELAI)

        corps = self.page()
        self.assertIn("terminée", corps)
        self.assertIn("Début", corps)
        self.assertIn("Fin", corps)
        self.assertIn("Opération terminée.", corps)

    def test_page_apres_arret_indique_l_arret(self) -> None:
        self.creneau.arreter()

        corps = self.page()
        self.assertIn("arrêt demandé", corps)

    def test_journal_echappe_dans_la_page(self) -> None:
        self.demarrer_operation(lignes=("<script>alert(1)</script>",))

        corps = self.page()
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", corps)
        self.assertNotIn("<script>alert(1)</script>", corps)

    def test_mutation_refusee_pendant_une_operation_en_409(self) -> None:
        appels: list[Path] = []
        app = self.construire_app(
            self.services(preparer_dossiers=lambda base: appels.append(base) or {})
        )
        self.demarrer_operation()

        reponse = self.post_autorise("/dossiers/verifier", app=app)
        corps = self.verifier_refus(reponse, 409, appels)

        self.assertIn("opération longue est déjà en cours", corps)
        self.assertEqual(self.creneau.instantane().etat, ETAT_EN_COURS)

    def test_mutation_refusee_apres_arret_en_503(self) -> None:
        appels: list[Path] = []
        app = self.construire_app(
            self.services(preparer_dossiers=lambda base: appels.append(base) or {})
        )
        self.creneau.arreter()

        reponse = self.post_autorise("/dossiers/verifier", app=app)
        corps = self.verifier_refus(reponse, 503, appels)

        self.assertIn("Le serveur est en cours d", corps)
        self.assertFalse(self.dossier_data.exists())

    def test_mutation_acceptee_executee_sous_le_creneau(self) -> None:
        appels: list[Path] = []
        app = self.construire_app(
            self.services(preparer_dossiers=lambda base: appels.append(base) or {})
        )

        reponse = self.post_autorise("/dossiers/verifier", app=app)

        self.assertEqual(reponse.status_code, 303)
        self.assertEqual(appels, [self.dossier_data])
        self.assertNotIn("Set-Cookie", reponse.headers)
        self.assertEqual(self.creneau.instantane().etat, ETAT_LIBRE)

    def test_page_et_mutation_protegees_sans_cookie(self) -> None:
        etranger = self.client.get(
            "/operation", base_url=self.base_url(), headers={"Host": "evil.example:8765"}
        )
        self.verifier_page_erreur(etranger, 403)
        self.assertNotIn("Set-Cookie", etranger.headers)

        sans_jeton = self.client.post(
            "/operation", data={"champ": "1"}, base_url=self.base_url()
        )
        self.verifier_page_erreur(sans_jeton, 403)
        self.assertNotIn("Set-Cookie", sans_jeton.headers)

        avec_jeton = self.post_autorise("/operation")
        self.verifier_page_erreur(avec_jeton, 405)


if __name__ == "__main__":
    unittest.main()
