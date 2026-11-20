"""Lancement supervisé d'une extraction dans le créneau unique (tâche 3.4, D5 à D7).

Ce service consomme une `ExtractionRequest` validée par `transcription_bench.extractions`
et exécute une extraction complète, dans le thread de fond du créneau :

1. **dossier de travail** sous `data/cache/execution-*`, créé au lancement et
   supprimé à la fin, y compris après échec, arrêt ou récupération ; un dossier
   de cache qui serait un lien symbolique refuse l'extraction avant toute
   écriture, le job contenant les textes des sources ;
2. **consignation à l'admission** (`resultats_extraction`) : dossier, `run.json`
   en cours, `run.log`, `grille.md`, `schema.json`, `consignes.json` et
   `source.txt` de chaque source, avant tout lancement de moteur ;
3. **`job.json`** de travail, au format de `engines/runner_extraction.py`. Il
   contient les textes des sources : il ne vit que sous `data/cache/` et il est
   supprimé avec le dossier de travail. Rien de ce qu'il contient n'est journalisé ;
4. **lancement** du runner d'extraction par `extraction_runner_command`, avec
   `environnement_moteur()` (mode hors ligne forcé) et dans son propre groupe de
   processus, comme le runner de transcription ;
5. **collecte** de la sortie standard : seuls les événements `chargement`,
   `extraction`, `extraction_erreur` et `fin` sont retenus. Tout autre type
   (dont `audio`), tout événement incohérent et tout doublon est refusé et
   résumé dans `run.log` par son type et son motif, jamais par la ligne brute ;
6. **publication incrémentale** : chaque événement de source est publié aussitôt
   (`sortie_brute.txt`, `extraction.json` si conforme, puis `result.json` en
   dernier) ; `chargement` et `fin` mettent à jour les mesures du run ;
7. **issue** : arrêt demandé → `interrompue` (source en cours non publiée, donc
   non traitée) ; échec du chargement ou sortie du runner en erreur sans
   événement de chargement → `echouee` avec le motif lu sur la sortie d'erreur ;
   fin absente ou source sans événement → `echouee` ; sinon `terminee`, même si
   des sources sont non conformes ou en erreur (le code de sortie de la commande
   le distingue, tâche 3.5).

Supervision et arrêt : `ProcessusMoteur` (groupe de processus, `SIGTERM` puis
`SIGKILL`, attente bornée) est réutilisé tel quel ; `arreter_execution` est la
même opération que pour la transcription, appelée par le signal de l'interface
(tâche 3.5). Le créneau reste occupé jusqu'à la fin réelle du processus. La
réservation (`reserver`, `annuler_reservation`) suit l'ordre de
`execution_launch` : elle précède l'admission dans le créneau.

Ce module n'importe aucune bibliothèque de moteur : seul le processus du runner
d'extraction en charge, dans son propre interpréteur.
"""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
import threading
import time
from collections import deque
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

from engines.declarations import TASK_EXTRACTION, DeclarationAdaptateur
from engines.hors_ligne import extraction_runner_command, environnement_moteur
from engines.protocole import (
    MARQUEUR_EVENEMENT,
    TYPE_CHARGEMENT,
    TYPE_EXTRACTION,
    TYPE_EXTRACTION_ERREUR,
    TYPE_FIN,
    TYPES_EVENEMENTS,
    analyser_ligne,
)
from engines.registre import MoteurInconnu, RegistreMoteurs
from transcription_bench.execution_moteur import (
    ARRET_AUCUN,
    ARRET_DEMANDE,
    ARRET_SURVIVANT,
    DELAI_ARRET_MOTEUR,
    ETAT_ECHOUEE,
    ETAT_INTERROMPUE,
    ETAT_TERMINEE,
    NOM_FICHIER_JOB,
    NOMBRE_LIGNES_PARASITES_JOURNALISEES,
    NOMBRE_LIGNES_STDERR_MAX,
    PREFIXE_DOSSIER_TRAVAIL,
    VERSION_JOB,
    ExecutionEchouee,
    ExecutionImpossible,
    ProcessusMoteur,
    collecter_stderr,
    heure_creation_processus,
    engine_interpreter,
    journaliser_stderr,
    message_erreur,
    resume_ligne,
)
from transcription_bench.executions import ModelePropose
from transcription_bench.extractions import ExtractionRequest
from transcription_bench.gestion_modeles import NOM_DOSSIER_FICHIERS
from transcription_bench.moteurs import (
    InstallationIndisponible,
    InstallationMoteurs,
    empreinte_fichier,
)
from transcription_bench.operations import (
    OperationInterrompue,
    Travailleur,
    horodatage_iso,
)
from transcription_bench.paths import (
    NOM_DOSSIER_CACHE,
    NOM_DOSSIER_EXTRACTIONS,
    NOM_DOSSIER_MODELES,
    ValeurRefusee,
    resoudre_dans_racine,
)
from transcription_bench.resultats import SOURCE_HEURE_SERVEUR, metadonnees_moteur
from transcription_bench.resultats_extraction import ExtractionRecorder

