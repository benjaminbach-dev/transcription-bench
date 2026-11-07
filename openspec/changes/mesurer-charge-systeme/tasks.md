# Tasks

## 1. Mesures aux frontières du runner

- [x] 1.1 Ajouter un helper injectable de relevés système utilisant psutil existant sur le même thread ; tester amorçage ignoré, second appel non bloquant, séquence de deux audios isolée, intervalle < 0,1 s sans attente, zéro retourné après amorçage sans promesse de diagnostic des compteurs, exceptions et valeurs non finies/hors bornes ; documenter méthode versionnée et limites dans le module.
- [ ] 1.2 Intégrer le CPU système autour des bornes de transcription et les instantanés RAM après chargement/après audio ; vérifier par horloge/compteurs injectés le périmètre sans décodage/chargement CPU, les instants RAM et des observations simulées déterministes avec le moteur factice, sans relevés réels mélangés.

## 2. Événements et stockage compatibles

- [ ] 2.1 Transmettre les objets facultatifs sur les événements existants sans nouveau type et persister aux emplacements D3 ; tester version/provenance/unités/motifs, invalidité ou provenance contradictoire du seul objet système ignoré sans persistance et sans perte de transcription, codes stockés distincts des états de lecture, et aucune modification de `machine` ou du schéma global 1.
- [ ] 2.2 Étendre la consultation et les vues typées ; tester anciens fichiers sans nouvelles clés, objets inconnus/mal formés, absence explicite, relecture sans réécriture et lecture des mesures après suppression d'un modèle local ; documenter le contrat additif.
- [ ] 2.3 Couvrir interruption, échec audio et clôture d'abandon avec conservation du premier audio et de ses relevés, absence du relevé final manquant du second et immutabilité des fichiers finalisés ; vérifier qu'aucun relevé de l'ordinateur courant n'est substitué.

## 3. Lecture du contexte ordinateur

- [ ] 3.1 Ajouter le bloc secondaire repliable « Contexte de l'ordinateur » dans le détail et la comparaison sélectionnée : CPU global moyen, RAM disponible après audio et relevé après chargement, sans colonne système dans les listes ni classement sur ces valeurs ; tester libellés/valeurs, absence des faux calculs total-RSS ou CPU système moins moteur et compatibilité avec les composants de la refonte.
- [ ] 3.2 Aligner l'aide et le guide sur instantanés, autres programmes, ressources visibles et absence de garantie de fluidité ; adapter leurs tests de cohérence et vérifier que les indicateurs moteur du change UI restent distincts du contexte système.

## 4. Vérification intégrée et preuves

- [ ] 4.1 Exécuter les tests ciblés runner/protocole/consignation/consultation/web/CI et une sonde de fonctionnement psutil par deux appels sur le même thread autour d'un court intervalle dans les tests unitaires Linux/Windows, sans charge lourde, installation ni réseau ; consigner les plateformes réellement exécutées, sans seuil de performance.
- [ ] 4.2 Étendre si nécessaire la liste blanche des rapports JSON CI nettoyés pour les agrégats/méthodes/provenances, et tester qu'aucun audio, transcription, chemin sensible ou nouvel artefact/cache n'est exporté.
- [ ] 4.3 Sur PC Linux explicitement déclaré, après annonce du lot et dans les environnements/modèles autorisés, vérifier les nouveaux champs du runner réel, leur cohérence de périmètre et l'arrêt ; consigner machine, versions, configuration et limites. Ne pas exécuter ce volet sur serveur de développement.
- [ ] 4.4 Vérifier le runner réel dans le job Windows moteur prévu uniquement après autorisation de son exécution ; consigner commit/image/versions et champs nettoyés, sans assimiler CI au PC utilisateur ni lancer de modèle supplémentaire.
- [ ] 4.5 Observer le bloc secondaire de contexte ouvert/fermé avec navigator sur bureau/mobile et clair/sombre ; vérifier que les chiffres clés de la refonte restent au premier plan, qu'aucune colonne ou explication répétée n'apparaît dans les listes, et contrôler distinction moteur/système et absence de débordement ; valider OpenSpec strict et les espaces du diff.

## Application de la tâche 1.1 — 2026-11-07

- Créé `engines/mesures_systeme.py` (couture injectable `ReleveurSysteme` + `AmorcageCpu`, stdlib + psutil 7.2.2 uniquement, aucun import serveur ni moteur) et `tests/test_mesures_systeme.py` (21 tests déterministes + sonde de fonctionnement). Emplacement `engines/` : seul consommateur prévu `engines/runner.py`, exécuté dans le venv moteur où seule la racine du dépôt est dans `sys.path` ; psutil est déjà présent dans les verrous.
- Contrat D2/D3 respecté : deux appels `cpu_percent(interval=None, percpu=False)` sur le même thread (amorçage dont la valeur est ignorée, lecture), aucun appel intermédiaire, aucune attente ; mémoire via `virtual_memory().total/.available` (jamais `total-free`, ni somme de RSS) ; enveloppe `version: 1`, `methode_cpu: "psutil-cpu-percent-nonbloquant-v1"`, `version_psutil`, `provenance` (`reelle`/`simulee`) ; motifs écrits `lecture_impossible`, `intervalle_trop_court`, `valeur_incoherente` distincts des états de lecture à venir ; erreurs d'OS jamais recopiées en texte ; 0 % conservé après amorçage valide ; isolation sans état partagé entre fenêtres ni après erreur.
- Choix documentés dans le module, à retenir pour 1.2/2.1 : `intervalle_s` factuel conservé à côté d'un motif (la validation 2.x doit accepter `motif != null` avec intervalle non nul) ; exception d'horloge → `lecture_impossible` ; mémoire partielle conservée champ par champ valide (le motif porte sur l'instantané) ; `releve_le` en ISO UTC réel. Limite documentée : un `cpu_percent` d'une autre bibliothèque sur le même thread réinitialiserait le compteur, sans garantie de détection. À ajuster en 1.2 : la docstring de `engines/runner.py` prétend encore que psutil n'est importé « sous Windows seulement ».
- Validation : `tests.test_mesures_systeme` 21 OK ; suite complète **1154 tests OK** (avant 1133), aucun test existant modifié ; `git diff --check` propre. Sonde de fonctionnement réelle : deux appels non bloquants même thread autour de 0,15 s + `relever_memoire()` réel, assertions souples (pas de seuil de performance). **Contrôle navigateur non applicable** (module Python sans surface observable). Preuve limitée au test unitaire Linux du serveur ; ni runner réel ni Windows (volets 4.x non exécutés, non PC de test).

## Workflow follow-up

- Aucun téléchargement, job moteur, nouvelle dépendance ou changement de service n'est autorisé par la seule rédaction de ce plan.
- Garder les volets non exécutés ouverts ; archiver seulement sur demande avec preuves et limites explicites, sans migration des fichiers de résultats.
