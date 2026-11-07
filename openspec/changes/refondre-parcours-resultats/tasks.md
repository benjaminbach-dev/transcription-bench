# Tasks

## 1. Préparer le socle autorisé et un premier écran de référence

- [x] 1.1 Faire relire la modification ciblée d'AGENTS autorisant JS local et CSS applicative, l'appliquer après accord puis demander `/reload` ; vérifier la règle chargée avant tout code JS ou élargissement CSS. Ne pas installer de dépendance.
- [x] 1.2 Ajouter route fixe `/app.js` et CSP selon D6 ; adapter le vérificateur HTML pour autoriser exactement le script local `defer` et continuer d'interdire inline, `on…`, code distant et fichiers arbitraires ; tester MIME, Host, CSP sur pages normales, 404, 405 et une 500 réellement provoquée, ainsi que les 404 statiques.
- [x] 1.3 Créer le composant compact de résultat et ses jetons CSS (tailles, couleurs et grille), avec groupes audio et formats existants ; tester toutes les unités, les valeurs absentes/invalides, les longues variantes, la RAM cumulative et les états visibles ; étendre le test de contraste aux nouveaux jetons clair/sombre.
- [x] 1.4 Construire Résultats sur jeux synthétiques avec groupes par empreinte, cinq valeurs/date et tris internes, défaut récents ; couvrir conservation de chaque essai, tri brut, égalités, noms identiques/empreintes différentes, durées divergentes, modèle supprimé et lien vers historique complet ; mettre à jour la section de guide correspondante.
- [x] 1.5 Faire observer par navigator le premier écran Résultats à 1280 × 800 et 360 × 800 et corriger avant de généraliser : au moins trois lignes courantes visibles sur bureau, chiffres lisibles d'emblée, aucun débordement, hiérarchie de tailles/couleurs. Clair réel observé ; contrôle sombre clos sur décision explicite du propriétaire le 2026-11-07, sans observation ni preuve de rendu sombre ; outillage reporté.

## 2. Généraliser la lecture et la sélection comparative

- [ ] 2.1 Employer le composant compact dans les groupes Comparaisons avec cases dans la cellule modèle ; conserver les sélections lors des tris par boutons GET du formulaire, y compris sans JS, avec un critère commun à la page appliqué dans chaque groupe ; valider les sélections sur la route de liste et tester refus 400 des valeurs invalides/disparues/hors groupe, doublons/tri inconnu, ordre, bornes et absence de comparaison inter-empreintes.
- [ ] 2.2 Alléger comparaison sélectionnée et détail individuel selon D3 : durée audio commune, modèles/valeurs/texte au premier plan, distinctions temps/RAM près des valeurs sans synthèse répétée ; tester égalités, absence de distinction CPU/factice/partiel, erreurs échappées et détails complets conservés.
- [ ] 2.3 Regrouper l'aide et les annotations générales une seule fois par page, sans ajouter de vue de mesures système encore absentes ; vérifier l'absence de doublons de prose hors données/libellés et aligner le guide sur ces écrans. La présentation des futurs relevés système reste dans leur change distinct, non bloquant.

## 3. Navigation et suivi intégré

- [ ] 3.1 Passer aux six rubriques dans l'ordre prescrit, rediriger GET `/` et `/operation`, remplacer les retours d'actions et déplacer les diagnostics de dossiers ainsi que l'historique technique dans Exécutions ; tester aria-current, statuts, anciens liens, traduction des seuls codes `arret-demande`/`arret-incomplet` et rejet d'un paramètre de redirection libre, historique sans transcription et vérification explicite des dossiers ; aligner README et guide.
- [ ] 3.2 Exposer une vue synchronisée de l'identifiant du résultat actif puis clos, associée à l'identité de l'opération et invalidée au début de toute nouvelle opération, pas seulement d'une réservation moteur ; tester résultat en cours, clôture, interruption, abandon, échec avant consignation et absence de lien vers un ancien essai lors d'une autre opération, sans changer les JSON finalisés.
- [ ] 3.3 Intégrer résumé d'opération et arrêt applicable dans Exécutions ; ajouter GET `/executions/etat` nettoyé/no-store et polling borné selon D5 ; tester validation du lien local `/resultats/`, pas de mutation GET, arrêt protégé, refus concurrent, terminal/erreur de requête/onglet masqué et une seule requête active ; observer focus conservé et repli Actualiser sans JS.

