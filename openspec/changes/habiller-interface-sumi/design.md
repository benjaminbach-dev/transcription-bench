## Context

Pages produites par Jinja2 (Flask, serveur Waitress), 14 gabarits, `static_folder=None`, aucun en-tête de sécurité hormis les contrôles `Host`/`Origin`/jeton CSRF. La règle actuelle interdit tout CSS et tout JavaScript ; un test vérifie même que `/static/base.css` répond 404.

Sumi.css (v1.0.0 selon son en-tête, dépôt `vladocar/Sumi.css`, commit `cee85b75efb2f129b82bc014439381b57ede7c22` du 2026-11-02, licence MIT) : fichier unique de 28 245 octets minifié (`sumi.min.css`, SHA-256 `3535cf90e19150a2805dd57ad442d8f6e4a04ed4f50aa53b34b8306d10297116`), 0 `url()`, 0 `@import`. Styles d'éléments à spécificité nulle (`:where()`), jetons `--s-*`, thème clair/sombre via `prefers-color-scheme`. Elle utilise `:where()`, `:has()` et `color-mix()` : Chrome/Edge 111, Firefox 121, Safari 16.2 ; un navigateur plus ancien affiche des pages lisibles avec des couleurs de survol et de focus plus simples (doc officielle).

## Faisabilité constatée (2026-11-03)

Essai jetable hors dépôt : les pages réelles de l'application (accueil, audios, moteurs, modèles, exécutions, résultats, détail d'un résultat, comparaisons) enregistrées telles quelles, reliées à `sumi.min.css` **sans modifier le HTML**, et observées par un navigateur (largeur 1280 px et 420 px, thème sombre émulé). Relevé factuel :

