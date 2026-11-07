---
title: Reprise transcription-bench — méthode d'orchestration et état après la refonte
  résultats, 2026-11-07
type: note
permalink: transcription-bench/projet/reprise-transcription-bench-methode-dorchestration-et-etat-apres-la-refonte-resultats-2026-11-07
tags:
- reprise
- orchestration
- methode
- openspec
- etat
---

# Reprise transcription-bench — méthode d'orchestration et état après la refonte résultats, 2026-11-07

Note de reprise fraîche, point d'entrée unique avant compaction de session. Elle documente la **méthode d'orchestration éprouvée** pour implémenter les changes restants, autant que l'état courant. Historique détaillé : [[Reprise refonte parcours résultats — pause après le lot 4, 2026-11-07]] (lots 1–6), [[Reprise refonte parcours résultats — lot 1 et orchestration 2026-11-07]], [[Décisions du prototype de benchmark]].

## État du dépôt

- [status] `transcription-bench`, branche `main`, remote `git@github.com:benjaminbach-dev/transcription-bench.git`, identité Benjamin Bach <mail@benjaminbach.dev>. Arbre propre (hors `.playwright-mcp/` non suivi, à préserver et ne jamais committer). Dernier commit `9a2a84f`, CI « Tests Linux et Windows » verte (run 42421207191, Ubuntu 24.04 + Windows 2022).
- [status] Change `refondre-parcours-resultats` : **20/20 tâches, lots 1–6 poussés, prêt pour archivage sur demande dédiée** (aucun archivage ni synchronisation sans demande ; ordre de fusion D7 : Sumi → première lecture → présent change). Aperçu de fusion déjà validé (4 RENAMED / 18 MODIFIED / 10 ADDED, copie isolée 9/9, matrice D7 préservée).
- [status] Autres travaux ouverts (la « suite vierge ») : `rediger-documentation-utilisateur` (7/19 tâches, artefacts complets), `mesurer-charge-systeme` (0/12 tâches, artefacts complets, indépendant, ne jamais réintroduire ses contraintes de présentation dans l'UI). Specs principales : benchmark-runs 16, engine-management 8, local-web-interface 25, model-management 11, platform-verification 24, results-comparison 12 exigences. `openspec list` / `openspec status --change <nom>` pour l'état à jour.

## Méthode d'orchestration (à réutiliser telle quelle)

- [decision] **Par lot de 3 tâches max, une tâche à la fois, séquentiellement.** Pour chaque tâche : (1) un **worker neuf** implémente ; (2) le principal **relit tout le diff, corrige et verrouille** (tests) ; (3) **navigator** contrôle en navigateur ; (4) le principal corrige les constats ; (5) **commit + push de la tâche seule** (fichiers de la tâche uniquement). Fin de lot : **advisor** relit le lot complet ; le principal corrige les majeurs (et les mineurs à coût nul) ; re-push. Puis lot suivant. Ne jamais commencer une tâche avant le push de la précédente.
- [decision] **Modèles** : worker = `opencode-go/deepseek-v4.1-flash` avec `thinking: high` (repli Haiku 5.5 / high si indisponible — jamais lent) ; navigator = `sonnet-5.5`, `thinking: medium` ; advisor = `opus-5.5`, `thinking: medium`. Un seul worker à la fois, aucun enfant ne délègue.
- [decision] **Contenu des briefs worker** (éprouvé) : intitulé exact de la tâche + chemins des specs/design à lire AVANT de coder ; état du code récent (commit précédent) ; exigences de réalisation point par point ; contraintes absolues (aucune installation/téléchargement/réseau/moteur réel/dépendance, `uv run --locked --offline`, suite complète verte, ne rien toucher hors périmètre, aucun commit, signaler le non résolu au lieu de deviner) ; rapport final exigé (fichiers, choix, comptes de tests, non résolus).
- [decision] **Contenu des briefs navigator** : URL de base du harnais local, données synthétiques décrites, périmètre de pages, actions interdites (POST destructeurs) explicites, points à vérifier avec mesures (positions y, attributs, comptage requêtes), console/réseau loopback, captures max à la racine (à supprimer avant commit), rapport constat/prouvé vs non vérifié. Navigator a `codemode` + Playwright MCP (22 outils) mais **aucun contrôle de contexte** (pas de JS-off ni d'`emulateMedia`) et pas de bash.
- [decision] **Advisor uniquement en fin de lot ou sur blocage** (« si blocage, advisor »). Lui demander de classer bloquant/majeur/mineur et de trancher les questions de conformité spec. Ses constats majeurs sont corrigés par le principal avec tests, puis poussés.
- [constraint] **Ne jamais s'arrêter pour une attente** (CI, workers, sous-agents) : suivre la CI jusqu'au vert (rerun du job défaillant si famille intermittente connue), relancer/attendre les workers. Seuls deux arrêts légitimes : décision nécessaire au propriétaire ou bilan final. Le propriétaire a explicitement sanctionné un arrêt inutile (« tu n'aurais pas du t'arrêter »).
- [decision] **Mémoire** : MCP `basic-memory`, `project: transcription-bench`, seul le principal écrit ; une note de reprise fraîche à chaque jalon de session, ajoutée au commit de clôture. Captures navigator supprimées nominalement avant commit ; `.playwright-mcp/` jamais committé.

## Réflexes de qualité (accumulés sur les 20 tâches)

- [implementation] Harness de recette dans `/tmp/<projet>/` (copie de `servir.py` + fixtures synthétiques : WAV courts via `ecrire_wav`, exécutions fabriquées, moteur factice enveloppé à délai artificiel pour polling/arrêt, inventaire de modèles factices injecté via `ServicesApplication(modeles=...)`). Un port par lot. Ne jamais supposer PID/port : relire et vérifier. `nohup .venv/bin/python harness.py > log 2>&1 &`, `kill -TERM` en fin.
- [implementation] Suites : ciblées d'abord, puis `uv run --locked --offline python -m unittest discover -s tests -t .` (référence courante **1133 tests**), `openspec validate --all --strict`, `git diff --check`. CI auto sur push (workflow « Tests Linux et Windows », job « Tests sans moteur réel ») ; pas de job moteur sans accord.
- [limit] **Famille d'intermittence connue** (tests d'arrêt/interruption : `test_arret_utilisateur_interrompu_conserve_les_resultats`, « pid vide », lectures de fichiers pas encore écrits) : module seul + suite verte au rerun, **jamais présenter un rerun vert comme preuve** ; flau ouvert.
- [implementation] Pièges récurrents : apostrophes françaises échappées par Jinja (`html.unescape` dans les assertions) ; `rg -n` sans `-r` (le `-r` remplace les correspondances) ; scénarios OpenSpec = **identifiants stables** (un bloc MODIFIED ne peut pas les renommer depuis le socle courant) ; les tests verts prouvent l'absence de régression, pas le comportement nouveau sans assertion dédiée ; distinguer « configuration hors ligne » et « isolation réseau prouvée ».
- [limit] **Ne pas réutiliser comme preuve** : validations de l'ancienne interface, données CI comme performances, valeurs factices comme mesures, comptages de tests comme lisibilité. Le sombre réel et le sans-JS ne sont **jamais observés** (décisions propriétaires 1.5 et 6.1 — constat honnête obligatoire si de nouveaux écrans les impliquent).

## Prochaines étapes

- [next] Sur demande : archivage/synchronisation de `refondre-parcours-resultats` (ordre D7 ci-dessus), puis suite de `rediger-documentation-utilisateur` (7/19) ou `mesurer-charge-systeme` (0/12) — **par la méthode ci-dessus, lot par lot**, en adaptant les briefs aux specs concernées. Respecter le périmètre de chaque change et ses préalables (qualification Linux, CI factice Windows autorisée, aucune mesure non qualifiée présentée comme représentative).
- [next] Les jobs moteurs manuels (installation des trois environnements, inférences) restent soumis à autorisation explicite avec périmètre annoncé — jamais déclenchés d'initiative.

## Relations

- relates_to [[Reprise refonte parcours résultats — pause après le lot 4, 2026-11-07]]
- relates_to [[Décisions du prototype de benchmark]]
- relates_to [[Lecture grand public et occupation des ressources — cadrage 2026-11-04]]
