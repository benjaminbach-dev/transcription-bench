"""Point d'entrée en ligne de commande et supervision d'arrêt du prototype.

Ordre de démarrage : verrou système d'instance sur le dossier de données,
récupération des exécutions antérieures (tâche 6.5 : terminaison vérifiée du
moteur survivant, clôture en état `abandoned`, nettoyage des restes du dossier
de travail, refus explicite si un état douteux subsiste), préparation des
dossiers, création de l'application, puis service HTTP par la seule API publique
`waitress.serve`.
Une seconde instance est donc refusée avant toute récupération et sans toucher
aux données existantes. Un port occupé produit un message clair, un code de
sortie non nul, sans trace, et le verrou est libéré.

Arrêt normal (tâche 6.6) : un même gestionnaire de `transcription_bench.supervision`
reçoit `SIGINT` sur les deux OS et `SIGTERM` sous Linux ; dès le premier signal
il ignore ces signaux puis lève `KeyboardInterrupt` ou `SystemExit`. Ces deux
exceptions sont interceptées autour de l'appel public `waitress.serve` : le
message « Arrêt du serveur. » est affiché et le code de sortie vient du
nettoyage, pas de l'exception. Le nettoyage idempotent y passe le créneau à
l'arrêt, termine et collecte le groupe du moteur d'exécution et le sous-processus
d'installation, attend le thread d'opération, puis libère le verrou d'instance en
dernier — seulement si ce thread est réellement terminé. Sinon, le journal
signale « opération non close » et le verrou reste détenu jusqu'à la fin réelle
du processus ; aucun thread Python n'est tué. Les gestionnaires de signaux ne
sont rétablis qu'après ce nettoyage, et un signal reçu laisse `SIG_IGN` en place
jusqu'à la sortie. Aucun nettoyage n'a lieu dans un `teardown_appcontext` ni dans
un handler HTTP.

Limites assumées : un téléchargement exécuté dans le processus serveur peut
encore attendre ses E/S (aucun délai global de sortie garanti) ; les Ctrl+C
suivants sont ignorés ; tuer le processus ou fermer la console relève de la
récupération après arrêt brutal (tâche 6.5). Aucune relance du serveur dans le
même processus n'est prévue. `Ctrl+C` et `SIGTERM` restent à éprouver sur PC par
la sonde 1.7 et les tâches 8.x : les tests du serveur de développement ne valent
pas validation Linux ou Windows.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable
from pathlib import Path

from waitress import serve

from engines.registre import creer_registre_fourni
from transcription_bench import paths
from transcription_bench.execution_moteur import ExecutionMoteur
from transcription_bench.gestion_modeles import GestionModeles
from transcription_bench.instance import InstanceDejaActive, VerrouInstance
from transcription_bench.moteurs import InstallationMoteurs
from transcription_bench.operations import CreneauOperations
from transcription_bench.recuperation import (
    EtatAnterieurNonTraitable,
    recuperer_executions_anterieures,
)
from transcription_bench.supervision import (
    GestionnaireSignaux,
    NettoyageArret,
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

    `recuperer` est le point d'injection de la récupération, utilisé par les
    tests ; par défaut `recuperer_executions_anterieures`, qui termine le moteur
    survivant vérifié et clôt en `abandoned` les exécutions restées en cours, ou
    refuse le démarrage avec un code non nul si un état douteux subsiste. Elle
    n'est jamais appelée si une autre instance tient déjà le verrou.
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

    recuperation = (
        recuperer_executions_anterieures if recuperer is None else recuperer
    )
    nettoyage: NettoyageArret | None = None
    gestionnaire: GestionnaireSignaux | None = None
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
            # Le service d'exécution est construit une fois et injecté dans
            # l'application : la supervision d'arrêt doit pouvoir terminer le
            # moteur de l'exécution réellement en cours.
            execution = ExecutionMoteur(dossier_data, registre, installation)
            application = create_app(
                ConfigApplication(port=arguments.port, dossier_data=dossier_data),
                ServicesApplication(
                    creneau=creneau,
                    moteurs=installation,
                    modeles=modeles,
                    execution=execution,
                ),
            )
            nettoyage = NettoyageArret(
                verrou=verrou,
                creneau=creneau,
                execution=execution,
                installation=installation,
            )
            print(
                f"Interface disponible : http://{ADRESSE_ECOUTE}:{arguments.port}",
                flush=True,
            )
            # Les signaux d'arrêt sont surveillés autour du seul appel public
            # `serve` : le nettoyage applicatif suit dans le `finally` extérieur,
            # même si Waitress intercepte l'exception levée par le gestionnaire.
            gestionnaire = GestionnaireSignaux()
            gestionnaire.installer()
            try:
                serve(
                    application,
                    host=ADRESSE_ECOUTE,
                    port=arguments.port,
                    threads=THREADS_REQUETES,
                    max_request_body_size=TAILLE_MAX_CORPS_SERVEUR,
                )
            except OSError as erreur:
                _signaler(
                    f"impossible d'écouter sur http://{ADRESSE_ECOUTE}:{arguments.port} : "
                    f"{erreur}. Vérifiez qu'aucun autre programme n'utilise ce port, "
                    "puis relancez la commande avec --port N."
                )
                code = CODE_ECHEC
            except (KeyboardInterrupt, SystemExit):
                # Arrêt normal demandé par signal : le message d'arrêt et le code
                # de sortie viennent du nettoyage, exécuté dans le `finally`.
                code = 0
            if gestionnaire.recu:
                print("Arrêt du serveur.", flush=True)
    finally:
        if nettoyage is None:
            # Refus de récupération ou échec avant le service : aucun travail de
            # fond ne peut exister, seul le verrou d'instance est à libérer.
            nettoyage = NettoyageArret(verrou=verrou)
        if not nettoyage.executer():
            code = CODE_ECHEC
        if gestionnaire is not None:
            # Rétablissement seulement après la clôture : après un signal, il
            # conserve le `SIG_IGN` jusqu'à la sortie réelle du processus.
            gestionnaire.restaurer()
    return code


def _signaler(message: str) -> None:
    """Écrit un message d'erreur en français sur la sortie d'erreur, sans trace."""
    print(f"transcription-bench : {message}", file=sys.stderr, flush=True)


if __name__ == "__main__":
    raise SystemExit(main())
