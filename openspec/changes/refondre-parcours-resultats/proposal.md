# Proposal

## Why

L'application à jour reste trop technique : les listes cachent les chiffres utiles derrière des identifiants, les tris ne montrent pas les mesures classées et le lancement répète un formulaire par modèle. Le retour utilisateur du 2026-11-06 demande une interface centrée sur les résultats et non sur les preuves techniques ; les validations sombres antérieures ne valent pas acceptation de cette ergonomie.

## What Changes

- Résultats et Comparaisons : modèle, durée audio, pic RAM moteur, CPU moyen moteur et moteur lisibles immédiatement ; temps de transcription distinct et visible pour comprendre le classement. Dates et variantes compactes, provenance et réglages complets en détail.
- Résultats devient la page d'entrée utile, avec groupes par audio et tris explicites à l'intérieur de chaque groupe ; l'historique technique complet est déplacé au second plan d'Exécutions.
- **BREAKING UX** : menu dans l'ordre Résultats, Comparaisons, Exécutions, Modèles, Moteurs, Audios ; plus d'accueil distinct ni d'entrée Opération. Les anciennes URL GET restent des redirections locales.
- Une seule page Exécutions pour préparer et suivre l'opération globale (transcription, installation ou téléchargement), avec arrêt uniquement d'une transcription active.
- Formulaire unique avec sélecteurs Modèle, Audio, Moteur compatible, réglages avancés facultatifs ; les lots séquentiels existants restent accessibles au second plan.
- Modèles locaux en premier, ajout par une entrée secondaire ; aucune installation ni aucun téléchargement implicites.
- Hiérarchie visuelle assumée : couleurs sémantiques accessibles, tailles de valeurs et espacements dédiés, pas seulement une nouvelle mise en accordéons du même texte. Une explication donnée n'apparaît qu'une fois par page.
- JavaScript local léger autorisé : choix initial vanilla sans dépendance, en amélioration progressive des formulaires HTML. Ni SPA, ni CDN, ni construction front-end, ni script issu d'un dépôt de modèle.

## Capabilities

### New Capabilities

Aucune.

### Modified Capabilities

- `local-web-interface` : navigation centrée résultats, ressources JS locales et CSS applicative, suivi intégré, accessibilité et hiérarchie visuelle.
- `results-comparison` : listes exploitables à première lecture, classement avec valeurs visibles, détail et comparaison compacts sans perte d'historique.
- `benchmark-runs` : préparation unique par sélecteurs compatibles, réglages avancés et accès aux lots sans formulaires répétés.
- `model-management` : inventaire local prioritaire et ajout secondaire, sans changer les garanties de téléchargement/suppression.

## Impact

Gabarits Jinja, routes Flask, vues de consultation et configuration, `app.css`, nouveau fichier `app.js` local, tests HTML et parcours synthétiques, README et guide. Pas de nouvelle mesure, bibliothèque moteur, dépendance ni changement de stockage des résultats. Les règles de sécurité locale, les actions explicites et le créneau unique restent applicables. Les contraintes contradictoires de Sumi et du premier change de lecture sont remplacées de façon ciblée, selon la matrice du design, sans archivage ni validation implicites. La règle actuelle d'AGENTS interdisant JS devra être révisée puis rechargée avant l'implémentation ; cette proposition ne la modifie pas.
