"""Tests de la couche web : fabrique, pages, redirections, erreurs et protections."""

from __future__ import annotations

import html
import tempfile
import threading
import unittest
from pathlib import Path

from tests.outils_html import assert_html_seul, assert_sans_script_ni_style
from transcription_bench.operations import CreneauOperations
from transcription_bench.paths import DOSSIERS_DATA
from transcription_bench.web import (
    LIMITE_CORPS_APPLICATION,
    NOM_CHAMP_JETON,
    ConfigApplication,
    ServicesApplication,
    create_app,
)
from transcription_bench.web.app import MESSAGE_DEMANDE_REFUSEE

ADRESSE_LOCALE = "127.0.0.1"
PORT_TEST = 8765
CHAMP_ESPION = "champ"


class SocleWebTest(unittest.TestCase):
    """Outils communs : application temporaire, base URL locale et helpers."""

    def setUp(self) -> None:
        temporaire = tempfile.TemporaryDirectory()
        self.addCleanup(temporaire.cleanup)
        self.dossier_data = Path(temporaire.name) / "data"
        self.creneau = CreneauOperations()
        self.app = self.construire_app()
        self.client = self.app.test_client()

    def services(self, **options) -> ServicesApplication:
        """Services de test partageant le même créneau d'opération."""
        return ServicesApplication(creneau=self.creneau, **options)

    def construire_app(self, services: ServicesApplication | None = None):
        return create_app(
            ConfigApplication(port=PORT_TEST, dossier_data=self.dossier_data),
            services or self.services(),
        )

    def base_url(self, port: int = PORT_TEST) -> str:
        return f"http://{ADRESSE_LOCALE}:{port}"

    def jeton(self, app=None) -> str:
        return (app or self.app).extensions[NOM_CHAMP_JETON]

    def post_autorise(self, chemin: str, donnees=None, jeton=None, app=None, **options):
        """POST local avec le jeton du démarrage courant, sauf valeur imposée."""
        application = app or self.app
        corps = dict(donnees or {})
        corps[NOM_CHAMP_JETON] = self.jeton(application) if jeton is None else jeton
        options.setdefault("base_url", self.base_url())
        return application.test_client().post(chemin, data=corps, **options)

    def corps_formulaire_de_taille(self, taille: int) -> bytes:
        """Corps urlencodé d'exactement `taille` octets, jeton courant compris."""
        prefixe = f"{NOM_CHAMP_JETON}={self.jeton()}&{CHAMP_ESPION}="
        return (prefixe + "a" * (taille - len(prefixe))).encode("ascii")

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

    def verifier_refus_preparation(self, reponse) -> str:
        """Refus 400 d'une demande : page Exécutions, choix restitués (4.3).

        Le refus n'est pas une page d'erreur qui perdrait les sélections : la
        page Exécutions est rendue avec un message fixe et une préparation
        reconstruite depuis les champs soumis.
        """
        self.assertEqual(reponse.status_code, 400)
        self.assertIn("text/html", reponse.headers["Content-Type"])
        corps = reponse.get_data(as_text=True)
        self.assertIn(MESSAGE_DEMANDE_REFUSEE, html.unescape(corps))
        self.assertIn("<h1>Exécutions</h1>", corps)
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
        self.assertEqual(self.app.config["MAX_CONTENT_LENGTH"], 64 * 1024)
        self.assertNotIn("static", self.app.view_functions)
        self.assertEqual(self.app.config["PORT"], PORT_TEST)
        self.assertEqual(self.app.config["DOSSIER_DATA"], str(self.dossier_data))
        self.assertNotIn("Set-Cookie", reponse.headers)

    def test_executions_liste_les_dossiers_de_donnees(self) -> None:
        reponse = self.client.get("/executions", base_url=self.base_url())
        corps = reponse.get_data(as_text=True)

        self.assertEqual(reponse.status_code, 200)
        self.assertEqual(corps.count("(absent)"), len(DOSSIERS_DATA))
        for nom in DOSSIERS_DATA:
            self.assertIn(str(self.dossier_data / nom), corps)
        self.verifier_html_seul(corps)

    def test_executions_echappe_le_contenu_dynamique(self) -> None:
        dossier_piege = self.dossier_data / "<script>alert(1)</script>"
        app = create_app(
            ConfigApplication(port=PORT_TEST, dossier_data=dossier_piege),
            self.services(),
        )
        reponse = app.test_client().get("/executions", base_url=self.base_url())
        corps = reponse.get_data(as_text=True)

        self.assertEqual(reponse.status_code, 200)
        # Sous Windows, pathlib traite les « / » du nom piégé comme des
        # séparateurs : l'attendu est calculé depuis le chemin effectivement
        # joint, et le contenu dynamique ne doit jamais apparaître brut.
        self.assertNotIn("<script>", corps)
        for nom in DOSSIERS_DATA:
            self.assertIn(html.escape(str(dossier_piege / nom)), corps)
        self.verifier_html_seul(corps)

    def test_action_acceptee_deleguee_au_service_injecte(self) -> None:
        appels: list[Path] = []

        def preparer(base: Path) -> dict[str, Path]:
            appels.append(base)
            return {}

        app = self.construire_app(self.services(preparer_dossiers=preparer))
        reponse = self.post_autorise("/dossiers/verifier", app=app)

        self.assertEqual(reponse.status_code, 303)
        self.assertEqual(appels, [self.dossier_data])
        self.assertFalse(self.dossier_data.exists())
        self.assertNotIn("Set-Cookie", reponse.headers)

    def test_post_verifie_puis_redirige_en_303_vers_un_get(self) -> None:
        reponse = self.post_autorise("/dossiers/verifier")

        self.assertEqual(reponse.status_code, 303)
        self.assertEqual(
            reponse.headers["Location"],
            "/executions?action=dossiers-verifies#diagnostics",
        )
        # Corps d'une redirection 303 : pas encore une page de l'interface, donc
        # sans les deux feuilles, mais toujours sans script ni style.
        assert_sans_script_ni_style(self, reponse.get_data(as_text=True))
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


