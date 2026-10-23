---
title: Protocole à définir
type: note
permalink: transcription-bench/bench/protocole-a-definir
status: exploratoire
provenance: conversation initiale
date: '2026-10-23'
tags:
- exploration
- '2026-10-23'
---

# Protocole à définir

## Statut

Piste de travail issue de la conversation du 2026-10-23. L’utilisateur souhaite ensuite un petit prototype portable de benchmark. Cette note n’autorise pas son implémentation ni ne fixe sa pile. Aucun corpus, modèle ou résultat présent dans le dépôt.

## Questions à trancher avant implémentation

- Quels OS et architectures doivent être supportés au premier jalon ? Linux de développement ne signifie pas portabilité Windows/macOS acquise.
- CLI, interface minimale ou autre forme ? Quel mécanisme d’installation et téléchargement explicite des modèles ?
- Quels un ou deux moteurs et modèles pour le premier comparatif ? Éviter d’implémenter toutes les pistes d’un coup.
- Quel corpus autorisé, quelles références manuelles et quel stockage local hors Git ?
- Fichiers seulement au premier jalon ou streaming explicitement inclus ? Diarisation immédiate ou après transcription ?
- Quel format de sortie reproductible et partageable sans données personnelles ?
- Quelle convention de nombres, unités, abréviations et segmentation des voix pour l’évaluation ?

## Mesures proposées, non implémentées

Conserver configuration et versions exactes : modèle, révision, quantification, moteur, threads, backend, découpage et matériel. Distinguer chargement à froid, exécution à chaud et durée totale réellement perçue. RTF = durée de calcul / durée audio ; RTF > 1 signifie plus lent que l’enregistrement.

- [proposal] Mesurer durée totale et par étape : transcription, alignement éventuel, diarisation et post-traitement.
- [proposal] Mesurer pic de RAM, swap et concurrence réelle des composants, sans déduire la consommation du seul poids des fichiers.
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
