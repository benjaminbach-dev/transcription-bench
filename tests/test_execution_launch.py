"""Tests de l'enchaînement de lancement partagé (tâche 1.6).

Couverture volontairement restreinte aux risques propres à l'extraction, non
couverts par ailleurs :

- passage des champs de formulaire à la validation (ordre des audios,
  réglages, valeurs par défaut, champ inconnu ignoré) ;
- ordre `verifier_lancable`, `reserver`, admission, avec annulation de la
  réservation si l'admission est refusée (y compris interruption) ;
- réservation préexistante ni annulée ni remplacée ;
- arrêt demandé pendant l'admission trouve la réservation (tâche 1.6).

Le reste est couvert par les tests existants : refus des champs répétés
(`tests/test_executions.py`, fonction et route), moteur non prêt sans
réservation, admission refusée sans état résiduel et réservation préexistante
conservée pendant une exécution réelle (`tests/test_execution_moteur.py`,
`RoutesExecutionTest`). Aucun moteur réel, aucun processus, aucun réseau :
les services sont des enregistreurs, sauf le service d'exécution réel du test
d'arrêt, qui ne lance jamais de processus moteur (réservation seule).
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from engines.registre import creer_registre_fourni
from transcription_bench.execution_launch import (
    ExecutionAlreadyReserved,
    launch_execution,
    validate_execution_fields,
)
from transcription_bench.execution_moteur import (
    ARRET_DEMANDE,
    ExecutionImpossible,
    ExecutionMoteur,
)
from transcription_bench.operations import TYPE_EXECUTION, CreneauOccupe, ServiceArrete


def fake_request() -> SimpleNamespace:
    """Demande minimale : seuls `moteur` et `identifiant` sont lus par l'enchaînement."""
    return SimpleNamespace(moteur="factice", identifiant="demande-test")


class FakeConfigurationExecutions:
    """Enregistre les arguments de `valider` et renvoie une demande fixe."""

    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []
        self.request = fake_request()

    def valider(self, **arguments: object) -> SimpleNamespace:
        self.calls.append(arguments)
        return self.request


class FakeExecutionMoteur:
    """Enregistre l'ordre des appels de l'enchaînement, sans processus."""

    def __init__(
        self,
        journal: list[str],
        *,
        verification_error: BaseException | None = None,
        reservation_error: BaseException | None = None,
    ) -> None:
        self.journal = journal
        self.verification_error = verification_error
        self.reservation_error = reservation_error

    def verifier_lancable(self, request: object) -> None:
        self.journal.append("verifier")
        if self.verification_error is not None:
            raise self.verification_error

    def reserver(self) -> None:
        self.journal.append("reserver")
        if self.reservation_error is not None:
            raise self.reservation_error

    def lancer(self, request: object, worker: object) -> None:
        self.journal.append("lancer")

    def annuler_reservation(self) -> None:
        self.journal.append("annuler")


class FakeOperations:
    """Enregistre l'admission ; exécute le travail en ligne, ou lève `refusal`."""

    def __init__(self, journal: list[str], refusal: BaseException | None = None) -> None:
        self.journal = journal
        self.refusal = refusal
        self.calls: list[tuple[str, str | None]] = []

    def demarrer(
        self,
        operation_type: str,
        work: object,
        *,
        cible: str | None = None,
    ) -> None:
        self.journal.append("admission")
        self.calls.append((operation_type, cible))
        if self.refusal is not None:
            raise self.refusal
        work(None)


class ValidateExecutionFieldsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.configuration = FakeConfigurationExecutions()

    def test_fields_are_passed_to_validation_in_form_order(self) -> None:
        fields = [
            ("modele", "factice/a"),
            ("audios", "b.wav"),
            ("audios", "a.wav"),
            ("threads", "2"),
            ("reglage_fenetre", "3"),
            ("moteur", "factice"),
            ("jeton_csrf", "non lu ici"),
        ]

        request = validate_execution_fields(self.configuration, fields)

        self.assertIs(request, self.configuration.request)
        self.assertEqual(
            self.configuration.calls,
            [
                {
                    "modele": "factice/a",
                    "audios": ["b.wav", "a.wav"],
                    "threads": "2",
                    "reglages": {"fenetre": "3"},
                    "moteur": "factice",
                }
            ],
        )

    def test_missing_fields_use_form_defaults(self) -> None:
        validate_execution_fields(self.configuration, [])

        self.assertEqual(
            self.configuration.calls,
            [
                {
                    "modele": "",
                    "audios": [],
                    "threads": "",
                    "reglages": {},
                    "moteur": None,
                }
            ],
        )


