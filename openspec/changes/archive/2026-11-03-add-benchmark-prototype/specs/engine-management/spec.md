# Spec Delta

## Purpose

Gère les moteurs d'inférence de transcription : leur installation isolée à la demande, leur exécution sur CPU uniquement et l'ajout ultérieur de nouveaux moteurs.

## ADDED Requirements

### Requirement: Moteurs fournis
Le programme SHALL proposer les moteurs faster-whisper, transcribe.cpp et Hugging Face Transformers, ainsi qu'un moteur factice réservé au développement qui ne télécharge et n'exécute aucun modèle. L'adaptateur Transformers ne couvre au premier jalon que les familles Whisper et Parakeet TDT ; les autres familles sont des extensions futures.

#### Scenario: Liste des moteurs
- **WHEN** l'utilisateur ouvre la page des moteurs
- **THEN** chaque moteur est listé avec son état (non installé, installation en cours, prêt, échec) et sa version installée le cas échéant

#### Scenario: Famille Transformers non couverte
- **WHEN** l'utilisateur choisit Transformers pour une famille autre que Whisper ou Parakeet TDT
- **THEN** l'ajout est refusé et la famille est présentée comme extension future

#### Scenario: Moteur factice
- **WHEN** une exécution utilise le moteur factice
- **THEN** elle produit une transcription et des mesures simulées clairement identifiées comme factices, sans accès réseau

### Requirement: Installation isolée à la demande
L'installation d'un moteur SHALL être déclenchée explicitement depuis l'interface et créer un environnement Python dédié à ce moteur, à partir de versions verrouillées propres à ce moteur.

#### Scenario: Installation réussie
- **WHEN** l'utilisateur lance l'installation d'un moteur non installé
- **THEN** son environnement dédié est créé, les versions verrouillées installées, et le moteur passe à l'état prêt après contrôle

#### Scenario: Échec d'installation
- **WHEN** l'installation échoue
- **THEN** le moteur passe à l'état échec, le journal d'installation est consultable et les autres moteurs ne sont pas affectés

### Requirement: Installation prête seulement après contrôle
Un moteur MUST NOT être marqué prêt sur le seul code de sortie de l'installation : le programme MUST vérifier que l'import du moteur réussit dans son environnement et que la synchronisation par uv depuis le verrou s'est terminée avec succès. Un environnement sans marqueur d'installation valide après redémarrage MUST être affiché en échec ; l'installation explicite rejoue la synchronisation et le contrôle d'import.

#### Scenario: Import en échec
- **WHEN** l'installation se termine sans erreur mais que l'import du moteur échoue
- **THEN** le moteur reste non prêt, l'erreur est journalisée et le moteur n'est pas proposé pour une exécution

#### Scenario: Installation interrompue
- **WHEN** le serveur redémarre avec un environnement moteur sans marqueur d'installation valide
- **THEN** le moteur est affiché en échec et une nouvelle installation explicite doit réussir sa synchronisation et son contrôle d'import avant de le rendre disponible

### Requirement: Exécution CPU uniquement
Chaque moteur MUST être configuré explicitement pour s'exécuter sur CPU, sans repli automatique vers un autre périphérique, et le périphérique effectivement utilisé MUST être consigné quand le moteur permet de le vérifier.

#### Scenario: Machine disposant d'un GPU
- **WHEN** une exécution démarre sur une machine équipée d'un GPU compatible
- **THEN** le moteur est configuré pour le CPU et les métadonnées indiquent le périphérique CPU lorsqu'il est lisible

#### Scenario: Périphérique inattendu
- **WHEN** le moteur rapporte un périphérique autre que CPU
- **THEN** l'exécution est arrêtée en erreur avec ce motif

### Requirement: Nombre de threads maîtrisé
Le nombre de threads CPU SHALL être réglable par exécution pour les trois moteurs. La valeur demandée MUST être consignée ; la valeur appliquée MUST être consignée lorsque l'API du moteur permet de la relire, sans jamais l'affirmer dans le cas contraire.

#### Scenario: Threads imposés
- **WHEN** l'utilisateur fixe un nombre de threads pour une exécution
- **THEN** le moteur reçoit cette valeur et les métadonnées contiennent le nombre demandé

#### Scenario: Valeur appliquée lisible
- **WHEN** le moteur expose une API permettant de relire le nombre de threads effectif
- **THEN** cette valeur est relue et consignée à côté du nombre demandé

### Requirement: Moteur exécuté hors du serveur
Chaque exécution SHALL être réalisée dans un processus séparé utilisant l'environnement du moteur, de sorte qu'un plantage du moteur n'arrête pas le serveur.

#### Scenario: Plantage du moteur
- **WHEN** le processus du moteur se termine anormalement
- **THEN** l'exécution est marquée en échec avec le message d'erreur disponible, et le serveur reste utilisable

### Requirement: Événements du moteur isolés de la sortie parasite
Le programme MUST distinguer les événements structurés du moteur des autres lignes écrites sur sa sortie standard : seules les lignes au format d'événement convenu sont interprétées, les autres sont journalisées sans provoquer d'échec.

#### Scenario: Bibliothèque bavarde
- **WHEN** une bibliothèque du moteur écrit une ligne non structurée sur la sortie standard
- **THEN** cette ligne est conservée dans le journal et l'exécution poursuit normalement

### Requirement: Ajout de moteurs
L'ajout d'un nouveau moteur SHALL nécessiter uniquement une déclaration sans dépendance moteur, un adaptateur d'exécution et sa liste de dépendances verrouillées, sans modification des fonctionnalités d'exécution, de stockage ou de comparaison.

#### Scenario: Nouveau moteur déclaré
- **WHEN** un adaptateur conforme et ses dépendances sont ajoutés au programme
- **THEN** le moteur apparaît dans l'interface et peut être installé et utilisé comme les autres
