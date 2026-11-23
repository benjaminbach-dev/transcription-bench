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


# --- Driver CLI Windows : scripts/ci/cli_windows.py (tâche 4.5, route A) ---
# Tests hors réseau : sorties simulées, répertoires temporaires, aucune CLI réelle.

import io
import shutil
import subprocess
import sys
import time

CHEMIN_CLI = Path(__file__).resolve().parents[1] / "scripts" / "ci" / "cli_windows.py"
SPEC_CLI = importlib.util.spec_from_file_location("cli_windows", CHEMIN_CLI)
cli = importlib.util.module_from_spec(SPEC_CLI)
# Enregistré avant exécution : les dataclasses du driver consultent sys.modules.
sys.modules[SPEC_CLI.name] = cli
SPEC_CLI.loader.exec_module(cli)
CONTEXTE_CI = {"GITHUB_ACTIONS": "true", "RUNNER_OS": "Windows", "TB_DEPOT_PUBLIC": "true"}


def sortie(code=0, stdout=b"", stderr=b""):
    return cli.Sortie(code, stdout, stderr)


class DriverCliBase(unittest.TestCase):
    def setUp(self):
        dossier = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, dossier, True)
        # Aucune écriture dans data/ ou data/ci du dépôt pendant ces tests.
        self.enterContext(patch.object(cli, "SORTIES", dossier / "cli"))
        self.enterContext(patch.object(cli, "DONNEES_CLI", dossier / "data"))

    def jouer(self, etape, resultat, ctx=None):
        ctx = ctx or cli.Contexte(phase="lecture")
        with patch.object(cli, "lancer_cli", return_value=resultat):
            cli.executer_commande(etape, ctx)
        return ctx.etapes[-1]


