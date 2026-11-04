#!/usr/bin/env python3
"""Dialogue français à deux voix -> WAV, via l'API Gemini TTS (Google AI Studio).

Outil annexe, hors benchmark. Stdlib seule (aucune dépendance).

Usage :
  uv run python scripts/tts_gemini.py dialogue.txt
  uv run python scripts/tts_gemini.py - -o data/tts/test.wav --voix-a Kore --voix-b Puck < dialogue.txt
  uv run python scripts/tts_gemini.py dialogue.txt --dry-run     # affiche la requête, sans clé ni réseau

Format du texte : une réplique par ligne, « A: ... » ou « B: ... ». Lignes vides ignorées.
Clé : variable d'environnement GOOGLE_API_KEY ou GEMINI_API_KEY (jamais dans un fichier).
Sortie par défaut : data/tts/dialogue.wav (ignoré par Git). Un -o relatif est résolu depuis le répertoire courant.

Attention : l'offre gratuite de l'API peut utiliser les contenus envoyés pour améliorer
les produits Google. N'envoyer que des dialogues fictifs, sans donnée de patient.
L'audio généré porte SynthID et ne doit pas servir à un usage clinique.
"""

import argparse
import base64
import io
import json
import os
import re
import sys
import urllib.error
import urllib.request
import wave
from pathlib import Path

RACINE = Path(__file__).resolve().parents[1]
MODELE = "gemini-3.8-flash-tts"
URL = f"https://generativelanguage.googleapis.com/v1beta/models/{MODELE}:generateContent"
# Estimation à valider : 16 384 tokens de sortie audio ≈ 8,5 min ; marge pour éviter la troncature.
MAX_MOTS = 1200
LIGNE = re.compile(r"^([AB])\s*:\s*(.+)$")


def lire_dialogue(texte: str) -> list[dict]:
    parts = []
    for numero, ligne in enumerate(texte.splitlines(), 1):
        ligne = ligne.strip()
        if not ligne:
            continue
        m = LIGNE.match(ligne)
        if not m:
            raise ValueError(f"ligne {numero} : attendu « A: … » ou « B: … »")
        parts.append({"text": m.group(2), "speech_metadata": {"speaker": m.group(1)}})
    if not parts:
        raise ValueError("aucune réplique trouvée")
    mots = sum(len(p["text"].split()) for p in parts)
    if mots > MAX_MOTS:
        raise ValueError(f"{mots} mots : au-delà de {MAX_MOTS}, découper le texte")
    return parts


def construire_requete(parts: list[dict], voix_a: str, voix_b: str) -> dict:
    voix = [
        {"speaker": "A", "voiceConfig": {"prebuiltVoiceConfig": {"voiceName": voix_a}}},
        {"speaker": "B", "voiceConfig": {"prebuiltVoiceConfig": {"voiceName": voix_b}}},
    ]
    return {
        "contents": [{"role": "user", "parts": parts}],
        "generationConfig": {
            "responseModalities": ["AUDIO"],
            "speechConfig": {"multiSpeakerVoiceConfig": {"speakerVoiceConfigs": voix}},
        },
    }


def appeler_api(requete: dict, cle: str) -> dict:
    entete = {"Content-Type": "application/json", "x-goog-api-key": cle}
    req = urllib.request.Request(URL, json.dumps(requete).encode(), entete, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=300) as reponse:
            return json.load(reponse)
    except urllib.error.HTTPError as erreur:
        detail = erreur.read().decode(errors="replace")[:500]
        if erreur.code == 429:
            sys.exit(f"Quota atteint (HTTP 429). Vérifier les limites dans AI Studio.\n{detail}")
        sys.exit(f"Erreur HTTP {erreur.code} : {detail}")
    except OSError as erreur:
        sys.exit(f"Erreur réseau : {erreur}")


def extraire_wav(reponse: dict) -> bytes:
    candidats = reponse.get("candidates") or []
    if not candidats:
        sys.exit(f"Réponse sans candidat : {reponse.get('promptFeedback')}")
    candidat = candidats[0]
    audios = [
        p["inlineData"]["data"]
        for p in candidat.get("content", {}).get("parts", [])
        if "inlineData" in p
    ]
    if len(audios) != 1:
        sys.exit(f"Réponse attendue avec un seul audio, reçu {len(audios)} (finishReason={candidat.get('finishReason')})")
    fin = candidat.get("finishReason")
    if fin not in (None, "STOP"):
        print(f"Avertissement : finishReason={fin}, l'audio peut être tronqué", file=sys.stderr)
    donnees = base64.b64decode(audios[0])
    if not donnees.startswith(b"RIFF"):
        sys.exit("Les données reçues ne sont pas un WAV (en-tête RIFF absent)")
    return donnees


def main() -> None:
    parser = argparse.ArgumentParser(description="Dialogue FR à deux voix -> WAV (Gemini TTS).")
    parser.add_argument("texte", type=Path, help="fichier texte, ou - pour lire stdin")
    parser.add_argument("-o", "--sortie", type=Path, default=RACINE / "data/tts/dialogue.wav")
    parser.add_argument("--voix-a", default="Kore", help="voix du locuteur A (défaut : Kore)")
    parser.add_argument("--voix-b", default="Puck", help="voix du locuteur B (défaut : Puck)")
    parser.add_argument("--dry-run", action="store_true", help="affiche la requête sans appel")
    args = parser.parse_args()

    try:
        brut = sys.stdin.buffer.read() if str(args.texte) == "-" else args.texte.read_bytes()
        texte = brut.decode("utf-8-sig")
    except (OSError, UnicodeDecodeError) as erreur:
        sys.exit(f"Lecture du texte impossible : {erreur}")
    try:
        parts = lire_dialogue(texte)
    except ValueError as erreur:
        sys.exit(f"Erreur de format : {erreur}")
    requete = construire_requete(parts, args.voix_a, args.voix_b)

    if args.dry_run:
        print(json.dumps(requete, ensure_ascii=False, indent=2))
        return

    cle = os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")
    if not cle:
        sys.exit("Clé absente : définir GOOGLE_API_KEY (ou GEMINI_API_KEY) dans l'environnement.")

    wav = extraire_wav(appeler_api(requete, cle))
    try:
        with wave.open(io.BytesIO(wav)) as w:
            duree = w.getnframes() / w.getframerate()
    except (wave.Error, EOFError):
        sys.exit("WAV reçu illisible : rien n'a été écrit")
    args.sortie.parent.mkdir(parents=True, exist_ok=True)
    args.sortie.write_bytes(wav)
    print(f"Écrit {args.sortie} ({duree:.1f} s, {len(parts)} répliques)")


if __name__ == "__main__":
    main()
