# Tasks

## 1. Jalon 0 — accord et faisabilité sur PC

Ce jalon précède toute implémentation complète. Aucune affirmation de « testé » ne peut être faite avant son exécution : les versions, roues et comportements de long-form restent documentaires jusque-là. Les sondes sont des scripts éphémères sous `data/feasibility/`, hors Git ; leurs constats et commandes utiles sont résumés en mémoire, sans données personnelles. Leurs mesures sont des contrôles de fonctionnement, pas des résultats de benchmark représentatifs.

- [ ] 1.1 Obtenir l'accord explicite de l'utilisateur sur les installations (uv, moteurs, modèles d'essai, espace disque) et arrêter la liste des modèles d'essai (`Systran/faster-whisper-large-v3-turbo`, `openai/whisper-large-v3-turbo`, `nvidia/parakeet-tdt-0.6b-v3`, et un dépôt GGUF Whisper dont l'identifiant et la variante sont confirmés avant téléchargement) ; vérifier que l'accord et la liste sont consignés dans la mémoire projet
- [ ] 1.2 Sur PC Linux, préparer les déclarations minimales de dépendances et compiler une fois les verrous universels des trois moteurs (`uv pip compile --universal`) pour Python 3.12 ; vérifier comment conserver et transmettre l'index torch CPU à `uv pip sync`, puis consigner versions et écarts ; retenir des verrous par OS seulement si nécessaire
- [ ] 1.3 Sur PC Windows, installer depuis les mêmes verrous validés, vérifier la disponibilité des roues Windows x64 et la variante torch CPU ; consigner les écarts, puis ajuster les verrous seulement si nécessaire
- [ ] 1.4 Créer l'environnement de chaque moteur et vérifier que l'import réussit et que l'exécution est explicitement configurée sur CPU (périphérique relu quand l'API le permet) ; consigner versions, périphérique et threads sur Linux puis Windows
- [ ] 1.5 Transcrire un court audio avec chaque moteur (faster-whisper, transcribe.cpp GGUF Whisper, Transformers Whisper, Transformers Parakeet TDT) sur Linux puis Windows ; consigner durée décodée, temps de chargement, temps de transcription, pic mémoire et fichiers réellement requis
- [ ] 1.6 Charger réseau coupé avec `HF_HUB_OFFLINE=1`, `local_files_only` et `trust_remote_code=False` aux API concernées ; vérifier pour Transformers la liste blanche safetensors et fichiers auxiliaires par famille (processor/préprocesseur, génération, tokenizer et index/shards compris) et le long-form Whisper ainsi que le découpage Parakeet ; consigner si le natif fonctionne ou si les fenêtres de 30 s s'appliquent
- [ ] 1.7 Consigner les écarts constatés et ajuster design et specs avant l'implémentation complète ; vérifier qu'aucun moteur ni poids n'a été installé sur le serveur de développement

## 2. Socle du projet

- [ ] 2.1 Installer uv pour l'utilisateur sur le serveur de développement (après accord explicite), sans toucher au Python système ni au runtime de Basic Memory ; vérifier `uv --version` et `uv python find 3.12`
- [ ] 2.2 Créer `pyproject.toml` (Python ≥ 3.12, dépendances serveur av, numpy, huggingface_hub, psutil), `.python-version`, le paquet `transcription_bench/` et le script `transcription-bench` ; vérifier que `uv run transcription-bench --help` fonctionne et que `uv.lock` est généré
- [ ] 2.3 Créer les dossiers de données sous `data/` au démarrage (audio, models, engines, results) et vérifier par test unitaire leur création ; contrôler manuellement que `data/` reste ignoré par Git

## 3. Serveur web et créneau d'opération

- [ ] 3.1 Implémenter le serveur `ThreadingHTTPServer` sur `127.0.0.1` avec port configurable, routage GET/POST, POST → redirection et rendu HTML échappé ; vérifier que l'URL est affichée au démarrage et qu'aucune page ne contient `script`, `style` ni attribut `style` (test unitaire sur toutes les routes)
- [ ] 3.2 Implémenter le contrôle de l'en-tête `Host`, le jeton anti-CSRF renouvelé au démarrage exigé sur les POST et le contrôle d'`Origin` lorsqu'il est présent (refus de `null`) ; vérifier par tests qu'un `Host` étranger, un POST sans jeton et une origine distante sont refusés
- [ ] 3.3 Implémenter la résolution contrôlée des noms d'audios, de résultats et d'identifiants de modèles (refus des chemins absolus, de `..` et des liens symboliques sortants) ; vérifier par tests qu'aucun accès hors des dossiers autorisés n'est possible
- [ ] 3.4 Implémenter le créneau unique global d'opération longue (état, journal, refus si occupé) et sa page d'état avec lien d'actualisation ; vérifier par test qu'une seconde opération est refusée quel que soit son type
- [ ] 3.5 Implémenter la page d'accueil (état du créneau, emplacements des dossiers, liens vers moteurs, modèles, audios, exécutions, résultats) et vérifier son rendu sans moteur installé ; refuser une seconde instance utilisant le même dossier de données avant toute récupération d'état ; vérifier que le verrou système d'instance est libéré après un arrêt brutal et permet un redémarrage sans intervention manuelle

## 4. Moteurs : cadre commun et moteur factice

- [ ] 4.1 Définir la déclaration d'adaptateur sans dépendance moteur (compatibilité, familles, réglages, durée native) et le registre, avec imports d'exécution différés ; vérifier par test que l'import du registre ne charge aucun paquet moteur et qu'un adaptateur de test enregistré apparaît dans la liste
- [ ] 4.2 Écrire `engines/runner.py` (lecture de `job.json`, chargement unique, traitement séquentiel, événements préfixés sur stdout, mesures de chargement/transcription, temps CPU, pic mémoire cumulatif Linux et Windows, fenêtres fixes de 30 s) sans dépendance serveur ; vérifier par test qu'une ligne stdout non préfixée est journalisée sans interrompre le flux d'événements
- [ ] 4.3 Implémenter le moteur factice (texte et mesures marqués factices, sans réseau) exécuté avec l'interpréteur du serveur ; vérifier une exécution complète de bout en bout par test
- [ ] 4.4 Implémenter l'installation d'un moteur (`uv venv --python 3.12`, `uv pip sync --python <interpréteur-du-venv> requirements/<moteur>.txt`), le contrôle d'import dans l'environnement, la synchronisation uv réussie depuis le verrou, le marqueur d'installation atomique et les états et le journal, ainsi que la page des moteurs ; vérifier avec un fichier de dépendances de test vide, sans téléchargement de moteur réel, qu'un import en échec, un échec de synchronisation ou l'absence du marqueur après redémarrage donne l'état échec, jamais prêt

## 5. Modèles Hugging Face

- [ ] 5.1 Implémenter les règles de compatibilité faster-whisper (fichiers CTranslate2) et Transformers (`config.json`, familles Whisper et Parakeet TDT, liste de fichiers avec préprocesseur et tokenizer, sélection exclusive de la liste blanche safetensors pour Transformers et refus de `auto_map` dans les petits JSON de configuration) ; vérifier par tests sur listes de fichiers et configs d'exemple, dont le refus d'un Whisper non converti pour faster-whisper, l'acceptation de son `model.bin` CTranslate2 et la sélection d'un dépôt Transformers mixte sans NeMo, GGUF ni pickle
- [ ] 5.2 Implémenter le lecteur partiel d'en-tête GGUF (`general.architecture`) et la règle transcribe.cpp avec choix du fichier de quantification ; vérifier par test sur un en-tête GGUF minimal généré localement
- [ ] 5.3 Implémenter la vérification distante (`model_info` avec tailles et commit), les messages d'incompatibilité et d'accès refusé sans affichage de jeton ; vérifier avec des réponses simulées, sans appel réseau dans les tests
- [ ] 5.4 Implémenter le téléchargement explicite à révision figée dans le créneau d'opération, l'inventaire `model.json` écrit atomiquement après succès, la page des modèles et la suppression locale ; vérifier par test avec un téléchargement simulé et le maintien des résultats après suppression ; vérifier qu'un téléchargement interrompu sans inventaire n'apparaît jamais prêt
- [ ] 5.5 Implémenter le refus de suppression d'un modèle utilisé par une exécution active, et l'imposition du mode hors ligne (`HF_HUB_OFFLINE=1`, `local_files_only`, `trust_remote_code=False`) au lancement du moteur ; vérifier par tests que la suppression est refusée et que l'environnement transmis contient les réglages hors ligne

## 6. Audios et exécutions

- [ ] 6.1 Implémenter la liste des audios du dossier d'entrée (formats acceptés, durée indicative, erreurs de lecture) et le décodage PyAV commun en `float32` 16 kHz mono avec SHA-256, durée décodée et temps de décodage ; vérifier par test sur un WAV généré localement, un fichier illisible et un fichier de durée décodée nulle
- [ ] 6.2 Implémenter le formulaire d'exécution (modèle prêt, sélection d'audios, threads demandés, réglages applicables avec défauts, indication des fenêtres fixes de 30 s) ; vérifier par test que seuls les réglages de l'adaptateur sont proposés et que les threads demandés sont consignés
- [ ] 6.3 Implémenter le lancement d'une exécution dans le créneau (job, sous-processus, lecture des seuls événements préfixés, arrêt par l'utilisateur, plantage du moteur) ; vérifier avec le moteur factice l'arrêt après un audio et la gestion d'un plantage simulé
- [ ] 6.4 Mesurer côté serveur la durée totale de l'opération et la durée du processus moteur selon D8 ; implémenter le stockage des résultats (`run.json`, `run.log`, dossier par audio, sans écrasement, erreurs par audio, ordre des audios, métadonnées machine, programme, Python, verrou, PyAV/FFmpeg, réglages effectifs) avec écriture atomique des JSON ; vérifier par test qu'une seconde exécution identique crée un nouveau résultat, que les métadonnées sont complètes et qu'aucun JSON tronqué n'apparaît après interruption simulée
- [ ] 6.5 Implémenter le cycle de vie de `run.json` (mutable pendant l'exécution, immuable ensuite), la détection au démarrage des exécutions restées en cours, leur clôture automatique en état abandonné sans reprise d'inférence, avec terminaison du moteur survivant seulement après vérification de son PID et de son heure de création enregistrés ; vérifier par test que les résultats existants ne sont pas réécrits et qu'une exécution terminée n'est plus modifiée ; tester les mesures absentes/partielles selon l'état final sans zéros inventés
- [ ] 6.6 Implémenter l'arrêt du serveur terminant le processus moteur et marquant l'exécution interrompue ; vérifier avec le moteur factice qu'aucun processus moteur ne survit à l'arrêt du serveur

## 7. Résultats et comparaison

- [ ] 7.1 Implémenter la liste des exécutions et le détail d'une transcription (texte, segments, métadonnées, durée totale de l'opération, durée du processus, RTF avec repère 2 non bloquant, marque factice, absence de RTF sur durée nulle) ; vérifier par test sur des résultats d'exemple
- [ ] 7.2 Implémenter la comparaison côte à côte par empreinte audio avec mise en évidence des réglages différents, des états (terminée, interrompue, abandonnée, échec) et des résultats partiels ; vérifier par test que deux fichiers de même nom et d'empreintes différentes ne sont pas regroupés

