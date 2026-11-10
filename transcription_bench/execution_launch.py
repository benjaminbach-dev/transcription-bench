"""Enchaînement de lancement d'une exécution, commun à la route web et à la CLI.

Ordre fixe, identique à la route d'origine : refus des champs répétés, validation
de la demande, contrôle du moteur (`verifier_lancable`), réservation de
l'exécution (`reserver`) avant son admission dans le créneau, puis annulation de
la réservation si l'admission est refusée. La réservation précède l'admission
pour qu'un arrêt demandé entre les deux ne soit pas perdu (design D3).

Aucune dépendance Flask : le formulaire arrive sous forme de paires multivaluées
(`request.form.items(multi=True)` côté web, équivalent côté CLI), que l'appelant
construit à sa frontière. Les refus sont remontés sous forme d'exceptions :
`ValeurRefusee` pour la demande, `EngineNotReady` pour le moteur,
`ExecutionAlreadyReserved` pour une réservation déjà posée, et les exceptions du
créneau (`CreneauOccupe`, `ServiceArrete`) telles quelles.
"""

from __future__ import annotations

from collections.abc import Sequence

from transcription_bench.execution_moteur import ExecutionImpossible, ExecutionMoteur
from transcription_bench.executions import (
    ConfigurationExecutions,
    DemandeExecution,
    refuser_champs_repetes,
    reglages_depuis_formulaire,
)
from transcription_bench.operations import TYPE_EXECUTION, CreneauOperations

#: Champs multivalués d'un formulaire : paires `(nom, valeur)` dans l'ordre reçu.
FormFields = Sequence[tuple[str, str]]


class EngineNotReady(RuntimeError):
    """Le moteur de la demande n'est pas prêt : rien n'a été réservé."""


class ExecutionAlreadyReserved(RuntimeError):
    """Une exécution est déjà réservée ou active : la réservation existante est intacte."""


def _first_value(fields: FormFields, name: str) -> str | None:
    """Première valeur du champ, comme `request.form.get` ; `None` si absent."""
    for field_name, value in fields:
        if field_name == name:
            return value
    return None


def _all_values(fields: FormFields, name: str) -> list[str]:
    """Toutes les valeurs du champ, dans l'ordre reçu, comme `getlist`."""
    return [value for field_name, value in fields if field_name == name]


def validate_execution_fields(
    preparation: ConfigurationExecutions, fields: FormFields
) -> DemandeExecution:
    """Refuse les champs répétés puis valide la demande ; lève `ValeurRefusee`.

    Les champs uniques (`modele`, `moteur`, `threads`, `reglage_*`) sont refusés
    avant toute validation. Les réglages restent donc sans ambiguïté lorsqu'ils
    sont convertis en mapping.
    """
    refuser_champs_repetes(fields)
    return preparation.valider(
        modele=_first_value(fields, "modele") or "",
        audios=_all_values(fields, "audios"),
        threads=_first_value(fields, "threads") or "",
        reglages=reglages_depuis_formulaire(dict(fields)),
        moteur=_first_value(fields, "moteur"),
    )


def launch_execution(
    preparation: ConfigurationExecutions,
    execution: ExecutionMoteur,
    operations: CreneauOperations,
    fields: FormFields,
) -> DemandeExecution:
    """Valide, réserve puis admet l'exécution dans le créneau ; renvoie la demande.

    Lève `ValeurRefusee` si la demande est invalide, `EngineNotReady` si le moteur
    n'est pas prêt, `ExecutionAlreadyReserved` si une réservation existe déjà
    (sans l'annuler, puisqu'elle appartient à une autre exécution), et laisse
    passer `CreneauOccupe` ou `ServiceArrete` après avoir annulé la réservation.
    Toute autre exception annule aussi la réservation avant d'être relevée.
    """
    request = validate_execution_fields(preparation, fields)
    try:
        execution.verifier_lancable(request)
    except ExecutionImpossible as exception:
        raise EngineNotReady(str(exception)) from exception
    try:
        execution.reserver()
    except ExecutionImpossible as exception:
        raise ExecutionAlreadyReserved(str(exception)) from exception
    try:
        operations.demarrer(
            TYPE_EXECUTION,
            lambda worker: execution.lancer(request, worker),
            cible=request.identifiant,
        )
    except BaseException:
        # Admission refusée ou interrompue : la réservation posée ci-dessus est
        # libérée, sans quoi un arrêt ultérieur viserait une exécution fantôme.
        execution.annuler_reservation()
        raise
    return request
