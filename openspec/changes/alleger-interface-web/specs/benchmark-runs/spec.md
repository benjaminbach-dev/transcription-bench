## MODIFIED Requirements

### Requirement: Audios d'entrée
Le programme SHALL lister les fichiers audio wav, mp3, m4a, ogg, opus et flac présents dans le dossier d'entrée prédéfini, avec leur durée indicative, et signaler les fichiers illisibles sans interrompre la liste.

#### Scenario: Dépôt de fichiers
- **WHEN** l'utilisateur dépose des audios dans le dossier d'entrée puis exécute `audios list`
- **THEN** les fichiers lisibles apparaissent avec leur durée indicative, et les fichiers illisibles avec un message d'erreur

### Requirement: Configuration d'une exécution
Une exécution SHALL associer un modèle prêt, un moteur compatible, un ou plusieurs audios ordonnés, les threads demandés et les seuls réglages pris en charge. `run options` présente les modèles exécutables ou non avec leur motif, les audios proposables, les threads par défaut et les réglages applicables avec leurs valeurs par défaut.

#### Scenario: Réglages proposés
- **WHEN** l'utilisateur exécute `run options` pour un modèle
- **THEN** seuls les réglages applicables à ce modèle et à son moteur sont présentés, avec leurs défauts, et un réglage étranger à la famille est refusé par `run check` et `run start`

### Requirement: Traitement séquentiel des audios
Dans une exécution, les audios SHALL être traités un par un, avec un seul chargement du modèle, et le résultat de chaque audio MUST être enregistré dès qu'il est produit. Le refus d'une nouvelle opération concurrente relève de `cli-interface`.

#### Scenario: Lot de plusieurs audios
- **WHEN** une exécution porte sur trois audios
- **THEN** le modèle est chargé une fois, les audios sont transcrits successivement et chaque résultat est enregistré dès qu'il est produit

### Requirement: Sélections compatibles et stables
Le choix de modèle SHALL identifier une ressource locale précise, variante et révision comprises. `run options` présente les modèles exécutables ou non avec leur motif ; seules les combinaisons réellement prêtes et compatibles sont proposées comme exécution, et le remplacement d'une référence périmée suppose qu'un choix applicable existe. Une vérification ou une préparation n'installe, ne convertit, ne télécharge ni ne lance rien.

#### Scenario: Un seul moteur applicable
- **WHEN** le modèle choisi n'est utilisable qu'avec un moteur prêt
- **THEN** ce moteur est retenu sans suggérer que les autres moteurs peuvent exploiter les mêmes fichiers

#### Scenario: Changement de modèle
- **WHEN** l'utilisateur relance `run options --model REF` avec un autre modèle ou une autre variante
- **THEN** la préparation affichée suit le nouveau choix, une référence périmée étant remplacée par le choix applicable avec une annonce courte lorsqu'un choix applicable existe ; un réglage inapplicable au nouveau modèle est refusé par `run check` et `run start` avec le code 2 en le nommant

#### Scenario: Combinaison forgée ou périmée
- **WHEN** une commande reçoit un moteur incompatible, une référence périmée, un doublon de champ unique ou des réglages étrangers à la famille
- **THEN** elle refuse explicitement la demande avec le code 2, sans lancement

## REMOVED Requirements

### Requirement: Préparation simple et lots optionnels
**Reason**: exigence de présentation du formulaire web d'exécution, supprimé.
**Migration**: `run options`, `run check` et `run start` avec `--audio` répétable et ordonné (exigence « Préparation, vérification à blanc et lancement d'une exécution » de `cli-interface`).

### Requirement: Séparation de la préparation et du lancement
**Reason**: exigence propre aux formulaires web (GET de préparation, POST protégés), supprimés.
**Migration**: `run options` et `run check` sont des lectures sans effet ; `run start` est la seule action, dans le créneau unique (`cli-interface`).
