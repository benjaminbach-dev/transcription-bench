"""Adaptateur d'exécution faster-whisper (CTranslate2), CPU uniquement.

Cet adaptateur est le seul code qui importe `faster_whisper` et `ctranslate2`,
et il le fait **à l'intérieur** de `charger` : importer ce module ne charge
aucun paquet moteur, donc le serveur peut l'importer sans dépendance moteur
(design D4).

Décisions appliquées, issues du jalon 0 Linux (2026-11-01) et du design :

- CPU explicite : `device="cpu"` et `num_workers=1`, sans aucun repli ; le
  périphérique effectivement rapporté par CTranslate2 est relu et consigné
  (`reglages_effectifs["device_relu"]`). Un périphérique non CPU est une erreur,
  pas un repli silencieux (D6).
- `cpu_threads` reçoit le nombre demandé par le job. CTranslate2 4.8.3 n'expose
  pas de lecture publique du nombre de threads appliqués : `threads_appliques`
  reste `None` et le demandé est consigné, jamais présenté comme appliqué.
- `compute_type` et `beam_size` sont les seuls réglages exposés. Le type de
  calcul validé est `int8` (le relu observé au jalon 0 est `int8_float32`) ;
  `float32` est proposé sans être présenté comme mesuré.
- Décodage fixé : `language="fr"`, `task` implicite `transcribe`,
  `temperature=0.0`, `condition_on_previous_text=False`, `vad_filter=False`.
  Le filtre VAD n'est pas exposé : il exigerait des fichiers ONNX absents du
  modèle hors ligne.
- Chargement local seulement : `local_files_only=True`, forcé par le runner. Le
  modèle est un dossier CTranslate2 déjà présent sous `data/models` : aucun
  téléchargement n'a lieu ici.
- Le mécanisme long de faster-whisper traite l'audio en un appel ; le runner ne
  l'utilise que jusqu'à la durée native déclarée, puis découpe en fenêtres
  fixes de 30 s (D9).

Le résultat respecte le contrat minimal de `engines/runner.py` : dict avec
`texte` et, en option, `segments`, `reglages_effectifs`, `langue_imposee` et
`threads_appliques`. Les métadonnées sont identiques pour toutes les fenêtres
d'un même audio.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

#: Types de calcul CTranslate2 proposés. `int8` est le seul mesuré au jalon 0.
TYPES_CALCUL = ("int8", "float32")
COMPUTE_TYPE_DEFAUT = "int8"
BEAM_SIZE_DEFAUT = 5
NOMBRE_BEAM_MINIMUM = 1
LANGUE_IMPOSEE = "fr"


def charger(
    modele: dict[str, Any], threads_demandes: int, reglages: Any
) -> dict[str, Any]:
    """Charge le modèle CTranslate2 local, une seule fois, sur CPU.

    `modele["chemin"]` désigne le dossier de fichiers téléchargés (contenant
    `model.bin`). `reglages` est le mapping des réglages validés par le serveur ;
    aucun réglage inconnu n'est inventé ici : les valeurs absentes prennent leur
    défaut documenté.
    """
    chemin = _chemin_modele(modele)
    valeurs = _reglages_effectifs_demandes(reglages)
    local_files_only = modele.get("local_files_only", True)
    if local_files_only is not True:
        raise RuntimeError(
            "chargement local obligatoire : local_files_only doit valoir True"
        )

    from faster_whisper import WhisperModel  # import différé : paquet moteur

    instance = WhisperModel(
        str(chemin),
        device="cpu",
        compute_type=valeurs["compute_type"],
        cpu_threads=threads_demandes,
        num_workers=1,
        local_files_only=True,
    )
    interne = getattr(instance, "model", None)
    device_relu = getattr(interne, "device", None)
    if not isinstance(device_relu, str) or device_relu.casefold() != "cpu":
        raise RuntimeError(
            "périphérique CTranslate2 non CPU après chargement : "
            f"{device_relu!r}"
        )
    compute_type_relu = getattr(interne, "compute_type", None)
    threads_appliques = _entier_ou_none(getattr(interne, "intra_threads", None))

    reglages_effectifs = {
        "device_relu": device_relu,
        "backend_relu": "ctranslate2",
        "compute_type": valeurs["compute_type"],
        "compute_type_relu": (
            compute_type_relu if isinstance(compute_type_relu, str) else None
        ),
        "cpu_threads_demandes": threads_demandes,
        "num_workers": 1,
        "beam_size": valeurs["beam_size"],
        "temperature": 0.0,
        "condition_on_previous_text": False,
        "vad_filter": False,
        "langue_imposee": LANGUE_IMPOSEE,
        "local_files_only": True,
    }
    return {
        "modele": instance,
        "beam_size": valeurs["beam_size"],
        "reglages_effectifs": reglages_effectifs,
        "threads_appliques": threads_appliques,
    }


def transcrire(
    moteur: dict[str, Any],
    signal: Any,
    taux_echantillonnage: int,
    reglages: Any,
) -> dict[str, Any]:
    """Transcrit un signal float32 mono 16 kHz en un appel faster-whisper.

    `signal` est en lecture seule ; faster-whisper accepte directement un tableau
    numpy. Le générateur de segments est consommé intégralement : aucune mesure
    paresseuse ne reste en attente après le retour.
    """
    if taux_echantillonnage != 16000:
        raise ValueError(
            f"fréquence attendue 16000 Hz, reçue {taux_echantillonnage!r}"
        )
    segments_bruts, _info = moteur["modele"].transcribe(
        signal,
        language=LANGUE_IMPOSEE,
        beam_size=moteur["beam_size"],
        temperature=0.0,
        vad_filter=False,
        condition_on_previous_text=False,
    )
    segments = [
        {
            "debut_s": round(float(segment.start), 3),
            "fin_s": round(float(segment.end), 3),
            "texte": segment.text.strip(),
        }
        for segment in segments_bruts
    ]
    texte = " ".join(segment["texte"] for segment in segments if segment["texte"])
    return {
        "texte": texte,
        "segments": segments,
        "reglages_effectifs": dict(moteur["reglages_effectifs"]),
        "langue_imposee": LANGUE_IMPOSEE,
        "threads_appliques": moteur["threads_appliques"],
    }


def _chemin_modele(modele: Mapping[str, Any]) -> Path:
    """Dossier local du modèle, refusé s'il est absent ou n'est pas un dossier."""
    valeur = modele.get("chemin")
    if not isinstance(valeur, str) or not valeur.strip():
        raise RuntimeError("chemin de modèle absent du job")
    chemin = Path(valeur)
    if not chemin.is_dir():
        raise RuntimeError(f"dossier de modèle absent : {chemin}")
    return chemin


def _reglages_effectifs_demandes(reglages: Any) -> dict[str, Any]:
    """Valide les seuls réglages exposés et applique leurs défauts documentés."""
    compute_type = reglages.get("compute_type", COMPUTE_TYPE_DEFAUT)
    if compute_type not in TYPES_CALCUL:
        raise ValueError(
            f"type de calcul inconnu : {compute_type!r} "
            f"(valeurs possibles : {', '.join(TYPES_CALCUL)})"
        )
    beam_size = reglages.get("beam_size", BEAM_SIZE_DEFAUT)
    if (
        not isinstance(beam_size, int)
        or isinstance(beam_size, bool)
        or beam_size < NOMBRE_BEAM_MINIMUM
    ):
        raise ValueError(f"beam_size invalide : {beam_size!r}")
    return {"compute_type": compute_type, "beam_size": beam_size}


def _entier_ou_none(valeur: Any) -> int | None:
    """Entier appliqué relu, ou `None` : aucune valeur n'est inventée."""
    if isinstance(valeur, int) and not isinstance(valeur, bool):
        return valeur
    return None
