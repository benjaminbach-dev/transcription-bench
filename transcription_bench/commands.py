"""Commandes publiques de lecture : « audios list », « data check » (tâche 2.1),
« engines list » et « engines log » (tâche 2.2), « models list » (tâche 2.3),
« run options » (tâche 2.4), puis « results list », « results history » et
« results explain » (tâche 2.5), puis « results show » et « compare » (tâche 2.6).

Chaque commande est l'équivalent CLI d'une route de la page web (design D7) et
réutilise les mêmes services sans dupliquer le métier :

- `audios list` appelle `lister_audios` : un fichier illisible reste listé avec
  son erreur, un dossier d'entrée absent donne une liste vide, et une erreur
  d'accès au dossier reçoit le même message fixe que la page (aucune trace) ;
- `data check` passe la préparation des dossiers par la mutation courte du
  créneau, comme `POST /dossiers/verifier`, puis décrit l'état des dossiers
  attendus ; la préparation faite au démarrage de toute commande (design D2)
  la précède de toute façon ;
- `engines list` appelle `inventaire` : mêmes états que la page Moteurs
  (non installé, prêt, échec, en cours d'installation), moteur factice signalé ;
- `engines log ID [--limit N]` appelle `lire_journal` : dernières lignes du
  journal d'installation, 2000 par défaut comme la page ; un moteur inconnu
  est refusé (code 2) comme le 404 de la page ;
- `engines install ID` (tâche 3.1, opération longue hors lecture) appelle
  `installer` dans le créneau unique, suivi par `OperationWatch` : mêmes refus
  que `POST /moteurs/<id>/installer` (moteur inconnu, factice ou verrou absent :
  code 2), journal écrit au fil de l'eau, code 0 seulement si le moteur est prêt
  après l'opération, 1 en échec, 3 après un signal ; la ligne finale donne l'état
  de l'opération et celui du moteur ;
- `models list` appelle `inventaire` : modèles locaux prêts, relus depuis des
  manifestes cohérents uniquement ; un manifeste incohérent est ignoré par le
  service (aucun modèle n'est prêt), jamais signalé en échec, comme la page.
- `models check REPO --engine E [--revision R] [--file F]` (tâche 3.2) appelle
  `lancer_verification` dans le créneau unique, suivi par `OperationWatch` : le
  dépôt est vérifié sans aucun téléchargement. Le code vient du résultat du
  service (`dernier_resultat`), pas de l'état du créneau : compatible 0, dépôt
  refusé par la compatibilité (dont GGUF multiple sans `--file`, fragment GGUF)
  2, échec réseau, accès refusé ou erreur inattendue 1. Le résultat final porte
  l'état de l'opération et le résultat de vérification, sérialisé comme les
  vues existantes.
- `models download REPO --engine E [--revision R] [--file F]` (tâche 3.3)
  enchaîne, dans le même processus et avec un seul `OperationWatch`, la
  vérification puis le téléchargement des fichiers retenus. La révision résolue
  et la taille totale sont publiées (événement JSON `revision`, avant tout
  transfert) ; un modèle déjà prêt donne le code 0 sans opération. La référence
  locale `moteur/clé` est construite avec `cle_stockage` et n'est donnée que si
  le modèle est prêt. Refus, codes et arrêt par signal suivent `models check`.
- `models delete ENGINE KEY` (tâche 3.4) appelle `supprimer` : le dossier du
  modèle et ses fichiers sont retirés sans question, la commande nommée valant
  confirmation ; un moteur inconnu, une clé non conforme (SHA-256 attendu, donc
  tout chemin traversant) ou un modèle absent donnent le code 2 sans rien
  supprimer. Les résultats d'exécution ne sont jamais touchés.
- `run options` appelle `modeles_proposables`, `audios_proposables` et
  `preparer` : l'inventaire complet des modèles exécutables ou non (modèle
  synthétique du moteur factice compris, motif du service à l'appui), les
  audios proposables, les threads et les réglages effectifs de la famille
  avec leurs valeurs par défaut. Une valeur nommée périmée est remplacée par
  le choix applicable et annoncée par le `notice` du service ; comme la page
  rend alors un statut 400, la commande rend le code 2 avec ce motif, sans
  dupliquer la validation.
- `run check --model REF --audio NAME... [--threads N] [--setting NOM=VALEUR]...`
  (tâche 3.5) applique la validation partagée avec la page (`validate_execution_fields`)
  puis `verifier_lancable`, sans réserver ni lancer : la demande normalisée est
  affichée, aucun résultat n'est écrit.
- `run start` (même options, tâche 3.5) passe par `launch_execution`, comme la route
  `POST /executions/lancer` : réservation avant admission, puis `OperationWatch`
  suit l'exécution dans le créneau unique avec son journal en direct. Code 0 si
  l'exécution est terminée sans audio en erreur, 1 sinon, 2 pour un refus avant
  admission, 3 après un signal. Les options répétées sont transmises telles quelles
  aux services : `--model`, `--threads` et un même `--setting` donné deux fois sont
  refusés (code 2), `--audio` garde l'ordre reçu.
- `results list [--sort temps|ram|cpu|recent]` appelle `groupes_par_empreinte`
  avec le critère reçu (`recent` par défaut, comme la page Résultats) : chaque
  groupe porte son empreinte et chaque essai sa sélection `identifiant:ordre`,
  les essais observés et les mesures simulées restant séparés. Le tri vient du
  service ; un critère inconnu est refusé à l'analyse des arguments (code 2,
  sans session ni E/S).
- `results history` appelle `lister` : toutes les exécutions enregistrées, des
  plus récentes aux plus anciennes, y compris non interprétables, avec états,
  marques et résultat partiel, comme l'historique de la page Exécutions.
- `results explain` imprime l'aide des indicateurs depuis la source unique
  partagée avec le gabarit web (`web/results_help.py`, design D7) : aucune
  copie dédiée à la CLI.

- `results show ID` appelle `detail` : détail d'une exécution avec, pour chaque
  audio, la transcription complète, les mesures du moteur et le contexte de
  l'ordinateur quand il est consigné. Une exécution absente, un identifiant
  hostile ou un résultat non interprétable est refusé (code 2).
- `compare AUDIO_HASH SEL SEL...` appelle `comparer` : 2 à 64 sélections
  `identifiant:ordre` d'une même empreinte, dans l'ordre reçu. Une sélection mal
  formée est refusée à l'analyse ; hors groupe, hors bornes ou empreinte
  invalide, le service refuse (code 2) avant toute lecture.

Les commandes s'exécutent dans une session de données (`run_session`) : verrou
d'instance, récupération et préparation avant l'action, libération garantie
après. Sortie : texte français concis par défaut ; avec `--json`, un unique
objet `schema: 1` sur la sortie standard, les diagnostics sur la sortie d'erreur.
Le drapeau de signal n'est pas consulté : ces lectures sont instantanées, la
clôture de session reste celle de `run_session`.
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from engines.declarations import Reglage, TYPE_BOOLEEN, TYPE_CHOIX
from engines.mesures_systeme import ETAT_ABSENT, ETAT_VERSION_INCONNUE
from engines.registre import MoteurInconnu
from transcription_bench import paths
from transcription_bench.audios import AudioListe, lister_audios
from transcription_bench.command_session import (
    CODE_ECHEC,
    CODE_INTERRUPTED,
    CODE_REFUS,
    CODE_SUCCESS,
    CommandGroup,
    CommandSpec,
)
from transcription_bench.compatibilite_modeles import RAISONS_REFUS
from transcription_bench.composition import DataServices
from transcription_bench.consultation_resultats import (
    AudioVue,
    CarteComparaison,
    ComparaisonVue,
    DetailExecutionVue,
    EntreeEmpreinte,
    ExecutionListee,
    GroupeEmpreinte,
    IndicateursAudio,
    LIBELLES_TRI,
    LectureResultatsImpossible,
    ObservationSystemeVue,
    ResultatIntrouvable,
    ResultatNonInterpretable,
    SELECTIONS_MAX_COMPARAISON,
    SEPARATEUR_SELECTION,
    SyntheseComparaison,
    TRI_RECENT,
    analyser_selection,
)
from transcription_bench.execution_launch import (
    EngineNotReady,
    ExecutionAlreadyReserved,
    launch_execution,
    validate_execution_fields,
)
from transcription_bench.execution_moteur import (
    ResultatAudio,
    ResultatExecution,
)
from transcription_bench.executions import (
    PREFIXE_CHAMP_REGLAGE,
    ConfigurationExecutions,
    DemandeExecution,
    ModelePropose,
    PreparationExecution,
    SEPARATEUR_REFERENCE_MODELE,
    VALEUR_FAUSSE,
    VALEUR_VRAIE,
)
from transcription_bench.gestion_modeles import (
    ModeleLocal,
    cle_stockage,
    empreinte_verification,
)
from transcription_bench.indicateurs_resultats import (
    NON_MESURE,
    formater_date_courte,
    formater_duree_premier_niveau,
    formater_memoire_premier_niveau,
    formater_pourcentage_premier_niveau,
)
from transcription_bench.moteurs import (
    ETAT_PRET,
    LIBELLES_ETATS_MOTEUR,
    EtatMoteur,
    InstallationIndisponible,
)
from transcription_bench.operation_watch import OperationWatch, execution_exit_code
from transcription_bench.operations import (
    ETAT_TERMINEE,
    LIBELLES_ETATS,
    TYPE_INSTALLATION,
    CreneauOccupe,
    InstantaneCreneau,
    ServiceArrete,
)
from transcription_bench.output import (
    CommandOutput,
    output_from_arguments,
    serialize_audio_entry,
    serialize_comparison,
    serialize_engine_state,
    serialize_execution_listing,
    serialize_hash_group,
    serialize_local_model,
    serialize_model_option,
    serialize_preparation,
    serialize_run_detail,
    serialize_run_result,
    serialize_run_request,
    serialize_verification_result,
)
from transcription_bench.paths import (
    DOSSIERS_DATA,
    NOM_DOSSIER_AUDIO,
    ValeurRefusee,
)
from transcription_bench.supervision import SignalFlag
from transcription_bench.verification_modeles import ResultatVerification
from transcription_bench.web.app import (
    MESSAGES_ACTION,
    MESSAGE_DOSSIER_AUDIO_INACCESSIBLE,
    MESSAGE_RESULTAT_NON_INTERPRETABLE,
    MESSAGE_RESULTATS_INACCESSIBLES,
)
from transcription_bench.web.results_help import RESULTS_HELP
from transcription_bench.web.vues_modeles import formater_taille_modele
from transcription_bench.web.vues_resultats import etats_ligne

#: Message de confirmation partagé avec l'action web « dossiers-verifies ».
FOLDERS_CHECKED_MESSAGE = MESSAGES_ACTION["dossiers-verifies"]
NO_AUDIO_MESSAGE = "Aucun fichier audio dans le dossier d'entrée."
#: Même information que la page Modèles quand l'inventaire est vide.
NO_MODEL_MESSAGE = "Aucun modèle local prêt."

#: « run options » : inventaire et préparation, mêmes libellés que la page.
NO_PROPOSABLE_MODEL_MESSAGE = "Aucun modèle proposable."
NO_READABLE_AUDIO_MESSAGE = "Aucun audio lisible dans le dossier d'entrée."
NOT_APPLICABLE_REASON = (
    "aucun modèle exécutable ou aucun audio lisible n'est disponible"
)
NO_FAMILY_SETTING_MESSAGE = (
    "aucun réglage n'est déclaré par cette famille : aucun réglage n'est "
    "proposé pour cette exécution"
)

#: Dernières lignes du journal affichées par défaut, comme la page Moteurs.
DEFAULT_LOG_LIMIT = 2000
#: Même information que la page Journal d'installation d'un moteur factice.
FAKE_ENGINE_JOURNAL_MESSAGE = (
    "Le moteur factice ne s'installe pas : il n'a ni environnement ni journal "
    "d'installation."
)
NO_INSTALLATION_MESSAGE = "Aucune installation enregistrée pour ce moteur."


def configure_no_arguments(parser: argparse.ArgumentParser) -> None:
    """Commande sans argument propre : seul `--json` est ajouté par la CLI."""


def _run_audios_list(
    arguments: argparse.Namespace,
    services: DataServices,
    signal_flag: SignalFlag,
) -> int:
    """Liste les audios du dossier d'entrée, comme la page « Audios ».

    Aucun signal n'est décodé : la durée reste celle annoncée par l'en-tête du
    conteneur. Une erreur d'accès au dossier est un refus (code 2) avec le
    message fixe de la page ; un fichier illisible ne fait pas échouer la liste.
    """
    output = output_from_arguments(arguments)
    try:
        entries = lister_audios(services.data_dir)
    except (ValeurRefusee, OSError):
        # Même validation que la route web : message fixe, sans trace ni chemin.
        output.diagnostic(MESSAGE_DOSSIER_AUDIO_INACCESSIBLE)
        return CODE_REFUS
    input_dir = services.data_dir / NOM_DOSSIER_AUDIO
    output.result(
        {
            "input_dir": str(input_dir),
            "audios": [serialize_audio_entry(entry) for entry in entries],
        },
        audio_text_lines(input_dir, entries),
    )
    return CODE_SUCCESS


def audio_text_lines(
    input_dir: Path, entries: Sequence[AudioListe]
) -> list[str]:
    """Lignes de texte de « audios list » : une ligne par audio, lisible ou non."""
    lines = [f"Dossier d'entrée : {input_dir}"]
    if not entries:
        lines.append(NO_AUDIO_MESSAGE)
        return lines
    for entry in entries:
        if entry.erreur is not None:
            lines.append(f"{entry.nom} : {entry.format} — {entry.erreur}")
            continue
        if entry.duree_indicative is None:
            duration = "inconnue"
        else:
            duration = formater_duree_premier_niveau(entry.duree_indicative)
        if entry.taille_octets is None:
            size = "taille inconnue"
        else:
            size = f"{entry.taille_octets} octets"
        lines.append(
            f"{entry.nom} : {entry.format}, {size}, "
            f"durée indicative {duration}, lisible"
        )
    return lines


def folder_states(data_dir: Path) -> list[dict[str, object]]:
    """État des dossiers attendus : nom, chemin et présence, sans rien créer."""
    return [
        {
            "name": name,
            "path": str(data_dir / name),
            "exists": (data_dir / name).is_dir(),
        }
        for name in DOSSIERS_DATA
    ]


def _run_data_check(
    arguments: argparse.Namespace,
    services: DataServices,
    signal_flag: SignalFlag,
) -> int:
    """Prépare puis décrit les dossiers, comme le bouton de la page Exécutions."""
    output = output_from_arguments(arguments)
    try:
        # Même chemin que POST /dossiers/verifier : mutation courte du créneau,
        # refusée pendant une opération longue ou après le passage à l'arrêt.
        services.operations.executer_mutation(
            lambda: paths.preparer_dossiers_data(services.data_dir)
        )
    except (CreneauOccupe, ServiceArrete) as error:
        output.diagnostic(str(error))
        return CODE_REFUS
    folders = folder_states(services.data_dir)
    output.result(
        {"data_dir": str(services.data_dir), "folders": folders},
        folder_text_lines(folders),
    )
    return CODE_SUCCESS


def folder_text_lines(folders: Sequence[dict[str, object]]) -> list[str]:
    """Lignes de texte de « data check » : message de vérification puis état."""
    lines = [FOLDERS_CHECKED_MESSAGE]
    for folder in folders:
        presence = "présent" if folder["exists"] else "absent"
        lines.append(f"{folder['name']} : {folder['path']} ({presence})")
    return lines


AUDIOS_LIST = CommandSpec(
    name="list",
    help_text="liste les audios du dossier d'entrée, erreurs de lecture comprises",
    configure=configure_no_arguments,
    run=_run_audios_list,
)

AUDIOS = CommandGroup(
    name="audios",
    help_text="consultation des audios du dossier d'entrée",
    commands=(AUDIOS_LIST,),
)

DATA_CHECK = CommandSpec(
    name="check",
    help_text="vérifie les dossiers de données puis décrit leur état",
    configure=configure_no_arguments,
    run=_run_data_check,
)

DATA = CommandGroup(
    name="data",
    help_text="état des dossiers de données",
    commands=(DATA_CHECK,),
)

def _run_engines_list(
    arguments: argparse.Namespace,
    services: DataServices,
    signal_flag: SignalFlag,
) -> int:
    """Liste les moteurs déclarés et leur état, comme la page Moteurs.

    Les états viennent du service (`inventaire`) : l'installation en cours est
    visible comme sur la page, le moteur factice est signalé, et aucune
    installation n'est lancée. Les notes du service (limite du serveur de
    développement, motif d'échec) sont conservées telles quelles.
    """
    output = output_from_arguments(arguments)
    states = services.engines.inventaire()
    output.result(
        {"engines": [serialize_engine_state(state) for state in states]},
        engine_text_lines(states),
    )
    return CODE_SUCCESS


def engine_text_lines(states: Sequence[EtatMoteur]) -> list[str]:
    """Lignes de texte de « engines list » : une ligne par moteur, note comprise."""
    lines: list[str] = []
    for state in states:
        line = (
            f"{state.identifiant} : {state.nom} — "
            f"{LIBELLES_ETATS_MOTEUR[state.etat]}"
        )
        if state.factice:
            line += " — FACTICE"
        lines.append(line)
        if state.note:
            lines.append(f"  {state.note}")
        if state.date_installation:
            lines.append(f"  installé le {state.date_installation}")
    return lines


def positive_limit(value: str) -> int:
    """Convertit `--limit` et le borne, avec un message de refus explicite.

    Une limite inférieure à 1 serait un piège : le service garde les dernières
    lignes et une « limite » de 0 les rendrait toutes.
    """
    message = f"limite invalide : {value!r} (entier attendu, au moins 1)"
    try:
        limit = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError(message) from None
    if limit < 1:
        raise argparse.ArgumentTypeError(message)
    return limit


def configure_engines_log(parser: argparse.ArgumentParser) -> None:
    """Arguments de « engines log » : l'identifiant du moteur et la limite."""
    parser.add_argument(
        "engine_id",
        metavar="ID",
        help="identifiant du moteur, comme sur la page Moteurs",
    )
    parser.add_argument(
        "--limit",
        type=positive_limit,
        default=DEFAULT_LOG_LIMIT,
        metavar="N",
        help=f"nombre de dernières lignes affichées (défaut : {DEFAULT_LOG_LIMIT})",
    )