## 4. Préparation d'exécution unique

- [ ] 4.1 Remplacer les formulaires par modèle par un seul panneau de préparation Modèle/Audio/Moteur, référence locale précise et mise à jour GET sans jeton URL ; tester moteur incohérent, référence périmée, références/audios GET invalides avec message borné et sans 500, inventaire vide, modèle non exécutable, défauts applicables et repli HTML en deux étapes ; actualiser le guide de lancement.
- [ ] 4.2 Ajouter l'amélioration vanilla des sélections compatibles sans déclencher d'action ; retirer/désactiver les anciens réglages, conserver les choix encore valides ou annoncer leur réinitialisation ; tester familles aux noms de réglages identiques, changement de variante, doublons et soumission forgée.
- [ ] 4.3 Conserver audio unitaire et lot optionnel ordonné, réglages avancés fermés et actions Lancer/Vérifier non répétées ; couvrir unitaire/lot, défauts non ouverts, revalidation POST, double soumission/créneau occupé et restitution des erreurs sans perte silencieuse de choix valides ; observer le parcours clavier.

## 5. Modèles et cohérence éditoriale

- [ ] 5.1 Placer inventaire Modèles avant l'ajout, afficher nom/moteur/variante/taille lisible et action Utiliser ; garder révision/fichiers/suppression en détail et explication générale unique ; tester ordre du DOM, état vide, modèle actif non supprimable et sélection transmise à Exécutions.
- [ ] 5.2 Mettre l'ajout au second plan, l'ouvrir sur erreur ou demande explicite et garder vérification/téléchargement séparés ; tester absence d'accès réseau à l'ouverture, choix GGUF, refus visibles et taille prévisionnelle lisible ; mettre à jour le guide.
- [ ] 5.3 Harmoniser unités, aides et liens de Moteurs/Audios sans refonte de leurs services ; vérifier qu'aucun premier niveau ne présente octets bruts ou temps à trois décimales, et qu'aucune phrase explicative de huit mots ou plus n'est répétée dans le texte rendu des jeux synthétiques, hors données/libellés ; conserver les données brutes dans les détails et les limitations factices hors ligne.

## 6. Recette intégrée, preuves et livraison

- [ ] 6.1 Faire observer le parcours complet synthétique avec/sans JS à 1280 × 800 et 360 × 800, clair/sombre réels et clavier : contenu de D8, comparaison de deux textes, sélections/tris, lancement/arrêt factice, suivi et ajout fermé ; vérifier lisibilité sans explication orale, absence de réseau externe et focus stable. Ne pas réutiliser la validation utilisateur de l'ancienne interface comme preuve de ces écrans.
- [ ] 6.2 Exécuter les tests ciblés des modules modifiés puis l'intégration sans moteur réel sous Linux ; obtenir les tests factices Windows via le workflow autorisé, consigner commit/image/versions et les limites, sans job moteur ni données personnelles ; vérifier aussi les protections de sécurité existantes.
- [ ] 6.3 Vérifier cohérence specs/design/guide/tests et ordre de fusion D7 dans un aperçu isolé de synchronisation, lancer `openspec validate --all --strict` et `git diff --check`, puis consigner les preuves et limites réelles avant clôture.

## Application du lot 1 — 2026-11-07 (clôture avec limite acceptée)

