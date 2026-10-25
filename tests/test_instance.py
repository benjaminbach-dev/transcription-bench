"""Tests du verrou système d'instance : refus, persistance, arrêt brutal.

Le verrou est un verrou de fichier du système d'exploitation
(`fcntl.flock`/`msvcrt.locking`), pas un fichier de PID. Les tests à deux vrais
processus tuent volontairement le détenteur pour vérifier que le système libère
le verrou sans intervention. Ils ne valent pas qualification Windows.
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

from transcription_bench.instance import InstanceDejaActive, VerrouInstance
from transcription_bench.paths import RACINE_PROJET

DELAI_PROCESSUS = 60.0

CODE_TENIR_VERROU = """
import sys, time
from pathlib import Path
from transcription_bench.instance import VerrouInstance

VerrouInstance(Path(sys.argv[1])).acquerir()
Path(sys.argv[2]).write_text("verrou tenu", encoding="utf-8")
time.sleep(60)
"""


def attendre_fichier(chemin: Path, delai: float = 30.0) -> None:
    echeance = time.monotonic() + delai
    while time.monotonic() < echeance:
        if chemin.exists():
            return
        time.sleep(0.05)
    raise AssertionError(f"marqueur absent dans le délai imparti : {chemin}")


class VerrouInstanceTest(unittest.TestCase):
    def setUp(self) -> None:
        temporaire = tempfile.TemporaryDirectory()
        self.addCleanup(temporaire.cleanup)
        self.dossier = Path(temporaire.name)
        self.donnees = self.dossier / "data-projet"

    def test_cree_la_racine_et_le_fichier_persistant(self) -> None:
        verrou = VerrouInstance(self.donnees)
        self.assertFalse(self.donnees.exists())

        verrou.acquerir()
        self.assertTrue(verrou.detenu)
        self.assertEqual(verrou.chemin, self.donnees / "instance.lock")
        self.assertTrue(verrou.chemin.is_file())

        verrou.liberer()
        self.assertFalse(verrou.detenu)
        self.assertTrue(
            verrou.chemin.exists(),
            "le fichier de verrou ne doit pas être supprimé : pas de course d'unlink",
        )

    def test_seconde_acquisition_refusee_puis_acceptee_apres_liberation(self) -> None:
        premier = VerrouInstance(self.donnees).acquerir()
        self.addCleanup(premier.liberer)

        with self.assertRaises(InstanceDejaActive) as capture:
            VerrouInstance(self.donnees).acquerir()

        self.assertIn("instance", str(capture.exception))
        self.assertIn(str(self.donnees / "instance.lock"), str(capture.exception))

        premier.liberer()
        second = VerrouInstance(self.donnees).acquerir()
        self.addCleanup(second.liberer)
        self.assertTrue(second.detenu)

    def test_liberation_idempotente_et_contexte(self) -> None:
        verrou = VerrouInstance(self.donnees).acquerir()
        verrou.liberer()
        verrou.liberer()
        self.assertFalse(verrou.detenu)

        with VerrouInstance(self.donnees) as contextuel:
            self.assertTrue(contextuel.detenu)
        self.assertFalse(contextuel.detenu)

    def test_deux_processus_refus_puis_liberation_apres_arret_brutal(self) -> None:
        marqueur = self.dossier / "pret"
        processus = subprocess.Popen(
            [sys.executable, "-c", CODE_TENIR_VERROU, str(self.donnees), str(marqueur)],
            cwd=RACINE_PROJET,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
        )
        self.addCleanup(self._arreter, processus)
        attendre_fichier(marqueur)

        with self.assertRaises(InstanceDejaActive):
            VerrouInstance(self.donnees).acquerir()

        processus.kill()
        processus.wait(timeout=DELAI_PROCESSUS)

        verrou = VerrouInstance(self.donnees).acquerir()
        self.addCleanup(verrou.liberer)
        self.assertTrue(verrou.detenu)

    def _arreter(self, processus: subprocess.Popen[str]) -> None:
        if processus.poll() is None:
            processus.kill()
            processus.wait(timeout=DELAI_PROCESSUS)
        if processus.stderr is not None:
            processus.stderr.close()


if __name__ == "__main__":
    unittest.main()
