# Design

## Context

Dépôt vierge hormis la mémoire projet (`.basic-memory/`) et un `.gitignore` excluant `data/`, audios, poids et environnements. Motivation : voir `proposal.md`. Exigences : voir les specs du change.

Hypothèses issues de la recherche documentaire du 2026-10-23 (notes `recherche/Moteurs et faisabilité technique` et suivantes), **non vérifiées par installation réelle** et donc documentaires :

- Plateformes visées : Windows x64 et Linux x64 (glibc ≥ 2.28). La recherche indique des roues cp312/abi3/py3 pour ces cibles ; aucune installation n'a été faite.
- Python 3.12 imposé de fait : PyAV 19 et numpy 2.5 exigeraient ≥ 3.12. Le serveur de développement (Debian 11, Python 3.9) passera par un Python géré par uv.
- Versions de référence : faster-whisper 1.2.1, ctranslate2 4.8.3 ; transcribe-cpp et transcribe-cpp-native 0.4.1 (épinglés ensemble, API pré-1.0) ; transformers 5.20.2, torch 2.14.1+cpu ; av 19.0.2 ; huggingface_hub 2.3.0 ; psutil 7.2.2 ; uv 0.13.5.
- Transformers n'offre pas d'inférence ASR générique : chaque famille a son parcours processor/generate/decode. Le premier jalon ne retient que Whisper et Parakeet TDT ; Qwen3-ASR, Voxtral, Cohere et Canary sont des extensions futures, hors du périmètre de ce change.
- Le serveur de développement ne télécharge ni moteur ni modèle.
- Aucun essai n'a été exécuté à ce stade : le jalon 0 de faisabilité (tâches 1.x) doit confirmer ou corriger tout cela avant l'implémentation complète.

## Goals / Non-Goals

**Goals:**
- Un code court, sans framework web ni base de données, lisible par deux développeurs.
- Isolation stricte des dépendances de chaque moteur et du serveur.
- Mesures prises au plus près du moteur, dans des conditions consignées.
- Développement et tests possibles sans aucun moteur réel (moteur factice).
- Garanties vérifiables : inférence hors ligne, aucun code distant, installations conformes aux verrous, stockage atomique.

**Non-Goals:**
- File d'attente d'opérations, multi-utilisateur, authentification.
- Conversion de modèles (CTranslate2, GGUF) : seuls les formats déjà publiés sont acceptés.
- Évaluation automatique de la qualité, diarisation, GPU, macOS.
- Diff textuel, score, texte de référence ou répétitions automatiques entre résultats.
- Familles Transformers autres que Whisper et Parakeet TDT.

## Decisions

### D1. Structure et lancement
Projet uv à la racine : `pyproject.toml` (`requires-python = ">=3.12"`), `.python-version` à 3.12, paquet `transcription_bench/`, script `transcription-bench`. Lancement : `uv run transcription-bench [--port N]`. uv crée l'environnement du serveur et télécharge si besoin un CPython géré. Dépendances du serveur : `av`, `numpy`, `huggingface_hub`, `psutil`, verrouillées par `uv.lock`.
*Alternative écartée* : script d'amorçage installant uv lui-même — accès réseau implicite et code spécifique par OS ; la documentation renvoie à l'installeur officiel.

### D2. Serveur web local durci
`http.server.ThreadingHTTPServer` lié à `127.0.0.1`, port par défaut 8765. Pages produites par f-strings avec `html.escape` systématique ; formulaires `application/x-www-form-urlencoded` lus avec `urllib.parse` ; motif POST → redirection → GET ; pages d'état avec lien « Actualiser ». Pas de multipart : les audios sont déposés dans le dossier, pas téléversés.
Protections, malgré l'écoute en boucle locale :
- En-tête `Host` comparé à la liste `127.0.0.1:<port>`, `localhost:<port>` ; sinon 403. Contre le DNS rebinding.
- POST : jeton anti-CSRF aléatoire renouvelé à chaque démarrage du serveur et recopié dans un champ caché du formulaire, sans cookie ni gestion de session, vérifié en comparaison constante ; en-tête `Origin`, s'il est présent, doit correspondre à l'origine locale, sinon 403 ; `Origin: null` est refusé.
- Chemins contrôlés : tout nom d'audio ou de résultat fourni par l'utilisateur est résolu puis vérifié comme restant sous le dossier autorisé (`data/audio`, `data/results`) ; traversée `..`, liens symboliques sortants et chemins absolus sont refusés. Identifiants de modèle validés par motif avant tout usage réseau ou fichier.
*Alternatives écartées* : Flask/Starlette — inutiles pour quelques formulaires locaux. Laisser le serveur sans contrôle d'origine — une page distante ouverte dans le navigateur pourrait déclencher des POST locaux.

