"""Historique combiné des exécutions, transcription et extraction (tâche 4.2).

Source unique, partagée par la commande `results history` et, plus tard, par
la page Historique (tâche 4.3, non construite ici) : une seule fusion des deux
services de consultation en lecture seule (`ConsultationResultats` pour les
transcriptions, `ExtractionConsultation` pour les extractions), sans écriture
ni accès réseau. `historique_combine` ne lit rien de plus que `lister()` et
`list_runs()` n'ont déjà lu ; les exécutions non interprétables des deux
services restent présentes, sans qu'aucun fait ne soit inventé pour elles.

Tri : date réelle (`cree_le` / `created_at`) décroissante, toutes exécutions
confondues ; une date absente ou illisible passe en fin, les égalités se
départagent par identifiant décroissant. Les identifiants des deux dossiers
(`data/results/` et `data/extractions/`) suivent le même format d'horodatage :
aucune collision n'est résolue spécialement, le type distingue chaque entrée.

`combined_history` est la seule fonction publique : nom anglais, comme tout
identifiant nouveau de ce module (seuls les noms de champs JSON hérités des
vues existantes restent français).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from transcription_bench.consultation_resultats import ConsultationResultats, ExecutionListee
from transcription_bench.extraction_consultation import ExtractionConsultation, RunSummary

#: Discriminant `type` d'une ligne d'historique.
HISTORY_TYPE_TRANSCRIPTION = "transcription"
HISTORY_TYPE_EXTRACTION = "extraction"


@dataclass(frozen=True)
class HistoryEntry:
    """Ligne unifiée de l'historique : transcription ou extraction, avec son type.

    `items_processed` et `items_total` reprennent les audios traités pour une
    transcription, les sources traitées pour une extraction. `exploitable` vaut
    `False` pour une exécution dont le fichier de suivi n'a pas pu être
    interprété : seuls `type`, `identifiant` et `motif` sont alors garantis.
    """

    type: str
    identifiant: str
    etat: str | None
    libelle_etat: str
    cree_le: str | None
    modele: str | None
    moteur: str | None
    items_processed: int | None
    items_total: int | None
    duree_operation_s: float | None
    partiel: bool | None
    marques: tuple[str, ...] | None
    exploitable: bool
    motif: str | None


def _transcription_entry(view: ExecutionListee) -> HistoryEntry:
    return HistoryEntry(
        type=HISTORY_TYPE_TRANSCRIPTION,
        identifiant=view.identifiant,
        etat=view.etat,
        libelle_etat=view.libelle_etat,
        cree_le=view.cree_le,
        modele=view.modele,
        moteur=view.moteur,
        items_processed=view.audios_traites,
        items_total=view.audios_total,
        duree_operation_s=view.duree_operation_s,
        partiel=view.partiel,
        marques=view.marques,
        exploitable=view.exploitable,
        motif=view.motif,
    )


def _extraction_entry(view: RunSummary) -> HistoryEntry:
    return HistoryEntry(
        type=HISTORY_TYPE_EXTRACTION,
        identifiant=view.run_id,
        etat=view.state,
        libelle_etat=view.state_label,
        cree_le=view.created_at,
        modele=view.model,
        moteur=view.engine,
        items_processed=view.sources_processed,
        items_total=view.sources_total,
        duree_operation_s=view.duration_operation_s,
        partiel=view.partial,
        marques=view.marks,
        exploitable=view.usable,
        motif=view.reason,
    )


def _date_key(value: Any) -> tuple[int, float]:
    """Clé de tri : une date connue (`1`) passe avant une date inconnue (`0`)."""
    if not isinstance(value, str):
        return (0, 0.0)
    try:
        date = datetime.fromisoformat(value)
    except ValueError:
        return (0, 0.0)
    if date.tzinfo is None:
        date = date.replace(tzinfo=timezone.utc)
    try:
        return (1, date.timestamp())
    except (OverflowError, OSError, ValueError):
        return (0, 0.0)


def combined_history(
    resultats: ConsultationResultats, extractions: ExtractionConsultation
) -> tuple[HistoryEntry, ...]:
    """Historique fusionné des transcriptions et extractions.

    Des plus récentes aux plus anciennes par date réelle consignée ; une date
    absente ou illisible passe en fin, les égalités se départagent par
    identifiant décroissant. Aucune exécution, interprétable ou non, ne
    disparaît. Lève `LectureResultatsImpossible` si l'un des deux dossiers
    existe mais ne peut pas être parcouru.
    """
    entries: list[HistoryEntry] = [
        *(_transcription_entry(view) for view in resultats.lister()),
        *(_extraction_entry(view) for view in extractions.list_runs()),
    ]
    entries.sort(key=lambda entry: (_date_key(entry.cree_le), entry.identifiant), reverse=True)
    return tuple(entries)
