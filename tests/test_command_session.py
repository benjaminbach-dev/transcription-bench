"""Tests de la session de commande (tâche 1.3).

Couvre l'exclusion dans les deux sens entre serveur et commandes (sous-processus
factices qui tiennent le verrou), la libération du verrou après succès, échec,
exception et interruption, la récupération d'une exécution laissée en cours par
un arrêt brutal, et le dispatch des commandes injectées dans `cli.main`.

Aucun moteur réel, aucun réseau, aucune donnée hors dossier temporaire. Les
vrais sous-processus servent de témoins : un moteur factice (sommeil) est lancé
par une commande tuée brutalement, puis terminé par la récupération suivante.
"""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import os
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

import psutil

from transcription_bench import cli, command_session, paths
from transcription_bench.command_session import (
    CODE_ECHEC,
    CODE_INTERRUPTED,
    CODE_REFUS,
    CommandSpec,
    run_session,
)
from transcription_bench.composition import DataServices
from transcription_bench.instance import InstanceDejaActive, VerrouInstance
from transcription_bench.resultats import ETAT_ABANDONNEE, SCHEMA
from transcription_bench.supervision import SignalFlag

DELAI_PROCESSUS = 60.0
CODE_MOTEUR_FACTICE = "import time; time.sleep(60)"

#: Serveur réel (`cli.main`) dont seul le démarrage HTTP est remplacé : il tient
#: le verrou d'instance jusqu'à la fin du processus.
CODE_TENIR_SERVEUR = """
import sys, time
from pathlib import Path
from transcription_bench import cli, paths

paths.DOSSIER_DATA = Path(sys.argv[1])
marqueur = Path(sys.argv[2])

def servir(application, **options):
    marqueur.write_text("serveur tenu", encoding="utf-8")
    time.sleep(60)

cli.serve = servir
raise SystemExit(cli.main([]))
"""

#: Commande de longue durée : tient le verrou via `run_session` et suit une
#: opération factice qui obéit à l'arrêt, jusqu'à un signal ou 60 secondes.
CODE_TENIR_COMMANDE = """
import sys, time
from pathlib import Path
from transcription_bench.command_session import run_session
from transcription_bench.operation_watch import OperationWatch
from transcription_bench.operations import OperationInterrompue, TYPE_INSTALLATION
from transcription_bench.output import CommandOutput

marqueur = Path(sys.argv[2])

def action(services, drapeau):
    def travail(travailleur):
        marqueur.write_text("commande tenue", encoding="utf-8")
        echeance = time.monotonic() + 60
        while time.monotonic() < echeance:
            if services.operations.instantane().arrete:
                raise OperationInterrompue("arrêt factice")
            time.sleep(0.02)

    services.operations.demarrer(TYPE_INSTALLATION, travail)
    sortie = CommandOutput(json_mode=False)
    return OperationWatch(services.operations, drapeau, sortie).wait(lambda etat: 0)

raise SystemExit(run_session(Path(sys.argv[1]), action))
"""

#: Téléchargement factice qui ignore l'arrêt : après un SIGINT reçu par la commande,
#: la clôture reste incomplète (délai de clôture réduit pour le test).
CODE_CLOTURE_INCOMPLETE = """
import functools, signal, sys, threading
from pathlib import Path
from transcription_bench import composition
from transcription_bench.command_session import run_session
from transcription_bench.operation_watch import OperationWatch
from transcription_bench.operations import TYPE_TELECHARGEMENT
from transcription_bench.output import CommandOutput
from transcription_bench.supervision import NettoyageArret

composition.NettoyageArret = functools.partial(NettoyageArret, delai_operation=0.2)
bloque = threading.Event()

def action(services, drapeau):
    services.operations.demarrer(TYPE_TELECHARGEMENT, lambda travailleur: bloque.wait(60))
    signal.raise_signal(signal.SIGINT)
    sortie = CommandOutput(json_mode=False)
    return OperationWatch(services.operations, drapeau, sortie, close_timeout=0.2).wait(
        lambda etat: 0
    )

raise SystemExit(run_session(Path(sys.argv[1]), action))
"""

