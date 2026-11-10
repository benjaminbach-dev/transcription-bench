# Design

## Context

Voir `proposal.md`. Constats sur le code (lecture, aucune exécution réelle) :

- `cli.py::main` verrouille l'instance (`VerrouInstance`), lance la récupération des exécutions abandonnées, prépare `data/`, puis construit `CreneauOperations`, le registre des moteurs, `InstallationMoteurs`, `GestionModeles` et `ExecutionMoteur`, enfin sert Flask via Waitress. Cette composition n'est pas réutilisable en l'état.
- Les routes Flask sont minces : elles valident, puis appellent les services. Le créneau (`CreneauOperations.demarrer`) exécute l'opération dans un thread démon ; `instantane()` en expose l'état et le journal, `thread_travailleur` le thread. Rien de cela ne dépend de Flask.
- La vérification d'un dépôt (`GestionModeles.lancer_verification`) passe aussi par le créneau et publie son résultat **en mémoire** (`dernier_resultat`) ; le téléchargement (`lancer_telechargement(empreinte)`) exige ce résultat et son empreinte. Une commande autonome doit donc enchaîner vérification puis téléchargement **dans le même processus**.
- `ExecutionMoteur` fournit `reserver`, `verifier_lancable`, `lancer`, `arreter_execution` ; `ConfigurationExecutions.preparer/valider` construisent la demande validée à partir de champs de formulaire.
- Le verrou d'instance est un verrou de fichier OS non bloquant, libéré par le système à la mort du processus.

Contraintes du projet : aucune dépendance nouvelle sans accord, serveur sans import de bibliothèque de moteur, CPU seul, hors ligne sauf action explicite, chemins contrôlés, une seule opération longue à la fois.

## Goals / Non-Goals

**Goals :** une commande par fonction de la page web ; mêmes services, mêmes refus, mêmes règles ; usage fiable par un agent (JSON stable, codes de sortie, journal en flux, arrêt propre) ; web inchangé par défaut.

**Non-Goals :** MCP, démon/détachement, accès simultané web + CLI, lecture sans verrou pendant que le serveur tourne, nouvelle fonction absente du web, changement du schéma des résultats.

## Decisions

### D1. Un programme, deux modes exclusifs

