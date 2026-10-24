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
