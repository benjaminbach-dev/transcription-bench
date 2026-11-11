# local-web-interface Specification

## Purpose
Permet de lancer l'outil de benchmark sur un poste Windows ou Linux et de le piloter entièrement depuis une page web locale sans JavaScript, habillée par des feuilles de style locales.

## Requirements

### Requirement: Lancement par une commande unique
Le programme SHALL se lancer par une seule commande uv documentée, identique sous Windows x64 et Linux x64, qui prépare au premier lancement l'environnement Python 3.12 du serveur et ses dépendances, sans droits administrateur ni modification du Python système.

#### Scenario: Premier lancement
- **WHEN** l'utilisateur exécute la commande de lancement sur un poste disposant de uv mais sans environnement préparé
- **THEN** l'environnement du serveur est créé avec les versions verrouillées, puis le serveur démarre

#### Scenario: uv absent
- **WHEN** la documentation de lancement est suivie sur un poste sans uv
- **THEN** elle indique la procédure officielle d'installation utilisateur de uv pour Windows et Linux

### Requirement: Aucun moteur ni modèle installé au lancement
Le lancement du serveur MUST NOT installer de moteur, télécharger de modèle ni accéder au réseau pour ces ressources.

#### Scenario: Lancement sur une machine de développement
- **WHEN** le serveur est lancé sur un poste où aucun moteur n'est installé
- **THEN** l'interface est utilisable et indique les moteurs comme non installés, sans téléchargement

### Requirement: Écoute locale uniquement
Le serveur SHALL écouter uniquement sur l'adresse de bouclage locale, sur un port configurable, et afficher l'URL de l'interface au démarrage.

#### Scenario: Démarrage
- **WHEN** le serveur démarre
- **THEN** il est accessible depuis la machine via l'URL affichée et n'écoute sur aucune interface réseau externe

### Requirement: Requêtes locales vérifiées
Le serveur MUST refuser toute requête dont l'en-tête `Host` ne correspond pas à une adresse de bouclage locale avec le port d'écoute. Toute requête POST MUST porter un jeton anti-CSRF renouvelé à chaque démarrage du serveur et émis dans le formulaire ; si un en-tête `Origin` est présent, il MUST correspondre à l'origine locale, sinon la requête est refusée, y compris pour `Origin: null`.

#### Scenario: Host étranger
- **WHEN** une requête arrive avec un en-tête `Host` qui ne correspond pas à l'adresse locale et au port d'écoute
- **THEN** le serveur la refuse sans exécuter d'action

#### Scenario: POST sans jeton ou origine distante
- **WHEN** un formulaire est soumis sans jeton anti-CSRF valide, ou avec un en-tête `Origin` distant
- **THEN** le serveur refuse la demande et aucune action n'est lancée

### Requirement: Chemins contrôlés
Tout nom de fichier, dossier ou identifiant fourni par l'utilisateur MUST être résolu et vérifié comme restant sous le dossier de données prévu. Un chemin absolu, une remontée `..` ou un lien symbolique sortant MUST être refusé.

#### Scenario: Tentative de traversée de dossier
- **WHEN** une demande contient un nom de fichier ou un identifiant tentant de sortir du dossier autorisé
- **THEN** la demande est refusée avec un message explicite et aucun fichier hors du dossier n'est lu ni écrit

### Requirement: Interface locale avec amélioration progressive
Les pages SHALL être rendues en HTML avec les feuilles locales `/sumi.css` et `/app.css`. Un script local `/app.js` SHALL être autorisé pour améliorer les interactions. Sans JavaScript, lecture, tri, sélection, lancement et arrêt restent utilisables par liens et formulaires. Aucune ressource distante, aucun script incorporé ou gestionnaire `on…` SHALL être chargé.

#### Scenario: Inspection d'une page
- **WHEN** une page de l'interface est chargée
- **THEN** ses feuilles sont `/sumi.css` puis `/app.css`, son éventuel script exécutable est uniquement `/app.js`, et elle ne contient ni script incorporé, élément `style`, attribut `style`, gestionnaire `on…`, lien `javascript:`, iframe ou objet distant

#### Scenario: JavaScript indisponible
- **WHEN** le script est désactivé ou ne se charge pas
- **THEN** l'utilisateur peut consulter les résultats, trier, comparer, actualiser le suivi et préparer puis soumettre une exécution avec des contrôles HTML explicites

