"""Tests de la couche web : fabrique, pages, redirections, erreurs et protections."""

from __future__ import annotations

import contextlib
import html
import io
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tests.outils_html import assert_html_seul
from transcription_bench.execution_moteur import ExecutionMoteur
from transcription_bench.executions import ConfigurationExecutions
from transcription_bench.gestion_modeles import GestionModeles
from transcription_bench.moteurs import InstallationMoteurs
from transcription_bench.operations import CreneauOperations
from transcription_bench.paths import NOM_DOSSIER_RESULTATS
from transcription_bench.web import (
    ConfigApplication,
    ServicesApplication,
    create_app,
)

ADRESSE_LOCALE = "127.0.0.1"
PORT_TEST = 8765
CHAMP_ESPION = "champ"

# Pages d'action supprimées (change `alleger-interface-web`, design D1) et script
# `/app.js` retiré (tâche 1.3, design D2) : 404.
ROUTES_SUPPRIMEES_GET = (
    "/audios",
    "/modeles",
    "/moteurs",
    "/moteurs/factice/journal",
    "/operation",
    "/executions/etat",
    "/app.js",
)
ROUTES_SUPPRIMEES_POST = (
    "/executions/verifier",
    "/executions/lancer",
    "/executions/arreter",
    "/modeles/verifier",
    "/modeles/telecharger",
    "/modeles/supprimer",
    "/moteurs/factice/installer",
    "/dossiers/verifier",
)
# Routes conservées : toute méthode autre que GET et HEAD y reçoit 405.
# Routes de consultation conservées, dynamiques comprises : identifiant et empreinte
# fictifs, le contrôle Host précède toute recherche.
ROUTES_CONSERVEES = (
    "/",
    "/resultats",
    "/resultats/absent",
    "/resultats/aide",
    "/resultats/comparaison",
    f"/resultats/comparaison/{'a' * 64}",
    "/executions",
    "/extractions",
    "/extractions/absent",
    "/extractions/aide",
    "/extractions/comparaison",
    f"/extractions/comparaison/{'a' * 64}",
    "/sumi.css",
    "/app.css",
)
HOTES_ETRANGERS = (
    "evil.example:8765",
    "unknown:8765",
    "127.0.0.1:8766",
    f"localhost:{PORT_TEST + 1}",
    "127.0.0.1",
    "",
)
METHODES_REFUSEES = ("POST", "PUT", "PATCH", "DELETE", "OPTIONS")


class SocleWebTest(unittest.TestCase):
    """Outils communs : application temporaire, base URL locale et helpers."""

    def setUp(self) -> None:
        temporaire = tempfile.TemporaryDirectory()
        self.addCleanup(temporaire.cleanup)
        self.dossier_data = Path(temporaire.name) / "data"
        self.app = self.construire_app()
        self.client = self.app.test_client()

    def construire_app(self, services: ServicesApplication | None = None):
        return create_app(
            ConfigApplication(port=PORT_TEST, dossier_data=self.dossier_data),
            services or ServicesApplication(),
        )

    def base_url(self, port: int = PORT_TEST) -> str:
        return f"http://{ADRESSE_LOCALE}:{port}"

    def verifier_html_seul(self, corps: str) -> None:
        assert_html_seul(self, corps)

    def verifier_page_erreur(self, reponse, code: int) -> str:
        self.assertEqual(reponse.status_code, code)
        self.assertIn("text/html", reponse.headers["Content-Type"])
        corps = reponse.get_data(as_text=True)
        self.assertIn(f"Erreur {code}", corps)
        self.assertNotIn("RuntimeError", corps)
        self.verifier_html_seul(corps)
        return corps

    def verifier_refus(self, reponse, code: int, appels: list[Path]) -> str:
        """Vérifie un refus HTML, sans cookie ni action déléguée."""
        corps = self.verifier_page_erreur(reponse, code)
        self.assertNotIn("Set-Cookie", reponse.headers)
        self.assertEqual(appels, [])
        return corps


