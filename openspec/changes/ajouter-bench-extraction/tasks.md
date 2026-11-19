## 0. Essai minimal de faisabilité (PC de test Linux déclaré, accord explicite requis)

- [ ] 0.1 Avec accord explicite annonçant moteur, modèle et volumes : installer llama-cpp-python 0.3.36 depuis la roue CPU dans un environnement d'essai sous `data/`, télécharger un candidat du palier 8 Go, puis vérifier sur deux sources synthétiques au préfixe identique (D10 point 1) : chargement de l'architecture par l'API de bas niveau sans compilation de gabarit Jinja, conversion et chargement natif de la grammaire de la grille d'exemple et refus sans repli d'une grammaire invalide, arrêt sur les tokens de fin, format local comparé au gabarit embarqué lu comme texte, génération token par token, comptage et limite, réinitialisation et relecture intégrale, compteurs natifs, hors ligne, pic mémoire, arrêt. Consigner OS, machine, versions et verdict ; revenir au propriétaire avant tout repli (D4). Le runner séparé et le moteur factice (groupes 1 à 4) peuvent avancer en parallèle ; l'adaptateur réel (3.3) attend ce verdict.

## 1. Grilles

- [x] 1.1 Module `transcription_bench/grilles.py` : découverte confinée de `grilles/`, lecture bornée, interprétation (D1), clés, erreurs avec ligne et règle. Tests : cases simple/liste/composée/liste composée, règle « Liste » (`Liste.`, `Liste:`, `Liste :`, `Listes`, sans signe), consignes générales, blocs de code fermés et non fermés, `####`, `###` orphelin, normalisation des clés (accents, `œ`, ponctuation répétée), doublons, clé réservée, limites de taille et de nombre, noms et liens sortants refusés.
- [x] 1.2 Génération déterministe du schéma (D2) et validateur interne du sous-ensemble. Tests : schéma attendu pour la grille d'exemple, sortie conforme, case manquante, clé inconnue, clé JSON dupliquée, liste vide, chaîne vide, mauvais type, `null` accepté partout sauf `autres_informations`.
- [x] 1.3 Gabarit de consignes versionné (D3) produisant message système et message utilisateur. Tests : présence des règles fixes, des consignes de la grille et de chaque case ; version consignée.
- [x] 1.4 Grille d'exemple `grilles/consultation-generale.md` (D1) et commandes `grids list`, `grids show` avec `--json`, instantanés de clés, codes 0/2, aucune écriture ni réseau.

## 2. Moteurs et modèles

- [ ] 2.1 Déclarations : champ de tâche (transcription/extraction) sur chaque moteur, moteur `llama-cpp` et famille `llm-gguf` avec réglages `contexte` et `sortie_max`, famille d'extraction du moteur factice ; refus croisés de tâche. Tests sans import moteur dans le serveur.
- [ ] 2.2 Verrou `requirements/llama-cpp.in|txt` : llama-cpp-python 0.3.36 depuis l'index de roues CPU, verrou auto-porté, `--no-build`, contrôle d'import. Aucune installation réelle sur le serveur de développement ; la résolution du verrou n'est faite qu'avec l'accord du propriétaire et sans installer.
- [ ] 2.3 Compatibilité llama.cpp (règles de `model-management`) : architecture lue par `gguf.py`, liste blanche provisoire limitée aux architectures dotées d'un format local, fichiers auxiliaires et dépôts restreints refusés, choix `--file`. Tests avec en-têtes GGUF synthétiques et réponses de vérification simulées.

## 3. Exécution d'extraction

