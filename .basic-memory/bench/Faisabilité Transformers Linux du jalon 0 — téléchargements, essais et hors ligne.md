---
title: Faisabilité Transformers Linux du jalon 0 — téléchargements, essais et hors
  ligne
type: note
permalink: transcription-bench/bench/faisabilite-transformers-linux-du-jalon-0-telechargements-essais-et-hors-ligne
tags:
- validation
- linux
- transformers
- parakeet
- whisper
- hors-ligne
- jalon0
---

# Faisabilité Transformers Linux du jalon 0 — téléchargements, essais CPU et hors ligne

## Contexte et périmètre
Lot exécuté le 2026-11-01 sur le PC de test Linux déclaré (Manjaro, Ryzen 7 PRO 6850U, 8 cœurs/16 threads, CPython 3.12.13, uv 0.11.8), sur instruction utilisateur explicite : reprise après la note [[Reprise du jalon 0 après préparation Transformers CPU]], lot annoncé puis confirmé (téléchargements ~3,9 Gio, essais CPU, vérification hors ligne, revue advisor, commit/push). Workers à tâches bornées une par une avec contrôle principal entre chacune ; advisor consulté sur le blocage librosa puis en revue finale du lot ; corrections appliquées par le principal. Aucune spec modifiée pendant le lot ; les écarts constatés sont reportés vers la tâche 1.8.

## Transport de l'index PyTorch CPU — point ouvert résolu
- [validation] `--extra-index-url https://download.pytorch.org/whl/cpu` ÉCHOUE : stratégie d'index first-index, l'index CPU sert des dépendances (filelock…) à d'anciennes versions, résolution insatisfaisable. Variante extra-index de la préparation précédente confirmée non retenue.
- [validation] Solution validée en dry-run : ligne `--find-links https://download.pytorch.org/whl/cpu/torch/` auto-portée dans le verrou (émise par uv via `--emit-find-links` à la compilation) ; pins à 0 dérive, roue Linux `torch-2.14.1+cpu-…manylinux_2_28_x86_64` et Windows `win_amd64` résolues. `uv pip sync` honore les options d'index écrites dans le fichier : le service d'installation (4.4) fonctionne sans flag torch. Le « Would make no changes » sans flag a été observé sur le verrou 37 pins complété à la main ; pour le verrou librosa, les preuves sont deux dry-runs sans flag (venv vide Linux, Windows simulé) et le sync réel.
- [limit] La ligne `--find-links` pointe vers une page distante qui peut changer ; le verrou n'a pas de hashes (`--generate-hashes` existe, à mettre en balance avec la simplicité). `uv pip sync` du service (moteurs.py 4.4) ne passe pas `--no-build` alors que tous les syncs réels du jalon l'utilisaient : risque de sdist exécutée un jour — écart à traiter en 1.8.

## Verrou de référence et dépendance librosa
- [decision] Verrou de référence candidat : `data/feasibility/transformers/transformers-librosa.txt` (59 pins, sha256 1efdc80d…), compilé avec `--universal --python-version 3.12 --no-build --emit-index-url --emit-find-links --find-links …/whl/cpu/torch/ --torch-backend cpu` depuis `transformers.in` augmenté de `librosa==1.0.0`. 37 pins d'origine inchangés, 22 ajoutés (librosa, numba, llvmlite, scipy, scikit-learn, soundfile, soxr, pooch, msgpack, cffi…), 0 occurrence nvidia/cuda/triton. Écart assumé : trois compilations au total au lieu d'une (original, K, librosa) — la tâche 1.2 disait « compiler une fois ». Le choix de verrous par OS reste suspendu à la tâche 1.3 (Windows).
- [decision] Décision du blocage Parakeet (ImportError `ParakeetFeatureExtractor requires the librosa library`, `@requires(("torch","librosa"))` + appel direct `librosa.filters.mel` — aucune option du processor n'évite librosa, le checkpoint ne fournit pas de filterbank) : avis advisor option A appliqué avec consentement utilisateur — pin direct `librosa==1.0.0` (l'extra `transformers[audio]` est écarté : torchaudio, pyctcdecode, phonemizer, kenlm superflus ; le monkeypatch du front-end mel est écarté : preuves non conformes au processor réel). Installation réelle : +335,2 Mio (351,5 Mo), environnement moteur 977 Mio → 1,3 Gio ; cache uv cantonné (360 Mio, `~/.cache` intact) ; `NUMBA_CACHE_DIR` fixé sous `data/feasibility/transformers/cache-numba`. Licences (faits documentaires) : soxr LGPL-2.1-or-later ; soundfile embarque libsndfile LGPL ; llvmlite BSD-2 + Apache-2.0 LLVM-exception — enjeu uniquement en cas de redistribution d'un environnement préconstruit.
- [observation] `transformers.audio_utils` importe désormais librosa et soxr même sur le chemin Whisper : coût d'import ~0,082 s, sans effet mesurable sur charge/transcription (re-mesure : chargement 0,881 s vs 0,877 s, court 9,808 s vs 9,979 s, texte identique, pic RSS 5092 vs 5016 Mio — écart de bruit 1–3 % à ne pas surinterpréter). Preuves de référence Whisper = avant librosa.

