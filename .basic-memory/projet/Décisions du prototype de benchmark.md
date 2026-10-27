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

## Lot 3 — protections serveur (3.2 partielle), 2026-10-25

Provenance : dépôt `transcription-bench`, branche `main`, base `baa424b`.

- [validation] Partie serveur 3.2 implémentée et relue favorablement après corrections : hook global Host → Origin → type → taille → jeton, y compris routes inconnues ; formulaires urlencoded 64 Kio, jeton aléatoire par démarrage sans session/cookie, refus sans action. Trente-quatre tests passent avec plusieurs graines ; sonde locale Waitress factice vérifie refus avant appel de l'application.
- [decision] Ports CLI limités à 1024–65535 : le port 80 est exclu, car navigateur/Werkzeug peuvent retirer son suffixe, incompatible avec le contrôle Host exact incluant le port. Port par défaut inchangé (8765).
- [observation] Waitress 3.0.2 rejette dès Content-Length = 1 048 576 (comparaison >=), et au-delà. La sonde envoie les en-têtes seuls pour éviter un reset de connexion sur Windows ; le petit corps de contrôle atteint l'application.
- [status] Case 3.2 laissée ouverte, progression 4/39 : sonde PC 1.7 sur Linux puis Windows toujours due. Les tests du serveur de développement ne la remplacent pas. Aucun moteur, poids ou inférence réelle.

## Lot 3 — chemins contrôlés (3.3), 2026-10-25

Provenance : dépôt `transcription-bench`, branche `main`, base `6ec2145`.

- [validation] Tâche 3.3 terminée, corrections worker puis revue finale favorable dans la même session advisor : confinement lexical et après résolution des chemins audio/résultats, refus absolus POSIX/Windows, remontées, liens sortants et boucles ; erreurs de résolution converties en refus explicites. Identifiants HF acceptés sous forme `nom` ou `org/nom`, sans import moteur. Cinquante et un tests passent avec deux graines ; tests de liens réellement exécutés ici. Progression 5/39, 3.2 reste ouverte.
- [constraint] Les services futurs des lots 5 à 7 doivent utiliser ces fonctions ; aucune route actuelle ne reçoit de nom de fichier. Pas de garantie contre une mutation concurrente du disque (TOCTOU). Liens/jonctions Windows non qualifiés : vérifier que les tests ne sont pas tous ignorés sur PC.
- [risk] À résoudre avant le stockage des modèles au lot 5 : `<org>__<nom>` du design est ambigu (`a__b/c` et `a/b__c` entrent en collision). Ne pas restreindre les identifiants valides pour contourner ce problème ; vérifier la stratégie de clé et réconcilier le design avant intégration. L'hypothèse d'un identifiant canonique retourné par `model_info` pour les noms seuls n'est pas validée.
- [next] Lot 6 : n'accepter comme audio qu'un fichier ordinaire présent dans la liste autorisée, notamment pour éviter les noms de périphériques Windows. Aucun moteur ni poids installé.

## Lot 3 — créneau unique (3.4), 2026-10-25

Provenance : dépôt `transcription-bench`, branche `main`, base `6bb9a8d`.

- [validation] Tâche 3.4 terminée, revue et corrections puis feu vert du même advisor. Créneau injecté dans les services, admission unique et thread démon indépendant de Flask, instantané immuable, état/journal et page `/operation` avec actualisation. Refus 409 si occupé, 503 après arrêt ; mutation et publication prêt protégées par le même verrou que le passage à l'arrêt. Échec de démarrage du thread testé et corrigé, sans blocage du créneau ni tentative de join sur un thread non démarré.
- [validation] Soixante-dix-sept tests passent avec plusieurs graines, contrôles du verrou et OpenSpec strict réussis. Sonde locale `/operation` 200 et POST sans jeton 403 ; aucune qualification PC.
- [constraint] Les routes doivent utiliser `executer_mutation` ; `publier_pret` est réservée au travailleur. Ces callbacks sous verrou restent courts et non réentrants ; le travail de fond est hors verrou. Pour 6.6 et le lot 6, l'état en mémoire du créneau ne remplace pas les marqueurs persistants ou `run.json` comme source de vérité : une course entre fin normale et arrêt peut le noter interrompu après une publication légitime antérieure à l'arrêt.
- [status] Progression 6/39, 3.2 toujours ouverte pour validation PC. Pas de supervision complète (6.6) ni verrou d'instance/accueil complet (3.5) à ce stade.

## Lot 3 — accueil et instance unique (3.5), 2026-10-25

Provenance : dépôt `transcription-bench`, branche `main`, base `7690e8c`.

