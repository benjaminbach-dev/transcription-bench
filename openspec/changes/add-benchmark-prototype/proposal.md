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
- Un jalon 0 de faisabilité sur PC Linux puis Windows (résolution des verrous, import des moteurs, exécution CPU, court audio et mode hors ligne, puis cycle de vie du serveur web avec moteur factice) reste préalable aux adaptateurs réels, à la qualification effective sous Linux et Windows et aux choix de moteur, famille, fichiers et long-form ; il n'interdit pas le développement et les tests sur le serveur de développement sans moteur réel, sur simulations et audios synthétiques locaux.
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
- Les versions, roues et comportements de long-form cités par la recherche documentaire restent des hypothèses à vérifier au jalon 0 ; aucun essai n'a été exécuté à ce stade. Le support Python 3.12/Windows/Linux de Flask et Waitress est documentaire ; Flask 3.1.3 et Waitress 3.0.2 restent des versions de référence à confirmer, dont l'installation et le fonctionnement sur le serveur de développement sont couverts par l'accord utilisateur sans valoir qualification Windows ni remplacer la sonde 1.7 sur PC, qui demeure obligatoire.
- Le serveur de développement ne télécharge ni moteur ni modèle : développement et tests s'y font avec le moteur factice, des simulations et des audios synthétiques locaux, sans mesure représentative des PC utilisateurs ; inférences réelles et mesures de qualification uniquement sur les PC Linux et Windows.
