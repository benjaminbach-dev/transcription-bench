"""Tests de l'absence de script et de la CSP des réponses HTML (tâche 1.3, design D2).

Le script local `/app.js` et son fichier sont supprimés : la route répond 404, aucune
page ne porte de balise `script` et la politique de sécurité des contenus interdit
tout script (`script-src 'none'`). Les 404 statiques restent des refus : aucun
fichier choisi par la requête n'est lu. Aucun accès réseau, aucune donnée réelle.
"""

from __future__ import annotations

import unittest

from tests.outils_html import analyser, assert_html_seul, assert_sans_script_ni_style
from tests.test_web import SocleWebTest
from transcription_bench.web.app import DOSSIER_FEUILLES, POLITIQUE_CONTENU

# Valeur exacte attendue (design D2) : D6 sans script, les autres directives inchangées.
# Recopiée ici pour qu'une dérive de la constante du serveur fasse échouer les tests.
CSP_ATTENDUE = (
    "default-src 'self'; script-src 'none'; style-src 'self'; "
    "connect-src 'self'; img-src 'self'; object-src 'none'; "
    "form-action 'self'; frame-ancestors 'none'; base-uri 'none'"
)

CHEMIN_SCRIPT = "/app.js"
CHEMINS_STATIQUES_ABSENTS = (
    "/static/app.js",
    "/ressources/app.js",
    "/app.js.map",
    "/static/base.css",
    "/sumi.min.css",
    "/%2e%2e/pyproject.toml",
    "/app.js/../pyproject.toml",
)


def page(scripts: str = "", corps: str = "") -> str:
    """Page minimale conforme au squelette, pour éprouver le vérificateur seul."""
    return (
        '<!DOCTYPE html><html lang="fr"><head><meta charset="utf-8">'
        "<title>Test — transcription-bench</title>"
        '<link rel="stylesheet" href="/sumi.css">'
        '<link rel="stylesheet" href="/app.css">'
        f"{scripts}</head><body>{corps}</body></html>"
    )


class RouteScriptSupprimeeTest(SocleWebTest):
    """`/app.js` n'existe plus : 404 HTML, aucun fichier de script dans le paquet."""

    def test_app_js_repond_404_avec_le_squelette(self) -> None:
        reponse = self.client.get(CHEMIN_SCRIPT, base_url=self.base_url())

        self.verifier_page_erreur(reponse, 404)
        self.assertIn("text/html", reponse.headers["Content-Type"])
        self.assertNotIn("javascript", reponse.headers["Content-Type"])

    def test_fichier_script_absent_du_paquet(self) -> None:
        self.assertFalse((DOSSIER_FEUILLES / "app.js").exists())

    def test_aucun_service_de_fichiers_arbitraires(self) -> None:
        for chemin in CHEMINS_STATIQUES_ABSENTS:
            with self.subTest(chemin=chemin):
                reponse = self.client.get(chemin, base_url=self.base_url())

                self.assertEqual(reponse.status_code, 404)
                self.assertIn("text/html", reponse.headers["Content-Type"])


class AucuneBaliseScriptTest(SocleWebTest):
    """Aucune page rendue ne contient de balise `script`, pas même une balise vide."""

    def test_aucune_page_ne_contient_de_script(self) -> None:
        for chemin in (
            "/resultats",
            "/resultats/aide",
            "/resultats/comparaison",
            "/executions",
            "/route-inexistante",
        ):
            with self.subTest(chemin=chemin):
                reponse = self.client.get(chemin, base_url=self.base_url())
                self.assertIn(reponse.status_code, (200, 404))

                pages = assert_html_seul(self, reponse.get_data(as_text=True))
                self.assertEqual(pages.balises_de("script"), [])


