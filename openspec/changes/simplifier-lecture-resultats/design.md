# Design

## Context

Voir `proposal.md` pour le besoin. Analyse du 2026-11-04, base `931e2a5` : `comparaison.html` reste un tableau champs × résultats ; les trois longs paragraphes techniques encadrent le texte. `consultation_resultats.py` lit les mesures par audio, mais `EntreeEmpreinte` ne les expose pas au classement. Les listes n'ont pas de tri paramétrable. `formats.html` affiche les durées à trois décimales et la mémoire en octets.

Conseil advisor avant rédaction et observations navigator Sonnet 5.5 high : retenir les synthèses courtes et chiffres avec unités d'Artificial Analysis, la densité de lignes et les variantes explicites de DeepSWE. Ne pas copier les graphiques, les scores, les couleurs de verdict ou les incertitudes ; Arena non observé (Cloudflare). Ce ne sont pas des validations de notre futur rendu.

## Goals / Non-Goals

**Goals:** lecture en quelques secondes de deux textes et trois indicateurs ; classement de mesures observées par audio ; conservation intégrale des données historiques en lecture ; aucune nouvelle dépendance.

**Non-Goals:** refonte des formulaires de préparation, nouveau menu, nouvelles mesures, score qualité/WER, diff textuel, graphiques, énergie, date de publication des modèles, taille disque, agrégat multi-audios, répétitions automatiques, dédoublonnage des configurations.

## Decisions

### D1. Trois indicateurs puis le texte, pas une fiche technique

Deux `article` dans `div.grid.cols-2` pour le cas courant ; au-delà de deux résultats, la même grille conserve toutes les cartes sélectionnées, sans changer la limite de sélection existante. Modèle court + moteur en titre ; réglage distinctif (variante ou threads) en sous-titre seulement s'il est utile. L'identifiant complet, la révision et la date restent accessibles ; la date distingue les essais répétés.

Ordre de carte : titre, marques/état si nécessaire, trois valeurs, annotation RAM conditionnelle, texte complet, accès aux détails. La synthèse se limite à « Plus rapide : A · Moins de RAM : B », avec égalités explicites. Le CPU est visible mais son minimum n'est pas vanté comme un vainqueur : faible occupation et rapidité ne sont pas équivalentes.

Exemple fictif de carte (ni données réelles ni nouveau moteur) :

```text
Modèle A · moteur X
Transcription   42 s
Mémoire max      2,4 Go sur 16 Go · 15 %
CPU du moteur   50 % en moyenne
[texte intégral de la transcription]
```

Alternative rejetée : une nouvelle table verticale avec trois mesures ajoutées ; elle conserve l'effort de recherche visuelle qui motive le changement.

### D2. Ratios calculés, sans retoucher les fichiers

Lire `machine` de l'exécution concernée, pas le matériel local présent. CPU = `100 * temps_cpu_s / (duree_transcription_s * coeurs_logiques)` ; RAM = `100 * pic_memoire_octets / ram_totale_octets`. Les temps existants viennent du même encadrement d'inférence (`engines/runner.py`, autour de la boucle de fenêtres). Valider types (exclure booléens), finitude, numérateurs >= 0, dénominateurs > 0, compte logique entier positif ; un ratio hors 0..100 reste incohérent, pas tronqué. Les bornes CPU/murales ne sont pas parfaitement simultanées et les compteurs peuvent être grossiers, notamment sous Windows : un léger dépassement n'est pas une surcapacité, seulement un ratio non interprétable. L'absence d'une capacité empêche le ratio mais pas l'affichage de la mesure brute disponible.

Le CPU est une moyenne du seul processus moteur (threads compris), pas une charge instantanée, le total de l'application, une puissance électrique ou une marge garantie. 100 % désigne les processeurs logiques visibles OS ; hyperthreading, quotas, affinité et virtualisation limitent l'interprétation. Ne pas appeler ce ratio « effort », « difficulté » ou « ordinateur utilisé ».

Le pic RSS existant reste cumulatif et inclut modèle, bibliothèques et buffers ; aucune somme avec le RSS serveur ni soustraction pour calculer la marge restante. Annotation visible si son ordre dans la demande n'est pas le premier (même si un audio précédent a échoué) ; en cas d'ordre non vérifiable, indiquer que le pic n'est pas isolé. Le contexte système réel est une autre mesure, définie dans `mesurer-charge-systeme`.

### D3. Formats partagés et tri avant arrondi

Formats français au premier niveau : sous une seconde, dixième de seconde ou « < 0,1 s » si positif ; secondes entières puis `1 min 37 s` et heures/minutes. Mo = 10^6 octets, Go = 10^9 octets ; une décimale utile, et une borne « < » pour les petites valeurs positives. Pourcentages entiers avec « < 1 % » si positif sous 1 ; 0 reste 0 si réellement mesuré. Détail avec valeurs brutes et unités explicites. Le formatage des horodatages de segments n'est pas modifié.

