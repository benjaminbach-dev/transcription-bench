"""Stockage des résultats d'une exécution : format, mesures serveur, écriture atomique.

Ce module couvre la tâche 6.4 et le format de stockage du design D11. Il ne
lance aucun processus et n'interprète aucun événement : le service d'exécution
(`transcription_bench.execution_moteur`) lui remet, au fil de l'exécution, les
valeurs déjà validées (demande, résultat d'un audio, mesures serveur).

Arborescence écrite, sans base de données et hors Git (sous `data/`) :

    data/results/<AAAAMMJJ-HHMMSS>-<court-id>/
      run.json        suivi de l'exécution (mutable pendant, immuable ensuite)
      run.log         sortie d'erreur complète du moteur, non bornée
      <n>-<nom-audio>/
        transcription.txt   texte transcrit (absent si l'audio n'a pas de texte)
        result.json         audio, segments, mesures, erreur éventuelle

**Sans écrasement** : chaque exécution reçoit un dossier neuf, créé exclusivement
sous le verrou commun de stockage ; un identifiant déjà pris est retiré au sort
plutôt que réutilisé. Les dossiers d'audios sont préfixés par leur ordre dans
l'exécution (`1-…`, `2-…`), ce qui les rend uniques même si deux noms se
réduisent au même nom sûr.

**Atomicité** : chaque JSON passe par `ecrire_json_atomique` (fichier temporaire
du même dossier, `fsync`, puis `os.replace`) sous le verrou commun de
`transcription_bench.stockage` ; un texte transcrit suit le même chemin. Une
interruption ne laisse donc jamais de JSON tronqué. Une erreur d'écriture
(disque plein, droits, remplacement refusé) n'est jamais avalée : elle est
retenue dans `ConsignateurExecution.erreur`, l'exécution est alors close en
échec et le fichier précédent reste lisible. L'état final est malgré tout
**toujours tenté** (`failed`, avec le motif retenu) pour ne pas laisser une
exécution `running` derrière elle ; si cette ultime écriture échoue aussi,
`run.json` reste dans son état précédent et la clôture de 6.5 le reprendra.

**Mesures** : `None` signifie « mesure indisponible » et n'est jamais remplacé
par zéro. Les mesures serveur (durée de l'opération, durée du processus moteur,
temps de décodage) sont réelles, y compris pour le moteur factice ; les mesures
d'un audio provenant du moteur sont recopiées telles quelles et restent marquées
`factice` / `mesures_simulees` lorsque le moteur les a simulées.

**Format** : `schema` vaut `SCHEMA` dans `run.json` et dans chaque
`result.json` ; les clés sont toujours présentes, avec `null` pour une valeur
indisponible. La clôture des exécutions restées `running` (état `abandoned`) est
faite par `abandonner_execution`, appelée par la récupération du démarrage
(tâche 6.5), qui lui remet le `run.json` déjà lu et validé : le format n'a ainsi
qu'un seul écrivain. Les pages de résultats relèvent des tâches 7.x.

**Secrets** : rien de l'environnement du serveur n'est recopié : ni jeton, ni
variable d'environnement. Les chemins persistés comme données (identifiant,
dossier d'audio) sont relatifs au dossier de résultat ; seuls un message
d'erreur d'E/S et les lignes brutes du journal du moteur (`run.log`) peuvent
citer un chemin absolu du système, sans devenir une donnée de configuration.
"""

from __future__ import annotations

import hashlib
import math
import platform
import re
import secrets
import threading
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import IO, TYPE_CHECKING, Any

import psutil

from engines.protocole import TYPE_CHARGEMENT, TYPE_FIN
from transcription_bench.operations import horodatage_iso
from transcription_bench.paths import (
    RACINE_PROJET,
    ValeurRefusee,
    resoudre_dans_racine,
    resoudre_resultat,
)
from transcription_bench.stockage import (
    VERROU_STOCKAGE,
    JsonInvalide,
    ecrire_json_atomique,
    ecrire_texte_atomique,
    lire_json,
)

if TYPE_CHECKING:  # pragma: no cover - uniquement pour les annotations
    from transcription_bench.execution_moteur import ResultatAudio, ResultatExecution
    from transcription_bench.executions import DemandeExecution

#: Version du format écrit dans `schema`, pour que 6.5 et 7.x sachent ce qu'ils
#: lisent. Toute évolution incompatible incrémente cette valeur.
SCHEMA = 1

NOM_FICHIER_EXECUTION = "run.json"
NOM_FICHIER_JOURNAL = "run.log"
NOM_FICHIER_RESULTAT = "result.json"
NOM_FICHIER_TRANSCRIPTION = "transcription.txt"

#: États persistés de `run.json`. `running` est mutable ; les quatre autres sont
#: finaux : le fichier n'est plus modifié ensuite.
ETAT_EN_COURS = "running"
ETAT_TERMINEE = "completed"
ETAT_INTERROMPUE = "interrupted"
ETAT_ECHOUEE = "failed"
#: Écrit uniquement par la clôture des exécutions abandonnées (tâche 6.5).
ETAT_ABANDONNEE = "abandoned"
ETATS_FINAUX = (ETAT_TERMINEE, ETAT_INTERROMPUE, ETAT_ECHOUEE, ETAT_ABANDONNEE)

#: États internes du service d'exécution (tâche 6.3) vers les états persistés :
#: la conversion vit ici pour que le format reste la seule référence écrite.
ETATS_EXECUTION_VERS_RESULTAT: dict[str, str] = {
    "terminee": ETAT_TERMINEE,
    "interrompue": ETAT_INTERROMPUE,
    "echouee": ETAT_ECHOUEE,
}

#: Statut d'un audio dans le suivi de l'exécution.
STATUT_OK = "ok"
STATUT_ERREUR = "erreur"
STATUT_NON_TRAITE = "non_traite"

