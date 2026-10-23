# Proposal

## Why

Le projet doit choisir des modèles de transcription française utilisables en local sur des ordinateurs ordinaires, sans GPU dédié. Aucun outil ne permet aujourd'hui de faire transcrire les mêmes audios par plusieurs modèles et moteurs, puis de comparer textes, réglages et coûts mesurés dans des conditions consignées.

## What Changes

- Création d'un programme Python local, lancé par uv, qui démarre un serveur web accessible uniquement depuis la machine.
- Interface en HTML pur (ni CSS ni JavaScript) pour piloter installations, modèles, exécutions et résultats.
- Trois moteurs d'inférence CPU dès le départ : faster-whisper, transcribe.cpp et Hugging Face Transformers, chacun dans un environnement isolé installé à la demande ; structure prévue pour en ajouter d'autres ; moteur factice pour le développement sans modèle.
- Ajout libre d'un modèle par identifiant Hugging Face, vérifié avant téléchargement contre les familles prises en charge par le moteur choisi, puis téléchargé explicitement à une révision figée.
- Exécutions unitaires ou par lot séquentiel sur les audios déposés dans un dossier prédéfini, un seul traitement à la fois, exclusivement sur CPU.
- Conservation sans écrasement de chaque transcription avec ses métadonnées (audio, modèle, moteur, réglages effectifs, machine) et ses mesures (temps de chargement et de transcription, RTF, pic de mémoire, temps CPU).
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
- Dépendances : uv, Python 3.12 géré par uv ; PyAV, huggingface_hub, numpy, psutil ; faster-whisper, transcribe-cpp, transformers et torch CPU dans leurs environnements respectifs.
- Accès réseau uniquement sur action explicite : installation d'un moteur, consultation ou téléchargement d'un modèle.
- Le serveur de développement ne télécharge ni moteur ni modèle ; inférences et mesures uniquement sur les PC Linux et Windows des utilisateurs.
