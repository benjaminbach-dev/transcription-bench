"""Adaptateur d'exécution Hugging Face Transformers, CPU uniquement.

Familles couvertes au premier jalon : **Whisper** et **Parakeet TDT**. Les autres
familles restent des extensions futures (spec `engine-management`).

Cet adaptateur est le seul code qui importe `transformers` et `torch`, et il le
fait **à l'intérieur** de `charger` (design D4). Le serveur peut donc l'importer
sans dépendance moteur.

Décisions appliquées, issues du jalon 0 Linux (2026-11-01), de D9, D10 et D13 :

- Famille déduite du fichier local `config.json` (`model_type` : `whisper` ou
  `parakeet_tdt`). Le job ne transmet pas la famille à `charger` ; la
  vérification de compatibilité du serveur garantit déjà que ce `model_type`
  correspond à la famille de l'inventaire. Une valeur inconnue est refusée.
- CPU explicite : `CUDA_VISIBLE_DEVICES=""`, `OMP_NUM_THREADS` et
  `MKL_NUM_THREADS` posés avant l'import de torch, puis
  `torch.set_num_threads(N)` ; le nombre effectivement relu par
  `torch.get_num_threads()` est consigné. Le périphérique et le dtype des poids
  sont relus et consignés. `fp32` est imposé explicitement (`dtype=torch.float32`)
  car transformers 5.20.2 charge par défaut le dtype de publication (fp16 pour
  Whisper), inadapté au CPU (D13).
- Poids safetensors uniquement (`use_safetensors=True`), sans code distant
  (`trust_remote_code=False`) et en local seulement (`local_files_only=True`).
- Whisper : long-form natif de Transformers (`truncation=False`,
  `padding="longest"`, `return_attention_mask=True`), jamais la troncature
  silencieuse à 30 s ; la couverture de la durée décodée par les trames mel est
  vérifiée. Décodage `language="fr"`, `task="transcribe"`,
  `return_timestamps=True`. `do_normalize` est fixé explicitement par réglage,
  sans dépendre du défaut du processor (défaut retenu : `False`, comportement
  mesuré au jalon 0).
- Parakeet TDT : une passe native jusqu'à la durée prouvée, `max_length` borné
  explicitement et proportionnel au nombre de trames encodeur, avec détection de
  son atteinte ; horodatages par jeton fournis par le processor, regroupés en
  segments par ponctuation finale (convention de lecture, pas une frontière
  acoustique). Les durées cumulées par jeton sont la seule information
  temporelle du modèle (D13). **La langue n'est pas forçable** :
  `ParakeetTDTGenerationMixin.generate()` n'expose aucune option de langue, le
  modèle est multilingue et choisit seul ; `langue_imposee` vaut donc `None`
  pour cette famille, jamais `"fr"`. Aucune option de langue n'est inventée.
- Inférence native seulement jusqu'à la durée native déclarée ; au-delà, le
  runner découpe en fenêtres fixes de 30 s (D9).

Le résultat respecte le contrat minimal de `engines/runner.py` : dict avec
`texte` et, en option, `segments`, `reglages_effectifs`, `langue_imposee` et
`threads_appliques`. Les métadonnées sont identiques pour toutes les fenêtres
d'un même audio : `max_length` n'y figure que sous forme de règle, jamais par
appel.
"""

from __future__ import annotations

import json
import math
import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any

TAUX_ECHANTILLONNAGE = 16000
LANGUE_IMPOSEE = "fr"
FAMILLE_WHISPER = "whisper"
FAMILLE_PARAKEET = "parakeet-tdt"
MODEL_TYPE_VERS_FAMILLE = {
    "whisper": FAMILLE_WHISPER,
    "parakeet_tdt": FAMILLE_PARAKEET,
}
PONCTUATIONS_FINALES = (".", "!", "?", "…")
#: Trames mel par seconde des deux extracteurs (hop_length 160 à 16 kHz).
TRAMES_MEL_PAR_SECONDE = 100.0
#: Facteur de sous-échantillonnage de l'encodeur Parakeet, si la configuration
#: ne l'expose pas (valeur de `nvidia/parakeet-tdt-0.6b-v3`).
SOUS_ECHANTILLONNAGE_DEFAUT = 8
MAX_SYMBOLS_PAR_PAS_DEFAUT = 10
#: Marge ajoutée à la borne `max_length` de Parakeet (jetons), pour ne jamais
#: tronquer un audio long : la borne de la bibliothèque est
#: `max_symbols_per_step x trames_encodeur`.
MARGE_MAX_LENGTH = 10
CONDITION_ON_PREV_DEFAUT = False
DO_NORMALIZE_DEFAUT = False


