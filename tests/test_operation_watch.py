"""Tests du suivi d'opération longue et du drapeau de signal (tâche 1.5).

Travaux factices sur un vrai créneau : succès, échec, signal, second signal,
arrêt de l'exécution par l'utilisateur, curseur par génération, sortie JSON en
flux, traduction du résultat métier et attente bornée. Aucun moteur réel, aucun
réseau. Chaque test vérifie qu'aucun thread d'opération ne reste actif.
"""

from __future__ import annotations

import io
import json
import signal
import threading
import time
import unittest
from unittest import mock

from transcription_bench.command_session import (
    CODE_ECHEC,
    CODE_INTERRUPTED,
    CODE_SUCCESS,
)
from transcription_bench.execution_moteur import (
    ARRET_DEMANDE,
    ExecutionMoteur,
    ResultatAudio,
    ResultatExecution,
)
from transcription_bench.moteurs import InstallationMoteurs
from transcription_bench.operation_watch import OperationWatch, execution_exit_code
from transcription_bench.operations import (
    ETAT_EN_COURS,
    ETAT_ECHOUEE,
    ETAT_INTERROMPUE,
    ETAT_TERMINEE,
    TYPE_EXECUTION,
    TYPE_INSTALLATION,
    TYPE_TELECHARGEMENT,
    CreneauOperations,
    OperationEchouee,
    OperationInterrompue,
)
from transcription_bench.output import CommandOutput
from transcription_bench.supervision import SignalFlag

THREAD_NAME = "transcription-bench-operation"
TIMEOUT_S = 10.0


def wait_for_stop(operations: CreneauOperations) -> None:
    """Travail coopératif : attend l'arrêt demandé, puis s'interrompt comme une exécution."""
    deadline = time.monotonic() + TIMEOUT_S
    while time.monotonic() < deadline and not operations.instantane().arrete:
        time.sleep(0.01)
    raise OperationInterrompue("arrêt factice demandé")


def wait_for_condition(condition, timeout: float = TIMEOUT_S) -> None:
    """Attend qu'une condition devienne vraie, avec une échéance bornée."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline and not condition():
        time.sleep(0.01)


def send_signal(signal_number: int) -> None:
    """Envoie un signal au processus et laisse le gestionnaire s'exécuter."""
    signal.raise_signal(signal_number)
    time.sleep(0.02)


def watch_operation(
    operations: CreneauOperations,
    signal_flag: SignalFlag,
    *,
    json_mode: bool = False,
    **options,
) -> tuple[OperationWatch, io.StringIO, io.StringIO]:
    """Suivi relié à des flux de test ; renvoie aussi les flux de sortie et d'erreur."""
    output, error = io.StringIO(), io.StringIO()
    command_output = CommandOutput(json_mode=json_mode, stdout=output, stderr=error)
    return OperationWatch(operations, signal_flag, command_output, **options), output, error


def json_lines(output: io.StringIO) -> list[dict]:
    """Chaque ligne du flux doit être un objet JSON complet."""
    return [json.loads(line) for line in output.getvalue().splitlines()]


def execution_result(etat: str, *, erreur_audio: str | None = None) -> ResultatExecution:
    """Résultat métier minimal, factice, pour tester la traduction en code."""
    audios: tuple[ResultatAudio, ...] = ()
    if erreur_audio is not None:
        audios = (
            ResultatAudio(
                index=0,
                nom="audio.wav",
                prepare=None,
                evenement=None,
                erreur=erreur_audio,
                factice=True,
                synthetique=True,
            ),
        )
    return ResultatExecution(
        etat=etat,
        factice=True,
        synthetique=True,
        moteur="factice",
        famille="factice",
        modele_identifiant="factice",
        threads_demandes=1,
        audios=audios,
        evenements=(),
        lignes_parasites=0,
        journal_moteur=(),
    )


class RecordingOutput(io.StringIO):
    """Flux qui retient chaque écriture et chaque vidage, pour contrôler le flux."""

    def __init__(self) -> None:
        super().__init__()
        self.writes: list[str] = []
        self.flushes = 0

    def write(self, text: str) -> int:
        self.writes.append(text)
        return super().write(text)

    def flush(self) -> None:
        self.flushes += 1
        super().flush()


