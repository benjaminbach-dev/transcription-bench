---
title: Validation Linux de transcribe.cpp avec Whisper GGUF Q5_K_M
type: note
permalink: transcription-bench/bench/validation-linux-de-transcribe.cpp-avec-whisper-gguf-q5-k-m
tags:
- validation
- linux
- transcribe-cpp
- faisabilite
---

# Validation Linux de transcribe.cpp avec Whisper GGUF Q5_K_M

## Périmètre et provenance
Lot autorisé explicitement le 2026-11-01 : transcribe.cpp 0.4.1 et Whisper large-v3-turbo GGUF Q5_K_M, CPU uniquement, mêmes deux WAV français synthétiques que faster-whisper, contrôle local/hors ligne. Le worker a préparé le verrou candidat et l'environnement ; le principal a contrôlé la source de l'API installée, téléchargé le modèle et réalisé les sondes pendant l'attente d'un contrôle auxiliaire du worker. Il a corrigé le harnais, les libellés de preuve et le design. Commit/push puis revue finale advisor demandés par l'utilisateur ; la revue fait l'objet d'une clôture séparée.

PC explicitement déclaré de test Linux : Manjaro x86_64, noyau 6.18.55-1-MANJARO, glibc 2.44, Ryzen 7 PRO 6850U (8 cœurs/16 threads), environ 30 Gio de RAM. CPython géré 3.12.13, uv 0.11.8. Les sources de décision restent OpenSpec ; ceci est un constat local, pas une qualification Windows ni une validation clinique.

## Installation et modèle
- [validation] Verrou candidat universel Python 3.12 : transcribe-cpp==0.4.1, transcribe-cpp-native==0.4.1, numpy==2.5.4, psutil==7.2.2. Compilation `uv pip compile --universal --python-version 3.12 --no-build`, puis création sans écrasement de `data/engines/transcribe-cpp/` et synchronisation uv sans build source. `uv pip check` réussi, imports isolés et versions confirmés par la sonde du principal.
- [measurement] Roue native signalée par uv : 21,7 Mio téléchargés (~22,8 Mo décimaux), autres dépendances principalement en cache. Pas de comptage réseau exact. Environnement relevé par `du -sh` : 121M (~127 Mo décimaux). Aucun torch, extra CUDA ou outil système installé dans ce lot.
- [limit] La roue native standard contient aussi `libggml-vulkan.so` sur le disque, en plus des variantes CPU. Cela ne signifie pas qu'elle est utilisée : backend CPU explicitement imposé, périphérique CPU relu et journaux ne rapportant que le chargement de `libggml-cpu-haswell.so`. Ne pas prétendre que les binaires Vulkan sont absents de l'installation.
- [validation] Dépôt public `handy-computer/whisper-large-v3-turbo-gguf`, licence MIT déclarée ; commit figé `18ada752005f5fddef499256f9a458d0b37a203a`. Un seul fichier sélectionné : `whisper-large-v3-turbo-Q5_K_M.gguf`, 619628096 octets ; SHA256 local conforme au LFS distant `06fc9923c09fb3ae878ea12c34d1be3ed18fad039ab14b4b045c7b6c40af56b2`. En-tête distant consulté avant téléchargement par HTTP Range limité à 65536 octets : GGUF v3, general.architecture=whisper ; architecture whisper également relue par l'API après chargement.
- [provenance] Modèle sous `data/models/transcribe-cpp/80ff6767e5e464371fff69ccdd5ba6d23961109be14e23dd0c71a849e68c1bca/fichiers/`. Téléchargement explicite par le principal en 18,955 s selon `telecharger-modele.py` et son manifeste, token=False, cache HF dédié sous data. Commande exécutée : `.venv/bin/python -B data/feasibility/transcribe-cpp/telecharger-modele.py`, donc interpréteur serveur (pas celui du moteur). Versions Python 3.12.13 et huggingface_hub 2.3.0 relues après téléchargement dans ce même environnement serveur préexistant, sans resynchronisation de celui-ci ; le manifeste initial ne les enregistrait pas automatiquement. Aucun inventaire applicatif model.json ni marqueur installation.json publié.

