# results-comparison Specification

## Purpose
Permet de relire les transcriptions produites avec leurs métadonnées et mesures, et de comparer pour un même audio les résultats de différents modèles, moteurs et réglages.

## Requirements

### Requirement: Liste des exécutions
L'interface SHALL lister les exécutions, des plus récentes aux plus anciennes, avec leur date, modèle, moteur, état, nombre d'audios traités et durée totale.

#### Scenario: Consultation de l'historique
- **WHEN** l'utilisateur ouvre la page des résultats
- **THEN** toutes les exécutions enregistrées apparaissent, y compris celles en échec ou interrompues

### Requirement: États des exécutions affichés
Chaque exécution MUST afficher un état explicite et distinct : en cours, terminée, interrompue, abandonnée ou en échec. Les résultats partiels d'une exécution non terminée MUST être accessibles et signalés comme partiels, sans être présentés comme un lot complet.

#### Scenario: Exécution abandonnée
- **WHEN** une exécution a été laissée en cours après un arrêt brutal du serveur
- **THEN** elle apparaît avec l'état abandonné, ses transcriptions disponibles sont consultables et les audios non traités sont signalés

#### Scenario: Comparaison avec un résultat partiel
- **WHEN** l'utilisateur compare des résultats dont certains proviennent d'une exécution non terminée
- **THEN** ces résultats sont identifiés comme partiels

### Requirement: Détail d'une transcription
L'utilisateur SHALL pouvoir lire chaque transcription avec ses segments horodatés éventuels, ses métadonnées et ses mesures.

#### Scenario: Ouverture d'une transcription
- **WHEN** l'utilisateur ouvre une transcription
- **THEN** le texte, les réglages effectifs, les informations de modèle, de moteur et de machine, et les mesures sont affichés

### Requirement: Comparaison par audio
Pour un audio donné, l'interface SHALL afficher côte à côte les transcriptions sélectionnées, avec pour chacune le modèle, le moteur, les réglages qui diffèrent entre elles et les principales mesures.

#### Scenario: Comparaison de deux modèles
- **WHEN** l'utilisateur sélectionne deux transcriptions d'un même audio produites par des modèles différents
- **THEN** elles sont affichées côte à côte avec les différences de configuration, la durée totale de l'opération et leurs mesures

### Requirement: Identité de l'audio comparé
Les transcriptions SHALL être regroupées par empreinte du fichier audio, et non par son seul nom ; les transcriptions de fichiers de même nom mais d'empreintes différentes MUST NOT être présentées comme comparables.

#### Scenario: Fichier modifié sous le même nom
- **WHEN** un audio est remplacé par un fichier différent portant le même nom
- **THEN** les transcriptions de l'ancien et du nouveau fichier apparaissent dans des groupes distincts

### Requirement: Distinction des résultats factices
Les résultats produits par le moteur factice MUST être signalés comme factices dans toutes les vues.

#### Scenario: Liste mêlant résultats réels et factices
- **WHEN** la page des résultats contient une exécution du moteur factice
- **THEN** cette exécution est marquée comme factice
