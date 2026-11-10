"""Supervision d'arrêt de la CLI, indépendante de Flask (tâche 6.6).

Ce module contient les deux pièces de l'arrêt normal du serveur, volontairement
hors de la couche web :

1. `GestionnaireSignaux` installe le **même** gestionnaire pour `SIGINT` et,
   sous Linux, `SIGTERM`. Dès le premier signal, il remet ces signaux à
   `SIG_IGN`, puis lève `KeyboardInterrupt` (SIGINT) ou `SystemExit` (SIGTERM).
   Les signaux suivants sont donc ignorés pendant l'arrêt de Waitress comme
   pendant le nettoyage ; ils ne peuvent plus interrompre une clôture en cours.
   Après un signal reçu, les anciens gestionnaires ne sont pas rétablis : le
   `SIG_IGN` reste en place jusqu'à la sortie réelle du processus.
2. `NettoyageArret` exécute une seule fois, dans un ordre fixe, la clôture
   applicative après le retour de `waitress.serve` : passage du créneau à l'arrêt
   sous son verrou **sans attendre**, terminaison bornée du moteur d'exécution et
   du sous-processus d'installation, attente bornée du thread d'opération, puis
   libération du verrou d'instance **en dernier**, seulement si ce thread est
   réellement terminé. Sinon le verrou reste détenu jusqu'à la fin du processus
   et le journal l'indique : aucun thread Python n'est tué.

Ce nettoyage n'est jamais placé dans un `teardown_appcontext` (appelé à la fin
de chaque requête) ni dans un handler HTTP : il dépend uniquement de la sortie
de l'appel public `waitress.serve()`, encadré par un `try/finally` dans la CLI.
Aucune API privée de Waitress (`create_server`, `close`, `task_dispatcher`) n'est
utilisée.

Limites assumées (design D5, D11) : un téléchargement exécuté dans le processus
serveur peut encore attendre ses E/S et ses threads internes, même si le thread
d'opération est démon ; aucun délai global de sortie n'est garanti pendant un
téléchargement. La descendance du moteur et de l'installation est relevée avant
le signal puis attendue et tuée si elle y survit, mais un descendant créé après
ce relevé échappe à la supervision. Un moteur insensible au signal de forçage
garde le créneau occupé jusqu'à sa fin réelle. Tuer le processus ou fermer la
console après le premier signal constitue un arrêt brutal, traité au démarrage
suivant par la récupération des exécutions abandonnées (tâche 6.5). Aucune
relance du serveur dans le même processus n'est prévue.

Rien ici ne constitue une validation PC : Ctrl+C sous Windows, `uv run` et le
double Ctrl+C restent à éprouver par la sonde 1.7, puis l'arrêt du moteur réel
sur chaque OS par les tâches 8.x.
"""

from __future__ import annotations

import os
import signal
import sys
import threading
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from types import FrameType
from typing import Any

from transcription_bench.execution_moteur import ARRET_SURVIVANT, ExecutionMoteur
from transcription_bench.instance import VerrouInstance
from transcription_bench.moteurs import InstallationMoteurs
from transcription_bench.operations import CreneauOperations

#: Délai d'attente du thread d'opération après l'arrêt du moteur et de
#: l'installation, en secondes. Chaque terminaison de processus est elle-même
#: bornée par `ProcessusMoteur` et `ExecuteurSubprocess`.
DELAI_OPERATION_S = 10.0
#: Code de sortie associé à `SystemExit` sur SIGTERM : arrêt normal demandé.
CODE_ARRET_SIGTERM = 0


def signaux_arret_normal() -> tuple[int, ...]:
    """Signaux d'arrêt normal : SIGINT partout, SIGTERM sous Linux seulement."""
    if os.name == "nt":
        return (signal.SIGINT,)
    return (signal.SIGINT, signal.SIGTERM)


