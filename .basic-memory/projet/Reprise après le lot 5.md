---
title: Reprise après le lot 5
type: note
permalink: transcription-bench/projet/reprise-apres-le-lot-5
date: '2026-10-26'
provenance: transcription-bench, main, base publiée e425370 ; clôture locale de 5.5
  après revue finale
status: lot 5 complet, 16/39 ; publication de clôture préparée
tags:
- reprise
- etat
- lot-5
---

# Reprise après le lot 5

## État actuel et sources

Provenance : dépôt `transcription-bench`, branche `main`, 2026-10-26 UTC, base publiée **e425370**. **Lot 5 complet : 5/5, progression 16/39**. Dernière tâche 5.5 terminée et revue favorablement, publication préparée ; vérifier Git pour le commit de clôture effectif. Cette note est le nouveau point de reprise ; [[Reprise du lot 5 — compatibilité en attente d’arbitrage]] conserve l'historique technique.

- Publications des trois dernières tâches : **5.3 `26653c2`**, **5.4 `e425370`**, puis clôture 5.5 avec cette note. 5.1 `34f147f`, 5.2 `12795fe`.
- **329 tests passent**, deux graines hors ligne, proxy injoignable pour les revues. OpenSpec strict, verrou uv et contrôle Git réussis. Navigator 5.4 : vérification → téléchargement → déjà présent → suppression → accueil/opération réussis avec données simulées. Résultat sentinelle conservé, serveur temporaire arrêté, traces nettoyées.
- Aucun moteur réel, poids, nouvelle dépendance ou inférence réelle. Familles réelles toujours non qualifiées. **Lot 6 non commencé.**

À reprendre : lire `AGENTS.md`, la mémoire par le MCP (projet `transcription-bench`, clone `.basic-memory/` à confirmer), `openspec list` puis les artefacts du change `add-benchmark-prototype` concernés. Les exigences restent dans OpenSpec, pas dans ces notes.

## Méthode conservée

Une tâche par worker → contrôle du principal → revue advisor → corrections worker → reprise du même advisor → commit/push des seuls fichiers concernés après validation. Publication autorisée par l'utilisateur, mais toujours vérifier identité, branche et remote ; préserver les autres modifications.

Même session advisor pendant un lot, nouvelle au changement de lot. Si elle expire, reconstituer le contexte en le signalant, sans redemander. Seul le principal écrit en mémoire et publie. Navigator seul utilise Playwright ; principal arrête les serveurs et nettoie les traces après exploitation.

Advisor final lot 5 : **aaf3b07a-0158-496**, feu vert 5.5 ; remplace `b3219082-86fa-461` expiré après validation 5.4. Worker 5.5 : **ed03c123-1bab-4c4**. Pour le futur lot 6, ouvrir un nouveau contexte advisor ; ne reprendre le précédent que pour une correction connexe au lot 5.

## Contrats importants acquis

- Déclarations et registre stdlib ; aucune bibliothèque moteur importée dans le serveur. Runner direct `python engines/runner.py job.json`, bootstrap depuis `__file__` uniquement, audios séquentiels et fenêtres 30 s. Factice sans modèle/réseau, textes et mesures marqués simulés dans chaque événement. Ce n'est pas une qualification PC.
- Profils simplifiés acceptés : Transformers exige tokenizer JSON/config ; CTranslate2 Whisper exige le prétraitement explicite pour tous les modèles. Certains dépôts pourtant utilisables par les bibliothèques sont volontairement refusés ; réexamen au jalon PC.
- Vérification distante admise avant réseau, résultat immuable en mémoire, commit exact et identifiant canonique validé, tailles inconnues conservées comme inconnues. model_info a 30 s de délai. HfFileSystem à Range exacte (`block_size=64 Kio`, cache `none`), pas le mode streaming `block_size=0` qui peut précharger des poids. Configurations lues seulement pour le moteur concerné. Jetons standards jamais demandés ni affichés.
- Modèles sous `data/models/<moteur>/<SHA256>/` : clé du JSON `[id_resolu, commit, variante]`, inventaire `model.json` séparé de `fichiers/`. Dernier résultat accepté côté serveur seulement, fichiers autorisés échappés avec glob.escape, téléchargement à commit figé. Pas de marqueur prêt avant contrôle complet ni après passage à l'arrêt. Lecture du marqueur, chemins, alias, cache et présence/tailles revérifiés ; les fragments GGUF repérés par nom sont refusés.
- JSON sous verrou commun ; suppression et retrait du marqueur le prennent aussi. Ordre de verrous : créneau → stockage, jamais l'inverse. Les résultats ne dépendent pas de la présence ultérieure du modèle.

