"""Adaptateur du moteur factice : textes simulés, sans modèle ni réseau.

Ce module est réservé au développement et aux tests du serveur de
développement. Il ne charge aucun modèle, n'écrit aucun fichier et n'ouvre
aucune connexion : `charger` ignore le chemin de modèle fourni (un emplacement
inexistant est normal pour le factice) et `transcrire` fabrique un texte
déterministe à partir de la seule durée de la fenêtre reçue. Aucune exécution
de ce moteur ne constitue une validation PC ni une mesure représentative.

Les valeurs renvoyées sont stables pour une même entrée : le runner les marque
comme factices et simulées dans ses événements, et ses mesures de temps et de
mémoire sont elles aussi remplacées par des valeurs simulées (voir
`engines/runner.py`). Les segments restent des valeurs fictives cohérentes avec
les métadonnées du contrat 4.2 (`reglages_effectifs`, `langue_imposee`,
`threads_appliques`), sans prétendre refléter un moteur réel.

Aucun import de bibliothèque tierce n'est nécessaire : le signal reçu est un
tableau `numpy` déjà chargé par le runner et seule sa taille est lue.
"""

from __future__ import annotations

from typing import Any

MARQUEUR_TEXTE = "[FACTICE]"


def charger(
    modele: dict[str, Any], threads_demandes: int, reglages: Any
) -> dict[str, Any]:
    """Contexte opaque du moteur factice, sans lecture de modèle ni I/O.

    Le chemin du modèle n'est volontairement pas consulté : un emplacement
    inexistant est normal pour ce moteur. Aucun réglage n'est appliqué.
    """
    return {
        "modele": modele.get("identifiant"),
        "threads_demandes": threads_demandes,
    }


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