class LaunchExecutionOrderTest(unittest.TestCase):
    def setUp(self) -> None:
        self.journal: list[str] = []
        self.configuration = FakeConfigurationExecutions()

    def launch(
        self,
        execution: FakeExecutionMoteur,
        operations: FakeOperations,
        fields: list[tuple[str, str]] | None = None,
    ) -> SimpleNamespace:
        return launch_execution(
            self.configuration,
            execution,
            operations,
            [("modele", "factice/a")] if fields is None else fields,
        )

    def test_admitted_launch_checks_then_reserves_then_admits(self) -> None:
        execution = FakeExecutionMoteur(self.journal)
        operations = FakeOperations(self.journal)

        request = self.launch(execution, operations)

        self.assertIs(request, self.configuration.request)
        self.assertEqual(
            self.journal, ["verifier", "reserver", "admission", "lancer"]
        )
        self.assertEqual(operations.calls, [(TYPE_EXECUTION, "demande-test")])

    def test_existing_reservation_is_neither_replaced_nor_cancelled(self) -> None:
        execution = FakeExecutionMoteur(
            self.journal,
            reservation_error=ExecutionImpossible("une exécution est déjà active"),
        )
        operations = FakeOperations(self.journal)

        with self.assertRaises(ExecutionAlreadyReserved):
            self.launch(execution, operations)

        # La réservation n'est pas celle de cet appel : ni annulée, ni admise.
        self.assertEqual(self.journal, ["verifier", "reserver"])

    def test_refused_admission_cancels_the_reservation(self) -> None:
        refusals = (
            CreneauOccupe("occupé"),
            ServiceArrete(),
            KeyboardInterrupt(),
        )
        for refusal in refusals:
            with self.subTest(refusal=type(refusal).__name__):
                self.journal.clear()
                execution = FakeExecutionMoteur(self.journal)
                operations = FakeOperations(self.journal, refusal=refusal)

                with self.assertRaises(type(refusal)):
                    self.launch(execution, operations)

                self.assertEqual(
                    self.journal,
                    ["verifier", "reserver", "admission", "annuler"],
                )


class StopWithReservationTest(unittest.TestCase):
    """Arrêt sans réservation manquante, avec le service d'exécution réel.

    Le service est réel mais n'ouvre aucun processus : `reserver` crée seulement
    le handle du moteur, et `arreter_execution` le termine sans effet.
    """

    def setUp(self) -> None:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        # Le registre fourni contient le moteur factice ; `moteurs` n'est lu
        # que pour les moteurs réels, jamais dans ces tests.
        self.execution = ExecutionMoteur(
            Path(directory.name),
            creer_registre_fourni(),
            None,  # type: ignore[arg-type]
            racine_temporaire=Path(directory.name) / "travail",
        )
        self.addCleanup(self.execution.annuler_reservation)
        self.configuration = FakeConfigurationExecutions()

    def test_stop_during_admission_finds_the_reservation(self) -> None:
        stops: list[str] = []
        execution = self.execution

        class OperationsStoppingDuringAdmission:
            def demarrer(self, operation_type, work, *, cible=None) -> None:
                # Arrêt demandé entre la réservation et l'admission effective.
                stops.append(execution.arreter_execution())

        launch_execution(
            self.configuration,
            self.execution,
            OperationsStoppingDuringAdmission(),  # type: ignore[arg-type]
            [("modele", "factice/a")],
        )

        self.assertEqual(stops, [ARRET_DEMANDE])


if __name__ == "__main__":
    unittest.main()