#: Commande qui lance un moteur factice, consigne une exécution « en cours » avec
#: son PID, puis attend d'être tuée brutalement (SIGKILL, sans clôture).
CODE_EXECUTION_BRUTALE = """
import json, subprocess, sys, time
from pathlib import Path
import psutil
from transcription_bench import paths
from transcription_bench.command_session import run_session
from transcription_bench.resultats import SCHEMA

CODE_MOTEUR = "import time; time.sleep(60)"

def action(services, drapeau):
    moteur = subprocess.Popen(
        [sys.executable, "-c", CODE_MOTEUR],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    dossier = Path(sys.argv[1]) / paths.NOM_DOSSIER_RESULTATS / "20260101-120000-brutal"
    dossier.mkdir(parents=True)
    contenu = {
        "schema": SCHEMA,
        "etat": "running",
        "processus_moteur": {
            "pid": moteur.pid,
            "heure_creation": psutil.Process(moteur.pid).create_time(),
            "heure_creation_source": "psutil",
            "lance_a": None,
        },
        "audios": [],
    }
    (dossier / "run.json").write_text(json.dumps(contenu), encoding="utf-8")
    Path(sys.argv[2]).write_text(str(moteur.pid), encoding="utf-8")
    time.sleep(60)
    return 0

raise SystemExit(run_session(Path(sys.argv[1]), action))
"""


def _rien(donnees: Path) -> None:
    """Récupération factice : rien à clore."""


def _arguments_essai(analyseur: argparse.ArgumentParser) -> None:
    analyseur.add_argument("--valeur", default="0", metavar="V")


def commande_espion(
    appels: list[tuple[argparse.Namespace, DataServices]], code: int = 0
) -> CommandSpec:
    """Commande injectée qui consigne ses appels et renvoie `code`."""

    def executer(
        arguments: argparse.Namespace, services: DataServices, drapeau: SignalFlag
    ) -> int:
        appels.append((arguments, services))
        return code

    return CommandSpec(
        name="essai",
        help_text="Commande d'essai injectée par les tests.",
        configure=_arguments_essai,
        run=executer,
    )


def attendre_fichier(chemin: Path, delai: float = DELAI_PROCESSUS) -> None:
    """Attend l'apparition d'un marqueur, avec une échéance bornée."""
    echeance = time.monotonic() + delai
    while time.monotonic() < echeance:
        if chemin.exists():
            return
        time.sleep(0.05)
    raise AssertionError(f"marqueur absent dans le délai imparti : {chemin}")


def vivant(pid: int) -> bool:
    """Vrai si le PID désigne encore un processus non zombie."""
    try:
        return psutil.Process(pid).status() != psutil.STATUS_ZOMBIE
    except psutil.NoSuchProcess:
        return False


def arborescence(base: Path) -> dict[str, bytes | None]:
    """Chemins et contenus de `data/`, pour prouver l'absence d'écriture."""
    return {
        str(chemin.relative_to(base)): None if chemin.is_dir() else chemin.read_bytes()
        for chemin in sorted(base.rglob("*"))
    }


class SessionTestCase(unittest.TestCase):
    """Dossier de données temporaire et processus témoins nettoyés."""

    def setUp(self) -> None:
        temporaire = tempfile.TemporaryDirectory()
        self.addCleanup(temporaire.cleanup)
        self.dossier = Path(temporaire.name)
        self.base = self.dossier / "data-projet"

    def lancer(self, code: str, *arguments: str) -> subprocess.Popen[str]:
        """Sous-processus Python réel, nettoyé en fin de test."""
        processus = subprocess.Popen(
            [sys.executable, "-c", code, *arguments],
            cwd=paths.RACINE_PROJET,
            env={**os.environ, "PYTHONIOENCODING": "utf-8"},
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
        )
        self.addCleanup(self._arreter, processus)
        return processus

    @staticmethod
    def _arreter(processus: subprocess.Popen[str]) -> None:
        if processus.poll() is None:
            processus.kill()
            processus.wait(timeout=DELAI_PROCESSUS)
        if processus.stderr is not None:
            processus.stderr.close()

    def assertLibre(self) -> None:
        """Le verrou d'instance peut être pris puis rendu : aucune session ne le tient."""
        VerrouInstance(self.base).acquerir().liberer()


