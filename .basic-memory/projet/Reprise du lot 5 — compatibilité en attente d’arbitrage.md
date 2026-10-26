---
title: Reprise du lot 5 — compatibilité en attente d’arbitrage
type: note
permalink: transcription-bench/projet/reprise-du-lot-5-compatibilite-en-attente-darbitrage
date: '2026-10-25'
provenance: transcription-bench, main, base publiée 12795fe ; clôture locale de 5.3,
  2026-10-25 UTC
status: 5.1 et 5.2 publiées ; 5.3 terminée et relue, publication préparée
tags:
- reprise
- lot-5
- compatibilite
---

# Reprise du lot 5 — tâche 5.1 terminée

Le titre historique du fichier conserve « en attente d’arbitrage », mais **l’arbitrage est clos**. Cette synthèse remplace les mentions précédentes d'attente.

## État et méthode
Provenance : `transcription-bench`, `main`, base publiée **12795fe**, 2026-10-25 UTC. **5.3 terminée et cochée : 14/39** après worker, contrôle principal, corrections puis validation advisor. Publication préparée ; vérifier Git pour son commit effectif. **5.4 et 5.5 à enchaîner, demande utilisateur explicite**, sans redemander l'accord général.

- [decision] Une tâche à la fois : worker → contrôle principal → advisor → corrections worker → même advisor → commit/push des seuls fichiers concernés. Même contexte advisor par lot ; reconstitution autorisée s'il expire, en le signalant.
- [decision] Profils simplifiés de 5.1 inchangés : tokenizer JSON/config pour Transformers ; prétraitement exigé pour tous les CTranslate2 Whisper. Réexamen PC sans promesse générale de sécurité.
- [validation] **275 tests passent**, deux graines hors ligne et proxy injoignable chez advisor. OpenSpec strict, verrou uv et contrôle Git réussis. Les tests du client réel utilisent MockTransport, aucun HTTP réel de modèle ni poids. Le principal a seulement consulté les métadonnées publiques de l'alias `gpt2` pour vérifier sa résolution.
- [constraint] Serveur de développement, pas PC. Aucun moteur, poids, nouvelle dépendance ou inférence réelle ; familles réelles toujours non qualifiées ; 1.x, 3.2 et 8.x restent ouvertes.
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
- Advisor lot 5 à reprendre : `975a80f1-3737-403`, revue finale de 5.3. Worker 5.3 `f57113d1-d90a-438`. Les précédents advisors devenus inaccessibles ont été reconstitués selon l'accord utilisateur.
- Prochaine tâche **5.4**, puis **5.5**, déjà autorisées. Corriger le stockage ambigu dans D10 avant de l'implémenter, sans interdire d'identifiants HF valides ; garder les résultats après suppression du modèle. Ne pas accepter un GGUF découpé comme fichier autonome.
- La lecture réelle Range côté CDN/Xet et les capacités réelles restent à confirmer sur PC. Le listage interne sans délai exposé et l'absence de délai global garanti restent à traiter/documenter en 6.6. Récupération 6.5 et supervision 6.6 toujours dues ; voir [[Reprise du développement après le lot 4]].
## Production de 5.2 — lecture GGUF partielle

Provenance : `main`, base `34f147f`, 2026-10-25. Nouveau `transcription_bench/gguf.py`, fixtures synthétiques et tests ; intégration dans la règle de compatibilité existante.

- [validation] Lecteur GGUF v2/v3, petit et grand boutisme, sur `read(n)` fourni par l'appelant. Métadonnées scalaires, chaînes et tableaux imbriqués sautés si nécessaire. Arrêt dès `general.architecture`, sans validation des tenseurs, des poids ni du reste du fichier. Borne totale 64 Mio, lecture par blocs de 64 Kio, tableaux limités à 8 niveaux ; architecture au-delà de la borne refusée, sans prétendre cette borne universelle.
- [decision] Seul le fichier GGUF choisi est lu et sélectionné ; choix explicite si plusieurs candidats. Validation des noms et du choix avant appel du lecteur. Architecture jamais déduite du nom de fichier ; le nom de quantification ne prouve pas son encodage réel. Production encore refusée si la famille est non qualifiée ; succès sur déclarations synthétiques dans les tests.
- [validation] Correction de revue importante : la magie reste toujours les octets `GGUF`, même en grand boutisme. L'ordre des octets se détecte sur la version, comme dans le lecteur officiel `llama.cpp/gguf-py/gguf/gguf_reader.py`. L'ancien faux `FUGG` partagé par la fixture et le parseur est désormais refusé ; test indépendant avec octets officiels écrits à la main. Version 1 explicitement refusée.
- [source] Documentation officielle `ggml/docs/gguf.md`, lecteur officiel `llama.cpp/gguf-py/gguf/gguf_reader.py` et Context7 `/infinitensor/gguf` consultés. Bibliothèque tierce non installée. Rien de ceci ne qualifie un moteur ou un PC.

## Production de 5.3 — vérification distante, 2026-10-25 UTC

Provenance : base `12795fe`, tâche relue et clôturée localement.

- [validation] `VerificationModeles.lancer` admet une vérification dans le créneau partagé avant tout appel réseau. Client créé dans le thread, pas à la construction ; résultat immuable en mémoire publié sous le verrou d'arrêt, aucune publication après arrêt. Page et téléchargement restent à brancher en 5.4.
- [decision] HfApi `model_info(files_metadata=True, timeout=30.0)` : commit exact, tailles des seuls fichiers retenus, total inconnu si une taille manque. Identifiant canonique validé conservé en `id_resolu`, identifiant demandé conservé pour affichage. Exemple public vérifié : `gpt2` → `openai-community/gpt2`, SHA `607a30d783dfa663caf39e06633721c8d4cfcd7e` ; aucune qualification ASR déduite de cet exemple.
- [validation] Noms distants contrôlés avant ouverture. JSON lus uniquement selon le moteur : CTranslate2 config/prétraitement, Transformers configurations et index, transcribe.cpp aucun JSON et uniquement l'en-tête choisi. JSON bornés 2 Mio, index 8 Mio, sans refuser le vrai tokenizer_config Whisper observé. Erreurs fixes et sans texte d'exception, jeton standard jamais affiché ni journalisé.
- [decision] `HfFileSystem.open(block_size=64 Kio, cache_type='none')` produit le lecteur à requêtes Range exactes. **Ne pas utiliser block_size=0** : le lecteur streaming peut lire du poids en avance. Tests du vrai client avec transport simulé : chaque GET fichier est une Range bornée, sentinelle de poids jamais demandée ni servie. La bibliothèque doit respecter les Range côté CDN/Xet : cette hypothèse réelle reste à confirmer sur PC, pas par une lecture de poids ici.
- [constraint] L'appel initial a un délai de 30 s ; le listage interne de HfFileSystem ne fournit pas partout de délai exposé. Aucun délai global d'arrêt garanti, à consigner en 6.6. Lire les erreurs réseau/lecture sans jamais recopier URL ou secret.
- [next] 5.4 doit exiger le dernier résultat accepté avec identité canonique/commit/variante exacts, vérifier l'installation du moteur avant admission et créer le marqueur seulement après succès complet. Clé dérivée de l'identité canonique+commit+variante plutôt que `<org>__<nom>` ; résolution à documenter dans D10 avant écriture du stockage. Les GGUF découpés ne doivent pas devenir prêts comme variante isolée.
- [continuity] Advisor lot 5 courant : `975a80f1-3737-403` (remplace `d46d5377-0ebf-450` expiré, reconstitution annoncée) ; worker 5.3 `f57113d1-d90a-438`.
