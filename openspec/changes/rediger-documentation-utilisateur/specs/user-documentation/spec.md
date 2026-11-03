## ADDED Requirements

### Requirement: Documentation organisée en trois niveaux
Le dépôt SHALL fournir un `README.md` court, un guide utilisateur (`docs/guide-utilisateur.md`) et une documentation technique (`docs/technique.md`). Le `README.md` SHALL tenir en moins de soixante lignes : usage, avertissement clinique, commande de lancement, liens vers le guide et la documentation technique, sans détail d'implémentation ni de CI. La documentation technique SHALL reprendre le contenu technique de l'ancien README sans perte.

#### Scenario: Premier contact
- **WHEN** une personne ouvre le `README.md`
- **THEN** elle y trouve en moins de soixante lignes ce que fait l'outil, que ce n'est pas un outil médical validé, et un lien direct vers le guide utilisateur

#### Scenario: Aucune perte d'information
- **WHEN** chaque section de l'ancien README est comparée à la documentation actuelle
- **THEN** chacune est conservée dans la documentation technique, réécrite dans le guide, ou déclarée obsolète avec sa raison

### Requirement: Termes techniques maîtrisés
Le guide et le README SHALL éviter le jargon : tout terme technique inévitable (par exemple moteur, modèle, terminal, empreinte, hors ligne) SHALL être défini en une phrase à sa première apparition et dans une section intitulée « Glossaire ». Les termes d'une liste d'interdits maintenue par un test (au minimum CSRF, WSGI, Flask, Jinja, venv, namespace, mmap, RTF, `HF_HUB_OFFLINE`) SHALL NOT apparaître dans le guide ni le README, sauf dans le glossaire ou dans un libellé d'interface en gras.

#### Scenario: Terme technique défini
- **WHEN** le guide emploie pour la première fois le mot « modèle » ou « moteur »
- **THEN** une phrase le définit à cet endroit et le glossaire le reprend

#### Scenario: Terme interdit
- **WHEN** un terme de la liste d'interdits apparaît dans le guide ou le README hors glossaire et hors libellé en gras
- **THEN** le test de cohérence de la documentation échoue

### Requirement: Libellés d'interface en gras
Les libellés exacts de l'interface cités dans le guide SHALL être écrits en gras, et le gras SHALL NOT servir à autre chose. Chaque texte en gras SHALL être présent dans les gabarits ou les chaînes de `transcription_bench/web`, dans le titre d'une page, ou dans une liste blanche explicite du test.

#### Scenario: Libellé changé dans l'interface
- **WHEN** un libellé d'une page est modifié sans mise à jour du guide
- **THEN** le test de cohérence échoue en nommant le libellé et le fichier

### Requirement: Parcours pas à pas de bout en bout
Le guide SHALL décrire dans l'ordre, de rien à une première transcription lue puis comparée : prérequis (système, espace disque, mémoire, versions minimales du navigateur), outil de lancement, obtention du projet, terminal, lancement, page dans le navigateur, dépôt des audios, moteur, modèle, transcription et suivi, lecture, comparaison de deux résultats, arrêt et relancement.

#### Scenario: Parcours complet
- **WHEN** le sommaire du guide est lu
- **THEN** chacune de ces étapes y figure, dans cet ordre

### Requirement: Étapes en trois parties pour Linux et Windows
Chaque étape du parcours SHALL indiquer ce qu'il faut faire, ce que l'on doit voir, et quoi faire sinon (renvoi vers le dépannage). Les commandes à copier SHALL exister pour Linux et pour Windows, avec le nom du terminal à ouvrir pour chacun.

#### Scenario: Étape complète
- **WHEN** une étape du parcours est lue
- **THEN** elle indique l'action, le résultat attendu avec le libellé exact de l'interface et un renvoi au dépannage

#### Scenario: Les deux systèmes
- **WHEN** une commande doit être saisie dans un terminal
- **THEN** la version Linux et la version Windows sont présentes

