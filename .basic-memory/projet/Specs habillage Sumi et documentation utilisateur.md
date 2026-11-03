---
title: Specs habillage Sumi et documentation utilisateur
type: note
permalink: transcription-bench/projet/specs-habillage-sumi-et-documentation-utilisateur
tags:
- openspec
- sumi
- documentation
- interface
---

# Specs habillage Sumi et documentation utilisateur

- [decision] 2026-11-03 : le propriétaire demande deux changes OpenSpec distincts après la clôture du prototype : `habiller-interface-sumi` (habillage avec Sumi.css, la règle « HTML sans CSS » est assouplie, JavaScript toujours interdit) et `rediger-documentation-utilisateur` (guide pour non-techniciens, README court). Artefacts dans openspec/changes/ ; non implémentés ni commités à cette date.
- [fact] Sumi.css : MIT, fichier unique, sumi.min.css 28 245 octets (commit amont cee85b75, SHA-256 3535cf90…7116), sans url() ni @import ; utilise :where(), :has(), color-mix() (Chrome/Edge 111, Firefox 121, Safari 16.2).
- [validation] Essai jetable le 2026-11-03 (pages réelles + Sumi sans retouche, navigateur 1280 px/420 px, thème sombre) : formulaires, titres et thème sombre corrects ; défauts : lignes trop longues, tableaux et transcriptions <pre> qui débordent à 420 px, valeurs sans espace (SHA-256) qui débordent. Les <pre> et valeurs longues exigent une petite feuille complémentaire (le HTML seul ne suffit pas).
- [decision] Le CSS est servi localement (/sumi.css, /app.css), jamais depuis un CDN . Politique CSP écartée par le propriétaire (usage strictement local).
- [limit] La spec d'habillage modifie une exigence qui n'existe dans openspec/specs qu'après archivage de add-benchmark-prototype : archiver d'abord.
- [limit] Le vocabulaire technique des pages (empreinte SHA-256, threads, créneau) reste hors périmètre des deux changes.

## Relations

- relates_to [[Qualification Qwen3-ASR 2026-11-03]]

## Révision et mise en œuvre (2026-11-03, suite)

- [decision] Archivage de `add-benchmark-prototype` fait le 2026-11-03 (6 specs de référence créées) : le préalable de la modification de l'exigence « sans CSS » est levé. Reste à corriger à la main le `## Purpose` de `openspec/specs/local-web-interface/spec.md` à l'archivage de l'habillage.
- [decision] Revue advisor puis arbitrages du propriétaire : palette **Flexoki** (MIT, Steph Ango) par surcharge des jetons de couleur de Sumi dans `app.css` ; bouton destructeur en couleur (`button.danger`, via `--s-btn`) ; libellés d'interface en **gras** dans le guide ; exemple principal `handy-computer/whisper-large-v3-turbo-gguf` (Q5_K_M, ≈ 620 Mo) à la place de Qwen3-ASR (Linux seulement). Specs poussées (commit 5c03627), `--strict` vert pour les deux changes.
- [fact] Contraste WCAG mesuré : Flexoki 600/400 ne suffit pas pour le succès clair (vert 600 : 4,39) ni le danger sombre (rouge 400 : 4,42) ; retenus vert 700 `#536907` et rouge 300 `#E8705F` (valeurs officielles du dépôt kepano/flexoki).
- [validation] Habillage implémenté par un worker en deux lots (ressources/routes/app.css/tests des feuilles ; gabarits/navigation/tests partagés) : suite complète de 756 tests verte sous Linux (serveur de développement). Vérification visuelle et CI Windows non encore faites à cette ligne.
- [limit] Guide utilisateur rédigé (docs/guide-utilisateur.md), README court (< 60 lignes), docs/technique.md et test de cohérence tests/test_documentation.py ; le parcours à froid exige un PC de test déclaré par le propriétaire (installation de moteur, téléchargement, inférence réelle) : non fait.

## Vérification visuelle de l'habillage (2026-11-03, sur serveur de développement, moteur factice)

- [validation] Quatre lots du worker + deux passes du navigator (thème clair réel, 360 et 1280 px) : aucune page ne défile horizontalement à 360 px, aucune requête hors application, console propre hors favicon et 404 volontaire ; suite complète de 764 tests verte sous Linux.
- [fact] Corrections issues du navigateur : nom du programme en `strong` (le `h1` de Sumi fait 45 px) avec un `h1` par page ; coupures `overflow-wrap` étendues (titres, `p`, `li`, `strong`, `dt`) ; `prose` homogène ; boutons de vérification en `secondary` ; liens sombres en bleu 300 `#66A0C8` (le bleu 400 donnait 4,37) ; bordures fortes en base-500 (3:1).
- [limit] Thème sombre vérifié seulement par injection des feuilles (aucune émulation de média dans le Playwright de l'hôte) ; bouton « Arrêter l'exécution » vu en aperçu injecté ; vue de comparaison à 360 px étroite (≈ 9 caractères par ligne dans les transcriptions) ; CI Windows (SHA-256 avec `-text`, type MIME) non encore exécutée.
- [limit] Restent : mise à jour d'AGENTS.md relue par le propriétaire (modifiée localement, non commitée), correction du `## Purpose` à l'archivage, parcours à froid de la documentation sur un PC de test déclaré.

## Revue advisor de l'implémentation et corrections (2026-11-03, soir)

- [validation] Revue advisor (lecture seule) : code conforme aux specs ; points corrigés : `td pre` en `break-word` puis `min-width: 14rem` (transcriptions à ≈ 20 caractères par ligne à 360 px au lieu de ≈ 10, mesuré au navigateur), licence Flexoki jointe, tests de contraste/feuilles durcis (rapport brut, commentaires ignorés, blocs imbriqués), test d'encart clinique et de classes plus stricts, guide corrigé (accès réseau, définitions à la première apparition, mention Microsoft Store retirée, nuance sur la vérification des modèles). 772 tests verts sous Linux.
- [limit] Paires de contraste non garanties ≥ 4,5 mais inutilisées aujourd'hui : `--s-muted` sur surface/card/card-section et encarts, `--s-primary` sur card-section en sombre.
- [limit] Le run CI Windows du 2026-11-03 sur le commit 5c03627 (specs seulement) a échoué sur `test_arret_utilisateur_interrompu_conserve_les_resultats` (FileNotFoundError, course probable), sans rapport avec l'habillage ; l'habillage n'a pas encore été vu par la CI Windows (SHA-256 de `sumi.min.css`, type MIME).

## État au 2026-11-03 (fin de séance)

- [validation] Commits poussés sur main : ed07bd4 (habillage Sumi.css + Flexoki) et 1d50ca3 (guide, README court, docs/technique.md) ; CI « Tests Linux et Windows » verte sur 1d50ca3 (run 41732163736), y compris Windows (SHA-256 de `sumi.min.css`, type MIME, nouveaux tests). Le test existant `test_arret_utilisateur_interrompu_conserve_les_resultats` avait échoué une fois sous Windows sur 5c03627 : instable probable, non diagnostiqué.
- [limit] Restent pour archiver `habiller-interface-sumi` : relecture d'AGENTS.md par le propriétaire puis /reload (1.2), thème sombre réel non observé (6.5), correction du `## Purpose` de `local-web-interface` (7.2). Pour `rediger-documentation-utilisateur` : parcours à froid sur un PC de test déclaré (moteur transcribe.cpp, modèle whisper-large-v3-turbo-gguf Q5_K_M ≈ 620 Mo, audio synthétique), relecture propriétaire, tâches 2.1/2.2/2.5, 4.x, 5.x.
