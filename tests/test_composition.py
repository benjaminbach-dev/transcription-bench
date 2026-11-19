"""Tests de la composition partagée : services reliés et session du dossier de données."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from engines.registre import creer_registre_fourni
from transcription_bench import composition, paths
from transcription_bench.composition import (
    SessionRefused,
    assemble_services,
    open_data_session,
    open_serve_session,
)
from transcription_bench.consultation_resultats import ConsultationResultats
from transcription_bench.execution_moteur import ExecutionMoteur
from transcription_bench.executions import ConfigurationExecutions
from transcription_bench.gestion_modeles import GestionModeles
from transcription_bench.instance import InstanceDejaActive, VerrouInstance
from transcription_bench.moteurs import InstallationMoteurs
from transcription_bench.operations import CreneauOperations
from transcription_bench.recuperation import EtatAnterieurNonTraitable


def _no_recovery(data_dir: Path) -> None:
    """Récupération factice : rien à clore dans un dossier vide."""


class ServicesAssemblyTest(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name) / "data-projet"

    def test_builds_every_linked_service(self) -> None:
        operations = CreneauOperations()

        services = assemble_services(self.base, operations=operations)

        self.assertIs(services.data_dir, self.base)
        self.assertIs(services.operations, operations)
        self.assertIsInstance(services.engines, InstallationMoteurs)
        self.assertIsInstance(services.models, GestionModeles)
        self.assertIsInstance(services.preparation, ConfigurationExecutions)
        self.assertIsInstance(services.execution, ExecutionMoteur)
        self.assertIsInstance(services.results, ConsultationResultats)
        self.assertFalse(self.base.exists(), "l'assemblage ne doit faire aucune E/S")

    def test_reuses_injected_services_without_rebuilding_them(self) -> None:
        operations = CreneauOperations()
        registry = creer_registre_fourni()
        engines = InstallationMoteurs(self.base, registry, operations)
        models = GestionModeles(self.base, registry, operations, engines)
        results = ConsultationResultats(self.base)

        services = assemble_services(
            self.base,
            operations=operations,
            registry=registry,
            engines=engines,
            models=models,
            results=results,
        )

        self.assertIs(services.registry, registry)
        self.assertIs(services.engines, engines)
        self.assertIs(services.models, models)
        self.assertIs(services.results, results)


class DataSessionTest(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name) / "data-projet"

    def test_lock_held_during_session_then_released_on_close(self) -> None:
        session = open_data_session(self.base, recover=_no_recovery)

        with self.assertRaises(InstanceDejaActive):
            VerrouInstance(self.base).acquerir()
        self.assertIsInstance(session.services.operations, CreneauOperations)
        self.assertTrue(session.close())

        VerrouInstance(self.base).acquerir().liberer()

    def test_recovery_refusal_releases_the_lock(self) -> None:
        def recover(data_dir: Path) -> None:
            raise EtatAnterieurNonTraitable("résultat antérieur non traitable (simulé)")

        with self.assertRaises(SessionRefused) as refusal:
            open_data_session(self.base, recover=recover)

        self.assertTrue(refusal.exception.lock_released)
        self.assertIn("non traitable", str(refusal.exception))
        VerrouInstance(self.base).acquerir().liberer()

    def test_preparation_failure_releases_the_lock_and_propagates(self) -> None:
        with mock.patch.object(
            paths, "preparer_dossiers_data", side_effect=OSError("disque indisponible")
        ):
            with self.assertRaises(OSError):
                open_data_session(self.base, recover=_no_recovery)

        VerrouInstance(self.base).acquerir().liberer()

    def test_lock_already_held_refuses_without_recovery(self) -> None:
        lock = VerrouInstance(self.base).acquerir()
        self.addCleanup(lock.liberer)
        calls: list[Path] = []

        with self.assertRaises(SessionRefused) as refusal:
            open_data_session(self.base, recover=calls.append)

        self.assertEqual(calls, [])
        self.assertTrue(refusal.exception.lock_released)
        self.assertIn("autre instance", str(refusal.exception))

    def test_context_manager_closes_on_exception(self) -> None:
        with self.assertRaisesRegex(ValueError, "simulated"):
            with open_data_session(self.base, recover=_no_recovery):
                with self.assertRaises(InstanceDejaActive):
                    VerrouInstance(self.base).acquerir()
                raise ValueError("simulated")
        VerrouInstance(self.base).acquerir().liberer()

    def test_close_is_idempotent(self) -> None:
        session = open_data_session(self.base, recover=_no_recovery)
        self.assertTrue(session.close())
        self.assertTrue(session.close(), "une seconde clôture renvoie l'issue mémorisée")
        VerrouInstance(self.base).acquerir().liberer()


class ServeSessionTest(unittest.TestCase):
    """Session du serveur : même verrou et récupération, sans créneau ni moteur (D4)."""

    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name) / "data-projet"

    def test_relie_la_consultation_sans_construire_d_action(self) -> None:
        with (
            mock.patch.object(
                composition, "CreneauOperations", side_effect=AssertionError("créneau")
            ),
            mock.patch.object(
                composition, "assemble_services", side_effect=AssertionError("services")
            ),
        ):
            session = open_serve_session(self.base, recover=_no_recovery)

        self.assertIsInstance(session.results, ConsultationResultats)
        with self.assertRaises(InstanceDejaActive):
            VerrouInstance(self.base).acquerir()
        self.assertTrue(session.close())
        VerrouInstance(self.base).acquerir().liberer()

    def test_recuperation_appliquee_sous_le_verrou_avant_la_consultation(self) -> None:
        observations: list[str] = []

        def recover(data_dir: Path) -> None:
            with self.assertRaises(InstanceDejaActive):
                VerrouInstance(self.base).acquerir()
            observations.append(str(data_dir))

        session = open_serve_session(self.base, recover=recover)

        self.assertEqual(observations, [str(self.base)])
        self.assertTrue((self.base / "results").is_dir(), "dossiers préparés")
        self.assertTrue(session.close())
        VerrouInstance(self.base).acquerir().liberer()

    def test_refus_de_recuperation_libere_le_verrou(self) -> None:
        def recover(data_dir: Path) -> None:
            raise EtatAnterieurNonTraitable("résultat antérieur non traitable (simulé)")

        with self.assertRaises(SessionRefused) as refusal:
            open_serve_session(self.base, recover=recover)

        self.assertTrue(refusal.exception.lock_released)
        self.assertIn("non traitable", str(refusal.exception))
        VerrouInstance(self.base).acquerir().liberer()

    def test_verrou_tenu_refuse_sans_recuperation(self) -> None:
        lock = VerrouInstance(self.base).acquerir()
        self.addCleanup(lock.liberer)
        appels: list[Path] = []

        with self.assertRaises(SessionRefused) as refusal:
            open_serve_session(self.base, recover=appels.append)

        self.assertEqual(appels, [])
        self.assertIn("autre instance", str(refusal.exception))


if __name__ == "__main__":
    unittest.main()
