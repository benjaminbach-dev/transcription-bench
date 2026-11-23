"""Vérification CI des commandes CLI sous Windows (route A, tâche 4.5).

Le driver exécute `python -m transcription_bench.cli` par phases : `lecture`
(sans réseau ni modèle), puis `modele-installation`, `modele-telechargement` et
`modele-execution` (un seul modèle d'essai : transcribe-cpp, GGUF Q5_K_M). Chaque
étape compare son code de sortie, sa sortie `--json` (UTF-8, objets `schema: 1`),
la présence d'un motif fixe dans sa sortie d'erreur et les états lus.

Le rapport publié, `data/ci/rapports/cli-<phase>.json`, ne contient que les champs
de la liste blanche `CHAMPS_VERIFICATION["cli"]` de `verifier.py` : aucun texte de
sortie, aucun chemin. Les sorties brutes restent sous `data/ci/cli/`, non publiées.

Ce driver ne prouve ni Ctrl+C, ni SIGINT ou SIGTERM, ni le code 3 sous Windows :
l'arrêt testé est une terminaison brutale de l'arbre de processus (psutil).
Spécification : docs/preparation-verification-windows-4-5.md, §2.3 à §2.6.
"""

from __future__ import annotations

import argparse
import http.client
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import urllib.request
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

RACINE = Path(__file__).resolve().parents[2]
DOSSIER_SCRIPTS = Path(__file__).resolve().parent
if str(DOSSIER_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(DOSSIER_SCRIPTS))

import psutil  # noqa: E402  (dépendance serveur verrouillée, comme verifier.py)
import verifier  # noqa: E402

PHASES = ("lecture", "modele-installation", "modele-telechargement", "modele-execution")
#: Une étape en écart arrête les phases qui touchent au modèle ; `lecture` va à son terme.
PHASES_BLOQUANTES = frozenset(PHASES[1:])
DONNEES_CLI = RACINE / "data"
SORTIES = verifier.DONNEES / "cli"
PAROLE_SOURCE = verifier.DONNEES / "audio" / "parole.wav"

ESSAI = verifier.CAS["transcribe-gguf"]
MOTEUR = ESSAI["moteur"]
DEPOT = ESSAI["depot"]
REVISION = ESSAI["revision"]
GGUF = ESSAI["gguf"]

CODES_CONTRAT = frozenset({0, 1, 2, 3})
CODE_REFUS = 2
STATUT_OK = "ok"
STATUT_OBSERVATION = "observation"
STATUT_ECART = "ecart"
STATUT_NON_CONCLUANT = "non_concluant"
MARQUEUR_TRACE = "Traceback"
ETAT_LISIBLE = re.compile(r"[a-z0-9_-]{1,32}")
ETAPE_CHAMPS = frozenset({"id", "arguments", "attendu", "code", "statut", "schema", "etat", "motif_present"})
CHAMPS_EXTRA = frozenset({"moteur", "revision", "versions", "taille_totale_octets", "parole",
                          "terminaison", "cpu_relu"})

NOM_AUDIO = "parole.wav"
THREADS = "4"
PORT_SERVEUR = 8765
ADRESSE_BOUCLE = "127.0.0.1"
DELAI_COMMANDE_S = 120
DELAI_LONG_S = 1800
DELAI_EXECUTION_S = 1200
DELAI_CHARGEMENT_S = 900
DELAI_SERVEUR_S = 120
DELAI_ARRET_S = 60
#: Fenêtre de récupération avant de compter les survivants : la terminaison Windows
#: est asynchrone, un processus demandé à l'arrêt peut encore être en extinction.
DELAI_EXTINCTION_S = 3
PAUSE_APRES_CHARGEMENT_S = 2.0

# Motifs fixes, relevés dans le code du programme (tests ou sorties réelles).
MOTIF_PORT = "ne s'applique qu'au serveur web"
MOTIF_MODELE_NON_PRET = "modèle non prêt ou inconnu"
MOTIF_SEPARATEUR_IDENTIFIANT = "séparateur"
MOTIF_CLE = "clé de modèle invalide"
MOTIF_TRI = "tri invalide"
MOTIF_HORS_LISTE = "hors de la liste du dossier d'entrée"
MOTIF_REGLAGE = "réglage non déclaré"
MOTIF_VERROU = "déjà ce dossier"
MOTIF_MODELE_CHARGE = "Modèle chargé"
RAISON_GGUF_NON_CHOISI = "fichier-gguf-non-choisi"
ETAT_MOTEUR_NON_INSTALLE = "non-installe"
ETAT_MOTEUR_PRET = "pret"
ETAT_OPERATION_TERMINEE = "terminee"
ETAT_EXECUTION_COMPLETEE = "completed"
ETAT_EXECUTION_ABANDONNEE = "abandoned"
ARGS_RUN_START = ("run", "start", "--model", "{REF}", "--audio", NOM_AUDIO, "--threads", THREADS, "--json")
ARGS_RUN_CHECK = ("run", "check", "--model", "{REF}", "--audio", NOM_AUDIO, "--threads", THREADS, "--json")
ARGS_MODELE_CHECK = ("models", "check", DEPOT, "--engine", MOTEUR, "--revision", REVISION)
ARGS_MODELE_TELECHARGEMENT = ("models", "download", DEPOT, "--engine", MOTEUR,
                              "--revision", REVISION, "--file", GGUF, "--json")


