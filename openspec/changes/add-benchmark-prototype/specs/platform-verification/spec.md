# Spec Delta

## Purpose

Définit comment les exigences sous Windows sont vérifiées sans poste Windows, quels niveaux de preuve en résultent, quelles garanties les jobs d'intégration continue doivent offrir, et à quelles conditions le dépôt peut être publié pour les exécuter.

## ADDED Requirements

### Requirement: Niveaux de preuve distincts
Chaque preuve MUST être rattachée à un seul niveau : documentaire (recherche non exécutée), tests sur le serveur de développement avec le moteur factice, qualification Linux sur PC de test, vérifications réelles en intégration continue Windows, qualification sur le PC de l'utilisateur. Une preuve documentaire MUST NOT être présentée comme une exécution.

#### Scenario: Absence de preuve Windows
- **WHEN** aucune exécution Windows n'a eu lieu pour un commit
- **THEN** aucune exigence Windows n'est présentée comme vérifiée et aucune tâche Windows n'est cochée

### Requirement: Aucun transfert entre niveaux de preuve
Une preuve d'un niveau MUST NOT être présentée comme valant un autre niveau. En particulier, une exécution réussie en CI MUST NOT être annoncée comme qualification Windows sur PC ni comme mesure représentative des performances d'un PC utilisateur.

#### Scenario: Rapport après une CI verte
- **WHEN** les jobs Windows réussissent pour un commit
- **THEN** le rapport indique le niveau « CI Windows » et n'en conclut ni une qualification du PC de l'utilisateur, ni une performance attendue sur un PC

### Requirement: Qualification Linux consignée et bornée à Linux
La qualification du jalon 0 sous Linux SHALL être consignée avec l'OS, la machine, les versions, les modèles d'essai et la configuration employée. La sonde du cycle de vie du serveur sous Linux SHALL être consignée avec ses limites : Ctrl+C obtenu par un PTY automatisé et non par une console humaine avec frappe clavier, et absence de validation Windows. Cette qualification MUST NOT être étendue à Windows, ni aux performances d'un PC moins doté.

#### Scenario: Relecture de la qualification Linux
- **WHEN** une preuve du jalon 0 Linux est relue
- **THEN** ses conditions sont identifiables et leur portée est explicitement limitée à Linux sur la machine consignée

### Requirement: Runners Windows versionnés en CI
Les vérifications Windows MUST s'exécuter sur des runners hébergés GitHub Actions Windows x64, avec une image explicitement versionnée par son libellé.

#### Scenario: Image du runner
- **WHEN** un job Windows démarre
- **THEN** son image est identifiée par un libellé versionné et consignée, jamais par un tag mobile

### Requirement: Couverture des vérifications Windows CI
Les vérifications MUST couvrir la suite de tests avec le moteur factice ; l'installation de chacun des trois moteurs réels depuis ses verrous avec `uv pip sync --no-build`, puis l'exercice du runner du projet et de l'adaptateur, un simple import de bibliothèque ne suffisant pas ; enfin une inférence courte pour chaque combinaison retenue.

#### Scenario: Couverture complète
- **WHEN** les vérifications Windows sont exécutées
- **THEN** les quatre combinaisons (faster-whisper, transcribe.cpp avec un GGUF Whisper, Transformers Whisper, Transformers Parakeet TDT) sont couvertes par une inférence courte

#### Scenario: Échec d'installation ou d'inférence
- **WHEN** une roue, un import ou une inférence échoue sous Windows
- **THEN** le job échoue sans `continue-on-error` ni saut conditionnel, l'écart est consigné et remonte à l'utilisateur pour décision

### Requirement: Audio de test créé localement par le job
L'audio des tests d'inférence MUST être de la parole synthétique produite localement par le job, sans présumer la disponibilité d'une API système de synthèse ni ajouter de dépendance sans décision explicite. Le workflow MUST NOT utiliser d'audio personnel ni provenant d'un poste utilisateur.

#### Scenario: Audio du job
- **WHEN** un job d'inférence démarre
- **THEN** son audio de test est créé dans le job par une voie locale, sans import d'audio utilisateur

### Requirement: Absence de voix locale remontée sans affaiblir
À défaut de voie locale de synthèse, l'écart MUST remonter pour arbitrage explicite et MUST NOT être remplacé par du bruit ni par un critère affaibli en silence.

#### Scenario: Voix locale non disponible
- **WHEN** aucune voix système locale ne peut produire de la parole sur le runner
- **THEN** l'écart est remonté pour arbitrage, sans remplacement par du bruit ni affaiblissement du critère

### Requirement: Voix locale de n'importe quelle langue
Aucune voix française n'est requise : une voix système locale activée MUST pouvoir être utilisée quelle que soit sa langue, sans changer les réglages fonctionnels du moteur pour le test. La culture de la voix, la langue du texte de synthèse et la langue réellement imposée par le moteur MUST être consignées séparément et l'empreinte audio MUST être vérifiée.

