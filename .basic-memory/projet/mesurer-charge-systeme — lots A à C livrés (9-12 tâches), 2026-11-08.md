---
title: mesurer-charge-systeme — lots A à C livrés (9/12 tâches), 2026-11-08
type: note
permalink: transcription-bench/projet/mesurer-charge-systeme-lots-a-a-c-livres-9-12-taches-2026-11-08
tags:
- mesurer-charge-systeme
- etat
- reprise
---

# mesurer-charge-systeme — lots A à C livrés (9/12 tâches), 2026-11-08

## État

- [status] Change `mesurer-charge-systeme` : **9/12 tâches livrées et poussées** (lots A `205f2e8`→`3876129`+`d951ebe`, B `3dacb97`/`25b59a6`/`a818ce5`+`9a53dfe`, C `a2b5891`/`70e119a`/`ac7123a`+`408ead5`), CI factice **Ubuntu et Windows verte** sur tous les commits du change. **4.3, 4.4 et 4.5 ouvertes par décision du propriétaire** (« pas de lot d » : non PC de test, jobs moteurs non autorisés) — 4.5 porte aussi la validation OpenSpec stricte finale et l'observation navigator clair/sombre. **Aucune mesure réelle ; change non archivable en l'état** (workflow : « garder les volets non exécutés ouverts »).
- [decision] Même méthode d'orchestration que `refondre-parcours-resultats` (worker deepseek flash/high par tâche, relecture principal, navigator Sonnet 5.5/medium sur les tâches UI, push par tâche, revue advisor Opus 5.5/medium par lot) : rien de bloquant ni majeur aux revues des lots A, B, C ; mineurs corrigés et poussés.
- [decision] **4.2 : rien à exporter.** Les rapports JSON CI (`scripts/ci/verifier.py`) n'exportent aucune observation système ; liste blanche rendue explicite et fail-closed (`CHAMPS_*`, `verifier_rapport` avant écriture, noms validés) sans élargir les exports. Si 4.4 doit publier des agrégats système : élargissement explicite et testé, et **rappeler** que le fail-closed ne contrôle pas les sous-dictionnaires (`reglages_effectifs`/`versions`/`timings_natifs`/`fichiers` passent en bloc, surface préexistante).
- [decision] Objets D3 (version 1, `psutil-cpu-percent-nonbloquant-v1`, provenance `reelle`/`simulee`, motifs `lecture_impossible`/`intervalle_trop_court`/`valeur_incoherente` ; états de lecture `absent`/`invalide`/`version_inconnue` jamais écrits) : collectés aux frontières du runner (fenêtre CPU hors décodage/chargement), persistés `run.json.mesures.observation_systeme_chargement` / `result.json.mesures.observation_systeme`, validation stricte côté runner et consignation (tout objet invalide écarté, journalisé, jamais persisté, transcription intacte). Scénario simulé déterministe `simulee` pour le moteur factice (jamais de collecte réelle en factice) ; date de scénario jamais présentée comme réelle.
- [limit] Preuves : 1251 tests locaux (Linux Debian 11, Python 3.12.15, uv 0.13.5, psutil 7.2.2) ; Windows **par la CI factice uniquement** (win22 20261101.353.1, Python 3.12.10, uv 0.11.8) — aucune mesure ne qualifie le PC utilisateur ; sonde psutil = deux appels même thread sans seuil de performance (l'assertion `get_ident` est quasi tautologique, la garantie est structurelle). Flau élargi : `test_moteurs.test_arret_pendant_le_demarrage_ne_laisse_pas_de_processus` (run 42429614073, Windows, timing d'arrêt) en plus de la famille arrêt/interruption connue — jamais présenter un rerun vert comme preuve. Sans-JS strict non simulé (constat `<details>` sans `open`).
- [next] Pour reprendre : lot D sur **accord explicite** (4.3 runner réel PC Linux déclaré + lot annoncé ; 4.4 job Windows moteur autorisé, avec rappel du mineur 3 ci-dessus ; 4.5 observation navigator bureau/mobile clair/sombre + hiérarchie `<h3>` et poids visuel des valeurs système reportés du lot B, + `openspec validate --strict` et clôture). Ensuite archivage/synchronisation sur demande dédiée.

## Relations

- relates_to [[Reprise transcription-bench — méthode d'orchestration et état après la refonte résultats, 2026-11-07]]
- relates_to [[Lecture grand public et occupation des ressources — cadrage 2026-11-04]]
