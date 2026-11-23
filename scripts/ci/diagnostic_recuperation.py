"""Diagnostic CI de la récupération après arrêt brutal d'une commande.

Rejoue, sans sonde préalable, le scénario de
`tests/test_command_session.py::RecuperationTest` : une commande réelle du
programme lance un moteur factice, consigne une exécution « en cours » puis
attend. Le processus de commande est tué (`kill`), attendu (`wait`), puis la
session de récupération (`run_session`) est lancée immédiatement, sans aucune
attente ni sonde du verrou. Chaque essai se fait dans un dossier neuf, en série.

Instrumentation passive, sans modifier le programme :
- `composition.VerrouInstance` est remplacé par une sous-classe qui relaie
  `acquerir`, consigne l'issue de la première tentative (temps monotone, code
  d'erreur système d'origine) puis relance l'exception telle quelle ;
- `recover` enveloppe `recuperer_executions_anterieures` de la même façon et
  consigne la classe de l'exception contextuelle (`__context__`), sans message ;
- la sortie d'erreur de la session est capturée et seulement comptée par motifs
  fixes (moteur terminé, identité différente, clôture, etc.).

Ce que le rapport prouve, champ par champ :
- `session.code` / `session.outcome` : code renvoyé par `run_session` ;
- `session.refusal` : `lock_busy` si la première tentative trouve le verrou
  occupé, `lock_acquisition` si l'ouverture ou le verrouillage lève une
  `OSError`, `previous_state` si la récupération refuse (identité, schéma...) ;
- `session.lock_first_attempt` : issue, `ms` depuis l'arrêt, `error_class`,
  `errno`, `winerror` d'origine (absents hors Windows) ;
- `session.recovery.error` : motif fixe déduit du message, classe de
  l'exception contextuelle (ex. `AccessDenied` = psutil refusé) ;
- `after_session.lock` : `free`, `busy` ou `acquisition_failed` (sonde posée
  après la session, jamais avant) ;
- `after_session.engine` : `engine` si le PID consigné porte le marqueur du moteur
  factice, `other_process` si le PID désigne un autre programme, `absent`,
  `zombie`, `unknown` (accès refusé) ;
- `after_session.execution` : `running`, `abandoned`, `other`, `unreadable`, `absent`.
- `retry` : si refus de verrou, une relance unique après `RETRY_DELAY_S` ;
- `session.recovery_log` : nombre de lignes du journal de récupération par motif.

Le rapport ne contient ni chemin, ni PID, ni message brut, ni variable
d'environnement. Codes de sortie : 0 si le diagnostic s'est exécuté, même si des
essais reproduisent un refus ; 1 seulement si le diagnostic lui-même casse
(scénario non atteint, précondition non vérifiée, arrêt impossible).
"""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import psutil  # noqa: E402

from transcription_bench import composition, paths  # noqa: E402
from transcription_bench.command_session import (  # noqa: E402
    CODE_ECHEC,
    CODE_INTERRUPTED,
    CODE_REFUS,
    CODE_SUCCESS,
    run_session,
)
from transcription_bench.instance import InstanceDejaActive, VerrouInstance  # noqa: E402
from transcription_bench.recuperation import (  # noqa: E402
    EtatAnterieurNonTraitable,
    recuperer_executions_anterieures,
)
from transcription_bench.resultats import (  # noqa: E402
    ETAT_ABANDONNEE,
    ETAT_EN_COURS,
    NOM_FICHIER_EXECUTION,
)

