---
title: Reprise refonte parcours résultats — pause après le lot 4, 2026-11-07
type: note
permalink: transcription-bench/projet/reprise-refonte-parcours-resultats-pause-apres-le-lot-4-2026-11-07
tags:
- reprise
- openspec
- interface
- pause
- orchestration
---

# Reprise refonte parcours résultats — pause après le lot 4, 2026-11-07

Note de reprise fraîche demandée par le propriétaire avant l'arrêt. Remplace les notes de reprise précédentes comme point d'entrée ; l'historique complet reste dans [[Reprise refonte parcours résultats — lot 1 et orchestration 2026-11-07]] et la note de cadrage. Le propriétaire a fixé la limite : **arrêt après publication du lot 4 et de cette note ; lot 5 non commencé**.

## État exact

- [status] Change OpenSpec `refondre-parcours-resultats` : **14/20 tâches cochées** (1.1–1.5, 2.1–2.3, 3.1–3.3, 4.1–4.3). Restent 5.1–5.3 (modèles et cohérence éditoriale), 6.1–6.3 (recette intégrée, preuves, livraison).
- [status] Branche `main` à jour sur `origin` (git@github.com:benjaminbach-dev/transcription-bench.git), identité Benjamin Bach <mail@benjaminbach.dev>. Publications du change : lot 1 `16fcf52` (+ correctif test `b99593e`), lot 2 `3023047`, lot 3 `149056a` (+ correctif UTF-8 harnais `ad840c3`), lot 4 `233d3fe`, note de reprise (commit à venir juste après cette note).
- [validation] CI « Tests sans moteur réel » verte à chaque lot : 42381533738 (lot 1), 42386908411 (lot 2), 42399490597 (lot 3), 42407167782 (lot 4), Ubuntu 24.04 et Windows 2022, sans moteur réel ni réseau externe pendant les tests. Dernière suite locale complète : **1094 tests OK en 31,638 s** (`uv run --locked --offline python -m unittest discover -s tests -t .`) ; `openspec validate --strict` et `git diff --check` verts.
- [status] Arbre de travail propre après publication (hors `.playwright-mcp/` préexistant non suivi, à préserver et ne jamais committer). Serveurs de recette temporaires arrêtés ; harnais réutilisable sous `/tmp/refonte-resultats-1-5/` (`servir.py` fixtures Résultats, `servir-lot3.py` ajoute 3 WAV + moteur factice ralenti 20 s pour polling/arrêt) — ne pas supposer PID/port/état, tout relire avant usage.

## Méthode et décisions à conserver

- [decision] **Orchestration par lot** : un worker neuf par tâche, relecture et corrections du principal avant chaque coche ; en fin de lot, navigator Sonnet 5.5 / thinking medium, transmission de son rapport à advisor Opus 5.5 / thinking medium, corrections, recontrôle si besoin, commit/push, puis CI avant le lot suivant. Pas d'archivage ni de synchronisation sans demande distincte.
- [decision] **Modèle des workers changé à la demande du propriétaire** : après la lenteur du défaut (3.1 ≈ 66 min, 3.3 ≈ 49 min), tout nouveau worker se lance en **Haiku 5.5 / thinking high** (repli déjà convenu). Aucun worker n'est actif à l'arrêt. Le principal a corrigé lui-même la fin du lot 4.
- [decision] Sombre réel clos par décision du propriétaire en 1.5, sans observation ni preuve de rendu, outillage Playwright (émulation média, JS off) explicitement reporté ; cette acceptation ne dispense ni du **sans JavaScript en 6.1** ni des limites futures à consigner honnêtement.
- [decision] Borne partagée de 64 valeurs de sélection reçues (doublons inclus, avant déduplication) en liste et comparaison : décision de réalisation, aucun plafond de nombre n'existait avant.
- [constraint] Pas de moteur réel, installation, poids, inférence réelle, job moteur, nouvelle dépendance ni réseau externe. Recettes navigateur sur harnais entirely synthétique uniquement. Ne pas modifier MCP/hôte. Mémoire via MCP `basic-memory`, project `transcription-bench`, seul principal écrit.

