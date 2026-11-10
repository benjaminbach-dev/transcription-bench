"""Arrêt réel de « run start » par signal et terminaison brutale (tâche 3.6).

Chaque scénario lance la vraie CLI (`cli.main`) dans un sous-processus Python,
sur un dossier de données temporaire. Le moteur est le moteur factice du dépôt,
rendu lent par le palier existant de `tests/test_execution_moteur.py` : le
processus moteur bloque au second audio jusqu'à un fichier de libération que ce
test n'écrit jamais. Aucun moteur réel, aucun poids, aucun réseau, aucune
inférence réelle ; les audios sont des WAV synthétiques.

Les attentes reposent sur des marqueurs (journal streamé, fichier de palier) et
sur un délai maximal borné, sans durée supposée. Tous les processus, CLI comme
moteur, sont arrêtés dans un nettoyage enregistré : il s'exécute même en cas
d'échec d'un test.

Limites : les signaux sont envoyés au seul PID de la CLI (POSIX). L'arrêt
brutal est un `SIGKILL` : il ne vaut pas un Ctrl+C sous Windows, qui n'est pas
couvert ici et reste à qualifier sur un PC de test.
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import tempfile
import unittest
from collections.abc import Callable
from pathlib import Path
from typing import Any

import psutil

from tests.test_audios import ecrire_wav
from tests.test_commands import JOURNAL_EVENT_KEYS, JSON_SNAPSHOT_KEYS
from tests.test_execution_moteur import (
    CODE_MOTEUR_PALIER,
    DELAI,
    _processus_termine,
    attendre_condition,
)
from transcription_bench import paths
from transcription_bench.command_session import CODE_INTERRUPTED, CODE_SUCCESS
from transcription_bench.executions import CLE_MODELE_FACTICE
from transcription_bench.execution_moteur import ETAT_INTERROMPUE as EXECUTION_STATE_INTERRUPTED
from transcription_bench.instance import VerrouInstance
from transcription_bench.operations import ETAT_INTERROMPUE as OPERATION_STATE_INTERRUPTED
from transcription_bench.resultats import (
    ETAT_ABANDONNEE as RUN_STATE_ABANDONED,
    ETAT_EN_COURS as RUN_STATE_RUNNING,
    ETAT_INTERROMPUE as RUN_STATE_INTERRUPTED,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
#: Référence du moteur factice, identique à celle des tests de commandes.
RUN_REFERENCE = f"factice/{CLE_MODELE_FACTICE}"
AUDIOS = ("a.wav", "b.wav", "c.wav")
AUDIO_DURATION_S = 0.5
#: Marqueur de journal écrit par le service après la consignation du premier audio.
JOURNAL_FIRST_AUDIO = "Audio « a.wav » transcrit"
#: Noms de paliers imposés par `CODE_MOTEUR_PALIER` (format externe, non renommable).
GATE_FIRST_AUDIO_RELEASED = "palier-1.liberer"
GATE_SECOND_AUDIO = "palier-2"
GATE_THIRD_AUDIO = "palier-3"
MESSAGE_SIGNAL_STOP = "arrêt demandé par signal"
STOP_SIGNALS = (signal.SIGTERM, signal.SIGINT)
REASON_POSIX_ONLY = "signaux POSIX ; l'arrêt Ctrl+C sous Windows reste à qualifier"

#: Pilote de la CLI : patch du dossier de données et du moteur (moteur lent).
#: Seul `construire_commande` est injecté, comme dans les tests existants ;
#: aucune option de production n'est ajoutée.
DRIVER_SCRIPT = """
import functools
import sys
from pathlib import Path
from unittest import mock

from tests.test_execution_moteur import commande_enveloppee
from transcription_bench import cli, composition, paths
from transcription_bench.execution_moteur import ExecutionMoteur