### D3. Créneau unique d'opération longue
Un objet `OperationSlot` protégé par verrou détient au plus une opération globale (installation, téléchargement, exécution) exécutée dans un thread d'arrière-plan, avec état, journal et horodatage. Toute nouvelle demande est refusée si le créneau est occupé. Les vérifications distantes de compatibilité de modèle sont également refusées pendant une exécution. La règle du créneau global appartient à la spec `local-web-interface` ; la spec `benchmark-runs` ne décrit que la séquence des audios dans une exécution. Évite qu'un téléchargement fausse les mesures CPU d'une exécution, sans file d'attente.

### D4. Moteurs : adaptations, environnements et verrous
- Dossier `engines/` avec, par moteur, une **déclaration** (nom, fichier de dépendances, règles de compatibilité, familles, réglages exposés, durée native) et un adaptateur d'exécution. La déclaration est importable par le serveur sans aucune dépendance du moteur : elle ne fait que des imports de la bibliothèque standard et ne charge aucun paquet moteur.
- Le code d'exécution est chargé uniquement dans le processus du moteur, avec des imports différés à l'intérieur des fonctions (torch, faster_whisper, transcribe_cpp…), jamais à l'import du module serveur.
- Dépendances : `requirements/<moteur>.in` compilé en `requirements/<moteur>.txt` par `uv pip compile --universal`, versionnés. Installation : `uv venv --python 3.12 data/engines/<moteur>` puis `uv pip sync --python <interpréteur-du-venv> requirements/<moteur>.txt`.
- Un marqueur d'installation atomique n'est écrit et le moteur n'est marqué **prêt** qu'après : code de sortie 0 de l'installation, contrôle d'import réussi dans un sous-processus avec l'interpréteur du moteur, et synchronisation réussie par `uv pip sync` depuis le verrou applicable à l'OS. uv évalue les marqueurs : le programme ne réimplémente pas un comparateur de dépendances. Au redémarrage, un environnement sans marqueur est affiché en **échec**, jamais prêt et une nouvelle installation explicite rejoue `sync` puis le contrôle d'import. L'empreinte du verrou et la date d'installation sont consignées.
- Transformers : torch depuis l'index `https://download.pytorch.org/whl/cpu` sur les deux OS. Aucune affirmation sur l'absence de CUDA dans les roues : c'est le verrou et l'index qui fixent la variante, et le périphérique est imposé explicitement (D6).
- Ajouter un moteur = une déclaration + un adaptateur + un `.in`/`.txt`, conformément à la spec.
*Alternative écartée* : un seul projet uv avec groupes en conflit — installation simultanée impossible et plus fragile pour des environnements créés à la demande.

### D5. Protocole serveur ↔ moteur
Pour chaque exécution, le serveur décode les audios (D7) en fichiers `float32` 16 kHz mono dans un dossier temporaire de l'exécution, écrit un `job.json` (modèle, chemins, réglages, threads demandés), puis lance `data/engines/<moteur>/…/python engines/runner.py job.json` avec un environnement contrôlé. Le runner charge le modèle une fois, traite les audios un par un et émet des lignes JSON préfixées par un marqueur fixe (par exemple `##TB-EVENT## `). Le serveur n'interprète que les lignes portant ce marqueur et journalise les autres lignes stdout comme sortie parasite, sans échec. stderr est conservé dans le journal de l'exécution. Le serveur est seul à écrire les résultats.
Arrêt : à la demande de l'utilisateur ou à l'arrêt normal du serveur, le processus du moteur est terminé (terminate puis kill après délai), les résultats déjà écrits sont conservés et l'exécution est marquée interrompue. Les audios non traités sont marqués comme tels. Le moteur factice est exécuté par le même runner avec l'interpréteur du serveur.