class CliWindowsDriverTests(DriverCliBase):
    def test_phases_et_identifiants_uniques(self):
        self.assertEqual(cli.PHASES, ("lecture", "modele-installation", "modele-telechargement",
                                      "modele-execution"))
        for phase in cli.PHASES:
            etapes = [e for e in cli.CONSTRUCTEURS[phase]() if isinstance(e, cli.Etape)]
            identifiants = [e.id for e in etapes]
            self.assertEqual(len(identifiants), len(set(identifiants)), phase)
            self.assertTrue(all(e.attendu in (0, 1, 2, 3, None) for e in etapes), phase)
        self.assertIn(cli.interruption_moteur, cli.CONSTRUCTEURS["modele-execution"]())

    def test_code_attendu_et_sortie_json_valide(self):
        fiche = self.jouer(cli.Etape("T1", ("data", "check", "--json"), json=True),
                           sortie(0, '{"schema": 1, "a": "été"}\n'.encode()))
        self.assertEqual((fiche["statut"], fiche["schema"], fiche["code"]), ("ok", True, 0))

    def test_schema_faux_booleen_ou_texte_refuses(self):
        for brut in (b'{"schema": 2}\n', b'{"schema": true}\n', b'[1]\n', b'pas du json\n'):
            with self.subTest(brut=brut):
                fiche = self.jouer(cli.Etape("T2", ("x",), json=True), sortie(0, brut))
                self.assertEqual(fiche["statut"], "ecart")

    def test_sortie_non_utf8_refusee(self):
        self.assertEqual(self.jouer(cli.Etape("T3", ("x",)), sortie(0, b"\xff\xfe"))["statut"], "ecart")

    def test_code_hors_contrat_et_code_inattendu(self):
        self.assertEqual(self.jouer(cli.Etape("T4", ("x",)), sortie(4))["statut"], "ecart")
        self.assertEqual(self.jouer(cli.Etape("T5", ("x",), attendu=0), sortie(2))["statut"], "ecart")
        self.assertEqual(self.jouer(cli.Etape("T6", ("x",), attendu=2), sortie(2))["statut"], "ok")

    def test_motif_requis_dans_la_sortie_d_erreur(self):
        etape = cli.Etape("T7", ("x",), attendu=2, motifs=("séparateur",))
        ok = self.jouer(etape, sortie(2, stderr="transcription-bench : nom refusé : séparateur Windows".encode()))
        self.assertEqual((ok["statut"], ok["motif_present"]), ("ok", True))
        ecart = self.jouer(etape, sortie(2, b"autre raison"))
        self.assertEqual((ecart["statut"], ecart["motif_present"]), ("ecart", False))

    def test_trace_refusee_meme_avec_le_bon_code(self):
        fiche = self.jouer(cli.Etape("T8", ("x",)), sortie(0, stderr=b"Traceback (most recent call last):"))
        self.assertEqual(fiche["statut"], "ecart")

    def test_refus_avec_sortie_standard_non_vide_refuse(self):
        fiche = self.jouer(cli.Etape("T9", ("x",), attendu=2, json=True), sortie(2, b'{"schema": 1}\n'))
        self.assertEqual(fiche["statut"], "ecart")

    def test_refus_json_avec_objet_si_declare(self):
        etape = cli.Etape("T10", ("x",), attendu=2, json=True, sortie_refus=True)
        fiche = self.jouer(etape, sortie(2, b'{"schema": 1, "verification": {"accepte": false}}\n'))
        self.assertEqual(fiche["statut"], "ok")

    def test_json_vide_sur_succes_refuse(self):
        self.assertEqual(self.jouer(cli.Etape("T11", ("x",), json=True), sortie(0))["statut"], "ecart")

    def test_plusieurs_lignes_json_et_etat_de_la_derniere(self):
        brut = ('{"schema": 1, "event": "log", "line": "Modèle chargé"}\n'
                '{"schema": 1, "operation": "terminee", "execution": {"etat": "terminee"}}\n').encode()
        etape = cli.Etape("T12", ("run", "start"), json=True, champ_etat=("execution", "etat"),
                          etat_attendu="terminee")
        fiche = self.jouer(etape, sortie(0, brut))
        self.assertEqual((fiche["statut"], fiche["etat"]), ("ok", "terminee"))

    def test_etat_inattendu_ou_illisible_refuse(self):
        etape = cli.Etape("T13", ("x",), json=True, champ_etat=("etat",), etat_attendu="pret")
        self.assertEqual(self.jouer(etape, sortie(0, b'{"schema": 1, "etat": "non-installe"}\n'))["statut"],
                         "ecart")
        self.assertEqual(self.jouer(etape, sortie(0, '{"schema": 1, "etat": "Prêt"}\n'.encode()))["statut"],
                         "ecart")

    def test_observation_non_asserte(self):
        self.assertEqual(self.jouer(cli.Etape("T14", ("x",), attendu=None), sortie(3))["statut"], "observation")

    def test_non_concluant_n_est_jamais_un_succes(self):
        def verifie(objets, ctx):
            raise cli.EtapeNonConcluante("pas de conclusion")

        ctx = cli.Contexte(phase="lecture")
        fiche = self.jouer(cli.Etape("T15", ("x",), json=True, verifie=verifie), sortie(0, b'{"schema": 1}\n'),
                           ctx)
        self.assertEqual(fiche["statut"], "non_concluant")
        self.assertEqual(cli.conclusion(ctx.etapes), "non_concluant")

    def test_ecriture_dans_data_detectee(self):
        def lancer(arguments, **options):
            (cli.DONNEES_CLI / "audio").mkdir(parents=True)
            return sortie(0)

        ctx = cli.Contexte(phase="lecture")
        with patch.object(cli, "lancer_cli", side_effect=lancer):
            cli.executer_commande(cli.Etape("T16", ("--help",), aucune_ecriture=True), ctx)
        self.assertEqual(ctx.etapes[-1]["statut"], "ecart")

    def test_encodage_retire_seulement_pour_l_etape_temoin(self):
        resultat = subprocess.CompletedProcess([], 0, b"", b"")
        with patch.dict(os.environ, {"PYTHONIOENCODING": "utf-8"}), \
                patch.object(cli.subprocess, "run", return_value=resultat) as lancement:
            cli.lancer_cli(["data", "check"], delai=5, sans_encodage=True)
            self.assertNotIn("PYTHONIOENCODING", lancement.call_args.kwargs["env"])
            cli.lancer_cli(["data", "check"], delai=5, sans_encodage=False)
            self.assertEqual(lancement.call_args.kwargs["env"]["PYTHONIOENCODING"], "utf-8")

    def test_arret_brutal_termine_l_arbre(self):
        code = ("import subprocess, sys, time; "
                "subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)']); time.sleep(60)")
        proc = subprocess.Popen([sys.executable, "-c", code])
        self.addCleanup(lambda: proc.poll() is None and proc.kill())
        limite = time.monotonic() + 10
        while time.monotonic() < limite and not cli.psutil.Process(proc.pid).children():
            time.sleep(0.1)
        resultat = cli.arreter_arbre(proc)
        self.assertGreaterEqual(resultat["processus_arbre"], 2)
        self.assertEqual(resultat["survivants"], 0)

    def test_interruption_observee_puis_arret_brutal(self):
        # Faux moteur : vrai processus qui affiche « Modèle chargé » puis un descendant.
        script = Path(tempfile.mkdtemp()) / "moteur_simule.py"
        self.addCleanup(shutil.rmtree, script.parent, True)
        script.write_text(
            "import json, subprocess, sys, time\n"
            "subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])\n"
            "ligne = json.dumps({'schema': 1, 'line': 'Mod\\u00e8le charg\\u00e9 : essai'}, ensure_ascii=False)\n"
            "sys.stdout.buffer.write((ligne + '\\n').encode('utf-8'))\n"
            "sys.stdout.flush()\n"
            "time.sleep(60)\n", encoding="utf-8")
        ctx = cli.Contexte(phase="modele-execution")
        ctx.valeurs["REF"] = f"{cli.MOTEUR}/{'a' * 64}"
        with patch.object(cli, "commande_cli", return_value=[sys.executable, str(script)]):
            cli.interruption_moteur(ctx)
        self.assertEqual(ctx.etapes[-1]["statut"], "observation")
        self.assertEqual(ctx.extra["terminaison"]["survivants"], 0)
        self.assertGreaterEqual(ctx.extra["terminaison"]["processus_arbre"], 2)
        self.assertTrue((cli.SORTIES / "modele-execution" / "X08.stdout.txt").is_file())

    def test_verifications_du_depot_et_de_l_espace(self):
        ctx = cli.Contexte(phase="modele-telechargement")
        cli.verifie_refus_gguf([{"verification": {"accepte": False, "raison": "fichier-gguf-non-choisi"}}], ctx)
        with self.assertRaises(cli.EtapeEnEcart):
            cli.verifie_refus_gguf([{"verification": {"accepte": True}}], ctx)
        accepte = [{"verification": {"accepte": True, "commit": cli.REVISION, "taille_totale": 1000}}]
        with patch.object(cli.shutil, "disk_usage", return_value=SimpleNamespace(free=10**6)):
            cli.verifie_depot_accepte(accepte, ctx)
        self.assertEqual(ctx.extra["taille_totale_octets"], 1000)
        with patch.object(cli.shutil, "disk_usage", return_value=SimpleNamespace(free=10)):
            with self.assertRaises(cli.EtapeEnEcart):
                cli.verifie_depot_accepte(accepte, ctx)
        revision = [{"verification": {"accepte": True, "commit": "f" * 40, "taille_totale": 1}}]
        with patch.object(cli.shutil, "disk_usage", return_value=SimpleNamespace(free=10**6)):
            with self.assertRaises(cli.EtapeEnEcart):
                cli.verifie_depot_accepte(revision, ctx)

    def test_backend_cpu_confirme_ou_non_concluant(self):
        ctx = cli.Contexte(phase="modele-execution")
        cli.verifie_cpu([{"reglages_effectifs": [{"label": "backend_relu", "value": "CPU"}]}], ctx)
        self.assertIs(ctx.extra["cpu_relu"], True)
        with self.assertRaises(cli.EtapeEnEcart):
            cli.verifie_cpu([{"reglages_effectifs": [{"label": "Backend relu", "value": "CUDA"}]}], ctx)
        with self.assertRaises(cli.EtapeNonConcluante):
            cli.verifie_cpu([{"reglages_effectifs": []}], ctx)

    def test_interruption_non_concluante_si_deja_terminee(self):
        ctx = cli.Contexte(phase="modele-execution")
        ctx.valeurs["ID"] = "ancien"

        def historique(etat, identifiant="nouveau"):
            return [{"executions": [{"etat": etat, "identifiant": identifiant}]}]

        cli.verifie_interruption(historique("abandoned"), ctx)
        with self.assertRaises(cli.EtapeNonConcluante):
            cli.verifie_interruption(historique("completed"), ctx)
        with self.assertRaises(cli.EtapeEnEcart):
            cli.verifie_interruption(historique("running"), ctx)
        with self.assertRaises(cli.EtapeEnEcart):
            cli.verifie_interruption(historique("abandoned", "ancien"), ctx)

    def test_modele_d_essai_unique_et_reference_capturee(self):
        ctx = cli.Contexte(phase="modele-execution")
        cle = "a" * 64
        modele = {"moteur": cli.MOTEUR, "commit": cli.REVISION, "reference": f"{cli.MOTEUR}/{cle}", "cle": cle}
        cli.capture_modele_essai([{"models": [modele]}], ctx)
        self.assertEqual((ctx.valeurs["REF"], ctx.valeurs["CLE"]), (f"{cli.MOTEUR}/{cle}", cle))
        with self.assertRaises(cli.EtapeEnEcart):
            cli.capture_modele_essai([{"models": [modele, modele]}], ctx)

    def test_copie_parole_refusee_sans_metadonnees(self):
        ctx = cli.Contexte(phase="modele-installation")
        with tempfile.TemporaryDirectory() as dossier:
            source = Path(dossier) / "parole.wav"
            source.write_bytes(b"RIFF")
            with patch.object(cli, "PAROLE_SOURCE", source), \
                    patch.object(cli, "DONNEES_CLI", Path(dossier) / "data"):
                cli.copier_parole(ctx)
                self.assertEqual(ctx.etapes[-1]["statut"], "ecart")
                self.assertFalse((Path(dossier) / "data" / "audio" / "parole.wav").exists())

    def test_phase_modele_s_arrete_au_premier_ecart(self):
        etapes = [cli.Etape("A1", ("x",)), cli.Etape("A2", ("y",))]
        with patch.dict(cli.CONSTRUCTEURS, {"modele-installation": lambda: etapes}), \
                patch.object(cli, "lancer_cli", return_value=sortie(1)):
            ctx = cli.executer_phase("modele-installation")
        self.assertEqual([f["id"] for f in ctx.etapes], ["A1"])

    def test_phase_lecture_va_a_son_terme(self):
        etapes = [cli.Etape("A1", ("x",)), cli.Etape("A2", ("y",))]
        with patch.dict(cli.CONSTRUCTEURS, {"lecture": lambda: etapes}), \
                patch.object(cli, "lancer_cli", return_value=sortie(1)):
            ctx = cli.executer_phase("lecture")
        self.assertEqual([f["id"] for f in ctx.etapes], ["A1", "A2"])

    def test_main_refuse_hors_contexte_ci_sans_lancer(self):
        with patch.dict(os.environ, {}, clear=True), patch.object(cli, "lancer_cli") as lancement, \
                patch("sys.stdout", io.StringIO()), patch("sys.stderr", io.StringIO()):
            self.assertEqual(cli.main(["lecture"]), 1)
        lancement.assert_not_called()

    def test_main_publie_le_rapport_du_driver(self):
        etapes = [cli.Etape("B1", ("--help",))]
        with patch.dict(os.environ, CONTEXTE_CI, clear=True), \
                patch.dict(cli.CONSTRUCTEURS, {"lecture": lambda: etapes}), \
                patch.object(cli, "lancer_cli", return_value=sortie(0)), \
                patch.object(cli.verifier, "rapport") as rapport, \
                patch("sys.stdout", io.StringIO()), patch("sys.stderr", io.StringIO()):
            self.assertEqual(cli.main(["lecture"]), 0)
        nom, contenu = rapport.call_args.args
        self.assertEqual(nom, "cli-lecture")
        self.assertEqual(contenu["conclusion"], "ok")
        self.assertEqual(set(contenu), {"phase", "conclusion", "resume", "etapes"})

    def test_rapport_limite_a_la_liste_blanche(self):
        ctx = cli.Contexte(phase="modele-execution")
        self.jouer(cli.Etape("R1", ("run", "check"), json=True), sortie(0, b'{"schema": 1, "texte": "secret"}\n'),
                   ctx)
        ctx.extra["cpu_relu"] = True
        ctx.extra["chemin"] = "/home/utilisateur"
        rapport = cli.construire_rapport(ctx)
        self.assertNotIn("chemin", rapport)
        self.assertNotIn("secret", json.dumps(rapport))
        ci.verifier_rapport("cli-modele-execution", rapport)

    def test_driver_sans_bibliotheque_moteur(self):
        texte = CHEMIN_CLI.read_text(encoding="utf-8")
        for interdit in ("import transcribe_cpp", "import faster_whisper", "import transformers", "import llama_cpp"):
            self.assertNotIn(interdit, texte)