def charger(
    modele: dict[str, Any], threads_demandes: int, reglages: Any
) -> dict[str, Any]:
    """Charge le processor et le modèle locaux de la famille détectée, sur CPU."""
    chemin = _chemin_modele(modele)
    famille = _famille_locale(chemin)
    do_normalize = _booleen(reglages, "do_normalize", DO_NORMALIZE_DEFAUT)
    local_files_only = modele.get("local_files_only", True)
    if local_files_only is not True:
        raise RuntimeError(
            "chargement local obligatoire : local_files_only doit valoir True"
        )

    precedents = _poser_environnement_cpu(threads_demandes)
    try:
        import torch  # import différé : paquet moteur

        torch.set_num_threads(threads_demandes)
        if famille == FAMILLE_WHISPER:
            from transformers import (  # import différé : paquet moteur
                WhisperForConditionalGeneration,
                WhisperProcessor,
            )

            processeur = WhisperProcessor.from_pretrained(
                str(chemin), local_files_only=True, trust_remote_code=False
            )
            instance = WhisperForConditionalGeneration.from_pretrained(
                str(chemin),
                dtype=torch.float32,
                use_safetensors=True,
                local_files_only=True,
                trust_remote_code=False,
            )
        else:
            from transformers import (  # import différé : paquet moteur
                ParakeetForTDT,
                ParakeetProcessor,
            )

            processeur = ParakeetProcessor.from_pretrained(
                str(chemin), local_files_only=True, trust_remote_code=False
            )
            instance = ParakeetForTDT.from_pretrained(
                str(chemin),
                dtype=torch.float32,
                use_safetensors=True,
                local_files_only=True,
                trust_remote_code=False,
            )
        instance.eval()
        parametre = next(instance.parameters())
        device_relu = str(parametre.device)
        dtype_relu = str(parametre.dtype)
        threads_appliques = int(torch.get_num_threads())
    finally:
        _restaurer_environnement(precedents)

    if device_relu.casefold() != "cpu":
        raise RuntimeError(
            f"périphérique Transformers non CPU après chargement : {device_relu!r}"
        )
    if dtype_relu != "torch.float32":
        raise RuntimeError(f"dtype Transformers non fp32 après chargement : {dtype_relu!r}")

    reglages_effectifs: dict[str, Any] = {
        "famille_locale": famille,
        "device_relu": device_relu,
        "backend_relu": "torch-cpu",
        "dtype_demande": "float32",
        "dtype_relu": dtype_relu,
        "use_safetensors": True,
        "local_files_only": True,
        "trust_remote_code": False,
        "threads_demandes": threads_demandes,
        "threads_appliques": threads_appliques,
    }
    if famille == FAMILLE_WHISPER:
        reglages_effectifs.update(
            {
                "do_normalize": do_normalize,
                "truncation": False,
                "padding": "longest",
                "return_attention_mask": True,
                "condition_on_prev_tokens": CONDITION_ON_PREV_DEFAUT,
                "langue_imposee": LANGUE_IMPOSEE,
            }
        )
    else:
        reglages_effectifs.update(
            {
                "max_length_regle": (
                    f"{_max_symbols_par_pas(instance)} x trames_encodeur "
                    f"+ {MARGE_MAX_LENGTH}"
                ),
                "decodage": "glouton TDT par construction",
                # L'API TDT ne permet pas d'imposer une langue : ne rien affirmer.
                "langue_imposee": None,
            }
        )
    return {
        "modele": instance,
        "processeur": processeur,
        "famille": famille,
        "do_normalize": do_normalize,
        "reglages_effectifs": reglages_effectifs,
        "threads_appliques": threads_appliques,
    }


def transcrire(
    moteur: dict[str, Any],
    signal: Any,
    taux_echantillonnage: int,
    reglages: Any,
) -> dict[str, Any]:
    """Transcrit un signal float32 mono 16 kHz avec la famille chargée."""
    if taux_echantillonnage != TAUX_ECHANTILLONNAGE:
        raise ValueError(
            f"fréquence attendue {TAUX_ECHANTILLONNAGE} Hz, "
            f"reçue {taux_echantillonnage!r}"
        )
    duree_s = signal.size / TAUX_ECHANTILLONNAGE
    if moteur["famille"] == FAMILLE_WHISPER:
        texte, segments = _transcrire_whisper(moteur, signal, duree_s)
        langue_imposee: str | None = LANGUE_IMPOSEE
    else:
        texte, segments = _transcrire_parakeet(moteur, signal, duree_s)
        # Parakeet TDT n'expose pas d'option de langue : rien n'est imposé.
        langue_imposee = None
    return {
        "texte": texte,
        "segments": segments,
        "reglages_effectifs": dict(moteur["reglages_effectifs"]),
        "langue_imposee": langue_imposee,
        "threads_appliques": moteur["threads_appliques"],
    }


