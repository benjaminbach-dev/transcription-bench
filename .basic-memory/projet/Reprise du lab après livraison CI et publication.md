---
title: Reprise du lab après livraison CI et publication
type: note
permalink: transcription-bench/projet/reprise-du-lab-apres-livraison-ci-et-publication
tags:
- reprise
- lab
- ci
- livraison
- relecture
---

# Reprise du lab après livraison CI et publication

Note de synthèse pour la reprise, rédigée en fin de session autonome du
2026-11-02 sur le serveur de développement lab (clone
`~/repos/github/transcription-bench`, branche `main`, remote
`benjaminbach-dev/transcription-bench`, désormais **public**).

## État au dernier push

- [status] OpenSpec `add-benchmark-prototype` : **54/55 tâches**. Un seul point
  ouvert : 8.2, seconde architecture GGUF de transcribe.cpp (Qwen3-ASR ou
  Parakeet), en attente de l'arbitrage utilisateur — modèle précis à qualifier
  sur le PC de test, ou report explicite du périmètre. L'adaptateur
  transcribe.cpp et GGUF Whisper sont écrits, versionnés et vérifiés ; la CI
  Windows l'a re-confirmé.
- [status] Dernier commit poussé : `cec2905` (10.9 cochée). Historique de la
  session : `4905a9b` (gate), `c309448` → `d9ee207` (portabilité Windows),
  `1e05d69`, `e5927d8` (imports 10.5), `ab92616` (specs 11.6), `930d900` →
  `3982ec0` (8.4, preuves), `d0f93f0` (rapport de livraison, 11.5/11.7),
  `0235e00`, `cec2905`. Le run de tests de chaque push est vert.
- [status] Publication : dépôt passé public le 2026-11-02 par décision de
  l'utilisateur (exposition assumée, historique complet) — voir
  [[Décisions de publication 2026-11-02]].
- [status] CI Windows : six runs en succès (tests factices 698×2, imports des
  trois moteurs, quatre inférences courtes) — voir [[Validations CI 2026-11-02]]
  et `docs/ci-windows.md`. Rapports locaux sous `data/ci/rapports/`, hors Git.
- [status] Livraison déclarée **partielle** dans `docs/rapport-livraison.md` :
  critères 11.1–11.6 satisfaits, 8.2 en reliquat, aucune présentation de
  livraison partielle comme complète.
- [fact] `gh` est installé et authentifié sur le lab (accord utilisateur) ;
  le lab lui-même reste **sans moteur réel ni poids** : toutes les
  installations et inférences ont eu lieu sur les runners éphémères GitHub.

## Inviter à la relecture des interventions autonomes

- [process] La session du 2026-11-02 après-midi a été menée en autonomie
  (« avance progressivement », commits/pushs réguliers autorisés). Une
  **relecture utilisateur** est invitée avant de considérer ces acquis comme
  définitifs, en particulier :
  - les **corrections de portabilité** et l'unique changement produit
    (`transcription_bench/stockage.py` : réessai de `os.replace` sur
    `PermissionError` sous Windows), commit `c309448` ;
  - les **cases cochées sur jugement** : 8.4 et 11.4 (renvois et preuves PC
    préexistantes jugées suffisantes), 10.4 (artefacts du job `parole`), 11.5
    et 11.7 (rapport rédigé par l'agent) — à confronter aux exigences
    OpenSpec ;
  - la **scission des exigences** `platform-verification` (commit `ab92616`,
    validation stricte, sans changement de fond revendiqué — à vérifier) ;
  - l'application du **contexte CI dans `AGENTS.md`/README** (`c3f48ca`,
    relue et rechargée avant les jobs moteurs, conformément à 10.9) ;
  - les **écritures mémoire** de la session (cette note comprise).
- [process] Ordre de relecture suggéré : `git log 4905a9b..cec2905` ; le
  tableau des runs dans `docs/ci-windows.md` ; `docs/rapport-livraison.md` ;
  les cases de `tasks.md` citées ci-dessus.

## Prochaines étapes possibles

1. Relecture utilisateur des interventions ci-dessus ; corrections ou
   décochage si un jugement est contesté.
2. Arbitrage 8.2 : choisir modèle GGUF de seconde architecture + qualification
   sur le PC de test Linux (annoncer moteurs, modèles, volumes), ou consigner
   un report explicite du périmètre — puis clôture du change (archivage
   OpenSpec) sur demande.
3. Au retour sur le PC : synchroniser (fetch/pull après examen des changements
   locaux), relire cette note, éviter deux chantiers concurrents sur `main`.
4. Le lab reste le poste de développement sans moteur ; toute inférence ou
   installation réelle reste réservée au PC de test ou aux runners CI
   autorisés.

## Relations

- relates_to [[Décisions de publication 2026-11-02]]
- relates_to [[Validations CI 2026-11-02]]
- relates_to [[Décisions du prototype de benchmark]]
- replaces [[Reprise serveur lab après validation Linux]]