#### Scenario: Page d'erreur
- **WHEN** une requête parvenue à l'application vise une route inexistante, utilise une méthode non autorisée ou provoque une erreur interne
- **THEN** la réponse conserve le statut HTTP approprié et le squelette local, sans trace d'exception ni débogueur ; aucun script n'est nécessaire à la lecture du message

#### Scenario: Aucun service de fichiers arbitraires
- **WHEN** une requête vise une ressource statique autre que les trois routes fixes autorisées, dont `/static/base.css` ou un chemin remontant l'arborescence
- **THEN** l'application répond 404 sans lire de fichier choisi par la requête

### Requirement: Formulaires bornés
Les POST transmis à l'application SHALL être des formulaires `application/x-www-form-urlencoded` d'au plus 64 Kio : dépassement refusé en 413, type non pris en charge en 415, sans action. Les requêtes rejetées par le serveur HTTP avant l'application (HTTP malformé, en-têtes ou corps au-delà de ses propres limites) reçoivent sa réponse d'erreur sans déclencher d'action.

#### Scenario: Corps de formulaire trop volumineux
- **WHEN** un POST local autorisé soumet un formulaire de plus de 64 Kio parvenu à l'application
- **THEN** le serveur répond en 413 et aucune opération n'est lancée

#### Scenario: Type de formulaire non pris en charge
- **WHEN** un POST local autorisé soumet un corps avec un type autre que `application/x-www-form-urlencoded`
- **THEN** le serveur répond en 415 et aucune opération n'est lancée

#### Scenario: Rejet avant l'application
- **WHEN** une requête dépasse la limite de corps du serveur HTTP ou ne peut pas être interprétée par celui-ci
- **THEN** le serveur renvoie sa propre erreur HTTP sans appeler l'application ni lancer d'opération

### Requirement: Suivi intégré des opérations longues
Les installations, téléchargements et transcriptions SHALL rester en arrière-plan et leur suivi SHALL apparaître dans Exécutions. Le suivi distingue type, cible, état, erreur éventuelle et résultats accessibles. Une actualisation manuelle reste possible ; un suivi automatique local ne déclenche aucune mutation et ne prend pas le focus.

#### Scenario: Consultation pendant une exécution
- **WHEN** une transcription est active et l'utilisateur ouvre Exécutions
- **THEN** il voit son état, sa cible et le bouton d'arrêt ; les résultats déjà écrits restent accessibles et le formulaire ne permet pas une seconde opération concurrente

#### Scenario: Installation ou téléchargement actif
- **WHEN** une installation ou un téléchargement est actif
- **THEN** le même emplacement affiche son type et sa cible sans proposer un arrêt réservé à la transcription ni créer une nouvelle rubrique Opération

#### Scenario: Absence d'opération
- **WHEN** aucune opération n'a été enregistrée depuis le démarrage
- **THEN** Exécutions présente en priorité la préparation sans grand panneau technique vide

### Requirement: Une seule opération longue à la fois
Le programme SHALL n'exécuter qu'une opération longue à la fois (installation, téléchargement ou exécution) afin de ne pas fausser les mesures ; les vérifications distantes de modèles MUST aussi être refusées pendant une exécution ; une nouvelle demande MUST être refusée tant qu'une opération est en cours.

#### Scenario: Téléchargement demandé pendant une exécution
- **WHEN** l'utilisateur demande un téléchargement pendant une exécution
- **THEN** la demande est refusée avec l'indication de l'opération en cours

### Requirement: Arrêt du serveur
L'arrêt normal du serveur MUST terminer le processus du moteur en cours d'exécution, conserver les résultats déjà écrits et marquer l'exécution interrompue.

#### Scenario: Arrêt pendant une exécution
- **WHEN** le serveur reçoit Ctrl+C sous Windows ou Linux, ou SIGTERM sous Linux, alors qu'un moteur transcrit un audio
- **THEN** le processus du moteur est terminé, l'exécution est marquée interrompue et les résultats déjà enregistrés restent consultables ; une installation ou un téléchargement interrompu laisse sa ressource non prête

### Requirement: Échappement des contenus affichés
Tout contenu provenant de fichiers, de modèles ou de saisies utilisateur MUST être échappé avant insertion dans le HTML.