- [validation] Tâche 3.5 terminée et revue favorable dans la même session advisor. Accueil avec état du créneau, dossiers et navigation ; pages des lots 4 à 7 explicitement provisoires, sans fausse capacité. Verrou système non bloquant dans `data/instance.lock`, fichier persistant sans PID, jamais supprimé ; `flock` Linux / `msvcrt.locking` Windows. Descripteur non hérité par les sous-processus, conservé jusqu'à la mort du processus si un thread d'opération reste actif.
- [validation] Ordre verrou → contrôle/récupération → dossiers → application → Waitress vérifié ; seconde instance refusée avant récupération, port réellement occupé sous Linux signalé sans trace et verrou libéré, arrêt brutal puis redémarrage vérifiés avec de vrais processus. Quatre-vingt-seize tests passent avec deux graines ; verrou et OpenSpec strict contrôlés. Navigator : parcours accueil/opération/retour/cinq pages provisoires/formulaire POST-303-GET/404 réussi, HTML sans CSS/JS ; seul favicon 404 non bloquant. Serveur de navigation arrêté et fichiers temporaires nettoyés.
- [constraint] Le contrôle de récupération est provisoire : il refuse un `run.json` non finalisé, illisible ou incohérent, sans réécrire les résultats. La tâche 6.5 doit le remplacer par la vraie clôture en abandonné et la gestion vérifiée du moteur survivant. La clé `etat` supposée doit être réconciliée avec le format décidé en 6.4. La coche 3.5 valide l'orchestration, pas la réalisation de 6.5.
- [risk] À éprouver sous Windows en 1.7 : Waitress active SO_REUSEADDR, ce qui pourrait laisser partager un port déjà occupé ; l'usage exclusif via une socket préparée et l'API publique `sockets` est une piste si le problème est confirmé. La libération du verrou OS après mort du processus peut aussi être légèrement différée sous Windows. Aucun correctif Windows ni qualification réelle affirmé ici.
- [status] Progression 7/39. Lot 3 réalisé côté serveur ; tâches 3.1, 3.3, 3.4 et 3.5 cochées. 3.2 reste ouverte uniquement pour la sonde PC 1.7. Aucun moteur, poids ni inférence réelle ; 6.5/6.6 restent ouvertes.

## Lot 4 — déclarations et registre (4.1), 2026-10-25

Provenance : dépôt `transcription-bench`, branche `main`, base `1ec5c0d`.

- [validation] Tâche 4.1 terminée, revue et corrections puis feu vert advisor. Paquet racine `engines/`, déclarations stdlib et registre par instance ; imports des adaptateurs différés. Trois moteurs réels et factice déclarés, aucune famille réelle qualifiée, aucun verrou ou adaptateur réel ajouté. Cent dix-sept tests annoncés par worker ; suite complète rejouée favorablement avec deux graines par advisor.
- [decision] Les réglages appartiennent aux familles, pas au moteur global. Aucun réglage réel n'est fixé avant les tâches 8.x : ni langue modifiable (français imposé par l'adaptateur lorsque possible), ni traduction, ni défaut de décodage supposé. Durée native strictement positive et finie, sans plafond arbitraire.
- [next] En 4.2, conserver la commande du design `python engines/runner.py job.json` par un bootstrap limité à la racine calculée depuis `__file__`, jamais un chemin du job. Vérifier en 4.3 ce lancement exact sans dépendre de l'installation éditable du serveur. La distribution wheel n'est pas une cible : lancement depuis le clone par uv.
- [status] Progression 8/39 ; 3.2 et validations PC restent ouvertes. Aucun moteur réel, poids ou inférence réelle.

## Lot 4 — runner isolé (4.2), 2026-10-25

Provenance : dépôt `transcription-bench`, branche `main`, base `4b7d36c`.

- [validation] Tâche 4.2 terminée et relue après corrections : runner autonome du serveur, job JSON, adaptateur issu du registre, chargement unique, audios séquentiels, fenêtres 30 s, texte/segments décalés, mesures secondes/octets et pic cumulatif Linux/Windows. Protocole stdout préfixé partagé sans dépendance serveur ; lignes parasites journalisées sans interrompre les événements. Cent trente-neuf tests passent avec deux graines ; vérification du verrou et OpenSpec strict réussies.
- [decision] Fichiers bruts float32 little-endian 16 kHz mono : taille multiple de quatre exigée, durée nulle en erreur. Métadonnées effectives, langue et threads appliqués doivent rester constants entre fenêtres d'un audio, sinon erreur explicite. Méthode `fenetres-fixes` consignée. Une erreur audio ne bloque pas les suivants.
- [constraint] Lancement direct `python engines/runner.py job.json` avec bootstrap limité à la racine issue de `__file__` ; aucune importation de module indiqué par un job. Chaque futur environnement moteur doit fournir numpy et, sous Windows, psutil 7.2.2 (`peak_wset`). Branche Windows testée par doublure seulement. Aucun adaptateur réel ni durée native activée avant validation PC/8.x.
- [status] Progression 9/39. 4.3 doit encore rendre le factice exécutable et marquer textes/mesures comme simulés ; 3.2 et validations PC restent ouvertes.