- Fonctionne sans retouche : titres, listes, `<dl>`, formulaires (champs, listes déroulantes, cases à cocher, boutons radio, boutons), thème sombre via le système, aucune ressource externe chargée, aucune erreur de console hormis le `favicon.ico` 404.
- À corriger dans le HTML : lignes de 140 caractères à 1280 px (aucune largeur de lecture) ; tableaux (`audios`, `resultats`, `comparaisons`, `resultat`) qui débordent la page à 420 px (jusqu'à 1102 px de large) faute de conteneur défilant ; boutons de largeur disparate dans les formulaires.
- **Ne se corrige pas par du HTML seul** : les blocs `<pre>` des transcriptions ne se replient pas (une transcription de 5 700 px dans une boîte de 386 px) et les valeurs sans espace (SHA-256, identifiants) débordent de leur boîte (`<dd>`, `<h3>`). Il faut donc une feuille complémentaire d'une dizaine de lignes (`white-space: pre-wrap`, `overflow-wrap: anywhere`). C'est une limite de l'approche « seulement ajuster le HTML » à connaître.
- Non observé : la vue `comparaison.html` côte à côte (aucun résultat à comparer dans l'essai) ; sa vérification visuelle est une tâche.

## Goals / Non-Goals

**Goals:**
- Un rendu lisible, sobre et cohérent, clair ou sombre selon le système, utilisable à 420 px comme à 1280 px.
- Aucun accès externe : la feuille est servie par l'application elle-même, hors ligne.
- La règle « jamais de JavaScript » reste vérifiée par des tests de gabarits ; aucune politique de sécurité de contenu (l'application est strictement locale, décision du propriétaire).
- Le moins possible de CSS propre : Sumi pour l'essentiel, quelques règles de débordement.

**Non-Goals:**
- Personnaliser les couleurs, polices ou jetons `--s-*` (les valeurs par défaut de Sumi conviennent ; changer plus tard = surcharger les jetons dans la feuille complémentaire).
- Bascule clair/sombre, mémorisation de préférence, tout JavaScript (dont `dialog.showModal()`, donc aucun usage de `<dialog>`).
- Refondre les textes, regrouper ou re-concevoir les formulaires.

## Decisions

### D1. Feuille copiée dans le dépôt, jamais depuis un CDN
Le serveur doit fonctionner hors ligne et ne contacter aucun tiers à l'ouverture d'une page. `sumi.min.css` est copié sous un dossier de ressources figées du paquet avec son texte de licence et une note de provenance (version, commit amont, SHA-256). L'en-tête de licence `/*! … MIT License */` reste dans le fichier. Une mise à jour est une opération explicite et son SHA-256 est contrôlé par un test.
*Alternative écartée* : CDN jsDelivr proposé par la doc de Sumi — accès externe à chaque page, contraire au projet.

### D2. Route dédiée et fixe, pas de dossier statique
`static_folder=None` est conservé (il n'y a toujours aucun service de fichiers arbitraires). Deux routes GET explicites servent exactement deux fichiers connus : `/sumi.css` et `/app.css`, avec `Content-Type: text/css; charset=utf-8` posé explicitement (sous Windows, le type MIME deviné par le registre est peu fiable), `X-Content-Type-Options: nosniff` et `Cache-Control: no-cache` (revalidation par ETag, pas de cache périmé après mise à jour). Les contrôles `Host` existants s'appliquent. Chemin lu par construction depuis le dossier du paquet, jamais depuis la requête.

### D3. Jeux de classes Sumi minimal et nommé
Seuls les mécanismes documentés de Sumi sont utilisés : éléments (`header`, `nav` avec deux `ul`, `main`, `footer`, `article`, `details`, `table`, `dl`), `aria-current="page"`, `role="button"`, et au plus les classes `.overflow-auto`, `.callout` (+ `.warning`/`.danger`/`.success`), `.secondary`, `.contrast`, `.outline`, `.muted`, `.small`, `.narrow`/`.prose`. Aucun attribut `style`. Un nouveau besoin se traite d'abord par un élément sémantique, ensuite par une classe Sumi, en dernier par une règle de la feuille complémentaire.

### D4. Feuille complémentaire limitée aux débordements
`app.css` se charge après Sumi et ne contient que : retour à la ligne des `<pre>` (`white-space: pre-wrap; overflow-wrap: anywhere`), coupure des valeurs longues dans `dd`, `td`, `th`, `h3`, `code` (`overflow-wrap: anywhere`). Aucune couleur, aucune police, aucune taille : tout ce qui relève de l'apparence reste dans les jetons de Sumi.

### D5. Navigation commune et page courante
`base.html` expose un bloc `page_courante` ; la barre de navigation (liens : Accueil, Audios, Moteurs, Modèles, Exécutions, Résultats, Comparaisons, Opération) marque la page courante par `aria-current="page"`. Les liens d'actions répétés sur l'accueil restent, mais l'accueil n'est plus le seul point d'entrée. L'avertissement « non validé cliniquement » est conservé dans l'en-tête sous forme d'encart.

## Risks / Trade-offs

- **`:has()`/`color-mix()` absents d'anciens navigateurs** → dégradation prévue par Sumi ; versions minimales à documenter dans le guide utilisateur (changement `rediger-documentation-utilisateur`).
- **Tests existants qui interdisent `<link>`** → ils doivent distinguer « lien vers la feuille locale autorisée » de « toute autre ressource », sans disparaître.
- **Dépendance tierce** : fichier figé, pas de mise à jour automatique ; la licence MIT impose de garder l'avis de copyright (conservé dans le fichier et la licence jointe).
- **Favicon** : le navigateur demande `/favicon.ico` et reçoit 404 (bruit dans la console, sans effet) ; laissé tel quel.

## Migration Plan

1. Décider du traitement de la dépendance à `add-benchmark-prototype` (non archivé à la rédaction : l'archivage conditionne l'archivage de ce change).
2. Implémenter, vérifier visuellement (voir tâches), mettre à jour `AGENTS.md` et le README minimalement (la refonte du README relève du change de documentation).
3. Ordre conseillé avec `rediger-documentation-utilisateur` : habillage d'abord, pour que le guide décrive l'interface définitive.

## Open Questions

- Noms définitifs des routes (`/sumi.css`, `/app.css`) : conventionnels, modifiables sans conséquence.
