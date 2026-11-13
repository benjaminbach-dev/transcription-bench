---
title: Qualification Linux CLI et charge système, 2026-11-13
type: note
permalink: transcription-bench/bench/qualification-cli-charge-linux-2026-11-13
tags:
- validation
- linux
- cli
- charge-systeme
---

# Qualification Linux CLI et charge système, 2026-11-13

Lot accepté dans la session : PC de test Linux déclaré (T14s, Manjaro), réutilisation des moteurs et modèles déjà présents, sans installation ni téléchargement. Un seul modèle lancé : transcribe.cpp, Whisper large-v3-turbo GGUF Q5_K_M, référence `transcribe-cpp/80ff6767e5e464371fff69ccdd5ba6d23961109be14e23dd0c71a849e68c1bca`. Audios synthétiques déjà dans `data/audio`. Commit `3b11338`. Le worker a exécuté les commandes ; le principal a relu les fichiers de résultats et le journal, pas seulement le rapport.

## Observations
- [validation] Machine : Linux 6.18.55-1-MANJARO x86_64, hostname T14s, Ryzen 7 PRO 6850U, 16 cœurs logiques / 8 physiques, MemTotal 31577408 kB. Python du .venv 3.12.13, uv 0.11.8, psutil 7.2.2. Moteur transcribe-cpp déjà prêt depuis 2026-11-02, transcribe_cpp 0.4.1, numpy 2.5.4. #linux
- [validation] `run check` puis `run start` sur validation-http-20261102-134503.wav (environ 10 s), threads demandés 8, aucun --setting. Code 0. Résultat 20261113-100519-e7724f76, état completed, factice et mesures_simulees faux, schema 1. #cli
- [measurement] Observation de chargement réelle : RAM disponible 21166145536 octets sur 32335265792, pas de clé cpu, méthode psutil-cpu-percent-nonbloquant-v1, psutil 7.2.2, relevé 2026-11-13T09:05:19Z. Observation audio : CPU système 53,1 % sur 5,796 s, RAM disponible ensuite 21129756672 octets. Pic mémoire moteur 792674304 octets, temps CPU moteur 44,74 s : distincts des champs système. Aucune date 1970. #charge
- [validation] Arrêt : `run start` sur consultation_05m_gemini.wav (environ 5 min 41 s). Après « Modèle chargé », un SIGTERM a d'abord visé un sous-shell ; un seul SIGTERM a ensuite visé le CLI réel (PID 23116). Journal : « arrêt demandé par signal ». Résultat 20261113-100611-ae40c300, état interrupted, audio non traité, pas de result.json, observation de chargement seule, pic mémoire partiel. Le processus moteur consigne code_sortie -15. Verrou libéré ensuite (`engines list` code 0). #signal
- [limit] Le code de sortie 3 du processus CLI n'a pas été capturé : le `wait` portait sur le sous-shell, pas sur le CLI. L'arrêt est prouvé par le journal et par le -15 du moteur, pas par le code de la commande. #signal
- [limit] Installation, téléchargement, autres modèles et Windows ne font pas partie de ce lot. Une exécution transcribe.cpp ne qualifie ni faster-whisper, ni transformers, ni un PC Windows. Les durées ne sont pas une preuve de performance. `threads_appliques` reste null : 8 threads demandés, non relus. `processeur` dans machine reste null, comme sur un résultat antérieur. #limite

## Relations
- relates_to [[Validation Linux de transcribe.cpp avec Whisper GGUF Q5_K_M]]
- relates_to [[Socle des commandes CLI et modes exclusifs]]
- qualifies [[Décisions du prototype de benchmark]]


## Complément de qualification — 2026-11-13 (même journée)

