"""Composition des services et sessions d'un dossier de données (tâches 1.1 et 1.5).

Ce module est le seul endroit où les services du prototype sont reliés entre
eux à partir du dossier de données. Deux sessions l'utilisent :

- les commandes de la CLI ouvrent `open_data_session`, qui relie tous les
  services, y compris le créneau d'opération et la supervision de moteur ;
- le serveur ouvre `open_serve_session`, qui ne relie que la consultation des
  résultats : il ne construit ni créneau ni supervision (change
  `alleger-interface-web`, D4).

Ordre d'ouverture commun, inchangé : verrou d'instance, récupération des
exécutions antérieures, préparation de `data/`. Les sessions de commande
construisent ensuite les services. La clôture de `DataSession` passe par
`NettoyageArret` : arrêt du créneau, du moteur et de l'installation, puis
libération du verrou en dernier ; celle de `ServeSession` libère seulement le
verrou. Aucune bibliothèque de moteur n'est importée ici ; aucune construction
de service ne lit ni n'écrit de fichier.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from types import TracebackType

from engines.registre import RegistreMoteurs, creer_registre_fourni
from transcription_bench import paths
from transcription_bench.audios import AudioListe, lister_audios
from transcription_bench.consultation_resultats import ConsultationResultats
from transcription_bench.execution_extraction import ExtractionExecution
from transcription_bench.execution_moteur import ExecutionMoteur
from transcription_bench.executions import ConfigurationExecutions
from transcription_bench.extractions import ExtractionConfiguration
from transcription_bench.gestion_modeles import GestionModeles
from transcription_bench.instance import InstanceDejaActive, VerrouInstance
from transcription_bench.moteurs import InstallationMoteurs
from transcription_bench.operations import CreneauOperations
from transcription_bench.recuperation import (
    EtatAnterieurNonTraitable,
    recuperer_executions_anterieures,
)
from transcription_bench.supervision import NettoyageArret


@dataclass(frozen=True)
class DataServices:
    """Services reliés pour un même dossier de données.

    `data_dir` est la racine des données de la session : les commandes de la
    CLI y trouvent le dossier dont elles décrivent l'état, sans le déduire
    d'une globale. `operations` est l'unique créneau d'opération longue ;
    `engines` le service d'installation, `models` la gestion des modèles,
    `preparation` la préparation des exécutions, `execution` le lancement
    supervisé et `results` la consultation en lecture seule. `extraction_preparation`
    et `extraction_execution` sont les équivalents de la préparation et du lancement
    pour les extractions (tâche 3.5) ; ils partagent le même créneau.
    """

    data_dir: Path
    operations: CreneauOperations
    registry: RegistreMoteurs
    engines: InstallationMoteurs
    models: GestionModeles
    preparation: ConfigurationExecutions
    execution: ExecutionMoteur
    results: ConsultationResultats
    extraction_preparation: ExtractionConfiguration
    extraction_execution: ExtractionExecution


def assemble_services(
    data_dir: Path,
    *,
    operations: CreneauOperations,
    registry: RegistreMoteurs | None = None,
    engines: InstallationMoteurs | None = None,
    models: GestionModeles | None = None,
    preparation: ConfigurationExecutions | None = None,
    execution: ExecutionMoteur | None = None,
    results: ConsultationResultats | None = None,
    extraction_preparation: ExtractionConfiguration | None = None,
    extraction_execution: ExtractionExecution | None = None,
    lister: Callable[[Path], tuple[AudioListe, ...]] = lister_audios,
) -> DataServices:
    """Relie les services dans l'ordre de dépendance.

    Un service fourni est repris tel quel ; un service absent est construit à
    partir des précédents. Aucune E/S : les constructeurs ne touchent pas au
    disque ni au réseau.
    """
    resolved_registry = creer_registre_fourni() if registry is None else registry
    resolved_engines = (
        InstallationMoteurs(data_dir, resolved_registry, operations)
        if engines is None
        else engines
    )
    resolved_models = (
        GestionModeles(data_dir, resolved_registry, operations, resolved_engines)
        if models is None
        else models
    )
    resolved_preparation = (
        ConfigurationExecutions(
            data_dir, resolved_registry, resolved_models.inventaire, lister=lister
        )
        if preparation is None
        else preparation
    )
    resolved_execution = (
        ExecutionMoteur(data_dir, resolved_registry, resolved_engines)
        if execution is None
        else execution
    )
    resolved_results = (
        ConsultationResultats(data_dir) if results is None else results
    )
    resolved_extraction_preparation = (
        ExtractionConfiguration(data_dir, resolved_registry, resolved_models.inventaire)
        if extraction_preparation is None
        else extraction_preparation
    )
    resolved_extraction_execution = (
        ExtractionExecution(data_dir, resolved_registry, resolved_engines)
        if extraction_execution is None
        else extraction_execution
    )
    return DataServices(
        data_dir=data_dir,
        operations=operations,
        registry=resolved_registry,
        engines=resolved_engines,
        models=resolved_models,
        preparation=resolved_preparation,
        execution=resolved_execution,
        results=resolved_results,
        extraction_preparation=resolved_extraction_preparation,
        extraction_execution=resolved_extraction_execution,
    )


class SessionRefused(RuntimeError):
    """Refus d'ouvrir la session : le message est à afficher, sans trace.

    `lock_released` vaut faux seulement si le refus suit une prise de verrou
    dont la libération a échoué ; la commande doit alors se terminer en échec
    (code 1), comme l'ancienne CLI.
    """

    def __init__(
        self, message: str, *, lock_released: bool = True,
        diagnostics: tuple[str, ...] = (),
    ) -> None:
        super().__init__(message)
        self.lock_released = lock_released
        self.diagnostics = diagnostics


class ServeSession:
    """Session du serveur : verrou tenu, récupération faite, consultation seule.

    Le serveur ne démarre aucune opération : sa clôture libère le verrou
    d'instance, sans moteur ni créneau à arrêter. L'appelant doit appeler `close`
    une seule fois, dans un `finally`, après l'usage de `results`.
    """

    def __init__(self, results: ConsultationResultats, cleanup: NettoyageArret) -> None:
        self.results = results
        self._cleanup = cleanup

    def close(self) -> bool:
        """Libère le verrou ; `False` si la libération a échoué."""
        return self._cleanup.executer()


class DataSession:
    """Session ouverte : verrou tenu, récupération faite, services prêts.

    L'appelant doit appeler `close` une seule fois, dans un `finally`, après
    l'usage des services.
    """

    def __init__(self, services: DataServices, cleanup: NettoyageArret) -> None:
        self.services = services
        self._cleanup = cleanup

    def __enter__(self) -> DataSession:
        return self

    def __exit__(
        self,
        error_type: type[BaseException] | None,
        error: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()

    def close(self) -> bool:
        """Clôt l'arrêt puis libère le verrou ; `False` si la clôture est incomplète."""
        return self._cleanup.executer()


