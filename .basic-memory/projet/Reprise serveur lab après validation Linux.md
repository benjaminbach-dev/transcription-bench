---
title: Reprise serveur lab après validation Linux
type: note
permalink: transcription-bench/projet/reprise-serveur-lab-apres-validation-linux
date: '2026-11-02'
status: reprise préparée ; clone lab non confirmé
tags:
- reprise
- lab
- multi-hotes
- livraison
---

# Reprise serveur lab après validation Linux

## Point d'arrêt et transmission

Le 2026-11-02, l'utilisateur demande une note et la publication des changements nécessaires pour poursuivre sur son serveur lab. Le dépôt de transmission reste **privé**, `benjaminbach-dev/transcription-bench`, branche `main`. Aucun passage en public, push forcé ou remplacement d'historique n'est autorisé par cette transmission. Identifier le commit reçu avec `git log -1` ; la version du code et de cette note doit être comparée au distant avant reprise.

Dernier poste de travail confirmé : **PC de test Linux**. Le clone et la configuration du lab ne sont pas encore constatés. Le serveur web lancé par l'agent sur le port 8766 a été arrêté sur demande ; le programme occupant 8765 n'a pas été identifié ni arrêté.

## État fonctionnel et validations

- [status] OpenSpec `add-benchmark-prototype` : **38/55** tâches. Les exigences restent dans OpenSpec, pas dans cette note.
- [implementation] Adaptateurs et verrous : faster-whisper/Whisper, transcribe.cpp/GGUF Whisper, Transformers/Whisper et Parakeet TDT. CPU, imports moteurs différés hors du serveur, options hors ligne. Parakeet ne reçoit pas de langue forcée ; `langue_imposee=null` est volontaire.
- [validation] **698 tests complets réussis** ; 59 tests ciblés CI/exécutions réussis après l'ajustement du rapport CI. OpenSpec strict, verrou uv hors ligne, contrôle des espaces et aide CLI vérifiés.
- [validation] Parcours CLI/Waitress/HTTP Linux réel : quatre combinaisons courtes, résultats et comparaison, refus 409 de concurrence, arrêts utilisateur et serveur sans moteur survivant, redémarrage sans réécriture des résultats finalisés.
- [validation] Timings natifs transcribe.cpp conservés par appel, en millisecondes, jusqu'au JSON et au tableau HTML ; vérification réelle en natif et en deux fenêtres de 30 s, aucune somme ou valeur absente inventée à zéro. Anciens résultats compatibles.
- [constraint] Tests de fonctionnement du logiciel, pas évaluation des modèles. La voix CI peut être de toute langue locale disponible ; culture de voix, langue du texte et langue imposée par le moteur sont séparées, aucun mot attendu ni score.
- [limit] Le parcours HTTP adopte des environnements existants resynchronisés hors ligne sans changement et des modèles revérifiés par SHA-256. Ce n'est pas un essai d'installation vierge par formulaire, ni une vérification Windows ou un contrôle visuel humain.

Compte rendu partageable : `docs/validation-linux.md`. Preuves brutes et empreintes du code testé : `data/feasibility/parcours-http/20261102-141608/`, uniquement sur le PC ; les tests ont porté sur l'arbre de travail basé sur `1424424` avant son commit de transmission.

## Ce qui voyage et ce qui reste ici

- [scope] Git transmet code, verrous, specs, documentation, workflows CI, licence MIT et mémoire `.basic-memory/`.
- [constraint] **Ne pas copier les venvs du PC comme environnements du lab.** `data/`, `.venv/`, poids, audios, résultats, preuves brutes, logs et sauvegardes privées ne voyagent pas par Git.
- [risk] Sous `data/publication-privee/` restent une sauvegarde vérifiée de l'ancien historique et un candidat assaini séparé de 40 commits. Ce candidat n'inclut pas les changements de cette session. La copie nue conserve des références privées de récupération : jamais de `push --mirror`, jamais de publication de la sauvegarde.
- [status] CI écrite, pas encore vérifiée sous Windows ; jobs conditionnés à la visibilité publique. Un push privé peut créer un run dont les jobs sont ignorés : ce n'est pas une validation CI Windows.

## Ordre de reprise sur le lab

1. Déclarer le contexte serveur de développement, vérifier répertoire, shell, branche, état Git et remote ; récupérer `main` du dépôt privé sans écraser des changements locaux. Aucun rôle de machine n'est déduit d'un chemin ou d'un hostname.
2. Vérifier par MCP que le projet Basic Memory **`transcription-bench`** pointe vers `.basic-memory/` de ce clone. Cette configuration ne voyage pas avec Git. Si absente ou ambiguë, le signaler et faire autoriser sa configuration ; pas de repli vers `main` ni de lecture des notes par fichiers/CLI.
3. Lire [[Décisions du prototype de benchmark]], puis cette note et OpenSpec. Vérifier uv/Python 3.12 ; préparer seulement l'environnement serveur du projet dans la portée d'installation autorisée. Les tests unitaires/factices n'ont besoin d'aucun poids.
4. Le lab, dans son contexte de développement, n'installe aucun moteur réel, ne télécharge aucun poids et ne fait aucune inférence réelle. Les preuves Linux déjà obtenues ne sont pas à refaire pour le seul changement de poste.
5. Finaliser la voie de publication publique et l'audit du candidat complet ; instructions CI proposées dans `docs/proposition-contexte-ci.md`, **AGENTS.md encore inchangé**. Relecture avant application, puis `/reload` avant d'utiliser le contexte CI.
6. Après les autorisations nécessaires : publication et exécutions CI Windows (tests, imports, sonde voix système, inférences techniques). Ne cocher aucune vérification Windows sans run correspondant.
7. Seul reliquat 8.2 : seconde architecture GGUF à choisir/qualifier avec accord précis de modèle/téléchargement, ou report explicite du périmètre. Les timings sont terminés ; ne pas recréer cette dette.

## Reprise entre deux postes

- [fact] Un clone sur le lab ne change rien au clone du PC et ne notifie pas les sessions d'agent. L'historique de conversation et la configuration MCP ne sont pas synchronisés par Git.
- [process] Une fois le lab effectivement prêt, y mettre à jour cette note avec poste de travail courant, branche, état et prochaine étape, puis commit/push sur demande. Un clone simplement prévu ne doit pas être présenté comme existant.
- [process] Au retour sur le PC, demander la synchronisation avec le travail du lab : examiner les changements locaux avant un fetch/pull autorisé, puis relire la note reçue. Ne pas supposer qu'une ancienne session a intégré les nouveaux commits.
- [constraint] Éviter deux chantiers concurrents sur `main`. Laisser une note et des commits/push à chaque passage de relais ; rien n'est automatiquement publié par l'agent.

## Relations
- relates_to [[Décisions du prototype de benchmark]]
- replaces [[Reprise après la clôture Linux du jalon 0]]