def _run_engines_log(
    arguments: argparse.Namespace,
    services: DataServices,
    signal_flag: SignalFlag,
) -> int:
    """Affiche les dernières lignes du journal d'un moteur, comme la page.

    Un moteur inconnu ou un identifiant qui sortirait du dossier des moteurs
    est refusé (code 2) avant toute lecture, comme le 404/403 de la page. Le
    moteur factice n'a pas de journal : il est signalé, jamais en échec.
    """
    output = output_from_arguments(arguments)
    engine_id = arguments.engine_id
    try:
        declaration = services.engines.declaration(engine_id)
        lines = services.engines.lire_journal(engine_id, arguments.limit)
    except MoteurInconnu:
        output.diagnostic(f"moteur inconnu : {engine_id!r}")
        return CODE_REFUS
    except ValeurRefusee as error:
        output.diagnostic(str(error))
        return CODE_REFUS
    output.result(
        {
            "engine": engine_id,
            "name": declaration.nom,
            "factice": declaration.factice,
            "limit": arguments.limit,
            "lines": list(lines),
        },
        engine_log_text_lines(declaration.factice, lines),
    )
    return CODE_SUCCESS


def engine_log_text_lines(
    factice: bool, lines: Sequence[str]
) -> list[str]:
    """Lignes de texte de « engines log » : journal, ou messages de la page."""
    if factice:
        return [FAKE_ENGINE_JOURNAL_MESSAGE]
    if not lines:
        return [NO_INSTALLATION_MESSAGE]
    return list(lines)


