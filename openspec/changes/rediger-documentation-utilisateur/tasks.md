## 1. Cadrage

- [x] 1.0 Préalable : `habiller-interface-sumi` implémenté (navigation, libellés et navigateurs minimaux définitifs)
- [x] 1.1 Faire valider par le propriétaire le public visé (hypothèse : à l'aise avec un ordinateur, sans programmation, prêt à copier-coller des commandes) ; l'exemple principal est décidé (design D5 : whisper-large-v3-turbo-gguf, Q5_K_M)
- [x] 1.2 Inventorier le README actuel section par section et établir le tableau de correspondance sans perte (reste, déplacé, réécrit dans le guide, obsolète), joint au change dans `correspondance.md`
- [x] 1.3 Relever dans l'interface les libellés, pages et messages réels (gabarits **et** chaînes Python de `transcription_bench/web`, CLI inclus) sur lesquels s'appuieront le guide et le dépannage

## 2. Rédaction

- [x] 2.1 Écrire `docs/guide-utilisateur.md` : avertissements, ce qu'il faut avoir, parcours pas à pas en trois parties, exemple concret, comparaison, tableau des modèles vérifiés ; `winget` en alternative pour uv sous Windows, archive ZIP en alternative à Git
- [x] 2.2 Écrire le glossaire (section « Glossaire »), la liste des accès réseau réels (design D9) et la section de dépannage à partir de messages réellement produits (de l'application, ou du système/navigateur relevés lors d'un essai)
- [x] 2.3 Déplacer le contenu technique dans `docs/technique.md` et corriger ce qui est périmé (dont la mention des durées natives, qui ne couvre plus Qwen3-ASR)
- [x] 2.4 Réduire `README.md` (moins de soixante lignes) avec liens vers le guide et la documentation technique
- [x] 2.5 Renseigner pour chaque procédure son niveau de vérification (Linux daté, CI Windows, non vérifié)
- [x] 2.6 Mettre à jour `docs/rapport-livraison.md` (la ligne qui cite « README.md à jour » comme preuve de la documentation de lancement) pour renvoyer au guide
- [x] 2.7 Renvoi du change `habiller-interface-sumi` (tâche 8.11) : `docs/guide-utilisateur.md` annonce encore un rappel de non-validation clinique sur l'accueil (lignes 5 et 138) alors que le bandeau a été retiré du squelette (lot 5, 2026-11-04) ; corriger au fil de la rédaction, en conservant l'avertissement global du prototype

## 3. Contrôles automatiques

- [x] 3.1 Test de cohérence (UTF-8 explicite) : textes en gras présents dans les gabarits ou chaînes Python de `transcription_bench/web` ou liste blanche ; liens relatifs valides (fichiers seulement) ; liste d'interdits hors glossaire
- [x] 3.2 Vérifier que le test échoue bien sur un libellé volontairement faux, un lien cassé et un terme interdit (puis annuler)

## 4. Validation en conditions réelles

- [x] 4.1 **Condition** : un PC de test Linux déclaré explicitement par le propriétaire dans la session. Annoncer et faire accepter le lot (moteur transcribe.cpp, modèle `handy-computer/whisper-large-v3-turbo-gguf` fichier Q5_K_M ≈ 620 Mo, audio synthétique ou non personnel, copie vierge du dépôt, dossier de données neuf) avant toute installation ou téléchargement ; consigner OS, machine, versions, dépendances
- [x] 4.2 Suivre le guide à froid sur ce PC jusqu'à une première transcription lue et une comparaison (deux exécutions du même modèle sur le même audio : pas de second téléchargement) ; relever les accès réseau réels et les durées mesurées ; consigner et corriger chaque écart
- [ ] 4.3 Relecture : critères de style (vouvoiement, phrases courtes, sigles développés, clarté) par le propriétaire, idéalement aussi par une personne qui ne connaît pas le projet ; intégrer les retours
- [x] 4.4 Windows : réutiliser les preuves CI existantes, **sans nouveau job** (accord explicite requis) ; consigner honnêtement ce qui reste non vérifié (installeur de uv, lancement en console, Ctrl+C)

## 5. Clôture

- [x] 5.1 Suite de tests complète et `openspec validate rediger-documentation-utilisateur --strict`
- [x] 5.2 Consigner en mémoire projet les décisions (public, structure, exemple, gras), les écarts du parcours à froid et les limites ; mettre à jour `AGENTS.md` si la structure de la documentation y est citée

## Validations du propriétaire — 2026-11-13

- 1.1 : public visé confirmé par le propriétaire dans la session (hypothèse du design D2 retenue telle quelle : à l'aise avec un ordinateur, sans programmation, prêt à copier-coller des commandes).
- 4.1 : lot du parcours à froid accepté le 2026-11-13 (moteur transcribe.cpp, modèle `handy-computer/whisper-large-v3-turbo-gguf` fichier Q5_K_M ≈ 620 Mo, audio synthétique, copie vierge du dépôt, dossier de données neuf) ; PC de test Linux déclaré (T14s, Manjaro). L'installation et le téléchargement n'ont lieu qu'après cet accord.

## Parcours à froid — 2026-11-13 (PC de test Linux T14s)

- 4.2 **fait** : copie vierge (archive ZIP 1,1 Mo de GitHub), dossier de données neuf, guide suivi pas à pas de l'étape 3 à l'étape 12, parties navigateur dans un vrai navigateur. Première transcription lue (audio synthétique de 10,7 s) puis comparaison de deux exécutions du même modèle sur le même audio (aucun second téléchargement). Durées mesurées : moteur ≈ 1 s (cache), vérifications ≈ 40 et 50 s, téléchargement 590,9 Mio en ≈ 6 s, exécutions 5,841 s et 5,923 s. Arrêt vérifié (« Arrêt du serveur. »). Détail dans `docs/validation-linux.md` (« Parcours à froid du guide utilisateur — 2026-11-13 »).
- Écarts corrigés dans le guide (12 relevés, tous documentaires) : panneau refermé après vérification + actualisation et attente, déroulement normal « Dépôt refusé (fichier-gguf-non-choisi) », journal d'installation dans « Versions installées », bouton d'installation restant affiché sur un moteur prêt, libellé réel « Utiliser ce modèle pour préparer une exécution. », durées mesurées renseignées, « meilleur temps » sur valeurs exactes avec affichage arrondi identique, libellé réel « RTF (durée de transcription / durée décodée) », tri « Plus rapides » par défaut en comparaison, durée dans l'historique (« Début » sans « Fin »), décalage historique/opération. Cas de dépannage réellement rencontré : port occupé par un autre programme (Thunderbird) — message réel conforme au guide, solution `--port 8080` appliquée.
- 2.1, 2.2, 2.5 : contenu vérifié et complété par le parcours (glossaire inchangé, accès réseau renseignés avec mesures, dépannage enrichi des messages réellement produits, niveaux de vérification datés par procédure).
- 4.4 : preuves CI réutilisées sans nouveau job ; `docs/ci-windows.md` complété avec le run `43411758748` (2026-11-13) et les limites honnêtes (installeur de uv, lancement en console, Ctrl+C non vérifiés sur un poste Windows).

## Clôture — 2026-11-13

- 5.1 : suite complète **1433 tests OK** (dont 11 tests documentaires) ; `openspec validate rediger-documentation-utilisateur --strict` OK.
- 5.2 : mémoire projet `projet/documentation-utilisateur-guide-public-parcours-froid-2026-11-13` (public confirmé, écarts du parcours, limites). `AGENTS.md` non modifié : la structure de la documentation n'y est pas citée.
- Il ne reste que la tâche 4.3 (relecture de style par le propriétaire).
