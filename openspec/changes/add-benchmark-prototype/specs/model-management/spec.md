# Spec Delta

## Purpose

Permet d'ajouter librement un modèle par identifiant Hugging Face pour un moteur donné, de vérifier sa compatibilité avant téléchargement, puis de le télécharger à une révision figée.

## ADDED Requirements

### Requirement: Ajout d'un modèle par identifiant
L'utilisateur SHALL pouvoir ajouter un modèle en saisissant un identifiant Hugging Face, en choisissant un moteur installé et, facultativement, une révision ; des exemples de modèles connus MAY être proposés sans limiter ce choix.

#### Scenario: Saisie d'un identifiant
- **WHEN** l'utilisateur soumet un identifiant et un moteur
- **THEN** le programme lance la vérification de compatibilité sans télécharger les poids

### Requirement: Vérification de compatibilité avant téléchargement
Le programme MUST vérifier, à partir de la liste des fichiers et de métadonnées légères du dépôt, que le modèle correspond à un format et une famille pris en charge par le moteur choisi, et MUST refuser clairement un modèle incompatible.

#### Scenario: Modèle compatible
- **WHEN** le dépôt correspond à une famille prise en charge par le moteur
- **THEN** l'interface affiche la famille détectée, la révision résolue, les fichiers à télécharger et leur taille totale

#### Scenario: Modèle incompatible
- **WHEN** le dépôt n'a pas le format attendu ou appartient à une famille non prise en charge
- **THEN** l'ajout est refusé avec la raison et, si elle est connue, l'indication d'un moteur compatible

### Requirement: Règles de compatibilité par moteur
Pour faster-whisper, le dépôt MUST être au format CTranslate2. Pour transcribe.cpp, il MUST contenir un fichier GGUF d'une architecture prise en charge. Pour Transformers, son type de modèle MUST appartenir aux familles prises en charge par l'adaptateur.

#### Scenario: Whisper au format Transformers proposé à faster-whisper
- **WHEN** l'utilisateur choisit faster-whisper pour un dépôt Whisper non converti en CTranslate2
- **THEN** l'ajout est refusé, aucune conversion n'est lancée, et Transformers est indiqué comme moteur possible

#### Scenario: Dépôt GGUF à plusieurs quantifications
- **WHEN** un dépôt pour transcribe.cpp contient plusieurs fichiers GGUF
- **THEN** l'utilisateur choisit le fichier à télécharger et seule cette variante est téléchargée

### Requirement: Aucun code distant exécuté
Le programme MUST NOT exécuter de code fourni par un dépôt de modèle ; un modèle qui l'exige est refusé.

#### Scenario: Dépôt exigeant du code distant
- **WHEN** la configuration du dépôt requiert l'exécution de code personnalisé
- **THEN** l'ajout est refusé avec ce motif

### Requirement: Téléchargement explicite à révision figée
Le téléchargement SHALL être lancé explicitement après la vérification, porter uniquement sur les fichiers nécessaires et enregistrer la révision exacte (commit) du dépôt.

#### Scenario: Téléchargement réussi
- **WHEN** l'utilisateur valide le téléchargement d'un modèle compatible
- **THEN** les fichiers sont stockés dans le dossier local des modèles et le modèle devient sélectionnable pour une exécution avec sa révision exacte

#### Scenario: Interruption
- **WHEN** le téléchargement échoue ou est interrompu
- **THEN** le modèle n'est pas marqué prêt et l'erreur est affichée

### Requirement: Dépôts à accès restreint
L'accès aux dépôts restreints SHALL utiliser le jeton Hugging Face déjà configuré sur le poste par les moyens standards ; le programme MUST NOT stocker ni afficher ce jeton.

#### Scenario: Accès refusé
- **WHEN** le dépôt exige l'acceptation de conditions ou un jeton absent
- **THEN** l'interface indique que l'accès est refusé et comment fournir un jeton, sans afficher de secret

### Requirement: Inventaire des modèles locaux
L'interface SHALL lister les modèles prêts avec leur moteur, identifiant, révision, variante ou quantification, famille et taille sur disque, et permettre leur suppression locale.

#### Scenario: Suppression d'un modèle
- **WHEN** l'utilisateur supprime un modèle local
- **THEN** ses fichiers sont retirés du dossier des modèles et les résultats déjà produits restent consultables