- [validation] **Arrêt prouvé de bout en bout** : SIGTERM unique au processus CLI réel (pilote Python possédant le processus) pendant l'inférence de l'audio de 5 min 41 s → **code de sortie 3 capturé** ; exécution 20261113-110831-4461ca96 interrompue, audio non traité, aucun result.json donc aucun relevé fabriqué, observation de chargement seule, moteur code_sortie -15, verrou libéré. Un essai antérieur (20261113-100611-ae40c300) prouvait déjà le comportement sans capturer le code. #signal
- [validation] **Cohérence de périmètre des mesures** : intervalle_s 5,796191996 s ≈ duree_transcription_s 5,796172091 s (écart ~20 µs) ; chargement sans cpu, audio avec cpu + méthode + psutil + intervalle + RAM ; distinct du pic moteur (792 674 304 o) et du temps CPU moteur (44,74 s). #charge
- [validation] **Commandes d'installation et de téléchargement** qualifiées sur copie vierge sous /tmp (clone local + venv propre, aucune écriture dans le dépôt) : data check 0 ; engines install transcribe-cpp 0 (env 123 Mo — roue native déjà en cache uv, le téléchargement réseau ~22 Mio n'a pas été réexercé) ; models check 2 sans --file (5 variantes GGUF listées) puis 0 avec whisper-large-v3-turbo-Q5_K_M.gguf (révision résolue 18ada752… identique au jalon 0) ; models download 0 (590,9 Mio, ~12 s) ; run check/start 0 (résultat 20261113-110808-0d94ee12 complété avec observations) ; models delete 0, résultats lisibles ensuite. #cli
- [validation] **Observation navigator du bloc « Contexte de l'ordinateur »** (serveur 8767, vrai dossier) : ouverture/fermeture clavier, valeurs réelles et second niveau brut, détail interrompu sans valeur fabriquée (« non traité », seule la section chargement), comparaison avec une entrée par transcription, chiffres clés au premier plan, aucune colonne système dans les listes, distinction moteur/système, aucun débordement en 1280/360 clair/sombre, console propre sauf favicon 404, réseau local seul. Nuance : la mention « Matériel différent sur RAM totale. » (19 lignes sur 21) est une annotation préexistante du change archivé refondre-parcours-resultats (commit 3b1145c), légitime ici (4 RAM totales différentes consignées dans data/results) et hors périmètre de la tâche. Le libellé « non mesuré » reste correct pour les mesures absentes (vérifié sur un résultat à audio en erreur). #interface
- [validation] openspec validate mesurer-charge-systeme --strict OK ; git diff --check OK. #validation
- [limit] Windows reste non vérifié (mesurer-charge 4.4 et cli 4.5) : aucun job moteur CI lancé faute d'autorisation explicite. Écritures clients Hugging Face dans ~/.cache/huggingface (journaux, sans poids) non supprimées. #limite


## CI Windows — 2026-11-13 (autorisation explicite du propriétaire)

- [validation] Gate de publication levé depuis 2026-11-02 (note projet dédiée) ; dépôt public, gh authentifié. Run **43411758748** du workflow Moteurs Windows (manuel), commit 3b11338, imports des trois moteurs + les quatre combinaisons autorisées (un modèle par job, téléchargements explicites, puis options hors ligne). **Vert dans son entier en 2 min 21 s**. #ci
- [validation] Runner réel vérifié sur windows-2022 : les quatre inférences passent par ExecutionMoteur/runner réel (psutil 7.2.2 présent), cpu_relu confirmé, transcription non vide, aucun signalement d'observation dans les journaux. Consigné : images win22 20261101.353.1 et 20261112.366.7 selon les jobs, Python 3.12.10, uv 0.11.8, faster_whisper 1.2.1, transcribe_cpp 0.4.1, transformers 5.20.2, numpy 2.5.4 ; révisions figées inchangées. #ci
- [limit] Les 15 rapports JSON nettoyés ne portent aucun champ d'observation système (décision 4.2 : liste blanche fermée) : la CI vérifie le fonctionnement du runner, pas le contenu des champs système sur Windows. Signaux non vérifiables en CI ; sous-commandes CLI non exercées par le harnais (il appelle les services). Ces essais ne qualifient ni le PC utilisateur ni une performance. #limite
- [decision] mesurer-charge-systeme 4.4 coché (tâche complète 12/12) ; archivage différé « seulement sur demande » selon le suivi du change. ajouter-cli-agent 4.5 reste ouvert : le propriétaire a décidé le 2026-11-13 de ne pas étendre le workflow CI pour exercer les commandes sur le runner Windows. Preuves disponibles (services et runner réels sur le runner CI, suite de tests de la CLI sous Windows) et limites consignées (sous-commandes CLI réelles sur Windows et signaux non vérifiés, ces derniers invérifiables en CI) ; c'est au propriétaire de trancher et de cocher. #decision
