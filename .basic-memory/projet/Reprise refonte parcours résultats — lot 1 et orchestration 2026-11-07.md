---
title: Reprise refonte parcours résultats — lot 1 et orchestration 2026-11-07
type: note
permalink: transcription-bench/projet/reprise-refonte-parcours-resultats-lot-1-et-orchestration-2026-11-07
tags:
- reprise
- openspec
- interface
- orchestration
---

# Reprise refonte parcours résultats — lot 1 et orchestration 2026-11-07

Note de reprise avant compactage expressément demandée par le propriétaire. Source des exigences : change `refondre-parcours-resultats`. Les anciennes mentions de blocage du lot 2 par le sombre, dans la note de cadrage et les rapports intermédiaires, sont remplacées par la décision de clôture ci-dessous, sans inventer une preuve visuelle.

## Décisions et méthode à conserver

- [decision] Continuer toute la refonte selon ses six lots, sans demander un nouvel accord à chaque tâche dans le périmètre. Autres changes UI suspendus ; `mesurer-charge-systeme` reste indépendant et non implémenté.
- [decision] **Un worker distinct pour chaque tâche**, séquentiellement (au plus un worker actif). Le principal lit le travail, vérifie et corrige avant de cocher la tâche et de passer à la suivante. Un même worker peut être repris pour corriger sa propre tâche.
- [decision] Worker : profil par défaut ; en cas d'indisponibilité, **Haiku 5.5 / thinking high** demandé explicitement. Ne pas substituer silencieusement un autre modèle. Le défaut DeepSeek a rencontré plusieurs erreurs 429 avant tout outil ; repli Haiku utilisé pour 1.3, 1.4 et préparation 1.5. La vérification initiale 1.1 a utilisé Sonnet avant la décision de repli Haiku.
- [decision] En fin de chaque lot : **navigator Sonnet 5.5 / thinking medium**, puis transmettre son rapport à **advisor Opus 5.5 / thinking medium** pour revue ; corriger, recontrôler si nécessaire, puis **commit et push du lot avant de poursuivre le suivant**. Autorisation explicite utilisateur de ces publications dans cette méthode, sans push forcé ni élargissement. Suivre aussi le résultat CI après push, ne pas confondre tests locaux et CI.
- [decision] Le propriétaire reporte la modification d'outillage Playwright et demande de considérer le contrôle sombre comme validé afin de continuer. **1.5 est cochée sur acceptation explicite, sombre réel toujours non observé**, pas sur preuve technique. Aucun accord pour modifier MCP/configuration hôte.
- [constraint] Ne pas étendre cette acceptation au mode sans JavaScript de 6.1 : il reste non observé et non dispensé. Les limites futures sont à consigner honnêtement, sans relancer le blocage sombre déjà arbitré pour 1.5.
- [constraint] Pas de moteur réel, installation, poids, inférence réelle ou job moteur. Tests factices/synthétiques uniquement sur le serveur. Pas de synchronisation ni archivage sans demande distincte.

## État exact à la pause

