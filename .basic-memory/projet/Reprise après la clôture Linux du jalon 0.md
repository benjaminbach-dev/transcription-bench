---
title: Reprise après la clôture Linux du jalon 0
type: note
permalink: transcription-bench/projet/reprise-apres-la-cloture-linux-du-jalon-0
tags:
- reprise
- jalon0
- windows
- en-attente
---

> Cette ancienne reprise est remplacée par [[Reprise serveur lab après validation Linux]] pour le passage de relais du 2026-11-02. Les sections historiques ci-dessous ne décrivent pas le travail restant actuel.

> Point d'arrêt actualisé 2026-11-02 : parcours réel CLI/Waitress/HTTP Linux validé sur les quatre combinaisons, comparaison, refus409, arrêts réels et redémarrage sans réécriture des résultats. Timings transcribe.cpp ajoutés et vérifiés jusqu'au JSON/HTML en1appel natif et2fenêtres. Suite complète698testsOK ; voir docs/validation-linux.md et preuve sous data/feasibility/parcours-http/20261102-141608/. OpenSpec38/55, seul reliquat8.2 = seconde architectureGGUF. Aucun job Windows, commit ou publication ; instructionsCI encore proposées, pas appliquées.

> Reprise après implémentation du 2026-11-02 : quatre parcours réels courts Linux réussis, 680 tests OK, OpenSpec38/55. CI et licence MIT préparées, sauvegarde et base historique assainie dans une copie privée séparée. Aucun job Windows ni publication. AGENTS.md inchangé : proposition CI à relire dans docs/proposition-contexte-ci.md. Points d'arrêt : voie de publication propre (nouveau dépôt indépendant ou purge coordonnée), revue des instructions, audit final et décisions8.2. Voir la dernière section de [[Décisions du prototype de benchmark]].

> Actualisation 2026-11-02 : la priorité Windows sur PC décrite ci-dessous est remplacée par la décision de livraison via CI Windows sur dépôt public après audit. Aucun PC Windows ne sera disponible ; voir la section « Livraison Windows par CI publique » de [[Décisions du prototype de benchmark]]. Révision OpenSpec et audit en cours, aucune CI exécutée ni publication effectuée.

# Reprise après la clôture Linux du jalon 0

> Point d'arrêt du 2026-11-01, après les lots « Transformers jalon 0 » et « Clôture Linux du jalon 0 ». Remplace implicitement le point d'arrêt porté jusqu'ici par les sections « reprise » des notes de validation.

## État au point d'arrêt
- Publié sur `origin/main` : commit **3e53a8c** (lot Transformers : index résolu, modèles téléchargés, essais CPU, hors ligne, 1.2 cochée) puis commit **37bc10b** (coupures OS des trois moteurs, durées natives 5 min, 1.8 partielle design/tasks, corrections de code `generation_config`/`--no-build`). OpenSpec `add-benchmark-prototype` : **26/39**, `openspec validate --strict` OK, 632 tests OK.
- Contexte machine : sessions sur le PC de test Linux (Manjaro, Ryzen 7 PRO 6850U, 30 Gio RAM, uv 0.11.8). Ne pas le présumer d'une future session : faire confirmer avant toute opération réservée à un PC de test.
- Environnements et modèles présents sous `data/` (hors Git) : moteurs faster-whisper, transcribe-cpp, transformers (avec librosa) ; modèles dropbox-dash CT2, handy-computer GGUF Q5_K_M, openai/whisper-large-v3-turbo, nvidia/parakeet-tdt-0.6b-v3 ; audios FR synthétiques court, long (47,7 s) et 5 min ; verrou de référence `data/feasibility/transformers/transformers-librosa.txt` (auto-porté par `--find-links`). Cache-uv et artefacts d'essai déjà nettoyés.

## Décisions tranchées le 2026-11-01
- 1.1 et 3.2 **cochées** (28/39) sur décision utilisateur : accords Linux consignés et liste des modèles d'essai arrêtée ; hook testé et sonde Linux 413 vérifiée. L'installation Windows gardera son propre accord de lot.
- 1.6 et 1.8 restent ouvertes (volets Windows), conformément à l'avis advisor.

## Prochaine priorité — volet Windows (PC du collègue)
- Ordre proposé : préparer une note « mode opératoire Windows » (raccourcit la session sur place : installation depuis les verrous avec `--no-build` face aux roues Windows, 1.3/1.4/1.5, coupure réseau OS à définir sous Windows — pas d'unshare : désactivation réseau ou règle pare-feu avec droits admin — volets Windows de 1.6/1.7), puis exécuter sur place, puis clôture de 1.8, puis adaptateurs 8.x.
- Aucune validation Windows existante : le dry-run `--python-platform windows` ne vaut rien.
- Windows et le jalon 0 complet restent préalables au lot 8 ; ne pas lancer d'adaptateur réel sur la seule lecture de cette note.

## Méthode et frontières (inchangées)
- Workers bornés une par une avec arrêt pour contrôle ; principal seul décideur et seul écrivain Basic Memory via MCP ; advisor sur demande/mandat, lecture seule ; revue advisor de lot puis corrections avant commit.
- Aucun commit/push sans demande explicite ; vérifier identité, remote, branche et fichiers concernés. Aucun curl ni sudo ; arrêt et remontée au refus, aucun contournement.
- Mesures : un seul passage, voix synthétiques, non représentatives ; aucune transcription présentable comme médicalement correcte.
- Lire d'abord [[Décisions du prototype de benchmark]], puis [[Faisabilité Transformers Linux du jalon 0 — téléchargements, essais et hors ligne]] et [[Clôture Linux du jalon 0 — coupures OS, durées natives et ajustements 1.8]] ; vérifier l'état Git et les versions réelles avant toute reprise.

## Relations
- relates_to [[Clôture Linux du jalon 0 — coupures OS, durées natives et ajustements 1.8]]
- relates_to [[Faisabilité Transformers Linux du jalon 0 — téléchargements, essais et hors ligne]]
- relates_to [[Décisions du prototype de benchmark]]