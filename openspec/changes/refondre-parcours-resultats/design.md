# Design

## Context

Voir `proposal.md` pour le besoin. Base inspectée : `5e0cfc7`, le 2026-11-06 ; l'utilisateur confirme son application locale à jour. Lecture des gabarits et services, pas nouvelle observation navigateur :

- `resultats.html` affiche surtout identifiant/date/modèle/état ; les ressources n'y figurent pas.
- `comparaisons.html` propose les quatre tris mais ses dix colonnes ne contiennent aucune des mesures classées.
- `formats.html` a déjà les formats SI et ratios moteur, mais les macros brutes restent utilisées ailleurs ; `indicateurs_resultats.py` est pur et réutilisable.
- `executions.html` répète formulaire et explications par modèle. Une référence `ModelePropose.reference` inclut déjà moteur et clé ; moteur et modèle ne sont donc pas deux choix indépendants.
- Les routes POST revalident les demandes et le créneau unique est centralisé. `ExecutionMoteur.derniere_execution()` ne décrit que la dernière exécution close, pas l'identité de celle en cours ; `cible` du créneau est le modèle et non un identifiant de résultat.
- Les specs principales sont antérieures aux deltas Sumi et première lecture, toujours actifs. La rédaction doit distinguer exigences désirées, réalisation et preuves.

Conseil advisor obtenu dans cette session : regrouper par audio, cinq valeurs utiles par ligne, date secondaire, ressources colorées plutôt que synthèse en prose ; vanilla local ; ne jamais supposer la compatibilité entre formats de modèles. La suggestion d'archiver les anciens changes avec des contrôles remplacés n'est pas retenue : aucun contrôle non exécuté ne devient validé et aucun archivage n'est autorisé par cette tâche.

## Goals / Non-Goals

**Goals:** une surface par intention ; un composant de résultat partagé ; retrouver valeurs et tris là où l'on choisit les résultats ; aucune migration JSON ; interactions HTML fiables avant amélioration JS.

**Non-Goals:** SPA, nouveau framework de serveur, chaîne Node, dépendance front-end, conversion de modèles, installation implicite, graphique, score qualité, nouvelle mesure système, réécriture des essais, suivi continu CPU/RAM.

## Decisions

### D1. Architecture des pages et compatibilité

| URL | Rôle final |
| --- | --- |
| `/resultats` | Entrée principale : groupes audio, lignes de résultats compactes, tris, lien vers texte/détail |
| `/resultats/comparaison` | Choisir dans un groupe audio les transcriptions à comparer, mêmes lignes compactes et cases de sélection |
| `/resultats/comparaison/<empreinte>` | Cartes sélectionnées et textes complets, puis différences/détails |
| `/executions` | Opération active s'il y en a une, préparation unique, historique technique secondaire, diagnostics de dossiers |
| `/modeles` | Inventaire local d'abord, accès secondaire Ajouter un modèle |
| `/moteurs`, `/audios` | Gestion existante, textes et unités de premier niveau harmonisés |
| `/` | Redirection GET locale vers `/resultats` |
| `/operation` | Redirection GET locale vers `/executions#operation`, message d'action borné conservé |

Conserver les POST existants et changer leurs cibles de redirection ; ne pas rediriger un POST d'action vers une autre action. Pour `/operation`, seuls `action=arret-demande` et `action=arret-incomplet` sont traduits vers les messages locaux connus ; aucun paramètre de redirection libre n'est transmis. L'ancienne vérification des dossiers reste accessible dans les diagnostics d'Exécutions, sans remettre l'accueil au menu. État d'erreur toujours rendu avec son vrai statut.

Alternative rejetée : renommer les URL de consultation et supprimer les anciens chemins, sans bénéfice utilisateur et avec davantage de ruptures. La navigation est indépendante de l'organisation historique des routes.

### D2. Contrat de densité et maquette de contenu

