# Design

## Context

Dépôt vierge hormis la mémoire projet (`.basic-memory/`) et un `.gitignore` excluant `data/`, audios, poids et environnements. Motivation : voir `proposal.md`. Exigences : voir les specs du change.

Contraintes établies par recherche documentaire du 2026-10-23 (notes `recherche/Moteurs et faisabilité technique` et suivantes), non encore validées par installation réelle :

- Plateformes : Windows x64 et Linux x64 (glibc ≥ 2.28). Toutes les roues nécessaires existent en cp312/abi3/py3 pour ces deux cibles.
- Python 3.12 imposé de fait : PyAV 19 et numpy 2.5 exigent ≥ 3.12. Le serveur de développement (Debian 11, Python 3.9) passera par un Python géré par uv.
- Versions de référence : faster-whisper 1.2.1, ctranslate2 4.8.3 ; transcribe-cpp et transcribe-cpp-native 0.4.1 (épinglés ensemble, API pré-1.0) ; transformers 5.20.2, torch 2.14.1+cpu ; av 19.0.2 ; huggingface_hub 2.3.0 ; psutil 7.2.2 ; uv 0.13.5.
- Transformers n'offre pas d'inférence ASR générique : chaque famille (Whisper, Qwen3-ASR, Parakeet TDT, Voxtral, Cohere, Canary) a son propre parcours processor/generate/decode. Toutes sont présentes dans transformers 5.20.2 sans `trust_remote_code` (Canary ≥ 5.17, Qwen3-ASR ≥ 5.13, Parakeet TDT ≥ 5.9, Cohere ≥ 5.4, Voxtral ≥ 4.54 + `mistral-common[audio]`).
- Le serveur de développement ne télécharge ni moteur ni modèle.

## Goals / Non-Goals

**Goals:**
- Un code court, sans framework web ni base de données, lisible par deux développeurs.
- Isolation stricte des dépendances de chaque moteur et du serveur.
- Mesures prises au plus près du moteur, dans des conditions consignées.
- Développement et tests possibles sans aucun moteur réel (moteur factice).

**Non-Goals:**
- File d'attente d'opérations, multi-utilisateur, authentification.
- Conversion de modèles (CTranslate2, GGUF) : seuls les formats déjà publiés sont acceptés.
- Évaluation automatique de la qualité, diarisation, GPU, macOS.

## Decisions

### D1. Structure et lancement
Projet uv à la racine : `pyproject.toml` (`requires-python = ">=3.12"`), `.python-version` à 3.12, paquet `transcription_bench/`, script `transcription-bench`. Lancement : `uv run transcription-bench [--port N]`. uv crée l'environnement du serveur et télécharge si besoin un CPython géré. Dépendances du serveur : `av`, `numpy`, `huggingface_hub`, `psutil`, verrouillées par `uv.lock`.
*Alternative écartée* : script d'amorçage installant uv lui-même — accès réseau implicite et code spécifique par OS ; la documentation renvoie à l'installeur officiel.

### D2. Serveur web en bibliothèque standard
`http.server.ThreadingHTTPServer` lié à `127.0.0.1`, port par défaut 8765. Pages produites par f-strings avec `html.escape` systématique ; formulaires `application/x-www-form-urlencoded` lus avec `urllib.parse` ; motif POST → redirection → GET ; pages d'état avec lien « Actualiser ». Pas de multipart : les audios sont déposés dans le dossier, pas téléversés.
*Alternatives écartées* : Flask/Starlette — inutiles pour quelques formulaires locaux. L'avertissement « non destiné à la production » de `http.server` est acceptable pour un outil local en boucle locale.

### D3. Créneau unique d'opération longue
Un objet `OperationSlot` protégé par verrou détient au plus une opération (installation, téléchargement, exécution) exécutée dans un thread d'arrière-plan, avec état, journal et horodatage. Toute nouvelle demande est refusée si le créneau est occupé. Évite qu'un téléchargement fausse les mesures CPU d'une exécution, sans file d'attente.

