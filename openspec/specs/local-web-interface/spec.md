# local-web-interface Specification

## Purpose
Permet de lancer l'outil de benchmark sur un poste Windows ou Linux et de le piloter entièrement depuis une page web locale sans CSS ni JavaScript.

## Requirements

### Requirement: Lancement par une commande unique
Le programme SHALL se lancer par une seule commande uv documentée, identique sous Windows x64 et Linux x64, qui prépare au premier lancement l'environnement Python 3.12 du serveur et ses dépendances, sans droits administrateur ni modification du Python système.

#### Scenario: Premier lancement
- **WHEN** l'utilisateur exécute la commande de lancement sur un poste disposant de uv mais sans environnement préparé
- **THEN** l'environnement du serveur est créé avec les versions verrouillées, puis le serveur démarre

#### Scenario: uv absent
- **WHEN** la documentation de lancement est suivie sur un poste sans uv
- **THEN** elle indique la procédure officielle d'installation utilisateur de uv pour Windows et Linux

### Requirement: Aucun moteur ni modèle installé au lancement
Le lancement du serveur MUST NOT installer de moteur, télécharger de modèle ni accéder au réseau pour ces ressources.

#### Scenario: Lancement sur une machine de développement
- **WHEN** le serveur est lancé sur un poste où aucun moteur n'est installé
- **THEN** l'interface est utilisable et indique les moteurs comme non installés, sans téléchargement

### Requirement: Écoute locale uniquement
Le serveur SHALL écouter uniquement sur l'adresse de bouclage locale, sur un port configurable, et afficher l'URL de l'interface au démarrage.

#### Scenario: Démarrage
- **WHEN** le serveur démarre
- **THEN** il est accessible depuis la machine via l'URL affichée et n'écoute sur aucune interface réseau externe

### Requirement: Requêtes locales vérifiées
Le serveur MUST refuser toute requête dont l'en-tête `Host` ne correspond pas à une adresse de bouclage locale avec le port d'écoute. Toute requête POST MUST porter un jeton anti-CSRF renouvelé à chaque démarrage du serveur et émis dans le formulaire ; si un en-tête `Origin` est présent, il MUST correspondre à l'origine locale, sinon la requête est refusée, y compris pour `Origin: null`.

#### Scenario: Host étranger
- **WHEN** une requête arrive avec un en-tête `Host` qui ne correspond pas à l'adresse locale et au port d'écoute
- **THEN** le serveur la refuse sans exécuter d'action

#### Scenario: POST sans jeton ou origine distante
- **WHEN** un formulaire est soumis sans jeton anti-CSRF valide, ou avec un en-tête `Origin` distant
- **THEN** le serveur refuse la demande et aucune action n'est lancée

### Requirement: Chemins contrôlés
Tout nom de fichier, dossier ou identifiant fourni par l'utilisateur MUST être résolu et vérifié comme restant sous le dossier de données prévu. Un chemin absolu, une remontée `..` ou un lien symbolique sortant MUST être refusé.

#### Scenario: Tentative de traversée de dossier
- **WHEN** une demande contient un nom de fichier ou un identifiant tentant de sortir du dossier autorisé
- **THEN** la demande est refusée avec un message explicite et aucun fichier hors du dossier n'est lu ni écrit

### Requirement: Interface HTML sans CSS ni JavaScript
Toutes les pages produites par l'application SHALL être en HTML seul, sans feuille de style, attribut de style ni script ; les actions passent par des liens et formulaires HTML. Les erreurs du serveur HTTP avant appel de l'application ne sont pas des pages de l'interface.

#### Scenario: Inspection d'une page
- **WHEN** une page quelconque de l'interface est chargée
- **THEN** elle ne contient aucun élément `script`, `style`, attribut `style` ni lien vers une feuille de style

#### Scenario: Page d'erreur
- **WHEN** une requête parvenue à l'application vise une route inexistante, utilise une méthode non autorisée ou provoque une erreur interne
- **THEN** la réponse conserve le statut HTTP approprié et présente une page HTML sans CSS ni JavaScript, sans trace d'exception ni débogueur interactif

### Requirement: Formulaires bornés
Les POST transmis à l'application SHALL être des formulaires `application/x-www-form-urlencoded` d'au plus 64 Kio : dépassement refusé en 413, type non pris en charge en 415, sans action. Les requêtes rejetées par le serveur HTTP avant l'application (HTTP malformé, en-têtes ou corps au-delà de ses propres limites) reçoivent sa réponse d'erreur sans déclencher d'action.

#### Scenario: Corps de formulaire trop volumineux
- **WHEN** un POST local autorisé soumet un formulaire de plus de 64 Kio parvenu à l'application
- **THEN** le serveur répond en 413 et aucune opération n'est lancée

#### Scenario: Type de formulaire non pris en charge
- **WHEN** un POST local autorisé soumet un corps avec un type autre que `application/x-www-form-urlencoded`
- **THEN** le serveur répond en 415 et aucune opération n'est lancée

#### Scenario: Rejet avant l'application
- **WHEN** une requête dépasse la limite de corps du serveur HTTP ou ne peut pas être interprétée par celui-ci
- **THEN** le serveur renvoie sa propre erreur HTTP sans appeler l'application ni lancer d'opération

### Requirement: Suivi des opérations longues par actualisation
Les opérations longues (installation, téléchargement, exécution) SHALL se dérouler en arrière-plan, le serveur restant disponible ; leur état est consultable sur une page actualisée manuellement par un lien ou bouton.

#### Scenario: Consultation pendant une exécution
- **WHEN** une opération longue est en cours et l'utilisateur actualise la page d'état
- **THEN** la page affiche l'état courant de l'opération sans bloquer les autres pages

### Requirement: Une seule opération longue à la fois
Le programme SHALL n'exécuter qu'une opération longue à la fois (installation, téléchargement ou exécution) afin de ne pas fausser les mesures ; les vérifications distantes de modèles MUST aussi être refusées pendant une exécution ; une nouvelle demande MUST être refusée tant qu'une opération est en cours.

#### Scenario: Téléchargement demandé pendant une exécution
- **WHEN** l'utilisateur demande un téléchargement pendant une exécution
- **THEN** la demande est refusée avec l'indication de l'opération en cours

### Requirement: Arrêt du serveur
L'arrêt normal du serveur MUST terminer le processus du moteur en cours d'exécution, conserver les résultats déjà écrits et marquer l'exécution interrompue.

#### Scenario: Arrêt pendant une exécution
- **WHEN** le serveur reçoit Ctrl+C sous Windows ou Linux, ou SIGTERM sous Linux, alors qu'un moteur transcrit un audio
- **THEN** le processus du moteur est terminé, l'exécution est marquée interrompue et les résultats déjà enregistrés restent consultables ; une installation ou un téléchargement interrompu laisse sa ressource non prête

### Requirement: Échappement des contenus affichés
Tout contenu provenant de fichiers, de modèles ou de saisies utilisateur MUST être échappé avant insertion dans le HTML.

#### Scenario: Transcription contenant du balisage
- **WHEN** une transcription contient des caractères tels que `<` ou `&`
- **THEN** ils sont affichés comme texte et ne sont pas interprétés comme du HTML

### Requirement: Dossiers de données prédéfinis
Le programme SHALL utiliser des dossiers locaux prédéfinis sous `data/` pour les audios, les modèles, les environnements des moteurs et les résultats, créés au besoin et exclus du dépôt Git.

#### Scenario: Premier démarrage sans dossiers
- **WHEN** le serveur démarre et que les dossiers de données n'existent pas
- **THEN** ils sont créés et leur emplacement est affiché dans l'interface
