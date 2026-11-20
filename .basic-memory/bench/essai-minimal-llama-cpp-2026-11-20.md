---
title: Essai minimal llama.cpp (tâche 0.1) sur PC de test — verrou résolu et verdicts
  bas niveau, 2026-11-20
type: validation
permalink: transcription-bench/bench/essai-minimal-llama-cpp-2026-11-20
status: active
updated: '2026-11-20'
tags:
- validation
- llama-cpp
- extraction
---

Session du 2026-11-20 sur le PC de test Linux déclaré (T14s, Manjaro, Ryzen 7 PRO 6850U, 16 cœurs logiques, 30 GiB RAM, uv 0.11.8, CPython 3.12.13). Accord du propriétaire : reprise des tâches devant être exécutées ici (0.1 puis 3.3 puis 6.x), exécutées par workers (GLM 5.3 high) relus et corrigés par le principal, revue advisor par lot (sol 6.2 medium) puis commit/push. Tâche 0.1 du change ajouter-bench-extraction ; preuves locales sous data/feasibility/llama-cpp/ (non versionnées).

## Verrou (tâche 2.2 close par la même occasion)
- [validation] Verrou requirements/llama-cpp.txt réellement résolu sur ce PC : uv pip compile --universal --python-version 3.12 --no-build --emit-index-url --emit-find-links (index abetlen). Pins identiques à la rédaction manuelle du 2026-11-19 (llama-cpp-python 0.3.36, diskcache 5.6.3, jinja2 3.1.6, markupsafe 3.0.4, numpy 2.5.5, psutil 7.2.2, typing-extensions 4.16.0) ; seule la rédaction de l'en-tête change. #verrou
- [validation] Installation vérifiée sans compilation dans un env d'essai sous data/feasibility/llama-cpp/env : uv pip sync --no-build (roue CPU 25,8 Mio via les directives auto-portées du verrou), 2,1 s, env 130 Mio, cache uv cantonné sous data/. Import llama_cpp 0.3.36 OK, liaisons C init/free OK, psutil présent. Drapeau verrou_valide=True repassé dans engines/declarations.py avant 6.1, tests mis à jour (garde-fou toujours testé à drapeau baissé forcé). #validation

## Essai bas niveau (Ministral-3-3B-Instruct-2512-Q8_0, 3,65 Go, révision eb599d40, sha256 conforme à l'oid LFS)
- [measurement] Run complet hors ligne (unshare -rn), threads 8, contexte 16384 : chargement 0,7 s, architecture mistral3 (liste blanche provisoire), mmap par défaut ; deux sources synthétiques au préfixe commun de 1341 tokens : S1 1505 entrée / 686 sortie conforme, S2 1498 / 579 conforme ; vitesse de génération ~6,5 tok/s, lecture estimée ~46 tok/s ; pic mémoire 5,3 GiB (poids mmap 3,5 GiB + KV) ; limite sortie_max=24 atteinte → fin=limite ; arrêt propre par SIGTERM en pleine génération ; gabarit embarqué lu comme texte (sha256 d28d7df9) et rendu local mistral3 conforme structurellement. #mesure
- [decision] Repli silencieux natif découvert : llama_sampler_init_grammar 0.3.36 renvoie un échantillonneur NON NUL et SANS AUCUNE contrainte pour une grammaire mal formée (l'erreur de parse native est captée par le rappel de journalisation, sans arrêt). Le refus sans repli est donc assuré par une SONDE DE CONTRAINTE : appliquer l'échantillonneur fraîchement créé à tout le vocabulaire et exiger des masques (grammaire de la grille : 131070/131072 masqués à l'état initial, non masqués = « { » et « {" » ; 0/131072 pour la grammaire invalide — contre-vérifié indépendamment par le principal). Sondes d'état complémentaires exigées par la revue advisor : clé inconnue masquée à la position d'ouverture (le GBNF généré énumère les clés du schéma en ordre fixe), liste vide interdite (« ] » masqué après « [ », minItems 1). À implémenter dans l'adaptateur réel 3.3 ; design D4 amendé en conséquence. #decision
- [decision] Compteurs natifs : comptes de tokens lisibles en cumul mais engagés seulement à l'accès aux sorties (cohérents à ±1 pour les sources terminées) ; TEMPS natifs toujours 0.0 dans cette roue, jamais consignés — toutes les durées viennent du chronomètre du programme. Design D6 amendé. #decision
- [fact] jinja2 est importé au niveau module par le seul import llama_cpp (0.3.36, via llama.py → llama_chat_format.py) : inévitable avec le paquet. La COMPILATION de gabarits, elle, n'a jamais lieu par l'API bas niveau : compteur instrumenté (Template.__init__, Environment.compile) à 0 sur tout l'essai. #fait

## Limites
- [limit] Un seul modèle (palier 8 Go), un seul réglage (threads 8), PC de test déclaré uniquement, non extrapolable ; installation Windows x64 non vérifiée (résolution universelle seulement) ; la qualité médicale des grilles extraites n'est pas jugée par cet essai ; la qualification (six modèles, trois transcriptions Gemini, tâches 6.1-6.3) reste à faire. #limite

## Relations
- relates_to [[Décision — bench d'extraction LLM et web en consultation seule (2026-11-19)]]
- relates_to [[Reprise lab — implémenter web en consultation puis bench d'extraction (2026-11-19)]]
- uses [[Comparatif des cinq paires moteur-modèle sur audios Gemini, 2026-11-19]]