- [status] OpenSpec **5/20** : 1.1 à 1.5 cochées, 2.1 à 6.3 non commencées. `openspec validate refondre-parcours-resultats --strict` et `git diff --check` réussis après la clôture propriétaire.
- [status] **Aucun commit ni push du lot 1 encore effectué** ; pause pour compactage demandée juste avant sa publication. Ne pas commencer un nouveau worker 2.1 avant d'avoir contrôlé puis publié le lot 1 et suivi sa CI. Branche `main`, remote `origin` = `git@github.com:benjaminbach-dev/transcription-bench.git`, identité vérifiée Benjamin Bach <mail@benjaminbach.dev> ; revérifier avant publication.
- [validation] `AGENTS.md` du dépôt modifié sur demande, `/reload` effectué et règles chargées confirmées : `/app.js` local vanilla `defer`, amélioration progressive avec repli HTML, CSS applicative Sumi/Flexoki, CSP D6 et protections maintenues. Aucun rechargement supplémentaire nécessaire pour ces règles inchangées.
- [implementation] Route JS fixe et CSP ; `app.js` encore inerte ; composant `web/templates/composants.html`, mapping `web/vues_resultats.py`, liste Résultats groupée par empreinte avec tris internes (récents par défaut), mesures visibles, factices séparés, états et matériel visibles. Noms courts sauf homonymes, préfixes d'empreinte/révision allongés en cas de collision, révision seulement si différente et utile. Anciennes données non réécrites.
- [implementation] Historique intégral provisoirement dans un détail de Résultats : déplacement vers Exécutions prévu en 3.1. Ancienne navigation encore présente, migration en 3.1. Le guide est ajusté à ce seul état intermédiaire.
- [validation] Principal : **949 tests OK, 25,512 s**, commande `uv run --locked --offline python -m unittest discover -s tests -t .`, log `/tmp/transcription-refonte-tests-lot1.log`. Derniers changements après cette suite : consignation documentaire de la clôture propriétaire seulement. Advisor final : 119 tests ciblés OK ; pas encore de CI du nouveau lot.
- [validation] Navigator Sonnet 5.5 / medium, deux passes sur données intégralement fabriquées : clair réel bureau 1280×800 et mobile 360×800, tris/détails/cas longs/dégradés/historique clavier. Après corrections, quatre entrées complètes bureau (y≈276–642), première entrée mobile complète (y≈361–573), aucun débordement de page, absences coupées entre mots seulement. Première passe : ressources uniquement locales ; seconde passe : réseau non recontrôlé, console sans anomalie nouvelle.
- [validation] Advisor Opus 5.5 / medium repris après transmission du rapport navigator et corrections : code 1.1–1.4 validé, aucun bloquant ni majeur restant. Ancien blocage de recette sombre ensuite levé par décision propriétaire, pas nouvelle observation.

## Points de reprise pratiques

- [next] Relire `tasks.md`, `design.md` et les deltas du change, rafraîchir `openspec instructions apply --change refondre-parcours-resultats --json`. Préserver l'état de travail. Contrôler l'index et les fichiers exacts, commit/push du lot 1, suivre tests Linux/Windows sans moteurs ; puis worker neuf pour **2.1 sélection comparative**. Répéter la méthode de revue/publication par lot.
- [limit] Mineurs connus : espace tri/premier groupe trop faible, listes fermées de classes/CSS héritées à ne pas perpétuer inutilement, libellés « Temps de transcription / Essais récents » au lieu des libellés ciblés, liens de résultat sans ancre par audio. Paramètre `empreinte` désormais inutilisé dans `entete_groupe_audio`. Reconnaissance des absences par textes de formateurs, couverte par tests mais à garder cohérente.
- [provenance] Arbre de travail non committé : AGENTS, guide, tâches, tests HTML/styles/résultats, consultation et web, nouveaux composants/mapping/script/tests, présente note et note de cadrage modifiées via MCP. `git status` est la source exacte pour préparer le commit ; ne pas ajouter tout le répertoire aveuglément.
- [constraint] Dossier **`.playwright-mcp/` préexistant non suivi** : préserver, ne pas inclure dans les commits ni nettoyer globalement. Captures créées pendant ce lot supprimées après exploitation. Navigateurs fermés.
- [provenance] Harnais temporaire `/tmp/refonte-resultats-1-5/servir.py`, données synthétiques `/tmp/refonte-resultats-1-5/data/` : serveur **arrêté** (ancien PID3552790, ancien port47275), ne pas supposer ces identifiants encore valides. Relançable avec Python `.venv` et `--port`, données sans marques artificielles utilisées uniquement pour le cas visuel courant. Aucun serveur publié ni service partagé modifié.

## Relations

- relates_to [[Lecture grand public et occupation des ressources — cadrage 2026-11-04]]
- relates_to [[Specs habillage Sumi et documentation utilisateur]]
- relates_to [[Décisions du prototype de benchmark]]