class EtapeEnEcart(Exception):
    """L'étape ne correspond pas à son attendu. Le message est une constante du driver."""


class EtapeNonConcluante(Exception):
    """L'étape ne conclut pas : elle n'est jamais un succès."""


def exiger(condition: bool, message: str) -> None:
    if not condition:
        raise EtapeEnEcart(message)


@dataclass(frozen=True)
class Sortie:
    code: int
    stdout: bytes
    stderr: bytes


@dataclass
class Contexte:
    """État d'une phase : valeurs captées (non publiées), étapes et rapport partiel."""

    phase: str
    valeurs: dict[str, Any] = field(default_factory=dict)
    etapes: list[dict[str, Any]] = field(default_factory=list)
    extra: dict[str, Any] = field(default_factory=dict)
    #: Diagnostics console seulement : messages constants, jamais publiés.
    diagnostics: list[str] = field(default_factory=list)

    def enregistrer(self, identifiant: str, arguments: str, attendu: int | None) -> dict[str, Any]:
        fiche = {"id": identifiant, "arguments": arguments, "attendu": attendu, "code": None,
                 "statut": None, "schema": None, "etat": None, "motif_present": None}
        self.etapes.append(fiche)
        return fiche


@dataclass(frozen=True)
class Etape:
    """Commande CLI et ses attendus (§2.4). `attendu=None` : observation non asserté."""

    id: str
    args: tuple[str, ...]
    attendu: int | None = 0
    json: bool = False
    sortie_refus: bool = False
    motifs: tuple[str, ...] = ()
    sans_encodage: bool = False
    aucune_ecriture: bool = False
    champ_etat: tuple[int | str, ...] | None = None
    etat_attendu: str | None = None
    verifie: Callable[[list[dict[str, Any]], Contexte], None] | None = None
    capture: Callable[[list[dict[str, Any]], Contexte], None] | None = None
    delai: int = DELAI_COMMANDE_S


# --- Processus ----------------------------------------------------------------


def commande_cli(arguments: list[str]) -> list[str]:
    """Interpréteur courant (venv du serveur) et module de la CLI, sans trampoline uv."""
    return [sys.executable, "-m", "transcription_bench.cli", *arguments]


def lancer_cli(arguments: list[str], *, delai: int, sans_encodage: bool) -> Sortie:
    """Exécute la CLI et capture les sorties en octets (décodées ensuite en UTF-8)."""
    environnement = dict(os.environ)
    if sans_encodage:
        environnement.pop("PYTHONIOENCODING", None)
    resultat = subprocess.run(commande_cli(arguments), cwd=RACINE, env=environnement,
                              capture_output=True, timeout=delai, check=False)
    return Sortie(resultat.returncode, resultat.stdout, resultat.stderr)


def arreter_arbre(proc: subprocess.Popen) -> dict[str, int]:
    """Termine le processus et ses descendants : terminaison brutale, pas un signal.

    Les descendants sont listés avant tout arrêt (sinon ils seraient réparentés).
    Un survivant est un processus de même PID et même date de création encore vivant
    après la fenêtre d'extinction bornée (`DELAI_EXTINCTION_S`) : la terminaison
    Windows étant asynchrone, un processus en cours d'extinction juste après la mort
    de la racine n'est pas un orphelin ; `delai_reap_ms` consigne le temps d'attente
    effectif, et un orphelin réel reste compté après la fenêtre.
    """
    processus: list[psutil.Process] = []
    if proc.poll() is None:
        try:
            racine = psutil.Process(proc.pid)
            processus = [racine, *racine.children(recursive=True)]
        except psutil.Error:
            processus = []
    identites: list[tuple[int, float]] = []
    for courant in processus:
        try:
            identites.append((courant.pid, courant.create_time()))
        except psutil.Error:
            continue
    for courant in reversed(processus):
        try:
            courant.kill()
        except psutil.Error:
            continue
    try:
        code = proc.wait(timeout=DELAI_ARRET_S)
    except subprocess.TimeoutExpired:
        raise EtapeEnEcart("processus non arrêté dans le délai") from None
    debut = time.monotonic()
    while True:
        survivants = sum(1 for pid, creation in identites if _survit(pid, creation))
        if survivants == 0 or time.monotonic() - debut >= DELAI_EXTINCTION_S:
            break
        time.sleep(0.05)
    return {
        "code_brut": code,
        "processus_arbre": len(identites),
        "survivants": survivants,
        "delai_reap_ms": round((time.monotonic() - debut) * 1000, 1),
    }


def _survit(pid: int, creation: float) -> bool:
    try:
        courant = psutil.Process(pid)
        return courant.create_time() == creation and courant.status() != psutil.STATUS_ZOMBIE
    except psutil.NoSuchProcess:
        return False
    except psutil.Error:
        return True  # état inconnu : compté comme survivant, donc en écart


def _lire_lignes(flux: Any, lignes: list[bytes], charge: threading.Event) -> None:
    marque = MOTIF_MODELE_CHARGE.encode("utf-8")
    for ligne in iter(flux.readline, b""):
        lignes.append(ligne)
        if marque in ligne:
            charge.set()


