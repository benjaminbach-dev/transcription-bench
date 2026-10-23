---
title: Modèles et sources
type: note
permalink: transcription-bench/recherche/modeles-et-sources
status: exploratoire
provenance: conversation initiale
date: '2026-10-23'
tags:
- exploration
- '2026-10-23'
---

# Modèles et sources

## Statut de la recherche

Première exploration web durant la conversation du 2026-10-23. Les fiches sont des déclarations d’auteurs ou mainteneurs ; aucune reproduction locale. Vérifier existence des artefacts, version, licence, conversion, support CPU et compatibilité OS au moment de l’implémentation. Aucun moteur définitivement retenu.

## Candidats généralistes

| Candidat | Rôle proposé | Point à vérifier |
| --- | --- | --- |
| Whisper large-v3 | Référence qualité sur fichier | Coût CPU, hallucinations sur silence, fidélité médicale |
| Whisper large-v3-turbo | Comparaison vitesse/qualité | Régression réelle sur le corpus cible |
| Qwen3-ASR 1.7B | Challenger qualité français | Moteur CPU, audio long, horodatages et alignement séparé |
| Parakeet TDT 0.6B v3 | Candidat plus léger avec français et horodatages | Ne pas confondre avec v2 anglophone ; vérifier moteur CPU et gestion des longs fichiers |
| Voxtral Mini 3B 2507 | Deuxième vague éventuelle | Déploiement CPU plus complexe que les exemples GPU officiels |

Sources primaires :
- https://huggingface.co/openai/whisper-large-v3
- https://huggingface.co/openai/whisper-large-v3-turbo
- https://github.com/QwenLM/Qwen3-ASR
- https://huggingface.co/nvidia/parakeet-tdt-0.6b-v3
- https://huggingface.co/mistralai/Voxtral-Mini-3B-2507

## Moteurs et diarisation

- https://github.com/ggml-org/whisper.cpp : piste de socle multiplateforme CPU pour Whisper, quantification, VAD et accélération facultative ; documentation également consultée via Context7.
- https://github.com/handy-computer/transcribe.cpp : piste communautaire multi-familles CPU/Vulkan, à qualifier plutôt qu’à présumer équivalente aux implémentations officielles.
- https://huggingface.co/pyannote/speaker-diarization-community-1 : candidat diarisation locale CPU, nombre d’intervenants configurable. Accès initial soumis aux conditions Hugging Face ; vérifier les exigences d’intégration. Ce n’est pas un transcripteur.
- Qwen3-ForcedAligner-0.6B : alignement texte/audio incluant le français, pas une diarisation ; coût et intégration à mesurer si Qwen est retenu.

## Pistes médicales françaises

- https://huggingface.co/leduckhai/MultiMed-ST : projet de recherche EMNLP 2025 avec poids ASR dont `asr/whisper-small-french` ; piste prioritaire à examiner, pas une validation sur consultation.
- https://huggingface.co/leduckhai/MultiMed : projet antérieur ACL 2025.
- https://huggingface.co/rayenhizaoui/Whisper-Rayen-Medical : Whisper Small adapté aux prescriptions françaises selon la fiche ; corpus propriétaire et évaluation à examiner.
- https://huggingface.co/StephaneBah/Whisper-AfroRad-FR : adaptation radiologique et accents francophones africains ; environ 4,5 h d’entraînement annoncées, évaluation étroite et auto-déclarée.
- https://huggingface.co/google/medasr : exemple spécialisé médical anglophone, 105 M paramètres selon Google ; pas un candidat français prêt à l’emploi.

## Observations
- [limitation] Le classement communautaire https://models.handy.computer/languages/fr/ sur FLEURS porte sur parole lue ; ne pas transposer ses scores aux consultations ou ses vitesses à une autre machine.
- [limitation] Les estimations de poids/RAM de la conversation ne sont pas des mesures. Ne pas promettre des seuils 8/16 Go sur leur base ni reprendre les chiffres comme résultats.
- [limitation] Les horodatages et capacités streaming dépendent aussi du moteur ; support de l’architecture ne prouve pas une intégration utilisable.
- [question] Vérifier séparément licences des poids, code, jeux de données et éventuels adaptateurs.

## Relations
- relates_to [[Cadrage et suite]]
- informs [[Protocole à définir]]
