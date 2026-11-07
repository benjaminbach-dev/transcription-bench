# Proposal

## Why

Les résultats restent présentés comme des fiches techniques : il est difficile de lire deux transcriptions et de voir immédiatement leur durée et leur empreinte sur l'ordinateur. L'habillage Sumi améliore la forme, mais ne résout pas la priorité des informations ni les textes répétitifs.

## What Changes

- Comparaison centrée sur les textes et trois indicateurs visibles : temps de transcription, mémoire max du moteur rapportée à la RAM totale, CPU moyen du moteur rapporté aux processeurs logiques de la machine consignée.
- Classement par audio, au choix : temps, RAM, occupation CPU ou date d'essai ; tous les essais restent accessibles, sans sélection silencieuse d'un représentant.
- Détails progressifs : différences utiles d'abord, ensemble des mesures et métadonnées ensuite ; explications regroupées dans une aide locale.
- Conservation des alertes et des résultats historiques, avec contexte de mesure visible et sans score global de qualité ou d'efficacité.
- Aucun changement de mesure ici : les ratios utilisent les valeurs brutes existantes. La nouvelle observation globale est portée séparément par `mesurer-charge-systeme`.

## Capabilities

### New Capabilities

Aucune.

### Modified Capabilities

- `results-comparison` : lecture comparative, classement par audio, ratios et formats compréhensibles, aide et divulgation progressive.

## Impact

Couche de consultation, routes GET de résultats, gabarits et macros de formatage, tests de consultation/comparaison/habillage, alignement ultérieur du guide. Aucun moteur ni nouvelle dépendance ; aucune modification des fichiers de résultats. Le menu, les routes existantes, Sumi et Flexoki sont conservés. Ce change s'appuie sur l'habillage déjà implémenté sans archiver ni lever les vérifications restantes du change Sumi.
