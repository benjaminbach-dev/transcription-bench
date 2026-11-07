## Context

Pages produites par Jinja2 (Flask, serveur Waitress), 14 gabarits, `static_folder=None`, aucun en-tête de sécurité hormis les contrôles `Host`/`Origin`/jeton CSRF. La règle actuelle interdit tout CSS et tout JavaScript ; un test vérifie même que `/static/base.css` répond 404. Les specs de référence (`openspec/specs/`) existent depuis l'archivage de `add-benchmark-prototype` (2026-11-03).

Sumi.css (v1.0.0 selon son en-tête, dépôt `vladocar/Sumi.css`, commit `cee85b75efb2f129b82bc014439381b57ede7c22` du 2026-11-02, licence MIT) : fichier unique de 28 245 octets minifié (`sumi.min.css`, SHA-256 `3535cf90e19150a2805dd57ad442d8f6e4a04ed4f50aa53b34b8306d10297116`), 0 `url()`, 0 `@import`. Styles d'éléments à spécificité nulle (`:where()`), jetons `--s-*` déclarés sur `:root` (clair), puis dans `@media (prefers-color-scheme: dark)` sur `:root:not([data-theme="light"])` (sombre). Elle utilise `:where()`, `:has()` et `color-mix()` : Chrome/Edge 111, Firefox 121, Safari 16.2 ; selon la doc officielle, un navigateur plus ancien affiche des pages lisibles avec des couleurs de survol et de focus plus simples (non vérifié ici : si `color-mix()` est ignoré, le fond d'un bouton survolé pourrait devenir transparent).

**Flexoki** (Steph Ango, https://stephango.com/flexoki, licence MIT) : palette « encre sur papier », 8 valeurs de base (3 de texte, 3 d'interface, 2 de fond) et 8 teintes d'accent, jeux clair et sombre. Les valeurs sont reprises du site officiel (papier `#FFFCF0`, noir `#100F0F`, rouge 600 `#AF3029` / 400 `#D14D41`, bleu 600 `#205EA6` / 400 `#4385BE`, etc.).

## Faisabilité constatée (2026-11-03)

Essai jetable hors dépôt : les pages réelles de l'application (accueil, audios, moteurs, modèles, exécutions, résultats, détail d'un résultat, comparaisons) enregistrées telles quelles, reliées à `sumi.min.css` **sans modifier le HTML**, et observées par un navigateur (largeur 1280 px et 420 px, thème sombre émulé). Relevé factuel :