#: Provenance de l'heure de création du processus moteur consignée.
SOURCE_HEURE_PSUTIL = "psutil"
SOURCE_HEURE_SERVEUR = "serveur"

#: Caractères interdits ou ambigus dans un nom de dossier sur Windows comme sur
#: Linux : séparateurs, lecteur, flux, jokers. Ils sont remplacés, jamais retirés,
#: pour qu'un nom hostile ne devienne pas un autre nom valide par accident.
CARACTERES_INTERDITS = '<>:"/\\|?*'
#: Longueur maximale de la partie « nom d'audio » d'un dossier (caractères). Le
#: préfixe d'ordre s'y ajoute : la composante reste courte et portable.
LONGUEUR_BASE_AUDIO_MAX = 80
NOMBRE_ESSAIS_IDENTIFIANT = 5

_MOTIF_BASE_IDENTIFIANT = re.compile(r"[0-9]{8}-[0-9]{6}", re.ASCII)
_MOTIF_COURT_ID = re.compile(r"[0-9a-f]{8}", re.ASCII)
#: Forme complète d'un identifiant de résultat (horodatage local et 8
#: hexadécimaux). Utilisée à la relecture par la consultation des résultats
#: (tâche 7.1) : un dossier dont le nom ne la respecte pas n'a pas été créé par
#: le programme et n'est pas interprété.
MOTIF_IDENTIFIANT = re.compile(r"[0-9]{8}-[0-9]{6}-[0-9a-f]{8}", re.ASCII)


class ConsignationImpossible(RuntimeError):
    """Création du dossier de résultat impossible (stockage indisponible).

    Levée seulement par `creer_dossier_resultat`, donc avant tout lancement de
    moteur. Les erreurs d'écriture ultérieures ne lèvent pas : elles sont
    retenues dans `ConsignateurExecution.erreur`, y compris lorsqu'elles
    surviennent dans le thread qui lit la sortie d'erreur du moteur.
    """


class ResultatImmuable(RuntimeError):
    """Tentative de modification d'une exécution déjà close (état final écrit)."""


@dataclass
class MesuresExecution:
    """Mesures serveur d'une exécution, remplies au fil de son déroulement.

    `debut` est l'instant `time.perf_counter()` du début de la préparation.
    `None` signifie « mesure indisponible », jamais zéro : une exécution
    interrompue avant le lancement du moteur n'a ni durée de processus ni pic
    mémoire, et une mesure jamais reçue reste absente.
    """

    debut: float
    duree_operation_s: float | None = None
    duree_processus_s: float | None = None
    duree_chargement_s: float | None = None
    pic_memoire_octets: int | None = None
    pic_memoire_partiel: bool | None = None


def etat_resultat(etat_execution: str) -> str:
    """État persisté correspondant à l'état interne d'une exécution close."""
    try:
        return ETATS_EXECUTION_VERS_RESULTAT[etat_execution]
    except KeyError:
        raise ValueError(
            f"état d'exécution inconnu : {etat_execution!r} "
            f"(attendu : {', '.join(sorted(ETATS_EXECUTION_VERS_RESULTAT))})"
        ) from None


def calculer_rtf(
    duree_transcription_s: Any, duree_decodee_s: Any
) -> float | None:
    """RTF = temps de transcription / durée **décodée**, ou `None`.

    La durée indicative de l'en-tête n'est jamais utilisée. Une durée décodée
    absente, non numérique ou nulle donne une mesure absente : aucun RTF n'est
    calculé, et aucun zéro n'est inventé.
    """
    if not _est_nombre(duree_transcription_s) or not _est_nombre(duree_decodee_s):
        return None
    if duree_decodee_s <= 0 or duree_transcription_s < 0:
        return None
    return duree_transcription_s / duree_decodee_s


def nom_dossier_audio(ordre: int, nom: str) -> str:
    """Nom de dossier sûr et unique pour l'audio `nom`, à l'ordre `ordre` (1-based).

    Le nom de l'audio est réduit à une seule composante portable : caractères
    interdits (séparateurs, `:`, jokers, guillemets) et caractères de contrôle
    remplacés par `_`, espaces et points finaux retirés (Windows les ignore), et
    longueur bornée. Le préfixe `"<ordre>-"` rend le dossier unique même si deux
    noms distincts se réduisent au même texte, et empêche qu'un nom de
    périphérique réservé Windows (`CON`, `NUL`, `COM1`…) désigne un périphérique.
    """
    if not isinstance(nom, str):
        raise ValeurRefusee("nom d'audio attendu sous forme de texte")
    return f"{_valider_ordre(ordre)}-{_base_sure(nom)}"


def creer_dossier_resultat(
    donnees: Path | str,
    *,
    base: str | None = None,
    court_id: str | None = None,
) -> tuple[str, Path]:
    """Crée un dossier de résultat neuf sous `data/results`, sans écrasement.

    L'identifiant suit `AAAAMMJJ-HHMMSS-<8 hexadécimaux>`. La création est
    exclusive (`mkdir` sans `exist_ok`) et se fait sous le verrou commun de
    stockage : un identifiant déjà pris, y compris par un dossier vide, est
    remplacé par un autre tirage. `base` et `court_id` ne sont fournis que par
    les tests. Le chemin renvoyé est résolu et vérifié comme restant sous
    `data/results` par `paths.resoudre_resultat`.
    """
    base_valide = _valider_base(base)
    for tentative in range(NOMBRE_ESSAIS_IDENTIFIANT):
        identifiant = f"{base_valide}-{_court_id(court_id if tentative == 0 else None)}"
        chemin = resoudre_resultat(identifiant, donnees)
        with VERROU_STOCKAGE:
            try:
                chemin.parent.mkdir(parents=True, exist_ok=True)
            except OSError as erreur:
                raise ConsignationImpossible(
                    f"dossier de résultat impossible à créer dans "
                    f"{chemin.parent.name}/ : {_message(erreur)}"
                ) from None
            try:
                chemin.mkdir(exist_ok=False)
            except FileExistsError:
                continue
            except OSError as erreur:
                raise ConsignationImpossible(
                    f"dossier de résultat impossible à créer : {_message(erreur)}"
                ) from None
        return identifiant, chemin
    raise ConsignationImpossible(
        "dossier de résultat impossible à créer : identifiant déjà pris "
        f"après {NOMBRE_ESSAIS_IDENTIFIANT} tentatives"
    )