class WebTest(SocleWebTest):
    def test_fabrique_sans_effet_de_bord(self) -> None:
        reponse = self.client.get("/resultats", base_url=self.base_url())

        self.assertEqual(reponse.status_code, 200)
        self.assertFalse(self.dossier_data.exists())
        self.assertFalse(self.app.debug)
        self.assertFalse(self.app.config["DEBUG"])
        self.assertIsNone(self.app.config["MAX_CONTENT_LENGTH"])
        self.assertNotIn("static", self.app.view_functions)
        self.assertEqual(self.app.config["PORT"], PORT_TEST)
        self.assertEqual(self.app.config["DOSSIER_DATA"], str(self.dossier_data))
        self.assertNotIn("Set-Cookie", reponse.headers)

    def test_executions_est_l_historique_sans_action(self) -> None:
        reponse = self.client.get("/executions", base_url=self.base_url())
        corps = reponse.get_data(as_text=True)

        self.assertEqual(reponse.status_code, 200)
        self.assertIn('<h1 id="historique">Historique</h1>', corps)
        self.assertIn("<title>Historique — transcription-bench</title>", corps)
        self.assertNotIn("<form", corps)
        self.assertNotIn("Dossiers de données", corps)
        self.assertNotIn("(absent)", corps)
        self.verifier_html_seul(corps)

    def test_executions_echappe_le_contenu_dynamique(self) -> None:
        dossier_piege = self.dossier_data / "<script>alert(1)</script>"
        app = create_app(
            ConfigApplication(port=PORT_TEST, dossier_data=dossier_piege),
            ServicesApplication(),
        )
        reponse = app.test_client().get("/executions", base_url=self.base_url())
        corps = reponse.get_data(as_text=True)

        self.assertEqual(reponse.status_code, 200)
        # Sous Windows, pathlib traite les « / » du nom piégé comme des
        # séparateurs : l'attendu est calculé depuis le chemin effectivement
        # joint, et le contenu dynamique ne doit jamais apparaître brut.
        self.assertNotIn("<script>", corps)
        self.assertIn(html.escape(str(dossier_piege / NOM_DOSSIER_RESULTATS)), corps)
        self.verifier_html_seul(corps)

    def test_route_inconnue_rend_une_page_404(self) -> None:
        reponse = self.client.get("/route-inconnue", base_url=self.base_url())

        self.verifier_page_erreur(reponse, 404)

    def test_route_statique_absente(self) -> None:
        # Les 404 des chemins statiques (`/static/base.css`, `/sumi.min.css`,
        # remontées d'arborescence) sont couverts par
        # `tests/test_feuilles.py::RoutesFeuillesTest` : aucun service de
        # fichiers arbitraires, seul le routeur et les pages d'erreur répondent.
        reponse = self.client.get("/route/inexistante", base_url=self.base_url())

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