class GestionnaireSignaux:
    """Gestionnaire unique des signaux d'arrêt normal, posé autour de `serve`.

    Le premier signal reçu remet ces signaux à `SIG_IGN` avant de lever
    l'exception : les suivants ne peuvent plus interrompre l'arrêt de Waitress ni
    le nettoyage. `restaurer` ne rétablit les anciens gestionnaires que si aucun
    signal n'a été reçu, sauf demande explicite des tests.
    """

    def __init__(self, signaux: Sequence[int] | None = None) -> None:
        self._signaux = tuple(signaux_arret_normal() if signaux is None else signaux)
        self._precedents: dict[int, Any] = {}
        self._installe = False
        self._recu = False

    @property
    def signaux(self) -> tuple[int, ...]:
        """Signaux surveillés, dans l'ordre d'installation."""
        return self._signaux

    @property
    def recu(self) -> bool:
        """Vrai si un signal a déjà été traité par ce gestionnaire."""
        return self._recu

    @property
    def installe(self) -> bool:
        """Vrai si les gestionnaires sont actuellement posés."""
        return self._installe

    def installer(self) -> None:
        """Pose le gestionnaire, en mémorisant les précédents."""
        if self._installe:
            return
        self._precedents = {numero: signal.getsignal(numero) for numero in self._signaux}
        self._installe = True
        for numero in self._signaux:
            signal.signal(numero, self.traiter)

    def restaurer(self, *, force: bool = False) -> None:
        """Rétablit les gestionnaires précédents, sauf après un signal reçu.

        Après un signal, `SIG_IGN` est conservé jusqu'à la sortie du processus :
        un Ctrl+C supplémentaire ne doit pas interrompre la clôture. `force`
        n'est utilisé que par les tests qui ont simulé un signal dans leur propre
        processus.
        """
        if not self._installe:
            return
        if self._recu and not force:
            return
        self._installe = False
        precedents, self._precedents = self._precedents, {}
        for numero, precedent in precedents.items():
            signal.signal(numero, precedent)

    def traiter(self, numero: int, cadre: FrameType | None = None) -> None:
        """Corps du gestionnaire : ignore ces signaux, puis interrompt `serve`.

        N'est jamais appelé deux fois avec effet : le second signal (déjà ignoré
        par le système) ne fait rien s'il est appelé directement par un test.
        """
        if self._recu:
            return
        self._recu = True
        for numero_surveille in self._signaux:
            try:
                signal.signal(numero_surveille, signal.SIG_IGN)
            except (OSError, ValueError):
                continue
        if numero == signal.SIGINT:
            raise KeyboardInterrupt
        raise SystemExit(CODE_ARRET_SIGTERM)


@contextmanager
def signaux_supervises() -> Iterator[GestionnaireSignaux]:
    """Installe le gestionnaire d'arrêt normal autour d'un bloc, puis le retire."""
    gestionnaire = GestionnaireSignaux()
    gestionnaire.installer()
    try:
        yield gestionnaire
    finally:
        gestionnaire.restaurer()


class SignalFlag:
    """Drapeau d'arrêt d'une commande (tâche 1.5) : enregistre, ne lève jamais.

    Le premier signal d'arrêt normal est noté (`received`, `signal_number`) ; la boucle de
    suivi de `operation_watch` le constate et engage l'arrêt de l'opération. Les
    signaux suivants sont seulement comptés (`ignored_count`) : ils n'interrompent
    ni la clôture ni l'écriture du journal. Les gestionnaires précédents sont
    rétablis à la sortie du bloc `with`.
    """

    def __init__(self, signals: Sequence[int] | None = None) -> None:
        self._signals = tuple(signaux_arret_normal() if signals is None else signals)
        self._previous: dict[int, Any] = {}
        self._installed = False
        self._signal_number: int | None = None
        self._ignored_count = 0
        self._keep_ignored = False

    def __enter__(self) -> SignalFlag:
        self.install()
        return self

    def __exit__(
        self,
        error_type: type[BaseException] | None,
        error: BaseException | None,
        traceback: Any,
    ) -> None:
        self.restore()

    @property
    def received(self) -> bool:
        """Vrai dès qu'un signal d'arrêt a été reçu."""
        return self._signal_number is not None

    @property
    def signal_number(self) -> int | None:
        """Numéro du premier signal reçu, `None` s'il n'y en a pas eu."""
        return self._signal_number

    @property
    def ignored_count(self) -> int:
        """Nombre de signaux reçus après le premier, ignorés sans effet."""
        return self._ignored_count

    def install(self) -> None:
        """Pose le gestionnaire sur les signaux surveillés, en mémorisant les précédents."""
        if self._installed:
            return
        self._previous = {signal_number: signal.getsignal(signal_number) for signal_number in self._signals}
        self._installed = True
        for signal_number in self._signals:
            signal.signal(signal_number, self._handle)

    def ignore_until_exit(self) -> None:
        """Maintient l'arrêt protégé si la clôture reste incomplète."""
        self._keep_ignored = True
        for number in self._signals:
            signal.signal(number, signal.SIG_IGN)

    def restore(self) -> None:
        """Rétablit les gestionnaires, sauf si la clôture reste incomplète."""
        if not self._installed or self._keep_ignored:
            return
        self._installed = False
        previous, self._previous = self._previous, {}
        for signal_number, handler in previous.items():
            # `getsignal` renvoie `None` pour un gestionnaire posé hors Python.
            signal.signal(signal_number, signal.SIG_DFL if handler is None else handler)

    def _handle(self, signal_number: int, frame: FrameType | None = None) -> None:
        """Pose le drapeau au premier signal, compte les suivants sans agir."""
        if self._signal_number is None:
            self._signal_number = signal_number
        else:
            self._ignored_count += 1


