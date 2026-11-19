"""Table de parité entre les pages web de consultation et les commandes CLI (design D3).

Le change `alleger-interface-web` inverse le sens de la parité : la CLI est la
seule interface d'action. Chaque page de consultation de l'application web a
une commande de lecture équivalente ; la CLI peut offrir davantage, sans page.
Chaque route de l'application possède exactement une entrée : soit les chemins
de commandes CLI qui couvrent la même fonction, soit une exclusion documentée
pour l'accueil et les ressources fixes servies. Le test de parité confronte
cette table aux routes réelles de ``create_app`` et à l'analyseur CLI : une
route sans entrée, une entrée sans route, une commande inexistante ou une page
sans commande de lecture y fait échouer la suite.
Les exclusions admises et les commandes de lecture sont listées dans
``tests/test_parity.py``, hors de ce module : élargir la table exige aussi de
modifier ce test.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RouteParity:
    """Une route web, ses commandes CLI de lecture ou sa raison d'exclusion.

    ``commands`` contient un ou plusieurs chemins de commandes (segments de
    l'analyseur, par exemple ``("results", "list")``) ; une entrée d'exclusion
    laisse ``commands`` vide et documente ``exclusion``.
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
    RouteParity(
        method="GET",
        rule="/executions",
        commands=(("results", "history"),),
    ),
)