ENGINES_LIST = CommandSpec(
    name="list",
    help_text="liste les moteurs déclarés avec leur état d'installation",
    configure=configure_no_arguments,
    run=_run_engines_list,
)

ENGINES_LOG = CommandSpec(
    name="log",
    help_text="affiche les dernières lignes du journal d'installation d'un moteur",
    configure=configure_engines_log,
    run=_run_engines_log,
)

def configure_engines_install(parser: argparse.ArgumentParser) -> None:
    """Argument de « engines install » : l'identifiant du moteur à installer."""
    parser.add_argument(
        "engine_id",
        metavar="ID",
        help="identifiant du moteur à installer, comme sur la page Moteurs",
    )


def _engine_state(services: DataServices, engine_id: str) -> EtatMoteur:
    """État courant d'un moteur, relu depuis le service d'inventaire."""
    return next(
        state
        for state in services.engines.inventaire()
        if state.identifiant == engine_id
    )


def _run_engines_install(
    arguments: argparse.Namespace,
    services: DataServices,
    signal_flag: SignalFlag,
) -> int:
    """Installe un moteur dans le créneau unique et suit l'opération jusqu'à sa fin.

    Les refus de la page (moteur inconnu, moteur factice ou verrou absent, créneau
    occupé, arrêt en cours) donnent le code 2 avec le motif du service, avant toute
    admission. L'installation réelle (`installer`) tourne dans le créneau et
    `OperationWatch` écrit son journal au fil de l'eau. Le code vient de l'état du
    moteur après l'opération : 0 seulement s'il est prêt, 1 sinon, 3 après un signal.
    La ligne finale donne l'état de l'opération, son motif éventuel et l'état du
    moteur, prêt ou non.
    """
    output = output_from_arguments(arguments)
    engine_id = arguments.engine_id
    try:
        services.engines.verifier_installable(engine_id)
    except MoteurInconnu:
        output.diagnostic(f"moteur inconnu : {engine_id!r}")
        return CODE_REFUS
    except (InstallationIndisponible, ValeurRefusee) as error:
        output.diagnostic(str(error))
        return CODE_REFUS
    try:
        services.operations.demarrer(
            TYPE_INSTALLATION,
            lambda worker: services.engines.installer(engine_id, worker),
            cible=engine_id,
        )
    except (CreneauOccupe, ServiceArrete) as error:
        output.diagnostic(str(error))
        return CODE_REFUS

    def translate(snapshot: InstantaneCreneau) -> int:
        ready = _engine_state(services, engine_id).etat == ETAT_PRET
        return CODE_SUCCESS if snapshot.etat == ETAT_TERMINEE and ready else CODE_ECHEC

    watch = OperationWatch(
        services.operations, signal_flag, output, installation=services.engines
    )
    code = watch.wait(translate)
    operation = services.operations.instantane()
    state = _engine_state(services, engine_id)
    output.result(
        {
            "engine": engine_id,
            "operation": operation.etat,
            "error": operation.erreur,
            "state": serialize_engine_state(state),
        },
        install_text_lines(engine_id, operation, state),
    )
    return code


def install_text_lines(
    engine_id: str, operation: InstantaneCreneau, state: EtatMoteur
) -> list[str]:
    """Lignes de texte de « engines install » : opération, moteur, motif éventuel."""
    lines = [
        f"Opération « installation » : {LIBELLES_ETATS[operation.etat]}",
        f"Moteur {engine_id} : {LIBELLES_ETATS_MOTEUR[state.etat]}",
    ]
    if operation.erreur is not None:
        lines.append(f"Motif : {operation.erreur}")
    return lines


ENGINES_INSTALL = CommandSpec(
    name="install",
    help_text=(
        "installe un moteur dans le créneau d'opération, avec le journal en direct ; "
        "code 0 seulement si le moteur est prêt"
    ),
    configure=configure_engines_install,
    run=_run_engines_install,
)

ENGINES = CommandGroup(
    name="engines",
    help_text="état, installation et journal d'installation des moteurs",
    commands=(ENGINES_LIST, ENGINES_INSTALL, ENGINES_LOG),
)

def _run_models_list(
    arguments: argparse.Namespace,
    services: DataServices,
    signal_flag: SignalFlag,
) -> int:
    """Liste les modèles locaux prêts, comme la page Modèles.

    L'inventaire vient du service : seuls les manifestes cohérents, dont les
    fichiers attendus sont présents, donnent un modèle prêt ; un manifeste
    incohérent est ignoré sans échec ni diagnostic, exactement comme la page.
    La référence de chaque modèle (moteur et clé) permet d'enchaîner sur la
    préparation d'une exécution.
    """
    output = output_from_arguments(arguments)
    models = services.models.inventaire()
    output.result(
        {"models": [serialize_local_model(model) for model in models]},
        model_text_lines(models),
    )
    return CODE_SUCCESS


def model_text_lines(models: Sequence[ModeleLocal]) -> list[str]:
    """Lignes de texte de « models list » : premier niveau de la page par modèle."""
    if not models:
        return [NO_MODEL_MESSAGE]
    lines: list[str] = []
    for model in models:
        header = (
            f"{model.identifiant} : moteur {model.moteur}, "
            f"famille {model.famille}"
        )
        if model.fichier_gguf is not None:
            header += f", variante GGUF {model.fichier_gguf}"
        lines.append(header)
        reference = f"{model.moteur}{SEPARATEUR_REFERENCE_MODELE}{model.cle}"
        lines.append(f"  référence : {reference}")
        lines.append(f"  révision : {model.commit}")
        lines.append(
            f"  taille sur disque : {formater_taille_modele(model.taille_disque)}"
        )
        lines.append(
            "  taille distante totale : "
            f"{formater_taille_modele(model.taille_distante)}"
        )
        lines.append(f"  ajouté le {model.date}")
        for file in model.fichiers:
            lines.append(
                f"  fichier : {file.nom} "
                f"({formater_taille_modele(file.taille)})"
            )
    return lines


MODELS_LIST = CommandSpec(
    name="list",
    help_text="liste les modèles locaux prêts avec leur référence et leur taille",
    configure=configure_no_arguments,
    run=_run_models_list,
)

def configure_models_check(parser: argparse.ArgumentParser) -> None:
    """Arguments de « models check » : dépôt, moteur, révision et fichier GGUF.

    Les valeurs partent vers `lancer_verification` : identifiant, révision et nom
    GGUF y sont validés comme sur la page. `--file` ne sert qu'aux dépôts GGUF.
    """
    parser.add_argument(
        "repo",
        metavar="REPO",
        help="identifiant du dépôt Hugging Face, de la forme organisation/nom",
    )
    parser.add_argument(
        "--engine",
        metavar="E",
        required=True,
        help="identifiant du moteur réel installé qui vérifiera le dépôt",
    )
    parser.add_argument(
        "--revision",
        metavar="R",
        default=None,
        help="révision à résoudre ; par défaut, la branche par défaut du dépôt",
    )
    parser.add_argument(
        "--file",
        metavar="F",
        dest="gguf_file",
        default=None,
        help="fichier GGUF à retenir quand le dépôt en propose plusieurs",
    )


def _run_models_check(
    arguments: argparse.Namespace,
    services: DataServices,
    signal_flag: SignalFlag,
) -> int:
    """Vérifie un dépôt sans télécharger de poids, comme la page Modèles.

    La vérification tourne dans le créneau et `OperationWatch` écrit son journal
    au fil de l'eau. Le code vient du résultat publié par le service, non de l'état
    du créneau : un dépôt refusé donne le code 2 avec la raison du service, un
    échec de vérification le code 1. Le dossier des modèles n'est pas écrit.
    """
    output = output_from_arguments(arguments)
    try:
        services.models.lancer_verification(
            arguments.repo,
            arguments.engine,
            revision=(arguments.revision or "").strip() or None,
            fichier_gguf=(arguments.gguf_file or "").strip() or None,
        )
    except MoteurInconnu:
        output.diagnostic(f"moteur inconnu : {arguments.engine!r}")
        return CODE_REFUS
    except (ValeurRefusee, CreneauOccupe, ServiceArrete) as error:
        output.diagnostic(str(error))
        return CODE_REFUS

    def translate(snapshot: InstantaneCreneau) -> int:
        return check_exit_code(snapshot, services.models.dernier_resultat())

    watch = OperationWatch(services.operations, signal_flag, output)
    code = watch.wait(translate)
    operation = services.operations.instantane()
    result = services.models.dernier_resultat()
    output.result(
        {
            "operation": operation.etat,
            "verification": (
                None if result is None else serialize_verification_result(result)
            ),
        },
        check_text_lines(operation, result),
    )
    return code


