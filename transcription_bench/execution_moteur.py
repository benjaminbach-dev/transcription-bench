"""Lancement supervisé d'une exécution dans le créneau global (tâche 6.3).

Ce service consomme une `DemandeExecution` validée par la tâche 6.2 et exécute
une exécution complète, dans le thread de fond du créneau unique :

1. **Dossier de travail** de l'exécution, sous `data/cache/<id>`, créé
   paresseusement au lancement (jamais au démarrage du serveur) et supprimé à la
   fin : les signaux décodés ne vont jamais dans le répertoire temporaire du
   système ;
2. **décodage** de chaque audio par le décodeur commun de la tâche 6.1, puis
   écriture immédiate du signal brut `float32` little-endian 16 kHz mono
   (`<f4`) dans ce dossier. L'audio est écrit dès qu'il est décodé : aucun
   signal n'est conservé en mémoire pour être écrit plus tard, donc aucune
   double copie. Une erreur de décodage, y compris inattendue, devient une
   erreur propre à cet audio et les audios suivants sont décodés ;
3. **`job.json`** conforme au contrat du runner (`engines/runner.py`) : moteur,
   famille, modèle (identifiant, révision, chemin), nombre de threads demandés,
   réglages effectifs et chemins des signaux bruts, relatifs au dossier du job.
   Pour le modèle synthétique du moteur factice, le chemin est un emplacement
   fictif sous `data/models/` : il n'existe pas et le moteur factice ne le lit
   pas, mais le runner exige un chemin non vide ;
4. **lancement** du runner par `engines.hors_ligne.commande_runner` avec
   `environnement_moteur()` (mode hors ligne forcé) et dans son propre groupe de
   processus (`start_new_session` sous POSIX, `CREATE_NEW_PROCESS_GROUP` sous
   Windows), pour que Ctrl+C au terminal soit traité par la supervision du
   serveur et non par le moteur ;
5. **lecture** de la sortie standard : seules les lignes du protocole
   `engines.protocole` sont interprétées ; les autres sont comptées et
   journalisées sans provoquer d'échec. Un événement dont la provenance
   (`factice`) ne correspond pas à la déclaration du moteur est traité comme
   une ligne parasite : une mesure simulée ne doit jamais passer pour réelle.
   Les événements en double le sont aussi : un second événement d'audio pour un
   même index, un second `chargement` ou un second `fin` sont ignorés, le
   premier reçu restant le seul conservé et jamais rejoué ;
6. **arrêt** à la demande de l'utilisateur ou à l'arrêt normal du serveur :
   signal au **groupe** du processus (`SIGTERM`, attente bornée puis `SIGKILL`
   sous POSIX ; arborescence psutil sous Windows), la descendance étant relevée
   avant le signal puis attendue et tuée si elle y survit ; les résultats
   d'audios déjà
   reçus sont conservés et les audios restants sont signalés non traités. Après la demande d'arrêt, les lignes
   encore lues sont drainées sans être interprétées : la troncature est donc
   bornée au dernier événement reçu avant l'arrêt, de façon déterministe ;
7. **issue** : sortie non nulle, événement `fin` absent ou événement manquant
   pour un audio donnent un échec explicite (`ExecutionEchouee`), jamais un
   succès déduit d'un silence. Les audios sans résultat restent signalés non
   traités ;
8. **consignation** des résultats de l'exécution (tâche 6.4) sous
   `data/results/<AAAAMMJJ-HHMMSS>-<court-id>/` : `run.json` créé en état
   `running` puis réécrit à chaque progression, `run.log` recevant la sortie
   d'erreur **complète** du moteur (le résumé en mémoire reste borné), et un
   dossier `<n>-<nom-audio>/` par audio avec `transcription.txt` et
   `result.json`. Chaque résultat d'audio est écrit dès qu'il est connu, donc
   avant de passer au suivant ; aucun dossier existant n'est réutilisé ni
   écrasé ;
9. **mesures serveur** (D8) : durée totale de l'opération, du début de la
   préparation à la fin de la collecte du moteur et de l'écriture des résultats
   d'audios (décodage, chargement, inférence et écriture compris, hors ultime
   sauvegarde de `run.json`), et durée du processus moteur, du lancement à sa
   sortie. Le temps de décodage par audio vient du décodeur commun ; le RTF est
   calculé sur la durée décodée. Une mesure indisponible reste absente, jamais
   zéro ;
10. **nettoyage** du cache décodé (suppression du dossier de travail) dans tous
    les cas, y compris après échec ou arrêt, mais seulement une fois le processus
    moteur réellement terminé, et avant la clôture de la consignation : de la
    place est ainsi libérée pour l'écriture de l'état final.

Le processus est toujours attendu avant la fin du thread de fond : le créneau
reste donc occupé jusqu'à la fin **réelle** du processus moteur, même après un
arrêt, un plantage ou le dépassement du délai d'arrêt.

Le format de stockage et les mesures globales vivent dans
`transcription_bench.resultats` ; ce module ne fait que les alimenter. Une erreur
d'écriture (disque plein, remplacement refusé) n'est jamais ignorée : elle est
retenue par la consignation, le moteur est arrêté aussitôt, la collecte s'arrête
et l'exécution est close en échec — l'état final est malgré tout tenté, en
`failed` avec le motif retenu. Si le PID du processus moteur ne peut pas être
consigné au lancement, le moteur est également arrêté et l'exécution échoue
avant toute collecte : sans PID persisté, la récupération de 6.5 ne pourrait pas
retrouver le processus. Une fois l'état final écrit, `run.json` n'est plus
modifié : la clôture des exécutions restées `running` est faite par la
récupération du démarrage (tâche 6.5), et les pages de résultats relèvent de la
tâche 7.x.

Après interruption ou échec, les durées vont jusqu'à la clôture et la sortie du
moteur, et le pic mémoire consigné est le dernier relevé transmis, marqué comme
partiel. `run.log` et `result.json` conservent les marques `factice`,
`synthetique` et `mesures_simulees` : un résultat simulé ne peut pas être
présenté comme réel.

Métadonnées : chaque `ResultatExecution` et chaque `ResultatAudio` porte
`factice` et `synthetique`, en plus des champs de provenance `factice` et
`mesures_simulees` déjà présents dans chaque événement du runner.

Aucun secret n'est persisté : ni jeton, ni variable d'environnement. Les chemins
persistés comme données sont relatifs au dossier de résultat ; seuls un message
d'erreur et les lignes brutes du journal du moteur (`run.log`) peuvent citer un
chemin absolu du système.

Verrous : ce service n'utilise ni verrou du créneau ni verrou de stockage de
façon imbriquée. Son verrou interne protège l'état d'exécution (processus en
cours, drapeau d'arrêt, dernière issue) et n'est jamais tenu pendant un appel au
créneau (journal) ni pendant une E/S longue : l'ordre « verrou du créneau puis
verrou de stockage » du reste du programme n'est donc jamais inversé ici.

Limites assumées : le dossier de travail et les signaux décodés vivent sous
`data/cache/`. Après un arrêt brutal du serveur ils subsistent : la récupération
du démarrage (tâche 6.5) les supprime, une fois vérifié qu'aucun moteur
enregistré n'est vivant. La supervision des signaux du
serveur et l'arrêt du moteur au moment de l'arrêt normal du serveur relèvent de
la tâche 6.6. Aucune inférence réelle n'est possible ici pour les moteurs réels,
dont les familles ne sont pas qualifiées sur PC : seul le moteur factice est
exécutable, avec des textes et des mesures simulés, jamais représentatifs d'un
PC.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from collections import deque
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

import numpy as np
import psutil

from engines.hors_ligne import commande_runner, environnement_moteur
from engines.protocole import (
    TYPE_AUDIO,
    TYPE_AUDIO_ERREUR,
    TYPE_CHARGEMENT,
    TYPE_FIN,
    analyser_ligne,
)
from engines.registre import MoteurInconnu, RegistreMoteurs
from transcription_bench.audios import AudioDecode, decoder_audio
from transcription_bench.executions import DemandeExecution
from transcription_bench.gestion_modeles import NOM_DOSSIER_FICHIERS
from transcription_bench.moteurs import (
    ETAT_PRET,
    LIBELLES_ETATS_MOTEUR,
    InstallationEchouee,
    InstallationIndisponible,
    InstallationMoteurs,
    empreinte_fichier,
)
from transcription_bench.operations import (
    OperationEchouee,
    OperationInterrompue,
    Travailleur,
    horodatage_iso,
)
from transcription_bench.paths import (
    NOM_DOSSIER_CACHE,
    NOM_DOSSIER_MODELES,
    NOM_DOSSIER_RESULTATS,
    ValeurRefusee,
    resoudre_dans_racine,
)
from transcription_bench.processus import (
    arreter_descendants,
    arreter_groupe,
    descendants,
    options_groupe,
)
from transcription_bench.resultats import (
    SOURCE_HEURE_PSUTIL,
    SOURCE_HEURE_SERVEUR,
    ConsignateurExecution,
    metadonnees_moteur,
)

#: Version et format de signal du job, tenus égaux à ceux du runner par un test
#: (`engines.runner.VERSION_JOB`, `engines.runner.FORMAT_AUDIO`), sans importer
#: le runner dans le serveur.
VERSION_JOB = 1
FORMAT_AUDIO_BRUT = "float32le-16000-mono"
#: Type numpy écrit dans le fichier brut : `float32` little-endian (`<f4`).
TYPE_SIGNAL = "<f4"

NOM_FICHIER_JOB = "job.json"
#: Moteur dont le modèle exécutable est un **fichier** GGUF unique, choisi à
#: l'ajout du modèle, et non le dossier `fichiers/`.
MOTEUR_GGUF = "transcribe-cpp"
PREFIXE_FICHIER_BRUT = "audio-"
SUFFIXE_FICHIER_BRUT = ".f32"
#: Préfixe des dossiers de travail créés sous `data/cache`, tenu égal à
#: `recuperation.PREFIXE_DOSSIER_TRAVAIL` par un test : la récupération ne purge
#: que ces dossiers-là.
PREFIXE_DOSSIER_TRAVAIL = "execution-"

#: Délai d'attente après `terminate` avant `kill`, puis après `kill`.
DELAI_ARRET_MOTEUR = 5.0
PAS_SONDAGE_ARRET = 0.02
#: Nombre maximal de lignes de sortie d'erreur conservées (les plus récentes).
NOMBRE_LIGNES_STDERR_MAX = 2000
#: Nombre maximal de lignes parasites journalisées ; le total reste consigné.
NOMBRE_LIGNES_PARASITES_JOURNALISEES = 20

ETAT_TERMINEE = "terminee"
ETAT_INTERROMPUE = "interrompue"
ETAT_ECHOUEE = "echouee"

#: Issues d'une demande d'arrêt (`arreter_execution`).
ARRET_AUCUN = "aucun"
ARRET_DEMANDE = "demande"
ARRET_SURVIVANT = "survivant"


class ExecutionImpossible(RuntimeError):
    """Exécution refusée avant lancement : moteur non prêt, interpréteur absent
    ou dossier de travail impossible à créer."""


class ExecutionEchouee(OperationEchouee):
    """Exécution en échec propre : processus moteur mort ou événements manquants.

    L'échec est signalé par une exception pour que le créneau enregistre lui
    aussi l'issue ; le `ResultatExecution` correspondant reste disponible.
    """


@dataclass(frozen=True)
class AudioPrepare:
    """Métadonnées d'un audio décodé et écrit, sans le signal (libéré).

    Le signal brut n'est pas conservé : il est écrit dans `fichier_brut` dès son
    décodage, puis seul ce résumé reste en mémoire.
    """

    index: int
    nom: str
    fichier_brut: str
    format: str
    taille_octets: int
    empreinte_sha256: str
    duree_indicative: float | None
    duree_decodee: float
    echantillons: int
    temps_decodage: float


@dataclass(frozen=True)
class ResultatAudio:
    """Issue d'un audio d'une exécution, telle que la tâche 6.4 la persistera.

    `prepare` est absent si le décodage a échoué ou si l'arrêt a été demandé
    avant ce décodage ; `evenement` est l'événement `audio` reçu du runner,
    `None` si l'audio n'a pas été traité ou si le moteur a signalé une erreur.
    `erreur` porte alors le motif. Un audio sans `evenement` ni `erreur` est
    **non traité** (arrêt ou plantage avant son tour). `factice` et
    `synthetique` accompagnent chaque audio pour qu'aucun résultat simulé ne
    puisse être présenté comme réel.
    """

    index: int
    nom: str
    prepare: AudioPrepare | None
    evenement: Mapping[str, Any] | None
    erreur: str | None
    factice: bool
    synthetique: bool

    @property
    def non_traite(self) -> bool:
        """Vrai si le moteur n'a produit ni résultat ni erreur pour cet audio."""
        return self.evenement is None and self.erreur is None


