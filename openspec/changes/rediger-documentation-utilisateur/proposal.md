# Proposal

## Why

Le README actuel (350 lignes) mélange le mode d'emploi, l'état des validations, les choix techniques, la sécurité, la CI et les limites : il est écrit pour des développeurs et des agents, pas pour la personne qui veut simplement transcrire des audios et comparer des modèles. Le propriétaire le juge « imbouffable ». Il n'existe aucun guide pas à pas, aucune explication du vocabulaire (moteur, modèle, empreinte, threads…), aucun dépannage en langage courant.

## What Changes

- Un **guide utilisateur** en français courant, pour une personne à l'aise avec un ordinateur mais sans connaissance en programmation : installer, lancer, déposer un audio, installer un moteur, ajouter un modèle, lancer une transcription, lire et comparer les résultats, arrêter. Chaque étape dit quoi faire, ce qu'on doit voir, et quoi faire sinon.
- Un **glossaire** et un **dépannage** (symptôme → cause probable → action).
- Un **README court** : à quoi sert l'outil, avertissement non clinique, liens vers le guide et vers la documentation technique.
- La matière technique actuelle du README est **déplacée, pas supprimée**, vers une documentation technique (`docs/technique.md`), corrigée au passage de ce qui est périmé.
- Des **contrôles automatiques légers** : les libellés d'interface cités dans le guide (en gras) existent vraiment, les liens relatifs résolvent, les termes techniques interdits n'apparaissent pas hors glossaire.
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
- Coordination : le guide décrit l'interface ; `habiller-interface-sumi` est un **préalable dur** (navigation et libellés définitifs, navigateurs minimaux supportés). Le guide est écrit après son implémentation.
- Autres fichiers : `docs/rapport-livraison.md` cite « README.md à jour » comme preuve de la documentation de lancement (exigence `platform-verification`) ; ce renvoi est mis à jour vers le guide.
- Consentement : la validation sur copie vierge implique installer un moteur, télécharger un modèle et lancer une inférence réelle. `AGENTS.md` les réserve à un **PC de test déclaré explicitement** dans la session : jamais sur le serveur de développement. Le lot (moteur, modèle, volume, audio synthétique) est annoncé et accepté avant exécution.
