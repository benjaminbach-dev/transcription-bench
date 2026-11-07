# Design

## Context

Voir `proposal.md`. L'analyse du 2026-11-04 sur `931e2a5` a confirmé : le serveur prépare tous les audios avant de lancer le runner ; les événements chargement/audio n'arrivent qu'à la fin de leur phase. Déduire les débuts d'inférence de leur réception serait approximatif. Le runner possède déjà les bornes exactes du temps CPU et du temps mural par audio ; psutil 7.2.2 est déjà dans les environnements verrouillés. La consultation accepte des champs additionnels sous `schema: 1` et refuse les versions globales inconnues.

Faisabilité documentaire : Context7 `/giampaolo/psutil/v7.2.2`, documentation officielle et source installée `psutil/__init__.py` (fonctions `cpu_percent`, `_cpu_tot_time`, `_cpu_busy_time`) : état CPU non bloquant par identifiant de thread, première valeur non interprétable, intervalle recommandé >= 0,1 s ; mémoire portable via `virtual_memory().available`. Source : https://github.com/giampaolo/psutil/blob/v7.2.2/docs/index.rst .

Sonde d'API initialement conçue pour la variante avec observateur, exécutée sur serveur de développement (ce n'est pas une validation du nouveau runner) : psutil 7.2.2, sous-processus Python synthétique dormant 0,6 s, lecture compteurs CPU processus, RSS, identité PID/heure de création, second relevé CPU système et mémoire disponible réussie. Aucun moteur/poids ni mesure représentative ; aucune preuve Windows. Le conseil advisor préalable a permis d'écarter le collecteur périodique.

## Goals / Non-Goals

**Goals:** contexte système par audio à coût borné, sans thread supplémentaire ; même périmètre temporel d'inférence pour le CPU moteur et système, à quelques appels de mesure près ; dégradation sans échec de transcription ; anciens résultats immuables.

**Non-Goals:** minimum de RAM pendant l'inférence, charge système pendant tout le décodage ou le chargement, courbe temporelle, mesure instantanée/pic CPU, suivi en direct, attribution à l'application entière, somme de RSS, consommation électrique/swap, seuil de confort, gestion exhaustive des quotas et processor groups. Le pic cumulatif moteur reste inchangé.

## Decisions

### D1. Mesurer dans le runner, pas observer depuis le serveur

Après chargement, relever un instantané RAM. Pour chaque audio, lire le signal et établir les fenêtres comme aujourd'hui, puis amorcer le compteur CPU système juste avant les bornes existantes de l'inférence ; lire la valeur après arrêt de ces compteurs, avant la sérialisation. Relever ensuite la RAM disponible. L'intervalle système englobe les bornes du moteur avec le seul surcoût des appels de mesure ; conserver sa durée monotone propre, pas celle du lot. Un échec audio n'obtient pas de mesure finale fabriquée ; les données système d'un audio terminé sont persistées avec cet audio.

Pas de nouveau type d'événement ni de changement du contrat des adaptateurs. Alternative rejetée : thread serveur toutes les 0,5 s, qui impose arrêt, couverture, agrégats et attribution approximative aux phases. Alternative rejetée : différence de RAM avant/après comme consommation de modèle (autres processus et caches).

### D2. API publique CPU non bloquante et provenance

Encapsuler psutil dans une petite couture injectable, utilisée sur le même thread que l'inférence. `psutil.cpu_percent(interval=None, percpu=False)` est appelé pour amorcer au début, sa valeur ignorée, puis pour lire à la fin ; aucun appel intermédiaire sur ce thread. La lecture du code 7.2.2 confirme que le cache est par thread. Éviter les API privées et une réimplémentation fragile de Linux guest/iowait ou Windows interrupt/dpc.

Un compteur inexploitable signifie ici : exception à l'amorçage ou à la lecture, intervalle monotone absent, non fini ou < 0,1 s, retour non numérique (booléen exclu), non fini ou hors 0..100. Dans ces cas : CPU global `null` et motif stable ; ne jamais attendre artificiellement. Les valeurs 0 % retournées après amorçage valide et intervalle suffisant sont conservées telles quelles ; psutil ne distingue pas un delta total nul d'une inactivité réelle et corrige certains deltas négatifs en interne. Aucune détection exhaustive des anomalies de compteur n'est promise. Le helper teste isolation de l'état entre audios et erreurs. Aucune collecte réelle en mode factice : scénario simulé déterministe marqué `simulee`, pour exercer le même parcours de bout en bout. Le coût sera contrôlé par sonde synthétique de fonctionnement, sans annoncer de surcoût négligeable avant mesure.

100 % = CPU logiques visibles OS. Le ratio moteur est défini séparément dans le change UI ; ne pas calculer CPU « autres applications » ou marge CPU par différence entre les deux mesures : compteurs, bornes et arrondis ne sont pas exactement identiques et l'hyperthreading limite l'interprétation.

### D3. Objets facultatifs versionnés sous le schéma existant

Contrat additif proposé, version de méthode 1 (unités explicites dans les noms) :

```text
chargement.observation_systeme
  version: 1
  methode_cpu: "psutil-cpu-percent-nonbloquant-v1"
  version_psutil: valeur lue dans psutil.__version__
  provenance: "reelle" | "simulee"
  memoire_apres:
    releve_le: date ISO UTC
    totale_octets: entier positif | null
    disponible_octets: entier >= 0 et <= total | null
    motif: null | code stable

audio.observation_systeme
  [mêmes version, méthode, version psutil, provenance]
  cpu:
    pourcentage_moyen: nombre 0..100 | null
    intervalle_s: nombre fini >= 0 | null
    motif: null | code stable
  memoire_apres: [mêmes champs]
```

