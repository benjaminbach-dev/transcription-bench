---
title: Cadrage et suite
type: note
permalink: transcription-bench/projet/cadrage-et-suite
status: historique du besoin produit ; prototype cadré dans OpenSpec
provenance: conversation initiale
date: '2026-10-23'
tags:
- exploration
- '2026-10-23'
---

# Cadrage et suite

## Provenance et état
Historique de l'exploration du 2026-10-23, conservé pour comprendre le besoin produit. Depuis, le prototype a été cadré dans [[Décisions du prototype de benchmark]] et dans le change OpenSpec `add-benchmark-prototype`, consolidé le 2026-10-24 (repo `transcription-bench`, branche `main`, base `b3f126c`). Aucun essai réel ni code applicatif à cette étape.

Le besoin initial comparait des modèles open weight français en local, en privilégiant la fidélité à la vitesse : dictée bruitée de 1 à 3 minutes et entretien de 20 à 40 minutes avec plusieurs voix. Une application métier de transcription a été envisagée comme prolongement distinct du prototype de benchmark, sans engagement dans ce premier jalon. Diarisation et streaming ne font pas partie de ce premier jalon.
## Observations
- [requirement] La transcription française et la fidélité du texte priment sur la rapidité ; aucun seuil acceptable de latence ou d’erreur n’est fixé.
- [requirement] Pour les consultations, distinguer au minimum deux intervenants, sans présumer leurs rôles ou connaître leur identité.
- [requirement] Le traitement doit pouvoir être entièrement local ; PC utilisateur et serveur local sont des pistes de déploiement.
- [proposal] Une même application pourrait utiliser un moteur sur le PC ou sur un serveur choisi par l’utilisateur ; ce n’est pas une architecture approuvée.
- [proposal] Le streaming a été exploré ; son caractère obligatoire et son délai acceptable ne sont pas décidés.
- [proposal] Une interface de transcription provisoire suivie d’une passe finale a été évoquée, sans engagement de réalisation.
- [proposal] Fine-tuning et location de serveur GPU sont des pistes ultérieures, pas des travaux démarrés.
- [decision] Initialiser ici un dépôt GitHub privé benjaminbach-dev/transcription-bench et une mémoire locale versionnable.
- [decision] Intention initiale désormais cadrée : réaliser le prototype portable décrit dans le change OpenSpec `add-benchmark-prototype` ; la faisabilité réelle reste à valider sur PC avant implémentation complète.
- [constraint] Ne pas assimiler la machine de développement à la configuration minimale du produit.

## Environnement observé, non cible produit

Répertoire initial : `/home/ben/Dev/Transcriptions bench`. Manjaro Linux, Ryzen 7 PRO 6850U (8 cœurs/16 threads), 32 Go installés (environ 30 Gio visibles), Radeon 680M intégrée, sans GPU dédié. Environ 22 Gio disponibles au relevé initial, aucun swap configuré. Ollama/llama.cpp non trouvés dans le PATH et emplacements usuels ; service Ollama absent. Cela n’exclut pas d’anciens fichiers ailleurs. Ces observations sont datées et ne prouvent aucune performance.

## Relations
- relates_to [[Écueils et arbitrages]]
- relates_to [[Modèles et sources]]
- relates_to [[Protocole à définir]]
