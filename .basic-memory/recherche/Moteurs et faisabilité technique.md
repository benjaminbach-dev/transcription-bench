---
title: Moteurs et faisabilité technique
type: note
permalink: transcription-bench/recherche/moteurs-et-faisabilite-technique
status: documentaire, non testé ; validation préalable sur PC requise
provenance: 'deux recherches scout du 2026-10-23 (sources primaires : PyPI, docs officielles,
  dépôts, fiches HF) ; aucune installation ni inférence'
date: '2026-10-23'
tags:
- recherche
- moteurs
- faisabilite
- '2026-10-23'
---

# Moteurs et faisabilité technique

## Statut
Recherche documentaire du 2026-10-23, versions relevées à cette date. Rien n'a été installé ni mesuré. Les références de versions et capacités ci-dessous restent des hypothèses documentaires à confirmer, pas une pile éprouvée.

Consolidation approuvée le 2026-10-24 (repo `transcription-bench`, branche `main`, base `b3f126c`) : trois moteurs conservés, mais Transformers limité à Whisper et Parakeet TDT au premier jalon. Le jalon de faisabilité Linux puis Windows est placé avant l'implémentation complète. Aucun moteur/poids sur le serveur de développement ; les contrôles réels attendent un PC et un accord sur leur périmètre.

