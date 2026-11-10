"""Suivi d'une opération longue par une commande : journal, arrêt, code (tâche 1.5).

Une commande qui lance une opération du créneau (installation, téléchargement,
vérification, exécution) ne l'attend pas par `join()` : `OperationWatch.attendre`
relit l'état du créneau à intervalle court, écrit chaque nouvelle ligne du
journal dès qu'elle existe, puis rend le code de sortie de la commande.

- Curseur : la position écrite dans le journal suit la génération de
  l'opération. Le journal repart de zéro à chaque admission : un enchaînement
  (vérification puis téléchargement) est écrit en entier, sans doublon ni perte.
- Signal : `SignalFlag` ne lève rien. Au premier signal constaté, la boucle
  engage l'arrêt une seule fois : le créneau passe à l'arrêt (aucun marqueur prêt
  publié ensuite), une exécution est arrêtée comme par l'utilisateur
  (`arreter_execution()`, sans motif serveur), le sous-processus d'installation
  est arrêté. L'attente suivante est bornée par `close_timeout`.
- Code : une opération `interrompue`, ou encore en cours à l'échéance après un
  signal, donne `CODE_INTERRUPTED`. Sinon le code vient du résultat métier fourni
  par l'appelant (`translate`) : l'état `terminee` du créneau ne dit pas si une
  vérification a été acceptée ni si une exécution est sans erreur.
- Clôture : la fermeture de la session (`NettoyageArret`) reste celle de
  `run_session`. Si le thread de fond survit, le message de clôture incomplète
  vient de ce nettoyage et le code 3 est conservé par `run_session`.
"""

from __future__ import annotations

import time
from collections.abc import Callable

from transcription_bench.command_session import (
    CODE_ECHEC,
    CODE_INTERRUPTED,
    CODE_SUCCESS,
)
from transcription_bench.execution_moteur import (
    ARRET_SURVIVANT,
    ExecutionMoteur,
    ResultatExecution,
)
from transcription_bench.execution_moteur import (
    ETAT_INTERROMPUE as ETAT_EXECUTION_INTERROMPUE,
)
from transcription_bench.execution_moteur import (
    ETAT_TERMINEE as ETAT_EXECUTION_TERMINEE,
)
from transcription_bench.moteurs import InstallationMoteurs
from transcription_bench.operations import (
    ETAT_EN_COURS,
    ETAT_INTERROMPUE,
    ETAT_LIBRE,
    CreneauOperations,
    InstantaneCreneau,
)
from transcription_bench.output import CommandOutput
from transcription_bench.supervision import DELAI_OPERATION_S, SignalFlag

#: Intervalle de sondage du créneau : court, pour rester interruptible (y compris
#: sous Windows, où `join()` avec délai ne réagit pas à Ctrl+C).
POLL_INTERVAL_S = 0.05
#: Attente après un signal, avant de rendre la main sans attendre davantage.
CLOSE_TIMEOUT_S = DELAI_OPERATION_S

LOG_EVENT = "log"
EVENT_KEY = "event"

SIGNAL_STOP_MESSAGE = "arrêt demandé par signal : clôture de l'opération en cours."
SURVIVING_ENGINE_MESSAGE = (
    "le processus moteur survit à l'arrêt : sa fin réelle reste attendue."
)


class OperationWatch:
    """Suit l'opération admise au créneau et rend le code de la commande.

    Une instance peut suivre plusieurs opérations successives d'une même commande
    (vérification puis téléchargement) : le curseur repart alors de zéro avec la
    génération. `wait` doit être appelé juste après l'admission.
    """

    def __init__(
        self,
        operations: CreneauOperations,
        signal_flag: SignalFlag,
        output: CommandOutput,
        *,
        execution: ExecutionMoteur | None = None,
        installation: InstallationMoteurs | None = None,
        poll_interval: float = POLL_INTERVAL_S,
        close_timeout: float = CLOSE_TIMEOUT_S,
    ) -> None:
        self._operations = operations
        self._signal_flag = signal_flag
        self._output = output
        self._execution = execution
        self._installation = installation
        self._poll_interval = poll_interval
        self._close_timeout = close_timeout
        self._generation: int | None = None
        self._cursor = 0
        self._stop_started = False
        self._deadline: float | None = None

    def wait(self, translate: Callable[[InstantaneCreneau], int]) -> int:
        """Suit l'opération jusqu'à sa fin, puis rend son code de sortie.

        `translate` reçoit l'état final du créneau seulement si l'opération n'a
        pas été interrompue ; il renvoie le code du résultat métier (par exemple
        `execution_exit_code`). Lève `RuntimeError` si aucune opération n'est admise.
        """
        if self._operations.instantane().etat == ETAT_LIBRE:
            raise RuntimeError("aucune opération admise à suivre")
        while True:
            snapshot = self._operations.instantane()
            self._emit(snapshot)
            thread = self._operations.thread_travailleur
            if snapshot.etat != ETAT_EN_COURS and (thread is None or not thread.is_alive()):
                break
            if self._signal_flag.received and not self._stop_started:
                self._start_stop()
                continue
            if self._deadline is not None and time.monotonic() >= self._deadline:
                break
            time.sleep(self._poll_interval)
        if self._signal_flag.received or snapshot.etat in (ETAT_EN_COURS, ETAT_INTERROMPUE):
            return CODE_INTERRUPTED
        return translate(snapshot)

    def _emit(self, snapshot: InstantaneCreneau) -> None:
        """Écrit les lignes du journal non encore écrites, pour cette génération."""
        if snapshot.generation != self._generation:
            self._generation = snapshot.generation
            self._cursor = 0
        for line in snapshot.journal[self._cursor:]:
            self._output.event(
                {
                    EVENT_KEY: LOG_EVENT,
                    "operation": snapshot.type_operation,
                    "generation": snapshot.generation,
                    "line": line,
                },
                line,
            )
        self._cursor = len(snapshot.journal)

    def _start_stop(self) -> None:
        """Arrête l'opération une seule fois, sans attendre sa fin."""
        self._stop_started = True
        self._output.diagnostic(SIGNAL_STOP_MESSAGE)
        # Refuse toute publication de marqueur prêt ensuite, même si l'opération
        # finit son travail pendant la clôture.
        self._operations.passer_a_l_arret()
        if self._execution is not None and self._execution.en_cours():
            # Arrêt demandé comme par l'utilisateur, non par le serveur : le journal
            # du créneau nomme ce motif, comme la page web.
            try:
                outcome = self._execution.arreter_execution()
            except Exception as error:
                self._output.diagnostic(f"arrêt du moteur impossible : {type(error).__name__}")
            else:
                if outcome == ARRET_SURVIVANT:
                    self._output.diagnostic(SURVIVING_ENGINE_MESSAGE)
        if self._installation is not None:
            try:
                self._installation.arreter()
            except Exception as error:
                self._output.diagnostic(f"arrêt de l'installation impossible : {type(error).__name__}")
        self._deadline = time.monotonic() + self._close_timeout


def execution_exit_code(result: ResultatExecution | None) -> int:
    """Code de sortie d'une exécution, déduit de son résultat métier.

    `interrompue` donne 3 ; un échec, l'absence de résultat ou un audio en erreur
    donne 1 ; une exécution `terminee` sans audio en erreur donne 0.
    """
    if result is None:
        return CODE_ECHEC
    if result.etat == ETAT_EXECUTION_INTERROMPUE:
        return CODE_INTERRUPTED
    if result.etat != ETAT_EXECUTION_TERMINEE or result.audios_en_erreur:
        return CODE_ECHEC
    return CODE_SUCCESS
