## Context

Voir `proposal.md`. Constats (lecture du code et recherches documentaires du 2026-11-19, aucune installation ni inférence) :

- Le serveur supervise des moteurs isolés : un environnement uv par moteur (`data/engines/<moteur>`, marqueur `installation.json`), un runner lancé en sous-processus avec un `job.json`, des événements préfixés `##TB-EVENT## ` (`chargement`, `audio`, `audio_erreur`, `fin`), un pic mémoire relevé dans le runner, des mesures système facultatives (`mesurer-charge-systeme`), un stockage atomique et immuable sous `data/results/`.
- Ce socle est générique ; l'entrée (signal audio), le contrat d'adaptateur (`transcrire`), les champs de l'événement `audio`, le RTF et le découpage en fenêtres sont propres à la transcription.
- Aucun moteur actuel ne convient : `transcribe-cpp` n'expose qu'un décodeur ASR ; CTranslate2 génère du texte mais sans sortie contrainte ; Transformers sur CPU est lent et la contrainte demanderait une dépendance supplémentaire (outlines).
- llama-cpp-python 0.3.36 (1er octobre 2026, llama.cpp `0c1e57098`) publie des roues CPU `py3-none-manylinux2014_x86_64` et `py3-none-win_amd64` sur l'index `https://abetlen.github.io/llama-cpp-python/whl/cpu/` — la page plate utilisée par `--find-links` est `https://abetlen.github.io/llama-cpp-python/whl/cpu/llama-cpp-python/` (vérifié le 2026-11-19) ; la 0.3.37 n'a pas de roue CPU sur cet index. PyPI ne fournit que la source. Licence MIT. La contrainte `response_format` avec schéma JSON est convertie en grammaire GBNF.
- Modèles candidats vérifiés par l'API publique Hugging Face (métadonnées seules, 2026-11-19) : tous Apache 2.0, non restreints.

| Palier | Dépôt GGUF | Fichier | Taille | Révision vue |
|---|---|---|---|---|
| 8 Go | `mistralai/Ministral-3-3B-Instruct-2512-GGUF` | `Ministral-3-3B-Instruct-2512-Q8_0.gguf` | 3,65 Go | `eb599d40…` |
| 8 Go | `unsloth/Qwen3.5-4B-GGUF` | `Qwen3.5-4B-Q4_K_M.gguf` | 2,74 Go | `e87f1764…` |
| 16 Go | `mistralai/Ministral-3-8B-Instruct-2512-GGUF` | `Ministral-3-8B-Instruct-2512-Q4_K_M.gguf` | 5,20 Go | `0102285a…` |
| 16 Go | `unsloth/Qwen3.5-9B-GGUF` | `Qwen3.5-9B-Q4_K_M.gguf` | 5,68 Go | `3885219b…` |
| 16 Go | `ibm-granite/granite-4.2-8b-GGUF` | `granite-4.2-8b-Q4_K_M.gguf` | 5,35 Go | `93f3f6a8…` |
| 16 Go | `ggml-org/gemma-4-E4B-it-GGUF` | `gemma-4-E4B-it-Q8_0.gguf` | 8,03 Go | `8903cb40…` |