def _transcrire_whisper(
    moteur: Mapping[str, Any], signal: Any, duree_s: float
) -> tuple[str, list[dict[str, Any]]]:
    """Long-form natif Whisper, avec contrôle de couverture des trames mel."""
    processeur = moteur["processeur"]
    entree = processeur(
        signal,
        sampling_rate=TAUX_ECHANTILLONNAGE,
        return_tensors="pt",
        truncation=False,
        padding="longest",
        return_attention_mask=True,
        do_normalize=moteur["do_normalize"],
    )
    _verifier_couverture(entree, duree_s, FAMILLE_WHISPER)
    sortie = moteur["modele"].generate(
        **entree,
        language=LANGUE_IMPOSEE,
        task="transcribe",
        return_timestamps=True,
        return_segments=True,
    )
    sequences = _champ(sortie, "sequences")
    texte = processeur.batch_decode(sequences, skip_special_tokens=True)[0].strip()
    segments: list[dict[str, Any]] = []
    groupes = _champ(sortie, "segments", None)
    if groupes:
        for segment in groupes[0]:
            jetons = _champ(segment, "tokens")
            if jetons is None:
                continue
            liste = jetons.tolist() if hasattr(jetons, "tolist") else list(jetons)
            segments.append(
                {
                    "debut_s": round(float(_champ(segment, "start")), 3),
                    "fin_s": round(float(_champ(segment, "end")), 3),
                    "texte": processeur.decode(
                        liste, skip_special_tokens=True
                    ).strip(),
                }
            )
    return texte, segments


def _transcrire_parakeet(
    moteur: Mapping[str, Any], signal: Any, duree_s: float
) -> tuple[str, list[dict[str, Any]]]:
    """Une passe TDT, borne `max_length` explicite et horodatages par jeton."""
    processeur = moteur["processeur"]
    instance = moteur["modele"]
    entree = processeur(
        signal, sampling_rate=TAUX_ECHANTILLONNAGE, return_tensors="pt"
    )
    _verifier_couverture(entree, duree_s, FAMILLE_PARAKEET)
    trames_mel = int(_forme(entree["input_features"])[1])
    trames_encodeur = math.ceil(
        trames_mel / _sous_echantillonnage(instance)
    )
    max_length = _max_symbols_par_pas(instance) * trames_encodeur + MARGE_MAX_LENGTH
    sortie = instance.generate(**entree, max_length=max_length)
    sequences = _champ(sortie, "sequences")
    durees = _champ(sortie, "durations")
    if durees is None:
        raise RuntimeError("sortie Parakeet sans durées par jeton")
    if int(sequences.shape[-1]) >= max_length:
        raise RuntimeError(
            "borne max_length atteinte pendant la génération Parakeet : "
            "sortie potentiellement tronquée"
        )
    textes, horodatages = processeur.decode(
        sequences, durations=durees, skip_special_tokens=True
    )
    texte = textes[0].strip()
    jetons = [
        {
            "jeton": jeton["token"],
            "debut_s": round(float(jeton["start"]), 3),
            "fin_s": round(float(jeton["end"]), 3),
        }
        for jeton in horodatages[0]
    ]
    segments: list[dict[str, Any]] = []
    courant: list[dict[str, Any]] = []
    for jeton in jetons:
        courant.append(jeton)
        if jeton["jeton"].strip().endswith(PONCTUATIONS_FINALES):
            segments.append(_segment(courant))
            courant = []
    if courant:
        segments.append(_segment(courant))
    return texte, segments


def _segment(jetons: list[dict[str, Any]]) -> dict[str, Any]:
    """Regroupe des jetons horodatés en segment de lecture (convention D13)."""
    return {
        "debut_s": jetons[0]["debut_s"],
        "fin_s": jetons[-1]["fin_s"],
        "texte": "".join(jeton["jeton"] for jeton in jetons).strip(),
    }


def _verifier_couverture(entree: Any, duree_s: float, famille: str) -> None:
    """Refuse une entrée tronquée : les trames mel doivent couvrir l'audio.

    L'axe des trames dépend de la famille : `[1, 128, T]` pour Whisper,
    `[1, T, 128]` pour Parakeet. Un déficit de plus d'une trame révèle une
    troncature silencieuse du processor (D9), qui n'est jamais acceptée.
    """
    caracteristiques = entree["input_features"]
    forme = _forme(caracteristiques)
    if len(forme) != 3:
        raise RuntimeError(
            f"forme d'entrée inattendue pour {famille} : {forme!r}"
        )
    if famille == FAMILLE_WHISPER:
        trames = int(forme[2])
    else:
        trames = int(forme[1])
    attendues = math.floor(duree_s * TRAMES_MEL_PAR_SECONDE)
    if trames < attendues - 1:
        raise RuntimeError(
            f"entrée tronquée pour {famille} : {trames} trames mel pour "
            f"{duree_s:.3f} s décodées ({attendues} attendues)"
        )
    if famille == FAMILLE_PARAKEET and "attention_mask" in entree:
        masque = entree["attention_mask"]
        utiles = int(masque.sum())
        if utiles < attendues - 1:
            raise RuntimeError(
                f"masque d'attention trop court pour {famille} : {utiles} trames "
                f"utiles pour {duree_s:.3f} s décodées ({attendues} attendues)"
            )