### D6. CPU uniquement et threads
| Moteur | CPU | Threads | Vérification |
|---|---|---|---|
| faster-whisper | `device="cpu"` | `cpu_threads=N` | implicite (périphérique imposé, aucun repli GPU) |
| transcribe.cpp | `TRANSCRIBE_BACKENDS=cpu` + `backend="cpu"` | `model.session(n_threads=N)` | `model.backend == "cpu"`, sinon erreur |
| Transformers | `CUDA_VISIBLE_DEVICES=""`, modèle sur `cpu` | `OMP_NUM_THREADS`, `MKL_NUM_THREADS`, `torch.set_num_threads(N)` avant tout calcul | `torch.get_num_threads()` consigné, si l'API est disponible |

Le nombre de threads demandé et, lorsque l'API permet de le lire, le nombre appliqué sont consignés séparément ; sans API de lecture, seul le demandé est consigné et aucun appliqué n'est affirmé. Valeur par défaut : nombre de cœurs physiques (`psutil.cpu_count(logical=False)`), à défaut cœurs logiques.

### D7. Décodage audio commun
PyAV (FFmpeg embarqué dans ses roues) dans l'environnement du serveur : décodage, mixage mono et rééchantillonnage 16 kHz `float32`. Empreinte SHA-256 du fichier source. La durée affichée dans la liste des audios est **indicative** ; la durée de référence, utilisée pour le RTF, est la durée décodée (nombre d'échantillons / 16 000) et les deux sont consignées. Le découpage en fenêtres s'applique audio par audio. Le cache décodé est supprimé à la fin de l'exécution.

### D8. Mesures
Dans le runner : `time.perf_counter()` pour le chargement et la transcription, `time.process_time()` (tous threads du processus) pour le temps CPU, pic de mémoire résidente du processus depuis son démarrage (`resource.getrusage().ru_maxrss` en Kio sous Linux ; `psutil.Process().memory_info().peak_wset` sous Windows avec psutil 7.2). Pic relevé après chargement puis après chaque audio (valeur cumulative) ; pic final à la fin normale de l'exécution. Pour une interruption ou un échec, le pic disponible est le dernier relevé transmis, signalé comme incomplet ; les durées sont mesurées jusqu'à la clôture et la sortie du moteur. Pour une exécution abandonnée, les durées totale et du processus sont inconnues et le dernier pic transmis reste identifié comme partiel. Les mesures indisponibles sont affichées comme absentes, jamais comme zéro.
Le serveur mesure séparément le temps de décodage par audio et la **durée totale de l'opération**, du début de sa préparation à la fin de la collecte du moteur et de l'écriture des résultats d'audios, décodage, chargement, inférence et écriture compris (hors ultime sauvegarde de `run.json`) ; la **durée du processus moteur**, du lancement à sa sortie, est consignée séparément. Le RTF est calculé sur la durée décodée ; une durée décodée nulle est une erreur et aucun RTF n'est calculé. transcribe.cpp : mode mmap par défaut consigné, `result.timings` ajoutés aux métadonnées.

### D9. Audios longs et fenêtres de secours
Chaque adaptateur déclare, par famille, la durée native maximale et la méthode retenue. Sans mécanisme natif prouvé, le runner découpe l'audio en fenêtres fixes de **30 s** sans recouvrement, concatène les textes et décale les horodatages éventuels ; la durée de fenêtre effective est consignée **pour chaque audio**.
- Transformers Whisper : long-form natif seulement si le jalon 0 le confirme ; sinon bascule en fenêtres de 30 s, décidée avant l'implémentation complète.
- Transformers Parakeet TDT : fenêtres fixes de 30 s.
- faster-whisper et transcribe.cpp : famille disponible seulement après vérification de son architecture (Whisper au jalon 0, autres architectures transcribe.cpp en tâche 8.2). Pour une architecture vérifiée, mécanisme long natif s'il est vérifié lui aussi, fenêtres fixes sinon. Une architecture non vérifiée reste refusée à l'ajout.
Le découpage commun pour toutes les familles est écarté pour le prototype : il mesurerait notre découpage plutôt que le comportement des moteurs.

