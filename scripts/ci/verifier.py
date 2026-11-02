"""Vérifications CI explicites, sans import moteur dans le serveur.

Installation et modèles : services du programme. Inférence : configuration,
décodage PyAV, supervision et runner du programme. Aucun accès réseau lors de
l'import de ce module ; les commandes réseau exigent le contexte CI public.
Les rapports publiables ne contiennent ni audio, ni texte transcrit, ni chemin
personnel. Ce harnais ne prouve pas une coupure réseau ou un Ctrl+C interactif.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

RACINE = Path(__file__).resolve().parents[2]
if str(RACINE) not in sys.path:
    sys.path.insert(0, str(RACINE))
DONNEES = RACINE / "data" / "ci"
RAPPORTS = DONNEES / "rapports"
CAS = {
    "faster-whisper": {
        "moteur": "faster-whisper", "famille": "whisper",
        "depot": "dropbox-dash/faster-whisper-large-v3-turbo", "licence": "MIT (carte)",
        "revision": "0a363e9161cbc7ed1431c9597a8ceaf0c4f78fcf",
    },
    "transcribe-gguf": {
        "moteur": "transcribe-cpp", "famille": "whisper",
        "depot": "handy-computer/whisper-large-v3-turbo-gguf", "licence": "MIT",
        "revision": "18ada752005f5fddef499256f9a458d0b37a203a",
        "gguf": "whisper-large-v3-turbo-Q5_K_M.gguf",
    },
    "transformers-whisper": {
        "moteur": "transformers", "famille": "whisper",
        "depot": "openai/whisper-large-v3-turbo", "licence": "MIT (carte)",
        "revision": "41f01f3fe87f28c78e2fbf8b568835947dd65ed9",
    },
    "transformers-parakeet": {
        "moteur": "transformers", "famille": "parakeet-tdt",
        "depot": "nvidia/parakeet-tdt-0.6b-v3", "licence": "CC-BY-4.0",
        "revision": "541d1f99c6b0c3cd0b11a95167540bb8edefd82b",
    },
}
MOTEURS = ("faster-whisper", "transcribe-cpp", "transformers")


def exiger_ci_publique() -> None:
    """Échouer, et non sauter silencieusement, hors du contexte adopté."""
    if (os.environ.get("GITHUB_ACTIONS") != "true"
            or os.environ.get("RUNNER_OS") != "Windows"
            or os.environ.get("TB_DEPOT_PUBLIC") != "true"):
        raise RuntimeError("Ces opérations exigent le runner CI Windows du dépôt public audité.")


def rapport(nom: str, contenu: dict) -> None:
    import psutil

    RAPPORTS.mkdir(parents=True, exist_ok=True)
    preuve = {
        "niveau": "CI Windows" if os.environ.get("RUNNER_OS") == "Windows" else "contrôle local",
        "date": datetime.now(timezone.utc).isoformat(),
        "commit": os.environ.get("GITHUB_SHA"),
        "run": os.environ.get("GITHUB_RUN_ID"),
        "tentative": os.environ.get("GITHUB_RUN_ATTEMPT"),
        "image": os.environ.get("ImageOS"),
        "version_image": os.environ.get("ImageVersion"),
        "python": platform.python_version(),
        "uv": subprocess.check_output(["uv", "--version"], text=True, encoding="utf-8").strip(),
        "os": platform.system(),
        "architecture": platform.machine(),
        "cpu_logiques": os.cpu_count(),
        "ram_octets": psutil.virtual_memory().total,
        "disque_libre_octets": shutil.disk_usage(RACINE).free,
        "verification": contenu,
    }
    (RAPPORTS / f"{nom}.json").write_text(
        json.dumps(preuve, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(preuve, ensure_ascii=False))


def services():
    from engines.registre import creer_registre_fourni
    from transcription_bench.moteurs import InstallationMoteurs
    from transcription_bench.operations import CreneauOperations
    from transcription_bench.paths import preparer_dossiers_data

    preparer_dossiers_data(DONNEES)
    registre = creer_registre_fourni()
    creneau = CreneauOperations()
    moteurs = InstallationMoteurs(DONNEES, registre, creneau)
    return registre, creneau, moteurs


def attendre(creneau, delai: float) -> None:
    from transcription_bench.operations import ETAT_TERMINEE

    if not creneau.attendre_thread(delai):
        raise RuntimeError("Délai de vérification dépassé.")
    etat = creneau.instantane()
    if etat.etat != ETAT_TERMINEE:
        # Ne pas imprimer le journal brut (il peut contenir des chemins).
        raise RuntimeError("Échec de l'opération ; diagnostic dans les journaux locaux non publiés.")


def installer(moteur: str) -> None:
    exiger_ci_publique()
    from transcription_bench.operations import TYPE_INSTALLATION

    registre, creneau, moteurs = services()
    try:
        creneau.demarrer(TYPE_INSTALLATION, lambda travailleur: moteurs.installer(moteur, travailleur))
        attendre(creneau, 1800)
        etat = next(e for e in moteurs.inventaire() if e.identifiant == moteur)
        if etat.etat != "pret":
            raise RuntimeError("Le service ne déclare pas le moteur prêt après installation.")
        # Exercer le runner factice dans le venv moteur, sans poids. L'import
        # différé de l'adaptateur réel est vérifié dans le même interpréteur.
        dossier = DONNEES / "smoke"
        dossier.mkdir(exist_ok=True)
        import numpy as np
        np.zeros(1600, dtype="<f4").tofile(dossier / "silence.f32")
        job = {"version": 1, "moteur": "factice", "famille": "factice",
               "modele": {"identifiant": "factice/ci", "revision": "factice", "chemin": "absent"},
               "threads_demandes": 1, "reglages": {}, "format_audio": "float32le-16000-mono",
               "audios": [{"nom": "silence", "chemin": "silence.f32"}]}
        chemin = dossier / "job.json"
        chemin.write_text(json.dumps(job), encoding="utf-8")
        code = (
            "import importlib,sys; sys.path.insert(0,sys.argv[1]); "
            "import engines.runner; importlib.import_module(sys.argv[2]); "
            "raise SystemExit(engines.runner.main([sys.argv[3]]))"
        )
        declaration = registre.obtenir(moteur)
        proc = subprocess.run(
            [str(moteurs.interpreteur(moteur)), "-I", "-c", code, str(RACINE),
             declaration.module_adaptateur, str(chemin)],
            env=environnement_hors_ligne(), capture_output=True, text=True, encoding="utf-8", timeout=120)
        if proc.returncode != 0:
            raise RuntimeError("Échec du runner factice ou de l'import de l'adaptateur dans le venv moteur.")
        from engines.protocole import analyser_ligne
        evenements = [analyser_ligne(ligne) for ligne in proc.stdout.splitlines()]
        if not any(e and e.get("type") == "fin" and e.get("audios_ok") == 1 for e in evenements):
            raise RuntimeError("Protocole du runner factice incomplet.")
        rapport(f"installation-{moteur}", {"moteur": moteur, "versions": dict(etat.versions),
                "runner_factice": True, "import_adaptateur": True})
    finally:
        moteurs.arreter()
        creneau.arreter()


def environnement_hors_ligne() -> dict[str, str]:
    from engines.hors_ligne import environnement_moteur

    env = environnement_moteur()
    env["NUMBA_CACHE_DIR"] = str(DONNEES / "numba")
    return env


def preparer(cas: str) -> None:
    exiger_ci_publique()
    from transcription_bench.gestion_modeles import GestionModeles, empreinte_verification

    choix = CAS[cas]
    registre, creneau, moteurs = services()
    modeles = GestionModeles(DONNEES, registre, creneau, moteurs)
    try:
        modeles.lancer_verification(choix["depot"], choix["moteur"],
                                    revision=choix["revision"], fichier_gguf=choix.get("gguf"))
        attendre(creneau, 300)
        resultat = modeles.dernier_resultat()
        if resultat is None or not resultat.accepte or resultat.commit != choix["revision"]:
            raise RuntimeError("Modèle refusé ou révision non conforme ; aucun contournement.")
        taille_connue = sum(f.taille or 0 for f in resultat.fichiers)
        if taille_connue > shutil.disk_usage(RACINE).free:
            raise RuntimeError("Espace libre inférieur à la taille connue du modèle ; téléchargement refusé.")
        if modeles.lancer_telechargement(empreinte_verification(resultat)):
            attendre(creneau, 1800)
        locaux = [m for m in modeles.inventaire() if m.commit == choix["revision"]]
        if len(locaux) != 1:
            raise RuntimeError("Inventaire du modèle incomplet.")
        rapport(f"modele-{cas}", {"cas": cas, "revision": choix["revision"],
                "depot": choix["depot"], "licence_declaree": choix["licence"],
                "source": f"https://huggingface.co/{choix['depot']}/tree/{choix['revision']}",
                "fichiers": [f.nom for f in locaux[0].fichiers]})
    finally:
        creneau.arreter()


def preuve_audio(chemin: Path, langue_imposee: str | None = None) -> dict:
    """Décrire le signal de test sans évaluer sa langue ou sa transcription."""
    import wave

    metadata = json.loads(chemin.with_suffix(".json").read_text(encoding="utf-8"))
    for champ in ("voix", "culture_voix", "texte_langue", "sha256"):
        if not isinstance(metadata.get(champ), str) or not metadata[champ].strip():
            raise RuntimeError(f"Métadonnée de parole absente ou invalide : {champ}.")
    empreinte = hashlib.sha256(chemin.read_bytes()).hexdigest()
    if metadata["sha256"].lower() != empreinte:
        raise RuntimeError("Les métadonnées de parole ne correspondent pas au WAV utilisé.")
    with wave.open(str(chemin), "rb") as wav:
        duree = wav.getnframes() / wav.getframerate()
    if duree <= 0:
        raise RuntimeError("Audio de parole de durée nulle.")
    return {"voix": metadata["voix"], "culture_voix": metadata["culture_voix"],
            "texte_langue": metadata["texte_langue"], "audio_sha256": empreinte,
            "duree_source_s": duree, "langue_imposee": langue_imposee}


def inferer(cas: str) -> None:
    exiger_ci_publique()
    from transcription_bench.execution_moteur import ExecutionMoteur
    from transcription_bench.executions import ConfigurationExecutions
    from transcription_bench.gestion_modeles import GestionModeles
    from transcription_bench.operations import ETAT_TERMINEE, TYPE_EXECUTION

    choix = CAS[cas]
    audio = DONNEES / "audio" / "parole.wav"
    parole = preuve_audio(audio)
    os.environ.update(environnement_hors_ligne())
    registre, creneau, moteurs = services()
    modeles = GestionModeles(DONNEES, registre, creneau, moteurs)
    configuration = ConfigurationExecutions(DONNEES, registre, modeles.inventaire)
    proposes = [m for m in configuration.modeles_proposables()
                if m.moteur == choix["moteur"] and m.commit == choix["revision"]]
    if len(proposes) != 1 or proposes[0].famille != choix["famille"]:
        raise RuntimeError("Modèle préparé introuvable, ambigu ou de famille inattendue.")
    demande = configuration.valider(modele=proposes[0].reference, audios=["parole.wav"],
                                     threads=min(os.cpu_count() or 1, 4), reglages={})
    execution = ExecutionMoteur(DONNEES, registre, moteurs)
    try:
        execution.reserver()
        try:
            creneau.demarrer(TYPE_EXECUTION, lambda travailleur: execution.lancer(demande, travailleur))
        except BaseException:
            execution.annuler_reservation()
            raise
        attendre(creneau, 1200)
        resultat = execution.derniere_execution()
        if resultat is None or resultat.etat != ETAT_TERMINEE or resultat.code_sortie != 0:
            raise RuntimeError("Exécution non terminée.")
        if resultat.factice or len(resultat.audios) != 1 or resultat.audios[0].erreur:
            raise RuntimeError("Résultat réel incomplet.")
        evenement = resultat.audios[0].evenement
        if evenement is None or evenement["duree_audio_s"] <= 0:
            raise RuntimeError("Résultat audio absent ou de durée nulle.")
        parole["langue_imposee"] = evenement.get("langue_imposee")
        if not evenement["texte"].strip():
            rapport(f"inference-{cas}", {"cas": cas, "etat": "controle_non_concluant",
                    "raison": "transcription_vide", "parole": parole,
                    "evaluation_qualite": False})
            raise RuntimeError("Contrôle de fonctionnement non concluant : transcription vide ; aucune conclusion sur la qualité du modèle.")
        effectifs = evenement["reglages_effectifs"]
        cpu_relu = effectifs.get("device_relu") or effectifs.get("backend_relu")
        if not isinstance(cpu_relu, str) or cpu_relu.lower() != "cpu":
            raise RuntimeError("Le périphérique CPU effectif n'est pas confirmé par l'adaptateur.")
        rapport(f"inference-{cas}", {
            "nature_controle": "fonctionnement du programme, sans évaluation du modèle",
            "parole": parole,
            "cas": cas, "revision": choix["revision"], "audio_synthetique": True,
            "audio_sha256": hashlib.sha256(audio.read_bytes()).hexdigest(),
            "duree_audio_s": evenement["duree_audio_s"],
            "texte_non_vide": True, "caracteres": len(evenement["texte"]),
            "threads_demandes": evenement["threads_demandes"],
            "threads_appliques": evenement["threads_appliques"],
            "cpu_relu": cpu_relu,
            "reglages_effectifs": effectifs,
            "timings_natifs": evenement.get("timings_natifs"),
            "mode_hors_ligne_configure": True, "isolation_reseau_prouvee": False,
        })
    finally:
        execution.arreter_execution(arret_serveur=True)
        creneau.arreter()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_subparsers(dest="action", required=True)
    actions.add_parser("ressources")
    actions.add_parser("installer").add_argument("moteur", choices=MOTEURS)
    for nom in ("preparer", "inferer"):
        actions.add_parser(nom).add_argument("cas", choices=tuple(CAS))
    args = parser.parse_args()
    if args.action == "ressources":
        rapport("ressources", {"but": "compatibilité, pas performance représentative"})
    elif args.action == "installer":
        installer(args.moteur)
    elif args.action == "preparer":
        preparer(args.cas)
    else:
        inferer(args.cas)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
