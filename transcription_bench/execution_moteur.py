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
6. **arrêt** à la demande de l'utilisateur : `terminate`, attente bornée puis
   `kill`, les résultats d'audios déjà reçus sont conservés et les audios
   restants sont signalés non traités. Après la demande d'arrêt, les lignes
   encore lues sont drainées sans être interprétées : la troncature est donc
   bornée au dernier événement reçu avant l'arrêt, de façon déterministe ;
7. **issue** : sortie non nulle, événement `fin` absent ou événement manquant
   pour un audio donnent un échec explicite (`ExecutionEchouee`), jamais un
   succès déduit d'un silence. Les audios sans résultat restent signalés non
   traités ;
8. **nettoyage** du cache décodé (suppression du dossier de travail) dans tous
   les cas, y compris après échec ou arrêt, mais seulement une fois le processus
   moteur réellement terminé.

Le processus est toujours attendu avant la fin du thread de fond : le créneau
reste donc occupé jusqu'à la fin **réelle** du processus moteur, même après un
arrêt, un plantage ou le dépassement du délai d'arrêt.

Ce module ne persiste aucun résultat : le stockage final (`run.json`,
`result.json`, `transcription.txt`, mesures serveur) relève de la tâche 6.4. Il
laisse à cet effet un `ResultatExecution` en mémoire, avec ses événements dans
l'ordre reçu : la tâche 6.4 y branchera sa propre consignation, audio par audio,
sans que ce module impose de format de fichier.

Métadonnées : chaque `ResultatExecution` et chaque `ResultatAudio` porte
`factice` et `synthetique`, en plus des champs de provenance `factice` et
`mesures_simulees` déjà présents dans chaque événement du runner.

