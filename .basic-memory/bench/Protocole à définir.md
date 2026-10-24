---
title: Protocole à définir
type: note
permalink: transcription-bench/bench/protocole-a-definir
status: protocole partiellement cadré ; corpus et évaluation à définir
provenance: conversation initiale
date: '2026-10-23'
tags:
- exploration
- '2026-10-23'
---

# Protocole à définir

## Statut
Exploration du 2026-10-23, réconciliée le 2026-10-24 avec les décisions du prototype (repo `transcription-bench`, branche `main`, base `b3f126c`). Le change OpenSpec `add-benchmark-prototype` définit désormais l'outil et les mesures ; aucun résultat réel n'existe. Les propositions d'évaluation qualité ci-dessous concernent la suite, pas des fonctionnalités approuvées du premier jalon.
## État du protocole : décisions et questions restantes
### Points désormais tranchés pour le prototype

Windows x64 et Linux x64 ; application Python locale via uv ; HTML sans CSS/JavaScript ; trois moteurs isolés, dont Transformers limité à Whisper et Parakeet TDT au premier jalon ; CPU uniquement ; fichiers et lots séquentiels ; installation et téléchargement explicites. Streaming, diarisation, correction LLM et WER automatique hors périmètre. Pas de mesure de swap ou de pourcentage dans ce jalon. Voir [[Décisions du prototype de benchmark]] et les exigences OpenSpec.

### Questions encore ouvertes

- Corpus autorisé et représentatif, références manuelles et protocole de relecture des erreurs critiques.
- Conventions de nombres, unités et abréviations pour une future évaluation de qualité.
- Conditions de répétition et distinction cache disque froid/chaud ; aucun nettoyage automatique du cache ni répétition automatisée prévus.
- Format agrégé partageable sans données personnelles, si un partage devient nécessaire.
- Validation pratique des moteurs, familles, fichiers et réglages sur chaque OS, au jalon préalable sur PC.
## Mesures proposées, non implémentées

Conserver configuration et versions exactes : modèle, révision, quantification, moteur, threads, backend, découpage et matériel. Distinguer chargement à froid, exécution à chaud et durée totale réellement perçue. RTF = durée de calcul / durée audio ; RTF > 1 signifie plus lent que l’enregistrement.

- [proposal] Mesurer durée totale et par étape : transcription, alignement éventuel, diarisation et post-traitement.
- [proposal historique] Mesurer swap et concurrence pourrait servir au produit ultérieur ; le prototype retient uniquement le pic RSS brut cumulatif du moteur, pas le swap ni les pourcentages.
- [proposal] Évaluer WER et erreurs critiques : noms de médicaments, doses, unités, fréquences, négations, allergies, omissions et ajouts.
- [proposal] Évaluer séparément l’attribution des intervenants, la stabilité de leurs étiquettes et les chevauchements.
- [proposal] Tester dictée propre/bruitée si ce cas reste dans le périmètre, et consultations de 20–40 minutes avec deux voix.
- [constraint] Ne pas corriger par LLM avant de scorer la transcription brute ; évaluer toute correction séparément contre l’audio et la référence.
- [constraint] Pas de résultat clinique validé ni de temps réel garanti sans protocole et mesures représentatives.
- [constraint] Résultats bruts et audios restent locaux et ignorés ; un résultat agrégé doit être inspecté avant tout partage.

## Relations
- implements [[Cadrage et suite]]
- depends_on [[Écueils et arbitrages]]
- relates_to [[Modèles et sources]]