## Acquis 5.5 à préserver en 6.3/6.6/8.x

- `engines/hors_ligne.py` : **`environnement_moteur()` retourne un nouveau dict** avec `HF_HUB_OFFLINE=1`, retire PYTHONHOME/PYTHONPATH/VIRTUAL_ENV, sans modifier le serveur. En 6.3, utiliser ce dict au lancement du sous-processus et **`commande_runner(...)`** ; ne pas résoudre le lien `bin/python` du venv vers CPython, sous peine de perdre l'environnement du moteur.
- Le runner active le hors ligne avant d'importer l'adaptateur et restaure sa valeur précédente en sortie. Ce contexte est un garde-fou, pas un remplacement de l'environnement transmis : huggingface_hub lit ce réglage à l'import. Ne jamais activer globalement le hors ligne dans le serveur, qui doit pouvoir télécharger explicitement.
- Copie des options du modèle avec **local_files_only=True** et **trust_remote_code=False**, valeurs contraires du job écrasées sans modifier le job. Les adaptateurs réels 8.x devront les transmettre seulement aux API qui les acceptent, et charger depuis le chemin local, jamais depuis l'identifiant du dépôt.
- Suppression refusée pendant toute opération, donc aussi pour le modèle actif ; type capturé sous le verrou au moment du refus et message HTTP 409 spécifique à une exécution. Fichiers et résultats conservés, suppression possible après fin. **6.3/6.6 doivent garder le créneau occupé jusqu'à la fin réelle du processus moteur**, même après demande d'arrêt, crash ou délai : ne pas libérer tôt.

## Limites restantes, sans qualification réelle

- Jalon PC 1.x, sonde 1.7, case 3.2 et adaptateurs 8.x restent dus sur les deux OS ; ne pas convertir les tests serveur en validation PC.
- Résolution de l'exemple `Systran/faster-whisper-large-v3-turbo` indisponible publiquement à revoir avant les essais. L'alias réel de faster-whisper v1.2.1 pointe vers `mobiuslabsgmbh/faster-whisper-large-v3-turbo` ; ne pas substituer les modèles d'essai sans confirmation.
- CDN/Xet respectant les Range, chargements, variantes et chemins Windows : à vérifier sur PC. Métadonnées de shards Xet possibles hors data, pas de poids. Dossiers partiels/non prêts absents de l'interface ; reprise ou nettoyage manuel. Corruption locale à moins d'une seconde du téléchargement/date restaurée : détectée comme non prête, mais le cache HF peut empêcher sa réparation sans nettoyage manuel. Une erreur OS de suppression donne encore 500 générique.
- 6.5 : vraie clôture des exécutions abandonnées non faite ; récupération actuelle refuse les états non finalisés. 6.6 : supervision et ordre d'arrêt à compléter, listage interne réseau sans délai exposé, pas de garantie de délai global d'arrêt pendant téléchargement. Voir [[Reprise du développement après le lot 4]].

## Suite

Prochaine étape proposée : **lot 6**, en commençant par **6.1 — liste et décodage des audios synthétiques**. Ne pas prétendre que l'exécution web complète ni le stockage des résultats sont déjà réalisés : ils restent au lot 6, puis consultation/comparaison au lot 7 et documentation/intégration au lot 9. Ne pas démarrer un nouveau lot au titre de la seule demande de terminer le lot 5.
