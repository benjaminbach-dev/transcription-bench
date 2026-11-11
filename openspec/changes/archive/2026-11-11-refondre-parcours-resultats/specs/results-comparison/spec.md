## MODIFIED Requirements

### Requirement: Liste des exécutions
La page Résultats SHALL présenter en priorité les résultats regroupés par audio, triables à l'intérieur de chaque groupe. Un historique secondaire dans Exécutions conserve tous les essais, des plus récents aux plus anciens, avec date, modèle, moteur, état, audios traités et durée totale. Aucun échec ni résultat sans empreinte valide ne disparaît de cet historique.

#### Scenario: Consultation de l'historique
- **WHEN** l'utilisateur ouvre Résultats
- **THEN** il voit d'abord les résultats par audio et un accès à l'historique complet dans Exécutions, qui conserve toutes les exécutions enregistrées, y compris en échec, interrompues, sans transcription ou sans empreinte exploitable, sans que leurs identifiants techniques dominent la liste principale

### Requirement: Détail d'une transcription
L'utilisateur SHALL lire chaque transcription avec un résumé compact du modèle, de la durée audio, du pic RAM moteur, du CPU moyen moteur, du moteur et du temps de transcription. Le texte complet suit immédiatement ; segments, réglages effectifs, machine, identifiants et mesures brutes restent accessibles en détail sans répéter le résumé.

#### Scenario: Ouverture d'une transcription
- **WHEN** l'utilisateur ouvre une transcription
- **THEN** le modèle et les valeurs lisibles précèdent le texte, tandis que réglages, informations complètes de modèle/moteur/machine, segments éventuels et mesures brutes ne constituent pas un second résumé visible par défaut

### Requirement: Comparaison par audio
Comparaisons SHALL permettre de choisir des transcriptions regroupées par empreinte audio, puis de lire les sélections côte à côte sur grand écran et empilées sur petit écran. Le choix affiche les mêmes valeurs compactes que Résultats ; les cartes finales mettent modèle et ressources avant les détails techniques et conservent le texte complet visible.

#### Scenario: Comparaison de deux modèles
- **WHEN** l'utilisateur sélectionne deux transcriptions d'un même audio
- **THEN** il voit deux cartes avec modèle, durée audio, pic RAM, CPU moteur, moteur et temps de transcription, puis les textes complets ; réglages différents et durée totale de l'opération restent consultables en détail

#### Scenario: Lecture sur petit écran
- **WHEN** deux transcriptions longues sont comparées à 360 px
- **THEN** les cartes s'empilent, leurs indicateurs sont lisibles sans défilement horizontal et aucun texte de la comparaison sélectionnée n'est enfermé dans un détail fermé

### Requirement: Indicateurs principaux de chaque transcription
Résultats, sélection comparative, détail et comparaison SHALL afficher modèle, pic RAM moteur, CPU moyen moteur, moteur et temps de transcription distinct. La durée décodée de l'audio figure dans l'entrée ou l'en-tête commun de son groupe. La durée d'un lot ne remplace jamais une durée audio ; RAM cumulative et états partiels restent signalés sans longs paragraphes répétés.

#### Scenario: Lot de plusieurs audios
- **WHEN** un audio n'est pas le premier dans la demande
- **THEN** sa durée audio et son temps de transcription restent propres à cet audio, et une mention courte signale son pic RAM cumulatif ; l'explication générale figure une seule fois dans l'aide

#### Scenario: Indicateur absent ou partiel
- **WHEN** une mesure manque ou est partielle
- **THEN** son emplacement affiche « non mesuré » ou « partiel », sans zéro inventé ni distinction attribuée sur cette valeur

### Requirement: Formats lisibles des indicateurs
Toutes les vues de premier niveau SHALL afficher durées en s/min/h, RAM en Mo/Go décimaux, CPU en pourcentage moyen explicitement attribué au moteur et dates courtes. Les valeurs brutes restent en détail. Les valeurs positives ne sont jamais arrondies à zéro ; durée audio et temps de transcription ont des libellés distincts.

#### Scenario: Trois valeurs immédiatement compréhensibles
- **WHEN** un audio dure 180 secondes et sa transcription prend 97 secondes avec un pic de 2400000000 octets et un CPU moyen de 0,4 %
- **THEN** la vue affiche « Audio : 3 min », « Transcription : 1 min 37 s », « RAM moteur : 2,4 Go » et « CPU moteur : < 1 % », sans octets ni secondes CPU cumulées au premier plan ; capacité et part RAM restent accessibles en détail

### Requirement: Classement choisi par audio
Chaque groupe SHALL conserver ses résultats sans dédoublonnage, triables par temps de transcription, pic RAM moteur, occupation CPU moteur ou date. Un critère commun à la page ordonne les entrées à l'intérieur de chaque groupe, jamais les audios entre eux. Comparaisons utilise le temps croissant par défaut ; valeurs absentes/incohérentes en fin et départage stable. Les valeurs classées restent visibles.

#### Scenario: Changement de critère
- **WHEN** l'utilisateur choisit Plus rapides, Moins de RAM, CPU le moins occupé ou Plus récents
- **THEN** les résultats sont ordonnés sur les valeurs brutes correspondantes, et les valeurs temps/RAM/CPU restent visibles avec date courte et variante utile ; « Plus rapides » utilise le temps de transcription, jamais la durée source ni un score global

