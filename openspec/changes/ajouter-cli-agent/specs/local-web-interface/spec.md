## ADDED Requirements

### Requirement: Serveur exclusif avec les commandes
Le serveur web SHALL tenir le verrou d'instance du dossier de données pendant tout son fonctionnement ; il MUST refuser de démarrer avec le code 2 et un message explicite si une commande du programme ou un autre serveur tient ce verrou, et MUST le libérer à son arrêt.

#### Scenario: Commande en cours
- **WHEN** une commande tient le verrou et l'utilisateur lance le serveur web
- **THEN** le serveur refuse de démarrer avec le code 2 sans modifier aucun fichier

#### Scenario: Commande lancée pendant le serveur
- **WHEN** le serveur tient le verrou et une commande est exécutée
- **THEN** la commande est refusée avec le code 2 et le serveur n'est pas perturbé