## Lot 4 — moteur factice (4.3), 2026-10-25

Provenance : dépôt `transcription-bench`, branche `main`, base `e3f0d90`.

- [validation] Tâche 4.3 terminée, revue et correction puis feu vert du même advisor. Adaptateur factice sans réseau, modèle ni I/O ; test de bout en bout via l'interpréteur serveur et la commande directe du runner, depuis un dossier temporaire : audio court, audio vide en erreur, audio 31 s ; un seul chargement et poursuite du lot. Cent quarante-huit tests passent avec deux graines, OpenSpec strict et verrou vérifiés.
- [decision] Le drapeau `factice` vient exclusivement de la déclaration du dépôt, pas du job. Sa famille reste non qualifiée sur PC ; ce drapeau autorise son exécution sans modifier le refus des moteurs réels. Chaque événement porte deux booléens obligatoires `factice` et `mesures_simulees`, vérifiés par le parseur et à préserver dans les futures vues.
- [constraint] Textes marqués `[FACTICE]`, mesures simulées déterministes (chargement 1,2 s, RTF 0,5, pic 300 Mio, temps CPU calculé fictivement) ; seule la durée audio est réelle. Ce ne sont ni des performances du serveur ni des PC. Le test couvre job → runner → événements, pas une exécution web ni le stockage des résultats du lot 6.
- [status] Progression 10/39. Prochaine tâche 4.4 ; 3.2 et validations PC toujours ouvertes.

## Lot 4 terminé — installation isolée (4.4), 2026-10-25

Provenance : dépôt `transcription-bench`, branche `main`, base `1ccdca1`.

- [validation] Tâche 4.4 terminée, revue et corrections puis feu vert advisor. Installation explicite dans le créneau unique : uv venv Python 3.12, uv pip sync depuis le verrou, sonde isolée du préfixe puis imports dans le venv, marqueur prêt atomique après succès avec empreinte/date/versions. Inventaire à quatre états et journaux HTML échappés ; absence ou corruption du marqueur ne rend jamais prêt. Le factice est prêt sans installation, les trois moteurs réels restent indisponibles tant que leurs verrous qualifiés PC sont absents.
- [validation] Cent soixante-dix-sept tests passent avec deux graines ; tests uv réels sur environnements temporaires et dépendances vides uniquement, UV_OFFLINE=1 et téléchargements Python interdits. Zéro moteur, poids, téléchargement ou dépendance nouvelle. Validation OpenSpec stricte, verrou et contrôle des espaces Git réussis. Navigator : accueil, moteurs, quatre journaux et opération réussis ; seul favicon 404 non bloquant. Serveur de navigation arrêté et traces temporaires nettoyées.
- [decision] Contrôles d'interpréteur/import en mode Python `-I` pour exclure PYTHONPATH, PYTHONHOME, site utilisateur et dossier courant ; préfixe vérifié avant synchronisation pour protéger l'environnement serveur. Lancement/enregistrement du sous-processus et refus d'arrêt sont atomiques sous un verrou court. Le lecteur JSON convertit aussi les erreurs d'encodage en refus explicites, sans casser les pages. Publication prêt sous le verrou du créneau puis verrou commun de stockage, jamais l'inverse.
- [constraint] En 6.6, passer d'abord le créneau à l'arrêt sans attendre, puis collecter l'installation : actuellement le nettoyage minimal arrête l'installation avant le créneau, et une installation réellement complète peut encore publier juste avant ce passage. L'arrêt minimal vise uv, pas tous ses éventuels enfants ; la supervision complète et son comportement Windows restent dus en 1.7/6.6. Aucun succès PC revendiqué.
- [decision] Continuité advisor : conserver la même session par lot ; si le fournisseur expire sa session, reconstitution du contexte autorisée sans nouvel accord, en le signalant. Ce repli ne dispense pas de transmettre les décisions et corrections précédentes.
- [status] Progression 11/39 : lot 4 complet. Le factice est testé de bout en bout au niveau runner ; parcours web d'exécution et stockage des résultats toujours au lot 6. 3.2, validations PC, récupération 6.5 et supervision 6.6 restent ouvertes. Avant le stockage des modèles au lot 5, résoudre et documenter la collision de la clé `<org>__<nom>` déjà relevée.

## Point de reprise après le lot 4 — 2026-10-25

Provenance : `transcription-bench`, `main`, HEAD publié `90a7c34` (11/39 tâches, 177 tests passants).

- [continuity] Lire [[Reprise du développement après le lot 4]] pour la synthèse de reprise : méthode worker/advisor/corrections/publication, reconstitution autorisée des sessions expirées, état du code, limites et suite possible. Cette synthèse n'autorise pas le lancement d'un nouveau lot à elle seule.
- [status] Lot 5 non commencé. Pour reprendre, relire les instructions et artefacts OpenSpec concernés ; les décisions récentes priment sur les états historiques de cette note. Les notes de reprise ajoutées ici restent documentaires et ne sont pas encore committées.

