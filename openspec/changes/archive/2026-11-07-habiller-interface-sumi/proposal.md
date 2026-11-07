# Proposal

## Why

L'interface actuelle est du HTML brut, sans aucune feuille de style : c'était volontaire pour le prototype, mais le rendu est trop austère pour être utilisé confortablement, surtout par des personnes non techniques (lignes de 140 caractères, aucune navigation commune, avertissements noyés dans le texte, tableaux et transcriptions qui sortent de l'écran sur petit écran).

Une feuille de style existe qui convient à cette contrainte : [Sumi.css](https://vladocar.github.io/Sumi.css/) (licence MIT, un seul fichier, sans JavaScript ni dépendance, sans `url()` ni `@import`, thème clair et sombre automatique selon le système). Elle se pilote surtout par les éléments HTML sémantiques, avec peu de classes.

## What Changes

- Le serveur sert, depuis le dépôt (jamais depuis un CDN), une copie figée de `sumi.min.css` et une petite feuille complémentaire du projet, chargée après elle. Cette dernière fait trois choses seulement : retours à la ligne et coupures des valeurs longues, palette **Flexoki** (par surcharge des jetons de couleur de Sumi, clair et sombre), et couleur des boutons d'actions destructrices.
- Le squelette commun des pages (`base.html`) gagne une barre de navigation vers les pages principales (page courante signalée) ; les pages sont ajustées pour utiliser les éléments et classes de Sumi (conteneurs de tableaux défilants, largeur de lecture, encarts d'avertissement, boutons destructeurs distincts).
- Les pages restent **sans JavaScript** : aucun script, aucun attribut `style`, aucun élément `style`. Pas de bascule clair/sombre (elle exigerait du JavaScript) : le thème suit le réglage du système.
- La règle « HTML sans CSS ni JavaScript » (spec `local-web-interface`, `AGENTS.md`, README) devient « sans JavaScript, avec feuilles de style locales ».

Hors périmètre : politique de sécurité de contenu (usage strictement local), toute modification du JavaScript (il n'y en a pas et il n'y en aura pas), de la logique métier, des routes d'action ou des textes de l'interface (le vocabulaire technique des pages est l'objet d'un autre travail éventuel), charte graphique propre au-delà de la palette Flexoki (polices et tailles de Sumi inchangées), bascule clair/sombre, captures d'écran, icône du site.

## Capabilities

### New Capabilities

Aucune.

### Modified Capabilities

- `local-web-interface` : la règle « Interface HTML sans CSS ni JavaScript » est renommée et assouplie (feuilles de style locales autorisées, JavaScript toujours interdit), et de nouvelles exigences encadrent la feuille servie, le squelette et la lisibilité des contenus longs.

## Impact

- Code : `transcription_bench/web/app.py` (routes des feuilles), `transcription_bench/web/templates/*.html`, nouveau dossier de ressources statiques figées (`sumi.min.css`, feuille complémentaire, licences Sumi.css et Flexoki), `.gitattributes` (fin de ligne de `sumi.min.css` préservée).
- Tests : `verifier_html_seul` (7 fichiers de test) et la constante propre à `tests/test_audios.py` interdisent aujourd'hui `<link>` et « stylesheet », et `tests/test_web.py` vérifie que `/static/base.css` n'existe pas ; ils sont remplacés par une seule fonction partagée fondée sur `html.parser`, précisée et non supprimée.
- Documentation : `AGENTS.md` (ligne « HTML sans CSS ni JavaScript »), README, `docs/licences-modeles.md` (dépendances Sumi.css MIT et Flexoki MIT), `## Purpose` de la spec de référence `local-web-interface`.
- Préalable levé : `add-benchmark-prototype` a été archivé le 2026-11-03, les specs de référence existent (la modification et le renommage ont leur cible). Il reste à corriger à la main le `## Purpose`, qu'un delta ne peut pas modifier.