## Reprise autonome et publication effective — 2026-11-07

- [decision] Le propriétaire confirme de poursuivre en autonomie, sans rendre la main pour une simple attente de CI ou entre les tâches. Maintenir les décisions et garde-fous ; remonter uniquement une décision nécessaire.
- [status] Lot 1 publié sur `main` : `16fcf520be3b7b86c6f03759f98e4e9b8fb827b7`, puis correctif de test `b99593e3598eef95183c84031a5c49b4ccb3d66a`. La mention « pas encore committé/poussé » ci-dessus est désormais historique.
- [validation] Première CI42379351543 en échec sur test_script_et_csp de script non fermé ; correction worker distinct et relecture principal : le rejet doit dépendre du compteur de script non fermé, non du contenu tamponné par HTMLParser variable selon les versions. Aucun changement de comportement du vérificateur, rejet inline/doublons/nonfermé conservé ; 61 tests ciblés locaux OK.
- [validation] CI corrective [42381533738](https://github.com/benjaminbach-dev/transcription-bench/actions/runs/42381533738) **réussie sous Ubuntu24.04 et Windows2022** sur b99593e, sans moteurs réels ni réseau externe pendant les tests. Le lot 1 est terminé, todo4 complétée.
- [status] Lot 2 en cours, worker neuf `df1badda-f876-4d1` pour 2.1 (comparaison compacte, conservation/validation des sélections et tris GET). Tâches2.1–2.3 pas encore cochées à cet instant. Worker par défaut DeepSeek disponible sur la correctionCI et cet appel ; repli Haiku5.5high seulement si indisponible.

## Lot 2 implémenté, relu et observé — 2026-11-07

- [status] Tâches 2.1–2.3 cochées, **8/20** : worker distinct par tâche (`df1badda-f876-4d1`, `4dc3a48a-ee9f-483`, `cf5d021a-bf42-4df`), principal relecture/corrections. GET de tri conserve cases du groupe revalidées, lignes compactes partout, badges temps/RAM locaux sans CPU ni distinction factice/partielle, aide/prose unique et guide aligné.
- [decision] Borne technique partagée désormais 64 valeurs de sélection reçues, doublons compris avant déduplication. Aucun plafond de nombre explicite n'existait avant (hypothèse D2 inexacte), maintenant appliqué à la liste et la comparaison et documenté ; pas d'inter-empreinte ni nouvel ordre arbitraire.
- [validation] Première observation navigator Sonnet 5.5 / medium a révélé densité de sélection insuffisante ; rapport transmis à advisor Opus 5.5 / medium, corrections du principal et recontrôle : 4 lignes complètes bureau 1280×800 (dernière date y≈752), première ligne mobile360×800 avec modèle/mesures/date avant y≈744, sans débordement. Deux cartes/textes courts visibles bureau avant800 ; mesures première carte mobile visibles. Factices/partiels comparés sans badge. Focus Tab Comparer visible. Données intégralement fabriquées.
- [validation] Réseau constaté pour chargement de liste : document et3ressources GET200 loopback uniquement ; console0erreur au recontrôle. Pas preuve de toutesnavigations. Sombre et mode sansJS nonobservés, pas de changement d'outillage. GET/HTML sansJS couverts par tests uniquement.
- [validation] Advisor final (`50292718-915d-47f`) valide corrections de densité et code sans bloquant/majeur ; guide corrigé ensuite sur3phrases précises. Principal a aussi rendu tableauxsecondaires focusables/nommés et couvert comparaison ; ne pas supprimer `.playwright-mcp/` malgré suggestion générique de revue, car préexistant protégé.
- [validation] Suite complète principal **970 tests OK en28,355s**, OpenSpec strict et diffcheck verts. Nouveau test dates/modèlesidentiques évite retour IDexécution en titre cartes, correctiondossierillisible garde erreur réelledossier au lieu400cases. Publication lot2 prochaine, puis CI et lot3 (3.1nouveauworker).
