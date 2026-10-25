---
title: Décisions du prototype de benchmark
type: note
permalink: transcription-bench/projet/decisions-du-prototype-de-benchmark
status: décisions validées, plan consolidé ; faisabilité réelle à valider
provenance: repo transcription-bench, branche main ; décisions initiales 2026-10-23
  (3aa6d35), consolidation 2026-10-24 (base b3f126c)
date: '2026-10-24'
tags:
- decision
- brainstorming
- '2026-10-23'
---

# Décisions du prototype de benchmark

## Provenance et état
Brainstorming du 2026-10-23, puis consolidation approuvée le 2026-10-24 dans le dépôt `transcription-bench`, branche `main`, base `b3f126c`. Le change OpenSpec `add-benchmark-prototype` contient les exigences, le design et les tâches ; il n'est pas implémenté. Aucune installation de moteur, aucun téléchargement de poids et aucune inférence réelle effectués sur le serveur de développement.

Cette note est le point d'entrée des décisions approuvées. Les specs sont la source des exigences ; les notes exploratoires conservent l'historique du besoin produit.
## Finalité
Outil de décision : estimer ce que des modèles ASR donneront sur des machines ordinaires, sans GPU dédié. Deux utilisateurs : Ben (Linux x64) et un collègue (PC Windows x64).

## Observations
- [decision] Programme Python, serveur web local, interface en HTML pur (ni CSS ni JavaScript), formulaires et bouton d'actualisation.
- [decision] Plateformes : Windows x64 et Linux x64 ; Mac hors périmètre.
- [decision] Libre choix du modèle par identifiant Hugging Face, dans les limites des moteurs installés ; refus explicite si incompatible ; aucune exécution de code distant arbitraire.
- [decision] Trois moteurs : faster-whisper (CTranslate2), transcribe.cpp, Hugging Face Transformers ; architecture prévue pour ajouter des moteurs via des adaptateurs.
- [decision] Transformers sert à l'exploration libre ; ses temps CPU ne représentent pas forcément un déploiement optimisé.
- [decision] Exécution CPU uniquement pour les mesures de référence (GPU et Vulkan désactivés, consigné dans les métadonnées).
- [decision] RTF ≤ 2 = objectif à terme, affiché comme repère ; jamais un critère d'exclusion pendant les benchs.
- [decision] Audios déposés dans un dossier prédéfini ; traitement unitaire ou par lot séquentiel ; jamais de parallélisme.
- [decision] Chaque exécution conserve transcription, métadonnées (audio + empreinte, modèle + révision, moteur + version, quantification, réglages effectifs, machine) et mesures, sans écraser les précédentes ; comparaison de transcriptions entre modèles dans l'interface.
- [decision] Réglages exposés seulement s'ils sont pris en charge par le moteur, valeurs par défaut effectives enregistrées.
- [decision] Mesures : temps de chargement, temps de transcription par audio, temps total, durée audio, RTF, pic de RAM en valeur brute, temps CPU consommé. Pas de pourcentages, pas de swap.
- [decision] Hors premier jalon : diarisation, correction par LLM, streaming, score WER automatique.
- [decision] Le lancement du serveur n'installe pas les moteurs ; installation d'un moteur et téléchargement d'un modèle = actions explicites dans l'interface.
- [constraint] Aucun téléchargement de moteur ou de modèle sur le serveur de développement ; inférences et mesures uniquement sur le PC de Ben (et celui du collègue). Le serveur sert au code, à l'interface et aux tests avec moteur factice.

## Relations
- relates_to [[Cadrage et suite]]
- implements [[Protocole à définir]]
- relates_to [[Moteurs et faisabilité technique]]

## Consolidation approuvée — 2026-10-24

