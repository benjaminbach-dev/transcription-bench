# transcription-bench

## Objectif et périmètre
Prototype local de comparaison de modèles de transcription française sur CPU,
sous Linux x64 et Windows x64. Ce n'est pas un produit clinique validé.
Répondre et documenter en français. Distinguer mesures locales, faits documentaires
et hypothèses ; ne jamais présenter une transcription fluide comme médicalement correcte.

## Sources de contexte
- Mémoire projet Basic Memory : `transcription-bench`, dossier versionné `.basic-memory/`,
  enregistrée sous ce même nom sur chaque hôte. Y accéder via le serveur MCP global
  `basic-memory` en passant toujours `project: transcription-bench` ; la mémoire
  globale `main` reste réservée au savoir transversal.
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
  Respecter les préalables du change actif : qualification Linux sur le PC de
  test ; vérifications Windows sur les runners CI explicitement autorisés.
  Les preuves CI ne qualifient pas le PC utilisateur et ne constituent pas des
  mesures représentatives de ses performances.
- Ne pas élargir le périmètre sans accord explicite. Garder le code simple et les
  tests ciblés sur les risques réels.
- uv et Python 3.12 géré par uv ; ne pas modifier le Python système.
- Environnement du serveur séparé de ceux des moteurs ; aucune bibliothèque de
  moteur importée dans le serveur. CPU uniquement, sans GPU ni Vulkan.
- HTML sans JavaScript, avec feuilles de style locales (Sumi.css et `app.css`, jamais de CDN) ;
  une seule opération longue, sans file d'attente.
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

### Intégration continue GitHub Actions

Ce contexte exige une autorisation explicite de l'utilisateur et l'application
des instructions relues. Il ne se déduit pas de la seule présence d'un workflow.
Pour la livraison décidée, l'exécution publique reste conditionnée à la levée
de l'audit et à l'accord final de publication ; aucun service externe n'est
activé par une modification locale de fichier.

- Tests sous Linux et Windows avec moteur factice et données synthétiques
  générées localement dans le job ; aucun accès réseau externe pendant les
  tests, loopback autorisé pour les sondes HTTP.
- Jobs moteurs manuels : installation des trois environnements depuis leurs
  verrous et contrôle d'import ; inférences CPU uniquement des quatre
  combinaisons et révisions arrêtées dans OpenSpec et dans le harnais CI.
- Téléchargements explicites avant l'inférence ; un seul modèle par job ; aucun
  modèle ni famille supplémentaire sans nouvel accord. Respecter les licences
  et conditions d'accès, sans jeton ni contournement d'un dépôt restreint.
- Parole synthétique créée sur le runner avec une voix système locale activée,
  sans exigence de français ; culture de voix et langue du texte consignées
  séparément de la langue imposée par le moteur. Ces tests vérifient le logiciel,
  pas la qualité des modèles. Aucune dépendance nouvelle sans accord ; échec
  explicite uniquement si aucune voix locale n'est disponible.
- Aucun audio personnel, audio provenant d'un poste utilisateur ou transcription
  sensible envoyé au service. Aucun poids, audio, environnement ni transcription
  conservé dans les artefacts/caches. Seuls les rapports JSON nettoyés prévus
  par les workflows et les journaux non sensibles servent de preuves.
- Distinguer configuration hors ligne et isolation réseau prouvée. L'annulation
  d'un job ne vaut pas Ctrl+C interactif. Consigner commit, image, versions et
  ressources ; ne jamais extrapoler les performances au PC utilisateur.
- Ne pas modifier les services d'un hôte, les règles de pare-feu ou la connectivité
  du runner pour vérifier une hypothèse sans accord spécifique.

## Données et secrets
- Audios, poids, environnements et résultats restent sous `data/`, hors Git.
- Aucun audio ni transcription envoyé à un service externe, y compris pour les tests.
  Les essais CI autorisés utilisent exclusivement de la parole synthétique créée
  sur le runner, sans import d'audio utilisateur et sans publication de l'audio
  ou de sa transcription. Cette exception ne vaut pas autorisation d'exporter des
  données locales existantes.
- Utiliser des données synthétiques en développement ; ne pas ajouter de données
  personnelles dans la mémoire ou la documentation.
- Ne jamais lire ni afficher de clés privées. Ne jamais afficher, journaliser ou
  enregistrer de jeton ; l'application utilise les mécanismes standards de son client.
- Examiner licences et conditions d'accès avant toute redistribution ou intégration.

## Git
Aucun commit ni push sans demande explicite. Avant : vérifier identité, remote,
branche et fichiers concernés. Préserver les modifications préexistantes ;
ne publier que les fichiers de la tâche.
