## ADDED Requirements

### Requirement: Regroupement par source et grille
Les extractions SHALL être regroupées par triplet (empreinte du texte source, empreinte de la grille, empreinte du schéma généré). Seules les extractions d'un même groupe MUST être présentées comme comparables ; une différence de version des consignes au sein d'un groupe est signalée.

#### Scenario: Même source, grilles différentes
- **WHEN** une même transcription a été extraite avec deux versions d'une grille
- **THEN** les extractions apparaissent dans deux groupes distincts et ne peuvent pas être comparées entre elles

### Requirement: Liste des extractions
`extract list` et la page Extractions SHALL présenter les groupes, nommés par l'audio d'origine, le modèle de transcription et le titre de la grille, ordonnés par leur extraction la plus récente. Chaque entrée montre modèle, durée de l'extraction, délai avant le premier token, vitesse de génération, RAM moteur, CPU moteur, conformité, état et date courte. Le tri dans un groupe SHALL être `temps`, `ram`, `cpu` ou `recent` (défaut). Les extractions factices sont séparées et marquées.

#### Scenario: Liste en JSON
- **WHEN** un agent exécute `extract list --json`
- **THEN** la sortie contient un seul objet `schema: 1` avec, pour chaque groupe, sa clé et, pour chaque entrée, sa sélection `identifiant:ordre` et ses indicateurs bruts

#### Scenario: Tri inconnu
- **WHEN** un tri inconnu est demandé, par la commande ou par la page
- **THEN** il est refusé sans opération

#### Scenario: Valeurs absentes dans un tri
- **WHEN** une entrée n'a pas la valeur du critère de tri demandé
- **THEN** elle est placée après les entrées qui l'ont

### Requirement: Détail d'une extraction
`extract show ID` et la page de détail SHALL présenter, pour chaque source, les indicateurs principaux, puis la grille remplie case par case dans l'ordre de la grille avec le libellé de chaque case, la section « Autres informations utiles », puis le texte source complet. Sur grand écran, la grille et le texte source SHALL être lisibles côte à côte ; sur petit écran, ils se suivent. Sortie brute, grille copiée, message système, réglages et métadonnées restent accessibles.

#### Scenario: Relecture humaine
- **WHEN** l'utilisateur ouvre une extraction conforme à 1280 px
- **THEN** il lit les cases remplies et la transcription source sans ouvrir de détail ni changer de page, et un lien mène au résultat de transcription d'origine s'il existe encore

#### Scenario: Sortie non conforme
- **WHEN** une source est non conforme
- **THEN** son état et son motif sont visibles et la sortie brute est affichée à la place de la grille remplie

#### Scenario: Contenu hostile
- **WHEN** une valeur extraite ou un texte source contient du balisage
- **THEN** il est affiché comme texte, sans exécution

#### Scenario: Valeurs particulières de la grille remplie
- **WHEN** une case vaut null, une chaîne vide, une sous-case ou une liste
- **THEN** elle est lue comme « non mentionné » pour null, « (vide) » pour une chaîne vide, avec sous-cases et entrées de liste lisibles

### Requirement: Comparaison case par case
`extract compare CLE SEL SEL…` et la page de comparaison SHALL présenter 2 à 6 extractions d'un même groupe dans l'ordre reçu : indicateurs principaux de chaque modèle, puis une ligne par case de la grille et une colonne par extraction, puis `autres_informations` ; la transcription source est accessible une fois. Une sélection hors groupe, mal formée, hors bornes ou mêlant factices et réelles MUST être refusée. Sur petit écran, la présentation se réorganise sans défilement horizontal de page.

#### Scenario: Trois modèles comparés
- **WHEN** l'utilisateur compare trois extractions conformes d'un même groupe
- **THEN** pour chaque case, les trois valeurs sont lisibles sur une même ligne à 1280 px, « non mentionné » étant affiché explicitement

#### Scenario: Extraction non conforme dans la sélection
- **WHEN** une des extractions comparées est non conforme
- **THEN** sa colonne indique l'état et renvoie à sa sortie brute, sans valeur inventée

### Requirement: Aucun jugement de qualité
Les vues d'extraction MUST NOT calculer ni afficher de score de qualité, de taux de remplissage présenté comme une qualité, ni désigner un meilleur modèle. Les meilleures valeurs observées de durée et de RAM MAY être signalées comme pour les transcriptions. L'aide SHALL rappeler qu'une grille bien remplie n'est pas une preuve d'exactitude médicale et que la vérification appartient à un humain ou à un agent local extérieur au programme.

#### Scenario: Aide des indicateurs
- **WHEN** l'utilisateur consulte l'aide des extractions
- **THEN** elle définit chaque indicateur (tokens, délai avant le premier token, vitesses, RAM, CPU, conformité) et rappelle que la conformité au schéma ne mesure que la forme

### Requirement: Lecture sans modification
Les commandes et pages de consultation des extractions MUST NOT écrire, réécrire ni supprimer de fichier de résultat, ni accéder au réseau ; elles appliquent le contrôle `Host` et le confinement des identifiants existants. Seule la récupération exécutée sous le verrou d'instance au démarrage du serveur ou d'une commande peut clore une extraction abandonnée, avant toute consultation.

#### Scenario: Identifiant sortant
- **WHEN** un identifiant d'extraction contient `..` ou un chemin absolu
- **THEN** la demande est refusée sans lecture hors de `data/extractions/`
