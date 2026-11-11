## ADDED Requirements

### Requirement: Commande unique, serveur web par défaut
Le programme SHALL rester lancé par la commande `transcription-bench`. Sans sous-commande, avec ou sans `--port`, ou avec la sous-commande `serve`, il MUST lancer le serveur web avec le même comportement, les mêmes messages et les mêmes codes de sortie qu'avant l'ajout des sous-commandes. Toute autre sous-commande SHALL exécuter une seule commande puis se terminer.

#### Scenario: Lancement sans sous-commande
- **WHEN** l'utilisateur exécute `transcription-bench --port 8080`
- **THEN** le serveur web démarre sur ce port comme avant

#### Scenario: Sous-commande serve
- **WHEN** l'utilisateur exécute `transcription-bench serve --port 8080`
- **THEN** le comportement est identique à l'exécution sans sous-commande

#### Scenario: Aide
- **WHEN** l'utilisateur exécute `transcription-bench --help` ou `transcription-bench <groupe> --help`
- **THEN** la liste des sous-commandes, de leurs options et des codes de sortie est affichée avec des descriptions en français, sans écrire ni lire dans `data/`

### Requirement: Exclusion entre serveur web et commandes
Le serveur web et les commandes SHALL ne jamais s'exécuter en même temps sur un même dossier de données. Toute sous-commande, y compris de simple lecture, MUST prendre le verrou d'instance existant et MUST se terminer avec le code 2 et un message explicite sans rien lancer ni modifier si une autre instance ou commande le tient. La récupération des exécutions abandonnées MUST s'appliquer avant chaque commande comme avant le serveur.

#### Scenario: Serveur déjà lancé
- **WHEN** le serveur web tient le verrou et l'utilisateur exécute `transcription-bench audios list`
- **THEN** la commande se termine avec le code 2, indique qu'une instance utilise déjà le dossier de données et ne modifie aucun fichier

#### Scenario: Commande en cours puis serveur
- **WHEN** une commande de longue durée tient le verrou et l'utilisateur lance le serveur
- **THEN** le serveur refuse de démarrer avec le code 2 et le même message

#### Scenario: Verrou libéré après la commande
- **WHEN** une commande se termine, normalement, en échec ou après un signal
- **THEN** le verrou est libéré et le serveur ou une autre commande peut démarrer

#### Scenario: Exécution laissée en cours par un arrêt brutal
- **WHEN** une commande démarre après un arrêt brutal ayant laissé une exécution en cours
- **THEN** l'exécution est clôturée en état abandonné avant la commande, comme au démarrage du serveur

#### Scenario: État antérieur non traitable
- **WHEN** la récupération au démarrage d'une commande trouve un état antérieur non traitable
- **THEN** la commande est refusée avec le code 2 avant toute action

### Requirement: Parité fonctionnelle avec l'interface web
Chaque route fonctionnelle de l'interface web SHALL avoir une commande équivalente, appelant les mêmes services et appliquant les mêmes règles de validation et de refus. Aucune commande ne SHALL offrir une fonction absente de l'interface web. Une route sans commande n'est admise que par une exclusion documentée dans la table de parité du code.

#### Scenario: Couverture des fonctions
- **WHEN** on énumère les fonctions de l'interface web
- **THEN** chacune a une commande : liste des audios et état des dossiers ; liste, installation et journal des moteurs ; inventaire, vérification, téléchargement et suppression des modèles ; options de préparation, vérification à blanc et lancement des exécutions, avec un ou plusieurs audios, threads et réglages avancés ; historique des exécutions ; liste des résultats groupés par audio avec les tris existants, détail d'un résultat, aide des indicateurs et comparaison

#### Scenario: Exclusions documentées
- **WHEN** une route de l'interface web n'a pas de commande
- **THEN** elle n'est admise que comme exclusion documentée : redirection, ressources statiques, arrêt remplacé par le signal, suivi remplacé par le flux de journal

#### Scenario: Route couverte
- **WHEN** un test énumère les routes de l'application web et la table de parité du code
- **THEN** chaque route correspond à une commande ou à une exclusion documentée, et une route sans entrée fait échouer le test

#### Scenario: Même refus que la page
- **WHEN** une commande reçoit une demande que la page web refuserait (modèle non prêt, audio illisible, réglage inapplicable à la famille, chemin sortant du dossier autorisé, champ répété)
- **THEN** elle se termine avec le code 2 et le motif fourni par le même service que la page, sans lancer d'opération

#### Scenario: Chemins contrôlés
- **WHEN** un nom d'audio, une clé ou un identifiant contient un chemin absolu, une remontée `..` ou sort d'un dossier autorisé par lien symbolique
- **THEN** la commande refuse sans lire ni écrire hors du dossier prévu