#: Types d'événements acceptés pour une extraction (protocole D5). Les types
#: `audio` et `audio_erreur` sont hors tâche et refusés par ce service.
EXTRACTION_EVENT_TYPES = (TYPE_CHARGEMENT, TYPE_EXTRACTION, TYPE_EXTRACTION_ERREUR, TYPE_FIN)
#: Types qui désignent une source : leur index est la position dans l'extraction.
SOURCE_EVENT_TYPES = (TYPE_EXTRACTION, TYPE_EXTRACTION_ERREUR)
#: Cache JIT du moteur, sous `data/` (même règle que la transcription, design D4).
NUMBA_CACHE_DIR_NAME = "cache-numba"
#: Motif fixe d'un dossier de travail resté en place : il contient le job et les textes.
MOTIF_DOSSIER_CONSERVE = (
    "dossier de travail non supprimé : il contient le job et les textes sources"
)
#: Motif fixe d'un dossier de cache lié : le job contient les textes des
#: sources, il n'est jamais écrit dans la cible d'un lien symbolique.
MOTIF_CACHE_LIE = (
    "dossier de travail impossible : le dossier de cache est un lien "
    "symbolique, il n'est pas suivi"
)


@dataclass(frozen=True)
class ExtractionResult:
    """Issue complète d'une extraction, en mémoire, et référence de sa consignation.

    `etat` suit les états internes du service (`terminee`, `interrompue`,
    `echouee`) ; la consignation les traduit en état persisté. Les états des
    sources vivent dans le dossier de l'extraction : `summary` en donne le compte
    pour le journal de l'opération, et `sources` (rang, nom, état, motif, dans
    l'ordre de la demande) le résumé par source de la commande (tâche 3.5). Vide
    si la consignation n'a pas été admise.
    """

    etat: str
    factice: bool
    moteur: str
    famille: str
    modele_identifiant: str
    nombre_sources: int
    erreur: str | None = None
    code_sortie: int | None = None
    pid: int | None = None
    arret_demande: bool = False
    identifiant_resultat: str | None = None
    duree_operation_s: float | None = None
    duree_processus_s: float | None = None
    summary: Mapping[str, int] = field(default_factory=dict)
    sources: tuple[Mapping[str, Any], ...] = ()
    # D7, arbitrage assumé : un dossier de travail que la purge n'a pas pu
    # supprimer est SIGNALÉ (journal `run.log`, ligne de résultat de la commande)
    # mais jamais puni — l'état reste celui des sources (`terminee`) et le code
    # de sortie reste le leur (0 si conformes, 3 après signal) : un échec de
    # purge ne doit ni masquer un résultat sain, ni faire croire à un échec.
    dossier_travail_conserve: bool = False


def evaluate_extraction_outcome(
    *,
    code_sortie: int,
    arret_demande: bool,
    evenements: Sequence[Mapping[str, Any]],
    nombre_sources: int,
    motif_moteur: str | None,
) -> tuple[str, str | None]:
    """Décide l'état final et son motif, à partir des seuls faits observés.

    Règles, dans cet ordre : un arrêt demandé donne `interrompue` quel que soit le
    code ; l'absence d'événement de chargement est un échec du chargement, avec
    le motif lu sur la sortie d'erreur (`motif_moteur`) ; un code de sortie non
    nul, puis l'absence de `fin`, puis une source sans événement sont des échecs.
    Une source non conforme ou en erreur n'est pas un échec de l'extraction.
    """
    if arret_demande:
        return ETAT_INTERROMPUE, None
    if not any(evenement.get("type") == TYPE_CHARGEMENT for evenement in evenements):
        return (
            ETAT_ECHOUEE,
            motif_moteur or "chargement du modèle absent de la sortie du moteur",
        )
    if code_sortie != 0:
        return (
            ETAT_ECHOUEE,
            f"le processus moteur s'est terminé avec le code {code_sortie}",
        )
    if not any(evenement.get("type") == TYPE_FIN for evenement in evenements):
        return ETAT_ECHOUEE, "événement de fin absent de la sortie du moteur"
    traitees = {
        evenement.get("index")
        for evenement in evenements
        if evenement.get("type") in SOURCE_EVENT_TYPES
    }
    manquantes = [rang for rang in range(nombre_sources) if rang not in traitees]
    if manquantes:
        positions = ", ".join(str(rang + 1) for rang in manquantes)
        return (
            ETAT_ECHOUEE,
            f"événements de source manquants pour la source n° {positions} "
            f"(extraction de {nombre_sources} source(s))",
        )
    return ETAT_TERMINEE, None