def check_exit_code(
    operation: InstantaneCreneau, result: ResultatVerification | None
) -> int:
    """Code de « models check » : 0 accepté, 2 refus du dépôt, 1 échec.

    Un refus de compatibilité (`RAISONS_REFUS` : dépôt incompatible, choix GGUF
    manquant, fragment découpé) donne 2. Un échec réseau, un accès refusé, une
    révision inconnue ou une erreur inattendue donne 1. L'état `terminee` seul ne
    suffit pas : il ne dit pas si le dépôt est accepté.
    """
    if operation.etat != ETAT_TERMINEE or result is None:
        return CODE_ECHEC
    if result.accepte:
        return CODE_SUCCESS
    if result.raison in RAISONS_REFUS:
        return CODE_REFUS
    return CODE_ECHEC


def check_text_lines(
    operation: InstantaneCreneau, result: ResultatVerification | None
) -> list[str]:
    """Lignes de texte de « models check » : verdict, puis identité et fichiers.

    Un dépôt compatible affiche sa révision résolue, sa famille, les fichiers
    retenus et la taille totale (« taille inconnue » tant qu'une taille manque).
    Un refus affiche la raison du service et son message, variantes GGUF comprises.
    """
    if result is None:
        return [f"Opération « vérification » : {LIBELLES_ETATS[operation.etat]}"]
    if not result.accepte:
        return [f"Dépôt refusé ({result.raison}) : {result.message}"]
    lines = [
        f"Dépôt compatible : {result.identifiant}, moteur {result.moteur}, "
        f"famille {result.famille}",
        f"Révision résolue : {result.commit}",
    ]
    if result.fichier_gguf is not None:
        lines.append(f"Variante GGUF retenue : {result.fichier_gguf}")
    lines.append("Fichiers retenus :")
    lines.extend(
        f"  {file.nom} ({formater_taille_modele(file.taille)})"
        for file in result.fichiers
    )
    lines.append(f"Taille totale : {formater_taille_modele(result.taille_totale)}")
    lines.append("Aucun poids n'a été téléchargé : vérification seulement.")
    return lines


MODELS_CHECK = CommandSpec(
    name="check",
    help_text=(
        "vérifie la compatibilité d'un dépôt sans télécharger de poids, à la "
        "révision résolue ; code 0 si compatible"
    ),
    configure=configure_models_check,
    run=_run_models_check,
)

#: Événement JSON publiant la révision résolue et la taille avant le transfert.
REVISION_EVENT = "revision"


def _run_models_download(
    arguments: argparse.Namespace,
    services: DataServices,
    signal_flag: SignalFlag,
) -> int:
    """Vérifie un dépôt puis télécharge ses fichiers, dans le même processus.

    La vérification tourne dans le créneau ; si elle n'accepte pas le dépôt, la
    commande s'arrête là avec le code de `check_exit_code` (refus 2, échec 1). Sinon
    la révision résolue et la taille sont publiées en événement, avant l'admission
    du téléchargement, puis `lancer_telechargement` admet le transfert avec la
    même empreinte. Un modèle déjà prêt donne 0 sans opération. Le même
    `OperationWatch` suit les deux opérations : chaque journal est écrit en entier,
    la génération séparant les deux. Le code de succès exige que le modèle soit
    présent dans l'inventaire, non seulement que l'opération soit `terminee`.
    """
    output = output_from_arguments(arguments)
    try:
        services.models.lancer_verification(
            arguments.repo,
            arguments.engine,
            revision=(arguments.revision or "").strip() or None,
            fichier_gguf=(arguments.gguf_file or "").strip() or None,
        )
    except MoteurInconnu:
        output.diagnostic(f"moteur inconnu : {arguments.engine!r}")
        return CODE_REFUS
    except (ValeurRefusee, CreneauOccupe, ServiceArrete) as error:
        output.diagnostic(str(error))
        return CODE_REFUS

    watch = OperationWatch(services.operations, signal_flag, output)
    code = watch.wait(
        lambda snapshot: check_exit_code(snapshot, services.models.dernier_resultat())
    )
    verification = services.operations.instantane()
    result = services.models.dernier_resultat()
    if code != CODE_SUCCESS or result is None:
        _emit_download_result(
            output,
            verification=verification,
            result=result,
            download=None,
            reference=None,
            already_ready=False,
        )
        return code

    output.event(
        {
            "event": REVISION_EVENT,
            "revision": result.commit,
            "taille_totale": result.taille_totale,
        },
        revision_text_line(result),
    )
    if signal_flag.received:
        services.operations.passer_a_l_arret()
        _emit_download_result(
            output, verification=verification, result=result, download=None,
            reference=None, already_ready=False,
        )
        return CODE_INTERRUPTED
    try:
        started = services.models.lancer_telechargement(empreinte_verification(result))
    except (ValeurRefusee, CreneauOccupe, ServiceArrete) as error:
        output.diagnostic(str(error))
        _emit_download_result(
            output,
            verification=verification,
            result=result,
            download=None,
            reference=None,
            already_ready=False,
        )
        return CODE_REFUS
    if not started:
        _emit_download_result(
            output,
            verification=verification,
            result=result,
            download=None,
            reference=_local_reference(services, result),
            already_ready=True,
        )
        return CODE_SUCCESS

    def translate_download(snapshot: InstantaneCreneau) -> int:
        ready = _local_reference(services, result) is not None
        return CODE_SUCCESS if snapshot.etat == ETAT_TERMINEE and ready else CODE_ECHEC

    code = watch.wait(translate_download)
    _emit_download_result(
        output,
        verification=verification,
        result=result,
        download=services.operations.instantane(),
        reference=_local_reference(services, result),
        already_ready=False,
    )
    return code


def _local_reference(services: DataServices, result: ResultatVerification) -> str | None:
    """Référence `moteur/clé` du modèle, si ce modèle figure à l'inventaire prêt.

    La clé vient de `cle_stockage`, comme pour le dossier écrit par le service ; un
    modèle absent de l'inventaire (transfert interrompu, marqueur non publié) n'a
    pas de référence.
    """
    if result.id_resolu is None or result.commit is None:
        return None
    key = cle_stockage(result.id_resolu, result.commit, result.fichier_gguf)
    if any(
        model.moteur == result.moteur and model.cle == key
        for model in services.models.inventaire()
    ):
        return f"{result.moteur}{SEPARATEUR_REFERENCE_MODELE}{key}"
    return None


def _emit_download_result(
    output: CommandOutput,
    *,
    verification: InstantaneCreneau,
    result: ResultatVerification | None,
    download: InstantaneCreneau | None,
    reference: str | None,
    already_ready: bool,
) -> None:
    """Résultat final de « models download » : états, vérification et référence."""
    output.result(
        {
            "verification_operation": verification.etat,
            "download_operation": None if download is None else download.etat,
            "already_ready": already_ready,
            "verification": (
                None if result is None else serialize_verification_result(result)
            ),
            "reference": reference,
        },
        download_text_lines(verification, result, download, reference, already_ready),
    )


def revision_text_line(result: ResultatVerification) -> str:
    """Ligne texte de la révision résolue et de la taille, avant le transfert."""
    return (
        f"Révision résolue : {result.commit}, taille totale : "
        f"{formater_taille_modele(result.taille_totale)}"
    )


def download_text_lines(
    verification: InstantaneCreneau,
    result: ResultatVerification | None,
    download: InstantaneCreneau | None,
    reference: str | None,
    already_ready: bool,
) -> list[str]:
    """Lignes de texte de « models download » : verdict, état et référence."""
    if result is None or not result.accepte:
        return check_text_lines(verification, result)
    if already_ready:
        lines = ["Modèle déjà prêt : aucun fichier n'a été téléchargé."]
    elif download is None:
        lines = ["Téléchargement non lancé."]
    else:
        lines = [f"Opération « téléchargement » : {LIBELLES_ETATS[download.etat]}"]
    if reference is not None:
        lines.append(f"Référence du modèle : {reference}")
    return lines


MODELS_DOWNLOAD = CommandSpec(
    name="download",
    help_text=(
        "vérifie un dépôt puis télécharge ses fichiers à la révision résolue, avec "
        "la révision et la taille publiées avant le transfert ; code 0 si prêt"
    ),
    configure=configure_models_check,
    run=_run_models_download,
)

def configure_models_delete(parser: argparse.ArgumentParser) -> None:
    """Arguments de « models delete » : moteur et clé du modèle local.

    Les deux valeurs partent telles quelles vers `GestionModeles.supprimer`, qui
    valide le moteur (registre) et la clé (SHA-256) avant tout accès disque.
    """
    parser.add_argument(
        "engine",
        metavar="ENGINE",
        help="identifiant du moteur auquel appartient le modèle local",
    )
    parser.add_argument(
        "key",
        metavar="KEY",
        help="clé de stockage du modèle, telle qu'affichée par « models list »",
    )


def _run_models_delete(
    arguments: argparse.Namespace,
    services: DataServices,
    signal_flag: SignalFlag,
) -> int:
    """Supprime le dossier d'un modèle local, comme `POST /modeles/supprimer`.

    La commande nommée vaut confirmation : aucune question n'est posée. Seuls le
    dossier du modèle et ses fichiers sont retirés par le service ; les résultats
    d'exécution restent consultables. Un moteur inconnu, une clé invalide, un
    modèle absent ou une suppression refusée donnent le code 2 sans rien supprimer.
    """
    output = output_from_arguments(arguments)
    try:
        services.models.supprimer(arguments.engine, arguments.key)
    except MoteurInconnu:
        output.diagnostic(f"moteur inconnu : {arguments.engine!r}")
        return CODE_REFUS
    except (ValeurRefusee, CreneauOccupe, ServiceArrete) as error:
        output.diagnostic(str(error))
        return CODE_REFUS
    reference = f"{arguments.engine}{SEPARATEUR_REFERENCE_MODELE}{arguments.key}"
    output.result(
        {"engine": arguments.engine, "key": arguments.key, "deleted": True},
        [
            f"Modèle local supprimé : {reference}",
            "Les résultats déjà produits restent consultables.",
        ],
    )
    return CODE_SUCCESS