def metadonnees_machine() -> dict[str, Any]:
    """Métadonnées de la machine, sans invention : `None` si non lisible."""
    try:
        coeurs_physiques = psutil.cpu_count(logical=False)
        coeurs_logiques = psutil.cpu_count(logical=True)
        ram_totale = psutil.virtual_memory().total
    except Exception:  # une mesure absente ne doit jamais empêcher une exécution
        coeurs_physiques = coeurs_logiques = ram_totale = None
    return {
        "os": platform.system() or None,
        "version_os": platform.release() or None,
        "architecture": platform.machine() or None,
        "processeur": platform.processor() or None,
        "coeurs_physiques": coeurs_physiques,
        "coeurs_logiques": coeurs_logiques,
        "ram_totale_octets": ram_totale,
    }


def metadonnees_programme(
    racine_projet: Path | str = RACINE_PROJET,
) -> dict[str, Any]:
    """Métadonnées du programme serveur et de sa pile de décodage.

    `empreinte_verrou` est celle du verrou de dépendances du **serveur**
    (`uv.lock`) ; celle du verrou du **moteur** figure dans les métadonnées du
    moteur. Le commit du programme n'est pas consigné : le programme n'embarque
    pas son commit, et aucune commande git n'est exécutée au lancement d'une
    exécution.
    """
    return {
        "nom": "transcription-bench",
        "version": _version_paquet(),
        "python": platform.python_version(),
        "empreinte_verrou": _empreinte_fichier(Path(racine_projet) / "uv.lock"),
        "pyav": _version_pyav(),
        "ffmpeg": _versions_ffmpeg(),
    }


def metadonnees_moteur(
    identifiant: str,
    nom: str,
    *,
    factice: bool,
    empreinte_verrou: str | None = None,
    versions: Mapping[str, str | None] | None = None,
) -> dict[str, Any]:
    """Métadonnées d'un moteur : identité, provenance, verrou et versions lues.

    `empreinte_verrou` est l'empreinte du verrou de dépendances du moteur,
    `None` s'il n'en a pas (moteur factice) ou s'il est illisible. `versions`
    reprend les versions réellement lues dans l'environnement du moteur lors de
    son installation ; elles ne sont ni déduites ni inventées.
    """
    return {
        "identifiant": identifiant,
        "nom": nom,
        "factice": bool(factice),
        "empreinte_verrou": empreinte_verrou,
        "versions": None if versions is None else dict(versions),
    }


