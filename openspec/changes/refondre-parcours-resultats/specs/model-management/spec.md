## MODIFIED Requirements

### Requirement: Inventaire des modèles locaux
Modèles SHALL présenter d'abord les modèles locaux prêts : nom, moteur, variante utile, taille lisible et action d'utilisation. Identifiant complet, révision, famille et fichiers restent accessibles en détail avec la suppression locale. La section d'ajout ne précède pas l'inventaire ; les explications générales ne sont pas répétées par modèle.

#### Scenario: Suppression d'un modèle
- **WHEN** l'utilisateur supprime un modèle local inutilisé
- **THEN** ses fichiers sont retirés et les résultats déjà produits restent consultables ; l'explication de conservation des résultats n'est affichée qu'une fois sur la page

#### Scenario: Inventaire non vide
- **WHEN** plusieurs modèles locaux sont prêts
- **THEN** leur liste constitue le premier contenu fonctionnel après le titre et les alertes nécessaires ; l'utilisateur peut aller préparer une exécution avec le modèle choisi sans traverser le formulaire d'ajout

## ADDED Requirements

### Requirement: Ajout secondaire explicite
La page SHALL proposer une entrée Ajouter un modèle après son inventaire ou dans une action secondaire. L'ouverture de cet espace ne vérifie aucun dépôt et ne télécharge rien. La saisie d'identifiant, le moteur installé, la révision facultative et le choix GGUF restent disponibles avec la vérification préalable et le téléchargement séparé.

#### Scenario: Ajout depuis une liste existante
- **WHEN** l'utilisateur ouvre Ajouter un modèle
- **THEN** le formulaire s'affiche sans répéter l'inventaire ni déclencher de réseau ; une vérification ne commence qu'après sa soumission explicite et les fichiers ne sont téléchargés qu'après confirmation dédiée

#### Scenario: Aucun modèle prêt
- **WHEN** l'inventaire est vide
- **THEN** un état vide court met en avant l'ajout ou, si nécessaire, l'installation d'un moteur, sans long inventaire technique vide

#### Scenario: Erreur de vérification
- **WHEN** une vérification refuse un dépôt ou exige un choix de fichier GGUF
- **THEN** le motif et les choix nécessaires sont visibles au même endroit, sans être cachés dans un panneau fermé ni répétés dans chaque modèle prêt