#### Scenario: Transcription contenant du balisage
- **WHEN** une transcription contient des caractères tels que `<` ou `&`
- **THEN** ils sont affichés comme texte et ne sont pas interprétés comme du HTML

### Requirement: Dossiers de données prédéfinis
Le programme SHALL utiliser des dossiers locaux prédéfinis sous `data/` pour les audios, les modèles, les environnements des moteurs et les résultats, créés au besoin et exclus du dépôt Git.

#### Scenario: Premier démarrage sans dossiers
- **WHEN** le serveur démarre et que les dossiers de données n'existent pas
- **THEN** ils sont créés et leur emplacement est affiché dans l'interface

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
Toutes les pages SHALL partager un squelette HTML : `lang="fr"`, `meta viewport`, un titre de page distinct, un `header` contenant la navigation, puis un `main`, ces deux éléments étant enfants directs de `body`. Le squelette ne porte aucun bandeau d'avertissement clinique : ce pré-projet de banc de modèles n'est pas diffusé en clinique (décision du propriétaire, 2026-11-04).

#### Scenario: Squelette d'une page
- **WHEN** une page quelconque est chargée
- **THEN** elle déclare `lang="fr"` et un `meta viewport`, son titre diffère de celui des autres pages, elle a un seul `header` enfant direct de `body` et son contenu est dans un `main` enfant direct de `body`

#### Scenario: Aucun bandeau d'avertissement clinique
- **WHEN** une page quelconque est chargée
- **THEN** elle n'affiche pas de bandeau « non validé cliniquement »

### Requirement: Hiérarchie des titres
Chaque page SHALL contenir exactement un élément `h1`, qui porte son titre, et ses sous-titres SHALL se suivre sans saut de niveau. Le nom du programme figure dans la navigation sans être un titre.

#### Scenario: Titres d'une page
- **WHEN** une page quelconque est chargée
- **THEN** elle contient un seul `h1` et aucun titre de niveau supérieur de plus d'un cran au précédent

### Requirement: Navigation commune et page courante
La navigation SHALL présenter exactement Résultats, Comparaisons, Exécutions, Modèles, Moteurs, Audios dans cet ordre. Accueil et Opération ne sont plus des rubriques. La page courante porte `aria-current="page"`, son parent porte `aria-current="true"` sur une sous-page ; une erreur ne signale aucune rubrique courante.

#### Scenario: Page courante signalée
- **WHEN** la page des modèles est chargée
- **THEN** la navigation contient les six liens dans l'ordre prescrit et seul Modèles porte `aria-current="page"`

#### Scenario: Sous-page
- **WHEN** un détail de transcription est chargé
- **THEN** Résultats porte `aria-current="true"` et aucun lien ne porte `aria-current="page"`

#### Scenario: Page d'erreur
- **WHEN** une page d'erreur est chargée
- **THEN** les six rubriques restent accessibles et aucune ne porte `aria-current`

### Requirement: Contenus longs lisibles de 360 à 1280 px
Les contenus SHALL rester lisibles de 360 à 1280 px sans défilement horizontal de page. Les listes et sélections de résultats réorganisent leurs indicateurs sans déplacement horizontal ; seuls les tableaux techniques secondaires peuvent défiler dans leur propre conteneur. Les transcriptions et valeurs longues se replient ; le texte courant garde une largeur de lecture confortable.

#### Scenario: Transcription longue sur petit écran
- **WHEN** une transcription de plusieurs milliers de caractères est affichée à 360 px
- **THEN** son texte se replie sans déborder de la page

#### Scenario: Tableau large sur petit écran
- **WHEN** une liste ou sélection comparative est affichée à 360 px
- **THEN** ses chiffres clés sont lisibles sans défilement horizontal ; un éventuel tableau technique ouvert en détail défile seulement dans son propre conteneur

#### Scenario: Valeur sans espace
- **WHEN** un identifiant long, une empreinte ou un chemin est affiché à 360 px
- **THEN** la valeur se replie sans être réduite à un tooltip ni faire déborder la page

#### Scenario: Texte courant sur grand écran
- **WHEN** une explication longue est affichée à 1280 px
- **THEN** sa largeur de lecture est limitée sans réduire inutilement celle des composants de résultats