MODELS_DELETE = CommandSpec(
    name="delete",
    help_text=(
        "supprime le dossier d'un modèle local par moteur et clé, sans confirmation "
        "interactive ; les résultats restent consultables"
    ),
    configure=configure_models_delete,
    run=_run_models_delete,
)

MODELS = CommandGroup(
    name="models",
    help_text=(
        "modèles locaux : inventaire, vérification, téléchargement et suppression"
    ),
    commands=(MODELS_LIST, MODELS_CHECK, MODELS_DOWNLOAD, MODELS_DELETE),
)

def configure_run_options(parser: argparse.ArgumentParser) -> None:
    """Arguments de « run options » : référence de modèle et audios ordonnés.

    Aucune validation ici : `--model` et `--audio` partent bruts vers
    `preparer`, qui remplace une valeur périmée par le choix applicable et
    l'annonce dans son `notice` (le même service que la page, design D7).
    `--audio` est répétable et l'ordre reçu est conservé, comme les cases
    cochées du lot de la page.
    """
    parser.add_argument(
        "--model",
        metavar="REF",
        default=None,
        help="référence du modèle proposable (<moteur>/<clé>) ; "
        "par défaut le premier modèle exécutable",
    )
    parser.add_argument(
        "--audio",
        metavar="NAME",
        action="append",
        default=None,
        help="nom d'un audio lisible du dossier d'entrée ; répétable, "
        "l'ordre reçu est conservé",
    )

def _run_run_options(
    arguments: argparse.Namespace,
    services: DataServices,
    signal_flag: SignalFlag,
) -> int:
    """Présente la préparation d'une exécution, comme la page « Exécutions ».

    Trois lectures du même service : `modeles_proposables` (modèles de
    l'inventaire, exécutables ou non avec leur motif, et modèle synthétique du
    moteur factice), `audios_proposables` (audios lisibles) et `preparer`
    (choix appliqués : modèle, audios ordonnés, threads, réglages de la
    famille avec leurs valeurs par défaut). Une valeur nommée périmée est
    remplacée et annoncée par le `notice` du service : la page rend alors un
    statut 400, la commande rend le code 2 avec ce motif, le résultat restant
    écrit pour montrer les choix applicables.
    """
    output = output_from_arguments(arguments)
    preparation = services.preparation.preparer(
        modele=arguments.model,
        audios=arguments.audio or (),
    )
    models = services.preparation.modeles_proposables()
    audios = services.preparation.audios_proposables()
    output.result(
        {
            "models": [serialize_model_option(model) for model in models],
            "audios": [serialize_audio_entry(audio) for audio in audios],
            "preparation": serialize_preparation(preparation),
            # Syntaxe des booléens pour les futurs `--setting NOM=VALEUR` : la
            # même que le formulaire (VALEUR_VRAIE / VALEUR_FAUX du service).
            "boolean_values": {"true": VALEUR_VRAIE, "false": VALEUR_FAUSSE},
        },
        run_options_text_lines(models, audios, preparation),
    )
    if preparation.notice is not None:
        output.diagnostic(preparation.notice)
        return CODE_REFUS
    return CODE_SUCCESS

def run_options_text_lines(
    models: Sequence[ModelePropose],
    audios: Sequence[AudioListe],
    preparation: PreparationExecution,
) -> list[str]:
    """Lignes de texte de « run options » : inventaire puis choix appliqués."""
    lines = ["Modèles proposables :"]
    if not models:
        lines.append(f"  {NO_PROPOSABLE_MODEL_MESSAGE}")
    else:
        lines.extend(model_option_line(model) for model in models)
    lines.append("Audios proposables :")
    if not audios:
        lines.append(f"  {NO_READABLE_AUDIO_MESSAGE}")
    else:
        lines.extend(f"  {audio.nom}" for audio in audios)
    lines.append(f"Threads par défaut : {preparation.threads}")
    if preparation.applicable and preparation.modele is not None:
        model = preparation.modele
        lines.append("Préparation appliquée :")
        model_line = f"  modèle : {model.identifiant} (référence {model.reference})"
        if model.fichier_gguf is not None:
            model_line += f", variante GGUF {model.fichier_gguf}"
        lines.append(model_line)
        lines.append(f"  moteur : {model.nom_moteur}")
        lines.append(
            "  audios, dans l'ordre de traitement : "
            f"{', '.join(preparation.audios)}"
        )
        lines.append(f"  threads : {preparation.threads}")
        lines.extend(setting_lines(preparation.reglages))
    else:
        lines.append(f"Préparation non applicable : {NOT_APPLICABLE_REASON}.")
    for message in (preparation.notice, preparation.reinitialisation):
        if message is not None:
            lines.append(message)
    return lines

def model_option_line(model: ModelePropose) -> str:
    """Une ligne par modèle proposable, exécutable ou non, synthétique compris."""
    line = (
        f"  {model.reference} : {model.identifiant} — moteur {model.nom_moteur}, "
        f"famille {model.libelle_famille}"
    )
    if model.synthetique:
        # L'identifiant du modèle synthétique est déjà le libellé du service :
        # seule la marque synthétique est ajoutée, sans le répéter.
        line += " — modèle synthétique (moteur factice)"
    if not model.executable:
        line += f" — NON EXÉCUTABLE : {model.motif_non_executable}"
    return line

def setting_lines(
    settings: Sequence[tuple[Reglage, int | bool | str]],
) -> list[str]:
    """Lignes des réglages de la famille, valeurs par défaut et syntaxe.

    Les booléens suivent la syntaxe du formulaire (`oui` ou `non`) : la ligne
    la rappelle pour chaque réglage booléen, la clé `boolean_values` la porte
    en JSON pour les futurs `--setting` de `run check` et `run start`.
    """
    if not settings:
        return [f"  {NO_FAMILY_SETTING_MESSAGE}"]
    lines: list[str] = []
    for setting, value in settings:
        line = (
            f"  réglage {setting.nom} ({setting.libelle}) : "
            f"{setting_value_text(value)}"
        )
        if setting.type_valeur == TYPE_BOOLEEN:
            line += f" (booléen : {VALEUR_VRAIE} ou {VALEUR_FAUSSE})"
        elif setting.type_valeur == TYPE_CHOIX:
            line += f" (valeurs : {', '.join(setting.valeurs)})"
        else:
            line += f" ({setting.type_valeur})"
        line += f" — {setting.description}"
        lines.append(line)
    return lines

def setting_value_text(value: int | bool | str) -> str:
    """Valeur d'un réglage telle que le formulaire la transmet (oui/non)."""
    if value is True:
        return VALEUR_VRAIE
    if value is False:
        return VALEUR_FAUSSE
    return str(value)

RUN_OPTIONS = CommandSpec(
    name="options",
    help_text=(
        "préparation d'une exécution : modèles proposables, audios, threads "
        "et réglages de la famille"
    ),
    configure=configure_run_options,
    run=_run_run_options,
)

#: Champs du formulaire d'exécution lus par `execution_launch` (noms de la page).
FORM_FIELD_MODEL = "modele"
FORM_FIELD_AUDIOS = "audios"
FORM_FIELD_THREADS = "threads"
#: Même marque que les pages de résultats pour une exécution du moteur factice.
SIMULATED_RUN_MESSAGE = (
    "MESURES SIMULÉES : moteur factice, ces mesures ne sont pas des mesures "
    "réelles de ce programme."
)
AUDIO_IN_ERROR_TEXT = "en erreur"
AUDIO_NOT_TREATED_TEXT = "non traité"
AUDIO_TREATED_TEXT = "traité"


def setting_pair(value: str) -> tuple[str, str]:
    """Découpe `NOM=VALEUR` au premier signe égal ; refus à l'analyse sinon."""
    name, separator, setting_value = value.partition("=")
    if not separator:
        raise argparse.ArgumentTypeError(
            f"réglage attendu sous la forme NOM=VALEUR : {value!r}"
        )
    return name, setting_value


def configure_run_request(parser: argparse.ArgumentParser) -> None:
    """Options communes de « run check » et « run start ».

    `--model` et `--audio` sont obligatoires. `--model`, `--threads` et `--setting`
    sont acceptés plusieurs fois **pour que** les services voient le doublon et le
    refusent : un argument écrasé en silence serait une perte. `--audio` garde l'ordre
    reçu, comme le lot coché sur la page.
    """
    parser.add_argument(
        "--model",
        metavar="REF",
        action="append",
        required=True,
        help="référence du modèle prêt (<moteur>/<clé>), une seule fois",
    )
    parser.add_argument(
        "--audio",
        metavar="NAME",
        action="append",
        required=True,
        help="nom d'un audio lisible du dossier d'entrée ; répétable, "
        "l'ordre reçu est l'ordre de traitement",
    )
    parser.add_argument(
        "--threads",
        metavar="N",
        action="append",
        default=None,
        help="nombre de threads, une seule fois ; par défaut celui de la préparation",
    )
    parser.add_argument(
        "--setting",
        metavar="NOM=VALEUR",
        action="append",
        type=setting_pair,
        default=None,
        help="réglage de la famille du modèle ; répétable, un même nom est refusé",
    )


