"""Protocole d'événements partagé entre le runner et le serveur.

Ce module ne dépend que de la bibliothèque standard : le processus moteur
(`engines/runner.py`) et le serveur (tâche 6.3) l'importent tous les deux, sans
Flask. Un événement est un objet JSON sur **une seule ligne**, préfixé par
`##TB-EVENT## `.

Seules les lignes préfixées dont l'objet est un dictionnaire portant un `type`
connu et tous les champs requis de ce type sont des événements. Toute autre
ligne — sortie parasite d'une bibliothèque, ligne préfixée mais illisible ou
type inconnu — est ignorée par `analyser_ligne` : l'appelant la journalise sans
interrompre le flux.

Le préfixe, les types et leurs champs requis forment le contrat : seul
`engines/runner.py` émet ici, et aucun autre module ne doit analyser ces lignes
lui-même.
"""

from __future__ import annotations

import json
import sys
from typing import IO, Any

PREFIXE_EVENEMENT = "##TB-EVENT## "

TYPE_CHARGEMENT = "chargement"
TYPE_AUDIO = "audio"
TYPE_AUDIO_ERREUR = "audio_erreur"
TYPE_FIN = "fin"

# Champs dont la présence est exigée pour chaque type. Les valeurs peuvent être
# `null` (mesure indisponible) : le contrat distingue « absente » de « zéro ».
CHAMPS_REQUIS: dict[str, tuple[str, ...]] = {
    TYPE_CHARGEMENT: ("duree_s", "pic_memoire_octets"),
    TYPE_AUDIO: (
        "index",
        "nom",
        "texte",
        "segments",
        "duree_audio_s",
        "duree_transcription_s",
        "temps_cpu_s",
        "rtf",
        "fenetre_s",
        "decoupage",
        "nb_fenetres",
        "pic_memoire_octets",
        "reglages_effectifs",
        "langue_imposee",
        "threads_demandes",
        "threads_appliques",
    ),
    TYPE_AUDIO_ERREUR: ("index", "nom", "erreur"),
    TYPE_FIN: (
        "duree_chargement_s",
        "pic_memoire_octets",
        "audios_ok",
        "audios_erreur",
    ),
}

TYPES_EVENEMENTS: tuple[str, ...] = tuple(CHAMPS_REQUIS)


def formater_ligne(evenement: dict[str, Any]) -> str:
    """Sérialise un événement en une ligne préfixée, encodable en UTF-8.

    `ensure_ascii=False` conserve les textes non ASCII tels quels : le runner
    configure sa sortie standard en UTF-8, indépendamment de la page de codes
    de la console Windows.
    """
    charge = json.dumps(evenement, ensure_ascii=False, separators=(",", ":"))
    return f"{PREFIXE_EVENEMENT}{charge}\n"


def emettre(evenement: dict[str, Any], flux: IO[str] | None = None) -> None:
    """Écrit un événement et vide le tampon, pour un suivi immédiat."""
    sortie = sys.stdout if flux is None else flux
    sortie.write(formater_ligne(evenement))
    sortie.flush()


def analyser_ligne(ligne: str) -> dict[str, Any] | None:
    """Renvoie l'événement contenu dans une ligne, ou `None`.

    Une ligne non préfixée, un JSON invalide, un objet qui n'est pas un
    dictionnaire, un type inconnu ou un champ requis manquant donnent `None` :
    c'est une sortie parasite à journaliser, jamais une erreur bloquante.
    """
    if not isinstance(ligne, str) or not ligne.startswith(PREFIXE_EVENEMENT):
        return None
    charge = ligne[len(PREFIXE_EVENEMENT) :].strip()
    try:
        evenement = json.loads(charge)
    except json.JSONDecodeError:
        return None
    if not isinstance(evenement, dict):
        return None
    type_evenement = evenement.get("type")
    if type_evenement not in CHAMPS_REQUIS:
        return None
    if any(champ not in evenement for champ in CHAMPS_REQUIS[type_evenement]):
        return None
    return evenement