def instantane_donnees() -> tuple[str, ...]:
    """Noms des entrées de data/ hors data/ci : une lecture ne doit rien créer."""
    if not DONNEES_CLI.is_dir():
        return ()
    return tuple(sorted(entree.name for entree in DONNEES_CLI.iterdir() if entree.name != "ci"))


def ecrire_sorties(phase: str, identifiant: str, sortie: Sortie) -> None:
    dossier = SORTIES / phase
    dossier.mkdir(parents=True, exist_ok=True)
    (dossier / f"{identifiant}.stdout.txt").write_bytes(sortie.stdout)
    (dossier / f"{identifiant}.stderr.txt").write_bytes(sortie.stderr)


# --- Contrôle des sorties --------------------------------------------------------


def decoder(donnees: bytes) -> str:
    try:
        return donnees.decode("utf-8")
    except UnicodeDecodeError:
        raise EtapeEnEcart("sortie non UTF-8") from None


def analyser_json(etape: Etape, code: int, texte: str) -> list[dict[str, Any]]:
    """Lignes JSON d'une sortie `--json` : un objet par ligne, chacun avec `schema: 1`."""
    if not etape.json:
        return []
    if code == CODE_REFUS and not etape.sortie_refus:
        exiger(texte.strip() == "", "sortie standard non vide sur refus")
        return []
    lignes = [ligne for ligne in texte.splitlines() if ligne.strip()]
    if not lignes:
        exiger(code != 0 and not etape.sortie_refus, "sortie --json vide")
        return []
    objets: list[dict[str, Any]] = []
    for ligne in lignes:
        try:
            objet = json.loads(ligne)
        except ValueError:
            raise EtapeEnEcart("sortie --json invalide") from None
        exiger(isinstance(objet, dict) and type(objet.get("schema")) is int and objet["schema"] == 1,
               "sortie --json sans schéma 1")
        objets.append(objet)
    return objets


def lire_etat(objets: list[dict[str, Any]], chemin: tuple[int | str, ...]) -> str:
    exiger(bool(objets), "état absent : aucune sortie --json")
    valeur: Any = objets[-1]
    for cle in chemin:
        try:
            valeur = valeur[cle]
        except (KeyError, IndexError, TypeError):
            raise EtapeEnEcart("état absent de la sortie") from None
    exiger(isinstance(valeur, str) and ETAT_LISIBLE.fullmatch(valeur) is not None,
           "état non lisible")
    return valeur


def controler_sortie(etape: Etape, sortie: Sortie, fiche: dict[str, Any]) -> list[dict[str, Any]]:
    exiger(sortie.code in CODES_CONTRAT, "code de sortie hors contrat")
    texte_sortie = decoder(sortie.stdout)
    texte_erreur = decoder(sortie.stderr)
    exiger(MARQUEUR_TRACE not in texte_erreur, "trace dans la sortie d'erreur")
    if etape.attendu is not None:
        exiger(sortie.code == etape.attendu, "code de sortie inattendu")
    if etape.motifs:
        present = any(motif in texte_erreur for motif in etape.motifs)
        fiche["motif_present"] = present
        exiger(present, "motif attendu absent de la sortie d'erreur")
    objets = analyser_json(etape, sortie.code, texte_sortie)
    if objets:
        fiche["schema"] = True
    if etape.champ_etat is not None:
        etat = lire_etat(objets, etape.champ_etat)
        fiche["etat"] = etat
        if etape.etat_attendu is not None:
            exiger(etat == etape.etat_attendu, "état inattendu")
    return objets


# --- Exécution des étapes ---------------------------------------------------------


def _conclure(ctx: Contexte, fiche: dict[str, Any], corps: Callable[[], None], *, observation: bool) -> None:
    """Fixe le statut d'une étape ; un écart ou une absence de conclusion ne lève pas plus haut."""
    try:
        corps()
    except EtapeNonConcluante as erreur:
        fiche["statut"] = STATUT_NON_CONCLUANT
        ctx.diagnostics.append(f"{fiche['id']} : {erreur}")
    except EtapeEnEcart as erreur:
        fiche["statut"] = STATUT_ECART
        ctx.diagnostics.append(f"{fiche['id']} : {erreur}")
    except subprocess.TimeoutExpired:
        fiche["statut"] = STATUT_ECART
        ctx.diagnostics.append(f"{fiche['id']} : délai dépassé")
    except Exception as erreur:  # écart explicite ; seul le type d'erreur est journalisé
        fiche["statut"] = STATUT_ECART
        ctx.diagnostics.append(f"{fiche['id']} : erreur {type(erreur).__name__}")
    else:
        fiche["statut"] = STATUT_OBSERVATION if observation else STATUT_OK


