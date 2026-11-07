# results-comparison Specification

## Purpose
Permet de relire les transcriptions produites avec leurs métadonnées et mesures, et de comparer pour un même audio les résultats de différents modèles, moteurs et réglages.

## Requirements

### Requirement: Liste des exécutions
L'interface SHALL lister les exécutions, des plus récentes aux plus anciennes, avec leur date, modèle, moteur, état, nombre d'audios traités et durée totale.

#### Scenario: Consultation de l'historique
- **WHEN** l'utilisateur ouvre la page des résultats
- **THEN** toutes les exécutions enregistrées apparaissent, y compris celles en échec ou interrompues

### Requirement: États des exécutions affichés
Chaque exécution MUST afficher un état explicite et distinct : en cours, terminée, interrompue, abandonnée ou en échec. Les résultats partiels d'une exécution non terminée MUST être accessibles et signalés comme partiels, sans être présentés comme un lot complet.

#### Scenario: Exécution abandonnée
- **WHEN** une exécution a été laissée en cours après un arrêt brutal du serveur
- **THEN** elle apparaît avec l'état abandonné, ses transcriptions disponibles sont consultables et les audios non traités sont signalés

#### Scenario: Comparaison avec un résultat partiel
- **WHEN** l'utilisateur compare des résultats dont certains proviennent d'une exécution non terminée
- **THEN** ces résultats sont identifiés comme partiels

### Requirement: Détail d'une transcription
L'utilisateur SHALL pouvoir lire chaque transcription avec ses segments horodatés éventuels, ses métadonnées et ses mesures.

#### Scenario: Ouverture d'une transcription
- **WHEN** l'utilisateur ouvre une transcription
- **THEN** le texte, les réglages effectifs, les informations de modèle, de moteur et de machine, et les mesures sont affichés

### Requirement: Comparaison par audio
Pour un audio donné, l'interface SHALL afficher les transcriptions sélectionnées en cartes côte à côte sur grand écran et empilées sur petit écran, avec le modèle, le moteur, les trois indicateurs principaux et le texte complet visibles. Les différences de configuration et les autres mesures SHALL être accessibles progressivement.

#### Scenario: Comparaison de deux modèles
- **WHEN** l'utilisateur sélectionne deux transcriptions d'un même audio produites par des modèles différents
- **THEN** les deux cartes montrent leur modèle, leur moteur, la durée de transcription de cet audio, le pic mémoire du moteur rapporté à la RAM totale et le CPU moyen du moteur rapporté aux processeurs logiques consignés, puis leur texte complet ; les différences de configuration et la durée totale de l'opération restent accessibles dans les détails

#### Scenario: Lecture sur petit écran
- **WHEN** deux transcriptions longues sont comparées à 360 px de large
- **THEN** leurs cartes s'empilent, le texte se replie sans défilement horizontal de la page et aucune transcription n'est cachée dans un accordéon fermé

### Requirement: Identité de l'audio comparé
Les transcriptions SHALL être regroupées par empreinte du fichier audio, et non par son seul nom ; les transcriptions de fichiers de même nom mais d'empreintes différentes MUST NOT être présentées comme comparables.

#### Scenario: Fichier modifié sous le même nom
- **WHEN** un audio est remplacé par un fichier différent portant le même nom
- **THEN** les transcriptions de l'ancien et du nouveau fichier apparaissent dans des groupes distincts

### Requirement: Distinction des résultats factices
Les résultats produits par le moteur factice MUST être signalés comme factices dans toutes les vues.

#### Scenario: Liste mêlant résultats réels et factices
- **WHEN** la page des résultats contient une exécution du moteur factice
- **THEN** cette exécution est marquée comme factice

### Requirement: Indicateurs principaux de chaque transcription
Le détail d'un résultat et la comparaison SHALL présenter immédiatement la durée de transcription, la mémoire maximale du moteur et son occupation CPU moyenne. Le chargement et les audios antérieurs inclus dans le pic mémoire MUST être distingués de la seule inférence ; la durée totale d'un lot MUST NOT être présentée comme la durée d'un audio.

#### Scenario: Lot de plusieurs audios
- **WHEN** un audio n'est pas le premier dans l'ordre de la demande
- **THEN** sa durée affichée est sa durée de transcription et une annotation visible indique que son pic mémoire cumulatif peut provenir d'un audio précédent ; l'aide précise que le chargement du modèle est inclus

#### Scenario: Indicateur absent ou partiel
- **WHEN** une mesure manque ou correspond à un relevé partiel
- **THEN** l'interface affiche « non mesuré » ou l'indication de mesure partielle, sans remplacer l'absence par zéro ni attribuer une distinction sur la valeur manquante ou partielle

### Requirement: Ratios rapportés au matériel consigné
L'occupation CPU du moteur SHALL être calculée par 100 × temps CPU / (durée de transcription × processeurs logiques). La part de RAM SHALL être calculée par 100 × pic mémoire / RAM totale. Seules les valeurs finies et valides de l'essai consigné MUST être utilisées, jamais celles de l'ordinateur qui consulte le résultat.

#### Scenario: Calcul CPU interprétable
- **WHEN** un audio a consommé 8 secondes CPU en 2 secondes de transcription sur 8 processeurs logiques
- **THEN** le CPU moyen du moteur vaut 50 %, avec une aide précisant que 100 % représente l'occupation de tous les processeurs logiques visibles par le système, sans mesurer la difficulté du calcul, l'énergie ni la fluidité