### D4. Moteurs : adaptateurs, environnements et verrous
- Dossier `engines/` contenant un adaptateur par moteur et un `runner.py` commun. Ce code est exécuté par l'interpréteur de l'environnement du moteur et ne dépend que de la bibliothèque standard, de numpy, psutil et des paquets du moteur — jamais des dépendances du serveur.
- Chaque moteur déclare : nom, fichier de dépendances, règles de compatibilité de modèle, familles prises en charge, réglages exposés (nom, type, défaut, choix), durée native maximale par famille.
- Dépendances : `requirements/<moteur>.in` compilé en `requirements/<moteur>.txt` par `uv pip compile --universal`, versionnés. Installation : `uv venv --python 3.12 data/engines/<moteur>` puis `uv pip install --python data/engines/<moteur> -r requirements/<moteur>.txt`.
- Transformers : torch depuis l'index `https://download.pytorch.org/whl/cpu` sur les deux OS (sur Linux, la roue PyPI tire la pile CUDA). `mistral-common[audio]` ajouté pour Voxtral.
- Ajouter un moteur = un adaptateur + un `.in`/`.txt`, conformément à la spec.
*Alternative écartée* : un seul projet uv avec groupes en conflit — installation simultanée impossible et plus fragile pour des environnements créés à la demande.

### D5. Protocole serveur ↔ moteur
Pour chaque exécution, le serveur décode les audios (D7) en fichiers `float32` 16 kHz mono dans un dossier temporaire de l'exécution, écrit un `job.json` (modèle, chemins, réglages, threads), puis lance `data/engines/<moteur>/…/python engines/runner.py job.json` avec un environnement contrôlé. Le runner charge le modèle une fois, traite les audios un par un et émet des lignes JSON sur stdout (`loaded`, `audio_done`, `audio_error`, `finished`). Le serveur est seul à écrire les résultats. Arrêt : terminaison du processus ; les audios non traités sont marqués comme tels. stderr est conservé dans le journal de l'exécution.
Le moteur factice est exécuté par le même runner avec l'interpréteur du serveur.

### D6. CPU uniquement et threads
| Moteur | CPU | Threads | Vérification |
|---|---|---|---|
| faster-whisper | `device="cpu"` | `cpu_threads=N` | implicite (CTranslate2 sans CUDA installé) |
| transcribe.cpp | `TRANSCRIBE_BACKENDS=cpu` + `backend="cpu"` | `model.session(n_threads=N)` | `model.backend == "cpu"`, sinon erreur |
| Transformers | torch CPU, `CUDA_VISIBLE_DEVICES=""`, modèle sur `cpu` | `OMP_NUM_THREADS`, `MKL_NUM_THREADS`, `torch.set_num_threads(N)` avant tout calcul | `torch.get_num_threads()` consigné |

Valeur par défaut de N : nombre de cœurs physiques (`psutil.cpu_count(logical=False)`), à défaut cœurs logiques.

### D7. Décodage audio commun
PyAV (FFmpeg embarqué dans ses roues) dans l'environnement du serveur : décodage, mixage mono et rééchantillonnage 16 kHz `float32`. Empreinte SHA-256 du fichier source. Durée = nombre d'échantillons / 16 000. Temps de décodage mesuré par le serveur. Le cache décodé est supprimé à la fin de l'exécution.

### D8. Mesures
Dans le runner : `time.perf_counter()` pour chargement et transcription, `time.process_time()` (tous threads du processus) pour le temps CPU, pic de mémoire résidente du processus depuis son démarrage (`resource.getrusage().ru_maxrss` en Kio sous Linux ; `psutil.Process().memory_info().peak_wset` sous Windows avec psutil 7.2, lu de façon compatible avec `peak_rss` de psutil 8). Pic relevé après chargement puis après chaque audio (valeur cumulative) ; pic final de l'exécution. Le serveur mesure la durée totale autour du processus. transcribe.cpp : mode mmap par défaut consigné, et `result.timings` ajoutés aux métadonnées.

### D9. Audios longs
Chaque adaptateur déclare, par famille, une durée native maximale. Au-delà, le runner découpe en fenêtres fixes sans recouvrement (30 s par défaut, réglable et consignée) et concatène les textes ; les horodatages éventuels sont décalés.
- Natif : faster-whisper (Whisper) ; transcribe.cpp Whisper, Qwen3-ASR (≤ 87 min) et Parakeet ; Transformers Whisper (long-form de `generate`), Voxtral (≤ 30 min), Cohere (découpage natif).
- Fenêtres fixes : Transformers Qwen3-ASR, Parakeet, Canary ; toute famille transcribe.cpp dont la limite n'est pas documentée.
Le découpage commun pour toutes les familles est écarté pour le prototype : il mesurerait notre découpage plutôt que le comportement des moteurs.

