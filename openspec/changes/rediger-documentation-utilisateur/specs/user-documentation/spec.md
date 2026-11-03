## ADDED Requirements

### Requirement: Documentation organisée en trois niveaux
Le dépôt SHALL fournir un `README.md` court (porte d'entrée), un guide utilisateur (`docs/guide-utilisateur.md`) et une documentation technique (`docs/technique.md`). Le `README.md` SHALL présenter en moins de soixante lignes l'usage de l'outil, l'avertissement de non-validation clinique, la commande de lancement et des liens vers le guide et vers la documentation technique, sans détail d'implémentation, de validation ou de CI. Le guide SHALL être le seul document que l'utilisateur doit lire pour réussir sa première transcription. La documentation technique SHALL reprendre le contenu technique de l'ancien README sans en perdre d'information : un tableau de correspondance (section de l'ancien README → emplacement actuel) SHALL être joint au change.

#### Scenario: Premier contact
- **WHEN** une personne ouvre le `README.md`
- **THEN** elle y trouve en moins de soixante lignes ce que fait l'outil, que ce n'est pas un outil médical validé, et un lien direct vers le guide utilisateur

#### Scenario: Aucune perte d'information
- **WHEN** chaque section de l'ancien README est comparée au tableau de correspondance
- **THEN** chacune est soit conservée dans la documentation technique, soit réécrite dans le guide, soit explicitement déclarée obsolète avec sa raison

### Requirement: Langage adapté à des non-techniciens
Le guide et le README SHALL être rédigés en français courant, au vouvoiement, en phrases courtes, avec une action par étape numérotée et des verbes à l'impératif. Tout terme technique inévitable (par exemple moteur, modèle, terminal, empreinte, hors ligne) SHALL être défini en une phrase à sa première apparition et dans un glossaire du guide. Un terme technique non défini, un sigle non développé et les termes d'une liste d'interdits maintenue par un test (au minimum CSRF, WSGI, Flask, Jinja, venv, namespace, mmap, RTF, `HF_HUB_OFFLINE`) SHALL NOT apparaître dans le guide ni le README, sauf dans le glossaire ou entre guillemets français lorsqu'ils reproduisent un libellé de l'interface. Les libellés exacts de l'interface SHALL être cités entre guillemets français « … », et ces guillemets SHALL NOT servir à autre chose.

#### Scenario: Terme technique défini
- **WHEN** le guide emploie pour la première fois le mot « modèle » ou « moteur »
- **THEN** une phrase le définit à cet endroit et le glossaire le reprend

#### Scenario: Terme interdit
- **WHEN** un terme de la liste d'interdits apparaît dans le guide ou le README hors glossaire et hors guillemets français
- **THEN** le test de cohérence de la documentation échoue

### Requirement: Parcours pas à pas de bout en bout
Le guide SHALL décrire, dans l'ordre, tout ce qu'il faut faire pour passer de rien à une première transcription lue puis comparée : ce dont il faut disposer (système, espace disque, mémoire, navigateur récent et ses versions minimales), installer l'outil de lancement, obtenir le projet, ouvrir un terminal, lancer l'application, ouvrir la page dans le navigateur, déposer des audios dans le dossier prévu, installer un moteur, ajouter et télécharger un modèle, lancer la transcription, suivre l'opération, lire le résultat, comparer deux résultats, arrêter l'application et relancer plus tard. Chaque étape SHALL comporter trois parties : ce qu'il faut faire, ce que l'on doit voir, et quoi faire si ce n'est pas le cas (renvoi vers le dépannage). Les commandes à copier SHALL être données pour Linux et pour Windows, et l'ouverture d'un terminal SHALL être expliquée pour chacun.

#### Scenario: Étape complète
- **WHEN** une étape du parcours est lue
- **THEN** elle indique l'action à faire, le résultat observable attendu avec le texte exact de l'interface et un renvoi au dépannage en cas d'écart

#### Scenario: Les deux systèmes
- **WHEN** une commande doit être saisie dans un terminal
- **THEN** la version Linux et la version Windows sont toutes deux présentes, avec le nom du terminal à ouvrir

### Requirement: Exemple concret vérifié
Le parcours principal SHALL utiliser un modèle d'essai réellement vérifié du projet, avec son moteur, son identifiant exact, le fichier à choisir lorsque le dépôt en propose plusieurs, la taille à télécharger et la durée approximative attendue. Le guide SHALL aussi lister dans un tableau les autres modèles d'essai vérifiés (moteur, identifiant, taille, remarque) avec un renvoi vers les licences. Il SHALL expliquer comment comparer deux résultats sans prétendre dire quel modèle est le meilleur ni que le texte obtenu est exact.

#### Scenario: Identifiants exacts
- **WHEN** le guide indique un identifiant de modèle ou un nom de fichier
- **THEN** il figure dans `docs/licences-modeles.md` ou dans les preuves de validation du projet

### Requirement: Avertissements, limites et vie privée en clair
Le guide SHALL expliquer en langage courant, au début et là où c'est pertinent : que l'outil n'est pas validé cliniquement et qu'une transcription qui se lit bien peut être fausse ; que les audios et les transcriptions restent sur l'ordinateur et ne sont envoyés à aucun service ; ce que l'application télécharge, quand et quelle quantité, et qu'elle ne le fait que sur action explicite ; que les performances mesurées dépendent de l'ordinateur ; et la liste des limites connues qui touchent l'utilisateur (une seule transcription à la fois, ordinateur sans carte graphique exploitée, systèmes pris en charge).

#### Scenario: Données personnelles
- **WHEN** le guide présente le dépôt des audios
- **THEN** il dit que les fichiers ne quittent pas l'ordinateur et que seuls les téléchargements d'outils et de modèles utilisent Internet

### Requirement: Dépannage en langage courant
Le guide SHALL contenir une section de dépannage organisée en « ce que vous voyez », « cause probable », « que faire », couvrant au minimum : port déjà utilisé, commande de lancement introuvable, moteur non prêt ou installation échouée, modèle refusé ou introuvable, téléchargement interrompu ou espace disque insuffisant, absence de connexion Internet, audio illisible ou format non pris en charge, transcription vide ou exécution interrompue, et page qui ne s'ouvre pas. Chaque cas SHALL s'appuyer sur un message ou comportement réellement produit par l'application.

#### Scenario: Message réel
- **WHEN** un cas du dépannage cite un message de l'application
- **THEN** ce message existe dans le code ou les gabarits de l'application

### Requirement: Fidélité à l'interface et aux liens
Le projet SHALL disposer d'un test automatique de cohérence de la documentation : tout texte entre guillemets français du guide est un libellé présent dans les gabarits de l'interface, un titre de page, ou figure dans une liste blanche explicite de non-libellés ; tous les liens relatifs du README et des documents du dossier `docs/` pointent vers un fichier existant ; la liste d'interdits du langage est respectée. Ce test SHALL s'exécuter dans la suite habituelle, sans réseau et sans nouvelle dépendance.

#### Scenario: Libellé changé dans l'interface
- **WHEN** un libellé d'une page est modifié sans mise à jour du guide
- **THEN** le test de cohérence échoue en nommant le libellé et le fichier

#### Scenario: Lien cassé
- **WHEN** le README renvoie vers un fichier qui n'existe plus
- **THEN** le test de cohérence échoue

### Requirement: Vérification honnête de la documentation
Chaque procédure du guide SHALL porter son niveau de vérification : « vérifié sous Linux le <date> », « contrôlé par la CI Windows » (en précisant ce qui l'a été) ou « non vérifié sur un poste Windows ». Avant d'être déclaré terminé, le guide SHALL avoir été suivi de bout en bout, sans autre connaissance du projet que ce qu'il dit, sur une copie neuve du dépôt avec un dossier de données vierge, jusqu'à une première transcription lue et une comparaison de deux résultats ; les écarts constatés SHALL être corrigés dans le guide. Aucune commande, taille ou durée non exécutée ou non mesurée ne SHALL être présentée comme vérifiée, et le guide SHALL être relu par le propriétaire avant clôture.

#### Scenario: Parcours à froid
- **WHEN** le guide est suivi pas à pas sur une copie neuve avec un dossier de données vierge
- **THEN** une première transcription est obtenue et lue sans autre aide, et chaque écart observé est consigné puis corrigé

#### Scenario: Windows non vérifié
- **WHEN** une procédure n'a été exécutée que sous Linux
- **THEN** le guide l'indique à côté de la version Windows au lieu de la présenter comme éprouvée
