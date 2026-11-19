## ADDED Requirements

### Requirement: Seule interface d'action
Les commandes du programme SHALL être la seule interface permettant d'installer un moteur, de vérifier, télécharger ou supprimer un modèle, de vérifier ou lancer une exécution et de l'arrêter. Chaque page de consultation de l'interface web SHALL avoir une commande de lecture équivalente, appelant le même service de consultation ; une commande MAY offrir une fonction sans page web. La table de parité du code associe chaque route web à sa commande de lecture ou à une exclusion documentée.

#### Scenario: Couverture des pages de consultation
- **WHEN** on énumère les pages de l'interface web
- **THEN** chacune a une commande : Résultats (`results list`), détail (`results show`), aide (`results explain`), sélection de comparaison (`results list`), comparaison (`compare`), Historique (`results history`)

#### Scenario: Route couverte
- **WHEN** un test énumère les routes de l'application web et la table de parité du code
- **THEN** chaque route correspond à une commande de lecture ou à une exclusion documentée (redirection `/`, feuilles de style), et une route sans entrée fait échouer le test

#### Scenario: Commande sans page
- **WHEN** une commande d'action ou de lecture n'a pas de page web équivalente
- **THEN** le test de parité l'accepte

#### Scenario: Chemins contrôlés
- **WHEN** un nom d'audio, une clé ou un identifiant contient un chemin absolu, une remontée `..` ou sort d'un dossier autorisé par lien symbolique
- **THEN** la commande refuse sans lire ni écrire hors du dossier prévu

#### Scenario: Préparation d'une exécution factice
- **WHEN** l'utilisateur exécute `run options` avec le moteur factice disponible
- **THEN** le modèle synthétique du moteur factice est proposé avec sa référence, les audios proposables, le nombre de threads par défaut et les réglages applicables avec leurs valeurs par défaut

### Requirement: Une seule opération longue à la fois
Le programme SHALL n'exécuter qu'une opération longue à la fois (installation, vérification distante, téléchargement ou exécution) afin de ne pas fausser les mesures, sans file d'attente. Le verrou d'instance et le créneau d'opération unique garantissent cette règle ; une demande d'opération pendant une autre MUST être refusée avec le code 2.

#### Scenario: Seconde commande pendant une exécution
- **WHEN** une commande d'exécution est en cours et qu'une commande de téléchargement est lancée
- **THEN** la seconde commande est refusée avec le code 2 et l'indication qu'une instance utilise déjà le dossier de données

## MODIFIED Requirements

### Requirement: Arrêt par signal
`Ctrl+C` sous Windows et Linux et `SIGTERM` sous Linux, appliqués à une commande en cours, SHALL arrêter l'opération : processus du moteur ou installation en cours terminés, résultats déjà écrits conservés, exécution marquée interrompue, installation ou téléchargement interrompu laissé non prêt, commande terminée avec le code 3. Il n'existe pas de commande d'arrêt séparée : ce signal est le seul moyen d'arrêt demandé par l'utilisateur.

#### Scenario: Arrêt pendant un lot
- **WHEN** l'utilisateur interrompt une commande d'exécution après le premier audio d'un lot
- **THEN** la transcription du premier audio est conservée, les audios restants sont marqués non traités, l'exécution est marquée interrompue et le code de sortie est 3

#### Scenario: Téléchargement interrompu
- **WHEN** une commande de téléchargement reçoit un signal d'arrêt
- **THEN** le modèle n'est pas marqué prêt et le code de sortie est 3 ; si le transfert ne se termine pas dans le délai borné, la commande l'indique et le verrou reste tenu jusqu'à la fin du processus

#### Scenario: Second signal
- **WHEN** un second signal arrive pendant la clôture
- **THEN** il est ignoré et la clôture se poursuit

#### Scenario: Terminaison brutale
- **WHEN** une commande en cours est tuée sans clôture puis qu'une autre commande ou le serveur est lancé
- **THEN** le moteur survivant vérifié est terminé et l'exécution est clôturée en état abandonné avant cette commande

#### Scenario: Propriétés du gestionnaire de signal
- **WHEN** un signal d'arrêt est reçu pendant la boucle de suivi
- **THEN** le gestionnaire pose un drapeau sans lever d'exception dans la boucle de suivi, et aucune ligne de sortie n'est laissée tronquée ; le verrou est libéré à la fin de la clôture

### Requirement: Suppression de modèle protégée
`models delete` SHALL supprimer le dossier d'un modèle local désigné sans confirmation interactive, avec les refus de clé et de dossier délégués au service de gestion des modèles. Les résultats déjà produits MUST rester consultables.

#### Scenario: Suppression d'un modèle inutilisé
- **WHEN** l'utilisateur exécute `models delete` pour un modèle local valide
- **THEN** ses fichiers sont retirés et les résultats déjà produits restent consultables

#### Scenario: Clé invalide
- **WHEN** la clé désigne un chemin hors du dossier des modèles
- **THEN** la commande refuse avec le code 2 sans rien supprimer

### Requirement: Préparation, vérification à blanc et lancement d'une exécution
`run options` SHALL présenter la préparation d'une exécution : modèles exécutables ou non avec motif, audios proposables, threads par défaut et réglages applicables avec leurs défauts. `run check` SHALL appliquer la validation d'une demande sans rien lancer ni écrire et afficher la demande normalisée. `run start` SHALL lancer l'exécution après la même validation, en réservant l'exécution avant son admission pour que l'arrêt par signal vise bien le moteur.

