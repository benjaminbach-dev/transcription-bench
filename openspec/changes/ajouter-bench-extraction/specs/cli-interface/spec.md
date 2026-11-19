## MODIFIED Requirements

### Requirement: Seule interface d'action
Les commandes du programme SHALL être la seule interface permettant d'installer un moteur, de vérifier, télécharger ou supprimer un modèle, de vérifier ou lancer une exécution de transcription ou d'extraction et de l'arrêter. Chaque page de consultation de l'interface web SHALL avoir une commande de lecture équivalente, appelant le même service de consultation ; une commande MAY offrir une fonction sans page web. La table de parité du code associe chaque route web à sa commande de lecture ou à une exclusion documentée.

#### Scenario: Couverture des pages de consultation
- **WHEN** on énumère les pages de l'interface web
- **THEN** chacune a une commande : Résultats (`results list`), détail (`results show`), aide (`results explain`), sélection de comparaison (`results list`), comparaison (`compare`), Historique (`results history`), Extractions et sélection de comparaison d'extractions (`extract list`), détail d'extraction (`extract show`), comparaison d'extractions (`extract compare`), aide des extractions (`extract explain`)

#### Scenario: Route couverte
- **WHEN** un test énumère les routes de l'application web et la table de parité du code
- **THEN** chaque route correspond à une commande de lecture ou à une exclusion documentée (redirection `/`, feuilles de style), et une route sans entrée fait échouer le test

#### Scenario: Commande sans page
- **WHEN** une commande d'action ou de lecture n'a pas de page web équivalente, comme `grids show`
- **THEN** le test de parité l'accepte

#### Scenario: Chemins contrôlés
- **WHEN** un nom d'audio ou de grille, une clé ou un identifiant contient un chemin absolu, une remontée `..` ou sort d'un dossier autorisé par lien symbolique
- **THEN** la commande refuse sans lire ni écrire hors du dossier prévu

#### Scenario: Préparation d'une exécution factice
- **WHEN** l'utilisateur exécute `run options` ou `extract options` avec le moteur factice disponible
- **THEN** le modèle synthétique du moteur factice correspondant à la tâche est proposé avec sa référence, les entrées proposables, le nombre de threads par défaut et les réglages applicables avec leurs valeurs par défaut
