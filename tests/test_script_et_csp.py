"""Tests de la route fixe `/app.js` et de la CSP des réponses HTML (tâche 1.2).

Design D6 : un seul script local `/app.js`, servi comme les feuilles (type
explicite, `nosniff`, `no-cache`, contrôle `Host`), et une politique de sécurité
des contenus stricte sur les réponses HTML, pages d'erreur réelles comprises.
Les 404 statiques restent des refus : aucun fichier choisi par la requête n'est
lu. Aucun accès réseau, aucune donnée réelle.
"""

from __future__ import annotations

import unittest

from tests.outils_html import (
    ATTRIBUTS_SCRIPT,
    SCRIPT_ATTENDU,
    analyser,
    assert_html_seul,
    assert_sans_script_ni_style,
)
from tests.test_web import SocleWebTest
from transcription_bench.web.app import (
    DOSSIER_FEUILLES,
    NOM_SCRIPT_APP,
    POLITIQUE_CONTENU,
    TYPE_SCRIPT,
)

# Valeur exacte attendue du design D6, recopiée ici pour qu'une dérive de la
# constante du serveur fasse échouer les tests au lieu de les suivre.
CSP_ATTENDUE = (
    "default-src 'self'; script-src 'self'; style-src 'self'; "
    "connect-src 'self'; img-src 'self'; object-src 'none'; "
    "form-action 'self'; frame-ancestors 'none'; base-uri 'none'"
)

CHEMIN_SCRIPT = "/app.js"
CHEMIN_SCRIPT_SUR_DISQUE = DOSSIER_FEUILLES / NOM_SCRIPT_APP
# Chaîne propre au fichier servi : elle ne doit jamais apparaître dans une 404.
MARQUEUR_SCRIPT = '"use strict"'
HOTES_REFUSES = ("evil.example:8765", "127.0.0.1:8766", "127.0.0.1")
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


class RouteScriptTest(SocleWebTest):
    """`/app.js` : fichier unique, en-têtes fixes, mêmes contrôles que les feuilles."""

    def test_script_servi_avec_entetes_fixes(self) -> None:
        reponse = self.client.get(CHEMIN_SCRIPT, base_url=self.base_url())

        self.assertEqual(reponse.status_code, 200)
        self.assertEqual(TYPE_SCRIPT, "text/javascript; charset=utf-8")
        self.assertEqual(reponse.headers["Content-Type"], TYPE_SCRIPT)
        self.assertEqual(reponse.headers["X-Content-Type-Options"], "nosniff")
        self.assertEqual(reponse.headers["Cache-Control"], "no-cache")
        self.assertNotIn("Set-Cookie", reponse.headers)
        self.assertTrue(reponse.get_data())

    def test_script_servi_est_le_fichier_du_paquet_decode_en_utf8(self) -> None:
        corps = self.client.get(CHEMIN_SCRIPT, base_url=self.base_url()).get_data()

        self.assertEqual(corps, CHEMIN_SCRIPT_SUR_DISQUE.read_bytes())
        self.assertTrue(corps.decode("utf-8"))

    def test_script_sans_evaluation_dynamique_ni_ressource_distante(self) -> None:
        source = CHEMIN_SCRIPT_SUR_DISQUE.read_text(encoding="utf-8")

        for interdit in ("eval(", "new Function", "http://", "https://", "<script"):
            with self.subTest(interdit=interdit):
                self.assertNotIn(interdit, source)

    def test_host_non_local_refuse_pour_le_script(self) -> None:
        for hote in HOTES_REFUSES:
            with self.subTest(hote=hote):
                reponse = self.client.get(
                    CHEMIN_SCRIPT,
                    base_url=self.base_url(),
                    headers={"Host": hote},
                )

                self.assertEqual(reponse.status_code, 403)
                self.assertIn("text/html", reponse.headers["Content-Type"])
                self.assertNotEqual(reponse.headers["Content-Type"], TYPE_SCRIPT)
                self.assertNotIn(MARQUEUR_SCRIPT, reponse.get_data(as_text=True))

    def test_adresse_locale_et_localhost_acceptees(self) -> None:
        for base in (self.base_url(), "http://localhost:8765"):
            with self.subTest(base=base):
                reponse = self.client.get(CHEMIN_SCRIPT, base_url=base)

                self.assertEqual(reponse.status_code, 200)
                self.assertEqual(reponse.headers["Content-Type"], TYPE_SCRIPT)

    def test_aucun_service_de_fichiers_arbitraires_pour_le_script(self) -> None:
        for chemin in CHEMINS_STATIQUES_ABSENTS:
            with self.subTest(chemin=chemin):
                reponse = self.client.get(chemin, base_url=self.base_url())

                self.assertEqual(reponse.status_code, 404)
                self.assertIn("text/html", reponse.headers["Content-Type"])
                self.assertNotIn(MARQUEUR_SCRIPT, reponse.get_data(as_text=True))

    def test_methode_non_autorisee_sur_le_script(self) -> None:
        reponse = self.client.post(
            CHEMIN_SCRIPT,
            data={},
            base_url=self.base_url(),
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )

        # Le contrôle Host puis jeton s'applique avant la méthode : refus 403
        # HTML, jamais un 405 ni le script lui-même.
        self.assertEqual(reponse.status_code, 403)
        self.assertNotEqual(reponse.headers["Content-Type"], TYPE_SCRIPT)