@dataclass(frozen=True)
class ResultatExecution:
    """Issue complète d'une exécution, en mémoire, et référence de sa consignation.

    `evenements` conserve tous les événements interprétés, dans l'ordre reçu :
    c'est le journal que la consignation persiste au fil de l'eau. Le résumé
    du moteur (`journal_moteur`) est borné ; le fichier `run.log` de la
    consignation, lui, n'est pas borné. `pid` est celui du processus lancé,
    utile aux tâches 6.4 et 6.5.

    `identifiant_resultat` nomme le dossier écrit sous `data/results` (absent si
    le stockage n'a pas pu être ouvert), et les deux durées sont les mesures
    serveur de D8 : `duree_operation_s` va du début de la préparation à la fin de
    la collecte du moteur et de l'écriture des résultats d'audios, hors ultime
    sauvegarde de `run.json` ; `duree_processus_s` va du lancement du moteur à sa
    sortie. Une durée inconnue vaut `None`, jamais zéro.
    """

    etat: str
    factice: bool
    synthetique: bool
    moteur: str
    famille: str
    modele_identifiant: str
    threads_demandes: int
    audios: tuple[ResultatAudio, ...]
    evenements: tuple[Mapping[str, Any], ...]
    lignes_parasites: int
    journal_moteur: tuple[str, ...]
    erreur: str | None = None
    code_sortie: int | None = None
    pid: int | None = None
    arret_demande: bool = False
    identifiant_resultat: str | None = None
    duree_operation_s: float | None = None
    duree_processus_s: float | None = None

    @property
    def audios_non_traites(self) -> tuple[str, ...]:
        """Noms des audios que le moteur n'a pas traités (arrêt, plantage)."""
        return tuple(audio.nom for audio in self.audios if audio.non_traite)

    @property
    def audios_en_erreur(self) -> tuple[str, ...]:
        """Noms des audios en erreur (décodage ou erreur signalée par le moteur)."""
        return tuple(audio.nom for audio in self.audios if audio.erreur is not None)


def evaluer_issue(
    *,
    code_sortie: int,
    arret_demande: bool,
    evenements: Sequence[Mapping[str, Any]],
    indices_job: Sequence[int],
    nb_audios: int,
) -> tuple[str, str | None]:
    """Décide l'état final et son motif, à partir des seuls faits observés.

    Règles, dans cet ordre : une demande d'arrêt donne `interrompue` quel que
    soit le code de sortie ; une sortie non nulle est un échec ; l'absence de
    l'événement `fin` ou d'un événement pour un audio du job est un échec. Aucun
    succès n'est déduit d'une sortie vide. `indices_job` associe la position d'un
    audio dans le job à sa position dans la demande.
    """
    if arret_demande:
        return ETAT_INTERROMPUE, None
    if code_sortie != 0:
        return (
            ETAT_ECHOUEE,
            f"le processus moteur s'est terminé avec le code {code_sortie}",
        )
    if not any(evenement.get("type") == TYPE_FIN for evenement in evenements):
        return ETAT_ECHOUEE, "événement de fin absent de la sortie du moteur"
    traites: set[int] = set()
    for evenement in evenements:
        if evenement.get("type") not in (TYPE_AUDIO, TYPE_AUDIO_ERREUR):
            continue
        position = evenement.get("index")
        if _position_valide(position, len(indices_job)):
            traites.add(indices_job[position])
    manquants = [index for index in indices_job if index not in traites]
    if manquants:
        positions = ", ".join(str(index + 1) for index in sorted(manquants))
        return (
            ETAT_ECHOUEE,
            f"événements d'audio manquants pour l'audio n° {positions} "
            f"(demande de {nb_audios} audio(s))",
        )
    return ETAT_TERMINEE, None


