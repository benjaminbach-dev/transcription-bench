---
title: Reprise du lot 5 — compatibilité en attente d’arbitrage
type: note
permalink: transcription-bench/projet/reprise-du-lot-5-compatibilite-en-attente-darbitrage
date: '2026-10-25'
provenance: transcription-bench, main, base publiée 90a7c34 ; clôture locale de 5.1
  après revue finale
status: arbitrage clos ; 5.1 terminée et relue, publication préparée
tags:
- reprise
- lot-5
- compatibilite
---

# Reprise du lot 5 — tâche 5.1 terminée

Le titre historique du fichier conserve « en attente d’arbitrage », mais **l’arbitrage est clos**. Cette synthèse remplace les mentions précédentes d'attente.

## État et méthode

Provenance : dépôt `transcription-bench`, branche `main`, base publiée **90a7c34**, 2026-10-25. **5.1 terminée et cochée : 12/39**. Revue finale favorable après réconciliation des specs et choix utilisateur. Publication préparée avec les seuls fichiers de la tâche et les notes de continuité ; vérifier Git pour son commit effectif. **5.2 non commencée**.

- [decision] Même méthode : une tâche par worker, revue advisor, corrections worker, reprise advisor, puis commit/push des seuls fichiers concernés par le principal. Un advisor par lot. Les sessions expirées peuvent être reconstituées avec contexte, en signalant le repli sans redemander d'accord.
- [decision] Profil simplifié retenu : Transformers exige `tokenizer.json` et `tokenizer_config.json`, même si vocabulaire et fusions seuls seraient lisibles par la bibliothèque. faster-whisper exige `preprocessor_config.json` pour tout modèle CTranslate2 Whisper, sans valeurs par défaut, même si cela exclut certains petits modèles comme `Systran/faster-whisper-small`. Motif : simplicité, moins de variantes à couvrir ; ne pas présenter toutes ces restrictions comme des garanties de sécurité. À réexaminer lors des essais PC.
- [validation] **221 tests passent**, dont 44 de compatibilité, avec deux graines et hors ligne. Validation OpenSpec stricte, verrou uv et contrôle des espaces Git réussis. Les fichiers spéciaux requis sont testés isolément ; pas de doublon du test tokenizer déjà couvert.
- [constraint] Serveur de développement uniquement. Aucun moteur, poids, dépendance nouvelle ou inférence réelle. Familles fournies **toujours `qualifiee=False`**. Aucune durée native ni réglage réel ajouté. Tâches 1.x, 3.2 et 8.x restent ouvertes.

## Production de 5.1 et limites

Deux nouveaux fichiers : `transcription_bench/compatibilite_modeles.py` et `tests/test_compatibilite_modeles.py`. Spec `model-management`, design D10 et tâche 5.1 alignés sur le profil accepté. Le proposal et les autres specs restent cohérents sans modification.

- API pure de compatibilité depuis déclaration, liste de fichiers et petits JSON déjà lus, sans E/S ni paquet moteur. Résultat structuré : famille, fichiers, raisons stables et éventuelle suggestion de moteur. Une famille reconnue mais non qualifiée reste refusée ; seuls des profils synthétiques qualifiés dans les tests exercent les succès.
- CT2 : `model.bin` accepté sans exiger un `model_type` HF absent du format. Transformers : correspondance `parakeet_tdt` → famille `parakeet-tdt`, listes blanches par famille, refus de `auto_map` dans les configurations inspectées. Whisper exige la configuration de génération pour le français et les horodatages ; Parakeet la conserve si présente.
- Safetensors uniquement pour Transformers, index et shards contrôlés. Si index complet et fichier unique coexistent, une seule variante est sélectionnée. NeMo, GGUF et pickle sont ignorés pour ce moteur.
- Corrections de revue : suppression d'un plafond de 2 000 nœuds qui refusait le tokenizer Whisper réel (282 843 octets, environ 1 600 jetons ajoutés), test synthétique de 1 700 entrées ; capture des erreurs JSON excessivement imbriquées ; séparation des fichiers par famille ; sélection sans doublon des poids.
- En **5.3**, borner les octets lus à distance sans refuser ces vraies configurations de tokenizer. Le code 5.1 ne télécharge pas et ne vérifie pas de dépôt distant. Les suffisances de fichiers et comportements de chargement restent à valider sur PC.

## Constats documentaires à conserver

Sources : Context7 faster-whisper et Transformers v5.19.0 ; pour v5.20.2 non indexée, tag GitHub officiel `18329f1065382e54db698e242cf98bd3f3e5a766`. Sources faster-whisper v1.2.1 `utils.py` et `transcribe.py`. Métadonnées publiques seulement, aucun poids consulté.

- Le dépôt public `Systran/faster-whisper-large-v3-turbo` cité au jalon est indisponible (401 : privé ou inexistant, distinction inconnue). L'alias `turbo` de faster-whisper v1.2.1 pointe vers `mobiuslabsgmbh/faster-whisper-large-v3-turbo`. **Ne pas remplacer silencieusement les exemples de modèles d'essai** : à confirmer avec l'utilisateur avant l'accord PC.
- Whisper public `openai/whisper-large-v3-turbo` (révision abrégée observée 41f01f3) a un préprocesseur séparé, pas de processor_config, avec tokenizer et auxiliaires dont `normalizer.json`.
- Parakeet public `nvidia/parakeet-tdt-0.6b-v3` (révision abrégée observée 541d1f9) a un processor avec extracteur imbriqué, pas de préprocesseur séparé, tokenizer JSON/config, poids safetensors, mais aussi NeMo et GGUF à ignorer pour Transformers.
- Aucun de ces constats documentaires ne prouve le chargement réel hors ligne sur un PC.

## Continuité des agents et suite

- Advisor lot 5 **à reprendre** : `c3afe5e6-b0f8-44e`, revue finale favorable. Il remplace `57c274d1-1f9e-44d`, expiré après ses revues B1–B4 et feu vert technique.
- Worker documentaire et test isolé : `5bfddc13-6023-479`. Worker initial 5.1 `95174c2c-fb65-484` expiré, code déjà relu ; aucune raison de refaire l'implémentation.
- Scout documentaire terminé `946d75d6-205b-4a5` ; investigation disponible sans la refaire.
- Prochaine tâche **5.2**. Avant **5.4**, résoudre la collision de stockage `<org>__<nom>` et réconcilier le design ; aucun stockage des modèles encore écrit. Les autres limites de récupération 6.5 et supervision 6.6 restent décrites dans [[Reprise du développement après le lot 4]].