build_command = commande_enveloppee({engine_code!r})
with (
    mock.patch.object(paths, "DOSSIER_DATA", Path({data_dir!r})),
    mock.patch.object(
        composition,
        "ExecutionMoteur",
        functools.partial(ExecutionMoteur, construire_commande=build_command),
    ),
):
    sys.exit(cli.main(sys.argv[1:]))
"""


def read_run_json(data_dir: Path) -> dict[str, Any]:
    """Contenu du `run.json` unique du dossier de données (une seule exécution)."""
    files = list((data_dir / paths.NOM_DOSSIER_RESULTATS).glob("*/run.json"))
    if len(files) != 1:
        raise AssertionError(f"un seul run.json attendu : {files}")
    return json.loads(files[0].read_text(encoding="utf-8"))


def engine_identities(data_dir: Path) -> list[tuple[int, float]]:
    """Identités des moteurs consignées pour ne pas arrêter un PID réutilisé."""
    identities: list[tuple[int, float]] = []
    for file in (data_dir / paths.NOM_DOSSIER_RESULTATS).glob("*/run.json"):
        try:
            content = json.loads(file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        record = content.get("processus_moteur") or {}
        pid = record.get("pid")
        created_at = record.get("heure_creation")
        if type(pid) is int and type(created_at) in (int, float):
            identities.append((pid, created_at))
    return identities


def terminate_live_process(pid: int, created_at: float) -> None:
    """Termine seulement le moteur identifié, jamais un PID réutilisé."""
    try:
        process = psutil.Process(pid)
        if process.status() == psutil.STATUS_ZOMBIE:
            return
        if abs(process.create_time() - created_at) > 0.001:
            return
        process.kill()
    except psutil.Error:
        return
    psutil.wait_procs([process], timeout=DELAI)


class CliProcess:
    """Une invocation réelle de `cli.main` dans son propre interpréteur.

    Les sorties vont dans des fichiers, lus par `stdout_lines` : aucun tube ne
    peut se remplir ni bloquer la CLI, et seules les lignes complètes sont lues.
    """

    def __init__(self, root: Path, name: str, data_dir: Path, gates: Path) -> None:
        self.data_dir = data_dir
        self.gates = gates
        self.stdout_file = root / f"{name}.out"
        self.stderr_file = root / f"{name}.err"
        self.process: subprocess.Popen[bytes] | None = None

    def start(self, *arguments: str) -> None:
        """Lance la CLI avec les arguments donnés, moteur lent injecté."""
        engine_code = CODE_MOTEUR_PALIER.format(dossier=str(self.gates))
        script = DRIVER_SCRIPT.format(engine_code=engine_code, data_dir=str(self.data_dir))
        with self.stdout_file.open("w", encoding="utf-8") as stdout, self.stderr_file.open(
            "w", encoding="utf-8"
        ) as stderr:
            self.process = subprocess.Popen(
                [sys.executable, "-c", script, *arguments],
                cwd=REPO_ROOT,
                stdin=subprocess.DEVNULL,
                stdout=stdout,
                stderr=stderr,
            )

    def stdout_lines(self) -> list[str]:
        """Lignes complètes de la sortie standard écrites jusqu'ici."""
        chunks = self.stdout_file.read_text(encoding="utf-8").split("\n")
        return chunks[:-1]

    def journal_contains(self, excerpt: str) -> bool:
        return any(excerpt in line for line in self.stdout_lines())

    def stderr_text(self) -> str:
        return self.stderr_file.read_text(encoding="utf-8")

    def wait_for(self, condition: Callable[[], bool], description: str) -> None:
        """Attend la condition ; échoue tôt si la CLI s'est terminée entre-temps."""

        def check() -> bool:
            if condition():
                return True
            code = self.process.poll() if self.process is not None else None
            if code is not None:
                raise AssertionError(
                    f"{description} : CLI terminée (code {code}) : {self.stderr_text()}"
                )
            return False

        attendre_condition(check, description)

    def send_signal(self, number: int) -> None:
        assert self.process is not None
        self.process.send_signal(number)

    def kill_brutally(self) -> None:
        assert self.process is not None
        self.process.kill()

    def wait_exit(self) -> int:
        """Attend la fin réelle de la CLI, bornée, et rend son code de sortie."""
        assert self.process is not None
        return self.process.wait(DELAI)

    def close(self) -> None:
        """Arrête la CLI si elle tourne encore ; sans effet sinon."""
        if self.process is not None and self.process.poll() is None:
            self.process.kill()
            self.process.wait(DELAI)


