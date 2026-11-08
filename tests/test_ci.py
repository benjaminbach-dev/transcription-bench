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


class ListeBlancheRapportsTests(unittest.TestCase):
    """Contrat des rapports JSON nettoyés : aucune donnée sensible publiée."""

    #: Noms interdits dans un rapport publié, y compris les nouveaux champs système.
    CHAMPS_SENSIBLES = (
        "transcription", "texte", "texte_transcrit", "audio", "audio_chemin",
        "chemin", "chemin_audio", "dossier", "utilisateur", "home", "cwd",
        "cache", "artefact", "run_json", "result_json", "observation_systeme",
        "cpu", "memoire", "memoire_apres", "pourcentage_moyen", "intervalle_s",
        "motif", "provenance", "methode_cpu", "version_psutil",
    )

    def ecrire(self, nom: str, contenu: dict) -> tuple[list[str], str, dict]:
        """Appeler `rapport()` dans un dossier isolé et relire ce qui est publié."""
        with tempfile.TemporaryDirectory() as dossier:
            rapports = Path(dossier) / "rapports"
            with patch.object(ci, "RAPPORTS", rapports), \
                    patch.object(ci.subprocess, "check_output", return_value="uv 0.11.8"), \
                    patch.dict(os.environ, {}, clear=True), \
                    patch("builtins.print"):
                ci.rapport(nom, contenu)
            fichiers = [p.name for p in rapports.iterdir()]
            texte = (rapports / f"{nom}.json").read_text(encoding="utf-8")
        return fichiers, texte, json.loads(texte)

    def test_rapport_ecrit_seulement_le_json_prevu(self):
        fichiers, _, preuve = self.ecrire("ressources", {"but": "compatibilité, pas performance représentative"})
        self.assertEqual(fichiers, ["ressources.json"])
        self.assertEqual(set(preuve), set(ci.CHAMPS_RAPPORT))
        self.assertEqual(preuve["verification"], {"but": "compatibilité, pas performance représentative"})

    def test_rapport_refuse_transcription_et_chemin(self):
        with tempfile.TemporaryDirectory() as dossier:
            rapports = Path(dossier) / "rapports"
            with patch.object(ci, "RAPPORTS", rapports):
                for contenu in ({"but": "x", "transcription": "bonjour"},
                                {"but": "x", "chemin": "/home/utilisateur/data"}):
                    with self.assertRaisesRegex(RuntimeError, "non autorisé"):
                        ci.rapport("ressources", contenu)
            # Un refus n'écrit rien : ni fichier, ni dossier de cache.
            self.assertFalse(rapports.exists())

    def test_rapport_refuse_observation_systeme(self):
        contenu = {"but": "x", "observation_systeme": {"version": 1, "provenance": "reelle"}}
        with self.assertRaisesRegex(RuntimeError, "non autorisé"):
            ci.verifier_rapport("ressources", contenu)

    def test_rapport_refuse_champ_de_parole_supplementaire(self):
        parole = {"voix": "Voix de test", "culture_voix": "en-US", "texte_langue": "en",
                  "audio_sha256": "0" * 64, "duree_source_s": 0.01,
                  "langue_imposee": None, "texte": "bonjour"}
        with self.assertRaisesRegex(RuntimeError, "parole non autorisé"):
            ci.verifier_rapport("inference-faster-whisper", {"parole": parole})

    def test_rapport_refuse_nom_hors_format(self):
        for nom in ("../evasion", "rapport/annexe", "Rapport", ""):
            with self.assertRaisesRegex(RuntimeError, "invalide"):
                ci.verifier_rapport(nom, {})

    def test_liste_blanche_exclut_tout_champ_sensible(self):
        for champs in (set(ci.CHAMPS_RAPPORT), *ci.CHAMPS_VERIFICATION.values()):
            self.assertEqual(champs & set(self.CHAMPS_SENSIBLES), set())
        # Contrôle négatif : la liste blanche n'est pas un refus général.
        self.assertIn("texte_non_vide", ci.CHAMPS_VERIFICATION["inference"])
        self.assertIn("audio_sha256", ci.CHAMPS_VERIFICATION["inference"])
        self.assertIn("ram_octets", ci.CHAMPS_RAPPORT)

    def test_familles_couvrent_les_rapports_reels(self):
        self.assertEqual(ci.champs_verification("ressources"), ci.CHAMPS_VERIFICATION["ressources"])
        for moteur in ci.MOTEURS:
            self.assertEqual(ci.champs_verification(f"installation-{moteur}"),
                             ci.CHAMPS_VERIFICATION["installation"])
        for cas in ci.CAS:
            self.assertEqual(ci.champs_verification(f"modele-{cas}"), ci.CHAMPS_VERIFICATION["modele"])
            self.assertEqual(ci.champs_verification(f"inference-{cas}"), ci.CHAMPS_VERIFICATION["inference"])
        with self.assertRaisesRegex(RuntimeError, "liste blanche"):
            ci.champs_verification("autre-1")

    def creer_evenement(self) -> dict:
        """Événement volontairement chargé en données qui ne doivent pas sortir."""
        return {
            "duree_audio_s": 1.25,
            "texte": "bonjour ceci est une transcription privée",
            "chemin": "/home/utilisateur/Données/parole.wav",
            "threads_demandes": 4, "threads_appliques": 4,
            "reglages_effectifs": {"device_relu": "cpu", "compute_type": "int8"},
            "timings_natifs": {"load_ms": 1.0, "mel_ms": 2.0},
            "observation_systeme": {
                "version": 1, "methode_cpu": "psutil-cpu-percent-nonbloquant-v1",
                "version_psutil": "7.2.2", "provenance": "reelle",
                "cpu": {"pourcentage_moyen": 42.5, "intervalle_s": 3.2, "motif": None},
                "memoire_apres": {"totale_octets": 17_174_360_064,
                                  "disponible_octets": 11_811_440_640, "motif": None},
            },
        }

    def parole(self) -> dict:
        return {"voix": "Voix de test", "culture_voix": "en-US", "texte_langue": "en",
                "audio_sha256": "a" * 64, "duree_source_s": 0.01, "langue_imposee": "fr"}

    def test_preuve_inference_sans_texte_ni_chemin_ni_observation(self):
        preuve = ci.preuve_inference("faster-whisper", "b" * 40, self.parole(), self.creer_evenement())
        ci.verifier_rapport("inference-faster-whisper", preuve)
        texte = json.dumps(preuve, ensure_ascii=False)
        self.assertNotIn("bonjour", texte)
        self.assertNotIn("privée", texte)
        self.assertNotIn("utilisateur", texte)
        self.assertNotIn("/home", texte)
        self.assertNotIn("observation_systeme", texte)
        self.assertNotIn("motif", texte)
        self.assertNotIn("provenance", texte)
        self.assertNotIn("psutil", texte)
        self.assertTrue(preuve["texte_non_vide"])
        self.assertEqual(preuve["caracteres"], len("bonjour ceci est une transcription privée"))
        self.assertEqual(preuve["audio_sha256"], "a" * 64)
        self.assertEqual(preuve["cpu_relu"], "cpu")
        self.assertEqual(preuve["reglages_effectifs"], {"device_relu": "cpu", "compute_type": "int8"})

    def test_rapport_inference_publie_sans_donnee_sensible(self):
        preuve = ci.preuve_inference("faster-whisper", "b" * 40, self.parole(), self.creer_evenement())
        fichiers, texte, relu = self.ecrire("inference-faster-whisper", preuve)
        self.assertEqual(fichiers, ["inference-faster-whisper.json"])
        for interdit in ("bonjour", "/home", "utilisateur", "observation_systeme",
                         "provenance", "psutil"):
            self.assertNotIn(interdit, texte)
        self.assertEqual(set(relu["verification"]), set(preuve))
        self.assertEqual(relu["verification"], preuve)

    def test_contenus_actuels_acceptes(self):
        """Les rapports réellement produits restent dans la liste blanche."""
        contenus = (
            ("ressources", {"but": "compatibilité, pas performance représentative"}),
            ("installation-faster-whisper", {
                "moteur": "faster-whisper", "versions": {"faster-whisper": "1.0"},
                "runner_factice": True, "import_adaptateur": True}),
            ("modele-faster-whisper", {
                "cas": "faster-whisper", "revision": "c" * 40, "depot": "depot/nom",
                "licence_declaree": "MIT", "source": "https://huggingface.co/depot/nom",
                "fichiers": ["model.bin"]}),
            ("inference-faster-whisper", {
                "cas": "faster-whisper", "etat": "controle_non_concluant",
                "raison": "transcription_vide", "parole": self.parole(),
                "evaluation_qualite": False}),
            ("inference-faster-whisper",
             ci.preuve_inference("faster-whisper", "c" * 40, self.parole(), self.creer_evenement())),
        )
        for nom, contenu in contenus:
            with self.subTest(nom=nom):
                ci.verifier_rapport(nom, contenu)

    def test_workflows_sans_nouvel_artefact_ni_cache(self):
        import re
        prefixes = set()
        for chemin in (CHEMIN.parents[2] / ".github" / "workflows").glob("*.yml"):
            texte = chemin.read_text(encoding="utf-8")
            self.assertNotIn("actions/cache", texte)
            self.assertNotIn("path: data/ci/rapports/**", texte)
            for nom in re.findall(r"^\s*name: (contexte|import|inference)-\$", texte, re.MULTILINE):
                prefixes.add(nom)
        self.assertEqual(prefixes, {"contexte", "import", "inference"})


if __name__ == "__main__":
    unittest.main()