class ProcessusMoteur:
    """Sous-processus du moteur, dans son propre groupe, avec arrêt borné.

    Le contrôle de la demande d'arrêt, `Popen` et l'enregistrement du processus
    se font sous le même verrou court : un arrêt demandé avant le lancement
    empêche le démarrage, et un arrêt demandé pendant le démarrage voit toujours
    un processus déjà enregistré. `arreter` est idempotent, ne lève pas et ne
    laisse pas de processus survivant quand le système coopère : il signale le
    **groupe** du processus (`SIGTERM`, attente bornée par sondage, puis
    `SIGKILL`) pour atteindre aussi les descendants lancés par un moteur réel ;
    sous Windows, l'arborescence psutil est terminée au mieux.
    """

    def __init__(
        self,
        *,
        delai_arret: float = DELAI_ARRET_MOTEUR,
        pas_sondage: float = PAS_SONDAGE_ARRET,
    ) -> None:
        self._verrou = threading.Lock()
        self._processus: subprocess.Popen[str] | None = None
        self._arrete = False
        self._delai_arret = delai_arret
        self._pas_sondage = pas_sondage

    @property
    def pid(self) -> int | None:
        """PID du processus lancé, ou `None` avant le lancement."""
        with self._verrou:
            processus = self._processus
        return None if processus is None else processus.pid

    def lancer(
        self,
        commande: Sequence[str],
        *,
        environ: Mapping[str, str],
        dossier: Path,
    ) -> subprocess.Popen[str]:
        """Lance la commande dans un groupe de processus propre.

        Le répertoire de travail est le dossier de travail de l'exécution :
        rien n'est écrit dans le dépôt. Lève `ExecutionImpossible` si un arrêt a
        déjà été demandé.
        """
        options = options_groupe()
        with self._verrou:
            if self._arrete:
                raise ExecutionImpossible(
                    "arrêt demandé : le processus moteur n'est pas lancé"
                )
            processus = subprocess.Popen(
                list(commande),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                env=dict(environ),
                cwd=str(dossier),
                bufsize=1,
                **options,
            )
            self._processus = processus
        return processus

    def arreter(self) -> bool:
        """Termine le groupe du processus : signal d'arrêt, attente, puis forcage.

        Le signal vise le groupe (POSIX) ou l'arborescence (Windows), pas
        seulement le processus direct : un moteur qui aurait lancé un
        sous-traitant ne doit pas en laisser un survivant. La descendance est
        relevée **avant** le signal, puis attendue et tuée si elle y survit :
        après la sortie du processus principal, le groupe n'est plus signalable.
        Renvoie `True` si le processus direct est terminé (ou n'a jamais été
        lancé), `False` s'il survit au délai même après le signal de forçage.
        """
        with self._verrou:
            self._arrete = True
            processus = self._processus
        if processus is None:
            return True
        if processus.poll() is not None:
            # Processus déjà collecté : son PID peut déjà avoir été réutilisé, le
            # groupe n'est donc plus signalé (un descendant resté orphelin après
            # une sortie propre n'est plus supervisable sans risque).
            return True
        arbre = descendants(processus.pid)
        arreter_groupe(processus)
        sorti = self._attendre_sortie(processus)
        if not sorti:
            arreter_groupe(processus, force=True)
            sorti = self._attendre_sortie(processus)
        arreter_descendants(arbre, self._delai_arret)
        return sorti

    def _attendre_sortie(self, processus: subprocess.Popen[str]) -> bool:
        """Sonde la sortie du processus pendant un délai borné, sans `wait` bloquant."""
        echeance = time.monotonic() + self._delai_arret
        while time.monotonic() < echeance:
            if processus.poll() is not None:
                return True
            time.sleep(self._pas_sondage)
        return processus.poll() is not None

    def attendre_fin(self) -> None:
        """Attend la fin réelle du processus, sans limite de durée.

        N'est appelé qu'après un arrêt qui n'a pas abouti (processus survivant
        à `kill`) : l'appelant garde alors le créneau occupé jusqu'à la fin
        réelle du processus, sans supprimer son dossier de travail avant.
        """
        with self._verrou:
            processus = self._processus
        if processus is None:
            return
        try:
            processus.wait()
        except (OSError, ChildProcessError):
            return

    def fermer(self) -> None:
        """Ferme les tuyaux du processus, après sa sortie, sans jamais lever."""
        with self._verrou:
            processus = self._processus
        if processus is None:
            return
        for flux in (processus.stdout, processus.stderr):
            if flux is None:
                continue
            try:
                flux.close()
            except (OSError, ValueError):
                continue


