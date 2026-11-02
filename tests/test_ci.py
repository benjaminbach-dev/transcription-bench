"""Contrôles du harnais CI sans réseau, installation ni moteur réel."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import tempfile
import unittest
import wave
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

CHEMIN = Path(__file__).resolve().parents[1] / "scripts" / "ci" / "verifier.py"
SPEC = importlib.util.spec_from_file_location("verification_ci", CHEMIN)
ci = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ci)


class VerificationCiTests(unittest.TestCase):
    def test_import_sans_creation_de_donnees(self):
        self.assertEqual(ci.DONNEES, CHEMIN.parents[2] / "data" / "ci")

    def test_refuse_contexte_local_avant_services(self):
        with patch.dict(os.environ, {}, clear=True), patch.object(ci, "services") as services:
            with self.assertRaises(RuntimeError):
                ci.installer("faster-whisper")
            services.assert_not_called()

    def test_refuse_runner_prive_avant_services(self):
        env = {"GITHUB_ACTIONS": "true", "RUNNER_OS": "Windows", "TB_DEPOT_PUBLIC": "false"}
        with patch.dict(os.environ, env, clear=True), patch.object(ci, "services") as services:
            with self.assertRaises(RuntimeError):
                ci.preparer("faster-whisper")
            services.assert_not_called()

    def test_refuse_linux_pour_moteurs_windows(self):
        env = {"GITHUB_ACTIONS": "true", "RUNNER_OS": "Linux", "TB_DEPOT_PUBLIC": "true"}
        with patch.dict(os.environ, env, clear=True):
            with self.assertRaises(RuntimeError):
                ci.exiger_ci_publique()

    def test_accepte_contexte_ci_public_explicite(self):
        env = {"GITHUB_ACTIONS": "true", "RUNNER_OS": "Windows", "TB_DEPOT_PUBLIC": "true"}
        with patch.dict(os.environ, env, clear=True):
            ci.exiger_ci_publique()

    def test_workflows_actions_epinglees_et_permissions_minimales(self):
        import re
        for chemin in (CHEMIN.parents[2] / ".github" / "workflows").glob("*.yml"):
            texte = chemin.read_text(encoding="utf-8")
            self.assertIn("contents: read", texte)
            self.assertIn('enable-cache: "false"', texte)
            self.assertIn("persist-credentials: false", texte)
            self.assertNotIn("secrets.", texte)
            self.assertNotIn("pull_request_target", texte)
            for action in re.findall(r"uses:\s*(\S+)", texte):
                self.assertRegex(action, r"^[^@]+@[0-9a-f]{40}$")

    def test_artefacts_limites_aux_rapports(self):
        for chemin in (CHEMIN.parents[2] / ".github" / "workflows").glob("*.yml"):
            chemins = [ligne.strip() for ligne in chemin.read_text(encoding="utf-8").splitlines()
                       if ligne.strip().startswith("path:")]
            self.assertTrue(all(ligne == "path: data/ci/rapports/*.json" for ligne in chemins))

    def test_modeles_uniquement_revisions_figees(self):
        self.assertEqual(len(ci.CAS), 4)
        for choix in ci.CAS.values():
            self.assertRegex(choix["revision"], r"^[0-9a-f]{40}$")
            self.assertIn(choix["moteur"], ci.MOTEURS)

    def test_environnement_hors_ligne_sans_mutation(self):
        with patch.dict(os.environ, {"HF_HUB_OFFLINE": "0", "PYTHONPATH": "a-retirer"}):
            env = ci.environnement_hors_ligne()
            self.assertEqual(env["HF_HUB_OFFLINE"], "1")
            self.assertNotIn("PYTHONPATH", env)
            self.assertTrue(Path(env["NUMBA_CACHE_DIR"]).is_relative_to(ci.DONNEES))
            self.assertEqual(os.environ["HF_HUB_OFFLINE"], "0")

    def creer_parole(self, dossier, *, culture="en-US", texte="en", trames=160):
        chemin = Path(dossier) / "parole.wav"
        with wave.open(str(chemin), "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(16000)
            wav.writeframes(b"\x00\x00" * trames)
        metadata = {"voix": "Voix de test", "culture_voix": culture,
                    "texte_langue": texte,
                    "sha256": hashlib.sha256(chemin.read_bytes()).hexdigest()}
        chemin.with_suffix(".json").write_text(json.dumps(metadata), encoding="utf-8")
        return chemin

    def test_parole_anglaise_et_langue_moteur_fr_separees(self):
        with tempfile.TemporaryDirectory() as dossier:
            preuve = ci.preuve_audio(self.creer_parole(dossier), langue_imposee="fr")
        self.assertEqual(preuve["culture_voix"], "en-US")
        self.assertEqual(preuve["texte_langue"], "en")
        self.assertEqual(preuve["langue_imposee"], "fr")
        self.assertEqual(preuve["duree_source_s"], 0.01)
        self.assertNotIn("texte", preuve)

    def test_parole_sans_langue_moteur_imposee(self):
        with tempfile.TemporaryDirectory() as dossier:
            preuve = ci.preuve_audio(self.creer_parole(dossier), langue_imposee=None)
        self.assertIsNone(preuve["langue_imposee"])

    def test_culture_voix_differente_du_texte_pas_jugee(self):
        with tempfile.TemporaryDirectory() as dossier:
            preuve = ci.preuve_audio(self.creer_parole(dossier, culture="de-DE", texte="en"))
        self.assertEqual(preuve["culture_voix"], "de-DE")
        self.assertEqual(preuve["texte_langue"], "en")

    def test_parole_empreinte_incorrecte_refusee(self):
        with tempfile.TemporaryDirectory() as dossier:
            chemin = self.creer_parole(dossier)
            metadata = json.loads(chemin.with_suffix(".json").read_text(encoding="utf-8"))
            metadata["sha256"] = "0" * 64
            chemin.with_suffix(".json").write_text(json.dumps(metadata), encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "ne correspondent pas"):
                ci.preuve_audio(chemin)

    def test_parole_metadata_absente_refusee(self):
        with tempfile.TemporaryDirectory() as dossier:
            chemin = self.creer_parole(dossier)
            chemin.with_suffix(".json").write_text("{}", encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "Métadonnée"):
                ci.preuve_audio(chemin)

    def test_parole_duree_nulle_refusee(self):
        with tempfile.TemporaryDirectory() as dossier:
            with self.assertRaisesRegex(RuntimeError, "durée nulle"):
                ci.preuve_audio(self.creer_parole(dossier, trames=0))

    def test_attente_echoue_sur_delai(self):
        creneau = Mock()
        creneau.attendre_thread.return_value = False
        with self.assertRaises(RuntimeError):
            ci.attendre(creneau, 1)

    def test_attente_ne_masque_pas_operation_echouee(self):
        creneau = Mock()
        creneau.attendre_thread.return_value = True
        creneau.instantane.return_value = SimpleNamespace(etat="echouee")
        with self.assertRaises(RuntimeError):
            ci.attendre(creneau, 1)

    def test_attente_operation_terminee(self):
        creneau = Mock()
        creneau.attendre_thread.return_value = True
        creneau.instantane.return_value = SimpleNamespace(etat="terminee")
        ci.attendre(creneau, 1)


if __name__ == "__main__":
    unittest.main()