class ExclusionTest(SessionTestCase):
    """Exclusion dans les deux sens, entre un vrai processus et la commande."""

    def test_command_refused_while_server_holds_the_lock(self) -> None:
        marqueur = self.dossier / "serveur-tenu"
        self.lancer(CODE_TENIR_SERVEUR, str(self.base), str(marqueur))
        attendre_fichier(marqueur)
        avant = arborescence(self.base)
        appels: list[tuple[argparse.Namespace, DataServices]] = []
        recuperations: list[Path] = []
        erreur = io.StringIO()

        with (
            mock.patch.object(paths, "DOSSIER_DATA", self.base),
            contextlib.redirect_stderr(erreur),
        ):
            code = cli.main(
                ["essai"],
                commands=(commande_espion(appels),),
                recuperer=recuperations.append,
            )

        self.assertEqual(code, CODE_REFUS)
        self.assertEqual(appels, [])
        self.assertEqual(recuperations, [])
        self.assertIn("autre instance", erreur.getvalue())
        self.assertNotIn("Traceback", erreur.getvalue())
        self.assertEqual(arborescence(self.base), avant)

    def test_server_and_other_command_refused_while_a_command_holds_the_lock(
        self,
    ) -> None:
        marqueur = self.dossier / "commande-tenue"
        processus = self.lancer(CODE_TENIR_COMMANDE, str(self.base), str(marqueur))
        attendre_fichier(marqueur)
        avant = arborescence(self.base)

        # Le serveur réel (`cli.main` sans sous-commande) est refusé avant tout.
        with (
            mock.patch.object(paths, "DOSSIER_DATA", self.base),
            mock.patch.object(cli, "create_app") as creer,
            mock.patch.object(cli, "serve") as servir,
            contextlib.redirect_stderr(io.StringIO()) as erreur_serveur,
        ):
            code_serveur = cli.main([], recuperer=_rien)

        self.assertEqual(code_serveur, CODE_REFUS)
        creer.assert_not_called()
        servir.assert_not_called()
        self.assertIn("autre instance", erreur_serveur.getvalue())

        # Une autre commande est refusée sans appeler son action ni la récupération.
        action = mock.Mock(return_value=0)
        recuperation = mock.Mock()
        messages: list[str] = []
        code_commande = run_session(
            self.base, action, recover=recuperation, report=messages.append
        )

        self.assertEqual(code_commande, CODE_REFUS)
        action.assert_not_called()
        recuperation.assert_not_called()
        self.assertTrue(any("autre instance" in message for message in messages))
        self.assertEqual(arborescence(self.base), avant)
        processus.kill()
        processus.wait(timeout=DELAI_PROCESSUS)

    def test_refusal_reports_lock_message_without_action_or_recovery(self) -> None:
        verrou = VerrouInstance(self.base).acquerir()
        self.addCleanup(verrou.liberer)
        action = mock.Mock(return_value=0)
        recuperation = mock.Mock()
        messages: list[str] = []

        code = run_session(
            self.base, action, recover=recuperation, report=messages.append
        )

        self.assertEqual(code, CODE_REFUS)
        action.assert_not_called()
        recuperation.assert_not_called()
        self.assertEqual(len(messages), 1)
        self.assertIn("autre instance", messages[0])