### D10. Modèles Hugging Face, hors ligne et sans code distant
Dans le serveur, via huggingface_hub (jeton lu par ses moyens standards, jamais stocké) :
- `HfApi.model_info(id, revision, files_metadata=True)` : commit exact et taille des fichiers.
- Pour Transformers : lecture des petits JSON de configuration attendus (`config.json`, `processor_config.json` ou `preprocessor_config.json`, `tokenizer_config.json`, selon la famille), `model_type` comparé aux familles vérifiées de l'adaptateur, puis sélection d'une **liste blanche de fichiers suffisante par famille** : poids safetensors et index/shards éventuels, configuration du modèle, du processor/préprocesseur, `generation_config.json` lorsque requis, vocabulaire/tokenizer et éventuels fichiers de fusion. Le jalon 0 fixe les fichiers requis ; Parakeet peut utiliser `processor_config.json`, pas nécessairement `preprocessor_config.json`. Un `auto_map` dans l'un des JSON de configuration inspectés est un motif de refus, mais le programme ne prétend pas qu'un simple scan de `auto_map` suffit : la décision repose sur la liste de fichiers et le type de modèle déclarés, et seuls les poids safetensors sont sélectionnés et chargés (`use_safetensors=True` aux API concernées). Tous les fichiers hors de la liste blanche, notamment variantes pickle, `.nemo`, `.gguf`, `.onnx` ou `.h5`, sont ignorés pour Transformers ; un dépôt sans variante safetensors complète est refusé.
- faster-whisper : présence de `model.bin`, `config.json`, `tokenizer.json` et des fichiers de prétraitement/vocabulaire requis par la version et la famille, notamment `preprocessor_config.json` pour Whisper large-v3. Le jalon 0 fixe la liste suffisante pour éviter tout repli vers un tokenizer distant ou un prétraitement incorrect.
- transcribe.cpp : liste des `*.gguf` ; lecture partielle de l'en-tête du fichier choisi via `HfFileSystem` pour extraire `general.architecture`, comparée aux architectures prises en charge par la version épinglée.
- Téléchargement : `snapshot_download(id, revision=<commit>, allow_patterns=…, local_dir=data/models/<moteur>/<org>__<nom>/<commit>[/<fichier>])`. Fichier `model.json` d'inventaire écrit atomiquement seulement après succès. Sans ce marqueur, un dossier partiel n'est jamais proposé comme modèle prêt ; une nouvelle demande explicite de téléchargement peut le compléter.
- Inférence et exécution du moteur : `HF_HUB_OFFLINE=1` obligatoire, `local_files_only=True` lorsque l'API du moteur le permet, `trust_remote_code=False` aux API qui exposent cette option. Aucun accès réseau une fois les fichiers présents.

### D11. Stockage des résultats, atomicité et clôture après incident
Fichiers JSON et texte, sans base de données :
```
data/results/<AAAAMMJJ-HHMMSS>-<court-id>/
  run.json        configuration, modèle, moteur, versions, machine, état, ordre des audios, mesures globales
  run.log         journal stderr du moteur
  <n>-<nom-audio>/
    transcription.txt
    result.json   audio (nom, SHA-256, durée indicative et décodée, format), segments, mesures, erreur éventuelle
```
Écriture atomique : chaque JSON est écrit dans un fichier temporaire du même dossier puis remplacé par `os.replace`, afin qu'une interruption de processus ne laisse pas un JSON tronqué. Un verrou serveur commun protège les lectures et remplacements JSON afin de ne pas tenter un remplacement Windows pendant une lecture ; ce comportement est à vérifier sur PC Windows. Un résultat d'audio est écrit avant de passer au suivant.
`run.json` évolue pendant l'exécution (état `running`, progression), puis devient immuable une fois l'état final atteint (`completed`, `interrupted`, `failed`, `abandoned`). Le PID et l'heure de création du processus moteur sont consignés dans `run.json` dès son lancement. Une seule instance du serveur peut utiliser le même dossier de données (verrou de fichier d'instance détenu par le système et libéré automatiquement à la mort du processus, y compris après arrêt brutal ; primitive à vérifier sur chaque OS au jalon 0) : un démarrage concurrent est refusé avant toute récupération. Un simple fichier de PID persistant ne constitue pas ce verrou. Au redémarrage après un arrêt brutal, le serveur termine le moteur encore vivant seulement si son PID et son heure de création concordent, puis toute exécution restée `running` est finalisée automatiquement en `abandoned`, ses audios sans résultat étant signalés non traités. Il n'y a pas de reprise d'inférence dans une ancienne exécution : retranscrire les audios restants crée une nouvelle exécution, avec un nouveau chargement et de nouvelles mesures. La suppression d'un modèle utilisé par une exécution active est refusée.
Les pages de résultats et de comparaison relisent ces fichiers ; la comparaison regroupe par SHA-256.

