"""Vues de la page Modèles (tâche 5.1 du change refonte du parcours de résultats).

Ce module ne lit aucun fichier et n'écrit rien : il transforme l'inventaire des
modèles prêts et l'instantané du créneau en dictionnaires simples, attendus par
`modeles.html`. Comme `vues_resultats`, il garde les valeurs brutes ; le gabarit
applique le format de premier niveau.

`reference` est la référence locale `<moteur>/<clé>` déjà acceptée en GET par
`/executions` (design D4) : la page s'en sert pour l'action « Utiliser », sans
nouvelle route ni jeton anti-CSRF, une référence locale n'étant pas un secret.

`actif` marque le modèle que l'opération longue en cours désigne par son
identifiant. Sa suppression est alors présentée comme indisponible dans le
gabarit ; le service la refuse de toute façon pendant une opération, et la route
POST le prouve pour une requête forgée. Aucune autre déduction n'est faite : un
modèle non visé reste supprimable dès que le créneau est libre.

Un modèle prêt n'a pas de nom convivial distinct de son identifiant : celui-ci
est le nom affiché au premier niveau, et l'identifiant canonique résolu reste
dans le détail avec la révision et les fichiers.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import Any

from transcription_bench.executions import SEPARATEUR_REFERENCE_MODELE
from transcription_bench.gestion_modeles import ModeleLocal
from transcription_bench.operations import ETAT_EN_COURS, InstantaneCreneau

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


def vues_modeles_locaux(
    inventaire: Sequence[ModeleLocal], instantane: InstantaneCreneau
) -> tuple[dict[str, Any], ...]:
    """Vues de l'inventaire, dans l'ordre du service, pour `modeles.html`.

    Chaque vue porte le nom affiché, le moteur, la famille, la variante GGUF
    éventuelle, la taille sur disque et la taille distante (brutes, formatées
    par le gabarit), la référence de préparation, la révision, l'identifiant
    complet, la date d'ajout, les fichiers retenus et l'état `actif`.
    """
    en_cours = instantane.etat == ETAT_EN_COURS
    return tuple(
        {
            "identifiant": modele.identifiant,
            "moteur": modele.moteur,
            "famille": modele.famille,
            "variante": modele.fichier_gguf,
            "taille_disque": modele.taille_disque,
            "taille_distante": modele.taille_distante,
            "reference": f"{modele.moteur}{SEPARATEUR_REFERENCE_MODELE}{modele.cle}",
            "cle": modele.cle,
            "id_resolu": modele.id_resolu,
            "commit": modele.commit,
            "date": modele.date,
            "fichiers": modele.fichiers,
            "actif": en_cours and instantane.cible == modele.identifiant,
        }
        for modele in inventaire
    )


def _decimal(nombre: int, unite: int, suffixe: str) -> str:
    """Valeur en unité binaire, tronquée au dixième, sans décimale nulle inutile."""
    dixiemes = math.floor((nombre / unite) * 10)
    entiers, reste = divmod(dixiemes, 10)
    return f"{entiers} {suffixe}" if reste == 0 else f"{entiers},{reste} {suffixe}"
