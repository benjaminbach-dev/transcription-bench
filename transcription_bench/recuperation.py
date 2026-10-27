"""Récupération au démarrage des exécutions restées en cours (tâche 6.5).

La CLI appelle `recuperer_executions_anterieures` après le verrou d'instance et
avant la création de l'application : aucune route ne peut donc voir un état en
cours de récupération. Pour chaque `run.json` à l'état `running` :

1. **terminaison vérifiée du moteur survivant** : le processus enregistré n'est
   arrêté que si son identité concorde, c'est-à-dire si son heure de création
   lue par le système correspond à celle consignée (`heure_creation`, source
   `psutil`) ou, à défaut, à l'heure de lancement du serveur (`lance_a`). Un PID
   réutilisé par un autre programme, ou un processus qui ne peut pas être
   identifié, n'est **jamais** tué ; en cas de doute, le démarrage est refusé
   plutôt que de clôturer une exécution dont le moteur vivrait encore ;
2. **finalisation en `abandoned`** : le format et l'écriture atomique restent
   ceux de `transcription_bench.resultats` (`abandonner_execution`), sans second
   écrivain. Les résultats déjà écrits (`result.json`, `transcription.txt`,
   `run.log`) ne sont jamais réécrits et aucune inférence n'est reprise ;
3. **nettoyage des restes** de `data/cache/`, une fois qu'aucun moteur
   enregistré n'est vivant : ces dossiers de travail ne sont plus utilisés.

Une exécution déjà finale n'est jamais modifiée, et n'est donc jamais refusée
pour son schéma : la validation ne vaut que pour les exécutions `running`, qui
sont les seules interprétées. Un dossier de résultats sans `run.json` (création
du dossier interrompue avant l'écriture de l'état) est ignoré. Un `run.json`
`running` illisible, d'un schéma inconnu ou incohérent est refusé sans être
réécrit, avec un message explicite. Une erreur système inattendue pendant la
terminaison (autre qu'un refus explicite) devient elle aussi un refus de
démarrer, sans trace Python. L'ensemble est idempotent : une récupération
interrompue peut être rejouée.

Chaque exécution traitée laisse une ligne de journal sur la sortie d'erreur
(« PID n ignoré : identité différente », « moteur PID n terminé », « exécution X
close en abandonnée »), sans secret. Le refus, lui, remonte par le message de
`EtatAnterieurNonTraitable`, que la CLI affiche aussi sur la sortie d'erreur.

**Règle d'identification du processus** (documentée aussi en D11). Le serveur
consigne l'horodatage epoch brut attribué par le système au processus
(`heure_creation`, source `psutil`) et, toujours, l'heure de lancement de son
propre horloge (`lance_a`). La comparaison se fait avec une tolérance :

- source `psutil` et heure non nulle : la même horloge système des deux côtés,
  écart maximal accepté ``TOLERANCE_HEURE_CREATION_S`` (1 s), très au-delà de
  la résolution de psutil (1/100 s) ;
- sinon (source `serveur`, heure nulle ou absente) : repli sur `lance_a`, écart
  maximal accepté ``TOLERANCE_LANCE_A_S`` (5 s). Cette tolérance est plus large
  parce que `lance_a` est tronquée à la seconde et que l'horloge du serveur peut
  différer de celle du système : sur le serveur de développement, l'écart relevé
  est d'environ 0,9 s.

Hors de cette tolérance, le PID ne désigne pas le moteur enregistré : il est
laissé intact. Un processus inaccessible (`AccessDenied`), ou qui survit à
`terminate` puis `kill`, refuse le démarrage : le programme ne clôt pas une
exécution dont le moteur pourrait encore écrire.

**Relecture avant signal** : l'heure de création n'est pas relue à la main,
`psutil.Process` la mettant en cache dès son instanciation (ce serait comparer
psutil à lui-même). psutil 7.2.2 revérifie lui-même l'identité du processus
(PID et heure de démarrage monotone) juste avant d'envoyer un signal :
`is_running()` compare l'instance à un `psutil.Process(pid)` neuf et
`terminate()`/`kill()` refusent alors d'agir si le PID a été réutilisé.

**Limites assumées** (documentées en D11) : une dérive d'horloge d'au moins 1 s
peut faire prendre le moteur pour un autre programme — il est alors laissé
vivant, mais mourra à sa prochaine écriture, la tuyauterie du serveur étant
fermée ; un arrêt brutal entre le lancement du moteur et l'écriture du PID
laisse un moteur non enregistré, donc non récupérable ; la supervision des
descendants orphelins au cours d'une exécution vivante relève de la tâche 6.6.
"""

