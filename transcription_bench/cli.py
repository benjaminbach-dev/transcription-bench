"""Point d'entrée en ligne de commande du prototype.

Le lot 3 branchera ici la fabrique Flask et le service HTTP Waitress. En
attendant, la commande ne doit produire aucun effet de bord : ni dossier de
données, ni serveur.
"""

from __future__ import annotations

import argparse
import sys

DESCRIPTION = (
    "Prototype local de comparaison de modèles de transcription française sur CPU."
)

MESSAGE_NON_IMPLEMENTE = "Erreur : serveur non encore implémenté."


def construire_analyseur() -> argparse.ArgumentParser:
    """Construit l'analyseur d'arguments, sans aucune lecture ni écriture."""
    return argparse.ArgumentParser(prog="transcription-bench", description=DESCRIPTION)


def main(argv: list[str] | None = None) -> int:
    """Affiche l'aide, ou signale que le serveur n'est pas encore implémenté."""
    analyseur = construire_analyseur()
    analyseur.parse_args(argv)
    print(MESSAGE_NON_IMPLEMENTE, file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
