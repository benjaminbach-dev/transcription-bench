"""Adaptateur du moteur factice : textes et sorties simulés, sans modèle ni réseau.

Ce module est réservé au développement et aux tests du serveur de
développement. Il ne charge aucun modèle, n'écrit aucun fichier et n'ouvre
aucune connexion. Il sert deux familles, depuis ce seul module et sans autre
import :

- transcription (`charger`, `transcrire`) : `charger` ignore le chemin de modèle
  fourni (un emplacement inexistant est normal pour le factice) et `transcrire`
  fabrique un texte déterministe à partir de la seule durée de la fenêtre reçue ;
- extraction (`charger`, `reinitialiser`, `extraire`) : `charger` reçoit le
  schéma du job et `extraire` rend une sortie conforme à ce schéma, dérivée du
  seul schéma. Le texte source n'est jamais utilisé pour la sortie ; il ne sert
  qu'au comptage simulé des tokens d'entrée.

Les valeurs renvoyées sont stables pour une même entrée : le runner les marque
comme factices et simulées dans ses événements, et ses mesures de temps et de
mémoire sont elles aussi remplacées par des valeurs simulées (voir
`engines/runner.py` et `engines/runner_extraction.py`). Les segments restent des
valeurs fictives cohérentes avec les métadonnées du contrat 4.2
(`reglages_effectifs`, `langue_imposee`, `threads_appliques`), sans prétendre
refléter un moteur réel.

Le factice n'a pas de vraie limite de contexte : `extraire` ne lève jamais
`ErreurContexteInsuffisant`, ce refus étant couvert par les tests du runner avec
l'adaptateur de test. Aucune exécution de ce moteur ne constitue une validation
PC ni une mesure représentative.

Aucun import de bibliothèque tierce n'est nécessaire : le signal reçu est un
tableau `numpy` déjà chargé par le runner et seule sa taille est lue.
"""

from __future__ import annotations

import json
import math
from typing import Any

MARQUEUR_TEXTE = "[FACTICE]"
#: Nombre de caractères par token simulé (approximation grossière, sans tokenizer).
CARACTERES_PAR_TOKEN_SIMULE = 4
#: Tokens de prompt lus par seconde, valeur simulée et sans lien avec un PC.
VITESSE_LECTURE_SIMULEE_TPS = 400.0
#: Tokens générés par seconde, valeur simulée et sans lien avec un PC.
VITESSE_GENERATION_SIMULEE_TPS = 20.0
#: Temps CPU simulé, en multiple de la durée simulée d'inférence.
FACTEUR_CPU_EXTRACTION_SIMULE = 1.5