DATA_CI = ROOT / "data" / "ci"
DEFAULT_WORK_DIR = DATA_CI / "diagnostic"
DEFAULT_REPORT_DIR = DATA_CI / "rapports"
REPORT_NAME = "diagnostic-recuperation.json"
REPORT_SCHEMA = 1
MAX_TRIALS = 20
MAX_DURATION_S = 300.0
RETRY_DELAY_S = 1.0
COMMAND_TIMEOUT_S = 60.0
MARKER_POLL_S = 0.01
ENGINE_CODE = "import time; time.sleep(60)"
#: Fragment du code moteur, reconnu dans la ligne de commande avant tout arrêt.
ENGINE_MARKER = "time.sleep(60)"
LOCK_REFUSALS = ("lock_busy", "lock_acquisition")
RECOVERY_LOG_KEYS = (
    "engine_terminated",
    "identity_mismatch",
    "closed_abandoned",
    "left_in_place",
    "cache_leftover",
    "other",
)
#: Motifs fixes déduits des messages du programme (texte jamais publié).
RECOVERY_MOTIFS = (
    ("identification ou terminaison", "psutil_or_os_identification"),
    ("inaccessible", "process_inaccessible"),
    ("non vérifiable", "identity_unverifiable"),
    ("résiste à l'arrêt", "survivor"),
    ("clôture en état abandonné impossible", "closure_failed"),
    ("illisible", "unreadable_result"),
    ("schéma", "unknown_schema"),
    ("état inconnu", "unknown_state"),
    ("incohérent", "inconsistent_result"),
)
OUTCOMES = {
    CODE_SUCCESS: "success",
    CODE_ECHEC: "closure_failed",
    CODE_REFUS: "refusal",
    CODE_INTERRUPTED: "interrupted",
}

MSG_PRECONDITION = (
    "précondition non vérifiée : l'exécution consignée n'est pas en cours "
    "ou ne désigne pas le moteur annoncé"
)
MSG_COMMAND_EXITED = "la commande s'est terminée avant de consigner son moteur"
MSG_MARKER_TIMEOUT = "marqueur du moteur absent dans le délai"
MSG_KILL = "arrêt forcé de la commande impossible"
MSG_WAIT = "commande non terminée après arrêt forcé"

#: Commande enfant : mécanique de CODE_EXECUTION_BRUTALE, marqueur écrit atomiquement.
COMMAND_CODE = """
import json, os, subprocess, sys, time
from pathlib import Path
import psutil
from transcription_bench import paths
from transcription_bench.command_session import run_session
from transcription_bench.resultats import (
    ETAT_EN_COURS, NOM_FICHIER_EXECUTION, SCHEMA, SOURCE_HEURE_PSUTIL,
)

base = Path(sys.argv[1])
marker = Path(sys.argv[2])
engine_code = sys.argv[3]

def action(services, drapeau):
    engine = subprocess.Popen(
        [sys.executable, "-c", engine_code],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    folder = base / paths.NOM_DOSSIER_RESULTATS / "20260101-120000-diagnostic"
    folder.mkdir(parents=True)
    content = {
        "schema": SCHEMA,
        "etat": ETAT_EN_COURS,
        "processus_moteur": {
            "pid": engine.pid,
            "heure_creation": psutil.Process(engine.pid).create_time(),
            "heure_creation_source": SOURCE_HEURE_PSUTIL,
            "lance_a": None,
        },
        "audios": [],
    }
    (folder / NOM_FICHIER_EXECUTION).write_text(json.dumps(content), encoding="utf-8")
    temporary = marker.with_name(marker.name + ".tmp")
    temporary.write_text(str(engine.pid), encoding="utf-8")
    os.replace(temporary, marker)
    time.sleep(60)
    return 0

raise SystemExit(run_session(base, action))
"""


class DiagnosticFailure(RuntimeError):
    """Le diagnostic lui-même ne peut pas aller au bout (message fixe, sans chemin)."""


def _ms(reference_ns: int, instant_ns: int) -> float:
    """Écart monotone en millisecondes, depuis la référence de l'essai."""
    return round((instant_ns - reference_ns) / 1_000_000, 3)


