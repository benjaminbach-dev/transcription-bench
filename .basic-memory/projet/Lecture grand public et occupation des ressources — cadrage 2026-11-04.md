---
title: Lecture grand public et occupation des ressources — cadrage 2026-11-04
type: note
permalink: transcription-bench/projet/lecture-grand-public-et-occupation-des-ressources-cadrage-2026-11-04
tags:
- decision
- interface
- ressources
- openspec
---

# Lecture grand public et occupation des ressources — cadrage 2026-11-04

Contexte : après la refonte Sumi (base 931e2a5), demande d'une lecture plus rapide des résultats et de spécifications revues avant et après rédaction par advisor. Les exigences détaillées restent dans les deux changes OpenSpec, pas dans cette note.

## Observations

- [decision] Priorité demandée : textes de transcription, durée, pic de RAM modèle chargé inclus et occupation CPU moyenne rapportée à l'ordinateur, immédiatement visibles ; détails moteurs/réglages au second niveau. Pas de graphiques ni de jugement automatique de qualité.
- [decision] Le temps CPU cumulé n'est pas un indicateur principal compréhensible pour cet usage. Le cadrage remplace l'ancien choix « pas de pourcentages » du 2026-10-23 par des pourcentages de ressources explicitement nommés et contextualisés.
- [decision] Deux changes distincts : `simplifier-lecture-resultats` dérive les ratios depuis les valeurs consignées existantes sans réécriture ; `mesurer-charge-systeme` ajoute CPU global moyen pendant chaque audio et RAM disponible après chargement/après audio.
- [rationale] Une mémoire disponible instantanée n'est pas le minimum pendant l'audio. Le contexte système inclut les autres programmes et ne doit pas servir à classer les modèles ou à attribuer une consommation à l'application entière. Le pic RSS moteur reste cumulatif, modèle et buffers inclus.
- [rationale] Deux relevés CPU dans le runner ont été préférés à un observateur périodique serveur : bornes d'inférence connues, pas de thread supplémentaire ni attribution approximative entre audios. Les deux appels non bloquants de psutil 7.2.2 partagent un état par thread ; le premier est ignoré.
- [validation] Lecture du code, documentation psutil 7.2.2 et sonde d'API Linux avec processus Python synthétique dormant réussies ; aucune inférence réelle ni validation Windows. Deux changes complets validés OpenSpec strict ; revue advisor après rédaction, corrections et contrôle final favorables.
- [status] Spécifications seulement, aucune implémentation. Ni archivage de Sumi ni levée de ses vérifications restantes ; aucun nouveau job moteur, installation ou téléchargement autorisé par ces documents.

## Relations

- relates_to [[Décisions du prototype de benchmark]]
- extends [[Specs habillage Sumi et documentation utilisateur]]

## Premier lot UI implémenté — 2026-11-04

- [validation] Tâches 1.1 et 1.2 réalisées par deux workers distincts, relues et corrigées par le principal ; revue advisor de fin de lot puis contrôle final favorables. Matériel/date/état/ordre et mesures par audio exposés dans les groupes, sans mesure de la machine courante ni dépendance aux poids locaux.
- [validation] Ratios et formats français purs ajoutés ; formats détaillés préservés. Corrections principales : arithmétique sans débordement intermédiaire, contrôle 0..100, échappement HTML, initialisation Jinja après configuration Flask et bruit flottant de pourcentage exact. Tests finaux du principal : 211 ciblés réussis, OpenSpec strict et diff sans espaces invalides ; advisor a aussi exécuté 799 tests complets avant les dernières petites corrections, puis 21 ciblés après. Aucun moteur réel ni validation Windows.
- [status] Progression `simplifier-lecture-resultats` : 2/9. Le gabarit d'aide est préparé et testé au rendu, mais non routé : l'accès HTTP relève de 3.3. Ni classement, cartes ni nouvelle mesure système implémentés dans ce lot.
- [next] Raccord des lots 2/3 : les ratios purs retournent None pour absence ou incohérence ; choisir le libellé avec les données brutes disponibles pour ne pas appeler « non mesurée » une mesure brute existante mais un ratio inexploitable. Aucun framework d'états supplémentaire nécessaire. La route d'aide et son test d'absence HTTP seront adaptés à 3.3.

## Cartes, détail et aide — lot final du 2026-11-05