class ExecutionMoteur:
    """Prépare, lance, supervise et clôt une exécution dans le créneau.

    Le service est construit une fois, sans aucune E/S. `reserver` puis `lancer`
    s'exécutent dans le thread de fond du créneau ; ils ne reçoivent aucun objet
    Flask. Les coutures injectables (`decoder`, `construire_commande`,
    `interpreteur_serveur`, `racine_temporaire`) servent aux tests ; aucune
    n'est nécessaire en exploitation.
    """

    def __init__(
        self,
        dossier_data: Path | str,
        registre: RegistreMoteurs,
        moteurs: InstallationMoteurs,
        *,
        decoder: Callable[[str, Path | str | None], AudioDecode] = decoder_audio,
        construire_commande: Callable[[str | Path, str | Path], list[str]] = commande_runner,
        interpreteur_serveur: str | Path | None = None,
        racine_temporaire: Path | str | None = None,
        delai_arret: float = DELAI_ARRET_MOTEUR,
    ) -> None:
        self._donnees = Path(dossier_data)
        self._registre = registre
        self._moteurs = moteurs
        self._decoder = decoder
        self._construire_commande = construire_commande
        self._interpreteur_serveur = (
            sys.executable if interpreteur_serveur is None else str(interpreteur_serveur)
        )
        #: Base des dossiers de travail : `data/cache` en exploitation, une
        #: racine de test injectée à la place pour ne rien écrire sous `data/`.
        self._racine_travail = (
            self._donnees / NOM_DOSSIER_CACHE
            if racine_temporaire is None
            else Path(racine_temporaire)
        )
        self._delai_arret = delai_arret
        self._verrou = threading.Lock()
        self._processus_moteur: ProcessusMoteur | None = None
        self._travailleur: Travailleur | None = None
        self._active = False
        self._arret_demande = False
        self._arret_serveur = False
        self._derniere: ResultatExecution | None = None
        #: Association publiée du résultat consigné et de l'opération admise
        #: (`generation`, identifiant du résultat). Écrite dès la création de la
        #: consignation et conservée après la clôture ; jamais exposée pour une
        #: autre génération, donc jamais pour une opération suivante.
        self._resultat_publie: tuple[int, str] | None = None

    # -- état observable (routes, tests, tâches 6.4 à 6.6) -------------------

    def derniere_execution(self) -> ResultatExecution | None:
        """Dernière exécution close, ou `None` si aucune n'est terminée.

        Vue de la dernière issue seulement : elle ne dit rien de l'exécution
        active. Le lien vers le résultat consigné, y compris pendant
        l'exécution, se lit par `identifiant_resultat`.
        """
        with self._verrou:
            return self._derniere

    def identifiant_resultat(self, generation: int | None) -> str | None:
        """Identifiant du résultat consigné par l'opération admise `generation`.

        Vue synchronisée du lien résultat/opération du design D5 : l'appelant
        lit l'identité d'abord (`CreneauOperations.instantane().generation`),
        puis demande l'identifiant associé à cette génération. L'association est
        publiée sous verrou dès que la consignation existe : le lien est donc
        disponible pendant l'exécution comme après sa clôture, alors que
        `derniere_execution` ne décrit que le cas clos.

        Aucune invalidation par rappel n'est nécessaire : chaque admission du
        créneau change de génération, et l'association n'est jamais renvoyée
        pour une génération différente. Une installation, un téléchargement, une
        vérification ou une exécution échouée avant la création de la
        consignation ne reçoit donc aucun identifiant, même si une exécution
        antérieure a consigné des résultats : `None` est renvoyé.
        """
        with self._verrou:
            publie = self._resultat_publie
        if publie is None or generation is None:
            return None
        generation_publiee, identifiant = publie
        return identifiant if generation_publiee == generation else None

    def en_cours(self) -> bool:
        """Vrai si une exécution prépare, exécute ou collecte encore son moteur."""
        with self._verrou:
            return self._active

    def pid_actif(self) -> int | None:
        """PID du processus moteur courant, ou `None`."""
        with self._verrou:
            processus = self._processus_moteur
        return None if processus is None else processus.pid

    def verifier_lancable(self, demande: DemandeExecution) -> None:
        """Revalide au lancement que le moteur et son interpréteur sont disponibles.

        Le modèle prêt est revalidé par le service des demandes (tâche 6.2) ;
        ici on recontrôle le moteur : prêt au sens de l'inventaire local, sauf le
        moteur factice qui n'a ni environnement ni installation et s'exécute avec
        l'interpréteur du serveur. Lève `ExecutionImpossible` sinon, sans effet
        de bord et sans lancer de processus.
        """
        self._interpreteur(demande)

    def arreter_execution(self, *, arret_serveur: bool = False) -> str:
        """Demande l'arrêt de l'exécution active, sans dépendre d'un contexte Flask.

        Idempotent. Renvoie `ARRET_AUCUN` sans exécution active, `ARRET_DEMANDE`
        si l'arrêt a été demandé et le processus terminé (ou jamais lancé), et
        `ARRET_SURVIVANT` si le processus n'a pas pu être terminé, même après
        `kill`. Le verrou du service n'est pas tenu pendant la journalisation ni
        pendant la terminaison du processus. `reserver` a créé le processus
        moteur : une exécution active en a donc toujours un, même avant son
        démarrage effectif. `arret_serveur` distingue l'arrêt normal du serveur
        d'une demande de l'utilisateur, pour que le journal du créneau nomme le
        bon motif.
        """
        with self._verrou:
            if not self._active:
                return ARRET_AUCUN
            self._arret_demande = True
            self._arret_serveur = self._arret_serveur or arret_serveur
            processus = self._processus_moteur
            travailleur = self._travailleur
        if travailleur is not None:
            travailleur.journaliser(
                "Arrêt de l'exécution demandé : terminaison du processus moteur."
            )
        return ARRET_DEMANDE if processus.arreter() else ARRET_SURVIVANT

    def reserver(self) -> None:
        """Réserve l'exécution avant son admission dans le créneau.

        Appelé par la route avant `creneau.demarrer` : une réservation existe
        donc dès avant le démarrage effectif, et un arrêt demandé dans cet
        intervalle n'est pas perdu. `lancer` ne remet jamais ces drapeaux à
        zéro : seul `reserver` les pose, `annuler_reservation` ou la clôture de
        l'exécution les libèrent. Lève `ExecutionImpossible` si une exécution
        est déjà réservée ou active.
        """
        with self._verrou:
            if self._active:
                raise ExecutionImpossible("une exécution est déjà active")
            self._active = True
            self._arret_demande = False
            self._arret_serveur = False
            self._processus_moteur = ProcessusMoteur(delai_arret=self._delai_arret)

    def annuler_reservation(self) -> None:
        """Libère une réservation que le créneau n'a pas admise (409 ou 503).

        La dernière issue publiée est conservée : un refus n'efface pas le
        résultat de l'exécution précédente.
        """
        with self._verrou:
            self._active = False
            self._processus_moteur = None
            self._travailleur = None

    # -- thread de fond du créneau ------------------------------------------

    def lancer(self, demande: DemandeExecution, travailleur: Travailleur) -> None:
        """Exécute une demande validée dans le thread de fond du créneau.

        Ne reçoit que des valeurs (la demande validée) et le handle du créneau :
        aucun objet Flask, aucune demande de persistance. Lève `ExecutionEchouee`
        pour un échec prévu (moteur mort, événements manquants, écriture des
        résultats impossible) et `OperationInterrompue` après un arrêt demandé
        par l'utilisateur, afin que le créneau enregistre l'issue ; un arrêt du
        serveur, lui, n'est pas une demande de l'utilisateur et c'est le créneau,
        déjà passé à l'arrêt, qui en consigne le motif. Le `ResultatExecution`
        reste disponible par `derniere_execution`.

        La consignation des résultats est propre à cette exécution : créée avant
        toute préparation, elle est close dans tous les cas (y compris une issue
        imprévue), une fois le processus moteur terminé et son journal fermé.
        Son identifiant est publié pour l'opération admise dès sa création, par
        `_publier_resultat` (voir `identifiant_resultat`).
        """
        processus = self._processus_reserve()
        resultat: ResultatExecution | None = None
        dossier: Path | None = None
        consignateur: ConsignateurExecution | None = None
        # Début de la préparation : référence de la durée totale de l'opération.
        debut_operation = time.perf_counter()
        try:
            dossier = self._creer_dossier_travail()
            with self._verrou:
                self._travailleur = travailleur
            consignateur, erreur_stockage = self._ouvrir_consignation(
                demande, travailleur, debut_operation
            )
            if consignateur is None:
                resultat = self._resultat_avant_lancement(demande, erreur_stockage)
            else:
                # Dès que le dossier de résultat existe, l'identifiant est publié
                # pour cette opération admise : le suivi peut y renvoyer avant la
                # clôture, sans jamais emprunter celui d'une exécution antérieure.
                self._publier_resultat(travailleur.generation, consignateur.identifiant)
                resultat = self._executer(
                    demande, travailleur, dossier, processus, consignateur
                )
        except ExecutionImpossible as exception:
            # Dossier de travail impossible : échec prévu, aucun processus lancé.
            resultat = self._resultat_avant_lancement(demande, _message_erreur(exception))
        except BaseException as exception:  # issue imprévue : jamais de résultat ambigu
            resultat = self._resultat_imprevu(demande, exception)
            raise
        finally:
            # Aucun survivant, quels que soient le chemin et l'issue : le dossier
            # de travail n'est supprimé et l'état libéré qu'après la fin réelle
            # du processus. Le cache décodé part avant la clôture : de la place
            # est ainsi libérée pour l'écriture de l'état final, même après une
            # erreur d'écriture (disque plein).
            self._clore_processus(processus, travailleur)
            processus.fermer()
            if dossier is not None:
                shutil.rmtree(dossier, ignore_errors=True)
            if consignateur is not None:
                consignateur.fermer()
                try:
                    resultat = self._clore_consignation(
                        consignateur, resultat, travailleur
                    )
                except Exception as erreur:  # la libération ne doit jamais manquer
                    travailleur.journaliser(
                        "Clôture de la consignation impossible : "
                        f"{_message_erreur(erreur)}"
                    )
                    if resultat is not None:
                        resultat = replace(
                            resultat,
                            etat=ETAT_ECHOUEE,
                            erreur=(
                                "clôture de la consignation impossible : "
                                f"{_message_erreur(erreur)}"
                            ),
                        )
            self._liberer_execution(resultat)
        self._journaliser_issue(resultat, travailleur)
        if resultat.etat == ETAT_ECHOUEE:
            raise ExecutionEchouee(resultat.erreur or "exécution en échec")
        if resultat.etat == ETAT_INTERROMPUE:
            if self._arret_serveur_actif():
                # L'arrêt du serveur n'est pas une demande de l'utilisateur : le
                # créneau, déjà passé à l'arrêt, consigne ce motif-là.
                return
            raise OperationInterrompue(
                "exécution interrompue à la demande de l'utilisateur"
            )

    def _executer(
        self,
        demande: DemandeExecution,
        travailleur: Travailleur,
        dossier: Path,
        processus: ProcessusMoteur,
        consignateur: ConsignateurExecution,
    ) -> ResultatExecution:
        """Prépare, lance, collecte et consigne ; ne lève pas pour un échec prévu.

        Les mesures serveur vivent dans la consignation : durée du processus
        moteur autour de son lancement et de sa sortie, durée totale de
        l'opération arrêtée après la collecte du moteur et l'écriture des
        résultats d'audios (l'ultime sauvegarde de `run.json` est exclue).
        """
        mesures = consignateur.mesures
        try:
            declaration = self._registre.obtenir(demande.moteur)
        except MoteurInconnu:
            return self._resultat(
                demande,
                factice=False,
                audios=self._audios_non_traites(demande, False),
                etat=ETAT_ECHOUEE,
                erreur=f"moteur inconnu : {demande.moteur!r}",
            )
        factice = declaration.factice
        synthetique = demande.synthetique
        try:
            interpreteur = self._interpreteur(demande)
        except ExecutionImpossible as erreur:
            return self._resultat(
                demande,
                factice=factice,
                audios=self._audios_non_traites(demande, factice),
                etat=ETAT_ECHOUEE,
                erreur=str(erreur),
            )
        travailleur.journaliser(
            f"Préparation de l'exécution : {len(demande.audios)} audio(s), moteur "
            f"{demande.moteur}, famille {demande.famille}, {demande.threads} "
            f"thread(s) demandé(s)"
            + (" (modèle synthétique, textes et mesures simulés)." if synthetique else ".")
        )
        audios = self._preparer_audios(
            demande, travailleur, dossier, factice, consignateur
        )
        if consignateur.erreur is not None:
            # Stockage indisponible : aucun moteur n'est lancé, l'exécution échoue.
            return self._resultat(
                demande,
                factice=factice,
                audios=audios,
                etat=ETAT_ECHOUEE,
                erreur=consignateur.erreur,
            )
        if self._arret_demande_actif():
            travailleur.journaliser(
                "Arrêt demandé avant le lancement du moteur : aucun processus n'est "
                "démarré."
            )
            return self._resultat(
                demande,
                factice=factice,
                audios=audios,
                etat=ETAT_INTERROMPUE,
                arret_demande=True,
            )
        indices_job = tuple(audio.index for audio in audios if audio.prepare is not None)
        if not indices_job:
            return self._resultat(
                demande,
                factice=factice,
                audios=audios,
                etat=ETAT_ECHOUEE,
                erreur=(
                    "aucun audio n'a pu être décodé : aucun processus moteur n'est lancé"
                ),
            )
        chemin_job = dossier / NOM_FICHIER_JOB
        try:
            self._ecrire_job(demande, audios, chemin_job)
        except (OSError, ValeurRefusee) as erreur:
            return self._resultat(
                demande,
                factice=factice,
                audios=audios,
                etat=ETAT_ECHOUEE,
                erreur=f"préparation du job impossible : {_message_erreur(erreur)}",
            )
        # Heure de création et PID consignés dès le lancement : la source dit si
        # l'heure vient du système ou de l'horloge du serveur (repli).
        lance_a = horodatage_iso()
        debut_processus = time.perf_counter()
        try:
            enfant = processus.lancer(
                self._construire_commande(interpreteur, chemin_job),
                environ=environnement_moteur(
                    dossier_cache_numba=self._donnees / "cache-numba"
                ),
                dossier=dossier,
            )
        except (OSError, ExecutionImpossible) as erreur:
            arret = self._arret_demande_actif()
            return self._resultat(
                demande,
                factice=factice,
                audios=audios,
                etat=ETAT_INTERROMPUE if arret else ETAT_ECHOUEE,
                erreur=None if arret else _message_erreur(erreur),
                arret_demande=arret,
            )
        heure_creation, source_heure = _heure_creation_processus(enfant.pid)
        if not consignateur.enregistrer_processus(
            pid=enfant.pid,
            heure_creation=heure_creation,
            source=source_heure or SOURCE_HEURE_SERVEUR,
            lance_a=lance_a,
        ):
            # Sans PID persisté, la récupération de 6.5 ne peut pas retrouver ce
            # processus : le moteur est arrêté et l'exécution conclut en échec
            # avant toute collecte, plutôt que de continuer sans trace du PID.
            arret_reel = processus.arreter()
            if arret_reel:
                mesures.duree_processus_s = time.perf_counter() - debut_processus
            mesures.duree_operation_s = time.perf_counter() - mesures.debut
            travailleur.journaliser(
                "PID du processus moteur impossible à consigner : moteur arrêté, "
                "exécution en échec."
            )
            return self._resultat(
                demande,
                factice=factice,
                audios=audios,
                etat=ETAT_ECHOUEE,
                erreur=(
                    consignateur.erreur
                    or "PID du processus moteur impossible à consigner"
                ),
                code_sortie=enfant.poll(),
                pid=enfant.pid,
            )
        travailleur.journaliser(f"Processus moteur lancé (PID {enfant.pid}).")
        # File locale de cette exécution : aucune ligne d'une exécution précédente
        # ne peut s'y mêler, et sa borne reste valable même si le tuyau déborde.
        # Le fichier `run.log` de la consignation, lui, reçoit toutes les lignes.
        stderr_moteur: deque[str] = deque(maxlen=NOMBRE_LIGNES_STDERR_MAX)
        fil_stderr = threading.Thread(
            target=_collecter_stderr,
            args=(enfant, stderr_moteur, consignateur),
            name="transcription-bench-moteur-stderr",
            daemon=True,
        )
        fil_stderr.start()
        evenements, parasites = self._collecter_evenements(
            enfant,
            processus,
            travailleur,
            demande,
            indices_job,
            factice,
            audios,
            consignateur,
        )
        code_sortie = enfant.wait()
        mesures.duree_processus_s = time.perf_counter() - debut_processus
        fil_stderr.join(self._delai_arret)
        consignateur.fermer()
        arret = self._arret_demande_actif()
        etat, motif = evaluer_issue(
            code_sortie=code_sortie,
            arret_demande=arret,
            evenements=evenements,
            indices_job=indices_job,
            nb_audios=len(demande.audios),
        )
        if consignateur.erreur is not None:
            # Une écriture a échoué pendant la collecte : l'exécution est en échec.
            etat, motif = ETAT_ECHOUEE, consignateur.erreur
        # Fin de la collecte du moteur et de l'écriture des résultats d'audios :
        # la durée totale s'arrête ici, avant l'ultime sauvegarde de `run.json`.
        mesures.duree_operation_s = time.perf_counter() - mesures.debut
        # `deque.copy()` est atomique vis-à-vis des ajouts d'un fil encore vivant.
        journal_moteur = tuple(stderr_moteur.copy())
        _journaliser_stderr(journal_moteur, travailleur)
        return self._resultat(
            demande,
            factice=factice,
            audios=audios,
            etat=etat,
            erreur=motif,
            evenements=evenements,
            parasites=parasites,
            journal_moteur=journal_moteur,
            code_sortie=code_sortie,
            pid=enfant.pid,
            arret_demande=arret,
        )

    # -- préparation ---------------------------------------------------------

    def _interpreteur(self, demande: DemandeExecution) -> str | Path:
        """Interpréteur à utiliser : celui du serveur pour le factice, sinon le venv."""
        try:
            declaration = self._registre.obtenir(demande.moteur)
        except MoteurInconnu:
            raise ExecutionImpossible(f"moteur inconnu : {demande.moteur!r}") from None
        if declaration.factice:
            return self._interpreteur_serveur
        etats = {moteur.identifiant: moteur for moteur in self._moteurs.inventaire()}
        etat = etats.get(demande.moteur)
        if etat is None:
            raise ExecutionImpossible(
                f"moteur non déclaré par l'inventaire : {demande.moteur!r}"
            )
        if etat.etat != ETAT_PRET:
            libelle = LIBELLES_ETATS_MOTEUR.get(etat.etat, etat.etat)
            raise ExecutionImpossible(
                f"moteur non prêt (état : {libelle}) : installation explicite requise "
                "avant toute exécution"
            )
        try:
            return self._moteurs.interpreteur(demande.moteur)
        except (
            InstallationEchouee,
            InstallationIndisponible,
            ValeurRefusee,
            OSError,
        ) as erreur:
            raise ExecutionImpossible(
                f"interpréteur du moteur indisponible : {_message_erreur(erreur)}"
            ) from None

    def _preparer_audios(
        self,
        demande: DemandeExecution,
        travailleur: Travailleur,
        dossier: Path,
        factice: bool,
        consignateur: ConsignateurExecution,
    ) -> list[ResultatAudio]:
        """Décode chaque audio et écrit son signal brut dès qu'il est décodé.

        Une erreur sur un audio (décodage, écriture) devient une erreur propre à
        cet audio : les suivants sont traités normalement, et son résultat est
        consigné immédiatement, donc avant de passer au suivant. Une demande
        d'arrêt interrompt la préparation sans lancer le moteur. Si le stockage
        devient indisponible, les audios restants ne sont plus décodés (ils
        resteront non traités) : l'appelant close l'exécution en échec.
        """
        resultats: list[ResultatAudio] = []
        total = len(demande.audios)
        for index, nom in enumerate(demande.audios):
            if consignateur.erreur is not None or self._arret_demande_actif():
                resultats.append(_audio_non_traite(index, nom, factice, demande.synthetique))
                continue
            try:
                decode = self._decoder(nom, self._donnees)
            except Exception as erreur:  # un audio ne bloque jamais les suivants
                message = _message_erreur(erreur)
                resultats.append(
                    ResultatAudio(
                        index=index,
                        nom=nom,
                        prepare=None,
                        evenement=None,
                        erreur=f"décodage impossible : {message}",
                        factice=factice,
                        synthetique=demande.synthetique,
                    )
                )
                travailleur.journaliser(
                    f"Audio {index + 1}/{total} « {nom} » : décodage impossible "
                    f"({message})."
                )
                consignateur.enregistrer_audio(resultats[-1])
                continue
            fichier_brut = f"{PREFIXE_FICHIER_BRUT}{index}{SUFFIXE_FICHIER_BRUT}"
            try:
                # Écriture directe du signal décodé : aucune copie conservée.
                np.asarray(decode.signal, dtype=TYPE_SIGNAL).tofile(dossier / fichier_brut)
            except OSError as erreur:
                message = _message_erreur(erreur)
                resultats.append(
                    ResultatAudio(
                        index=index,
                        nom=nom,
                        prepare=None,
                        evenement=None,
                        erreur=f"écriture du signal brut impossible : {message}",
                        factice=factice,
                        synthetique=demande.synthetique,
                    )
                )
                travailleur.journaliser(
                    f"Audio {index + 1}/{total} « {nom} » : écriture du signal brut "
                    f"impossible ({message})."
                )
                consignateur.enregistrer_audio(resultats[-1])
                continue
            prepare = AudioPrepare(
                index=index,
                nom=nom,
                fichier_brut=fichier_brut,
                format=decode.format,
                taille_octets=decode.taille_octets,
                empreinte_sha256=decode.empreinte_sha256,
                duree_indicative=decode.duree_indicative,
                duree_decodee=decode.duree_decodee,
                echantillons=decode.echantillons,
                temps_decodage=decode.temps_decodage,
            )
            # Le signal complet n'est pas conservé au-delà de cette itération.
            del decode
            resultats.append(
                ResultatAudio(
                    index=index,
                    nom=nom,
                    prepare=prepare,
                    evenement=None,
                    erreur=None,
                    factice=factice,
                    synthetique=demande.synthetique,
                )
            )
            travailleur.journaliser(
                f"Audio {index + 1}/{total} « {nom} » décodé : "
                f"{prepare.duree_decodee:.2f} s décodées, signal brut écrit."
            )
        return resultats

    def _ecrire_job(
        self, demande: DemandeExecution, audios: Sequence[ResultatAudio], chemin: Path
    ) -> None:
        """Écrit `job.json` au format attendu par `engines/runner.py`."""
        contenu = {
            "version": VERSION_JOB,
            "moteur": demande.moteur,
            "famille": demande.famille,
            "modele": {
                "identifiant": demande.identifiant,
                "revision": demande.commit,
                "chemin": str(self.chemin_modele(demande)),
            },
            "threads_demandes": demande.threads,
            "reglages": {
                reglage.nom: reglage.valeur for reglage in demande.reglages
            },
            "format_audio": FORMAT_AUDIO_BRUT,
            "audios": [
                {"nom": audio.nom, "chemin": audio.prepare.fichier_brut}
                for audio in audios
                if audio.prepare is not None
            ],
        }
        chemin.write_text(
            json.dumps(contenu, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def chemin_modele(self, demande: DemandeExecution) -> Path:
        """Emplacement du modèle sous `data/models`, contrôlé.

        Pour un moteur GGUF (`transcribe-cpp`), le chemin transmis au job est le
        **fichier** retenu à l'ajout (`demande.fichier_gguf`), résolu sous
        `data/models/<moteur>/<clé>/fichiers/` : un nom absent, absolu, remontant
        ou sortant est refusé par `resoudre_dans_racine`, et un fichier
        introuvable est refusé avant tout lancement. Les autres moteurs reçoivent
        le dossier `fichiers/` (CTranslate2, Transformers). Le modèle synthétique
        du factice n'existe pas et n'est pas lu.
        """
        dossier_moteur = resoudre_dans_racine(
            self._donnees / NOM_DOSSIER_MODELES, demande.moteur
        )
        dossier_fichiers = resoudre_dans_racine(
            dossier_moteur, f"{demande.cle}/{NOM_DOSSIER_FICHIERS}"
        )
        if demande.moteur != MOTEUR_GGUF:
            return dossier_fichiers
        if not isinstance(demande.fichier_gguf, str) or not demande.fichier_gguf:
            raise ValeurRefusee(
                "fichier GGUF absent de la demande pour le moteur "
                f"{demande.moteur!r}"
            )
        fichier = resoudre_dans_racine(dossier_fichiers, demande.fichier_gguf)
        if not fichier.is_file():
            raise ValeurRefusee(f"fichier GGUF introuvable : {demande.fichier_gguf!r}")
        return fichier

    # -- collecte ------------------------------------------------------------

    def _collecter_evenements(
        self,
        enfant: subprocess.Popen[str],
        processus: ProcessusMoteur,
        travailleur: Travailleur,
        demande: DemandeExecution,
        indices_job: Sequence[int],
        factice: bool,
        audios: list[ResultatAudio],
        consignateur: ConsignateurExecution,
    ) -> tuple[list[Mapping[str, Any]], int]:
        """Lit la sortie standard, n'interprète que les événements du protocole.

        Toute autre ligne (sortie parasite, événement illisible, index hors du
        job, provenance `factice` incohérente avec la déclaration, événement en
        double) est comptée et journalisée sans provoquer d'échec. Après une
        demande d'arrêt, les lignes suivantes sont drainées sans être
        interprétées.

        Chaque événement d'audio met à jour le résultat de cet audio et le
        consigne aussitôt, donc avant l'audio suivant. Une erreur d'écriture ne
        lève pas : la consignation la retient, le moteur est aussitôt arrêté (la
        fin réelle reste attendue par l'appelant, qui garde le créneau jusqu'à
        elle), les lignes suivantes sont drainées sans être interprétées et
        l'appelant conclut à un échec. Les résultats déjà écrits restent valides.
        """
        evenements: list[Mapping[str, Any]] = []
        parasites = 0
        ecriture_impossible = False
        vus: set[tuple[str, int | None]] = set()
        flux = enfant.stdout
        if flux is None:
            return evenements, parasites
        for brut in flux:
            if ecriture_impossible or self._arret_demande_actif():
                continue
            ligne = brut.rstrip("\r\n")
            evenement = analyser_ligne(ligne)
            motif = _motif_ligne_ignoree(
                evenement, indices_job=indices_job, factice=factice, vus=vus
            )
            if motif is not None:
                parasites += 1
                if parasites <= NOMBRE_LIGNES_PARASITES_JOURNALISEES:
                    travailleur.journaliser(
                        f"Sortie du moteur ignorée ({motif}) : {_resume_ligne(ligne)}"
                    )
                continue
            vus.add(_cle_evenement(evenement))
            evenements.append(evenement)
            self._journaliser_evenement(evenement, travailleur, len(demande.audios))
            _consigner_evenement(audios, indices_job, evenement, consignateur)
            if consignateur.erreur is not None:
                ecriture_impossible = True
                processus.arreter()
        return evenements, parasites

    def _journaliser_evenement(
        self, evenement: Mapping[str, Any], travailleur: Travailleur, total: int
    ) -> None:
        """Journalise brièvement un événement interprété, sans recopier de texte long."""
        type_evenement = evenement.get("type")
        if type_evenement == TYPE_CHARGEMENT:
            travailleur.journaliser("Modèle chargé : événement de chargement reçu.")
        elif type_evenement == TYPE_AUDIO:
            travailleur.journaliser(
                f"Audio « {evenement.get('nom')} » transcrit : événement reçu."
            )
        elif type_evenement == TYPE_AUDIO_ERREUR:
            travailleur.journaliser(
                f"Audio « {evenement.get('nom')} » en erreur côté moteur : "
                f"{_resume_ligne(str(evenement.get('erreur', '')))}"
            )
        elif type_evenement == TYPE_FIN:
            travailleur.journaliser(
                f"Fin du moteur annoncée : {evenement.get('audios_ok')} audio(s) "
                f"transcrit(s), {evenement.get('audios_erreur')} en erreur, sur {total}."
            )

    def _journaliser_issue(
        self, resultat: ResultatExecution, travailleur: Travailleur
    ) -> None:
        """Journalise l'issue finale en une ligne, pour la page d'opération."""
        traites = sum(1 for audio in resultat.audios if audio.evenement is not None)
        erreurs = len(resultat.audios_en_erreur)
        non_traites = len(resultat.audios_non_traites)
        resume = (
            f"{traites} audio(s) transcrit(s), {erreurs} en erreur, "
            f"{non_traites} non traité(s)"
        )
        if resultat.etat == ETAT_TERMINEE:
            travailleur.journaliser(f"Exécution terminée : {resume}.")
        elif resultat.etat == ETAT_INTERROMPUE:
            travailleur.journaliser(
                f"Exécution interrompue : {resume}. Les résultats reçus sont conservés."
            )
        else:
            travailleur.journaliser(
                f"Exécution en échec : {resume} ({resultat.erreur})."
            )
        if resultat.identifiant_resultat is not None:
            travailleur.journaliser(
                f"Résultats consignés : {NOM_DOSSIER_RESULTATS}/"
                f"{resultat.identifiant_resultat}."
            )

    # -- état et helpers -----------------------------------------------------

    def _processus_reserve(self) -> ProcessusMoteur:
        """Processus réservé par `reserver`, sans quoi le lancement est refusé."""
        with self._verrou:
            processus = self._processus_moteur
        if processus is None:
            raise ExecutionImpossible("aucune réservation : lancement refusé")
        return processus

    def _creer_dossier_travail(self) -> Path:
        """Crée paresseusement le dossier de travail de l'exécution.

        Par défaut `data/cache/<id>` : les signaux décodés ne vont jamais dans
        le répertoire temporaire du système, qui peut être vidé sans lien avec
        l'exécution. `racine_temporaire` remplace cette base pour les tests.
        Lève `ExecutionImpossible` si le dossier ne peut pas être créé, avant
        tout lancement de processus.
        """
        try:
            self._racine_travail.mkdir(parents=True, exist_ok=True)
            return Path(
                tempfile.mkdtemp(
                    prefix=PREFIXE_DOSSIER_TRAVAIL, dir=self._racine_travail
                )
            )
        except OSError as erreur:
            raise ExecutionImpossible(
                f"dossier de travail impossible : {_message_erreur(erreur)}"
            ) from None

    def _clore_processus(
        self, processus: ProcessusMoteur, travailleur: Travailleur | None
    ) -> None:
        """Termine le processus, puis attend sa fin réelle si l'arrêt échoue.

        Un processus insensible à `kill` garde le créneau occupé jusqu'à sa fin
        réelle : le dossier de travail n'est supprimé et l'état libéré
        qu'ensuite.
        """
        if processus.arreter():
            return
        if travailleur is not None:
            travailleur.journaliser(
                "Processus moteur encore actif après kill : attente de sa fin réelle, "
                "le créneau reste occupé jusque-là."
            )
        processus.attendre_fin()

    def _liberer_execution(self, resultat: ResultatExecution | None) -> None:
        """Libère l'état d'exécution et publie la dernière issue, sous verrou."""
        with self._verrou:
            self._active = False
            self._processus_moteur = None
            self._travailleur = None
            self._derniere = resultat

    def _publier_resultat(self, generation: int, identifiant: str) -> None:
        """Associe le résultat consigné à l'opération admise, sous verrou.

        Une publication remplace la précédente : dès qu'une nouvelle exécution
        crée sa consignation, l'ancienne association n'est plus exposée, sans
        comparaison de type ni de début. Le verrou du moteur est pris seul, sans
        appel au créneau sous ce verrou : aucun ordre de verrous croisé.
        """
        with self._verrou:
            self._resultat_publie = (generation, identifiant)

    def _arret_demande_actif(self) -> bool:
        with self._verrou:
            return self._arret_demande

    def _arret_serveur_actif(self) -> bool:
        with self._verrou:
            return self._arret_serveur

    def _factice(self, demande: DemandeExecution) -> bool:
        """Déclaration du moteur demandé, ou `False` s'il est inconnu."""
        try:
            return self._registre.obtenir(demande.moteur).factice
        except MoteurInconnu:
            return False

    def _audios_non_traites(
        self, demande: DemandeExecution, factice: bool
    ) -> list[ResultatAudio]:
        """Un résultat « non traité » par audio demandé, dans l'ordre de la demande."""
        return [
            _audio_non_traite(index, nom, factice, demande.synthetique)
            for index, nom in enumerate(demande.audios)
        ]

    # -- consignation des résultats (tâche 6.4) ------------------------------

    def _metadonnees_moteur(self, demande: DemandeExecution) -> dict[str, Any]:
        """Identité du moteur demandé, verrou de dépendances et versions lues.

        Les versions viennent du marqueur d'installation relu par l'inventaire
        local, jamais d'une supposition ; le moteur factice n'a ni verrou ni
        version, et un moteur inconnu est consigné comme tel.
        """
        try:
            declaration = self._registre.obtenir(demande.moteur)
        except MoteurInconnu:
            return metadonnees_moteur(demande.moteur, demande.moteur, factice=False)
        empreinte: str | None = None
        versions: dict[str, str | None] | None = None
        if not declaration.factice:
            try:
                empreinte = empreinte_fichier(self._moteurs.chemin_verrou(declaration))
            except (InstallationIndisponible, ValeurRefusee, OSError):
                empreinte = None
            etats = {moteur.identifiant: moteur for moteur in self._moteurs.inventaire()}
            etat = etats.get(declaration.identifiant)
            if etat is not None and etat.versions:
                versions = dict(etat.versions)
        return metadonnees_moteur(
            declaration.identifiant,
            declaration.nom,
            factice=declaration.factice,
            empreinte_verrou=empreinte,
            versions=versions,
        )

    def _ouvrir_consignation(
        self, demande: DemandeExecution, travailleur: Travailleur, debut: float
    ) -> tuple[ConsignateurExecution | None, str | None]:
        """Crée la consignation de cette exécution, ou explique son impossibilité.

        Le dossier de résultat, `run.json` en état `running` et `run.log` sont
        créés ici, avant tout décodage : une exécution qui ne peut pas être
        consignée ne lance aucun moteur.
        """
        consignateur = ConsignateurExecution(
            self._donnees,
            demande,
            self._metadonnees_moteur(demande),
            debut=debut,
        )
        if not consignateur.ouvrir():
            # Aucun handle ne doit rester ouvert derrière une consignation refusée.
            consignateur.fermer()
            return None, (
                "enregistrement des résultats impossible : "
                f"{consignateur.erreur or 'stockage indisponible'}"
            )
        travailleur.journaliser(
            f"Résultats de l'exécution : {NOM_DOSSIER_RESULTATS}/"
            f"{consignateur.identifiant}."
        )
        return consignateur, None

    def _clore_consignation(
        self,
        consignateur: ConsignateurExecution,
        resultat: ResultatExecution,
        travailleur: Travailleur,
    ) -> ResultatExecution:
        """Écrit l'état final, puis rapporte identifiant et mesures au résultat.

        Une erreur d'écriture ici (disque plein) ne doit pas masquer l'issue
        réelle : `clore` tente malgré tout l'état final, en `failed` avec le
        motif retenu, l'exécution est close en échec et aucune exception ne
        remonte au créneau. Une erreur d'écriture du journal du moteur, elle, est
        seulement signalée : `run.log` n'est qu'une trace et les résultats
        restent exploitables.
        """
        mesures = consignateur.mesures
        if mesures.duree_operation_s is None:
            # Issue imprévue avant la fin mesurée : la durée va jusqu'à la clôture.
            mesures.duree_operation_s = time.perf_counter() - mesures.debut
        consignateur.clore(resultat)
        resultat = replace(
            resultat,
            identifiant_resultat=consignateur.identifiant,
            duree_operation_s=mesures.duree_operation_s,
            duree_processus_s=mesures.duree_processus_s,
        )
        if consignateur.erreur is not None:
            if consignateur.erreur != resultat.erreur:
                travailleur.journaliser(
                    f"Consignation des résultats en échec : {consignateur.erreur}"
                )
            if resultat.etat != ETAT_ECHOUEE:
                resultat = replace(
                    resultat, etat=ETAT_ECHOUEE, erreur=consignateur.erreur
                )
        if consignateur.erreur_journal is not None:
            travailleur.journaliser(
                f"Journal du moteur incomplet : {consignateur.erreur_journal}"
            )
        return resultat

    def _resultat(
        self,
        demande: DemandeExecution,
        *,
        factice: bool,
        audios: Sequence[ResultatAudio],
        etat: str,
        erreur: str | None = None,
        evenements: Sequence[Mapping[str, Any]] = (),
        parasites: int = 0,
        journal_moteur: Sequence[str] = (),
        code_sortie: int | None = None,
        pid: int | None = None,
        arret_demande: bool = False,
    ) -> ResultatExecution:
        """Construit un `ResultatExecution` complet, sans effet de bord."""
        return ResultatExecution(
            etat=etat,
            factice=factice,
            synthetique=demande.synthetique,
            moteur=demande.moteur,
            famille=demande.famille,
            modele_identifiant=demande.identifiant,
            threads_demandes=demande.threads,
            audios=tuple(audios),
            evenements=tuple(evenements),
            lignes_parasites=parasites,
            journal_moteur=tuple(journal_moteur),
            erreur=erreur,
            code_sortie=code_sortie,
            pid=pid,
            arret_demande=arret_demande,
        )

    def _resultat_avant_lancement(
        self, demande: DemandeExecution, erreur: str
    ) -> ResultatExecution:
        """Échec prévu avant tout lancement, avec tous les audios non traités."""
        factice = self._factice(demande)
        return self._resultat(
            demande,
            factice=factice,
            audios=self._audios_non_traites(demande, factice),
            etat=ETAT_ECHOUEE,
            erreur=erreur,
        )

    def _resultat_imprevu(
        self, demande: DemandeExecution, exception: BaseException
    ) -> ResultatExecution:
        """Résultat d'échec pour une exception non prévue, sans exposer de trace."""
        resultat = self._resultat_avant_lancement(
            demande,
            "exécution interrompue par une erreur interne : "
            f"{_message_erreur(exception)}",
        )
        return replace(resultat, arret_demande=self._arret_demande_actif())


def _heure_creation_processus(pid: int) -> tuple[float | None, str | None]:
    """Heure de création du processus moteur, brute, lue par le système.

    `psutil.Process(pid).create_time()` renvoie un horodatage epoch en secondes,
    conservé tel quel (flottant, sans troncature à la seconde) : c'est lui que la
    tâche 6.5 pourra confronter au PID enregistré, avec une tolérance. L'horloge
    du serveur, elle, donne `lance_a` ; les deux lectures peuvent différer de
    quelques dixièmes de seconde. Le processus peut déjà être mort (moteur très
    court, moteur factice) : la valeur et la source renvoyées valent alors `None`
    et l'appelant consigne l'absence d'heure système, avec `lance_a` comme
    référence (source `serveur`).
    """
    try:
        return psutil.Process(pid).create_time(), SOURCE_HEURE_PSUTIL
    except (psutil.Error, OSError, ValueError):
        return None, None


def _cle_evenement(evenement: Mapping[str, Any]) -> tuple[str, int | None]:
    """Clé d'unicité d'un événement : type normalisé et index d'audio éventuel.

    `audio` et `audio_erreur` partagent la même clé pour un même index : deux
    événements concurrents pour un audio n'en laissent donc passer qu'un.
    """
    type_evenement = evenement.get("type")
    if type_evenement in (TYPE_AUDIO, TYPE_AUDIO_ERREUR):
        return (TYPE_AUDIO, evenement.get("index"))
    return (type_evenement, None)


def _collecter_stderr(
    enfant: subprocess.Popen[str],
    journal: deque[str],
    consignateur: ConsignateurExecution,
) -> None:
    """Lit la sortie d'erreur du moteur et l'écrit intégralement dans `run.log`.

    Le résumé gardé en mémoire (`journal`, borné) sert aux messages et à la page
    d'opération ; le fichier, lui, n'est pas borné : 2000 lignes de trace ne
    suffisent pas à comprendre un échec d'installation de moteur. Une erreur
    d'écriture est retenue par la consignation et n'interrompt pas la lecture, le
    moteur ne devant jamais rester bloqué sur un tuyau plein.
    """
    flux = enfant.stderr
    if flux is None:
        return
    try:
        for brut in flux:
            ligne = brut.rstrip("\r\n")
            journal.append(ligne)
            consignateur.ecrire_journal(ligne)
    except (OSError, ValueError):
        # Tuyau fermé par le nettoyage : la collecte s'arrête sans erreur.
        return


def _journaliser_stderr(
    journal_moteur: Sequence[str], travailleur: Travailleur
) -> None:
    """Journalise un résumé de la sortie d'erreur, sans la recopier en entier."""
    if not journal_moteur:
        return
    travailleur.journaliser(
        f"Sortie d'erreur du moteur : {len(journal_moteur)} ligne(s) conservée(s) "
        "dans le résultat de l'exécution."
    )
    derniere = next(
        (ligne for ligne in reversed(journal_moteur) if ligne.strip()), None
    )
    if derniere is not None:
        travailleur.journaliser(
            f"Dernière ligne d'erreur du moteur : {_resume_ligne(derniere)}"
        )


def _audio_non_traite(
    index: int, nom: str, factice: bool, synthetique: bool
) -> ResultatAudio:
    """Audio jamais préparé, faute d'arrêt demandé avant son décodage."""
    return ResultatAudio(
        index=index,
        nom=nom,
        prepare=None,
        evenement=None,
        erreur=None,
        factice=factice,
        synthetique=synthetique,
    )


def _consigner_evenement(
    audios: list[ResultatAudio],
    indices_job: Sequence[int],
    evenement: Mapping[str, Any],
    consignateur: ConsignateurExecution,
) -> None:
    """Retient les mesures puis le résultat de l'audio concerné, aussitôt.

    Les mesures de l'événement sont consignées avant tout filtrage : celles du
    chargement sont donc persistées dès leur réception, et le pic mémoire de
    chaque audio est retenu avant l'écriture de son résultat. L'index d'un
    événement est sa position dans le job, qui exclut les audios dont le décodage
    a échoué : `indices_job` le ramène à la position dans la demande, qui fixe
    l'ordre de traitement, de consignation et de lecture par les pages de
    résultats. La consignation est faite ici, donc avant l'audio suivant, sans
    mécanisme d'abonnement générique.
    """
    consignateur.enregistrer_mesures(evenement)
    if evenement.get("type") not in (TYPE_AUDIO, TYPE_AUDIO_ERREUR):
        return
    position = evenement.get("index")
    if not _position_valide(position, len(indices_job)):
        return
    index = indices_job[position]
    if not 0 <= index < len(audios):
        return
    audio = _avec_evenement(audios[index], evenement)
    audios[index] = audio
    consignateur.enregistrer_audio(audio)


def _avec_evenement(
    audio: ResultatAudio, evenement: Mapping[str, Any]
) -> ResultatAudio:
    """Résultat d'un audio complété par son événement (texte ou erreur moteur)."""
    if evenement.get("type") == TYPE_AUDIO_ERREUR:
        return replace(audio, erreur=f"moteur : {evenement.get('erreur')}")
    return replace(audio, evenement=evenement)


def _motif_ligne_ignoree(
    evenement: Mapping[str, Any] | None,
    *,
    indices_job: Sequence[int],
    factice: bool,
    vus: set[tuple[str, int | None]],
) -> str | None:
    """Motif pour lequel une ligne n'est pas un événement exploitable, ou `None`.

    Une ligne non préfixée, illisible ou d'un type inconnu est déjà écartée par
    `analyser_ligne`. Sont écartés ici : un index d'audio hors du job, une
    provenance `factice` différente de la déclaration du moteur (qui rendrait
    une mesure simulée indiscernable d'une mesure réelle) et un événement déjà
    reçu (`vus`), dont seul le premier est conservé.
    """
    if evenement is None:
        return "ligne non conforme au protocole"
    if evenement.get("type") in (TYPE_AUDIO, TYPE_AUDIO_ERREUR):
        if not _position_valide(evenement.get("index"), len(indices_job)):
            return "index d'audio hors du job"
    if evenement.get("factice") is not factice:
        return "provenance incohérente avec la déclaration du moteur"
    if _cle_evenement(evenement) in vus:
        return "événement en double, premier reçu conservé"
    return None


def _position_valide(position: Any, taille: int) -> bool:
    """Vrai si `position` est un entier d'index utilisable dans `[0, taille[`."""
    return (
        isinstance(position, int)
        and not isinstance(position, bool)
        and 0 <= position < taille
    )


def _resume_ligne(ligne: str, limite: int = 200) -> str:
    """Tronque une ligne de sortie du moteur pour le journal."""
    texte = " ".join(ligne.split())
    return texte if len(texte) <= limite else texte[:limite] + "…"


def _message_erreur(erreur: BaseException) -> str:
    """Texte court d'une erreur, sans type vide ni message absent."""
    texte = str(erreur).strip()
    return texte if texte else type(erreur).__name__
