## RENAMED Requirements

- FROM: `### Requirement: Interface HTML sans JavaScript, habillée par des feuilles de style locales`
- TO: `### Requirement: Interface locale avec amélioration progressive`
- FROM: `### Requirement: Suivi des opérations longues par actualisation`
- TO: `### Requirement: Suivi intégré des opérations longues`
- FROM: `### Requirement: Feuille complémentaire bornée`
- TO: `### Requirement: Hiérarchie visuelle applicative`
- FROM: `### Requirement: Classes d'habillage restreintes`
- TO: `### Requirement: Composants applicatifs sémantiques`

## MODIFIED Requirements

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

### Requirement: Composants applicatifs sémantiques
Les gabarits SHALL pouvoir employer des classes applicatives documentées en plus de Sumi pour les indicateurs, résultats compacts et formulaires. Les contrôles conservent leur sémantique HTML native ; aucune interaction essentielle ne repose sur un élément non interactif déguisé. Les états invalides et d'attente sont annoncés de façon accessible lorsqu'ils existent.

#### Scenario: Classe inconnue
- **WHEN** un composant de métriques ou de sélection est ajouté
- **THEN** ses classes et comportements sont testés pour leur contrat utile sans être refusés au seul motif qu'ils ne figuraient pas dans l'ancienne liste de classes Sumi

#### Scenario: Grille de cartes
- **WHEN** des résultats sont disposés en colonnes sur bureau
- **THEN** les composants restent sémantiques et se réorganisent à 360 px sans imposer un tableau de textes ni un défilement horizontal

### Requirement: Thème selon le système avec la palette Flexoki
Le thème clair ou sombre SHALL suivre `prefers-color-scheme` avec la palette Flexoki, sans imposer de bascule ni préférence mémorisée. Les nouveaux composants et contrôles conservent un contraste lisible dans les deux thèmes ; les avis de licence existants restent conservés.

#### Scenario: Système en thème sombre
- **WHEN** le système signale `prefers-color-scheme: dark`
- **THEN** textes, indicateurs, formulaires et états de survol/focus sont lisibles en palette sombre sans dépendre du script

#### Scenario: Thème non forcé
- **WHEN** une page est chargée
- **THEN** l'application n'impose aucun thème contraire au réglage système

### Requirement: Contenus jamais masqués par un accordéon
Erreurs, états partiels, marques de simulation, alertes utiles, indicateurs principaux et actions principales SHALL rester visibles. Le texte complet reste visible dans le détail et la comparaison sélectionnée. Réglages avancés, sélection de lot et journal normal peuvent être repliés ; une erreur d'opération reste visible même si son journal détaillé est fermé.

#### Scenario: Contenu à garder visible dans un accordéon
- **WHEN** les détails techniques et réglages avancés sont fermés
- **THEN** les chiffres clés, alertes, textes du détail et de la comparaison sélectionnée, lancement et arrêt applicable restent accessibles sans les ouvrir

#### Scenario: Journal d'une opération en cours
- **WHEN** une opération est en cours
- **THEN** son résumé d'état et sa cible sont visibles, son journal technique peut rester replié et toute erreur actuelle est affichée hors de ce journal

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

## ADDED Requirements

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
