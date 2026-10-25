"""Tests de la ligne de commande : aide, refus explicite, absence d'effet."""

from __future__ import annotations

import contextlib
import io
import os
import subprocess
import sys
import tempfile
import unittest

from transcription_bench import cli

PAQUETS_MOTEURS = ("ctranslate2", "faster_whisper", "torch", "transcribe_cpp", "transformers")


class CliTest(unittest.TestCase):
    def test_help_affiche_l_aide_sans_effet_de_bord(self) -> None:
        with tempfile.TemporaryDirectory() as dossier:
            with contextlib.chdir(dossier):
                sortie = io.StringIO()
                with contextlib.redirect_stdout(sortie):
                    with self.assertRaises(SystemExit) as sortie_erreur:
                        cli.main(["--help"])
                self.assertEqual(sortie_erreur.exception.code, 0)
                self.assertIn("transcription-bench", sortie.getvalue())
                self.assertEqual(os.listdir(dossier), [])

    def test_sans_argument_refuse_serveur_non_implemente(self) -> None:
        with tempfile.TemporaryDirectory() as dossier:
            with contextlib.chdir(dossier):
                sortie = io.StringIO()
                with contextlib.redirect_stderr(sortie):
                    code = cli.main([])
                self.assertEqual(code, 1)
                self.assertIn("serveur non encore implémenté", sortie.getvalue())
                self.assertEqual(os.listdir(dossier), [])

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