class SqueletteScriptTest(SocleWebTest):
    """Le squelette commun charge exactement le script local, en `defer`."""

    def scripts_de(self, chemin: str) -> list[dict[str, str | None]]:
        reponse = self.client.get(chemin, base_url=self.base_url())
        self.assertIn(reponse.status_code, (200, 404), chemin)
        corps = reponse.get_data(as_text=True)
        pages = assert_html_seul(self, corps)
        return [dict(attributs) for _, _, attributs in pages.balises_de("script")]

    def test_script_unique_en_defer_sur_les_pages(self) -> None:
        for chemin in ("/", "/resultats", "/modeles", "/route-inexistante"):
            with self.subTest(chemin=chemin):
                self.assertEqual(self.scripts_de(chemin), [dict(ATTRIBUTS_SCRIPT)])

    def test_script_annonce_par_le_verificateur(self) -> None:
        self.assertEqual(ATTRIBUTS_SCRIPT, {"src": SCRIPT_ATTENDU, "defer": None})


class VerificateurScriptTest(unittest.TestCase):
    """Le vérificateur n'accepte que le script local `defer`, sans contenu."""

    def test_script_local_en_defer_accepte(self) -> None:
        pages = assert_html_seul(self, page('<script src="/app.js" defer></script>'))

        self.assertEqual(pages.scripts_contenus, [""])
        self.assertEqual(pages.scripts_non_fermes, 0)
        self.assertEqual(
            [dict(attributs) for _, _, attributs in pages.balises_de("script")],
            [dict(ATTRIBUTS_SCRIPT)],
        )

    def test_analyse_expose_les_doublons_et_scripts_non_fermes(self) -> None:
        # Contrat du vérificateur : l'analyse ne perd ni doublon d'attribut ni
        # script sans balise de fermeture, sinon un contrôle par `dict` ou par
        # contenu vide accepterait un script hostile.
        double = analyser(
            page(
                '<script src="/app.js" src="https://cdn.example/app.js" defer></script>'
            )
        )
        ouvert = analyser(page('<script src="/app.js" defer>alert(1)'))

        self.assertEqual(
            [valeur for _, nom, valeur in double.attributs if nom == "src"],
            ["/app.js", "https://cdn.example/app.js"],
        )
        self.assertEqual(ouvert.scripts_non_fermes, 1)
        self.assertTrue(ouvert.scripts_contenus[0].startswith("alert(1)"))
        # Un script non fermé avale la fin du document : contenu non vide.
        self.assertTrue(ouvert.scripts_contenus[0])

    def test_page_sans_script_acceptee(self) -> None:
        self.assertEqual(assert_html_seul(self, page()).balises_de("script"), [])

    def test_scripts_refuses(self) -> None:
        refuses = {
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
            "attribut supplémentaire": (
                '<script src="/app.js" defer async></script>'
            ),
            # `dict(attributs)` masquerait ces deux cas : les attributs sont lus
            # dans l'ordre du document, doublons compris.
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

    def test_gestionnaire_on_refuse(self) -> None:
        with self.assertRaises(AssertionError):
            assert_html_seul(self, page('<script src="/app.js" defer></script>',
                                        '<button onclick="alert(1)">x</button>'))

    def test_corps_hors_page_refuse_meme_le_script_local(self) -> None:
        # Corps de redirection : aucun script, pas même le fichier local.
        with self.assertRaises(AssertionError):
            assert_sans_script_ni_style(
                self, page('<script src="/app.js" defer></script>')
            )


class PolitiqueContenuTest(SocleWebTest):
    """CSP exacte de D6 sur les réponses HTML, y compris les erreurs réelles."""

    def verifier_csp(self, reponse) -> None:
        self.assertEqual(reponse.headers["Content-Security-Policy"], CSP_ATTENDUE)

    def test_politique_exacte_sans_echappatoire(self) -> None:
        self.assertEqual(POLITIQUE_CONTENU, CSP_ATTENDUE)
        self.assertNotIn("unsafe-inline", CSP_ATTENDUE)
        self.assertNotIn("unsafe-eval", CSP_ATTENDUE)

    def test_csp_sur_les_pages_normales(self) -> None:
        for chemin in ("/", "/resultats", "/modeles", "/audios", "/operation"):
            with self.subTest(chemin=chemin):
                reponse = self.client.get(chemin, base_url=self.base_url())

                self.assertEqual(reponse.status_code, 200)
                self.verifier_csp(reponse)

    def test_csp_sur_404(self) -> None:
        reponse = self.client.get("/route-inconnue", base_url=self.base_url())

        self.verifier_page_erreur(reponse, 404)
        self.verifier_csp(reponse)

    def test_csp_sur_405(self) -> None:
        reponse = self.client.get("/dossiers/verifier", base_url=self.base_url())

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

    def test_csp_absente_des_ressources(self) -> None:
        # La CSP décrit ce que le document charge, pas le type de la ressource.
        for chemin in ("/sumi.css", "/app.css", CHEMIN_SCRIPT):
            with self.subTest(chemin=chemin):
                reponse = self.client.get(chemin, base_url=self.base_url())

                self.assertEqual(reponse.status_code, 200)
                self.assertNotIn("Content-Security-Policy", reponse.headers)


if __name__ == "__main__":
    unittest.main()
