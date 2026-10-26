"""Tests de l'environnement du processus moteur, sans moteur ni réseau.

Les bases d'environnement sont de petits dictionnaires factices. Les assertions
ne portent que sur les clés HF/PYTHON* utilisées et `PATH` ; aucun test
n'affiche ni ne compare l'environnement complet du processus.
"""

from __future__ import annotations

import os
import unittest
from pathlib import Path
from unittest import mock

from engines.hors_ligne import (
    commande_runner,
    environnement_moteur,
    mode_hors_ligne,
    options_modele,
)


class EnvironnementMoteurTest(unittest.TestCase):
    def test_copie_neuve_force_hf_et_retire_les_variables_python(self) -> None:
        base = {
            "HF_HUB_OFFLINE": "0",
            "HF_HOME": "/hf-factice",
            "PYTHONHOME": "/python-serveur",
            "PYTHONPATH": "/lib-serveur",
            "VIRTUAL_ENV": "/venv-serveur",
            "PATH": "/usr/bin",
        }
        env = environnement_moteur(base)

        self.assertIsNot(env, base)
        self.assertEqual(env["HF_HUB_OFFLINE"], "1")
        self.assertEqual(base["HF_HUB_OFFLINE"], "0")
        self.assertEqual(env["HF_HOME"], "/hf-factice")
        for cle in ("PYTHONHOME", "PYTHONPATH", "VIRTUAL_ENV"):
            self.assertNotIn(cle, env)
        self.assertEqual(env["PATH"], "/usr/bin")

    def test_sans_base_ne_modifie_pas_os_environ(self) -> None:
        with mock.patch.dict(os.environ, {"HF_HUB_OFFLINE": "0"}):
            env = environnement_moteur()

            self.assertIsNot(env, os.environ)
            self.assertEqual(env["HF_HUB_OFFLINE"], "1")
            self.assertEqual(os.environ["HF_HUB_OFFLINE"], "0")

    def test_contexte_force_puis_restaure(self) -> None:
        with mock.patch.dict(os.environ, {"HF_HUB_OFFLINE": "0"}):
            with mode_hors_ligne():
                self.assertEqual(os.environ["HF_HUB_OFFLINE"], "1")
            self.assertEqual(os.environ["HF_HUB_OFFLINE"], "0")

    def test_commande_runner_preserve_le_chemin_de_l_interpreteur(self) -> None:
        # Un lien de venv ne doit jamais être résolu : le CPython géré perdrait
        # numpy et les paquets du moteur.
        commande = commande_runner("/venv-moteur/bin/python", "job.json")

        self.assertEqual(commande[0], "/venv-moteur/bin/python")
        self.assertTrue(commande[1].endswith("runner.py"))
        self.assertEqual(commande[2], str(Path("job.json").resolve()))

    def test_options_modele_forcent_le_chargement_local_sans_mutation(self) -> None:
        modele = {
            "identifiant": "org/modele",
            "local_files_only": False,
            "trust_remote_code": True,
        }
        options = options_modele(modele)

        self.assertIsNot(options, modele)
        self.assertIs(options["local_files_only"], True)
        self.assertIs(options["trust_remote_code"], False)
        self.assertIs(modele["local_files_only"], False)
        self.assertIs(modele["trust_remote_code"], True)
        self.assertEqual(options["identifiant"], "org/modele")


if __name__ == "__main__":
    unittest.main()
