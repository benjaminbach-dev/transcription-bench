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

- [status] OpenSpec `add-benchmark-prototype` : **53/55 tâches**. Deux points liés restent ouverts : 8.2 (seconde architecture GGUF de transcribe.cpp, Qwen3-ASR ou Parakeet, en attente d'arbitrage utilisateur — qualification sur le PC de test ou report explicite) et 11.4 (décochée après revue advisor tant que 8.2 n'est pas tranché). L'adaptateur transcribe.cpp et GGUF Whisper sont écrits, versionnés et vérifiés ; la CI Windows l'a re-confirmé.
- [status] Dernier commit poussé : les corrections issues de la revue advisor du 2026-11-02 soir (commits exacts des runs, artéfacts manquants, roues, conclusion d'audit, README, 11.4 décochée, écart 10.9 consigné, encodage autonome des tests, tests du réessai atomique — suite locale 701 tests OK). Historique de la session : `4905a9b` (gate), `c309448` → `d9ee207` (portabilité Windows), `1e05d69`, `e5927d8` (imports 10.5), `ab92616` (specs 11.6), `930d900` → `3982ec0` (8.4, preuves), `d0f93f0` (rapport de livraison), `0235e00`, `cec2905`, `4a5c1e6`, puis les correctifs de revue. Le dernier run de tests est vert ; les runs intermédiaires de correction ont échoué sous Windows avant de converger (voir [[Validations CI 2026-11-02]]).
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
  **revue advisor indépendante** (gpt-6.1-sol, medium, demandée par le
  propriétaire) a eu lieu le soir même : verdict « succès CI réels, acquis à
  ne pas accepter intégralement en l'état », avec corrections appliquées
  ensuite (voir [[Validations CI 2026-11-02]]). Restent **à arbitrer par le
  propriétaire** :
  - l'**écart de procédure 10.9** : instructions CI rechargées avant les jobs
    moteurs mais après les premiers runs de tests (16 h 48 vs 16 h 04/16 h 31) ;
  - le sort de **8.2/11.4** (seconde architecture GGUF : qualification sur PC
    ou report explicite).
  Les points suivants restent aussi invités à une relecture humaine : les
  corrections de portabilité et l'unique changement produit
  (`transcription_bench/stockage.py`), la scission des exigences, les cases
  cochées sur jugement (8.4, 10.4, 10.5, 10.7, 10.9, 11.5–11.7) et les écritures
  mémoire de la session (cette note comprise).

## Prochaines étapes possibles

1. Relecture utilisateur des interventions ci-dessus ; corrections ou
   décochage si un jugement est contesté.
2. Arbitrages utilisateur en attente : 8.2/11.4 (modèle GGUF de seconde
   architecture + qualification sur le PC de test Linux, ou report explicite)
   et l'écart de procédure 10.9 (runs de tests antérieurs à l'application du
   contexte CI) ; puis clôture du change (archivage OpenSpec) sur demande.
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