Verrous : ce service n'utilise ni verrou du créneau ni verrou de stockage de
façon imbriquée. Son verrou interne protège l'état d'exécution (processus en
cours, drapeau d'arrêt, dernière issue) et n'est jamais tenu pendant un appel au
créneau (journal) ni pendant une E/S longue : l'ordre « verrou du créneau puis
verrou de stockage » du reste du programme n'est donc jamais inversé ici.

Limites assumées : le dossier de travail et les signaux décodés vivent sous
`data/cache/`. Après un arrêt brutal du serveur, ou si un processus insensible
à `kill` survit, ils peuvent subsister : la tâche 6.5 devra nettoyer ces restes,
car aucun autre code ne les supprime. La supervision des signaux du
serveur et l'arrêt du moteur au moment de l'arrêt normal du serveur relèvent de
la tâche 6.6. Aucune inférence réelle n'est possible ici pour les moteurs réels,
dont les familles ne sont pas qualifiées sur PC : seul le moteur factice est
exécutable, avec des textes et des mesures simulés, jamais représentatifs d'un
PC.
"""

from __future__ import annotations

import json
import os
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
)
from transcription_bench.operations import (
    OperationEchouee,
    OperationInterrompue,
    Travailleur,
)
from transcription_bench.paths import (
    NOM_DOSSIER_CACHE,
    NOM_DOSSIER_MODELES,
    ValeurRefusee,
    resoudre_dans_racine,
)

#: Version et format de signal du job, tenus égaux à ceux du runner par un test
#: (`engines.runner.VERSION_JOB`, `engines.runner.FORMAT_AUDIO`), sans importer
#: le runner dans le serveur.
VERSION_JOB = 1
FORMAT_AUDIO_BRUT = "float32le-16000-mono"
#: Type numpy écrit dans le fichier brut : `float32` little-endian (`<f4`).
TYPE_SIGNAL = "<f4"

NOM_FICHIER_JOB = "job.json"
PREFIXE_FICHIER_BRUT = "audio-"
SUFFIXE_FICHIER_BRUT = ".f32"
#: Sous-dossier de `data/` où vivent les dossiers de travail des exécutions.
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
    """Issue complète d'une exécution, en mémoire, destinée à la tâche 6.4.

    `evenements` conserve tous les événements interprétés, dans l'ordre reçu :
    c'est le journal que la tâche 6.4 persistera. `journal_moteur` contient la
    sortie d'erreur du moteur (borne aux dernières lignes). `pid` est celui du
    processus lancé, utile aux tâches 6.4 et 6.5. Les mesures serveur (durée de
    l'opération, durée du processus) ne sont pas prises ici : elles relèvent de
    la tâche 6.4.
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
    laisse pas de processus survivant quand le système coopère : `terminate`,
    attente bornée par sondage, puis `kill`.
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
        options: dict[str, Any] = {}
        if os.name == "nt":
            options["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
        else:
            options["start_new_session"] = True
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
        """Termine le processus : `terminate`, attente bornée, puis `kill`.

        Renvoie `True` si le processus est terminé (ou n'a jamais été lancé),
        `False` s'il survit au délai même après `kill`.
        """
        with self._verrou:
            self._arrete = True
            processus = self._processus
        if processus is None:
            return True
        if processus.poll() is not None:
            return True
        try:
            processus.terminate()
        except OSError:
            return True
        if self._attendre_sortie(processus):
            return True
        try:
            processus.kill()
        except OSError:
            return True
        return self._attendre_sortie(processus)

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
        self._derniere: ResultatExecution | None = None

    # -- état observable (routes, tests, tâches 6.4 à 6.6) -------------------

    def derniere_execution(self) -> ResultatExecution | None:
        """Dernière exécution close, ou `None` si aucune n'est terminée."""
        with self._verrou:
            return self._derniere

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

    def arreter_execution(self) -> str:
        """Demande l'arrêt de l'exécution active, sans dépendre d'un contexte Flask.

        Idempotent. Renvoie `ARRET_AUCUN` sans exécution active, `ARRET_DEMANDE`
        si l'arrêt a été demandé et le processus terminé (ou jamais lancé), et
        `ARRET_SURVIVANT` si le processus n'a pas pu être terminé, même après
        `kill`. Le verrou du service n'est pas tenu pendant la journalisation ni
        pendant la terminaison du processus. `reserver` a créé le processus
        moteur : une exécution active en a donc toujours un, même avant son
        démarrage effectif.
        """
        with self._verrou:
            if not self._active:
                return ARRET_AUCUN
            self._arret_demande = True
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
        pour un échec prévu (moteur mort, événements manquants) et
        `OperationInterrompue` après un arrêt de l'utilisateur, afin que le
        créneau enregistre l'issue ; le `ResultatExecution` reste disponible par
        `derniere_execution`.
        """
        processus = self._processus_reserve()
        resultat: ResultatExecution | None = None
        dossier: Path | None = None
        try:
            dossier = self._creer_dossier_travail()
            with self._verrou:
                self._travailleur = travailleur
            resultat = self._executer(demande, travailleur, dossier, processus)
        except ExecutionImpossible as exception:
            # Dossier de travail impossible : échec prévu, aucun processus lancé.
            resultat = self._resultat_avant_lancement(demande, _message_erreur(exception))
        except BaseException as exception:  # issue imprévue : jamais de résultat ambigu
            resultat = self._resultat_imprevu(demande, exception)
            raise
        finally:
            # Aucun survivant, quels que soient le chemin et l'issue : le dossier
            # de travail n'est supprimé et l'état libéré qu'après la fin réelle
            # du processus.
            self._clore_processus(processus, travailleur)
            processus.fermer()
            if dossier is not None:
                shutil.rmtree(dossier, ignore_errors=True)
            self._liberer_execution(resultat)
        self._journaliser_issue(resultat, travailleur)
        if resultat.etat == ETAT_ECHOUEE:
            raise ExecutionEchouee(resultat.erreur or "exécution en échec")
        if resultat.etat == ETAT_INTERROMPUE:
            raise OperationInterrompue(
                "exécution interrompue à la demande de l'utilisateur"
            )

    def _executer(
        self,
        demande: DemandeExecution,
        travailleur: Travailleur,
        dossier: Path,
        processus: ProcessusMoteur,
    ) -> ResultatExecution:
        """Prépare, lance et collecte l'exécution ; ne lève pas pour un échec prévu."""
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
        audios = self._preparer_audios(demande, travailleur, dossier, factice)
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
        try:
            enfant = processus.lancer(
                self._construire_commande(interpreteur, chemin_job),
                environ=environnement_moteur(),
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
        travailleur.journaliser(f"Processus moteur lancé (PID {enfant.pid}).")
        # File locale de cette exécution : aucune ligne d'une exécution précédente
        # ne peut s'y mêler, et sa borne reste valable même si le tuyau déborde.
        stderr_moteur: deque[str] = deque(maxlen=NOMBRE_LIGNES_STDERR_MAX)
        fil_stderr = threading.Thread(
            target=_collecter_stderr,
            args=(enfant, stderr_moteur),
            name="transcription-bench-moteur-stderr",
            daemon=True,
        )
        fil_stderr.start()
        evenements, parasites = self._collecter_evenements(
            enfant, travailleur, demande, indices_job, factice
        )
        code_sortie = enfant.wait()
        fil_stderr.join(self._delai_arret)
        arret = self._arret_demande_actif()
        resultats = _appliquer_evenements(audios, evenements, indices_job)
        etat, motif = evaluer_issue(
            code_sortie=code_sortie,
            arret_demande=arret,
            evenements=evenements,
            indices_job=indices_job,
            nb_audios=len(demande.audios),
        )
        journal_moteur = tuple(stderr_moteur)
        _journaliser_stderr(journal_moteur, travailleur)
        return self._resultat(
            demande,
            factice=factice,
            audios=resultats,
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
    ) -> list[ResultatAudio]:
        """Décode chaque audio et écrit son signal brut dès qu'il est décodé.

        Une erreur sur un audio (décodage, écriture) devient une erreur propre à
        cet audio : les suivants sont traités normalement. Une demande d'arrêt
        interrompt la préparation sans lancer le moteur.
        """
        resultats: list[ResultatAudio] = []
        total = len(demande.audios)
        for index, nom in enumerate(demande.audios):
            if self._arret_demande_actif():
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
        """Emplacement du modèle sous `data/models`, contrôlé ; repris du docstring
        du module pour le modèle synthétique : il n'existe pas et n'est pas lu.
        """
        dossier_moteur = resoudre_dans_racine(
            self._donnees / NOM_DOSSIER_MODELES, demande.moteur
        )
        return resoudre_dans_racine(
            dossier_moteur, f"{demande.cle}/{NOM_DOSSIER_FICHIERS}"
        )

    # -- collecte ------------------------------------------------------------

    def _collecter_evenements(
        self,
        enfant: subprocess.Popen[str],
        travailleur: Travailleur,
        demande: DemandeExecution,
        indices_job: Sequence[int],
        factice: bool,
    ) -> tuple[list[Mapping[str, Any]], int]:
        """Lit la sortie standard, n'interprète que les événements du protocole.

        Toute autre ligne (sortie parasite, événement illisible, index hors du
        job, provenance `factice` incohérente avec la déclaration, événement en
        double) est comptée et journalisée sans provoquer d'échec. Après une
        demande d'arrêt, les lignes suivantes sont drainées sans être
        interprétées.
        """
        evenements: list[Mapping[str, Any]] = []
        parasites = 0
        vus: set[tuple[str, int | None]] = set()
        flux = enfant.stdout
        if flux is None:
            return evenements, parasites
        for brut in flux:
            if self._arret_demande_actif():
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

    def _arret_demande_actif(self) -> bool:
        with self._verrou:
            return self._arret_demande

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


def _cle_evenement(evenement: Mapping[str, Any]) -> tuple[str, int | None]:
    """Clé d'unicité d'un événement : type normalisé et index d'audio éventuel.

    `audio` et `audio_erreur` partagent la même clé pour un même index : deux
    événements concurrents pour un audio n'en laissent donc passer qu'un.
    """
    type_evenement = evenement.get("type")
    if type_evenement in (TYPE_AUDIO, TYPE_AUDIO_ERREUR):
        return (TYPE_AUDIO, evenement.get("index"))
    return (type_evenement, None)


def _collecter_stderr(enfant: subprocess.Popen[str], journal: deque[str]) -> None:
    """Remplit la file locale de sortie d'erreur du moteur, bornée à sa taille."""
    flux = enfant.stderr
    if flux is None:
        return
    try:
        for brut in flux:
            journal.append(brut.rstrip("\r\n"))
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


def _appliquer_evenements(
    audios: Sequence[ResultatAudio],
    evenements: Sequence[Mapping[str, Any]],
    indices_job: Sequence[int],
) -> list[ResultatAudio]:
    """Rattache à chaque audio son événement reçu, s'il y en a un.

    L'index d'un événement est sa position dans le job, qui exclut les audios
    dont le décodage a échoué : `indices_job` le ramène à la position dans la
    demande, qui fixe l'ordre de traitement et de consignation.
    """
    par_index: dict[int, Mapping[str, Any]] = {}
    for evenement in evenements:
        if evenement.get("type") not in (TYPE_AUDIO, TYPE_AUDIO_ERREUR):
            continue
        position = evenement.get("index")
        if _position_valide(position, len(indices_job)):
            par_index[indices_job[position]] = evenement
    resultats: list[ResultatAudio] = []
    for audio in audios:
        evenement = par_index.get(audio.index)
        if evenement is None:
            resultats.append(audio)
        elif evenement.get("type") == TYPE_AUDIO_ERREUR:
            resultats.append(
                replace(audio, erreur=f"moteur : {evenement.get('erreur')}")
            )
        else:
            resultats.append(replace(audio, evenement=evenement))
    return resultats


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
