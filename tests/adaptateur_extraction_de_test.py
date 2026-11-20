"""Adaptateur de test du runner d'extraction, sans aucun moteur réel.

Ce module n'est pas un adaptateur de production : il n'apparaît dans aucune
déclaration fournie. `tests/test_runner.py` construit un registre de test dont la
déclaration pointe ici, comme pour `tests/adaptateur_runner_de_test.py` côté
transcription. Il respecte le contrat décrit dans `engines/runner_extraction.py` :
`charger`, `reinitialiser` et `extraire`.

Le refus de contexte est décidé ici, comme le ferait l'adaptateur réel qui seul
tokenise : le nombre de tokens du prompt est fixé par le scénario de chaque
source, et la génération n'est jamais journalisée pour une source refusée. Le
journal `journal` rend donc la séquence observable : `charger`, `reinitialiser`,
`generer`, dans l'ordre des appels.

Le dict rendu par `charger` ne porte `meta_chargement` que si le scénario le demande
(`configurer(meta=...)`) ; sans lui, la clé est absente, comme pour le moteur
factice. Les comptes natifs passent par le scénario d'une source (`comptes_natifs`).
"""

from __future__ import annotations

import json
import os
from typing import Any

from engines.declarations import DEFAUT_CONTEXTE_LLAMA, DEFAUT_SORTIE_MAX_LLAMA
from engines.runner_extraction import ErreurContexteInsuffisant

#: Valeur de `meta` signifiant « pas de `meta_chargement` » (distincte de `None`).
AUCUNE_META = object()

ETAT: dict[str, Any] = {
    "echec_charger": None,
    "scenario": [],
    "tokens_entree": 812,
    "meta": AUCUNE_META,
}

compteur_chargements = 0
journal: list[str] = []
appels_generation: list[dict[str, Any]] = []
derniere_consigne: dict[str, Any] | None = None


def configurer(
    *,
    echec_charger: str | None = None,
    scenario: list[Any] | None = None,
    tokens_entree: int = 812,
    meta: Any = AUCUNE_META,
) -> None:
    """Remet le module dans un état connu avant chaque test.

    `scenario` donne le comportement de chaque appel à `extraire`, dans l'ordre :
    un dictionnaire remplace des champs du résultat par défaut (`tokens_entree`
    est lu par le refus de contexte, `brut` rend le résultat tel quel), une
    exception est levée telle quelle. Sans entrée, le résultat est conforme.
    """
    global compteur_chargements, derniere_consigne
    ETAT["echec_charger"] = echec_charger
    ETAT["scenario"] = list(scenario or [])
    ETAT["tokens_entree"] = tokens_entree
    ETAT["meta"] = meta
    compteur_chargements = 0
    derniere_consigne = None
    journal.clear()
    appels_generation.clear()


def sortie_conforme(schema: dict[str, Any]) -> str:
    """Sortie valide du schéma : cases non mentionnées (`null`), section vide."""
    valeurs: dict[str, Any] = {
        cle: None for cle in schema["properties"] if cle != "autres_informations"
    }
    valeurs["autres_informations"] = []
    return json.dumps(valeurs, ensure_ascii=False)


def charger(
    modele: dict[str, Any],
    threads_demandes: int,
    reglages: Any,
    schema: dict[str, Any],
) -> dict[str, Any]:
    """Charge une fois : consigne les arguments, puis simule un échec de grammaire."""
    global compteur_chargements, derniere_consigne
    compteur_chargements += 1
    journal.append("charger")
    derniere_consigne = {
        "modele": dict(modele),
        "threads_demandes": threads_demandes,
        "reglages": dict(reglages),
        "schema": schema,
        "hf_hub_offline": os.environ.get("HF_HUB_OFFLINE"),
    }
    if ETAT["echec_charger"] is not None:
        raise ValueError(ETAT["echec_charger"])
    moteur: dict[str, Any] = {"schema": schema}
    if ETAT["meta"] is not AUCUNE_META:
        moteur["meta_chargement"] = ETAT["meta"]
    return moteur


def reinitialiser(moteur: dict[str, Any]) -> None:
    """Réinitialisation du contexte : consignée dans l'ordre des appels."""
    journal.append("reinitialiser")


def extraire(
    moteur: dict[str, Any],
    messages: list[dict[str, str]],
    reglages: Any,
) -> dict[str, Any]:
    """Une source : refus de contexte avant génération, sinon résultat simulé."""
    comportement = ETAT["scenario"].pop(0) if ETAT["scenario"] else {}
    if isinstance(comportement, BaseException):
        raise comportement
    tokens_entree = comportement.get("tokens_entree", ETAT["tokens_entree"])
    sortie_max = reglages.get("sortie_max", DEFAUT_SORTIE_MAX_LLAMA)
    contexte = reglages.get("contexte", DEFAUT_CONTEXTE_LLAMA)
    if tokens_entree + sortie_max > contexte:
        raise ErreurContexteInsuffisant(tokens_entree, sortie_max, contexte)
    journal.append("generer")
    appels_generation.append(
        {"messages": [dict(message) for message in messages]}
    )
    if "brut" in comportement:
        return comportement["brut"]
    resultat: dict[str, Any] = {
        "sortie_brute": sortie_conforme(moteur["schema"]),
        "tokens_entree": tokens_entree,
        "tokens_sortie": 24,
        "fin": "arret",
        "delai_premier_token_s": 1.25,
        "duree_generation_s": 2.5,
        "temps_cpu_s": 2.6,
    }
    resultat.update(
        {
            cle: valeur
            for cle, valeur in comportement.items()
            if cle != "tokens_entree"
        }
    )
    return resultat
