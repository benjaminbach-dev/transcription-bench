# Proposal

## Why

L'interface actuelle est du HTML brut, sans aucune feuille de style : c'était volontaire pour le prototype, mais le rendu est trop austère pour être utilisé confortablement, surtout par des personnes non techniques (lignes de 140 caractères, aucune navigation commune, avertissements noyés dans le texte, tableaux et transcriptions qui sortent de l'écran sur petit écran).

Une feuille de style existe qui convient à cette contrainte : [Sumi.css](https://vladocar.github.io/Sumi.css/) (licence MIT, un seul fichier, sans JavaScript ni dépendance, sans `url()` ni `@import`, thème clair et sombre automatique selon le système). Elle se pilote surtout par les éléments HTML sémantiques, avec peu de classes.

## What Changes

- Le serveur sert, depuis le dépôt (jamais depuis un CDN), une copie figée de `sumi.min.css` et une très petite feuille complémentaire du projet, chargée après elle, limitée aux retours à la ligne et aux débordements.
- Le squelette commun des pages (`base.html`) gagne une barre de navigation vers les pages principales (page courante signalée) et un pied de page ; les pages sont ajustées pour utiliser les éléments et classes de Sumi (conteneurs de tableaux défilants, largeur de lecture, encarts d'avertissement, hiérarchie des boutons).
- Les pages restent **sans JavaScript** : aucun script, aucun attribut `style`, aucun élément `style`. Pas de bascule clair/sombre (elle exigerait du JavaScript) : le thème suit le réglage du système.
- La règle « HTML sans CSS ni JavaScript » (spec `local-web-interface`, `AGENTS.md`, README) devient « sans JavaScript, avec feuilles de style locales ».

Hors périmètre : politique de sécurité de contenu (usage strictement local), toute modification du JavaScript (il n'y en a pas et il n'y en aura pas), de la logique métier, des routes d'action ou des textes de l'interface (le vocabulaire technique des pages est l'objet d'un autre travail éventuel), thème personnalisé ou charte graphique propre, bascule clair/sombre, captures d'écran, icône du site.

## Capabilities

### New Capabilities

Aucune.

### Modified Capabilities

- `local-web-interface` : la règle « Interface HTML sans CSS ni JavaScript » est renommée et assouplie (feuilles de style locales autorisées, JavaScript toujours interdit), et de nouvelles exigences encadrent la feuille servie, le squelette et la lisibilité des contenus longs.

## Impact

- Code : `transcription_bench/web/app.py` (routes des feuilles), `transcription_bench/web/templates/*.html`, nouveau dossier de ressources statiques figées (`sumi.min.css`, feuille complémentaire, licence).
- Tests : plusieurs tests vérifient aujourd'hui l'absence de `<link>` et de « stylesheet » (`tests/test_web.py`, `tests/test_audios.py`) et que `/static/base.css` n'existe pas ; ils doivent être précisés, pas supprimés.
- Documentation : `AGENTS.md` (ligne « HTML sans CSS ni JavaScript »), README, `docs/licences-modeles.md` (dépendance Sumi.css, MIT).
- Préalable à l'implémentation : l'exigence modifiée n'existe dans les specs de référence qu'après l'archivage de `add-benchmark-prototype`, que le propriétaire a choisi de ne pas faire pour l'instant ; le traitement de cette dépendance est à décider avant d'implémenter.