class RunStartSignalTest(unittest.TestCase):
    """Arrêt de « run start » par signal, puis terminaison brutale et récupération."""

    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.launched: list[CliProcess] = []
        # Enregistré après le dossier temporaire : exécuté avant sa suppression.
        self.addCleanup(self.cleanup_processes)

    def cleanup_processes(self) -> None:
        """Termine toute CLI et tout moteur de l'essai, même après un échec."""
        for cli in self.launched:
            try:
                cli.close()
            finally:
                for pid, created_at in engine_identities(cli.data_dir):
                    terminate_live_process(pid, created_at)

    def new_scenario(self, name: str) -> tuple[Path, Path]:
        """Dossier de données, paliers et audios synthétiques, propres à un essai."""
        data_dir = self.root / name / "data-projet"
        gates = self.root / name / "paliers"
        gates.mkdir(parents=True)
        audio_folder = data_dir / paths.NOM_DOSSIER_AUDIO
        audio_folder.mkdir(parents=True)
        for audio in AUDIOS:
            ecrire_wav(audio_folder / audio, duree=AUDIO_DURATION_S)
        # Seul le premier audio est libéré ; le moteur bloque ensuite au second.
        (gates / GATE_FIRST_AUDIO_RELEASED).write_text("ok", encoding="utf-8")
        return data_dir, gates

    def launch_run_start(self, name: str, data_dir: Path, gates: Path) -> CliProcess:
        cli = CliProcess(self.root, name, data_dir, gates)
        self.launched.append(cli)
        arguments = ["run", "start", "--model", RUN_REFERENCE]
        for audio in AUDIOS:
            arguments += ["--audio", audio]
        cli.start(*arguments, "--threads", "2", "--json")
        return cli

    def wait_second_audio_blocked(self, cli: CliProcess) -> None:
        """Premier audio consigné et moteur bloqué au second : état voulu pour l'arrêt."""
        cli.wait_for(
            lambda: cli.journal_contains(JOURNAL_FIRST_AUDIO)
            and (cli.gates / GATE_SECOND_AUDIO).exists(),
            "premier audio transcrit et moteur bloqué au second",
        )

    def execution_identifier(self, data_dir: Path) -> str:
        """Nom du dossier de résultat de l'unique exécution du dossier de données."""
        return next((data_dir / paths.NOM_DOSSIER_RESULTATS).glob("*/run.json")).parent.name

    def assertWorkDirEmpty(self, data_dir: Path) -> None:
        cache = data_dir / paths.NOM_DOSSIER_CACHE
        leftovers = list(cache.iterdir()) if cache.exists() else []
        self.assertEqual(leftovers, [])

    def assertLockFree(self, data_dir: Path) -> None:
        """Le verrou d'instance peut être repris : une autre session démarre."""
        VerrouInstance(data_dir).acquerir().liberer()

    @unittest.skipIf(os.name == "nt", REASON_POSIX_ONLY)
    def test_stop_signal_keeps_written_result_and_leaves_rest_untreated(self) -> None:
        for number in STOP_SIGNALS:
            name = signal.Signals(number).name.lower()
            with self.subTest(signal=name):
                data_dir, gates = self.new_scenario(name)
                cli = self.launch_run_start(name, data_dir, gates)
                self.wait_second_audio_blocked(cli)
                # Précondition : le moteur est vivant avant le signal, donc son arrêt est réel.
                pid = read_run_json(data_dir)["processus_moteur"]["pid"]
                self.assertFalse(_processus_termine(pid))

                cli.send_signal(number)
                code = cli.wait_exit()

                self.assertEqual(code, CODE_INTERRUPTED)
                errors = cli.stderr_text()
                self.assertIn(MESSAGE_SIGNAL_STOP, errors)
                self.assertNotIn("Traceback", errors)

                # Sortie JSON : lignes complètes, puis un résultat final de schéma 1.
                *events, final = [json.loads(line) for line in cli.stdout_lines()]
                for event in events:
                    self.assertEqual(list(event), JOURNAL_EVENT_KEYS)
                self.assertEqual(list(final), JSON_SNAPSHOT_KEYS[("run", "start")])
                self.assertEqual(final["schema"], 1)
                self.assertEqual(final["operation"], OPERATION_STATE_INTERRUPTED)
                execution = final["execution"]
                self.assertEqual(execution["etat"], EXECUTION_STATE_INTERRUPTED)
                self.assertEqual(execution["audios_non_traites"], ["b.wav", "c.wav"])
                first = execution["audios"][0]
                self.assertEqual(first["nom"], "a.wav")
                self.assertIsNone(first["erreur"])
                self.assertFalse(first["non_traite"])

                # Le résultat du premier audio reste écrit ; l'exécution est interrompue.
                identifier = final["identifiant_resultat"]
                self.assertIsNotNone(identifier)
                self.assertEqual(identifier, self.execution_identifier(data_dir))
                run = read_run_json(data_dir)
                self.assertEqual(run["etat"], RUN_STATE_INTERRUPTED)
                result_dir = data_dir / paths.NOM_DOSSIER_RESULTATS / identifier / "1-a.wav"
                self.assertTrue((result_dir / "result.json").is_file())
                self.assertTrue((result_dir / "transcription.txt").is_file())

                # Audios restants jamais traités : le moteur n'a pas atteint le troisième.
                self.assertFalse((gates / GATE_THIRD_AUDIO).exists())

                # Aucun moteur survivant, pas de dossier de travail, verrou libéré.
                self.assertTrue(_processus_termine(pid))
                self.assertWorkDirEmpty(data_dir)
                self.assertLockFree(data_dir)

    @unittest.skipIf(os.name == "nt", REASON_POSIX_ONLY)
    def test_brutal_termination_is_recovered_by_next_command(self) -> None:
        data_dir, gates = self.new_scenario("brutal")
        cli = self.launch_run_start("brutal", data_dir, gates)
        self.wait_second_audio_blocked(cli)

        # Précondition : exécution « running », moteur vivant, aucun arrêt propre.
        before = read_run_json(data_dir)
        identifier = self.execution_identifier(data_dir)
        self.assertEqual(before["etat"], RUN_STATE_RUNNING)
        pid = before["processus_moteur"]["pid"]
        self.assertFalse(_processus_termine(pid))

        cli.kill_brutally()
        self.assertEqual(cli.wait_exit(), -signal.SIGKILL)
        # Le moteur, dans son propre groupe, survit à la CLI tuée.
        self.assertFalse(_processus_termine(pid))
        self.assertEqual(read_run_json(data_dir)["etat"], RUN_STATE_RUNNING)

        # Une autre commande récupère avant d'agir : moteur terminé, exécution abandonnée.
        follow_up = CliProcess(self.root, "follow-up", data_dir, gates)
        self.launched.append(follow_up)
        follow_up.start("results", "show", identifier, "--json")
        self.assertEqual(follow_up.wait_exit(), CODE_SUCCESS)

        self.assertTrue(_processus_termine(pid))
        self.assertEqual(read_run_json(data_dir)["etat"], RUN_STATE_ABANDONED)
        result_dir = data_dir / paths.NOM_DOSSIER_RESULTATS / identifier / "1-a.wav"
        self.assertTrue((result_dir / "result.json").is_file())
        self.assertWorkDirEmpty(data_dir)
        self.assertLockFree(data_dir)
        self.assertFalse((gates / GATE_THIRD_AUDIO).exists())


if __name__ == "__main__":
    unittest.main()
