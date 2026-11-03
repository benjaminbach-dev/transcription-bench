---
title: Qualification Qwen3-ASR 2026-11-03
type: note
permalink: transcription-bench/projet/qualification-qwen3-asr-2026-11-03
tags:
- qwen3-asr
- transcribe-cpp
- gguf
- tache-8-2
- validation
- revue-advisor
---

# Qualification Qwen3-ASR 2026-11-03

## Contexte et décisions

- [decision] 2026-11-03 : l'utilisateur déclare ce poste (Manjaro) PC de test et choisit **Qwen3-ASR-0.6B Q8_0** comme seconde architecture GGUF de la tâche 8.2 (alternative écartée : Parakeet v3 GGUF). Accord explicite de télécharger ce seul fichier (~850 Mo).
- [fact] Modèle : `handy-computer/Qwen3-ASR-0.6B-gguf` commit `7e7c69a577fa2725dfedbe34b5e999336e30a19b`, Apache-2.0 (LICENSE, NOTICE, carte lus), `Qwen3-ASR-0.6B-Q8_0.gguf` 850 423 456 octets, SHA-256 `f081b2d5…acd8` identique à l'oid LFS publié (consigné dans identite-modele.txt).

## Mise en œuvre

- [implementation] GGUF : `general.architecture = qwen3_asr` (soulignés) ; un identifiant de famille n'admet que des tirets, d'où la correspondance explicite `FAMILLES_PAR_ARCHITECTURE_GGUF` (`whisper`, `qwen3_asr` → `qwen3-asr`) dans `compatibilite_modeles.py`. Famille `qwen3-asr` qualifiée dans `engines/declarations.py`, réglage `no_mmap` seul.
- [implementation] Adaptateur `transcribe_cpp.py` : branche selon `Model.arch` ; Qwen3 appelle `session.run(language="fr", timestamps="none")`, sans option de famille ni segments ; réglage effectif `decodage = défauts du moteur, non réglés`.
- [validation] Vérification, téléchargement et exécutions par les formulaires HTTP du serveur. Configuration finale, dans un namespace réseau isolé (`unshare -rn`, accès externe impossible vérifié) : trois audios synthétiques (10,7 s, 45 s recadrés, 47,7 s) en fenêtres de 30 s, statut ok, RTF ≈ 0,16–0,17, pic mémoire ≈ 1,4 Gio, CPU relu, 4 threads demandés. Qualité non évaluée. Suite : 706 tests OK. Preuves hors Git : `data/feasibility/validation-qwen3-asr/` (LISEZMOI.txt).
- [limit] **Aucune durée native** : un appel unique sur 45 s de parole synthétique répétitive a été arrêté par le moteur (« output repetition », statut 19, run ECHEC-natif-45s). Une première version déclarait 47,7 s « natifs » sur la foi d'une exploration hors runner non conservée ; la revue advisor l'a signalé et le rejeu l'a infirmé : retirée. Risque résiduel d'arrêt par répétition sur une fenêtre.
- [limit] Pas d'horodatage ni de segments ; langue imposée fr ; Windows non couvert (aucun job CI Qwen3-ASR) ; aucune évaluation de qualité.
- [process] Revue advisor du 2026-11-03 (sur demande utilisateur) : aucun défaut bloquant dans le code ; corrigés : durée native, traçabilité du namespace isolé et de l'identité du modèle, contradiction du rapport de livraison, trous de tests, clé de décodage. 8.2 et 11.4 cochées (55/55), sans commit ; archivage OpenSpec seulement sur décision de l'utilisateur.
- [lesson] Ne déclarer une durée native qu'après un appel unique réussi par le runner sur un audio de cette durée, avec la preuve conservée ; une exploration hors runner ne suffit pas.

## Relations

- relates_to [[Reprise du lab après livraison CI et publication]]
- relates_to [[Décisions du prototype de benchmark]]
