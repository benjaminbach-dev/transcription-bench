## RENAMED Requirements

- FROM: `### Requirement: Interface HTML sans CSS ni JavaScript`
- TO: `### Requirement: Interface HTML sans JavaScript, habillée par des feuilles de style locales`

## MODIFIED Requirements

### Requirement: Interface HTML sans JavaScript, habillée par des feuilles de style locales
Toutes les pages produites par l'application SHALL être du HTML sans script, sans élément `style` et sans attribut `style` ; les actions passent par des liens et formulaires HTML. Chaque page SHALL se relier à exactement deux feuilles de style, `/sumi.css` puis `/app.css`, par des éléments `link rel="stylesheet"` à chemin relatif à la racine du serveur, et à aucune autre ressource externe ou distante. Les erreurs du serveur HTTP avant appel de l'application ne sont pas des pages de l'interface.

#### Scenario: Inspection d'une page
- **WHEN** une page quelconque de l'interface est chargée
- **THEN** elle ne contient aucun élément `script`, `style`, `iframe`, `object` ou `img`, aucun attribut `style`, aucun attribut de gestionnaire d'événement (`on…`), aucun lien `javascript:`, et ses seuls éléments `link` sont les deux feuilles `/sumi.css` et `/app.css`, dans cet ordre

#### Scenario: Page d'erreur
- **WHEN** une requête parvenue à l'application vise une route inexistante, utilise une méthode non autorisée ou provoque une erreur interne
- **THEN** la réponse conserve le statut HTTP approprié et présente une page HTML habillée des deux feuilles, sans JavaScript, sans trace d'exception ni débogueur interactif