def charger(
    modele: dict[str, Any],
    threads_demandes: int,
    reglages: Any,
    schema: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Contexte opaque du moteur factice, sans lecture de modèle ni I/O.

    Le chemin du modèle n'est volontairement pas consulté : un emplacement
    inexistant est normal pour ce moteur. Aucun réglage n'est appliqué. Le
    `schema` n'est fourni que pour l'extraction ; sans lui, le contexte est celui
    de la transcription, inchangé.
    """
    contexte: dict[str, Any] = {
        "modele": modele.get("identifiant"),
        "threads_demandes": threads_demandes,
    }
    if schema is not None:
        contexte["schema"] = schema
    return contexte


def reinitialiser(moteur: dict[str, Any]) -> None:
    """Ne fait rien : le factice ne garde aucun état entre deux sources.

    Le contexte rendu par `charger` ne contient ni cache ni échantillonneur à
    vider. L'opération existe pour respecter le contrat du runner, qui l'appelle
    avant chaque source.
    """
    return None


def extraire(
    moteur: dict[str, Any],
    messages: list[dict[str, str]],
    reglages: Any,
) -> dict[str, Any]:
    """Rend une sortie conforme au schéma et des mesures simulées, sans modèle.

    La sortie est le JSON compact de valeurs dérivées du seul schéma ; les
    compteurs et durées sont calculés de façon déterministe à partir de la
    longueur des messages et de la sortie. La cause de fin est toujours `arret`.
    """
    if "schema" not in moteur:
        raise ValueError("schéma absent : charger doit recevoir le schéma d'extraction")
    sortie = json.dumps(
        _objet_factice(moteur["schema"]), ensure_ascii=False, separators=(",", ":")
    )
    longueur_prompt = sum(len(message["content"]) for message in messages)
    tokens_entree = _tokens_simules(longueur_prompt)
    tokens_sortie = _tokens_simules(len(sortie))
    delai_premier_token = round(tokens_entree / VITESSE_LECTURE_SIMULEE_TPS, 3)
    duree_generation = round((tokens_sortie - 1) / VITESSE_GENERATION_SIMULEE_TPS, 3)
    return {
        "sortie_brute": sortie,
        "tokens_entree": tokens_entree,
        "tokens_sortie": tokens_sortie,
        "fin": "arret",
        "delai_premier_token_s": delai_premier_token,
        "duree_generation_s": duree_generation,
        "temps_cpu_s": round(
            (delai_premier_token + duree_generation) * FACTEUR_CPU_EXTRACTION_SIMULE,
            3,
        ),
    }


def _tokens_simules(longueur: int) -> int:
    """Nombre de tokens simulé d'un texte de `longueur` caractères, au moins un."""
    return max(1, math.ceil(longueur / CARACTERES_PAR_TOKEN_SIMULE))


def _objet_factice(schema: dict[str, Any]) -> dict[str, Any]:
    """Objet de premier niveau : une valeur factice par propriété du schéma."""
    if schema.get("type") != "object":
        raise ValueError("schéma d'extraction attendu sous forme d'objet")
    return {
        cle: _valeur_factice(cle, sous_schema)
        for cle, sous_schema in schema["properties"].items()
    }


def _valeur_factice(cle: str, schema: dict[str, Any]) -> Any:
    """Valeur conforme au sous-schéma D2 (jamais `null`, jamais le texte source).

    Un `anyOf` se réduit à son alternative non nulle. Un texte devient une chaîne
    portant la marque factice et la clé ; un tableau avec `minItems` reçoit une
    seule entrée ; un tableau sans `minItems` (`autres_informations`) reste vide.
    """
    if "anyOf" in schema:
        alternatives = [
            option for option in schema["anyOf"] if option.get("type") != "null"
        ]
        if len(alternatives) != 1:
            raise ValueError(f"alternative non prise en charge pour {cle!r}")
        schema = alternatives[0]
    type_valeur = schema.get("type")
    if type_valeur == "string":
        return f"{MARQUEUR_TEXTE} contenu factice de {cle}"
    if type_valeur == "array":
        if schema.get("minItems", 0) < 1:
            return []
        return [_valeur_factice(cle, schema["items"])]
    if type_valeur == "object":
        return _objet_factice(schema)
    raise ValueError(f"type non pris en charge pour {cle!r} : {type_valeur!r}")


def transcrire(
    moteur: dict[str, Any],
    signal: Any,
    taux_echantillonnage: int,
    reglages: Any,
) -> dict[str, Any]:
    """Renvoie une transcription simulée, déterministe pour une fenêtre donnée.

    Le texte et les segments ne dépendent que de la durée de la fenêtre reçue ;
    ils sont en français et portent le marqueur `[FACTICE]`. Aucune langue n'est
    imposée et aucun thread appliqué n'est affirmé : ce moteur n'en applique pas.
    """
    duree = signal.size / taux_echantillonnage
    texte = (
        f"{MARQUEUR_TEXTE} transcription simulée de {duree:.1f} s, "
        "sans modèle ni inférence réelle."
    )
    return {
        "texte": texte,
        "segments": [
            {"debut_s": 0.0, "fin_s": round(duree, 3), "texte": texte},
        ],
        "reglages_effectifs": {},
        "langue_imposee": None,
        "threads_appliques": None,
    }
