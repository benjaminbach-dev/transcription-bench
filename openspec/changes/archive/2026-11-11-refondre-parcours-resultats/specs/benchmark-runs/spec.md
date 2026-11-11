## MODIFIED Requirements

### Requirement: Configuration d'une exécution
Une exécution SHALL associer un modèle prêt, un moteur compatible, un ou plusieurs audios, les threads demandés et les seuls réglages pris en charge. La préparation présente une seule sélection Modèle, Audio, Moteur, avec valeurs par défaut et réglages avancés facultatifs, et non un formulaire complet répété par modèle.

#### Scenario: Réglages proposés
- **WHEN** un modèle et son moteur sont sélectionnés
- **THEN** seuls les réglages applicables à cette combinaison sont proposés, leurs défauts sont utilisables sans ouvrir les réglages avancés et aucun contrôle actif d'une ancienne combinaison n'est soumis

## ADDED Requirements

### Requirement: Sélections compatibles et stables
Le choix de modèle SHALL identifier une ressource locale précise, variante et révision comprises. Le moteur ne propose que les combinaisons réellement prêtes et compatibles ; un seul choix est présélectionné. Une modification de sélection n'installe, ne convertit, ne télécharge ni ne lance rien.

#### Scenario: Un seul moteur applicable
- **WHEN** le modèle sélectionné n'est utilisable qu'avec un moteur prêt
- **THEN** le moteur est déjà choisi et lisible sans suggérer que les autres moteurs peuvent exploiter les mêmes fichiers

#### Scenario: Changement de modèle
- **WHEN** l'utilisateur change de modèle ou de variante
- **THEN** les moteurs et réglages disponibles correspondent au nouveau choix ; les audios encore valides restent sélectionnés et les réglages incompatibles sont retirés ou réinitialisés avec une indication courte

#### Scenario: Combinaison forgée ou périmée
- **WHEN** une requête soumet un moteur incompatible, une référence périmée, un doublon de champ unique ou des réglages étrangers à la famille
- **THEN** le serveur refuse explicitement la demande sans lancement, indépendamment des restrictions de l'interface

### Requirement: Préparation simple et lots optionnels
Un audio SHALL être sélectionnable par un contrôle simple dans le cas courant. Un mode lot secondaire conserve la sélection multiple et son ordre séquentiel sans multiplier les panneaux de modèle. Le bouton principal lance l'exécution ; une vérification sans lancement reste une action secondaire.

#### Scenario: Lancement courant
- **WHEN** au moins un modèle exécutable et un audio lisible sont disponibles
- **THEN** un seul panneau présente Modèle, Audio, Moteur et Lancer ; aucun paragraphe sur la méthode interne, aucun commit ni formulaire par modèle ne précède ces contrôles

#### Scenario: Sélection de lot
- **WHEN** l'utilisateur active le mode lot et sélectionne plusieurs audios
- **THEN** il peut connaître leur ordre avant lancement ; le modèle est chargé une fois et les audios restent traités séquentiellement

#### Scenario: Inventaire incomplet
- **WHEN** aucun modèle exécutable ou aucun audio lisible n'est disponible
- **THEN** une explication unique et une action vers Modèles ou Audios remplacent les contrôles inapplicables sans proposer un lancement voué à l'échec

### Requirement: Séparation de la préparation et du lancement
Les changements de sélection et la consultation des défauts SHALL être des lectures sans effet de bord. Lancer et arrêter restent des POST explicites protégés ; une seule opération longue peut être admise. Une demande refusée conserve les choix encore valides ou indique précisément ce qui doit être choisi à nouveau.

#### Scenario: Mise à jour des options
- **WHEN** le navigateur actualise les choix compatibles, automatiquement ou via le contrôle HTML de repli
- **THEN** aucune exécution ni téléchargement ne commence et aucun jeton anti-CSRF n'est placé dans une URL

#### Scenario: Double soumission et opération occupée
- **WHEN** un lancement est soumis deux fois ou pendant une opération active
- **THEN** le serveur n'admet qu'une opération ; le refus signale le suivi intégré sans file d'attente et sans annoncer de lancement supplémentaire
