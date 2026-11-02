"""Adaptateur d'exécution transcribe.cpp 0.4.1 (GGUF), CPU uniquement.

Cet adaptateur est le seul code qui importe `transcribe_cpp`, et il le fait
**à l'intérieur** de `charger` : importer ce module ne charge ni la
bibliothèque native ni un paquet moteur (design D4).

Décisions appliquées, issues du jalon 0 Linux (2026-11-01) et du design :

- CPU explicite : `TRANSCRIBE_BACKENDS=cpu`, `TRANSCRIBE_BACKEND=cpu` et
  `CUDA_VISIBLE_DEVICES=""` sont posés avant l'import de la bibliothèque native
  (elle lit ces variables au chargement), puis `backend="cpu"` est passé
  explicitement à `Model`. La valeur réellement rapportée par le moteur est
  relue et consignée telle quelle (`backend_relu`, `device_type_relu`) ; la
  version 0.4.1 renvoie `"CPU"` sur le PC Linux validé. Un backend ou un
  périphérique non CPU est une erreur, pas un repli (D6).
- Architecture vérifiée : `Model.arch` doit valoir `whisper` pour la famille
  Whisper, seule famille qualifiée ici (D9). Toute autre architecture est
  refusée au chargement, sans tentative d'exécution.
- `n_threads` reçoit le nombre demandé par le job. Aucune API publique ne permet
  de relire le nombre appliqué en 0.4.1 : `threads_appliques` reste `None` et le
  demandé est consigné.
- mmap : le mode par défaut (`no_mmap=False`, poids mmapés) est consigné ; le
  réglage `no_mmap` permet de le désactiver (D8).
- Décodage fixé : `language="fr"`, `timestamps="segment"`,
  `WhisperRunOptions(condition_on_prev_tokens=…, temperature=0.0,
  temperature_inc=0.0)`. Le réglage `condition_on_prev_tokens` est exposé,
  défaut `False` (valeur mesurée au jalon 0).
- Le mécanisme long de transcribe.cpp traite l'audio en un appel ; le runner ne
  l'utilise que jusqu'à la durée native déclarée, puis découpe en fenêtres fixes
  de 30 s (D9).

Timings natifs : `Result.timings` porte `load_ms`, `mel_ms`, `encode_ms` et
`decode_ms`, en millisecondes flottantes dans la version 0.4.1. Ces durées
varient par appel ; elles sont donc transmises dans le champ facultatif
`timings_natifs`, une entrée par appel et par étape, avec l'unité consignée.
Le runner les conserve dans l'ordre des appels sans les agréger : elles ne sont
pas des réglages effectifs (qui restent identiques pour toutes les fenêtres
d'un même audio) et une étape absente n'est jamais remplacée par zéro.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any

LANGUE_IMPOSEE = "fr"
#: Variables d'environnement lues par la bibliothèque native au chargement.
CLE_BACKENDS = "TRANSCRIBE_BACKENDS"
CLE_BACKEND = "TRANSCRIBE_BACKEND"
CLE_CUDA_VISIBLE_DEVICES = "CUDA_VISIBLE_DEVICES"
ENVIRONNEMENT_CPU = {
    CLE_BACKENDS: "cpu",
    CLE_BACKEND: "cpu",
    CLE_CUDA_VISIBLE_DEVICES: "",
}
ARCHITECTURE_WHISPER = "whisper"
NO_MMAP_DEFAUT = False
CONDITION_ON_PREV_TOKENS_DEFAUT = False


def charger(
    modele: dict[str, Any], threads_demandes: int, reglages: Any
) -> dict[str, Any]:
    """Charge le GGUF local, vérifie le backend CPU et ouvre une session.

    `modele["chemin"]` désigne le fichier `.gguf` choisi à l'ajout du modèle.
    Le modèle est ouvert sans mmap désactivé par défaut ; le réglage `no_mmap`
    permet de copier les poids en mémoire.
    """
    chemin = _chemin_modele(modele)
    no_mmap = _booleen(reglages, "no_mmap", NO_MMAP_DEFAUT)
    condition_on_prev_tokens = _booleen(
        reglages, "condition_on_prev_tokens", CONDITION_ON_PREV_TOKENS_DEFAUT
    )

    precedents = _poser_environnement_cpu()
    try:
        import transcribe_cpp as tc  # import différé : bibliothèque native

        instance = tc.Model(str(chemin), backend="cpu", no_mmap=no_mmap)
    finally:
        _restaurer_environnement(precedents)

    try:
        backend_relu = str(instance.backend)
        if backend_relu.casefold() != "cpu":
            raise RuntimeError(
                f"backend transcribe.cpp non CPU après chargement : {backend_relu!r}"
            )
        device = instance.device
        device_type_relu = str(getattr(device, "device_type", ""))
        if device_type_relu.casefold() != "cpu":
            raise RuntimeError(
                "périphérique transcribe.cpp non CPU après chargement : "
                f"{device_type_relu!r}"
            )
        architecture_relue = str(instance.arch)
        if architecture_relue.casefold() != ARCHITECTURE_WHISPER:
            raise RuntimeError(
                "architecture GGUF non prise en charge par cet adaptateur : "
                f"{architecture_relue!r} (famille Whisper attendue)"
            )
        session = instance.session(n_threads=threads_demandes)
    except Exception:
        instance.close()
        raise

    reglages_effectifs = {
        "backend_relu": backend_relu,
        "device_type_relu": device_type_relu,
        "architecture_relue": architecture_relue,
        "variante_relue": str(instance.variant),
        "no_mmap": no_mmap,
        "n_threads_demandes": threads_demandes,
        "condition_on_prev_tokens": condition_on_prev_tokens,
        "temperature": 0.0,
        "temperature_inc": 0.0,
        "timestamps": "segment",
        "langue_imposee": LANGUE_IMPOSEE,
        "local_files_only": True,
    }
    return {
        "modele": instance,
        "session": session,
        "module": tc,
        "condition_on_prev_tokens": condition_on_prev_tokens,
        "reglages_effectifs": reglages_effectifs,
        # Aucune API publique ne relit le nombre appliqué en 0.4.1.
        "threads_appliques": None,
    }


def transcrire(
    moteur: dict[str, Any],
    signal: Any,
    taux_echantillonnage: int,
    reglages: Any,
) -> dict[str, Any]:
    """Transcrit un signal float32 mono 16 kHz en un appel de session."""
    if taux_echantillonnage != 16000:
        raise ValueError(
            f"fréquence attendue 16000 Hz, reçue {taux_echantillonnage!r}"
        )
    tc = moteur["module"]
    resultat = moteur["session"].run(
        signal,
        language=LANGUE_IMPOSEE,
        timestamps="segment",
        family=tc.WhisperRunOptions(
            condition_on_prev_tokens=moteur["condition_on_prev_tokens"],
            temperature=0.0,
            temperature_inc=0.0,
        ),
    )
    segments = [
        {
            "debut_s": round(float(segment.t0_ms) / 1000.0, 3),
            "fin_s": round(float(segment.t1_ms) / 1000.0, 3),
            "texte": segment.text.strip(),
        }
        for segment in resultat.segments
    ]
    return {
        "texte": resultat.text.strip(),
        "segments": segments,
        "timings_natifs": _timings_natifs(resultat),
        "reglages_effectifs": dict(moteur["reglages_effectifs"]),
        "langue_imposee": LANGUE_IMPOSEE,
        "threads_appliques": moteur["threads_appliques"],
    }


def _timings_natifs(resultat: Any) -> list[dict[str, Any]] | None:
    """Timings natifs de l'appel, en millisecondes, ou `None` s'ils manquent.

    Un seul appel natif par `transcrire` : la liste contient au plus une entrée,
    que le runner concatène ensuite dans l'ordre des appels. Les valeurs sont
    recopiées telles quelles ; aucune n'est déduite ni agrégée.
    """
    timings = getattr(resultat, "timings", None)
    if timings is None:
        return None
    return [
        {
            "unite": "ms",
            "load_ms": float(timings.load_ms),
            "mel_ms": float(timings.mel_ms),
            "encode_ms": float(timings.encode_ms),
            "decode_ms": float(timings.decode_ms),
        }
    ]


def _chemin_modele(modele: Mapping[str, Any]) -> Path:
    """Fichier GGUF local, refusé s'il est absent ou n'est pas un fichier."""
    valeur = modele.get("chemin")
    if not isinstance(valeur, str) or not valeur.strip():
        raise RuntimeError("chemin de modèle absent du job")
    chemin = Path(valeur)
    if not chemin.is_file():
        raise RuntimeError(f"fichier GGUF absent : {chemin}")
    return chemin


def _booleen(reglages: Any, nom: str, defaut: bool) -> bool:
    valeur = reglages.get(nom, defaut)
    if not isinstance(valeur, bool):
        raise ValueError(f"réglage {nom!r} invalide : {valeur!r} (booléen attendu)")
    return valeur


def _poser_environnement_cpu() -> dict[str, str | None]:
    """Force les variables lues par la bibliothèque native avant son import."""
    precedents: dict[str, str | None] = {}
    for cle, valeur in ENVIRONNEMENT_CPU.items():
        precedents[cle] = os.environ.get(cle)
        os.environ[cle] = valeur
    return precedents


def _restaurer_environnement(precedents: Mapping[str, str | None]) -> None:
    """Restaure exactement l'environnement précédent, pour ne pas muter l'appelant."""
    for cle, valeur in precedents.items():
        if valeur is None:
            os.environ.pop(cle, None)
        else:
            os.environ[cle] = valeur