Résultats est regroupé par empreinte audio : le nom du fichier et la durée décodée commune sont écrits une seule fois au titre du groupe. Les groupes restent distincts pour deux empreintes de même nom. Si une durée consignée diffère à empreinte identique, montrer ce désaccord au lieu d'inventer une durée commune. Résultats ordonne les groupes par l'essai le plus récent, puis applique le tri choisi à leurs entrées (date décroissante par défaut). Comparaisons garde temps croissant par défaut. Aucun classement de rapidité entre audios différents. Le critère `tri` est commun à la page et s'applique dans chaque groupe, comme dans le service existant. Pour conserver les cases sans JS, les boutons de tri sont des boutons GET du formulaire de sélection (`name=tri`, `formaction` vers la liste) ; la route de liste accepte et revalide `transcription` selon les mêmes identités que la comparaison, avec 400 si sélection invalide/disparue/hors groupe. Les sélections des autres groupes ne sont pas fusionnées. Les paramètres multiples légitimes sont bornés à la taille maximale déjà autorisée, et les champs de tri restent uniques.

Maquette illustrative, valeurs entièrement fictives :

```text
entretien.wav · Audio 3 min
[Plus récents] [Plus rapides] [Moins de RAM] [CPU le moins occupé]

Modèle                       Transcription     RAM moteur    CPU moteur    Moteur        Date
whisper-large-v3-turbo        1 min 37 s         2,4 Go        50 %          faster-whisper 06/11 14:20
parakeet-tdt-0.6b-v3           42 s               3,1 Go        61 %          transformers  06/11 14:10
```

Ce n'est pas une longue phrase par ligne : modèle dominant, cinq valeurs courtes alignées (modèle, temps, RAM, CPU, moteur), date secondaire. Sur mobile le même DOM devient un bloc étiqueté, pas un tableau à déplacer horizontalement. La sélection comparative ajoute une case dans la cellule modèle, pas une colonne technique. Identifiant d'exécution jamais titre de ligne ; version, threads et révision uniquement si nécessaires à une désambiguïsation courte, sinon en détail. Noms longs se replient sans limiter la valeur au seul tooltip.

Au premier niveau : RAM en Go/Mo SI, CPU moteur moyen en %, durée audio et temps de transcription en s/min/h, dates françaises courtes ; aucune taille en octets ni temps CPU cumulé. Conserver les calculs validés et le tri sur les valeurs brutes. Une occupation CPU plus faible n'est pas un score d'efficacité. La RAM est toujours un pic du moteur incluant le chargement et pouvant provenir d'un audio antérieur : marque courte et explicable, pas paragraphe par ligne. Capacité et ratio RAM deviennent des informations détaillées plutôt que d'allonger chaque cellule.

Factices séparés à l'intérieur du groupe, distinction textuelle compacte ; partiels, erreurs et matériel différent/inconnu restent visibles. Ne pas masquer ces états pour atteindre un budget de densité.

### D3. Comparaison et texte

Le composant de valeurs est partagé entre listes, résultat individuel et comparaison finale. Dans la comparaison d'un même audio, sa durée commune est dans l'en-tête, les cartes portent modèle, moteur, temps, RAM et CPU puis le texte complet. Le texte n'apparaît pas intégralement dans toutes les listes : un lien ouvre le détail.

Remplacer le paragraphe « Plus rapide : A · Moins de RAM : B » par un traitement directement près des meilleures valeurs : accent de couleur + libellé court, égalités comprises. Ne jamais distinguer les factices ou partiels comme meilleurs. « Ce qui diffère » et « Toutes les mesures et informations » restent accessibles sans répéter le texte ni afficher la même fiche au-dessus et au-dessous de la transcription.

Les observations système du change séparé ne sont pas des consommations moteur et ne deviennent pas des colonnes du classement. Si leur ajout intervient ensuite, le change de mesures réservera un bloc secondaire explicitement nommé, avec méthode et valeurs absentes, sans modifier les cinq valeurs de lecture. Cette refonte n'ajoute ni vue de données système ni exigence MODIFIED dépendant de ce change non implémenté ; sa présentation a été réconciliée dans ses propres artefacts après confirmation du propriétaire le 2026-11-07, sans modification de collecte ou stockage.

