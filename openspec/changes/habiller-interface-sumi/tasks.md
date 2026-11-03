## 1. Préalables

- [ ] 1.1 Vérifier l'état de l'archivage de `add-benchmark-prototype` (non archivé à la rédaction, volontairement) ; s'il ne l'est toujours pas, demander au propriétaire comment traiter la modification de l'exigence avant d'implémenter

## 2. Ressources figées

- [ ] 2.1 Copier `sumi.min.css` (commit amont `cee85b75efb2f129b82bc014439381b57ede7c22`, SHA-256 `3535cf90…7116`) dans un dossier de ressources du paquet, avec le texte de la licence MIT et une note de provenance (version, commit, SHA-256, date de récupération)
- [ ] 2.2 Écrire `app.css` limité aux retours à la ligne et coupures (design D4), sans couleur, police, taille ni jeton
- [ ] 2.3 Ajouter la dépendance Sumi.css (MIT) à `docs/licences-modeles.md`

## 3. Serveur

- [ ] 3.1 Routes GET `/sumi.css` et `/app.css` : un fichier connu chacune, `text/css; charset=utf-8` explicite, `nosniff`, `no-cache`, `static_folder=None` conservé

## 4. Gabarits

- [ ] 4.1 Refondre `base.html` : `viewport`, bloc `page_courante`, `header` + `nav` à deux listes, encart d'avertissement clinique, `main`, `footer`, deux `link`
- [ ] 4.2 Envelopper chaque tableau dans un conteneur défilant ; limiter la largeur de lecture des textes ; remplacer les liens d'action de l'accueil par les éléments de navigation sans perdre d'information
- [ ] 4.3 Différencier les actions destructrices (suppression de modèle, arrêt d'exécution) et employer `callout` pour les refus, états et avertissements
- [ ] 4.4 Page d'erreur habillée par le même squelette

## 5. Tests

- [ ] 5.1 Adapter les tests existants qui interdisent `<link>`/`stylesheet` (`tests/test_web.py`, `tests/test_audios.py`, autres) : autoriser exactement les deux feuilles locales, conserver les interdictions de script, style et attribut `style`
- [ ] 5.2 Remplacer le test « `/static/base.css` répond 404 » par les 404 de l'exigence « Aucun service de fichiers arbitraires »
- [ ] 5.3 Tests : en-têtes des feuilles, SHA-256 de `sumi.min.css`, `aria-current` unique, classes autorisées, absence de `dialog`, contenu borné d'`app.css`
- [ ] 5.4 Suite complète sous Linux ; la CI Windows doit rester verte (type MIME `text/css` explicite)

## 6. Vérification visuelle (navigator, parole et données synthétiques)

- [ ] 6.1 Observer toutes les pages, y compris `comparaison.html` (côte à côte, non observée à ce jour) et la page d'erreur, à 1280 px et 420 px, en thème clair et sombre
- [ ] 6.2 Contrôler l'absence de défilement horizontal de la page à 420 px (tableaux, transcriptions, empreintes)
- [ ] 6.3 Contrôler la console : aucune ressource externe chargée (le `favicon.ico` 404 est connu et toléré)
- [ ] 6.4 Rejouer un parcours réel avec le moteur factice (lancer, suivre, consulter) pour confirmer qu'aucune action n'est cassée

## 7. Documentation

- [ ] 7.1 Mettre à jour `AGENTS.md` (règle « HTML sans CSS ni JavaScript » → « sans JavaScript, avec feuilles de style locales ») après relecture du propriétaire, puis demander /reload
- [ ] 7.2 Corriger les mentions « sans CSS » du README et des specs de référence ; consigner la décision et la provenance de Sumi.css en mémoire projet