def _famille_locale(chemin: Path) -> str:
    """Famille déduite du `model_type` du `config.json` local, sans réseau."""
    chemin_config = chemin / "config.json"
    try:
        configuration = json.loads(chemin_config.read_text(encoding="utf-8"))
    except OSError as exception:
        raise RuntimeError(
            f"configuration du modèle illisible : {chemin_config} ({exception})"
        ) from exception
    except json.JSONDecodeError as exception:
        raise RuntimeError(
            f"configuration du modèle invalide : {chemin_config} ({exception})"
        ) from exception
    if not isinstance(configuration, dict):
        raise RuntimeError(f"configuration du modèle inattendue : {chemin_config}")
    model_type = configuration.get("model_type")
    famille = MODEL_TYPE_VERS_FAMILLE.get(model_type)
    if famille is None:
        raise RuntimeError(
            "famille Transformers non prise en charge par cet adaptateur : "
            f"model_type={model_type!r} (Whisper et Parakeet TDT seulement)"
        )
    return famille


def _chemin_modele(modele: Mapping[str, Any]) -> Path:
    """Dossier local du modèle, refusé s'il est absent ou n'est pas un dossier."""
    valeur = modele.get("chemin")
    if not isinstance(valeur, str) or not valeur.strip():
        raise RuntimeError("chemin de modèle absent du job")
    chemin = Path(valeur)
    if not chemin.is_dir():
        raise RuntimeError(f"dossier de modèle absent : {chemin}")
    return chemin


def _booleen(reglages: Any, nom: str, defaut: bool) -> bool:
    valeur = reglages.get(nom, defaut)
    if not isinstance(valeur, bool):
        raise ValueError(f"réglage {nom!r} invalide : {valeur!r} (booléen attendu)")
    return valeur


def _poser_environnement_cpu(threads: int) -> dict[str, str | None]:
    """Force le CPU et les threads avant l'import de torch (D6)."""
    valeurs = {
        "CUDA_VISIBLE_DEVICES": "",
        "OMP_NUM_THREADS": str(threads),
        "MKL_NUM_THREADS": str(threads),
    }
    precedents: dict[str, str | None] = {}
    for cle, valeur in valeurs.items():
        precedents[cle] = os.environ.get(cle)
        os.environ[cle] = valeur
    return precedents


def _restaurer_environnement(precedents: Mapping[str, str | None]) -> None:
    """Restaure l'environnement précédent après configuration de torch."""
    for cle, valeur in precedents.items():
        if valeur is None:
            os.environ.pop(cle, None)
        else:
            os.environ[cle] = valeur


def _champ(sortie: Any, nom: str, defaut: Any = None) -> Any:
    """Champ d'une sortie de génération, dict-like ou objet."""
    if isinstance(sortie, Mapping):
        return sortie.get(nom, defaut)
    return getattr(sortie, nom, defaut)


def _forme(tenseur: Any) -> tuple[int, ...]:
    """Forme d'un tenseur, sans dépendre de l'API torch."""
    forme = getattr(tenseur, "shape", None)
    if forme is None:
        raise RuntimeError("tenseur d'entrée sans forme lisible")
    return tuple(int(dimension) for dimension in forme)


def _sous_echantillonnage(modele: Any) -> int:
    """Facteur de sous-échantillonnage de l'encodeur Parakeet."""
    encoder = getattr(modele.config, "encoder_config", None)
    valeur = (
        encoder.get("subsampling_factor")
        if isinstance(encoder, Mapping)
        else getattr(encoder, "subsampling_factor", None)
    )
    if isinstance(valeur, int) and not isinstance(valeur, bool) and valeur > 0:
        return valeur
    return SOUS_ECHANTILLONNAGE_DEFAUT


def _max_symbols_par_pas(modele: Any) -> int:
    """`max_symbols_per_step` déclaré par la configuration du modèle."""
    valeur = getattr(modele.config, "max_symbols_per_step", None)
    if isinstance(valeur, int) and not isinstance(valeur, bool) and valeur > 0:
        return valeur
    return MAX_SYMBOLS_PAR_PAS_DEFAUT
