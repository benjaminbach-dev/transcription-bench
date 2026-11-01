---
title: Clôture Linux du jalon 0 — coupures OS, durées natives et ajustements 1.8
type: note
permalink: transcription-bench/bench/cloture-linux-du-jalon-0-coupures-os-durees-natives-et-ajustements-1.8
tags:
- validation
- linux
- jalon0
- hors-ligne
- durées-natives
- '1.8'
---

# Clôture Linux du jalon 0 — coupures OS, durées natives et ajustements 1.8

## Contexte
Lots 1–3 exécutés le 2026-11-01 sur le PC de test Linux déclaré (Manjaro, Ryzen 7 PRO 6850U, 8 threads, 30 Gio RAM, uv 0.11.8), à la suite de [[Faisabilité Transformers Linux du jalon 0 — téléchargements, essais et hors ligne]]. Séquencement dicté par un avis d'orientation advisor : fin de la partie Linux de 1.6, puis 1.8 partielle (documentation), puis corrections de code ciblées. Workers bornés une par une, contrôle principal, revue advisor finale ; corrections appliquées avant commit. Méthode et frontières inchangées (voir les notes de reprise précédentes) : principal seul écrivain mémoire, aucun curl/sudo, arrêt au refus.

## Lot 1 — coupure réseau OS des trois moteurs et durées natives
- [validation] La sonde web 1.7 sous Linux avait DÉJÀ été faite le 2026-11-01 (constat de l'advisor d'orientation : `data/feasibility/preuves-sonde-1.7.json`, 8 scénarios concluants sur le code actuel) et le code 6.6 était déjà livré (commit 4007d17) : aucune des deux à refaire ; seul le volet Windows reste.
- [validation] **faster-whisper** sous `unshare -rn` (namespace vide : 0 route, `lo` seul, TCP/UDP/DNS en OSError 101/gaierror, 0 tentative réseau observée, HF_HOME vierge resté vide) : chargement 3,037 s, court 10,673 s → 6,186 s (RTF 0,580), long 47,704 s → 13,193 s (RTF 0,277), pic RSS 1658 Mio, int8_float32, long-form 6 segments dernier à 47,1 s. **Textes et horodatages identiques au lot hors coupure** (identité recalculée par l'advisor contre `preuves-transcription-fr.json`, non enregistrée dans le JSON de preuve — provenance consignée ici). Bruit inter-lots ~±9 % sur un passage.
- [validation] **transcribe.cpp** sous `unshare -rn` : chargement 0,086 s (mmap, pages chargées à la demande — non comparable aux autres moteurs), court 9,929 s (RTF 0,930), long 17,338 s (RTF 0,364), pic RSS 778 Mio, backend relu « CPU » (normalisé cpu, D6), mmap observé (589,1 Mio CPU_Mapped). Textes strictement identiques au lot de référence (entrées .f32 sha256 recoupés). API 0.4.1 : PCM f32 mono 16 kHz uniquement, pas de chemin WAV. Piège documenté : `/proc/1` illisible en userns ; le champ `inode_netns_hote` de la preuve est erroné (`stat` sans `-L`) — la preuve réelle de distinction hôte/namespace est le relevé `--hote` du journal (4026531833 ≠ 4026533018) ; un même numéro d'inode peut être réutilisé par le noyau entre essais.
- [measurement] **Audio 5 min** (300,885 s, construit par concaténation locale 5× long + 5× court + 1 s de silence, sha256 consignés, décodé 300,884813 s), un processus par modèle sous `unshare -rn` (+ garde Python bloquante dans cet essai, contrairement aux deux précédents), plafond RSS 12 Gio fixé par le principal avec kill automatique, non déclenché :
  - Parakeet natif une passe : 55,89 s (RTF 0,186), pic RSS 4915 Mio dont ~1041 Mio au chargement (la mémoire croît avec la durée), dernier horodatage 99,92 %, arrêt par épuisement d'encodeur (max_length générique non atteint).
  - Whisper long-form natif : 148,54 s (RTF 0,494 — proche du 0,515 à 47,7 s), pic RSS 5112 Mio atteint DÈS LE CHARGEMENT (RSS échantillonné ~3787 Mio pendant la transcription), 51 segments, 99,83 %.
  - 10/10 blocs couverts, aucune boucle (aucun 6-gramme répété), mais couverture ≠ fidélité : « court enregistrement » retrouvé 0/5 par les deux modèles, « commence ici » 4/5 pour Parakeet.
  - RTF Parakeet : trois points non monotones (0,115 / 0,102 / 0,186), à ne pas extrapoler au-delà de 300,9 s ; explication probable (attention non fenêtrée) lue dans le code, pas mesurée.
- [limit] Un seul passage par mesure, un seul PC Linux, voix synthétiques espeak-ng, aucun WER : contrôles de fonctionnement, pas un benchmark ; réglages de décodage différents entre moteurs (faster-whisper beam 5, Transformers glouton) : aucun classement. Coupure IP seulement (TCP/UDP/DNS) ; `unshare` n'existe que sous Linux.

## Lot 2 — 1.8 partielle (documentation)
- [decision] design.md ajusté : D4 (`--no-build`, verrou Transformers auto-porté par `--find-links` sans hashes, librosa 1.0.0 obligatoire, `NUMBA_CACHE_DIR`), D9 (durée native maximale prouvée 5 min sur PC 30 Gio avec attribution correcte des pics RSS ; Whisper troncature silencieuse interdite + vérification des trames par l'adaptateur, axe dépendant de la famille ; Parakeet natif jusqu'à preuve, fenêtres au-delà, RTF non monotone), D10 (`generation_config.json` requis pour parakeet-tdt), D13 nouveau (contraintes adaptateur : dtype fp32 explicite — `dtype="auto"` par défaut chargerait Whisper en fp16 ; `do_normalize` à fixer ; `max_length` proportionnel aux trames, jamais troncant, atteinte détectée ; horodatages Parakeet = convention de lecture), risques (verrou sans hashes, huggingface_hub 2.3.0 serveur / 2.4.0 moteur, trois compilations du seul verrou Transformers, dépôt dropbox-dash validé fonctionnellement avec sha256 consigné, limite « Interface disponible », durée prouvée sur un seul PC). Context corrigé (essais Linux faits, Windows reste ; uv 0.11.8 réel vs 0.13.5 documentaire). tasks.md : dépôt GGUF nommé (`handy-computer/whisper-large-v3-turbo-gguf` Q5_K_M) en 1.1, Systran→dropbox-dash en 1.1/8.1, 8.3 renvoie à D13/NUMBA. **Aucune spec (dossier specs/) modifiée** : le scénario benchmark-runs couvre déjà la nouvelle version de D9.
- [status] 1.8 reste NON cochée : le volet Windows (sonde web, 1.3–1.5) devra y être intégré avant clôture.

## Lot 3 — corrections de code (développement serveur, 632 tests OK)
- [validation] `compatibilite_modeles.py` : `generation_config.json` requis pour parakeet-tdt (refus `fichiers-manquants` sans lui) + docstring ; nouveau test de refus. Le modèle Parakeet local contient le fichier et les règles ne s'appliquent qu'à la vérification avant téléchargement : aucun modèle présent ne régresse.
- [validation] `moteurs.py` : `--no-build` ajouté à `uv pip sync` du service + docstring précisée (refuse la compilation des sdists ; le code des roues installées reste exécuté — moteurs verrouillés pour cela) ; test de la commande par exécuteur enregistreur. Effet voulu et documenté : un moteur sans roue binaire devient ininstallable ; à vérifier en 1.3 sous Windows.
- [validation] Suite complète 632 tests OK (33 s) ; `openspec validate --strict` OK ; `git diff --check` propre.

## Revue advisor et corrections
Revue finale favorable sur les mesures et le code, avec corrections appliquées avant commit : attribution des pics RSS (Whisper au chargement, Parakeet à la passe), RTF non monotone et explication comme lecture de code, dtype D13 inversé (fp16 par défaut → fp32 à imposer), max_length = arrêt normal par épuisement d'encodeur, vérification des trames par l'adaptateur (axes distincts), uv 0.11.8, trois compilations du seul verrou Transformers, formulations prudentes ; champs erronés de preuves (`inode_netns_hote` sans `-L`, `trames_mel` Parakeet) exclus de la consignation. Champs non repris dans cette note.

## État et reprise
- [status] OpenSpec 26/39 inchangé après ces lots (1.6, 1.8 non cochées : volets Windows manquants). Fichiers prêts à committer : design.md, tasks.md, compatibilite_modeles.py, moteurs.py, deux fichiers de tests, cette note.
- [next] **Volet Windows sur le PC du collègue** : 1.3 (installation depuis les verrous — attention `--no-build` face aux roues Windows), 1.4, 1.5, volets Windows de 1.6 (coupure OS à définir sous Windows : pas d'unshare, désactivation réseau ou pare-feu avec droits admin) et 1.7, puis clôture de 1.8. Un mode opératoire Windows à préparer en note dédiée raccourcirait la session sur place. Décisions en attente utilisateur : cocher 1.1 (liste arrêtée : dropbox-dash, openai/whisper-large-v3-turbo, nvidia/parakeet-tdt-0.6b-v3, handy-computer GGUF Q5_K_M) et 3.2 (hook testé + sonde Linux 413 ; avis advisor : cochables) ; avis advisor défavorable à cocher 1.6.
- [limit] Windows simulé seulement par dry-run de résolution (`--python-platform`) : aucune validation réelle.

## Relations
- relates_to [[Faisabilité Transformers Linux du jalon 0 — téléchargements, essais et hors ligne]]
- relates_to [[Décisions du prototype de benchmark]]