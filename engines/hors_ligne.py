"""Mode hors ligne et options de chargement du processus moteur.

Ce module ne dépend que de la bibliothèque standard : le serveur peut importer
`environnement_moteur` sans charger de paquet moteur, et le runner l'utilise
comme garde-fou dans son propre processus. Il ne remplace pas le futur lancement
supervisé de la tâche 6.3 : il fournit seulement l'environnement à transmettre
au sous-processus moteur et les options de modèle à forcer.

`environnement_moteur(base=None)` renvoie toujours un **nouveau** dictionnaire :
il force `HF_HUB_OFFLINE=1`, conserve les autres variables utiles et retire les
variables d'interpréteur du serveur (`PYTHONHOME`, `PYTHONPATH`, `VIRTUAL_ENV`)
qui pourraient dérouter l'interpréteur du moteur. `PATH` n'est pas réorganisé.
Il force aussi `PYTHONIOENCODING=utf-8` : le serveur décode la sortie du moteur
en UTF-8, et sous Windows la console n'utilise pas cet encodage par défaut, ce
qui ferait échouer l'écriture d'un message accentué sur la sortie d'erreur du
runner. Enfin, il fixe `NUMBA_CACHE_DIR` (design D4) : librosa/numba, requis par
la famille Parakeet, écrit sinon son cache JIT dans le profil utilisateur ou
dans le paquet installé. La valeur par défaut est `data/cache-numba` à la racine
du dépôt ; `dossier_cache_numba` permet à un appelant d'utiliser son propre
dossier de données. Le mapping source et `os.environ` du serveur ne sont jamais
modifiés.

`mode_hors_ligne()` est le garde-fou du runner lorsqu'il est appelé directement
(`python engines/runner.py job.json`). Il force `HF_HUB_OFFLINE=1` dans le
processus du runner avant l'import de l'adaptateur, puis restaure la valeur
précédente à la sortie, y compris pour un test ou un appelant partageant le
processus. Le serveur n'utilise jamais ce contexte et ne mute pas son propre
environnement.

`options_modele(modele)` copie les options remises à `adaptateur.charger` et y
impose `local_files_only=True` et `trust_remote_code=False`. Un job ne peut donc
pas les désactiver. Les adaptateurs réels consomment ces options aux API
concernées et relisent le périphérique effectif ; le moteur factice reste le
seul exécutable sans modèle ni qualification PC.
"""

from __future__ import annotations

import os
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from pathlib import Path
from typing import Any

CLE_HORS_LIGNE = "HF_HUB_OFFLINE"
CLE_ENCODAGE_STDIO = "PYTHONIOENCODING"
ENCODAGE_STDIO = "utf-8"
CLE_CACHE_NUMBA = "NUMBA_CACHE_DIR"
#: Cache JIT sous `data/`, hors du profil utilisateur (design D4).
DOSSIER_CACHE_NUMBA = Path(__file__).resolve().parent.parent / "data" / "cache-numba"
VARIABLES_PYTHON_RETIREES = ("PYTHONHOME", "PYTHONPATH", "VIRTUAL_ENV")


def environnement_moteur(
    base: Mapping[str, str] | None = None,
    dossier_cache_numba: str | Path | None = None,
) -> dict[str, str]:
    """Prépare un nouvel environnement de sous-processus moteur, hors ligne.

    `base` est copié ; sa valeur par défaut est `os.environ` du processus
    appelant. Le dictionnaire renvoyé force `HF_HUB_OFFLINE=1`, force l'encodage
    UTF-8 des entrées/sorties de l'interpréteur enfant, fixe
    `NUMBA_CACHE_DIR` et retire les variables d'interpréteur du serveur. Aucune
    autre variable, notamment `PATH`, n'est modifiée. `dossier_cache_numba`
    remplace le dossier `data/cache-numba` par défaut ; le dossier lui-même est
    créé par numba au premier besoin, jamais ici.
    """
    source = os.environ if base is None else base
    environnement = {
        cle: valeur
        for cle, valeur in source.items()
        if cle not in VARIABLES_PYTHON_RETIREES
    }
    environnement[CLE_HORS_LIGNE] = "1"
    environnement[CLE_ENCODAGE_STDIO] = ENCODAGE_STDIO
    cache_numba = (
        DOSSIER_CACHE_NUMBA
        if dossier_cache_numba is None
        else Path(dossier_cache_numba)
    )
    environnement[CLE_CACHE_NUMBA] = str(cache_numba)
    return environnement


@contextmanager
def mode_hors_ligne() -> Iterator[None]:
    """Force `HF_HUB_OFFLINE=1` dans ce processus, puis restaure la valeur.

    Utilisé par le runner comme garde-fou avant l'import de l'adaptateur. Le
    bloc `finally` restaure exactement la valeur précédente, ou retire la clé
    si elle était absente : un appelant de test retrouve son environnement.
    """
    precedent = os.environ.get(CLE_HORS_LIGNE)
    os.environ[CLE_HORS_LIGNE] = "1"
    try:
        yield
    finally:
        if precedent is None:
            os.environ.pop(CLE_HORS_LIGNE, None)
        else:
            os.environ[CLE_HORS_LIGNE] = precedent


def commande_runner(
    interpreteur: str | Path, chemin_job: str | Path
) -> list[str]:
    """Commande minimale `interpréteur engines/runner.py job.json`.

    Le chemin de l'interpréteur est conservé tel quel : il s'agit en pratique du
    `bin/python` du venv du moteur, et le résoudre suivrait son lien vers le
    CPython géré, ce qui perdrait le venv et ses paquets (numpy, moteur). Seuls
    le chemin du runner, calculé depuis `__file__`, et celui du job sont résolus.
    Aucun lancement, superviseur ni attente de processus n'est effectué ici.
    """
    runner = Path(__file__).resolve().with_name("runner.py")
    return [str(interpreteur), str(runner), str(Path(chemin_job).resolve())]


def options_modele(modele: Mapping[str, Any]) -> dict[str, Any]:
    """Copie les options de modèle en imposant le chargement local sans code distant.

    Le job peut fournir `local_files_only` ou `trust_remote_code` avec une valeur
    contraire : elle est écrasée ici. Le mapping d'origine n'est jamais modifié.
    """
    options = dict(modele)
    options["local_files_only"] = True
    options["trust_remote_code"] = False
    return options