#### Scenario: Aucun service de fichiers arbitraires
- **WHEN** une requête vise un chemin statique quelconque autre que `/sumi.css` et `/app.css` (par exemple `/static/base.css`, `/sumi.min.css` ou un chemin remontant l'arborescence)
- **THEN** l'application répond 404 sans lire de fichier choisi par la requête

## ADDED Requirements

### Requirement: Feuilles de style servies localement et figées
L'application SHALL servir `/sumi.css` (copie figée de `sumi.min.css` de Sumi.css) et `/app.css` (feuille complémentaire du projet) depuis des fichiers du dépôt, par des routes GET qui ne servent chacune qu'un fichier connu, avec le type `text/css; charset=utf-8` posé explicitement, `X-Content-Type-Options: nosniff` et `Cache-Control: no-cache`. Les contrôles de l'en-tête `Host` s'appliquent à ces routes. La copie de Sumi.css SHALL conserver son avis de licence MIT, être accompagnée du texte de la licence et d'une note de provenance (version amont, commit amont, SHA-256), et son SHA-256 SHALL être contrôlé par un test. Aucune feuille, police ou ressource SHALL être chargée depuis un réseau.

#### Scenario: Feuille servie hors ligne
- **WHEN** un navigateur charge une page puis `/sumi.css` et `/app.css` sans accès réseau externe
- **THEN** les deux feuilles répondent 200 avec le type `text/css; charset=utf-8`, `nosniff` et `no-cache`, et la page ne déclenche aucune autre requête que vers l'application

#### Scenario: Feuille modifiée sans décision
- **WHEN** le contenu de la copie de `sumi.min.css` ne correspond plus au SHA-256 consigné dans la note de provenance
- **THEN** un test de la suite échoue

#### Scenario: Hôte non local
- **WHEN** `/sumi.css` est demandée avec un en-tête `Host` qui ne correspond pas à l'adresse locale et au port d'écoute
- **THEN** la requête est refusée comme toute autre requête de l'application

### Requirement: Squelette et navigation communs
Toutes les pages SHALL partager un squelette HTML sémantique : `lang="fr"`, `meta viewport`, un titre de page distinct, un `header` contenant un `nav` à deux listes (nom du programme à gauche, liens à droite) vers Accueil, Audios, Moteurs, Modèles, Exécutions, Résultats, Comparaisons et Opération, un `main` et un `footer`, ces trois éléments étant enfants directs de `body`. Le lien de la page courante SHALL porter `aria-current="page"`, et lui seul. L'avertissement de non-validation clinique SHALL rester visible en haut de chaque page, dans un encart.

#### Scenario: Page courante signalée
- **WHEN** la page des modèles est chargée
- **THEN** la navigation contient les huit liens et seul celui des modèles porte `aria-current="page"`

#### Scenario: Avertissement visible
- **WHEN** une page quelconque est chargée
- **THEN** l'avertissement indiquant que le prototype n'est pas validé cliniquement figure dans un encart avant le contenu de `main`

### Requirement: Lisibilité des contenus longs
Les contenus susceptibles de dépasser la largeur de l'écran SHALL rester lisibles de 420 px à 1280 px de large sans défilement horizontal de la page : tout tableau est enveloppé dans un conteneur défilant, les blocs `pre` de transcription se replient à la ligne, et les valeurs sans espace (empreintes SHA-256, identifiants, chemins) se coupent plutôt que de déborder. La largeur d'un texte courant SHALL être limitée à une largeur de lecture confortable. `/app.css` SHALL se limiter à ces retours à la ligne et coupures : aucune couleur, police ni taille propre au projet.

#### Scenario: Transcription longue sur petit écran
- **WHEN** une transcription de plusieurs milliers de caractères est affichée à 420 px de large
- **THEN** le texte se replie à la ligne et la largeur défilable de la page ne dépasse pas la largeur de la fenêtre

#### Scenario: Tableau large sur petit écran
- **WHEN** la liste des résultats ou des comparaisons est affichée à 420 px de large
- **THEN** seul le conteneur du tableau défile horizontalement ; la page elle-même ne défile pas horizontalement

#### Scenario: Valeur sans espace
- **WHEN** une empreinte SHA-256 de 64 caractères est affichée dans un titre ou une liste de définitions à 420 px de large
- **THEN** elle se coupe sur plusieurs lignes et reste entièrement visible

#### Scenario: Feuille complémentaire bornée
- **WHEN** le contenu de `/app.css` est inspecté
- **THEN** il ne déclare ni couleur, ni police, ni taille de texte, ni jeton `--s-*`

### Requirement: Thème selon le système, sans script
Le thème clair ou sombre SHALL suivre le réglage du système de l'utilisateur par la seule feuille de style ; l'interface SHALL NOT proposer de bascule ni mémoriser de préférence, puisque cela exigerait du JavaScript.

#### Scenario: Système en thème sombre
- **WHEN** le système signale `prefers-color-scheme: dark` et qu'une page est chargée
- **THEN** la page s'affiche avec la palette sombre, texte et contrôles lisibles, sans aucun script

### Requirement: Classes et éléments d'habillage restreints
Les gabarits SHALL n'employer que des éléments HTML sémantiques et, au plus, les classes et attributs documentés par Sumi.css (`overflow-auto`, `callout` avec `warning`, `danger` ou `success`, `secondary`, `contrast`, `outline`, `muted`, `small`, `narrow`, `prose`, `role="button"`, `aria-current`, `aria-invalid`, `aria-busy`). Les actions destructrices (suppression d'un modèle, arrêt d'une exécution) SHALL se distinguer visuellement des actions ordinaires. L'élément `dialog` et ses classes SHALL NOT être utilisés (ils exigent du JavaScript).

#### Scenario: Classe inconnue
- **WHEN** les gabarits sont analysés par un test
- **THEN** toute classe utilisée appartient à la liste autorisée de cette exigence ou est déclarée dans `/app.css`, et aucun élément `dialog` n'est présent

#### Scenario: Action destructrice
- **WHEN** la page des modèles affiche un bouton de suppression et un bouton de téléchargement
- **THEN** leurs apparences diffèrent (classe distincte), sans autre texte ajouté ni confirmation JavaScript
