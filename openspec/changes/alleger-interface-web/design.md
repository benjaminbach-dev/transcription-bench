## Context

Voir `proposal.md`. État constaté du code (lecture seule, 2026-11-19) :

- `transcription_bench/web/app.py` déclare les routes GET de consultation (`/`, `/resultats`, `/resultats/<id>`, `/resultats/aide`, `/resultats/comparaison`, `/resultats/comparaison/<empreinte>`), trois ressources fixes (`/sumi.css`, `/app.css`, `/app.js`), des pages d'action (`/audios`, `/executions`, `/modeles`, `/moteurs`, `/moteurs/<id>/journal`, `/operation`, `/executions/etat`) et sept POST protégés par jeton anti-CSRF et contrôle `Origin`.
- `/executions` mélange la préparation d'une exécution et l'historique complet exigé par `results-comparison` (« Liste des exécutions »).
- `ressources/app.js` ne sert qu'à la préparation d'exécution (choix compatibles) et au suivi d'opération (`/executions/etat`).
- `parity.py` associe chaque route à une commande ou à une exclusion ; `tests/test_parity.py` échoue si une route n'a pas d'entrée.
- La composition des services (`composition.py`) est partagée par `serve` et les commandes ; le verrou d'instance rend serveur et commandes mutuellement exclusifs.

## Goals / Non-Goals

**Goals :** web de consultation seule, sans POST ni script ; suppression du code d'action web devenu inutile ; CLI seule interface d'action ; aucune perte de fonction (chaque action supprimée du web existe déjà en commande).

**Non-Goals :** accès simultané web + CLI, nouveaux indicateurs, changement de présentation des pages conservées, changement du format des résultats.

## Decisions

### D1. Routes conservées et supprimées

| Route | Sort |
|---|---|
| `GET /` | conservée : redirection vers `/resultats` |
| `GET /resultats`, `/resultats/<id>`, `/resultats/aide`, `/resultats/comparaison`, `/resultats/comparaison/<empreinte>` | conservées sans changement de contenu, hormis les liens vers des pages supprimées |
| `GET /executions` | conservée, réduite à l'historique complet, libellée « Historique » ; l'URL est gardée pour ne pas casser les liens existants |
| `GET /sumi.css`, `/app.css` | conservées |
| `GET /app.js` | supprimée (404), fichier retiré |
| `GET /audios`, `/modeles`, `/moteurs`, `/moteurs/<id>/journal`, `/operation`, `/executions/etat` | supprimées (404) |
| tout `POST` (`/executions/verifier`, `/executions/lancer`, `/executions/arreter`, `/modeles/verifier`, `/modeles/telecharger`, `/modeles/supprimer`, `/moteurs/<id>/installer`, `/dossiers/verifier`) | supprimé ; toute méthode autre que GET/HEAD, `OPTIONS` automatique de Flask compris, reçoit 405 (route existante) ou 404 |

Le `Purpose` de `openspec/specs/local-web-interface/spec.md` (« piloter entièrement depuis une page web ») ne se modifie pas par delta : il est actualisé à l'archivage (« consulter les résultats depuis une page web locale »).

Alternative écartée : pages résiduelles « utilisez la CLI » à la place des pages supprimées. Elles ajoutent des gabarits pour un public unique qui connaît déjà la CLI ; un 404 standard suffit, la documentation donne les commandes.

### D2. Sécurité conservée, protections d'action retirées

Le serveur reste sur la boucle locale, contrôle `Host` sur toutes les routes, confine les chemins et identifiants, échappe tout contenu et applique une CSP. Sans POST, le jeton anti-CSRF par démarrage, le contrôle `Origin` des POST et les limites de formulaire (64 Kio, 413/415) n'ont plus d'objet et sont retirés avec leur code. Sans script, la CSP passe à `script-src 'none'` en conservant les autres directives (styles et connexions limités à l'origine locale, `frame-ancestors 'none'`, `base-uri 'none'`, `form-action 'self'` pour les formulaires GET de tri et de sélection). La limite de corps de Waitress reste celle du serveur HTTP.

### D3. Parité inversée

`parity.py` ne décrit plus « route d'action → commande » mais « page de consultation → commande de lecture » : `/resultats` → `results list`, `/resultats/<id>` → `results show`, `/resultats/aide` → `results explain`, `/resultats/comparaison` → `results list`, `/resultats/comparaison/<empreinte>` → `compare`, `/executions` → `results history` ; exclusions : `/`, ressources CSS. Le test confronte toujours la table aux routes réelles : une nouvelle page sans commande de lecture fait échouer la suite. L'inverse n'est plus exigé : une commande peut exister sans page.

### D4. Opération longue unique et arrêt

Le serveur ne démarrant plus aucune opération, il ne construit plus le créneau d'opération ni la supervision de moteur pour ses besoins propres ; la récupération des exécutions abandonnées au démarrage reste appliquée, comme avant chaque commande. L'arrêt du serveur libère le verrou sans moteur à terminer. La règle « une seule opération longue à la fois » est désormais portée par `cli-interface` ; elle est de toute façon garantie par le verrou d'instance.

### D5. Ordre des changes et deltas

`ajouter-cli-agent` crée `cli-interface` mais n'est pas archivé (tâche 4.5, qualification Windows des commandes, laissée ouverte par décision du propriétaire). Les deltas `cli-interface` de ce change supposent son archivage préalable ; l'implémentation peut néanmoins commencer avant, le code de la CLI étant déjà en place. `refondre-parcours-resultats` est archivé. `mesurer-charge-systeme` (terminé, non archivé) modifie `benchmark-runs` (« Mesures enregistrées » et exigences nouvelles) et ajoute des exigences à `results-comparison` ; aucune ne recoupe les exigences modifiées ou retirées ici (vérifié à la rédaction le 2026-11-19), son archivage peut donc précéder ou suivre celui-ci.

## Risks / Trade-offs

- **Perte d'un suivi visuel des opérations** : le journal en flux de la CLI le remplace ; c'est l'usage constaté du propriétaire.
- **Liens externes vers les pages supprimées** (marque-pages) : 404 assumé, outil mono-utilisateur.
- **Documentation et tests documentaires** : `tests/test_documentation.py` contrôle des libellés ; la documentation est adaptée sans contourner ces contrôles, en coordination avec `rediger-documentation-utilisateur`.
- **Archivage dépendant** d'`ajouter-cli-agent` : si sa tâche 4.5 reste ouverte longtemps, l'archivage de ce change attend ; le propriétaire peut décider d'archiver `ajouter-cli-agent` avec cette limite consignée.
