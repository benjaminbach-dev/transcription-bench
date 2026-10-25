"""Tests du garde-fou de récupération des exécutions antérieures.

La clôture réelle relève de la tâche 6.5 : par défaut le démarrage est refusé
si un `run.json` n'est pas dans un état final, sans qu'aucun fichier ne soit
créé, modifié ni supprimé.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from transcription_bench.recuperation import (
    ETATS_FINAUX,
    EtatAnterieurNonTraitable,
    verifier_executions_anterieures,
)


class RecuperationAnterieureTest(unittest.TestCase):
    def setUp(self) -> None:
        temporaire = tempfile.TemporaryDirectory()
        self.addCleanup(temporaire.cleanup)
        self.donnees = Path(temporaire.name) / "data-projet"

    def ecrire_run(self, nom: str, contenu: object) -> Path:
        dossier = self.donnees / "results" / nom
        dossier.mkdir(parents=True)
        run_json = dossier / "run.json"
        if isinstance(contenu, str):
            run_json.write_text(contenu, encoding="utf-8")
        else:
            run_json.write_text(json.dumps(contenu), encoding="utf-8")
        return run_json

    def arborescence(self) -> dict[str, bytes]:
        return {
            str(chemin.relative_to(self.donnees)): chemin.read_bytes()
            for chemin in sorted(self.donnees.rglob("*"))
            if chemin.is_file()
        }

    def test_sans_dossier_de_resultats_aucun_refus(self) -> None:
        verifier_executions_anterieures(self.donnees)
        self.assertFalse(self.donnees.exists())

    def test_resultats_finaux_acceptes_sans_modification(self) -> None:
        for etat in sorted(ETATS_FINAUX):
            self.ecrire_run(f"20260101-120000-{etat}", {"etat": etat, "audios": []})
        avant = self.arborescence()

        verifier_executions_anterieures(self.donnees)

        self.assertEqual(self.arborescence(), avant)

    def test_execution_restee_en_cours_refusee_sans_modification(self) -> None:
        run_json = self.ecrire_run(
            "20260101-120000-encours", {"etat": "running", "audios": ["a.wav"]}
        )
        avant = self.arborescence()

        with self.assertRaises(EtatAnterieurNonTraitable) as capture:
            verifier_executions_anterieures(self.donnees)

        message = str(capture.exception)
        self.assertIn("exécution restée en cours", message)
        self.assertIn(str(run_json), message)
        self.assertIn("tâche 6.5", message)
        self.assertIn("aucun fichier n'a été modifié", message)
        self.assertEqual(self.arborescence(), avant)

    def test_etat_inconnu_ou_incoherent_refuse_sans_modification(self) -> None:
        cas = {
            "etat-inconnu": {"etat": "en-cours-peut-etre"},
            "sans-etat": {"audios": []},
            "etat-non-texte": {"etat": 3},
            "liste": [],
            "json-casse": "{ pas du json",
            "objet-vide": {},
        }
        for nom, contenu in cas.items():
            with self.subTest(nom=nom):
                temporaire = tempfile.TemporaryDirectory()
                self.addCleanup(temporaire.cleanup)
                self.donnees = Path(temporaire.name) / "data-projet"
                self.ecrire_run(nom, contenu)
                avant = self.arborescence()

                with self.assertRaises(EtatAnterieurNonTraitable):
                    verifier_executions_anterieures(self.donnees)

                self.assertEqual(self.arborescence(), avant)


if __name__ == "__main__":
    unittest.main()
