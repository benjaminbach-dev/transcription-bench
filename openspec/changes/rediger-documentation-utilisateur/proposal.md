# Proposal

## Why

Le README actuel (350 lignes) mélange le mode d'emploi, l'état des validations, les choix techniques, la sécurité, la CI et les limites : il est écrit pour des développeurs et des agents, pas pour la personne qui veut simplement transcrire des audios et comparer des modèles. Le propriétaire le juge « imbouffable ». Il n'existe aucun guide pas à pas, aucune explication du vocabulaire (moteur, modèle, empreinte, threads…), aucun dépannage en langage courant.

## What Changes

- Un **guide utilisateur** en français courant, pour une personne à l'aise avec un ordinateur mais sans connaissance en programmation : installer, lancer, déposer un audio, installer un moteur, ajouter un modèle, lancer une transcription, lire et comparer les résultats, arrêter. Chaque étape dit quoi faire, ce qu'on doit voir, et quoi faire sinon.
- Un **glossaire** et un **dépannage** (symptôme → cause probable → action).
- Un **README court** : à quoi sert l'outil, avertissement non clinique, liens vers le guide et vers la documentation technique.
- La matière technique actuelle du README est **déplacée, pas supprimée**, vers une documentation technique (`docs/technique.md`), corrigée au passage de ce qui est périmé.
- Des **contrôles automatiques légers** : les libellés d'interface cités dans le guide existent vraiment, les liens relatifs résolvent, les termes techniques interdits n'apparaissent pas hors glossaire.
- Une **validation en conditions réelles** : le guide est suivi pas à pas, sans connaissance du projet, sur une copie vierge ; ce qui n'a pas été vérifié (notamment Windows) est annoncé comme tel.

Hors périmètre : modifier l'interface (textes, vocabulaire des pages, fenêtres d'aide) ou le code, produire des scripts de lancement à double-clic, des captures d'écran, des vidéos, une traduction, une documentation destinée aux développeurs au-delà du déplacement ci-dessus. Ces points sont listés comme questions ouvertes dans le design.

## Capabilities

### New Capabilities

- `user-documentation` : contenu, organisation, langage, exactitude et vérification de la documentation destinée aux utilisateurs non techniques.

### Modified Capabilities

Aucune.

## Impact

- Fichiers : `README.md` (réduit), nouveau `docs/guide-utilisateur.md`, `docs/technique.md` (contenu repris du README), éventuellement `docs/glossaire.md` si le glossaire n'est pas dans le guide.
- Tests : un test de cohérence documentation/interface (libellés, liens, termes interdits) ; aucune modification de code applicatif.
- Coordination : le guide décrit l'interface ; il est préférable de l'écrire après `habiller-interface-sumi` (navigation et libellés définitifs, navigateurs minimaux supportés).
- Consentement : la validation sur copie vierge implique installer un moteur et télécharger au moins un modèle sur le PC de test ; le lot (moteur, modèle, volume) devra être annoncé et accepté explicitement avant exécution.
