## ADDED Requirements

### Requirement: Consultation seule
L'interface web SHALL se limiter à la consultation : Résultats, détail d'un résultat, aide des indicateurs, Comparaisons et Historique des exécutions. Elle MUST NOT installer de moteur, vérifier ou télécharger de modèle, supprimer de fichier, lancer ou arrêter d'exécution, ni démarrer aucune opération longue. Ces actions relèvent exclusivement des commandes du programme. Le serveur MUST NOT accepter d'autre méthode que GET et HEAD.

#### Scenario: Requête POST
- **WHEN** une requête dont l'en-tête `Host` est local utilise POST, PUT, PATCH, DELETE ou OPTIONS, sur une route existante ou supprimée
- **THEN** elle est refusée avec le statut 405 ou 404, sans lire de corps de formulaire ni déclencher d'action ; une requête dont l'en-tête `Host` est étranger est refusée par le contrôle `Host` quelle que soit sa méthode

#### Scenario: Ancienne page d'action
- **WHEN** l'utilisateur ouvre `/audios`, `/modeles`, `/moteurs`, `/moteurs/<id>/journal`, `/operation` ou `/executions/etat`
- **THEN** l'application répond 404 avec le squelette local et aucune opération n'est démarrée

#### Scenario: Historique
- **WHEN** l'utilisateur ouvre `/executions`
- **THEN** il voit l'historique complet des exécutions, sans formulaire de préparation, de lancement ou d'arrêt

#### Scenario: Arrêt du serveur
- **WHEN** le serveur reçoit Ctrl+C sous Windows ou Linux, ou SIGTERM sous Linux
- **THEN** il s'arrête et libère le verrou d'instance sans moteur à terminer, aucune opération n'ayant pu être démarrée par l'interface

## MODIFIED Requirements

### Requirement: Aucun moteur ni modèle installé au lancement
Le lancement du serveur MUST NOT installer de moteur, télécharger de modèle ni accéder au réseau pour ces ressources.

#### Scenario: Lancement sur une machine de développement
- **WHEN** le serveur est lancé sur un poste où aucun moteur n'est installé et sans résultat enregistré
- **THEN** l'interface est utilisable, Résultats présente un état vide court qui renvoie aux commandes du programme, et rien n'est téléchargé

### Requirement: Requêtes locales vérifiées
Le serveur MUST refuser toute requête dont l'en-tête `Host` ne correspond pas à une adresse de bouclage locale avec le port d'écoute. Il MUST refuser toute méthode autre que GET et HEAD sans lire de corps de requête ; aucune route ne modifie l'état du programme.

#### Scenario: Host étranger
- **WHEN** une requête arrive avec un en-tête `Host` qui ne correspond pas à l'adresse locale et au port d'écoute
- **THEN** le serveur la refuse sans exécuter d'action

#### Scenario: Méthode modificatrice
- **WHEN** une requête locale utilise une méthode autre que GET ou HEAD
- **THEN** le serveur la refuse et aucun fichier n'est lu ni écrit pour elle

### Requirement: Interface locale avec amélioration progressive
Les pages SHALL être rendues en HTML avec les feuilles locales `/sumi.css` et `/app.css`, sans aucun script : lecture, tri et sélection de comparaison restent utilisables par liens et formulaires GET. Aucune ressource distante, aucun script, élément `style`, attribut `style` ou gestionnaire `on…` SHALL être chargé.

#### Scenario: Inspection d'une page
- **WHEN** une page de l'interface est chargée
- **THEN** ses feuilles sont `/sumi.css` puis `/app.css`, elle ne contient aucun élément `script`, élément `style`, attribut `style`, gestionnaire `on…`, lien `javascript:`, iframe ni objet distant

#### Scenario: Navigation sans script
- **WHEN** l'utilisateur consulte, trie et compare des résultats
- **THEN** toutes ces fonctions passent par des liens et formulaires GET, sans script

#### Scenario: Page d'erreur
- **WHEN** une requête parvenue à l'application vise une route inexistante, utilise une méthode non autorisée ou provoque une erreur interne
- **THEN** la réponse conserve le statut HTTP approprié et le squelette local, sans trace d'exception ni débogueur

#### Scenario: Aucun service de fichiers arbitraires
- **WHEN** une requête vise une ressource statique autre que les deux routes fixes autorisées, dont `/app.js`, `/static/base.css` ou un chemin remontant l'arborescence
- **THEN** l'application répond 404 sans lire de fichier choisi par la requête

### Requirement: Dossiers de données prédéfinis
Le programme SHALL utiliser des dossiers locaux prédéfinis sous `data/` pour les audios, les modèles, les environnements des moteurs et les résultats, créés au besoin et exclus du dépôt Git. Leur emplacement et leur état SHALL être consultables par la commande `data check`.

