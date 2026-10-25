"""Tests de la couche web : fabrique, pages, redirections et erreurs HTML."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from transcription_bench.paths import DOSSIERS_DATA
from transcription_bench.web import ConfigApplication, ServicesApplication, create_app

ADRESSE_LOCALE = "127.0.0.1"
PORT_TEST = 8765
ELEMENTS_CSS_JS_INTERDITS = ("<script", "<style", "style=", "stylesheet", "<link", "javascript:")


class WebTest(unittest.TestCase):
    def setUp(self) -> None:
        temporaire = tempfile.TemporaryDirectory()
        self.addCleanup(temporaire.cleanup)
        self.dossier_data = Path(temporaire.name) / "data"
        self.app = create_app(
            ConfigApplication(port=PORT_TEST, dossier_data=self.dossier_data),
            ServicesApplication(),
        )
        self.client = self.app.test_client()

    def base_url(self, port: int = PORT_TEST) -> str:
        return f"http://{ADRESSE_LOCALE}:{port}"

    def verifier_html_seul(self, corps: str) -> None:
        for interdit in ELEMENTS_CSS_JS_INTERDITS:
            self.assertNotIn(interdit, corps)
        self.assertNotIn("Traceback", corps)

    def verifier_page_erreur(self, reponse, code: int) -> str:
        self.assertEqual(reponse.status_code, code)
        self.assertIn("text/html", reponse.headers["Content-Type"])
        corps = reponse.get_data(as_text=True)
        self.assertIn(f"Erreur {code}", corps)
        self.assertNotIn("RuntimeError", corps)
        self.verifier_html_seul(corps)
        return corps

    def test_fabrique_sans_effet_de_bord(self) -> None:
        reponse = self.client.get("/", base_url=self.base_url())

        self.assertEqual(reponse.status_code, 200)
        self.assertFalse(self.dossier_data.exists())
        self.assertFalse(self.app.debug)
        self.assertFalse(self.app.config["DEBUG"])
        self.assertNotIn("static", self.app.view_functions)
        self.assertEqual(self.app.config["PORT"], PORT_TEST)
        self.assertEqual(self.app.config["DOSSIER_DATA"], str(self.dossier_data))

    def test_accueil_liste_les_dossiers_de_donnees(self) -> None:
        reponse = self.client.get("/", base_url=self.base_url())
        corps = reponse.get_data(as_text=True)

        self.assertEqual(reponse.status_code, 200)
        self.assertEqual(corps.count("(absent)"), len(DOSSIERS_DATA))
        for nom in DOSSIERS_DATA:
            self.assertIn(str(self.dossier_data / nom), corps)
        self.verifier_html_seul(corps)

    def test_accueil_echappe_le_contenu_dynamique(self) -> None:
        dossier_piege = self.dossier_data / "<script>alert(1)</script>"
        app = create_app(
            ConfigApplication(port=PORT_TEST, dossier_data=dossier_piege),
            ServicesApplication(),
        )
        reponse = app.test_client().get("/", base_url=self.base_url())
        corps = reponse.get_data(as_text=True)

        self.assertEqual(reponse.status_code, 200)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", corps)
        self.verifier_html_seul(corps)

    def test_action_acceptee_deleguee_au_service_injecte(self) -> None:
        appels: list[Path] = []

        def preparer(base: Path) -> dict[str, Path]:
            appels.append(base)
            return {}

        app = create_app(
            ConfigApplication(port=PORT_TEST, dossier_data=self.dossier_data),
            ServicesApplication(preparer_dossiers=preparer),
        )
        reponse = app.test_client().post("/dossiers/verifier", base_url=self.base_url())

        self.assertEqual(reponse.status_code, 303)
        self.assertEqual(appels, [self.dossier_data])
        self.assertFalse(self.dossier_data.exists())

    def test_post_verifie_puis_redirige_en_303_vers_un_get(self) -> None:
        reponse = self.client.post("/dossiers/verifier", base_url=self.base_url())

        self.assertEqual(reponse.status_code, 303)
        self.assertEqual(reponse.headers["Location"], "/?action=dossiers-verifies")
        self.verifier_html_seul(reponse.get_data(as_text=True))
        for nom in DOSSIERS_DATA:
            self.assertTrue((self.dossier_data / nom).is_dir(), nom)

        page = self.client.get(reponse.headers["Location"], base_url=self.base_url())
        corps = page.get_data(as_text=True)
        self.assertEqual(page.status_code, 200)
        self.assertIn("Dossiers de données vérifiés.", corps)
        self.assertEqual(corps.count("(présent)"), len(DOSSIERS_DATA))
        self.verifier_html_seul(corps)

    def test_action_en_get_refusee_avec_en_tete_allow(self) -> None:
        reponse = self.client.get("/dossiers/verifier", base_url=self.base_url())

        self.verifier_page_erreur(reponse, 405)
        methodes_autorisees = {m.strip() for m in reponse.headers["Allow"].split(",")}
        self.assertEqual(methodes_autorisees, {"OPTIONS", "POST"})

    def test_route_inconnue_rend_une_page_404(self) -> None:
        reponse = self.client.get("/route-inconnue", base_url=self.base_url())

        self.verifier_page_erreur(reponse, 404)

    def test_route_statique_absente(self) -> None:
        reponse = self.client.get("/static/base.css", base_url=self.base_url())

        self.verifier_page_erreur(reponse, 404)

    def test_erreur_interne_sans_trace_dans_la_reponse(self) -> None:
        self.app.config["PROPAGATE_EXCEPTIONS"] = False

        @self.app.get("/test/erreur")
        def provoquer_erreur() -> str:
            raise RuntimeError("échec interne simulé")

        with self.assertLogs(self.app.logger, level="ERROR"):
            reponse = self.client.get("/test/erreur", base_url=self.base_url())

        corps = self.verifier_page_erreur(reponse, 500)
        self.assertNotIn("échec interne simulé", corps)


if __name__ == "__main__":
    unittest.main()
