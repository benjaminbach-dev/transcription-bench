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