class ConsignateurExecution:
    """Consignation propre à une exécution : `run.json`, `run.log`, audios.

    Construit sans E/S ; `ouvrir` crée le dossier, `run.json` en état `running`
    et `run.log` vide. `run.json` est ensuite réécrit à chaque progression
    (mesures du chargement, audio consigné, processus lancé) puis une dernière
    fois par `clore`, qui le rend immuable : toute modification ultérieure lève
    `ResultatImmuable`.

    Aucune méthode d'écriture ne lève pour une erreur d'E/S : la première erreur
    rencontrée est retenue dans `erreur` (avec son message), les écritures de
    résultats suivantes sont ignorées et l'appelant close l'exécution en échec.
    Le fichier précédent reste alors lisible, jamais tronqué. L'erreur propre au
    journal du moteur est retenue séparément dans `erreur_journal` : un
    `run.log` incomplet n'empêche pas d'écrire les résultats, qui ne dépendent
    pas de lui.
    """

    def __init__(
        self,
        dossier_data: Path | str,
        demande: DemandeExecution,
        moteur: Mapping[str, Any],
        *,
        debut: float,
        machine: Mapping[str, Any] | None = None,
        programme: Mapping[str, Any] | None = None,
        horloge: Any = horodatage_iso,
        base: str | None = None,
        court_id: str | None = None,
    ) -> None:
        self._donnees = Path(dossier_data)
        self._demande = demande
        self._moteur = dict(moteur)
        self._machine = dict(machine) if machine is not None else metadonnees_machine()
        self._programme = (
            dict(programme) if programme is not None else metadonnees_programme()
        )
        self._horloge = horloge
        self._base = base
        self._court_id = court_id
        self._verrou = threading.RLock()
        self._erreur: str | None = None
        self._erreur_journal: str | None = None
        self._etat_final: str | None = None
        self._identifiant: str | None = None
        self._dossier: Path | None = None
        self._date: str | None = None
        self._journal: IO[str] | None = None
        self._processus: dict[str, Any] = {
            "pid": None,
            "heure_creation": None,
            "heure_creation_source": None,
            "lance_a": None,
            "code_sortie": None,
        }
        self._audios: list[dict[str, Any]] = [
            {
                "ordre": position + 1,
                "nom": nom,
                "dossier": nom_dossier_audio(position + 1, nom),
                "statut": STATUT_NON_TRAITE,
                "erreur": None,
                "fenetre_s": None,
                "decoupage": None,
            }
            for position, nom in enumerate(demande.audios)
        ]
        self._progression: dict[str, Any] = {
            "audios_traites": 0,
            "audios_total": len(self._audios),
        }
        #: Valeurs effectives relues du moteur pour le dernier audio traité.
        self._effectifs: dict[str, Any] = {
            "threads_demandes": demande.threads,
            "threads_appliques": None,
            "reglages_effectifs": None,
        }
        self.mesures = MesuresExecution(debut=debut)

    # -- état observable -----------------------------------------------------

    @property
    def identifiant(self) -> str | None:
        """Identifiant du dossier de résultat, ou `None` avant `ouvrir`."""
        return self._identifiant

    @property
    def dossier(self) -> Path | None:
        """Dossier de résultat créé, ou `None`."""
        return self._dossier

    @property
    def erreur(self) -> str | None:
        """Première erreur d'écriture des résultats rencontrée, ou `None`."""
        with self._verrou:
            return self._erreur

    @property
    def erreur_journal(self) -> str | None:
        """Première erreur d'écriture du journal du moteur, ou `None`.

        Distincte de `erreur` : `run.log` n'est qu'une trace, son échec ne rend
        pas les résultats inutilisables et n'empêche pas de les écrire.
        """
        with self._verrou:
            return self._erreur_journal

    @property
    def etat_final(self) -> str | None:
        """État final écrit par `clore`, ou `None` tant que l'exécution dure."""
        with self._verrou:
            return self._etat_final

    # -- cycle de vie --------------------------------------------------------

    def ouvrir(self) -> bool:
        """Crée le dossier, `run.json` en état `running` et `run.log` vide.

        Renvoie `True` si la consignation est prête, `False` si le stockage est
        indisponible : dans ce cas `erreur` porte le motif et aucun fichier
        n'est laissé à moitié écrit.
        """
        try:
            self._identifiant, dossier = creer_dossier_resultat(
                self._donnees, base=self._base, court_id=self._court_id
            )
        except (ConsignationImpossible, ValeurRefusee) as erreur:
            self._definir_erreur(str(erreur))
            return False
        self._dossier = dossier
        self._date = self._horloge()
        try:
            self._journal = (dossier / NOM_FICHIER_JOURNAL).open(
                "w", encoding="utf-8", newline="\n"
            )
        except OSError as erreur:
            self._definir_erreur(
                f"journal du moteur impossible à créer : {_message(erreur)}"
            )
            return False
        return self._ecrire_execution(etat=ETAT_EN_COURS)

    def enregistrer_processus(
        self,
        *,
        pid: int,
        heure_creation: float | None,
        source: str,
        lance_a: str,
    ) -> bool:
        """Consigne le PID et l'heure de création du moteur dès son lancement.

        `heure_creation` est l'horodatage epoch brut que le système attribue au
        processus (source `psutil`), conservé sans troncature : c'est lui que la
        tâche 6.5 confrontera au PID enregistré, avec une tolérance. Il vaut
        `None` si le système n'a pas pu le lire ; la source vaut alors
        `serveur` et 6.5 se rabat sur `lance_a`, l'horloge du serveur au
        lancement. Les deux horloges peuvent différer de quelques dixièmes de
        seconde. Renvoie `False` si le PID n'a pas pu être persisté : sans lui,
        la récupération ne peut pas retrouver le processus.
        """
        self._refuser_si_clos()
        if self.erreur is not None or self._dossier is None:
            return False
        self._processus.update(
            {
                "pid": pid,
                "heure_creation": heure_creation,
                "heure_creation_source": source,
                "lance_a": lance_a,
            }
        )
        return self._ecrire_execution(etat=ETAT_EN_COURS)

    def enregistrer_mesures(self, evenement: Mapping[str, Any]) -> bool:
        """Retient les mesures transmises par un événement, sans attendre `clore`.

        La durée de chargement n'est retenue qu'une fois, depuis l'événement de
        chargement, et seulement si elle est finie ; le pic mémoire est le
        dernier entier non booléen transmis, comme dans `_pic_memoire` (valeur
        cumulative du processus moteur), et il est marqué partiel tant que
        l'exécution n'est pas terminée. Une mesure absente, non finie ou d'un
        type invalide ne remplace rien : aucune valeur n'est inventée.

        `run.json` n'est réécrit en état `running` que pour l'événement de
        chargement, afin qu'un arrêt brutal conserve ces mesures. Pour un
        événement d'audio, l'écriture est celle d'`enregistrer_audio`, appelée
        juste après, qui porte déjà les mesures à jour. `clore` recalcule les
        mesures finales à partir de tous les événements. Renvoie `False` si
        l'écriture du chargement échoue : l'erreur est retenue, jamais avalée,
        et l'appelant arrête le moteur et conclut en échec.
        """
        self._refuser_si_clos()
        type_evenement = evenement.get("type")
        if type_evenement == TYPE_CHARGEMENT and self.mesures.duree_chargement_s is None:
            duree = evenement.get("duree_s")
            if _est_nombre(duree):
                self.mesures.duree_chargement_s = duree
        pic = evenement.get("pic_memoire_octets")
        if isinstance(pic, int) and not isinstance(pic, bool):
            self.mesures.pic_memoire_octets = pic
            self.mesures.pic_memoire_partiel = True
        if type_evenement != TYPE_CHARGEMENT:
            return True
        if self.erreur is not None or self._dossier is None:
            return False
        return self._ecrire_execution(etat=ETAT_EN_COURS)

    def enregistrer_audio(self, audio: ResultatAudio) -> bool:
        """Écrit le résultat d'un audio, avant de passer au suivant.

        `transcription.txt` n'est écrit que si l'audio a un texte transcrit ;
        `result.json` porte toujours le statut, l'erreur éventuelle et les
        mesures disponibles. `run.json` est ensuite réécrit (état `running` et
        progression), sans jamais devenir final. Renvoie `True` en cas de succès.
        """
        self._refuser_si_clos()
        if self.erreur is not None or self._dossier is None:
            return False
        plan = self._plan_audio(audio.index)
        if plan is None:
            return False
        contenu = self._contenu_audio(audio, plan)
        dossier_audio = self._dossier_audio(plan)
        texte = _texte_evenement(audio)
        try:
            dossier_audio.mkdir(parents=True, exist_ok=True)
            if texte is not None:
                ecrire_texte_atomique(
                    dossier_audio / NOM_FICHIER_TRANSCRIPTION,
                    texte if texte.endswith("\n") else f"{texte}\n",
                )
            ecrire_json_atomique(dossier_audio / NOM_FICHIER_RESULTAT, contenu)
        except (OSError, ValeurRefusee) as erreur:
            self._definir_erreur(
                f"écriture du résultat de l'audio « {audio.nom} » impossible : "
                f"{_message(erreur)}"
            )
            return False
        if plan["statut"] == STATUT_NON_TRAITE:
            self._progression["audios_traites"] += 1
        plan.update(
            {
                "statut": contenu["statut"],
                "erreur": contenu["erreur"],
                "fenetre_s": (contenu["fenetre"] or {}).get("duree_s"),
                "decoupage": (contenu["fenetre"] or {}).get("decoupage"),
            }
        )
        self._maj_effectifs(contenu)
        return self._ecrire_execution(etat=ETAT_EN_COURS)

    def _maj_effectifs(self, contenu: Mapping[str, Any]) -> None:
        """Retient les threads appliqués et réglages effectifs relus du moteur.

        Un moteur qui ne permet pas de relire ces valeurs les laisse absentes :
        aucun nombre appliqué n'est affirmé et `None` n'est jamais remplacé par
        le nombre demandé. Les valeurs retenues sont celles du dernier audio
        traité.
        """
        threads = contenu["threads"]["appliques"]
        if isinstance(threads, int) and not isinstance(threads, bool):
            self._effectifs["threads_appliques"] = threads
        effectifs = contenu["reglages_effectifs"]
        if isinstance(effectifs, Mapping):
            self._effectifs["reglages_effectifs"] = dict(effectifs)

    def ecrire_journal(self, ligne: str) -> None:
        """Ajoute une ligne de la sortie d'erreur du moteur à `run.log`.

        Appelée depuis le fil de lecture du moteur : ne lève jamais. La première
        erreur d'écriture est retenue dans `erreur_journal`, distincte de
        `erreur` : le journal n'est qu'une trace, son échec n'empêche ni la
        consignation des résultats ni leur état final. Le journal n'est pas
        borné, contrairement au résumé gardé en mémoire par le service
        d'exécution.
        """
        with self._verrou:
            fichier = self._journal
            if fichier is None or self._etat_final is not None:
                return
            if self._erreur_journal is not None:
                return
            try:
                fichier.write(f"{ligne}\n")
                fichier.flush()
            except (OSError, ValueError) as erreur:
                self._erreur_journal = (
                    f"écriture du journal du moteur impossible : {_message(erreur)}"
                )

    def fermer(self) -> None:
        """Ferme `run.log` ; idempotent, ne lève pas."""
        with self._verrou:
            fichier, self._journal = self._journal, None
        if fichier is None:
            return
        try:
            fichier.close()
        except OSError:
            pass

    def clore(self, resultat: ResultatExecution) -> bool:
        """Écrit l'état final de `run.json` et rend le résultat immuable.

        L'état final est **toujours tenté**, même après une erreur d'écriture
        précédente : il vaut alors `failed`, avec le motif retenu dans `erreur`,
        pour ne pas laisser une exécution `running` derrière elle. Un statut
        d'audio déjà consigné (`ok` ou `erreur`) n'est jamais rétrogradé en
        `non_traite` : la consignation au fil de l'eau fait foi. Les mesures
        globales absentes restent absentes ; le pic mémoire est le dernier
        relevé transmis par le moteur, signalé comme partiel dès que l'exécution
        n'est pas terminée normalement ou que ce relevé ne vient pas de
        l'événement `fin`. Renvoie `True` si l'état final a bien été écrit ;
        `erreur` porte sinon le motif, et `run.json` reste dans son état
        précédent, lisible.
        """
        self._refuser_si_clos()
        etat = etat_resultat(resultat.etat)
        pic, pic_final = _pic_memoire(resultat.evenements)
        self.mesures.duree_chargement_s = _duree_chargement(resultat.evenements)
        self.mesures.pic_memoire_octets = pic
        self.mesures.pic_memoire_partiel = (
            None if pic is None else etat != ETAT_TERMINEE or not pic_final
        )
        self._processus["code_sortie"] = resultat.code_sortie
        if self._erreur is None:
            # Sans erreur d'écriture, les statuts manquants sont complétés depuis
            # le résultat en mémoire ; un statut déjà consigné fait foi.
            for audio in resultat.audios:
                plan = self._plan_audio(audio.index)
                if plan is None or plan["statut"] != STATUT_NON_TRAITE:
                    continue
                plan.update(
                    {
                        "statut": _statut_audio(audio),
                        "erreur": audio.erreur,
                    }
                )
        self._progression["audios_traites"] = sum(
            1 for plan in self._audios if plan["statut"] != STATUT_NON_TRAITE
        )
        if self._erreur is None:
            etat_final, erreur_finale = etat, resultat.erreur
        else:
            etat_final, erreur_finale = ETAT_ECHOUEE, self._erreur
        self._etat_final = etat_final
        return self._ecrire_execution(
            etat=etat_final, erreur=erreur_finale, fin=self._horloge(), forcer=True
        )

    # -- écriture ------------------------------------------------------------

    def _ecrire_execution(
        self,
        *,
        etat: str,
        erreur: str | None = None,
        fin: str | None = None,
        forcer: bool = False,
    ) -> bool:
        """Écrit `run.json` (atomique, sous le verrou de stockage).

        `forcer` n'est utilisé que pour l'état final : une erreur d'écriture
        précédente ne doit pas empêcher l'ultime tentative, qui porte alors le
        motif retenu.
        """
        dossier = self._dossier
        if dossier is None:
            return False
        if self.erreur is not None and not forcer:
            return False
        contenu = {
            "schema": SCHEMA,
            "identifiant": self._identifiant,
            "etat": etat,
            "cree_le": self._date,
            "fin": fin,
            "erreur": erreur,
            "factice": bool(self._moteur.get("factice")),
            "synthetique": bool(self._demande.synthetique),
            "mesures_simulees": bool(self._moteur.get("factice")),
            "demande": self._contenu_demande(),
            "moteur": dict(self._moteur),
            "machine": dict(self._machine),
            "programme": dict(self._programme),
            "processus_moteur": dict(self._processus),
            "mesures": {
                "duree_operation_s": self.mesures.duree_operation_s,
                "duree_processus_s": self.mesures.duree_processus_s,
                "duree_chargement_s": self.mesures.duree_chargement_s,
                "pic_memoire_octets": self.mesures.pic_memoire_octets,
                "pic_memoire_partiel": self.mesures.pic_memoire_partiel,
            },
            "effectifs": dict(self._effectifs),
            "progression": dict(self._progression),
            "audios": [dict(plan) for plan in self._audios],
        }
        try:
            ecrire_json_atomique(dossier / NOM_FICHIER_EXECUTION, contenu)
        except (OSError, ValueError) as erreur_ecriture:
            self._definir_erreur(
                f"écriture de l'état de l'exécution impossible : "
                f"{_message(erreur_ecriture)}"
            )
            return False
        return True

    def _contenu_demande(self) -> dict[str, Any]:
        demande = self._demande
        return {
            "moteur": demande.moteur,
            "famille": demande.famille,
            "modele": {
                "identifiant": demande.identifiant,
                "id_resolu": demande.id_resolu,
                "commit": demande.commit,
                "cle": demande.cle,
                "fichier_gguf": demande.fichier_gguf,
            },
            "audios": list(demande.audios),
            "threads_demandes": demande.threads,
            "reglages": {
                reglage.nom: reglage.valeur for reglage in demande.reglages
            },
            "fenetre_fixe_secondes": demande.fenetre_fixe_secondes,
        }

    def _contenu_audio(
        self, audio: ResultatAudio, plan: Mapping[str, Any]
    ) -> dict[str, Any]:
        prepare = audio.prepare
        evenement = audio.evenement
        return {
            "schema": SCHEMA,
            "execution": self._identifiant,
            "ordre": plan["ordre"],
            "nom": audio.nom,
            "dossier": plan["dossier"],
            "statut": _statut_audio(audio),
            "ecrit_le": self._horloge(),
            "factice": audio.factice,
            "synthetique": audio.synthetique,
            "mesures_simulees": audio.factice,
            "audio": {
                "nom": audio.nom,
                "format": None if prepare is None else prepare.format,
                "taille_octets": None if prepare is None else prepare.taille_octets,
                "empreinte_sha256": (
                    None if prepare is None else prepare.empreinte_sha256
                ),
                "duree_indicative_s": (
                    None if prepare is None else prepare.duree_indicative
                ),
                "duree_decodee_s": None if prepare is None else prepare.duree_decodee,
                "echantillons": None if prepare is None else prepare.echantillons,
            },
            "modele": {
                **self._contenu_demande()["modele"],
                "famille": self._demande.famille,
            },
            "moteur": dict(self._moteur),
            "machine": dict(self._machine),
            "programme": dict(self._programme),
            "reglages": {
                reglage.nom: reglage.valeur for reglage in self._demande.reglages
            },
            "reglages_effectifs": (
                None if evenement is None else _valeur(evenement, "reglages_effectifs")
            ),
            "langue_imposee": (
                None if evenement is None else _valeur(evenement, "langue_imposee")
            ),
            "threads": {
                "demandes": self._demande.threads,
                "appliques": (
                    None if evenement is None else _valeur(evenement, "threads_appliques")
                ),
            },
            "fenetre": (
                None
                if evenement is None
                else {
                    "duree_s": _valeur(evenement, "fenetre_s"),
                    "decoupage": _valeur(evenement, "decoupage"),
                    "nb_fenetres": _valeur(evenement, "nb_fenetres"),
                }
            ),
            "mesures": {
                "temps_decodage_s": None if prepare is None else prepare.temps_decodage,
                "duree_transcription_s": _mesure(evenement, "duree_transcription_s"),
                "temps_cpu_s": _mesure(evenement, "temps_cpu_s"),
                "rtf": calculer_rtf(
                    _mesure(evenement, "duree_transcription_s"),
                    None if prepare is None else prepare.duree_decodee,
                ),
                "pic_memoire_octets": _mesure(evenement, "pic_memoire_octets"),
            },
            "transcription": (
                None
                if evenement is None
                else {
                    "texte": _valeur(evenement, "texte"),
                    "segments": _valeur(evenement, "segments") or [],
                }
            ),
            "erreur": audio.erreur,
        }

    # -- helpers -------------------------------------------------------------

    def _plan_audio(self, index: int) -> dict[str, Any] | None:
        """Plan de consignation d'un audio, par sa position dans la demande."""
        if not isinstance(index, int) or isinstance(index, bool):
            return None
        if 0 <= index < len(self._audios):
            return self._audios[index]
        return None

    def _dossier_audio(self, plan: Mapping[str, Any]) -> Path:
        """Dossier d'un audio, confiné sous le dossier de résultat."""
        dossier = self._dossier
        if dossier is None:
            raise ValueError("consignation non ouverte")
        return resoudre_dans_racine(dossier, str(plan["dossier"]))

    def _definir_erreur(self, message: str) -> None:
        """Retient la première erreur d'écriture rencontrée."""
        with self._verrou:
            if self._erreur is None:
                self._erreur = message

    def _refuser_si_clos(self) -> None:
        """Refuse toute modification d'un résultat déjà finalisé."""
        if self._etat_final is not None:
            raise ResultatImmuable(
                f"résultat déjà finalisé ({self._etat_final}) : "
                f"{self._identifiant or 'identifiant inconnu'} n'est plus modifiable"
            )


