"""Tests de la ligne de commande : aide, dossiers de données, lancement Waitress."""

from __future__ import annotations

import contextlib
import io
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from flask import Flask

from transcription_bench import cli, paths
from transcription_bench.operations import CreneauOperations

PAQUETS_MOTEURS = ("ctranslate2", "faster_whisper", "torch", "transcribe_cpp", "transformers")
CONFIGURATION_ATTENDUE = {
    "host": "127.0.0.1",
    "threads": 4,
    "max_request_body_size": 1024 * 1024,
}


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
                sorted(os.listdir(base)), ["audio", "engines", "models", "results"]
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


if __name__ == "__main__":
    unittest.main()