#### Scenario: Premier démarrage sans dossiers
- **WHEN** le serveur ou une commande démarre et que les dossiers de données n'existent pas
- **THEN** ils sont créés, et `data check` affiche leur emplacement

### Requirement: Navigation commune et page courante
La navigation SHALL présenter exactement Résultats, Comparaisons, Historique dans cet ordre. Historique désigne `/executions`. La page courante porte `aria-current="page"`, son parent porte `aria-current="true"` sur une sous-page ; une erreur ne signale aucune rubrique courante.

#### Scenario: Page courante signalée
- **WHEN** la page Historique est chargée
- **THEN** la navigation contient les trois liens dans l'ordre prescrit et seul Historique porte `aria-current="page"`

#### Scenario: Sous-page
- **WHEN** un détail de transcription est chargé
- **THEN** Résultats porte `aria-current="true"` et aucun lien ne porte `aria-current="page"`

#### Scenario: Page d'erreur
- **WHEN** une page d'erreur est chargée
- **THEN** les trois rubriques restent accessibles et aucune ne porte `aria-current`

### Requirement: Contenus jamais masqués par un accordéon
Erreurs, états partiels, marques de simulation, alertes utiles et indicateurs principaux SHALL rester visibles. Le texte complet reste visible dans le détail et la comparaison sélectionnée. Métadonnées complètes, réglages et mesures brutes peuvent être repliés.

#### Scenario: Contenu à garder visible dans un accordéon
- **WHEN** les détails techniques sont fermés
- **THEN** les chiffres clés, alertes et textes du détail et de la comparaison sélectionnée restent accessibles sans les ouvrir

### Requirement: Entrée directe et compatibilité des liens
L'URL `/` SHALL rediriger vers Résultats. Les liens internes ne visent que des pages de consultation existantes. Les pages d'action supprimées répondent 404.

#### Scenario: Premier démarrage
- **WHEN** l'utilisateur ouvre `/`
- **THEN** il rejoint `/resultats` par redirection GET locale ; sans résultats, un état vide court renvoie aux commandes du programme

#### Scenario: Ancien lien d'opération
- **WHEN** l'utilisateur ouvre un ancien lien `/operation`
- **THEN** l'application répond 404 sans démarrer d'opération

### Requirement: Politique de sécurité des contenus
Les réponses HTML SHALL appliquer une CSP interdisant tout script (`script-src 'none'`), limitant styles, connexions et soumissions de formulaires à l'origine locale, interdisant l'inclusion en frame et le changement de base URL. Les contenus provenant de fichiers ou de modèles restent du texte échappé ; la CSP ne remplace pas le contrôle `Host`.

#### Scenario: Contenu hostile ou ressource externe
- **WHEN** un nom, journal ou texte transcrit contient du balisage exécutable ou qu'un contenu tente de charger un script externe
- **THEN** le contenu est affiché comme texte, aucun code ne s'exécute et la CSP bloque la ressource

## REMOVED Requirements

### Requirement: Formulaires bornés
**Reason**: l'interface n'accepte plus aucun POST ; il n'existe plus de formulaire à corps.
**Migration**: les actions passent par les commandes du programme ; les formulaires GET de tri et de sélection restent bornés par leurs propres validations (`results-comparison`).

### Requirement: Suivi intégré des opérations longues
**Reason**: l'interface ne démarre plus d'opération ; le suivi est assuré par le journal en flux des commandes bloquantes.
**Migration**: exigence « Opérations longues bloquantes avec journal en flux » de `cli-interface`.

### Requirement: Une seule opération longue à la fois
**Reason**: l'interface ne démarre plus d'opération ; la règle est portée par la CLI.
**Migration**: exigence « Une seule opération longue à la fois » ajoutée à `cli-interface`.

### Requirement: Arrêt du serveur
**Reason**: le serveur ne supervise plus aucun moteur ni opération.
**Migration**: scénario « Arrêt du serveur » de l'exigence « Consultation seule » ; l'arrêt d'une opération relève de « Arrêt par signal » dans `cli-interface`.

### Requirement: Actions destructrices distinctes
**Reason**: l'interface ne propose plus d'action destructrice (suppression de modèle, arrêt d'exécution).
**Migration**: `models delete` et l'arrêt par signal de la CLI.

### Requirement: Script servi localement par route fixe
**Reason**: `/app.js` ne servait qu'à la préparation d'exécution et au suivi d'opération, tous deux supprimés.
**Migration**: aucune ; les pages de consultation fonctionnent sans script et la CSP interdit tout script.
