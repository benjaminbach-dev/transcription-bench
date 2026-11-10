## Why

Le programme ne se pilote aujourd'hui que par la page web. Or l'usage prévu est celui d'un prototype d'aide à la décision, utilisé par une seule personne, qui doit pouvoir confier à un agent la préparation, le lancement et la lecture des essais. Un agent se sert naturellement de commandes de terminal à sortie structurée ; il ne manipule pas un formulaire HTML avec jeton anti-CSRF.

## What Changes

- Ajout de sous-commandes à `transcription-bench` couvrant **100 %** des fonctions de la page web : audios, moteurs (liste, installation, journal), modèles (vérification, téléchargement, inventaire, suppression), exécutions (options de préparation, vérification à blanc, lancement, historique), résultats (liste groupée, détail, aide des indicateurs) et comparaison.
- **Web d'abord** : `transcription-bench` sans sous-commande, avec ou sans `--port`, continue de lancer le serveur web exactement comme aujourd'hui ; une sous-commande explicite `serve` est l'équivalent.
- **Exclusion web/CLI** : le programme tourne soit en serveur web, soit en commande, jamais les deux. Toutes les commandes prennent le verrou d'instance existant et refusent proprement (code 2, message clair) si le serveur ou une autre commande le tient. Aucun arbitrage de concurrence nouveau.
- Chaque commande est un processus bloquant : une opération longue (installation, téléchargement, exécution) affiche son journal au fil de l'eau, se termine avec un code de sortie explicite et s'interrompt par `Ctrl+C` / `SIGTERM` avec la même sémantique que l'arrêt du serveur (résultats déjà écrits conservés, exécution marquée interrompue).
- Sortie lisible en français par défaut, `--json` (schéma versionné, clés verrouillées par test) sur toutes les commandes pour les agents ; aide `--help` complète servant de documentation de découverte.
- Extraction de la composition des services (aujourd'hui dans `cli.py`) pour que `serve` et les commandes construisent exactement les mêmes services ; aucune logique métier dupliquée.
- Même contrôle de chemins, mêmes refus métier et mêmes règles de modèle/moteur que la page web, via les mêmes services.

Hors périmètre : serveur MCP, mode détaché ou démon, accès concurrent web + CLI, commandes lisant les résultats pendant que le serveur tourne, nouvelle dépendance, changement du format des résultats, nouvelle fonction absente de la page web.

## Capabilities

### New Capabilities

- `cli-interface` : sous-commandes, parité fonctionnelle avec la page web, exclusion avec le serveur, sortie JSON, codes de sortie, opérations longues bloquantes, arrêt par signal, aide.

### Modified Capabilities

- `local-web-interface` : le lancement du serveur reste la commande par défaut ; exigence ajoutée d'exclusion mutuelle avec les commandes.

## Impact

`transcription_bench/cli.py` (analyse des arguments, sous-commandes), nouveau module de composition des services et nouveaux modules de commandes ; `pyproject.toml` inchangé si `argparse` suffit (aucune dépendance ajoutée). Services existants (`moteurs`, `gestion_modeles`, `verification_modeles`, `executions`, `execution_moteur`, `consultation_resultats`, `audios`, `operations`) réutilisés sans changement de comportement ; ajustements éventuels limités à rendre leurs données sérialisables en JSON. Tests unitaires avec moteur factice, sans réseau. Documentation : guide technique et section agent. Le change `rediger-documentation-utilisateur` (en cours) devra être complété ou croisé avec la nouvelle documentation CLI, sans bloquer celui-ci.

La rédaction de ce change n'autorise ni installation de moteur, ni téléchargement, ni inférence réelle ; la qualification des commandes réelles reste à réaliser sur le PC de test.