## 8. Adaptateurs réels (validation sur PC uniquement)

- [ ] 8.1 Reprendre et versionner les dépendances et verrous faster-whisper validés au jalon 0, puis écrire l'adaptateur faster-whisper (CPU explicite, `cpu_threads` demandés et appliqués si lisible, `compute_type`, réglages de décodage, langue fr, long-form vérifié) ; vérifier sur le PC Linux avec `Systran/faster-whisper-large-v3-turbo` ou équivalent sur un court audio
- [ ] 8.2 Reprendre et versionner les dépendances et verrous transcribe.cpp validés au jalon 0 (versions natives et Python épinglées ensemble), puis écrire l'adaptateur transcribe.cpp (`TRANSCRIBE_BACKENDS=cpu`, contrôle `model.backend`, `n_threads`, options Whisper, `timings`, mmap consigné, durées natives par architecture) ; vérifier sur le PC Linux avec un GGUF Whisper puis un GGUF Qwen3-ASR ou Parakeet (architectures transcribe.cpp, indépendantes du périmètre Transformers)
- [ ] 8.3 Reprendre et versionner les dépendances et verrous Transformers validés au jalon 0 (torch CPU via l'index PyTorch CPU), puis écrire l'adaptateur Transformers limité à Whisper et Parakeet TDT (poids safetensors uniquement, mode hors ligne, `trust_remote_code=False`) ; vérifier sur le PC Linux avec Whisper puis Parakeet, et consigner que les autres familles restent des extensions futures
- [ ] 8.4 Rejouer l'installation des trois moteurs et une exécution courte sur le PC Windows ; consigner écarts et corrections éventuelles de specs ; vérifier notamment le remplacement atomique des JSON pendant la consultation de pages et la protection commune des lectures/écritures sous Windows

## 9. Documentation et intégration

- [ ] 9.1 Rédiger le README de lancement (installation de uv Windows/Linux, commande unique, dossiers de données, jeton Hugging Face, fonctionnement hors ligne, règle « aucun modèle sur le serveur de développement ») et vérifier que la commande documentée démarre le serveur
- [ ] 9.2 Vérifier de bout en bout sur le serveur de développement avec le moteur factice : lancement, dépôt d'un audio, exécution par lot, arrêt, arrêt du serveur, clôture d'une exécution abandonnée, consultation et comparaison ; puis `openspec validate add-benchmark-prototype --strict`

## Workflow follow-up

- Mettre à jour la mémoire projet avec les écarts constatés lors du jalon 0 et sur PC.
- Archiver le change après validation par l'utilisateur.
