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

Les événements `extraction` et `extraction_erreur` sont validés strictement : un
champ inconnu, un type inattendu ou une combinaison incohérente de `conforme`,
`valeur` et `motif` les fait refuser. Les événements de transcription gardent la
validation par champs requis seule, sans changement.

Le préfixe, les types et leurs champs requis forment le contrat : seul
`engines/runner.py` émet ici, et aucun autre module ne doit analyser ces lignes
lui-même.

Chaque événement porte sa provenance : `factice` et `mesures_simulees` valent
`False` pour un moteur réel et `True` pour le moteur factice (tâche 4.3). Ces
deux champs sont obligatoires pour que le serveur, la comparaison et toute
exploitation ultérieure ne puissent pas confondre un texte ou une mesure simulés
avec une mesure de moteur réel. Ils sont fixés par la déclaration du moteur dans
le code, jamais par le job.
"""

from __future__ import annotations

import json
import math
import sys
from collections.abc import Callable
from typing import IO, Any

#: Marqueur nu d'une ligne d'événement. Seul le préfixe avec espace définit un
#: événement analysable ; mais toute ligne qui commence par le marqueur nu,
#: espace ou non, reste une ligne d'événement pour les journaux du serveur :
#: elle peut contenir une sortie de modèle et n'y est jamais recopiée.
MARQUEUR_EVENEMENT = "##TB-EVENT##"
PREFIXE_EVENEMENT = f"{MARQUEUR_EVENEMENT} "

TYPE_CHARGEMENT = "chargement"
TYPE_AUDIO = "audio"
TYPE_AUDIO_ERREUR = "audio_erreur"
TYPE_FIN = "fin"
# Événements d'extraction (design D5 à D7) : `extraction` pour une source traitée,
# `extraction_erreur` pour une source en erreur côté moteur.
TYPE_EXTRACTION = "extraction"
TYPE_EXTRACTION_ERREUR = "extraction_erreur"

# Longueur maximale du motif d'une source non conforme ou en erreur. Un motif
# décrit l'échec : il ne recopie jamais le texte source ni la sortie du modèle.
LONGUEUR_MAX_MOTIF = 200
FINS_GENERATION: tuple[str, ...] = ("arret", "limite")


def _entier(valeur: Any) -> bool:
    return isinstance(valeur, int) and not isinstance(valeur, bool) and valeur >= 0


def _nombre(valeur: Any) -> bool:
    if not isinstance(valeur, (int, float)) or isinstance(valeur, bool):
        return False
    try:
        # `math.isfinite` lève `OverflowError` pour un entier trop grand pour un
        # flottant : un tel nombre est invalide, jamais une exception.
        return math.isfinite(valeur) and valeur >= 0
    except OverflowError:
        return False


def _booleen(valeur: Any) -> bool:
    return isinstance(valeur, bool)


def _texte(valeur: Any) -> bool:
    return isinstance(valeur, str)


def _motif(valeur: Any) -> bool:
    return isinstance(valeur, str) and 0 < len(valeur) <= LONGUEUR_MAX_MOTIF


def _objet(valeur: Any) -> bool:
    return isinstance(valeur, dict)


def _fin(valeur: Any) -> bool:
    return valeur in FINS_GENERATION


def _ou_nul(verificateur: Callable[[Any], bool]) -> Callable[[Any], bool]:
    """Vérificateur d'un champ qui vaut `null` quand il est absent (jamais zéro)."""
    return lambda valeur: valeur is None or verificateur(valeur)


# Validation stricte des événements d'extraction : seuls ces champs sont admis,
# chacun avec son type. `valeur` (objet décodé) n'est renseigné que si la sortie
# est conforme ; `motif` seulement sinon ; `sortie_brute` vaut `null` si aucun
# token n'a été généré. La cohérence entre ces champs est contrôlée par
# `_coherent_extraction`.
VERIFICATEURS_EXTRACTION: dict[str, Callable[[Any], bool]] = {
    "index": _entier,
    "nom": _texte,
    "conforme": _booleen,
    "motif": _ou_nul(_motif),
    "valeur": _ou_nul(_objet),
    "sortie_brute": _ou_nul(_texte),
    "tokens_entree": _ou_nul(_entier),
    "tokens_sortie": _ou_nul(_entier),
    "delai_premier_token_s": _ou_nul(_nombre),
    "duree_generation_s": _ou_nul(_nombre),
    "duree_extraction_s": _ou_nul(_nombre),
    "vitesse_generation_tps": _ou_nul(_nombre),
    "vitesse_lecture_estimee_tps": _ou_nul(_nombre),
    "temps_cpu_s": _ou_nul(_nombre),
    "pic_memoire_octets": _ou_nul(_entier),
    "fin": _fin,
    "factice": _booleen,
    "mesures_simulees": _booleen,
}
VERIFICATEURS_EXTRACTION_ERREUR: dict[str, Callable[[Any], bool]] = {
    "index": _entier,
    "nom": _texte,
    "motif": _motif,
    "factice": _booleen,
    "mesures_simulees": _booleen,
}
# Types dont la validation est stricte (champs inconnus et types refusés). Les
# événements de transcription ne sont validés que sur leurs champs requis.
VERIFICATEURS_STRICTS: dict[str, dict[str, Callable[[Any], bool]]] = {
    TYPE_EXTRACTION: VERIFICATEURS_EXTRACTION,
    TYPE_EXTRACTION_ERREUR: VERIFICATEURS_EXTRACTION_ERREUR,
}