class ProtectionsRequetesTest(SocleWebTest):
    """Contrôles Host, Origin, type, taille et jeton, dans cet ordre."""

    def setUp(self) -> None:
        super().setUp()
        self.appels: list[Path] = []

        def preparer(base: Path) -> dict[str, Path]:
            self.appels.append(base)
            return {}

        self.app = self.construire_app(self.services(preparer_dossiers=preparer))
        self.client = self.app.test_client()

    def test_jetons_differents_a_chaque_demarrage(self) -> None:
        autre = self.construire_app()

        self.assertNotEqual(self.jeton(autre), self.jeton())
        self.assertTrue(self.jeton())

    def test_executions_contient_le_jeton_en_champ_cache(self) -> None:
        corps = self.client.get("/executions", base_url=self.base_url()).get_data(
            as_text=True
        )

        self.assertIn(f'name="{NOM_CHAMP_JETON}"', corps)
        self.assertIn(f'value="{self.jeton()}"', corps)

    def test_host_etranger_mauvais_port_absent_ou_inconnu_refuse(self) -> None:
        for hote in (
            "evil.example:8765",
            "unknown:8765",
            "127.0.0.1:8766",
            f"localhost:{PORT_TEST + 1}",
            "127.0.0.1",
            "",
        ):
            with self.subTest(hote=hote):
                get = self.client.get("/", base_url=self.base_url(), headers={"Host": hote})
                self.verifier_refus(get, 403, self.appels)

                inconnue = self.client.get(
                    "/route-inconnue", base_url=self.base_url(), headers={"Host": hote}
                )
                self.verifier_refus(inconnue, 403, self.appels)

                post = self.post_autorise("/dossiers/verifier", headers={"Host": hote})
                self.verifier_refus(post, 403, self.appels)

    def test_localhost_et_adresse_locale_acceptes(self) -> None:
        for base in (self.base_url(), f"http://localhost:{PORT_TEST}"):
            with self.subTest(base=base):
                page = self.client.get("/resultats", base_url=base)
                self.assertEqual(page.status_code, 200)

                action = self.post_autorise("/dossiers/verifier", base_url=base)
                self.assertEqual(action.status_code, 303)
                self.assertNotIn("Set-Cookie", action.headers)

        self.assertEqual(self.appels, [self.dossier_data, self.dossier_data])

    def test_origine_absente_ou_locale_acceptee(self) -> None:
        for origine in (None, self.base_url(), f"http://localhost:{PORT_TEST}"):
            with self.subTest(origine=origine):
                entetes = {} if origine is None else {"Origin": origine}
                reponse = self.post_autorise("/dossiers/verifier", headers=entetes)
                self.assertEqual(reponse.status_code, 303)

        self.assertEqual(len(self.appels), 3)

    def test_origine_distante_null_mauvais_port_ou_schema_refusee(self) -> None:
        for origine in (
            "null",
            "http://192.168.1.20:8765",
            "http://evil.example",
            f"http://127.0.0.1:{PORT_TEST + 1}",
            f"https://127.0.0.1:{PORT_TEST}",
        ):
            with self.subTest(origine=origine):
                reponse = self.post_autorise(
                    "/dossiers/verifier", headers={"Origin": origine}
                )
                self.verifier_refus(reponse, 403, self.appels)

    def test_type_de_corps_non_pris_en_charge_refuse(self) -> None:
        for type_corps in (
            "application/json",
            "text/plain",
            "multipart/form-data",
            "application/octet-stream",
        ):
            with self.subTest(type_corps=type_corps):
                reponse = self.post_autorise(
                    "/dossiers/verifier",
                    donnees={"x": "1"},
                    headers={"Content-Type": type_corps},
                )
                self.verifier_refus(reponse, 415, self.appels)

    def test_corps_trop_gros_refuse_en_413(self) -> None:
        reponse = self.post_autorise(
            "/dossiers/verifier",
            donnees={CHAMP_ESPION: "a" * LIMITE_CORPS_APPLICATION},
        )

        self.verifier_refus(reponse, 413, self.appels)

    def test_corps_a_la_limite_exacte_accepte(self) -> None:
        reponse = self.client.post(
            "/dossiers/verifier",
            data=self.corps_formulaire_de_taille(LIMITE_CORPS_APPLICATION),
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            base_url=self.base_url(),
        )

        self.assertEqual(reponse.status_code, 303)
        self.assertEqual(self.appels, [self.dossier_data])

        trop_gros = self.client.post(
            "/dossiers/verifier",
            data=self.corps_formulaire_de_taille(LIMITE_CORPS_APPLICATION + 1),
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            base_url=self.base_url(),
        )
        self.verifier_page_erreur(trop_gros, 413)
        self.assertNotIn("Set-Cookie", trop_gros.headers)
        self.assertEqual(self.appels, [self.dossier_data])

    def test_jeton_absent_invalide_ou_precedent_refuse(self) -> None:
        absent = self.client.post(
            "/dossiers/verifier",
            data={CHAMP_ESPION: "1"},
            base_url=self.base_url(),
        )
        self.verifier_refus(absent, 403, self.appels)

        invalide = self.post_autorise("/dossiers/verifier", jeton="mauvais-jeton")
        self.verifier_refus(invalide, 403, self.appels)

        autre = self.construire_app()
        precedent = self.post_autorise("/dossiers/verifier", jeton=self.jeton(autre))
        self.verifier_refus(precedent, 403, self.appels)

    def test_jeton_non_ascii_refuse_sans_erreur_interne(self) -> None:
        reponse = self.post_autorise("/dossiers/verifier", jeton="é" * 16)

        self.verifier_refus(reponse, 403, self.appels)

    def test_post_sur_route_inconnue_sans_jeton_refuse(self) -> None:
        reponse = self.client.post(
            "/route-inconnue", data={CHAMP_ESPION: "1"}, base_url=self.base_url()
        )

        self.verifier_refus(reponse, 403, self.appels)

    def test_ordre_host_origine_type_taille_jeton(self) -> None:
        gros_corps = {CHAMP_ESPION: "a" * (LIMITE_CORPS_APPLICATION + 10)}

        tout_invalide = self.client.post(
            "/dossiers/verifier",
            data=gros_corps,
            headers={
                "Host": "evil.example:8765",
                "Origin": "http://192.168.1.20:8765",
                "Content-Type": "application/json",
            },
            base_url=self.base_url(),
        )
        self.verifier_refus(tout_invalide, 403, self.appels)

        origine_distante = self.post_autorise(
            "/dossiers/verifier",
            donnees=gros_corps,
            jeton="mauvais-jeton",
            headers={"Origin": "http://192.168.1.20:8765", "Content-Type": "application/json"},
        )
        self.verifier_refus(origine_distante, 403, self.appels)

        type_invalide = self.post_autorise(
            "/dossiers/verifier",
            donnees=gros_corps,
            jeton="mauvais-jeton",
            headers={"Content-Type": "application/json"},
        )
        self.verifier_refus(type_invalide, 415, self.appels)

        corps_trop_gros = self.post_autorise(
            "/dossiers/verifier", donnees=gros_corps, jeton="mauvais-jeton"
        )
        self.verifier_refus(corps_trop_gros, 413, self.appels)

        jeton_invalide = self.post_autorise(
            "/dossiers/verifier",
            donnees={CHAMP_ESPION: "1"},
            jeton="mauvais-jeton",
        )
        self.verifier_refus(jeton_invalide, 403, self.appels)

        valide = self.post_autorise(
            "/dossiers/verifier",
            donnees={CHAMP_ESPION: "1"},
            headers={"Origin": self.base_url()},
        )
        self.assertEqual(valide.status_code, 303)
        self.assertEqual(self.appels, [self.dossier_data])


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

    def test_executions_montre_dossiers_et_verification_explicite(self) -> None:
        corps = self.texte("/executions")

        self.assertIn("<h2 id=\"diagnostics\">Dossiers de données</h2>", corps)
        for nom in DOSSIERS_DATA:
            self.assertIn(str(self.dossier_data / nom), corps)
        self.assertIn("(absent)", corps)
        # La vérification reste une action POST explicite, jamais un GET.
        self.assertIn('method="post" action="/dossiers/verifier"', corps)
        self.assertIn("Vérifier les dossiers de données", corps)
        self.assertIn(f'name="{NOM_CHAMP_JETON}"', corps)
        self.verifier_html_seul(corps)
        self.assertFalse(
            self.dossier_data.exists(),
            "une page réelle a créé ou touché les dossiers de données",
        )

    def test_liens_de_navigation_menent_a_des_pages_reelles(self) -> None:
        for chemin in (
            "/resultats",
            "/resultats/comparaison",
            "/executions",
            "/modeles",
            "/moteurs",
            "/audios",
        ):
            with self.subTest(chemin=chemin):
                corps = self.texte(chemin)
                self.assertNotIn("Fonctionnalité non disponible", corps)
                self.verifier_html_seul(corps)

        self.assertIn("Aucune transcription à regrouper", self.texte("/resultats"))
        self.assertIn("créneau global", self.texte("/executions"))
        self.assertIn("Moteurs", self.texte("/moteurs"))
        self.assertIn("Modèles", self.texte("/modeles"))
        self.assertIn("Aucun fichier audio", self.texte("/audios"))
        self.assertFalse(
            self.dossier_data.exists(),
            "une page réelle a créé ou touché les dossiers de données",
        )

    def test_executions_reflete_une_operation_en_cours(self) -> None:
        liberation = threading.Event()
        self.addCleanup(liberation.set)
        self.creneau.demarrer(
            "execution", lambda travailleur: liberation.wait(60), cible="test suivi"
        )

        def terminer() -> None:
            liberation.set()
            self.creneau.arreter(5.0)
            thread = self.creneau.thread_travailleur
            if thread is not None:
                thread.join(10)

        self.addCleanup(terminer)
        corps = self.texte("/executions")

        self.assertIn('id="operation"', corps)
        self.assertIn("État : en cours", corps)
        self.assertIn("Type : exécution", corps)
        self.assertIn("Cible : test suivi", corps)
        self.assertIn("Journal", corps)
        self.assertIn("Actualiser", corps)

    def test_executions_apres_arret_indique_le_refus(self) -> None:
        self.creneau.arreter()

        corps = self.texte("/executions")

        self.assertIn("Arrêt du serveur demandé", corps)


