"""Verrou système d'instance unique sur un dossier de données.

Une seule instance du serveur peut utiliser un dossier de données : le verrou
est un verrou de fichier pris par le système d'exploitation (`fcntl.flock` sous
Linux, `msvcrt.locking` sous Windows), non bloquant et portant sur un seul
octet du fichier `data/instance.lock`. Le fichier reste persistant : il n'est
jamais supprimé à la libération, ce qui évite une course entre suppression et
réouverture. Il ne s'agit pas d'un fichier de PID : la présence du fichier ne
prouve rien, c'est le verrou qui compte, et le système le libère de lui-même
quand le processus meurt, y compris après un arrêt brutal.

La primitive exacte reste à éprouver sur PC (tâche 1.7) ; les tests du serveur
de développement ne valent pas qualification Linux ou Windows. Le descripteur
est conservé sous forme d'entier brut : même si l'objet `VerrouInstance` était
ramassé par le ramasse-miettes, le fichier ne serait pas refermé et le verrou
resterait tenu jusqu'à la mort du processus. Seuls `liberer` et la fin réelle du
processus le libèrent, jamais une finalisation implicite.
"""

from __future__ import annotations

import os
from pathlib import Path
from types import TracebackType

NOM_FICHIER_VERROU = "instance.lock"
TAILLE_VERROU = 1


class InstanceDejaActive(RuntimeError):
    """Refus de démarrer : une autre instance tient déjà le verrou."""


class VerrouInstance:
    """Verrou d'instance détenu par le système, libéré à la mort du processus.

    `acquerir` crée le dossier de données et le fichier de verrou au besoin,
    puis tente un verrou exclusif non bloquant. Un objet ne détient qu'un
    verrou ; `liberer` est idempotent.
    """

    def __init__(self, dossier_data: Path | str) -> None:
        self._chemin = Path(dossier_data) / NOM_FICHIER_VERROU
        self._descripteur: int | None = None

    @property
    def chemin(self) -> Path:
        """Chemin du fichier de verrou, conservé après la libération."""
        return self._chemin

    @property
    def detenu(self) -> bool:
        """Vrai si cet objet tient le verrou."""
        return self._descripteur is not None

    def acquerir(self) -> VerrouInstance:
        """Prend le verrou ou lève `InstanceDejaActive` sans rien modifier d'autre.

        Un échec d'ouverture ou de verrouillage laisse le fichier en place et
        referme le descripteur : aucune donnée du dossier n'est touchée.
        """
        if self._descripteur is not None:
            raise RuntimeError("verrou d'instance déjà détenu par cet objet")
        self._chemin.parent.mkdir(parents=True, exist_ok=True)
        descripteur = os.open(self._chemin, os.O_RDWR | os.O_CREAT, 0o644)
        try:
            _verrouiller(descripteur, self._chemin)
        except BaseException:
            os.close(descripteur)
            raise
        self._descripteur = descripteur
        return self

    def liberer(self) -> None:
        """Libère le verrou et referme le descripteur ; sans effet si déjà fait."""
        descripteur = self._descripteur
        if descripteur is None:
            return
        self._descripteur = None
        try:
            _deverrouiller(descripteur)
        finally:
            os.close(descripteur)

    def __enter__(self) -> VerrouInstance:
        return self.acquerir()

    def __exit__(
        self,
        type_exception: type[BaseException] | None,
        exception: BaseException | None,
        trace: TracebackType | None,
    ) -> None:
        self.liberer()


def _verrouiller(descripteur: int, chemin: Path) -> None:
    """Pose le verrou exclusif non bloquant, ou lève `InstanceDejaActive`."""
    try:
        if os.name == "nt":
            import msvcrt

            msvcrt.locking(descripteur, msvcrt.LK_NBLCK, TAILLE_VERROU)
        else:
            import fcntl

            fcntl.flock(descripteur, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError as erreur:
        raise InstanceDejaActive(
            "une autre instance utilise déjà ce dossier de données "
            f"(verrou {chemin} détenu). Fermez l'autre instance avant de redémarrer."
        ) from erreur


def _deverrouiller(descripteur: int) -> None:
    """Retire le verrou ; la fermeture du descripteur suffit en dernier recours."""
    if os.name == "nt":
        import msvcrt

        os.lseek(descripteur, 0, os.SEEK_SET)
        msvcrt.locking(descripteur, msvcrt.LK_UNLCK, TAILLE_VERROU)
    else:
        import fcntl

        fcntl.flock(descripteur, fcntl.LOCK_UN)