class LiberationTest(SessionTestCase):
    """Le verrou est libéré après succès, échec, exception et interruption."""

    def test_lock_held_during_action_and_released_after_success(self) -> None:
        services_vus: list[DataServices] = []

        def action(services: DataServices, drapeau: SignalFlag) -> int:
            with self.assertRaises(InstanceDejaActive):
                VerrouInstance(self.base).acquerir()
            services_vus.append(services)
            return 0

        code = run_session(self.base, action, recover=_rien)

        self.assertEqual(code, 0)
        self.assertIsInstance(services_vus[0], DataServices)
        self.assertTrue(services_vus[0].operations.instantane().arrete)
        self.assertLibre()

    def test_failure_code_is_returned_and_lock_released(self) -> None:
        code = run_session(self.base, lambda services, drapeau: CODE_ECHEC, recover=_rien)

        self.assertEqual(code, CODE_ECHEC)
        self.assertLibre()

    def test_exception_releases_lock_and_propagates(self) -> None:
        def action(services: DataServices, drapeau: SignalFlag) -> int:
            raise RuntimeError("échec simulé")

        with self.assertRaisesRegex(RuntimeError, "échec simulé"):
            run_session(self.base, action, recover=_rien)

        self.assertLibre()

    def test_interruption_releases_lock_and_propagates(self) -> None:
        # Interruption simulée au niveau de l'action : la clôture doit passer
        # par le `finally` de la session, puis l'exception continue.
        def action(services: DataServices, drapeau: SignalFlag) -> int:
            raise KeyboardInterrupt

        with self.assertRaises(KeyboardInterrupt):
            run_session(self.base, action, recover=_rien)

        self.assertLibre()

    def test_refused_recovery_returns_refusal_without_action_and_releases_lock(
        self,
    ) -> None:
        dossier = self.base / paths.NOM_DOSSIER_RESULTATS / "20260101-120000-casse"
        dossier.mkdir(parents=True)
        (dossier / "run.json").write_text(
            '{"etat": "running", "audios": []}', encoding="utf-8"
        )
        action = mock.Mock(return_value=0)
        messages: list[str] = []

        code = run_session(self.base, action, report=messages.append)

        self.assertEqual(code, CODE_REFUS)
        action.assert_not_called()
        self.assertTrue(any("schéma" in message for message in messages))
        self.assertLibre()

    @unittest.skipIf(os.name == "nt", "SIGINT n'est pas envoyable à un enfant Windows")
    def test_real_sigint_exits_3_without_trace_and_releases_lock(self) -> None:
        marqueur = self.dossier / "en-cours"
        processus = self.lancer(CODE_TENIR_COMMANDE, str(self.base), str(marqueur))
        attendre_fichier(marqueur)

        processus.send_signal(signal.SIGINT)
        _, erreur = processus.communicate(timeout=DELAI_PROCESSUS)

        self.assertEqual(processus.returncode, CODE_INTERRUPTED, erreur)
        self.assertNotIn("Traceback", erreur)
        self.assertNotIn("KeyboardInterrupt", erreur)
        self.assertIn("arrêt demandé par signal", erreur)
        self.assertLibre()

    @unittest.skipIf(os.name == "nt", "SIGTERM n'est pas un signal d'arrêt Windows")
    def test_real_sigterm_exits_3_without_trace_and_releases_lock(self) -> None:
        marqueur = self.dossier / "en-cours"
        processus = self.lancer(CODE_TENIR_COMMANDE, str(self.base), str(marqueur))
        attendre_fichier(marqueur)

        processus.send_signal(signal.SIGTERM)
        _, erreur = processus.communicate(timeout=DELAI_PROCESSUS)

        self.assertEqual(processus.returncode, CODE_INTERRUPTED, erreur)
        self.assertNotIn("Traceback", erreur)
        self.assertLibre()

    @unittest.skipIf(os.name == "nt", "SIGINT n'est pas envoyable à un enfant Windows")
    def test_real_signal_with_incomplete_closure_keeps_code_3(self) -> None:
        # Le téléchargement ignore l'arrêt : la clôture reste incomplète. Le code
        # reste 3, le message vient du nettoyage, et le processus, en se terminant,
        # rend le verrou (aucun thread ni verrou ne survit au test).
        processus = self.lancer(CODE_CLOTURE_INCOMPLETE, str(self.base))

        _, erreur = processus.communicate(timeout=DELAI_PROCESSUS)

        self.assertEqual(processus.returncode, CODE_INTERRUPTED, erreur)
        self.assertNotIn("Traceback", erreur)
        self.assertIn("opération non close", erreur)
        self.assertLibre()

    def test_signal_received_during_recovery_runs_no_action(self) -> None:
        def recuperer(donnees: Path) -> None:
            signal.raise_signal(signal.SIGINT)

        action = mock.Mock(return_value=0)
        messages: list[str] = []

        code = run_session(self.base, action, recover=recuperer, report=messages.append)

        self.assertEqual(code, CODE_INTERRUPTED)
        action.assert_not_called()
        self.assertTrue(any("avant le début" in message for message in messages))
        self.assertLibre()


class RecuperationTest(SessionTestCase):
    """Récupération d'une exécution laissée en cours par un arrêt brutal."""

    def test_next_session_recovers_execution_left_by_killed_command(self) -> None:
        marqueur = self.dossier / "moteur-pid"
        processus = self.lancer(CODE_EXECUTION_BRUTALE, str(self.base), str(marqueur))
        attendre_fichier(marqueur)
        moteur_pid = int(marqueur.read_text(encoding="utf-8"))
        self.addCleanup(_tuer_si_vivant, moteur_pid)
        run_json = next((self.base / paths.NOM_DOSSIER_RESULTATS).glob("*/run.json"))
        self.assertEqual(json.loads(run_json.read_text(encoding="utf-8"))["etat"], "running")

        processus.kill()  # terminaison brutale : aucune clôture côté commande
        processus.wait(timeout=DELAI_PROCESSUS)
        observe: dict[str, object] = {}

        def action(services: DataServices, drapeau: SignalFlag) -> int:
            observe["etat"] = json.loads(run_json.read_text(encoding="utf-8"))["etat"]
            observe["moteur_vivant"] = vivant(moteur_pid)
            return 0

        with contextlib.redirect_stderr(io.StringIO()):
            code = run_session(self.base, action)

        self.assertEqual(code, 0)
        self.assertEqual(observe["etat"], ETAT_ABANDONNEE)
        self.assertFalse(observe["moteur_vivant"], "le moteur orphelin doit être terminé")
        self.assertLibre()