def executer_commande(etape: Etape, ctx: Contexte) -> None:
    fiche = ctx.enregistrer(etape.id, " ".join(etape.args), etape.attendu)

    def corps() -> None:
        arguments = [gabarit.format(**ctx.valeurs) for gabarit in etape.args]
        avant = instantane_donnees() if etape.aucune_ecriture else None
        sortie = lancer_cli(arguments, delai=etape.delai, sans_encodage=etape.sans_encodage)
        fiche["code"] = sortie.code
        ecrire_sorties(ctx.phase, etape.id, sortie)
        objets = controler_sortie(etape, sortie, fiche)
        if avant is not None:
            exiger(instantane_donnees() == avant, "écriture détectée dans data/")
        if etape.verifie is not None:
            etape.verifie(objets, ctx)
        if etape.capture is not None:
            etape.capture(objets, ctx)

    _conclure(ctx, fiche, corps, observation=etape.attendu is None)


def etape_manuelle(ctx: Contexte, identifiant: str, arguments: str, attendu: int | None,
                   corps: Callable[[dict[str, Any]], None], *, observation: bool = False) -> dict[str, Any]:
    """Étape sans commande simple (serveur, interruption, copie) : même contrat de statut."""
    fiche = ctx.enregistrer(identifiant, arguments, attendu)
    _conclure(ctx, fiche, lambda: corps(fiche), observation=observation)
    return fiche


def attendre_serveur(proc: subprocess.Popen) -> None:
    """Attend HTTP 200 sur la boucle locale, sans proxy (loopback seulement)."""
    ouvreur = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    url = f"http://{ADRESSE_BOUCLE}:{PORT_SERVEUR}/"
    limite = time.monotonic() + DELAI_SERVEUR_S
    while time.monotonic() < limite:
        exiger(proc.poll() is None, "serveur arrêté avant d'écouter")
        try:
            with ouvreur.open(url, timeout=2) as reponse:
                if reponse.status == 200:
                    return
        except (OSError, http.client.HTTPException):
            pass
        time.sleep(0.5)
    raise EtapeEnEcart("serveur non joignable sur la boucle locale")


def terminer_serveur(proc: subprocess.Popen, fiche: dict[str, Any], ctx: Contexte) -> None:
    terminaison = arreter_arbre(proc)
    fiche["code"] = terminaison["code_brut"]
    ctx.extra["terminaison"] = terminaison
    exiger(terminaison["survivants"] == 0, "processus survivant après arrêt brutal")


def verrou_serveur(ctx: Contexte) -> None:
    """L15/L16 : serveur tenant le verrou, refus des autres commandes, puis arrêt brutal."""
    dossier = SORTIES / ctx.phase
    dossier.mkdir(parents=True, exist_ok=True)
    arguments = ["serve", "--port", str(PORT_SERVEUR)]
    with (dossier / "L15-serve.stdout.txt").open("wb") as sortie, \
            (dossier / "L15-serve.stderr.txt").open("wb") as erreur:
        proc = subprocess.Popen(commande_cli(arguments), cwd=RACINE, stdout=sortie, stderr=erreur)
        try:
            fiche = etape_manuelle(ctx, "L15", " ".join(arguments), None,
                                   lambda _: attendre_serveur(proc))
            if fiche["statut"] == STATUT_OK:
                executer_commande(Etape("L15a", ("data", "check"), attendu=CODE_REFUS,
                                        motifs=(MOTIF_VERROU,)), ctx)
                executer_commande(Etape("L15b", ("engines", "list"), attendu=CODE_REFUS,
                                        motifs=(MOTIF_VERROU,)), ctx)
        finally:
            etape_manuelle(ctx, "L16", "terminaison brutale de l'arbre du serveur", None,
                           lambda fiche_arret: terminer_serveur(proc, fiche_arret, ctx),
                           observation=True)
    executer_commande(Etape("L16a", ("data", "check"), attendu=0), ctx)
    executer_commande(Etape("L16b", ("engines", "list"), attendu=0), ctx)


def interruption_moteur(ctx: Contexte) -> None:
    """X08 : terminaison brutale pendant l'inférence, après « Modèle chargé » et 2 s."""
    arguments = [gabarit.format(**ctx.valeurs) for gabarit in ARGS_RUN_START]

    def corps(fiche: dict[str, Any]) -> None:
        dossier = SORTIES / ctx.phase
        dossier.mkdir(parents=True, exist_ok=True)
        lignes: list[bytes] = []
        charge = threading.Event()
        with (dossier / "X08.stderr.txt").open("wb") as erreur:
            proc = subprocess.Popen(commande_cli(arguments), cwd=RACINE,
                                    stdout=subprocess.PIPE, stderr=erreur)
            lecteur = threading.Thread(target=_lire_lignes, args=(proc.stdout, lignes, charge),
                                       daemon=True)
            lecteur.start()
            try:
                limite = time.monotonic() + DELAI_CHARGEMENT_S
                while not charge.is_set() and proc.poll() is None and time.monotonic() < limite:
                    charge.wait(0.2)
                exiger(charge.is_set(), "« Modèle chargé » non observé")
                time.sleep(PAUSE_APRES_CHARGEMENT_S)
                termine_seul = proc.poll() is not None
                terminaison = arreter_arbre(proc)
            finally:
                if proc.poll() is None:
                    arreter_arbre(proc)
        lecteur.join(timeout=DELAI_ARRET_S)
        if not lecteur.is_alive():
            # Un descendant qui retient le tube laisse le lecteur bloqué : on ne ferme pas sous lui.
            proc.stdout.close()
        (dossier / "X08.stdout.txt").write_bytes(b"".join(lignes))
        ctx.extra["terminaison"] = terminaison
        fiche["code"] = terminaison["code_brut"]
        exiger(terminaison["survivants"] == 0, "processus survivant après arrêt brutal")
        if termine_seul:
            raise EtapeNonConcluante("exécution terminée avant l'arrêt")

    etape_manuelle(ctx, "X08", " ".join(ARGS_RUN_START), None, corps, observation=True)