def abandonner_execution(
    dossier: Path | str,
    contenu: Mapping[str, Any],
    *,
    fin: str | None = None,
    horloge: Any = horodatage_iso,
) -> dict[str, Any]:
    """Finalise en `abandoned` une exécution restée `running`, sans reprise.

    Appelée par la récupération du démarrage (tâche 6.5) avec le contenu de
    `run.json` déjà lu et validé : `etat` vaut `running`, le schéma est connu et
    les entrées d'`audios` sont exploitables. Le fichier est réécrit une seule
    fois, atomiquement, par le même écrivain que le reste du format ; la
    fonction renvoie le contenu écrit.

    Règles, conformes à D8 et D11 : `fin` est renseignée, `etat` vaut
    `abandoned`, les durées totale et du processus deviennent inconnues (le
    serveur est mort avant de les mesurer) alors que la durée de chargement
    déjà consignée est conservée ; le dernier pic mémoire transmis est conservé
    et marqué partiel ; `erreur`, `processus_moteur` et les autres clés gardent
    leur valeur, aucun fait n'étant inventé. Un statut d'audio déjà consigné
    (`ok` ou `erreur`) n'est jamais rétrogradé ; un audio sans `result.json`
    exploitable est marqué non traité, et un `result.json` présent mais non
    encore reflété dans `run.json` fait foi (la consignation écrit le résultat
    de l'audio avant de réécrire `run.json`). Ni `result.json`, ni
    `transcription.txt`, ni `run.log` ne sont touchés : la clôture ne produit
    aucune inférence et ne réécrit aucun résultat existant.

    Une erreur d'écriture remonte à l'appelant (`OSError`, `ValueError`) :
    `run.json` reste alors lisible dans son état précédent et le démarrage est
    refusé plutôt que de laisser une exécution en cours. Un contenu qui n'est
    plus `running` est refusé de la même façon : une exécution finale est
    immuable (D11).
    """
    if contenu.get("etat") != ETAT_EN_COURS:
        raise ValueError(
            f"clôture en abandonné refusée : état {contenu.get('etat')!r} au lieu de "
            f"{ETAT_EN_COURS!r}"
        )
    dossier_resultat = Path(dossier)
    final = _contenu_abandon(
        dossier_resultat,
        contenu,
        fin=horloge() if fin is None else fin,
    )
    ecrire_json_atomique(dossier_resultat / NOM_FICHIER_EXECUTION, final)
    return final