### D10. Modèles Hugging Face
Dans le serveur, via huggingface_hub (jeton lu par ses moyens standards, jamais stocké) :
- `HfApi.model_info(id, revision, files_metadata=True)` : commit exact et taille des fichiers.
- faster-whisper : présence de `model.bin`, `config.json` et `tokenizer.json` ou `vocabulary.*`.
- transcribe.cpp : liste des `*.gguf` ; lecture partielle de l'en-tête du fichier choisi via `HfFileSystem` pour extraire `general.architecture`, comparée à la liste des architectures prises en charge par la version épinglée.
- Transformers : téléchargement du seul `config.json` ; refus si `auto_map` présent ; `model_type` comparé aux familles de l'adaptateur.
- Téléchargement : `snapshot_download(id, revision=<commit>, allow_patterns=…, local_dir=data/models/<moteur>/<org>__<nom>/<commit>[/<fichier>])`. Fichier `model.json` d'inventaire écrit seulement après succès.

### D11. Stockage des résultats
Fichiers JSON et texte, sans base de données :
```
data/results/<AAAAMMJJ-HHMMSS>-<court-id>/
  run.json        configuration, modèle, moteur, versions, machine, état, mesures globales
  run.log         journal stderr du moteur
  <n>-<nom-audio>/
    transcription.txt
    result.json   audio (nom, SHA-256, durée, format), segments, mesures, erreur éventuelle
```
Les pages de résultats et de comparaison relisent ces fichiers ; la comparaison regroupe par SHA-256.

### D12. Tests et développement sur le serveur
Tests `unittest` limités aux parties à risque : règles de compatibilité (fichiers et `config.json` d'exemple), lecteur d'en-tête GGUF, stockage sans écrasement, protocole runner avec moteur factice. Aucun test ne télécharge de moteur ou de modèle. Les adaptateurs réels sont validés sur le PC de l'utilisateur.

## Risks / Trade-offs

- [Versions issues d'une recherche documentaire, non installées] → verrous par moteur ; premier passage sur PC Linux puis Windows ; specs ajustées si besoin, comme convenu avec l'utilisateur.
- [Compilation universelle du verrou torch CPU non vérifiée] → sinon épingler explicitement `torch==2.14.1+cpu` avec l'index CPU dans le `.in`, ou verrous séparés par OS.
- [faster-whisper 1.2.1 avec huggingface_hub 2.x non prouvé] → aucun téléchargement par faster-whisper (modèle déjà local, D10) ; borne `huggingface-hub<2` dans son verrou si l'import échoue.
- [Paramètres exacts du long-form Whisper dans Transformers non vérifiés] → si le mode natif échoue au test, basculer la famille en fenêtres fixes (D9).
- [Pic mémoire cumulatif, non attribuable à un audio précis] → valeur consignée comme pic du processus depuis son démarrage.
- [mmap de transcribe.cpp : RSS partiellement composé de pages de fichier] → mode consigné ; option `no_mmap` réglable.
- [transcribe.cpp pré-1.0, ruptures d'API entre versions mineures] → versions épinglées ensemble ; mise à jour = changement explicite.
- [Fenêtres fixes : mots coupés et perte de contexte] → appliquées uniquement aux familles sans mécanisme natif, durée consignée.
- [Dépôts restreints (ex. Cohere)] → message explicite d'accès refusé.
- [Débit des modèles lourds sur CPU, ex. Voxtral] → aucune limite imposée ; RTF affiché comme repère.

## Migration Plan

Nouveau projet, aucune migration. Préalable sur le serveur de développement : installer uv pour l'utilisateur, sans toucher au Python système ni au runtime de Basic Memory. Sur les PC : installer uv via l'installeur officiel, puis `uv run transcription-bench`.

## Open Questions

- Nom et version exacts des repos GGUF `handy-computer/*-gguf` autres que Whisper large-v3 : à confirmer lors des premiers ajouts de modèles, sans impact sur le code.
- Liste définitive des réglages exposés par famille dans transcribe.cpp hors Whisper : complétée lors de l'implémentation des adaptateurs.