def form_fields_from_arguments(
    arguments: argparse.Namespace, preparation: ConfigurationExecutions
) -> list[tuple[str, str]]:
    """Champs de formulaire équivalents aux options, dans l'ordre de la ligne.

    Les services valident ces paires comme celles d'un POST : un champ unique reçu
    deux fois est refusé par eux. Les threads prennent la valeur par défaut de la
    préparation quand `--threads` est absent.
    """
    threads = arguments.threads or [str(preparation.threads_par_defaut())]
    fields = [(FORM_FIELD_MODEL, value) for value in arguments.model]
    fields += [(FORM_FIELD_AUDIOS, name) for name in arguments.audio]
    fields += [(FORM_FIELD_THREADS, value) for value in threads]
    fields += [
        (PREFIXE_CHAMP_REGLAGE + name, value)
        for name, value in arguments.setting or ()
    ]
    return fields


def _run_run_check(
    arguments: argparse.Namespace,
    services: DataServices,
    signal_flag: SignalFlag,
) -> int:
    """Valide une demande sans rien lancer ni écrire, comme la page avant lancement.

    `validate_execution_fields` applique les mêmes refus que la route de
    vérification : champs répétés, modèle prêt, audios lisibles, threads et
    réglages déclarés. Le contrôle de lancement du moteur reste propre à
    `run start`, comme sur le web. Seule la préparation de `data/` de la session
    a lieu. Un refus donne le code 2 avec le motif du service.
    """
    output = output_from_arguments(arguments)
    fields = form_fields_from_arguments(arguments, services.preparation)
    try:
        request = validate_execution_fields(services.preparation, fields)
    except ValeurRefusee as error:
        output.diagnostic(str(error))
        return CODE_REFUS
    output.result({"request": serialize_run_request(request)}, run_check_text_lines(request))
    return CODE_SUCCESS


def _run_run_start(
    arguments: argparse.Namespace,
    services: DataServices,
    signal_flag: SignalFlag,
) -> int:
    """Lance l'exécution dans le créneau unique et suit son journal jusqu'à sa fin.

    `launch_execution` valide, contrôle le moteur, réserve puis admet : un refus
    avant admission donne le code 2 avec le motif du service, sans opération. Le
    code final vient du résultat de l'exécution (`execution_exit_code`) : 0 si
    tous les audios sont traités, 1 si un audio est en erreur, 3 après un signal.
    La ligne finale donne l'état de l'opération, l'identifiant du résultat et
    l'issue de chaque audio, dans l'ordre demandé.
    """
    output = output_from_arguments(arguments)
    fields = form_fields_from_arguments(arguments, services.preparation)
    try:
        launch_execution(
            services.preparation,
            services.execution,
            services.operations,
            fields,
        )
    except (
        ValeurRefusee,
        EngineNotReady,
        ExecutionAlreadyReserved,
        CreneauOccupe,
        ServiceArrete,
    ) as error:
        output.diagnostic(str(error))
        return CODE_REFUS

    watch = OperationWatch(
        services.operations, signal_flag, output, execution=services.execution
    )
    code = watch.wait(
        lambda _snapshot: execution_exit_code(services.execution.derniere_execution())
    )
    operation = services.operations.instantane()
    result = services.execution.derniere_execution()
    identifier = services.execution.identifiant_resultat(operation.generation)
    output.result(
        {
            "operation": operation.etat,
            "error": operation.erreur,
            "identifiant_resultat": identifier,
            "execution": None if result is None else serialize_run_result(result),
        },
        run_start_text_lines(operation, result, identifier),
    )
    return code


def run_check_text_lines(request: DemandeExecution) -> list[str]:
    """Lignes de texte de « run check » : demande valide et choix effectifs."""
    reference = f"{request.moteur}{SEPARATEUR_REFERENCE_MODELE}{request.cle}"
    lines = [
        "Demande valide : aucune exécution lancée, aucun résultat écrit.",
        f"Modèle : {request.identifiant} (référence {reference}), "
        f"moteur {request.moteur}, famille {request.famille}",
    ]
    if request.fichier_gguf is not None:
        lines.append(f"Variante GGUF : {request.fichier_gguf}")
    if request.synthetique:
        lines.append(SIMULATED_RUN_MESSAGE)
    lines.append(
        f"Audios, dans l'ordre de traitement : {', '.join(request.audios)}"
    )
    lines.append(f"Threads : {request.threads}")
    if not request.reglages:
        lines.append("Réglages : aucun")
    for setting in request.reglages:
        lines.append(f"Réglage {setting.nom} : {setting_value_text(setting.valeur)}")
    return lines


def run_start_text_lines(
    operation: InstantaneCreneau,
    result: ResultatExecution | None,
    identifier: str | None,
) -> list[str]:
    """Lignes de texte de « run start » : opération, résultat et état par audio."""
    lines = [f"Opération « exécution » : {LIBELLES_ETATS[operation.etat]}"]
    if operation.erreur is not None:
        lines.append(f"Motif : {operation.erreur}")
    if result is None:
        return lines
    if result.factice:
        lines.append(SIMULATED_RUN_MESSAGE)
    if identifier is not None:
        lines.append(f"Résultat enregistré : {identifier}")
    lines.append("Audios :")
    lines.extend(
        f"  {audio.nom} : {audio_state_text(audio)}" for audio in result.audios
    )
    return lines


def audio_state_text(audio: ResultatAudio) -> str:
    """État d'un audio : en erreur (avec le motif), non traité ou traité."""
    if audio.erreur is not None:
        return f"{AUDIO_IN_ERROR_TEXT} ({audio.erreur})"
    if audio.non_traite:
        return AUDIO_NOT_TREATED_TEXT
    return AUDIO_TREATED_TEXT


RUN_CHECK = CommandSpec(
    name="check",
    help_text=(
        "valide une demande d'exécution sans rien lancer ni écrire, et affiche la "
        "demande normalisée"
    ),
    configure=configure_run_request,
    run=_run_run_check,
)

RUN_START = CommandSpec(
    name="start",
    help_text=(
        "lance une exécution sur un ou plusieurs audios, avec le journal en direct ; "
        "code 1 si un audio est en erreur"
    ),
    configure=configure_run_request,
    run=_run_run_start,
)

RUN = CommandGroup(
    name="run",
    help_text="préparation, vérification et lancement des exécutions",
    commands=(RUN_OPTIONS, RUN_CHECK, RUN_START),
)

#: « results list » : regroupement par empreinte et sélection par essai.
NO_GROUP_MESSAGE = (
    "Aucune transcription à regrouper par audio pour l'instant."
)
#: « results history » : mêmes informations que l'historique de la page.
NO_EXECUTION_MESSAGE = "Aucune exécution enregistrée."
NON_INTERPRETABLE_PREFIX = "non interprétable"


def sort_choice(value: str) -> str:
    """Convertit `--sort` en le bornant aux critères du service, refus sinon.

    Le refus a lieu à l'analyse des arguments : code 2, sans session ni E/S.
    """
    message = f"tri invalide : {value!r} (temps, ram, cpu ou recent attendu)"
    if value not in LIBELLES_TRI:
        raise argparse.ArgumentTypeError(message)
    return value


def configure_results_list(parser: argparse.ArgumentParser) -> None:
    """Arguments de « results list » : le critère de classement des essais."""
    parser.add_argument(
        "--sort",
        type=sort_choice,
        default=TRI_RECENT,
        metavar="CRITERE",
        help="classement des essais dans chaque groupe : temps, ram, cpu ou "
        "recent (défaut : recent, comme la page Résultats)",
    )


def _run_results_list(
    arguments: argparse.Namespace,
    services: DataServices,
    signal_flag: SignalFlag,
) -> int:
    """Liste les résultats groupés par empreinte d'audio, comme la page.

    Le regroupement, les tris et la séparation observées/simulées viennent du
    service ; la commande ajoute l'empreinte du groupe et la sélection
    `identifiant:ordre` de chaque essai, de quoi enchaîner sur la comparaison.
    Le critère inconnu est déjà refusé à l'analyse ; un dossier des résultats
    illisible est un échec (code 1) avec le message de la page, sans écriture.
    """
    output = output_from_arguments(arguments)
    try:
        groups = services.results.groupes_par_empreinte(arguments.sort)
    except LectureResultatsImpossible:
        output.diagnostic(MESSAGE_RESULTATS_INACCESSIBLES)
        return CODE_ECHEC
    output.result(
        {
            "sort": arguments.sort,
            "groups": [serialize_hash_group(group) for group in groups],
        },
        results_list_text_lines(arguments.sort, groups),
    )
    return CODE_SUCCESS


def results_list_text_lines(
    sort: str, groups: Sequence[GroupeEmpreinte]
) -> list[str]:
    """Lignes de texte de « results list » : un groupe par audio, par essai."""
    lines = [f"Tri des essais : {LIBELLES_TRI[sort]}"]
    if not groups:
        lines.append(NO_GROUP_MESSAGE)
        return lines
    for group in groups:
        names = ", ".join(group.noms) or "fichier non consigné"
        lines.append(f"Audio {names} — empreinte {group.empreinte} :")
        if group.entrees_reelles:
            lines.append("  essais observés :")
            for entry in group.entrees_reelles:
                lines.extend(result_entry_lines(entry))
        if group.entrees_simulees:
            lines.append("  mesures simulées :")
            for entry in group.entrees_simulees:
                lines.extend(result_entry_lines(entry))
    return lines


def result_entry_lines(entry: EntreeEmpreinte) -> list[str]:
    """Lignes d'un essai : sélection, modèle, états, puis trois indicateurs.

    Les états (statut d'audio, état d'exécution non terminée, marques) reprennent
    `etats_ligne`, la même lecture que la page ; les mesures absentes restent
    « non mesuré » ou « non interprétable », jamais zéro.
    """
    selection = f"{entry.execution}{SEPARATEUR_SELECTION}{entry.ordre}"
    header = f"    {selection} : {entry.modele or 'modèle non consigné'}"
    if entry.variante:
        header += f", variante {entry.variante}"
    header += f" — moteur {entry.moteur or 'non consigné'}"
    header += f", {formater_date_courte(entry.date_essai)}"
    states = etats_ligne(entry)
    if states:
        header += f" — {', '.join(states)}"
    measures = f"      {engine_measures_text(entry.indicateurs, entry.annotation_ram)}"
    return [header, measures]


