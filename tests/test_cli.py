"""Tests de la ligne de commande : aide, dossiers, démarrage ordonné, verrou."""

from __future__ import annotations

import contextlib
import inspect
import io
import json
import os
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

from flask import Flask
from waitress import serve as serve_waitress

from transcription_bench import cli, paths
from transcription_bench.instance import InstanceDejaActive, VerrouInstance
from transcription_bench.operations import CreneauOperations
from transcription_bench.recuperation import EtatAnterieurNonTraitable

PAQUETS_MOTEURS = ("ctranslate2", "faster_whisper", "torch", "transcribe_cpp", "transformers")
CONFIGURATION_ATTENDUE = {
    "host": "127.0.0.1",
    "threads": 4,
    "max_request_body_size": 1024 * 1024,
}
DELAI_PROCESSUS = 60.0

CODE_TENIR_VERROU = """
import sys, time
from pathlib import Path
from transcription_bench.instance import VerrouInstance

verrou = VerrouInstance(Path(sys.argv[1])).acquerir()
Path(sys.argv[2]).write_text("verrou tenu", encoding="utf-8")
time.sleep(60)
"""

CODE_PORT_OCCUPE = """
import sys
from pathlib import Path
from transcription_bench import cli, paths

paths.DOSSIER_DATA = Path(sys.argv[1])
raise SystemExit(cli.main(["--port", sys.argv[2]]))
"""

CODE_SECONDE_INSTANCE = """
import sys
from pathlib import Path
from transcription_bench import cli, paths

paths.DOSSIER_DATA = Path(sys.argv[1])
marqueur = Path(sys.argv[2])

def recuperer(donnees):
    marqueur.write_text("récupération appelée", encoding="utf-8")

raise SystemExit(cli.main(["--port", sys.argv[3]], recuperer=recuperer))
"""

CODE_REDEMARRAGE = """
import sys
from pathlib import Path
from transcription_bench import cli, paths

paths.DOSSIER_DATA = Path(sys.argv[1])
cli.serve = lambda application, **options: None
raise SystemExit(cli.main(["--port", "9126"]))
"""