## Téléchargements explicites
- [validation] `openai/whisper-large-v3-turbo` @ `41f01f3fe87f28c78e2fbf8b568835947dd65ed9` : 11 fichiers de la liste blanche Whisper (safetensors 1,511 Gio + requis + facultatifs présents), 49,4 s, exclusions vérifiées ; sha256 model.safetensors `542566a422ae…` = ETag LFS. Destination `data/models/transformers/c26a953cd77…/fichiers` (clé `cle_stockage`).
- [validation] `nvidia/parakeet-tdt-0.6b-v3` @ `541d1f99c6b0c3cd0b11a95167540bb8edefd82b` : 6 fichiers (safetensors 2,337 Gio, config, processor_config, tokenizer.json, tokenizer_config, generation_config), 67,9 s ; `.nemo`, `.gguf`, README, plots, eval_results vérifiés ABSENTS ; sha256 `3a2026366188…` = ETag LFS. Destination `data/models/transformers/f48d5ad9762c…/fichiers`.
- [limit] Manifestes et journaux sous `data/feasibility/transformers/` ; aucun `model.json` applicatif ni marqueur d'installation. Téléchargements non authentifiés (avertissement quota HF sans incidence d'intégrité).

## Essais CPU Whisper (fp32, 8 threads, un seul passage par audio)
- [measurement] Chargement 0,877 s (poids publiés fp16 convertis en fp32 au chargement, pic RSS 5016 Mio atteint au chargement, ~3,5–3,6 Gio en inférence). Audio court 10,673 s : transcription 9,989 s, RTF 0,936 — RTF GONFLÉ par le padding du processor jusqu'à 30 s (coût d'encodeur fixe), non comparable au RTF long. Audio long 47,704 s : long-form natif 24,547 s (RTF 0,515) ; fenêtres fixes 30 s : 32,97 s et texte DÉGRADÉ (hallucination « L'aise-moi » à la coupure, « deuxième » pour « troisième »).
- [validation] Constat critique : l'appel processor PAR DÉFAUT tronque silencieusement à 30 s (3000 trames mel, aucun avertissement, les 4 dernières phrases de la référence disparaissent). Le long-form natif exige la combinaison `truncation=False, padding='longest', return_attention_mask=True` (combinaison testée ensemble, nécessité de chaque option non isolée). L'adaptateur doit rendre la troncature silencieuse impossible.
- [observation] `WhisperFeatureExtractor` n'applique PAS `do_normalize` par défaut dans transformers 5.20.2 (argument d'appel, absent du preprocessor_config ; aucune preuve d'un changement de comportement entre versions — hypothèse, pas un fait). Texte identique avec/sans sur l'audio court : réglage à fixer explicitement dans l'adaptateur.
- [measurement] Qualité vs références (comparaison manuelle, aucun WER) : court 2 substitutions ; long-form natif 5 substitutions + nombres en chiffres — erreurs cohérentes avec faster-whisper sur les mêmes poids, imputables au signal espeak synthétique.

## Essais CPU Parakeet TDT (fp32, 8 threads, un seul passage)
- [measurement] Chargement 1,121 s — NON comparable au 0,877 s de Whisper : poids fp32 mmapés (RSS 1022 Mio au chargement, chargés à la demande, pic atteint au premier passage). Audio court 10,673 s : transcription 1,222 s, RTF 0,115. Audio long 47,704 s : natif EN UNE PASSE (4771 trames mel, `truncation=False`/`padding='longest'` par défaut du processor), 4,854 s, RTF 0,102, pic RSS 3311 Mio, dernier jeton 47,28 s (99,1 %). Arrêt de génération par épuisement de l'encodeur, pas par `max_length` (valeur générique affichée en avertissement — à borner explicitement dans l'adaptateur).
- [decision] ÉCART MAJEUR vs design D9 : le design impose des fenêtres fixes de 30 s pour Parakeet ; l'essai montre le natif en une passe jusqu'à 47,7 s. Choix à faire en 1.8 : natif avec durée maximale déclarée (croissance mémoire et comportement au-delà de 47,7 s inconnus) ou fenêtres en garde-fou mémoire. Pour Whisper, le natif est confirmé et les fenêtres dégradent le résultat sur cet échantillon.
- [observation] Horodatages Parakeet : `generate` renvoie `(sequences, durations)` ; les bornes par jeton viennent de la somme cumulée des durées ; les « segments » de la sonde sont un regroupement à la ponctuation — CONVENTION DE LECTURE, pas une sortie du modèle : à spécifier dans l'adaptateur.
- [measurement] Qualité vs références : nettement moins fidèle que Whisper sur ces voix synthétiques (« trois nombres : deux, sept et quinze » → « trois noob. C'est case » ; « l'enregistrement loup »), sans omission ni boucle. Parakeet est ~5 à 8 fois plus rapide ici MAIS moins fidèle sur ce signal : les deux constats ne se généralisent pas, aucun classement de modèles.

