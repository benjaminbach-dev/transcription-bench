# Tasks

## 1. Mesures aux frontières du runner

- [ ] 1.1 Ajouter un helper injectable de relevés système utilisant psutil existant sur le même thread ; tester amorçage ignoré, second appel non bloquant, séquence de deux audios isolée, intervalle < 0,1 s sans attente, zéro retourné après amorçage sans promesse de diagnostic des compteurs, exceptions et valeurs non finies/hors bornes ; documenter méthode versionnée et limites dans le module.
- [ ] 1.2 Intégrer le CPU système autour des bornes de transcription et les instantanés RAM après chargement/après audio ; vérifier par horloge/compteurs injectés le périmètre sans décodage/chargement CPU, les instants RAM et des observations simulées déterministes avec le moteur factice, sans relevés réels mélangés.

## 2. Événements et stockage compatibles

- [ ] 2.1 Transmettre les objets facultatifs sur les événements existants sans nouveau type et persister aux emplacements D3 ; tester version/provenance/unités/motifs, invalidité ou provenance contradictoire du seul objet système ignoré sans persistance et sans perte de transcription, codes stockés distincts des états de lecture, et aucune modification de `machine` ou du schéma global 1.
- [ ] 2.2 Étendre la consultation et les vues typées ; tester anciens fichiers sans nouvelles clés, objets inconnus/mal formés, absence explicite, relecture sans réécriture et lecture des mesures après suppression d'un modèle local ; documenter le contrat additif.
- [ ] 2.3 Couvrir interruption, échec audio et clôture d'abandon avec conservation du premier audio et de ses relevés, absence du relevé final manquant du second et immutabilité des fichiers finalisés ; vérifier qu'aucun relevé de l'ordinateur courant n'est substitué.

## 3. Lecture du contexte ordinateur

- [ ] 3.1 Ajouter la ligne visible CPU total moyen / RAM disponible après audio, sans classement sur ces valeurs, et le relevé après chargement en détail ; tester libellés/valeurs et absence des faux calculs total-RSS ou CPU système moins moteur.
- [ ] 3.2 Aligner l'aide et le guide sur instantanés, autres programmes, ressources visibles et absence de garantie de fluidité ; adapter leurs tests de cohérence et vérifier que les indicateurs moteur du change UI restent distincts du contexte système.

## 4. Vérification intégrée et preuves

- [ ] 4.1 Exécuter les tests ciblés runner/protocole/consignation/consultation/web/CI et une sonde de fonctionnement psutil par deux appels sur le même thread autour d'un court intervalle dans les tests unitaires Linux/Windows, sans charge lourde, installation ni réseau ; consigner les plateformes réellement exécutées, sans seuil de performance.
- [ ] 4.2 Étendre si nécessaire la liste blanche des rapports JSON CI nettoyés pour les agrégats/méthodes/provenances, et tester qu'aucun audio, transcription, chemin sensible ou nouvel artefact/cache n'est exporté.
- [ ] 4.3 Sur PC Linux explicitement déclaré, après annonce du lot et dans les environnements/modèles autorisés, vérifier les nouveaux champs du runner réel, leur cohérence de périmètre et l'arrêt ; consigner machine, versions, configuration et limites. Ne pas exécuter ce volet sur serveur de développement.
- [ ] 4.4 Vérifier le runner réel dans le job Windows moteur prévu uniquement après autorisation de son exécution ; consigner commit/image/versions et champs nettoyés, sans assimiler CI au PC utilisateur ni lancer de modèle supplémentaire.
- [ ] 4.5 Observer la ligne de contexte avec navigator sur les cartes finales bureau/mobile et clair/sombre ; revérifier les critères de lecture à 1280 × 800 sans alerte avec la nouvelle ligne, puis vérifier visibilité, absence de confusion moteur/système et absence de débordement, puis valider OpenSpec strict et les espaces du diff.

## Workflow follow-up

- Aucun téléchargement, job moteur, nouvelle dépendance ou changement de service n'est autorisé par la seule rédaction de ce plan.
- Garder les volets non exécutés ouverts ; archiver seulement sur demande avec preuves et limites explicites, sans migration des fichiers de résultats.
