"""Test de fumée du diagnostic de récupération (Linux, essai unique bref).

Vérifie seulement que le script démarre, joue un essai dans des dossiers
temporaires, écrit un rapport sans chemin et sort avec 0. Le diagnostic Windows
ne tourne pas dans la suite : il relève le workflow manuel sur runner Windows.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

RACINE = Path(__file__).resolve().parents[1]
SCRIPT = RACINE / "scripts" / "ci" / "diagnostic_recuperation.py"
NOM_RAPPORT = "diagnostic-recuperation.json"


@unittest.skipIf(os.name == "nt", "diagnostic Windows : workflow manuel, hors suite locale")
class DiagnosticRecuperationFumeeTest(unittest.TestCase):
    def test_essai_unique_bref_ecrit_un_rapport_sans_chemin(self) -> None:
        with (
            tempfile.TemporaryDirectory() as travail,
            tempfile.TemporaryDirectory() as sortie,
        ):
            resultat = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--trials",
                    "1",
                    "--max-duration-s",
                    "60",
                    "--work-dir",
                    travail,
                    "--report-dir",
                    sortie,
                ],
                cwd=RACINE,
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=180,
                env={**os.environ, "PYTHONIOENCODING": "utf-8"},
            )
            texte = (Path(sortie) / NOM_RAPPORT).read_text(encoding="utf-8")

        self.assertEqual(resultat.returncode, 0, resultat.stderr)
        self.assertNotIn("Traceback", resultat.stderr)
        rapport = json.loads(texte)
        self.assertEqual(rapport["status"], "complete")
        self.assertEqual(len(rapport["trials"]), 1)
        essai = rapport["trials"][0]
        # Sous Linux, le verrou est libéré à la sortie du processus tué : aucun refus.
        self.assertEqual(essai["session"]["code"], 0)
        self.assertEqual(essai["after_session"]["execution"], "abandoned")
        self.assertTrue(essai["cleanup"]["folder_removed"])
        for interdit in (str(RACINE), travail, sortie):
            self.assertNotIn(interdit, texte)


if __name__ == "__main__":
    unittest.main()
