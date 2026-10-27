"""Créneau unique d'opération longue, indépendant de Flask.

Un objet `CreneauOperations` détient au plus une opération globale
(installation, téléchargement, exécution ou vérification distante) exécutée
dans un thread démon. Il
est créé par la CLI puis injecté dans les services de l'application : il n'est
ni global au module, ni construit par la fabrique Flask, qui ne démarre aucun
thread.

Le verrou du créneau (`threading.Lock`, non réentrant) protège toutes les
valeurs : état, journal et horodatages. Trois opérations passent sous ce même
verrou, ce qui rend l'arrêt atomique : l'admission d'une opération
(`demarrer`), les mutations courtes (`executer_mutation`) et la publication
d'un marqueur prêt (`publier_pret`). Dès que `arreter` a posé la demande
d'arrêt, ces trois opérations sont refusées : une opération admise avant l'arrêt
peut encore finir pendant le nettoyage, mais elle ne publiera aucun marqueur
prêt.

Les callbacks de `executer_mutation` et de `publier_pret` s'exécutent sous ce
verrou : ils doivent rester courts (aucune E/S longue, aucun téléchargement) et
ne doivent jamais rappeler une méthode du créneau, faute d'interblocage. Le
travail de fond, lui, s'exécute hors du verrou et peut donc faire des E/S
longues : il ne touche au créneau que par le handle `Travailleur`, dont
`journaliser` prend le verrou brièvement et `publier_pret` l'exécute sous
verrou. Le travail de fond ne reçoit aucun objet Flask (`request`, `session`,
contexte d'application) : uniquement ce handle et des valeurs déjà validées par
l'appelant.

Ce module ne conserve aucun historique persistant : l'état et le journal vivent
en mémoire, pour l'opération courante et la dernière opération terminée.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import TypeVar

T = TypeVar("T")

LOGGER = logging.getLogger(__name__)

ETAT_LIBRE = "libre"
ETAT_EN_COURS = "en_cours"
ETAT_TERMINEE = "terminee"
ETAT_ECHOUEE = "echouee"
ETAT_INTERROMPUE = "interrompue"

LIBELLES_ETATS = {
    ETAT_LIBRE: "libre",
    ETAT_EN_COURS: "en cours",
    ETAT_TERMINEE: "terminée",
    ETAT_ECHOUEE: "échouée",
    ETAT_INTERROMPUE: "interrompue",
}

TYPE_INSTALLATION = "installation"
TYPE_TELECHARGEMENT = "telechargement"
TYPE_EXECUTION = "execution"
TYPE_VERIFICATION = "verification"

TYPES_OPERATION = (
    TYPE_INSTALLATION,
    TYPE_TELECHARGEMENT,
    TYPE_EXECUTION,
    TYPE_VERIFICATION,
)

LIBELLES_TYPES = {
    TYPE_INSTALLATION: "installation",
    TYPE_TELECHARGEMENT: "téléchargement",
    TYPE_EXECUTION: "exécution",
    TYPE_VERIFICATION: "vérification",
}

DELAI_ARRET_DEFAUT = 5.0


class CreneauOccupe(RuntimeError):
    """Refus d'une demande : une opération longue est déjà en cours (HTTP 409).

    `type_operation` est le type de l'opération qui occupait le créneau au
    moment du refus, capturé sous le verrou. Il vaut `None` si l'exception a été
    construite sans ce contexte. Il ne faut jamais le relire depuis un
    instantané ultérieur, qui pourrait déjà décrire une autre opération ou un
    créneau libre.
    """

    def __init__(self, message: str, *, type_operation: str | None = None) -> None:
        super().__init__(message)
        self.type_operation = type_operation


class ServiceArrete(RuntimeError):
    """Refus d'une demande : le serveur est en cours d'arrêt (HTTP 503)."""


class OperationEchouee(RuntimeError):
    """Échec prévu d'une opération de fond.

    Le créneau consigne l'échec et son message sans trace complète : une erreur
    prévue (moteur mort, événements manquants) n'apprend rien de plus sous
    forme de pile d'appels. Les services concernés en dérivent leurs propres
    exceptions.
    """


class OperationInterrompue(RuntimeError):
    """Opération de fond interrompue à la demande de l'utilisateur.

    Ce n'est pas un échec : le créneau la traduit en état `interrompue`, sans
    erreur consignée. Elle se distingue de l'arrêt du serveur, qui a son propre
    motif de journal.
    """


def horodatage_iso() -> str:
    """Horodate en ISO 8601 local, à la seconde, pour le journal et les états."""
    return datetime.now().astimezone().isoformat(timespec="seconds")


@dataclass(frozen=True)
class InstantaneCreneau:
    """Copie immuable de l'état du créneau, prise sous verrou.

    `journal` est un tuple : une page ou un test peut conserver cet instantané
    sans que les écritures suivantes du travail de fond le modifient.
    """

    etat: str
    arrete: bool
    type_operation: str | None
    cible: str | None
    debut: str | None
    fin: str | None
    erreur: str | None
    journal: tuple[str, ...]


class Travailleur:
    """Handle remis au travail de fond : journal et publication protégée.

    Aucun objet Flask n'est transmis. Les deux méthodes prennent le verrou du
    créneau : elles ne doivent pas être appelées depuis une publication en
    cours (verrou non réentrant), et les publications doivent rester brèves.
    """

    __slots__ = ("_creneau",)

    def __init__(self, creneau: CreneauOperations) -> None:
        self._creneau = creneau

    def journaliser(self, message: str) -> None:
        """Ajoute une ligne horodatée au journal de l'opération."""
        self._creneau._journaliser(message)

    def publier_pret(self, publication: Callable[[], T]) -> T:
        """Publie un marqueur prêt sous le verrou, refusé après passage à l'arrêt."""
        return self._creneau.publier_pret(publication)


