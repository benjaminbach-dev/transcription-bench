---
title: Reprise du lot 5 — compatibilité en attente d’arbitrage
type: note
permalink: transcription-bench/projet/reprise-du-lot-5-compatibilite-en-attente-darbitrage
date: '2026-10-25'
provenance: transcription-bench, main, base publiée 34f147f ; clôture locale de 5.2
  après revue finale
status: 5.1 publiée ; 5.2 terminée et relue, publication préparée
tags:
- reprise
- lot-5
- compatibilite
---

# Reprise du lot 5 — tâche 5.1 terminée

Le titre historique du fichier conserve « en attente d’arbitrage », mais **l’arbitrage est clos**. Cette synthèse remplace les mentions précédentes d'attente.

## État et méthode
Provenance : dépôt `transcription-bench`, branche `main`, base publiée **34f147f**, 2026-10-25. **5.1 publiée ; 5.2 terminée et cochée : 13/39**. Revue et corrections puis feu vert advisor. Publication de 5.2 préparée ; vérifier Git pour son commit effectif. **5.3 non commencée**.

- [decision] Une tâche par worker, revue advisor, corrections worker, reprise advisor, puis commit/push des seuls fichiers concernés par le principal. Un advisor par lot. Les sessions expirées ou inaccessibles peuvent être reconstituées avec contexte, en signalant le repli sans redemander d'accord.
- [decision] Profil simplifié de 5.1 conservé : tokenizer JSON et sa configuration pour Transformers ; fichier de prétraitement requis pour tout CTranslate2 Whisper. Simplicité et limitation des variantes, pas de garantie générale de sécurité ; réexamen au jalon PC.
- [validation] **247 tests passent**, dont 70 ciblés GGUF et compatibilité, deux graines hors ligne. OpenSpec strict, verrou uv et contrôle des espaces Git réussis. Tests GGUF sur octets synthétiques, aucun vrai modèle.
- [constraint] Serveur de développement uniquement. Aucun moteur, poids, nouvelle dépendance ou inférence réelle. Familles réelles toujours non qualifiées, tâches 1.x, 3.2 et 8.x ouvertes.
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
- Advisor lot 5 **à reprendre** : `d46d5377-0ebf-450`, revue et validation de 5.2. Remplace `c3afe5e6-b0f8-44e`, devenu inaccessible ; reconstitution annoncée à l'utilisateur selon l'autorisation existante.
- Worker 5.2 : `5500b73d-2fa4-42d`. Workers 5.1 et scout documentaire restent historiques, pas besoin de refaire leurs investigations.
- Prochaine tâche **5.3**. Prévoir la conversion des erreurs du lecteur (réseau/OSError) en refus ; lecture réseau bornée sans télécharger implicitement des poids, avec une stratégie de tampon à vérifier (éviter à la fois les requêtes par champ de 4 octets et la prélecture excessive). Limiter les JSON sans rejeter les vrais tokenizer_config de Whisper déjà observés.
- Avant **5.4**, résoudre la collision `<org>__<nom>` et réconcilier le design. Les GGUF découpés en plusieurs fichiers ne doivent pas être traités comme des quantifications indépendantes : choisir un refus explicite ou une stratégie documentée avant de publier un inventaire prêt. Aucune prise en charge de GGUF découpé n'est acquise.
- Architecture réelle `general.architecture` de transcribe.cpp, familles et quantifications à confirmer sur PC. Récupération 6.5 et supervision 6.6 toujours dues ; voir [[Reprise du développement après le lot 4]].

## Production de 5.2 — lecture GGUF partielle

Provenance : `main`, base `34f147f`, 2026-10-25. Nouveau `transcription_bench/gguf.py`, fixtures synthétiques et tests ; intégration dans la règle de compatibilité existante.

- [validation] Lecteur GGUF v2/v3, petit et grand boutisme, sur `read(n)` fourni par l'appelant. Métadonnées scalaires, chaînes et tableaux imbriqués sautés si nécessaire. Arrêt dès `general.architecture`, sans validation des tenseurs, des poids ni du reste du fichier. Borne totale 64 Mio, lecture par blocs de 64 Kio, tableaux limités à 8 niveaux ; architecture au-delà de la borne refusée, sans prétendre cette borne universelle.
- [decision] Seul le fichier GGUF choisi est lu et sélectionné ; choix explicite si plusieurs candidats. Validation des noms et du choix avant appel du lecteur. Architecture jamais déduite du nom de fichier ; le nom de quantification ne prouve pas son encodage réel. Production encore refusée si la famille est non qualifiée ; succès sur déclarations synthétiques dans les tests.
- [validation] Correction de revue importante : la magie reste toujours les octets `GGUF`, même en grand boutisme. L'ordre des octets se détecte sur la version, comme dans le lecteur officiel `llama.cpp/gguf-py/gguf/gguf_reader.py`. L'ancien faux `FUGG` partagé par la fixture et le parseur est désormais refusé ; test indépendant avec octets officiels écrits à la main. Version 1 explicitement refusée.
- [source] Documentation officielle `ggml/docs/gguf.md`, lecteur officiel `llama.cpp/gguf-py/gguf/gguf_reader.py` et Context7 `/infinitensor/gguf` consultés. Bibliothèque tierce non installée. Rien de ceci ne qualifie un moteur ou un PC.
