---
title: Décision — bench d'extraction LLM et web en consultation seule (2026-11-19)
type: decision
permalink: transcription-bench/projet/decision-bench-dextraction-llm-et-web-en-consultation-seule-2026-11-19
status: active
updated: '2026-11-19'
tags:
- decision
- extraction
- llm
- web
- cli
---

Provenance : session du 2026-11-19, dépôt `transcription-bench`, branche `main` (base `8cafec7`), contexte serveur de développement ; décisions du propriétaire, specs rédigées puis relues par advisor (publiables). Aucun moteur, poids ni inférence.

## Décisions
- [decision] Élargir le banc aux LLM locaux qui remplissent une grille structurée depuis une transcription de consultation. Le programme mesure les ressources et présente les résultats ; il ne juge pas la qualité (humain ou agent local extérieur). Change OpenSpec `ajouter-bench-extraction`.
- [decision] Grille = fichier Markdown sous `grilles/` : `##` = case, texte = consigne, « Liste. » = plusieurs entrées, `###` = sous-cases, `null` = non mentionné, section `autres_informations` ajoutée d'office. Pas de citation-preuve par valeur (refusée par le propriétaire).
- [decision] Entrée = transcriptions existantes (`identifiant:ordre`) ; pas de saisie libre ni d'enchaînement automatique pour l'instant.
- [decision] Moteur llama.cpp via llama-cpp-python 0.3.36 (dernière avec roues CPU Linux x64/Windows x64, vérifié le 2026-11-19), API de bas niveau seulement (la classe `Llama` compile les gabarits Jinja embarqués), format de conversation local par architecture, grammaire chargée explicitement sans repli (`response_format` retombe silencieusement en 0.3.36), génération token par token.
- [decision] Paliers ciblés dès le départ : 8 Go (Ministral 3 3B Q8_0, Qwen3.5-4B Q4_K_M) et 16 Go (Ministral 3 8B, Qwen3.5-9B, Granite 4.2 8B en Q4_K_M, Gemma 4 E4B Q8_0) ; tous Apache 2.0, non restreints (API HF, 2026-11-19). Écartés : MedGemma, LFM2.5, EuroLLM-22B.
- [decision] Web réduit à la consultation (GET seul, sans script) ; CLI = seule interface d'action ; parité inversée. Change séparé `alleger-interface-web`, à archiver après `ajouter-cli-agent` et avant `ajouter-bench-extraction`.
- [decision] `ajouter-cli-agent` et `rediger-documentation-utilisateur` laissés en l'état.
- [decision] `AGENTS.md` mis à jour avec accord (périmètre, web cible et transition, CI sans llama-cpp sans nouvel accord).

## Limites et suite
- [incertain] Prise en charge des architectures Qwen3.5/Gemma 4/Granite 4.2 par la llama.cpp de la 0.3.36, conversion JSON Schema → GBNF du sous-ensemble prévu et compteurs natifs — invérifiable d'ici, vérifié le 2026-11-19, non tranché : essai minimal (tâche 0) sur PC Linux avec accord.
- [constraint] Qualité française et débits CPU des candidats non mesurés ; aucune vérification Windows sans extension autorisée de la CI.

## Relations
- relates_to [[Décisions du prototype de benchmark]]
- relates_to [[Protocole à définir]]