#### Scenario: Préparation d'une exécution factice
- **WHEN** l'utilisateur exécute `run options` avec le moteur factice disponible
- **THEN** le modèle synthétique du moteur factice est proposé avec sa référence, les audios proposables, le nombre de threads par défaut et les réglages applicables avec leurs valeurs par défaut

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
- **THEN** aucun jeton ni donnée audio n'est ajouté au-delà de ce que l'interface web affiche

### Requirement: Codes de sortie
Les commandes SHALL se terminer avec le code 0 en cas de succès, 1 en cas d'échec de l'opération, 2 en cas de refus et 3 en cas d'interruption par un signal. Le code SHALL être déduit du résultat du service concerné (résultat de vérification, état de l'exécution), et non du seul état du créneau d'opération. Un modèle déjà prêt lors d'un téléchargement est un succès.

#### Scenario: Argument invalide
- **WHEN** une commande reçoit un moteur inconnu ou une option invalide
- **THEN** elle se termine avec le code 2 sans lancer d'opération

#### Scenario: Installation en échec
- **WHEN** l'installation d'un moteur échoue
- **THEN** la commande se termine avec le code 1 et le motif d'échec est affiché

#### Scenario: Vérification refusée
- **WHEN** `models check` conclut qu'un dépôt est incompatible
- **THEN** la commande se termine avec le code 2 et la raison fournie par la vérification

#### Scenario: Exécution terminée avec un audio en erreur
- **WHEN** une exécution se termine mais qu'un de ses audios est en erreur
- **THEN** la commande se termine avec le code 1 et le résumé identifie l'audio en erreur ; les autres résultats restent enregistrés

#### Scenario: Cas d'échec
- **WHEN** une installation, un téléchargement ou une exécution est en erreur, une exécution se termine avec au moins un audio en erreur, ou une vérification subit un échec réseau ou un accès refusé
- **THEN** la commande se termine avec le code 1

#### Scenario: Cas de refus
- **WHEN** la commande rencontre des arguments invalides, un verrou tenu, une ressource non prête, un dépôt incompatible, un choix de fichier GGUF manquant ou un état antérieur non traitable
- **THEN** elle se termine avec le code 2

### Requirement: Opérations longues bloquantes avec journal en flux
Une installation, un téléchargement ou une exécution lancés par une commande SHALL s'exécuter dans le créneau d'opération unique existant ; la commande attend la fin par un sondage interruptible et écrit au fil de l'eau le journal de l'opération. Aucune commande ne SHALL se détacher du terminal, ni laisser un processus moteur ou thread d'opération actif après sa fin, hors le cas d'un téléchargement non annulable (voir l'exigence d'arrêt).

#### Scenario: Exécution de plusieurs audios
- **WHEN** l'utilisateur lance une exécution avec trois audios
- **THEN** le journal de l'opération apparaît pendant le déroulement, les audios sont traités dans l'ordre demandé avec un seul chargement de modèle, et la commande se termine avec l'état final de l'exécution

#### Scenario: Deux opérations enchaînées
- **WHEN** `models download` enchaîne la vérification puis le téléchargement
- **THEN** le journal de chacune des deux opérations est écrit en entier, sans perte au changement d'opération

#### Scenario: Aucune opération résiduelle
- **WHEN** une commande d'installation ou d'exécution se termine
- **THEN** aucun processus moteur ni thread d'opération ne reste actif

### Requirement: Arrêt par signal équivalent à l'arrêt web
`Ctrl+C` sous Windows et Linux et `SIGTERM` sous Linux, appliqués à une commande en cours, SHALL se comporter comme l'arrêt demandé par l'utilisateur sur la page web : processus du moteur ou installation en cours terminés, résultats déjà écrits conservés, exécution marquée interrompue, installation ou téléchargement interrompu laissé non prêt, commande terminée avec le code 3. Il n'existe pas de commande d'arrêt séparée : l'arrêt de la page web a pour équivalent ce signal.

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
- **WHEN** une commande en cours est tuée sans clôture puis qu'une autre commande est lancée
- **THEN** le moteur survivant vérifié est terminé et l'exécution est clôturée en état abandonné avant cette commande, comme après un arrêt brutal du serveur

#### Scenario: Propriétés du gestionnaire de signal
- **WHEN** un signal d'arrêt est reçu pendant la boucle de suivi
- **THEN** le gestionnaire pose un drapeau sans lever d'exception dans la boucle de suivi, et aucune ligne de sortie n'est laissée tronquée ; le verrou est libéré à la fin de la clôture

### Requirement: Téléchargement explicite d'un modèle vérifié
`models check` SHALL vérifier la compatibilité d'un dépôt sans télécharger de poids et afficher famille, révision résolue, fichiers et taille totale. `models download` SHALL enchaîner, dans le même processus, la vérification puis le téléchargement des seuls fichiers retenus à la révision résolue par cette vérification ; il MUST refuser un dépôt incompatible et un fragment GGUF découpé.