def entry_cpu_text(indicators: IndicateursAudio) -> str:
    """Occupation CPU du moteur : ratio, ou motif d'absence, jamais zéro."""
    if indicators.occupation_cpu is not None:
        return formater_pourcentage_premier_niveau(indicators.occupation_cpu)
    if indicators.temps_cpu_s is not None:
        return "non interprétable"
    return "non mesuré"


def _run_results_history(
    arguments: argparse.Namespace,
    services: DataServices,
    signal_flag: SignalFlag,
) -> int:
    """Historique complet des exécutions, comme la page Exécutions.

    Toutes les exécutions enregistrées, des plus récentes aux plus anciennes,
    y compris non interprétables ; aucun fichier de résultat n'est modifié.
    """
    output = output_from_arguments(arguments)
    try:
        executions = services.results.lister()
    except LectureResultatsImpossible:
        output.diagnostic(MESSAGE_RESULTATS_INACCESSIBLES)
        return CODE_ECHEC
    output.result(
        {
            "executions": [
                serialize_execution_listing(execution) for execution in executions
            ]
        },
        history_text_lines(executions),
    )
    return CODE_SUCCESS


def history_text_lines(
    executions: Sequence[ExecutionListee],
) -> list[str]:
    """Lignes de texte de « results history » : une exécution par bloc."""
    if not executions:
        return [NO_EXECUTION_MESSAGE]
    lines = ["De la plus récente à la plus ancienne :"]
    for execution in executions:
        if not execution.exploitable:
            lines.append(
                f"{execution.identifiant} : {NON_INTERPRETABLE_PREFIX} — "
                f"{execution.motif}"
            )
            continue
        line = f"{execution.identifiant} : {execution.libelle_etat}"
        if execution.partiel:
            line += " (résultats partiels)"
        line += f", créée le {execution.cree_le or 'date non consignée'}"
        lines.append(line)
        details = (
            f"    modèle {execution.modele or 'non consigné'}, "
            f"moteur {execution.moteur or 'non consigné'}"
        )
        if execution.audios_traites is not None:
            details += (
                f", {execution.audios_traites} audios traités "
                f"sur {execution.audios_total}"
            )
        if execution.duree_operation_s is not None:
            details += (
                ", durée de l'opération "
                f"{formater_duree_premier_niveau(execution.duree_operation_s)}"
            )
        lines.append(details)
        if execution.marques:
            lines.append(f"    marques : {', '.join(execution.marques)}")
    return lines


def _run_results_explain(
    arguments: argparse.Namespace,
    services: DataServices,
    signal_flag: SignalFlag,
) -> int:
    """Imprime l'aide des indicateurs depuis la source unique (design D7).

    Même texte que la page « Comprendre les indicateurs » : aucune lecture de
    résultat, aucune écriture, la session ne sert que le verrou commun à toute
    commande (design D2).
    """
    output = output_from_arguments(arguments)
    output.result(
        {
            "title": RESULTS_HELP["title"],
            "intro": RESULTS_HELP["intro"],
            "sections": RESULTS_HELP["sections"],
        },
        explain_text_lines(),
    )
    return CODE_SUCCESS


def explain_text_lines() -> list[str]:
    """Lignes de texte de « results explain » : la source unique, en clair.

    La mise en évidence (`strong`, `code`) est perdue sans dommage : les textes
    restent identiques, seule leur structure (sections, définitions, listes)
    guide la lecture.
    """
    lines = [RESULTS_HELP["title"], inline_text(RESULTS_HELP["intro"])]
    for section in RESULTS_HELP["sections"]:
        lines.append("")
        lines.append(section["title"])
        for block in section["blocks"]:
            lines.extend(block_text_lines(block))
    return lines


def inline_text(parts: Sequence[dict[str, str]]) -> str:
    """Texte d'une suite de portions, sans la mise en évidence du gabarit."""
    return "".join(part["text"] for part in parts)


def block_text_lines(block: dict[str, Any]) -> list[str]:
    """Lignes d'un bloc d'aide : paragraphe, définitions ou liste."""
    if block["type"] == "paragraph":
        return [inline_text(block["parts"])]
    if block["type"] == "definitions":
        return [
            f"{inline_text(entry['term'])} : "
            f"{inline_text(entry['definition'])}"
            for entry in block["entries"]
        ]
    return [f"- {inline_text(item)}" for item in block["items"]]


#: « results show » et « compare » : mêmes refus et libellés que la page de détail.
SIMULATED_MEASURES_MESSAGE = (
    "MESURES SIMULÉES : ces mesures ne sont pas des mesures réelles de ce "
    "programme."
)
SIMULATED_COMPARISON_MESSAGE = (
    "MESURES SIMULÉES : au moins une transcription porte des mesures simulées, "
    "exclues de la synthèse."
)
PARTIAL_COMPARISON_MESSAGE = (
    "Résultats partiels : au moins une transcription provient d'une exécution "
    "non terminée."
)
NO_SYNTHESIS_MESSAGE = (
    "Synthèse : aucune distinction attribuée, au moins deux mesures observées "
    "comparables sont nécessaires."
)
NO_TRANSCRIPT_MESSAGE = "Aucun résultat enregistré pour cet audio."


def engine_measures_text(
    indicators: IndicateursAudio, annotation_ram: str | None
) -> str:
    """Mesures du moteur d'un essai : durée, RAM et CPU, sans zéro pour l'absent.

    Même lecture que les lignes de la liste : le pic mémoire est annoté comme
    cumulatif quand l'audio n'est pas le premier de sa demande.
    """
    ram = formater_memoire_premier_niveau(indicators.pic_memoire_octets)
    if annotation_ram is not None and indicators.pic_memoire_octets is not None:
        ram += " (pic cumulatif)"
    return (
        f"transcription "
        f"{formater_duree_premier_niveau(indicators.duree_transcription_s)}, "
        f"RAM moteur {ram}, CPU moteur {entry_cpu_text(indicators)}"
    )


def system_context_text(observation: ObservationSystemeVue) -> str:
    """Contexte de l'ordinateur d'un audio : CPU total et RAM après l'audio.

    Distinct des mesures du moteur. Une observation absente ou hors contrat dit
    pourquoi, sans valeur de l'ordinateur courant ; une observation simulée est
    nommée comme telle, jamais présentée comme un relevé réel.
    """
    if not observation.lisible:
        if observation.etat == ETAT_ABSENT:
            reason = (
                "relevé écarté avant écriture"
                if observation.ecarte_a_l_ecriture
                else "aucun relevé consigné"
            )
        elif observation.etat == ETAT_VERSION_INCONNUE:
            reason = "version de relevé non prise en charge"
        else:
            reason = "relevé hors contrat"
        return f"Contexte de l'ordinateur : {reason}"
    cpu = observation.cpu
    memory = observation.memoire_apres
    cpu_text = formater_pourcentage_premier_niveau(
        None if cpu is None else cpu.pourcentage_moyen
    )
    if (
        memory is None
        or memory.disponible_octets is None
        or memory.totale_octets is None
    ):
        ram_text = NON_MESURE
    else:
        ram_text = (
            f"{formater_memoire_premier_niveau(memory.disponible_octets)} sur "
            f"{formater_memoire_premier_niveau(memory.totale_octets)}"
        )
    prefix = "Contexte de l'ordinateur"
    if observation.simulee:
        prefix += " (scénario simulé, aucun ordinateur réel)"
    return (
        f"{prefix} : CPU total moyen {cpu_text}, "
        f"RAM disponible après l'audio {ram_text}"
    )


def transcript_lines(text: str | None) -> list[str]:
    """Texte transcrit complet, ligne à ligne, sans troncature ni comparaison."""
    if text is None:
        return ["  Aucun texte transcrit pour cet audio."]
    return text.split("\n")


def run_detail_text_lines(detail: DetailExecutionVue) -> list[str]:
    """Lignes de texte de « results show » : en-tête de l'exécution, puis audios.

    L'état, les marques de simulation et le caractère partiel sont annoncés en
    tête ; les mesures globales du lot restent distinctes du contexte de
    l'ordinateur, audio par audio.
    """
    execution = detail.execution
    header = f"Exécution {execution.identifiant} : {execution.libelle_etat}"
    if detail.partiel:
        header += " (résultats partiels)"
    header += f", créée le {execution.cree_le or 'date non consignée'}"
    lines = [header]
    if detail.simule_mesures:
        lines.append(SIMULATED_MEASURES_MESSAGE)
    lines.append(
        f"Modèle : {detail.libelle_modele}, "
        f"moteur {execution.moteur or 'non consigné'}"
    )
    if execution.audios_traites is not None and execution.audios_total is not None:
        lines.append(
            f"Audios traités : {execution.audios_traites} sur {execution.audios_total}"
        )
    lines.append(
        "Durée de l'opération : "
        f"{formater_duree_premier_niveau(detail.mesures.duree_operation_s)}"
    )
    pic = formater_memoire_premier_niveau(detail.mesures.pic_memoire_octets)
    if detail.mesures.pic_memoire_partiel:
        pic += " (partiel)"
    lines.append(f"Pic mémoire du moteur sur le lot : {pic}")
    if detail.erreur is not None:
        lines.append(f"Erreur de l'exécution : {detail.erreur}")
    if execution.marques:
        lines.append(f"Marques : {', '.join(execution.marques)}")
    for audio in detail.audios:
        lines.extend(detail_audio_text_lines(audio))
    return lines


