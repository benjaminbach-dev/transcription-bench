---
title: Socle des commandes CLI et modes exclusifs
type: note
permalink: transcription-bench/projet/socle-des-commandes-cli-et-modes-exclusifs
tags:
- cli
- decision
- validation
---

# Socle des commandes CLI et modes exclusifs

## Contexte et provenance

Développement serveur du change `ajouter-cli-agent`, à partir de `7ce5cc1` sur `main`, le 2026-11-10. L'utilisateur demande un worker par tâche, contrôle et corrections du principal, puis revue et publication par lot. Le modèle worker initial était Anthropic Haiku 5.5 high ; après pause, l'utilisateur impose `hyper/glm-5.3` high et une sélection plus stricte des tests. Il suspend ensuite les nouveaux appels advisor ; aucun nouvel appel n'a été lancé depuis.

## Décisions

- [decision] Web et commandes se partagent exclusivement le verrou du même dossier de données, y compris pour les lectures. Le serveur reste le comportement par défaut ; pas de mode concurrent ou détaché.
- [decision] La composition, la récupération et le nettoyage des services sont communs aux deux modes ; le lancement validé/réservé est partagé entre route et future commande.
- [decision] Le propriétaire valide le réagencement des instantanés JSON : sérialiseurs au socle, contrat de chaque commande lors de son ajout, puis vérification exhaustive transversale. L'exigence n'est pas réduite.
- [decision] L'aide des indicateurs aura une source unique pour le web et `results explain` ; cette dernière commande n'est pas encore implémentée au terme du socle.
- [decision] Limiter les nouveaux tests aux risques non couverts : le fichier de lancement partagé passe de onze à six tests après comparaison aux tests des routes et services, sans retirer les garanties de réservation/arrêt.

## Vérifications et limites

- [validation] Tâches 1.1 à 1.6 vérifiées : composition, analyse des sous-commandes, exclusion/récupération, sérialiseurs JSON UTF-8, suivi JSONL/signaux à drapeau et lancement partagé. Revue advisor du socle réalisée avant sa suspension, puis corrections principales des identifiants anglais et des clés de journal `event: log` / `line`.
- [validation] Suite complète de 1352 tests passée avant les dernières corrections et la réduction des cinq tests redondants (44,7 s). Après ces modifications : 146 tests ciblés de lancement/routes, signaux, session, sorties et CLI réussis. Ces nombres ne désignent pas des tests tous ajoutés par la CLI.
- [limit] Neuf avertissements OpenSpec préexistants de longueur d'exigences font encore échouer la validation stricte du change ; à résoudre avant sa validation finale.
- [limit] Aucun moteur réel, poids ou inférence réelle sur le serveur. Qualification Linux réelle et Windows non effectuées pour ces commandes. Aucun nouveau service ni dépendance ajouté.
- [status] Socle seul terminé : commandes métier des lots suivants encore à réaliser. Les preuves serveur ne qualifient pas un PC utilisateur.

## Relations

- relates_to [[Décisions du prototype de benchmark]]

## Lot de lecture CLI — 2026-11-10

- [status] Tâches 2.1 à 2.6 vérifiées : audios/dossiers, moteurs et journaux, inventaire modèles, options de préparation, résultats groupés/historique/aide, détail et comparaison. Les exigences et coches restent dans OpenSpec.
- [decision] À la demande de l'utilisateur, chevaucher travail du worker suivant et contrôles principaux uniquement sur des fichiers distincts ; pas d'édition concurrente des fichiers communs. Nouveaux appels advisor suspendus depuis sa demande explicite.
- [implementation] Le texte d'aide est extrait dans `web/results_help.py` et rendu par un gabarit échappé. Comparaison ponctuelle du texte visible intégral, exemples compris, avec la version précédente : identique après normalisation des espaces. Les contrôles documentaires portent désormais sur la page réellement rendue.
- [validation] Dernière vérification principale du lot : 107 tests ciblés commandes/CLI/aide/documentation/CSP réussis. Un test redondant de l'aide a été retiré ; aucun nouveau test pour la seule différence de mise en page.
- [limit] Hyper a refusé le worker 2.5 avec HTTP402 (crédits épuisés). Repli vers Anthropic Haiku5.5high explicitement autorisé par l'utilisateur et effectué ; le nouveau worker a repris les fichiers sans recommencer la tâche. Une reprise de session conservait le modèle Hyper : un nouveau worker Haiku a été nécessaire.
- [limit] Pas de qualification réelle Linux/Windows des commandes, aucune inférence ou téléchargement de poids. Les neuf avertissements de longueur OpenSpec restent à traiter avant validation finale.

## Lot des opérations CLI terminé, pause avant lot 4 — 2026-11-10

- [status] Tâches 3.1 à 3.6 terminées et vérifiées : installation, vérification puis téléchargement, suppression, vérification à blanc/lancement, arrêt et récupération. Progression du change : 18/23 ; le lot 4 n'est pas commencé, sur demande explicite de l'utilisateur.
- [implementation] Contrôles principaux : un signal entre vérification et transfert empêche le transfert ; `run check` conserve les mêmes validations que la route web, sans lui ajouter le contrôle propre au lancement ; la demande JSON réutilise le sérialiseur existant. Un résultat synthétique seul ne suffit pas à annoncer des mesures simulées.
- [validation] Vérification finale principale du lot : 114 tests ciblés de commandes, signaux réels POSIX avec moteur factice, session, cas limites de suivi et CLI réussis (13,8 s), `git diff --check` réussi. Pas de suite complète rejouée : elle reste prévue en 4.4.
- [validation] Deux tests d'intégration de l'arrêt couvrent SIGTERM/SIGINT puis SIGKILL suivi d'une commande : résultat du premier audio conservé, suivants non traités, code3 en arrêt propre, état abandonné après récupération brutale, moteur terminé et verrou libéré. Le nettoyage des témoins vérifie aussi l'heure de création avant d'arrêter un PID, pour éviter un PID réutilisé sur l'hôte partagé.
- [constraint] Pause après le lot 3. Ne pas commencer spontanément le lot 4. Aucun nouvel appel advisor n'est autorisé pour le moment ; cette suspension est toujours active.
- [limit] Aucun moteur réel, poids ou inférence réelle ; ces essais Linux serveur avec factice ne qualifient ni le PC utilisateur ni Windows. La qualification 4.5 reste hors de cet hôte.
- [next] À la reprise autorisée : lot 4 (parité, contrôles transversaux, documentation, revue/validation finale). Les neuf avertissements de longueur de la spec CLI bloquent toujours la validation OpenSpec stricte ; la revue advisor prévue en 4.4 reste soumise à la levée de sa suspension. Conserver les exigences, ne pas réduire silencieusement les tests ou la qualification.
