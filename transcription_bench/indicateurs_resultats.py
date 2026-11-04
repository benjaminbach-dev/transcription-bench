"""Ratios et formats de premier niveau des résultats (tâche 1.2).

Module **pur** : aucune E/S, aucun accès au matériel du poste qui consulte, aucune
dépendance à Flask. Les ratios ne s'appliquent qu'aux valeurs **consignées** de
l'essai ; les formats de premier niveau sont distincts des formats détaillés de
`formats.html` (trois décimales, octets bruts), qui restent inchangés.

**Ratios.** Le CPU moyen du moteur vaut
`100 × temps CPU / (durée de transcription × processeurs logiques)` ; la part de
RAM vaut `100 × pic mémoire / RAM totale`. Les booléens, les nombres non finis,
les valeurs négatives, un dénominateur nul ou une capacité absente donnent
`None`, jamais zéro. Un ratio strictement supérieur à 100 % donne aussi `None`,
sans être ramené à 100 % : un léger dépassement traduit une mesure grossière ou
non simultanée, pas une surcapacité. Un zéro réellement mesuré reste valide.

**Formats.** Les durées s'expriment en secondes, minutes ou heures ; la mémoire
en Mo et Go **décimaux** (1 Mo = 10⁶ octets, 1 Go = 10⁹ octets) ; les
pourcentages sont entiers. Une petite valeur strictement positive s'affiche avec
une borne (« < 0,1 s », « < 0,1 Mo », « < 1 % ») et n'est jamais arrondie à zéro.
Les valeurs négatives, non finies ou d'un autre type affichent « indisponible ».
Aucun de ces calculs ne réécrit un fichier de résultat.
"""

from __future__ import annotations

import math
from typing import Any

#: Libellés de premier niveau : absence distincte d'une valeur brute invalide.
NON_MESURE = "non mesuré"
INDISPONIBLE = "indisponible"

#: Unités décimales SI, jamais binaires : 1 Mo = 10⁶ octets, 1 Go = 10⁹ octets.
OCTETS_PAR_MO = 10**6
OCTETS_PAR_GO = 10**9


def ratio_cpu(
    temps_cpu_s: Any, duree_transcription_s: Any, coeurs_logiques: Any
) -> float | None:
    """Occupation moyenne du moteur, en pourcentage des processeurs logiques.

    `temps_cpu_s` est le temps CPU du seul processus moteur (threads compris),
    `duree_transcription_s` la durée de transcription de l'audio et
    `coeurs_logiques` le compte entier positif **consigné** avec l'essai.
    Une entrée invalide ou un ratio supérieur à 100 % donne `None`, sans écrêtage.
    """
    temps_cpu = _nombre_fini(temps_cpu_s)
    duree = _nombre_fini(duree_transcription_s)
    coeurs = _entier_positif(coeurs_logiques)
    if temps_cpu is None or duree is None or coeurs is None:
        return None
    if temps_cpu < 0 or duree <= 0:
        return None
    # Diviser avant de multiplier évite les débordements intermédiaires pour
    # des mesures finies dont le rapport est pourtant interprétable.
    try:
        return _ratio((temps_cpu / duree / coeurs) * 100)
    except OverflowError:
        return None


def ratio_ram(pic_memoire_octets: Any, ram_totale_octets: Any) -> float | None:
    """Part de la RAM totale consignée occupée par le pic du moteur.

    Le pic est celui de l'essai, cumulatif ; la capacité est celle du matériel
    enregistré avec l'essai, jamais celle du poste qui consulte. Une entrée
    invalide ou un ratio supérieur à 100 % donne `None`, sans écrêtage.
    """
    pic = _nombre_fini(pic_memoire_octets)
    totale = _nombre_fini(ram_totale_octets)
    if pic is None or totale is None:
        return None
    if pic < 0 or totale <= 0:
        return None
    return _ratio((pic / totale) * 100)


