## MODIFIED Requirements

### Requirement: Ajout d'un modèle par identifiant
L'utilisateur SHALL pouvoir ajouter un modèle en fournissant à `models check` ou `models download` un identifiant Hugging Face, un moteur installé et, facultativement, une révision et un fichier GGUF ; la documentation MAY citer des modèles connus sans limiter ce choix.

#### Scenario: Saisie d'un identifiant
- **WHEN** l'utilisateur exécute `models check` avec un identifiant et un moteur
- **THEN** le programme lance la vérification de compatibilité sans télécharger les poids

### Requirement: Vérification de compatibilité avant téléchargement
Le programme MUST vérifier, à partir de la liste des fichiers et de métadonnées légères du dépôt, que le modèle correspond à un format, une famille et un jeu de fichiers pris en charge par le moteur choisi, et MUST refuser clairement un modèle incompatible.

#### Scenario: Modèle compatible
- **WHEN** le dépôt correspond à une famille prise en charge par le moteur
- **THEN** la commande affiche la famille détectée, la révision résolue, les fichiers à télécharger et leur taille totale

#### Scenario: Modèle incompatible
- **WHEN** le dépôt n'a pas le format attendu ou appartient à une famille non prise en charge
- **THEN** l'ajout est refusé avec la raison et, si elle est connue, l'indication d'un moteur compatible

### Requirement: Dépôts à accès restreint
L'accès aux dépôts restreints SHALL utiliser le jeton Hugging Face déjà configuré sur le poste par les moyens standards ; le programme MUST NOT stocker ni afficher ce jeton.

#### Scenario: Accès refusé
- **WHEN** le dépôt exige l'acceptation de conditions ou un jeton absent
- **THEN** la commande indique que l'accès est refusé et comment fournir un jeton, sans afficher de secret

## REMOVED Requirements

### Requirement: Inventaire des modèles locaux
**Reason**: la page Modèles est supprimée.
**Migration**: `models list` présente l'inventaire ; `models delete` supprime un modèle local (exigence « Suppression de modèle protégée » de `cli-interface`).

### Requirement: Ajout secondaire explicite
**Reason**: la page Modèles et son formulaire d'ajout sont supprimés.
**Migration**: `models check` puis `models download` (exigence « Téléchargement explicite d'un modèle vérifié » de `cli-interface`).
