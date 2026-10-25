"""Tests du créneau unique d'opération longue, sans Flask et sans moteur réel.

La synchronisation repose uniquement sur des `threading.Event` et des attentes
bornées : aucun `sleep` de synchronisation. Chaque test libère le travail de fond
dans un nettoyage `addCleanup` et attend la fin du thread avant de rendre la
main, pour ne pas laisser de thread bloqué entre deux tests.
"""

from __future__ import annotations

import dataclasses
import threading
import unittest
from unittest import mock

import flask

from transcription_bench.operations import (
    ETAT_ECHOUEE,
    ETAT_EN_COURS,
    ETAT_INTERROMPUE,
    ETAT_LIBRE,
    ETAT_TERMINEE,
    TYPES_OPERATION,
    CreneauOccupe,
    CreneauOperations,
    ServiceArrete,
)

DELAI = 5.0
ATTENTE_COURTE = 0.2


class CreneauTest(unittest.TestCase):
    """Outils communs : créneau neuf, événements et attentes bornées."""

    def setUp(self) -> None:
        self.creneau = CreneauOperations()
        self.demarre = threading.Event()
        self.fin = threading.Event()
        self.addCleanup(self.liberer_travail)

    def attendre(self, evenement: threading.Event, message: str) -> None:
        self.assertTrue(evenement.wait(DELAI), message)

    def liberer_travail(self) -> None:
        self.fin.set()
        thread = self.creneau.thread_travailleur
        if thread is not None:
            thread.join(DELAI)

    def terminer_thread(self) -> threading.Thread:
        thread = self.creneau.thread_travailleur
        self.assertIsNotNone(thread)
        thread.join(DELAI)
        self.assertFalse(thread.is_alive(), "le thread de fond ne s'est pas terminé")
        return thread

    def demarrer_bloque(
        self,
        type_operation: str = "execution",
        cible: str | None = "audio.wav",
        lignes: tuple[str, ...] = ("Préparation",),
    ) -> None:
        """Démarre une opération dont le travail attend `self.fin`."""

        def travail(travailleur) -> None:
            for ligne in lignes:
                travailleur.journaliser(ligne)
            self.demarre.set()
            if not self.fin.wait(DELAI):
                raise AssertionError("le test n'a pas libéré le travail de fond")

        self.creneau.demarrer(type_operation, travail, cible=cible)
        self.attendre(self.demarre, "le travail de fond n'a pas démarré")