def _prendre_verrou_et_recuperer(
    data_dir: Path, recover: Callable[[Path], None] | None
) -> VerrouInstance:
    """Prend le verrou d'instance, récupère et prépare `data/`.

    Lève `SessionRefused` si une autre instance tient le verrou, si le verrou
    est indisponible ou si un état antérieur n'est pas traitable. Toute autre
    exception libère le verrou puis se propage. `recover` remplace la
    récupération par défaut dans les tests.
    """
    try:
        lock = VerrouInstance(data_dir).acquerir()
    except InstanceDejaActive as erreur:
        raise SessionRefused(str(erreur)) from None
    except OSError as erreur:
        raise SessionRefused(
            f"verrou d'instance indisponible dans {data_dir} : {erreur}"
        ) from None

    recovery = recuperer_executions_anterieures if recover is None else recover
    try:
        recovery(data_dir)
        paths.preparer_dossiers_data(data_dir)
    except EtatAnterieurNonTraitable as erreur:
        diagnostics: list[str] = []
        release_ok = NettoyageArret(verrou=lock, journal=diagnostics.append).executer()
        raise SessionRefused(
            str(erreur), lock_released=release_ok, diagnostics=tuple(diagnostics)
        ) from None
    except BaseException:
        NettoyageArret(verrou=lock).executer()
        raise
    return lock


def open_data_session(
    data_dir: Path,
    *,
    recover: Callable[[Path], None] | None = None,
) -> DataSession:
    """Prend le verrou, récupère, prépare `data/` et construit les services.

    Mêmes refus que `_prendre_verrou_et_recuperer`. Toute autre exception libère
    le verrou puis se propage. Ce sont les seules sessions qui construisent le
    créneau d'opération et la supervision de moteur, pour les commandes.
    """
    lock = _prendre_verrou_et_recuperer(data_dir, recover)
    try:
        operations = CreneauOperations()
        services = assemble_services(data_dir, operations=operations)
    except BaseException:
        NettoyageArret(verrou=lock).executer()
        raise

    cleanup = NettoyageArret(
        verrou=lock,
        creneau=operations,
        execution=services.execution,
        installation=services.engines,
        extraction=services.extraction_execution,
    )
    return DataSession(services, cleanup)


def open_serve_session(
    data_dir: Path,
    *,
    recover: Callable[[Path], None] | None = None,
) -> ServeSession:
    """Prend le verrou, récupère, prépare `data/` et relie la seule consultation.

    Mêmes refus et même récupération que `open_data_session`, donc avant toute
    consultation. Aucun créneau d'opération ni supervision de moteur n'est
    construit : le serveur n'en a pas besoin.
    """
    lock = _prendre_verrou_et_recuperer(data_dir, recover)
    return ServeSession(ConsultationResultats(data_dir), NettoyageArret(verrou=lock))