## Réalisations clés des lots 1–4 (pour reprise rapide)

- [implementation] Socle : `/app.js` local vanilla `defer`, CSP stricte D6 sur tout HTML (erreurs comprises), vérificateur HTML ne tolérant que ce script ; composant compact `composants.html` + jetons `app.css` (Flexoki, contrastes testés clair/sombre) ; Résultats groupé par empreinte audio, tris internes, désambiguïsation noms/révisions, historique complet conservé.
- [implementation] Comparaisons : lignes compactes avec cases dans la cellule modèle, tris GET conservant les cases (même groupe seulement, 400 sinon), comparaison sélectionnée/détail réutilisant le composant, distinctions « meilleur temps »/« meilleure RAM » près des valeurs (jamais CPU, ni factice/partiel), prose unique par page, aide alignée.
- [implementation] Navigation : six rubriques, `/`→Résultats et `/operation`→Exécutions#operation (302, codes d'action bornés), POST en 303 vers destinations fixes ; historique + diagnostics dans Exécutions ; génération stable par admission du créneau, association résultat→opération publiée dès consignation (`identifiant_resultat(generation)`) ; `GET /executions/etat` JSON no-store borné ; polling 3 s, une requête, suspension onglet masqué, arrêt terminal ; bouton d'arrêt terminal `aria-disabled` sans perte de focus, soumission empêchée ; garde « opération changée → actualiser ».
- [implementation] Préparation unique (D4) : panneau GET lecture seule (Modèle/Audio/Moteur + `source`, copies non sensibles désactivées sans JS) puis POST « Préparation appliquée » nommé avec CSRF ; audio unitaire par défaut, lot optionnel ordonné persistant, réglages avancés fermés ; réglages compatibles conservés, textes libres jamais en GET ; moteur seul changé (sans JS) sélectionne la première référence exécutable ; refus POST 400/403/409/503 restituent les choix valides ; harnais Node réel pour app.js (préparation + suivi), ignoré seulement si node absent.

## Points ouverts pour le lot 5 et suivants

- [next] 5.1 inventaire Modèles avant ajout (Utiliser → Exécutions), 5.2 ajout secondaire, 5.3 harmonisation unités/aides Moteurs/Audios. Puis 6.1 recette parcours complet **avec/sans JS** (observation réelle obligatoire, non couverte à ce jour), 6.2 tests ciblés + CI factice Windows avec consignation, 6.3 cohérence specs/design/guide + fusion D7 en copie isolée.
- [limit] Non observés à ce jour : mode sans JavaScript en navigateur réel, sombre réel (accepté/reporté), onglet masqué/panne fetch/opérations enchaînées en navigateur (couverts par harnais Node), multifamilles en préparation (couvert par tests serveur/Node). Le guide/technique sont alignés sur l'état observé, pas sur des parcours futurs.
- [limit] Connus mineurs non traités (facultatifs selon revues) : boutons Lancer/Vérifier sous la ligne de flottaison (aucune exigence 800 px pour la préparation), focus au body après soumission « Vérifier » (natif), espace tri/groupe Résultats, « Ce qui diffère » en valeurs brutes (5.3), `empreinte` inutilisé dans `entete_groupe_audio`, délai max fetch absent.
- [validation] Preuves à ne pas réutiliser : validations de l'ancienne interface, données CI comme mesures représentatives, valeurs factices comme performances. Les essais CI autorisés restent parole synthétique sur runner uniquement.

## Relations

- relates_to [[Reprise refonte parcours résultats — lot 1 et orchestration 2026-11-07]]
- relates_to [[Lecture grand public et occupation des ressources — cadrage 2026-11-04]]
- relates_to [[Décisions du prototype de benchmark]]

### Publication finale et incident CI intermittent — 2026-11-07 soir