### Requirement: Hiérarchie visuelle applicative
`/app.css` SHALL pouvoir définir tailles, espacements, dispositions adaptatives et couleurs pour hiérarchiser modèles, indicateurs et actions. Ses règles restent locales à l'application et la copie figée de Sumi n'est pas modifiée. Les textes secondaires restent lisibles ; les couleurs ne portent jamais seules un état ou une distinction.

#### Scenario: Feuille complémentaire bornée
- **WHEN** une liste ou comparaison est affichée
- **THEN** modèle et valeurs principales se distinguent visuellement des libellés, dates et détails par la taille, le poids et des accents de couleur cohérents en clair et sombre

### Requirement: Thème selon le système avec la palette Flexoki
Le thème clair ou sombre SHALL suivre `prefers-color-scheme` avec la palette Flexoki, sans imposer de bascule ni préférence mémorisée. Les nouveaux composants et contrôles conservent un contraste lisible dans les deux thèmes ; les avis de licence existants restent conservés.

#### Scenario: Système en thème sombre
- **WHEN** le système signale `prefers-color-scheme: dark`
- **THEN** textes, indicateurs, formulaires et états de survol/focus sont lisibles en palette sombre sans dépendre du script

#### Scenario: Thème non forcé
- **WHEN** une page est chargée
- **THEN** l'application n'impose aucun thème contraire au réglage système

### Requirement: Contraste de la palette
Chaque paire texte/fond des jetons de couleur déclarés dans `/app.css` SHALL atteindre un rapport de contraste WCAG d'au moins 4,5, en thème clair comme en thème sombre.

#### Scenario: Contraste des jetons
- **WHEN** un test calcule le rapport de contraste de chaque paire texte/fond déclarée dans `/app.css`, clair et sombre
- **THEN** aucune paire n'est inférieure à 4,5

### Requirement: Composants applicatifs sémantiques
Les gabarits SHALL pouvoir employer des classes applicatives documentées en plus de Sumi pour les indicateurs, résultats compacts et formulaires. Les contrôles conservent leur sémantique HTML native ; aucune interaction essentielle ne repose sur un élément non interactif déguisé. Les états invalides et d'attente sont annoncés de façon accessible lorsqu'ils existent.

#### Scenario: Classe inconnue
- **WHEN** un composant de métriques ou de sélection est ajouté
- **THEN** ses classes et comportements sont testés pour leur contrat utile sans être refusés au seul motif qu'ils ne figuraient pas dans l'ancienne liste de classes Sumi

#### Scenario: Grille de cartes
- **WHEN** des résultats sont disposés en colonnes sur bureau
- **THEN** les composants restent sémantiques et se réorganisent à 360 px sans imposer un tableau de textes ni un défilement horizontal

### Requirement: Cartes et accordéons natifs
Les regroupements de contenu SHALL employer les éléments HTML natifs : une carte est un `article` dont le `header` porte le titre de la carte (et non un titre de section hors carte), et un regroupement repliable est un `details` dont le premier enfant est un `summary` ; aucun `footer` n'est un enfant direct de `body`. Le `summary` SHALL NOT contenir de titre (`h1` à `h6`), de lien ni de bouton. La hiérarchie des titres reste sans saut de niveau malgré les cartes.

#### Scenario: Carte d'une page
- **WHEN** une page présente des cartes
- **THEN** chaque carte est un `article` dont le `header` porte un titre, et tout `footer` de la page est dans un `article`

#### Scenario: Résumé d'accordéon
- **WHEN** les gabarits sont analysés par un test
- **THEN** chaque `details` a exactement un `summary`, qui ne contient ni titre, ni lien, ni bouton

### Requirement: Contenus jamais masqués par un accordéon
Erreurs, états partiels, marques de simulation, alertes utiles, indicateurs principaux et actions principales SHALL rester visibles. Le texte complet reste visible dans le détail et la comparaison sélectionnée. Réglages avancés, sélection de lot et journal normal peuvent être repliés ; une erreur d'opération reste visible même si son journal détaillé est fermé.

#### Scenario: Contenu à garder visible dans un accordéon
- **WHEN** les détails techniques et réglages avancés sont fermés
- **THEN** les chiffres clés, alertes, textes du détail et de la comparaison sélectionnée, lancement et arrêt applicable restent accessibles sans les ouvrir