def _contenu_abandon(
    dossier_resultat: Path, contenu: Mapping[str, Any], *, fin: str
) -> dict[str, Any]:
    """Contenu de `run.json` finalisé en `abandoned`, à partir du contenu validé."""
    final = dict(contenu)
    final["etat"] = ETAT_ABANDONNEE
    final["fin"] = fin
    mesures = dict(_mapping(contenu.get("mesures")))
    # Le serveur est mort avant la clôture : ces deux durées n'ont jamais été
    # mesurées et ne doivent pas être déduites d'un horodatage de fichier.
    mesures["duree_operation_s"] = None
    mesures["duree_processus_s"] = None
    pic = mesures.get("pic_memoire_octets")
    mesures["pic_memoire_partiel"] = None if pic is None else True
    final["mesures"] = mesures
    audios = [_plan_abandon(dossier_resultat, plan) for plan in contenu.get("audios") or ()]
    final["audios"] = audios
    final["progression"] = {
        **_mapping(contenu.get("progression")),
        "audios_traites": sum(
            1 for plan in audios if plan["statut"] != STATUT_NON_TRAITE
        ),
        "audios_total": len(audios),
    }
    return final


def _plan_abandon(dossier_resultat: Path, plan: Mapping[str, Any]) -> dict[str, Any]:
    """Plan d'audio finalisé : statut consigné conservé, sinon relu du résultat."""
    final = dict(plan)
    if final.get("statut") in (STATUT_OK, STATUT_ERREUR):
        return final
    consigne = _statut_resultat_audio(dossier_resultat, final.get("dossier"))
    if consigne is None:
        final.update({"statut": STATUT_NON_TRAITE, "erreur": None})
        return final
    final.update(consigne)
    return final