class _Observation:
    """Faits relevés pendant une session, relatifs à l'arrêt de la commande."""

    def __init__(self, reference_ns: int) -> None:
        self.reference_ns = reference_ns
        self.lock: dict[str, Any] | None = None
        self.recovery: dict[str, Any] | None = None
        self.action_called = False

    def note_lock(self, start_ns: int, outcome: str, error: BaseException | None) -> None:
        """Consigne la première tentative de verrou seulement."""
        if self.lock is not None:
            return
        self.lock = {
            "outcome": outcome,
            "ms": _ms(self.reference_ns, start_ns),
            "error_class": None if error is None else type(error).__name__,
            "errno": getattr(error, "errno", None),
            "winerror": getattr(error, "winerror", None),
        }

    def recover(self, data_dir: Path) -> None:
        """Remplace la récupération par défaut, sans changer son comportement."""
        start_ns = time.perf_counter_ns()
        try:
            recuperer_executions_anterieures(data_dir)
        except EtatAnterieurNonTraitable as error:
            self.recovery = self._recovery_record(start_ns, error)
            raise
        self.recovery = self._recovery_record(start_ns, None)

    def _recovery_record(
        self, start_ns: int, error: EtatAnterieurNonTraitable | None
    ) -> dict[str, Any]:
        described = None
        if error is not None:
            # Motif déduit du message fixe ; le texte lui-même n'est jamais publié.
            context = error.__context__
            described = {
                "motif": _recovery_motif(str(error)),
                "context_class": None if context is None else type(context).__name__,
                "errno": getattr(context, "errno", None),
                "winerror": getattr(context, "winerror", None),
            }
        return {
            "start_ms": _ms(self.reference_ns, start_ns),
            "end_ms": _ms(self.reference_ns, time.perf_counter_ns()),
            "error": described,
        }

    def action(self, services: Any, drapeau: Any) -> int:
        self.action_called = True
        return CODE_SUCCESS


class _ObservedLock(VerrouInstance):
    """Verrou passif : relaie `acquerir`, consigne l'issue, relance l'exception."""

    def __init__(self, dossier_data: Path | str, observation: _Observation) -> None:
        super().__init__(dossier_data)
        self._observation = observation

    def acquerir(self) -> VerrouInstance:
        start_ns = time.perf_counter_ns()
        try:
            super().acquerir()
        except InstanceDejaActive as error:
            # Cause système (OSError de msvcrt/fcntl) portée par l'exception.
            self._observation.note_lock(start_ns, "busy", error.__cause__)
            raise
        except OSError as error:
            self._observation.note_lock(start_ns, "acquisition_failed", error)
            raise
        self._observation.note_lock(start_ns, "free", None)
        return self


def _recovery_motif(message: str) -> str:
    for fragment, motif in RECOVERY_MOTIFS:
        if fragment in message:
            return motif
    return "other"


def _count_recovery_log(texte: str) -> dict[str, int]:
    """Compte les lignes du journal de récupération par motif fixe."""
    compte = dict.fromkeys(RECOVERY_LOG_KEYS, 0)
    for ligne in texte.splitlines():
        if not ligne.strip():
            continue
        if "moteur PID" in ligne and "terminé" in ligne:
            cle = "engine_terminated"
        elif "identité différente" in ligne:
            cle = "identity_mismatch"
        elif "close en abandonnée" in ligne:
            cle = "closed_abandoned"
        elif "laissée en l'état" in ligne:
            cle = "left_in_place"
        elif "non supprimé" in ligne:
            cle = "cache_leftover"
        else:
            cle = "other"
        compte[cle] += 1
    return compte


def _run_session_observed(base: Path, reference_ns: int) -> dict[str, Any]:
    """Lance `run_session` avec instrumentation passive et renvoie les faits."""
    observation = _Observation(reference_ns)
    messages: list[str] = []
    captured = io.StringIO()
    code: int | None = None
    exception: str | None = None
    start_ns = time.perf_counter_ns()
    with (
        mock.patch.object(
            composition, "VerrouInstance", lambda dossier: _ObservedLock(dossier, observation)
        ),
        contextlib.redirect_stderr(captured),
    ):
        try:
            code = run_session(
                base,
                observation.action,
                recover=observation.recover,
                report=messages.append,
            )
        except Exception as error:  # erreur du programme : résultat observé
            exception = type(error).__name__
    end_ns = time.perf_counter_ns()
    return {
        "start_ms": _ms(reference_ns, start_ns),
        "end_ms": _ms(reference_ns, end_ns),
        "code": code,
        "outcome": "exception" if exception else OUTCOMES.get(code, "unexpected"),
        "exception": exception,
        "refusal": _refusal(code, observation),
        "lock_first_attempt": observation.lock,
        "recovery": observation.recovery,
        "action_called": observation.action_called,
        "recovery_log": _count_recovery_log(captured.getvalue()),
        "report_count": len(messages),
    }


