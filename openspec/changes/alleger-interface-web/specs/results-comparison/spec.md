## MODIFIED Requirements

### Requirement: Liste des exécutions
La page Résultats SHALL présenter en priorité les résultats regroupés par audio, triables à l'intérieur de chaque groupe. La page Historique conserve tous les essais, des plus récents aux plus anciens, avec date, modèle, moteur, état, audios traités et durée totale. Aucun échec ni résultat sans empreinte valide ne disparaît de cet historique.

#### Scenario: Consultation de l'historique
- **WHEN** l'utilisateur ouvre Résultats
- **THEN** il voit d'abord les résultats par audio et un accès à Historique, qui conserve toutes les exécutions enregistrées, y compris en échec, interrompues, sans transcription ou sans empreinte exploitable, sans que leurs identifiants techniques dominent la liste principale

### Requirement: Détails progressifs et explications regroupées
Les vues SHALL mettre les informations demandées avant la provenance technique. Date courte et variante utile restent secondaires, sans ajouter de longues colonnes d'identifiants ou de réglages. Aide générale, différences et métadonnées complètes restent accessibles sans répétition systématique entre en-tête, corps et pied d'un même résultat.

#### Scenario: Lecture sans détails techniques
- **WHEN** l'utilisateur ouvre un résultat ou une comparaison sélectionnée
- **THEN** il voit modèle, durée audio, RAM, CPU, moteur, temps de transcription et texte, sans chemins, SHA-256, versions, PID, réglages complets ou paragraphes méthodologiques avant le texte

#### Scenario: Accès aux résultats et à tout l'historique
- **WHEN** l'utilisateur ouvre Résultats
- **THEN** les chiffres et contrôles de classement sont au premier plan ; un lien vers Historique et l'aide locale restent accessibles au second plan
