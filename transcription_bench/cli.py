"""Point d'entrée en ligne de commande du prototype.

Le lot 3 branchera ici la fabrique Flask et le service HTTP Waitress. D'ici
là, la commande prépare seulement les dossiers de données puis refuse encore
explicitement de démarrer un serveur.
"""

from __future__ import annotations

import argparse
import sys

from transcription_bench.paths import preparer_dossiers_data

DESCRIPTION = (
    "Prototype local de comparaison de modèles de transcription française sur CPU."
)

MESSAGE_NON_IMPLEMENTE = "Erreur : serveur non encore implémenté."


def construire_analyseur() -> argparse.ArgumentParser:
    """Construit l'analyseur d'arguments, sans aucune lecture ni écriture."""
    return argparse.ArgumentParser(prog="transcription-bench", description=DESCRIPTION)


def main(argv: list[str] | None = None) -> int:
    """Prépare les dossiers de données, puis signale que le serveur reste à venir."""
    analyseur = construire_analyseur()
    analyseur.parse_args(argv)
    preparer_dossiers_data()
    print(MESSAGE_NON_IMPLEMENTE, file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
