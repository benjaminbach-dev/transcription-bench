## MODIFIED Requirements

### Requirement: Consultation seule
L'interface web SHALL se limiter à la consultation : Résultats, détail d'un résultat, aide des indicateurs, Comparaisons, Extractions (liste, détail, aide, comparaison) et Historique des exécutions. Elle MUST NOT installer de moteur, vérifier ou télécharger de modèle, supprimer de fichier, lancer ou arrêter d'exécution de transcription ou d'extraction, ni démarrer aucune opération longue. Ces actions relèvent exclusivement des commandes du programme. Le serveur MUST NOT accepter d'autre méthode que GET et HEAD.

#### Scenario: Requête POST
- **WHEN** une requête dont l'en-tête `Host` est local utilise POST, PUT, PATCH, DELETE ou OPTIONS, sur une route existante ou supprimée
- **THEN** elle est refusée avec le statut 405 ou 404, sans lire de corps de formulaire ni déclencher d'action ; une requête dont l'en-tête `Host` est étranger est refusée par le contrôle `Host` quelle que soit sa méthode

#### Scenario: Ancienne page d'action
- **WHEN** l'utilisateur ouvre `/audios`, `/modeles`, `/moteurs`, `/moteurs/<id>/journal`, `/operation` ou `/executions/etat`
- **THEN** l'application répond 404 avec le squelette local et aucune opération n'est démarrée

#### Scenario: Historique
- **WHEN** l'utilisateur ouvre `/executions`
- **THEN** il voit l'historique complet des exécutions de transcription et d'extraction, sans formulaire de préparation, de lancement ou d'arrêt

#### Scenario: Arrêt du serveur
- **WHEN** le serveur reçoit Ctrl+C sous Windows ou Linux, ou SIGTERM sous Linux
- **THEN** il s'arrête et libère le verrou d'instance sans moteur à terminer, aucune opération n'ayant pu être démarrée par l'interface

### Requirement: Navigation commune et page courante
La navigation SHALL présenter exactement Résultats, Comparaisons, Extractions, Historique dans cet ordre. Historique désigne `/executions` ; Extractions désigne `/extractions`. La page courante porte `aria-current="page"`, son parent porte `aria-current="true"` sur une sous-page ; une erreur ne signale aucune rubrique courante.

#### Scenario: Page courante signalée
- **WHEN** la page Extractions est chargée
- **THEN** la navigation contient les quatre liens dans l'ordre prescrit et seul Extractions porte `aria-current="page"`

#### Scenario: Sous-page
- **WHEN** un détail d'extraction ou une comparaison d'extractions est chargé
- **THEN** Extractions porte `aria-current="true"` et aucun lien ne porte `aria-current="page"`

#### Scenario: Page d'erreur
- **WHEN** une page d'erreur est chargée
- **THEN** les quatre rubriques restent accessibles et aucune ne porte `aria-current`