class WatchTestCase(unittest.TestCase):
    """Créneau neuf, drapeau armé pendant le test, aucun thread résiduel en fin."""

    def setUp(self) -> None:
        # Enregistré en premier : exécuté en dernier, après les autres nettoyages.
        self.addCleanup(self._assert_no_remaining_thread)
        self.operations = CreneauOperations()
        self.signal_flag = self.enterContext(SignalFlag())

    def _assert_no_remaining_thread(self) -> None:
        active_threads = [t for t in threading.enumerate() if t.name == THREAD_NAME and t.is_alive()]
        self.assertEqual(active_threads, [])


class OperationOutcomeTest(WatchTestCase):
    """Succès, échec et résultat métier, sans signal."""

    def test_succes_rend_le_code_du_resultat_et_ecrit_tout_le_journal(self) -> None:
        def work(worker) -> None:
            worker.journaliser("premiere étape")
            worker.journaliser("seconde étape")

        self.operations.demarrer(TYPE_INSTALLATION, work)
        watch, output, error = watch_operation(self.operations, self.signal_flag, json_mode=True)

        code = watch.wait(lambda snapshot: CODE_SUCCESS)

        self.assertEqual(code, CODE_SUCCESS)
        lines = json_lines(output)
        self.assertEqual({line["schema"] for line in lines}, {1})
        self.assertEqual({line["event"] for line in lines}, {"log"})
        self.assertEqual({line["generation"] for line in lines}, {1})
        self.assertEqual({line["operation"] for line in lines}, {TYPE_INSTALLATION})
        self.assertEqual(
            [line["line"] for line in lines],
            list(self.operations.instantane().journal),
        )
        self.assertEqual(error.getvalue(), "")

    def test_echec_est_traduit_par_le_resultat_et_non_par_l_etat_seul(self) -> None:
        def work(worker) -> None:
            raise OperationEchouee("panne factice")

        self.operations.demarrer(TYPE_INSTALLATION, work)
        watch, _, _ = watch_operation(self.operations, self.signal_flag)
        received_states: list[str] = []

        def translate(snapshot) -> int:
            received_states.append(snapshot.etat)
            return CODE_ECHEC

        code = watch.wait(translate)

        self.assertEqual(code, CODE_ECHEC)
        self.assertEqual(received_states, [ETAT_ECHOUEE])

    def test_terminee_n_est_pas_un_succes_metier(self) -> None:
        # Le créneau est `terminee`, mais le résultat métier (par exemple une
        # vérification refusée) décide du code : 1, pas 0.
        self.operations.demarrer(TYPE_INSTALLATION, lambda worker: None)
        watch, _, _ = watch_operation(self.operations, self.signal_flag)

        code = watch.wait(lambda snapshot: CODE_ECHEC)

        self.assertEqual(self.operations.instantane().etat, ETAT_TERMINEE)
        self.assertEqual(code, CODE_ECHEC)

    def test_suivi_sans_operation_admise_est_refuse(self) -> None:
        watch, _, _ = watch_operation(self.operations, self.signal_flag)

        with self.assertRaisesRegex(RuntimeError, "aucune opération"):
            watch.wait(lambda snapshot: CODE_SUCCESS)

    def test_traduction_des_resultats_d_execution(self) -> None:
        self.assertEqual(execution_exit_code(execution_result(ETAT_TERMINEE)), CODE_SUCCESS)
        self.assertEqual(
            execution_exit_code(execution_result(ETAT_TERMINEE, erreur_audio="illisible")),
            CODE_ECHEC,
        )
        self.assertEqual(execution_exit_code(execution_result(ETAT_ECHOUEE)), CODE_ECHEC)
        self.assertEqual(execution_exit_code(None), CODE_ECHEC)
        self.assertEqual(
            execution_exit_code(execution_result(ETAT_INTERROMPUE)), CODE_INTERRUPTED
        )


