"""Format lisible des tailles de modèles, partagé par la CLI.

La page Modèles et ses actions POST ont été retirées de l'interface web (change
`alleger-interface-web`, tâche 1.1) : l'inventaire, la vérification, le
téléchargement et la suppression se pilotent par la CLI, dont les tests vivent
dans `tests/test_commands.py`.
"""

from __future__ import annotations

import unittest

from transcription_bench.web.vues_modeles import formater_taille_modele


class TailleModeleTest(unittest.TestCase):
    """Format lisible des tailles de modèles, sans octets bruts."""

    def test_format_binaire_sans_octets_bruts(self) -> None:
        cas = {
            None: "taille inconnue",
            0: "0 Mio",
            10: "< 0,1 Mio",
            104_857: "< 0,1 Mio",
            104_858: "0,1 Mio",
            1_048_576: "1 Mio",
            3 * 1_048_576 // 2: "1,5 Mio",
            2 * 1024**3 + 1024**3 // 2: "2,5 Gio",
            -1: "indisponible",
            True: "indisponible",
            "1024": "indisponible",
            1.5: "indisponible",
        }
        for valeur, attendu in cas.items():
            with self.subTest(valeur=valeur):
                self.assertEqual(formater_taille_modele(valeur), attendu)


if __name__ == "__main__":
    unittest.main()
