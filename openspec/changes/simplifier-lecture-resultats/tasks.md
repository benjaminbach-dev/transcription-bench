# Tasks

## 1. Données de lecture et formats

- [x] 1.1 Enrichir les entrées de groupes avec mesures par audio, matériel de l'essai, date, état et ordre ; vérifier dans les tests de consultation que les données proviennent des résultats consignés et restent disponibles après suppression du modèle local.
- [x] 1.2 Ajouter les ratios CPU/RAM purs et les formats français de premier niveau ; tester 50 % CPU (8 s CPU / 2 s / 8 logiques), RAM SI, valeurs absentes, booléens, infinis, dénominateurs invalides, ratios > 100 %, valeurs positives très petites et absence de réécriture des JSON ; documenter les conventions dans l'aide locale.

## 2. Classement par audio

- [x] 2.1 Ajouter le tri GET borné temps/ram/cpu/recent, temps par défaut et départage stable avant arrondi sur les listes de `/resultats/comparaison`, avec ancre de retour au groupe et limite explicite des cases non soumises ; couvrir dans les tests web tri dupliqué/inconnu (400), None en fin, égalités, dates inconnues et conservation de l'ordre reçu sur la vue de comparaison.
- [x] 2.2 Présenter une ligne par résultat avec état, marques, date et réglages distinctifs, séparer les simulations et exclure les mesures partielles des distinctions ; tester absence de dédoublonnage, classement CPU non qualifié d'efficacité, et accès à l'historique global complet sans empreinte valide.

## 3. Comparaison et détail progressif

- [x] 3.1 Remplacer le tableau des transcriptions par des cartes à trois indicateurs et texte complet, synthèse descriptive temps/RAM, différences puis toutes les informations ; adapter les tests de rendu sans perdre les sélections multiples déjà permises ni le RTF avec son repère en détail.
- [x] 3.2 Appliquer la même priorité au détail individuel et afficher les annotations RAM cumulative, matériel différent/inconnu selon les quatre champs requis (nom CPU seul absent sans alerte) et états partiels ; tester que textes, marques et avertissements restent hors accordéons fermés et que durée du lot n'est jamais durée de l'audio.
- [x] 3.3 Regrouper les explications répétées dans l'aide locale et mettre en avant le lien existant Résultats vers groupes/classement et ajouter seulement la route GET fixe `/resultats/aide`, sans modifier le menu ni les routes existantes ; mettre à jour le guide concerné et ses tests de cohérence, vérifier la lecture éditoriale sans jargon avant les textes.

## 4. Vérification intégrée

- [x] 4.1 Exécuter les tests ciblés consultation/comparaison/résultats/habillage/hors-ligne avec données synthétiques, sans réseau ni moteur réel ; vérifier absence de nouvelle classe/CSS/script et `git diff --check`.
- [ ] 4.2 Faire observer par navigator les écrans finaux à 1280 × 800 et 360 px, clair/sombre réel et clavier : noms, trois métriques et début des textes visibles sur bureau pour le cas courant sans encart d'alerte, empilement et absence de débordement mobile, cas longs/absents/factices/partiels/égalités ; consigner ce qui n'a pas pu être observé sans le cocher comme validé.

## Vérifications du lot final — 2026-11-05

- Implémentation 3.1 à 3.3 par un worker séquentiel, relecture et corrections du principal après chaque tâche ; revue advisor après réception des constats navigator, puis contrôle des corrections. Aucun moteur réel, installation, téléchargement ni nouvelle mesure système.
- Navigator Sonnet / medium, données entièrement fabriquées sur un serveur HTTP loopback temporaire : clair à 1280 × 800 et 360 × 800, cas courant/long/absent/factice/partiel/égalité/matériel différent/erreur ; clavier et détails ouverts/fermés observés. Les jeux sans marques servent uniquement à observer le rendu normal, jamais de preuve de mesure réelle.
- Après corrections de densité sans CSS : à 1280 × 800, début des deux textes à y = 710,1 sans défiler ; à 360 × 800, titre de première carte à y = 444,9–540,3 et bloc complet des trois indicateurs à y = 641,3–785,8, sans débordement horizontal (largeur de page 360). Erreur comparée visible hors détails et échappée ; matériel et versions consultables ; PID, lancement, timings et segments restent dans les informations complètes, pas dans le résumé des différences.
- **4.2 reste non cochée : thème sombre réel non observé**, l'outil navigateur disponible n'exposant pas l'émulation de `prefers-color-scheme`. Aucune injection CSS n'est présentée comme validation du sombre. Ce reliquat n'est ni une dérogation aux exigences ni une validation de l'autre change Sumi. Une configuration/outillage adapté ou un contrôle utilisateur réel reste nécessaire.
- Détail individuel : segments, mesures détaillées et ordinateur/version ouverts et vérifiés ; les autres sections ne sont pas revendiquées comme explorées exhaustivement. Les passes finales sont ciblées : pas de nouveau balayage intégral de tous les scénarios après chaque petite correction.

## Workflow follow-up

- Ne pas archiver Sumi ni considérer ses vérifications comme réalisées par cette rédaction ; coordonner les gabarits pour éviter deux implémentations simultanées.
- Après implémentation, relire les artefacts et synchroniser les deltas lors d'un archivage explicitement demandé. Le change système complète la lecture sans bloquer cette refonte.