def copier_parole(ctx: Contexte) -> None:
    """M01 : vérifie la parole synthétique (métadonnées, empreinte) puis la copie dans data/audio."""

    def corps(_: dict[str, Any]) -> None:
        try:
            preuve = verifier.preuve_audio(PAROLE_SOURCE)
        except (OSError, ValueError, RuntimeError):
            raise EtapeEnEcart("parole synthétique absente ou invalide") from None
        destination = DONNEES_CLI / "audio"
        destination.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(PAROLE_SOURCE, destination / NOM_AUDIO)
        ctx.extra["parole"] = preuve

    etape_manuelle(ctx, "M01", "copie du WAV vérifié vers data/audio", None, corps)


# --- Vérifications et captures par étape -----------------------------------------------


def _entree_moteur(objets: list[dict[str, Any]]) -> dict[str, Any]:
    moteurs = objets[-1].get("engines")
    exiger(isinstance(moteurs, list), "liste des moteurs absente")
    for entree in moteurs:
        if isinstance(entree, dict) and entree.get("identifiant") == MOTEUR:
            return entree
    raise EtapeEnEcart("moteur d'essai absent de la liste")


def verifie_etat_moteur(attendu: str) -> Callable[[list[dict[str, Any]], Contexte], None]:
    def verifie(objets: list[dict[str, Any]], _: Contexte) -> None:
        exiger(_entree_moteur(objets).get("etat") == attendu, "état du moteur inattendu")
    return verifie


def verifie_moteur_pret(objets: list[dict[str, Any]], ctx: Contexte) -> None:
    entree = _entree_moteur(objets)
    exiger(entree.get("etat") == ETAT_MOTEUR_PRET, "moteur non prêt après installation")
    versions = entree.get("versions")
    exiger(isinstance(versions, list), "versions du moteur absentes")
    ctx.extra["versions"] = [{"module": v["module"], "version": v.get("version")} for v in versions]


def verifie_cpu(objets: list[dict[str, Any]], ctx: Contexte) -> None:
    """Backend relu dans `results show` : CPU confirmé, ou étape non concluante."""
    paires = objets[-1].get("reglages_effectifs")
    valeurs = [p.get("value") for p in paires or []
               if isinstance(p, dict) and "backend" in str(p.get("label", "")).casefold()]
    if not valeurs:
        raise EtapeNonConcluante("backend non relu dans les réglages effectifs")
    cpu = str(valeurs[0]).casefold() == "cpu"
    ctx.extra["cpu_relu"] = cpu
    exiger(cpu, "backend non CPU")


def capture_modele_essai(objets: list[dict[str, Any]], ctx: Contexte) -> None:
    modeles = objets[-1].get("models")
    exiger(isinstance(modeles, list), "liste des modèles absente")
    retenus = [m for m in modeles if m.get("moteur") == MOTEUR and m.get("commit") == REVISION]
    exiger(len(retenus) == 1, "modèle d'essai absent ou en double")
    ctx.valeurs["REF"] = retenus[0]["reference"]
    ctx.valeurs["CLE"] = retenus[0]["cle"]


def capture_grille(objets: list[dict[str, Any]], ctx: Contexte) -> None:
    grilles = [g for g in objets[-1].get("grids", []) if g.get("valid") is True]
    exiger(bool(grilles), "aucune grille valide")
    ctx.valeurs["GRILLE"] = grilles[0]["name"]


def capture_modele_factice(objets: list[dict[str, Any]], ctx: Contexte) -> None:
    factices = [m for m in objets[-1].get("models", []) if m.get("synthetique") is True]
    exiger(bool(factices), "modèle factice absent des options d'extraction")
    ctx.valeurs["REF_FACTICE"] = factices[0]["reference"]


def verifie_refus_gguf(objets: list[dict[str, Any]], _: Contexte) -> None:
    verification = objets[-1].get("verification") or {}
    exiger(verification.get("accepte") is False and verification.get("raison") == RAISON_GGUF_NON_CHOISI,
           "refus GGUF inattendu")


def verifie_depot_accepte(objets: list[dict[str, Any]], ctx: Contexte) -> None:
    verification = objets[-1].get("verification") or {}
    exiger(verification.get("accepte") is True and verification.get("commit") == REVISION,
           "dépôt non accepté à la révision figée")
    taille = verification.get("taille_totale")
    exiger(type(taille) is int and taille > 0, "taille annoncée absente")
    # Contrôle d'espace avant tout transfert (§2.7) : la taille annoncée doit tenir.
    exiger(taille <= shutil.disk_usage(RACINE).free, "espace libre inférieur à la taille annoncée")
    ctx.extra["taille_totale_octets"] = taille