- [implementation] Tâches 3.1, 3.2 et 3.3 de `simplifier-lecture-resultats` réalisées par le même worker, une à une, puis relues/corrigées par le principal ; 4.1 vérifiée. Cartes à trois indicateurs/texte intégral, synthèse temps/RAM sans score, détails progressifs, alertes matériel et mémoire cumulative, route GET fixe `/resultats/aide`, guide aligné. Aucun CSS, script, moteur réel, dépendance ou nouvelle mesure système ajouté ; résultats historiques non réécrits.
- [validation] Revue advisor après transmission du rapport navigator Sonnet / medium, corrections puis contrôle : message d'erreur comparée visible et échappé, matériel/versions/provenance accessibles dans la comparaison ; provenance technique volumineuse hors résumé des différences, segments sans diff textuel ; libellés désambiguïsés pour deux audios de la même exécution.
- [validation] Observation navigateur sur résultats intégralement fabriqués, pas mesures de moteurs : clair bureau 1280 × 800 et mobile 360 × 800, clavier, détails ouverts/fermés, long/absent/factice/partiel/égalité/matériel/erreur. Après correction HTML de densité, début des deux textes à y=710,1 sur bureau ; trois indicateurs complets de première carte à y=641,3–785,8 sur mobile, sans débordement horizontal. Les jeux sans marques servent seulement au cas visuel normal.
- [validation] Suite finale exécutée par le principal : 873 tests réussis, 23,681 s, `uv run --locked --offline python -m unittest discover -s tests -t .`. Aucun moteur réel ni accès réseau externe dans les tests. OpenSpec strict et diffcheck exécutés pendant le lot ; vérifications finales de publication à consigner séparément.
- [limit] Progression 8/9, tâche 4.2 volontairement non cochée : sombre réel non observé, faute d'émulation `prefers-color-scheme` exposée par l'outil navigateur. Aucune injection substitutive, aucune dérogation acceptée ; besoin d'outillage/configuration adapté ou contrôle utilisateur réel. Aucun archivage, aucune levée implicite des reliquats Sumi ou documentation.

### Publication et CI du lot final