class NavigationEtAnciensLiensTest(SocleWebTest):
    """Navigation à six rubriques, redirections GET fixes et messages bornés."""

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

    def test_ancien_lien_operation_redirige_vers_executions(self) -> None:
        reponse = self.client.get("/operation", base_url=self.base_url())

        self.assertEqual(reponse.status_code, 302)
        self.assertEqual(reponse.headers["Location"], "/executions#operation")
        self.assertNotIn("Set-Cookie", reponse.headers)

    def test_ancien_lien_operation_traduit_seulement_les_codes_d_arret(self) -> None:
        for action in ("arret-demande", "arret-incomplet"):
            with self.subTest(action=action):
                reponse = self.client.get(
                    f"/operation?action={action}", base_url=self.base_url()
                )

                self.assertEqual(reponse.status_code, 302)
                self.assertEqual(
                    reponse.headers["Location"],
                    f"/executions?action={action}#operation",
                )

        for action in ("dossiers-verifies", "inconnu", "", "verification-lancee"):
            with self.subTest(action=action):
                reponse = self.client.get(
                    f"/operation?action={action}", base_url=self.base_url()
                )

                self.assertEqual(reponse.status_code, 302)
                self.assertEqual(reponse.headers["Location"], "/executions#operation")

    def test_ancien_lien_operation_ne_repercute_aucun_autre_parametre(self) -> None:
        reponse = self.client.get(
            "/operation?action=arret-demande&next=http://evil.example/x",
            base_url=self.base_url(),
        )

        self.assertEqual(reponse.status_code, 302)
        self.assertEqual(
            reponse.headers["Location"], "/executions?action=arret-demande#operation"
        )

    def test_redirections_aboutissent_sur_les_nouvelles_destinations(self) -> None:
        for chemin, titre in (
            ("/", "<h1>Résultats</h1>"),
            ("/operation", "<h1>Exécutions</h1>"),
        ):
            with self.subTest(chemin=chemin):
                reponse = self.client.get(
                    chemin, base_url=self.base_url(), follow_redirects=True
                )

                self.assertEqual(reponse.status_code, 200)
                self.assertIn(titre, reponse.get_data(as_text=True))


if __name__ == "__main__":
    unittest.main()
