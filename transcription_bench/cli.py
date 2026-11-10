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
from collections.abc import Callable, Sequence
from pathlib import Path

from waitress import serve

from transcription_bench import paths
from transcription_bench.command_session import (
    CODE_ECHEC,
    CODE_REFUS,
    CommandSpec,
    run_session,
)
from transcription_bench.composition import SessionRefused, open_data_session
from transcription_bench.output import add_json_option, configure_utf8_streams
from transcription_bench.supervision import GestionnaireSignaux
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

#: Commandes à résultat unique enregistrées publiquement : aucune pour l'instant ;
#: les tests les injectent par `main(commandes=...)`.
COMMANDS: tuple[CommandSpec, ...] = ()

COMMAND_SERVE = "serve"
EXIT_CODES_HELP = (
    "codes de sortie :\n"
    "  0  succès ou arrêt normal\n"
    "  1  échec (port indisponible, libération du verrou impossible)\n"
    "  2  refus ou argument invalide (verrou tenu, état antérieur non traitable)"
)
COMMAND_EXIT_CODES_HELP = (
    "codes de sortie :\n"
    "  0  succès\n"
    "  1  échec de l'opération (installation, téléchargement, exécution en erreur,\n"
    "     vérification en échec ou audio en erreur)\n"
    "  2  refus ou argument invalide (verrou tenu, ressource non prête, dépôt incompatible)\n"
    "  3  interrompu par un signal (Ctrl+C, SIGTERM sous Linux)"
)
PORT_HELP = f"port d'écoute local sur {ADRESSE_ECOUTE} (défaut : {PORT_DEFAUT})"


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


def construire_analyseur(
    commands: Sequence[CommandSpec] = (),
) -> argparse.ArgumentParser:
    """Construit l'analyseur d'arguments, sans aucune lecture ni écriture.

    Sans sous-commande, la racine lance `serve` (`set_defaults`). La racine et
    `serve` portent `--port` ; celui de `serve` a `default=argparse.SUPPRESS`
    pour ne pas réécrire le port donné avant la sous-commande. Aucune autre
    option n'est acceptée par `serve` (pas de `--json`). `commands` ajoute un
    sous-analyseur par commande ; `serve` et les noms dupliqués sont refusés.
    """
    analyseur = argparse.ArgumentParser(
        prog="transcription-bench",
        description=DESCRIPTION,
        epilog=(
            "Sans sous-commande, le serveur web est lancé comme avec « serve ».\n\n"
            + EXIT_CODES_HELP
            + "\n\nLes commandes ont leurs propres codes de sortie : voir leur aide."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        add_help=False,
    )
    _add_help_option(analyseur)
    analyseur.add_argument(
        "--port",
        type=port_valide,
        default=PORT_DEFAUT,
        metavar="N",
        help=PORT_HELP,
    )
    subcommands = analyseur.add_subparsers(
        dest="command", title="sous-commandes"
    )
    # Après `add_subparsers` : l'action de sous-commande reprend ce défaut.
    analyseur.set_defaults(command=COMMAND_SERVE)
    serve = subcommands.add_parser(
        COMMAND_SERVE,
        help="lance le serveur web local (commande par défaut)",
        description=f"Lance le serveur web local sur {ADRESSE_ECOUTE}.",
        epilog=EXIT_CODES_HELP,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        add_help=False,
    )
    _add_help_option(serve)
    serve.add_argument(
        "--port",
        type=port_valide,
        default=argparse.SUPPRESS,
        metavar="N",
        help=PORT_HELP,
    )
    reserved_names = {COMMAND_SERVE}
    for command in commands:
        if command.name in reserved_names:
            raise ValueError(
                f"nom de commande dupliqué ou réservé : {command.name!r}"
            )
        reserved_names.add(command.name)
        command_parser = subcommands.add_parser(
            command.name,
            help=command.help_text,
            description=command.help_text,
            epilog=COMMAND_EXIT_CODES_HELP,
            formatter_class=argparse.RawDescriptionHelpFormatter,
            add_help=False,
        )
        _add_help_option(command_parser)
        command.configure(command_parser)
        add_json_option(command_parser)
    return analyseur


def _add_help_option(analyseur: argparse.ArgumentParser) -> None:
    """Ajoute `-h/--help` avec un libellé français."""
    analyseur.add_argument(
        "-h",
        "--help",
        action="help",
        default=argparse.SUPPRESS,
        help="affiche cette aide et quitte",
    )


def main(
    argv: list[str] | None = None,
    *,
    recuperer: Callable[[Path], None] | None = None,
    commands: Sequence[CommandSpec] | None = None,
) -> int:
    """Verrouille, récupère, prépare, sert, puis libère le verrou.

    `recuperer` est le point d'injection de la récupération, utilisé par les
    tests ; par défaut `recuperer_executions_anterieures`, qui termine le moteur
    survivant vérifié et clôt en `abandoned` les exécutions restées en cours, ou
    refuse le démarrage avec un code non nul si un état douteux subsiste. Elle
    n'est jamais appelée si une autre instance tient déjà le verrou.

    Toute sous-commande autre que `serve` est une commande de `commands`,
    exécutée par `command_session.run_session` (session close dans tous les cas).
    """
    # Avant l'analyse : l'aide écrit aussi sur la sortie standard.
    configure_utf8_streams(sys.stdout, sys.stderr)
    if commands is None:
        commands = COMMANDS
    arguments = construire_analyseur(commands).parse_args(argv)
    dossier_data = paths.DOSSIER_DATA
    if arguments.command != COMMAND_SERVE:
        command = next(c for c in commands if c.name == arguments.command)
        return run_session(
            dossier_data,
            lambda services, signal_flag: command.run(arguments, services, signal_flag),
            recover=recuperer,
        )
    try:
        session = open_data_session(dossier_data, recover=recuperer)
    except SessionRefused as erreur:
        _signaler(str(erreur))
        for diagnostic in erreur.diagnostics:
            _signaler(diagnostic)
        return CODE_REFUS if erreur.lock_released else CODE_ECHEC

    gestionnaire: GestionnaireSignaux | None = None
    code = 0
    try:
        services = session.services
        application = create_app(
            ConfigApplication(port=arguments.port, dossier_data=dossier_data),
            ServicesApplication(
                creneau=services.operations,
                moteurs=services.engines,
                modeles=services.models,
                executions=services.preparation,
                execution=services.execution,
                resultats=services.results,
            ),
        )
        print(
            f"Interface disponible : http://{ADRESSE_ECOUTE}:{arguments.port}",
            flush=True,
        )
        # Les signaux d'arrêt sont surveillés autour du seul appel public
        # `serve` : la clôture de la session suit dans le `finally` extérieur,
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
            # de sortie viennent de la clôture, exécutée dans le `finally`.
            code = 0
        if gestionnaire.recu:
            print("Arrêt du serveur.", flush=True)
    finally:
        if not session.close():
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
