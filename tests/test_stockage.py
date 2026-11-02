"""Réessai du remplacement atomique sous Windows (contention de lecteur).

Un lecteur peut détenir le fichier cible un instant sous Windows : `os.replace`
échoue alors par `PermissionError`. Les trois comportements attendus sont
vérifiés de façon déterministe, sans dépendre de la plateforme.
"""

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import transcription_bench.stockage as stockage
from transcription_bench.stockage import ecrire_json_atomique


class RemplacementAtomiqueTest(unittest.TestCase):
    def setUp(self) -> None:
        temporaire = tempfile.TemporaryDirectory()
        self.addCleanup(temporaire.cleanup)
        self.chemin = Path(temporaire.name) / "run.json"

    def _fichiers_du_dossier(self) -> list[str]:
        return sorted(entree.name for entree in self.chemin.parent.iterdir())

    def test_permission_ephemere_puis_succes(self) -> None:
        """Un refus transitoire est retenté puis l'écriture réussit."""
        appels: list[tuple[str, str]] = []
        vraie = os.replace

        def remplacer(source, cible):
            appels.append((source, cible))
            if len(appels) == 1:
                raise PermissionError("lecteur Windows détient le fichier")
            vraie(source, cible)

        self.chemin.write_text('{"etat": "ancien"}', encoding="utf-8")
        with (
            mock.patch.object(stockage, "DELAI_REMPLACEMENT_S", 0),
            mock.patch("os.replace", side_effect=remplacer),
        ):
            ecrire_json_atomique(self.chemin, {"etat": "nouveau"})

        self.assertEqual(len(appels), 2)
        self.assertEqual(
            json.loads(self.chemin.read_text(encoding="utf-8"))["etat"], "nouveau"
        )
        self.assertEqual(self._fichiers_du_dossier(), [self.chemin.name])

    def test_permission_persistante_propagee_sans_ecriture_en_place(self) -> None:
        """À épuisement des tentatives, l'erreur remonte et l'ancien reste intact."""
        self.chemin.write_text('{"etat": "ancien"}', encoding="utf-8")

        def refuser(source, cible):
            raise PermissionError("lecteur persistant")

        with (
            mock.patch.object(stockage, "DELAI_REMPLACEMENT_S", 0),
            mock.patch("os.replace", side_effect=refuser) as remplace,
        ):
            with self.assertRaises(PermissionError):
                ecrire_json_atomique(self.chemin, {"etat": "nouveau"})

        self.assertEqual(remplace.call_count, stockage.NB_REMPLACEMENTS)
        self.assertEqual(
            json.loads(self.chemin.read_text(encoding="utf-8"))["etat"], "ancien"
        )
        self.assertEqual(self._fichiers_du_dossier(), [self.chemin.name])

    def test_autre_erreur_sans_reessai(self) -> None:
        """Seule `PermissionError` est retentée ; une autre erreur est immédiate."""

        def refuser(source, cible):
            raise OSError("espace insuffisant")

        with (
            mock.patch.object(stockage, "DELAI_REMPLACEMENT_S", 0),
            mock.patch("os.replace", side_effect=refuser) as remplace,
        ):
            with self.assertRaises(OSError):
                ecrire_json_atomique(self.chemin, {"etat": "nouveau"})

        self.assertEqual(remplace.call_count, 1)
        # Aucun fichier partiel ni temporaire n'est laissé.
        self.assertEqual(self._fichiers_du_dossier(), [])


if __name__ == "__main__":
    unittest.main()
