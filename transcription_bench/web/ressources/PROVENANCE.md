# Provenance des feuilles de style servies par l'application

Ce dossier contient les feuilles de style figées du paquet, servies par les routes
`/sumi.css` et `/app.css` (`transcription_bench/web/app.py`). Aucune feuille n'est
chargée depuis un réseau à l'ouverture d'une page.

## `sumi.min.css` (route `/sumi.css`)

- Amont : [Sumi.css](https://github.com/vladocar/Sumi.css), dépôt public
  `vladocar/Sumi.css`, de Vladimir Carrer, licence MIT (voir `LICENSE-Sumi.css`).
- Version amont : `v1.0.0` (en-tête du fichier ; commit amont du 2026-11-02).
- Commit amont copié : `cee85b75efb2f129b82bc014439381b57ede7c22`.
- Fichier d'origine : `sumi.min.css` à la racine du dépôt amont.
- Récupération : 2026-11-03, par
  `https://raw.githubusercontent.com/vladocar/Sumi.css/cee85b75efb2f129b82bc014439381b57ede7c22/sumi.min.css`,
  copie octet pour octet, sans modification (l'en-tête `/*! … MIT License */` est
  conservé).
- Taille de la copie : 28 245 octets.
- SHA-256 de la copie :
  `3535cf90e19150a2805dd57ad442d8f6e4a04ed4f50aa53b34b8306d10297116`.
  Ce condensat est vérifié par `tests/test_feuilles.py` ; le fichier est déclaré
  `-text` dans `.gitattributes` pour qu'aucune conversion de fin de ligne ne le
  modifie (même condensat sous Linux et sous Windows).
- Mise à jour : opération explicite (nouveau commit amont, nouveau condensat),
  jamais automatique.

## `app.css` (route `/app.css`)

Feuille complémentaire du projet, chargée après `sumi.min.css`, limitée à quatre
rôles : retours à la ligne et coupures, surcharge des jetons de couleur de Sumi
avec la palette Flexoki, couleur des boutons d'action destructrice, et composant
compact de résultat (jetons `--s-resultat-*` de taille, de couleur et de grille,
règles `resultat-*` de la macro `composants.html`). Elle ne contient aucune police
ni ressource externe.

- Palette : [Flexoki](https://github.com/kepano/flexoki), © Steph Ango, licence
  MIT ; le texte intégral est joint dans `LICENSE-Flexoki`. L'avis de licence
  figure aussi en tête de `app.css` et dans `docs/licences-modeles.md`.
- Valeurs reprises de la palette officielle (échelle encre et papier, accents
  50 à 950) ; aucune couleur hors palette n'est introduite.

## Licence Flexoki (`LICENSE-Flexoki`)

- Amont : [Flexoki](https://github.com/kepano/flexoki), de Steph Ango.
- Fichier d'origine : `LICENSE` à la racine du dépôt amont.
- Récupération : 2026-11-03, par
  `https://raw.githubusercontent.com/kepano/flexoki/main/LICENSE`.
- Licence MIT, © 2023 Steph Ango, texte reproduit sans modification.

## Licences

- Sumi.css : MIT, texte intégral dans `LICENSE-Sumi.css` (copie du fichier
  `LICENSE` du dépôt amont au même commit).
- Flexoki : MIT, © Steph Ango ; texte intégral dans `LICENSE-Flexoki`, et
  attribution dans `docs/licences-modeles.md`.