class RoutesRetireesTest(SocleWebTest):
    """Pages d'action supprimées (404), méthodes refusées (405) et services non appelés."""

    def test_pages_d_action_supprimees_repondent_404(self) -> None:
        for chemin in ROUTES_SUPPRIMEES_GET:
            with self.subTest(chemin=chemin):
                reponse = self.client.get(chemin, base_url=self.base_url())

                self.verifier_page_erreur(reponse, 404)

    def test_posts_d_action_supprimes_repondent_404(self) -> None:
        for chemin in ROUTES_SUPPRIMEES_POST:
            with self.subTest(chemin=chemin):
                reponse = self.client.post(chemin, base_url=self.base_url())

                self.verifier_page_erreur(reponse, 404)

    def test_toute_methode_sur_une_route_supprimee_repond_404(self) -> None:
        for chemin in ROUTES_SUPPRIMEES_GET + ROUTES_SUPPRIMEES_POST:
            for methode in METHODES_REFUSEES:
                with self.subTest(chemin=chemin, methode=methode):
                    reponse = self.client.open(
                        chemin, method=methode, base_url=self.base_url()
                    )

                    self.verifier_page_erreur(reponse, 404)

    def test_methodes_autres_que_get_et_head_refusees_en_405(self) -> None:
        for chemin in ROUTES_CONSERVEES:
            for methode in METHODES_REFUSEES:
                with self.subTest(chemin=chemin, methode=methode):
                    reponse = self.client.open(
                        chemin, method=methode, base_url=self.base_url()
                    )

                    self.verifier_page_erreur(reponse, 405)
                    autorisees = {
                        m.strip() for m in reponse.headers["Allow"].split(",")
                    }
                    self.assertEqual(autorisees, {"GET", "HEAD"})

    def test_get_et_head_restent_servis_sur_les_routes_conservees(self) -> None:
        for chemin in ("/resultats", "/executions", "/sumi.css", "/app.css"):
            for methode in ("GET", "HEAD"):
                with self.subTest(chemin=chemin, methode=methode):
                    reponse = self.client.open(
                        chemin, method=methode, base_url=self.base_url()
                    )

                    self.assertEqual(reponse.status_code, 200)

    def test_fabrique_et_routes_ne_construisent_aucun_service_d_action(self) -> None:
        """Le serveur n'instancie ni créneau, ni moteur, ni préparation (D4).

        Les constructeurs sont espionnés pendant la fabrique et les requêtes : la
        consultation des résultats suffit, aucune construction d'action n'a lieu.
        """
        construits: list[str] = []

        def espionner(classe: type):
            def initialiser(self, *arguments, **options) -> None:
                construits.append(classe.__name__)

            return mock.patch.object(classe, "__init__", initialiser)

        with contextlib.ExitStack() as pile:
            for classe in (
                CreneauOperations,
                InstallationMoteurs,
                GestionModeles,
                ConfigurationExecutions,
                ExecutionMoteur,
            ):
                pile.enter_context(espionner(classe))
            client = self.construire_app().test_client()
            for chemin in ROUTES_CONSERVEES + ROUTES_SUPPRIMEES_GET:
                client.get(chemin, base_url=self.base_url())
            for chemin in ROUTES_SUPPRIMEES_POST:
                client.post(chemin, base_url=self.base_url())

        self.assertEqual(construits, [])


class ProtectionsRequetesTest(SocleWebTest):
    """Contrôle Host sur chaque route, puis refus de toute méthode modificatrice."""

    def test_pages_conservees_sans_champ_jeton(self) -> None:
        for chemin in ("/resultats", "/resultats/aide", "/resultats/comparaison", "/executions"):
            with self.subTest(chemin=chemin):
                corps = self.client.get(chemin, base_url=self.base_url()).get_data(
                    as_text=True
                )

                self.assertNotIn("csrf", corps.lower())

    def test_host_etranger_refuse_sur_chaque_route_conservee(self) -> None:
        for chemin in ROUTES_CONSERVEES + ("/route-inconnue",):
            for hote in HOTES_ETRANGERS:
                for methode in ("GET", "POST"):
                    with self.subTest(chemin=chemin, hote=hote, methode=methode):
                        reponse = self.client.open(
                            chemin,
                            method=methode,
                            base_url=self.base_url(),
                            headers={"Host": hote},
                        )

                        self.verifier_refus(reponse, 403, [])

    def test_localhost_et_adresse_locale_acceptes(self) -> None:
        for base in (self.base_url(), f"http://localhost:{PORT_TEST}"):
            with self.subTest(base=base):
                page = self.client.get("/resultats", base_url=base)
                self.assertEqual(page.status_code, 200)

                methode = self.client.post("/resultats", base_url=base)
                self.verifier_page_erreur(methode, 405)
                self.assertNotIn("Set-Cookie", methode.headers)

    def test_post_formulaire_refuse_en_405_sans_action(self) -> None:
        reponse = self.client.post(
            "/resultats", data={CHAMP_ESPION: "1"}, base_url=self.base_url()
        )

        self.verifier_page_erreur(reponse, 405)
        self.assertNotIn("Set-Cookie", reponse.headers)

    def test_methode_refusee_ne_lit_pas_le_corps(self) -> None:
        """Revue du lot 1 : le refus arrive avant toute lecture du corps reçu.

        Un flux d'entrée hostile qui lèverait une exception à la lecture ne doit
        jamais être lu : la réponse reste un refus 404 ou 405, jamais une erreur
        interne causée par ce flux.
        """

        class FluxHostile(io.BytesIO):
            def read(self, size: int = -1) -> bytes:
                raise RuntimeError("corps lu")

        for chemin in ("/resultats", "/executions", "/extractions", "/extractions/comparaison", "/route-inconnue"):
            with self.subTest(chemin=chemin):
                reponse = self.client.post(
                    chemin,
                    input_stream=FluxHostile(),
                    content_length=10,
                    content_type="application/x-www-form-urlencoded",
                    base_url=self.base_url(),
                )

                self.assertIn(reponse.status_code, (404, 405))