def line_rejection_reason(
    ligne: str,
    evenement: Mapping[str, Any] | None,
    *,
    factice: bool,
    noms_sources: Sequence[str],
    vus: set[tuple[str, int | None]],
    chargement_recu: bool,
    fin_recue: bool,
) -> str | None:
    """Motif pour lequel une ligne du moteur n'est pas retenue, ou `None`.

    Une ligne refusée par le protocole n'est jamais citée : seuls son type (s'il
    appartient à l'ensemble fixe du protocole) et un motif fixe sont rendus. Un
    événement valide est refusé s'il est hors tâche (`audio`), de provenance
    incohérente, en double, hors ordre (avant le chargement, après la fin) ou
    désigne une source inconnue ou de nom différent de l'extraction.
    """
    if evenement is None:
        return _non_protocol_reason(ligne)
    type_evenement = evenement.get("type")
    if type_evenement not in EXTRACTION_EVENT_TYPES:
        return f"type hors tâche d'extraction : {type_evenement}"
    if evenement.get("factice") is not factice:
        return "provenance incohérente avec la déclaration du moteur"
    if fin_recue:
        return "événement reçu après la fin du moteur"
    if type_evenement == TYPE_CHARGEMENT:
        if chargement_recu:
            return "chargement en double, premier reçu conservé"
        return None
    if not chargement_recu:
        return f"{type_evenement} reçu avant le chargement"
    if type_evenement == TYPE_FIN:
        return None
    index = evenement.get("index")
    if not isinstance(index, int) or not 0 <= index < len(noms_sources):
        return "index de source hors de l'extraction"
    if evenement.get("nom") != noms_sources[index]:
        return "nom de source incohérent avec l'extraction"
    if ("source", index) in vus:
        return "source déjà traitée, premier événement conservé"
    return None


def _non_protocol_reason(ligne: str) -> str:
    """Motif fixe d'une ligne refusée par `analyser_ligne`, sans recopie de son contenu."""
    if not ligne.startswith(MARQUEUR_EVENEMENT):
        return "sortie hors protocole"
    try:
        # Mêmes exceptions que `analyser_ligne` : un entier démesuré lève
        # `ValueError` (pas seulement `JSONDecodeError`), une clé non hachable
        # `TypeError`, un JSON trop profondément imbriqué `RecursionError` —
        # la ligne est illisible, jamais une exception.
        charge = json.loads(ligne[len(MARQUEUR_EVENEMENT) :].strip())
    except (ValueError, TypeError, RecursionError):
        return "événement illisible (JSON invalide)"
    if not isinstance(charge, dict):
        return "événement qui n'est pas un objet"
    type_evenement = charge.get("type")
    if type_evenement not in TYPES_EVENEMENTS:
        return "type d'événement inconnu"
    if type_evenement not in EXTRACTION_EVENT_TYPES:
        return f"type hors tâche d'extraction : {type_evenement}"
    return f"événement {type_evenement} non conforme au protocole"


def _journaliser_dossier_conserve(
    consignateur: ExtractionRecorder | None, travailleur: Travailleur
) -> None:
    """Signale un dossier de travail resté en place, dans `run.log` si possible.

    Le motif est fixe : ni le chemin ni le contenu du job ne sont recopiés. Le
    journal du moteur est déjà fermé à cet instant : la ligne passe par
    `ecrire_notice`, qui ajoute au fichier tant que l'extraction n'est pas
    close ; sans consignation ou si cette écriture échoue, elle va au journal
    de l'opération.
    """
    if consignateur is None or not consignateur.ecrire_notice(MOTIF_DOSSIER_CONSERVE):
        travailleur.journaliser(MOTIF_DOSSIER_CONSERVE)


def extraction_model_path(donnees: Path, modele: ModelePropose) -> Path:
    """Emplacement du modèle sous `data/models`, contrôlé et confiné.

    Un modèle GGUF renvoie le **fichier** retenu, qui doit exister. Le modèle
    synthétique du moteur factice n'a pas de fichier et n'est pas lu : le runner
    exige seulement un chemin non vide.
    """
    dossier_moteur = resoudre_dans_racine(donnees / NOM_DOSSIER_MODELES, modele.moteur)
    dossier_fichiers = resoudre_dans_racine(
        dossier_moteur, f"{modele.cle}/{NOM_DOSSIER_FICHIERS}"
    )
    if not modele.fichier_gguf:
        return dossier_fichiers
    fichier = resoudre_dans_racine(dossier_fichiers, modele.fichier_gguf)
    if not fichier.is_file():
        raise ValeurRefusee(f"fichier GGUF introuvable : {modele.fichier_gguf!r}")
    return fichier


def extraction_engine_metadata(
    registre: RegistreMoteurs, moteurs: InstallationMoteurs, identifiant: str
) -> dict[str, Any]:
    """Identité du moteur d'extraction, verrou et versions lues, sans supposition."""
    try:
        declaration: DeclarationAdaptateur = registre.obtenir(identifiant)
    except MoteurInconnu:
        return metadonnees_moteur(identifiant, identifiant, factice=False)
    empreinte: str | None = None
    versions: dict[str, str | None] | None = None
    if not declaration.factice:
        try:
            empreinte = empreinte_fichier(moteurs.chemin_verrou(declaration))
        except (InstallationIndisponible, ValeurRefusee, OSError):
            empreinte = None
        etats = {etat.identifiant: etat for etat in moteurs.inventaire()}
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


