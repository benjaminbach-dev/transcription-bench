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

### Requirement: Feuilles de style servies par des routes fixes
L'application SHALL servir `/sumi.css` et `/app.css` depuis des fichiers du dépôt, par deux routes GET qui ne servent chacune qu'un fichier connu, avec le type `text/css; charset=utf-8` posé explicitement, `X-Content-Type-Options: nosniff` et `Cache-Control: no-cache`. Les contrôles de l'en-tête `Host` s'appliquent à ces routes. Aucune feuille, police ou ressource SHALL être chargée depuis un réseau.

#### Scenario: Feuilles servies hors ligne
- **WHEN** un navigateur charge une page puis `/sumi.css` et `/app.css` sans accès réseau externe
- **THEN** les deux feuilles répondent 200 avec le type `text/css; charset=utf-8`, `nosniff` et `no-cache`, et la page ne déclenche aucune autre requête que vers l'application

#### Scenario: Hôte non local
- **WHEN** `/sumi.css` est demandée avec un en-tête `Host` qui ne correspond pas à l'adresse locale et au port d'écoute
- **THEN** la requête est refusée comme toute autre requête de l'application

### Requirement: Copie figée de Sumi.css avec provenance
`/sumi.css` SHALL être une copie figée de `sumi.min.css` de Sumi.css, conservant son avis de licence MIT, accompagnée du texte de la licence et d'une note de provenance (version amont, commit amont, SHA-256). Le SHA-256 de la copie SHALL être contrôlé par un test, et le fichier SHALL être déclaré sans conversion de fin de ligne (`-text`) pour que ce contrôle donne le même résultat sous Linux et sous Windows.

#### Scenario: Feuille modifiée sans décision
- **WHEN** le contenu de la copie de `sumi.min.css` ne correspond plus au SHA-256 consigné dans la note de provenance
- **THEN** un test de la suite échoue

#### Scenario: Extraction sous Windows
- **WHEN** le dépôt est extrait sur un runner Windows et que la suite de tests s'exécute
- **THEN** le SHA-256 de la copie est identique à celui consigné

### Requirement: Squelette commun des pages
Toutes les pages SHALL partager un squelette HTML : `lang="fr"`, `meta viewport`, un titre de page distinct, un `header` contenant la navigation, puis un `main`, ces deux éléments étant enfants directs de `body`. L'avertissement de non-validation clinique SHALL rester visible en haut de chaque page, dans un encart placé avant le contenu de `main`.

#### Scenario: Avertissement visible
- **WHEN** une page quelconque est chargée
- **THEN** l'avertissement indiquant que le prototype n'est pas validé cliniquement figure dans un encart avant le contenu de `main`

#### Scenario: Squelette d'une page
- **WHEN** une page quelconque est chargée
- **THEN** elle déclare `lang="fr"` et un `meta viewport`, et son titre diffère de celui des autres pages

### Requirement: Hiérarchie des titres
Chaque page SHALL contenir exactement un élément `h1`, qui porte son titre, et ses sous-titres SHALL se suivre sans saut de niveau. Le nom du programme figure dans la navigation sans être un titre.

#### Scenario: Titres d'une page
- **WHEN** une page quelconque est chargée
- **THEN** elle contient un seul `h1` et aucun titre de niveau supérieur de plus d'un cran au précédent

### Requirement: Navigation commune et page courante
Le `header` SHALL contenir un `nav` portant un `aria-label`, à deux listes : le nom du programme en `strong`, puis des liens vers Accueil, Audios, Moteurs, Modèles, Exécutions, Résultats, Comparaisons et Opération. Sur chacune de ces huit pages, son lien SHALL porter `aria-current="page"` et lui seul ; sur une sous-page (détail d'un résultat, vue de comparaison, journal d'un moteur), le lien de la page parente SHALL porter `aria-current="true"` ; la page d'erreur n'en porte aucun.

#### Scenario: Page courante signalée
- **WHEN** la page des modèles est chargée
- **THEN** la navigation contient les huit liens et seul celui des modèles porte `aria-current="page"`

#### Scenario: Sous-page
- **WHEN** le détail d'un résultat est chargé
- **THEN** le lien « Résultats » porte `aria-current="true"` et aucun lien ne porte `aria-current="page"`

#### Scenario: Page d'erreur
- **WHEN** la page d'erreur est chargée
- **THEN** la navigation est présente et aucun lien ne porte `aria-current`

### Requirement: Contenus longs lisibles de 360 à 1280 px
Les contenus susceptibles de dépasser la largeur de l'écran SHALL rester lisibles de 360 px à 1280 px de large sans défilement horizontal de la page : tout tableau est enveloppé dans un conteneur défilant, les blocs `pre` de transcription se replient à la ligne, et les valeurs sans espace (empreintes SHA-256, identifiants, chemins) se coupent plutôt que de déborder. Les blocs de texte courant SHALL avoir une largeur de lecture limitée, sans limiter celle des tableaux.