def _statut_resultat_audio(
    dossier_resultat: Path, nom_dossier: Any
) -> dict[str, Any] | None:
    """Statut consigné dans le `result.json` d'un audio, ou `None` s'il manque.

    Un `result.json` absent, illisible ou incohérent n'est jamais réécrit : il
    est traité comme non exploitable et l'audio reste non traité.
    """
    if not isinstance(nom_dossier, str) or not nom_dossier:
        return None
    try:
        chemin = resoudre_dans_racine(dossier_resultat, nom_dossier)
        contenu = lire_json(chemin / NOM_FICHIER_RESULTAT)
    except (ValeurRefusee, JsonInvalide):
        return None
    if not isinstance(contenu, Mapping):
        return None
    statut = contenu.get("statut")
    if statut not in (STATUT_OK, STATUT_ERREUR):
        return None
    fenetre = contenu.get("fenetre")
    fenetre = fenetre if isinstance(fenetre, Mapping) else {}
    return {
        "statut": statut,
        "erreur": contenu.get("erreur"),
        "fenetre_s": fenetre.get("duree_s"),
        "decoupage": fenetre.get("decoupage"),
    }


def _mapping(valeur: Any) -> Mapping[str, Any]:
    """Valeur d'un sous-objet de `run.json`, vide si elle n'est pas un objet."""
    return valeur if isinstance(valeur, Mapping) else {}