### D12. Tests et développement sur le serveur
Tests `unittest` limités aux parties à risque : règles de compatibilité (listes de fichiers et `config.json` d'exemple, dont refus d'un poids non safetensors pour Transformers, acceptation du `model.bin` CTranslate2, dépôts mixtes, et refus d'un `auto_map`), lecteur d'en-tête GGUF, stockage sans écrasement et écriture atomique, événements runner avec lignes stdout parasites, serveur (contrôle `Host`, jeton anti-CSRF, chemins refusés), clôture d'une exécution abandonnée, protocole runner avec moteur factice. Aucun test ne télécharge de moteur ou de modèle, ni n'appelle le réseau. Les adaptateurs réels sont validés au jalon 0 puis sur les PC de l'utilisateur.

## Risks / Trade-offs

- [Versions et roues issues d'une recherche documentaire, non installées] → jalon 0 de faisabilité avant toute implémentation complète : résolution des verrous, import, CPU, court audio, hors ligne, sur Linux puis Windows ; specs ajustées si besoin.
- [Long-form Whisper de Transformers non prouvé] → garde conditionnel : mécanisme natif seulement s'il est vérifié au jalon 0, sinon fenêtres fixes de 30 s.
- [Compilation universelle du verrou torch CPU non vérifiée] → sinon épingler explicitement `torch==2.14.1+cpu` avec l'index CPU dans le `.in`, ou verrous séparés par OS, décidé au jalon 0.
- [faster-whisper 1.2.1 avec huggingface_hub 2.x non prouvé] → aucun téléchargement par faster-whisper (modèle déjà local, D10) ; borne `huggingface-hub<2` dans son verrou si l'import échoue.
- [Pic mémoire cumulatif, non attribuable à un audio précis] → valeur consignée comme pic du processus depuis son démarrage.
- [Durée totale de l'opération incluant décodage et écriture] → ne mesure pas l'inférence seule ; la durée du processus moteur et les temps de chargement/transcription sont consignés séparément.
- [mmap de transcribe.cpp : RSS partiellement composé de pages de fichier] → mode consigné ; option `no_mmap` réglable.
- [transcribe.cpp pré-1.0, ruptures d'API entre versions mineures] → versions épinglées ensemble ; mise à jour = changement explicite.
- [Fenêtres fixes : mots coupés et perte de contexte] → appliquées uniquement aux familles sans mécanisme natif vérifié, durée consignée par audio.
- [Dépôts restreints (acceptation de conditions, jeton absent)] → message explicite d'accès refusé.
- [Débit des modèles lourds sur CPU] → aucune limite imposée ; RTF affiché comme repère.
- [Jeton anti-CSRF et contrôle `Host` sur un serveur de développement] → coût faible, protège contre les POST d'une page distante et le DNS rebinding ; pas de TLS, trafic local uniquement.
- [Écriture atomique insuffisante si le disque est plein] → l'erreur est journalisée, l'exécution passe en échec et le JSON précédent reste lisible.

## Migration Plan

Nouveau projet, aucune migration. Préalable sur le serveur de développement : installer uv pour l'utilisateur, sans toucher au Python système ni au runtime de Basic Memory. Sur les PC : installer uv via l'installeur officiel, puis `uv run transcription-bench`. Aucun moteur ni poids n'est installé sur le serveur de développement.

## Open Questions

- Nom et version exacts des repos GGUF `handy-computer/*-gguf` autres que Whisper large-v3 : à confirmer lors des premiers ajouts de modèles, sans impact sur le code.
- Liste définitive des réglages exposés par famille dans transcribe.cpp hors Whisper : vérifiée au jalon 0 pour Whisper puis lors de la tâche 8.2 pour toute autre famille annoncée comme prise en charge ; les familles non vérifiées restent indisponibles. Tout écart modifiant une exigence est reporté dans les specs avant implémentation.
