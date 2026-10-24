# transcription-bench

## Objectif et périmètre
Prototype local de comparaison de modèles de transcription française sur CPU,
sous Linux x64 et Windows x64. Ce n'est pas un produit clinique validé.
Répondre et documenter en français. Distinguer mesures locales, faits documentaires
et hypothèses ; ne jamais présenter une transcription fluide comme médicalement correcte.

## Sources de contexte
- Mémoire projet Basic Memory : `transcription-bench`, dossier versionné `.basic-memory/`.
- Lire d'abord `projet/decisions-du-prototype-de-benchmark`, puis les notes pertinentes.
  Les explorations anciennes ne remplacent pas les décisions ultérieures.
- Vérifier via le MCP que le projet pointe vers `.basic-memory/` de ce clone.
  Signaler un accès absent ou ambigu ; ne pas contourner le MCP en lisant les fichiers.
  La configuration de mémoire sur un autre poste ne voyage pas avec Git.
- Seul l'agent principal écrit dans la mémoire. Y consigner décisions, limites et
  validations avec leur provenance, sans recopier les specs ni les conversations.
- Les exigences vivent dans OpenSpec ; la mémoire explique le contexte des décisions.

## Spécifications et développement
- Consulter `openspec list` pour identifier les changements actifs ; lire les specs,
  le design et les tâches concernés avant de modifier le code.
- Vérifier la faisabilité des choix techniques avant de les spécifier. Une recherche
  documentaire ne vaut pas validation réelle ; signaler les hypothèses restantes.
  Respecter le jalon préalable de validation sur PC prévu dans les tâches.
- Ne pas élargir le périmètre sans accord explicite. Garder le code simple et les
  tests ciblés sur les risques réels.
- uv et Python 3.12 géré par uv ; ne pas modifier le Python système.
- Environnement du serveur séparé de ceux des moteurs ; aucune bibliothèque de
  moteur importée dans le serveur. CPU uniquement, sans GPU ni Vulkan.
- HTML sans CSS ni JavaScript ; une seule opération longue, sans file d'attente.
- Installations et téléchargements explicites ; inférences exclusivement locales
  et hors ligne, sans exécution de code distant.

## Identifier le contexte de travail
Ne jamais déduire le rôle de la machine de son OS, hostname ou chemin.
Sans contexte confirmé, appliquer les restrictions du serveur de développement.
Demander confirmation avant toute opération réservée à un PC de test.
Ces consignes sont des garde-fous pour les agents, pas une isolation technique.

### Serveur de développement
Autorisé : code, documentation, interface, tests unitaires et moteur factice ;
audios synthétiques créés localement pour les tests. La consultation explicite de
métadonnées publiques de modèles (listes de fichiers, petits JSON, sans poids) est
permise pour documenter la faisabilité ; les tests restent sans réseau.
Interdit : installation de moteurs réels, téléchargement de poids, inférence réelle
et mesures présentées comme représentatives des PC utilisateurs.
L'installation de nouveaux outils ou dépendances de développement nécessite un
accord explicite ; ne pas modifier les environnements des services partagés.

### PC de test Linux ou Windows
Ce contexte doit être déclaré explicitement par l'utilisateur dans la session.
Installations, téléchargements et inférences réelles sont possibles uniquement
pour le périmètre autorisé : annoncer moteurs, modèles, opérations et volumes connus.
Un accord peut couvrir un lot précis ; ne pas demander à nouveau pour chaque
commande de ce lot, mais demander avant de l'élargir.
Consigner OS, machine, version du programme, dépendances et configuration de chaque
validation. Une validation Linux ne vaut pas validation Windows, ni inversement.
Vérifier le shell disponible : ne pas supposer bash ou des outils Linux sous Windows.
Utiliser des chemins portables dans le code.

## Données et secrets
- Audios, poids, environnements et résultats restent sous `data/`, hors Git.
- Aucun audio ni transcription envoyé à un service externe, y compris pour les tests.
- Utiliser des données synthétiques en développement ; ne pas ajouter de données
  personnelles dans la mémoire ou la documentation.
- Ne jamais lire ni afficher de clés privées. Ne jamais afficher, journaliser ou
  enregistrer de jeton ; l'application utilise les mécanismes standards de son client.
- Examiner licences et conditions d'accès avant toute redistribution ou intégration.

## Git
Aucun commit ni push sans demande explicite. Avant : vérifier identité, remote,
branche et fichiers concernés. Préserver les modifications préexistantes ;
ne publier que les fichiers de la tâche.