from __future__ import annotations

import json
import math
import os
import shutil
import sys
from collections.abc import Mapping
from datetime import datetime
from pathlib import Path
from typing import Any

import psutil

from transcription_bench import resultats
from transcription_bench.paths import NOM_DOSSIER_CACHE, NOM_DOSSIER_RESULTATS
from transcription_bench.resultats import (
    ETAT_EN_COURS,
    ETATS_FINAUX,
    NOM_FICHIER_EXECUTION,
    SCHEMA,
    SOURCE_HEURE_PSUTIL,
    STATUT_ERREUR,
    STATUT_NON_TRAITE,
    STATUT_OK,
)

#: Écart maximal accepté entre l'heure de création consignée (source `psutil`)
#: et celle du processus candidat, en secondes.
TOLERANCE_HEURE_CREATION_S = 1.0
#: Écart maximal accepté quand l'identification se rabat sur `lance_a`, l'heure
#: du serveur tronquée à la seconde, en secondes.
TOLERANCE_LANCE_A_S = 5.0
#: Délai d'attente de la terminaison du moteur, en secondes, par étape
#: (`terminate` puis `kill`). Aligné sur `execution_moteur.DELAI_ARRET_MOTEUR`,
#: sans import de ce module (qui chargerait numpy et les moteurs).
DELAI_TERMINAISON_S = 5.0
#: Préfixe des dossiers de travail d'exécution, tenu égal à
#: `execution_moteur.PREFIXE_DOSSIER_TRAVAIL` par un test, sans importer ce
#: module (qui chargerait numpy et les moteurs). Seuls ces dossiers sont purgés.
PREFIXE_DOSSIER_TRAVAIL = "execution-"

CLE_ETAT = "etat"


class EtatAnterieurNonTraitable(RuntimeError):
    """Refus de démarrer : un résultat antérieur exige une intervention."""


def recuperer_executions_anterieures(
    donnees: Path | str,
    *,
    delai_terminaison: float = DELAI_TERMINAISON_S,
) -> None:
    """Termine les moteurs survivants vérifiés, clôt en `abandoned`, purge le cache.

    Lève `EtatAnterieurNonTraitable` — après avoir laissé les fichiers lisibles
    et sans clore l'exécution concernée — si un `run.json` resté en cours est
    illisible, incohérent ou d'un schéma inconnu, si un processus ne peut pas
    être identifié, ou s'il survit à l'arrêt. Les exécutions déjà finales et les
    dossiers sans `run.json` ne sont pas modifiés. `delai_terminaison` n'est
    fourni que par les tests.
    """
    dossier_resultats = Path(donnees) / NOM_DOSSIER_RESULTATS
    if dossier_resultats.is_dir():
        for run_json in sorted(dossier_resultats.glob(f"*/{NOM_FICHIER_EXECUTION}")):
            contenu = _lire_execution(run_json)
            if contenu[CLE_ETAT] in ETATS_FINAUX:
                continue
            try:
                _terminer_moteur(
                    contenu["processus_moteur"],
                    run_json=run_json,
                    delai=delai_terminaison,
                )
            except EtatAnterieurNonTraitable:
                raise
            except (psutil.Error, OSError) as erreur:
                # Erreur système inattendue : refus lisible plutôt qu'une trace.
                raise EtatAnterieurNonTraitable(
                    f"démarrage refusé : identification ou terminaison du processus "
                    f"moteur impossible pour {run_json} ({_message(erreur)}). Aucun "
                    "fichier n'a été modifié et l'exécution n'est pas close. "
                    "Vérifiez les processus en cours, puis relancez la commande."
                ) from None
            _abandonner(run_json, contenu)
    # Aucun moteur enregistré n'est vivant à ce stade (sinon l'appel ci-dessus a
    # refusé le démarrage) : les dossiers de travail restants sont des restes.
    _purger_cache(Path(donnees))


