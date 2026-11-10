"""Session des commandes à résultat unique : verrou, récupération, services (tâche 1.3).

Une commande qui lit ou modifie `data/` s'exécute dans `run_session` : la session
est ouverte par `composition.open_data_session` (verrou d'instance, récupération
des exécutions antérieures, préparation de `data/`, services reliés), l'action
reçoit les services, puis la session est close dans un `finally`. La clôture
passe par `NettoyageArret` et libère le verrou en dernier, y compris quand
l'action échoue ou qu'une interruption (`KeyboardInterrupt`, `SystemExit`) la
traverse : l'exception continue alors de se propager vers l'appelant.

Codes : un refus d'ouverture (verrou tenu par le serveur ou une autre commande,
état antérieur non traitable) est affiché sans trace et donne `CODE_REFUS`,
sans appel de l'action ; une clôture incomplète (thread de fond encore actif)
donne `CODE_ECHEC`, sauf après un signal d'arrêt : elle donne alors
`CODE_INTERRUPTED` (tâche 1.5).

Signaux (tâche 1.5) : `run_session` arme un `SignalFlag` avant l'ouverture de la
session et le passe à l'action, qui le consulte ; un signal reçu pendant la
récupération n'interrompt donc rien brutalement, et l'action n'est pas appelée.

`CommandSpec` décrit une commande pour `cli` : nom, aide, arguments et action.
`CommandGroup` rassemble des feuilles sous un même nom de groupe. Les commandes
publiques (groupes « audios », « data », …) vivent dans
`transcription_bench.commands` ; les tests injectent leurs propres commandes.
"""

from __future__ import annotations

import argparse
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from transcription_bench.composition import (
    DataServices,
    SessionRefused,
    open_data_session,
)
from transcription_bench.supervision import SignalFlag, signaler

CODE_SUCCESS = 0
CODE_ECHEC = 1
CODE_REFUS = 2
#: Interruption par signal ; garde ce code même si la clôture reste incomplète.
CODE_INTERRUPTED = 3


@dataclass(frozen=True)
class CommandSpec:
    """Commande exécutée dans une session de données.

    `configure` ajoute ses arguments au sous-analyseur ; `run` reçoit les
    arguments analysés, les services de la session et le drapeau d'arrêt, puis
    renvoie le code de sortie de la commande.
    """

    name: str
    help_text: str
    configure: Callable[[argparse.ArgumentParser], None]
    run: Callable[[argparse.Namespace, DataServices, SignalFlag], int]


@dataclass(frozen=True)
class CommandGroup:
    """Groupe de sous-commandes publié sous un même nom (par exemple « audios »).

    Le groupe porte l'aide commune ; ses feuilles sont des `CommandSpec`
    enregistrées comme sous-commandes du groupe. Aucun argument ne s'ajoute au
    groupe lui-même : ni `--json` ni option, tout appartient aux feuilles, et une
    invocation sans feuille est refusée à l'analyse des arguments (code 2).
    """

    name: str
    help_text: str
    commands: tuple[CommandSpec, ...]


def run_session(
    data_dir: Path,
    action: Callable[[DataServices, SignalFlag], int],
    *,
    recover: Callable[[Path], None] | None = None,
    report: Callable[[str], None] = signaler,
) -> int:
    """Ouvre la session, exécute `action` avec les services, puis clôt toujours.

    Le drapeau d'arrêt est armé avant l'ouverture et désarmé après la clôture.
    `recover` remplace la récupération par défaut dans les tests ; `report`
    reçoit les lignes de refus (sortie d'erreur par défaut). Une exception de
    l'action n'est pas interceptée : la session est close, puis elle se propage.
    """
    with SignalFlag() as signal_flag:
        return _run_session(data_dir, action, signal_flag, recover, report)


def _run_session(
    data_dir: Path,
    action: Callable[[DataServices, SignalFlag], int],
    signal_flag: SignalFlag,
    recover: Callable[[Path], None] | None,
    report: Callable[[str], None],
) -> int:
    """Corps de `run_session`, drapeau déjà armé par l'appelant."""
    try:
        session = open_data_session(data_dir, recover=recover)
    except SessionRefused as refusal:
        report(str(refusal))
        for diagnostic in refusal.diagnostics:
            report(diagnostic)
        return CODE_REFUS if refusal.lock_released else CODE_ECHEC
    try:
        if signal_flag.received:
            report("arrêt demandé avant le début de la commande : rien n'a été lancé.")
            code = CODE_INTERRUPTED
        else:
            code = action(session.services, signal_flag)
    finally:
        closed = session.close()
        if signal_flag.received and not closed:
            signal_flag.ignore_until_exit()
    # Après un signal, une clôture incomplète reste un arrêt : code 3, le
    # message de clôture venant du nettoyage de la session.
    if code == CODE_INTERRUPTED or signal_flag.received:
        return CODE_INTERRUPTED
    return code if closed else CODE_ECHEC
