# Tasks

## 1. Socle du projet

- [ ] 1.1 Installer uv pour l'utilisateur sur le serveur de développement (après accord explicite), sans toucher au Python système ni au runtime de Basic Memory ; vérifier `uv --version` et `uv python find 3.12`
- [ ] 1.2 Créer `pyproject.toml` (Python ≥ 3.12, dépendances serveur av, numpy, huggingface_hub, psutil), `.python-version`, le paquet `transcription_bench/` et le script `transcription-bench` ; vérifier que `uv run transcription-bench --help` fonctionne et que `uv.lock` est généré
- [ ] 1.3 Créer les dossiers de données sous `data/` au démarrage (audio, models, engines, results) et vérifier par test unitaire leur création et leur exclusion par `.gitignore` (`git check-ignore`)

## 2. Serveur web et créneau d'opération

- [ ] 2.1 Implémenter le serveur `ThreadingHTTPServer` sur `127.0.0.1` avec port configurable, routage GET/POST, POST → redirection et rendu HTML échappé ; vérifier que l'URL est affichée au démarrage et qu'aucune page ne contient `script`, `style` ni attribut `style` (test unitaire sur toutes les routes)
- [ ] 2.2 Implémenter le créneau unique d'opération longue (état, journal, refus si occupé) et sa page d'état avec lien d'actualisation ; vérifier par test qu'une seconde opération est refusée
- [ ] 2.3 Implémenter la page d'accueil (état du créneau, emplacements des dossiers, liens vers moteurs, modèles, audios, exécutions, résultats) et vérifier son rendu sans moteur installé

## 3. Moteurs : cadre commun et moteur factice

- [ ] 3.1 Définir l'interface d'adaptateur (compatibilité, familles, réglages exposés, durée native, chargement, transcription) et le registre des moteurs ; vérifier qu'un adaptateur de test enregistré apparaît dans la liste
- [ ] 3.2 Écrire `engines/runner.py` (lecture de `job.json`, chargement unique, traitement séquentiel, événements JSON sur stdout, mesures temps/CPU/pic mémoire Linux et Windows, fenêtres fixes au-delà de la durée native) sans dépendance serveur ; vérifier par test avec le moteur factice
- [ ] 3.3 Implémenter le moteur factice (texte et mesures marqués factices, sans réseau) exécuté avec l'interpréteur du serveur ; vérifier une exécution complète de bout en bout par test
- [ ] 3.4 Implémenter l'installation d'un moteur (`uv venv --python 3.12`, `uv pip install -r requirements/<moteur>.txt`), ses états et son journal, et la page des moteurs ; vérifier états et journal avec un fichier de dépendances de test vide, sans téléchargement de moteur réel

## 4. Modèles Hugging Face

- [ ] 4.1 Implémenter les règles de compatibilité faster-whisper (fichiers CTranslate2) et Transformers (`config.json`, refus de `auto_map`, familles) ; vérifier par tests sur listes de fichiers et configs d'exemple, dont le refus d'un Whisper non converti pour faster-whisper
- [ ] 4.2 Implémenter le lecteur partiel d'en-tête GGUF (`general.architecture`) et la règle transcribe.cpp avec choix du fichier de quantification ; vérifier par test sur un en-tête GGUF minimal généré localement
- [ ] 4.3 Implémenter la vérification distante (`model_info` avec tailles et commit), les messages d'incompatibilité et d'accès refusé sans affichage de jeton ; vérifier avec des réponses simulées, sans appel réseau dans les tests
- [ ] 4.4 Implémenter le téléchargement explicite à révision figée dans le créneau d'opération, l'inventaire `model.json` écrit après succès, la page des modèles et la suppression locale ; vérifier par test avec un téléchargement simulé et le maintien des résultats après suppression

## 5. Audios et exécutions

- [ ] 5.1 Implémenter la liste des audios du dossier d'entrée (formats acceptés, durée, erreurs de lecture) et le décodage PyAV commun en `float32` 16 kHz mono avec SHA-256 et temps de décodage ; vérifier par test sur un WAV généré localement et un fichier illisible
- [ ] 5.2 Implémenter le formulaire d'exécution (modèle prêt, sélection d'audios, threads, réglages applicables avec défauts, durée de fenêtre) ; vérifier par test que seuls les réglages de l'adaptateur sont proposés
- [ ] 5.3 Implémenter le lancement d'une exécution dans le créneau (job, sous-processus, lecture des événements, arrêt par l'utilisateur, plantage du moteur) ; vérifier avec le moteur factice l'arrêt après un audio et la gestion d'un plantage simulé
- [ ] 5.4 Implémenter le stockage des résultats (`run.json`, `run.log`, dossier par audio, sans écrasement, erreurs par audio, métadonnées machine et réglages effectifs) ; vérifier par test qu'une seconde exécution identique crée un nouveau résultat et que les métadonnées sont complètes

## 6. Résultats et comparaison

- [ ] 6.1 Implémenter la liste des exécutions et le détail d'une transcription (texte, segments, métadonnées, mesures, RTF avec repère 2 non bloquant, marque factice) ; vérifier par test sur des résultats d'exemple
- [ ] 6.2 Implémenter la comparaison côte à côte par empreinte audio avec mise en évidence des réglages différents ; vérifier par test que deux fichiers de même nom et d'empreintes différentes ne sont pas regroupés

## 7. Adaptateurs réels (validation sur PC uniquement)

- [ ] 7.1 Écrire `requirements/faster-whisper.in` et son verrou universel, et l'adaptateur faster-whisper (CPU, `cpu_threads`, `compute_type`, réglages de décodage, langue fr, long-form natif) ; vérifier sur le PC Linux avec `Systran/faster-whisper-large-v3-turbo` ou équivalent sur un court audio
- [ ] 7.2 Écrire `requirements/transcribe-cpp.in` (transcribe-cpp et transcribe-cpp-native 0.4.1) et son verrou, et l'adaptateur transcribe.cpp (`TRANSCRIBE_BACKENDS=cpu`, contrôle `model.backend`, `n_threads`, options Whisper, `timings`, mmap consigné, durées natives par architecture) ; vérifier sur le PC Linux avec un GGUF Whisper puis Qwen3-ASR ou Parakeet
- [ ] 7.3 Écrire `requirements/transformers.in` (torch CPU via l'index PyTorch CPU, transformers 5.20.2, mistral-common) et son verrou, et l'adaptateur Transformers par famille (Whisper, Qwen3-ASR, Parakeet TDT, Voxtral, Cohere, Canary) ; vérifier sur le PC Linux au moins Whisper et Parakeet, puis consigner les familles non testées
- [ ] 7.4 Rejouer l'installation des trois moteurs et une exécution courte sur le PC Windows ; consigner écarts et corrections éventuelles de specs

## 8. Documentation et intégration

- [ ] 8.1 Rédiger le README de lancement (installation de uv Windows/Linux, commande unique, dossiers de données, jeton Hugging Face, règle « aucun modèle sur le serveur de développement ») et vérifier que la commande documentée démarre le serveur
- [ ] 8.2 Vérifier de bout en bout sur le serveur de développement avec le moteur factice : lancement, dépôt d'un audio, exécution par lot, arrêt, consultation et comparaison ; puis `openspec validate add-benchmark-prototype --strict`

## Workflow follow-up

- Mettre à jour la mémoire projet avec les écarts constatés sur PC.
- Archiver le change après validation par l'utilisateur.
