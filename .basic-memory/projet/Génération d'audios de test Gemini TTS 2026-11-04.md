---
title: Génération d'audios de test Gemini TTS 2026-11-04
type: note
permalink: transcription-bench/projet/generation-daudios-de-test-gemini-tts-2026-11-04
tags:
- tts
- gemini
- audios-de-test
- validation
---

# Génération d'audios de test Gemini TTS 2026-11-04

## Contexte

Le prototype a besoin d'audios de test plus réalistes que la référence eSpeak du jeu de test existant. Un outil annexe a été ajouté au dépôt pour générer des dialogues français à deux voix via l'API Gemini TTS de Google AI Studio. Le 2026-11-04, sur le PC local (Manjaro), les trois dialogues fictifs du jeu de test (2 min 33, 5 min, 10 min) ont été générés avec succès, et leurs textes sources ont été rangés à côté des audios. Cette note consigne l'outil, les fichiers produits, la clé API locale et la logique de découpage appliquée pour le fichier de 10 minutes.

## Observations
- [fact] Outil annexe hors specs et hors benchmark : `scripts/tts_gemini.py` et sa notice `scripts/TTS_GEMINI.md` (commit d03b230), stdlib seule, dialogue « A:/B: » → WAV via `gemini-3.8-flash-tts` (nom de modèle vérifié contre la doc officielle), voix Kore/Puck, sortie 24 kHz mono 16 bits, garde-fou de 1200 mots par appel.
- [validation] 2026-11-04, PC local Manjaro : trois audios générés avec succès depuis les verbatims fictifs de ~/Téléchargements/consultation_* (scénarios entièrement fictifs selon leur LISEZMOI, aucune donnée de santé réelle) : `data/tts/consultation_02m33_gemini.wav` (2 min 26 s, 34 répliques, un appel ; référence eSpeak 2 min 33 s), `data/tts/consultation_05m_gemini.wav` (5 min 42 s, 69 répliques, un appel de 1130 mots ; référence 5 min 00 s), `data/tts/consultation_10m_gemini.wav` (10 min 04 s, 112 répliques, deux appels + concaténation ; référence 10 min 00 s).
- [limit] Qualité vocale et cohérence des locuteurs non évaluées, notamment à la jonction des deux parties du 10 min (~5 min 04 s) : à valider à l'oreille. Les durées Gemini approchent les références sans les reproduire (Gemini parle plus lentement que l'eSpeak de référence, surtout sur le 5 min).
- [fact] Clé API Gemini stockée dans `~/.gemini_tts_key` (hors dépôt, chmod 600, contient un `export GOOGLE_API_KEY`) : la sourcer avant chaque appel, car l'environnement ne persiste ni entre sessions ni entre terminaux, et rien dans le dépôt ne référence ce chemin. Valeur jamais consignée ; révocable depuis AI Studio si besoin.
- [process] Découpage du 10 min : 2003 mots dépassant le garde-fou du script → deux moitiés (~1006 et 997 mots) coupées à la frontière d'une réplique (fin de tour du médecin), deux appels API, concaténation des WAV via le module wave de la stdlib (formats identiques vérifiés), parties intermédiaires supprimées. Logique appliquée ad hoc en Python inline par l'agent, non intégrée au script : à refaire manuellement tant qu'elle n'y est pas ajoutée.
- [fact] Textes sources convertis (« Médecin : » → « A: », « Patiente : »/« Patient : » → « B: ») et rangés dans `data/tts/` (hors Git, comme tous les data/) : `dialogue_02m33.txt`, `dialogue_05m.txt`, `dialogue_10m1.txt` (texte complet), `dialogue_10m_p1.txt` et `dialogue_10m_p2.txt` (morceaux effectivement envoyés à l'API).
- [lesson] Les verbatims mélangent « Patiente : » et « Patient : » selon le dossier ; la conversion doit couvrir les deux formes avant l'envoi.
- [constraint] Offre gratuite Google : n'envoyer que des dialogues fictifs ; l'audio porte SynthID et ne doit servir à aucun usage clinique (rappel de la notice du script).

## Relations
- relates_to [[Décisions du prototype de benchmark]]
- relates_to [[Protocole à définir]]
