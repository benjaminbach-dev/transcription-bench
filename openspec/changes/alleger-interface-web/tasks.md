## 1. Réduction de l'application web

- [x] 1.1 Supprimer les routes d'action et pages associées (D1) : `/audios`, `/modeles` et ses POST, `/moteurs`, `/moteurs/<id>/installer`, `/moteurs/<id>/journal`, `/operation`, `/executions/etat`, POST de `/executions`, `/dossiers/verifier` ; réduire `/executions` à l'historique complet libellé Historique ; retirer gabarits, messages d'action et code devenus inutiles. Tests : 404 pour chaque page supprimée, 405/404 pour toute méthode autre que GET/HEAD (`OPTIONS` compris), aucun appel aux services d'action depuis l'application web.
- [x] 1.2 Retirer le jeton anti-CSRF, le contrôle `Origin` des POST et les limites de formulaire ; conserver le contrôle `Host` sur toutes les routes, le confinement des identifiants et l'échappement. Tests : Host étranger refusé sur chaque route conservée, identifiant sortant refusé, contenu hostile échappé.
- [x] 1.3 Supprimer `/app.js` et son fichier, retirer toute balise `script` des gabarits, passer la CSP à `script-src 'none'` (D2). Tests : aucune page ne contient de `script`, `/app.js` répond 404, en-tête CSP attendu.
- [x] 1.4 Navigation Résultats, Comparaisons, Historique ; liens internes et états vides renvoyant aux commandes du programme ; `/` redirige vers `/resultats`. Mettre à jour les tests de squelette, de navigation et d'accessibilité existants sans affaiblir leurs contrôles.
- [x] 1.5 Ne plus construire pour le serveur le créneau d'opération ni la supervision de moteur ; conserver verrou d'instance et récupération au démarrage (D4). Tests : démarrage/arrêt du serveur avec libération du verrou, récupération d'une exécution abandonnée toujours appliquée.

## 2. CLI et parité

- [x] 2.1 Inverser la table de parité (D3) : page de consultation → commande de lecture, exclusions `/` et feuilles de style ; adapter `tests/test_parity.py` pour qu'une nouvelle page sans commande fasse échouer la suite et qu'une commande sans page soit admise.
- [x] 2.2 Vérifier que les messages, l'aide `--help` et les sorties des commandes ne renvoient plus à des pages supprimées ; refus d'une seconde opération en code 2 toujours testé.

## 3. Documentation et vérifications

- [x] 3.1 Mettre à jour `README.md` et `docs/` (guide utilisateur et technique : actions par commandes, web en consultation seule) en coordination avec `rediger-documentation-utilisateur` ; adapter `tests/test_documentation.py` sans contourner ses contrôles.
- [x] 3.2 Mettre à jour `AGENTS.md` (interface web de consultation seule, sans script) — validé avec le propriétaire lors de la rédaction des specs.
- [x] 3.3 `openspec validate alleger-interface-web --strict`, suite de tests complète avec moteur factice sur le serveur de développement ; relecture advisor ; consigner la décision en mémoire projet.
- [ ] 3.4 Contrôle visuel par le propriétaire des trois pages (Résultats, Comparaisons, Historique) dans un navigateur, clair et sombre, 1280 et 360 px.
- [ ] 3.5 Archiver après `ajouter-cli-agent` (D5) ; actualiser à cette occasion le `Purpose` de `local-web-interface` (D1) et valider l'état fusionné des specs.
