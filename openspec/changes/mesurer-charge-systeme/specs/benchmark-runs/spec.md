## MODIFIED Requirements

### Requirement: Mesures enregistrées
Le programme SHALL mesurer la durée totale de l'opération, décodage, chargement, inférence et écriture des résultats compris, ainsi que la durée du processus moteur, le temps de chargement, et pour chaque audio sa durée décodée, son temps de décodage séparé, son temps de transcription, son RTF (temps de transcription / durée décodée) et le temps CPU consommé.

#### Scenario: Audio transcrit
- **WHEN** un audio est transcrit
- **THEN** ses mesures sont enregistrées avec leurs unités et valeurs brutes ; les pourcentages système portent une méthode et un périmètre explicites, les ratios moteur restent dérivables depuis les valeurs brutes et la durée totale de l'opération est distincte de la durée du processus moteur

#### Scenario: Audio de durée décodée nulle
- **WHEN** un fichier est décodé sans aucun échantillon
- **THEN** l'audio est marqué en erreur, aucun RTF n'est calculé et l'exécution continue avec les audios suivants

## ADDED Requirements

### Requirement: Occupation CPU globale pendant un audio
Pour chaque audio transcrit, le programme SHALL tenter de relever l'occupation CPU moyenne de l'ensemble du système sur l'intervalle de transcription, hors chargement du modèle et décodage. La valeur MUST être distincte de celle du moteur et inclure les autres programmes ; 100 % représente tous les processeurs logiques visibles du système.

#### Scenario: Ordinateur occupé par d'autres programmes
- **WHEN** le moteur transcrit un audio pendant que d'autres programmes calculent
- **THEN** le résultat conserve une occupation CPU système moyenne, son intervalle observé et sa méthode ; cette valeur n'est pas attribuée au seul moteur et la part des autres programmes n'est pas déduite par soustraction

#### Scenario: Intervalle trop court ou compteur inexploitable
- **WHEN** l'intervalle monotone observé est absent ou inférieur à 0,1 seconde, qu'un appel de relevé échoue ou que son retour n'est pas numérique, fini et compris entre 0 et 100 %
- **THEN** la mesure système reste indisponible avec un motif, aucun faux zéro d'amorçage n'est enregistré et la transcription n'est pas ralentie pour obtenir une mesure

#### Scenario: Zéro après amorçage valide
- **WHEN** l'API retourne 0 % après un amorçage réussi et un intervalle monotone d'au moins 0,1 seconde
- **THEN** ce zéro est conservé comme retour de l'API ; il n'est pas présenté comme une preuve distinguant une inactivité réelle d'une absence de progression des compteurs système

### Requirement: Instantanés de RAM disponible
Le programme SHALL tenter de consigner la RAM totale et disponible du système après le chargement du modèle et après chaque audio transcrit, avec l'instant du relevé. Chaque valeur MUST être décrite comme un instantané de mémoire disponible estimée par le système, distinct du pic mémoire cumulatif du moteur et d'un minimum pendant l'audio.

#### Scenario: Modèle chargé puis audio terminé
- **WHEN** le modèle a fini de charger puis un audio a fini d'être transcrit
- **THEN** un instantané est associé à chacune de ces frontières, même si l'occupation mémoire change entre les deux ; aucune baisse de RAM disponible n'est annoncée comme consommation attribuable à la transcription

#### Scenario: Mémoire récupérable
- **WHEN** le système distingue mémoire libre et mémoire disponible, notamment par des caches récupérables
- **THEN** l'instantané emploie la mémoire disponible, jamais le simple total moins la mémoire libre ou le RSS du moteur

### Requirement: Collecte système facultative et non bloquante
Une erreur de mesure système MUST NOT faire échouer une transcription ni modifier les règles d'arrêt. Les résultats déjà enregistrés MUST rester immuables ; aucune valeur finale manquante après interruption ou abandon ne doit être reconstruite depuis l'état courant de l'ordinateur.

#### Scenario: Interruption pendant le second audio
- **WHEN** un essai est interrompu ou abandonné après l'enregistrement du premier audio
- **THEN** les relevés du premier audio restent inchangés, l'absence de relevé final du second reste explicite et aucun observateur périodique ni relevé d'un autre essai ne complète les mesures manquantes

### Requirement: Extension compatible des résultats de ressources
Les nouvelles observations SHALL être facultatives et porter leur version de méthode, leur provenance réelle ou simulée et leurs unités. Les anciens résultats MUST rester lisibles sans migration ni réécriture ; les mesures absentes, invalides ou de version inconnue MUST rester explicitement indisponibles, sans empêcher la lecture du texte et des mesures historiques.

#### Scenario: Résultat antérieur aux observations système
- **WHEN** un résultat ne contient aucun nouveau relevé
- **THEN** ses transcriptions et anciennes mesures sont consultables, les observations système sont « non mesurées » et aucune valeur de l'ordinateur courant n'est substituée

#### Scenario: Simulation ou champ additionnel invalide
- **WHEN** le moteur factice est utilisé ou que l'objet d'observation système est mal formé
- **THEN** les observations factices sont simulées de manière déterministe, marquées comme telles et cohérentes avec la provenance du résultat ; un objet invalide ou de provenance contradictoire est ignoré avec un motif sans rejeter un événement audio par ailleurs valide
