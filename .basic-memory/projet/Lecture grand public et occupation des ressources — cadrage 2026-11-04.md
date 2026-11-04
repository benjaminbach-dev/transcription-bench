---
title: Lecture grand public et occupation des ressources — cadrage 2026-11-04
type: note
permalink: transcription-bench/projet/lecture-grand-public-et-occupation-des-ressources-cadrage-2026-11-04
tags:
- decision
- interface
- ressources
- openspec
---

# Lecture grand public et occupation des ressources — cadrage 2026-11-04

Contexte : après la refonte Sumi (base 931e2a5), demande d'une lecture plus rapide des résultats et de spécifications revues avant et après rédaction par advisor. Les exigences détaillées restent dans les deux changes OpenSpec, pas dans cette note.

## Observations

- [decision] Priorité demandée : textes de transcription, durée, pic de RAM modèle chargé inclus et occupation CPU moyenne rapportée à l'ordinateur, immédiatement visibles ; détails moteurs/réglages au second niveau. Pas de graphiques ni de jugement automatique de qualité.
- [decision] Le temps CPU cumulé n'est pas un indicateur principal compréhensible pour cet usage. Le cadrage remplace l'ancien choix « pas de pourcentages » du 2026-10-23 par des pourcentages de ressources explicitement nommés et contextualisés.
- [decision] Deux changes distincts : `simplifier-lecture-resultats` dérive les ratios depuis les valeurs consignées existantes sans réécriture ; `mesurer-charge-systeme` ajoute CPU global moyen pendant chaque audio et RAM disponible après chargement/après audio.
- [rationale] Une mémoire disponible instantanée n'est pas le minimum pendant l'audio. Le contexte système inclut les autres programmes et ne doit pas servir à classer les modèles ou à attribuer une consommation à l'application entière. Le pic RSS moteur reste cumulatif, modèle et buffers inclus.
- [rationale] Deux relevés CPU dans le runner ont été préférés à un observateur périodique serveur : bornes d'inférence connues, pas de thread supplémentaire ni attribution approximative entre audios. Les deux appels non bloquants de psutil 7.2.2 partagent un état par thread ; le premier est ignoré.
- [validation] Lecture du code, documentation psutil 7.2.2 et sonde d'API Linux avec processus Python synthétique dormant réussies ; aucune inférence réelle ni validation Windows. Deux changes complets validés OpenSpec strict ; revue advisor après rédaction, corrections et contrôle final favorables.
- [status] Spécifications seulement, aucune implémentation. Ni archivage de Sumi ni levée de ses vérifications restantes ; aucun nouveau job moteur, installation ou téléchargement autorisé par ces documents.

## Relations

- relates_to [[Décisions du prototype de benchmark]]
- extends [[Specs habillage Sumi et documentation utilisateur]]