## Configuration et correction d'API
- [validation] `TRANSCRIBE_BACKENDS=cpu`, `TRANSCRIBE_BACKEND=cpu`, `backend="cpu"`, `no_mmap=False`, session `n_threads=8`. Le harnais fixe également `OMP_NUM_THREADS=8`, `TRANSCRIBE_NO_MMAP=0`, `CUDA_VISIBLE_DEVICES=""`, `HF_HUB_DISABLE_IMPLICIT_TOKEN=1` et un HF_HOME dédié. OMP_NUM_THREADS configure la limite OpenMP ; il ne constitue pas une relecture des threads effectivement appliqués par la session. Le moteur rapporte le backend brut **"CPU"**, le périphérique kind=cpu/device_type=cpu et la variante whisper-large-v3-turbo. Les threads appliqués n'ont pas de getter public identifié : seulement 8 demandés, jamais affirmés appliqués.
- [correction] La première garde du harnais attendait la chaîne exacte "cpu" et a arrêté la sonde après le chargement/mapping et avant toute inférence. Diagnostic : c'était une différence de casse, pas une exécution GPU. Le principal a corrigé la garde en `model.backend.casefold() == "cpu"`, sans retirer la vérification du périphérique CPU. Le design D6 est réconcilié sur cette comparaison, la valeur brute reste conservée. Le premier échec est résumé manuellement dans `echec-garde-initial.log`, pas conservé sous forme d'un journal brut intégral. `diagnostic-device.json` a été réécrit lors des passages suivants ; les valeurs CPU relues corroborent la différence de casse, mais ce fichier n'est pas une capture immuable du premier échec.
- [correction] Le paramètre device de Model accepte un BackendDevice, y compris CPU ; il n'est pas réservé aux GPU. La preuve d'installation du worker a été corrigée sur ce point, sur sa date initialement erronée et sur le tag de roue native (py3-none-manylinux, utilisée avec CPython 3.12).
- [validation] mmap réellement observé via les mappings du processus vers le fichier GGUF, et signalé par la bibliothèque. Les temps de chargement ci-dessous mesurent l'ouverture/mapping : ils ne prouvent pas une lecture complète des poids ni un chargement disque à froid. Le RSS comprend des pages du modèle mappé.

## Deux WAV français, chargement unique et exécution séquentielle
Les signaux sont les fichiers float32 mono 16 kHz issus du décodeur commun PyAV du serveur lors du lot précédent. SHA256 source et f32 sont réutilisés et contrôlés par le harnais ; aucune nouvelle donnée audio externe.

Réglages : langue fr imposée, timestamps segment, `WhisperRunOptions(condition_on_prev_tokens=False, temperature=0.0, temperature_inc=0.0)`, décodage glouton natif, aucun découpage manuel. Aucune option beam_size n'est exposée par cette API. La langue renvoyée est une chaîne vide sur ces deux résultats ; ne pas la présenter comme détection ni remplacer la valeur brute par fr.

| Relevé local | Court | Long |
|---|---:|---:|
| Durée décodée | 10,6733125 s | 47,7036875 s |
| Temps de transcription | 9,359 s | 17,859 s |
| Temps CPU transcription | 74,318 s | 141,167 s |
| RTF observé | 0,8769 | 0,3744 |
| Pic RSS cumulatif du processus | 802533376 octets | 814194688 octets |