def capture_reference(objets: list[dict[str, Any]], ctx: Contexte) -> None:
    reference = objets[-1].get("reference")
    exiger(isinstance(reference, str) and reference.startswith(f"{MOTEUR}/"),
           "référence locale absente")
    ctx.valeurs["REF"] = reference
    ctx.valeurs["CLE"] = reference.split("/", 1)[1]


def verifie_telechargement(objets: list[dict[str, Any]], _: Contexte) -> None:
    sortie = objets[-1]
    exiger(sortie.get("download_operation") == ETAT_OPERATION_TERMINEE
           and sortie.get("already_ready") is False, "téléchargement non terminé")


def verifie_deja_pret(objets: list[dict[str, Any]], ctx: Contexte) -> None:
    sortie = objets[-1]
    exiger(sortie.get("already_ready") is True and sortie.get("reference") == ctx.valeurs.get("REF"),
           "second téléchargement non reconnu comme déjà prêt")


def verifie_modele_unique(objets: list[dict[str, Any]], _: Contexte) -> None:
    modeles = objets[-1].get("models")
    exiger(isinstance(modeles, list) and len(modeles) == 1, "inventaire : un seul modèle attendu")
    exiger(modeles[0].get("commit") == REVISION and modeles[0].get("moteur") == MOTEUR,
           "modèle local non conforme à la révision figée")


def verifie_audio_unique(objets: list[dict[str, Any]], _: Contexte) -> None:
    noms = [audio.get("nom") for audio in objets[-1].get("audios", [])]
    exiger(noms == [NOM_AUDIO], "audios proposés différents de parole.wav")


def verifie_reference_presente(objets: list[dict[str, Any]], ctx: Contexte) -> None:
    exiger(ctx.valeurs["REF"] in json.dumps(objets[-1], ensure_ascii=False),
           "référence absente des options d'exécution")


def capture_nombre_resultats(objets: list[dict[str, Any]], ctx: Contexte) -> None:
    ctx.valeurs["NB_AVANT"] = len(objets[-1].get("executions", []))


def verifie_nombre_inchange(objets: list[dict[str, Any]], ctx: Contexte) -> None:
    exiger(len(objets[-1].get("executions", [])) == ctx.valeurs["NB_AVANT"],
           "nombre de résultats modifié par une vérification à blanc")


def verifie_execution_terminee(objets: list[dict[str, Any]], _: Contexte) -> None:
    sortie = objets[-1]
    execution = sortie.get("execution") or {}
    en_erreur = execution.get("audios_en_erreur")
    non_traites = execution.get("audios_non_traites")
    # Schéma réel de `run start --json` : ces compteurs sont des listes d'audios,
    # vides si aucun cas ; un champ absent ou non vide est un écart.
    exiger(sortie.get("operation") == ETAT_OPERATION_TERMINEE
           and isinstance(en_erreur, list) and not en_erreur
           and isinstance(non_traites, list) and not non_traites,
           "exécution non terminée sans erreur")


def capture_identifiant(objets: list[dict[str, Any]], ctx: Contexte) -> None:
    identifiant = objets[-1].get("identifiant_resultat")
    exiger(isinstance(identifiant, str) and identifiant != "", "identifiant de résultat absent")
    ctx.valeurs["ID"] = identifiant


def verifie_nouvelle_execution(objets: list[dict[str, Any]], ctx: Contexte) -> None:
    exiger(objets[-1].get("identifiant_resultat") != ctx.valeurs.get("ID"),
           "identifiant de résultat non renouvelé")
    verifie_execution_terminee(objets, ctx)


def verifie_interruption(objets: list[dict[str, Any]], ctx: Contexte) -> None:
    """X09 : récupération. Une exécution `completed` rend l'interruption non concluante."""
    dernier = objets[-1].get("executions", [{}])[0]
    if dernier.get("etat") == ETAT_EXECUTION_COMPLETEE:
        raise EtapeNonConcluante("dernière exécution terminée avant l'arrêt")
    exiger(dernier.get("etat") == ETAT_EXECUTION_ABANDONNEE, "dernière exécution non abandonnée")
    exiger(dernier.get("identifiant") != ctx.valeurs.get("ID"), "exécution interrompue absente")


def verifie_modele_supprime(objets: list[dict[str, Any]], ctx: Contexte) -> None:
    modeles = objets[-1].get("models", [])
    exiger(not any(m.get("cle") == ctx.valeurs.get("CLE") for m in modeles),
           "modèle encore présent après suppression")


# --- Phases -------------------------------------------------------------------------


