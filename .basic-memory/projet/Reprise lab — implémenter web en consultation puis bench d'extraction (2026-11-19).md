---
title: Reprise lab — implémenter web en consultation puis bench d'extraction (2026-11-19)
type: handoff
permalink: transcription-bench/projet/reprise-lab-implementer-web-en-consultation-puis-bench-dextraction-2026-11-19
status: active
updated: '2026-11-19'
tags:
- handoff
- extraction
- web
---

Point de reprise pour l'agent du lab (serveur de développement). Provenance : session locale du 2026-11-19, base `8cafec7` + commit des specs. Contexte des choix : [[Décision — bench d'extraction LLM et web en consultation seule (2026-11-19)]].

## Par où commencer
1. Lire `AGENTS.md` (mis à jour le 2026-11-19), puis `openspec list` et les deux changes : `alleger-interface-web` et `ajouter-bench-extraction` (proposal, design, tasks, specs).
2. Implémenter d'abord `alleger-interface-web` (petit, sans dépendance nouvelle) : tâches 1.1 → 3.4. Son archivage (3.5) attend celui d'`ajouter-cli-agent`, laissé ouvert par le propriétaire (tâche 4.5 Windows) : ne pas archiver sans son accord.
3. Puis `ajouter-bench-extraction`, groupes 1 à 4 (grilles, déclarations, runner, moteur factice, stockage, commandes, pages), entièrement testables avec le moteur factice.

## Ce que le lab ne fait pas
- [constraint] Tâches 0 (essai minimal) et 6 (qualification) : PC de test Linux déclaré uniquement, avec accord explicite (installation de llama-cpp-python, téléchargement de poids, inférence). Ne pas les exécuter sur le lab.
- [constraint] Tâche 2.2 : rédiger le verrou `requirements/llama-cpp.*` ; ne le résoudre qu'avec l'accord du propriétaire et sans rien installer.
- [constraint] L'adaptateur réel `llama_cpp.py` (3.3) attend le verdict de la tâche 0 ; seuls des tests sans import de la bibliothèque sont possibles avant.
- [constraint] Aucune extension de la CI à llama-cpp sans nouvel accord.

## Pièges déjà identifiés (revue advisor)
- Ne jamais utiliser la classe `Llama` ni `response_format` de llama-cpp-python 0.3.36 : API de bas niveau, grammaire chargée explicitement, format de conversation local par architecture (design D3/D4).
- `result.json` écrit en dernier par source ; journal sans texte médical ; `job.json` nettoyé (D7).
- Regroupement des extractions par source + grille + schéma (D9).

## Méthode
- Comme les lots précédents : une tâche à la fois via worker, revue advisor par lot, le principal coche `tasks.md` ; commit et push seulement sur demande explicite du propriétaire.