def signaler(message: str) -> None:
    """Écrit une ligne de supervision sur la sortie d'erreur, sans trace."""
    print(f"transcription-bench : {message}", file=sys.stderr, flush=True)


class NettoyageArret:
    """Clôture d'arrêt idempotente, dans l'ordre fixé par le design D5.

    1. `CreneauOperations.passer_a_l_arret` : arrêt posé sous le verrou, sans
       attendre, ce qui refuse toute mutation et toute publication de marqueur
       prêt ultérieure ;
    2. arrêt du moteur d'exécution (groupe de processus) puis du sous-processus
       d'installation (`uv` et ses descendants), avec leurs délais bornés ;
    3. attente bornée du thread d'opération, sans jamais le tuer ;
    4. si ce thread est terminé, sa clôture est déjà enregistrée (`run.json`
       final, état du créneau figé) et le verrou d'instance est libéré en
       dernier ; sinon le verrou reste détenu jusqu'à la fin réelle du
       processus.

    Une seule exécution effective : un second appel renvoie l'issue mémorisée,
    sans nouvelle terminaison ni double libération. L'arrêt du moteur, celui de
    l'installation et la libération du verrou sont protégés : un échec inattendu
    y est journalisé sans pile et n'empêche pas les étapes suivantes. Le passage
    du créneau à l'arrêt et l'attente bornée de son thread ne sont, eux, pas
    protégés : ce sont des opérations purement locales sous verrou, dont l'échec
    relèverait d'un défaut du programme.
    """

    def __init__(
        self,
        *,
        verrou: VerrouInstance,
        creneau: CreneauOperations | None = None,
        execution: ExecutionMoteur | None = None,
        installation: InstallationMoteurs | None = None,
        delai_operation: float = DELAI_OPERATION_S,
        journal: Callable[[str], None] = signaler,
    ) -> None:
        self._verrou = verrou
        self._creneau = creneau
        self._execution = execution
        self._installation = installation
        self._delai_operation = delai_operation
        self._journal = journal
        self._verrou_nettoyage = threading.Lock()
        self._execute = False
        self._issue = False

    @property
    def issue(self) -> bool | None:
        """Issue mémorisée : `None` avant exécution, sinon `True` si tout est clos."""
        return self._issue if self._execute else None

    def executer(self) -> bool:
        """Exécute le nettoyage une seule fois et renvoie l'issue mémorisée."""
        with self._verrou_nettoyage:
            if self._execute:
                return self._issue
            try:
                self._issue = self._executer_une_fois()
                return self._issue
            finally:
                self._execute = True

    def _executer_une_fois(self) -> bool:
        if self._creneau is not None:
            self._creneau.passer_a_l_arret()
        self._arreter_moteur()
        self._arreter_installation()
        clos = self._creneau is None or self._creneau.attendre_thread(
            self._delai_operation
        )
        if not clos:
            self._journal(
                "opération non close : verrou d'instance conservé jusqu'à la fin "
                "réelle du processus (aucun thread n'est tué)."
            )
            return False
        # Clôture déjà enregistrée par le thread de fond lui-même (run.json final,
        # état du créneau figé) : il ne reste qu'à libérer le verrou, en dernier.
        try:
            self._verrou.liberer()
        except OSError as erreur:
            self._journal(
                "libération du verrou d'instance impossible : "
                f"{type(erreur).__name__} ; il sera libéré à la fin du processus."
            )
            return False
        return True

    def _arreter_moteur(self) -> None:
        """Termine et collecte le moteur d'exécution éventuellement en cours."""
        if self._execution is None:
            return
        try:
            issue = self._execution.arreter_execution(arret_serveur=True)
        except Exception as erreur:  # l'arrêt ne doit jamais empêcher la clôture
            self._journal(
                "arrêt du moteur impossible : "
                f"{type(erreur).__name__} ; le créneau reste occupé."
            )
            return
        if issue == ARRET_SURVIVANT:
            self._journal(
                "le processus moteur survit au signal de forçage : attente de sa "
                "fin réelle, le verrou d'instance reste détenu."
            )

    def _arreter_installation(self) -> None:
        """Termine le sous-processus d'installation (`uv`) éventuellement en cours."""
        if self._installation is None:
            return
        try:
            self._installation.arreter()
        except Exception as erreur:  # idem : la clôture continue
            self._journal(
                "arrêt du sous-processus d'installation impossible : "
                f"{type(erreur).__name__}."
            )
