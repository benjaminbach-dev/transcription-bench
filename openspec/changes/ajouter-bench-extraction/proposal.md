## Why

Le banc de transcription a rempli son rôle : il a permis de retenir des modèles de transcription française utilisables sur CPU. Mais une transcription mot à mot ne suffit pas aux projets visés : il faut ensuite **synthétiser** une consultation médicale, c'est-à-dire en extraire l'utile, écarter le bavardage et ranger les informations dans une grille structurée (qui, quand, symptômes, examens, doute restant, prescription, posologie, prise en charge…). Cette étape doit elle aussi tourner localement, sur des ordinateurs ordinaires sans GPU (8 à 16 Go de RAM). Il faut donc pouvoir mesurer, comme pour la transcription, ce que consomment des LLM locaux pour ce travail et rendre leur résultat facile à relire.

Le programme ne juge pas la qualité des extractions : un humain ou un agent local, extérieur au programme, compare la grille remplie à la transcription brute ou à l'audio. Le programme mesure les ressources consommées et présente les résultats.

## What Changes

- **Grilles d'extraction** : fichiers Markdown versionnés sous `grilles/`, lisibles par un humain comme par un agent. Un titre `##` = une case, le texte qui suit = la consigne pour le modèle ; « Liste » en tête de consigne = plusieurs entrées ; des sous-titres `###` = case composée (par exemple médicament, posologie, durée). Chaque case accepte « non mentionné ». Une section **Autres informations utiles**, ajoutée d'office, permet au modèle de consigner des éléments hors grille. Le programme convertit la grille en schéma JSON imposé au modèle et consigne son empreinte. Une grille d'exemple de consultation de médecine générale est fournie.
- **Moteur llama.cpp** : nouveau moteur `llama-cpp` (llama-cpp-python, roues CPU précompilées Linux x64 et Windows x64), environnement isolé, poids GGUF, exécution CPU hors ligne, API de bas niveau de llama-cpp-python (sans la classe `Llama`, qui compile les gabarits Jinja embarqués), sortie contrainte par une grammaire convertie et chargée explicitement depuis le schéma (échec franc sinon), format de conversation maintenu localement par architecture, décodage glouton et graine fixe consignés, dépôts restreints refusés. Le moteur factice gagne une famille d'extraction pour les tests.
- **Exécutions d'extraction** : entrée = transcription(s) issue(s) d'exécutions de transcription déjà enregistrées (`identifiant:ordre`), lot séquentiel avec un seul chargement du modèle, contexte insuffisant refusé sans tronquer, sortie tronquée ou non conforme conservée et signalée. Le résultat conserve une copie de la transcription source, de la grille, du schéma et des consignes, sans écrasement.
- **Mesures** (sur une génération token par token) : temps de chargement, tokens du prompt et générés, délai avant le premier token, vitesse de génération, vitesse de lecture estimée, durée de l'extraction, temps CPU, pic de mémoire, contexte système existant. Aucun score de qualité.
- **Consultation** : commandes `grids …` et `extract …` (JSON stable comme les autres) ; pages web en lecture seule « Extractions » (liste groupée par transcription source et grille, détail case par case à côté de la transcription source, comparaison de 2 à 6 modèles case par case) ; l'Historique liste aussi les exécutions d'extraction.
- **Modèles candidats documentés** (Apache 2.0, accès libre, GGUF) en deux paliers : machines 8 Go (Ministral 3 3B Q8_0, Qwen3.5-4B Q4_K_M) et 16 Go (Ministral 3 8B Q4_K_M, Qwen3.5-9B Q4_K_M, Granite 4.2 8B Q4_K_M, Gemma 4 E4B Q8_0). Le choix reste libre par identifiant Hugging Face, dans les règles du moteur.

Hors périmètre : évaluation automatique de la qualité (référence, score, juge LLM), saisie libre de texte source ou import de fichiers texte, enchaînement automatique audio → transcription → extraction, modèles exigeant un accès restreint, GPU, second moteur LLM de comparaison, MedGemma et modèles sous licence restrictive, diffusion clinique.

## Capabilities

### New Capabilities

- `extraction-grids` : format Markdown des grilles, validation, conversion en schéma JSON, section hors grille, empreinte, commandes `grids list|show`.
- `extraction-runs` : préparation et lancement d'une extraction, sources, consignes, sortie contrainte, traitement séquentiel, mesures, métadonnées, conservation, arrêt et récupération.
- `extraction-results` : consultation par commande et pages web en lecture seule, regroupement, détail, comparaison case par case.

### Modified Capabilities

- `engine-management` : moteur llama.cpp et famille factice d'extraction ; une déclaration de moteur indique sa tâche (transcription ou extraction) ; threads réglables pour chaque moteur.
- `model-management` : règles de compatibilité GGUF du moteur llama.cpp (architectures autorisées, fichier unique, fichiers auxiliaires refusés).
- `local-web-interface` : navigation Résultats, Comparaisons, Extractions, Historique ; consultation seule étendue aux pages d'extraction.
- `cli-interface` : couverture des pages d'extraction par des commandes de lecture.
- `results-comparison` : l'Historique liste les exécutions des deux types en les distinguant.

## Impact

- Code : nouveau runner d'extraction et adaptateur `engines/adaptateurs/llama_cpp.py`, déclarations (`engines/declarations.py`), protocole d'événements (nouveaux types), services serveur d'extraction, stockage `data/extractions/`, récupération au démarrage, grilles (`transcription_bench/grilles.py`), consultation, commandes, gabarits web. Aucune bibliothèque de moteur importée dans le serveur.
- Dépendances : nouveau verrou `requirements/llama-cpp.in|txt` (llama-cpp-python 0.3.36, roues CPU de l'index du projet, dernière version disposant de roues CPU Linux x64 et Windows x64 au 2026-11-19). Aucune dépendance ajoutée au serveur.
- Données : `data/extractions/` (hors Git), `grilles/` (versionné, sans donnée personnelle).
- Documentation : guide, technique, `docs/licences-modeles.md`, `AGENTS.md` (périmètre étendu à l'extraction, moteur supplémentaire).
- Préalables : `alleger-interface-web` archivé avant ce change ; essai minimal sur le PC de test Linux (roue, un modèle, grammaire, mesures) avant l'adaptateur réel, puis qualification réelle du moteur et des modèles sur le PC de test Linux, avec accord explicite au moment voulu (environ 31 Go de poids pour les six modèles). Vérification Windows uniquement si le propriétaire autorise une extension de la CI.
- La rédaction de ce change n'autorise aucune installation, aucun téléchargement ni aucune inférence réelle.