class CliTest(unittest.TestCase):
    def test_help_affiche_l_aide_sans_effet_de_bord(self) -> None:
        with tempfile.TemporaryDirectory() as dossier, tempfile.TemporaryDirectory() as donnees:
            base = Path(donnees) / "data-projet"
            with mock.patch.object(paths, "DOSSIER_DATA", base):
                with contextlib.chdir(dossier):
                    sortie = io.StringIO()
                    with mock.patch.object(cli, "serve") as servir:
                        with contextlib.redirect_stdout(sortie):
                            with self.assertRaises(SystemExit) as sortie_erreur:
                                cli.main(["--help"])
                    self.assertEqual(sortie_erreur.exception.code, 0)
                    servir.assert_not_called()
                    self.assertIn("transcription-bench", sortie.getvalue())
                    self.assertIn("--port", sortie.getvalue())
                    self.assertEqual(os.listdir(dossier), [])
            self.assertFalse(base.exists())

    def test_lance_waitress_sur_l_adresse_locale_avec_le_port_demande(self) -> None:
        with tempfile.TemporaryDirectory() as dossier, tempfile.TemporaryDirectory() as donnees:
            base = Path(donnees) / "data-projet"
            with mock.patch.object(paths, "DOSSIER_DATA", base):
                with contextlib.chdir(dossier):
                    sortie = io.StringIO()
                    with mock.patch.object(cli, "serve") as servir:
                        with contextlib.redirect_stdout(sortie):
                            code = cli.main(["--port", "9123"])

                    self.assertEqual(code, 0)
                    self.assertEqual(os.listdir(dossier), [])
                    self.assertIn("http://127.0.0.1:9123", sortie.getvalue())

                    servir.assert_called_once()
                    application = servir.call_args.args[0]
                    self.assertIsInstance(application, Flask)
                    self.assertEqual(
                        servir.call_args.kwargs,
                        {**CONFIGURATION_ATTENDUE, "port": 9123},
                    )
                    self.assertFalse(application.debug)
                    self.assertNotIn("static", application.view_functions)
                    self.assertEqual(application.config["PORT"], 9123)
                    self.assertEqual(application.config["DOSSIER_DATA"], str(base))

            self.assertEqual(
                sorted(os.listdir(base)),
                ["audio", "engines", "instance.lock", "models", "results"],
            )

    def test_port_par_defaut_sans_ouvrir_le_port(self) -> None:
        analyseur = cli.construire_analyseur()

        self.assertEqual(analyseur.parse_args([]).port, 8765)
        self.assertEqual(analyseur.parse_args(["--port", "1024"]).port, 1024)
        self.assertEqual(analyseur.parse_args(["--port", "65535"]).port, 65535)
        with tempfile.TemporaryDirectory() as donnees:
            base = Path(donnees) / "data-projet"
            with mock.patch.object(paths, "DOSSIER_DATA", base):
                sortie = io.StringIO()
                with mock.patch.object(cli, "serve") as servir:
                    with contextlib.redirect_stdout(sortie):
                        code = cli.main([])

            self.assertEqual(code, 0)
            self.assertIn("http://127.0.0.1:8765", sortie.getvalue())
            self.assertEqual(servir.call_args.kwargs["port"], 8765)

    def test_refuse_un_port_invalide_au_parsing_sans_effet(self) -> None:
        for valeur in ("0", "80", "1023", "65536", "-1", "abc", ""):
            with self.subTest(valeur=valeur):
                with tempfile.TemporaryDirectory() as dossier, tempfile.TemporaryDirectory() as donnees:
                    base = Path(donnees) / "data-projet"
                    with mock.patch.object(paths, "DOSSIER_DATA", base):
                        with contextlib.chdir(dossier):
                            erreur = io.StringIO()
                            with mock.patch.object(cli, "serve") as servir:
                                with contextlib.redirect_stderr(erreur), contextlib.redirect_stdout(io.StringIO()):
                                    with self.assertRaises(SystemExit) as sortie:
                                        cli.main(["--port", valeur])

                            self.assertEqual(sortie.exception.code, 2)
                            servir.assert_not_called()
                            self.assertIn("port invalide", erreur.getvalue())
                            self.assertEqual(os.listdir(dossier), [])
                    self.assertFalse(base.exists())

    def test_cree_et_injecte_un_creneau_partage_sans_thread(self) -> None:
        instances: list[CreneauOperations] = []

        class CreneauEspion(CreneauOperations):
            def __init__(self) -> None:
                super().__init__()
                instances.append(self)

        with tempfile.TemporaryDirectory() as donnees:
            base = Path(donnees) / "data-projet"
            with mock.patch.object(paths, "DOSSIER_DATA", base):
                with mock.patch.object(cli, "CreneauOperations", CreneauEspion):
                    with mock.patch.object(cli, "serve") as servir:
                        with contextlib.redirect_stdout(io.StringIO()):
                            self.assertEqual(cli.main([]), 0)

        self.assertEqual(len(instances), 1)
        self.assertIsNone(instances[0].thread_travailleur)
        instances[0].arreter()
        application = servir.call_args.args[0]
        page = application.test_client().get(
            "/operation", base_url="http://127.0.0.1:8765"
        )
        self.assertEqual(page.status_code, 200)
        self.assertIn("arrêt demandé", page.get_data(as_text=True))
        self.assertNotIn("Set-Cookie", page.headers)

    def test_import_du_cli_ne_charge_aucun_paquet_moteur(self) -> None:
        code = (
            "import sys, transcription_bench.cli;"
            f"charges = sorted(m for m in sys.modules if m.split('.')[0] in {PAQUETS_MOTEURS!r});"
            "print(' '.join(charges))"
        )
        resultat = subprocess.run(
            [sys.executable, "-c", code], capture_output=True, text=True, check=True
        )
        self.assertEqual(resultat.stdout.strip(), "")
        self.assertEqual(resultat.stderr, "")


def port_local_ecoute() -> tuple[socket.socket, int]:
    """Ouvre un port local réellement occupé, sur un numéro éphémère."""
    prise = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    prise.bind(("127.0.0.1", 0))
    prise.listen(1)
    return prise, prise.getsockname()[1]


def attendre_fichier(chemin: Path, delai: float = 30.0) -> None:
    """Attend l'apparition d'un fichier marqueur, avec une échéance bornée."""
    echeance = time.monotonic() + delai
    while time.monotonic() < echeance:
        if chemin.exists():
            return
        time.sleep(0.05)
    raise AssertionError(f"marqueur absent dans le délai imparti : {chemin}")


def lancer_code(code: str, *arguments: str) -> subprocess.CompletedProcess[str]:
    """Exécute un scénario CLI dans un vrai processus, sans réseau externe."""
    return subprocess.run(
        [sys.executable, "-c", code, *arguments],
        cwd=paths.RACINE_PROJET,
        capture_output=True,
        text=True,
        timeout=DELAI_PROCESSUS,
    )


def arborescence(base: Path) -> dict[str, bytes | None]:
    """Photographie des chemins et contenus, hors fichier de verrou persistant."""
    return {
        str(chemin.relative_to(base)): None if chemin.is_dir() else chemin.read_bytes()
        for chemin in sorted(base.rglob("*"))
        if chemin.name != "instance.lock"
    }


