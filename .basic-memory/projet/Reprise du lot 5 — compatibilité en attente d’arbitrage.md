---
title: Reprise du lot 5 — compatibilité en attente d’arbitrage
type: note
permalink: transcription-bench/projet/reprise-du-lot-5-compatibilite-en-attente-darbitrage
date: '2026-10-25'
provenance: transcription-bench, main, base publiée 26653c2 ; clôture locale 5.4,
  2026-10-26 UTC
status: 'historique : lot 5 complet ; nouveau point de reprise projet/reprise-apres-le-lot-5'
tags:
- reprise
- lot-5
- compatibilite
---

# Reprise du lot 5 — tâche 5.1 terminée

Le titre historique du fichier conserve « en attente d’arbitrage », mais **l’arbitrage est clos**. Cette synthèse remplace les mentions précédentes d'attente.

## État et méthode
**Lot 5 terminé : 16/39 tâches, 329 tests passants.** Provenance : `main`, base publiée `e425370`, clôture 5.5 relue le 2026-10-26 UTC, publication préparée. Cette note conserve l'historique des choix et limites ; son titre et les anciens états d'attente ne sont plus l'état courant. **Lire désormais [[Reprise après le lot 5]]** pour la méthode, l'état, les contrats à préserver et la suite. Lot 6 non commencé.
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
Lot 5 clos après feu vert de **aaf3b07a-0158-496** (session b3219082 expirée, reconstitution annoncée). Worker 5.5 **ed03c123-1bab-4c4**. Nouvelle synthèse [[Reprise après le lot 5]] ; nouveau contexte advisor lors du futur lot 6. Les instructions anciennes d'enchaîner 5.4/5.5 sont accomplies ; ne pas relancer ces tâches.
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

## Enchaînement en cours — après publication 5.3

Provenance : `main`, commit publié **26653c2**, 2026-10-25 UTC, dépôt propre au démarrage de la suite. User a demandé explicitement d'enchaîner 5.3/5.4/5.5, ordre worker → principal → advisor ; ne pas s'arrêter volontairement après 5.4 si aucun blocage.

- [status] Worker **30a089eb-11b7-44b** implémente **5.4** ; pas encore contrôlé ni revu. Advisor lot 5 à reprendre **975a80f1-3737-403**. 5.5 non commencée. Dernier état publié 14/39, 275 tests.
- [decision] Correction interne de la collision de stockage annoncée avant démarrage : dossier `data/models/<moteur>/<SHA256>/` calculé sur JSON déterministe `[id_resolu, commit, variante_gguf_ou_null]` ; `model.json` séparé d'un sous-dossier `fichiers/` pour les téléchargements. Noms lisibles gardés dans l'inventaire. Preuve principale locale : `a__b/c` et `a/b__c` distincts, noms courts et `CON` acceptés comme identifiants sans créer un dossier réservé ; variantes distinctes. D10 doit être aligné avant la persistance. Aucun modèle préexistant à migrer.
- [decision] Les GGUF repérés comme fragments par leur nom sont refusés avant téléchargement/état prêt ; pas de prise en charge multi-fichiers spéculative ni de validation des tenseurs. Toujours une seule variante complète.
- [constraint] `snapshot_download` attend des glob patterns : échapper les noms littéraux avec `glob.escape` pour ne pas télécharger des fichiers supplémentaires. Preuve locale `model[abc].safetensors` ne sélectionne pas `modela.safetensors` après échappement.
- [next] Après rapport worker : principal lit code/tests et vérifie parcours ciblé, puis advisor ; corrections éventuelles ; cocher uniquement après validation ; mémoire, identité/remote, commit/push explicites par tâche. Ensuite 5.5 : suppression du modèle actif interdite (créneau global) et mode hors ligne imposé au lancement. Aucun moteur, poids ou inférence réelle, tests simulés seulement.

## Production de 5.4 — téléchargement et inventaire, 2026-10-26 UTC

Provenance : base `26653c2`, clôture relue et publication préparée.

- [decision] D10 aligné : clé SHA-256 JSON `[id_resolu, commit, variante]`, `data/models/<moteur>/<clé>/model.json` séparé de `fichiers/`. Pas de collision de l'ancien assemblage `org__nom`, pas d'identifiant valide interdit pour contourner le stockage. Empreinte du dernier résultat accepté uniquement côté serveur, moteur prêt vérifié, commit et liste autorisée non fournis par le formulaire.
- [validation] snapshot_download à commit figé, fichiers échappés avec glob.escape, max_workers=1, client créé dans le thread admis. Contrôle présence et tailles avant marqueur atomique sous le verrou d'arrêt. Après redémarrage, fichier absent/tronqué, marqueur incohérent ou alias ne donne jamais prêt. Répertoire moteur/clé non aliasé, marqueur confiné avant lecture, cache confiné au modèle ; suppression/marqueur protégés par le verrou JSON commun, ordre créneau puis stockage.
- [validation] Page modèles réelle, POST protégés et PRG 303, données échappées, GET sans réseau. Le formulaire de choix d'une variante GGUF conserve maintenant le commit exact. Suppression conserve les résultats et les autres modèles. Fragments GGUF reconnus par nom refusés avant téléchargement, sans prétendre valider intrinsèquement les poids.
- [constraint] Dossiers partiels/non prêts invisibles dans l'UI : reprise explicite ou nettoyage manuel. Une troncature détectée par l'application n'est pas forcément réparée par le cache HF si elle est faite à moins d'une seconde du téléchargement, ou si sa date est restaurée : le modèle reste non prêt ; cache/nettoyage manuel peut être nécessaire. Métadonnées de shards Xet (pas de poids) possibles hors data dans ~/.cache/huggingface/xet. Une erreur OS de suppression donne encore 500 générique. Réseau réel, réparations et chemins longs Windows à confirmer sur PC.
