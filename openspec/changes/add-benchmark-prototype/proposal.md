# Proposal

## Why

Le projet doit choisir des modèles de transcription française utilisables en local sur des ordinateurs ordinaires, sans GPU dédié. Aucun outil ne permet aujourd'hui de faire transcrire les mêmes audios par plusieurs modèles et moteurs, puis de comparer textes, réglages et coûts mesurés dans des conditions consignées.

## What Changes

- Création d'un programme Python local, lancé par uv, qui démarre un serveur web accessible uniquement depuis la machine.
- Interface en HTML pur (ni CSS ni JavaScript) pour piloter installations, modèles, exécutions et résultats ; couche web Flask avec templates Jinja2 et serveur WSGI Waitress, plutôt qu'un routage et un rendu maison.
- Trois moteurs d'inférence CPU dès le départ : faster-whisper, transcribe.cpp et Hugging Face Transformers, chacun dans un environnement isolé installé à la demande ; structure prévue pour en ajouter d'autres ; moteur factice pour le développement sans modèle. Pour Transformers, seules les familles Whisper et Parakeet TDT sont retenues au premier jalon ; les autres familles sont des extensions futures.
- Ajout libre d'un modèle par identifiant Hugging Face, vérifié avant téléchargement contre les familles prises en charge par le moteur choisi, puis téléchargé explicitement à une révision figée.
- Inférence strictement hors ligne à partir des fichiers locaux, sans exécution de code distant ; pour Transformers, uniquement des poids au format safetensors.
- Exécutions unitaires ou par lot séquentiel sur les audios déposés dans un dossier prédéfini, un seul traitement à la fois, exclusivement sur CPU.
- Conservation sans écrasement de chaque transcription avec ses métadonnées (audio, modèle, moteur, réglages effectifs, machine, versions) et ses mesures (durée totale de l'opération, temps de chargement et de transcription, RTF, pic de mémoire, temps CPU).
- Un jalon 0 de faisabilité sur PC Linux puis Windows (résolution des verrous, import des moteurs, exécution CPU, court audio et mode hors ligne, puis cycle de vie du serveur web avec moteur factice) précède l'implémentation complète.
- Consultation des transcriptions et comparaison, pour un même audio, des résultats produits par différents modèles, moteurs et réglages.

Hors périmètre : diarisation, correction par LLM, streaming, score WER automatique, accélération GPU, support macOS.

## Capabilities

### New Capabilities

- `local-web-interface`: lancement du programme, serveur local et règles de l'interface HTML.
- `engine-management`: moteurs disponibles, installation isolée à la demande, exécution CPU et extensibilité.
- `model-management`: ajout d'un modèle par identifiant Hugging Face, vérification de compatibilité, téléchargement et inventaire local.
- `benchmark-runs`: audios d'entrée, configuration et déroulement des exécutions, mesures et conservation des résultats.
- `results-comparison`: consultation des transcriptions, de leurs métadonnées et comparaison entre exécutions.

### Modified Capabilities

Aucune.

## Impact

- Nouveau code Python à la racine du dépôt, fichiers de dépendances verrouillées par environnement, documentation de lancement.
- Dossiers de données locaux sous `data/` (audios, modèles, environnements des moteurs, résultats), ignorés par Git.
- Dépendances : uv, Python 3.12 géré par uv ; Flask et Waitress avec Jinja2 fourni par Flask, PyAV, huggingface_hub, numpy, psutil dans l'environnement serveur ; faster-whisper, transcribe-cpp, transformers et torch CPU dans leurs environnements respectifs. Pas de framework asynchrone, ORM ou extension de formulaires.
- Accès réseau uniquement sur action explicite : installation d'un moteur, consultation ou téléchargement d'un modèle. Une fois les fichiers présents, l'inférence ne fait aucun appel réseau.
- Les versions, roues et comportements de long-form cités par la recherche documentaire restent des hypothèses à vérifier au jalon 0 ; aucun essai n'a été exécuté à ce stade. Le support Python 3.12/Windows/Linux de Flask et Waitress est documentaire ; leur installation combinée et l'arrêt via uv restent à éprouver, sans installation autorisée implicitement par cette révision.
- Le serveur de développement ne télécharge ni moteur ni modèle ; inférences et mesures uniquement sur les PC Linux et Windows des utilisateurs.