- [ ] 3.1 Protocole : événements `extraction` et `extraction_erreur`, champs requis et provenance factice ; tests de validation.
- [ ] 3.2 Runner `engines/runner_extraction.py` et contrat `charger`/`extraire` (D5), pic mémoire et contexte système réutilisés, réinitialisation avant chaque source, comptage du prompt soumis et refus « contexte insuffisant », validation de la sortie, cause de fin, états de source (D7). Tests avec l'adaptateur factice.
- [ ] 3.3 Adaptateur factice d'extraction (sortie conforme déterministe, mesures simulées) puis, après le verdict de 0.1, adaptateur `llama_cpp.py` (D4 : API de bas niveau sans classe `Llama` ni compilation Jinja, CPU, threads, contexte, graine, grammaire convertie et chargée nativement sans repli, formats locaux par architecture, génération token par token arrêtée sur tout token de fin, mesures D6, compteurs natifs seulement s'ils ont été vérifiés). L'adaptateur réel n'est testé sur le serveur de développement que par des tests unitaires sans import de la bibliothèque.
- [ ] 3.4 Service serveur d'extraction : sources `identifiant:ordre` (D8), validation de la demande, réservation et admission dans le créneau unique, supervision et arrêt réutilisés, écriture incrémentale sous `data/extractions/` avec `result.json` en dernier (D7), journal sans texte, nettoyage du fichier de travail, récupération des extractions abandonnées au démarrage. Tests : lot de trois sources, source en erreur, non conforme, contexte insuffisant, grammaire en échec, arrêt après la première source, interruption entre deux écritures, abandon puis récupération, immuabilité, copie des sources.
- [ ] 3.5 Commandes `extract options`, `extract check`, `extract start` : JSON, journal en flux, codes 0/1/2/3 (D7), signal. Instantanés de clés.

## 4. Consultation

- [ ] 4.1 Service de consultation des extractions : regroupement par source, grille et schéma (D9), tris, indicateurs et ratios, factices séparés, version de consignes différente signalée, aucune écriture. Tests.
- [ ] 4.2 Commandes `extract list`, `extract show`, `extract compare` (2 à 6 sélections, factices et réelles non mêlées), `extract explain` ; `results history` étendu aux extractions avec leur type. Instantanés de clés.
- [ ] 4.3 Pages web `/extractions`, `/extractions/<id>`, `/extractions/aide`, `/extractions/comparaison`, `/extractions/comparaison/<cle>` (GET, sans script, contrôle `Host`, échappement) ; navigation à quatre rubriques ; Historique à deux types ; table de parité étendue. Tests de gabarits, de structure et d'échappement.
- [ ] 4.4 Contrôle visuel par le propriétaire du détail (grille et source côte à côte) et de la comparaison à six modèles, clair et sombre, 1280 et 360 px.

## 5. Documentation et vérifications

- [ ] 5.1 Documentation : guide (écrire une grille, lancer une extraction, relire et comparer), technique (protocole, stockage, mesures, formats locaux), `docs/licences-modeles.md` (six modèles candidats, licences Apache 2.0, conditions d'accès), rappel « grille remplie ≠ exactitude médicale » ; adaptation de `tests/test_documentation.py` sans contourner ses contrôles.
- [x] 5.2 Mettre à jour `AGENTS.md` (périmètre étendu à l'extraction, moteur llama.cpp, CI inchangée sans nouvel accord) — validé avec le propriétaire lors de la rédaction des specs.
- [ ] 5.3 `openspec validate ajouter-bench-extraction --strict`, suite de tests complète avec moteur factice sur le serveur de développement ; relecture advisor ; consigner décisions et limites en mémoire projet.

## 6. Qualification réelle (PC de test Linux déclaré, accord explicite requis)

- [ ] 6.1 Installer `llama-cpp` depuis le verrou par le programme, sans compilation ; consigner OS, machine, versions, durée et taille de l'environnement.
- [ ] 6.2 Vérifier puis télécharger les six modèles candidats (environ 31 Go) ; consigner le commit de révision complet et l'architecture GGUF de chacun ; fixer la liste blanche définitive.
- [ ] 6.3 Extraire avec la grille d'exemple les trois transcriptions des audios Gemini existants pour chaque modèle, threads 8 ; verdict par modèle (chargé, conforme, mesures), budget RAM mesuré par palier, hors ligne, arrêt par signal ; consigner sans extrapolation à d'autres machines.
- [ ] 6.4 Vérification Windows : uniquement si le propriétaire autorise une extension de la CI ; sinon consigner la limite « non vérifié sous Windows ».