class DemarrageOrdonneTest(unittest.TestCase):
    """Ordre verrou → récupération → dossiers → application → HTTP."""

    def setUp(self) -> None:
        temporaire = tempfile.TemporaryDirectory()
        self.addCleanup(temporaire.cleanup)
        self.base = Path(temporaire.name) / "data-projet"

    def test_ordre_verrou_recuperation_dossiers_application_serve(self) -> None:
        ordre: list[str] = []

        def recuperer(donnees: Path) -> None:
            ordre.append("recuperation")
            self.assertEqual(Path(donnees), self.base)
            with self.assertRaises(InstanceDejaActive):
                VerrouInstance(self.base).acquerir()

        def preparer(donnees: Path) -> dict[str, Path]:
            ordre.append("dossiers")
            self.assertEqual(Path(donnees), self.base)
            return {}

        def creer(config, services):
            ordre.append("application")
            self.assertEqual(config.port, 9124)
            self.assertEqual(Path(config.dossier_data), self.base)
            self.assertIsInstance(services.creneau, CreneauOperations)
            return mock.sentinel.application

        def servir(application, **options) -> None:
            ordre.append("serve")
            self.assertIs(application, mock.sentinel.application)
            self.assertEqual(options, {**CONFIGURATION_ATTENDUE, "port": 9124})

        with (
            mock.patch.object(paths, "DOSSIER_DATA", self.base),
            mock.patch.object(paths, "preparer_dossiers_data", preparer),
            mock.patch.object(cli, "create_app", creer),
            mock.patch.object(cli, "serve", servir),
        ):
            with contextlib.redirect_stdout(io.StringIO()):
                code = cli.main(["--port", "9124"], recuperer=recuperer)

        self.assertEqual(code, 0)
        self.assertEqual(ordre, ["recuperation", "dossiers", "application", "serve"])
        self.assertTrue((self.base / "instance.lock").is_file())
        VerrouInstance(self.base).acquerir().liberer()

    def test_recuperation_par_defaut_clot_en_abandonne_avant_de_servir(self) -> None:
        resultat = self.base / "results" / "20260101-120000-aaaaaaaa" / "run.json"
        resultat.parent.mkdir(parents=True)
        resultat.write_text(
            json.dumps(
                {
                    "schema": 1,
                    "etat": "running",
                    "processus_moteur": {"pid": None},
                    "audios": [],
                }
            ),
            encoding="utf-8",
        )

        def servir(application, **options) -> None:
            contenu = json.loads(resultat.read_text(encoding="utf-8"))
            self.assertEqual(contenu["etat"], "abandoned")
            self.assertIsNotNone(contenu["fin"])

        with (
            mock.patch.object(paths, "DOSSIER_DATA", self.base),
            mock.patch.object(cli, "create_app", return_value=mock.sentinel.application),
            mock.patch.object(cli, "serve", servir),
        ):
            erreurs = io.StringIO()
            with (
                contextlib.redirect_stdout(io.StringIO()),
                contextlib.redirect_stderr(erreurs),
            ):
                code = cli.main([])

        self.assertEqual(code, 0)
        # Une ligne de journal par exécution traitée, sans chemin absolu ni secret.
        self.assertIn(
            "exécution 20260101-120000-aaaaaaaa close en abandonnée",
            erreurs.getvalue(),
        )
        VerrouInstance(self.base).acquerir().liberer()

    def test_refus_de_recuperation_avant_dossiers_et_serve(self) -> None:
        def recuperer(donnees: Path) -> None:
            raise EtatAnterieurNonTraitable("résultat antérieur non traitable (simulé)")

        with (
            mock.patch.object(paths, "DOSSIER_DATA", self.base),
            mock.patch.object(cli, "create_app") as creer,
            mock.patch.object(cli, "serve") as servir,
        ):
            erreur = io.StringIO()
            with (
                contextlib.redirect_stderr(erreur),
                contextlib.redirect_stdout(io.StringIO()),
            ):
                code = cli.main([], recuperer=recuperer)

        self.assertEqual(code, cli.CODE_REFUS)
        self.assertIn("non traitable", erreur.getvalue())
        self.assertNotIn("Traceback", erreur.getvalue())
        creer.assert_not_called()
        servir.assert_not_called()
        self.assertEqual(os.listdir(self.base), ["instance.lock"])
        VerrouInstance(self.base).acquerir().liberer()

    def test_port_occupe_erreur_claire_sans_verrou_ni_trace(self) -> None:
        prise, port = port_local_ecoute()
        self.addCleanup(prise.close)

        processus = lancer_code(CODE_PORT_OCCUPE, str(self.base), str(port))

        self.assertEqual(processus.returncode, cli.CODE_ECHEC, processus.stderr)
        self.assertIn("impossible d'écouter", processus.stderr)
        self.assertIn(str(port), processus.stderr)
        self.assertIn("--port N", processus.stderr)
        self.assertNotIn("Traceback", processus.stderr)
        self.assertIn(f"http://127.0.0.1:{port}", processus.stdout)
        self.assertEqual(
            sorted(os.listdir(self.base)),
            ["audio", "engines", "instance.lock", "models", "results"],
        )
        VerrouInstance(self.base).acquerir().liberer()

    def test_serve_publique_sans_api_privee_ni_controle_prealable_du_port(self) -> None:
        self.assertIs(cli.serve, serve_waitress)
        source = inspect.getsource(cli)
        for interdit in ("create_server", "task_dispatcher", "socket"):
            self.assertNotIn(interdit, source)

    def test_verrou_conserve_tant_que_le_thread_d_operation_est_actif(self) -> None:
        verrou = VerrouInstance(self.base).acquerir()
        self.addCleanup(verrou.liberer)
        creneau = CreneauOperations()
        liberation = threading.Event()
        self.addCleanup(liberation.set)
        creneau.demarrer("execution", lambda travailleur: liberation.wait(DELAI_PROCESSUS))
        erreur = io.StringIO()

        with mock.patch.object(cli, "DELAI_ARRET_SERVEUR", 0.05):
            with contextlib.redirect_stderr(erreur):
                self.assertFalse(cli._clore_apres_arret(creneau, verrou))

        self.assertTrue(verrou.detenu)
        with self.assertRaises(InstanceDejaActive):
            VerrouInstance(self.base).acquerir()
        self.assertIn("verrou d'instance conservé", erreur.getvalue())

        liberation.set()
        creneau.thread_travailleur.join(DELAI_PROCESSUS)
        self.assertTrue(cli._clore_apres_arret(creneau, verrou))
        self.assertFalse(verrou.detenu)
        VerrouInstance(self.base).acquerir().liberer()