class SignalTest(WatchTestCase):
    """Signal à drapeau : arrêt engagé une fois, second signal ignoré, code 3."""

    def test_signal_arrete_le_travail_et_rend_3_sans_traduction(self) -> None:
        def work(worker) -> None:
            send_signal(signal.SIGINT)
            wait_for_stop(self.operations)

        self.operations.demarrer(TYPE_INSTALLATION, work)
        watch, _, error = watch_operation(self.operations, self.signal_flag)
        translate = mock.Mock(return_value=CODE_SUCCESS)

        code = watch.wait(translate)

        self.assertEqual(code, CODE_INTERRUPTED)
        translate.assert_not_called()
        self.assertTrue(self.signal_flag.received)
        self.assertEqual(self.signal_flag.signal_number, signal.SIGINT)
        self.assertEqual(self.operations.instantane().etat, ETAT_INTERROMPUE)
        self.assertIn("arrêt demandé par signal", error.getvalue())
        self.assertNotIn("Traceback", error.getvalue())

    def test_second_signal_est_ignore_sans_effet(self) -> None:
        def work(worker) -> None:
            send_signal(signal.SIGINT)
            wait_for_condition(lambda: self.signal_flag.received)
            send_signal(signal.SIGINT)
            wait_for_condition(lambda: self.signal_flag.ignored_count >= 1)
            wait_for_stop(self.operations)

        self.operations.demarrer(TYPE_INSTALLATION, work)
        watch, _, _ = watch_operation(self.operations, self.signal_flag)

        code = watch.wait(lambda snapshot: CODE_SUCCESS)

        self.assertEqual(code, CODE_INTERRUPTED)
        self.assertEqual(self.signal_flag.ignored_count, 1)
        self.assertEqual(self.operations.instantane().etat, ETAT_INTERROMPUE)

    def test_arret_d_une_execution_est_demande_par_l_utilisateur(self) -> None:
        execution = mock.Mock(spec=ExecutionMoteur)
        execution.en_cours.return_value = True
        execution.arreter_execution.return_value = ARRET_DEMANDE
        installation = mock.Mock(spec=InstallationMoteurs)

        def work(worker) -> None:
            wait_for_stop(self.operations)

        send_signal(signal.SIGINT)
        self.operations.demarrer(TYPE_EXECUTION, work)
        watch, _, _ = watch_operation(
            self.operations, self.signal_flag, execution=execution, installation=installation
        )

        code = watch.wait(lambda snapshot: CODE_SUCCESS)

        self.assertEqual(code, CODE_INTERRUPTED)
        # Motif utilisateur : aucun argument, donc pas `arret_serveur=True`.
        execution.arreter_execution.assert_called_once_with()
        installation.arreter.assert_called_once_with()

    def test_arret_d_une_installation_termine_son_sous_processus(self) -> None:
        installation = mock.Mock(spec=InstallationMoteurs)

        def work(worker) -> None:
            wait_for_stop(self.operations)

        send_signal(signal.SIGINT)
        self.operations.demarrer(TYPE_INSTALLATION, work)
        watch, _, _ = watch_operation(self.operations, self.signal_flag, installation=installation)

        code = watch.wait(lambda snapshot: CODE_SUCCESS)

        self.assertEqual(code, CODE_INTERRUPTED)
        installation.arreter.assert_called_once_with()
        self.assertEqual(self.operations.instantane().etat, ETAT_INTERROMPUE)

    def test_travail_qui_survit_au_signal_rend_3_apres_le_delai_borne(self) -> None:
        release = threading.Event()

        def work(worker) -> None:
            # Ignore l'arrêt, comme un téléchargement non annulable.
            release.wait(TIMEOUT_S)

        self.operations.demarrer(TYPE_TELECHARGEMENT, work)
        thread = self.operations.thread_travailleur
        self.addCleanup(self._release, release, thread)
        send_signal(signal.SIGINT)
        watch, _, _ = watch_operation(self.operations, self.signal_flag, close_timeout=0.1)
        translate = mock.Mock(return_value=CODE_SUCCESS)

        start = time.monotonic()
        code = watch.wait(translate)

        self.assertEqual(code, CODE_INTERRUPTED)
        self.assertLess(time.monotonic() - start, TIMEOUT_S / 2)
        translate.assert_not_called()
        self.assertEqual(self.operations.instantane().etat, ETAT_EN_COURS)
        self.assertTrue(thread.is_alive())

    @staticmethod
    def _release(release: threading.Event, thread: threading.Thread) -> None:
        release.set()
        thread.join(TIMEOUT_S)