### D4. Préparation unique et dépendances des sélecteurs

Une référence locale réelle identifie modèle + révision + variante + moteur. Ne pas fusionner deux formats de poids sous un faux choix « même modèle » interchangeable. Le sélecteur Modèle donne un nom court et la variante utile ; moteur connu et unique présélectionné dans son propre contrôle. Un champ moteur soumis doit être cohérent avec la référence, vérifié côté serveur ; la référence existante reste source de vérité. Le moteur sert à restreindre les options compatibles, jamais à convertir des fichiers.

Audio unitaire par défaut ; mode lot optionnel avec sélection ordonnée, réutilisant le traitement séquentiel existant. Réglages avancés fermés par défaut, avec défauts déjà applicables. Préserver l'audio valide après changement de modèle ; réinitialiser les paramètres non applicables avec une seule indication. Ne pas garder des contrôles cachés mais actifs : toute famille non retenue doit être absente ou désactivée.

Implémentation progressive simple : préparation par GET ne recevant que les références non sensibles et choix audio, puis POST Lancer avec champs validés et jeton caché. Ces deux formulaires techniques forment un seul panneau utilisateur et ne répètent pas les sélecteurs. Avec JS, les sélections mettent à jour la préparation sans bouton intermédiaire superflu ; sans JS, un bouton « Appliquer les choix » explicite charge le formulaire correspondant, y compris ses réglages avancés. Le jeton CSRF ne passe jamais dans la requête GET. Une référence ou un audio invalide en préparation rend un message borné et échappé avec un statut de refus approprié, jamais une 500 ni une valeur interprétée comme HTML. Les réglages avancés d'une préparation déjà affichée sont conservés lorsqu'encore compatibles ; une réinitialisation est annoncée plutôt que silencieuse.

Pas de concaténation de fragments utilisateur avec `innerHTML`. Rendre les contrôles par Jinja et, si données en attributs nécessaires, sérialiser par `tojson` dans un attribut correctement cité. Le POST de lancement revalide tout, y compris moteur prêt, fichiers et créneau.

Alternative rejetée : tous les formulaires pré-rendus et seulement masqués par CSS, qui laisse soumettre plusieurs champs de même nom et recrée le bruit actuel. Un choix moteur impossible est refusé, pas présenté comme un moteur installable automatiquement.

### D5. Opération intégrée et suivi sans envahir le formulaire

Un résumé d'opération n'est affiché en tête d'Exécutions que si utile (active ou dernière issue). Type et cible sont distincts. Bouton Arrêter uniquement pour une transcription active, toujours POST avec jeton ; pas de nouvelle annulation d'installation/téléchargement. Journal technique repliable, erreur visible hors journal. L'état compact ne remplace ni le formulaire complet ni la page entière lors du suivi.

Nouvelle lecture fixe `GET /executions/etat`, JSON nettoyé et `no-store` : type/état/cible, erreur, identifiant de résultat éventuel et URL locale construite côté serveur. Pas de PID, jeton ni transcription. Une URL de résultat est construite côté serveur depuis un identifiant validé ; avant de créer le lien, le JS vérifie également origine locale et chemin `/resultats/`, et refuse toute autre cible. Polling vanilla toutes les 3 s tant qu'une opération est active, une requête à la fois, suspendu si onglet masqué, arrêté à l'état terminal ; échec signalé avec actualisation manuelle, pas de boucle agressive. Construire les messages en `textContent` et conserver les contrôles/focus existants. L'actualisation GET de la page reste le repli.

