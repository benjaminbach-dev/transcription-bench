"""Arrêt borné d'un sous-processus, de son groupe ou de son arborescence.

Le processus moteur et les commandes d'installation (`uv venv`, `uv pip sync`)
sont lancés dans leur propre groupe ou session de processus : un Ctrl+C au
terminal ne les atteint donc pas et c'est la supervision du serveur (tâche 6.6)
qui les arrête. Ce module fournit les primitives correspondantes, sans
dépendre de Flask ni du créneau :

- `options_groupe()` : options `Popen` créant le groupe (`start_new_session`
  sous POSIX, `CREATE_NEW_PROCESS_GROUP` sous Windows) ;
- `arreter_groupe()` : envoi de `SIGTERM` puis, si nécessaire, de `SIGKILL` au
  **groupe** sous POSIX (`os.killpg`), pour atteindre aussi les descendants
  lancés par le moteur ou par `uv`. Le processus visé doit avoir été lancé avec
  `options_groupe()` : le groupe n'est signalé que si `os.getpgid(pid)` vaut
  bien son propre PID et ne désigne pas notre propre groupe (`os.getpgrp()`),
  afin de ne jamais viser un groupe étranger. À défaut, le signal est envoyé au
  seul processus ;
- `descendants()` puis `arreter_descendants()` : la descendance est relevée
  **avant** le signal, puis attendue et tuée si elle y survit. Un descendant
  insensible à `SIGTERM` reste en effet en vie après la sortie du processus
  principal, et le groupe n'est alors plus signalable (`os.getpgid` échoue) :
  ces références psutil, identifiées par PID **et** heure de création, sont le
  seul moyen sûr de l'atteindre sans risquer de tuer un PID réutilisé.

Sous Windows, il n'existe pas d'équivalent portable de `killpg` et un
`CTRL_BREAK_EVENT` n'atteint que les processus partageant une console : l'arrêt
parcourt donc l'arborescence avec psutil (`children(recursive=True)`) et termine
les enfants puis le parent. C'est un « au mieux » assumé : ni Job Object ni
`CTRL_BREAK_EVENT` ne sont utilisés ; un descendant créé après ce parcours, ou
détaché de l'arborescence, peut survivre. Ce comportement reste à éprouver sur
PC Windows (tâches 1.7 et 8.4) ; les tests du serveur de développement ne
constituent pas cette validation.

Aucune de ces fonctions n'attend la fin du processus principal : chaque
appelant borne l'attente qui le concerne. Seul `arreter_descendants` attend, de
façon bornée, la descendance qu'on lui a relevée. Aucune ne lève pour un
processus déjà disparu.
"""

from __future__ import annotations

import os
import signal
import subprocess
from collections.abc import Sequence
from typing import Any

import psutil


def options_groupe() -> dict[str, Any]:
    """Options `Popen` d'un sous-processus isolé des signaux du terminal."""
    if os.name == "nt":
        return {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
    return {"start_new_session": True}


def arreter_groupe(processus: subprocess.Popen[Any], *, force: bool = False) -> bool:
    """Envoie `SIGTERM` (ou `SIGKILL` si `force`) au groupe du processus.

    Renvoie `True` si au moins un signal a pu être envoyé, `False` si le groupe
    et le processus ont déjà disparu. Ne lève jamais pour un processus absent et
    ne vise jamais un groupe auquel le processus n'appartient pas.
    """
    if os.name == "nt":
        return _arreter_arborescence_windows(processus.pid, force=force)
    return _arreter_groupe_posix(processus, force=force)


def _arreter_groupe_posix(processus: subprocess.Popen[Any], *, force: bool) -> bool:
    """Signale le groupe POSIX du processus, ou le processus seul en repli."""
    numero = signal.SIGKILL if force else signal.SIGTERM
    try:
        groupe = os.getpgid(processus.pid)
    except (ProcessLookupError, OSError):
        groupe = None
    if groupe == processus.pid and groupe != os.getpgrp():
        try:
            os.killpg(groupe, numero)
            return True
        except ProcessLookupError:
            return False
        except OSError:
            # Groupe hostile ou droits insuffisants : repli sur le processus.
            pass
    try:
        processus.send_signal(numero)
        return True
    except (ProcessLookupError, OSError):
        return False


def descendants(pid: int) -> list[psutil.Process]:
    """Descendance actuelle du processus, relevée **avant** tout signal.

    Les références psutil portent le PID et l'heure de création : elles restent
    utilisables après la disparition du parent, et psutil refuse d'agir sur un
    PID réutilisé entre-temps. Renvoie une liste vide si le processus a déjà
    disparu, sans lever.
    """
    try:
        return psutil.Process(pid).children(recursive=True)
    except psutil.Error:
        return []


def arreter_descendants(arbre: Sequence[psutil.Process], delai: float) -> None:
    """Attend la fin des descendants relevés, puis tue les survivants.

    Appelé après le signal envoyé au groupe : un descendant insensible à
    `SIGTERM` survit à la sortie du processus principal, où le groupe n'est plus
    signalable. L'attente est bornée par `delai`, ainsi que l'attente qui suit
    le forçage. Ne lève jamais : un descendant déjà disparu ou inaccessible est
    ignoré.
    """
    vivants = list(arbre)
    if not vivants:
        return
    _, vivants = psutil.wait_procs(vivants, timeout=delai)
    if not vivants:
        return
    for cible in vivants:
        try:
            cible.kill()
        except psutil.Error:
            continue
    psutil.wait_procs(vivants, timeout=delai)


def _arreter_arborescence_windows(pid: int, *, force: bool) -> bool:
    """Termine l'arborescence psutil du processus, enfants d'abord (« au mieux »)."""
    try:
        racine = psutil.Process(pid)
        descendants = racine.children(recursive=True)
    except psutil.Error:
        return False
    envoye = False
    for cible in reversed(descendants):  # les plus profonds d'abord
        try:
            if force:
                cible.kill()
            else:
                cible.terminate()
            envoye = True
        except psutil.Error:
            continue
    try:
        if force:
            racine.kill()
        else:
            racine.terminate()
        envoye = True
    except psutil.Error:
        pass
    return envoye
