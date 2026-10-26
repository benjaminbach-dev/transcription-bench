"""Point d'entrée en ligne de commande du prototype.

Ordre de démarrage : verrou système d'instance sur le dossier de données,
récupération des exécutions antérieures (point d'injection de la tâche 6.5,
refus explicite par défaut), préparation des dossiers, création de
l'application, puis service HTTP par la seule API publique `waitress.serve`.
Une seconde instance est donc refusée avant toute récupération et sans toucher
aux données existantes. Un port occupé produit un message clair, un code de
sortie non nul, sans trace, et le verrou est libéré.

Le verrou n'est libéré qu'après le retour de `serve` et seulement si le thread
d'opération est terminé ; sinon il reste détenu jusqu'à la fin réelle du
processus, et aucun thread Python n'est tué. La supervision complète des
signaux, des moteurs et des installations relève de la tâche 6.6 et n'est pas
implémentée ici : `Ctrl+C` remonte comme `KeyboardInterrupt` et suit ce même
chemin borné.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable
from pathlib import Path

from waitress import serve

from engines.registre import creer_registre_fourni
from transcription_bench import paths
from transcription_bench.gestion_modeles import GestionModeles
from transcription_bench.instance import InstanceDejaActive, VerrouInstance
from transcription_bench.moteurs import InstallationMoteurs
from transcription_bench.operations import CreneauOperations
from transcription_bench.recuperation import (
    EtatAnterieurNonTraitable,
    verifier_executions_anterieures,
)
from transcription_bench.web import ConfigApplication, ServicesApplication, create_app

DESCRIPTION = (
    "Prototype local de comparaison de modèles de transcription française sur CPU."
)

PORT_DEFAUT = 8765
PORT_MIN = 1024
PORT_MAX = 65535
ADRESSE_ECOUTE = "127.0.0.1"
THREADS_REQUETES = 4
TAILLE_MAX_CORPS_SERVEUR = 1024 * 1024
DELAI_ARRET_SERVEUR = 5.0

CODE_REFUS = 2
CODE_ECHEC = 1


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


def main(
    argv: list[str] | None = None,
    *,
    recuperer: Callable[[Path], None] | None = None,
) -> int:
    """Verrouille, récupère, prépare, sert, puis libère le verrou.

    `recuperer` est le point d'injection de la récupération : par défaut la
    fonction de `transcription_bench.recuperation`, qui refuse le démarrage si
    un résultat antérieur n'est pas dans un état final. Elle n'est jamais
    appelée si une autre instance tient déjà le verrou.
    """
    arguments = construire_analyseur().parse_args(argv)
    dossier_data = paths.DOSSIER_DATA
    try:
        verrou = VerrouInstance(dossier_data).acquerir()
    except InstanceDejaActive as erreur:
        _signaler(str(erreur))
        return CODE_REFUS
    except OSError as erreur:
        _signaler(f"verrou d'instance indisponible dans {dossier_data} : {erreur}")
        return CODE_REFUS

    recuperation = verifier_executions_anterieures if recuperer is None else recuperer
    creneau: CreneauOperations | None = None
    installation: InstallationMoteurs | None = None
    code = 0
    try:
        try:
            recuperation(dossier_data)
        except EtatAnterieurNonTraitable as erreur:
            _signaler(str(erreur))
            code = CODE_REFUS
        else:
            paths.preparer_dossiers_data(dossier_data)
            creneau = CreneauOperations()
            registre = creer_registre_fourni()
            installation = InstallationMoteurs(dossier_data, registre, creneau)
            modeles = GestionModeles(dossier_data, registre, creneau, installation)
            application = create_app(
                ConfigApplication(port=arguments.port, dossier_data=dossier_data),
                ServicesApplication(
                    creneau=creneau,
                    moteurs=installation,
                    modeles=modeles,
                ),
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
            except OSError as erreur:
                _signaler(
                    f"impossible d'écouter sur http://{ADRESSE_ECOUTE}:{arguments.port} : "
                    f"{erreur}. Vérifiez qu'aucun autre programme n'utilise ce port, "
                    "puis relancez la commande avec --port N."
                )
                code = CODE_ECHEC
    finally:
        if not _clore_apres_arret(creneau, verrou, installation):
            code = CODE_ECHEC
    return code


def _clore_apres_arret(
    creneau: CreneauOperations | None,
    verrou: VerrouInstance,
    installation: InstallationMoteurs | None = None,
) -> bool:
    """Arrête le créneau et libère le verrou seulement si le travail est fini.

    `installation.arreter` termine le sous-processus uv éventuellement en cours
    avant l'arrêt du créneau : une installation ne doit pas rester orpheline. Ce
    nettoyage minimal ne remplace pas la supervision complète des signaux de la
    tâche 6.6 ; `CreneauOperations.arreter` est idempotent et borne son attente.
    Si le thread d'opération est encore actif, le verrou n'est pas libéré : il le
    sera par le système à la mort du processus, ce qui évite qu'une seconde
    instance ouvre le même dossier de données pendant un travail en cours.
    """
    if installation is not None:
        installation.arreter()
    if creneau is None:
        verrou.liberer()
        return True
    if creneau.arreter(DELAI_ARRET_SERVEUR):
        verrou.liberer()
        return True
    _signaler(
        "opération encore active : verrou d'instance conservé jusqu'à la fin du "
        "processus (aucun thread n'est tué)."
    )
    return False


def _signaler(message: str) -> None:
    """Écrit un message d'erreur en français sur la sortie d'erreur, sans trace."""
    print(f"transcription-bench : {message}", file=sys.stderr, flush=True)


if __name__ == "__main__":
    raise SystemExit(main())
