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

Point de reprise pour l'agent du lab (serveur de développement). Provenance : sessions du 2026-11-19 sur le lab, base `e921611` puis commits `7dba2c9` (lot 1), `62137ce` (lot 2) et lot 3 poussés le même jour. Contexte des choix : [[Décision — bench d'extraction LLM et web en consultation seule (2026-11-19)]].

## État au 2026-11-19 (soir)
- [validation] `alleger-interface-web` appliqué sur le lab : tâches 1.1 à 1.5, 2.1, 2.2, 3.1 et 3.3 cochées (3.2 l'était à la rédaction). Suite 1436 → 1240 tests OK moteur factice ; `openspec validate --strict` exit 0, seul l'INFO attendu `cli-interface` (spec cible absente tant que `ajouter-cli-agent` n'est pas archivé, D5). Web en consultation seule sans POST ni script, CLI seule interface d'action, AGENTS.md actualisé (clause de transition retirée).
- [validation] Méthode appliquée selon accord du propriétaire : worker par tâche, corrections et relecture du principal, revue advisor par lot, commit et push par lot. Délégation de session sur consigne du propriétaire : workers sur `opencode-go/glm-5.3` (thinking max) ; revues advisor du lot 1 sur Opus, du lot 2 sur GLM (quota Anthropic saturé), du lot 3 sur `openai/gpt-6.2-sol` (thinking medium, deux contre-avis).
- [limit] Tâches 3.4 (contrôle visuel par le propriétaire des trois pages, clair et sombre, 1280 et 360 px) et 3.5 (archivage, `Purpose` de `local-web-interface`) ouvertes ; 3.5 attend l'archivage d'`ajouter-cli-agent` (tâche 4.5 Windows). La revue du lot 3 a distingué dans le guide les preuves CLI du 13-11 des mesures de l'ancien parcours web ; le parcours à froid du guide réécrit n'est pas rejoué, la 4.3 de `rediger-documentation-utilisateur` doit porter sur le nouveau texte. CI Windows : dernier run de la suite factice le 2026-11-02, moteurs le 2026-11-13.
- [observation] Flake connu : `test_run_signals.py::test_brutal_termination_is_recovered_by_next_command` échoue rarement en suite complète (famille intermittente documentée) ; relancer en isolation avant tout diagnostic.

## Par où continuer
1. `ajouter-bench-extraction` lots 1 à 5 avec le moteur factice, même méthode ; grilles, déclarations, runner, service, commandes, pages, documentation.
2. Hors lab sans nouvel accord : tâches 0 (essai minimal) et 6 (qualification) sur PC de test Linux déclaré ; tâche 2.2 verrou à rédiger sans le résoudre ni installer ; adaptateur réel 3.3 après le verdict de 0.1 ; aucune extension de la CI.

## Pièges déjà identifiés (revue advisor de la rédaction)
- Ne jamais utiliser la classe `Llama` ni `response_format` de llama-cpp-python 0.3.36 : API de bas niveau, grammaire chargée explicitement sans repli, format de conversation local par architecture (D3/D4).
- `result.json` écrit en dernier par source ; journal sans texte médical ; `job.json` nettoyé (D7).
- Regroupement des extractions par source + grille + schéma (D9).

## Méthode
- Une tâche à la fois via worker, revue advisor par lot, le principal coche `tasks.md` et corrige ; commit et push par lot sur demande explicite du propriétaire (accord du 2026-11-19 pour ce fil de travail).