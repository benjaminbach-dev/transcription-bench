---
title: Reprise du jalon 0 après préparation Transformers CPU
type: note
permalink: transcription-bench/projet/reprise-du-jalon-0-apres-preparation-transformers-cpu
date: '2026-11-01'
status: remplacée — lot exécuté et consigné le 2026-11-01, voir la note de remplacement
base_publiee: 79ed1d4f61cc429ef248b6741244befcc47b5998
tags:
- reprise
- transformers
- jalon0
- linux
---

# Reprise du jalon 0 après préparation Transformers CPU

> Remplacée le 2026-11-01 : le lot prévu ici a été exécuté et consigné dans [[Faisabilité Transformers Linux du jalon 0 — téléchargements, essais et hors ligne]]. Cette note ne reflète plus l'état courant (modèles non téléchargés, point d'index ouvert, 1.2 non terminée : obsolètes). La méthode et les frontières qu'elle décrit restent d'actualité.

## Point d'arrêt demandé
L'utilisateur a demandé de s'arrêter après la première tâche Transformers, puis de faire commit/push et enfin cette note de reprise. Le constat a été publié sur origin/main au commit **79ed1d4f61cc429ef248b6741244befcc47b5998** (`Consigner la préparation Transformers CPU et le point ouvert d’index`). Cette note est créée APRÈS ce push : elle n'est volontairement pas incluse dans ce commit. Ne pas la supprimer ni la publier automatiquement sans respecter la demande Git applicable à la reprise.

## Lire et vérifier
- Lire [[Décisions du prototype de benchmark]], puis [[Préparation Linux de Transformers et PyTorch CPU]]. Les exigences restent dans OpenSpec ; `add-benchmark-prototype` est actif, **25/39 tâches cochées**, aucune spec ni code produit modifié pendant la première tâche Transformers.
- Le contexte de cette session était explicitement PC de test Linux (Manjaro, Ryzen6850U, CPython géré3.12.13, uv0.11.8). Ne pas déduire le contexte d'une future session de son OS ou chemin : faire confirmer si nécessaire avant opérations réservées à un PC de test.
- Vérifier Git, les fichiers locaux et les versions réelles avant toute reprise ; les poids/environnements/preuves sous data ne voyagent pas avec Git. Le projet Basic Memory transcription-bench doit pointer vers .basic-memory de ce clone.

## Ce qui est réellement fait
- Worker borné : candidat universel sous `data/feasibility/transformers/transformers.in` et `.txt`, environnement `data/engines/transformers/` installé et contrôlé.
- Pins : Transformers5.20.2, torch2.14.1+cpu, numpy2.5.4, psutil7.2.2. **37 pins universels, 35 paquets installés sur Linux**. CPU vérifié (torch.version.cuda=None, is_available=False, get_num_threads=8, tenseurCPU) ; classes Whisper et Parakeet TDT importables.
- Aucun modèle Transformers téléchargé, aucun from_pretrained, aucune inférence. data/models ne contient encore que faster-whisper et transcribe-cpp. Les deux WAV FR synthétiques réutilisables sont sous `data/feasibility/faster-whisper/` ; espeak-ng et ses deux dépendances ont été retirés et leur absence vérifiée dans le lot précédent.
- Advisor a relu les preuves en lecture seule : préparation CPU favorable avec réserves. Principal a corrigé les comptes37/35, unitésMio/Mo, interprétation de l'estimation incomplète et provenance des échecs. Constat détaillé et limites sont dans la note bench publiée.

## Prochaine priorité — avant les poids
**Point ouvert à résoudre : l'index PyTorch CPU n'est pas transporté par le verrou candidat seul.**

Commande qui a réussi sous uv0.11.8 :
`uv pip sync --no-build --torch-backend cpu --python data/engines/transformers/bin/python data/feasibility/transformers/transformers.txt`

- La compilation utilisait `--universal --python-version 3.12 --no-build --emit-index-url --torch-backend cpu`, mais le .txt ne conserve que `--index-url https://pypi.org/simple`.
- Le worker rapporte un dry-run sans `--torch-backend cpu` en échec pour torch+cpu introuvable. Le journal de cet échec précis n'a pas été conservé ; il est cité comme témoignage, pas comme log brut. Le dry-run verbeux AVEC backend CPU, lui, archive l'index CPU et la roue choisie.
- `transformers-variante-extra-index.txt` émet l'indexCPU et réussit au dry-run, mais change vers des versions plus anciennes plusieurs paquets sans rapport ; variante non retenue ni installée. Ne pas la promouvoir sans analyse.
- **Ne pas déclarer la tâche OpenSpec1.2 terminée ni l'installation service prête.** Déterminer un transport reproductible compatible avec les specs existantes ; aucune solution de code ou d'index n'est encore approuvée. Ne pas modifier les specs pour contourner le point.
- Script exploratoire tailles-roues.py : HTTP403 de cause/URL non déterminées, pas un refus de politique. Ne pas rejouer des URLs pour le contourner. Taille torch connue au téléchargement187,2Mio ; total estimé210–225Mio, environnement920M selondu (~965Mo), pas un comptage réseau exact.

Après résolution et nouvelle instruction de poursuite : téléchargement explicite à révision figée de openai/whisper-large-v3-turbo puis nvidia/parakeet-tdt-0.6b-v3, liste blanche safetensors, essais CPU court/long et vraie coupure réseau à compléter. Ces opérations n'ont PAS été exécutées dans cette première tâche ; ne pas les lancer sur la seule lecture de cette note. Windows et le jalon0 global restent préalables au lot8.

## Méthode et frontières
- Respecter les specs : l'utilisateur a explicitement refusé de les modifier pour accélérer. Aucun adaptateur réel, marqueur prêt ni requirements versionné avant le jalon prévu.
- Principal autonome et décideur ; workers à tâches strictement bornées avec arrêt pour contrôle, jamais autonomes sur le choix de la suite. Advisor uniquement dans le mandat demandé, lecture seule. Principal seul écrivain Basic Memory via MCP.
- Au refus de politique : arrêter, remonter, aucun changement d'outil/chemin pour refaire l'action refusée. Curl/sudo ont été refusés aux workers précédemment ; ne pas les retenter ni demander d'élévation interactive. Les commandes shell complexes ont causé des attentes : préférer scripts locaux et invocations simples.
- À cette pause, les tâches locales de téléchargement/modèles/inférences Transformers restent non commencées ; le point d'index demeure ouvert malgré l'installation CPU locale réussie.

## Relations
- relates_to [[Préparation Linux de Transformers et PyTorch CPU]]
- relates_to [[Décisions du prototype de benchmark]]