Publier explicitement l'identifiant du résultat courant depuis `ExecutionMoteur` après création de la consignation, avec synchronisation par verrou. Associer le résultat à l'identité de l'opération du créneau (type et début ou identifiant dédié stable) : il n'est exposé que si l'opération observée correspond à cette transcription. Invalider l'association au début de toute nouvelle opération, y compris installation et téléchargement ; une remise à zéro de la seule réservation moteur ne suffit pas. Ne pas inférer l'identifiant depuis `cible` ni depuis un ancien `derniere_execution`. Cette petite vue de suivi ne change pas le schéma des JSON. Tester lien pendant/après exécution et absence de lien ancien pendant installation, téléchargement ou échec avant consignation.

### D6. Choix JS/CSS et sécurité

Choix : un fichier `/app.js` vanilla chargé `defer`, sans dépendance ni étape de compilation ; Jinja/Flask restent la source du HTML et des validations. Trois besoins seulement : faciliter la préparation compatible, protéger la sélection comparative pendant le tri, suivre l'opération. Alpine/htmx ne sont pas nécessaires ; ils impliqueraient version/licence/provenance et configuration CSP pour un gain non démontré. Aucun paquet n'a été installé pour cette rédaction.

Faisabilité documentaire : Flask 3.1.3 utilisé dans le verrou ; Context7 `/pallets/flask` (documentation de la série 3.1, pas une validation du patch 3.1.3) confirme fichier à MIME explicite, données Jinja via `tojson`, autoéchappement `.html` et en-tête CSP. Le code sert déjà les CSS par chemins fixes avec contrôle Host. Étendre ce patron à JS sans ouvrir un répertoire statique arbitraire. Faisabilité de rendu/interaction restant à démontrer par tests et navigateur lors de l'implémentation.

CSP proposée : `default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self'; object-src 'none'; form-action 'self'; frame-ancestors 'none'; base-uri 'none'`. Aucun `unsafe-inline`, `unsafe-eval`, script inline, attribut `on…`, `eval`, `new Function` ou code issu des modèles. Ajouter dans `after_request` sur les réponses HTML, erreurs 404/405/500 réelles comprises, avec tests dédiés. Conserver Host/Origin/CSRF, bornes des formulaires, confinement et échappement ; URL de redirection fixe, codes d'action bornés, jamais paramètre libre `next`.

Conserver Sumi figé et la palette Flexoki, étendre `app.css` avec des composants ciblés : modèle 1,125 rem en gras, valeurs temps/RAM/CPU 1,25 rem ou plus, métadonnées secondaires au moins 0,875 rem, texte courant au moins 1 rem. Temps en accent cyan/bleu, RAM violet, CPU orange selon les teintes offrant 4,5:1 ; les meilleurs temps/RAM ont aussi un libellé, pas seulement une couleur. Les teintes exactes sont des jetons de CSS à valider en clair et sombre, pas des performances codées vert/rouge. Espacements et grille conçus pour les écrans de recette. Ne pas introduire une seconde bibliothèque CSS.

### D7. Cohérence des changes : ne pas effacer les preuves anciennes

Les deltas de ce change expriment la cible APRÈS Sumi et la première lecture ; les exigences renommées/modifiées qui n'existent pas encore dans `openspec/specs/` ne doivent pas être synchronisées seules sur le socle ancien.

| Source antérieure | Conservé | Remplacé par ce change |
| --- | --- | --- |
| Sumi | copie figée, licences, ressources locales, Flexoki, contraste, sémantique, contrôles de sécurité | interdiction JS, menu à huit liens, liste fermée de classes, CSS sans tailles/espacements, journal toujours ouvert |
| Première lecture | ratios et formats, tri brut, factices/partiels, historique intégral, texte complet dans détail/comparaison | simple lien Résultats vers classement, longues lignes de sélection, synthèse en prose, limite HTML qui perd la sélection, non-goals de menu/formulaire |
| Mesures système non implémentées | collecte/stockage/méthodes restent dans leur change, sans nouvelle mesure ici | réconciliation approuvée dans ses propres artefacts : bloc secondaire, pas une sixième métrique ni une colonne de classement |
| Documentation utilisateur | informations de lancement/sécurité et données | guide final attend les nouveaux parcours ; ne pas achever des captures/procédures sur l'ancienne navigation |