#### Scenario: Journal d'une opération en cours
- **WHEN** une opération est en cours
- **THEN** son résumé d'état et sa cible sont visibles, son journal technique peut rester replié et toute erreur actuelle est affichée hors de ce journal

### Requirement: Actions destructrices distinctes
Les boutons des actions destructrices (suppression d'un modèle local, arrêt d'une exécution) SHALL porter la classe `danger` et s'afficher avec la couleur de danger de la palette, sans autre texte ajouté ni confirmation JavaScript. Les autres boutons SHALL NOT porter cette classe ; les boutons de simple contrôle (vérifications) portent `secondary`.

#### Scenario: Action destructrice
- **WHEN** la page des modèles affiche un bouton de suppression et un bouton de téléchargement
- **THEN** seul le bouton de suppression porte la classe `danger`, et leurs apparences diffèrent

#### Scenario: Arrêt d'une exécution
- **WHEN** la page de l'opération en cours affiche le bouton d'arrêt
- **THEN** il porte la classe `danger`

### Requirement: Entrée directe et compatibilité des liens
L'URL `/` SHALL rediriger vers Résultats et `/operation` vers le suivi intégré d'Exécutions. Les liens internes et retours d'actions utilisent les nouvelles destinations. Les diagnostics de dossiers autrefois sur l'accueil restent accessibles au second plan sans recréer une page d'accueil.

#### Scenario: Ancien lien ou premier démarrage
- **WHEN** l'utilisateur ouvre `/` ou un ancien lien `/operation`
- **THEN** il rejoint respectivement `/resultats` ou `/executions#operation` par redirection GET locale sans perte de message d'état applicable ; sans résultats, une action vers Exécutions est proposée

#### Scenario: Vérification des dossiers
- **WHEN** l'utilisateur cherche les chemins locaux ou leur vérification
- **THEN** un accès secondaire depuis Exécutions les présente et permet la vérification explicite existante

### Requirement: Script servi localement par route fixe
`/app.js` SHALL servir un unique fichier connu avec `text/javascript; charset=utf-8`, `nosniff` et `no-cache`, sous les mêmes contrôles Host que les feuilles. Le navigateur n'exécute aucun code téléchargé à l'exécution depuis Internet, ni contenu de transcription comme code.

#### Scenario: Chargement hors ligne et hôte étranger
- **WHEN** `/app.js` est demandé depuis l'application locale sans réseau externe, puis avec un Host non autorisé
- **THEN** la première requête réussit avec les en-têtes prescrits et la seconde est refusée

### Requirement: Politique de sécurité des contenus
Les réponses HTML SHALL appliquer une CSP limitant scripts, styles, connexions et soumissions à l'origine locale, interdisant scripts incorporés, évaluation dynamique de code, inclusion en frame et changement de base URL. Les contenus utilisateur restent du texte échappé, y compris lors du suivi dynamique ; la CSP ne remplace pas Host, Origin ou anti-CSRF.

#### Scenario: Contenu hostile ou ressource externe
- **WHEN** un nom, journal ou texte transcrit contient du balisage exécutable ou qu'un contenu tente de charger un script externe
- **THEN** le contenu est affiché comme texte, aucun code ne s'exécute et la CSP bloque la ressource non autorisée

### Requirement: Lecture compacte et accessible
Les pages SHALL fonctionner à 360 px sans défilement horizontal de page ni déplacement horizontal pour lire leurs indicateurs principaux. Les modèles et valeurs ont une hiérarchie de taille visible ; texte et fond atteignent 4,5:1, et le focus est visible. Les explications identiques ne sont pas répétées dans chaque résultat ou modèle.

#### Scenario: Densité bureau et mobile
- **WHEN** les pages Résultats et Comparaisons sont ouvertes à 1280 × 800 puis 360 × 800 sur les jeux synthétiques de recette
- **THEN** le premier résultat et ses chiffres clés sont lisibles sans ouvrir de détails ; plusieurs résultats sont comparables visuellement sur bureau et les champs se réorganisent en blocs étiquetés sur mobile

#### Scenario: Explication unique
- **WHEN** une page présente plusieurs modèles ou résultats
- **THEN** chaque explication générale n'apparaît qu'une fois sur la page, aide comprise ; seuls libellés de champs, noms, valeurs et états propres aux éléments sont répétés si nécessaire
