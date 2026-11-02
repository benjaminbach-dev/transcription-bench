# Proposition d'instructions pour le contexte CI

**À relire avant application dans `AGENTS.md`**, conformément à la tâche 10.9.
Ce document n'ajoute aucune autorisation à lui seul. Aucun job GitHub n'a été
exécuté et les instructions actuelles du dépôt restent inchangées.

## Remplacement proposé dans « Spécifications et développement »

Remplacer « Respecter le jalon préalable de validation sur PC prévu dans les
tâches » par :

> Respecter les préalables du change actif : qualification Linux sur le PC de
> test ; vérifications Windows sur les runners CI explicitement autorisés.
> Les preuves CI ne qualifient pas le PC utilisateur et ne constituent pas des
> mesures représentatives de ses performances.

## Nouvelle section proposée après « PC de test Linux ou Windows »

### Intégration continue GitHub Actions

Ce contexte exige une autorisation explicite de l'utilisateur et l'application
des instructions relues. Il ne se déduit pas de la seule présence d'un workflow.
Pour la livraison décidée, l'exécution publique reste conditionnée à la levée de
l'audit et à l'accord final de publication ; aucun service externe n'est activé
par une modification locale de fichier.

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

## Précision proposée dans « Données et secrets »

Conserver l'interdiction d'envoyer des audios ou transcriptions à un service
externe. Ajouter :

> Les essais CI autorisés utilisent exclusivement de la parole synthétique créée
> sur le runner, sans import d'audio utilisateur et sans publication de l'audio
> ou de sa transcription. Cette exception ne vaut pas autorisation d'exporter des
> données locales existantes.

## Après approbation

Appliquer le texte ciblé dans `AGENTS.md`, demander `/reload`, puis vérifier les
instructions dans la session rechargée avant d'exécuter le contexte CI. Aucun
commit, push ou changement de visibilité n'est implicite.