def _abandonner(run_json: Path, contenu: Mapping[str, Any]) -> None:
    """Clôt une exécution `running` en `abandoned`, sans toucher à ses résultats."""
    try:
        resultats.abandonner_execution(run_json.parent, contenu)
    except (OSError, ValueError, KeyError, TypeError) as erreur:
        raise EtatAnterieurNonTraitable(
            f"démarrage refusé : clôture en état abandonné impossible : {run_json} "
            f"({_message(erreur)}). Le fichier reste dans son état précédent, "
            "lisible, et aucun résultat n'a été modifié. Vérifiez les droits "
            "d'écriture du dossier des résultats puis relancez la commande."
        ) from None
    _journaliser(f"exécution {run_json.parent.name} close en abandonnée")


# -- lecture et validation de `run.json` -------------------------------------


def _lire_execution(run_json: Path) -> Mapping[str, Any]:
    """Lit `run.json` ; refuse tout contenu non traitable sans le réécrire."""
    try:
        contenu = json.loads(run_json.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as erreur:
        raise EtatAnterieurNonTraitable(
            f"démarrage refusé : résultat antérieur illisible : {run_json} "
            f"({_message(erreur)}). Aucun fichier n'a été modifié."
        ) from None
    if not isinstance(contenu, dict):
        raise EtatAnterieurNonTraitable(
            f"démarrage refusé : résultat antérieur incohérent : {run_json} "
            "(objet JSON attendu). Aucun fichier n'a été modifié."
        )
    etat = contenu.get(CLE_ETAT)
    if not isinstance(etat, str) or not etat:
        raise EtatAnterieurNonTraitable(
            f"démarrage refusé : résultat antérieur incohérent : {run_json} "
            f"(clé {CLE_ETAT!r} absente ou invalide). Aucun fichier n'a été modifié."
        )
    if etat not in ETATS_FINAUX and etat != ETAT_EN_COURS:
        raise EtatAnterieurNonTraitable(
            f"démarrage refusé : résultat antérieur non traitable (état inconnu "
            f"{etat!r}) : {run_json}. Aucun fichier n'a été modifié. Traitez ce "
            "résultat manuellement avant de redémarrer."
        )
    if etat == ETAT_EN_COURS:
        _valider_execution_en_cours(contenu, run_json)
    return contenu


def _valider_execution_en_cours(
    contenu: Mapping[str, Any], run_json: Path
) -> None:
    """Vérifie ce que la clôture doit interpréter, avant toute action.

    Seuls les champs relus par la récupération sont contrôlés : le schéma, le
    processus consigné et les plans d'audios. Un `run.json` final n'est jamais
    interprété, donc jamais refusé pour ces raisons.
    """
    schema = contenu.get("schema")
    if type(schema) is not int or schema != SCHEMA:
        raise EtatAnterieurNonTraitable(
            f"démarrage refusé : résultat antérieur d'un schéma non pris en charge "
            f"({schema!r}, schéma {SCHEMA} attendu) : {run_json}. Aucun fichier "
            "n'a été modifié ; ce résultat ne doit pas être interprété."
        )
    processus = contenu.get("processus_moteur")
    if not isinstance(processus, Mapping):
        raise _incoherent(run_json, "clé 'processus_moteur' absente ou invalide")
    pid = processus.get("pid")
    if pid is not None and (type(pid) is not int or pid <= 0):
        raise _incoherent(run_json, f"PID consigné invalide ({pid!r})")
    heure = processus.get("heure_creation")
    if heure is not None and (
        isinstance(heure, bool)
        or not isinstance(heure, (int, float))
        or not math.isfinite(heure)
    ):
        raise _incoherent(run_json, f"heure de création consignée invalide ({heure!r})")
    source = processus.get("heure_creation_source")
    if source is not None and not isinstance(source, str):
        raise _incoherent(run_json, "source de l'heure de création invalide")
    lance_a = processus.get("lance_a")
    if lance_a is not None and not isinstance(lance_a, str):
        raise _incoherent(run_json, "heure de lancement consignée invalide")
    audios = contenu.get("audios")
    if not isinstance(audios, list):
        raise _incoherent(run_json, "clé 'audios' absente ou invalide")
    for plan in audios:
        if not isinstance(plan, Mapping):
            raise _incoherent(run_json, "plan d'audio invalide")
        dossier = plan.get("dossier")
        if not isinstance(dossier, str) or not dossier:
            raise _incoherent(run_json, "plan d'audio sans dossier")
        if plan.get("statut") not in (STATUT_OK, STATUT_ERREUR, STATUT_NON_TRAITE):
            raise _incoherent(run_json, "plan d'audio au statut inconnu")


def _incoherent(run_json: Path, detail: str) -> EtatAnterieurNonTraitable:
    """Refus pour un `run.json` en cours d'exécution mais incohérent."""
    return EtatAnterieurNonTraitable(
        f"démarrage refusé : résultat antérieur incohérent : {run_json} "
        f"({detail}). Aucun fichier n'a été modifié. Traitez ce résultat "
        "manuellement avant de redémarrer."
    )


# -- terminaison du moteur survivant -----------------------------------------


def _terminer_moteur(
    processus: Mapping[str, Any],
    *,
    run_json: Path,
    delai: float = DELAI_TERMINAISON_S,
) -> None:
    """Termine le moteur enregistré s'il vit encore **et** si son identité concorde.

    Ne lève pas quand le processus est déjà mort, est un zombie, ou quand son
    identité ne correspond pas : dans ce dernier cas il n'est jamais tué. Lève
    `EtatAnterieurNonTraitable` si le processus ne peut pas être identifié ou
    s'il survit à l'arrêt : la clôture serait alors mensongère.
    """
    pid = processus.get("pid")
    if not isinstance(pid, int) or isinstance(pid, bool) or pid <= 0:
        return  # Moteur jamais lancé, ou PID non consigné : rien à terminer.
    if pid == os.getpid():
        # Le processus enregistré ne peut pas être le serveur lui-même : un tel
        # PID vient d'un `run.json` trafiqué et n'est jamais tué.
        _journaliser(
            f"PID {pid} ignoré : identité différente ({run_json.parent.name})"
        )
        return
    try:
        candidat = psutil.Process(pid)
        etat = candidat.status()
    except (psutil.NoSuchProcess, psutil.ZombieProcess):
        return  # Moteur déjà mort (un zombie est déjà terminé).
    except psutil.AccessDenied as erreur:
        raise _non_verifiable(run_json, pid, erreur) from None
    if etat == psutil.STATUS_ZOMBIE:
        return
    if not _identite_verifiee(candidat, processus, run_json=run_json):
        # PID réutilisé par un autre programme : jamais tué.
        _journaliser(
            f"PID {pid} ignoré : identité différente ({run_json.parent.name})"
        )
        return
    _terminer_arborescence(candidat, run_json=run_json, delai=delai)
    _journaliser(f"moteur PID {pid} terminé ({run_json.parent.name})")


def _identite_verifiee(
    candidat: psutil.Process,
    processus: Mapping[str, Any],
    *,
    run_json: Path,
) -> bool:
    """Vrai si le processus candidat est bien le moteur consigné.

    Lève `EtatAnterieurNonTraitable` si l'heure de création du candidat est
    illisible ou si aucune référence consignée n'est exploitable : sans preuve,
    le programme ne tue pas et n'affirme pas que le moteur est mort.
    """
    try:
        creation = candidat.create_time()
    except (psutil.NoSuchProcess, psutil.ZombieProcess):
        return False
    except psutil.AccessDenied as erreur:
        raise _non_verifiable(run_json, candidat.pid, erreur) from None
    heure = processus.get("heure_creation")
    if (
        processus.get("heure_creation_source") == SOURCE_HEURE_PSUTIL
        and isinstance(heure, (int, float))
        and not isinstance(heure, bool)
    ):
        return abs(creation - heure) <= TOLERANCE_HEURE_CREATION_S
    reference = _epoch_lance_a(processus.get("lance_a"))
    if reference is None:
        raise EtatAnterieurNonTraitable(
            f"démarrage refusé : identité du processus moteur (PID {candidat.pid}) "
            f"non vérifiable pour {run_json} : ni heure de création système, ni "
            "heure de lancement exploitable. Aucun processus n'a été tué et aucun "
            "fichier n'a été modifié ; terminez ce processus manuellement avant de "
            "redémarrer."
        )
    return abs(creation - reference) <= TOLERANCE_LANCE_A_S


def _epoch_lance_a(lance_a: Any) -> float | None:
    """`lance_a` consignée convertie en epoch, ou `None` si elle est inexploitable."""
    if not isinstance(lance_a, str) or not lance_a:
        return None
    try:
        return datetime.fromisoformat(lance_a).timestamp()
    except (ValueError, OverflowError, OSError):
        return None


def _terminer_arborescence(
    candidat: psutil.Process, *, run_json: Path, delai: float
) -> None:
    """Termine le processus vérifié et sa descendance, puis vérifie leur sortie.

    Les descendants sont terminés avant leur parent ; `_signaler` ne tue que si
    psutil confirme, juste avant le signal, que le PID n'a pas été réutilisé. Un
    survivant après `kill`, ou une terminaison refusée par le système, refuse le
    démarrage.
    """
    cibles = _cibles(candidat)
    for processus in reversed(cibles):
        _signaler(processus, "terminate", run_json=run_json)
    restants = _attendre_sortie(cibles, delai)
    for processus in restants:
        _signaler(processus, "kill", run_json=run_json)
    survivants = _attendre_sortie(restants, delai)
    if survivants:
        pids = ", ".join(str(processus.pid) for processus in survivants)
        raise EtatAnterieurNonTraitable(
            f"démarrage refusé : le processus moteur survivant (PID {pids}) résiste "
            f"à l'arrêt demandé pour {run_json}. Aucun fichier n'a été modifié et "
            "l'exécution n'est pas close. Terminez ce processus manuellement, puis "
            "relancez la commande."
        )


def _cibles(candidat: psutil.Process) -> list[psutil.Process]:
    """Processus vérifié et descendance (petits-enfants compris)."""
    return [candidat, *_enfants(candidat)]


def _enfants(candidat: psutil.Process) -> list[psutil.Process]:
    """Descendance du processus (petits-enfants compris), ou liste vide."""
    try:
        return candidat.children(recursive=True)
    except (psutil.NoSuchProcess, psutil.ZombieProcess, psutil.AccessDenied):
        return []


def _signaler(
    processus: psutil.Process,
    methode: str,
    *,
    run_json: Path,
) -> None:
    """Envoie `terminate` ou `kill`, sans jamais viser un PID réutilisé.

    Aucune relecture maison de l'heure de création : `psutil.Process` la met en
    cache, la comparaison serait donc psutil avec lui-même. psutil 7.2.2
    revérifie l'identité juste avant d'envoyer le signal : `is_running()`
    compare l'instance à un `psutil.Process(pid)` neuf et le signal est refusé
    (`NoSuchProcess`) si le PID a été réutilisé entre-temps.
    """
    try:
        if not processus.is_running():
            return  # Déjà sorti ou PID réutilisé : jamais tué.
        getattr(processus, methode)()
    except (psutil.NoSuchProcess, psutil.ZombieProcess):
        return
    except psutil.AccessDenied as erreur:
        raise _non_verifiable(run_json, processus.pid, erreur) from None


def _attendre_sortie(
    cibles: list[psutil.Process], delai: float
) -> list[psutil.Process]:
    """Attend la sortie des processus pendant `delai` ; renvoie ceux qui vivent."""
    try:
        psutil.wait_procs(cibles, timeout=delai)
    except psutil.TimeoutExpired:  # toutes les versions de psutil ne l'évitent pas
        pass
    return [processus for processus in cibles if _est_vivant(processus)]


def _est_vivant(processus: psutil.Process) -> bool:
    """Vrai si le processus existe encore, hors PID réutilisé et hors zombie."""
    try:
        return processus.is_running() and processus.status() != psutil.STATUS_ZOMBIE
    except (psutil.NoSuchProcess, psutil.ZombieProcess):
        return False
    except psutil.AccessDenied:  # non vérifiable : traité comme vivant, donc refus
        return True


def _non_verifiable(
    run_json: Path, pid: Any, erreur: BaseException
) -> EtatAnterieurNonTraitable:
    """Refus quand un processus ne peut pas être identifié ou terminé."""
    return EtatAnterieurNonTraitable(
        f"démarrage refusé : processus moteur (PID {pid}) inaccessible "
        f"({_message(erreur)}) pour {run_json}. Aucun fichier n'a été modifié et "
        "l'exécution n'est pas close. Terminez ce processus manuellement, puis "
        "relancez la commande."
    )


# -- restes du dossier de travail --------------------------------------------


def _purger_cache(donnees: Path) -> None:
    """Supprime les restes de `data/cache`, après la mort des moteurs enregistrés.

    Seuls les dossiers de travail d'exécutions (préfixe `execution-`, D5) sont
    supprimés : ce sont les seules entrées que le programme crée là, et tout
    autre contenu déposé par l'utilisateur reste intact. Aucune suppression n'a
    lieu dans un `cache` qui serait un lien symbolique ou une jonction (le
    programme ne connaît pas la cible), ni sur une entrée qui serait elle-même
    un lien. Une suppression impossible est ignorée : elle ne coûte que de
    l'espace disque et ne doit pas bloquer le démarrage. Le dossier lui-même est
    laissé en place, il est recréé paresseusement.
    """
    cache = donnees / NOM_DOSSIER_CACHE
    if not cache.is_dir() or cache.is_symlink() or cache.is_junction():
        return
    for reste in sorted(cache.iterdir()):
        if not reste.name.startswith(PREFIXE_DOSSIER_TRAVAIL):
            continue
        if reste.is_symlink() or reste.is_junction():
            continue
        try:
            if reste.is_dir():
                shutil.rmtree(reste, ignore_errors=True)
            else:
                reste.unlink()
        except OSError:
            continue


# -- journal ----------------------------------------------------------------


def _journaliser(message: str) -> None:
    """Écrit une ligne de journal sur la sortie d'erreur, sans secret.

    Une ligne par exécution traitée : le nom du dossier de résultat (horodatage
    et court identifiant) et les PID, jamais un chemin absolu des données.
    """
    print(
        f"transcription-bench : récupération : {message}",
        file=sys.stderr,
        flush=True,
    )


def _message(erreur: BaseException) -> str:
    """Texte court d'une erreur, sans message vide."""
    texte = str(erreur).strip()
    return texte if texte else type(erreur).__name__
