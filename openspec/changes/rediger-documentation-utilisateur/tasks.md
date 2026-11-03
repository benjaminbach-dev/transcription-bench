## 1. Cadrage

- [ ] 1.1 Faire valider par le propriétaire le public visé (hypothèse : à l'aise avec un ordinateur, sans programmation, prêt à copier-coller des commandes) et le choix de l'exemple principal (design D5)
- [ ] 1.2 Inventorier le README actuel section par section et établir le tableau de correspondance (reste, déplacé, réécrit dans le guide, obsolète)
- [ ] 1.3 Relever dans l'interface les libellés, pages et messages réels sur lesquels s'appuieront le guide et le dépannage (idéalement après `habiller-interface-sumi`, pour la navigation définitive)

## 2. Rédaction

- [ ] 2.1 Écrire `docs/guide-utilisateur.md` : avertissements, ce qu'il faut avoir, parcours pas à pas en trois parties, exemple concret, tableau des modèles vérifiés
- [ ] 2.2 Écrire le glossaire et la section de dépannage à partir de messages réellement produits
- [ ] 2.3 Déplacer le contenu technique dans `docs/technique.md` et corriger ce qui est périmé (dont la mention des durées natives, qui ne couvre plus Qwen3-ASR)
- [ ] 2.4 Réduire `README.md` (moins de soixante lignes) avec liens vers le guide et la documentation technique
- [ ] 2.5 Renseigner pour chaque procédure son niveau de vérification (Linux daté, CI Windows, non vérifié)

## 3. Contrôles automatiques

- [ ] 3.1 Test de cohérence : libellés entre « » présents dans l'interface, liens relatifs valides, liste d'interdits hors glossaire
- [ ] 3.2 Vérifier que le test échoue bien sur un libellé volontairement faux, un lien cassé et un terme interdit (puis annuler)

## 4. Validation en conditions réelles

- [ ] 4.1 Annoncer et faire accepter explicitement le lot de validation (moteur à installer, modèle et fichier, volumes, copie vierge du dépôt et dossier de données neuf) avant toute installation ou téléchargement
- [ ] 4.2 Suivre le guide à froid sous Linux jusqu'à une première transcription lue et une comparaison ; consigner et corriger chaque écart
- [ ] 4.3 Faire relire le guide par le propriétaire, idéalement par une personne qui ne connaît pas le projet, et intégrer les retours
- [ ] 4.4 Vérifier les commandes Windows dans la mesure où la CI le permet ; consigner honnêtement ce qui reste non vérifié

## 5. Clôture

- [ ] 5.1 Suite de tests complète et `openspec validate rediger-documentation-utilisateur --strict`
- [ ] 5.2 Consigner en mémoire projet les décisions (public, structure, exemple), les écarts du parcours à froid et les limites ; mettre à jour `AGENTS.md` si la structure de la documentation y est citée
