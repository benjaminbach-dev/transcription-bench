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