- [measurement] Chargement chronométré 0,0825 s ; pic final 814194688 octets (~776,5 Mio, ~0,758 Gio). Durée du processus chargé puis traitant les deux audios : 29,056 s, incluant les vérifications SHA-256 du GGUF de 619 Mo et des fichiers f32, les imports et la sérialisation des preuves ; ce n'est pas l'inférence seule. Les quatre timings natifs load_ms/mel_ms/encode_ms/decode_ms sont conservés bruts dans la preuve ; ils ne remplacent pas les mesures murales du principal et leur portée interne ne doit pas être extrapolée.
- [validation] Court : quatre segments, dernière fin 10,18 s. Long : six segments, un segment traverse 30 s et trois commencent après 30 s ; dernière fin 47,10 s, repère final « fin du texte et arrêt final » présent. Toutes les bornes observées restent dans la durée audio. Le mécanisme natif fonctionne sur CE fichier de 47,7 s ; pas de généralisation à tout audio long.
- [observation] Exemples non exhaustifs d'erreurs lexicales relus par le principal : « contrôle » devient « coup trône », « court enregistrement » devient « coup enregistrement » ; long « long » devient « lourd », « marquer » devient « manquer », « banc » devient « vent », « compare » devient « coupant », « clarté » devient « plantée », « comparaison entre moteurs » devient « coupe à résoudre entre moteurs ». Les nombres rendus en chiffres sont une normalisation, pas automatiquement une erreur. Aucun WER ni nouveau score automatique calculé.

## Rechargement et limites hors ligne
- [validation] Second processus frais, cache HF distinct initialement absent, même fichier local : chargement réussi en 0,0455 s, processus complet 1,018 s, CPU brut "CPU" et mmap observés. HF_HUB_OFFLINE=1 et hook d'audit Python actif avant les imports pour les deux processus ; zéro tentative réseau Python interceptée. Les paramètres local_files_only et trust_remote_code n'existent pas dans cette API : seul le fichier GGUF local est fourni.
- [limit] Ce n'est pas une coupure réseau OS ; le hook Python ne couvre pas les appels natifs C++. La tâche 1.6 n'est donc pas complètement validée. Ni Windows, ni une autre architecture GGUF, ni un vrai adaptateur produit n'ont été qualifiés. Verrou candidat et sondes restent hors Git ; les cases globales du jalon 0 et 8.2 restent ouvertes.
- [limit] Une seule mesure par audio, voix robotique synthétique, modèles/précisions/réglages différents de faster-whisper (glouton contre beam_size=5). Les durées et RSS ne permettent pas un classement équitable des moteurs ; aucune conclusion sur parole naturelle ou médicale.

## Preuves et procédure
- [provenance] Preuves locales non versionnées sous `data/feasibility/transcribe-cpp/` : candidat .in/.txt, `preuve-installation-candidat.json`, `manifeste-modele.json`, `diagnostic-device.json`, `preuves-transcription-fr.json`, `preuves-rechargement.json`, `preuves-lancement.json`, scripts et journaux. Les mesures du présent rapport ont été lues par le principal dans ces fichiers.
- [process] Un curl de lecture de métadonnées PyPI a été refusé au worker : arrêt et remontée, pas de lecture de remplacement. Ce contrôle redondant a été retiré de sa mission, les tailles/versions étant déjà connues du principal avant le refus ; une tâche distincte de compilation/installation uv autorisée a ensuite été confiée. Aucun nouveau refus rapporté par le worker. Le téléchargement HF et les inférences du principal étaient des opérations distinctes explicitement autorisées, pas une répétition du curl refusé.
- [validation] Retrait espeak-ng annoncé par l'utilisateur puis vérifié par le principal : espeak-ng, pcaudiolib et libsonic absents. Les WAV persistants restent disponibles ; aucun sudo ni nettoyage de cache système tenté dans ce lot.

## Relations
- relates_to [[Décisions du prototype de benchmark]]
- relates_to [[Moteurs et faisabilité technique]]


## Revue advisor après publication du lot
- [review] Revue du commit d960a7c : favorable avec réserves, aucune erreur bloquante. Les corrections documentaires recommandées sont intégrées ici : erreurs lexicales non exhaustives complétées, module Vulkan présent mais non utilisé dans les essais, interpréteur/version du téléchargement précisés, configuration et portée des temps clarifiées. Aucun nouvel essai ni inférence exécuté pour ces corrections.
- [process] L'advisor a signalé une lecture initiale du contenu mémoire via git diff au lieu du seul MCP et des refus de commandes de lecture ultérieurs, non contournés. Sa lecture de référence de la note a ensuite utilisé le MCP ; aucun fichier ni état n'a été modifié par lui. Les limites de sa revue incluent l'absence de rejeu des inférences, de recalcul de SHA complet et de vérification de taille du venv.