def _statut_audio(audio: ResultatAudio) -> str:
    """Statut persisté d'un audio : transcrit, en erreur ou non traité."""
    if audio.evenement is not None:
        return STATUT_OK
    if audio.erreur is not None:
        return STATUT_ERREUR
    return STATUT_NON_TRAITE


def _texte_evenement(audio: ResultatAudio) -> str | None:
    """Texte transcrit de l'audio, ou `None` s'il n'y en a pas."""
    if audio.evenement is None:
        return None
    texte = audio.evenement.get("texte")
    return texte if isinstance(texte, str) else None


def _valeur(evenement: Mapping[str, Any], champ: str) -> Any:
    """Champ d'un événement, ou `None` (mesure absente, jamais zéro)."""
    return evenement.get(champ)


def _mesure(evenement: Mapping[str, Any] | None, champ: str) -> Any:
    """Mesure numérique finie d'un événement ; `None` si elle est absente."""
    if evenement is None:
        return None
    valeur = evenement.get(champ)
    return valeur if _est_nombre(valeur) else None


def _pic_memoire(
    evenements: Sequence[Mapping[str, Any]],
) -> tuple[int | None, bool]:
    """Dernier pic mémoire transmis, et s'il vient de l'événement `fin`.

    Le pic est cumulatif depuis le démarrage du processus moteur : le dernier
    relevé est donc le plus complet. Un pic qui ne vient pas de `fin` (exécution
    interrompue, échouée, ou moteur qui n'en transmet pas dans `fin`) ne peut pas
    être présenté comme le pic final ; le second élément le dit à l'appelant.
    """
    for evenement in reversed(evenements):
        valeur = evenement.get("pic_memoire_octets")
        if isinstance(valeur, int) and not isinstance(valeur, bool):
            return valeur, evenement.get("type") == TYPE_FIN
    return None, False


def _duree_chargement(evenements: Sequence[Mapping[str, Any]]) -> float | None:
    """Durée de chargement annoncée par le moteur, ou `None`."""
    for evenement in evenements:
        if evenement.get("type") != "chargement":
            continue
        valeur = evenement.get("duree_s")
        if _est_nombre(valeur):
            return valeur
    return None


def _est_nombre(valeur: Any) -> bool:
    """Vrai pour un nombre fini : NaN et les infinis ne sont pas des mesures."""
    if not isinstance(valeur, (int, float)) or isinstance(valeur, bool):
        return False
    try:
        return math.isfinite(valeur)
    except OverflowError:  # entier trop grand pour un flottant : mesure absurde
        return False


def _valider_ordre(ordre: int) -> int:
    if not isinstance(ordre, int) or isinstance(ordre, bool) or ordre < 1:
        raise ValeurRefusee(
            f"ordre d'audio invalide : {ordre!r} (entier supérieur ou égal à 1 attendu)"
        )
    return ordre


def _base_sure(nom: str) -> str:
    """Réduit un nom d'audio à une seule composante de nom de dossier portable."""
    caracteres = [
        "_"
        if caractere in CARACTERES_INTERDITS or ord(caractere) < 32 or ord(caractere) == 127
        else caractere
        for caractere in nom
    ]
    base = "".join(caracteres).strip(" .")
    base = base[:LONGUEUR_BASE_AUDIO_MAX].rstrip(" .")
    if not base or base in (".", ".."):
        return "audio"
    return base


def _valider_base(base: str | None) -> str:
    """Partie horodatée de l'identifiant : `AAAAMMJJ-HHMMSS`."""
    if base is None:
        return datetime.now().strftime("%Y%m%d-%H%M%S")
    if not isinstance(base, str) or not _MOTIF_BASE_IDENTIFIANT.fullmatch(base):
        raise ValeurRefusee(
            f"horodatage de résultat invalide : {base!r} "
            "(format AAAAMMJJ-HHMMSS attendu)"
        )
    return base


def _court_id(court_id: str | None) -> str:
    """Identifiant court du dossier : 8 caractères hexadécimaux."""
    if court_id is None:
        return secrets.token_hex(4)
    if not isinstance(court_id, str) or not _MOTIF_COURT_ID.fullmatch(court_id):
        raise ValeurRefusee(
            f"identifiant court invalide : {court_id!r} "
            "(8 caractères hexadécimaux attendus)"
        )
    return court_id


def _version_paquet() -> str | None:
    """Version installée du programme, ou `None` si elle n'est pas lisible."""
    try:
        from importlib import metadata
    except ImportError:
        return None
    try:
        return metadata.version("transcription-bench")
    except (metadata.PackageNotFoundError, ValueError):
        return None


def _version_pyav() -> str | None:
    """Version de PyAV du serveur, ou `None` (mesure absente)."""
    try:
        import av

        return str(av.__version__)
    except (ImportError, AttributeError):
        return None


def _versions_ffmpeg() -> dict[str, Any] | None:
    """Versions des bibliothèques FFmpeg embarquées dans PyAV, ou `None`."""
    try:
        import av

        bibliotheques = {
            nom: ".".join(str(partie) for partie in version)
            for nom, version in dict(av.library_versions).items()
        }
        version_globale = getattr(av, "ffmpeg_version_info", None)
    except (ImportError, AttributeError, TypeError, ValueError):
        return None
    return {
        "version": str(version_globale) if version_globale is not None else None,
        "bibliotheques": bibliotheques,
    }


def _empreinte_fichier(chemin: Path) -> str | None:
    """Empreinte SHA-256 d'un fichier de verrou, ou `None` s'il est illisible."""
    try:
        empreinte = hashlib.sha256()
        with Path(chemin).open("rb") as fichier:
            for bloc in iter(lambda: fichier.read(1024 * 1024), b""):
                empreinte.update(bloc)
        return empreinte.hexdigest()
    except OSError:
        return None


def _message(erreur: BaseException) -> str:
    """Texte court d'une erreur, sans message vide."""
    texte = str(erreur).strip()
    return texte if texte else type(erreur).__name__