class ProcessusReelsTest(unittest.TestCase):
    """Deux vrais processus, port occupé réel et redémarrage sans intervention."""

    def setUp(self) -> None:
        temporaire = tempfile.TemporaryDirectory()
        self.addCleanup(temporaire.cleanup)
        self.dossier = Path(temporaire.name)
        self.base = self.dossier / "data-projet"
        self.marqueur = self.dossier / "pret"

    def demarrer_teneur(self) -> subprocess.Popen[str]:
        processus = subprocess.Popen(
            [sys.executable, "-c", CODE_TENIR_VERROU, str(self.base), str(self.marqueur)],
            cwd=paths.RACINE_PROJET,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
        )
        self.addCleanup(self._arreter, processus)
        attendre_fichier(self.marqueur)
        return processus

    def _arreter(self, processus: subprocess.Popen[str]) -> None:
        if processus.poll() is None:
            processus.kill()
            processus.wait(timeout=DELAI_PROCESSUS)
        if processus.stderr is not None:
            processus.stderr.close()

    def test_seconde_instance_refusee_avant_recuperation_et_mutation(self) -> None:
        resultat = self.base / "results" / "20260101-120000-abc"
        resultat.mkdir(parents=True)
        run_json = resultat / "run.json"
        contenu = '{"etat": "running", "audios": []}'
        run_json.write_text(contenu, encoding="utf-8")
        sentinelle = resultat / "transcription.txt"
        sentinelle.write_text("déjà écrit", encoding="utf-8")
        avant = arborescence(self.base)
        marqueur_recuperation = self.dossier / "recuperation-appelee"

        self.demarrer_teneur()
        processus = lancer_code(
            CODE_SECONDE_INSTANCE,
            str(self.base),
            str(marqueur_recuperation),
            "9125",
        )

        self.assertEqual(processus.returncode, cli.CODE_REFUS, processus.stderr)
        self.assertIn("instance", processus.stderr)
        self.assertNotIn("Traceback", processus.stderr)
        self.assertFalse(
            marqueur_recuperation.exists(),
            "la récupération a été appelée malgré le verrou d'instance",
        )
        self.assertEqual(run_json.read_text(encoding="utf-8"), contenu)
        self.assertEqual(sentinelle.read_text(encoding="utf-8"), "déjà écrit")
        self.assertEqual(arborescence(self.base), avant)

    def test_redemarrage_apres_arret_brutal_sans_intervention(self) -> None:
        processus = self.demarrer_teneur()
        processus.kill()
        processus.wait(timeout=DELAI_PROCESSUS)

        resultat = lancer_code(CODE_REDEMARRAGE, str(self.base))

        self.assertEqual(resultat.returncode, 0, resultat.stderr)
        self.assertIn("Interface disponible", resultat.stdout)
        self.assertEqual(resultat.stderr, "")
        for nom in ("audio", "models", "engines", "results"):
            self.assertTrue((self.base / nom).is_dir(), nom)
        VerrouInstance(self.base).acquerir().liberer()


if __name__ == "__main__":
    unittest.main()
