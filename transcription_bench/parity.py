"""Table de parité entre les routes web et les commandes CLI (design D7).

Chaque route de l'application web possède exactement une entrée : soit les
chemins de commandes CLI qui couvrent la même fonction, soit une exclusion
documentée par une raison courte. Le test de parité confronte cette table aux
routes réelles de ``create_app`` et aux commandes réelles de l'analyseur CLI :
une route sans entrée, une entrée sans route ou une commande inexistante y fait
échouer la suite.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RouteParity:
    """Une route web, ses commandes CLI ou sa raison d'exclusion.

    ``commands`` contient un ou plusieurs chemins de commandes (segments de
    l'analyseur, par exemple ``("engines", "install")``) ; une entrée
    d'exclusion laisse ``commands`` vide et documente ``exclusion``.
    """

    method: str
    rule: str
    commands: tuple[tuple[str, ...], ...] = ()
    exclusion: str = ""


#: Table de parité web/CLI, confrontée aux routes réelles et à l'analyseur CLI.
WEB_CLI_PARITY: tuple[RouteParity, ...] = (
    RouteParity(
        method="GET",
        rule="/",
        exclusion="redirection vers Résultats : aucune fonction propre",
    ),
    RouteParity(
        method="GET",
        rule="/sumi.css",
        exclusion="ressource locale de la page, sans fonction",
    ),
    RouteParity(
        method="GET",
        rule="/app.css",
        exclusion="ressource locale de la page, sans fonction",
    ),
    RouteParity(
        method="GET",
        rule="/app.js",
        exclusion="ressource locale de la page, sans fonction",
    ),
    RouteParity(
        method="GET",
        rule="/audios",
        commands=(("audios", "list"),),
    ),
    RouteParity(
        method="POST",
        rule="/dossiers/verifier",
        commands=(("data", "check"),),
    ),
    RouteParity(
        method="GET",
        rule="/moteurs",
        commands=(("engines", "list"),),
    ),
    RouteParity(
        method="POST",
        rule="/moteurs/<identifiant>/installer",
        commands=(("engines", "install"),),
    ),
    RouteParity(
        method="GET",
        rule="/moteurs/<identifiant>/journal",
        commands=(("engines", "log"),),
    ),
    RouteParity(
        method="GET",
        rule="/modeles",
        commands=(("models", "list"),),
    ),
    RouteParity(
        method="POST",
        rule="/modeles/verifier",
        commands=(("models", "check"),),
    ),
    RouteParity(
        method="POST",
        rule="/modeles/telecharger",
        commands=(("models", "download"),),
    ),
    RouteParity(
        method="POST",
        rule="/modeles/supprimer",
        commands=(("models", "delete"),),
    ),
    RouteParity(
        method="GET",
        rule="/executions",
        commands=(("run", "options"), ("results", "history")),
    ),
    RouteParity(
        method="POST",
        rule="/executions/verifier",
        commands=(("run", "check"),),
    ),
    RouteParity(
        method="POST",
        rule="/executions/lancer",
        commands=(("run", "start"),),
    ),
    RouteParity(
        method="POST",
        rule="/executions/arreter",
        exclusion="arrêt par signal sur la commande en cours (design D4)",
    ),
    RouteParity(
        method="GET",
        rule="/executions/etat",
        exclusion="journal en flux, état final et code de sortie de la commande bloquante",
    ),
    RouteParity(
        method="GET",
        rule="/operation",
        exclusion="ancien lien : suivi couvert par la commande bloquante",
    ),
    RouteParity(
        method="GET",
        rule="/resultats",
        commands=(("results", "list"),),
    ),
    RouteParity(
        method="GET",
        rule="/resultats/<identifiant>",
        commands=(("results", "show"),),
    ),
    RouteParity(
        method="GET",
        rule="/resultats/aide",
        commands=(("results", "explain"),),
    ),
    RouteParity(
        method="GET",
        rule="/resultats/comparaison",
        commands=(("results", "list"),),
    ),
    RouteParity(
        method="GET",
        rule="/resultats/comparaison/<empreinte>",
        commands=(("compare",),),
    ),
)
