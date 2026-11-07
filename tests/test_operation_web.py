"""Tests du suivi d'opération dans Exécutions et des mutations sous verrou.

`GET /operation` n'est plus une page : il redirige vers la section `#operation`
d'Exécutions (tâche 3.1). La page Exécutions ne doit rien démarrer, le travail
de fond ne dépend d'aucun contexte de requête et les mutations courtes passent
par le créneau : acceptées au repos, refusées en 409 pendant une opération et en
503 après le passage à l'arrêt.
"""

from __future__ import annotations

import json
import threading
import unittest
from pathlib import Path

from tests.test_web import SocleWebTest
from transcription_bench.execution_moteur import ARRET_AUCUN
from transcription_bench.operations import (
    ETAT_EN_COURS,
    ETAT_LIBRE,
    ETAT_TERMINEE,
    TYPE_EXECUTION,
    TYPE_INSTALLATION,
    OperationEchouee,
)

DELAI = 5.0

# Champs exacts de `GET /executions/etat` : ensemble borné, sans journal brut,
# sans PID, sans jeton anti-CSRF et sans transcription.
CHAMPS_ETAT = frozenset(
    {
        "generation",
        "etat",
        "libelle_etat",
        "type",
        "libelle_type",
        "cible",
        "erreur",
        "actif",
        "url_resultat",
    }
)
IDENTIFIANT_RESULTAT = "20240103-000000-0000dead"


class FauxExecution:
    """Double du service d'exécution : seule la vue du lien de résultat sert.

    Il reproduit le contrat de `ExecutionMoteur.identifiant_resultat` : une
    association publiée pour la génération admise, conservée après la clôture
    et jamais renvoyée pour une autre génération. Aucun processus, aucune E/S.
    """

    def __init__(self) -> None:
        self.associations: dict[int, str] = {}

    def publier(self, generation: int, identifiant: str) -> None:
        self.associations[generation] = identifiant

    def identifiant_resultat(self, generation: int | None) -> str | None:
        if generation is None:
            return None
        return self.associations.get(generation)

    def arreter_execution(self) -> str:
        return ARRET_AUCUN

    def reserver(self) -> None:
        """Aucune réservation réelle dans ce double."""

    def annuler_reservation(self) -> None:
        """Aucune réservation réelle dans ce double."""



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
        reponse = self.client.get("/executions", base_url=self.base_url())
        self.assertEqual(reponse.status_code, 200)
        corps = reponse.get_data(as_text=True)
        self.verifier_html_seul(corps)
        return corps

    def test_ancien_lien_operation_redirige_vers_executions(self) -> None:
        reponse = self.client.get("/operation", base_url=self.base_url())

        self.assertEqual(reponse.status_code, 302)
        self.assertEqual(reponse.headers["Location"], "/executions#operation")
        self.assertNotIn("Set-Cookie", reponse.headers)

    def test_page_executions_libre_par_defaut(self) -> None:
        corps = self.page()

        self.assertIn("<h1>Exécutions</h1>", corps)
        self.assertIn("Actualiser", corps)
        self.assertIn("Nouvelle demande", corps)
        # Design D5 : aucune opération enregistrée n'affiche pas un grand panneau
        # technique vide ; la préparation vient en premier plan.
        self.assertNotIn('id="operation"', corps)
        self.assertNotIn("Aucune opération enregistrée depuis le démarrage.", corps)
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
        self.assertIn('id="operation"', corps)
        self.assertIn("terminée", corps)
        self.assertIn("Début", corps)
        self.assertIn("Fin", corps)
        self.assertIn("Opération terminée.", corps)

    def test_page_apres_arret_indique_l_arret(self) -> None:
        self.creneau.arreter()

        corps = self.page()
        self.assertIn("Arrêt du serveur demandé", corps)

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