## Lot 5 commencé — 5.1 en attente d'arbitrage, 2026-10-25

Provenance : `transcription-bench`, `main`, base publiée `90a7c34` ; code local non committé. Cette section remplace l'état précédent « lot 5 non commencé ».

- [status] Voir [[Reprise du lot 5 — compatibilité en attente d’arbitrage]] : règles de compatibilité implémentées dans deux nouveaux fichiers, corrections de revue validées techniquement ; **220 tests passent**. 5.1 reste ouverte et non publiée, progression officielle 11/39 ; 5.2 non commencée.
- [pending] Avant de clore/publier 5.1, l'utilisateur doit trancher deux restrictions de profil non encore approuvées : exiger `tokenizer.json` pour Transformers même si vocab/merges suffisent à la bibliothèque, et exiger `preprocessor_config.json` pour tous les dépôts faster-whisper (ce qui exclut certains petits modèles). Ne pas adopter ces exclusions silencieusement.
- [constraint] Toutes les familles réelles restent non qualifiées. Aucun moteur, poids ni inférence réelle ; consultations documentaires publiques seulement, tests hors ligne. Les notes de mémoire et les deux nouveaux fichiers de code/tests restent des modifications locales à préserver jusqu'à la publication autorisée après arbitrage.

## Lot 5 — arbitrage clos et tâche 5.1 terminée, 2026-10-25

Provenance : `transcription-bench`, `main`, base `90a7c34` ; clôture relue et publication préparée. Cette décision remplace l'attente d'arbitrage précédente.

- [decision] Profil simplifié accepté : Transformers exige `tokenizer.json` + `tokenizer_config.json` ; faster-whisper exige `preprocessor_config.json` pour tout modèle CTranslate2 Whisper, sans mode alternatif ni valeurs de prétraitement par défaut. Certains dépôts utilisables par les bibliothèques sont donc volontairement exclus. Motif : simplicité et réduction des variantes ; réexamen au jalon PC, pas de promesse générale de sécurité.
- [validation] Spec des modèles, design D10 et tâche 5.1 alignés ; revue finale advisor favorable. **221 tests passent**, 44 ciblés, deux graines hors ligne ; verrou et OpenSpec strict valides. 5.1 cochée : **12/39**. Toutes les familles réelles restent non qualifiées, aucune installation moteur, aucun poids ni inférence réelle.
- [continuity] [[Reprise du lot 5 — compatibilité en attente d’arbitrage]] a été réécrite pour refléter la clôture, malgré son titre historique. Advisor du lot à reprendre : `c3afe5e6-b0f8-44e` (session précédente expirée, contexte reconstitué). Prochaine tâche 5.2, non commencée.

## Lot 5 — tâche 5.2 terminée, 2026-10-25

Provenance : `transcription-bench`, `main`, base publiée `34f147f` ; clôture relue et publication préparée.

- [validation] Lecture GGUF partielle et choix d'une seule variante intégrés aux règles de compatibilité. Formats v2/v3, lecture bornée ; magie `GGUF` inchangée quel que soit l'ordre des octets, contrôle indépendant des fixtures après correction advisor. **247 tests passent**, deux graines hors ligne ; OpenSpec strict et verrou uv valides. Case 5.2 cochée : **13/39**.
- [constraint] Aucun vrai GGUF, moteur, poids, nouvelle dépendance ou inférence réelle. Architecture et quantifications réelles toujours non qualifiées. Un fichier sélectionné par son en-tête n'est pas validé intégralement.
- [continuity] Voir [[Reprise du lot 5 — compatibilité en attente d’arbitrage]], mise à jour. Advisor à reprendre `d46d5377-0ebf-450`, worker 5.2 `5500b73d-2fa4-42d`. Prochaine tâche 5.3 : erreurs réseau et lecture bornée sans prélecture implicite de poids. Avant 5.4 : clé de stockage sans collision et traitement explicite des GGUF découpés. Les validations PC restent dues.

## Lot 5 — tâche 5.3 terminée, 2026-10-25 UTC

Provenance : `main`, base `12795fe` ; revue finale favorable et publication préparée. **14/39** tâches, **275 tests passants**.

- [validation] Vérification distante à commit figé, tailles et messages sans secrets ; admission avant réseau dans le créneau global ; résultat non publié après arrêt. Contrôle principal puis correction des lectures en avance, des identifiants courts et des fichiers parasites, revue advisor puis délai model_info 30 s et identifiant canonique conservé. Tests réseau entièrement simulés, aucune installation moteur ni poids.
- [constraint] HfFileSystem utilise Range exact sans cache ; respect effectif par CDN/Xet à confirmer sur PC, listage interne sans délai exposé reste une limite 6.6. Aucun succès PC revendiqué.
- [continuity] [[Reprise du lot 5 — compatibilité en attente d’arbitrage]] actualisée. Reprendre advisor `975a80f1-3737-403`. Enchaînement 5.4 puis 5.5 explicitement demandé, méthode worker → principal → advisor, publication par tâche.