class ExtractionExecution:
    """Prépare, lance, supervise et clôt une extraction dans le créneau.

    Construit une fois, sans aucune E/S. `reserver` puis `lancer` s'exécutent
    dans le thread de fond du créneau. Les coutures (`construire_commande`,
    `interpreteur_serveur`, `racine_temporaire`, `delai_arret`) servent aux tests.
    """

    def __init__(
        self,
        dossier_data: Path | str,
        registre: RegistreMoteurs,
        moteurs: InstallationMoteurs,
        *,
        construire_commande: Callable[[str | Path, str | Path], list[str]] = (
            extraction_runner_command
        ),
        interpreteur_serveur: str | Path | None = None,
        racine_temporaire: Path | str | None = None,
        delai_arret: float = DELAI_ARRET_MOTEUR,
    ) -> None:
        self._donnees = Path(dossier_data)
        self._registre = registre
        self._moteurs = moteurs
        self._construire_commande = construire_commande
        self._interpreteur_serveur = (
            sys.executable if interpreteur_serveur is None else str(interpreteur_serveur)
        )
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
        self._derniere: ExtractionResult | None = None
        self._resultat_publie: tuple[int, str] | None = None

    # -- état observable -----------------------------------------------------

    def derniere_execution(self) -> ExtractionResult | None:
        """Dernière extraction close, ou `None` si aucune n'est terminée."""
        with self._verrou:
            return self._derniere

    def identifiant_resultat(self, generation: int | None) -> str | None:
        """Identifiant du dossier d'extraction publié pour l'opération `generation`."""
        with self._verrou:
            publie = self._resultat_publie
        if publie is None or generation is None:
            return None
        generation_publiee, identifiant = publie
        return identifiant if generation_publiee == generation else None

    def en_cours(self) -> bool:
        """Vrai si une extraction prépare, exécute ou collecte encore son moteur."""
        with self._verrou:
            return self._active

    def pid_actif(self) -> int | None:
        """PID du processus moteur courant, ou `None`."""
        with self._verrou:
            processus = self._processus_moteur
        return None if processus is None else processus.pid

    def verifier_lancable(self, demande: ExtractionRequest) -> None:
        """Revalide que le moteur, son interpréteur et le dossier de travail sont disponibles.

        Lève `ExecutionImpossible` sans effet de bord et sans lancer de
        processus : un dossier de cache lié refuse la demande avant toute
        réservation, le job qui contient les textes n'étant jamais écrit dans
        la cible d'un lien.
        """
        self._refuse_linked_work_root()
        self._interpreter(demande)

    def arreter_execution(self, *, arret_serveur: bool = False) -> str:
        """Demande l'arrêt de l'extraction active ; idempotent.

        Même contrat que `ExecutionMoteur.arreter_execution` : renvoie
        `ARRET_AUCUN`, `ARRET_DEMANDE` ou `ARRET_SURVIVANT`.
        """
        with self._verrou:
            if not self._active:
                return ARRET_AUCUN
            self._arret_demande = True
            self._arret_serveur = self._arret_serveur or arret_serveur
            processus = self._processus_moteur
            travailleur = self._travailleur
        if processus is None:
            return ARRET_DEMANDE
        if travailleur is not None:
            travailleur.journaliser(
                "Arrêt de l'extraction demandé : terminaison du processus moteur."
            )
        return ARRET_DEMANDE if processus.arreter() else ARRET_SURVIVANT

    def reserver(self) -> None:
        """Réserve l'extraction avant son admission dans le créneau.

        Lève `ExecutionImpossible` si une extraction est déjà réservée ou active.
        """
        with self._verrou:
            if self._active:
                raise ExecutionImpossible("une exécution est déjà active")
            self._active = True
            self._arret_demande = False
            self._arret_serveur = False
            self._processus_moteur = ProcessusMoteur(delai_arret=self._delai_arret)

    def annuler_reservation(self) -> None:
        """Libère une réservation que le créneau n'a pas admise ; la dernière issue reste."""
        with self._verrou:
            self._active = False
            self._processus_moteur = None
            self._travailleur = None

    # -- thread de fond du créneau ------------------------------------------

    def lancer(self, demande: ExtractionRequest, travailleur: Travailleur) -> None:
        """Exécute une extraction validée dans le thread de fond du créneau.

        Lève `ExecutionEchouee` pour un échec prévu et `OperationInterrompue` après
        un arrêt demandé par l'utilisateur. Un arrêt du serveur n'est pas une
        demande de l'utilisateur : le créneau, déjà à l'arrêt, en consigne le motif.
        """
        processus = self._reserved_process()
        resultat: ExtractionResult | None = None
        dossier: Path | None = None
        consignateur: ExtractionRecorder | None = None
        debut_operation = time.perf_counter()
        try:
            dossier = self._create_work_dir()
            with self._verrou:
                self._travailleur = travailleur
            consignateur, erreur_stockage = self._open_record(
                demande, travailleur, debut_operation
            )
            if consignateur is None:
                resultat = self._result_before_launch(demande, erreur_stockage or "")
            else:
                # L'identifiant est publié dès l'admission : le suivi peut y renvoyer
                # avant la clôture, sans emprunter celui d'une opération antérieure.
                self._publish_result(travailleur.generation, consignateur.identifiant)
                resultat = self._execute(demande, travailleur, dossier, processus, consignateur)
        except ExecutionImpossible as exception:
            resultat = self._result_before_launch(demande, message_erreur(exception))
        except BaseException as exception:  # issue imprévue : jamais de résultat ambigu
            resultat = self._result_unexpected(demande, exception)
            raise
        finally:
            # Aucun survivant : le dossier de travail (et le job qui contient les
            # textes) n'est supprimé qu'une fois le processus réellement terminé.
            self._close_process(processus, travailleur)
            processus.fermer()
            travail_conserve = False
            if dossier is not None:
                shutil.rmtree(dossier, ignore_errors=True)
                travail_conserve = dossier.exists()
                if travail_conserve:
                    _journaliser_dossier_conserve(consignateur, travailleur)
            if consignateur is not None:
                consignateur.fermer()
                try:
                    resultat = self._finalize_record(consignateur, resultat, travailleur)
                except Exception as erreur:  # la libération ne doit jamais manquer
                    travailleur.journaliser(
                        f"Clôture de l'extraction impossible : {message_erreur(erreur)}"
                    )
                    resultat = replace(
                        resultat,
                        etat=ETAT_ECHOUEE,
                        erreur=f"clôture de l'extraction impossible : {message_erreur(erreur)}",
                    )
            if travail_conserve and resultat is not None:
                # Arbitrage D7 (documenté sur `ExtractionResult`) : le reste est
                # porté par le résultat pour la ligne finale de la commande, sans
                # changer l'état ni le code de sortie.
                resultat = replace(resultat, dossier_travail_conserve=True)
            self._release(resultat)
        self._log_outcome(resultat, travailleur)
        if resultat.etat == ETAT_ECHOUEE:
            raise ExecutionEchouee(resultat.erreur or "extraction en échec")
        if resultat.etat == ETAT_INTERROMPUE:
            if self._server_stop_requested():
                return
            raise OperationInterrompue(
                "extraction interrompue à la demande de l'utilisateur"
            )

    def _execute(
        self,
        demande: ExtractionRequest,
        travailleur: Travailleur,
        dossier: Path,
        processus: ProcessusMoteur,
        consignateur: ExtractionRecorder,
    ) -> ExtractionResult:
        """Lance, collecte et publie ; ne lève pas pour un échec prévu."""
        measures = consignateur.measures
        factice = self._factice(demande)
        try:
            interpreteur = self._interpreter(demande)
        except ExecutionImpossible as erreur:
            return self._result(demande, factice=factice, etat=ETAT_ECHOUEE, erreur=str(erreur))
        travailleur.journaliser(
            f"Préparation de l'extraction : {len(demande.sources)} source(s), moteur "
            f"{demande.moteur}, famille {demande.modele.famille}, "
            f"{demande.threads} thread(s) demandé(s)"
            + (" (modèle synthétique, textes et mesures simulés)." if demande.synthetique else ".")
        )
        if self._stop_requested():
            travailleur.journaliser(
                "Arrêt demandé avant le lancement du moteur : aucun processus n'est démarré."
            )
            return self._result(demande, factice=factice, etat=ETAT_INTERROMPUE, arret_demande=True)
        chemin_job = dossier / NOM_FICHIER_JOB
        try:
            self._write_job(demande, chemin_job)
        except (OSError, ValeurRefusee) as erreur:
            return self._result(
                demande,
                factice=factice,
                etat=ETAT_ECHOUEE,
                erreur=f"préparation du job impossible : {message_erreur(erreur)}",
            )
        lance_a = horodatage_iso()
        debut_processus = time.perf_counter()
        try:
            enfant = processus.lancer(
                self._construire_commande(interpreteur, chemin_job),
                environ=environnement_moteur(
                    dossier_cache_numba=self._donnees / NUMBA_CACHE_DIR_NAME
                ),
                dossier=dossier,
            )
        except (OSError, ExecutionImpossible) as erreur:
            arret = self._stop_requested()
            return self._result(
                demande,
                factice=factice,
                etat=ETAT_INTERROMPUE if arret else ETAT_ECHOUEE,
                erreur=None if arret else message_erreur(erreur),
                arret_demande=arret,
            )
        heure_creation, source_heure = heure_creation_processus(enfant.pid)
        if not consignateur.enregistrer_processus(
            pid=enfant.pid,
            heure_creation=heure_creation,
            source=source_heure or SOURCE_HEURE_SERVEUR,
            lance_a=lance_a,
        ):
            # Sans PID persisté, la récupération ne retrouverait pas ce processus.
            if processus.arreter():
                measures.duree_processus_s = time.perf_counter() - debut_processus
            measures.duree_operation_s = time.perf_counter() - measures.debut
            travailleur.journaliser(
                "PID du processus moteur impossible à consigner : moteur arrêté, "
                "extraction en échec."
            )
            return self._result(
                demande,
                factice=factice,
                etat=ETAT_ECHOUEE,
                erreur=consignateur.erreur or "PID du processus moteur impossible à consigner",
                code_sortie=enfant.poll(),
                pid=enfant.pid,
            )
        travailleur.journaliser(f"Processus moteur lancé (PID {enfant.pid}).")
        stderr_moteur: deque[str] = deque(maxlen=NOMBRE_LIGNES_STDERR_MAX)
        fil_stderr = threading.Thread(
            target=collecter_stderr,
            args=(enfant, stderr_moteur, consignateur),
            name="transcription-bench-extraction-stderr",
            daemon=True,
        )
        fil_stderr.start()
        evenements, parasites = self._collect(
            enfant, processus, travailleur, demande, factice, consignateur
        )
        code_sortie = enfant.wait()
        measures.duree_processus_s = time.perf_counter() - debut_processus
        fil_stderr.join(self._delai_arret)
        consignateur.fermer()
        arret = self._stop_requested()
        journal_moteur = tuple(stderr_moteur.copy())
        etat, motif = evaluate_extraction_outcome(
            code_sortie=code_sortie,
            arret_demande=arret,
            evenements=evenements,
            nombre_sources=len(demande.sources),
            motif_moteur=_last_reason(journal_moteur),
        )
        if consignateur.erreur is not None:
            etat, motif = ETAT_ECHOUEE, consignateur.erreur
        measures.duree_operation_s = time.perf_counter() - measures.debut
        journaliser_stderr(journal_moteur, travailleur)
        if parasites:
            travailleur.journaliser(
                f"{parasites} ligne(s) du moteur ignorée(s) : motifs consignés dans run.log."
            )
        return self._result(
            demande,
            factice=factice,
            etat=etat,
            erreur=motif,
            code_sortie=code_sortie,
            pid=enfant.pid,
            arret_demande=arret,
        )

    # -- collecte ------------------------------------------------------------

    def _collect(
        self,
        enfant: Any,
        processus: ProcessusMoteur,
        travailleur: Travailleur,
        demande: ExtractionRequest,
        factice: bool,
        consignateur: ExtractionRecorder,
    ) -> tuple[list[Mapping[str, Any]], int]:
        """Lit la sortie standard, retient les événements valides, publie aussitôt.

        Après une demande d'arrêt, les lignes restantes sont drainées sans être
        interprétées. Une erreur d'écriture arrête le moteur ; les publications
        déjà faites restent valides.
        """
        evenements: list[Mapping[str, Any]] = []
        parasites = 0
        ecriture_impossible = False
        vus: set[tuple[str, int | None]] = set()
        chargement_recu = False
        fin_recue = False
        noms = [source.nom for source in demande.sources]
        flux = enfant.stdout
        if flux is None:
            return evenements, parasites
        for brut in flux:
            if ecriture_impossible or self._stop_requested():
                continue
            ligne = brut.rstrip("\r\n")
            evenement = analyser_ligne(ligne)
            motif = line_rejection_reason(
                ligne,
                evenement,
                factice=factice,
                noms_sources=noms,
                vus=vus,
                chargement_recu=chargement_recu,
                fin_recue=fin_recue,
            )
            if motif is not None:
                parasites += 1
                if parasites <= NOMBRE_LIGNES_PARASITES_JOURNALISEES:
                    consignateur.ecrire_journal(f"Ligne du moteur ignorée : {motif}.")
                continue
            assert evenement is not None  # garanti par `line_rejection_reason`
            type_evenement = evenement["type"]
            if type_evenement == TYPE_CHARGEMENT:
                chargement_recu = True
            elif type_evenement == TYPE_FIN:
                fin_recue = True
            else:
                vus.add(("source", evenement["index"]))
            evenements.append(evenement)
            travailleur.journaliser(_event_summary(evenement))
            consignateur.record_event(evenement)
            if consignateur.erreur is not None:
                ecriture_impossible = True
                processus.arreter()
        return evenements, parasites

    # -- préparation ---------------------------------------------------------

    def _write_job(self, demande: ExtractionRequest, chemin: Path) -> None:
        """Écrit `job.json` au format de `engines/runner_extraction.py`.

        Le fichier contient les textes des sources : il ne vit que dans le dossier
        de travail, supprimé à la fin de l'extraction.
        """
        contenu = {
            "version": VERSION_JOB,
            "tache": TASK_EXTRACTION,
            "moteur": demande.moteur,
            "famille": demande.modele.famille,
            "modele": {
                "identifiant": demande.modele.identifiant,
                "revision": demande.modele.commit,
                "chemin": str(extraction_model_path(self._donnees, demande.modele)),
            },
            "threads_demandes": demande.threads,
            "reglages": {reglage.nom: reglage.valeur for reglage in demande.reglages},
            "schema": dict(demande.grille.schema),
            "message_systeme": demande.grille.message_systeme,
            "sources": [
                {"texte": source.texte, "ordre": source.ordre, "nom": source.nom}
                for source in demande.sources
            ],
        }
        chemin.write_text(json.dumps(contenu, ensure_ascii=False, indent=2), encoding="utf-8")

    def _interpreter(self, demande: ExtractionRequest) -> str | Path:
        """Interpréteur du moteur d'extraction : celui du serveur pour le factice."""
        return engine_interpreter(
            self._registre, self._moteurs, self._interpreteur_serveur, demande.moteur
        )

    def _factice(self, demande: ExtractionRequest) -> bool:
        """Déclaration factice du moteur demandé, ou `False` s'il est inconnu."""
        try:
            return self._registre.obtenir(demande.moteur).factice
        except MoteurInconnu:
            return False

    def _create_work_dir(self) -> Path:
        """Crée le dossier de travail `data/cache/execution-*`, préfixe purgé à la récupération."""
        self._refuse_linked_work_root()
        try:
            self._racine_travail.mkdir(parents=True, exist_ok=True)
            return Path(
                tempfile.mkdtemp(prefix=PREFIXE_DOSSIER_TRAVAIL, dir=self._racine_travail)
            )
        except OSError as erreur:
            raise ExecutionImpossible(
                f"dossier de travail impossible : {message_erreur(erreur)}"
            ) from None

    def _refuse_linked_work_root(self) -> None:
        """Refuse une racine de travail qui serait un lien symbolique ou une jonction.

        Le job écrit sous cette racine contient les textes des sources : il
        n'est jamais créé dans la cible d'un lien. Le contrôle précède la
        création ; `verifier_lancable` l'applique aussi, pour refuser la
        demande avant toute réservation.
        """
        if self._racine_travail.is_symlink() or self._racine_travail.is_junction():
            raise ExecutionImpossible(MOTIF_CACHE_LIE)

    def _open_record(
        self, demande: ExtractionRequest, travailleur: Travailleur, debut: float
    ) -> tuple[ExtractionRecorder | None, str | None]:
        """Admission de la consignation ; `None` avec son motif si le stockage manque."""
        consignateur = ExtractionRecorder(
            self._donnees,
            demande,
            extraction_engine_metadata(self._registre, self._moteurs, demande.moteur),
            debut=debut,
        )
        if not consignateur.ouvrir():
            consignateur.fermer()
            return None, (
                "enregistrement de l'extraction impossible : "
                f"{consignateur.erreur or 'stockage indisponible'}"
            )
        travailleur.journaliser(
            f"Résultats de l'extraction : {NOM_DOSSIER_EXTRACTIONS}/"
            f"{consignateur.identifiant}."
        )
        return consignateur, None

    def _finalize_record(
        self,
        consignateur: ExtractionRecorder,
        resultat: ExtractionResult,
        travailleur: Travailleur,
    ) -> ExtractionResult:
        """Écrit l'état final, puis rapporte identifiant, mesures et compte des sources."""
        consignateur.clore(
            etat=resultat.etat,
            erreur=resultat.erreur,
            code_sortie=resultat.code_sortie,
        )
        measures = consignateur.measures
        resultat = replace(
            resultat,
            identifiant_resultat=consignateur.identifiant,
            duree_operation_s=measures.duree_operation_s,
            duree_processus_s=measures.duree_processus_s,
            summary=consignateur.summary(),
            sources=consignateur.resume_sources(),
        )
        if consignateur.erreur is not None:
            if consignateur.erreur != resultat.erreur:
                travailleur.journaliser(
                    f"Consignation de l'extraction en échec : {consignateur.erreur}"
                )
            if resultat.etat != ETAT_ECHOUEE:
                resultat = replace(resultat, etat=ETAT_ECHOUEE, erreur=consignateur.erreur)
        if consignateur.erreur_journal is not None:
            travailleur.journaliser(
                f"Journal du moteur incomplet : {consignateur.erreur_journal}"
            )
        return resultat

    def _close_process(self, processus: ProcessusMoteur, travailleur: Travailleur | None) -> None:
        """Termine le processus, puis attend sa fin réelle si l'arrêt échoue."""
        if processus.arreter():
            return
        if travailleur is not None:
            travailleur.journaliser(
                "Processus moteur encore actif après kill : attente de sa fin réelle, "
                "le créneau reste occupé jusque-là."
            )
        processus.attendre_fin()

    def _reserved_process(self) -> ProcessusMoteur:
        """Processus réservé par `reserver`, sans quoi le lancement est refusé."""
        with self._verrou:
            processus = self._processus_moteur
        if processus is None:
            raise ExecutionImpossible("aucune réservation : lancement refusé")
        return processus

    def _release(self, resultat: ExtractionResult | None) -> None:
        """Libère l'état d'extraction et publie la dernière issue, sous verrou."""
        with self._verrou:
            self._active = False
            self._processus_moteur = None
            self._travailleur = None
            self._derniere = resultat

    def _publish_result(self, generation: int, identifiant: str) -> None:
        """Associe le dossier consigné à l'opération admise, sous verrou."""
        with self._verrou:
            self._resultat_publie = (generation, identifiant)

    def _stop_requested(self) -> bool:
        with self._verrou:
            return self._arret_demande

    def _server_stop_requested(self) -> bool:
        with self._verrou:
            return self._arret_serveur

    # -- résultats et journal ------------------------------------------------

    def _result(
        self,
        demande: ExtractionRequest,
        *,
        factice: bool,
        etat: str,
        erreur: str | None = None,
        code_sortie: int | None = None,
        pid: int | None = None,
        arret_demande: bool = False,
    ) -> ExtractionResult:
        """Construit un `ExtractionResult` complet, sans effet de bord."""
        return ExtractionResult(
            etat=etat,
            factice=factice,
            moteur=demande.moteur,
            famille=demande.modele.famille,
            modele_identifiant=demande.modele.identifiant,
            nombre_sources=len(demande.sources),
            erreur=erreur,
            code_sortie=code_sortie,
            pid=pid,
            arret_demande=arret_demande,
        )

    def _result_before_launch(self, demande: ExtractionRequest, erreur: str) -> ExtractionResult:
        """Échec prévu avant tout lancement."""
        return self._result(
            demande, factice=self._factice(demande), etat=ETAT_ECHOUEE, erreur=erreur
        )

    def _result_unexpected(
        self, demande: ExtractionRequest, exception: BaseException
    ) -> ExtractionResult:
        """Résultat d'échec pour une exception non prévue, sans trace."""
        resultat = self._result_before_launch(
            demande,
            "extraction interrompue par une erreur interne : "
            f"{message_erreur(exception)}",
        )
        return replace(resultat, arret_demande=self._stop_requested())

    def _log_outcome(self, resultat: ExtractionResult, travailleur: Travailleur) -> None:
        """Une ligne d'issue pour la page d'opération, sans contenu de source."""
        compte = resultat.summary
        summary = (
            f"{compte.get('conformes', 0)} conforme(s), "
            f"{compte.get('non_conformes', 0)} non conforme(s), "
            f"{compte.get('erreurs', 0)} en erreur, "
            f"{compte.get('non_traitees', resultat.nombre_sources)} non traitée(s)"
        )
        if resultat.etat == ETAT_TERMINEE:
            travailleur.journaliser(f"Extraction terminée : {summary}.")
        elif resultat.etat == ETAT_INTERROMPUE:
            travailleur.journaliser(
                f"Extraction interrompue : {summary}. Les résultats reçus sont conservés."
            )
        else:
            travailleur.journaliser(f"Extraction en échec : {summary} ({resultat.erreur}).")
        if resultat.identifiant_resultat is not None:
            travailleur.journaliser(
                f"Résultats consignés : {NOM_DOSSIER_EXTRACTIONS}/"
                f"{resultat.identifiant_resultat}."
            )


def _event_summary(evenement: Mapping[str, Any]) -> str:
    """Ligne de progression d'un événement accepté, sans aucun contenu de source."""
    type_evenement = evenement["type"]
    if type_evenement == TYPE_CHARGEMENT:
        return "Modèle chargé : événement de chargement reçu."
    if type_evenement == TYPE_FIN:
        return (
            f"Fin du moteur annoncée : {evenement.get('audios_ok')} extraite(s), "
            f"{evenement.get('audios_erreur')} en erreur."
        )
    rang = evenement["index"] + 1
    if type_evenement == TYPE_EXTRACTION_ERREUR:
        return f"Source {rang} en erreur : {resume_ligne(str(evenement.get('motif', '')))}"
    if evenement.get("conforme"):
        return f"Source {rang} conforme."
    return f"Source {rang} non conforme : {resume_ligne(str(evenement.get('motif', '')))}"


def _last_reason(journal: Sequence[str]) -> str | None:
    """Dernière ligne non vide de la sortie d'erreur du moteur, bornée."""
    derniere = next((ligne for ligne in reversed(journal) if ligne.strip()), None)
    return None if derniere is None else resume_ligne(derniere)