class CursorTest(WatchTestCase):
    """Curseur de journal suivant la génération, sortie en flux."""

    def test_curseur_repart_de_zero_a_chaque_admission(self) -> None:
        watch, output, _ = watch_operation(self.operations, self.signal_flag, json_mode=True)

        self.operations.demarrer(TYPE_INSTALLATION, lambda t: t.journaliser("un"))
        watch.wait(lambda snapshot: CODE_SUCCESS)
        first_log = list(self.operations.instantane().journal)

        self.operations.demarrer(TYPE_TELECHARGEMENT, lambda t: t.journaliser("deux"))
        watch.wait(lambda snapshot: CODE_SUCCESS)
        second_log = list(self.operations.instantane().journal)

        lines = json_lines(output)
        self.assertEqual(
            [line["line"] for line in lines], first_log + second_log
        )
        self.assertEqual(
            [line["generation"] for line in lines],
            [1] * len(first_log) + [2] * len(second_log),
        )

    def test_journal_est_ecrit_pendant_l_operation(self) -> None:
        watch, output, _ = watch_operation(self.operations, self.signal_flag)
        observed: list[bool] = []

        def work(worker) -> None:
            worker.journaliser("premiere étape")
            wait_for_condition(lambda: "premiere étape" in output.getvalue())
            observed.append("premiere étape" in output.getvalue())
            worker.journaliser("seconde étape")

        self.operations.demarrer(TYPE_INSTALLATION, work)
        watch.wait(lambda snapshot: CODE_SUCCESS)

        self.assertEqual(observed, [True])


class JsonStreamTest(WatchTestCase):
    """Chaque ligne JSON est écrite d'un bloc puis vidée, sans troncature."""

    def test_chaque_ligne_est_complete_et_videe(self) -> None:
        message = "é 中文 😀 " + "x" * 5000
        self.operations.demarrer(TYPE_INSTALLATION, lambda t: t.journaliser(message))
        stream = RecordingOutput()
        watch = OperationWatch(
            self.operations,
            self.signal_flag,
            CommandOutput(json_mode=True, stdout=stream, stderr=io.StringIO()),
        )

        watch.wait(lambda snapshot: CODE_SUCCESS)

        self.assertGreater(len(stream.writes), 2)
        self.assertEqual(stream.flushes, len(stream.writes))
        for write in stream.writes:
            self.assertTrue(write.endswith("\n"))
            self.assertEqual(write.count("\n"), 1)
            data = json.loads(write)
            self.assertEqual(data["schema"], 1)
        self.assertTrue(
            any(json.loads(e)["line"].endswith(message) for e in stream.writes)
        )

    def test_mode_texte_ecrit_le_message_sans_json(self) -> None:
        self.operations.demarrer(TYPE_INSTALLATION, lambda t: t.journaliser("étape"))
        watch, output, _ = watch_operation(self.operations, self.signal_flag, json_mode=False)

        watch.wait(lambda snapshot: CODE_SUCCESS)

        lines = output.getvalue().splitlines()
        self.assertTrue(any(line.endswith("étape") for line in lines))
        self.assertFalse(any(line.startswith("{") for line in lines))


class SignalFlagTest(unittest.TestCase):
    """`SignalFlag` seul : aucune exception, comptage, restauration."""

    def test_premier_signal_pose_le_drapeau_sans_exception(self) -> None:
        with SignalFlag() as signal_flag:
            send_signal(signal.SIGINT)

            self.assertTrue(signal_flag.received)
            self.assertEqual(signal_flag.signal_number, signal.SIGINT)
            self.assertEqual(signal_flag.ignored_count, 0)

    def test_signaux_suivants_sont_comptes_et_ignores(self) -> None:
        with SignalFlag() as signal_flag:
            send_signal(signal.SIGINT)
            send_signal(signal.SIGINT)
            send_signal(signal.SIGINT)

            self.assertEqual(signal_flag.signal_number, signal.SIGINT)
            self.assertEqual(signal_flag.ignored_count, 2)

    def test_gestionnaires_precedents_sont_retablis_a_la_sortie(self) -> None:
        previous = signal.getsignal(signal.SIGINT)

        with SignalFlag():
            self.assertNotEqual(signal.getsignal(signal.SIGINT), previous)
        self.assertEqual(signal.getsignal(signal.SIGINT), previous)


class OutputEventTest(unittest.TestCase):
    """Un événement est une ligne JSON en mode JSON, sinon son seul texte."""

    def test_evenement_texte_ou_json(self) -> None:
        text_output = io.StringIO()
        CommandOutput(json_mode=False, stdout=text_output).event({"a": 1}, "ligne")
        self.assertEqual(text_output.getvalue(), "ligne\n")

        json_output = io.StringIO()
        CommandOutput(json_mode=True, stdout=json_output).event({"a": 1}, "ligne")
        self.assertEqual(json.loads(json_output.getvalue()), {"schema": 1, "a": 1})


if __name__ == "__main__":
    unittest.main()