def formater_duree_premier_niveau(valeur: Any) -> str:
    """Durée lisible : secondes, « 1 min 37 s » ou « 2 h 5 min ».

    Zéro reste « 0 s ». Une valeur strictement positive sous la seconde garde un
    dixième (« 0,4 s ») ou une borne (« < 0,1 s »). Les valeurs invalides ou
    négatives affichent « indisponible ».
    """
    if valeur is None:
        return NON_MESURE
    nombre = _nombre_fini(valeur)
    if nombre is None or nombre < 0:
        return INDISPONIBLE
    if nombre == 0:
        return "0 s"
    if nombre < 0.1:
        return "< 0,1 s"
    if nombre < 1:
        # Troncature au dixième : une valeur positive ne devient jamais « 0 s ».
        return f"0,{math.floor(nombre * 10)} s"
    secondes = math.floor(nombre)
    if secondes < 60:
        return f"{secondes} s"
    if secondes < 3600:
        minutes, reste = divmod(secondes, 60)
        return f"{minutes} min" if reste == 0 else f"{minutes} min {reste} s"
    heures, reste = divmod(secondes, 3600)
    minutes = reste // 60
    return f"{heures} h" if minutes == 0 else f"{heures} h {minutes} min"


def formater_memoire_premier_niveau(valeur: Any) -> str:
    """Mémoire lisible en Mo ou Go décimaux, avec une décimale utile.

    `1 Mo = 10⁶ octets` et `1 Go = 10⁹ octets` : aucune unité binaire n'est
    utilisée. Zéro reste « 0 Mo » ; une petite valeur positive sous 0,1 Mo
    s'affiche « < 0,1 Mo ». Les valeurs invalides ou négatives affichent
    « indisponible ».
    """
    if valeur is None:
        return NON_MESURE
    nombre = _nombre_fini(valeur)
    if nombre is None or nombre < 0:
        return INDISPONIBLE
    if nombre == 0:
        return "0 Mo"
    if nombre < 0.1 * OCTETS_PAR_MO:
        return "< 0,1 Mo"
    if nombre < OCTETS_PAR_GO:
        return _decimal(nombre, OCTETS_PAR_MO, "Mo")
    return _decimal(nombre, OCTETS_PAR_GO, "Go")


def formater_pourcentage_premier_niveau(valeur: Any) -> str:
    """Pourcentage entier ; « < 1 % » pour une petite valeur positive.

    Zéro reste « 0 % ». La troncature évite de surestimer la valeur mesurée ;
    une valeur positive n'est jamais présentée comme zéro. Les valeurs invalides
    ou négatives affichent « indisponible ».
    """
    if valeur is None:
        return NON_MESURE
    nombre = _nombre_fini(valeur)
    if nombre is None or not 0 <= nombre <= 100:
        return INDISPONIBLE
    if nombre == 0:
        return "0 %"
    if nombre < 1:
        return "< 1 %"
    # Neutraliser le bruit binaire d'un ratio exact (29 -> 28,999999999999996)
    # avant la troncature ; la valeur brute servant au tri reste inchangée.
    return f"{math.floor(round(nombre, 9))} %"


def _ratio(calcul: float) -> float | None:
    """Ratio interprétable, ou `None` s'il est non fini ou supérieur à 100 %.

    Les entrées sont déjà validées : un dépassement n'est pas écrêté, il rend le
    ratio indisponible pour l'interprétation.
    """
    if not math.isfinite(calcul) or calcul > 100:
        return None
    return calcul


def _decimal(nombre: float, unite: int, suffixe: str) -> str:
    """Valeur en unité SI, tronquée au dixième, sans décimale nulle inutile."""
    dixiemes = math.floor((nombre / unite) * 10)
    entiers, reste = divmod(dixiemes, 10)
    return f"{entiers} {suffixe}" if reste == 0 else f"{entiers},{reste} {suffixe}"


def _nombre_fini(valeur: Any) -> float | None:
    """Nombre fini, ou `None` : booléens, NaN et infinis ne sont pas des mesures."""
    if isinstance(valeur, bool) or not isinstance(valeur, (int, float)):
        return None
    try:
        return float(valeur) if math.isfinite(valeur) else None
    except OverflowError:
        return None


def _entier_positif(valeur: Any) -> int | None:
    """Entier strict positif, ou `None` : un flottant n'est pas un compte de cœurs."""
    return valeur if type(valeur) is int and valeur > 0 else None
