"""Point d'entrée en ligne de commande du prototype.

La CLI prépare les dossiers de données, construit l'application Flask puis sert
celle-ci avec la seule API publique `waitress.serve`, sur l'adresse de bouclage
locale. Aucun moteur, poids ou accès réseau n'est mis en jeu au lancement.
"""

from __future__ import annotations

import argparse

from waitress import serve

from transcription_bench import paths
from transcription_bench.web import ConfigApplication, ServicesApplication, create_app

DESCRIPTION = (
    "Prototype local de comparaison de modèles de transcription française sur CPU."
)

PORT_DEFAUT = 8765
PORT_MIN = 1
PORT_MAX = 65535
ADRESSE_ECOUTE = "127.0.0.1"
THREADS_REQUETES = 4
TAILLE_MAX_CORPS_SERVEUR = 1024 * 1024


def port_valide(valeur: str) -> int:
    """Convertit le port et le borne, avec un message de refus explicite."""
    message = f"port invalide : {valeur!r} (entier attendu entre {PORT_MIN} et {PORT_MAX})"
    try:
        port = int(valeur)
    except ValueError:
        raise argparse.ArgumentTypeError(message) from None
    if not PORT_MIN <= port <= PORT_MAX:
        raise argparse.ArgumentTypeError(message)
    return port


def construire_analyseur() -> argparse.ArgumentParser:
    """Construit l'analyseur d'arguments, sans aucune lecture ni écriture."""
    analyseur = argparse.ArgumentParser(prog="transcription-bench", description=DESCRIPTION)
    analyseur.add_argument(
        "--port",
        type=port_valide,
        default=PORT_DEFAUT,
        metavar="N",
        help=f"port d'écoute local sur {ADRESSE_ECOUTE} (défaut : {PORT_DEFAUT})",
    )
    return analyseur


def main(argv: list[str] | None = None) -> int:
    """Prépare les dossiers de données puis sert l'interface locale."""
    analyseur = construire_analyseur()
    arguments = analyseur.parse_args(argv)
    dossier_data = paths.DOSSIER_DATA
    paths.preparer_dossiers_data(dossier_data)
    application = create_app(
        ConfigApplication(port=arguments.port, dossier_data=dossier_data),
        ServicesApplication(),
    )
    print(
        f"Interface disponible : http://{ADRESSE_ECOUTE}:{arguments.port}",
        flush=True,
    )
    try:
        serve(
            application,
            host=ADRESSE_ECOUTE,
            port=arguments.port,
            threads=THREADS_REQUETES,
            max_request_body_size=TAILLE_MAX_CORPS_SERVEUR,
        )
    except KeyboardInterrupt:
        print("Arrêt du serveur.", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