Ordre de synchronisation lors d'une demande dédiée : Sumi, première lecture, puis présent change, afin que les remplacements ciblés gagnent. Le change de mesures système n'est pas un préalable et reste 0/12 tant qu'inexécuté. Sa présentation est réconciliée dans ses propres artefacts ; ne pas synchroniser ses exigences non implémentées pour faire passer cette refonte. Ne jamais réappliquer ensuite les anciens deltas UI au-dessus de la nouvelle cible. Aucun archivage dans cette session. À l'application de ce change, les autres tâches UI restent suspendues pour éviter des modifications concurrentes ; une reprise doit lire cette matrice.

### D8. Recette et provenance des validations

L'utilisateur a validé sombre et hover/focus sur son PC local dans cette conversation ; OS/navigateur/résolutions non consignés. C'est une validation déclarée du rendu antérieur, pas une recette exhaustive des cartes/grilles Sumi ni de l'ergonomie, explicitement contestée ensuite. La recette de cette nouvelle refonte reste entièrement à faire.

Jeux synthétiques à prévoir : quatre essais courts d'un même audio ; modèle long/variantes proches ; deux empreintes de même nom ; durées décodées divergentes ; valeurs absentes/invalides, ratios >100 %, factices, partiels, erreurs, égalités ; modèle supprimé et historique sans transcription ; opération active/terminée/échouée ; combinaison moteur forgée ; familles à réglages de même nom ; lot.

À 1280 × 800, au chargement initial sous la navigation, les listes montrent au moins trois entrées du premier groupe avec toutes leurs valeurs ; la comparaison de deux résultats courants montre leurs valeurs et le début des deux textes. À 360 × 800, pas de défilement horizontal, première entrée et ses valeurs accessibles d'emblée dans le cas court sans alerte. Vérifier clair/sombre réels, clavier, contraste, focus stable pendant polling, JS activé puis désactivé. L'utilisateur doit pouvoir retrouver les critères demandés sans explication orale ; ne pas accepter un simple comptage de classes/tests comme preuve de lisibilité.

## Risks / Trade-offs

- [Trop d'information déguisée en cartes] → budget de contenu explicite, groupes audio, dates secondaires, recette bureau/mobile avant déclinaison intégrale.
- [Trois sélecteurs supposés indépendants] → référence inventaire source de vérité, contrôle moteur cohérent et revalidation serveur.
- [Tri inter-audios trompeur] → groupes par empreinte et tri interne ; ordre des groupes indépendant du score.
- [JS réduit la sûreté] → vanilla local, CSP stricte, pas de mutation via GET, DOM sûr et repli HTML complet.
- [Polling coûteux ou focus perdu] → petit JSON sans relire les poids, cadence bornée, aucune réécriture du formulaire.
- [Ancien change écrase le nouveau] → ordre de synchronisation explicite et aucune tâche UI concurrente ; preuve de fusion à vérifier avant synchronisation réelle.

## Migration Plan

1. Faire approuver la règle d'instructions autorisant JS local et CSS applicative puis demander `/reload` avant tout code concerné ; cette rédaction ne change pas AGENTS.
2. Réaliser un premier écran Résultats sur données synthétiques et le faire observer avant de propager le composant.
3. Reprendre sélection/comparaison et détail, puis navigation, formulaire, suivi, inventaire modèles et documentation sans changer les résultats stockés.
4. Tester progressivement puis exécuter les tests sans moteurs Linux/Windows ; seuls les jobs factices sont autorisés par cette demande, aucun job moteur.
5. Valider le parcours visuellement, consigner les limites et demander la synchronisation/archivage séparément. Retour arrière du code possible sans migration des données ; aucune réécriture de résultats finalisés.