class DispatchTest(SessionTestCase):
    """Dispatch d'une commande injectée par `cli.main`, sans commande publique."""

    def test_registered_command_receives_arguments_and_session_services(self) -> None:
        appels: list[tuple[argparse.Namespace, DataServices]] = []

        with mock.patch.object(paths, "DOSSIER_DATA", self.base):
            code = cli.main(
                ["essai", "--valeur", "7"],
                commands=(commande_espion(appels, code=CODE_ECHEC),),
                recuperer=_rien,
            )

        self.assertEqual(code, CODE_ECHEC)
        self.assertEqual(len(appels), 1)
        arguments, services = appels[0]
        self.assertEqual(arguments.valeur, "7")
        self.assertEqual(arguments.command, "essai")
        self.assertIsInstance(services, DataServices)
        self.assertTrue((self.base / paths.NOM_DOSSIER_RESULTATS).is_dir())
        self.assertLibre()

    def test_help_of_registered_command_reads_no_data(self) -> None:
        appels: list[tuple[argparse.Namespace, DataServices]] = []
        sortie = io.StringIO()

        with (
            mock.patch.object(paths, "DOSSIER_DATA", self.base),
            mock.patch.object(command_session, "open_data_session") as ouvrir,
            mock.patch.object(cli, "serve") as servir,
            contextlib.redirect_stdout(sortie),
        ):
            with self.assertRaises(SystemExit) as fin:
                cli.main(["essai", "--help"], commands=(commande_espion(appels),))

        self.assertEqual(fin.exception.code, 0)
        self.assertIn("--valeur", sortie.getvalue())
        ouvrir.assert_not_called()
        servir.assert_not_called()
        self.assertEqual(appels, [])
        self.assertFalse(self.base.exists())

    def test_command_help_lists_codes_0_to_3_and_serve_help_keeps_its_own(self) -> None:
        appels: list[tuple[argparse.Namespace, DataServices]] = []
        aides: dict[str, str] = {}

        for argv in ((["essai", "--help"]), (["serve", "--help"])):
            sortie = io.StringIO()
            with (
                mock.patch.object(paths, "DOSSIER_DATA", self.base),
                contextlib.redirect_stdout(sortie),
            ):
                with self.assertRaises(SystemExit) as fin:
                    cli.main(argv, commands=(commande_espion(appels),))
            self.assertEqual(fin.exception.code, 0)
            aides[argv[0]] = sortie.getvalue()

        self.assertIn("  3  interrompu par un signal", aides["essai"])
        self.assertIn("  0  succès", aides["essai"])
        self.assertNotIn("  3  ", aides["serve"])
        self.assertIn("arrêt normal", aides["serve"])
        self.assertFalse(self.base.exists())

    def test_duplicate_or_reserved_command_names_are_refused(self) -> None:
        appels: list[tuple[argparse.Namespace, DataServices]] = []
        espion = commande_espion(appels)

        with self.assertRaisesRegex(ValueError, "serve"):
            cli.construire_analyseur(_nommee("serve"))
        with self.assertRaisesRegex(ValueError, "essai"):
            cli.construire_analyseur((espion, espion))

    def test_unknown_command_is_refused_before_any_session(self) -> None:
        with (
            mock.patch.object(paths, "DOSSIER_DATA", self.base),
            mock.patch.object(command_session, "open_data_session") as ouvrir,
            contextlib.redirect_stderr(io.StringIO()),
        ):
            with self.assertRaises(SystemExit) as fin:
                cli.main(["inconnue"], commands=())

        self.assertEqual(fin.exception.code, 2)
        ouvrir.assert_not_called()
        self.assertFalse(self.base.exists())


def _nommee(nom: str) -> tuple[CommandSpec, ...]:
    """Commande factice portant un nom donné, pour tester les noms réservés."""
    return (
        CommandSpec(
            name=nom,
            help_text="factice",
            configure=_arguments_essai,
            run=lambda arguments, services, drapeau: 0,
        ),
    )


def _tuer_si_vivant(pid: int) -> None:
    """Filet de sécurité : aucun moteur factice ne survit au test."""
    try:
        psutil.Process(pid).kill()
    except (psutil.NoSuchProcess, psutil.ZombieProcess, psutil.AccessDenied):
        pass


if __name__ == "__main__":
    unittest.main()
