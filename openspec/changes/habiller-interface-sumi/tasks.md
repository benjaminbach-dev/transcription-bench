## 1. Préalables

- [x] 1.1 Archivage de `add-benchmark-prototype` : fait le 2026-11-03 (`openspec/specs/` existe ; modification et renommage ont leur cible)
- [ ] 1.2 Mettre à jour `AGENTS.md` (règle « HTML sans CSS ni JavaScript » → « sans JavaScript, avec feuilles de style locales ») après relecture du propriétaire, puis demander /reload : à faire avant tout code, sinon l'implémentation enfreint la consigne actuelle
- [x] 1.3 Ajouter `.gitattributes` déclarant `sumi.min.css` sans conversion de fin de ligne (`-text`)

## 2. Ressources figées

- [x] 2.1 Copier `sumi.min.css` (commit amont `cee85b75efb2f129b82bc014439381b57ede7c22`, SHA-256 `3535cf90…7116`) dans un dossier de ressources du paquet, avec le texte de la licence MIT et une note de provenance (version, commit, SHA-256, date de récupération)
- [x] 2.2 Écrire `app.css` : retours à la ligne et coupures (design D4-1), jetons de couleur Flexoki clair et sombre (D4-2, avis de licence en commentaire), règle `button.danger` (D4-3) ; aucune autre propriété
- [x] 2.3 Ajouter les dépendances Sumi.css (MIT) et Flexoki (MIT) à la documentation des licences (`docs/licences-modeles.md`, dont l'intitulé ou la section est élargi au-delà des modèles)

## 3. Serveur

- [x] 3.1 Routes GET `/sumi.css` et `/app.css` : un fichier connu chacune, `text/css; charset=utf-8` explicite, `nosniff`, `no-cache`, `static_folder=None` conservé

## 4. Gabarits

- [x] 4.1 Refondre `base.html` : `viewport`, bloc `page_courante`, `header` + `nav` à deux listes avec `aria-label` (nom du programme en texte simple), encart d'avertissement clinique, `main`, deux `link` ; pas de `footer` ; `aria-current="page"` sur les huit pages, `"true"` sur le parent des sous-pages, aucun sur la page d'erreur — fait au lot 2 (`h1` conservé dans le premier `li` du `nav`, encart `callout warning` dans le `header`, avant `main`) — NB : le nom du programme est finalement un `strong` (et non un `h1`) ; un `h1` par page (4.5)
- [x] 4.2 Envelopper chaque tableau dans un conteneur `overflow-auto` ; poser `prose`/`narrow` sur les blocs de texte courant (jamais sur `main`) ; **conserver** les liens d'action de l'accueil (aucun texte d'interface retiré) — fait au lot 2 (5 tableaux, aucun texte modifié)
- [x] 4.3 Classe `danger` sur « Supprimer ce modèle local » et « Arrêter l'exécution » ; employer `callout` pour les refus, états et avertissements (en conservant `role="status"`) — fait au lot 2 (9 `role="status"` conservés, chacun dans un encart)
- [x] 4.4 Page d'erreur habillée par le même squelette — fait au lot 2 (`erreur.html` étend `base.html`, statuts HTTP et messages inchangés, aucun `aria-current`)
- [x] 4.5 Corrections issues de la vérification visuelle du 2026-11-03 : coupures supplémentaires dans `app.css` (`p`, `li`, `strong`), nom du programme en `strong` et renumérotation des titres (un `h1` par page, design D7), `prose` homogène, `secondary` sur les boutons de vérification — fait au lot 3 (`anywhere` sur `p`/`li`/`strong` avec `break-word` conservé dans les cellules, `strong` dans le premier `li` du `nav`, h1 → h4 sans saut, `prose` sur tous les `p`/`ul`/`ol`/`dl` de contenu, trois boutons `secondary`, aucun texte modifié)

## 5. Tests

- [x] 5.1 Remplacer `verifier_html_seul` (7 fichiers de test) et la constante de `tests/test_audios.py` par une fonction partagée fondée sur `html.parser` : autorise exactement les deux feuilles locales, interdit `script`, `style`, `iframe`, `object`, `img`, attribut `style`, attributs `on…`, liens `javascript:` — fait au lot 2 (`tests/outils_html.py`, employé par les 7 fichiers)
- [x] 5.2 Remplacer le test « `/static/base.css` répond 404 » par les 404 de l'exigence « Aucun service de fichiers arbitraires » (partie feuilles faite, lot 1 ; doublon retiré de `tests/test_web.py` au lot 2, 404 couverts par `tests/test_feuilles.py`)
- [x] 5.3 Tests : en-têtes émis des feuilles et refus d'un `Host` non local, SHA-256 de `sumi.min.css`, `aria-current` (page, parent de sous-page, erreur), classes autorisées, absence de `dialog`/`role="button"`/`aria-busy`/`aria-invalid`/`data-theme`, propriétés autorisées d'`app.css`, classe `danger` sur les deux boutons seulement (partie feuilles faite au lot 1 ; parties `aria-current`, classes, attributs interdits et `danger` faites au lot 2 dans `tests/test_habillage.py`)
- [x] 5.4 Test de contraste WCAG ≥ 4,5 des paires de jetons de couleur d'`app.css`, clair et sombre (design D6) ; en cas d'échec, choisir une autre teinte de l'échelle Flexoki (fait au lot 1)
- [x] 5.5 Suite complète sous Linux : verte (764 tests au lot 4 ; 756, puis 762 aux lots précédents)
- [ ] 5.7 CI Windows verte : type MIME `text/css` explicite, SHA-256 inchangé grâce à `-text` (scénario « Extraction sous Windows »), non exécutable localement ; le run du 2026-11-03 sur `5c03627` a échoué sur un test existant sans rapport (`test_arret_utilisateur_interrompu_conserve_les_resultats`, course probable sous Windows)
- [x] 5.6 Tests de ces corrections (un `h1`, pas de saut de niveau ; `app.css` ; boutons `secondary`) — fait au lot 3 (sélecteurs de coupure contrôlés dans `tests/test_feuilles.py` ; hiérarchie des titres, `prose` homogène et boutons `secondary` dans `tests/test_habillage.py`, 6 tests ajoutés, suite verte à 762 tests)

## 6. Vérification visuelle (navigator, parole et données synthétiques)

- [x] 6.1 Observer toutes les pages, y compris `comparaison.html` (côte à côte, non observée à ce jour) et la page d'erreur, à 360 px et 1280 px, en thème clair et sombre (rendu Flexoki, boutons `danger`, présence du `h1`) — fait le 2026-11-03 (deux passes, thème clair réel à 360 et 1280 px, toutes les pages dont comparaison et erreur). **Limite** (suite en 6.5) : thème sombre observé seulement par approximation (injection des feuilles avec `@media all`), aucune émulation `prefers-color-scheme` disponible ; pas de captures conservées ; bouton « Arrêter l'exécution » vu en aperçu injecté (le moteur factice termine trop vite) ; état `:hover`/`:focus` non relevé
- [x] 6.2 Contrôler l'absence de défilement horizontal de la page à 360 px (tableaux, transcriptions, empreintes) et la largeur de lecture des textes à 1280 px — fait : aucune page ne défile horizontalement à 360 px après les lots 3 et 4 ; limite connue : la vue de comparaison côte à côte à 360 px reste étroite (colonnes de transcription ≈ 9 caractères par ligne, défilement interne du tableau)
- [x] 6.3 Contrôler la console : aucune ressource externe chargée (le `favicon.ico` 404 est connu et toléré) — fait : aucune requête hors de l'application, seules erreurs de console = `favicon.ico` 404 et la 404 volontaire
- [x] 6.4 Rejouer un parcours complet avec le moteur factice (lancer, suivre, consulter) pour confirmer qu'aucune action n'est cassée ; vérifier que `127.0.0.1` est autorisé pour le navigateur du navigator — fait avec le moteur factice (deux exécutions, résultat, comparaison, journal d'un moteur) sans action cassée
- [ ] 6.5 Observer le thème sombre réel (`prefers-color-scheme: dark`, scénario « Système en thème sombre ») ainsi que `:hover`/`:focus` : non fait, l'émulation de média n'est pas disponible dans le navigateur de l'hôte (seule une approximation par injection de feuilles a été observée)

## 7. Documentation et clôture

- [x] 7.1 Corriger les mentions « sans CSS » du README
- [ ] 7.2 À l'archivage : corriger à la main le `## Purpose` de `openspec/specs/local-web-interface/spec.md` (« sans CSS ni JavaScript ») ; consigner en mémoire projet la décision (Sumi.css + Flexoki, bouton `danger` en couleur, pas de footer) et la provenance
