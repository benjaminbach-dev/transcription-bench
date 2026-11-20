---
title: Adaptateur réel llama.cpp (tâche 3.3) — contrat étendu et formats locaux, 2026-11-20
type: decision
permalink: transcription-bench/projet/adaptateur-reel-llama-cpp-3-3-2026-11-20
status: active
updated: '2026-11-20'
tags:
- decision
- llama-cpp
- extraction
---

Lot 3.3 du change ajouter-bench-extraction, exécuté le 2026-11-20 sur le PC de test Linux déclaré, après le verdict de l'essai minimal 0.1. Workers (GLM 5.3 high) relus et corrigés par le principal ; suite complète 1565 tests OK à la livraison ; revue advisor par lot avant commit/push.

## Décisions
- [decision] Adaptateur `engines/adaptateurs/llama_cpp.py` : import de llama_cpp différé dans `charger` (le module s'importe sans paquet moteur), liaisons C bas niveau seules (jamais la classe `Llama` ni `response_format`), sonde de contrainte obligatoire au chargement (aucun masque ou vocabulaire entièrement masqué → refus), grammaire+glouton, réinitialisation KV+échantillonneur avant chaque source, refus de contexte insuffisant avant tout décodage, comptes natifs (lecture/génération) rendus seulement pour une source terminée et omis après un échec partiel, aucun temps natif. Revue advisor : le rappel de journal natif est conservé au niveau module (pointeur C vivant) et NEUTRALISÉ (rien n'est recopié vers run.log, seuls les diagnostics du programme y entrent) ; `ErreurSource`/`ErreurContexteInsuffisant` déplacées dans engines/protocole.py — le runner lancé en script exécute `__main__` et l'import historique créait une seconde classe jamais attrapée (test bout en bout runpy avec motif exact). #decision
- [decision] Contrat du runner étendu AVEC le protocole et le consignateur (le verrou « 7 clés » était levé à ce moment-là, pas avant) : `meta_moteur` facultatif sur l'événement `chargement` (threads_appliques, mode_chargement_poids, architecture, sha256_gabarit_embarque, version_format, decodage, graine) validé deux fois (runner avant émission, serveur à réception, même fonction `valider_meta_moteur`) ; `comptes_natifs` facultatif sur l'événement `extraction` (champs `CHAMPS_FACULTATIFS`, cohérence fin ∈ {arret, limite}) ; `consignes.json` réécrit atomiquement avec `version_format` au chargement conforme (fichier d'admission inchangé sinon). #decision
- [decision] Formats de conversation locaux (design D3) : mistral3 vérifié à l'essai (sha gabarit d28d7df9…) ; qwen35 (ChatML trimé, sans BOS), granite (ChatML non trimé, sans BOS) et gemma4 (tours <|turn>, BOS) rédigés le 2026-11-20 depuis les gabarits publics lus comme texte (tokenizer_config/métadonnées des dépôts, sans poids) — les trois restent À VÉRIFIER en qualification 6.3 contre le gabarit embarqué de chaque modèle réel. #decision
- [decision] `collecter_stderr` (partagé transcription/extraction) borne chaque ligne à 400 caractères suffixe compris (« … (ligne tronquée, N caractères) ») : les journaux natifs sont courts, un moteur qui recopierait du texte ne remplit plus run.log. Limite résiduelle acceptée : une ligne géante sans saut de ligne reste en mémoire transitoire avant troncature. #decision

## Limites
- [limit] Adaptateur testé sans import de la bibliothèque (module simulé) ; exécution réelle reportée à la qualification 6.1-6.3 ; formats qwen35/granite/gemma4 non vérifiés contre gabarits réels ; threads_appliques consigne la valeur posée (aucune lecture native n'existe en 0.3.36). #limite

## Relations
- relates_to [[Essai minimal llama.cpp (tâche 0.1) sur PC de test — verrou résolu et verdicts bas niveau, 2026-11-20]]
- relates_to [[Décision — bench d'extraction LLM et web en consultation seule (2026-11-19)]]