Le palier est une recommandation documentaire (poids + contexte + système), pas une règle du programme. Les qualités en français, les débits CPU et la prise en charge de ces architectures par la version de llama.cpp embarquée **ne sont pas vérifiés** : ils relèvent de la qualification sur PC. Écartés : MedGemma (accès restreint, entraînement majoritairement anglophone), LFM2.5 (licence limitée selon le chiffre d'affaires), EuroLLM-22B (trop lourd), modèles < 2 B (extraction peu fiable selon les sources consultées).

## Goals / Non-Goals

**Goals :** mesurer les ressources d'une extraction structurée locale sur CPU ; grilles modifiables par un humain et compréhensibles par un agent ; résultat relisible case par case à côté de la transcription source ; réutiliser au maximum le socle (moteurs isolés, supervision, stockage, mesures, CLI, consultation).

**Non-Goals :** juger la qualité ; saisie libre de texte ; enchaînement audio → extraction ; second moteur LLM ; GPU ; streaming affiché ; comparaison entre transcription et extraction.

## Decisions

### D1. Format des grilles

Fichier `grilles/<nom>.md` (nom `[a-z0-9][a-z0-9-]{0,63}`), UTF-8, au plus 64 Kio, versionné. Exemple fourni :

```markdown
# Consultation de médecine générale

Consignes : n'extraire que ce qui est dit pendant la consultation.

## Qui ?
Personnes présentes et leur rôle (patient, accompagnant, soignant).

## Quand ?
Date, moment ou délai évoqués pour les faits rapportés.

## Motif de consultation ?

## Symptômes déclarés ?
Liste. Un symptôme par entrée, avec durée ou intensité si dites.

## Examens pratiqués ?
Liste. Examen clinique ou complémentaire réalisé ou demandé, avec résultat s'il est dit.

## Doute restant ?
Hypothèses non tranchées, points à vérifier.

## Prescription ?
Liste.
### Médicament
### Posologie
### Durée

## Prise en charge ?
Orientation, conseils, suivi prévu.
```

Règles d'interprétation (déterministes, sans dépendance) :

- Le premier contenu non vide est un titre `# ` unique : le titre de la grille. Le texte avant le premier `## ` forme les consignes générales.
- `## Libellé` ouvre une case ; le texte jusqu'au titre suivant est sa consigne (facultative). La case est une liste si la première ligne non vide de sa consigne, blancs de tête retirés, commence par le mot `Liste` (casse ignorée), suivi d'espaces facultatifs puis de `.` ou `:` ; `Liste.`, `Liste:` et `Liste :` comptent, alors que `Listes`, `Liste des…` ou `Liste` sans signe laissent une case texte.
- `### Libellé` sous une case ouvre une sous-case ; la case devient composée. Une sous-case peut aussi être une liste (même règle). Une case composée garde sa propre consigne pour la liste ou l'objet entier. `####` et plus profond sont refusés, de même qu'un `###` avant tout `##`.
- Blocs de code : une ligne commençant (après au plus trois espaces) par trois accents graves ou trois tildes ouvre un bloc, fermé par une ligne commençant par la même clôture ; les titres qu'il contient ne sont pas interprétés et restent du texte de consigne. Un bloc non fermé rend la grille invalide.
- Clé de chaque case : décomposition Unicode NFKD, marques diacritiques retirées, `œ`→`oe`, `æ`→`ae`, `ß`→`ss`, minuscules, toute suite de caractères hors `[a-z0-9]` remplacée par un seul `_`, `_` retirés en tête et en fin. Exemples : `Examens pratiqués ?` → `examens_pratiques` ; `Œdème / douleur !!` → `oedeme_douleur` ; `Qui ?` et `Qui` → `qui` (doublon refusé). Une clé vide, un doublon au même niveau ou la clé réservée `autres_informations` sont refusés. Au plus 60 cases et sous-cases au total, au moins une case.
- Toute erreur produit un refus nommant la ligne et la règle ; une grille invalide n'est jamais proposée à l'exécution.

### D2. Schéma JSON généré

Toutes les clés sont requises, `additionalProperties: false`, et `null` signifie « non mentionné » :

| Case | Schéma de la valeur |
|---|---|
| texte | `{"anyOf": [{"type": "string"}, {"type": "null"}]}` |
| liste de textes | `{"anyOf": [{"type": "array", "items": {"type": "string"}, "minItems": 1}, {"type": "null"}]}` |
| composée | `{"anyOf": [{"type": "object", "properties": {…sous-cases…}, "required": […], "additionalProperties": false}, {"type": "null"}]}` |
| liste composée | `{"anyOf": [{"type": "array", "items": {objet des sous-cases}, "minItems": 1}, {"type": "null"}]}` |
| `autres_informations` (ajoutée d'office, en dernier) | `{"type": "array", "items": {"type": "object", "properties": {"intitule": {"type": "string"}, "valeur": {"type": "string"}}, "required": ["intitule", "valeur"], "additionalProperties": false}}` |

Ce sous-ensemble (objets, tableaux, `anyOf`, `null`, `minItems`, `required`, `additionalProperties`) est choisi parce qu'il est documenté comme pris en charge par la conversion JSON Schema → GBNF de llama.cpp ; sa prise en charge effective par la version embarquée est à prouver sur PC. Le programme valide lui-même la sortie contre ce schéma restreint (validateur interne d'une centaine de lignes, sans dépendance) : la contrainte du moteur n'est pas tenue pour une preuve. Le décodage refuse les clés JSON dupliquées (non conforme). `null` = non mentionné ; une chaîne vide est conforme mais affichée « (vide) », distincte de « non mentionné » ; une liste vide est non conforme (`minItems`), sauf `autres_informations`.

Conformité ≠ exactitude : elle ne dit que la forme.

### D3. Consignes envoyées au modèle

Un gabarit de consignes du programme, versionné (`version_consignes`), produit deux messages :

- **système** : rôle (extraire d'une transcription de consultation les informations demandées) ; règles fixes (n'utiliser que ce qui est dit ; `null` si non mentionné ; ne rien inventer ni déduire ; reprendre noms de médicaments, doses et chiffres tels qu'entendus ; ignorer le bavardage ; consigner dans `autres_informations` ce qui est utile mais hors grille) ; consignes générales de la grille ; liste des cases avec clé, libellé, type et consigne.
- **utilisateur** : la transcription source, délimitée.

Le gabarit n'est pas configurable (YAGNI) ; toute modification incrémente `version_consignes`, consignée avec le résultat et affichée en cas de différence dans une comparaison.

**Format de conversation local.** Le gabarit Jinja embarqué dans un GGUF est un contenu fourni par le dépôt ; l'interpréter, même en bac à sable, contredirait la règle « aucun code distant ». Le programme maintient donc localement, dans l'adaptateur, un format de conversation par architecture admise (assemblage de chaînes et de tokens spéciaux, sans moteur de gabarits), versionné (`version_format`). Une architecture sans format local n'est pas admise. Le gabarit embarqué n'est jamais exécuté : il est lu comme texte lors de la qualification pour vérifier la correspondance, et son SHA-256 est consigné avec le résultat à titre d'information. Le mode raisonnement éventuel est désactivé dans ce format quand l'architecture le prévoit.

### D4. Moteur llama.cpp

- Déclaration `llama-cpp`, tâche `extraction`, verrou `requirements/llama-cpp.txt` (llama-cpp-python 0.3.36 depuis l'index de roues CPU, dépendances pures Python en verrou auto-porté comme pour Transformers), `uv pip sync --no-build` : une roue absente fait échouer l'installation au lieu de compiler.
- Famille `llm-gguf` : architecture lue dans `general.architecture` par `gguf.py` existant (inchangé), comparée à une liste blanche d'architectures disposant d'un format local (D3), provisoire jusqu'à la qualification. Fichiers auxiliaires (`mmproj-*`, `mtp-*`, architecture `clip`) refusés. Les dépôts à accès restreint sont refusés pour ce moteur ; la politique des moteurs de transcription est inchangée.
- **API de bas niveau uniquement** : l'adaptateur utilise les liaisons C de llama-cpp-python (`llama_cpp` : chargement du modèle, contexte, tokenisation, décodage, chaîne d'échantillonnage) et **jamais la classe `Llama`**, dont le constructeur 0.3.36 compile en Jinja2 les gabarits embarqués dès le chargement. Chargement : aucune couche GPU, threads de lecture et de génération = threads demandés, taille de contexte = réglage `contexte`, graine fixe, journaux natifs redirigés hors de la sortie d'événements ; aucun cache de prompt ; projection mémoire (`mmap`) laissée par défaut et consignée comme mode de chargement des poids.
- Grammaire : le schéma est converti en GBNF par le convertisseur Python du paquet (`json_schema_to_gbnf`), puis chargée nativement en initialisant l'échantillonneur de grammaire, une fois par exécution et avant la première source. Une exception de conversion ou un échantillonneur nul met l'exécution en échec avec ce motif, sans génération. `response_format` n'est pas utilisé : dans la 0.3.36, il retombe silencieusement sur une grammaire JSON générique si la conversion échoue.
- Génération : le prompt est rendu par le format local (D3) puis tokenisé par le modèle, tokens spéciaux compris ; ce sont **ces tokens** qui sont comptés, comparés à la limite et soumis. La génération se fait token par token (décodage de bas niveau, chaîne d'échantillonnage grammaire puis glouton), jusqu'à **tout token de fin de génération** reconnu par le vocabulaire du modèle ou à `sortie_max` ; la sortie est détokenisée à la fin.
- Réglages exposés : `contexte` (défaut 16384 tokens) et `sortie_max` (défaut 4096 tokens). Température nulle (glouton), graine et échantillonnage sont fixes et consignés.
- Avant chaque source, la mémoire du contexte (cache KV) est vidée et l'échantillonneur réinitialisé : sans cela, le préfixe commun des consignes serait réutilisé et fausserait la lecture des sources suivantes. La relecture intégrale est vérifiée par l'essai minimal (tâche 0) avec deux sources au préfixe identique.
- Si le nombre de tokens du prompt augmenté de `sortie_max` dépasse `contexte`, la source est en erreur « contexte insuffisant » sans troncature ni génération.

Alternatives écartées : binaire `llama-server` en sous-processus (serveur HTTP local supplémentaire, téléchargement de binaires hors pip ; gardé comme repli si la roue 0.3.36 échoue sur PC) ; CTranslate2 (pas de contrainte) ; ONNX Runtime GenAI (export ONNX et contrainte non prouvée en roue) ; OpenVINO GenAI (CPU AMD hors exigences officielles) ; Ollama/LM Studio (services externes).

### D5. Runner et protocole

Un runner distinct `engines/runner_extraction.py` réutilise les modules communs (`protocole`, `hors_ligne`, `mesures_systeme`, pic mémoire) ; le runner audio reste inchangé. Job `version: 1`, `tache: "extraction"`, avec moteur, famille, modèle, threads, réglages, schéma, messages système et liste ordonnée de sources (texte + ordre). Contrat d'adaptateur : `charger(modele, threads_demandes, reglages, schema)` (modèle et grammaire) puis `extraire(moteur, messages, reglages)` qui rend sortie brute, compteurs et chronométrages. Nouveaux événements : `extraction` et `extraction_erreur` ; `chargement` et `fin` sont réutilisés. Les champs requis et la provenance `factice`/`mesures_simulees` suivent les règles existantes.

### D6. Mesures

Par source, mesurées par le programme sur la génération token par token (D4) :

- `tokens_entree` : nombre de tokens du prompt soumis ; `tokens_sortie` : nombre de tokens générés (token de fin exclu) ;
- `delai_premier_token_s` : du début de la génération à l'obtention du premier token généré ; il inclut la lecture du prompt **et** le calcul du premier token ;
- `duree_generation_s` : du premier au dernier token généré ; `duree_extraction_s` : génération complète, détokenisation et validation comprises ;
- `vitesse_generation_tps` = (tokens_sortie − 1) / durée de génération, absente si moins de deux tokens ;
- `vitesse_lecture_estimee_tps` = tokens_entree / délai avant le premier token, **étiquetée estimation** (elle inclut le premier token) ;
- `temps_cpu_s`, pic mémoire cumulatif, `fin` (`arret` ou `limite`), conformité.

Les compteurs natifs de llama.cpp (temps et nombres de tokens de lecture et de génération) ne sont consignés, à part et sous leur nom, qu'après vérification par l'essai minimal qu'ils sont lisibles et cohérents ; sinon ils sont absents. Par exécution : chargement, durée du processus moteur, durée totale, contexte système (méthode existante, facultative). CPU moteur affiché = 100 × temps CPU / (durée d'extraction × processeurs logiques). Aucune mesure inventée : absente si illisible.

### D7. Stockage

`data/extractions/<AAAAMMJJ-HHMMSS>-<8hex>/` : `run.json` (`schema: 1`, `type: "extraction"`, état, métadonnées complètes, mesures), `run.log`, `grille.md` (copie exacte), `schema.json`, `consignes.json` (message système, `version_consignes`, `version_format`), puis par source `<n>-<libellé>/` : `source.txt` (copie de la transcription, écrite dès l'admission), `sortie_brute.txt` (si au moins un token a été généré), `extraction.json` (uniquement si conforme), `result.json` (état, motif, mesures, provenance). `result.json` est écrit **en dernier** et sert de marqueur de publication : une source sans `result.json` est non traitée, même si d'autres fichiers sont présents.

États d'une source : `conforme`, `non_conforme` (JSON indécodable, clé dupliquée, schéma non respecté ou limite `sortie_max` atteinte), `erreur` (contexte insuffisant, erreur du moteur), `non_traitee`. États d'une exécution : ceux des transcriptions (en cours, terminée, interrompue, abandonnée, en échec). Code de sortie de `extract start` : 0 si toutes les sources sont conformes, 1 si au moins une est non conforme ou en erreur, ou si l'exécution est en échec (grammaire, chargement), 3 après signal ; le résumé détaille chaque source.

Mêmes règles que pour les transcriptions : écriture atomique, état `en cours` puis immuable, aucun écrasement. La récupération au démarrage (serveur ou commande, sous le verrou, avant toute consultation) est étendue à ce dossier ; c'est la seule écriture admise hors exécution. `run.log` ne contient ni texte source ni sortie du modèle, seulement états, motifs et mesures ; le `job.json` de travail (qui contient les textes) reste sous `data/cache/` et est supprimé par le nettoyage existant, y compris après récupération. La copie de la source rend chaque extraction relisible seule ; la provenance (identifiant et ordre de l'exécution de transcription, audio et son empreinte, modèle et moteur de transcription, marque factice) permet de remonter à l'audio.

### D8. Sources

Une source est une transcription `identifiant:ordre` d'une exécution de transcription dont l'audio est terminé avec un texte non vide. Les transcriptions factices sont acceptées et l'extraction est alors marquée « source factice ». L'empreinte de la source est le SHA-256 du texte en UTF-8 ; c'est elle, et non l'audio, qui définit la comparabilité.

### D9. Consultation

- Regroupement : par triplet (empreinte du texte source, empreinte de la grille, empreinte du schéma généré). Deux extractions d'une même source avec des grilles différentes, ou d'une même grille convertie par deux versions incompatibles du programme, ne sont pas comparables.
- Commandes : `grids list`, `grids show NOM` (cases interprétées, schéma, message système, sans écriture) ; `extract options`, `extract check`, `extract start` (`--model`, `--grid`, `--source ID:ORDRE` répétable et ordonné, `--threads`, `--setting`) ; `extract list [--sort temps|ram|cpu|recent]`, `extract show ID`, `extract compare CLE SEL SEL…` (2 à 6 sélections `identifiant:ordre`, soit les six candidats sur une même source ; borne confirmée par le contrôle visuel), `extract explain` (aide des indicateurs, source unique partagée avec la page `/extractions/aide`) ; `results history` liste aussi les extractions avec leur type.
- Pages web (GET, sans script) : `/extractions` (groupes ; par entrée : modèle, durée d'extraction, délai premier token, vitesse de génération, RAM, CPU, conformité), `/extractions/<id>` (indicateurs, grille remplie case par case avec « non mentionné », autres informations, puis transcription source visible à côté sur grand écran et à la suite sur petit écran), `/extractions/comparaison` (sélection GET) et `/extractions/comparaison/<cle>` (une ligne par case, une colonne par modèle ; cartes empilées sur petit écran ; transcription source accessible une fois). Navigation : Résultats, Comparaisons, Extractions, Historique.
- Sortie non conforme : la sortie brute est affichée à la place de la grille, avec l'état et le motif.

### D10. Vérification

Serveur de développement : tests unitaires (grilles, schéma, validateur, consignes, runner avec moteur factice, stockage, récupération, commandes, pages), sans réseau ; ils ne qualifient pas la bibliothèque réelle.

PC de test Linux, sur accord explicite, en deux temps :

1. **Essai minimal** (tâche 0), avant l'adaptateur réel : roue CPU 0.3.36, un candidat du palier 8 Go, deux sources synthétiques au préfixe identique ; vérifier chargement de l'architecture par l'API de bas niveau sans compilation de gabarit Jinja, conversion et chargement natif de la grammaire de la grille d'exemple (listes composées, `null`, liste vide interdite, clés inconnues), refus d'une grammaire invalide, arrêt sur les tokens de fin, format local contre gabarit embarqué lu comme texte, génération token par token, comptage et limite, réinitialisation et relecture intégrale, compteurs natifs, hors ligne, pic mémoire, arrêt. Le runner séparé et le moteur factice peuvent avancer en parallèle.
2. **Qualification** : six modèles, trois transcriptions des audios Gemini existants, threads 8 ; commit de révision complet, verdict par modèle (chargé, conforme, mesures) et budget RAM mesuré par palier ; liste blanche définitive. Windows : aucune vérification prévue sans nouvel accord pour étendre la CI ; la limite est consignée.

## Risks / Trade-offs

- **Architectures non prises en charge par la 0.3.36** (Qwen3.5, Gemma 4, Granite 4.2) → refus explicite à la vérification ; repli possible sur une version plus récente compilée ou sur le binaire `llama-server`, sur nouvelle décision.
- **Format de conversation local** : un format local erroné dégrade la sortie sans erreur visible ; la comparaison au gabarit embarqué (lu comme texte) pendant la qualification et la consignation de `version_format` et du SHA-256 du gabarit embarqué limitent ce risque. Chaque nouvelle architecture demande un format local.
- **Mode raisonnement** de certains modèles : la contrainte impose le JSON dès le premier token, ce qui empêche un raisonnement préalable visible ; l'effet sur la qualité est accepté et à observer.
- **Grammaire et performances** : certaines constructions de schéma ralentissent la génération ; le sous-ensemble D2 reste simple.
- **Coût du prompt sur CPU** : la lecture d'une transcription de 10 min peut prendre plusieurs minutes sur une machine modeste ; mesure attendue, pas un défaut.
- **RAM et mmap** : le pic résident inclut les pages du fichier projeté ; le mode de chargement est consigné pour l'interprétation.
- **Lecture médicale** : une grille bien remplie n'est pas médicalement correcte ; la documentation et l'aide le rappellent sans bandeau clinique.
- **Volume** : environ 31 Go de poids pour la qualification complète.

## Open Questions

- Liste blanche définitive des architectures GGUF : fixée après la qualification Linux.
- Réglage `contexte` par défaut (16384) suffisant pour une consultation de 30 min : à confirmer par la mesure des tokens sur les transcriptions existantes.