class SuiviOperationTest(SocleWebTest):
    """`GET /executions/etat` et lien de résultat du suivi (tâche 3.3, D5).

    L'état est une lecture seule, bornée et non mise en cache ; le lien de
    résultat vient de l'association publiée par l'exécution réellement admise,
    jamais d'une exécution antérieure ni d'un identifiant forgé.
    """

    def setUp(self) -> None:
        super().setUp()
        self.faux = FauxExecution()
        self.app = self.construire_app(self.services(execution=self.faux))
        self.client = self.app.test_client()
        self.fin = threading.Event()
        self.addCleanup(self.liberer)

    def liberer(self) -> None:
        self.fin.set()
        thread = self.creneau.thread_travailleur
        if thread is not None:
            thread.join(DELAI)

    def demarrer(
        self,
        type_operation: str = TYPE_EXECUTION,
        cible: str = "modele-test",
    ) -> None:
        demarre = threading.Event()

        def travail(travailleur) -> None:
            demarre.set()
            if not self.fin.wait(DELAI):
                raise AssertionError("le test n'a pas libéré le travail de fond")

        self.creneau.demarrer(type_operation, travail, cible=cible)
        self.assertTrue(demarre.wait(DELAI), "le travail de fond n'a pas démarré")

    def terminer(self, type_operation: str = TYPE_EXECUTION) -> None:
        self.demarrer(type_operation=type_operation)
        self.fin.set()
        self.creneau.thread_travailleur.join(DELAI)
        self.assertEqual(self.creneau.instantane().etat, ETAT_TERMINEE)

    def generer_et_publier(self, identifiant: str = IDENTIFIANT_RESULTAT) -> int:
        """Génération de l'opération admise, associée à un résultat publié."""
        generation = self.creneau.instantane().generation
        self.faux.publier(generation, identifiant)
        return generation

    def etat(self, **options):
        options.setdefault("base_url", self.base_url())
        return self.client.get("/executions/etat", **options)

    def charge(self) -> dict[str, object]:
        reponse = self.etat()
        self.assertEqual(reponse.status_code, 200)
        self.assertEqual(
            reponse.headers["Content-Type"], "application/json; charset=utf-8"
        )
        self.assertEqual(reponse.headers["Cache-Control"], "no-store")
        self.assertEqual(reponse.headers["X-Content-Type-Options"], "nosniff")
        self.assertNotIn("Set-Cookie", reponse.headers)
        return json.loads(reponse.get_data(as_text=True))

    def page(self) -> str:
        reponse = self.client.get("/executions", base_url=self.base_url())
        self.assertEqual(reponse.status_code, 200)
        corps = reponse.get_data(as_text=True)
        self.verifier_html_seul(corps)
        return corps

    def test_etat_libre_borne_et_sans_lien(self) -> None:
        charge = self.charge()

        self.assertEqual(set(charge), CHAMPS_ETAT)
        self.assertEqual(charge["etat"], ETAT_LIBRE)
        self.assertEqual(charge["libelle_etat"], "libre")
        self.assertIsNone(charge["type"])
        self.assertIsNone(charge["libelle_type"])
        self.assertIsNone(charge["cible"])
        self.assertIsNone(charge["erreur"])
        self.assertFalse(charge["actif"])
        self.assertIsNone(charge["url_resultat"])

    def test_etat_pendant_execution_publie_le_lien(self) -> None:
        self.demarrer(cible="modele.wav")
        self.generer_et_publier()

        charge = self.charge()

        self.assertEqual(charge["etat"], ETAT_EN_COURS)
        self.assertEqual(charge["type"], TYPE_EXECUTION)
        self.assertEqual(charge["libelle_type"], "exécution")
        self.assertEqual(charge["cible"], "modele.wav")
        self.assertTrue(charge["actif"])
        self.assertEqual(charge["url_resultat"], f"/resultats/{IDENTIFIANT_RESULTAT}")
        corps = self.page()
        self.assertIn(f'href="/resultats/{IDENTIFIANT_RESULTAT}"', corps)
        # La page reçoit la même identité et la même adresse que le JSON.
        self.assertIn("Ouvrir le résultat de cette exécution", corps)

    def test_etat_apres_cloture_conserve_le_lien(self) -> None:
        self.demarrer()
        self.generer_et_publier()
        self.fin.set()
        self.creneau.thread_travailleur.join(DELAI)
        self.assertEqual(self.creneau.instantane().etat, ETAT_TERMINEE)

        charge = self.charge()

        self.assertEqual(charge["etat"], ETAT_TERMINEE)
        self.assertFalse(charge["actif"])
        self.assertEqual(charge["url_resultat"], f"/resultats/{IDENTIFIANT_RESULTAT}")
        self.assertIn(f'href="/resultats/{IDENTIFIANT_RESULTAT}"', self.page())

    def test_autre_operation_ne_reprend_pas_l_ancien_lien(self) -> None:
        self.demarrer()
        self.generer_et_publier()
        self.fin.set()
        self.creneau.thread_travailleur.join(DELAI)
        self.assertIn(f'href="/resultats/{IDENTIFIANT_RESULTAT}"', self.page())

        for type_operation in (TYPE_INSTALLATION, "telechargement", TYPE_EXECUTION):
            with self.subTest(type_operation=type_operation):
                self.fin.clear()
                self.demarrer(type_operation=type_operation)
                charge = self.charge()
                self.assertIsNone(charge["url_resultat"])
                self.assertNotIn(
                    f"/resultats/{IDENTIFIANT_RESULTAT}", self.page()
                )
                self.fin.set()
                self.creneau.thread_travailleur.join(DELAI)

    def test_identifiant_forge_ne_produit_aucun_lien(self) -> None:
        for identifiant in (
            "../evil", "a/b", "..", "", "a\\b", "a\x00b", "modele",
            "20240103-000000-0000dead%2f..", "20240103-000000-0000dead%5c..",
        ):
            with self.subTest(identifiant=identifiant):
                self.fin.clear()
                self.demarrer()
                try:
                    generation = self.creneau.instantane().generation
                    self.faux.associations[generation] = identifiant
                    charge = self.charge()
                    self.assertIsNone(charge["url_resultat"])
                    corps = self.page()
                    self.assertIn(
                        '<p class="prose" data-champ="resultat" hidden>', corps
                    )
                    self.assertNotIn('<a data-champ="lien-resultat" href=', corps)
                    self.assertNotIn("evil", corps)
                finally:
                    self.fin.set()
                    self.creneau.thread_travailleur.join(DELAI)

    def test_echec_avant_consignation_sans_lien(self) -> None:
        self.terminer()
        self.generer_et_publier()
        # Une opération suivante n'a aucune consignation publiée pour sa
        # génération : aucun lien n'est proposé, même si un essai antérieur a
        # publié le sien (échec avant stockage couvert par les tests du moteur).
        self.fin.clear()
        self.demarrer()
        charge = self.charge()

        self.assertIsNone(charge["url_resultat"])
        self.assertNotIn('<a data-champ="lien-resultat" href=', self.page())

    def test_etat_ne_divulgue_ni_journal_ni_jeton(self) -> None:
        demarre = threading.Event()

        def travail(travailleur) -> None:
            travailleur.journaliser("texte transcrit confidentiel")
            demarre.set()
            self.fin.wait(DELAI)

        self.creneau.demarrer(TYPE_EXECUTION, travail, cible="modele.wav")
        self.assertTrue(demarre.wait(DELAI))
        self.addCleanup(self.fin.set)

        corps = self.etat().get_data(as_text=True)

        self.assertIn("en cours", corps)
        self.assertNotIn("texte transcrit confidentiel", corps)
        self.assertNotIn(self.jeton(), corps)
        self.assertNotIn("pid", corps.lower())
        self.assertNotIn("journal", corps.lower())

    def test_cible_echappee_dans_le_resume(self) -> None:
        self.demarrer(cible="<script>alert(1)</script>")

        corps = self.page()

        self.assertIn("Cible : &lt;script&gt;alert(1)&lt;/script&gt;", corps)
        self.assertNotIn("<script>alert(1)</script>", corps)

    def test_get_etat_ne_mute_rien(self) -> None:
        journaux_avant = self.creneau.instantane().journal
        generation_avant = self.creneau.instantane().generation

        for _ in range(3):
            self.charge()

        instantane = self.creneau.instantane()
        self.assertEqual(instantane.journal, journaux_avant)
        self.assertEqual(instantane.generation, generation_avant)
        self.assertEqual(instantane.etat, ETAT_LIBRE)
        self.assertFalse(instantane.arrete)
        self.assertIsNone(self.creneau.thread_travailleur)

    def test_post_etat_refuse_sans_mutation(self) -> None:
        sans_jeton = self.client.post(
            "/executions/etat",
            data={"champ": "1"},
            base_url=self.base_url(),
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        self.verifier_page_erreur(sans_jeton, 403)

        avec_jeton = self.post_autorise("/executions/etat")
        self.verifier_page_erreur(avec_jeton, 405)
        self.assertEqual(self.creneau.instantane().etat, ETAT_LIBRE)

    def test_hote_etranger_refuse_sur_l_etat(self) -> None:
        reponse = self.etat(headers={"Host": "evil.example:8765"})

        self.verifier_page_erreur(reponse, 403)
        self.assertNotIn("application/json", reponse.headers["Content-Type"])

    def test_arret_protege_et_sans_effet_sur_une_autre_operation(self) -> None:
        self.demarrer(type_operation=TYPE_INSTALLATION, cible="faster-whisper")

        sans_jeton = self.client.post(
            "/executions/arreter",
            data={"champ": "1"},
            base_url=self.base_url(),
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        self.verifier_page_erreur(sans_jeton, 403)

        origine_etrangere = self.client.post(
            "/executions/arreter",
            data={"jeton_csrf": self.jeton()},
            base_url=self.base_url(),
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "Origin": "http://evil.example:8765",
            },
        )
        self.verifier_page_erreur(origine_etrangere, 403)

        arret = self.post_autorise("/executions/arreter")

        # Aucune exécution active : rien n'est arrêté, l'installation continue
        # et aucun message d'arrêt n'est ajouté.
        self.assertEqual(arret.status_code, 303)
        self.assertEqual(arret.headers["Location"], "/executions#operation")
        self.assertEqual(self.creneau.instantane().etat, ETAT_EN_COURS)
        self.assertEqual(
            self.creneau.instantane().type_operation, TYPE_INSTALLATION
        )
        self.assertNotIn("Arrêt de l'exécution demandé", self.page())

    def test_erreur_visible_hors_du_journal_replie(self) -> None:
        demarre = threading.Event()

        def travail(travailleur) -> None:
            travailleur.journaliser("Préparation")
            demarre.set()
            raise OperationEchouee("moteur absent")

        self.creneau.demarrer(TYPE_EXECUTION, travail, cible="modele.wav")
        self.assertTrue(demarre.wait(DELAI))
        self.creneau.thread_travailleur.join(DELAI)
        self.assertEqual(self.creneau.instantane().etat, "echouee")

        corps = self.page()
        self.assertIn("Erreur : OperationEchouee : moteur absent", corps)
        # L'erreur précède le journal, qui reste un accordéon fermé.
        self.assertLess(
            corps.index("Erreur : OperationEchouee"), corps.index("<h3>Journal</h3>")
        )
        position = corps.index("<summary>Journal complet</summary>")
        self.assertTrue(
            corps[:position].endswith("<details>\n"),
            "journal ouvert alors que l'erreur suffit hors de lui",
        )


if __name__ == "__main__":
    unittest.main()