`transcription-bench` reste l'unique point d'entrée (`[project.scripts]` inchangé). Sans sous-commande, ou avec `--port` seul, il lance le serveur (comportement actuel, y compris le message d'arrêt et les codes 0/1/2). `serve [--port N]` est l'équivalent explicite. Toute autre sous-commande exécute une commande puis rend la main.

Pour ne pas casser `transcription-bench --port 8080`, l'analyse d'arguments traite l'absence de sous-commande comme `serve` : `argparse` avec sous-parseurs facultatifs, `--port` rattaché à la racine et à `serve` (le sous-parseur utilise `default=argparse.SUPPRESS` pour ne pas écraser la valeur de la racine). `--json` n'est pas accepté par `serve`. Alternative rejetée : forcer `serve` (change le contrat existant et la doc).

### D2. Toutes les commandes prennent le verrou d'instance

Même lecture seule. Conséquence : une commande refuse (code 2, message du verrou existant) si le serveur ou une autre commande tient `data/`, et la récupération au démarrage s'applique avant toute commande, comme avant `serve`. Un seul chemin à raisonner, aucun cas « lecture concurrente d'un fichier en cours d'écriture ». Alternative rejetée : lectures sans verrou, utiles seulement si le serveur tourne, cas explicitement exclu par la décision « web ou CLI » ; elle réintroduirait la question de la récupération et des fichiers mutables.

### D3. Composition des services extraite

Nouveau module (`services.py`, nom indicatif) avec un gestionnaire de contexte qui : prend le verrou, lance la récupération, prépare `data/`, construit **tous** les services (ceux de `main` — créneau, registre, installation, modèles, exécution — et ceux que `create_app` construit aujourd'hui lui-même : `ConfigurationExecutions`, `ConsultationResultats`), puis garantit le nettoyage (`NettoyageArret`) et la libération du verrou. `create_app` reçoit ces services injectés ; `serve` et les commandes partagent donc la même composition. Le code de sortie, les messages et le comportement d'arrêt de `serve` sont préservés. `tests/test_cli.py` remplace aujourd'hui `cli.CreneauOperations`, `cli.create_app` et `cli.serve` : la tâche d'extraction adapte ces tests (ou conserve ces noms résolus dans `cli`) sans affaiblir leurs assertions.

Le lancement d'exécution est aujourd'hui enchaîné dans la route (`refuser_champs_repetes` → `valider` → `verifier_lancable` → `reserver` → `creneau.demarrer` → `annuler_reservation` si refus). Cet enchaînement est extrait dans une fonction partagée par la route et la commande `run start` : sans `reserver` avant l'admission, `arreter_execution` ne verrait aucune exécution à arrêter.

### D4. Commandes bloquantes sur le créneau existant

Une opération longue appelle `creneau.demarrer(...)`, puis une boucle de suivi sonde `instantane()` à intervalle court (`sleep`), écrit chaque nouvelle ligne du journal, et sort quand l'état n'est plus « en cours » et que le thread est terminé. Le curseur de lecture du journal suit la génération de l'opération (le journal repart de zéro à chaque admission, notamment entre la vérification et le téléchargement de `models download`). Aucun `join()` sans délai : l'attente doit rester interruptible, y compris sous Windows. Chaque ligne JSON est écrite entière puis vidée (`flush`) ; la boucle n'est jamais interrompue par une exception levée dans le fil principal.

**Signaux.** `GestionnaireSignaux` actuel lève `KeyboardInterrupt`/`SystemExit` autour de `waitress.serve` ; il ne convient pas à une boucle qui écrit sur la sortie standard et lit le créneau sous son verrou. La CLI utilise un gestionnaire à drapeau : le signal (Ctrl+C, SIGTERM sous Linux, Ctrl+Break/Ctrl+C sous Windows) pose le drapeau et les signaux suivants sont ignorés ; la boucle de suivi constate le drapeau, demande l'arrêt (`ExecutionMoteur.arreter_execution()` pour une exécution, comme le bouton web, d'où un arrêt « utilisateur » et non « arrêt du serveur » ; `NettoyageArret` pour le reste), attend la clôture bornée, puis sort avec le code 3.

**Limites d'arrêt héritées.** Un téléchargement n'est pas annulable (`supervision.py`) : après le délai borné, le thread peut survivre ; le nettoyage le signale non clos, le modèle n'est jamais marqué prêt, le code reste 3 et le verrou n'est libéré qu'à la fin réelle du processus. Il n'y a pas de commande `stop` : une autre commande ne peut pas prendre le verrou ; l'équivalent du bouton web est le signal.

**Arrêt brutal et agents.** Un agent sans console ne peut pas envoyer `Ctrl+C` sous Windows et `SIGTERM` n'y existe pas ; un délai d'agent peut finir en terminaison brutale (SIGKILL). Le moteur vit dans son propre groupe de processus et peut survivre ; la prochaine commande (ou le prochain serveur) le termine après vérification de son identité et clôt l'exécution en abandonnée (récupération existante). La documentation recommande, sous Linux, de lancer en arrière-plan puis d'envoyer SIGTERM, et décrit ce chemin de récupération ; sous Windows, la limite est assumée et à éprouver sur PC.

### D5. Vérifier puis télécharger dans le même processus

`models download` enchaîne : vérification (créneau, attente de fin), lecture de `dernier_resultat()`, refus si non accepté (`raison` du service) ou si plusieurs fichiers GGUF sont proposés sans `--file` (`fichier-gguf-non-choisi`, liste `gguf_candidats`), calcul de l'empreinte, `lancer_telechargement(empreinte)` (qui renvoie `False` si le modèle est déjà prêt, sans opération), attente. La révision téléchargée est le commit résolu par la vérification de cette même commande, affiché avant le transfert. `models check` ne fait que la vérification (bouton « Vérifier la compatibilité sans télécharger ») et applique le même refus GGUF multiple. L'état du créneau ne suffit pas à déduire le code : une vérification refusée ou en échec réseau finit avec un créneau `terminee` ; le code vient de `dernier_resultat()` (`accepte`, `raison`).

### D6. Sortie et codes de sortie

- Par défaut : texte concis en français.
- `--json` (toutes les commandes sauf `serve`) : un unique objet JSON sur la sortie standard pour les commandes à résultat ; pour les opérations longues, des lignes JSON (JSON Lines) d'événements de journal suivies d'une dernière ligne de résultat. Chaque objet porte `schema: 1`. Les noms de champs sont ceux des vues typées existantes (aujourd'hui en français, avec unités dans leurs noms), complétés explicitement des propriétés calculées nécessaires (indicateurs principaux, `simule`, annotation RAM) ; **aucun** `asdict` aveugle qui perdrait ces propriétés. Un test d'instantané verrouille les clés de chaque commande ; une évolution des vues (par exemple `mesurer-charge-systeme`) est une évolution additive consciente de ce contrat. Les noms de commandes et d'options sont en anglais (identifiants nouveaux), les messages et l'aide descriptive en français ; les mots génériques d'`argparse` restent tels quels.
- En mode JSON, rien d'autre n'est écrit sur la sortie standard ; messages et diagnostics vont sur la sortie d'erreur. Les sorties sont écrites en UTF-8 (`reconfigure`) pour ne pas échouer avec l'encodage local d'un agent sous Windows.
- Les lignes de fin donnent de quoi enchaîner : `run start` rend l'identifiant du résultat (et l'état de chaque audio), `models download` la référence locale du modèle, `results list` l'empreinte de chaque groupe et la sélection `identifiant:ordre` de chaque essai.
- Codes : `0` succès ; `1` échec (installation, téléchargement ou exécution en erreur, y compris exécution terminée avec au moins un audio en erreur, détaillé dans le résumé ; échec réseau ou accès refusé lors d'une vérification) ; `2` refus (arguments invalides, verrou tenu, ressource non prête, dépôt incompatible, état antérieur non traitable) ; `3` interrompu par signal. Si un signal a été reçu mais que la clôture est incomplète, le code reste 3 et le message l'indique. Les codes 1 et 2 correspondent à `CODE_ECHEC` et `CODE_REFUS` existants. Un modèle déjà prêt lors d'un téléchargement est un succès (0).

### D7. Parité route par route avec la page web

La table est **dans le code** (`transcription_bench/…`, constante nommée) et non dans le dossier du change, déplacé à l'archivage ; le test de parité (tâche 4.1) la lit et la confronte aux routes réelles de l'application.

| Route web | Commande ou exclusion |
|---|---|
| `GET /` | redirection vers Résultats : exclusion (aucune fonction) |
| `GET /sumi.css`, `/app.css`, `/app.js` | ressources de la page : exclusion |
| `GET /audios` | `audios list` |
| `POST /dossiers/verifier` | `data check` (affiche l'état des dossiers ; la préparation de `data/` est de toute façon faite par chaque commande) |
| `GET /moteurs` | `engines list` |
| `POST /moteurs/<id>/installer` | `engines install ID` |
| `GET /moteurs/<id>/journal` | `engines log ID [--limit N]` (2000 par défaut, comme la page) |
| `GET /modeles` | `models list` |
| `POST /modeles/verifier` | `models check REPO --engine E [--revision R] [--file F]` |
| `POST /modeles/telecharger` | `models download REPO --engine E [--revision R] [--file F]` |
| `POST /modeles/supprimer` | `models delete ENGINE KEY` |
| `GET /executions` (préparation) | `run options [--model REF] [--audio NAME]...` : modèles proposables (y compris le modèle synthétique du moteur factice), exécutables ou non avec motif, audios proposables, threads par défaut, réglages déclarés de la famille avec valeurs par défaut |
| `POST /executions/verifier` | `run check --model REF --audio NAME... [--threads N] [--setting NOM=VALEUR]...` |
| `POST /executions/lancer` | `run start` (mêmes options) |
| `POST /executions/arreter` | signal sur la commande en cours (D4) : exclusion documentée |
| `GET /executions/etat`, `GET /operation` | flux de journal de la commande bloquante, état final et code de sortie : exclusion documentée |
| `GET /executions` (historique complet) | `results history` |
| `GET /resultats` | `results list [--sort temps\|ram\|cpu\|recent]` (défaut `recent`, comme la page) |
| `GET /resultats/<id>` | `results show ID` |
| `GET /resultats/aide` | `results explain` |
| `GET /resultats/comparaison` (sélection) | `results list` (empreinte de groupe et sélection `identifiant:ordre` de chaque essai) |
| `GET /resultats/comparaison/<empreinte>` | `compare AUDIO_HASH SEL SEL...` avec `SEL = identifiant:ordre` (2 à 64 sélections, comme `analyser_selection`) |

Les valeurs de tri sont celles du service (`temps`, `ram`, `cpu`, `recent`) ; `compare` n'utilise pas de tri : l'ordre reçu est conservé. `--threads` prend par défaut `threads_par_defaut()`. Les booléens de réglages suivent la syntaxe du formulaire existant. `ID`, `REF`, `KEY` sont les identifiants déjà employés par la page. Les règles de refus viennent des services (`ConfigurationExecutions`, `ExecutionMoteur`, `GestionModeles`), sans copie ; le motif affiché est celui du service, la page ajoutant seulement un habillage HTML.

Refus **inatteignables** en CLI parce qu'un seul processus tient le verrou : créneau occupé, suppression pendant une opération, moteur « en cours d'installation », état `actif` d'un modèle. Ils restent couverts par les tests des services ; la CLI ne les teste que par injection et ne les promet pas.

`results explain` imprime le texte d'aide des indicateurs. Pour ne pas dupliquer silencieusement le gabarit HTML, le texte vient d'une source unique partagée avec le gabarit si elle existe à l'implémentation, sinon d'une constante dédiée accompagnée d'un test vérifiant la présence des termes clés ; ce choix est soumis à l'utilisateur (voir Open Questions).

### D8. Réutiliser les vues typées, ne pas réécrire le métier

La sérialisation JSON s'appuie sur les vues typées de `consultation_resultats`, `executions` et `gestion_modeles` (dataclasses), avec une conversion explicite des types non sérialisables (chemins, énumérations) et l'ajout nommé des propriétés calculées (voir D6). Aucune de ces vues ne doit changer de comportement. Aucun fichier de résultat n'est réécrit par une commande de lecture ; la récupération et la préparation de `data/` effectuées au démarrage de chaque commande (D2) peuvent, elles, clore une exécution abandonnée et créer des dossiers ou `instance.lock`.

### D9. Données sensibles et réseau

Mêmes règles que le web : aucun jeton affiché ou journalisé, aucune donnée audio ou transcription envoyée à un service externe, accès réseau uniquement pour `engines install`, `models check` et `models download`. Les commandes ne demandent aucune confirmation interactive (un agent ne peut pas répondre) ; l'action explicite est la commande elle-même, et la suppression/téléchargement nommés dans la ligne de commande sont leur propre confirmation.

## Risks / Trade-offs

- **Opérations longues sous délai d'agent** : une exécution bloque l'appel. Atténuation : flux de journal régulier ; l'agent peut lancer la commande en arrière-plan avec ses propres outils. Pas de mode détaché (hors périmètre).
- **Chemin de signal sous Windows** : `Ctrl+C`/`SIGTERM` et terminaison de la descendance sont déjà documentés comme « à éprouver » ; la CLI hérite de cette limite et ne la lève pas.
- **Mémoire de `dernier_resultat`** : valable seulement dans le processus ; couvert par D5.
- **Récupération avant chaque commande** : une lecture simple peut refuser (code 2) si un état antérieur est douteux, comme le démarrage du serveur. Comportement voulu et documenté.
- **Dérive de parité** : un test énumère les routes réelles de l'application et vérifie que chacune figure dans la table de parité du code (commande ou exclusion documentée), pour qu'une future route sans équivalent fasse échouer la suite.
- **Changements actifs** : `refondre-parcours-resultats` (toutes tâches faites, non archivé) modifie aussi `local-web-interface` et `results-comparison` ; `mesurer-charge-systeme` ajoute le contexte de l'ordinateur ; `rediger-documentation-utilisateur` porte `README.md` et `docs/technique.md` avec des contrôles dans `tests/test_documentation.py`. Ordre retenu : archiver `refondre-parcours-resultats` avant ce change ; la CLI suit les vues de consultation sans règle propre, et la lecture CLI conserve la distinction « empreinte du moteur / contexte de l'ordinateur » dès que `mesurer-charge-systeme` est appliqué. La documentation CLI est écrite en coordination avec les contrôles documentaires existants (libellés et termes interdits) : la tâche de documentation les adapte au lieu de les contourner.
- **Qualification** : les commandes réelles (moteurs, modèles, signaux) ne sont pas éprouvées par ce change ; une qualification sur PC Linux de test, puis sur Windows, reste à faire séparément.

## Open Questions

- Format texte par défaut des commandes de lecture (tableaux ou listes) : à fixer à l'implémentation selon la lisibilité, sans incidence sur le contrat JSON.
- Faut-il ajouter plus tard un mode sans verrou pour les lectures ? Non décidé ; hors périmètre.
- `results explain` : source unique partagée avec le gabarit d'aide (refactoring du gabarit) ou constante dédiée avec test de termes ? À arbitrer par le propriétaire ; la parité à 100 % demande une commande dans les deux cas.