class PolitiqueContenuTest(SocleWebTest):
    """CSP exacte de D2 sur les réponses HTML, y compris les erreurs réelles."""

    def verifier_csp(self, reponse) -> None:
        self.assertEqual(reponse.headers["Content-Security-Policy"], CSP_ATTENDUE)

    def test_politique_exacte_sans_script_ni_echappatoire(self) -> None:
        self.assertEqual(POLITIQUE_CONTENU, CSP_ATTENDUE)
        self.assertIn("script-src 'none'", POLITIQUE_CONTENU)
        self.assertNotIn("unsafe-inline", CSP_ATTENDUE)
        self.assertNotIn("unsafe-eval", CSP_ATTENDUE)

    def test_csp_sur_les_pages_normales(self) -> None:
        for chemin in (
            "/resultats",
            "/resultats/comparaison",
            "/executions",
        ):
            with self.subTest(chemin=chemin):
                reponse = self.client.get(chemin, base_url=self.base_url())

                self.assertEqual(reponse.status_code, 200)
                self.verifier_csp(reponse)

    def test_csp_sur_404(self) -> None:
        reponse = self.client.get("/route-inconnue", base_url=self.base_url())

        self.verifier_page_erreur(reponse, 404)
        self.verifier_csp(reponse)

    def test_csp_sur_404_script_supprime(self) -> None:
        reponse = self.client.get(CHEMIN_SCRIPT, base_url=self.base_url())

        self.verifier_page_erreur(reponse, 404)
        self.verifier_csp(reponse)

    def test_csp_sur_405(self) -> None:
        reponse = self.client.post("/resultats", data={}, base_url=self.base_url())

        self.verifier_page_erreur(reponse, 405)
        self.verifier_csp(reponse)
        self.assertIn("Allow", reponse.headers)

    def test_csp_sur_404_statiques(self) -> None:
        for chemin in CHEMINS_STATIQUES_ABSENTS:
            with self.subTest(chemin=chemin):
                reponse = self.client.get(chemin, base_url=self.base_url())

                self.verifier_page_erreur(reponse, 404)
                self.verifier_csp(reponse)

    def test_csp_sur_500_reellement_provoquee(self) -> None:
        self.app.config["PROPAGATE_EXCEPTIONS"] = False

        @self.app.get("/test/erreur-csp")
        def provoquer_erreur() -> str:
            raise RuntimeError("échec interne simulé")

        with self.assertLogs(self.app.logger, level="ERROR"):
            reponse = self.client.get("/test/erreur-csp", base_url=self.base_url())

        corps = self.verifier_page_erreur(reponse, 500)
        self.verifier_csp(reponse)
        self.assertNotIn("échec interne simulé", corps)

    def test_csp_absente_des_feuilles(self) -> None:
        # La CSP décrit ce que le document charge, pas le type de la ressource.
        for chemin in ("/sumi.css", "/app.css"):
            with self.subTest(chemin=chemin):
                reponse = self.client.get(chemin, base_url=self.base_url())

                self.assertEqual(reponse.status_code, 200)
                self.assertNotIn("Content-Security-Policy", reponse.headers)


class VerificateurAucunScriptTest(unittest.TestCase):
    """Le vérificateur refuse toute balise script, même locale ou sans contenu."""

    def test_page_sans_script_acceptee(self) -> None:
        self.assertEqual(assert_html_seul(self, page()).balises_de("script"), [])

    def test_tout_script_refuse(self) -> None:
        refuses = {
            "local en defer": '<script src="/app.js" defer></script>',
            "incorporé": '<script src="/app.js" defer>alert(1)</script>',
            "sans defer": '<script src="/app.js"></script>',
            "fichier arbitraire": '<script src="/static/app.js" defer></script>',
            "fichier distant": (
                '<script src="https://cdn.example/app.js" defer></script>'
            ),
            "deux scripts": (
                '<script src="/app.js" defer></script>'
                '<script src="/app.js" defer></script>'
            ),
            "src répété": (
                '<script src="/app.js" src="https://cdn.example/app.js" defer></script>'
            ),
            "defer répété": '<script src="/app.js" defer defer></script>',
            # Un script non fermé avale le reste du document comme contenu.
            "non fermé avec code": '<script src="/app.js" defer>alert(1)',
            "non fermé vide": '<script src="/app.js" defer>',
            # HTML ne connaît pas de script auto-fermant : la balise reste ouverte.
            "auto-fermant": '<script src="/app.js" defer />',
            "src vide": '<script src="" defer></script>',
        }
        for cas, scripts in refuses.items():
            with self.subTest(cas=cas):
                with self.assertRaises(AssertionError):
                    assert_html_seul(self, page(scripts))

    def test_analyse_expose_les_scripts_non_fermes(self) -> None:
        # Contrat de l'analyseur : un script resté ouvert est compté comme tel.
        ouvert = analyser(page('<script src="/app.js" defer>alert(1)'))

        self.assertEqual(ouvert.scripts_non_fermes, 1)
        self.assertEqual(len(ouvert.scripts_contenus), 1)

    def test_gestionnaire_on_refuse(self) -> None:
        with self.assertRaises(AssertionError):
            assert_html_seul(
                self, page(corps='<button onclick="alert(1)">x</button>')
            )

    def test_corps_hors_page_refuse_tout_script(self) -> None:
        # Corps de redirection : aucun script, pas même un fichier local.
        with self.assertRaises(AssertionError):
            assert_sans_script_ni_style(
                self, page('<script src="/app.js" defer></script>')
            )


if __name__ == "__main__":
    unittest.main()
