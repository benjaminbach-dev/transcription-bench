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

Point de reprise pour l'agent du lab (serveur de développement). Provenance : sessions du 2026-11-19 sur le lab, base `e921611` puis commits poussés le même jour : `7dba2c9`/`62137ce`/`def9cbf` (change `alleger-interface-web` appliqué), `72e528c`/`26868bc` (lots 1-2 d'`ajouter-bench-extraction`) et lot 3 poussé en fin de soirée. Contexte des choix : [[Décision — bench d'extraction LLM et web en consultation seule (2026-11-19)]].

## État au 2026-11-19 (fin de soirée, pause demandée)
- [validation] `alleger-interface-web` appliqué : 10/12 tâches (3.4 contrôle visuel propriétaire et 3.5 archivage — dépend `ajouter-cli-agent` — restent ouvertes). Suite 1436 → 1240 OK ; validate --strict exit 0.
- [validation] `ajouter-bench-extraction` : lots 1 à 3 appliqués et poussés (grilles D1/D2/D3 + commandes `grids` ; déclarations + verrou llama-cpp non résolu + compatibilité ; protocole, runner, factice, service, commandes `extract options/check/start`). Suite au lot 3 : **1527 tests OK** (1240 → 1527). Cases cochées : 1.1-1.4, 2.1-2.3, 3.1, 3.2, 3.4, 3.5 (et 5.2). **Case 3.3 volontairement ouverte** : partie factice faite, l'adaptateur réel `llama_cpp.py` attend le verdict de 0.1 (annotation détaillée dans tasks.md).
- [validation] Revues par lot : advisor Opus ou GLM/sol selon les saturations du quota Anthropic ; le lot 3 a eu Opus (favorable) puis trois contre-revues sol exigeantes — toutes les failles relevées ont été corrigées avec tests (journal sans recopie des lignes refusées même au marqueur nu, confinement des fichiers JSON et de la racine `data/extractions`, cache lié refusé, `run.json` écrit avant les copies, restes de travail visibles dans la ligne finale, `RecursionError` couvert).
- [limit] Verrou `llama-cpp` : rédigé par métadonnées, NON résolu ni vérifié ; résolution réelle sur PC (0.1), verrou résolu commité et `verrou_valide=True` AVANT 6.1 (sinon le programme refuse l'installation) ; liste blanche provisoire (mistral3, qwen35, granite, gemma4) à confirmer en 6.2.
- [limit] Dettes déclarées au lot 3 (revues) : sortie brute perdue si `ErreurSource` après des tokens (bogue d'adaptateur, cas limite) ; ~100 lignes de machine d'état dupliquées d'`ExecutionMoteur` dans `ExtractionExecution` (factorisation à prévoir) ; asymétrie : la transcription historique n'a pas le contrôle « cache lié » ; tests de liens sans gardes Windows (convention des fichiers existants) ; TOCTOU assumé (documenté au niveau du projet) ; `openspec validate ajouter-bench-extraction --strict` échoue sur 9 WARNING « exigences > 500 caractères » (rédaction à raccourcir en 5.3) + INFO d'ordonnancement D5.
- [observation] Flake connu : `test_run_signals.py::test_brutal_termination_is_recovered_by_next_command` — un échec à froid rare, repasse en isolation et en suite ; relancer avant tout diagnostic.

## Par où continuer (lots 4-5 sur le lab)
1. `extract list/show/compare/explain` + `results history` aux deux types (4.1, 4.2) ; pages web `/extractions` à quatre rubriques et parité (4.3) ; 4.4 contrôle visuel propriétaire suspendu.
2. Documentation 5.1 (guide, technique, licences des six candidats) puis 5.3 : validate --strict (raccourcir les exigences verboses), suite complète, revue advisor, mémoire.
3. Hors lab sans nouvel accord : tâches 0 (essai minimal) et 6 (qualification) sur PC de test Linux déclaré ; l'adaptateur réel 3.3 après 0.1 ; pas d'extension de la CI.

## Pièges déjà identifiés (revues advisor)
- Ne jamais utiliser la classe `Llama` ni `response_format` de llama-cpp-python 0.3.36 : API de bas niveau, grammaire chargée explicitement sans repli, format de conversation local par architecture (D3/D4).
- `result.json` écrit en dernier par source ; journal sans texte médical ni sortie du modèle ; `job.json` nettoyé (D7).
- Regroupement des extractions par source + grille + schéma (D9) ; le moteur réel devra neutraliser ses journaux natifs sur stderr pour tenir « run.log sans texte ».
- Contrat du runner figé à 7 clés : l'étendre AVEC le protocole et le consignateur au moment de l'adaptateur réel.

## Méthode
- Une tâche à la fois via worker, revue advisor par lot, le principal coche `tasks.md` et corrige ; commit et push par lot sur demande explicite du propriétaire (accord du 2026-11-19 pour ce fil de travail ; pause demandée après le lot 3).