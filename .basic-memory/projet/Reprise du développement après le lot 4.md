---
title: Reprise du développement après le lot 4
type: note
permalink: transcription-bench/projet/reprise-du-developpement-apres-le-lot-4
date: '2026-10-25'
provenance: transcription-bench, main, 90a7c34
status: lot 4 terminé ; lot 5 non démarré
tags:
- reprise
- workflow
- etat
---

# Reprise du développement après le lot 4

## À relire au redémarrage

1. `AGENTS.md` du dépôt et consignes globales.
2. Via MCP Basic Memory, projet `transcription-bench` : [[Décisions du prototype de benchmark]], puis cette note de synthèse. Vérifier que le projet pointe vers `.basic-memory/` de ce clone ; ne pas lire les fichiers de mémoire directement.
3. `openspec list`, puis les instructions apply, les tâches, design et specs concernés du change `add-benchmark-prototype`. Les exigences sont dans OpenSpec ; les anciens paragraphes de mémoire peuvent être historiques et remplacés par les décisions plus récentes.
4. Vérifier branche, HEAD et modifications locales avant toute écriture. Cette note de reprise et son lien peuvent être des modifications documentaires locales à préserver.

## Méthode décidée

- [decision] Une tâche à la fois. Le principal délègue l'implémentation au **worker**, donne un périmètre précis et la vérification attendue ; pas de délégation par les sous-agents.
- [decision] Après chaque tâche : revue **advisor**, correction par worker, reprise du même advisor pour validation ciblée, puis commit et push des seuls fichiers concernés. L'utilisateur a explicitement autorisé ces publications. Vérifier identité Git, remote et branche avant chaque publication, et préserver tout changement préexistant.
- [decision] Un contexte advisor par **lot**, repris avec `resume` après chaque tâche et correction ; nouveau contexte au changement de lot uniquement. Si l'outil expire une session, l'utilisateur autorise sa reconstitution automatique avec les décisions et revues précédentes, en lui signalant l'incident, sans redemander l'accord. Ne pas promettre qu'une session technique expirée est encore la même.
- [decision] Seul le principal écrit en mémoire, avec provenance et validations/limites ; les sous-agents lisent. Tests unitaires proportionnés, `unittest`, aucun outil de test supplémentaire. Navigator réservé aux parcours Playwright ; le principal ne l'utilise pas lui-même, puis nettoie captures et journaux générés et arrête ses serveurs temporaires.
- [decision] Cocher une tâche seulement quand tout son contrat est satisfait ; une validation PC explicitement incluse ne peut être remplacée par des tests serveur. Vérifier OpenSpec strict, verrou uv et `git diff --check` ; les suites ont aussi été rejouées avec plusieurs graines de hachage.

## Contexte et restrictions

- [constraint] Contexte confirmé : **serveur de développement**, pas PC de test. Aucun moteur réel installé, poids téléchargé ou inférence réelle. Audios synthétiques locaux uniquement, aucune donnée audio/transcription envoyée à l'extérieur.
- [decision] Le plan révisé autorise le développement serveur avec moteur factice et simulations sans attendre le jalon PC. Les dépendances serveur prévues sont autorisées dans `.venv` du projet ; aucune modification de Python système, Basic Memory ou services partagés.
- [constraint] Le jalon 0 et les qualifications Linux/Windows restent obligatoires avant les adaptateurs réels/choix techniques réels. Les capacités et performances réelles ne sont pas prouvées par le serveur.

## État vérifié au 2026-10-25

Provenance : dépôt `transcription-bench`, branche `main`, HEAD **`90a7c34`**, poussé sur `origin/main` ; dépôt propre avant écriture de cette synthèse. Change **`add-benchmark-prototype` : 11/39** tâches cochées.

- Lots **2 et 4 complets** ; lot **3 réalisé côté serveur**. **3.2 reste ouverte** seulement pour sa vérification PC 1.7.
- Lot 4 publié : 4.1 `4b7d36c`, 4.2 `e3f0d90`, 4.3 `1ccdca1`, 4.4 `90a7c34`.
- **177 tests passent**, validation OpenSpec stricte et verrou uv OK. Tests uv sur environnements temporaires et requirements vides, hors ligne : aucun moteur ou paquet nouveau téléchargé. Parcours navigateur accueil/moteurs/journaux/opération réussi ; favicon 404 non bloquant connu. Serveurs et journaux temporaires nettoyés.
- uv 0.13.5 et Python 3.12.15 géré, environnement serveur `.venv`, commande `uv run --locked transcription-bench [--port N]`. Ports 1024–65535, défaut 8765, écoute 127.0.0.1. Le dossier `data/` est ancré à la racine du clone et ignoré par Git.
- Interface Flask/Jinja2/Waitress, HTML seul, protections Host/Origin/type/64 Kio/jeton ; Waitress limité séparément à 1 Mio (rejette dès cette taille). Créneau unique d'opération et verrou système d'instance disponibles.