#### Scenario: Tri borné et sélection HTML explicite
- **WHEN** une requête contient un tri inconnu ou dupliqué, ou une sélection invalide, disparue ou extérieure au groupe
- **THEN** elle est refusée sans opération ; un changement de tri valide conserve les cases sélectionnées encore présentes, y compris sans JavaScript, et aucun résultat masqué n'est comparé sans être identifié dans la sélection

#### Scenario: Ordre de la comparaison sélectionnée
- **WHEN** l'utilisateur soumet une sélection valide
- **THEN** la comparaison conserve l'ordre reçu et les bornes de sélection existantes

#### Scenario: Résultats factices et incomplets
- **WHEN** des résultats réels, factices et partiels coexistent
- **THEN** les factices sont séparés des réels, les états restent visibles et aucune valeur simulée ou partielle ne reçoit de distinction de performance réelle

### Requirement: Détails progressifs et explications regroupées
Les vues SHALL mettre les informations demandées avant la provenance technique. Date courte et variante utile restent secondaires, sans ajouter de longues colonnes d'identifiants ou de réglages. Aide générale, différences et métadonnées complètes restent accessibles sans répétition systématique entre en-tête, corps et pied d'un même résultat.

#### Scenario: Lecture sans détails techniques
- **WHEN** l'utilisateur ouvre un résultat ou une comparaison sélectionnée
- **THEN** il voit modèle, durée audio, RAM, CPU, moteur, temps de transcription et texte, sans chemins, SHA-256, versions, PID, réglages complets ou paragraphes méthodologiques avant le texte

#### Scenario: Accès aux résultats et à tout l'historique
- **WHEN** l'utilisateur ouvre Résultats
- **THEN** les chiffres et contrôles de classement sont au premier plan ; un lien vers l'historique d'Exécutions et l'aide locale restent accessibles au second plan

### Requirement: Contexte comparatif sans score global
Les meilleures valeurs observées de temps et de RAM SHALL être signalées directement près des mesures, par couleur et libellé court, sans répéter les modèles dans une synthèse en prose ni attribuer de score global. Une faible occupation CPU n'est pas présentée comme une meilleure efficacité. Les différences ou inconnues de matériel restent signalées de façon concise.

#### Scenario: Matériel différent ou inconnu
- **WHEN** OS, architecture, processeurs logiques ou RAM totale diffèrent ou manquent entre essais
- **THEN** une alerte courte reste visible et les valeurs consignées restent consultables ; le nom CPU seul manquant ne déclenche pas d'alerte et des métadonnées identiques ne prouvent pas l'identité de la machine

#### Scenario: Un seul passage par essai
- **WHEN** une valeur de temps ou RAM est signalée en tête sur des résultats réels complets
- **THEN** le libellé décrit une mesure observée, égalités comprises, sans performance garantie, incertitude inventée ni jugement sur le texte ; factices et partiels ne reçoivent pas de distinction

## ADDED Requirements

### Requirement: Liste principale utile sans ouvrir un résultat
Résultats SHALL afficher un groupe par empreinte audio, nommé par le fichier et sa durée décodée commune. Chaque entrée montre modèle court, temps de transcription, RAM moteur, CPU moteur, moteur et date courte secondaire. Les groupes sont ordonnés par leur essai le plus récent ; le tri initial interne est la date décroissante. L'identifiant interne n'est pas le titre.

#### Scenario: Résultats de plusieurs exécutions
- **WHEN** plusieurs audios et essais sont enregistrés
- **THEN** la liste conserve chaque essai et affiche ses mesures sans clic préalable ; l'utilisateur peut trier les essais dans chaque groupe par date, temps de transcription, RAM ou CPU, sans classement de rapidité entre audios différents

#### Scenario: Même nom et configurations proches
- **WHEN** deux résultats ont un nom de modèle ou de fichier identique mais des variantes, révisions ou empreintes différentes
- **THEN** une désambiguïsation courte les distingue sans fusionner leurs données ; les détails donnent l'identité complète et aucune comparaison inter-empreintes n'est autorisée ; si des durées décodées consignées diffèrent dans un groupe, elles sont affichées sur les entrées concernées au lieu d'une durée commune trompeuse

### Requirement: Densité maîtrisée des résultats
Le premier niveau SHALL être composé de blocs courts et alignés, pas d'une phrase technique concaténant tous les champs. Les valeurs de ressources sont visuellement plus saillantes que leurs libellés et les informations secondaires. Les dates et variantes ne repoussent pas les mesures derrière des colonnes hors écran.

#### Scenario: Recette du cas courant sur bureau
- **WHEN** Résultats puis la sélection Comparaisons contiennent au moins quatre essais aux noms courts et sont observés à 1280 × 800
- **THEN** au chargement initial, sous la navigation, au moins trois entrées du premier groupe et leurs valeurs principales sont lisibles sans défilement vertical, sans ouvrir de détail et sans défilement horizontal

#### Scenario: Recette de la comparaison sélectionnée
- **WHEN** deux transcriptions courantes sans alerte sont observées à 1280 × 800
- **THEN** les deux modèles, leurs mesures principales et le début des deux textes sont visibles sans défilement vertical ; les mêmes valeurs restent accessibles à 360 px dans la première carte sans défilement horizontal