- [decision] Trois moteurs conservés ; Transformers limité à Whisper et Parakeet TDT au premier jalon. Les autres familles Transformers sont des extensions futures.
- [decision] Fenêtres de secours fixes de 30 s, consignées par audio ; méthode native seulement après vérification de la famille.
- [decision] Inférence hors ligne à partir de fichiers locaux complets ; aucun téléchargement implicite. Transformers charge uniquement des poids safetensors et aucun code distant.
- [decision] Priorité à un jalon de faisabilité sur PC Linux puis Windows : installation/import, CPU, court audio, fichiers requis et hors ligne. Rien de cela n'est exécuté sur le serveur de développement.
- [decision] Sécurité minimale du serveur local, résultats finalisés immuables, clôture des états abandonnés sans reprise d'inférence dans une ancienne exécution. Les détails contractuels restent dans OpenSpec.
- [decision] Les contextes sont définis dans `AGENTS.md` : restrictions serveur par défaut, PC de test explicitement déclaré ; aucun rôle déduit de l'OS ou du hostname. Les opérations réelles exigent un accord de portée précise.
- [scope] Pas de diff textuel, référence, WER ou répétitions automatiques ajoutés. Pas de nouvelle installation autorisée par cette mise à jour documentaire.

Prochaine étape : exécuter le jalon préalable sur PC autorisé, puis ajuster les hypothèses documentaires avant l'implémentation complète. Le code applicatif n'existe pas encore.

### Précisions après relecture

La restriction Safetensors concerne uniquement Transformers : `model.bin` reste le format attendu de CTranslate2 pour faster-whisper. Les dépôts mixtes ne sont pas rejetés pour la seule présence d'autres formats ; seuls les fichiers explicitement autorisés pour la famille sont téléchargés et chargés. Les mesures finales indisponibles restent absentes, jamais remplacées par zéro. La sécurité locale utilise un jeton renouvelé au démarrage, sans gestion de session.

### État de la consolidation documentaire

Relecture intégrale par le principal et advisor, puis vérification ciblée des corrections le 2026-10-24. `AGENTS.md`, les huit artefacts du change et les six notes ont été réconciliés. Validation OpenSpec stricte et contrôle des espaces Git réussis. Aucun code applicatif, moteur ni poids ajouté ; aucune validation réelle Linux/Windows effectuée. Prochaine action fonctionnelle : jalon 0 sur PC avec accord explicite ; la publication de ces documents n'autorise pas les téléchargements ou installations.

## Révision de la couche web — 2026-10-24

Provenance : dépôt `transcription-bench`, branche `main`, base `09b366f` ; décision utilisateur d'adopter un framework dès le départ, comparaison documentaire par trois scouts puis arbitrage avec advisor.

- [decision] Flask 3.1.3 pour les conventions requête/réponse, formulaires, erreurs et client de test ; templates Jinja2 `.html` avec échappement automatique ; Waitress 3.0.2 pour servir sur Windows/Linux. Le routage stdlib et les f-strings HTML prévus initialement sont remplacés. Le choix et ses alternatives sont décrits dans OpenSpec D1/D2.
- [decision] Routes minces, fabrique d'application sans effets de bord, services et supervision indépendants de Flask. Pas de base de données, d'asynchrone, d'extension de formulaires ni de nouveau lanceur de tests.
- [decision] Lancement par la CLI et la seule API publique `waitress.serve`, sans débogueur, reloader ni workers multiples. Le serveur de développement Werkzeug n'est pas utilisé en fonctionnement normal. Le jeton anti-CSRF par démarrage reste sans cookie/session ; le contrôle Host conserve le port.
- [constraint] L'arrêt du moteur reste sous la responsabilité de la supervision CLI, pas du framework. Le cycle de vie via uv et les signaux Windows/Linux doivent être vérifiés par une sonde factice préalable sur PC (tâche 1.7), avant implémentation complète.
- [validation] Recherche documentaire uniquement ; aucune pile web installée, aucune sonde réelle exécutée. La révision n'autorise pas de nouvelles installations sur le serveur de développement. Le prototype reste non implémenté. Relecture finale advisor : publiable après corrections appliquées (signaux, verrous, attente du worker et limites de corps) ; `openspec validate --all --strict` et `git diff --check` réussis. Les validations réelles restent au jalon 0.