## Points techniques à ne pas perdre

- `engines/` racine : déclarations stdlib, registre sans import moteur. Réglages **par famille**, aucun défaut réel fixé avant 8.x ; français imposé par les futurs adaptateurs si possible, pas de traduction.
- Runner exact : `python engines/runner.py job.json`, bootstrap de la racine depuis `__file__` seulement, pas depuis le job ; ne pas dépendre de l'installation éditable du serveur. Chargement unique, audios séquentiels, fenêtres fixes 30 s, erreurs par audio puis suite du lot. Raw float32 little-endian 16 kHz mono, taille multiple de quatre exigée ; durées nulles en erreur. Métadonnées effectives constantes entre fenêtres, sinon erreur.
- Événements stdout préfixés `##TB-EVENT## ` ; les lignes parasites n'arrêtent pas le flux. Quatre types chargement/audio/audio_erreur/fin ; `factice` et `mesures_simulees` sont des booléens obligatoires à préserver dans les résultats et toutes les vues.
- Factice exécutable par l'interpréteur serveur grâce au drapeau de déclaration issu du code (jamais du job), sans qualification PC. Texte `[FACTICE]` et mesures **simulées** déterministes ; ce n'est pas un benchmark réel. E2E actuel = job → runner → événements, **pas encore le parcours web d'exécution ni le stockage** (lot 6).
- Installation réelle bloquée tant que les verrous qualifiés n'existent pas. Le factice est prêt sans installation. Installation générique : uv venv/sync, contrôle `sys.prefix` avant sync et imports Python `-I` dans le venv, marqueur prêt atomique empreinte/date/versions, publication sous verrou du créneau puis stockage. Pas de faux prêt après erreur/import échoué/absence ou corruption de marqueur. Les venvs moteurs devront fournir numpy et psutil 7.2.2 sous Windows, sans emprunter les bibliothèques du serveur.
- Ordre actuel du nettoyage CLI : arrêt minimal de l'installation avant arrêt du créneau. **6.6 doit l'aligner** : demander d'abord l'arrêt du créneau sans attente, puis terminer/collecter les processus. L'arrêt minimal vise uv, pas tous ses enfants. Ne pas annoncer la supervision complète acquise.
- **6.5 reste à faire** : le contrôle de récupération actuel refuse les résultats non finalisés/illisibles sans mutation ; il ne les clôture pas encore en abandonné. Réconcilier la clé `etat` supposée avec le format décidé en 6.4. Ne pas présenter 3.5 comme la réalisation de 6.5.
- Windows toujours à qualifier : fichiers JSON remplacés pendant consultation, verrous/liens/jonctions, arrêt/processus, port occupé (SO_REUSEADDR de Waitress peut permettre un partage), délai éventuel de libération d'un verrou après arrêt brutal. Aucun correctif fondé sur ces hypothèses sans vérification PC.

## Suite possible, non encore lancée

- **Lot 5**, puis **6**, **7**, **9** : réalisables côté serveur avec simulations et audios synthétiques. Partie PC de 6.6 restera ouverte jusqu'aux essais sur les deux OS.
- Prochaine tâche suggérée **5.1**, mais pas encore démarrée ni nouvel accord pour lancer ce lot dans cette étape de reprise.
- Les listes définitives de fichiers par famille et capacités restent à confirmer au jalon PC ; ne pas annoncer une compatibilité réelle démontrée avec des fixtures.
- Avant le stockage en **5.4**, résoudre et réconcilier le design : clé `<org>__<nom>` ambiguë (`a__b/c` et `a/b__c` entrent en collision). Les identifiants HF valides `nom` **ou** `org/nom` doivent rester acceptés. L'hypothèse d'un identifiant canonique retourné par `model_info` pour les noms seuls n'est pas validée.
- Lot 6 : n'accepter comme audio qu'un fichier ordinaire présent dans la liste autorisée, utiliser les helpers de confinement 3.3 ; aucun accès hors racines. Pas de garantie contre les modifications concurrentes du disque (TOCTOU).
- Lots **1 et 8** attendent les PC et un accord explicite sur installations, modèles et volumes ; aucun moteur réel sur ce serveur.