### Requirement: Exemple concret vérifié
Le parcours principal SHALL utiliser `handy-computer/whisper-large-v3-turbo-gguf` avec le moteur transcribe.cpp et le fichier `whisper-large-v3-turbo-Q5_K_M.gguf`, en indiquant la taille à télécharger. Durée, mémoire et espace disque SHALL n'être indiqués que s'ils ont été mesurés, avec la machine de mesure, sinon signalés « non mesuré ». Un tableau SHALL lister les autres modèles d'essai vérifiés (moteur, identifiant, taille, remarque) avec un renvoi vers les licences.

#### Scenario: Identifiants exacts
- **WHEN** le guide indique un identifiant de modèle ou un nom de fichier
- **THEN** il figure dans `docs/licences-modeles.md` ou dans les preuves de validation du projet

#### Scenario: Mesure absente
- **WHEN** le guide mentionne une durée ou une taille mémoire sans mesure faite
- **THEN** il la signale « non mesurée » au lieu de l'estimer

### Requirement: Comparaison expliquée sans jugement
Le guide SHALL expliquer comment comparer deux résultats, sans prétendre dire quel modèle est le meilleur ni que le texte obtenu est exact.

#### Scenario: Lecture d'une comparaison
- **WHEN** le guide présente la comparaison
- **THEN** il indique que le texte le plus fluide n'est pas forcément le plus exact et que l'outil n'est pas validé cliniquement

### Requirement: Limites et vie privée en clair
Le guide SHALL expliquer en langage courant, au début et là où c'est pertinent : l'absence de validation clinique ; que les audios et transcriptions restent sur l'ordinateur ; les limites connues qui touchent l'utilisateur (une seule transcription à la fois, ordinateur sans carte graphique exploitée, systèmes pris en charge) ; que les performances dépendent de l'ordinateur.

#### Scenario: Audios locaux
- **WHEN** le guide présente le dépôt des audios
- **THEN** il dit que les audios et les transcriptions ne quittent pas l'ordinateur

### Requirement: Accès réseau décrits tels qu'ils sont
Le guide SHALL lister les accès réseau réels de l'outil (installation de l'outil de lancement, obtention du projet, premier lancement, installation d'un moteur, vérification et téléchargement d'un modèle), dire quand ils ont lieu, à quelle quantité de données et qu'ils ne se produisent que sur action explicite de l'utilisateur, sauf le premier lancement s'il télécharge de lui-même ses dépendances.

#### Scenario: Premier lancement
- **WHEN** le guide présente le premier lancement
- **THEN** il dit si ce lancement télécharge des éléments, d'après l'observation du parcours à froid

### Requirement: Dépannage en langage courant
Le guide SHALL contenir une section de dépannage organisée en « ce que vous voyez », « cause probable », « que faire », couvrant au minimum : port déjà utilisé, commande de lancement introuvable, moteur non prêt ou installation échouée, modèle refusé ou introuvable, téléchargement interrompu ou espace disque insuffisant, absence de connexion Internet, audio illisible ou format non pris en charge, transcription vide ou exécution interrompue, page qui ne s'ouvre pas.

#### Scenario: Message cité
- **WHEN** un cas du dépannage cite un message
- **THEN** ce message existe dans le code ou les gabarits de l'application, ou a été relevé lors d'un essai pour un message du système ou du navigateur

### Requirement: Liens valides
Un test de cohérence de la documentation SHALL vérifier que tous les liens relatifs du README et des documents du dossier `docs/` pointent vers un fichier existant. Il SHALL s'exécuter dans la suite habituelle, sans réseau ni nouvelle dépendance, en lisant les fichiers en UTF-8.

#### Scenario: Lien cassé
- **WHEN** le README renvoie vers un fichier qui n'existe plus
- **THEN** le test de cohérence échoue

### Requirement: Niveau de vérification affiché
Chaque procédure du guide SHALL porter son niveau de vérification : « vérifié sous Linux le <date> », « contrôlé par la CI Windows » en précisant ce qui l'a été, ou « non vérifié sur un poste Windows ». Aucune commande, taille ou durée non exécutée ou non mesurée ne SHALL être présentée comme vérifiée.

#### Scenario: Windows non vérifié
- **WHEN** une procédure n'a été exécutée que sous Linux
- **THEN** le guide l'indique à côté de la version Windows au lieu de la présenter comme éprouvée