## Lot 5 — tâche 5.4 terminée, 2026-10-26 UTC

Provenance : `main`, base `26653c2`, revue finale favorable et publication préparée. **15/39**, **319 tests passants**.

- [validation] Téléchargement explicite à commit figé, inventaire atomique, page modèles et suppression réalisés. Collision de stockage corrigée via clé calculée sur identité canonique/commit/variante ; contrôle des fichiers, chemins, alias, cache et verrous JSON après contrôle principal et revue advisor. Variante GGUF vérifiée sans perte de révision. Navigator : parcours complet simulé réussi, résultats conservés, serveur et traces nettoyés.
- [constraint] Aucun moteur ni poids réel, aucune inférence ou qualification PC. Limites cache HF/réparation, dossiers partiels, suppression OS et métadonnées Xet consignées dans [[Reprise du lot 5 — compatibilité en attente d’arbitrage]].
- [continuity] Advisor courant `b3219082-86fa-461`. Terminer **5.5** sans nouvelle demande d'accord général, ordre worker → principal → advisor ; garder le hors ligne dans le moteur uniquement, pas le serveur.

## Lot 5 complet — tâche 5.5 et clôture, 2026-10-26 UTC

Provenance : `transcription-bench`, `main`, base publiée `e425370` ; dernière tâche relue favorablement, publication de clôture préparée. **16/39 tâches, lot 5 complet (5/5), 329 tests passants** avec deux graines hors ligne.

- [validation] Suppression pendant une exécution refusée en 409 avec indication adaptée, type capturé sous verrou au moment du refus ; fichiers et résultats intacts, suppression possible après fin. Les autres opérations et l'arrêt restent correctement refusés.
- [validation] Environnement moteur dédié HF_HUB_OFFLINE=1 sans modifier le serveur ; runner force local_files_only=True/trust_remote_code=False dans une copie des options, active le hors ligne avant import et restaure le contexte. Interpréteur du venv conservé sans résolution du lien. Aucun moteur, poids ou nouvelle dépendance, aucune inférence ni qualification PC.
- [constraint] En 6.3/6.6, utiliser environnement_moteur/commande_runner et garder le créneau occupé jusqu'à la fin réelle du moteur. En 8.x, transmettre les options aux seules API concernées et charger depuis les fichiers locaux. Jalon PC, 3.2 et 8.x toujours ouverts.
- [continuity] **Nouveau point de reprise : [[Reprise après le lot 5]]**. Ancienne note lot 5 conservée comme historique. Advisor final `aaf3b07a-0158-496`, worker 5.5 `ed03c123-1bab-4c4`. Lot 6 non commencé ; la demande de terminer le lot 5 n'autorise pas à le démarrer automatiquement.


## Lot 6 — tâches 6.1 et 6.2, 2026-10-26 UTC

Provenance : `transcription-bench`, `main`, commit `e83bf5a` (base `15f6682`). **18/39**, 390 tests passants, deux graines hors ligne.

- [validation] 6.1 : liste/décodage PyAV des audios (`transcription_bench/audios.py`), refus des noms réservés Windows, sous-chemins, liens sortants et non-fichiers ; fichiers refusés listés « nom refusé », non sélectionnables. 6.2 : formulaire `/executions` et validation de la demande par service (`executions.py`) ; POST de vérification sans lancement ni 303. Revue advisor puis corrections et recontrôle ; une correction finale appliquée par le principal (`is_dir` dans un `try`).
- [decision] Le moteur factice est proposé via un **modèle synthétique** à clé constante (sans inventaire, sans fichiers) ; le job 6.3 lui passe un chemin fictif sous `data/`. Une seule fonction `motif_famille_non_executable` (engines/declarations.py) sert le runner et le formulaire ; les familles non exécutables sont affichées non sélectionnables.
- [constraint] Pour 6.3 : décodage `decoder_audio` n'attrape que FFmpegError/OSError, la boucle d'exécution doit convertir toute autre exception en erreur propre à l'audio ; écrire chaque signal en `<f4` dès son décodage (double copie mémoire actuelle) ; empreinte et décodage lus séparément (TOCTOU, 7.2 regroupe par SHA-256) ; les métadonnées doivent porter `factice` et `synthetique`. Aucun réglage réel déclaré (jalon 0/8.x). La case 6.2 ne prouve pas la consignation des threads dans `job.json`/`run.json` (6.3/6.4).
- [limit] Aucune validation PC ; durcissement `protocol_whitelist` PyAV non vérifié.


## Lot 6 — tâche 6.3, 2026-10-26 UTC