def etapes_lecture() -> list[Etape | Callable[[Contexte], None]]:
    """Phase lecture : sans réseau, sans modèle, sans moteur (L01 à L16)."""
    return [
        Etape("L01", ("--help",), aucune_ecriture=True),
        Etape("L02a", ("serve", "--help"), aucune_ecriture=True),
        Etape("L02b", ("engines", "install", "--help"), aucune_ecriture=True),
        Etape("L02c", ("run", "start", "--help"), aucune_ecriture=True),
        Etape("L02d", ("models", "download", "--help"), aucune_ecriture=True),
        Etape("L03", ("--port", "9000", "data", "check"), attendu=CODE_REFUS, motifs=(MOTIF_PORT,)),
        Etape("L04", ("commande-inexistante",), attendu=CODE_REFUS),
        Etape("L05", ("data", "check", "--json"), json=True),
        Etape("L06a", ("audios", "list", "--json"), json=True),
        Etape("L06b", ("models", "list", "--json"), json=True),
        Etape("L06c", ("run", "options", "--json"), json=True),
        Etape("L06d", ("results", "list", "--json"), json=True),
        Etape("L06e", ("results", "history", "--json"), json=True),
        Etape("L06f", ("results", "explain"), attendu=0),
        Etape("L06g", ("extract", "options", "--json"), json=True, capture=capture_modele_factice),
        Etape("L06h", ("extract", "list", "--json"), json=True),
        Etape("L06i", ("grids", "list", "--json"), json=True, capture=capture_grille),
        Etape("L07", ("engines", "list", "--json"), json=True,
              verifie=verifie_etat_moteur(ETAT_MOTEUR_NON_INSTALLE)),
        Etape("L08", ("grids", "show", "{GRILLE}")),
        # Sans transcription source, `extract check` refuse : le cas vert relève d'une autre phase.
        Etape("L09", ("extract", "check", "--model", "{REF_FACTICE}", "--grid", "{GRILLE}",
                      "--source", "1:1"), attendu=CODE_REFUS),
        Etape("L10", ("extract", "check", "--model", f"llama-cpp/{'0' * 64}", "--grid", "{GRILLE}",
                      "--source", "1:1"), attendu=CODE_REFUS),
        # Le modèle est validé avant l'audio : seul ce motif est atteignable en lecture.
        Etape("L11", ("run", "check", "--model", f"{MOTEUR}/{'0' * 64}", "--audio", "..\\x.wav",
                      "--threads", THREADS), attendu=CODE_REFUS, motifs=(MOTIF_MODELE_NON_PRET,)),
        Etape("L12a", ("models", "delete", MOTEUR, "..\\x"), attendu=CODE_REFUS, motifs=(MOTIF_CLE,)),
        Etape("L12b", ("results", "show", "..\\x", "--json"), attendu=CODE_REFUS, json=True,
              motifs=(MOTIF_SEPARATEUR_IDENTIFIANT,)),
        Etape("L13", ("data", "check"), sans_encodage=True),
        Etape("L14", ("results", "list")),
        verrou_serveur,
    ]


def etapes_installation() -> list[Etape | Callable[[Contexte], None]]:
    return [
        copier_parole,
        Etape("M02", ("engines", "install", MOTEUR), delai=DELAI_LONG_S),
        Etape("M03a", ("engines", "list", "--json"), json=True, verifie=verifie_moteur_pret),
        Etape("M03b", ("engines", "log", MOTEUR, "--limit", "2000", "--json"), json=True),
    ]


def etapes_telechargement() -> list[Etape | Callable[[Contexte], None]]:
    return [
        Etape("M04", (*ARGS_MODELE_CHECK, "--json"), attendu=CODE_REFUS, json=True,
              sortie_refus=True, verifie=verifie_refus_gguf),
        Etape("M05", (*ARGS_MODELE_CHECK, "--file", GGUF, "--json"), json=True,
              verifie=verifie_depot_accepte),
        Etape("M06", ARGS_MODELE_TELECHARGEMENT, json=True, delai=DELAI_LONG_S,
              verifie=verifie_telechargement, capture=capture_reference),
        Etape("M07", ARGS_MODELE_TELECHARGEMENT, json=True, delai=DELAI_LONG_S,
              verifie=verifie_deja_pret),
        Etape("M08", ("models", "list", "--json"), json=True, verifie=verifie_modele_unique),
    ]


def etapes_execution() -> list[Etape | Callable[[Contexte], None]]:
    return [
        Etape("X00", ("models", "list", "--json"), json=True, capture=capture_modele_essai),
        Etape("X01", ("audios", "list", "--json"), json=True, verifie=verifie_audio_unique),
        Etape("X02", ("run", "options", "--json"), json=True, verifie=verifie_reference_presente),
        Etape("X02b", ("results", "history", "--json"), json=True, capture=capture_nombre_resultats),
        Etape("X03", ARGS_RUN_CHECK, json=True),
        Etape("X03b", ("results", "history", "--json"), json=True, verifie=verifie_nombre_inchange),
        Etape("X04", ARGS_RUN_START, json=True, delai=DELAI_EXECUTION_S,
              champ_etat=("execution", "etat"), etat_attendu=ETAT_OPERATION_TERMINEE,
              verifie=verifie_execution_terminee, capture=capture_identifiant),
        Etape("X05a", ("results", "list", "--json"), json=True),
        Etape("X05b", ("results", "show", "{ID}", "--json"), json=True,
              champ_etat=("execution", "etat"), etat_attendu=ETAT_EXECUTION_COMPLETEE,
              verifie=verifie_cpu),
        Etape("X05c", ("results", "history", "--json"), json=True),
        Etape("X05d", ("results", "list", "--sort", "temps", "--json"), json=True),
        Etape("X06", ("results", "list", "--sort", "inconnu"), attendu=CODE_REFUS, motifs=(MOTIF_TRI,)),
        Etape("X07a", ("run", "start", "--model", "{REF}", "--audio", "absent.wav"),
              attendu=CODE_REFUS, motifs=(MOTIF_HORS_LISTE,)),
        Etape("X07b", ("run", "start", "--model", "{REF}", "--audio", "..\\parole.wav"),
              attendu=CODE_REFUS, motifs=(MOTIF_HORS_LISTE,)),
        Etape("X07c", ("run", "check", "--model", "{REF}", "--audio", NOM_AUDIO, "--threads", THREADS,
                       "--setting", "INCONNU=1"), attendu=CODE_REFUS, motifs=(MOTIF_REGLAGE,)),
        interruption_moteur,
        Etape("X09a", ARGS_RUN_CHECK, json=True),
        Etape("X09b", ("results", "history", "--json"), json=True,
              champ_etat=("executions", 0, "etat"), verifie=verifie_interruption),
        Etape("X10", ARGS_RUN_START, json=True, delai=DELAI_EXECUTION_S, verifie=verifie_nouvelle_execution),
        # Observation : la casse n'est pas documentée ; la liste exacte refuse « PARole.wav ».
        Etape("X11", ("run", "check", "--model", "{REF}", "--audio", "PARole.wav", "--threads", THREADS),
              attendu=None),
        Etape("X12a", ("models", "delete", MOTEUR, "..\\x"), attendu=CODE_REFUS, motifs=(MOTIF_CLE,)),
        Etape("X12b", ("models", "delete", MOTEUR, "{CLE}")),
        Etape("X12c", ("results", "show", "{ID}", "--json"), json=True),
        Etape("X12d", ("models", "list", "--json"), json=True, verifie=verifie_modele_supprime),
    ]


