"""Format lisible des tailles de modèles, partagé par la CLI.

La page Modèles a été retirée de l'interface web (change `alleger-interface-web`,
tâche 1.1) : ce module ne porte plus que le formatage des tailles, utilisé par
les commandes `models` de la CLI. Il ne lit aucun fichier et n'écrit rien.
"""

from __future__ import annotations

import math
from typing import Any

#: Tailles de poids en unités binaires conventionnelles : 1 Mio = 2²⁰ octets.
#: Les mesures de RAM gardent les unités SI décimales du design D2 ; ce sont
#: deux grandeurs distinctes, et aucune taille de fichier n'est réécrite.
OCTETS_PAR_MIO = 1024**2
OCTETS_PAR_GIO = 1024**3
TAILLE_INCONNUE = "taille inconnue"
TAILLE_INTERPRETABLE_ABSENTE = "indisponible"


def formater_taille_modele(valeur: Any) -> str:
    """Taille de modèle lisible en Mio ou Gio, jamais en octets bruts.

    `1 Mio = 2²⁰ octets` et `1 Gio = 2³⁰ octets` : ce sont les unités des
    tailles de poids, distinctes des unités SI décimales des mesures de RAM.
    Une taille absente affiche « taille inconnue », une valeur qui n'est pas un
    entier d'octets positif ou nul « indisponible » : aucune valeur inconnue
    n'est remplacée par zéro. Le dixième est tronqué, sans décimale nulle
    inutile, et une petite valeur positive garde une borne (« < 0,1 Mio »).
    """
    if valeur is None:
        return TAILLE_INCONNUE
    if isinstance(valeur, bool) or not isinstance(valeur, int) or valeur < 0:
        return TAILLE_INTERPRETABLE_ABSENTE
    if valeur == 0:
        return "0 Mio"
    if valeur * 10 < OCTETS_PAR_MIO:
        return "< 0,1 Mio"
    if valeur < OCTETS_PAR_GIO:
        return _decimal(valeur, OCTETS_PAR_MIO, "Mio")
    return _decimal(valeur, OCTETS_PAR_GIO, "Gio")


def _decimal(nombre: int, unite: int, suffixe: str) -> str:
    """Valeur en unité binaire, tronquée au dixième, sans décimale nulle inutile."""
    dixiemes = math.floor((nombre / unite) * 10)
    entiers, reste = divmod(dixiemes, 10)
    return f"{entiers} {suffixe}" if reste == 0 else f"{entiers},{reste} {suffixe}"