class FamilleCliVerifierTests(unittest.TestCase):
    def test_famille_cli_couvre_les_rapports_du_driver(self):
        for nom in ("cli-lecture", "cli-modele-installation", "cli-modele-telechargement",
                    "cli-modele-execution"):
            self.assertEqual(ci.champs_verification(nom), ci.CHAMPS_VERIFICATION["cli"])
        with self.assertRaisesRegex(RuntimeError, "liste blanche"):
            ci.champs_verification("clix-1")

    def test_rapport_cli_refuse_un_champ_hors_liste(self):
        with self.assertRaisesRegex(RuntimeError, "non autorisé"):
            ci.verifier_rapport("cli-lecture", {"phase": "lecture", "stdout": "x"})

    def test_champs_cli_sans_donnee_sensible(self):
        sensibles = {"transcription", "texte", "audio", "chemin", "dossier", "utilisateur", "cache",
                     "motif", "cpu", "memoire", "stdout", "stderr"}
        self.assertFalse(ci.CHAMPS_VERIFICATION["cli"] & sensibles)


class WorkflowCliWindowsTests(unittest.TestCase):
    def setUp(self):
        chemin = CHEMIN.parents[2] / ".github" / "workflows" / "cli-windows.yml"
        self.texte = chemin.read_text(encoding="utf-8")

    def test_declenchement_manuel_seul(self):
        self.assertIn("on:\n  workflow_dispatch:", self.texte)
        for declencheur in ("push:", "pull_request", "schedule:"):
            self.assertNotIn(declencheur, self.texte)

    def test_entrees_booleennes_au_defaut_prudent(self):
        self.assertRegex(self.texte, r"lecture:\n\s+description:[^\n]*\n\s+type: boolean\n\s+default: true")
        self.assertRegex(self.texte, r"modele:\n\s+description:[^\n]*\n\s+type: boolean\n\s+default: false")

    def test_gate_public_sur_chaque_job(self):
        self.assertIn("if: inputs.lecture && github.event.repository.private == false", self.texte)
        self.assertIn("if: inputs.modele && github.event.repository.private == false", self.texte)

    def test_voix_avant_installation_puis_phases_ordonnees(self):
        ordre = [self.texte.index(marque) for marque in (
            "generer-parole.ps1", "modele-installation", "modele-telechargement", "modele-execution")]
        self.assertEqual(ordre, sorted(ordre))

    def test_artefacts_limites_aux_rapports_et_sans_cache(self):
        chemins = [ligne.strip() for ligne in self.texte.splitlines() if ligne.strip().startswith("path:")]
        self.assertEqual(len(chemins), 2)
        self.assertTrue(all(ligne == "path: data/ci/rapports/*.json" for ligne in chemins))
        self.assertNotIn("actions/cache", self.texte)
        self.assertNotIn("secrets.", self.texte)
        self.assertNotIn("consultation_05m", self.texte)


if __name__ == "__main__":
    unittest.main()