#### Scenario: Voix d'une autre langue
- **WHEN** la seule voix locale disponible n'est pas française
- **THEN** elle est utilisée pour le test technique et sa culture est consignée séparément de la langue imposée par le moteur

### Requirement: Contrôle technique des inférences CI
Chaque combinaison MUST produire une transcription non vide comme contrôle de fonctionnement, sans mot attendu, comparaison linguistique ni évaluation de qualité du modèle. Les métadonnées MUST consigner le périphérique CPU, les threads et les versions. Une sortie vide MUST être signalée comme contrôle non concluant, sans diagnostic sur la qualité du modèle. Les modèles utilisés MUST être ceux déjà retenus pour les essais : la CI n'ajoute ni modèle ni famille.

#### Scenario: Job d'inférence réussi
- **WHEN** un job d'inférence Windows se termine avec succès
- **THEN** une transcription non vide est produite pour la combinaison visée et les métadonnées CPU, threads et versions sont consignées

#### Scenario: Sortie vide
- **WHEN** une inférence produit une transcription vide
- **THEN** le contrôle est signalé non concluant, sans diagnostic sur la qualité du modèle

### Requirement: Preuves consignées par exécution
Chaque exécution MUST laisser des preuves exploitables : commit testé, libellé et version d'image du runner, version de Python et de uv, versions installées des moteurs, nature, procédure et empreinte de l'audio de parole et journaux des jobs. Ces preuves MUST être conservées avec leur niveau et leur date.

#### Scenario: Relecture d'une exécution
- **WHEN** une exécution est relue
- **THEN** commit, image et sa version, versions installées, empreinte de l'audio et journaux sont retrouvés ensemble

### Requirement: Permissions et épinglage du workflow
Le workflow MUST appliquer des permissions minimales au jeton du service, en lecture seule sur le contenu, et MUST épingler chaque action utilisée, y compris les actions officielles `actions/*`, par SHA de commit complet. Il MUST NOT utiliser de secret et le cache de `setup-uv` (ou équivalent) MUST être explicitement désactivé.

#### Scenario: Contrôle du workflow
- **WHEN** le workflow est relu avant activation
- **THEN** permissions en lecture, actions épinglées par SHA, absence de secret et cache désactivé sont présents

#### Scenario: Action référencée par un tag mobile
- **WHEN** une action utilisée, y compris une action officielle `actions/*`, est référencée par un tag mobile plutôt que par un SHA
- **THEN** la configuration est refusée en revue

### Requirement: Aucune donnée sensible en artéfact
Le workflow MUST NOT publier ni mettre en cache par défaut des poids de modèles, des audios, des environnements ou des transcriptions. Il MUST définir un délai maximal par job ainsi qu'une politique de concurrence annulant les exécutions obsolètes.

#### Scenario: Artéfacts d'un run
- **WHEN** un run se termine
- **THEN** aucun artéfact ni cache ne contient de poids, d'audio, d'environnement moteur ni de transcription, et chaque job a respecté son délai maximal

### Requirement: Ressources consignées et non représentatives
Les jobs Windows MUST utiliser les runners standards hébergés, sans runner plus grand ni payant ; les caractéristiques documentaires de ces runners sont consignées, datées, dans le design et ne constituent pas des valeurs normatives. Les ressources réellement attribuées à chaque job MUST être mesurées et consignées. Les mesures CI MUST NOT servir à annoncer une performance sur un PC utilisateur.

#### Scenario: Job Windows exécuté
- **WHEN** un job Windows se termine
- **THEN** les ressources attribuées et mesurées sont consignées, sans extrapolation à un PC utilisateur

### Requirement: Disque et déclenchement des jobs lourds
Les vérifications d'inférence MUST s'exécuter en jobs indépendants, chacun ne téléchargeant que le modèle de sa combinaison et n'en conservant aucun cache, afin de rester dans le disque du runner. Les jobs lourds (installation des moteurs et inférence) MUST être déclenchables manuellement ; un déclenchement automatique MAY se limiter à la suite de tests.

#### Scenario: Déclenchement manuel
- **WHEN** l'utilisateur déclenche manuellement une ou plusieurs combinaisons
- **THEN** seules les combinaisons demandées s'exécutent, chacune dans son job et sous la limite de disque du runner

### Requirement: Configuration hors ligne sans preuve d'isolation
Le fait que les jobs exercent les options hors ligne MUST NOT être présenté comme une preuve d'absence d'accès réseau. Une sonde dédiée à l'isolation réseau MAY être ajoutée à l'intégration continue après revue, sans valoir preuve de coupure système.

#### Scenario: Rapport d'un job hors ligne
- **WHEN** un job configure les options hors ligne et réussit
- **THEN** le rapport distingue la configuration hors ligne d'une isolation réseau prouvée

### Requirement: Ctrl+C console et coupure réseau hors CI
L'arrêt interactif Ctrl+C simple et double dans une vraie console Windows via la commande documentée, ainsi que la coupure réseau réelle du système, MUST NOT être considérés comme couverts par l'intégration continue.

