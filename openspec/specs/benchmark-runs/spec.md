# benchmark-runs Specification

## Purpose
Définit comment les audios déposés localement sont transcrits par un modèle, avec quels réglages, quelles mesures et comment chaque résultat est conservé pour être comparé.

## Requirements

### Requirement: Audios d'entrée
Le programme SHALL lister les fichiers audio wav, mp3, m4a, ogg, opus et flac présents dans le dossier d'entrée prédéfini, avec leur durée indicative, et signaler les fichiers illisibles sans interrompre la liste.

#### Scenario: Dépôt de fichiers
- **WHEN** l'utilisateur dépose des audios dans le dossier d'entrée puis actualise la page
- **THEN** les fichiers lisibles apparaissent avec leur durée indicative, et les fichiers illisibles avec un message d'erreur

### Requirement: Entrée audio identique pour tous les moteurs
Chaque audio SHALL être décodé par le programme en un signal mono 16 kHz commun transmis à tous les moteurs. La durée décodée MUST être consignée et servir de référence pour le RTF, distincte de la durée indicative de la liste.

#### Scenario: Même audio, moteurs différents
- **WHEN** un même fichier est transcrit par deux moteurs
- **THEN** les deux reçoivent un signal identique et les métadonnées contiennent la même empreinte du fichier source et la même durée décodée

#### Scenario: Durée indicative différente de la durée décodée
- **WHEN** la durée annoncée lors du listage diffère de la durée réellement décodée
- **THEN** les deux valeurs sont consignées et le RTF est calculé sur la durée décodée

### Requirement: Configuration d'une exécution
Une exécution SHALL associer un modèle prêt, un moteur compatible, un ou plusieurs audios, les threads demandés et les seuls réglages pris en charge. La préparation présente une seule sélection Modèle, Audio, Moteur, avec valeurs par défaut et réglages avancés facultatifs, et non un formulaire complet répété par modèle.

#### Scenario: Réglages proposés
- **WHEN** un modèle et son moteur sont sélectionnés
- **THEN** seuls les réglages applicables à cette combinaison sont proposés, leurs défauts sont utilisables sans ouvrir les réglages avancés et aucun contrôle actif d'une ancienne combinaison n'est soumis

### Requirement: Langue de transcription
Le français SHALL être imposé comme langue de transcription lorsque le moteur et le modèle le permettent ; sinon les métadonnées MUST indiquer que la langue n'a pas été imposée.

#### Scenario: Modèle sans choix de langue
- **WHEN** la famille du modèle ne permet pas d'imposer la langue
- **THEN** l'exécution se déroule et les métadonnées indiquent l'absence de langue imposée

### Requirement: Traitement séquentiel des audios
Dans une exécution, les audios SHALL être traités un par un, avec un seul chargement du modèle, et le résultat de chaque audio MUST être enregistré dès qu'il est produit. Le refus d'une nouvelle exécution concurrente relève de la spec de l'interface locale.

#### Scenario: Lot de plusieurs audios
- **WHEN** une exécution porte sur trois audios
- **THEN** le modèle est chargé une fois, les audios sont transcrits successivement et chaque résultat est enregistré dès qu'il est produit

### Requirement: Arrêt d'une exécution
L'utilisateur SHALL pouvoir arrêter l'exécution active ; les résultats déjà produits sont conservés et l'exécution est marquée interrompue.

#### Scenario: Arrêt pendant un lot
- **WHEN** l'utilisateur arrête une exécution après le premier audio d'un lot
- **THEN** la transcription du premier audio est conservée et les audios restants sont marqués non traités

### Requirement: Clôture d'une exécution abandonnée
Une exécution laissée en cours après un arrêt brutal du serveur MUST être finalisée en état abandonné au redémarrage. Le moteur survivant MUST être terminé si son identité enregistrée (PID et heure de création) est vérifiée. Les résultats déjà enregistrés MUST être conservés et les audios sans résultat signalés non traités ; les retranscrire SHALL créer une nouvelle exécution.

#### Scenario: Redémarrage après arrêt brutal
- **WHEN** le serveur redémarre et trouve une exécution restée en cours
- **THEN** elle est marquée abandonnée, ses résultats restent consultables et ses audios non traités peuvent être sélectionnés dans une nouvelle exécution

### Requirement: État mutable puis immuable d'un résultat
Le fichier de suivi d'une exécution SHALL évoluer pendant son déroulement, puis devenir immuable une fois son état final atteint. La clôture automatique d'une exécution abandonnée constitue sa finalisation, pas une reprise du traitement.

#### Scenario: Exécution terminée
- **WHEN** une exécution atteint son état final
- **THEN** son fichier de suivi n'est plus modifié, même si les mêmes audios sont retranscrits ensuite

### Requirement: Audios longs
Chaque exécution MUST consigner, pour chaque audio, la méthode de traitement retenue : mécanisme natif vérifié du moteur, ou découpage par le programme en fenêtres fixes de 30 s sans recouvrement, avec la durée de fenêtre effective.

