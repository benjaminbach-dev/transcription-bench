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
- Un jalon 0 de faisabilité (résolution des verrous, import des moteurs, exécution CPU, court audio et mode hors ligne, cycle de vie du serveur web avec moteur factice, sonde 1.7 par PTY) est acquis sous Linux sur un PC de test le 2026-11-01 et ne conditionne plus l'écriture des adaptateurs réels ; les choix de moteur, famille, fichiers et long-form restent ouverts tant qu'ils ne sont pas vérifiés.
- Vérification Windows sans PC Windows : suite de tests avec moteur factice, installation depuis les verrous (`uv pip sync --no-build`) puis import et exercice du runner et des adaptateurs des trois moteurs, puis inférence courte sur un audio de parole synthétique créé par le job pour les quatre combinaisons (faster-whisper, transcribe.cpp GGUF Whisper, Transformers Whisper, Transformers Parakeet TDT), en jobs indépendants et à déclenchement manuel pour les plus lourds, exécutés en intégration continue GitHub Actions sur runners hébergés Windows x64 ; si la CI s'avère impossible ou si une combinaison échoue durablement, l'état reste bloqué ou partiel et le périmètre n'est révisé que par décision explicite de l'utilisateur.
- Consultation des transcriptions et comparaison, pour un même audio, des résultats produits par différents modèles, moteurs et réglages.

Hors périmètre : diarisation, correction par LLM, streaming, score WER automatique, accélération GPU, support macOS.

## Capabilities

### New Capabilities

- `local-web-interface`: lancement du programme, serveur local et règles de l'interface HTML.
- `engine-management`: moteurs disponibles, installation isolée à la demande, exécution CPU et extensibilité.
- `model-management`: ajout d'un modèle par identifiant Hugging Face, vérification de compatibilité, téléchargement et inventaire local.
- `benchmark-runs`: audios d'entrée, configuration et déroulement des exécutions, mesures et conservation des résultats.
- `results-comparison`: consultation des transcriptions, de leurs métadonnées et comparaison entre exécutions.
- `platform-verification`: niveaux de preuve distincts, vérifications Windows réelles en intégration continue, sécurité et ressources des jobs, audit préalable et publication du dépôt.

### Modified Capabilities

Aucune.

## Impact

- Nouveau code Python à la racine du dépôt, fichiers de dépendances verrouillées par environnement, documentation de lancement.
- Dossiers de données locaux sous `data/` (audios, modèles, environnements des moteurs, résultats), ignorés par Git.
- Dépendances : uv, Python 3.12 géré par uv ; Flask et Waitress avec Jinja2 fourni par Flask, PyAV, huggingface_hub, numpy, psutil dans l'environnement serveur ; faster-whisper, transcribe-cpp, transformers et torch CPU dans leurs environnements respectifs. Pas de framework asynchrone, ORM ou extension de formulaires.
- Accès réseau uniquement sur action explicite : installation d'un moteur, consultation ou téléchargement d'un modèle. Une fois les fichiers présents, l'inférence ne fait aucun appel réseau.
- Un workflow d'intégration continue reste à implémenter après cette révision, tout comme l'audit préalable (visibilité, historique Git, mémoire projet, licences du code et des dépendances, licences ciblées des modèles téléchargés par la CI) et le gate de publication : le dépôt ne devient public qu'après cet audit et une décision explicite ; les jobs n'utilisent aucun secret et ne publient ni poids, ni audio, ni transcription en artéfact ou en cache. Un premier audit du 2026-11-02 conclut à ne pas publier en l'état ; le régime de licence du projet reste à choisir par l'utilisateur, une licence propriétaire restant possible.
- Les versions, roues et comportements de long-form cités par la recherche documentaire restent des hypothèses (niveau documentaire) hors Linux : le jalon 0 Linux a été exécuté le 2026-11-01 et ne vaut pas Windows. Le support Python 3.12/Windows/Linux de Flask et Waitress est documentaire ; Flask 3.1.3 et Waitress 3.0.2 restent des versions de référence, dont l'installation et le fonctionnement sur le serveur de développement sont couverts par l'accord utilisateur sans valoir qualification Windows. La sonde 1.7 sous Linux est exécutée et consignée (port occupé, verrou d'instance, absence de moteur survivant, Ctrl+C par PTY, SIGTERM, arrêt brutal) ; sous Windows, les points vérifiables sans console relèvent de la CI, et la console interactive ainsi que la coupure réseau réelle restent des limites consignées avec leur procédure, sans bloquer les adaptateurs.
- Le serveur de développement ne télécharge ni moteur ni modèle : développement et tests s'y font avec le moteur factice, des simulations et des audios synthétiques locaux, sans mesure représentative des PC utilisateurs ; les inférences réelles et les mesures de qualification se font uniquement sur le PC Linux de test et, sous Windows, dans les jobs d'intégration continue, sans qu'aucune performance PC puisse en être déduite.