class CreneauOperations:
    """Créneau global : au plus une opération longue, un thread démon, un verrou.

    États : `libre` (aucune opération), `en_cours`, puis l'issue de la dernière
    opération (`terminee`, `echouee` ou `interrompue`). Une opération terminée
    ou échouée libère le créneau : une nouvelle demande est acceptée et repart
    d'un journal vide. Après `arreter`, le créneau reste définitivement fermé :
    aucune admission, mutation ou publication n'est plus acceptée.
    """

    def __init__(self, horloge: Callable[[], str] = horodatage_iso) -> None:
        self._verrou = threading.Lock()
        self._horloge = horloge
        self._arrete = False
        self._etat = ETAT_LIBRE
        self._type_operation: str | None = None
        self._cible: str | None = None
        self._debut: str | None = None
        self._fin: str | None = None
        self._erreur: str | None = None
        self._journal: list[str] = []
        self._thread: threading.Thread | None = None

    def demarrer(
        self,
        type_operation: str,
        travail: Callable[[Travailleur], None],
        *,
        cible: str | None = None,
    ) -> None:
        """Admet une opération et lance son thread démon, sous le verrou.

        `type_operation` appartient à `TYPES_OPERATION` ; `cible` et les données
        du travail sont des valeurs déjà validées par l'appelant. Lève
        `CreneauOccupe` si une opération est en cours et `ServiceArrete` si le
        serveur est en cours d'arrêt, sans rien démarrer.
        """
        if type_operation not in TYPES_OPERATION:
            raise ValueError(
                f"type d'opération inconnu : {type_operation!r} "
                f"(attendu : {', '.join(TYPES_OPERATION)})"
            )
        if not callable(travail):
            raise ValueError("travail attendu sous forme d'appelable")
        with self._verrou:
            self._refuser_si_indisponible()
            self._etat = ETAT_EN_COURS
            self._type_operation = type_operation
            self._cible = cible
            self._debut = self._horloge()
            self._fin = None
            self._erreur = None
            self._journal = []
            libelle = LIBELLES_TYPES[type_operation]
            if cible:
                self._consigner(f"Opération « {libelle} » démarrée : {cible}.")
            else:
                self._consigner(f"Opération « {libelle} » démarrée.")
            self._thread = None
            try:
                thread = threading.Thread(
                    target=self._executer,
                    args=(travail, Travailleur(self)),
                    name="transcription-bench-operation",
                    daemon=True,
                )
                thread.start()
            except BaseException as exception:
                # Échec de création du thread : l'opération est close sur place.
                self._etat = ETAT_ECHOUEE
                self._fin = self._horloge()
                self._erreur = f"{type(exception).__name__} : {exception}"
                self._consigner("Démarrage du thread de fond impossible.")
                raise
            self._thread = thread

    def executer_mutation(self, action: Callable[[], T]) -> T:
        """Exécute une mutation courte sous le verrou du créneau.

        Refusée en `ServiceArrete` après passage à l'arrêt et en
        `CreneauOccupe` pendant une opération. `action` doit rester brève et ne
        jamais rappeler le créneau.
        """
        with self._verrou:
            self._refuser_si_indisponible()
            return action()

    def publier_pret(self, publication: Callable[[], T]) -> T:
        """Publie un marqueur prêt sous le verrou, ou refuse en `ServiceArrete`.

        La publication s'exécute pendant que le verrou est tenu : le passage à
        l'arrêt attend donc sa fin, et une opération qui aurait déjà fini son
        travail pendant l'arrêt ne publie plus rien de prêt. `publication` doit
        rester brève et ne jamais rappeler le créneau.
        """
        with self._verrou:
            if self._arrete:
                raise ServiceArrete(
                    "publication d'un marqueur prêt refusée : arrêt du serveur en cours"
                )
            return publication()

    def arreter(self, delai: float = DELAI_ARRET_DEFAUT) -> bool:
        """Passe le créneau à l'arrêt, puis attend le thread de fond `delai`.

        Idempotent, y compris pour le journal : seule la première demande d'arrêt
        consigne le passage à l'arrêt ou une opération non close. La demande
        d'arrêt est posée sous le verrou, ce qui refuse toute admission, mutation
        ou publication ultérieure ; une opération déjà admise garde la main pour
        finir. Renvoie `True` si le thread de fond est
        terminé après l'attente bornée, `False` s'il est encore actif (le
        nettoyage complet relève de la tâche 6.6).
        """
        with self._verrou:
            premier_passage = not self._arrete
            self._arrete = True
            if premier_passage and self._etat == ETAT_EN_COURS:
                self._consigner("Arrêt demandé pendant l'opération.")
            thread = self._thread
        if thread is None:
            return True
        thread.join(delai)
        if thread.is_alive():
            if premier_passage:
                with self._verrou:
                    self._consigner(
                        "Opération non close : le thread de fond est encore actif."
                    )
            return False
        return True

    def instantane(self) -> InstantaneCreneau:
        """Renvoie une copie immuable de l'état et du journal, sous verrou."""
        with self._verrou:
            return InstantaneCreneau(
                etat=self._etat,
                arrete=self._arrete,
                type_operation=self._type_operation,
                cible=self._cible,
                debut=self._debut,
                fin=self._fin,
                erreur=self._erreur,
                journal=tuple(self._journal),
            )

    @property
    def thread_travailleur(self) -> threading.Thread | None:
        """Thread démon de l'opération courante ou de la dernière opération.

        Exposé pour la supervision bornée de la CLI (tâche 6.6) : après
        `arreter`, elle peut constater si le thread est réellement terminé.
        Aucune attente ni terminaison n'est gérée ici.
        """
        with self._verrou:
            return self._thread

    def _refuser_si_indisponible(self) -> None:
        """Refuse une demande ; doit être appelé avec le verrou tenu."""
        if self._arrete:
            raise ServiceArrete("arrêt du serveur en cours : demande refusée")
        if self._etat == ETAT_EN_COURS:
            raise CreneauOccupe(
                "une opération longue est déjà en cours : demande refusée",
                type_operation=self._type_operation,
            )

    def _journaliser(self, message: str) -> None:
        with self._verrou:
            self._consigner(message)

    def _consigner(self, message: str) -> None:
        """Ajoute une ligne horodatée ; doit être appelé avec le verrou tenu."""
        self._journal.append(f"{self._horloge()} {message}")

    def _executer(
        self, travail: Callable[[Travailleur], None], travailleur: Travailleur
    ) -> None:
        """Corps du thread démon : exécute puis fige l'issue sous le verrou."""
        erreur: BaseException | None = None
        try:
            travail(travailleur)
        except OperationInterrompue as exception:
            erreur = exception
            LOGGER.info("Opération de fond interrompue : %s", exception)
        except OperationEchouee as exception:
            # Échec prévu : le message suffit, une pile d'appels n'ajoute rien.
            erreur = exception
            LOGGER.warning("Opération de fond en échec : %s", exception)
        except BaseException as exception:  # tout échec doit libérer le créneau
            erreur = exception
            LOGGER.exception("Échec de l'opération de fond du créneau")
        with self._verrou:
            self._fin = self._horloge()
            if not isinstance(erreur, OperationInterrompue) and erreur is not None:
                self._erreur = f"{type(erreur).__name__} : {erreur}"
            if isinstance(erreur, OperationInterrompue):
                self._etat = ETAT_INTERROMPUE
                self._consigner("Opération interrompue à la demande de l'utilisateur.")
            elif self._arrete:
                self._etat = ETAT_INTERROMPUE
                self._consigner("Opération interrompue par l'arrêt du serveur.")
            elif erreur is not None:
                self._etat = ETAT_ECHOUEE
                self._consigner("Opération terminée en échec.")
            else:
                self._etat = ETAT_TERMINEE
                self._consigner("Opération terminée.")
