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
`static_folder=None` est conservé (il n'y a toujours aucun service de fichiers arbitraires). Deux routes GET explicites servent exactement deux fichiers connus : `/sumi.css` et `/app.css`, avec `Content-Type: text/css; charset=utf-8` posé explicitement (sous Windows, le type MIME deviné par le registre est peu fiable), `X-Content-Type-Options: nosniff` et `Cache-Control: no-cache`. Les contrôles `Host` existants s'appliquent. Chemin lu par construction depuis le dossier du paquet, jamais depuis la requête. Les tests vérifient les en-têtes effectivement émis (ETag compris) plutôt que de supposer le comportement de `send_file`.

### D3. Jeu de classes Sumi minimal et nommé
Seuls les éléments HTML standard et les classes suivantes sont utilisés : `overflow-auto`, `callout` (+ `warning`/`danger`/`success`), `secondary`, `contrast`, `outline`, `muted`, `small`, `narrow`, `prose`, plus `danger` sur les boutons (définie par `app.css`, D4). `role="status"` des gabarits actuels est conservé ; `role="button"` (annonce un bouton que la touche Espace n'active pas sans JavaScript), `aria-busy` (animation de chargement permanente sans JavaScript) et `aria-invalid` (aucun formulaire ne l'utilise) ne sont pas employés. Aucun attribut `style` ni `data-theme` (il forcerait le thème). Un nouveau besoin se traite d'abord par un élément standard, ensuite par une classe Sumi, en dernier par `app.css`. `.prose` (68 ch) ou `.narrow` (44 rem) se posent sur les blocs de texte courant, jamais sur `main` (cela rétrécirait les tableaux de comparaison).

### D4. Feuille complémentaire à trois rôles bornés
`app.css` se charge après Sumi et se limite à :
1. **Retours à la ligne** : `white-space: pre-wrap; overflow-wrap: anywhere` sur `pre` ; `overflow-wrap: anywhere` sur `dd`, `h3`, `code` hors tableaux ; `overflow-wrap: break-word` (qui ne réduit pas la largeur minimale) dans `td` et `th`, car `anywhere` y rétrécirait les colonnes jusqu'à empêcher le conteneur de défiler.
2. **Palette Flexoki** : surcharge des jetons de **couleur** de Sumi (`--s-bg`, `--s-surface`, `--s-card`, `--s-card-section`, `--s-text`, `--s-muted`, `--s-border`, `--s-border-strong`, `--s-primary`, `--s-on-primary`, `--s-secondary`, `--s-on-secondary`, `--s-contrast`, `--s-on-contrast`, `--s-success`, `--s-warning`, `--s-danger`, `--s-code-bg`) sur `:root` (clair) puis dans `@media (prefers-color-scheme: dark)` sur `:root:not([data-theme="light"])` (même sélecteur que Sumi, chargé après lui : à spécificité égale, la dernière règle l'emporte). Correspondance : papier → `--s-bg` ; base-50 → `--s-surface` ; texte → noir/base-200 ; base-600/500 → `--s-muted` ; bleu → `--s-primary` ; vert, orange, rouge → succès, avertissement, danger (600 en clair, 400 en sombre, comme le recommande Flexoki). Les jetons de police, de taille, d'espacement, d'ombre et `--s-mix`/`--s-mark-*` ne sont pas touchés.
3. **Bouton destructeur** : `button.danger { --s-btn: var(--s-danger); --s-btn-on: var(--s-on-primary); }` — une seule règle, qui s'appuie sur les mécanismes de Sumi (survol et focus compris).

Aucune autre propriété. La borne est testée par une **liste de propriétés autorisées** (`white-space`, `overflow-wrap`, les jetons de couleur nommés ci-dessus, `--s-btn`, `--s-btn-on`), pas par une liste d'interdits.
*Alternative écartée* : bouton destructeur seulement par `.outline`/`.contrast`, sans couleur — décision du propriétaire en faveur de la couleur.

### D5. Navigation commune et page courante
`base.html` expose un bloc `page_courante` ; le `header` contient un `nav` (avec `aria-label`, autre que « breadcrumb » qui déclenche un style particulier de Sumi) à deux listes : nom du programme en texte simple (pas un lien, qui doublerait « Accueil »), puis les liens Accueil, Audios, Moteurs, Modèles, Exécutions, Résultats, Comparaisons, Opération. Sur les huit pages de premier niveau, le lien de la page porte `aria-current="page"` ; sur les sous-pages (détail d'un résultat, vue de comparaison, journal d'un moteur), le lien de la page parente porte `aria-current="true"` (Sumi stylise les deux) ; la page d'erreur n'en porte aucun. Les liens d'actions de l'accueil **restent** (aucun texte d'interface retiré : un test vérifie par exemple « Comparer des transcriptions d'un même audio » sur l'accueil). L'avertissement « non validé cliniquement » est conservé en haut de chaque page sous forme d'encart. Il n'y a pas de `footer`.

### D6. Palette Flexoki : pourquoi par jetons, et comment la contrôler
Les couleurs de Sumi sont toutes des jetons : les remplacer ne touche aucune règle d'élément. Le contraste n'est pas garanti par la seule réputation de Flexoki (par exemple, un texte clair sur le vert 600 ou le rouge 400 est limite) : un test lit les jetons déclarés dans `app.css` et vérifie un rapport de contraste WCAG d'au moins 4,5 pour les paires texte/fond (`--s-text`/`--s-bg`, `--s-muted`/`--s-bg`, `--s-on-primary`/`--s-primary`, `--s-on-secondary`/`--s-secondary`, `--s-on-contrast`/`--s-contrast`, `--s-on-primary`/`--s-danger`, `--s-on-primary`/`--s-success`), en clair et en sombre. Si une paire échoue, on choisit une autre teinte de l'échelle étendue de Flexoki, pas un hex inventé. L'avis de licence Flexoki (MIT, © Steph Ango) figure dans un commentaire en tête d'`app.css` et dans `docs/licences-modeles.md`.

## Risks / Trade-offs

- **`:has()`/`color-mix()` absents d'anciens navigateurs** → dégradation prévue par Sumi (non vérifiée ici, voir Context) ; versions minimales à documenter dans le guide utilisateur (changement `rediger-documentation-utilisateur`).
- **Tests existants qui interdisent `<link>`** → une fonction partagée, fondée sur `html.parser`, autorise exactement les deux feuilles locales et conserve l'interdiction de tout le reste.
- **Dépendances tierces** : fichiers figés, pas de mise à jour automatique ; les licences MIT imposent de garder les avis de copyright (Sumi dans le fichier et la licence jointe, Flexoki en tête d'`app.css`).
- **Contraste de la palette** → test de contraste (D6), et vérification visuelle clair/sombre.
- **`app.css` sort de la sobriété initiale** (D4 initiale : aucune couleur) → assumé : la couleur passe par les seuls jetons de Sumi ; si Flexoki est abandonné un jour, supprimer le bloc de jetons suffit.
- **Favicon** : le navigateur demande `/favicon.ico` et reçoit 404 (bruit dans la console, sans effet) ; laissé tel quel.
- **Hiérarchie des titres** : `base.html` porte aujourd'hui `h1` = nom du programme et les pages commencent en `h2` ; le déplacement du nom dans le `nav` ne doit pas supprimer le `h1` (à contrôler visuellement avec Sumi).

## Migration Plan

1. `add-benchmark-prototype` est archivé (2026-11-03) ; les specs de référence existent. Mettre à jour `AGENTS.md` d'abord (tâche 1.2), faute de quoi toute implémentation enfreint la consigne actuelle.
2. Implémenter, vérifier visuellement (voir tâches), mettre à jour le README minimalement (la refonte du README relève du change de documentation).
3. À l'archivage de ce change, corriger à la main le `## Purpose` de `openspec/specs/local-web-interface/spec.md` (« sans CSS ni JavaScript »).
4. Ordre conseillé avec `rediger-documentation-utilisateur` : habillage d'abord (préalable dur : navigation, libellés et navigateurs minimaux définitifs).

## Open Questions

- Noms définitifs des routes (`/sumi.css`, `/app.css`) : conventionnels, modifiables sans conséquence.
- Teintes exactes retenues pour chaque jeton : fixées à l'implémentation, d'après le test de contraste (D6).