## Hors ligne et coupure réseau OS
- [validation] Coupure OS réelle par `unshare -rn` (namespace réseau vide : 0 route, `lo` seul, tentatives TCP/UDP/DNS en `OSError 101`/`gaierror`, aucune garde Python) : chargement + transcription de l'AUDIO COURT réussis pour les deux modèles, HF_HOME vierge resté vide. Portée : audio court uniquement ; le long-form Whisper et le long Parakeet n'ont tourné qu'avec les gardes internes ; `unshare` n'existe que sous Linux (Windows exigera une autre méthode).
- [validation] Suffisance des listes de fichiers (audio court, appel des essais de référence) : Whisper liste stricte du design (model.safetensors, config, generation_config, tokenizer.json, tokenizer_config, preprocessor_config) = succès, texte identique, facultatifs inutiles. Parakeet stricte SANS `generation_config.json` = échec à `generate()` (`decoder_start_token_id` null) ; avec = succès. **ÉCART vs design D10/`compatibilite_modeles.py` : `generation_config.json` doit devenir REQUIS pour parakeet-tdt** (sinon un dépôt sans ce fichier serait accepté puis échouerait à l'exécution).
- [limit] Essais hors ligne dans un seul processus : pics RSS cumulatifs, caches chauds, durées de chargement non comparables entre essais (Whisper « complet » 7,02 s dont 6,29 s de processor, cause non établie — probablement premiers imports, hypothèse).

## Écarts à traiter en tâche 1.8 (avant adaptateurs 8.x)
1. D9 Parakeet : fenêtres 30 s vs natif une passe (choix, durée max à déclarer).
2. D9 Whisper : natif confirmé ; interdire la troncature silencieuse à 30 s.
3. D10/code : `generation_config.json` requis pour parakeet-tdt.
4. dtype Whisper (fp16 publié → fp32 CPU) à fixer et inscrire dans les réglages effectifs.
5. `do_normalize` Whisper à fixer explicitement.
6. Horodatages Parakeet : convention de lecture à spécifier.
7. librosa : dépendance obligatoire du moteur Transformers (Parakeet) ; `NUMBA_CACHE_DIR` à définir dans l'environnement moteur.
8. `uv pip sync` du service sans `--no-build` : à ajouter ou consigner.
9. Verrou sans hashes + fragilité de la page `--find-links`.
10. huggingface_hub 2.3.0 (serveur, conforme design) vs 2.4.0 (moteur, transitive) : différence d'environnements à consigner.
11. Recompilation du verrou (3 compilations au lieu d'une).
12. `max_length` Parakeet générique : borner ou documenter le bornage interne.

## État OpenSpec et reprise
- [status] **1.2 cochée (26/39)** : verrous des trois moteurs préparés, transport de l'index torch CPU résolu, versions et écarts consignés ici. Restent ouvertes : 1.3 (Windows), 1.4/1.5 (Windows), 1.6 (coupure OS pour faster-whisper et transcribe-cpp + Windows), 1.7 (sonde web PC), 1.8 (écarts ci-dessus), 6.6, 8.x.
- [next] Ordre proposé : 1.8 (ajustements design/specs des écarts ci-dessus) puis 1.3/1.4/1.5 Windows sur le PC du collègue, coupure OS des deux autres moteurs, avant les adaptateurs 8.x. Windows et le jalon 0 global restent préalables au lot 8.
- [limit] Mesures : un seul poste, fp32, un seul passage, voix synthétiques espeak-ng, pic RSS `ru_maxrss` cumulatif, caches disque chauds — aucune représentativité de performance ou de qualité ; aucune métrique WER ; aucune transcription présentable comme médicalement correcte.

## Méthode et frontières
Workers bornés un par un avec arrêt pour contrôle ; le blocage librosa a été tranché par avis advisor (lecture seule) appliqué après consentement utilisateur d'élargissement ; revue advisor finale du lot favorable avec réserves, corrections appliquées dans cette note (RSS Parakeet 3311 Mio, portée exacte des dry-runs, non-comparabilité des chargements, « n'est pas appliqué » pour do_normalize, qualité Parakeet obligatoire, portée de la coupure OS). Principal seul écrivain Basic Memory via MCP. Aucun curl ni sudo ; cache uv (360 Mio) et artefacts d'essai (venv de test, liaisons symlinks) conservés sous `data/` — nettoyage à décider par l'utilisateur. Preuves principales sous `data/feasibility/transformers/` : `preuves-transport-index.json`, `manifeste-modele-{whisper,parakeet}.json`, `preuves-installation-librosa.json`, `preuves-essai-whisper.json`, `preuves-essai-parakeet.json`, `preuves-essai-whisper-apres-librosa.json`, `preuves-hors-ligne.json` + journaux.

## Relations
- relates_to [[Préparation Linux de Transformers et PyTorch CPU]]
- relates_to [[Décisions du prototype de benchmark]]
- remplace [[Reprise du jalon 0 après préparation Transformers CPU]]