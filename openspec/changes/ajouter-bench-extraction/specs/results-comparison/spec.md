## MODIFIED Requirements

### Requirement: Liste des exécutions
La page Résultats SHALL présenter en priorité les résultats de transcription regroupés par audio, triables à l'intérieur de chaque groupe. La page Historique conserve toutes les exécutions de transcription et d'extraction, des plus récentes aux plus anciennes, avec type, date, modèle, moteur, état, entrées traitées et durée totale. Aucun échec ni résultat sans empreinte valide ne disparaît de cet historique.

#### Scenario: Accès depuis Résultats
- **WHEN** l'utilisateur ouvre Résultats
- **THEN** il voit d'abord les résultats de transcription par audio et un accès à Historique, sans que les identifiants techniques dominent la liste principale ; chaque détail de transcription reste accessible

#### Scenario: Consultation de l'historique
- **WHEN** l'utilisateur ouvre Historique ou exécute `results history`
- **THEN** il voit toutes les exécutions enregistrées des deux types, distinguées par leur type, y compris en échec, interrompues, abandonnées ou sans résultat exploitable, chacune menant à son détail
