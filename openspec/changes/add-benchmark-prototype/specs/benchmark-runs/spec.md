# Spec Delta

## Purpose

Définit comment les audios déposés localement sont transcrits par un modèle, avec quels réglages, quelles mesures et comment chaque résultat est conservé pour être comparé.

## ADDED Requirements

### Requirement: Audios d'entrée
Le programme SHALL lister les fichiers audio wav, mp3, m4a, ogg, opus et flac présents dans le dossier d'entrée prédéfini, avec leur durée, et signaler les fichiers illisibles sans interrompre la liste.

#### Scenario: Dépôt de fichiers
- **WHEN** l'utilisateur dépose des audios dans le dossier d'entrée puis actualise la page
- **THEN** les fichiers lisibles apparaissent avec leur durée, et les fichiers illisibles avec un message d'erreur

### Requirement: Entrée audio identique pour tous les moteurs
Chaque audio SHALL être décodé par le programme en un signal mono 16 kHz commun transmis à tous les moteurs ; le temps de décodage MUST être mesuré séparément du temps de transcription.

#### Scenario: Même audio, moteurs différents
- **WHEN** un même fichier est transcrit par deux moteurs
- **THEN** les deux reçoivent un signal identique et les métadonnées contiennent la même empreinte du fichier source

### Requirement: Configuration d'une exécution
Une exécution SHALL associer un modèle prêt, un ou plusieurs audios sélectionnés, le nombre de threads et les réglages de décodage que le moteur et la famille du modèle prennent réellement en charge.

#### Scenario: Réglages proposés
- **WHEN** l'utilisateur prépare une exécution pour un modèle
- **THEN** seuls les réglages applicables à ce moteur et à cette famille sont proposés, avec leurs valeurs par défaut

### Requirement: Langue de transcription
Le français SHALL être imposé comme langue de transcription lorsque le moteur et le modèle le permettent ; sinon les métadonnées MUST indiquer que la langue n'a pas été imposée.

#### Scenario: Modèle sans choix de langue
- **WHEN** la famille du modèle ne permet pas d'imposer la langue
- **THEN** l'exécution se déroule et les métadonnées indiquent l'absence de langue imposée

### Requirement: Traitement séquentiel unique
Une seule exécution SHALL être active à la fois ; ses audios sont traités un par un, avec un seul chargement du modèle par exécution. Une nouvelle exécution MUST être refusée tant qu'une autre est active.

#### Scenario: Lot de plusieurs audios
- **WHEN** une exécution porte sur trois audios
- **THEN** le modèle est chargé une fois, les audios sont transcrits successivement et chaque résultat est enregistré dès qu'il est produit

#### Scenario: Exécution déjà active
- **WHEN** l'utilisateur lance une exécution pendant qu'une autre est active
- **THEN** la demande est refusée avec l'indication de l'exécution en cours

### Requirement: Arrêt d'une exécution
L'utilisateur SHALL pouvoir arrêter l'exécution active ; les résultats déjà produits sont conservés et l'exécution est marquée interrompue.

#### Scenario: Arrêt pendant un lot
- **WHEN** l'utilisateur arrête une exécution après le premier audio d'un lot
- **THEN** la transcription du premier audio est conservée et les audios restants sont marqués non traités

### Requirement: Audios longs
Chaque exécution MUST consigner la méthode de traitement des audios longs : mécanisme natif du moteur, ou découpage par le programme en fenêtres de durée fixe lorsque la famille n'en dispose pas.

#### Scenario: Famille sans mécanisme long natif
- **WHEN** un audio dépasse la durée que la famille traite nativement
- **THEN** le programme le découpe en fenêtres de durée fixe, concatène les textes et consigne la durée des fenêtres

### Requirement: Mesures enregistrées
Le programme SHALL mesurer le temps de chargement du modèle, et pour chaque audio sa durée, le temps de décodage, le temps de transcription, le RTF (temps de transcription / durée audio) et le temps CPU consommé ; ainsi que le pic de mémoire du moteur et la durée totale.

#### Scenario: Audio transcrit
- **WHEN** un audio est transcrit
- **THEN** ses mesures sont enregistrées en valeurs brutes, sans pourcentage, avec leurs unités

#### Scenario: Pic de mémoire
- **WHEN** une exécution se termine
- **THEN** le pic de mémoire résidente du processus moteur depuis son démarrage est enregistré, chargement du modèle inclus, avec le mode de chargement des poids si le moteur le précise

### Requirement: RTF repère non bloquant
Le RTF SHALL être affiché avec le repère d'objectif 2 sans jamais bloquer, exclure ni marquer en échec une exécution plus lente.

#### Scenario: RTF supérieur à 2
- **WHEN** un audio est transcrit avec un RTF de 3
- **THEN** la transcription est enregistrée normalement et le RTF est simplement indiqué au-dessus du repère

### Requirement: Métadonnées complètes
Chaque transcription MUST être accompagnée de l'audio (nom, empreinte, durée, format), du modèle (identifiant, révision, fichier ou quantification, famille), du moteur (nom, versions), des réglages effectifs défauts compris, du découpage, de la machine (OS, CPU, cœurs logiques, RAM totale) et de la date.

#### Scenario: Réglage laissé par défaut
- **WHEN** l'utilisateur ne modifie pas un réglage
- **THEN** sa valeur par défaut effective figure dans les métadonnées

### Requirement: Conservation sans écrasement
Chaque exécution SHALL être enregistrée dans un emplacement unique contenant ses métadonnées, ses mesures et, pour chaque audio, la transcription et les segments horodatés si le moteur les fournit ; aucun résultat existant n'est modifié.

#### Scenario: Même audio retranscrit
- **WHEN** un audio déjà transcrit est transcrit de nouveau avec la même configuration
- **THEN** un nouveau résultat est créé et le précédent reste inchangé

#### Scenario: Échec sur un audio
- **WHEN** la transcription d'un audio échoue dans un lot
- **THEN** l'erreur est enregistrée pour cet audio et l'exécution continue avec les audios suivants