#### Scenario: Vérification sans téléchargement
- **WHEN** l'utilisateur exécute `models check` sur un dépôt compatible
- **THEN** la famille, la révision, les fichiers et la taille sont affichés, aucun poids n'est téléchargé et aucun fichier du dossier des modèles n'est créé

#### Scenario: Téléchargement après vérification
- **WHEN** l'utilisateur exécute `models download` sur un dépôt compatible
- **THEN** la révision résolue et la taille sont affichées avant le téléchargement, puis les fichiers retenus sont téléchargés à cette révision ; pour un modèle déjà prêt, la commande l'indique sans rien télécharger

#### Scenario: Plusieurs quantifications sans choix
- **WHEN** l'utilisateur exécute `models check` ou `models download` sur un dépôt GGUF à plusieurs fichiers sans `--file`
- **THEN** la commande refuse avec le code 2 et liste les fichiers disponibles, sans télécharger

#### Scenario: Modèle déjà présent
- **WHEN** l'utilisateur exécute `models download` pour un modèle déjà prêt à la même révision
- **THEN** la commande l'indique, ne télécharge rien et se termine avec le code 0

### Requirement: Suppression de modèle protégée
`models delete` SHALL supprimer le dossier d'un modèle local désigné sans confirmation interactive, avec les mêmes refus de clé et de dossier que la page web, délégués au service. Les résultats déjà produits MUST rester consultables.

#### Scenario: Suppression d'un modèle inutilisé
- **WHEN** l'utilisateur exécute `models delete` pour un modèle local valide
- **THEN** ses fichiers sont retirés et les résultats déjà produits restent consultables

#### Scenario: Clé invalide
- **WHEN** la clé désigne un chemin hors du dossier des modèles
- **THEN** la commande refuse avec le code 2 sans rien supprimer

### Requirement: Préparation, vérification à blanc et lancement d'une exécution
`run options` SHALL présenter la préparation d'une exécution comme la page web. `run check` SHALL appliquer la validation d'une demande sans rien lancer ni écrire et afficher la demande normalisée. `run start` SHALL lancer l'exécution comme la page web, en réservant l'exécution avant son admission pour que l'arrêt par signal vise bien le moteur.

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

### Requirement: Lecture des résultats sans modification
Les commandes `results list`, `results history`, `results show`, `results explain` et `compare` SHALL réutiliser la consultation existante et ne jamais écrire, réécrire ni supprimer de fichier de résultat ; seules la récupération et la préparation de `data/` exécutées au démarrage de toute commande peuvent clore une exécution abandonnée ou créer des dossiers.

#### Scenario: Lecture sans écriture
- **WHEN** une commande de lecture se termine sans état antérieur à récupérer
- **THEN** aucun fichier de résultat n'a été modifié ni créé

### Requirement: Distinctions de lecture conservées
Les commandes `results list`, `results history`, `results explain`, `results show` et `compare` SHALL conserver les distinctions de l'interface : exécutions factices et mesures simulées signalées, résultats partiels et états (en cours, terminée, interrompue, abandonnée, en échec) explicites, regroupement par empreinte de l'audio, tris existants (`temps`, `ram`, `cpu`, `recent`), mesures du moteur distinguées de celles de l'ordinateur, sans score global ni désignation d'un meilleur modèle.

#### Scenario: Liste groupée
- **WHEN** l'utilisateur exécute `results list --sort ram`
- **THEN** les essais sont regroupés par empreinte d'audio, triés par pic mémoire croissant avec les valeurs absentes en dernier, les résultats factices étant séparés

#### Scenario: Tri par défaut
- **WHEN** l'utilisateur exécute `results list` sans `--sort`
- **THEN** le tri `recent` s'applique, comme pour la page web

#### Scenario: Tri inconnu
- **WHEN** l'utilisateur fournit un tri inconnu
- **THEN** la commande refuse avec le code 2

#### Scenario: Comparaison de deux essais
- **WHEN** l'utilisateur exécute `compare` avec l'empreinte d'un audio et deux sélections `identifiant:ordre` de ce groupe
- **THEN** les deux essais sont présentés dans l'ordre reçu avec modèle, moteur, indicateurs principaux et texte complet ; une sélection hors de ce groupe, mal formée ou en dehors de 2 à 64 sélections est refusée avec le code 2

### Requirement: Aucune dépendance ni exposition réseau supplémentaires
Les commandes MUST NOT ajouter de dépendance au programme, ne SHALL écouter sur aucun port et MUST NOT accéder au réseau, sauf `engines install`, `models check` et `models download` qui l'utilisent sur action explicite comme leurs équivalents web.

#### Scenario: Commande de lecture hors ligne
- **WHEN** une commande de lecture est exécutée sans accès réseau
- **THEN** elle réussit sans tentative de connexion

#### Scenario: Aucune bibliothèque de moteur dans la commande
- **WHEN** une commande quelconque est exécutée
- **THEN** aucune bibliothèque de moteur n'est importée dans son processus