class EtatsCreneauTest(CreneauTest):
    def test_etat_libre_par_defaut(self) -> None:
        instantane = self.creneau.instantane()

        self.assertEqual(instantane.etat, ETAT_LIBRE)
        self.assertFalse(instantane.arrete)
        self.assertIsNone(instantane.type_operation)
        self.assertIsNone(instantane.debut)
        self.assertIsNone(instantane.fin)
        self.assertIsNone(instantane.erreur)
        self.assertEqual(instantane.journal, ())
        self.assertIsNone(self.creneau.thread_travailleur)

    def test_travail_de_fond_dans_un_thread_demon_sans_contexte_flask(self) -> None:
        observations: dict[str, object] = {}

        def travail(travailleur) -> None:
            observations["thread"] = threading.current_thread()
            observations["requete"] = flask.has_request_context()
            observations["application"] = flask.has_app_context()
            travailleur.journaliser("ligne de travail")
            self.demarre.set()

        self.creneau.demarrer("execution", travail, cible="audio.wav")
        self.attendre(self.demarre, "le travail de fond n'a pas démarré")
        thread = self.creneau.thread_travailleur

        self.assertIsNotNone(thread)
        self.assertTrue(thread.daemon)
        self.assertIsNot(thread, threading.main_thread())
        self.assertEqual(observations["thread"], thread)
        self.assertFalse(observations["requete"])
        self.assertFalse(observations["application"])

        self.fin.set()
        self.terminer_thread()
        instantane = self.creneau.instantane()
        self.assertEqual(instantane.etat, ETAT_TERMINEE)
        self.assertEqual(instantane.type_operation, "execution")
        self.assertEqual(instantane.cible, "audio.wav")
        self.assertIsNotNone(instantane.debut)
        self.assertIsNotNone(instantane.fin)
        self.assertIsNone(instantane.erreur)
        self.assertEqual(len(instantane.journal), 3)

    def test_seconde_operation_refusee_quel_que_soit_le_type(self) -> None:
        self.demarrer_bloque()

        for type_operation in TYPES_OPERATION:
            with self.subTest(type_operation=type_operation):
                with self.assertRaises(CreneauOccupe):
                    self.creneau.demarrer(type_operation, lambda travailleur: None)

        appels: list[str] = []
        with self.assertRaises(CreneauOccupe):
            self.creneau.executer_mutation(lambda: appels.append("mutation"))
        self.assertEqual(appels, [])
        self.assertEqual(self.creneau.instantane().type_operation, "execution")

        self.fin.set()
        self.terminer_thread()

        self.creneau.demarrer("installation", lambda travailleur: None)
        self.terminer_thread()
        instantane = self.creneau.instantane()
        self.assertEqual(instantane.etat, ETAT_TERMINEE)
        self.assertEqual(instantane.type_operation, "installation")
        self.assertEqual(len(instantane.journal), 2)

    def test_echec_du_travail_marque_l_echec_et_libere_le_creneau(self) -> None:
        def travail(travailleur) -> None:
            travailleur.journaliser("avant l'échec")
            raise RuntimeError("panne simulée")

        with self.assertLogs("transcription_bench.operations", level="ERROR"):
            self.creneau.demarrer("telechargement", travail, cible="modele")
            self.terminer_thread()

        instantane = self.creneau.instantane()
        self.assertEqual(instantane.etat, ETAT_ECHOUEE)
        self.assertIn("RuntimeError", instantane.erreur or "")
        self.assertIn("panne simulée", instantane.erreur or "")
        self.assertIn("avant l'échec", " ".join(instantane.journal))
        self.assertIn("Opération terminée en échec.", instantane.journal[-1])
        self.assertIsNotNone(instantane.fin)

        self.creneau.demarrer("execution", lambda travailleur: None)
        self.terminer_thread()
        instantane = self.creneau.instantane()
        self.assertEqual(instantane.etat, ETAT_TERMINEE)
        self.assertIsNone(instantane.erreur)
        self.assertNotIn("panne simulée", " ".join(instantane.journal))

    def test_echec_du_demarrage_du_thread_clot_l_operation_et_libere_le_creneau(self) -> None:
        with mock.patch.object(
            threading.Thread, "start", side_effect=RuntimeError("start impossible")
        ):
            with self.assertRaises(RuntimeError):
                self.creneau.demarrer(
                    "installation", lambda travailleur: None, cible="moteur"
                )

        instantane = self.creneau.instantane()
        self.assertEqual(instantane.etat, ETAT_ECHOUEE)
        self.assertIn("RuntimeError", instantane.erreur or "")
        self.assertIn("start impossible", instantane.erreur or "")
        self.assertIsNotNone(instantane.fin)
        self.assertIn("Démarrage du thread de fond impossible.", instantane.journal[-1])
        self.assertIsNone(self.creneau.thread_travailleur)

        self.creneau.demarrer("execution", lambda travailleur: None)
        self.terminer_thread()
        instantane = self.creneau.instantane()
        self.assertEqual(instantane.etat, ETAT_TERMINEE)
        self.assertIsNone(instantane.erreur)
        self.assertTrue(self.creneau.arreter())

    def test_type_operation_inconnu_refuse_sans_demarrage(self) -> None:
        with self.assertRaises(ValueError):
            self.creneau.demarrer("transcription", lambda travailleur: None)

        self.assertEqual(self.creneau.instantane().etat, ETAT_LIBRE)
        self.assertIsNone(self.creneau.thread_travailleur)

    def test_instantane_immuable_pris_sous_verrou(self) -> None:
        self.demarrer_bloque(lignes=("première ligne",))
        instantane = self.creneau.instantane()

        self.assertIsInstance(instantane.journal, tuple)
        self.assertEqual(instantane.etat, ETAT_EN_COURS)
        self.assertIn("première ligne", " ".join(instantane.journal))
        with self.assertRaises(dataclasses.FrozenInstanceError):
            instantane.etat = ETAT_TERMINEE  # type: ignore[misc]

        self.fin.set()
        self.terminer_thread()
        final = self.creneau.instantane()

        self.assertEqual(instantane.etat, ETAT_EN_COURS)
        self.assertEqual(len(instantane.journal), 2)
        self.assertGreater(len(final.journal), len(instantane.journal))

    def test_horloge_par_defaut_horodate_journal_et_etats(self) -> None:
        self.creneau.demarrer("execution", lambda travailleur: None)
        self.terminer_thread()

        instantane = self.creneau.instantane()
        self.assertRegex(instantane.debut or "", r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}")
        self.assertRegex(instantane.fin or "", r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}")
        self.assertTrue(instantane.journal[0].startswith(instantane.debut or "?"))

    def test_horloge_injectable(self) -> None:
        creneau = CreneauOperations(horloge=lambda: "T0")

        creneau.demarrer("execution", lambda travailleur: None)
        creneau.thread_travailleur.join(DELAI)

        instantane = creneau.instantane()
        self.assertEqual(instantane.debut, "T0")
        self.assertEqual(instantane.fin, "T0")
        self.assertTrue(instantane.journal[0].startswith("T0 "))