#### Scenario: Job annulé
- **WHEN** un job d'intégration continue est annulé
- **THEN** aucune conclusion n'est tirée sur Ctrl+C ni sur la supervision d'arrêt sous Windows

### Requirement: Limites interactives consignées avec procédure
Les limites des vérifications interactives et la procédure permettant de les lever SHALL être consignées, la tâche correspondante étant close par cette consignation, sans attendre un poste dont la disponibilité n'est pas acquise et sans présenter la sonde Linux par PTY comme une console humaine. L'annulation d'un job MUST NOT être présentée comme un arrêt normal du serveur. Les exigences fonctionnelles Windows restent en vigueur et sont vérifiées en CI pour leur partie testable sans interaction.

#### Scenario: Rapport de livraison
- **WHEN** la livraison est présentée
- **THEN** les limites hors CI sont citées avec leur état non exécuté et la procédure de levée, à côté des preuves CI

### Requirement: Audit préalable de l'historique et des contenus
Le dépôt MUST NOT devenir public avant un audit consigné de sa visibilité, de son historique Git (secrets, jetons, données personnelles, poids, audios, environnements), du contenu de sa mémoire projet et de son historique de notes, et des licences du code et des dépendances.

#### Scenario: Points d'audit
- **WHEN** l'audit est relu
- **THEN** visibilité, historique Git, mémoire projet et licences du code et des dépendances sont couverts et consignés

### Requirement: Licences et accès des modèles téléchargés en CI
Les licences et conditions d'accès des modèles effectivement téléchargés par les jobs CI MUST être contrôlées de façon ciblée, sans attribution globale imposée.

#### Scenario: Modèle téléchargé par un job
- **WHEN** un job CI télécharge un modèle
- **THEN** sa licence et ses conditions d'accès ont été contrôlées pour ce modèle précis

### Requirement: Verdict d'audit défavorable bloque la publication
Un audit dont le verdict est défavorable MUST bloquer la publication tant que ses points ne sont pas levés.

#### Scenario: Audit incomplet
- **WHEN** un point d'audit reste non résolu, par exemple un secret dans l'historique ou une licence incompatible
- **THEN** le dépôt reste privé et les jobs Windows ne sont pas exécutés sur un runner public

### Requirement: Gate de publication explicite
Le régime de licence du projet MUST être choisi explicitement par l'utilisateur avant publication, un régime propriétaire sans licence ouverte restant possible. La publication MUST être une décision explicite de l'utilisateur postérieure aux décisions d'audit ; tout point non résolu MUST bloquer la publication et l'exécution des jobs Windows sur runner public. Une réécriture d'historique ou une rotation MUST relever d'un accord explicite distinct.

#### Scenario: Audit complet et décision explicite
- **WHEN** l'audit est complet, ses points sont levés et l'utilisateur décide explicitement la publication
- **THEN** le dépôt peut devenir public et les jobs Windows peuvent être exécutés sur le runner standard

### Requirement: Preuves exigées pour la livraison
La livraison du prototype pour Linux et Windows MUST être constatée par des preuves : suite de tests passée sous Linux et sous Windows CI ; installation depuis les verrous et exercice du runner et des adaptateurs réussis sous Windows CI ; inférence courte réussie des quatre combinaisons sous Windows CI sur un audio de parole synthétique ; adaptateurs réels vérifiés sous Linux ; preuves CI consignées ; documentation de lancement à jour.

#### Scenario: Rapport de livraison complet
- **WHEN** la livraison est déclarée
- **THEN** chaque critère est accompagné de sa preuve et de son niveau, et les limites restantes sont explicites

### Requirement: Limites assumées consignées avec leur procédure
Les limites assumées MUST être consignées avec leur procédure : console Windows non éprouvée, coupure réseau réelle, performances non garanties, PC Windows non qualifié. L'absence de PC Windows MUST NOT être en soi un motif d'échec de livraison dès lors que les vérifications sont exécutées et consignées.

#### Scenario: Livraison sans PC Windows
- **WHEN** toutes les vérifications CI sont exécutées et consignées sans PC Windows disponible
- **THEN** la livraison reste possible avec ces limites explicites, sans les présenter comme couvertes

### Requirement: Livraison partielle jamais présentée comme complète
Un critère Windows non couvert MUST laisser l'état bloqué ou partiel et une révision du périmètre MUST relever d'une décision explicite de l'utilisateur. Une livraison partielle MUST NOT être présentée comme complète et aucune clôture automatique n'a lieu.

#### Scenario: Combinaison en échec sous Windows
- **WHEN** une combinaison échoue durablement sous Windows, ou que la CI s'avère impossible
- **THEN** l'état est consigné comme bloqué ou partiel, la décision de réviser le périmètre est soumise à l'utilisateur, aucune exigence Windows n'est cochée et aucun archivage automatique n'a lieu
