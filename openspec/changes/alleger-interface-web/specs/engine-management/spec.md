## MODIFIED Requirements

### Requirement: Moteurs fournis
Le programme SHALL proposer les moteurs faster-whisper, transcribe.cpp et Hugging Face Transformers, ainsi qu'un moteur factice réservé au développement qui ne télécharge et n'exécute aucun modèle. L'adaptateur Transformers ne couvre au premier jalon que les familles Whisper et Parakeet TDT ; les autres familles sont des extensions futures.

#### Scenario: Liste des moteurs
- **WHEN** l'utilisateur exécute `engines list`
- **THEN** chaque moteur est listé avec son état (non installé, installation en cours, prêt, échec) et sa version installée le cas échéant

#### Scenario: Famille Transformers non couverte
- **WHEN** l'utilisateur choisit Transformers pour une famille autre que Whisper ou Parakeet TDT
- **THEN** l'ajout est refusé et la famille est présentée comme extension future

#### Scenario: Moteur factice
- **WHEN** une exécution utilise le moteur factice
- **THEN** elle produit une transcription et des mesures simulées clairement identifiées comme factices, sans accès réseau

### Requirement: Installation isolée à la demande
L'installation d'un moteur SHALL être déclenchée explicitement par la commande `engines install` et créer un environnement Python dédié à ce moteur, à partir de versions verrouillées propres à ce moteur.

#### Scenario: Installation réussie
- **WHEN** l'utilisateur lance l'installation d'un moteur non installé
- **THEN** son environnement dédié est créé, les versions verrouillées installées, et le moteur passe à l'état prêt après contrôle

#### Scenario: Échec d'installation
- **WHEN** l'installation échoue
- **THEN** le moteur passe à l'état échec, le journal d'installation est consultable par `engines log` et les autres moteurs ne sont pas affectés

### Requirement: Ajout de moteurs
L'ajout d'un nouveau moteur SHALL nécessiter uniquement une déclaration sans dépendance moteur, un adaptateur d'exécution et sa liste de dépendances verrouillées, sans modification des fonctionnalités d'exécution, de stockage ou de comparaison.

#### Scenario: Nouveau moteur déclaré
- **WHEN** un adaptateur conforme et ses dépendances sont ajoutés au programme
- **THEN** le moteur apparaît dans `engines list` et peut être installé et utilisé comme les autres