### Précisions de la relecture web

- [decision] Deux limites distinctes : 64 Kio pour les formulaires dans Flask, 1 Mio pour le corps tamponné par Waitress. Les refus HTTP de Waitress avant appel de l'application ne passent pas par les templates ; ils ne déclenchent aucune action. Les pages normales et d'erreur de l'application restent en HTML seul.
- [decision] Dès le premier signal d'arrêt, les signaux suivants sont ignorés ; mutation et publication de marqueurs prêts sont interdites sous le verrou du créneau. L'attente du thread d'opération est bornée, pas la durée globale de sortie pendant un téléchargement : les E/S et threads internes peuvent encore retarder la fin du processus. Aucun thread Python n'est tué.
- [constraint] Si le worker n'est pas terminé, le verrou d'instance reste détenu jusqu'à la fin réelle du processus et aucun marqueur prêt n'est publié. Un arrêt forcé reste brutal et relève de la récupération existante. La sonde PC doit confirmer ces comportements ; aucune validation réelle n'est revendiquée.

## Début du travail sur serveur — 2026-10-25

Provenance : dépôt `transcription-bench`, branche `main`, base `163972c` ; contexte serveur de développement déclaré par l'utilisateur.

- [decision] Avancer tâche par tâche via worker, avec revue advisor après chaque tâche, corrections éventuelles, puis commit/push des seuls fichiers concernés, sur demande explicite de l'utilisateur.
- [validation] Tâche 2.1 terminée : outillage utilisateur uv et Python 3.12 géré préparé avec accord ; commandes `uv --version` et `uv python find 3.12` vérifiées. Revue advisor favorable, sans correction nécessaire. Python système et runtime Basic Memory préservés ; aucun moteur, poids ou inférence réelle.
- [status] Progression OpenSpec : 1/39. Aucun code applicatif ajouté. Le jalon PC n'est pas validé.
- [next] Avant 2.2 : réconcilier le préalable dans proposal/design/tasks pour permettre le développement serveur avec moteur factice, en conservant les validations Linux/Windows obligatoires avant qualification des moteurs et de la pile web sur PC. La dépendance actuelle de 2.2 à 1.7 reste inchangée.

## Développement serveur autorisé avant qualification PC — 2026-10-25

Provenance : dépôt `transcription-bench`, branche `main`, base `4077f0c` ; révision de proposal/design/tasks approuvée par l'utilisateur puis relue par le même advisor du lot 2.

- [decision] Cette décision remplace le blocage historique de toute implémentation avant le jalon PC et les mentions antérieures d'absence d'autorisation d'installation : le développement et les tests sur serveur peuvent avancer sans moteur réel, avec moteur factice, réponses simulées et audios synthétiques locaux. L'accord couvre uv, Python 3.12 géré et les dépendances serveur prévues (Flask, Waitress, av, numpy, huggingface_hub, psutil et leurs dépendances), dans l'environnement du projet seulement.
- [constraint] Aucun moteur réel, poids ou inférence réelle sur le serveur. Le jalon 0 reste obligatoire avant les adaptateurs réels et la qualification des moteurs, familles, fichiers et méthodes long-form sur Linux et Windows. La sonde web 1.7 sur les deux PC reste due ; les tests serveur ne la remplacent pas. Une tâche incluant une validation PC ne peut être cochée pour son seul code factice.
- [decision] Même session advisor reprise après chaque tâche et correction d'un lot ; rafraîchissement de son contexte uniquement lors du passage à un nouveau lot. Worker réalise les tâches une par une ; commit et push après revue favorable et corrections.
- [risk] Le développement de la couche web précède sa qualification PC : un écart observé plus tard peut imposer des corrections de code ; tout écart doit être consigné et réconcilié avant la mise en œuvre qui en dépend.

