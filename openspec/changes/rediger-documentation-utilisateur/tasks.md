## 1. Cadrage

- [ ] 1.0 Préalable : `habiller-interface-sumi` implémenté (navigation, libellés et navigateurs minimaux définitifs)
- [ ] 1.1 Faire valider par le propriétaire le public visé (hypothèse : à l'aise avec un ordinateur, sans programmation, prêt à copier-coller des commandes) ; l'exemple principal est décidé (design D5 : whisper-large-v3-turbo-gguf, Q5_K_M)
- [x] 1.2 Inventorier le README actuel section par section et établir le tableau de correspondance sans perte (reste, déplacé, réécrit dans le guide, obsolète), joint au change dans `correspondance.md`
- [x] 1.3 Relever dans l'interface les libellés, pages et messages réels (gabarits **et** chaînes Python de `transcription_bench/web`, CLI inclus) sur lesquels s'appuieront le guide et le dépannage

## 2. Rédaction

- [ ] 2.1 Écrire `docs/guide-utilisateur.md` : avertissements, ce qu'il faut avoir, parcours pas à pas en trois parties, exemple concret, comparaison, tableau des modèles vérifiés ; `winget` en alternative pour uv sous Windows, archive ZIP en alternative à Git
- [ ] 2.2 Écrire le glossaire (section « Glossaire »), la liste des accès réseau réels (design D9) et la section de dépannage à partir de messages réellement produits (de l'application, ou du système/navigateur relevés lors d'un essai)
- [x] 2.3 Déplacer le contenu technique dans `docs/technique.md` et corriger ce qui est périmé (dont la mention des durées natives, qui ne couvre plus Qwen3-ASR)
- [x] 2.4 Réduire `README.md` (moins de soixante lignes) avec liens vers le guide et la documentation technique
- [ ] 2.5 Renseigner pour chaque procédure son niveau de vérification (Linux daté, CI Windows, non vérifié)
- [x] 2.6 Mettre à jour `docs/rapport-livraison.md` (la ligne qui cite « README.md à jour » comme preuve de la documentation de lancement) pour renvoyer au guide

## 3. Contrôles automatiques

- [x] 3.1 Test de cohérence (UTF-8 explicite) : textes en gras présents dans les gabarits ou chaînes Python de `transcription_bench/web` ou liste blanche ; liens relatifs valides (fichiers seulement) ; liste d'interdits hors glossaire
- [x] 3.2 Vérifier que le test échoue bien sur un libellé volontairement faux, un lien cassé et un terme interdit (puis annuler)

## 4. Validation en conditions réelles

- [ ] 4.1 **Condition** : un PC de test Linux déclaré explicitement par le propriétaire dans la session. Annoncer et faire accepter le lot (moteur transcribe.cpp, modèle `handy-computer/whisper-large-v3-turbo-gguf` fichier Q5_K_M ≈ 620 Mo, audio synthétique ou non personnel, copie vierge du dépôt, dossier de données neuf) avant toute installation ou téléchargement ; consigner OS, machine, versions, dépendances
- [ ] 4.2 Suivre le guide à froid sur ce PC jusqu'à une première transcription lue et une comparaison (deux exécutions du même modèle sur le même audio : pas de second téléchargement) ; relever les accès réseau réels et les durées mesurées ; consigner et corriger chaque écart
- [ ] 4.3 Relecture : critères de style (vouvoiement, phrases courtes, sigles développés, clarté) par le propriétaire, idéalement aussi par une personne qui ne connaît pas le projet ; intégrer les retours
- [ ] 4.4 Windows : réutiliser les preuves CI existantes, **sans nouveau job** (accord explicite requis) ; consigner honnêtement ce qui reste non vérifié (installeur de uv, lancement en console, Ctrl+C)

## 5. Clôture

- [ ] 5.1 Suite de tests complète et `openspec validate rediger-documentation-utilisateur --strict`
- [ ] 5.2 Consigner en mémoire projet les décisions (public, structure, exemple, gras), les écarts du parcours à froid et les limites ; mettre à jour `AGENTS.md` si la structure de la documentation y est citée
