"""Lectures et écritures JSON atomiques sous data/, protégées par un verrou commun.

Un seul verrou (`VERROU_STOCKAGE`) protège les lectures et les remplacements de
fichiers JSON écrits par les services : il évite de remplacer un fichier pendant
qu'une page le lit, en particulier sous Windows où un remplacement concurrent
d'une lecture peut échouer. Ce verrou est local au processus serveur ; il ne
prétend pas protéger contre un autre programme qui modifierait les mêmes
fichiers.

Ordre des verrous : le verrou du créneau peut être tenu pendant un appel à
`ecrire_json_atomique` (publication d'un marqueur prêt sous verrou), jamais
l'inverse. Aucun code ne doit donc prendre le verrou du créneau en tenant celui
du stockage.

Chaque JSON est écrit dans un fichier temporaire du même dossier, fermé avant
`os.replace`, afin qu'une interruption ne laisse pas de fichier tronqué et que
le remplacement fonctionne sous Windows.
"""

from __future__ import annotations

import json
import os
import tempfile
import threading
from pathlib import Path
from typing import Any

VERROU_STOCKAGE = threading.Lock()


class JsonInvalide(ValueError):
    """Fichier JSON illisible ou non conforme, sans exposer son contenu."""


def lire_json(chemin: Path) -> Any | None:
    """Lit un JSON sous le verrou commun ; `None` si le fichier est absent.

    Les octets sont lus sous le verrou, puis décodés en UTF-8 et interprétés
    comme JSON hors de celui-ci : un contenu non UTF-8 ou une syntaxe invalide
    lève `JsonInvalide`, jamais un `UnicodeDecodeError` brut remonté à
    l'appelant. Celui-ci décide alors de l'état affiché, sans réécrire le
    fichier fautif.
    """
    chemin = Path(chemin)
    with VERROU_STOCKAGE:
        try:
            brut = chemin.read_bytes()
        except FileNotFoundError:
            return None
    try:
        return json.loads(brut.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as erreur:
        raise JsonInvalide(f"JSON illisible : {chemin.name} ({erreur})") from None


def ecrire_json_atomique(chemin: Path, contenu: Any) -> None:
    """Écrit `contenu` en JSON dans `chemin` par remplacement atomique.

    Le fichier temporaire vit dans le même dossier, il est fermé avant
    `os.replace`, et il est supprimé en cas d'échec. Les échecs d'écriture
    remontent à l'appelant, qui ne doit alors publier aucun état prêt.
    """
    chemin = Path(chemin)
    with VERROU_STOCKAGE:
        chemin.parent.mkdir(parents=True, exist_ok=True)
        descripteur, nom_temporaire = tempfile.mkstemp(
            dir=chemin.parent, prefix=f".{chemin.name}.", suffix=".tmp"
        )
        try:
            with os.fdopen(descripteur, "w", encoding="utf-8", newline="\n") as fichier:
                json.dump(contenu, fichier, ensure_ascii=False, indent=2, sort_keys=True)
                fichier.write("\n")
                fichier.flush()
                os.fsync(fichier.fileno())
            os.replace(nom_temporaire, chemin)
        except BaseException:
            try:
                os.unlink(nom_temporaire)
            except OSError:
                pass
            raise