#### Scenario: Famille sans mécanisme long natif vérifié
- **WHEN** un audio dépasse la durée que la famille traite nativement, ou que le mécanisme natif n'a pas été vérifié
- **THEN** le programme le découpe en fenêtres de 30 s, concatène les textes et consigne la méthode et la durée de fenêtre pour cet audio

### Requirement: Mesures enregistrées
Le programme SHALL mesurer la durée totale de l'opération, décodage, chargement, inférence et écriture des résultats compris, ainsi que la durée du processus moteur, le temps de chargement, et pour chaque audio sa durée décodée, son temps de décodage séparé, son temps de transcription, son RTF (temps de transcription / durée décodée) et le temps CPU consommé.

#### Scenario: Audio transcrit
- **WHEN** un audio est transcrit
- **THEN** ses mesures sont enregistrées en valeurs brutes, sans pourcentage, avec leurs unités, et la durée totale de l'opération est distincte de la durée du processus moteur

#### Scenario: Audio de durée décodée nulle
- **WHEN** un fichier est décodé sans aucun échantillon
- **THEN** l'audio est marqué en erreur, aucun RTF n'est calculé et l'exécution continue avec les audios suivants

### Requirement: Pic de mémoire du moteur
Le programme SHALL enregistrer le pic de mémoire résidente du processus moteur depuis son démarrage, chargement du modèle inclus, relevé après le chargement puis après chaque audio et consigné comme valeur cumulative.

#### Scenario: Pic de mémoire
- **WHEN** une exécution se termine normalement
- **THEN** le pic de mémoire cumulatif du processus moteur est enregistré, avec le mode de chargement des poids si le moteur le précise

### Requirement: Mesures partielles explicites
Les mesures indisponibles MUST être signalées comme absentes, jamais remplacées par zéro. Après interruption ou échec, les durées disponibles SHALL aller jusqu'à la clôture et la sortie du moteur ; le pic mémoire SHALL être le dernier relevé transmis, signalé comme partiel. Après abandon, les durées totale et du processus MUST être inconnues, avec conservation des mesures d'audios déjà écrites.

#### Scenario: Abandon sans mesures finales
- **WHEN** le serveur clôture une exécution abandonnée
- **THEN** les durées finales inconnues restent absentes et le dernier pic mémoire transmis est identifié comme partiel

### Requirement: RTF repère non bloquant
Le RTF SHALL être affiché avec le repère d'objectif 2 sans jamais bloquer, exclure ni marquer en échec une exécution plus lente.

#### Scenario: RTF supérieur à 2
- **WHEN** un audio est transcrit avec un RTF de 3
- **THEN** la transcription est enregistrée normalement et le RTF est simplement indiqué au-dessus du repère

### Requirement: Métadonnées complètes
Chaque transcription MUST être accompagnée de métadonnées couvrant l'audio, le modèle, le moteur, les réglages effectifs, les threads, le découpage, la machine, le programme et la date.

#### Scenario: Contenu des métadonnées
- **WHEN** une transcription est enregistrée
- **THEN** elle contient l'audio (nom, empreinte, durée indicative et décodée, format, ordre dans l'exécution), le modèle (identifiant, révision, fichier ou quantification, famille), le moteur et ses versions, les réglages effectifs défauts compris, les threads demandés et, si vérifiables, appliqués, le découpage, la machine (OS, CPU, cœurs physiques et logiques, RAM totale), le programme (version, commit si disponible, version de Python, empreinte du verrou, versions de PyAV et FFmpeg) et la date

#### Scenario: Réglage laissé par défaut
- **WHEN** l'utilisateur ne modifie pas un réglage
- **THEN** sa valeur par défaut effective figure dans les métadonnées

#### Scenario: Threads appliqués inconnus
- **WHEN** l'API du moteur ne permet pas de relire le nombre de threads appliqué
- **THEN** le nombre demandé est consigné et aucun nombre appliqué n'est affirmé

### Requirement: Conservation sans écrasement
Chaque exécution SHALL être enregistrée dans un emplacement unique contenant ses métadonnées, ses mesures et, pour chaque audio, la transcription et les segments horodatés si le moteur les fournit ; les transcriptions déjà produites et les exécutions finalisées ne sont pas modifiées.

#### Scenario: Même audio retranscrit
- **WHEN** un audio déjà transcrit est transcrit de nouveau avec la même configuration
- **THEN** un nouveau résultat est créé et le précédent reste inchangé

#### Scenario: Échec sur un audio
- **WHEN** la transcription d'un audio échoue dans un lot
- **THEN** l'erreur est enregistrée pour cet audio et l'exécution continue avec les audios suivants

### Requirement: Écriture atomique des résultats
Chaque fichier JSON de résultat MUST être écrit dans un fichier temporaire puis remplacé atomiquement ; une interruption MUST NOT laisser de JSON tronqué.

#### Scenario: Interruption pendant l'écriture
- **WHEN** le serveur est arrêté pendant l'écriture d'un fichier de résultat
- **THEN** le fichier de résultat reste absent ou dans son état précédent complet, jamais partiellement écrit

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