- Fonctionne sans retouche : titres, listes, `<dl>`, formulaires (champs, listes déroulantes, cases à cocher, boutons radio, boutons), thème sombre via le système, aucune ressource externe chargée, aucune erreur de console hormis le `favicon.ico` 404.
- À corriger dans le HTML : lignes de 140 caractères à 1280 px (aucune largeur de lecture) ; tableaux (`audios`, `resultats`, `comparaisons`, `resultat`) qui débordent la page à 420 px (jusqu'à 1102 px de large) faute de conteneur défilant ; boutons de largeur disparate dans les formulaires.
- **Ne se corrige pas par du HTML seul** : les blocs `<pre>` des transcriptions ne se replient pas (une transcription de 5 700 px dans une boîte de 386 px) et les valeurs sans espace (SHA-256, identifiants) débordent de leur boîte (`<dd>`, `<h3>`). Il faut donc une feuille complémentaire (`white-space: pre-wrap`, `overflow-wrap`). C'est une limite de l'approche « seulement ajuster le HTML ».
- Lecture du code amont de Sumi (2026-11-03) : un bouton se pilote par `--s-btn` / `--s-btn-on` ; `.secondary`, `.contrast` et `.outline` le modifient ; `.danger` n'existe que pour `.callout`. Il n'existe donc pas de bouton « danger » natif.
- Non observé : la vue `comparaison.html` côte à côte (aucun résultat à comparer dans l'essai) ; sa vérification visuelle est une tâche. Non essayé non plus : le rendu de la palette Flexoki (tâche de vérification visuelle et de contraste).

## Goals / Non-Goals

**Goals:**
- Un rendu lisible, sobre et cohérent (palette Flexoki), clair ou sombre selon le système, utilisable de 360 px à 1280 px de large.
- Aucun accès externe : les feuilles sont servies par l'application elle-même, hors ligne.
- La règle « jamais de JavaScript » reste vérifiée par des tests de gabarits ; aucune politique de sécurité de contenu (l'application est strictement locale, décision du propriétaire).
- Le moins possible de CSS propre : Sumi pour l'essentiel ; `app.css` se limite à trois rôles bornés (D4).

**Non-Goals:**
- Changer polices, tailles ou espacements de Sumi ; créer une charte graphique au-delà de la palette Flexoki.
- Bascule clair/sombre, mémorisation de préférence, tout JavaScript (dont `dialog.showModal()`, donc aucun usage de `<dialog>`).
- Refondre les textes, regrouper ou re-concevoir les formulaires ; pied de page (rien d'utile à y mettre, YAGNI).

## Decisions

### D1. Feuille copiée dans le dépôt, jamais depuis un CDN
Le serveur doit fonctionner hors ligne et ne contacter aucun tiers à l'ouverture d'une page. `sumi.min.css` est copié sous un dossier de ressources figées du paquet avec son texte de licence et une note de provenance (version, commit amont, SHA-256). L'en-tête de licence `/*! … MIT License */` reste dans le fichier. Une mise à jour est une opération explicite et son SHA-256 est contrôlé par un test.
**Fins de ligne** : le fichier est déclaré `-text` dans `.gitattributes`, sinon Git sous Windows peut le convertir en CRLF et casser le SHA-256 (hypothèse probable, à confirmer par la CI Windows).
*Alternative écartée* : CDN jsDelivr proposé par la doc de Sumi — accès externe à chaque page, contraire au projet.

### D2. Route dédiée et fixe, pas de dossier statique
`static_folder=None` est conservé (il n'y a toujours aucun service de fichiers arbitraires). Deux routes GET explicites servent exactement deux fichiers connus : `/sumi.css` et `/app.css`, avec `Content-Type: text/css; charset=utf-8` posé explicitement (sous Windows, le type MIME deviné par le registre est peu fiable), `X-Content-Type-Options: nosniff` et `Cache-Control: no-cache`. Les contrôles `Host` existants s'appliquent. Chemin lu par construction depuis le dossier du paquet, jamais depuis la requête. Les tests vérifient les en-têtes effectivement émis plutôt que de supposer le comportement d'un `send_file` (la route actuelle lit le fichier et répond sans ETag : `no-cache` suffit pour un fichier local de cette taille).

### D3. Jeu de classes Sumi minimal et nommé
Seuls les éléments HTML standard et les classes suivantes sont utilisés : `overflow-auto`, `grid` avec `cols-2` ou `cols-3`, `callout` (+ `warning`/`danger`/`success`), `secondary`, `contrast`, `outline`, `muted`, `small`, `narrow`, `prose`, plus `danger` sur les boutons (définie par `app.css`, D4). `cols-4` et au-delà ne sont pas employées (aucune page n'a quatre cartes par ligne) ; les ajouter serait un besoin nouveau. Les classes de grille ne se posent jamais sur `main` ni sur un tableau. `role="status"` des gabarits actuels est conservé ; `role="button"` (annonce un bouton que la touche Espace n'active pas sans JavaScript), `aria-busy` (animation de chargement permanente sans JavaScript) et `aria-invalid` (aucun formulaire ne l'utilise) ne sont pas employés. Aucun attribut `style` ni `data-theme` (il forcerait le thème). Un nouveau besoin se traite d'abord par un élément standard, ensuite par une classe Sumi, en dernier par `app.css`. `.prose` (68 ch) ou `.narrow` (44 rem) se posent sur les blocs de texte courant, jamais sur `main` (cela rétrécirait les tableaux de comparaison). Sumi ramène `grid.cols-2`/`cols-3` à une colonne sous 48 rem : la grille ne remplace pas la vérification à 360 px.

### D4. Feuille complémentaire à trois rôles bornés
`app.css` se charge après Sumi et se limite à :
1. **Retours à la ligne** : `white-space: pre-wrap; overflow-wrap: anywhere` sur `pre` ; `overflow-wrap: anywhere` sur `p`, `li`, `strong`, `dd`, `dt`, `h1` à `h4`, `code` hors tableaux (la vérification visuelle du 2026-11-03 a montré que des chemins absolus dans des `strong` et `li` et une empreinte dans un `strong` faisaient défiler la page à 360 px) ; `overflow-wrap: break-word` (qui ne réduit pas la largeur minimale) dans `td`, `th` et leurs descendants (dont `pre`, avec `white-space: pre-wrap` et `min-width: 14rem`, ≈ 25 caractères par ligne : constaté au navigateur à 360 px, sans largeur minimale la colonne se réduit au plus petit mot et la transcription tombe à ~10 caractères par ligne ; le conteneur défilant absorbe l'excédent), car `anywhere` y rétrécirait les colonnes jusqu'à empêcher le conteneur de défiler.
2. **Palette Flexoki** : surcharge des jetons de **couleur** de Sumi (`--s-bg`, `--s-surface`, `--s-card`, `--s-card-section`, `--s-text`, `--s-muted`, `--s-border`, `--s-border-strong`, `--s-primary`, `--s-on-primary`, `--s-secondary`, `--s-on-secondary`, `--s-contrast`, `--s-on-contrast`, `--s-success`, `--s-warning`, `--s-danger`, `--s-code-bg`) sur `:root` (clair) puis dans `@media (prefers-color-scheme: dark)` sur `:root:not([data-theme="light"])` (même sélecteur que Sumi, chargé après lui : à spécificité égale, la dernière règle l'emporte). Correspondance : papier → `--s-bg` ; base-50 → `--s-surface` ; texte → noir/base-200 ; base-600/500 → `--s-muted` ; bleu → `--s-primary` ; vert, orange, rouge → succès, avertissement, danger (600 en clair, 400 en sombre, comme le recommande Flexoki). Les jetons de police, de taille, d'espacement, d'ombre et `--s-mix`/`--s-mark-*` ne sont pas touchés.
3. **Bouton destructeur** : `button.danger { --s-btn: var(--s-danger); --s-btn-on: var(--s-on-primary); }` — une seule règle, qui s'appuie sur les mécanismes de Sumi (survol et focus compris).

Aucune autre propriété. La borne est testée par une **liste de propriétés autorisées** (`white-space`, `overflow-wrap`, `min-width` pour les seuls `pre` de cellule, les jetons de couleur nommés ci-dessus, `--s-btn`, `--s-btn-on`), pas par une liste d'interdits.
*Alternative écartée* : bouton destructeur seulement par `.outline`/`.contrast`, sans couleur — décision du propriétaire en faveur de la couleur.

### D5. Navigation commune et page courante
`base.html` expose un bloc `page_courante` ; le `header` contient un `nav` (avec `aria-label`, autre que « breadcrumb » qui déclenche un style particulier de Sumi) à deux listes : nom du programme en `strong` (pas un lien, qui doublerait « Accueil » ; pas un `h1` : Sumi le dessine à 45 px, démesuré dans une barre, constat visuel du 2026-11-03), puis les liens Accueil, Audios, Moteurs, Modèles, Exécutions, Résultats, Comparaisons, Opération. Sur les huit pages de premier niveau, le lien de la page porte `aria-current="page"` ; sur les sous-pages (détail d'un résultat, vue de comparaison, journal d'un moteur), le lien de la page parente porte `aria-current="true"` (Sumi stylise les deux) ; la page d'erreur n'en porte aucun. Les liens d'actions de l'accueil **restent** (aucun texte d'interface retiré : un test vérifie par exemple « Comparer des transcriptions d'un même audio » sur l'accueil). **Amendement du 2026-11-04** : le bandeau « non validé cliniquement » est retiré de `base.html` (décision du propriétaire : pré-projet de banc de modèles, sans diffusion clinique) ; les avertissements propres à une page ou à un résultat (marques factices, résultats partiels, arrêt du serveur) restent affichés. Il n'y a pas de `footer` de page.

### D6. Palette Flexoki : pourquoi par jetons, et comment la contrôler
Les couleurs de Sumi sont toutes des jetons : les remplacer ne touche aucune règle d'élément. Le contraste n'est pas garanti par la seule réputation de Flexoki (par exemple, un texte clair sur le vert 600 ou le rouge 400 est limite) : un test lit les jetons déclarés dans `app.css` et vérifie un rapport de contraste WCAG d'au moins 4,5 pour les paires texte/fond (`--s-text`/`--s-bg`, `--s-muted`/`--s-bg`, `--s-on-primary`/`--s-primary`, `--s-on-secondary`/`--s-secondary`, `--s-on-contrast`/`--s-contrast`, `--s-on-primary`/`--s-danger`, `--s-on-primary`/`--s-success`), en clair et en sombre. Si une paire échoue, on choisit une autre teinte de l'échelle étendue de Flexoki, pas un hex inventé. Constat à l'implémentation (2026-11-03) : le texte papier sur le vert 600 (4,39) et le texte noir sur le rouge 400 (4,42) échouent ; retenus : vert 700 `#536907` (succès, clair) et rouge 300 `#E8705F` (danger, sombre), valeurs officielles du dépôt kepano/flexoki. Seconde vérification (lot 4) : les liens sombres prennent le bleu 300 `#66A0C8`, car les liens emploient `--s-primary` comme couleur de texte et le bleu 400 `#4385BE` ne donne que 4,37 avec le noir. `--s-border-strong` passe à la base 500 `#878580` dans les deux thèmes, pour les bordures de champs (composant d'interface, WCAG 1.4.11, seuil de 3 : les teintes précédentes ne donnaient que 2,00 en clair et 2,34 en sombre). L'avis de licence Flexoki (MIT, © Steph Ango) figure dans un commentaire en tête d'`app.css` et dans `docs/licences-modeles.md`.

### D7. Hiérarchie des titres et boutons secondaires
Chaque page a exactement un `h1` (son titre) et aucun saut de niveau (h1 → h2 → h3). Les boutons de simple contrôle (« Vérifier la demande (aucun lancement) », « Vérifier la compatibilité sans télécharger », « Vérifier avec … ») portent `secondary` ; les actions principales (lancer, télécharger, installer, comparer) gardent le style primaire ; les actions destructrices portent `danger`. Largeur de lecture : `prose` s'applique à tous les paragraphes, listes et listes de définitions de texte courant (pas seulement à certains), pour une largeur homogène.

### D8. Cartes et accordéons natifs (lot 5)
Le prisme non technique se lit d'abord : une carte de synthèse, les résultats par audio, puis les détails techniques repliés dans des accordéons ouverts en un clic.

- **Cartes** : un `article` par moteur, modèle, exécution, audio, groupe de comparaison et section de l'accueil ; le `header` de la carte porte son titre (jamais un titre hors carte) ; un `footer` de carte reçoit l'action ou le lien de la carte. `base.html` garde un seul `header` de page, aucun `footer` de page : les `header`/`footer` de cartes sont donc enfants d'un `article`. Le test de squelette est amendé en conséquence (un `header` enfant direct de `body`, les autres dans un `article`).
- **Accordéons** : `details` + `summary`, sans JavaScript. Le `summary` porte un libellé seul : ni titre, ni lien, ni bouton. La hiérarchie des titres reste dans les cartes (`h2` de section, `h3` de carte, `h4` dans une carte), sans saut.
- **Grilles** : `div.grid.cols-2` pour les cartes de moteurs et de modèles locaux, `div.grid.cols-3` pour les sections de l'accueil ; les cartes d'exécution restent en pleine largeur (elles contiennent des formulaires). Sumi ramène ces grilles à une colonne sous 48 rem ; `cols-4` n'est pas employée.
- **Contenus jamais masqués** : erreurs, marques `FACTICE`/`SYNTHÉTIQUE`/`MESURES SIMULÉES`, résultats partiels, refus de dépôt, texte transcrit (`pre`), état de l'opération et boutons d'action restent hors de tout accordéon fermé. Un `details` qui contient une erreur ou un avertissement porte `open` côté serveur, et le journal d'une opération en cours, échouée ou interrompue est ouvert d'emblée. Les champs de formulaire (threads, réglages de famille) peuvent être repliés, leurs boutons de soumission non.
- **Où va le détail** : par audio — segments horodatés, mesures détaillées, informations du fichier source, paramètres utilisés et timings natifs ; globalement — mesures de l'opération, modèle et moteur, réglages de l'exécution, ordinateur et version du programme. Les listes de résultats gardent un tableau réduit (Exécution, Date, Modèle, État, Marques) et le moteur, les audios traités et la durée passent dans un accordéon ; les comparaisons sont titrées par les noms d'audios consignés (`noms`), l'empreinte SHA-256 passant en `small`/accordéon.
- **Vérification** : le contrôle automatisé s'appuie sur `html.parser` (un `details` fermé ne contient ni `pre`, ni bouton, ni encart `warning`/`danger`, ni `role="status"`), le rendu visuel restant à observer par le navigator.

## Risks / Trade-offs

- **`:has()`/`color-mix()` absents d'anciens navigateurs** → dégradation prévue par Sumi (non vérifiée ici, voir Context) ; versions minimales à documenter dans le guide utilisateur (changement `rediger-documentation-utilisateur`).
- **Tests existants qui interdisent `<link>`** → une fonction partagée, fondée sur `html.parser`, autorise exactement les deux feuilles locales et conserve l'interdiction de tout le reste.
- **Dépendances tierces** : fichiers figés, pas de mise à jour automatique ; les licences MIT imposent de garder les avis de copyright (Sumi dans le fichier et la licence jointe, Flexoki en tête d'`app.css`).
- **Contraste de la palette** → test de contraste (D6), et vérification visuelle clair/sombre. Limite connue : `--s-muted` sur `--s-surface`/`--s-card`/`--s-card-section` et dans les encarts, et `--s-primary` sur `--s-card-section` en sombre, restent sous 4,5 ; aucun gabarit ne les utilise aujourd'hui (à surveiller à toute nouvelle classe ou élément).
- **`app.css` sort de la sobriété initiale** (D4 initiale : aucune couleur) → assumé : la couleur passe par les seuls jetons de Sumi ; si Flexoki est abandonné un jour, supprimer le bloc de jetons suffit.
- **Favicon** : le navigateur demande `/favicon.ico` et reçoit 404 (bruit dans la console, sans effet) ; laissé tel quel.
- **Hiérarchie des titres** : `base.html` portait `h1` = nom du programme et les pages commençaient en `h2`. Le nom passe dans le `nav` en `strong` ; chaque page devient `h1` (son titre), ses sous-titres `h2`, etc. : renumérotation de balises seulement, sans changer un texte (D7).
- **Cartes et accordéons sans JavaScript** (D8) → la seule interactivité est celle du navigateur (`details`/`summary`), sans état mémorisé : un rechargement referme les accordéons sauf ceux que le serveur ouvre (`open`). Aucun test ne peut prouver le rendu visuel des cartes et des grilles : il reste à observer par le navigator.
- **`header`/`footer` de cartes** → le test de squelette exigeait un seul `header` et aucun `footer` ; il est amendé (les `header`/`footer` de cartes sont enfants d'un `article`) plutôt que supprimé, pour garder l'unicité de l'en-tête de page.

## Migration Plan

1. `add-benchmark-prototype` est archivé (2026-11-03) ; les specs de référence existent. Mettre à jour `AGENTS.md` d'abord (tâche 1.2), faute de quoi toute implémentation enfreint la consigne actuelle.
2. Implémenter, vérifier visuellement (voir tâches), mettre à jour le README minimalement (la refonte du README relève du change de documentation).
3. À l'archivage de ce change, corriger à la main le `## Purpose` de `openspec/specs/local-web-interface/spec.md` (« sans CSS ni JavaScript »).
4. Ordre conseillé avec `rediger-documentation-utilisateur` : habillage d'abord (préalable dur : navigation, libellés et navigateurs minimaux définitifs).

## Open Questions

- Noms définitifs des routes (`/sumi.css`, `/app.css`) : conventionnels, modifiables sans conséquence.
- Teintes exactes retenues pour chaque jeton : fixées à l'implémentation (voir `ressources/app.css`), d'après le test de contraste (D6).