- Tâches 1.1 à 1.4 réalisées : règles locales modifiées sur demande puis rechargées ; un worker par tâche, relecture et corrections du principal. Repli Haiku 5.5 / high après indisponibilité du worker par défaut.
- Validation locale du principal : 949 tests `unittest` réussis en 25,512 s (`uv run --locked --offline python -m unittest discover -s tests -t .`), sans moteur réel ni réseau externe ; validation OpenSpec stricte et contrôle des espaces réussis.
- Observation navigator Sonnet 5.5 / medium sur serveur temporaire et JSON entièrement fabriqués : clair réel à 1280 × 800 et 360 × 800, tris, cas longs/dégradés, détails et historique au clavier. Après corrections, quatre entrées complètes sur bureau (y ≈ 276–642), première entrée complète sur mobile (y ≈ 361–573), aucun débordement horizontal ; libellés absents sans coupure au milieu des mots. Les données sans marques sont des fixtures de présentation, jamais des mesures de moteurs.
- Revue advisor Opus 5.5 / medium après transmission des observations, corrections puis contrôle final : code 1.1–1.4 validé, aucun bloquant ni majeur de code restant ; 119 tests ciblés également relancés par l'advisor.
- **1.5 close sur décision explicite du propriétaire** : il demande de considérer le contrôle sombre comme validé et de continuer, en reportant l'outillage. Le sombre réel reste non observé avec les outils Playwright exposés (ni `emulateMedia` ni réglage de contexte) ; cette acceptation ne constitue pas une preuve de rendu. Aucun thème forcé/injecté, aucune réutilisation des validations de l'ancienne interface. Mode sans JS non observé (requis ultérieurement en 6.1), sans dérogation déduite. Le préalable du lot 2 est levé ; aucune modification d'outillage hors dépôt autorisée.
- Limites mineures à reprendre : espacement tri/premier groupe, listes fermées de classes héritées, libellés des tris, ancre vers l'audio dans le détail. Historique provisoirement conservé dans un détail de Résultats jusqu'à son déplacement prévu en 3.1. Aucun commit, push, CI, synchronisation ni archivage effectué à la pause avant compactage ; publication du lot 1 à effectuer avant le lot 2 selon la méthode demandée.

## Workflow follow-up

- La rédaction ne lance aucune implémentation et ne change ni AGENTS ni les services de cet hôte. Nouvelle demande d'application nécessaire ; `/reload` sera requis après modification d'instructions.
- Maintenir les autres travaux UI suspendus pendant cette refonte ; le change de mesures système reste indépendant pour la collecte et ne peut réintroduire ses anciennes contraintes de présentation.
- Synchroniser seulement sur demande, dans l'ordre Sumi → première lecture → présent change, sans dépendre des mesures système non implémentées. Cette opération de contrats ne valide aucune implémentation ; ne pas archiver des vérifications non réalisées ni rejouer les anciens deltas après la nouvelle cible.
- Faire approuver le rendu réel avant archivage, qui exige une demande explicite. Aucun job moteur ni inférence réelle n'est autorisé par cette liste.

## Vérifications documentaires — 2026-11-06/07

- Conseil puis deux passes de revue par le même advisor : corrections intégrées, contrôle final favorable sur la refonte ; réserve initiale sur la réconciliation du change de mesures système levée par la confirmation du propriétaire le 2026-11-07 et sa mise à jour ciblée (présentation uniquement). Dernière revue advisor après réconciliation : prêt à publier, aucune correction bloquante. Aucun code applicatif modifié et aucune nouvelle recette visuelle revendiquée.
- `openspec validate --all --strict` : 11 éléments valides sur le dépôt, sans édition des specs principales. Les informations « archive would refuse » de ce change isolé sont attendues tant que ses deux prédécesseurs ne sont pas synchronisés.
- Fusion testée dans une copie jetable `/tmp/transcription-spec-fusion-afi64d6b` : Sumi → première lecture → présent change, sans synchronisation des mesures système. Les trois fusions aboutissent ; les specs résultantes et les autres changes passent `--all --strict` (8 éléments). Les scénarios antérieurs sont préservés ou remplacés explicitement sous leurs en-têtes. Les commandes d'archivage n'ont été employées QUE dans cette copie pour éprouver le mécanisme ; aucune clôture ni coche d'implémentation n'est déduite de cette simulation.
- CI sans moteur réel sur le code de base `5e0cfc77641e8bd54007a10873f77c5490ec4e61` : run [42126402493](https://github.com/benjaminbach-dev/transcription-bench/actions/runs/42126402493), tentative 3, Windows 2022 et Ubuntu 24.04 verts. Cela ne teste aucune des nouvelles interactions, non implémentées.
- Revalidation du 2026-11-07 après réconciliation approuvée des mesures système : copie jetable `/tmp/transcription-spec-fusion-iz0fkicg`, fusion Sumi → première lecture → refonte valide sans mesures système (8 éléments stricts), puis ajout futur des mesures système réconciliées valide également (7 éléments stricts). Aucun archivage réel et aucune tâche d'implémentation cochée.
