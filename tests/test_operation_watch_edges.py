"""Cas limites : signal tardif, thread encore vivant et arrêt défaillant."""

import io
import signal
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from transcription_bench.command_session import run_session
from transcription_bench.operation_watch import OperationWatch
from transcription_bench.operations import CreneauOperations, InstantaneCreneau
from transcription_bench.output import CommandOutput
from transcription_bench.supervision import SignalFlag


class OperationWatchEdgesTest(unittest.TestCase):
    def test_waits_for_thread_after_final_state_is_published(self):
        state = InstantaneCreneau("terminee", False, "verification", "test", None,
                                  None, None, (), 1)
        slot = mock.Mock(spec=CreneauOperations)
        slot.instantane.return_value = state
        slot.thread_travailleur.is_alive.side_effect = [True, False]
        watch = OperationWatch(slot, SignalFlag(), CommandOutput(json_mode=True), poll_interval=0)
        self.assertEqual(watch.wait(lambda snapshot: 0), 0)
        self.assertEqual(slot.thread_travailleur.is_alive.call_count, 2)

    def test_received_signal_overrides_success_after_action_returns(self):
        def action(services, flag):
            flag._handle(signal.SIGINT)
            return 0
        with tempfile.TemporaryDirectory() as folder:
            self.assertEqual(run_session(Path(folder), action), 3)

    def test_stop_failure_does_not_interrupt_bounded_cleanup(self):
        slot = mock.Mock(spec=CreneauOperations)
        slot.instantane.return_value = InstantaneCreneau(
            "en_cours", False, "installation", "test", None, None, None, (), 1)
        slot.thread_travailleur.is_alive.return_value = True
        installer = mock.Mock()
        installer.arreter.side_effect = OSError("simulated")
        flag = SignalFlag()
        flag._handle(signal.SIGINT)
        errors = io.StringIO()
        watch = OperationWatch(
            slot, flag, CommandOutput(json_mode=True, stdout=io.StringIO(), stderr=errors),
            installation=installer, close_timeout=0, poll_interval=0,
        )
        self.assertEqual(watch.wait(lambda snapshot: 0), 3)
        installer.arreter.assert_called_once()
        self.assertIn("OSError", errors.getvalue())