class PagesReellesTest(SocleWebTest):
    """Entrée directe, pages réelles et liens utiles, sans effet de bord."""

    def texte(self, chemin: str) -> str:
        reponse = self.client.get(chemin, base_url=self.base_url())
        self.assertEqual(reponse.status_code, 200, chemin)
        return html.unescape(reponse.get_data(as_text=True))

    def test_resultats_est_l_entree_et_renvoie_a_l_historique(self) -> None:
        corps = self.texte("/resultats")

        self.assertIn("<h1>Résultats</h1>", corps)
        self.assertIn('href="/resultats/comparaison"', corps)
        self.assertIn('href="/resultats/aide"', corps)
        # L'historique complet a quitté Résultats pour Exécutions (tâche 3.1) :
        # un lien secondaire y mène, sans recréer de page d'accueil.
        self.assertIn('href="/executions#historique"', corps)
        contenu = corps.split("<main>", 1)[1]
        self.assertNotIn('href="/"', contenu, "plus de lien interne vers l'accueil")
        self.verifier_html_seul(corps)

    def test_liens_de_navigation_menent_a_des_pages_reelles(self) -> None:
        for chemin in ("/resultats", "/resultats/comparaison", "/executions"):
            with self.subTest(chemin=chemin):
                corps = self.texte(chemin)
                self.assertNotIn("Fonctionnalité non disponible", corps)
                self.verifier_html_seul(corps)

        self.assertIn("Aucune transcription à regrouper", self.texte("/resultats"))
        self.assertIn("Aucune exécution enregistrée", self.texte("/executions"))
        navigation = self.texte("/resultats").split("<nav", 1)[1].split("</nav>", 1)[0]
        for chemin_supprime in ('href="/modeles"', 'href="/moteurs"', 'href="/audios"'):
            self.assertNotIn(chemin_supprime, navigation)
        self.assertFalse(
            self.dossier_data.exists(),
            "une page réelle a créé ou touché les dossiers de données",
        )


class NavigationEtAnciensLiensTest(SocleWebTest):
    """Entrée directe, anciens liens d'action en 404 et messages bornés."""

    def test_racine_redirige_vers_resultats(self) -> None:
        for chemin in ("/", "/?next=/modeles", "/?action=dossiers-verifies"):
            with self.subTest(chemin=chemin):
                reponse = self.client.get(chemin, base_url=self.base_url())

                self.assertEqual(reponse.status_code, 302)
                self.assertEqual(reponse.headers["Location"], "/resultats")
                self.assertNotIn("Set-Cookie", reponse.headers)

    def test_racine_ne_repercute_aucune_redirection_libre(self) -> None:
        for cible in ("/modeles", "http://evil.example/x", "//evil.example"):
            with self.subTest(cible=cible):
                reponse = self.client.get(
                    f"/?next={cible}", base_url=self.base_url()
                )

                self.assertEqual(reponse.status_code, 302)
                self.assertEqual(reponse.headers["Location"], "/resultats")

    def test_ancien_lien_operation_repond_404_sans_demarrer_d_operation(self) -> None:
        for chemin in ("/operation", "/operation?action=arret-demande"):
            with self.subTest(chemin=chemin):
                reponse = self.client.get(chemin, base_url=self.base_url())

                self.verifier_page_erreur(reponse, 404)
                self.assertNotIn("Set-Cookie", reponse.headers)
        self.assertFalse(self.dossier_data.exists(), "aucune opération ni dossier créé")

    def test_redirection_racine_aboutit_sur_resultats(self) -> None:
        reponse = self.client.get("/", base_url=self.base_url(), follow_redirects=True)

        self.assertEqual(reponse.status_code, 200)
        corps = reponse.get_data(as_text=True)
        self.assertIn("<h1>Résultats</h1>", corps)
        # Premier démarrage sans résultat : l'état vide renvoie à la CLI.
        self.assertIn("« run start »", corps)


if __name__ == "__main__":
    unittest.main()