Le relevé chargement ne comporte pas de CPU moyen de chargement. `methode_cpu` n'est pas une promesse de cette mesure, seulement l'identifiant de protocole de la méthode employée par le runner. Les dates sont des instantanés, pas des coordonnées pour reconstruire une courbe.

Persister l'objet chargement sous `run.json.mesures.observation_systeme_chargement` et celui de chaque audio sous `result.json.mesures.observation_systeme`. Ne pas modifier `machine`, les anciens champs ni `schema: 1`. Le runner et la consignation valident les nouveaux champs sans rejeter l'audio si ces seuls champs sont invalides. La provenance doit correspondre à `mesures_simulees` de l'événement et du résultat (`simulee` si vrai, `reelle` sinon) ; toute contradiction invalide l'objet. Le serveur ne persiste pas un objet invalide : il le signale seulement au journal et enregistre l'audio sans cet objet. Codes écrits avec une métrique absente : `lecture_impossible`, `intervalle_trop_court`, `valeur_incoherente`. États calculés à la lecture, jamais écrits : `absent`, `invalide`, `version_inconnue`. Les erreurs brutes d'OS ne sont pas des textes affichables non filtrés.

Les futurs lecteurs reconnaissent version 1, ignorent l'objet inconnu/invalide avec motif et gardent texte/mesures anciennes. Un lecteur ancien ignore les additions. Aucun backfill, aucune migration. Après abandon, conserver instantané chargement et audios déjà écrits ; le relevé manquant reste absent et l'état de l'exécution porte l'interruption. Ne pas marquer rétrospectivement comme incomplète une observation valide d'un audio déjà fini.

### D4. Affichage complémentaire, pas une quatrième compétition

Dans le détail et la comparaison sélectionnée, proposer un bloc secondaire repliable « Contexte de l'ordinateur » : « CPU total moyen : 90 % pendant la transcription ; RAM disponible après : 5,2 Go sur 16 Go ». Si une valeur manque, « non mesuré ». Le relevé après chargement, méthode/version/intervalle et les valeurs brutes restent accessibles dans ce même niveau secondaire. Formats SI français identiques aux formats de premier niveau de `refondre-parcours-resultats` ; aucun ratio inventé entre mémoire disponible et pic RSS. L'aide explique une seule fois les autres programmes inclus, l'instantané après l'audio et l'absence de garantie de confort.

Réconciliation approuvée par le propriétaire le 2026-11-07 avec `refondre-parcours-resultats` : aucune colonne système dans les listes, aucune sixième métrique au premier plan et pas de paragraphe répété par résultat. La refonte peut être implémentée et synchronisée sans ces champs ; ce change reste indépendant pour leur collecte et stockage. Lors de sa réalisation, employer les composants et la navigation alors en vigueur, sans réintroduire les anciennes contraintes Sumi sur menu/classes/CSS. Cette révision ne change ni D1–D3, ni les autorisations de validation réelle.

### D5. Tests et preuves proportionnés

Tests déterministes injectant les deux retours CPU, l'horloge monotone et les retours mémoire : frontière chargement/audio, intervalle court, exceptions, booléens, infinis, bornes, zéro retourné par l'API, mode factice, version inconnue. Cas Linux et Windows sans moteur via psutil existant par deux appels sur le même thread, sans seuil de performance attendu. Pas de suite ou installation nouvelle nécessaire à la rédaction. La sonde intégrée peut se limiter à deux appels non bloquants sur le même thread autour d'un court intervalle d'au moins 0,1 s ; aucun processus moteur ni sous-processus supplémentaire requis.

Prévoir une validation du runner réel sur PC Linux déclaré et dans le job Windows moteur prévu, dont l'exécution exige une autorisation explicite, sans modèle supplémentaire : présence/plausibilité des champs, pas performance comparative. Le lot devra être annoncé avant exécution ; cette spec ne déclenche aucun job. Rapports CI : whitelister seulement nouveaux agrégats numériques, méthode et provenance si conservés ; aucune transcription, audio, chemin ou donnée personnelle. Les mesures CI ne qualifient pas le PC utilisateur.

## Risks / Trade-offs

- [RAM maximale de l'essai non observée par instantanés] → libellé explicite après chargement/après audio ; ne pas revendiquer un minimum restant.
- [CPU très court ou précision des compteurs] → seuil documentaire 0,1 s, absence explicite et tests ; pas d'attente.
- [État implicite psutil par thread] → helper isolé, même thread, pas d'appel intermédiaire, méthode versionnée et tests d'enchaînement ; vérifier à toute mise à jour de psutil. Un appel à `cpu_percent` sur le même thread par une bibliothèque pendant l'inférence réinitialiserait aussi le compteur ; cette limite est documentée, sans garantie de détection.
- [Contexte système variable] → aucune attribution, aucun classement modèles par CPU global ou mémoire disponible.
- [Échec collecte] → `null` avec motif par métrique, sans changer le statut audio ; immutabilité inchangée.
- [Plateformes] → source documentaire et sonde Linux de développement ne remplacent ni runner réel Linux ni Windows.

## Migration Plan

1. Helper injecté et tests ; champs facultatifs des événements ; écriture/lecture additive sans migration.
2. Tests d'intégration factices puis sondes synthétiques Linux/Windows ; vérifier arrêt et relecture sans altération des résultats.
3. Afficher le contexte et aligner l'aide/guide, puis valider le runner réel seulement dans les contextes autorisés et consigner les limites.
4. Retour arrière : ignorer les champs additionnels ; les anciens champs et textes sont conservés. Ne pas réécrire les fichiers finalisés.
