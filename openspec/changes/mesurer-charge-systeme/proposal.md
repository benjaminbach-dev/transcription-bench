# Proposal

## Why

L'empreinte du moteur ne dit pas combien l'ordinateur était occupé au total ni quelle RAM restait disponible. Ces observations demandent de nouveaux relevés et une évolution additive des résultats : elles méritent un petit change séparé de la refonte de lecture.

## What Changes

- Relevé CPU système moyen pendant la transcription de chaque audio, distinct du CPU du moteur : les autres programmes sont inclus.
- Instantané de RAM disponible après le chargement du modèle puis après chaque audio ; ce n'est ni un minimum pendant l'audio, ni une prédiction de fluidité.
- Mesures facultatives, méthode et périmètre explicites, ajoutées aux événements et JSON existants sans modifier les anciens résultats.
- Deux relevés aux frontières de l'inférence, sans thread d'observation, collecte périodique ni privilège supplémentaire ; échec de mesure sans échec de transcription.
- Présentation locale concise du contexte système, en complément des trois indicateurs moteur définis dans `simplifier-lecture-resultats` ; jamais de classement de modèles par charge système.

## Capabilities

### New Capabilities

Aucune.

### Modified Capabilities

- `benchmark-runs` : autoriser et définir les pourcentages avec leur méthode, enregistrer le CPU système par audio et les instantanés de RAM disponible, préserver la compatibilité.
- `results-comparison` : distinguer empreinte du moteur, occupation de l'ordinateur et instantanés de marge mémoire.

## Impact

`engines/runner.py`, protocole des événements facultatifs, consignation/consultation, tests runner/résultats et rapports CI nettoyés. psutil 7.2.2 est déjà verrouillé dans les environnements ; aucune dépendance supplémentaire. Pas de somme de RSS des processus, de déduction d'attribution depuis une variation système, de suivi en direct, d'énergie, de swap ou de garantie de confort. La rédaction n'autorise aucune inférence ni nouvelle exécution de job moteur ; leur validation reste à réaliser dans les contextes autorisés.
