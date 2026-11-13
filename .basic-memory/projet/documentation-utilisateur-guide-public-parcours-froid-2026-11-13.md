---
title: Documentation utilisateur — guide, public et parcours à froid, 2026-11-13
type: note
permalink: transcription-bench/projet/documentation-utilisateur-guide-public-parcours-froid-2026-11-13
tags:
- documentation
- guide
- validation
---

# Documentation utilisateur — guide, public et parcours à froid, 2026-11-13

Clôture du change OpenSpec `rediger-documentation-utilisateur` hors relecture de style (tâche 4.3, laissée au propriétaire). Les sources de décision restent OpenSpec (design D1-D10) ; ceci consigne le contexte et les constats.

## Observations
- [decision] Public visé confirmé par le propriétaire le 2026-11-13 : personne à l'aise avec un ordinateur, sans programmation, prête à copier-coller des commandes (hypothèse D2 retenue telle quelle). Exemple principal confirmé : whisper-large-v3-turbo GGUF Q5_K_M via transcribe.cpp. #decision
- [validation] Parcours à froid complet le 2026-11-13 sur le PC de test Linux (T14s, Manjaro) : copie vierge par archive ZIP (1,1 Mo depuis GitHub), dossier de données neuf, guide suivi des étapes 3 à 12, parties navigateur dans un vrai navigateur. Première transcription lue (audio synthétique 10,7 s) puis comparaison de deux exécutions du même modèle sur le même audio, aucun second téléchargement. Durées : moteur ≈ 1 s (cache local), vérifications ≈ 40 et 50 s, téléchargement 590,9 Mio en ≈ 6 s, exécutions 5,841 s et 5,923 s. Arrêt vérifié (« Arrêt du serveur. »). #validation
- [fact] Écarts guide/application relevés au parcours, tous corrigés dans le guide (12) : panneau refermé après vérification avec résultat après actualisation, attentes des vérifications distantes, déroulement normal « Dépôt refusé (fichier-gguf-non-choisi) » sur dépôt à 5 variantes, journal d'installation dans « Versions installées », bouton d'installation restant affiché sur moteur prêt, libellé réel « Utiliser ce modèle pour préparer une exécution. », durées mesurées renseignées, distinction « meilleur temps » sur valeurs exactes avec affichage arrondi identique, libellé réel « RTF (durée de transcription / durée décodée) » (terme interdit hors gras/glossaire dans les tests), tri « Plus rapides » par défaut en comparaison, durée d'exécution dans l'historique (« Début » sans « Fin » à l'opération), décalage passager historique/opération. #ecart
- [fact] Cas de dépannage rencontré pour de vrai : port 8765 occupé par Thunderbird sur le PC de test ; message réel conforme au guide, solution documentée `--port 8080` appliquée sans toucher à l'autre programme. #ecart
- [validation] Contrôles : suite complète 1433 tests OK, dont 11 tests documentaires (libellés en gras = libellés d'interface, liens, termes interdits hors gras et glossaire, README < 60 lignes) ; `openspec validate rediger-documentation-utilisateur --strict` OK. #validation
- [decision] Preuves Windows réutilisées sans nouveau job : `docs/ci-windows.md` complété avec le run 43411758748 (2026-11-13, quatre combinaisons) et limites honnêtes (installeur de uv, lancement en console, Ctrl+C non vérifiés sur un poste Windows). AGENTS.md non modifié : il ne cite pas la structure de la documentation. #decision
- [limit] Reste ouvert : relecture de style (4.3) par le propriétaire. Non vérifié : installation de uv, décompression par l'explorateur, clonage Git, Windows sur poste réel ; durées propres à la machine de test. #limite

## Relations
- relates_to [[Qualification Linux CLI et charge système, 2026-11-13]]
- relates_to [[Décisions du prototype de benchmark]]