- [status] Lot 4 publié `233d3fe`, CI code [42407167782](https://github.com/benjaminbach-dev/transcription-bench/actions/runs/42407167782) **verte Ubuntu/Windows** (1094 tests). Note de reprise poussée `0351311`.
- [validation] Premier run de la note `0351311` (commit **sans aucun code**, `.basic-memory` seul) : échec Windows sur `test_echec_de_consignation_du_pid_arrete_le_moteur` (dossier cache résiduel) et `test_arret_pendant_le_demarrage_ne_laisse_pas_de_processus` — la famille d'incidents intermittents Windows déjà documentée (PID vide/arrêt au démarrage, non résolue). Relance du job défaillant : **vert**, confirming intermittence et non-causalité avec le lot 4 ni la note. Run final [42407380188](https://github.com/benjaminbach-dev/transcription-bench/actions/runs/42407380188) vert après rerun. Ce flau reste ouvert pour 6.2 : ne jamais présenter un succès unique comme preuve de correction.
- [status] Session close conformément à la demande : lots 1–4 publiés, 14/20, aucun worker actif, serveurs temporaires arrêtés, `.playwright-mcp/` préservé non suivi, arbre propre hors ce dossier. Reprise : tâches 5.1–6.3 selon la méthode ci-dessus, workers en Haiku 5.5 / thinking high.

## Clôture des lots 5 et 6 — 2026-11-07 (fin de session)

- [status] **Change `refondre-parcours-resultats` : 20/20 tâches**, lots 1–6 terminés et poussés. Commits du jour : lot 5 `a6225ea` (5.1 inventaire Modèles + Utiliser), `3afbf23` (5.2 ajout replié + tailles lisibles), `d58c36e` (5.3 unités/aides/liens Moteurs-Audios), `c3f6757` (correctifs revue fin lot 5) ; lot 6 `eab10c9` (6.1 observation + décision c), `85a5d35` (6.2 preuves CI), `d5780e8` (6.3 aperçu fusion D7), `0b7e004` (correctifs revue fin lot 6).
- [decision] Workers en **deepseek flash / thinking high** à la demande du propriétaire (repli Haiku 5.5/high jamais nécessaire) ; orchestration par tâche : worker → relecture/correctifs principal → navigator Sonnet 5.5 medium → correctifs → push ; revue advisor Opus 5.5 medium en fin de lot, puis push. Le propriétaire a demandé de ne jamais s'arrêter sur incertitude : le seul arrêt légitime reste la décision nécessaire ou le bilan final.
- [decision] **6.1 sans-JS et sombre réel : NON OBSERVÉS, clôturés sur décision explicite du propriétaire (« seule réponse possible : c »)**, comme en 1.5. Outillage : les 22 outils Playwright du profil navigator n'ont ni `javaScriptEnabled` ni `emulateMedia` ; `chrome_devtools` non configuré ; MCP/hôte intouchables. L'option d'un script CDP ad hoc (conseillée par advisor) a été écartée comme réouverture de la décision « outillage reporté ». Ne jamais présenter ces modes comme vérifiés.
- [validation] Preuves : 1133 tests locaux OK ; CI « Tests Linux et Windows » (job « Tests sans moteur réel ») verte à chaque push ; observations navigateur clair+JS à 1280/360 (lots 4, 5, 6) ; aperçu de fusion D7 isolé (/tmp, 4 RENAMED / 18 MODIFIED / 10 ADDED, copie validée 9/9, matrice D7 préservée, specs moteurs et plateforme intactes, mesures système non synchronisées). `openspec validate --all --strict` 9/9. **Aucun archivage ni synchronisation réelle** (pas de demande dédiée) ; ordre de fusion futur : Sumi → première lecture → présent change.
- [limit] Limites finales déclarées : sans-JS et sombre non observés (décision c) ; aucune mesure représentative du PC utilisateur ; aucune validation Windows locale ; flau d'intermittence arrêt/interruption (`test_arret_utilisateur_interrompu_conserve_les_resultats`, famille « pid vide ») toujours ouvert — un rerun vert n'est jamais une preuve ; aucune validation utilisateur de la nouvelle interface ; scénarios OpenSpec = identifiants stables (un bloc MODIFIED ne peut pas les renommer depuis le socle courant).
- [next] Pour livrer : demande dédiée d'archivage/synchronisation (D7), ou suite du change de mesures système (0/12) qui reste indépendant. Changer de modèle de worker reste possible à tout moment ; la méthode par tâche ci-dessus est reproductible.