CONSTRUCTEURS: dict[str, Callable[[], list[Etape | Callable[[Contexte], None]]]] = {
    "lecture": etapes_lecture,
    "modele-installation": etapes_installation,
    "modele-telechargement": etapes_telechargement,
    "modele-execution": etapes_execution,
}


def executer_phase(phase: str) -> Contexte:
    ctx = Contexte(phase=phase)
    if phase != "lecture":
        ctx.extra.update({"moteur": MOTEUR, "revision": REVISION})
    SORTIES.joinpath(phase).mkdir(parents=True, exist_ok=True)
    for element in CONSTRUCTEURS[phase]():
        try:
            if isinstance(element, Etape):
                executer_commande(element, ctx)
            else:
                element(ctx)
        except Exception as erreur:  # aucune exception ne sort sans rapport
            fiche = ctx.enregistrer("ERREUR", "", None)
            fiche["statut"] = STATUT_ECART
            ctx.diagnostics.append(f"driver : erreur {type(erreur).__name__}")
        if phase in PHASES_BLOQUANTES and any(
                f["statut"] in (STATUT_ECART, STATUT_NON_CONCLUANT) for f in ctx.etapes):
            ctx.diagnostics.append("phase arrêtée à la première étape en écart")
            break
    return ctx


def conclusion(etapes: list[dict[str, Any]]) -> str:
    statuts = {fiche["statut"] for fiche in etapes}
    if not etapes or STATUT_ECART in statuts:
        return STATUT_ECART
    if STATUT_NON_CONCLUANT in statuts:
        return STATUT_NON_CONCLUANT
    return STATUT_OK


def construire_rapport(ctx: Contexte) -> dict[str, Any]:
    """Rapport limité à la liste blanche : aucune sortie brute, aucun chemin, aucun motif libre."""
    etapes = [{cle: fiche[cle] for cle in ETAPE_CHAMPS} for fiche in ctx.etapes]
    compte = Counter(fiche["statut"] for fiche in etapes)
    rapport: dict[str, Any] = {
        "phase": ctx.phase,
        "conclusion": conclusion(etapes),
        "resume": {"etapes": len(etapes), "ok": compte[STATUT_OK],
                   "observations": compte[STATUT_OBSERVATION], "ecarts": compte[STATUT_ECART],
                   "non_concluantes": compte[STATUT_NON_CONCLUANT]},
        "etapes": etapes,
    }
    for cle in CHAMPS_EXTRA & set(ctx.extra):
        rapport[cle] = ctx.extra[cle]
    return rapport


def main(argv: list[str] | None = None) -> int:
    for flux in (sys.stdout, sys.stderr):
        if hasattr(flux, "reconfigure"):
            flux.reconfigure(encoding="utf-8", errors="backslashreplace")
    analyseur = argparse.ArgumentParser(description="Vérification CI des commandes CLI (Windows).")
    analyseur.add_argument("phase", choices=PHASES)
    arguments = analyseur.parse_args(argv)
    try:
        verifier.exiger_ci_publique()
    except RuntimeError as erreur:
        print(f"cli_windows : {erreur}", file=sys.stderr)
        return 1
    ctx = executer_phase(arguments.phase)
    rapport = construire_rapport(ctx)
    verifier.rapport(f"cli-{arguments.phase}", rapport)
    for fiche in ctx.etapes:
        print(f"{fiche['id']} {fiche['statut']} code={fiche['code']}")
    for message in ctx.diagnostics:
        print(f"diagnostic : {message}", file=sys.stderr)
    return 0 if rapport["conclusion"] == STATUT_OK else 1


if __name__ == "__main__":
    raise SystemExit(main())