class ArretCreneauTest(CreneauTest):
    def test_arret_immediat_refuse_operations_mutations_et_publications(self) -> None:
        self.assertTrue(self.creneau.arreter())

        for type_operation in TYPES_OPERATION:
            with self.subTest(type_operation=type_operation):
                with self.assertRaises(ServiceArrete):
                    self.creneau.demarrer(type_operation, lambda travailleur: None)

        appels: list[str] = []
        with self.assertRaises(ServiceArrete):
            self.creneau.executer_mutation(lambda: appels.append("mutation"))
        with self.assertRaises(ServiceArrete):
            self.creneau.publier_pret(lambda: appels.append("marqueur prêt"))
        self.assertEqual(appels, [])
        self.assertIsNone(self.creneau.thread_travailleur)

        self.assertTrue(self.creneau.arreter())
        instantane = self.creneau.instantane()
        self.assertTrue(instantane.arrete)
        self.assertEqual(instantane.etat, ETAT_LIBRE)

    def test_arret_pendant_operation_refuse_mutation_et_publication(self) -> None:
        appels: list[str] = []
        self.demarrer_bloque()

        self.assertFalse(self.creneau.arreter(delai=ATTENTE_COURTE))
        instantane = self.creneau.instantane()
        self.assertEqual(instantane.etat, ETAT_EN_COURS)
        self.assertTrue(instantane.arrete)
        self.assertIn("Arrêt demandé pendant l'opération.", " ".join(instantane.journal))

        with self.assertRaises(ServiceArrete):
            self.creneau.demarrer("installation", lambda travailleur: None)
        with self.assertRaises(ServiceArrete):
            self.creneau.executer_mutation(lambda: appels.append("mutation"))
        with self.assertRaises(ServiceArrete):
            self.creneau.publier_pret(lambda: appels.append("marqueur prêt"))
        self.assertEqual(appels, [])

        self.fin.set()
        self.terminer_thread()
        instantane = self.creneau.instantane()
        self.assertEqual(instantane.etat, ETAT_INTERROMPUE)
        self.assertIn("Opération interrompue par l'arrêt du serveur.", instantane.journal[-1])

    def test_operation_finie_pendant_arret_ne_publie_aucun_marqueur_pret(self) -> None:
        publications: list[str] = []
        autoriser = threading.Event()
        refuse = threading.Event()

        def travail(travailleur) -> None:
            self.demarre.set()
            if not autoriser.wait(DELAI):
                raise AssertionError("le test n'a pas autorisé la publication")
            try:
                travailleur.publier_pret(lambda: publications.append("prêt"))
            except ServiceArrete:
                travailleur.journaliser("Publication refusée après l'arrêt.")
                refuse.set()

        self.creneau.demarrer("installation", travail, cible="moteur factice")
        self.attendre(self.demarre, "le travail de fond n'a pas démarré")

        self.assertFalse(self.creneau.arreter(delai=ATTENTE_COURTE))
        autoriser.set()
        self.attendre(refuse, "la publication aurait dû être refusée par l'arrêt")

        self.terminer_thread()
        self.assertEqual(publications, [])
        instantane = self.creneau.instantane()
        self.assertEqual(instantane.etat, ETAT_INTERROMPUE)
        self.assertIn("Publication refusée après l'arrêt.", " ".join(instantane.journal))

    def test_arret_idempotent_ne_repete_pas_le_journal(self) -> None:
        self.demarrer_bloque()

        self.assertFalse(self.creneau.arreter(delai=ATTENTE_COURTE))
        self.assertFalse(self.creneau.arreter(delai=ATTENTE_COURTE))
        journal = " ".join(self.creneau.instantane().journal)
        self.assertEqual(journal.count("Arrêt demandé pendant l'opération."), 1)
        self.assertEqual(journal.count("Opération non close"), 1)

        self.fin.set()
        self.terminer_thread()
        self.assertTrue(self.creneau.arreter())
        journal = " ".join(self.creneau.instantane().journal)
        self.assertEqual(journal.count("interrompue par l'arrêt du serveur."), 1)
        self.assertEqual(journal.count("Arrêt demandé pendant l'opération."), 1)

    def test_arret_apres_operation_terminee_conserve_l_etat_final(self) -> None:
        self.creneau.demarrer("execution", lambda travailleur: travailleur.journaliser("fini"))
        self.terminer_thread()

        self.assertTrue(self.creneau.arreter())

        instantane = self.creneau.instantane()
        self.assertEqual(instantane.etat, ETAT_TERMINEE)
        self.assertTrue(instantane.arrete)
        self.assertNotIn("Arrêt demandé pendant l'opération.", instantane.journal)

    def test_publication_et_mutation_partagent_le_meme_verrou(self) -> None:
        resultats: list[str] = []
        refus: list[str] = []
        publie = threading.Event()
        libere = threading.Event()
        tentee = threading.Event()
        terminee = threading.Event()

        def publication() -> None:
            publie.set()
            if not libere.wait(DELAI):
                raise AssertionError("le test n'a pas libéré la publication")
            resultats.append("publication terminée")

        def travail(travailleur) -> None:
            travailleur.publier_pret(publication)
            if not self.fin.wait(DELAI):
                raise AssertionError("le test n'a pas libéré le travail de fond")

        def mutation() -> None:
            tentee.set()
            try:
                self.creneau.executer_mutation(lambda: resultats.append("mutation exécutée"))
            except CreneauOccupe:
                refus.append("occupé")
            finally:
                terminee.set()

        sonde = threading.Thread(target=mutation, daemon=True)

        def liberer_sonde() -> None:
            libere.set()
            if sonde.is_alive():
                sonde.join(DELAI)

        self.addCleanup(liberer_sonde)

        self.creneau.demarrer("telechargement", travail)
        self.attendre(publie, "la publication n'a pas commencé")
        sonde.start()
        self.attendre(tentee, "la mutation n'a pas été tentée")

        self.assertFalse(
            terminee.wait(ATTENTE_COURTE),
            "la mutation ne doit pas progresser pendant que la publication tient le verrou",
        )
        self.assertEqual(resultats, [])

        libere.set()
        self.attendre(terminee, "la mutation n'a pas repris après la publication")
        self.assertEqual(resultats, ["publication terminée"])
        self.assertEqual(refus, ["occupé"])

        self.fin.set()
        self.terminer_thread()
        self.assertEqual(self.creneau.instantane().etat, ETAT_TERMINEE)


if __name__ == "__main__":
    unittest.main()