def _refusal(code: int | None, observation: _Observation) -> str | None:
    if code != CODE_REFUS:
        return None
    if observation.lock is not None and observation.lock["outcome"] == "busy":
        return "lock_busy"
    if observation.lock is not None and observation.lock["outcome"] == "acquisition_failed":
        return "lock_acquisition"
    if observation.recovery is not None and observation.recovery["error"] is not None:
        return "previous_state"
    return "other"


def _lock_state(base: Path) -> str:
    """Sonde posée après la session : verrou libre, occupé ou indisponible."""
    try:
        VerrouInstance(base).acquerir().liberer()
    except InstanceDejaActive:
        return "busy"
    except OSError:
        return "acquisition_failed"
    return "free"


def _engine_state(pid: int) -> str:
    """État du moteur consigné, identifié par son marqueur de ligne de commande."""
    try:
        processus = psutil.Process(pid)
        if processus.status() == psutil.STATUS_ZOMBIE:
            return "zombie"
        ligne = " ".join(processus.cmdline())
    except psutil.ZombieProcess:
        return "zombie"
    except psutil.NoSuchProcess:
        return "absent"
    except psutil.AccessDenied:
        return "unknown"
    return "engine" if ENGINE_MARKER in ligne else "other_process"


def _execution_state(base: Path) -> tuple[str, int | None]:
    """État de l'unique exécution et PID consigné, sans chemin ni contenu publié."""
    fichiers = sorted((base / paths.NOM_DOSSIER_RESULTATS).glob(f"*/{NOM_FICHIER_EXECUTION}"))
    if len(fichiers) != 1:
        return "absent", None
    try:
        contenu = json.loads(fichiers[0].read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return "unreadable", None
    if not isinstance(contenu, dict):
        return "unreadable", None
    valeur = contenu.get("etat")
    etat = {ETAT_EN_COURS: "running", ETAT_ABANDONNEE: "abandoned"}.get(valeur, "other")
    processus = contenu.get("processus_moteur")
    pid = processus.get("pid") if isinstance(processus, dict) else None
    return etat, pid if type(pid) is int else None


def _after_session(base: Path, pid: int) -> dict[str, str]:
    return {
        "lock": _lock_state(base),
        "engine": _engine_state(pid),
        "execution": _execution_state(base)[0],
    }


def _wait_marker(command: subprocess.Popen[str], marker: Path) -> int:
    """Attend le PID du moteur consigné par la commande, borné."""
    deadline = time.monotonic() + COMMAND_TIMEOUT_S
    while True:
        if marker.exists():
            try:
                return int(marker.read_text(encoding="utf-8"))
            except ValueError:
                pass  # écriture atomique : ne devrait pas arriver, sans effet
        if command.poll() is not None:
            raise DiagnosticFailure(MSG_COMMAND_EXITED)
        if time.monotonic() >= deadline:
            raise DiagnosticFailure(MSG_MARKER_TIMEOUT)
        time.sleep(MARKER_POLL_S)


def _run_trial(number: int, folder: Path, engines: list[int]) -> dict[str, Any]:
    base = folder / "donnees"
    marker = folder / "moteur.pid"
    command_log = folder / "commande.err"
    with command_log.open("w", encoding="utf-8") as command_stderr:
        command = subprocess.Popen(
            [sys.executable, "-c", COMMAND_CODE, str(base), str(marker), ENGINE_CODE],
            cwd=ROOT,
            env={**os.environ, "PYTHONIOENCODING": "utf-8"},
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=command_stderr,
        )
    try:
        pid = _wait_marker(command, marker)
        engines.append(pid)
        state, recorded_pid = _execution_state(base)
        if state != "running" or recorded_pid != pid:
            raise DiagnosticFailure(MSG_PRECONDITION)
        reference_ns = time.perf_counter_ns()
        try:
            command.kill()
        except OSError:
            raise DiagnosticFailure(MSG_KILL) from None
        kill_ns = time.perf_counter_ns()
        try:
            command.wait(timeout=COMMAND_TIMEOUT_S)
        except subprocess.TimeoutExpired:
            raise DiagnosticFailure(MSG_WAIT) from None
        wait_ns = time.perf_counter_ns()
    finally:
        if command.poll() is None:
            command.kill()
            command.wait(timeout=COMMAND_TIMEOUT_S)

    trace = "Traceback" in command_log.read_text(encoding="utf-8", errors="replace")
    first = _run_session_observed(base, reference_ns)
    after_first = _after_session(base, pid)
    retry = None
    if first["refusal"] in LOCK_REFUSALS:
        time.sleep(RETRY_DELAY_S)
        second = _run_session_observed(base, reference_ns)
        retry = {
            "delay_ms": round(second["start_ms"] - first["end_ms"], 3),
            "session": second,
            "after_session": _after_session(base, pid),
        }
    return {
        "number": number,
        "command": {
            "marker_reached": True,
            "execution_before_kill": "running",
            "exit_code": command.returncode,
            "python_trace": trace,
        },
        "timeline_ms": {
            "kill_returned": _ms(reference_ns, kill_ns),
            "wait_returned": _ms(reference_ns, wait_ns),
        },
        "session": first,
        "after_session": after_first,
        "retry": retry,
    }


def _stop_engine(pid: int) -> bool:
    """Arrête le moteur du diagnostic seulement s'il porte encore son marqueur."""
    if _engine_state(pid) != "engine":
        return False
    try:
        psutil.Process(pid).kill()
    except psutil.Error:
        return False
    return True


def _remove_folder(folder: Path) -> bool:
    shutil.rmtree(folder, ignore_errors=True)
    return not folder.exists()


def _run_one(number: int, work_dir: Path) -> dict[str, Any]:
    """Un essai dans un dossier neuf ; le dossier et le moteur sont toujours nettoyés."""
    folder = Path(tempfile.mkdtemp(prefix=f"essai-{number:02d}-", dir=work_dir))
    engines: list[int] = []
    try:
        trial = _run_trial(number, folder, engines)
    finally:
        stopped = [pid for pid in engines if _stop_engine(pid)]
        removed = _remove_folder(folder)
    trial["cleanup"] = {"engine_stopped": bool(stopped), "folder_removed": removed}
    return trial


def _summary(trials: list[dict[str, Any]]) -> dict[str, Any]:
    retries = [trial["retry"] for trial in trials if trial["retry"] is not None]
    return {
        "trials_completed": len(trials),
        "first_session_outcomes": dict(Counter(t["session"]["outcome"] for t in trials)),
        "first_session_refusals": dict(
            Counter(t["session"]["refusal"] or "none" for t in trials)
        ),
        "first_session_engine": dict(Counter(t["after_session"]["engine"] for t in trials)),
        "first_session_lock": dict(Counter(t["after_session"]["lock"] for t in trials)),
        "retries": len(retries),
        "retry_outcomes": dict(Counter(r["session"]["outcome"] for r in retries)),
    }


def _report(
    trials: list[dict[str, Any]],
    failure: str | None,
    stop_reason: str,
    arguments: argparse.Namespace,
) -> dict[str, Any]:
    return {
        "schema": REPORT_SCHEMA,
        "diagnostic": "recuperation-apres-arret-brutal",
        "date": datetime.now(timezone.utc).isoformat(),
        "status": "failed" if failure else "complete",
        "failure_reason": failure,
        "stop_reason": stop_reason,
        "context": {
            "run": os.environ.get("GITHUB_RUN_ID"),
            "attempt": os.environ.get("GITHUB_RUN_ATTEMPT"),
            "commit": os.environ.get("GITHUB_SHA"),
            "image": os.environ.get("ImageOS"),
            "image_version": os.environ.get("ImageVersion"),
            "system": platform.system(),
            "system_release": platform.release(),
            "architecture": platform.machine(),
            "python": platform.python_version(),
            "psutil_version": psutil.__version__,
            "logical_cpus": os.cpu_count(),
        },
        "parameters": {
            "max_trials": arguments.trials,
            "max_duration_s": arguments.max_duration_s,
            "retry_delay_s": RETRY_DELAY_S,
            "command_timeout_s": COMMAND_TIMEOUT_S,
            "clock": "time.perf_counter_ns (monotone)",
            "retry_on": list(LOCK_REFUSALS),
        },
        "trials": trials,
        "summary": _summary(trials),
    }


def _write_report(report: dict[str, Any], folder: Path) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    (folder / REPORT_NAME).write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def _print_summary(report: dict[str, Any]) -> None:
    print(
        f"Diagnostic de récupération : statut {report['status']}, "
        f"{len(report['trials'])} essai(s), arrêt : {report['stop_reason']}."
    )
    for trial in report["trials"]:
        session = trial["session"]
        line = f"  essai {trial['number']} : {session['outcome']}"
        if session["code"] is not None:
            line += f" (code {session['code']})"
        if session["refusal"]:
            line += f", refus {session['refusal']}"
        if trial["retry"] is not None:
            line += f", relance {trial['retry']['session']['outcome']}"
        print(line)
    if report["failure_reason"]:
        print(f"Échec du diagnostic : {report['failure_reason']}")
    print(f"Rapport écrit : {REPORT_NAME}")


def _parse_arguments(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Diagnostic CI de la récupération après arrêt brutal."
    )
    parser.add_argument("--trials", type=int, default=MAX_TRIALS, help="essais (1 à 20)")
    parser.add_argument(
        "--max-duration-s",
        type=float,
        default=MAX_DURATION_S,
        help="durée au-delà de laquelle aucun essai n'est engagé",
    )
    parser.add_argument("--work-dir", type=Path, default=DEFAULT_WORK_DIR)
    parser.add_argument("--report-dir", type=Path, default=DEFAULT_REPORT_DIR)
    arguments = parser.parse_args(argv)
    if not 1 <= arguments.trials <= MAX_TRIALS:
        parser.error(f"--trials doit être compris entre 1 et {MAX_TRIALS}")
    if arguments.max_duration_s <= 0:
        parser.error("--max-duration-s doit être positif")
    return arguments


def main(argv: list[str] | None = None) -> int:
    arguments = _parse_arguments(argv)
    trials: list[dict[str, Any]] = []
    failure: str | None = None
    stop_reason = "trials_reached"
    started = time.monotonic()
    current = 0
    try:
        arguments.work_dir.mkdir(parents=True, exist_ok=True)
        for number in range(1, arguments.trials + 1):
            if time.monotonic() - started >= arguments.max_duration_s:
                stop_reason = "duration_reached"
                break
            current = number
            trials.append(_run_one(number, arguments.work_dir))
            current = 0
    except DiagnosticFailure as error:
        failure = str(error)
    except Exception as error:  # le diagnostic lui-même a cassé
        failure = f"exception inattendue du diagnostic ({type(error).__name__})"
    if failure is not None:
        stop_reason = "diagnostic_failed"
        if current:
            failure = f"{failure} (essai {current})"

    report = _report(trials, failure, stop_reason, arguments)
    try:
        _write_report(report, arguments.report_dir)
    except OSError:
        print("Échec : rapport non écrit (erreur d'écriture).", file=sys.stderr)
        return 1
    _print_summary(report)
    return 1 if failure is not None else 0


if __name__ == "__main__":
    raise SystemExit(main())
