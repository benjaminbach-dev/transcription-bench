---
title: rediger-documentation-utilisateur — rédaction faite sur le serveur, 2026-11-11
type: note
permalink: transcription-bench/projet/rediger-documentation-utilisateur-redaction-faite-sur-le-serveur-2026-11-11
tags:
- rediger-documentation-utilisateur
- etat
- reprise
---

# rediger-documentation-utilisateur — état au 2026-11-11

- [status] Cochées : 1.0 (habiller-interface-sumi archivé), 2.7 (aucun rappel d'accueil dans le guide). Laissées ouvertes à dessein : 1.1 (public visé à valider par le propriétaire — hypothèse seulement), 2.1, 2.2, 2.5 (rédaction faite et revue par advisor, mais ni parcours à froid ni messages système réellement relevés), 4.1–4.4 (PC de test Linux déclaré, relecture de style, Windows), 5.x.
- [decision] Les validations Linux/CI Windows de novembre 02-03 portaient sur une ancienne interface (commit 1424424, client HTTP automatisé, sans navigateur) : le guide le dit à chaque « Vérification », sans sur-déclarer. Aucun run CI postérieur à la refonte n'est consigné dans le dépôt.
- [implementation] Guide corrigé : trois parties §10/§11, glossaire étendu (CPU, RAM, Mo/Mio, empreinte, threads, JavaScript, lot, variante…), messages système non relevés paraphrasés sans guillemets, paragraphes raccourcis.
- [next] Propriétaire : valider le public (1.1) ; puis parcours à froid sur PC Linux déclaré (4.1/4.2) pour cocher 2.1/2.2/2.5 avec preuves.

## Relations
- relates_to [[Socle des commandes CLI et modes exclusifs]]