Enrichir la vue des entrées de groupe avec mesures, date, état, matériel et ordre, déjà accessibles via les JSON lus. Sur `GET /resultats/comparaison`, `tri=temps|ram|cpu|recent`, omission = temps ; valeur inconnue ou paramètre dupliqué = 400. Le tri s'applique aux listes de résultats de tous les groupes ; un lien d'ancre ramène au groupe choisi. Les cases cochées non soumises ne sont pas conservées lors d'un changement de tri (limite explicite du HTML sans JS). La sélection soumise reste validée par le service, sans modifier ses bornes ; `/resultats/comparaison/<empreinte>` garde l'ordre reçu et n'a pas de tri de colonnes. Tri sur durées/pics/ratios non arrondis ; absents/incohérents à la fin ; départage par date décroissante puis identifiant d'exécution et ordre audio. Date d'essai = `cree_le` de l'exécution ; date inconnue après les dates connues. Pas de colonne « meilleur ».

Les mesures factices sont dans une sous-liste distincte marquée au sein de chaque groupe audio et ne concourent pas avec les réelles. Les résultats partiels gardent leur état et n'ont pas de badge ; les valeurs disponibles restent consultables et triables. Les différences de moteur, modèle, threads et réglages font partie de l'expérience, pas d'une interdiction de comparer.

### D4. Deux niveaux de détail et une aide, suppression réelle de texte

Niveau principal : noms, date courte, trois indicateurs, texte et alertes utiles. Deux entrées secondaires : « Ce qui diffère » (valeurs différentes uniquement ; valeurs communes résumées) et « Toutes les mesures et informations » (chargement, durées essai/processus, RTF avec repère 2, CPU cumulé, fichiers, segments, paramètres, versions, matériel et provenance). Les segments horodatés peuvent garder leur propre détail dans le résultat individuel. Pas d'arborescence d'accordéons imbriqués pour le cas courant.

Déplacer les paragraphes sur SHA-256, JSON brut, null, RTF et lecture seule dans une aide locale servie par une nouvelle route GET fixe `/resultats/aide`, liée depuis les résultats (aucune entrée de menu supplémentaire). La route fixe reste distincte de la route dynamique du détail. Éviter le simple remplacement d'un paragraphe par son équivalent dans chaque carte. Cible rédactionnelle : au plus une phrase d'introduction de 25 mots ; une synthèse courte ; aucune explication répétée par résultat. Ce budget exclut texte transcrit, valeurs, noms, alertes conditionnelles et détails ouverts par choix utilisateur. Vérification visuelle et éditoriale plutôt qu'un test fragile de nombre total de mots.

Le résultat individuel suit la même tête de lecture ; la liste globale des essais reste complète et respecte la spec « Liste des exécutions ». Conserver et mettre en avant le lien existant vers les groupes/classements depuis Résultats. Ne pas modifier le menu à huit liens ni la spec Sumi en cours ; aucune route existante supprimée, seule l'aide a une nouvelle route.

### D5. Rendu dans les bornes actuelles

`article`, `dl`, `strong`, `small`, `details/summary` et classes Sumi déjà autorisées suffisent a priori ; aucune nouvelle CSS prévue. Pas de badges fondés sur la seule couleur. Les avertissements, erreurs, marques, textes et boutons restent hors détails fermés selon Sumi D8. Tests de classes et de propriétés conservés.

## Risks / Trade-offs

- [Pic RAM cumulatif] → annotation visible ; aucune promesse de mesure isolée par audio.
- [CPU bas interprété comme efficacité] → libellé d'occupation, durée affichée à côté, aide sur les limites ; aucun badge de supériorité CPU.
- [Matériel similaire pris pour identique] → comparaison d'OS, architecture, processeurs logiques et RAM totale pour détecter différences/inconnus (nom CPU facultatif informatif), jamais preuve d'identité ; une mention courte sur différences visibles, détails des threads inconnus et des réglages.
- [Empilement mobile] → lecture linéaire assumée ; pas de tableau contenant les textes.
- [Changements Sumi/documentation actifs] → pas d'édition simultanée des mêmes gabarits ; conserver les tâches et limites non vérifiées de Sumi, sans archivage implicite. Aligner le guide sur les écrans finaux.

## Migration Plan

1. Implémenter consultation/ratios/formats et tests synthétiques ; aucune migration des résultats.
2. Ajouter classement puis comparaison/détail et aide locale, garder navigation et URLs existantes.
3. Observer le cas courant sans encart d'alerte à 1280 × 800 : synthèse, titres, trois indicateurs de chaque carte et début des deux textes sans défiler ; à 360 px : titre et indicateurs de première carte accessibles d'emblée, textes complets en défilement vertical, aucun débordement de page. Cas longs/absents/partiels/factices/égalités.
4. Vérifier clair/sombre réel et navigation clavier ; relever toute impossibilité d'émulation comme limite non validée, pas comme preuve.
5. Aligner le guide et consigner les validations. L'observation système peut suivre via son propre change, qui n'écrase aucun requirement de celui-ci. Retour arrière limité aux gabarits et à la consultation, sans perte de données.
