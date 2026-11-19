## MODIFIED Requirements

### Requirement: Moteurs fournis
Le programme SHALL proposer les moteurs de transcription faster-whisper, transcribe.cpp et Hugging Face Transformers, le moteur d'extraction llama.cpp (llama-cpp-python, poids GGUF), ainsi qu'un moteur factice réservé au développement qui ne télécharge et n'exécute aucun modèle et propose une famille de transcription et une famille d'extraction. L'adaptateur Transformers ne couvre que les familles Whisper et Parakeet TDT ; les autres familles sont des extensions futures.

#### Scenario: Liste des moteurs
- **WHEN** l'utilisateur exécute `engines list`
- **THEN** chaque moteur est listé avec sa tâche (transcription ou extraction), son état (non installé, installation en cours, prêt, échec) et sa version installée le cas échéant

#### Scenario: Famille Transformers non couverte
- **WHEN** l'utilisateur choisit Transformers pour une famille autre que Whisper ou Parakeet TDT
- **THEN** l'ajout est refusé et la famille est présentée comme extension future

#### Scenario: Moteur factice
- **WHEN** une exécution de transcription ou d'extraction utilise le moteur factice
- **THEN** elle produit un résultat et des mesures simulées clairement identifiés comme factices, sans accès réseau

#### Scenario: Installation de llama.cpp sans compilation
- **WHEN** l'utilisateur exécute `engines install llama-cpp` sur Linux x64 ou Windows x64
- **THEN** l'environnement est créé uniquement à partir de roues précompilées CPU du verrou ; si une roue manque, l'installation échoue avec ce motif au lieu de compiler

### Requirement: Nombre de threads maîtrisé
Le nombre de threads CPU SHALL être réglable par exécution pour chaque moteur réel. La valeur demandée MUST être consignée ; la valeur appliquée MUST être consignée lorsque l'API du moteur permet de la relire, sans jamais l'affirmer dans le cas contraire. Pour llama.cpp, la valeur demandée s'applique à la lecture du prompt comme à la génération.

#### Scenario: Threads imposés
- **WHEN** l'utilisateur fixe un nombre de threads pour une exécution
- **THEN** le moteur reçoit cette valeur et les métadonnées contiennent le nombre demandé

#### Scenario: Valeur appliquée lisible
- **WHEN** le moteur expose une API permettant de relire le nombre de threads effectif
- **THEN** cette valeur est relue et consignée à côté du nombre demandé

### Requirement: Ajout de moteurs
L'ajout d'un nouveau moteur SHALL nécessiter uniquement une déclaration sans dépendance moteur indiquant sa tâche (transcription ou extraction), un adaptateur d'exécution respectant le contrat de cette tâche et sa liste de dépendances verrouillées, sans modification des fonctionnalités d'exécution, de stockage ou de comparaison de cette tâche.

#### Scenario: Nouveau moteur déclaré
- **WHEN** un adaptateur conforme et ses dépendances sont ajoutés au programme
- **THEN** le moteur apparaît dans `engines list` avec sa tâche et peut être installé et utilisé comme les autres moteurs de cette tâche

#### Scenario: Tâche respectée
- **WHEN** un modèle d'un moteur d'extraction est proposé à une exécution de transcription, ou l'inverse
- **THEN** la demande est refusée avec le code 2 et ce motif
