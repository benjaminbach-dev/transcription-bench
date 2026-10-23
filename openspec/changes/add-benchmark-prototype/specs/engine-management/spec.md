# Spec Delta

## Purpose

Gère les moteurs d'inférence de transcription : leur installation isolée à la demande, leur exécution sur CPU uniquement et l'ajout ultérieur de nouveaux moteurs.

## ADDED Requirements

### Requirement: Moteurs fournis
Le programme SHALL proposer les moteurs faster-whisper, transcribe.cpp et Hugging Face Transformers, ainsi qu'un moteur factice réservé au développement qui ne télécharge et n'exécute aucun modèle.

#### Scenario: Liste des moteurs
- **WHEN** l'utilisateur ouvre la page des moteurs
- **THEN** chaque moteur est listé avec son état (non installé, installation en cours, installé, échec) et sa version installée le cas échéant

#### Scenario: Moteur factice
- **WHEN** une exécution utilise le moteur factice
- **THEN** elle produit une transcription et des mesures simulées clairement identifiées comme factices, sans accès réseau

### Requirement: Installation isolée à la demande
L'installation d'un moteur SHALL être déclenchée explicitement depuis l'interface et créer un environnement Python dédié à ce moteur, à partir de versions verrouillées propres à ce moteur.

#### Scenario: Installation réussie
- **WHEN** l'utilisateur lance l'installation d'un moteur non installé
- **THEN** son environnement dédié est créé, les versions verrouillées installées, et le moteur passe à l'état installé

#### Scenario: Échec d'installation
- **WHEN** l'installation échoue
- **THEN** le moteur passe à l'état échec, le journal d'installation est consultable et les autres moteurs ne sont pas affectés

### Requirement: Exécution CPU uniquement
Chaque moteur MUST être exécuté sur CPU uniquement ; toute accélération GPU ou Vulkan MUST être désactivée, et le périphérique effectivement utilisé MUST être consigné quand le moteur permet de le vérifier.

#### Scenario: Machine disposant d'un GPU
- **WHEN** une exécution démarre sur une machine équipée d'un GPU compatible
- **THEN** le moteur s'exécute sur CPU et les métadonnées indiquent le périphérique CPU

#### Scenario: Périphérique inattendu
- **WHEN** le moteur rapporte un périphérique autre que CPU
- **THEN** l'exécution est arrêtée en erreur avec ce motif

### Requirement: Nombre de threads maîtrisé
Le nombre de threads CPU SHALL être réglable par exécution pour les trois moteurs, et la valeur effective MUST être consignée.

#### Scenario: Threads imposés
- **WHEN** l'utilisateur fixe un nombre de threads pour une exécution
- **THEN** le moteur l'applique et les métadonnées contiennent la valeur effective

### Requirement: Moteur exécuté hors du serveur
Chaque exécution SHALL être réalisée dans un processus séparé utilisant l'environnement du moteur, de sorte qu'un plantage du moteur n'arrête pas le serveur.

#### Scenario: Plantage du moteur
- **WHEN** le processus du moteur se termine anormalement
- **THEN** l'exécution est marquée en échec avec le message d'erreur disponible, et le serveur reste utilisable

### Requirement: Ajout de moteurs
L'ajout d'un nouveau moteur SHALL nécessiter uniquement un adaptateur et sa liste de dépendances verrouillées, sans modification des fonctionnalités d'exécution, de stockage ou de comparaison.

#### Scenario: Nouveau moteur déclaré
- **WHEN** un adaptateur conforme et ses dépendances sont ajoutés au programme
- **THEN** le moteur apparaît dans l'interface et peut être installé et utilisé comme les autres