Les exigences sont dans `openspec/changes/add-benchmark-prototype/`. Les variantes et familles non validées ne doivent pas être annoncées comme opérationnelles.
## Modèles à benchmarker
- Priorité : whisper-large-v3, whisper-large-v3-turbo, bofenghuang/whisper-large-v3-french, Qwen3-ASR-1.7B, parakeet-tdt-0.6b-v3 et moondream/parakeet-ultra, Voxtral-Mini-3B-2507.
- Second rang : CohereLabs/cohere-transcribe-03-2026, nvidia/canary-1b-v2, ibm-granite/granite-speech (biais de vocabulaire = condition de test distincte).
- Médical FR : MultiMed-ST whisper-small-french (WER ≈ 40–45 % sur conversations médicales réelles, arXiv 2504.03546), Whisper-Rayen-Medical (dictée d'ordonnances, sans métrique). Whisper-AfroRad-FR écarté (résultats internes douteux, LoRA non fusionné). UltiMed (Parakeet ONNX, voix TTS unique) nécessiterait onnx-asr.
- [fact] Pas de Voxtral Mini Transcribe open weight ; Voxtral sans horodatages.
- [limitation] Débits CPU tiers (Ryzen 4750U, parole lue) : Qwen3-ASR-1.7B RTF ≈ 0,4 ; Voxtral-Mini-3B RTF ≈ 1,7. Non transposables.

## Moteurs retenus
| Moteur | Faits clés |
|---|---|
| faster-whisper 1.2.1 / CTranslate2 4.8.3 | Whisper seulement ; roues Windows/Linux ; `device="cpu"`, `compute_type="int8"`, `cpu_threads` ; repos CT2 préconvertis (ex. Systran/faster-whisper-large-v3) ; conversion `ct2-transformers-converter` exige torch → à éviter ; nombreux réglages de décodage ; VAD Silero optionnelle |
| transcribe.cpp 0.4.1 (`transcribe-cpp` + `transcribe-cpp-native`) | Whisper, Qwen3-ASR, Voxtral, Parakeet, Canary, Cohere, Granite ; GGUF préconstruits `handy-computer/*-gguf` ; roues manylinux_2_28 et win_amd64 ; forcer CPU via `backend="cpu"` ou `TRANSCRIBE_BACKEND=cpu` (défaut préfère Vulkan) ; entrée PCM float32 16 kHz mono ; poids en mmap ; API pré-1.0 à épingler |
| Transformers 5.20.2 + torch CPU 2.14.1 | Python ≥ 3.10 ; torch CPU via l'index https://download.pytorch.org/whl/cpu ; Qwen3-ASR `-hf` ≥ 5.13 ; Parakeet TDT, Cohere, Voxtral supportés en 5.x ; passer un tableau numpy évite le ffmpeg système |

## Observations
- [constraint] Un environnement virtuel par moteur (versions de transformers incompatibles entre paquets) ; le serveur lance chaque moteur en sous-processus.
- [proposal] uv pour créer ces environnements (`uv venv --python 3.12`, `uv pip install --python <venv>`), uv pouvant fournir un CPython géré ; installation de uv proposée explicitement si absent. Python 3.12 recommandé.
- [proposal] Décodage audio commun par PyAV (FFmpeg embarqué dans ses roues) vers PCM float32 16 kHz mono, entrée identique pour tous les moteurs ; temps de décodage mesuré à part.
- [proposal] Mesures dans le sous-processus moteur : pic mémoire (`peak_wset`/`peak_rss` psutil sous Windows, `ru_maxrss` ou VmHWM sous Linux), temps CPU du processus, temps écoulé mesuré par le parent.
- [proposal] Longs audios : mode natif de chaque moteur par défaut, découpage commun optionnel, découpage effectif toujours consigné.
- [proposal] Validation d'un identifiant HF avant téléchargement via `huggingface_hub` (fichiers, `config.json`, `.gguf`, `model.bin`), taille via `snapshot_download(dry_run=True)` ou `model_info(files_metadata=True)`, révision figée par commit.
- [correction] transcribe.cpp 0.4.1 expose bien les threads : `model.session(n_threads=N)` (défaut min(cœurs logiques autorisés, 8)) ; CPU strict via `backend="cpu"` + `TRANSCRIBE_BACKENDS=cpu`, contrôle par `model.backend` ; décodage glouton, pas de beam ; roues natives Windows/Linux réellement publiées (README obsolète).
- [fact] Transformers n'a pas d'inférence ASR générique : un parcours par famille. Versions minimales stables : Qwen3-ASR 5.13, Parakeet TDT 5.9, Cohere 5.4, Canary 5.17, Voxtral 4.54 (+ mistral-common[audio]) ; aucune ne requiert trust_remote_code. Long-form natif : Whisper (generate), Voxtral ≤ 30 min, Cohere ; non documenté pour Qwen3-ASR, Parakeet, Canary.
- [documentaire] Selon les métadonnées et publications consultées le 2026-10-23, des roues cp312/abi3 Windows x64 et manylinux x86_64 seraient disponibles ; av 19 et numpy 2.5 exigeraient Python 3.12 ; torch CPU est à obtenir via l'index PyTorch CPU. Références documentaires : psutil 7.2.2 (`peak_wset` Windows), huggingface_hub 2.3.0 (`dry_run` depuis 1.0), uv 0.13.5. Installation et compatibilité combinée non testées.
- [decision] Specs rédigées dans le change OpenSpec `add-benchmark-prototype` (2026-10-23), sur la base de ces preuves documentaires ; écarts constatés sur PC à reporter dans les specs.
- [risk] Le RSS inclut les poids mappés (GGUF mmap) : choisir et consigner le mode mmap.
- [question] Installation réelle des trois environnements sous Windows et Linux ; README transcribe.cpp contradictoire sur les roues.
- [question] Présence effective de `ParakeetForTDT` et `CohereAsrForConditionalGeneration` dans la version de Transformers installée.

## Serveur de développement (relevé 2026-10-23)
Debian 11, Python système 3.9.2, uv et ffmpeg absents, 4 cœurs, 11 Gio de RAM. Python 3.9 insuffisant pour Transformers et PyAV récents : passer par uv et un Python géré, sans toucher au Python système.

## Relations
- relates_to [[Modèles et sources]]
- relates_to [[Décisions du prototype de benchmark]]
- informs [[Protocole à définir]]

## Priorité des décisions consolidées — 2026-10-24

Les tableaux et propositions du 23 octobre sont des recherches historiques : ils ne promettent pas le support de toutes les familles citées. Les exigences actuelles sont dans OpenSpec. Au premier jalon, Transformers couvre Whisper et Parakeet TDT ; transcribe.cpp n'annonce que les architectures effectivement vérifiées. Les fenêtres de secours sont fixes à 30 s, pas une option de formulaire. La variable transcribe.cpp à vérifier pour la version épinglée est `TRANSCRIBE_BACKENDS=cpu` (pluriel), avec `backend="cpu"` explicite ; la mention singulière du tableau initial n'est pas une commande de référence.

Le jalon préalable doit aussi confirmer les fichiers de prétraitement/tokenizer (notamment large-v3), le chargement Safetensors de Transformers et l'absence d'appels réseau au chargement. Les variations de versions ne sont pas validées par les relectures documentaires. Aucune installation ou inférence réelle effectuée lors de cette consolidation.

### Métadonnées Parakeet contrôlées — 2026-10-24

Source primaire : https://huggingface.co/api/models/nvidia/parakeet-tdt-0.6b-v3 et fichiers de ce dépôt, consultés en lecture seule lors de la relecture documentaire. Le dépôt est déclaré pour Transformers avec `model_type=parakeet_tdt` et contient notamment `model.safetensors`, `processor_config.json`, `generation_config.json`, des fichiers `tokenizer*.json`, ainsi que des variantes `.nemo` et `.gguf`. Ce constat valide la nécessité d'une liste blanche par famille et ne prouve pas le fonctionnement de l'inférence. Le jalon 0 doit confirmer fichiers minimaux, APIs et fonctionnement CPU hors ligne sur les deux OS.