- [validation] Lot publié sur `origin/main`, commit `3b1145c35c558f4e04f60a0f7bf36c0db2dc7fdb`, après contrôle identité Benjamin Bach, remote et branche. Revue advisor finale favorable, vérification navigator mobile finale conforme. `openspec validate simplifier-lecture-resultats --strict`, `uv lock --check --offline`, contrôles diff et index réussis ; captures d'anomalies supprimées après exploitation et serveur temporaire arrêté.
- [validation] Run GitHub Actions [42126153452](https://github.com/benjaminbach-dev/transcription-bench/actions/runs/42126153452), déclenché par ce push, terminé en succès sur Ubuntu 24.04 et Windows 2022, jobs sans moteur réel. Suivi jusqu'à conclusion via `gh run watch --exit-status`. Aucun job moteur manuel lancé ; ces preuves ne valident ni le sombre navigateur ni des performances utilisateur. L'ancien incident de lecture PID vide n'est pas déclaré corrigé par ce seul succès.
- [limit] `simplifier-lecture-resultats` reste à 8/9 sans archivage : contrôle réel du thème sombre toujours à faire. Le dossier `.playwright-mcp/` préexistant reste non suivi et hors des commits.

## Retour utilisateur et nouvelle proposition — 2026-11-06

- [validation] L'utilisateur confirme son PC local à jour et valide sombre ainsi que hover/focus ; OS/navigateur/résolutions non consignés. La matrice complète 4.2 reste ouverte et le thème sombre n'est plus présenté comme un blocage.
- [decision] L'ergonomie livrée est contestée : listes trop denses, chiffres clés mal placés. Nouveau change `refondre-parcours-resultats` rédigé, sans implémentation : parcours centrés sur résultats, préparation unique, navigation à six rubriques et JS local léger proposé. Les exigences détaillées restent dans OpenSpec.
- [rationale] Modèle et moteur sont liés par la référence locale ; ne pas inventer une interchangeabilité des formats. Groupes par empreinte audio pour ne pas comparer directement des temps d'audios distincts ; durée source commune séparée du temps de transcription.
- [validation] Conseil advisor puis revue et contrôle des corrections : refonte cohérente, réserve sur la réconciliation de la présentation du change de mesures système encore non implémenté. Correction de son delta/design/tâches proposée explicitement au propriétaire, en attente de confirmation. Ni collecte, stockage ni autorisations d'inférence élargis.
- [validation] Dépôt `openspec validate --all --strict` : 11 éléments valides ; simulation de fusion dans /tmp des seuls Sumi, première lecture et nouvelle refonte : 8 éléments valides, sans mesures système. Aucun archivage ni synchronisation des specs principales réels. Windows et Linux sans moteurs verts au run 42126402493 tentative 3 sur 5e0cfc7 ; cette CI ne valide pas la nouvelle UI non implémentée.
- [status] Publication demandée par l'utilisateur une fois tout validé ; pas encore effectuée à cette note. AGENTS conserve sa règle sans JS : sa révision avec rechargement reste un préalable explicite à l'implémentation.

## Réconciliation approuvée — 2026-11-07

- [decision] Le propriétaire confirme l'alignement de `mesurer-charge-systeme` : bloc secondaire repliable « Contexte de l'ordinateur » dans détail/comparaison, aucune colonne système dans les listes ; collecte, schéma et stockage inchangés. Proposal, delta de présentation, design D4 et tâches 3.1/4.5 réconciliés ; ce change reste non implémenté, 0/12.
- [validation] Nouvelle composition des contrats dans une copie jetable /tmp : Sumi → première lecture → refonte valide sans mesures système (8 éléments stricts), puis ajout futur des mesures système valide également (7 éléments stricts). Aucun archivage ni synchronisation réelle ; le dépôt reste à 11 éléments valides.
- [status] Accord explicite de commit/push après revue finale et vérifications, sans implémentation. La réserve de consentement sur la réconciliation est levée ; la nouvelle recette UI et les 20 tâches de réalisation restent à faire.

- [validation] Revue finale advisor après réconciliation le 2026-11-07 : prêt à publier, aucun bloquant. Collecte/stockage inchangés, validations utilisateur bornées et absence d'implémentation confirmées. Précisions éditoriales intégrées : bloc explicitement repliable et référence des formats à la nouvelle refonte.

## Début de la refonte — lot 1 partiel, 2026-11-07

- [decision] Application de `refondre-parcours-resultats` demandée : un worker distinct par tâche, relecture/corrections du principal, navigator Sonnet 5.5 / medium puis rapport transmis à advisor Opus 5.5 / medium en fin de lot ; corrections et push avant le lot suivant. Repli worker explicitement décidé : Haiku 5.5 / high si défaut indisponible. Aucun archivage demandé.
- [validation] `AGENTS.md` autorise désormais JS local vanilla en amélioration progressive et CSS applicative ; modification demandée au principal puis `/reload` effectué et règles chargées vérifiées. Pas de dépendance ajoutée.
- [status] Tâches 1.1–1.4 réalisées et cochées : route JS/CSP, composant compact, liste Résultats groupée par empreinte et tris internes, historique intégral conservé provisoirement dans un détail secondaire. Données historiques non réécrites ; aucun moteur réel ni poids installé.
- [validation] Principal : suite complète locale de 949 tests réussie en 25,512 s, commande `uv run --locked --offline python -m unittest discover -s tests -t .`, validation OpenSpec stricte et diffcheck réussis. Ces preuves ne sont pas des vérifications Windows ni des mesures de modèles.
- [validation] Navigator sur serveur éphémère et données intégralement fabriquées : clair réel, bureau 1280 × 800 et mobile 360 × 800 ; après corrections, quatre entrées complètes bureau (y ≈ 276–642), première entrée complète mobile (y ≈ 361–573), aucun débordement horizontal ; tris, cas longs/dégradés, défilement de l'historique au clavier observés. Les fixtures sans marques servent seulement au rendu courant, jamais à des performances réelles.
- [validation] Advisor Opus 5.5 / medium, rapport navigator transmis puis corrections et contrôle final : code 1.1–1.4 conforme, aucun bloquant/majeur de code restant ; 119 tests ciblés supplémentaires relancés par l'advisor.
- [blocker] Tâche 1.5 volontairement ouverte : outils Playwright exposés sans émulation de thème sombre ni désactivation JS. Clair vérifié par matchMedia ; aucune injection CSS/JS substitutive. Demande d'accord utilisateur distinct pour traiter l'outillage hors dépôt ; lot 2 non commencé tant que le préalable visuel n'est pas levé.
- [limit] Petits reliquats : espacement tri/groupe, listes fermées de classes héritées, libellés de tri, ancre audio dans le détail. Sans JS non observé (recette 6.1 à venir). Aucun commit/push/CI/synchronisation/archivage à ce stade : lot 1 encore partiel.

### Décision de clôture 1.5 et reprise avant compactage — 2026-11-07

- [decision] Le propriétaire demande explicitement de considérer le contrôle sombre comme validé et de continuer, outillage reporté : 1.5 cochée sur cette acceptation, sans observation du sombre ni preuve inventée. Cette décision remplace le blocage historique décrit ci-dessus ; aucun accord de modification MCP ni dispense du mode sans JS n'est déduit.
- [status] `refondre-parcours-resultats` : 5/20, lot 1 validé avec cette limite acceptée ; aucun commit/push encore effectué au moment de la pause demandée avant compactage. Publier le lot 1 puis reprendre 2.1 selon l'orchestration prescrite.
- [next] Point de reprise détaillé, état des fichiers et méthode worker/navigator/advisor : [[Reprise refonte parcours résultats — lot 1 et orchestration 2026-11-07]].
