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
