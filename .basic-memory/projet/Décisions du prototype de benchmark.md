---
title: Décisions du prototype de benchmark
type: note
permalink: transcription-bench/projet/decisions-du-prototype-de-benchmark
status: brainstorming validé, specs non rédigées
provenance: session Pi du 2026-10-23, repo transcription-bench, branche main, commit
  3aa6d35
date: '2026-10-23'
tags:
- decision
- brainstorming
- '2026-10-23'
---

# Décisions du prototype de benchmark

## Provenance et état
Brainstorming du 2026-10-23 (serveur, branche `main`, commit `3aa6d35`). Décisions validées par Ben ; specs OpenSpec pas encore rédigées ; aucun code, moteur ou modèle installé.

## Finalité
Outil de décision : estimer ce que des modèles ASR donneront sur des machines ordinaires, sans GPU dédié. Deux utilisateurs : Ben (Linux x64) et un collègue (PC Windows x64).

## Observations
- [decision] Programme Python, serveur web local, interface en HTML pur (ni CSS ni JavaScript), formulaires et bouton d'actualisation.
- [decision] Plateformes : Windows x64 et Linux x64 ; Mac hors périmètre.
- [decision] Libre choix du modèle par identifiant Hugging Face, dans les limites des moteurs installés ; refus explicite si incompatible ; aucune exécution de code distant arbitraire.
- [decision] Trois moteurs : faster-whisper (CTranslate2), transcribe.cpp, Hugging Face Transformers ; architecture prévue pour ajouter des moteurs via des adaptateurs.
- [decision] Transformers sert à l'exploration libre ; ses temps CPU ne représentent pas forcément un déploiement optimisé.
- [decision] Exécution CPU uniquement pour les mesures de référence (GPU et Vulkan désactivés, consigné dans les métadonnées).
- [decision] RTF ≤ 2 = objectif à terme, affiché comme repère ; jamais un critère d'exclusion pendant les benchs.
- [decision] Audios déposés dans un dossier prédéfini ; traitement unitaire ou par lot séquentiel ; jamais de parallélisme.
- [decision] Chaque exécution conserve transcription, métadonnées (audio + empreinte, modèle + révision, moteur + version, quantification, réglages effectifs, machine) et mesures, sans écraser les précédentes ; comparaison de transcriptions entre modèles dans l'interface.
- [decision] Réglages exposés seulement s'ils sont pris en charge par le moteur, valeurs par défaut effectives enregistrées.
- [decision] Mesures : temps de chargement, temps de transcription par audio, temps total, durée audio, RTF, pic de RAM en valeur brute, temps CPU consommé. Pas de pourcentages, pas de swap.
- [decision] Hors premier jalon : diarisation, correction par LLM, streaming, score WER automatique.
- [decision] Le lancement du serveur n'installe pas les moteurs ; installation d'un moteur et téléchargement d'un modèle = actions explicites dans l'interface.
- [constraint] Aucun téléchargement de moteur ou de modèle sur le serveur de développement ; inférences et mesures uniquement sur le PC de Ben (et celui du collègue). Le serveur sert au code, à l'interface et aux tests avec moteur factice.

## Relations
- relates_to [[Cadrage et suite]]
- implements [[Protocole à définir]]
- relates_to [[Moteurs et faisabilité technique]]
