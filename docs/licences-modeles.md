# Licences et provenance des modèles d'essai

Vérification documentaire du 2026-11-02, à partir des cartes et fichiers texte publics ; aucun poids téléchargé pour cet examen. Ce relevé ne constitue pas un avis juridique ou un audit complet des composants binaires.

La licence MIT du **code de transcription-bench** ne s'applique pas aux modèles téléchargés ni aux dépendances. Aucun poids ou bibliothèque tierce n'est redistribué dans le dépôt.

| Modèle et révision CI | Licence déclarée et provenance |
| --- | --- |
| `dropbox-dash/faster-whisper-large-v3-turbo` — `0a363e9161cbc7ed1431c9597a8ceaf0c4f78fcf` | MIT selon la carte ; conversion CTranslate2 tierce d'OpenAI Whisper turbo, sans fichier LICENSE propre constaté dans ce dépôt |
| `handy-computer/whisper-large-v3-turbo-gguf` — `18ada752005f5fddef499256f9a458d0b37a203a` | MIT ; conversion et quantification GGUF, fichiers LICENSE et NOTICE constatés ; variante utilisée : `whisper-large-v3-turbo-Q5_K_M.gguf` |
| `openai/whisper-large-v3-turbo` — `41f01f3fe87f28c78e2fbf8b568835947dd65ed9` | MIT selon la carte ; modèle OpenAI, sans fichier LICENSE propre constaté dans ce dépôt de poids |
| `handy-computer/Qwen3-ASR-0.6B-gguf` — `7e7c69a577fa2725dfedbe34b5e999336e30a19b` | Apache-2.0 (carte, balise Hugging Face, en-tête GGUF, LICENSE et NOTICE lus le 2026-11-03 ; le NOTICE déclare les modifications : conversion GGUF, quantification, pas de réentraînement) ; conversion et quantification GGUF du modèle Qwen/Qwen3-ASR-0.6B (Alibaba Qwen) ; variante utilisée : `Qwen3-ASR-0.6B-Q8_0.gguf`, essai Linux seulement (non utilisé en CI) |
| `nvidia/parakeet-tdt-0.6b-v3` — `541d1f99c6b0c3cd0b11a95167540bb8edefd82b` | CC BY 4.0 selon la carte NVIDIA ; aucune modification des poids par le prototype |

Sources figées :

- [Carte de la conversion CTranslate2](https://huggingface.co/dropbox-dash/faster-whisper-large-v3-turbo/raw/0a363e9161cbc7ed1431c9597a8ceaf0c4f78fcf/README.md)
- [Carte de la conversion GGUF](https://huggingface.co/handy-computer/whisper-large-v3-turbo-gguf/raw/18ada752005f5fddef499256f9a458d0b37a203a/README.md)
- [Carte OpenAI](https://huggingface.co/openai/whisper-large-v3-turbo/raw/41f01f3fe87f28c78e2fbf8b568835947dd65ed9/README.md)
- [Carte NVIDIA et conditions indiquées](https://huggingface.co/nvidia/parakeet-tdt-0.6b-v3/raw/541d1f99c6b0c3cd0b11a95167540bb8edefd82b/README.md)
- [Carte de la conversion GGUF Qwen3-ASR](https://huggingface.co/handy-computer/Qwen3-ASR-0.6B-gguf/raw/7e7c69a577fa2725dfedbe34b5e999336e30a19b/README.md) 
- [Texte CC BY 4.0](https://creativecommons.org/licenses/by/4.0/)
- [Licence du projet Whisper](https://github.com/openai/whisper/blob/main/LICENSE)

Les pages et arborescences étaient lisibles sans authentification ; l'accès effectif aux poids sera vérifié au téléchargement, sans jeton. Si un dépôt devient restreint ou indisponible, ne pas le contourner ni changer silencieusement de modèle. Les rapports CI identifient le modèle, sa révision et sa licence ; pour NVIDIA, ce document fournit aussi l'attribution et le lien de licence. Une éventuelle redistribution future des poids imposerait une vérification distincte des notices, copyrights, modifications et conditions exactes.

## Dépendances principales

D'après leurs métadonnées officielles et dépôts : faster-whisper 1.2.1, CTranslate2 4.8.3, transcribe-cpp et transcribe-cpp-native 0.4.1 déclarent MIT ; Transformers 5.20.2 déclare Apache-2.0 ; PyTorch 2.14.1 utilise notamment BSD-3-Clause avec des composants tiers sous plusieurs licences ; librosa 1.0.0 déclare ISC.

Ce relevé **ne couvre pas toutes les transitives ni tous les composants embarqués des roues**, notamment FFmpeg/PyAV, bibliothèques mathématiques et modules natifs. Le dépôt référence des paquets installés depuis leurs sources, sans les reconditionner. Avant toute distribution d'environnements, de roues, d'exécutables ou de poids, établir un inventaire complet des licences et notices du contenu réellement livré.
