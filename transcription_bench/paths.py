"""Dossiers de données locaux du prototype.

Les dossiers de données vivent sous `data/` à la racine du projet, et non sous
le dossier courant : lancer la commande depuis un sous-dossier ne disperse pas
les données. La base reste hors Git. Seule la préparation de ces dossiers
prédéfinis est assurée ici : la résolution contrôlée d'autres noms ou chemins
relève du lot 3.
"""

from __future__ import annotations

from pathlib import Path

RACINE_PROJET = Path(__file__).resolve().parent.parent
DOSSIER_DATA = RACINE_PROJET / "data"
DOSSIERS_DATA = ("audio", "models", "engines", "results")


def preparer_dossiers_data(base: Path | str | None = None) -> dict[str, Path]:
    """Crée les dossiers de données manquants et renvoie leurs chemins.

    `base` vaut `DOSSIER_DATA` (`data/` à la racine du projet) par défaut ; il
    n'est fourni que par les tests. Idempotent : un dossier existant est
    conservé tel quel et aucun fichier qu'il contient n'est écrasé.
    """
    racine = DOSSIER_DATA if base is None else Path(base)
    chemins: dict[str, Path] = {}
    for nom in DOSSIERS_DATA:
        chemin = racine / nom
        chemin.mkdir(parents=True, exist_ok=True)
        chemins[nom] = chemin
    return chemins
