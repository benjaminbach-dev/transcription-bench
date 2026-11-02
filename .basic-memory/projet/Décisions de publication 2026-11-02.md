---
title: Décisions de publication 2026-11-02
type: note
permalink: transcription-bench/projet/decisions-de-publication-2026-11-02
tags:
- publication
- decisions
- audit
---

# Décisions de publication — 2026-11-02

## Décisions de l'utilisateur

- [decision] Publier le dépôt existant `benjaminbach-dev/transcription-bench` **tel quel**, historique complet, sans réécriture, sans candidat assaini, sans nouveau dépôt. Décision explicite de l'utilisateur le 2026-11-02 : il assume l'exposition des éléments personnels (identités d'auteur et adresses, machine et environnement, notes de travail versionnées).
- [decision] La sauvegarde privée et le candidat assaini sous `data/publication-privee/` (côté PC) deviennent sans objet pour la publication ; ils restent des archives locales privées. Règle inchangée : jamais de `push --mirror`, jamais de publication de la sauvegarde.
- [limit] Réserve signalée à l'utilisateur : le prénom de la tierce personne reste dans les anciennes versions Git des notes mémoire ; anonymisation de l'état courant maintenue, historique assumé. Décision prise en connaissance de cause.
- [decision] Gate de publication (tâche 10.2) levé par cet accord ; les jobs CI Windows cessent d'être conditionnés à des décisions d'audit manquantes. La CI publique reste soumise aux contraintes des tâches 10.3–10.6 (aucun poids/audio/transcription en artéfact, actions épinglées, image Windows versionnée).

## Contrôle secrets exécuté avant publication

- [validation] Scan de l'historique Git complet du clone lab le 2026-11-02 : 369 blobs atteignables, aucune correspondance aux formats GitHub/Hugging Face/AWS/Google/OpenAI, en-têtes de clés privées, ni URL avec identifiants intégrés. Aucun blob binaire, aucun blob > 1 Mo, aucun chemin `data/`, poids, audio ou fichier d'authentification dans l'historique. Les seules occurrences « secret » sont des chemins de fixtures de tests. Recherche heuristique locale, sans détecteur spécialisé : pas une garantie d'absence exhaustive.
- [fact] Le flip de visibilité n'a pu être exécuté depuis le lab : CLI `gh` absente sur ce serveur. Exécuté par le propriétaire côté GitHub ou après installation autorisée de `gh`.
- [validation] Visibilité constatée publique le 2026-11-02 via l'API GitHub anonyme (`private: false`, `visibility: public`, branche `main`). Changement effectué manuellement par le propriétaire ; dépôt publié tel quel, historique complet, conformément aux décisions ci-dessus. Tâche 10.2 cochée après constat.

## Statut des tâches OpenSpec

- [status] 10.1 audit de publication : decisions consignées dans cette note ; le rapport `docs/audits/publication-2026-11-02.md` reste la référence des constats. Le point « audit final du candidat » est clos par l'abandon de la voie du candidat.
- [status] 10.2 levée du gate : accord explicite obtenu le 2026-11-02 ; à cocher après le changement de visibilité effectif constaté.

## Relations

- relates_to [[Décisions du prototype de benchmark]]
- relates_to [[Reprise serveur lab après validation Linux]]