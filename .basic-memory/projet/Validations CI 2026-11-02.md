---
title: Validations CI 2026-11-02
type: note
permalink: transcription-bench/projet/validations-ci-2026-11-02
tags:
- ci
- windows
- validation
- portabilite
---

# Validations CI GitHub Actions — 2026-11-02

## Premier passage CI Windows et correction de portabilité

- [validation] Suite complète (698 tests) **réussie sous Linux (`ubuntu-24.04`) et Windows (`windows-2022`)** : run GitHub Actions `41472430238` sur le commit `d9ee207`, workflow « Tests Linux et Windows », déclenché par push sur `main` public. Le moteur factice seul est en jeu : aucun poids, aucun moteur réel, audio synthétique local, aucun artéfact de transcription.
- [implementation] Itérations depuis le lab sur `main` public : `4905a9b` (gate levé, 10.1/10.2) → `c309448` (portabilité Windows des tests, réessai du remplacement atomique) → `13249ae` (suppression CON via préfixe étendu, SIGKILL absent sous Windows, cache numba par chemin) → `d9ee207` (code de sortie Windows 15 d'un `os.kill`). Runs intermédiaires : `41467927122` (Windows 20 échecs), `41470878043` (4), `41471769788` (2).
- [implementation] Corrections de portabilité : encodage UTF-8 explicite des sorties de sous-processus dans les tests (cp1252 par défaut sous Windows) ; chemins temporaires résolus (8.3 `RUNNER~1` vs `runneradmin`) ; `resource` réservé à Linux ; `CON.wav` créé et supprimé par préfixe `\\?\` pour exercer le refus de nom réservé ; PID du trampoline uv (parent de l'interpréteur réel) accepté sous Windows ; codes de sortie d'arrêt Windows (15 = `os.kill` sans signal, 1 = TerminateProcess) ; attendu d'échappement web calculé depuis le chemin joint.
- [implementation] Produit : `os.replace` du stockage atomique retenté jusqu'à 20 fois (10 ms) sur `PermissionError` — un lecteur Windows peut détenir le fichier un instant ; les lectures sondées des tests tolèrent la même contention. C'est la « protection des lectures/écritures sous Windows » de 10.3.
- [limit] Diagnostics par journaux collés par le propriétaire (pas de `gh` ni jeton sur le lab à ce stade ; accord pour installer `gh` plus tard). Journal complet observable sur GitHub, dépôt public.
- [status] OpenSpec : 10.3 et 11.1 cochées. Restent 10.4–10.9 (jobs moteurs manuels, preuves, AGENTS.md/README) et 8.2 (PC), 8.4 (renvois).

## Jobs moteurs (10.5) — 2026-11-02, après relecture du contexte CI

- [validation] Contexte CI appliqué dans `AGENTS.md` et README (tâche 10.9) après relecture utilisateur et `/reload` ; commit `c3f48ca`. Le lab reste sans moteur ni poids ; les opérations concernent les runners GitHub uniquement.
- [validation] Job « imports » du workflow « Moteurs Windows (manuel) » : run `41477235301` sur le commit `c3f48ca` de `main` public, déclenché manuellement via `gh` (compte propriétaire). Les trois moteurs (faster-whisper, transcribe.cpp, Transformers) installés depuis leurs verrous sous `windows-2022`, déclarés prêts, runner factice exécuté dans chaque venv moteur et adaptateur réel importé dans le même interpréteur. Conclusion : **success** pour les trois jobs ; `parole` et `inference` ignorés conformément à `combinaison=aucune`. Tâches 10.5 et 11.2 cochées. Roues arrêtées par `uv.lock` versionné ; téléchargements relevés dans le journal du run.
- [validation] Quatre inférences courtes réussies sous Windows CI (`windows-2022`, image `20261026.347.1`, Python 3.12.10, uv 0.11.8) sur parole synthétique créée dans le job (voix `Microsoft David Desktop`, culture `en-US`, texte `en`, langue imposée `fr` sauf Parakeet sans langue forcée, empreinte SHA-256 vérifiée) : faster-whisper run `41478535615`, transcribe.cpp GGUF Whisper run `41479081739` (timings natifs conservés), Transformers Whisper run `41480184141`, Transformers Parakeet TDT run `41480997693`. Transcriptions non vides à chaque fois (contrôle technique, sans évaluation des modèles). Rapports JSON recopiés sous `data/ci/rapports/` du lab, hors Git.
- [validation] OpenSpec strict levé le 2026-11-02 : exigences `platform-verification` scindées sans changement de fond (commit `ab92616`) ; `openspec validate --strict` sans erreur.
- [status] État du change consigné dans `docs/rapport-livraison.md` : **partiel** — 8.2 (seconde architecture GGUF transcribe.cpp : arbitrage utilisateur modèle/téléchargement sur PC ou report explicite) et 11.4 (décochée : la coche « adaptateurs 8.1 à 8.3 » était prématurée tant que 8.2 n'est pas qualifié ou reporté) restent ouvertes ; 53/55.
- [validation] Revue advisor indépendante (gpt-6.1-sol, medium, demandée par le propriétaire) le 2026-11-02 soir : verdict « succès CI réels, acquis à ne pas accepter intégralement en l'état ». Corrections appliquées ensuite : commits réels des runs corrigés dans la documentation (`41477235301`→`c3f48ca`, `41479081739`→`ab92616`, `41480997693`→`3982ec0`) ; artéfacts des runs tests et imports récupérés sous `data/ci/rapports/` ; roues consignées (`uv.lock` + journal) ; conclusion d'audit ajoutée à `docs/audits/publication-2026-11-02.md` (contrôles exécutés / risques assumés / contrôles non exécutés) ; README précisé (moteurs CI = Windows uniquement, essais vierges et limites reformulés) ; 11.4 décochée ; lien licences des modèles CI restauré dans l'exigence d'audit préalable ; encodage UTF-8 rendu autonome dans les tests (env `PYTHONIOENCODING`, plus de dépendance à la variable du workflow) ; trois tests déterministes du réessai atomique ajoutés (`tests/test_stockage.py`, suite 701 OK).
- [limit] Écart de procédure consigné, à arbitrer par le propriétaire (10.9) : le contexte CI a été relu et rechargé à 16 h 48 (`c3f48ca`), avant les jobs moteurs, mais après les premiers runs de tests (16 h 04 sur `4905a9b`, 16 h 31 sur `d9ee207`). La valeur technique des tests n'est pas contestée ; le préalable chronologique de 10.9 ne peut pas être satisfait rétroactivement.
- [fact] `gh` installé et authentifié sur le lab après accord utilisateur : déclenchement des jobs et lecture des journaux possibles sans copier-coller. Le jeton reste dans le magasin du client, jamais affiché ni journalisé.

## Conditions

- [fact] Jobs conditionnés au dépôt public (`github.event.repository.private == false`) : levés par le passage en public du 2026-11-02. Avant, un run privé (`41461687022`) s'était terminé « skipped ».
- [fact] La suite locale du lab reste 698 tests OK sous Linux à chaque itération (validation proportionnelle, moteur factice uniquement).

## Relations

- relates_to [[Décisions de publication 2026-11-02]]
- relates_to [[Reprise du lab après livraison CI et publication]]