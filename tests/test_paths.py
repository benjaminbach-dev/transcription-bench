"""Tests de la préparation des dossiers de données prédéfinis sous `data/`."""

from __future__ import annotations

import contextlib
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from transcription_bench import paths
from transcription_bench.paths import DOSSIERS_DATA, preparer_dossiers_data


class DossiersDataTest(unittest.TestCase):
    def test_base_par_defaut_ancre_a_la_racine_du_projet(self) -> None:
        self.assertEqual(paths.DOSSIER_DATA, paths.RACINE_PROJET / "data")
        self.assertTrue((paths.RACINE_PROJET / "pyproject.toml").is_file())

    def test_cree_les_dossiers_manquants(self) -> None:
        with tempfile.TemporaryDirectory() as dossier:
            chemins = preparer_dossiers_data(Path(dossier) / "data")
            self.assertEqual(sorted(chemins), sorted(DOSSIERS_DATA))
            for nom, chemin in chemins.items():
                self.assertTrue(chemin.is_dir(), nom)
                self.assertEqual(chemin, Path(dossier) / "data" / nom)

    def test_idempotent_et_conserve_les_fichiers_existants(self) -> None:
        with tempfile.TemporaryDirectory() as dossier:
            base = Path(dossier) / "data"
            preparer_dossiers_data(base)
            temoin = base / "audio" / "exemple.wav"
            temoin.write_bytes(b"contenu existant")

            chemins = preparer_dossiers_data(base)

            self.assertTrue(temoin.is_file())
            self.assertEqual(temoin.read_bytes(), b"contenu existant")
            self.assertEqual(sorted(chemins), sorted(DOSSIERS_DATA))

    def test_base_par_defaut_independante_du_dossier_courant(self) -> None:
        with tempfile.TemporaryDirectory() as dossier, tempfile.TemporaryDirectory() as ailleurs:
            base = Path(dossier) / "data-projet"
            with mock.patch.object(paths, "DOSSIER_DATA", base):
                with contextlib.chdir(ailleurs):
                    chemins = preparer_dossiers_data()

            for nom, chemin in chemins.items():
                self.assertTrue(chemin.is_dir(), nom)
                self.assertEqual(chemin, base / nom)
            self.assertEqual(os.listdir(ailleurs), [])
