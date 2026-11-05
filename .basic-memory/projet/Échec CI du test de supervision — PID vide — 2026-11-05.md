---
title: Échec CI du test de supervision — PID vide — 2026-11-05
type: note
permalink: transcription-bench/projet/echec-ci-du-test-de-supervision-pid-vide-2026-11-05
tags:
- ci
- supervision
- incident
---

# Échec CI du test de supervision — PID vide — 2026-11-05

Constat effectué par le principal avec `gh run list` et `gh run view --log-failed`, après signalement utilisateur d'un courriel GitHub. Incident observé pendant la livraison du lot 2 de `simplifier-lecture-resultats` ; aucune correction de supervision réalisée dans ce lot.

## Observations

- [validation] Le run [41977560241](https://github.com/benjaminbach-dev/transcription-bench/actions/runs/41977560241), commit `a0d7308854fb68bc7ed2be6ac7f40d77e17fe743` (tâche 2.1), échoue dans le job Ubuntu 24.04 : 813 tests exécutés, une erreur.
- [fact] Le test concerné est `tests.test_supervision.MoteurReelArreteTest.test_arret_termine_le_moteur_et_son_descendant`. La trace passe par `_scenario_arret` (ligne 883 sur ce commit), puis `lire_pid` (ligne 242) : `int(chemin.read_text(encoding="utf-8").strip())` lit une chaîne vide depuis `moteur.pid`, produisant `ValueError: invalid literal for int() with base 10: ''`.
- [hypothesis] Une course entre création, écriture et lecture du fichier PID est plausible. Cette cause n'a pas été confirmée par investigation ou reproduction ciblée ; ne pas présenter l'incident comme un simple aléa résolu.
- [validation] Le run suivant [41979186077](https://github.com/benjaminbach-dev/transcription-bench/actions/runs/41979186077), commit `939af28315ed62055b85fa6cf30887c62fe0e276` (tâche 2.2), réussit sur Ubuntu 24.04 et Windows 2022. Ce succès ne prouve pas la correction de l'échec précédent.
- [status] Incident à investiguer ; aucun correctif de ce test, aucune relance CI manuelle et aucun changement de supervision effectué pour le traiter dans cette session.
- [lesson] Le principal avait vérifié les tests locaux et les push, mais pas les résultats GitHub Actions avant d'annoncer la clôture du lot. Vérifier les runs associés à chaque commit poussé avec `gh` et signaler les échecs avant de conclure ; distinguer validation locale et CI.

## Relations

- relates_to [[Lecture grand public et occupation des ressources — cadrage 2026-11-04]]
- relates_to [[Validations CI 2026-11-02]]