#### Scenario: Demande valide à blanc
- **WHEN** l'utilisateur exécute `run check` avec un modèle prêt et un audio lisible
- **THEN** la demande normalisée (modèle, moteur, audios, threads, réglages effectifs) est affichée, aucune opération n'est lancée et aucun résultat n'est écrit

#### Scenario: Réglage inapplicable
- **WHEN** un `--setting` n'est pas pris en charge par le moteur et la famille du modèle
- **THEN** la commande refuse avec le code 2 et nomme le réglage

#### Scenario: Modèle non exécutable
- **WHEN** `run options` liste un modèle non exécutable
- **THEN** son motif est affiché et `run start` le refuse avec le code 2

#### Scenario: Arguments acceptés par run start
- **WHEN** l'utilisateur exécute `run start`
- **THEN** la commande accepte un modèle prêt, un ou plusieurs audios ordonnés (`--audio` répétable), un nombre de threads (par défaut celui de la préparation) et des réglages `--setting NOM=VALEUR` applicables à la famille du modèle

### Requirement: Sorties lisibles et sortie JSON stable
Chaque commande SHALL écrire par défaut un texte français concis. Toutes les sorties, texte ou JSON, SHALL être écrites en UTF-8. L'option `--json` SHALL être acceptée par toutes les commandes sauf `serve` : en mode JSON, rien d'autre que la sortie prévue n'est écrit sur la sortie standard, et messages d'erreur et diagnostics vont sur la sortie d'erreur.

#### Scenario: Liste en JSON
- **WHEN** l'utilisateur exécute `transcription-bench models list --json`
- **THEN** la sortie standard contient un seul objet JSON valide avec `schema: 1` et la liste des modèles prêts, et rien d'autre

#### Scenario: Opération longue en JSON
- **WHEN** l'utilisateur lance une installation avec `--json`
- **THEN** la sortie standard contient des lignes JSON de journal puis une ligne finale avec l'état de l'opération, chaque ligne étant un objet complet

#### Scenario: Propriétés calculées conservées
- **WHEN** un résultat contenant des mesures simulées est lu avec `--json`
- **THEN** la marque de simulation et les indicateurs principaux figurent dans la sortie

#### Scenario: Mesure absente
- **WHEN** une mesure du résultat est absente ou partielle
- **THEN** la sortie la signale comme absente ou partielle, jamais comme zéro

#### Scenario: Sortie redirigée avec un encodage local limité
- **WHEN** la sortie est redirigée vers un fichier ou un tube et qu'une transcription contient des caractères accentués ou non latins
- **THEN** la commande écrit la sortie en UTF-8 sans erreur d'encodage

#### Scenario: Structure de la sortie JSON, résultat unique
- **WHEN** une commande à résultat unique s'exécute avec `--json`
- **THEN** la sortie standard contient exactement un objet JSON

#### Scenario: Structure de la sortie JSON, opération longue
- **WHEN** une opération longue s'exécute avec `--json`
- **THEN** la sortie standard contient des lignes JSON d'événements de journal puis une dernière ligne de résultat

#### Scenario: Champs et clés stables
- **WHEN** une commande produit un objet JSON
- **THEN** chaque objet porte `schema: 1` ; ses champs reprennent ceux des vues typées existantes, complétés des indicateurs principaux et de la marque de simulation, avec les valeurs brutes et leurs unités, et les clés de chaque commande sont verrouillées par un test d'instantané

#### Scenario: Enchaînement des commandes
- **WHEN** `run start`, `models download` ou `results list` se termine
- **THEN** le résultat de fin permet d'enchaîner : identifiant du résultat et état de chaque audio pour `run start`, référence locale du modèle pour `models download`, empreinte de chaque groupe et sélection `identifiant:ordre` de chaque essai pour `results list`

#### Scenario: Aucune donnée excédentaire
- **WHEN** une commande écrit sa sortie, en texte ou en JSON
- **THEN** aucun jeton, secret ni donnée audio brute n'y figure ; seules les données des résultats enregistrés et de l'état du programme utiles à la commande sont écrites

### Requirement: Aucune dépendance ni exposition réseau supplémentaires
Les commandes MUST NOT ajouter de dépendance au programme, ne SHALL écouter sur aucun port et MUST NOT accéder au réseau, sauf `engines install`, `models check` et `models download` qui l'utilisent uniquement sur action explicite de l'utilisateur, pour la ressource nommée.

#### Scenario: Commande de lecture hors ligne
- **WHEN** une commande de lecture est exécutée sans accès réseau
- **THEN** elle réussit sans tentative de connexion

#### Scenario: Aucune bibliothèque de moteur dans la commande
- **WHEN** une commande quelconque est exécutée
- **THEN** aucune bibliothèque de moteur n'est importée dans son processus

## REMOVED Requirements

### Requirement: Parité fonctionnelle avec l'interface web
**Reason**: l'interface web n'offre plus d'action ; la parité stricte dans les deux sens empêcherait d'ajouter des commandes sans page.
**Migration**: exigence « Seule interface d'action » (parité à sens unique, des pages de consultation vers les commandes de lecture).

## RENAMED Requirements

- FROM: `### Requirement: Arrêt par signal équivalent à l'arrêt web`
- TO: `### Requirement: Arrêt par signal`
