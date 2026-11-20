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

## État au 2026-11-20 (lots 4.1-4.3 du lab)

- [validation] 4.1 consultation des extractions : regroupement par triplet (empreinte texte, grille, schéma), tris temps/ram/cpu/recent, indicateurs et ratios, factices séparés, version de consignes différente signalée, aucune écriture. Tests unitaires 48. Revue principal : contrôle de l'enveloppe extraction.json, lecture des copies au-delà de 16 MiB, tris de RAM sans overflow. Suite complète 1621 tests OK après 4.1.
- [validation] 4.2 commandes de consultation : extract list/show/compare/explain, results history étendu aux deux types. Sortie texte et JSON avec indicateurs complets (délai premier token, vitesse de génération, marques, copy_issue), métadonnées complètes accessibles. Historique combiné (historique.py) avec anciennes clés audios_traites/audios_total préservées. 209 tests ciblés OK.
- [validation] 4.3 pages web : cinq routes GET/HEAD (/extractions, /extractions/<id>, /extractions/aide, /extractions/comparaison, /extractions/comparaison/<cle>), navigation à quatre rubriques, détail grille/source côte à côte, comparaison 2-6 avec source commune, historique combiné typé, parité web/CLI étendue. 345 tests ciblés OK. Suite complète 1658 tests OK.
- [observation] Navigation automatique : detail clair 1280×900 vérifié (grille+source côte à côte, 571 px chacun, scrollWidth=clientWidth=1280, chaînes hostiles affichées en texte, navigation 4 liens avec aria-current). Sombre et 360px non vérifiés (bascule thème indisponible dans le navigateur headless). favicon 404 mineur en console.
- [limit] 4.4 contrôle visuel propriétaire non effectué (clair/sombre 1280/360). 5.1 documentation et 5.3 validation finale restent ouvertes. Tâches 6.2-6.3 (qualification PC) hors périmètre lab.
- [limit] 9 WARNING OpenSpec (exigences > 500 caractères) et 2 INFO (archive) à traiter en 5.3.
- [next] 4.4 contrôle visuel par le propriétaire (clair/sombre, 1280 et 360 px, détail grille/source côte à côte et comparaison 6 modèles). 5.1 documentation (guide, technique, licences, rappel exactitude médicale). 5.3 validation OpenSpec strict + suite complète + revue advisor + mémoire.

## Méthode
- Une tâche à la fois via worker, revue advisor par lot, le principal coche `tasks.md` et corrige ; commit et push par lot sur demande explicite du propriétaire (accord du 2026-11-19 pour ce fil de travail ; pause demandée après le lot 3).


## État au 2026-11-20 (fin de journée : lot 4 et lot 5 côté lab)

- [validation] Lot 4 terminé et poussé : 4.3 relue (aucun défaut ; commentaires périmés corrigés), audit de couverture des scénarios (test des anciennes routes 404 ajouté), revue advisor Opus sans bloquant, 4.4 contrôle visuel fait par navigator sur données synthétiques (clair/sombre, 1280/360, aucun défilement horizontal).
- [limit] 4.4 : le thème sombre n'a pas pu être émulé nativement (aucun outil Playwright MCP pour emulateMedia) ; contrôle fait via feuilles temporaires où prefers-color-scheme: dark devient all. Observation mineure non corrigée : noms de modèles coupés en milieu de mot dans les colonnes étroites de la comparaison à 1280 px.
- [validation] 5.1 documentation (guide section 12 avec renumérotation, technique, licences des six candidats) rédigée par worker Opus puis revue advisor (une erreur corrigée : cause de fin « arret », pas « eog »). 5.3 : 9 exigences raccourcies, openspec validate --strict valide (2 INFO d'archivage attendus : dépendent de l'archivage préalable d'alleger-interface-web et ajouter-cli-agent). Suite complète 1659 OK.
- [next] Archivage de ajouter-bench-extraction après alleger-interface-web (3.4/3.5) et ajouter-cli-agent ; tâches 6.2/6.3 restantes sur PC de test (statuer sur les écarts de gabarit Qwen et Granite). Dettes du lot 3 inchangées.