#### Scenario: Ancien résultat ou valeur incohérente
- **WHEN** un résultat ancien contient les valeurs brutes nécessaires, ou qu'un dénominateur manque, est nul ou qu'un ratio dépasse 100 %
- **THEN** le ratio est calculé en lecture dans le premier cas ; dans les autres cas il est indisponible ou signalé incohérent, jamais borné silencieusement à 100 %, et aucun fichier n'est réécrit

### Requirement: Formats lisibles des indicateurs
Les indicateurs principaux SHALL employer des durées adaptées en secondes, minutes ou heures, de la mémoire en Mo ou Go décimaux et des pourcentages clairement nommés. Les valeurs brutes et leur précision SHALL rester accessibles en détail ; un nombre positif MUST NOT être présenté comme zéro par l'arrondi.

#### Scenario: Trois valeurs immédiatement compréhensibles
- **WHEN** une carte possède une durée de 97 secondes, un pic de 2400000000 octets sur 16000000000 octets et un CPU moyen de 0,4 %
- **THEN** elle affiche « Transcription : 1 min 37 s », « Mémoire max : 2,4 Go sur 16 Go — 15 % » et « CPU du moteur : < 1 % en moyenne », sans octets ni secondes CPU cumulées au premier niveau

### Requirement: Classement choisi par audio
Chaque groupe d'audio SHALL proposer tous ses résultats sans dédoublonnage silencieux, triables par temps de transcription, pic RAM, occupation CPU du moteur ou date d'essai. Le tri par défaut SHALL être le temps croissant ; les valeurs absentes ou incohérentes viennent après les valeurs valides, et les égalités ont un départage stable.

#### Scenario: Changement de critère
- **WHEN** l'utilisateur choisit « Moins de RAM », « CPU le moins occupé » ou « Essais récents »
- **THEN** une requête de lecture ordonne respectivement les pics mémoire croissants, les ratios CPU moteur croissants ou les dates décroissantes, avant arrondi ; la liste conserve date et réglages distinctifs de chaque résultat

#### Scenario: Tri borné et sélection HTML explicite
- **WHEN** une requête de classement fournit un tri inconnu ou répété
- **THEN** elle est refusée par une erreur explicite sans lancer d'opération ; un tri valide réordonne les listes de résultats des groupes d'audios et renvoie vers l'ancre du groupe choisi, sans promettre de conserver des cases cochées non soumises

#### Scenario: Ordre de la comparaison sélectionnée
- **WHEN** l'utilisateur soumet les résultats à comparer
- **THEN** la comparaison conserve l'ordre de la sélection reçue, validée selon les règles existantes, indépendamment du paramètre de tri des listes

#### Scenario: Résultats factices et incomplets
- **WHEN** un groupe contient des mesures simulées ou des résultats partiels
- **THEN** ils restent accessibles et identifiés, les factices sont séparés des résultats réels dans le classement, et aucune mesure simulée ou partielle ne reçoit de distinction de performance réelle

### Requirement: Contexte comparatif sans score global
Une synthèse courte SHALL décrire séparément les résultats observés les plus rapides et les moins consommateurs de RAM, sans score global ni jugement de qualité. Les différences de matériel consigné, les données de contexte inconnues et les biais de pic mémoire MUST être visibles sans ouvrir les détails ; modèle, moteur et réglages différents restent comparables comme configurations testées.

#### Scenario: Matériel différent ou inconnu
- **WHEN** les valeurs consignées d'OS, d'architecture, de processeurs logiques ou de RAM totale diffèrent ou manquent entre deux essais
- **THEN** les valeurs restent affichées et triables avec une mention « matériel différent » ou « matériel non vérifié » ; le nom du CPU est informatif et son absence seule ne déclenche pas d'alerte, mais une différence connue reste consultable ; des métadonnées identiques ne prouvent jamais l'identité de la machine

#### Scenario: Un seul passage par essai
- **WHEN** la synthèse présente un résultat en tête
- **THEN** elle indique qu'il s'agit de mesures observées, sans intervalle d'incertitude inventé, sans performance garantie et sans assimiler faible occupation CPU à meilleure efficacité ou à meilleur texte

### Requirement: Détails progressifs et explications regroupées
Les vues de résultats SHALL privilégier les textes transcrits et les trois indicateurs, puis proposer les différences de configuration et enfin toutes les mesures et métadonnées. Les explications générales SHALL être regroupées dans une aide locale ; erreurs, états partiels, marques de simulation et avertissements utiles restent visibles.

#### Scenario: Lecture sans détails techniques
- **WHEN** l'utilisateur ouvre une comparaison
- **THEN** il voit les modèles, moteurs, indicateurs et textes sans ouvrir de détail ; empreintes, chemins, versions, temps CPU cumulé, chargement et RTF avec son repère restent consultables mais ne précèdent pas les textes

#### Scenario: Accès aux résultats et à tout l'historique
- **WHEN** l'utilisateur consulte Résultats
- **THEN** l'accès existant aux groupes d'audios et à leur classement est mis en avant, et l'historique complet des exécutions reste accessible des plus récentes aux plus anciennes avec date, modèle, moteur, état, nombre d'audios et durée totale, y compris échecs et résultats sans empreinte valide
