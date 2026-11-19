## Why

Le programme se pilote aujourd'hui de deux façons : la page web et la CLI ajoutée par `ajouter-cli-agent`. À l'usage, le propriétaire confie la préparation, le lancement et la lecture des essais à des agents, qui utilisent la CLI ; les pages d'action (Exécutions, Modèles, Moteurs, Audios) ne servent plus. Maintenir une parité stricte entre deux interfaces d'action double le coût de chaque évolution, alors que le prochain change (`ajouter-bench-extraction`) ajoute un second type de benchmark. Seule la lecture humaine des résultats et des comparaisons garde un intérêt dans un navigateur.

## What Changes

- **BREAKING** : l'interface web devient une interface de **consultation seule** : Résultats, Comparaisons, Historique des exécutions et aide des indicateurs. Elle ne lance plus ni installation, ni téléchargement, ni exécution, ni suppression, et n'accepte plus aucun POST.
- Suppression des pages et routes d'action : `/audios`, `/moteurs`, `/moteurs/<id>/installer`, `/moteurs/<id>/journal`, `/modeles` et ses POST, préparation et POST de `/executions`, `/executions/etat`, `/operation`, `/dossiers/verifier`. `/executions` ne garde que l'historique complet, présenté sous le libellé Historique.
- Suppression de `/app.js` et de toute exécution de script dans les pages : il ne servait qu'à la préparation d'exécution et au suivi d'opération. La CSP interdit alors tout script.
- Suppression du jeton anti-CSRF, des limites de formulaires POST et du suivi d'opération côté web, devenus sans objet. Les contrôles `Host`, le confinement des chemins, l'échappement et la CSP sont conservés.
- La CLI devient la **seule interface d'action**. L'exigence de parité « chaque route web a une commande et aucune commande n'offre de fonction absente du web » est remplacée par une règle à sens unique : chaque page de consultation a une commande de lecture équivalente, la CLI pouvant offrir plus que le web.
- La règle « une seule opération longue à la fois » est rattachée à la CLI. L'exclusion mutuelle serveur/commandes par le verrou d'instance est **conservée** sans changement.
- Mise à jour des exigences qui citaient une page ou un formulaire supprimés (moteurs, modèles, exécutions, audios) pour citer la commande correspondante.

Hors périmètre : nouveau type de benchmark (change `ajouter-bench-extraction`), accès simultané web + CLI, changement du format des résultats, changement des indicateurs ou des tris, mode détaché de la CLI.

## Capabilities

### New Capabilities

Aucune.

### Modified Capabilities

- `local-web-interface` : consultation seule, plus de POST ni de script, navigation Résultats/Comparaisons/Historique, routes d'action supprimées.
- `cli-interface` (introduite par `ajouter-cli-agent`, non archivé) : CLI seule interface d'action, parité inversée vers les seules pages de consultation, opération longue unique rattachée à la CLI, arrêt par signal décrit sans référence à la page web.
- `engine-management` : installation et liste des moteurs par commande.
- `model-management` : vérification, téléchargement, inventaire et accès restreint décrits par commande ; exigences propres à la page Modèles retirées.
- `benchmark-runs` : préparation et sélection décrites par commande ; exigences propres au formulaire d'exécution retirées.
- `results-comparison` : l'historique complet est la page Historique.

## Impact

- Code : `transcription_bench/web/app.py` (routes, jeton, limites de formulaire), gabarits `audios.html`, `executions.html` (réduit à l'historique), `journal.html`, `modeles.html`, `moteurs.html`, `base.html` (navigation), `ressources/app.js` (supprimé), `parity.py` et `tests/test_parity.py` (sens de la parité), tests web associés. Services métier inchangés.
- Documentation : `README.md`, `docs/` (guide utilisateur et technique), en coordination avec `rediger-documentation-utilisateur` resté ouvert ; `AGENTS.md` (règles de l'interface web).
- Dépendances : aucune ajoutée ni retirée (Flask et Waitress restent nécessaires à la consultation).
- Ordre : `ajouter-cli-agent` MUST être archivé avant ce change, puisque ses deltas modifient la capability `cli-interface` qu'il crée. Ce change MUST être archivé avant `ajouter-bench-extraction`, dont les deltas supposent la consultation seule.
- La rédaction de ce change n'autorise aucune installation, aucun téléchargement ni aucune inférence réelle.