# Champs de provenance présents dans chaque événement : jamais facultatifs,
# pour qu'aucun consommateur ne puisse ignorer qu'un résultat est simulé.
CHAMPS_PROVENANCE: tuple[str, ...] = ("factice", "mesures_simulees")

# Champs dont la présence est exigée pour chaque type. Les valeurs peuvent être
# `null` (mesure indisponible) : le contrat distingue « absente » de « zéro ».
# Un événement `audio` peut porter en plus le champ facultatif `timings_natifs` :
# liste d'objets, un par appel natif du moteur, chacun portant son unité (`ms` ou
# `s`) et ses étapes. Il est laissé de côté par les moteurs qui n'en transmettent
# aucun et n'est jamais obligatoire : l'absence signifie « non transmis », jamais
# zéro. Le runner le recopie sans l'agréger, dans l'ordre des appels.
# Les événements `chargement` et `audio` peuvent aussi porter le champ facultatif
# `observation_systeme` (tâche 2.1) ; un `fin` d'extraction le porte pour la fenêtre
# du lot (tâche 3.2). Il s'agit de l'objet versionné du design D3, avec sa
# provenance `reelle` ou `simulee`. Il n'est jamais exigé, n'ajoute aucun type
# d'événement et ne change pas le contrat des adaptateurs : un ancien émetteur
# l'omet, un ancien consommateur l'ignore. Le serveur ne persiste un tel objet
# que s'il est conforme ; sinon il l'écarte et le signale au journal.
CHAMPS_REQUIS: dict[str, tuple[str, ...]] = {
    TYPE_CHARGEMENT: (
        "duree_s",
        "pic_memoire_octets",
    ) + CHAMPS_PROVENANCE,
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
    ) + CHAMPS_PROVENANCE,
    TYPE_AUDIO_ERREUR: ("index", "nom", "erreur") + CHAMPS_PROVENANCE,
    TYPE_FIN: (
        "duree_chargement_s",
        "pic_memoire_octets",
        "audios_ok",
        "audios_erreur",
    ) + CHAMPS_PROVENANCE,
    TYPE_EXTRACTION: tuple(VERIFICATEURS_EXTRACTION),
    TYPE_EXTRACTION_ERREUR: tuple(VERIFICATEURS_EXTRACTION_ERREUR),
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

    Une ligne non préfixée, un JSON invalide (y compris un entier dépassant la
    limite de conversion de CPython, qui lève `ValueError` et non
    `JSONDecodeError`, ou un JSON trop profondément imbriqué pour le décodeur,
    qui lève `RecursionError`), un objet qui n'est pas un dictionnaire, un type
    inconnu ou non textuel, un champ requis manquant ou un champ de provenance
    qui n'est pas un booléen donnent `None` : c'est une sortie parasite à journaliser,
    jamais une erreur bloquante — ni une exception. Les deux champs de
    provenance sont validés indépendamment : aucune égalité entre eux n'est
    exigée.
    """
    if not isinstance(ligne, str) or not ligne.startswith(PREFIXE_EVENEMENT):
        return None
    charge = ligne[len(PREFIXE_EVENEMENT) :].strip()
    try:
        # `json.loads` lève `JSONDecodeError` (sous-classe de `ValueError`) pour
        # un JSON invalide, mais aussi `ValueError` pour un entier dépassant la
        # limite de conversion de CPython (4300 chiffres), `TypeError` pour
        # une clé non hachable et `RecursionError` pour un JSON trop
        # profondément imbriqué : la ligne est invalide, jamais une exception.
        evenement = json.loads(charge)
    except (ValueError, TypeError, RecursionError):
        return None
    if not isinstance(evenement, dict):
        return None
    type_evenement = evenement.get("type")
    # Un type non textuel (liste, objet) serait de plus non hachable au test
    # d'appartenance ci-dessous : il est écarté ici, sans exception.
    if not isinstance(type_evenement, str) or type_evenement not in CHAMPS_REQUIS:
        return None
    if any(champ not in evenement for champ in CHAMPS_REQUIS[type_evenement]):
        return None
    if any(
        not isinstance(evenement[champ], bool) for champ in CHAMPS_PROVENANCE
    ):
        return None
    verificateurs = VERIFICATEURS_STRICTS.get(type_evenement)
    if verificateurs is not None and not _valide_strict(evenement, verificateurs):
        return None
    return evenement


def _valide_strict(
    evenement: dict[str, Any], verificateurs: dict[str, Callable[[Any], bool]]
) -> bool:
    """Vrai si l'événement n'a que les champs prévus, tous bien typés et cohérents."""
    if set(evenement) - {"type"} != set(verificateurs):
        return False
    if not all(
        verificateur(evenement[champ]) for champ, verificateur in verificateurs.items()
    ):
        return False
    if evenement["type"] != TYPE_EXTRACTION:
        return True
    return _coherent_extraction(evenement)


def _coherent_extraction(evenement: dict[str, Any]) -> bool:
    """Vrai si `conforme`, `valeur`, `motif` et `sortie_brute` se correspondent."""
    if evenement["conforme"]:
        return (
            evenement["valeur"] is not None
            and evenement["motif"] is None
            and evenement["sortie_brute"] is not None
        )
    return evenement["valeur"] is None and evenement["motif"] is not None