Provenance : `transcription-bench`, `main`, base `e83bf5a`. **19/39**, 427 tests passants (deux graines), revue advisor puis corrections et recontrôle ; dernière correction (`annuler_reservation` conserve le dernier résultat) par le principal.

- [validation] Lancement d'une exécution dans le créneau (`transcription_bench/execution_moteur.py`) : routes POST `/executions/lancer` et `/executions/arreter` (jeton, 303), runner via `commande_runner`/`environnement_moteur()` en groupe de processus propre, arrêt terminate→attente→kill, créneau occupé jusqu'à la fin réelle (y compris chemin d'exception), événements dupliqués = parasites, `reserver()` avant `creneau.demarrer`, arrêt utilisateur = état `interrompue` (`OperationInterrompue`). Seul le factice est exécuté, mesures simulées.
- [decision] Signaux décodés `<f4` sous `data/cache/<id>` (créé paresseusement, supprimé en fin) ; restes après arrêt brutal à nettoyer en 6.5. `sur_evenement` retiré : 6.4 définira sa propre consignation par exécution (dossier de résultats, AudioPrepare, PID + heure de création, run.log complet, durées D8). `derniere_execution()` → `ResultatExecution` en mémoire (non persistant).
- [constraint] 6.6 : `terminate`/`kill` ne visent que le PID du runner, pas son groupe (killpg Linux, Job Object Windows à décider) ; `tuple(stderr)` sans protection si le lecteur survit au join ; stderr Windows non forcé en UTF-8 ; `InstallationEchouee` journalise encore une pile complète. Dossiers `data/cache` à nettoyer en 6.5.
- [limit] Tests parallèles ×8 instables uniquement à cause des limites de tâches du sandbox (RLIMIT_NPROC), pas de la logique. Aucune validation PC ni Windows.


## Lot 6 — tâche 6.4, 2026-10-26 UTC

Provenance : `transcription-bench`, `main`, base `1a3fe57`. **20/39**, 476 tests passants, revue advisor + corrections + recontrôle favorable.

- [validation] Stockage des résultats (`transcription_bench/resultats.py`) : `data/results/<AAAAMMJJ-HHMMSS>-<8 hex>/` créé sous verrou, jamais réutilisé ; `run.json` (schéma 1, états `running` → `completed|interrupted|failed`), `run.log` complet, `<n>-<nom>/result.json` + `transcription.txt` écrits audio par audio. Mesures D8 serveur (durée d'opération, durée du processus), `null` = indisponible, jamais zéro. Format documenté en D11.
- [decision] `clore` tente toujours d'écrire l'état final `failed` après une erreur d'écriture, cache supprimé avant ; une erreur d'écriture arrête le moteur ; un statut d'audio consigné n'est jamais rétrogradé ; `heure_creation` = flottant brut de `psutil.create_time()` (source consignée) ; échec d'écriture de `run.log` signalé sans faire échouer l'exécution.
- [constraint] 6.5 : comparer `heure_creation` avec tolérance (sur ce serveur ~0,9 s avant l'horloge serveur) ou se rabattre sur `lance_a` ; tolérer un dossier sans `run.json` (échec d'`ouvrir` après mkdir) ; `run.json` peut rester `running` si l'ultime écriture échoue → `abandoned` ; NaN possible dans segments/réglages recopiés bruts ; nettoyer `data/cache`. Le mode mmap/`timings` transcribe.cpp est absent du schéma 1 (8.x). Immuabilité garantie en processus seulement.
- [limit] Aucune validation PC/Windows (os.replace, verrous).


## Lot 6 — tâche 6.5, 2026-10-26 UTC

Provenance : `transcription-bench`, `main`, base `31572bf`. **21/39**, 501 tests passants, revue advisor + corrections (contrôle final par le principal : suite et validations).

- [validation] Vraie récupération au démarrage (`recuperation.py`, après verrou d'instance, avant application) : `run.json` `running` → moteur survivant terminé seulement si PID **et** heure de création concordent (tolérance 1 s `psutil`, 5 s via `lance_a` en repli ; revérification interne psutil 7.2.2 avant signal ; descendance psutil) ; refus de démarrer si non identifiable, inaccessible ou survivant ; puis `abandoned` via `resultats.abandonner_execution` (durées null, pic partiel, audios non traités, statuts consignés conservés, `result.json` fait foi, aucun fichier final réécrit). Purge de `data/cache/execution-*` (jamais si lien/jonction). Idempotent ; états finaux, dossiers sans `run.json` ignorés ; `run.json` illisible/incohérent refusé sans réécriture.
- [limit] Dérive d'horloge ≥ 1 s : moteur non reconnu (mourra à sa prochaine écriture) ; arrêt brutal entre lancement et écriture du PID ; descendants orphelins → 6.6 (killpg / Job Object). Windows non éprouvé (AccessDenied, terminate immédiat).


## Lot 6 — tâche 6.6 (code livré, case ouverte), 2026-10-26 UTC

Provenance : `transcription-bench`, `main`, base `545b421`. **21/39 cochées**, 530 tests passants, revue advisor + corrections.

- [validation] Supervision CLI (`supervision.py`, `processus.py`, `cli.py`) autour de `waitress.serve` : gestionnaire SIGINT (+SIGTERM Linux) → SIG_IGN dès le premier signal puis exception ; `finally` idempotent : créneau à l'arrêt sans attente → moteur (signal au groupe, descendance psutil relevée avant SIGTERM, attente bornée puis kill) → installation uv idem → attente bornée du thread → verrou d'instance libéré en dernier, conservé si l'opération n'est pas close (code 1). Exécution interrompue par arrêt serveur = `interrupted` ; aucun marqueur prêt après arrêt. Vrais serveurs Waitress en sous-processus testés (SIGINT, SIGTERM, double signal) sans survivant.
- [decision] Windows : arborescence psutil « au mieux », pas de Job Object ni CTRL_BREAK ; stderr du runner en UTF-8 (`PYTHONIOENCODING`).
- [constraint] **Case 6.6 laissée ouverte** : le rejeu sur PC Linux/Windows (cas 1.7 via `uv run`, Ctrl+C console, double Ctrl+C, port occupé, arrêt brutal) reste dû. Limites : groupe non signalable après la sortie du processus principal ; un téléchargement bloqué retarde la sortie (pas de délai global) ; un moteur insensible au kill garde le créneau occupé.
- [status] Lot 6 réalisé côté serveur (6.1–6.5 cochées, 6.6 code livré). Suite : lot 7 (résultats/comparaison), puis 9.x ; jalon PC 1.x et 8.x toujours dus.


## Lot 7 — tâche 7.1, 2026-10-27

Provenance : `transcription-bench`, branche `main`, base `4007d17` ; revue finale advisor favorable, publication de la tâche préparée. **22/39 tâches cochées, 572 tests passants** (principal et advisor, hors ligne ; plusieurs graines).

- [validation] Consultation en lecture seule : historique et détail des exécutions, cinq états, transcriptions/segments/métadonnées/mesures, résultats partiels, marques factice/synthétique/mesures simulées. Lectures JSON sous verrou commun, confinement des fichiers eux-mêmes, schémas inconnus et identités incohérentes refusés sans modification ; liste tolérante aux fichiers illisibles. Un vrai runner factice puis lecture et rendu vérifient la compatibilité avec le stockage 6.4. OpenSpec strict, verrou uv et contrôle des espaces Git valides.
- [decision] Réglages composés affichés en JSON compact échappé ; nombres non finis seuls indisponibles, imbriqués convertis en null pour l'affichage. Le runner laisse encore passer des bornes de segments non finies : la vue les affiche indisponibles sans masquer texte et mesures. À confirmer sur les réglages réels en 8.x, aucune qualification PC/Windows.
- [continuity] Suite autorisée dans cette session : 7.2 puis 9.1 et 9.2, worker tâche par tâche → contrôle principal → advisor → corrections/recontrôle → commit/push par tâche. Advisor lot 7 à reprendre : `71cdf277-6293-41b`. Aucun moteur/poids réel ni nouvelle dépendance ; jalon PC, 3.2 et 6.6 restent ouverts.


## Lot 7 complet — tâche 7.2, 2026-10-27

Provenance : `transcription-bench`, `main`, base publiée `50aebcc` ; revue finale advisor favorable, publication préparée. **23/39 tâches, 621 tests passants**, plusieurs graines hors ligne, OpenSpec strict et contrôle Git valides.

- [validation] Groupes par SHA-256 source valide et comparaison HTML côte à côte des textes sélectionnés ; mélanges d'empreintes refusés, mêmes noms/empreintes distinctes séparés, mêmes contenus/noms différents regroupés. États, partiels, marques factices, modèles, moteurs, fenêtres, threads et mesures distinctes sont affichés ; RTF repère 2 non bloquant. Tests avec vrai runner factice et fichiers synthétiques seulement.
- [decision] Comparaison des réglages demandés/defaults et effectifs sur les valeurs JSON brutes, séparées des valeurs formatées. Liste et chaîne JSON, null et NaN/infini, types JSON distincts ne sont pas confondus ; l'affichage des non-finis peut être identique malgré une différence brute signalée. Aucun diff textuel, WER, référence ni score de qualité.
- [limit] Historique relu à chaque affichage, sans index ni pagination ; empreinte absente/invalide jamais groupée. Aucune validation PC/Windows, moteur/poids réel ni dépendance nouvelle.
- [continuity] Suite : 9.1 puis 9.2 selon méthode autorisée. Advisor 7 initial expiré ; contexte reconstitué dans `7eeb80de-cede-4c3`, feu vert 7.2. Nouveau lot 9 : nouveau contexte advisor. Tâches PC, 3.2 et 6.6 toujours ouvertes.


## Lot 9 — tâche 9.1, 2026-10-27

Provenance : `transcription-bench`, `main`, base publiée `175d84b` ; README relu favorablement après corrections, publication préparée. **24/39 tâches cochées**, suite inchangée **621 tests passants**.

- [validation] README de lancement et utilisation, installation officielle uv Linux/PowerShell, versions verrouillées, données, factice, architecture, hors ligne et limites documentés. Vérification worker en copie temporaire avec ressources déjà en cache : commande uv --locked --offline, accueil200, SIGINT et SIGTERM code0, instance concurrente refusée, ports invalides refusés, 621 tests. Copie et processus nettoyés, data du dépôt intact. Aucune nouvelle dépendance, moteur ou poids ; contrôle serveur uniquement, pas qualification PC.
- [decision] Documentation distingue synchronisation de .venv et immuabilité de uv.lock, interpréteur 3.12 existant ou géré par uv sans modification système, mesures serveur réelles et mesures moteur factice simulées, variables hors ligne et options de chargement. Arrêt décrit sans promesse de délai global ni de suivi des descendants échappés ; code1 si nettoyage incomplet, code2 si récupération impossible.
- [continuity] Prochaine tâche 9.2 autorisée : parcours intégré factice, corriger aussi le texte périmé de l'accueil annonçant encore la comparaison indisponible. Advisor lot9 à reprendre `46d2959b-894d-452`. Les validations PC et adaptateurs réels restent dus ; aucune archive du change à ce stade.


## Lot 9 complet côté serveur — tâche 9.2, 2026-10-27

Provenance : `transcription-bench`, `main`, base publiée `44c847a` ; revue finale favorable après correctif et contrôle navigateur, publication préparée. **25/39 tâches cochées, 630 tests passants** (worker trois graines 0/1/12345, principal graine71 ; advisor 148 tests ciblés). Publications précédentes : 7.1 `50aebcc`, 7.2 `175d84b`, 9.1 `44c847a`.

- [validation] Parcours HTTP réel en copie temporaire isolée via commande uv --locked --offline : dépôt de deux WAV synthétiques, vérification sans lancement, lot terminé, arrêt utilisateur et arrêt serveur en cours de lot → interrupted, résultats écrits intacts, moteur terminé/cache nettoyé. Arrêt brutal → running avec moteur survivant, puis redémarrage → moteur identifié terminé, abandoned sans reprise, audio restant non traité, nouvelle exécution distincte. Consultation/groupes SHA/comparaison fonctionnels. Accueil corrigé pour proposer la comparaison effectivement disponible.
- [correction] L'intégration a révélé que chargement et pic global n'étaient persistés qu'à la clôture : leur absence après abandon contrevenait à D8/D11. Désormais ConsignateurExecution retient les mesures dès réception, écrit run.json au chargement et persiste le pic actualisé avec chaque audio. Une erreur d'écriture au chargement arrête le moteur et conclut failed. Tests couvrent le vrai runner factice, la récupération sans mesures affectées manuellement, valeurs invalides, immuabilité et erreur d'E/S.
- [validation] Scénario d'abandon rejoué après correction : chargement simulé 1.2 s, pic simulé 314572800 octets conservé et marqué partiel ; durées opération/processus null, audio déjà écrit intact, suivant non traité. Navigator a confirmé ces valeurs et leur comparaison avec un résultat interrompu, ainsi que le parcours complet des pages ; seul favicon404 non bloquant. OpenSpec strict, verrou uv et contrôle Git réussis. Serveurs dédiés arrêtés, copie/harness/traces navigateur supprimés ; data du dépôt inchangé, aucun moteur/poids réel ni nouvelle dépendance.
- [limit] Signaux envoyés par killpg dans le serveur de développement : simulation, pas Ctrl+C console réel ni fermeture console Windows. Pause de timing injectée uniquement dans l'adaptateur factice de la copie puis restaurée ; aucune option produit ajoutée. Les mesures du moteur sont simulées, les durées serveur/décodées seules sont réelles. Fenêtre résiduelle : mort entre result.json et run.json → statut audio récupérable, dernier pic de cet audio pas encore persisté globalement.
- [status] Les travaux serveur planifiés sont terminés. **14 tâches restantes**, toutes liées aux PC : 1.1–1.8, clôtures 3.2 et 6.6, adaptateurs/validations 8.1–8.4. Ne pas cocher ces tâches ni archiver le change pour du factice. Prochaine étape : déclarer un PC de test, obtenir l'accord précis installations/modèles/volumes et commencer le jalon 0 ; vérifier le modèle faster-whisper d'essai et confirmer dépôt/variante GGUF avant téléchargement. Advisor final lot9 `e964a055-77d6-47c` (contexte reconstitué après expiration de `46d2959b-894d-452`).