def detail_audio_text_lines(audio: AudioVue) -> list[str]:
    """Un audio du détail : mesures du moteur, contexte, puis texte complet."""
    title = f"Audio {audio.ordre} : {audio.nom} — {audio.libelle_statut}"
    if audio.partiel:
        title += " (résultat partiel)"
    lines = [title]
    transcription = audio.transcription
    if transcription is None:
        lines.append(f"  {audio.motif_indisponible or NO_TRANSCRIPT_MESSAGE}")
        return lines
    if audio.erreur is not None:
        lines.append(f"  Erreur : {audio.erreur}")
    lines.append(
        f"  Mesures du moteur : "
        f"{engine_measures_text(audio.indicateurs, audio.annotation_ram)}"
    )
    lines.append(f"  {system_context_text(audio.observation_systeme)}")
    if audio.materiel_alerte is not None:
        lines.append(f"  {audio.materiel_alerte}")
    lines.append("  Transcription complète :")
    lines.extend(transcript_lines(transcription.texte))
    return lines


def comparison_text_lines(comparison: ComparaisonVue) -> list[str]:
    """Lignes de texte de « compare » : en-tête, synthèse, puis essais reçus.

    Les cartes suivent l'ordre reçu. La synthèse ne désigne ni score global ni
    meilleur modèle : elle reprend les distinctions du service, mesures simulées
    et résultats partiels exclus.
    """
    names = ", ".join(comparison.noms) or "fichier non consigné"
    lines = [
        f"Comparaison de {len(comparison.cartes)} transcriptions — "
        f"audio {names}, empreinte {comparison.empreinte}"
    ]
    if any(card.entree.simule for card in comparison.cartes):
        lines.append(SIMULATED_COMPARISON_MESSAGE)
    if comparison.partiel:
        lines.append(PARTIAL_COMPARISON_MESSAGE)
    lines.extend(synthesis_text_lines(comparison))
    lines.append("Ordre reçu :")
    for index, card in enumerate(comparison.cartes, start=1):
        lines.extend(card_text_lines(index, card))
    return lines


def synthesis_text_lines(comparison: ComparaisonVue) -> list[str]:
    """Distinctions descriptives de la comparaison, sans vainqueur global.

    Les mesures sont nommées par leur sélection `identifiant:ordre` quand elles
    sont exclues : deux essais simulés peuvent porter le même libellé.
    """
    summary = comparison.synthese
    lines: list[str] = []
    if summary.plus_rapides:
        lines.append(
            f"Plus rapides (mesures observées) : {', '.join(summary.plus_rapides)}"
        )
    if summary.moins_de_ram:
        lines.append(
            f"Moins de RAM (mesures observées) : {', '.join(summary.moins_de_ram)}"
        )
    if not lines:
        lines.append(NO_SYNTHESIS_MESSAGE)
    if summary.exclues:
        excluded = [
            selection_text(card.entree)
            for card in comparison.cartes
            if card.libelle in summary.exclues
        ]
        lines.append(
            "Exclues de la synthèse (simulées ou partielles) : "
            f"{', '.join(excluded)}"
        )
    return lines


def selection_text(entry: EntreeEmpreinte) -> str:
    """Sélection `identifiant:ordre` d'un essai, telle que la commande l'attend."""
    return f"{entry.execution}{SEPARATEUR_SELECTION}{entry.ordre}"


def card_text_lines(index: int, card: CarteComparaison) -> list[str]:
    """Un essai comparé : sélection, états, mesures, contexte et texte complet."""
    entry = card.entree
    lines = [
        f"{index}. {selection_text(entry)} — {card.libelle}, "
        f"moteur {entry.moteur or 'non consigné'}, "
        f"{formater_date_courte(entry.date_essai)}"
    ]
    states = etats_ligne(entry)
    if states:
        lines.append(f"  États : {', '.join(states)}")
    if card.erreur is not None:
        lines.append(f"  Erreur : {card.erreur}")
    lines.append(
        f"  Mesures du moteur : "
        f"{engine_measures_text(card.indicateurs, card.annotation_ram)}"
    )
    lines.append(f"  {system_context_text(entry.observation_systeme)}")
    if card.materiel_alerte is not None:
        lines.append(f"  {card.materiel_alerte}")
    lines.append("  Transcription complète :")
    lines.extend(transcript_lines(card.texte))
    return lines


RESULTS_LIST = CommandSpec(
    name="list",
    help_text=(
        "liste les résultats groupés par empreinte d'audio, essais observés et "
        "mesures simulées séparés, avec la sélection de chaque essai"
    ),
    configure=configure_results_list,
    run=_run_results_list,
)

RESULTS_HISTORY = CommandSpec(
    name="history",
    help_text=(
        "historique complet des exécutions enregistrées, des plus récentes aux "
        "plus anciennes"
    ),
    configure=configure_no_arguments,
    run=_run_results_history,
)

RESULTS_EXPLAIN = CommandSpec(
    name="explain",
    help_text=(
        "aide des indicateurs des résultats, même source que la page « Comprendre "
        "les indicateurs »"
    ),
    configure=configure_no_arguments,
    run=_run_results_explain,
)

def configure_results_show(parser: argparse.ArgumentParser) -> None:
    """Argument de « results show » : l'identifiant de l'exécution."""
    parser.add_argument(
        "result_id",
        metavar="ID",
        help="identifiant de l'exécution, comme dans « results list » ou "
        "« results history »",
    )


def _run_results_show(
    arguments: argparse.Namespace,
    services: DataServices,
    signal_flag: SignalFlag,
) -> int:
    """Détail d'une exécution, comme la page de résultat (lecture seule).

    Le service refuse un identifiant hostile ou inconnu (`ValeurRefusee`,
    `ResultatIntrouvable`) et un `run.json` non interprétable : code 2 dans les
    trois cas, sans trace ni fichier modifié.
    """
    output = output_from_arguments(arguments)
    try:
        detail = services.results.detail(arguments.result_id)
    except (ValeurRefusee, ResultatIntrouvable) as error:
        output.diagnostic(str(error))
        return CODE_REFUS
    except ResultatNonInterpretable:
        output.diagnostic(MESSAGE_RESULTAT_NON_INTERPRETABLE)
        return CODE_REFUS
    output.result(serialize_run_detail(detail), run_detail_text_lines(detail))
    return CODE_SUCCESS


RESULTS_SHOW = CommandSpec(
    name="show",
    help_text=(
        "détail d'une exécution : transcription complète, mesures du moteur, "
        "contexte de l'ordinateur et états simulés ou partiels"
    ),
    configure=configure_results_show,
    run=_run_results_show,
)

RESULTS = CommandGroup(
    name="results",
    help_text="consultation en lecture seule des résultats enregistrés",
    commands=(RESULTS_LIST, RESULTS_SHOW, RESULTS_HISTORY, RESULTS_EXPLAIN),
)


def selection_choice(value: str) -> tuple[str, int]:
    """Décode une sélection `identifiant:ordre` à l'analyse, sans aucune E/S.

    La forme seule est vérifiée ici (`analyser_selection`) ; l'appartenance au
    groupe et les bornes restent du service `comparer`.
    """
    try:
        return analyser_selection(value)
    except ValeurRefusee as error:
        raise argparse.ArgumentTypeError(str(error)) from None


def configure_compare(parser: argparse.ArgumentParser) -> None:
    """Arguments de « compare » : empreinte de l'audio puis sélections ordonnées."""
    parser.add_argument(
        "audio_hash",
        metavar="AUDIO_HASH",
        help="empreinte SHA-256 de l'audio, comme le groupe de « results list »",
    )
    parser.add_argument(
        "selections",
        metavar="SEL",
        nargs="+",
        type=selection_choice,
        help="sélection identifiant:ordre d'un essai du groupe ; de 2 à "
        f"{SELECTIONS_MAX_COMPARAISON} sélections, l'ordre reçu est conservé",
    )


def _run_compare(
    arguments: argparse.Namespace,
    services: DataServices,
    signal_flag: SignalFlag,
) -> int:
    """Comparaison côte à côte d'essais d'un même audio, en lecture seule.

    Le service refuse, avant toute lecture de transcription, une empreinte
    invalide, plus de `SELECTIONS_MAX_COMPARAISON` sélections, moins de deux
    essais distincts, une sélection hors du groupe ou inconnue : code 2.
    """
    output = output_from_arguments(arguments)
    try:
        comparison = services.results.comparer(
            arguments.audio_hash, arguments.selections
        )
    except (ValeurRefusee, ResultatIntrouvable) as error:
        output.diagnostic(str(error))
        return CODE_REFUS
    except ResultatNonInterpretable:
        output.diagnostic(MESSAGE_RESULTAT_NON_INTERPRETABLE)
        return CODE_REFUS
    output.result(
        serialize_comparison(comparison), comparison_text_lines(comparison)
    )
    return CODE_SUCCESS


COMPARE = CommandSpec(
    name="compare",
    help_text=(
        "compare des essais d'un même audio (2 à "
        f"{SELECTIONS_MAX_COMPARAISON} sélections identifiant:ordre, ordre reçu)"
    ),
    configure=configure_compare,
    run=_run_compare,
)

#: Enregistrement public : groupes « audios », « data », « engines »,
#: « models », « results » et « run », et commande racine « compare », sans
#: commande future vide. `cli` y ajoute `serve` et refuse les doublons.
COMMANDS: tuple[CommandSpec | CommandGroup, ...] = (
    AUDIOS,
    DATA,
    ENGINES,
    MODELS,
    RESULTS,
    RUN,
    COMPARE,
)
