## 1. Préalables

- [x] 1.1 Archivage de `add-benchmark-prototype` : fait le 2026-11-03 (`openspec/specs/` existe ; modification et renommage ont leur cible)
- [ ] 1.2 Mettre à jour `AGENTS.md` (règle « HTML sans CSS ni JavaScript » → « sans JavaScript, avec feuilles de style locales ») après relecture du propriétaire, puis demander /reload : à faire avant tout code, sinon l'implémentation enfreint la consigne actuelle
- [ ] 1.3 Ajouter `.gitattributes` déclarant `sumi.min.css` sans conversion de fin de ligne (`-text`)

## 2. Ressources figées

- [ ] 2.1 Copier `sumi.min.css` (commit amont `cee85b75efb2f129b82bc014439381b57ede7c22`, SHA-256 `3535cf90…7116`) dans un dossier de ressources du paquet, avec le texte de la licence MIT et une note de provenance (version, commit, SHA-256, date de récupération)
- [ ] 2.2 Écrire `app.css` : retours à la ligne et coupures (design D4-1), jetons de couleur Flexoki clair et sombre (D4-2, avis de licence en commentaire), règle `button.danger` (D4-3) ; aucune autre propriété
- [ ] 2.3 Ajouter les dépendances Sumi.css (MIT) et Flexoki (MIT) à la documentation des licences (`docs/licences-modeles.md`, dont l'intitulé ou la section est élargi au-delà des modèles)

## 3. Serveur

- [ ] 3.1 Routes GET `/sumi.css` et `/app.css` : un fichier connu chacune, `text/css; charset=utf-8` explicite, `nosniff`, `no-cache`, `static_folder=None` conservé

## 4. Gabarits

- [ ] 4.1 Refondre `base.html` : `viewport`, bloc `page_courante`, `header` + `nav` à deux listes avec `aria-label` (nom du programme en texte simple), encart d'avertissement clinique, `main`, deux `link` ; pas de `footer` ; `aria-current="page"` sur les huit pages, `"true"` sur le parent des sous-pages, aucun sur la page d'erreur
- [ ] 4.2 Envelopper chaque tableau dans un conteneur `overflow-auto` ; poser `prose`/`narrow` sur les blocs de texte courant (jamais sur `main`) ; **conserver** les liens d'action de l'accueil (aucun texte d'interface retiré)
- [ ] 4.3 Classe `danger` sur « Supprimer ce modèle local » et « Arrêter l'exécution » ; employer `callout` pour les refus, états et avertissements (en conservant `role="status"`)
- [ ] 4.4 Page d'erreur habillée par le même squelette

## 5. Tests

- [ ] 5.1 Remplacer `verifier_html_seul` (7 fichiers de test) et la constante de `tests/test_audios.py` par une fonction partagée fondée sur `html.parser` : autorise exactement les deux feuilles locales, interdit `script`, `style`, `iframe`, `object`, `img`, attribut `style`, attributs `on…`, liens `javascript:`
- [ ] 5.2 Remplacer le test « `/static/base.css` répond 404 » par les 404 de l'exigence « Aucun service de fichiers arbitraires »
- [ ] 5.3 Tests : en-têtes émis des feuilles et refus d'un `Host` non local, SHA-256 de `sumi.min.css`, `aria-current` (page, parent de sous-page, erreur), classes autorisées, absence de `dialog`/`role="button"`/`aria-busy`/`aria-invalid`/`data-theme`, propriétés autorisées d'`app.css`, classe `danger` sur les deux boutons seulement
- [ ] 5.4 Test de contraste WCAG ≥ 4,5 des paires de jetons de couleur d'`app.css`, clair et sombre (design D6) ; en cas d'échec, choisir une autre teinte de l'échelle Flexoki
- [ ] 5.5 Suite complète sous Linux ; la CI Windows doit rester verte (type MIME `text/css` explicite, SHA-256 inchangé grâce à `-text`)

## 6. Vérification visuelle (navigator, parole et données synthétiques)

- [ ] 6.1 Observer toutes les pages, y compris `comparaison.html` (côte à côte, non observée à ce jour) et la page d'erreur, à 360 px et 1280 px, en thème clair et sombre (rendu Flexoki, boutons `danger`, présence du `h1`)
- [ ] 6.2 Contrôler l'absence de défilement horizontal de la page à 360 px (tableaux, transcriptions, empreintes) et la largeur de lecture des textes à 1280 px
- [ ] 6.3 Contrôler la console : aucune ressource externe chargée (le `favicon.ico` 404 est connu et toléré)
- [ ] 6.4 Rejouer un parcours complet avec le moteur factice (lancer, suivre, consulter) pour confirmer qu'aucune action n'est cassée ; vérifier que `127.0.0.1` est autorisé pour le navigateur du navigator

## 7. Documentation et clôture

- [ ] 7.1 Corriger les mentions « sans CSS » du README
- [ ] 7.2 À l'archivage : corriger à la main le `## Purpose` de `openspec/specs/local-web-interface/spec.md` (« sans CSS ni JavaScript ») ; consigner en mémoire projet la décision (Sumi.css + Flexoki, bouton `danger` en couleur, pas de footer) et la provenance
