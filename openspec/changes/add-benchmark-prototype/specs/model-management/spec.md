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
Le programme MUST vérifier, à partir de la liste des fichiers et de métadonnées légères du dépôt, que le modèle correspond à un format, une famille et un jeu de fichiers pris en charge par le moteur choisi, et MUST refuser clairement un modèle incompatible.

#### Scenario: Modèle compatible
- **WHEN** le dépôt correspond à une famille prise en charge par le moteur
- **THEN** l'interface affiche la famille détectée, la révision résolue, les fichiers à télécharger et leur taille totale

#### Scenario: Modèle incompatible
- **WHEN** le dépôt n'a pas le format attendu ou appartient à une famille non prise en charge
- **THEN** l'ajout est refusé avec la raison et, si elle est connue, l'indication d'un moteur compatible

### Requirement: Règles de compatibilité par moteur
Pour faster-whisper, le dépôt MUST être au format CTranslate2. Pour transcribe.cpp, il MUST contenir un fichier GGUF d'une architecture prise en charge. Pour Transformers, son type de modèle MUST appartenir aux familles prises en charge par l'adaptateur, soit Whisper et Parakeet TDT au premier jalon.

#### Scenario: Poids CTranslate2
- **WHEN** un dépôt CTranslate2 compatible contient `model.bin` et les fichiers requis pour faster-whisper
- **THEN** il est accepté pour faster-whisper ; la restriction safetensors s'applique uniquement à Transformers

#### Scenario: Whisper au format Transformers proposé à faster-whisper
- **WHEN** l'utilisateur choisit faster-whisper pour un dépôt Whisper non converti en CTranslate2
- **THEN** l'ajout est refusé, aucune conversion n'est lancée, et Transformers est indiqué comme moteur possible

#### Scenario: Dépôt GGUF à plusieurs quantifications
- **WHEN** un dépôt pour transcribe.cpp contient plusieurs fichiers GGUF
- **THEN** l'utilisateur choisit le fichier à télécharger et seule cette variante est téléchargée

#### Scenario: Famille Transformers hors périmètre
- **WHEN** le type de modèle du dépôt n'est ni Whisper ni Parakeet TDT
- **THEN** l'ajout pour Transformers est refusé et la famille est annoncée comme extension future

### Requirement: Fichiers requis par famille
Les fichiers téléchargés et chargés MUST appartenir à une liste blanche complète propre au moteur et à la famille ; tout autre fichier est ignoré. Un dépôt incomplet MUST être refusé. Pour Transformers, la liste couvre les safetensors, leurs index et shards éventuels, les configurations requises (modèle, processor, préprocesseur, génération) et les fichiers de tokenizer/vocabulaire. L'absence de `auto_map` ne suffit pas à prouver la compatibilité.

#### Scenario: Préprocesseur ou tokenizer manquant
- **WHEN** le dépôt contient les poids et la configuration du modèle mais aucun fichier de préprocesseur ou de tokenizer requis
- **THEN** l'ajout est refusé en indiquant les fichiers manquants

#### Scenario: Dépôt sans auto_map mais incomplet
- **WHEN** un dépôt ne déclare pas de `auto_map` mais ne fournit pas la liste de fichiers attendue pour sa famille
- **THEN** l'ajout est refusé : l'absence de `auto_map` n'est pas traitée comme une preuve de compatibilité

### Requirement: Aucun code distant ni poids pickle
Le programme MUST NOT exécuter de code fourni par un dépôt de modèle et MUST refuser un dépôt qui l'exige. Pour Transformers, seuls les poids au format safetensors sont acceptés ; les variantes `.bin`, `.pt` ou `.pth` MUST NOT être téléchargées ni chargées pour ce moteur.

#### Scenario: Dépôt exigeant du code distant
- **WHEN** la configuration du dépôt requiert l'exécution de code personnalisé
- **THEN** l'ajout est refusé avec ce motif

#### Scenario: Dépôt avec plusieurs formats de poids
- **WHEN** un dépôt Transformers propose une variante safetensors complète et des variantes pickle
- **THEN** seuls les poids safetensors et leurs fichiers auxiliaires autorisés sont sélectionnés ; les autres formats, notamment pickle, NeMo et GGUF, sont ignorés

#### Scenario: Poids au format pickle
- **WHEN** un dépôt Transformers ne propose ses poids qu'en `.bin`, `.pt` ou `.pth`
- **THEN** l'ajout est refusé et seuls les dépôts proposant des safetensors sont acceptés

### Requirement: Téléchargement explicite à révision figée
Le téléchargement SHALL être lancé explicitement après la vérification, porter uniquement sur les fichiers nécessaires et enregistrer la révision exacte (commit) du dépôt.

#### Scenario: Téléchargement réussi
- **WHEN** l'utilisateur valide le téléchargement d'un modèle compatible
- **THEN** les fichiers sont stockés dans le dossier local des modèles et le modèle devient sélectionnable pour une exécution avec sa révision exacte

#### Scenario: Interruption
- **WHEN** le téléchargement échoue ou est interrompu
- **THEN** le modèle n'est pas marqué prêt et l'erreur est affichée

### Requirement: Exécution hors ligne après téléchargement
Une fois les fichiers présents, l'inférence MUST s'exécuter sans accès réseau : le programme MUST imposer le mode hors ligne de Hugging Face et `local_files_only` lorsque l'API du moteur le permet, avec `trust_remote_code` désactivé.

#### Scenario: Réseau indisponible pendant une exécution
- **WHEN** le réseau est coupé et qu'un modèle déjà téléchargé est exécuté
- **THEN** l'exécution se déroule normalement à partir des fichiers locaux

#### Scenario: Fichier local manquant
- **WHEN** un fichier nécessaire au modèle est absent du dossier local malgré son inventaire
- **THEN** l'exécution échoue avec un message explicite, sans tentative de téléchargement implicite

### Requirement: Dépôts à accès restreint
L'accès aux dépôts restreints SHALL utiliser le jeton Hugging Face déjà configuré sur le poste par les moyens standards ; le programme MUST NOT stocker ni afficher ce jeton.

#### Scenario: Accès refusé
- **WHEN** le dépôt exige l'acceptation de conditions ou un jeton absent
- **THEN** l'interface indique que l'accès est refusé et comment fournir un jeton, sans afficher de secret

### Requirement: Inventaire des modèles locaux
L'interface SHALL lister les modèles prêts avec leur moteur, identifiant, révision, variante ou quantification, famille et taille sur disque, et permettre leur suppression locale.

#### Scenario: Suppression d'un modèle
- **WHEN** l'utilisateur supprime un modèle local inutilisé
- **THEN** ses fichiers sont retirés du dossier des modèles et les résultats déjà produits restent consultables

### Requirement: Suppression d'un modèle actif interdite
La suppression d'un modèle MUST être refusée tant qu'une exécution l'utilise.

#### Scenario: Suppression pendant une exécution
- **WHEN** l'utilisateur demande la suppression du modèle utilisé par l'exécution active
- **THEN** la suppression est refusée avec l'indication de l'exécution en cours et les fichiers du modèle restent en place
