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


## Observation navigator et corrections du bloc contexte — 2026-11-11

- [validation] Observation clair, bureau 1280 et mobile 390, sur copie isolée en /tmp avec moteur factice (mesures simulées) : liste, détail et comparaison. Constats corrigés : libellés `<summary>` distincts (« Valeurs brutes et méthode — après l'audio / après le chargement du modèle »), intertitre « Après chargement du modèle » ajouté à la comparaison (h4), h2 « Relevés système de cette exécution » rattachant les h3 du détail, titres du bloc réduits (`resultat-contexte-titre`), valeurs système plus discrètes (`resultat-valeur-systeme`, 1 rem contre 1,25 rem). Suite complète 1433 tests OK ; OpenSpec strict 9/9.
- [decision] Acceptés comme préexistants/conformes aux specs : tableau « Toutes les mesures » défilant dans son conteneur, coupure de « Moteur factice (développement) » par overflow-wrap, bouton « Comparer » sans état inactif (formulaire sans JS).
- [limit] **4.5 reste ouverte** : thème sombre non observable (outils Playwright sans émulation de prefers-color-scheme), sans-JS strict non simulé, largeur 360 px non contrôlée, aucune donnée réelle. Le h2 du bloc contexte et les h3 ont des tailles proches ; répétitions mineures de « Scénario simulé ». Décision du propriétaire attendue pour clore sans observation sombre (précédent refondre-parcours-resultats 1.5/6.1). 4.3/4.4 toujours sur accord PC/CI.
