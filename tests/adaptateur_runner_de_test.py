"""Adaptateur de test contrôlé du runner, sans aucun moteur réel.

Ce module n'est pas un adaptateur de production : il n'ajoute aucun moteur et
n'apparaît dans aucune déclaration fournie. `tests/test_runner.py` construit un
registre de test dont la déclaration pointe ici, conformément à la tâche 4.2.
Le module étant importé dans le même processus que les tests, ceux-ci le
configurent directement (`reinitialiser`).

La valeur du premier échantillon identifie l'audio, la taille du signal donne la
fenêtre reçue : les tests vérifient ainsi l'ordre des audios, le découpage et le
fait que le signal est en lecture seule.
"""

from __future__ import annotations

import os
from typing import Any

ETAT: dict[str, Any] = {
    "echec_appel": None,
    "parasite": False,
    "resultat_invalide": False,
    "divergence": None,
    "timings_natifs": False,
    "timings_invalides": False,
}

compteur_chargements = 0
appels: list[dict[str, Any]] = []
derniere_consigne: dict[str, Any] | None = None


def reinitialiser(
    *,
    echec_appel: int | None = None,
    parasite: bool = False,
    resultat_invalide: bool = False,
    divergence: str | None = None,
    timings_natifs: bool = False,
    timings_invalides: bool = False,
) -> None:
    """Remet le module dans un état connu avant chaque test."""
    global compteur_chargements, derniere_consigne
    ETAT["echec_appel"] = echec_appel
    ETAT["parasite"] = parasite
    ETAT["resultat_invalide"] = resultat_invalide
    ETAT["divergence"] = divergence
    ETAT["timings_natifs"] = timings_natifs
    ETAT["timings_invalides"] = timings_invalides
    compteur_chargements = 0
    derniere_consigne = None
    appels.clear()


def charger(
    modele: dict[str, Any], threads_demandes: int, reglages: Any
) -> dict[str, Any]:
    """Charge une fois : ne fait que consigner les consignes reçues."""
    global compteur_chargements, derniere_consigne
    compteur_chargements += 1
    derniere_consigne = {
        "modele": dict(modele),
        "threads_demandes": threads_demandes,
        "reglages": dict(reglages),
        "hf_hub_offline": os.environ.get("HF_HUB_OFFLINE"),
    }
    return derniere_consigne


def transcrire(
    moteur: dict[str, Any], signal: Any, taux_echantillonnage: int, reglages: Any
) -> dict[str, Any]:
    """Renvoie un résultat factice et contrôlable, jamais une transcription réelle."""
    appels.append(
        {
            "premier_echantillon": float(signal[0]),
            "echantillons": int(signal.size),
            "modifiable": bool(signal.flags.writeable),
            "taux_echantillonnage": taux_echantillonnage,
            "reglages": dict(reglages),
            "hf_hub_offline": os.environ.get("HF_HUB_OFFLINE"),
        }
    )
    if ETAT["parasite"] and len(appels) == 1:
        print("bavardage de bibliothèque sans préfixe")
    if ETAT["echec_appel"] == len(appels):
        raise RuntimeError("échec simulé de transcription")
    if ETAT["resultat_invalide"] and len(appels) == 1:
        return ["pas un dict"]
    duree = signal.size / taux_echantillonnage
    texte = f"héllo {signal.size}"
    reglages_effectifs: dict[str, Any] = {"modele": "test"}
    langue_imposee: str | None = "fr"
    threads_appliques: int | None = None
    if len(appels) >= 2:
        if ETAT["divergence"] == "effectifs":
            reglages_effectifs = {"modele": "autre"}
        elif ETAT["divergence"] == "langue":
            langue_imposee = "en"
        elif ETAT["divergence"] == "threads":
            threads_appliques = 8
    resultat = {
        "texte": texte,
        "segments": [{"debut_s": 0.0, "fin_s": duree, "texte": texte}],
        "reglages_effectifs": reglages_effectifs,
        "langue_imposee": langue_imposee,
        "threads_appliques": threads_appliques,
    }
    timings = _timings()
    if timings is not None:
        resultat["timings_natifs"] = timings
    return resultat


def _timings() -> list[dict[str, Any]] | None:
    """Timings natifs simulés par appel, ou `None` quand le moteur n'en a pas.

    La valeur de `load_ms` suit le numéro d'appel pour que les tests vérifient
    l'ordre des fenêtres ; `timings_invalides` produit une unité refusée.
    """
    if ETAT["timings_invalides"]:
        return [
            {
                "unite": "min",
                "load_ms": 1.0,
                "mel_ms": 0.5,
                "encode_ms": 2.0,
                "decode_ms": 3.0,
            }
        ]
    if not ETAT["timings_natifs"]:
        return None
    return [
        {
            "unite": "ms",
            "load_ms": float(len(appels)),
            "mel_ms": 0.5,
            "encode_ms": 2.0,
            "decode_ms": 3.0,
        }
    ]