#### Scenario: Transcription longue sur petit écran
- **WHEN** une transcription de plusieurs milliers de caractères est affichée à 360 px de large
- **THEN** le texte se replie à la ligne et la largeur défilable de la page ne dépasse pas la largeur de la fenêtre

#### Scenario: Tableau large sur petit écran
- **WHEN** la liste des résultats ou des comparaisons est affichée à 360 px de large
- **THEN** seul le conteneur du tableau défile horizontalement ; la page elle-même ne défile pas horizontalement

#### Scenario: Valeur sans espace
- **WHEN** une empreinte SHA-256 de 64 caractères ou un chemin absolu est affiché dans un titre, un paragraphe, une liste ou une liste de définitions à 360 px de large
- **THEN** il se coupe sur plusieurs lignes, reste entièrement visible et la page ne défile pas horizontalement

#### Scenario: Texte courant sur grand écran
- **WHEN** une page contenant un paragraphe long est affichée à 1280 px de large
- **THEN** les lignes du paragraphe restent d'une largeur de lecture confortable (vérification visuelle)

### Requirement: Feuille complémentaire bornée
`/app.css` SHALL se limiter à trois rôles : les retours à la ligne, coupures et largeur minimale des blocs `pre` de transcription dans les tableaux (`white-space`, `overflow-wrap`, `min-width`), la surcharge des jetons de couleur de Sumi pour la palette (clair et sombre), et la couleur des boutons destructeurs par `--s-btn` et `--s-btn-on`. Elle SHALL NOT déclarer de police, de taille, d'espacement ni de jeton de Sumi autre que les jetons de couleur nommés dans le design.

#### Scenario: Feuille complémentaire bornée
- **WHEN** le contenu de `/app.css` est analysé par un test
- **THEN** chaque propriété déclarée appartient à la liste autorisée (`white-space`, `overflow-wrap`, `min-width` pour les seuls `pre` de cellule, les jetons de couleur nommés dans le design, `--s-btn`, `--s-btn-on`)

### Requirement: Thème selon le système avec la palette Flexoki
Le thème clair ou sombre SHALL suivre le réglage du système de l'utilisateur par la seule feuille de style, avec la palette Flexoki, sans bascule, sans préférence mémorisée (cela exigerait du JavaScript) et sans attribut `data-theme` dans les gabarits. L'avis de licence MIT de Flexoki SHALL figurer dans la feuille et dans la documentation des licences.

#### Scenario: Système en thème sombre
- **WHEN** le système signale `prefers-color-scheme: dark` et qu'une page est chargée
- **THEN** la page s'affiche avec la palette sombre de Flexoki, texte et contrôles lisibles, sans aucun script (vérification visuelle)

#### Scenario: Thème non forcé
- **WHEN** les gabarits sont analysés par un test
- **THEN** aucun ne contient d'attribut `data-theme`

### Requirement: Contraste de la palette
Chaque paire texte/fond des jetons de couleur déclarés dans `/app.css` SHALL atteindre un rapport de contraste WCAG d'au moins 4,5, en thème clair comme en thème sombre.

#### Scenario: Contraste des jetons
- **WHEN** un test calcule le rapport de contraste de chaque paire texte/fond déclarée dans `/app.css`, clair et sombre
- **THEN** aucune paire n'est inférieure à 4,5

### Requirement: Classes d'habillage restreintes
Les gabarits SHALL n'employer que des éléments HTML standard et, au plus, les classes `overflow-auto`, `callout` (avec `warning`, `danger` ou `success`), `secondary`, `contrast`, `outline`, `muted`, `small`, `narrow`, `prose` et `danger` sur un bouton. Ils SHALL NOT employer l'élément `dialog`, `role="button"`, `aria-busy` ni `aria-invalid`.

#### Scenario: Classe inconnue
- **WHEN** les gabarits sont analysés par un test
- **THEN** toute classe littérale utilisée appartient à la liste autorisée, et aucun élément `dialog` ni attribut `role="button"`, `aria-busy` ou `aria-invalid` n'est présent

### Requirement: Actions destructrices distinctes
Les boutons des actions destructrices (suppression d'un modèle local, arrêt d'une exécution) SHALL porter la classe `danger` et s'afficher avec la couleur de danger de la palette, sans autre texte ajouté ni confirmation JavaScript. Les autres boutons SHALL NOT porter cette classe ; les boutons de simple contrôle (vérifications) portent `secondary`.

#### Scenario: Action destructrice
- **WHEN** la page des modèles affiche un bouton de suppression et un bouton de téléchargement
- **THEN** seul le bouton de suppression porte la classe `danger`, et leurs apparences diffèrent

#### Scenario: Arrêt d'une exécution
- **WHEN** la page de l'opération en cours affiche le bouton d'arrêt
- **THEN** il porte la classe `danger`