## Socle Python créé — tâche 2.2, 2026-10-25

Provenance : dépôt `transcription-bench`, branche `main`, base `3b340a2`.

- [validation] Tâche 2.2 terminée et revue favorable sans correction. `pyproject.toml`, paquet racine `transcription_bench`, CLI minimale, `.python-version` et `uv.lock` créés. `uv run --locked transcription-bench --help`, vérification du verrou, trois tests unittest, validation OpenSpec stricte et contrôle Git réussis. Sans argument, la CLI refuse explicitement le démarrage : serveur non encore implémenté.
- [validation] Dépendances serveur installées uniquement dans `.venv` : Flask 3.1.3, Waitress 3.0.2, Jinja2 3.1.6, Werkzeug 3.1.9, av 19.0.2, numpy 2.5.4, huggingface_hub 2.3.0, psutil 7.2.2. Verrou universel PyPI ; aucun paquet moteur installé. Cela ne valide ni les PC ni la sonde web 1.7.
- [status] Progression 2/39. Prochaine tâche : 2.3, création des dossiers de données au démarrage. Aucun serveur web ni moteur réel à ce stade.

## Lot 2 terminé — tâche 2.3, 2026-10-25

Provenance : dépôt `transcription-bench`, branche `main`, base `df9f776`.

- [decision] `data/` est ancré à la racine du projet, pas au répertoire courant : `uv run` peut être lancé depuis un sous-dossier, alors que la règle Git `/data/` ne couvre que la racine. Cela évite la dispersion des modèles/résultats et leur suivi Git accidentel. Initialisation idempotente des dossiers audio/models/engines/results, sans écraser leur contenu.
- [validation] Tâche 2.3 terminée ; advisor du lot repris pour revue, correction de l'ancrage appliquée par worker puis relue favorablement dans la même session. Sept tests unittest réussis, aide CLI sans effet, verrou et OpenSpec strict validés, contrôle des espaces Git et exclusion des quatre dossiers vérifiés. Tests limités aux dossiers temporaires.
- [status] Progression 3/39 : lot 2 complet. Prochain lot : serveur web et créneau d'opération (3.x), avec nouveau contexte advisor au changement de lot. La CLI prépare les dossiers mais refuse encore explicitement de démarrer un serveur non implémenté. Aucune validation PC, installation moteur, poids ou inférence réelle.

## Lot 3 — couche web initiale (3.1), 2026-10-25

Provenance : dépôt `transcription-bench`, branche `main`, base `8f8b366`.

- [validation] Tâche 3.1 terminée : fabrique Flask sans effets, templates HTML seuls et échappés, erreurs 404/405/500 sans trace et en-têtes conservés ; CLI Waitress API publique sur 127.0.0.1, port configurable (8765 par défaut), quatre threads et limite de corps 1 Mio. Dix-huit tests passent, dont rejeu avec huit graines de hachage après correction advisor du test Allow sensible à l'ordre. Revue finale favorable, validation OpenSpec stricte et verrou vérifiés.
- [decision] `POST /dossiers/verifier` réutilise provisoirement le service idempotent de préparation des dossiers pour un parcours POST → 303 → GET réel. Il ne prétend pas implémenter les opérations futures. Il devra être protégé par le jeton en 3.2.
- [validation] Sonde HTTP locale sur serveur, port 8799 : accueil 200, action 303, erreur 404 ; processus arrêté ensuite. Contrôle de fonctionnement uniquement, ne remplace pas la sonde 1.7 sur les PC.
- [status] Progression 4/39. Host/Origin/jeton et limite applicative (3.2), chemins (3.3), créneau (3.4), verrou/accueil complet (3.5) et supervision complète (6.6) restent à réaliser. Aucun moteur ni poids.
