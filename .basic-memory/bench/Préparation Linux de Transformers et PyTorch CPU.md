---
title: Préparation Linux de Transformers et PyTorch CPU
type: note
permalink: transcription-bench/bench/preparation-linux-de-transformers-et-py-torch-cpu
tags:
- validation
- linux
- transformers
- torch
- cpu
---

# Préparation Linux de Transformers et PyTorch CPU

## Périmètre arrêté par l'utilisateur — 2026-11-01
Première tâche uniquement : préparer le verrou candidat et l'environnement Transformers/PyTorch CPU sur le PC Linux déclaré. Aucun téléchargement de modèle ASR, aucune inférence, aucun adaptateur produit ; interdiction explicite de modifier les specs. Après contrôle et revue, commit/push du constat puis note de reprise mémoire séparée après publication. Principal seul autonome ; worker borné et advisor en lecture seule.

## Réalisations et preuves
- [environment] PC Manjaro Linux x86_64, noyau 6.18.55-1-MANJARO, Ryzen 7 PRO 6850U (8 cœurs/16 threads), CPython géré 3.12.13, uv 0.11.8. Environnement isolé nouveau : `data/engines/transformers/`, cible absente avant création, sans écrasement et sans téléchargement d'un autre Python.
- [validation] Pins candidats : transformers==5.20.2, torch==2.14.1+cpu, numpy==2.5.4, psutil==7.2.2. Compilation `uv pip compile --universal --python-version 3.12 --no-build --emit-index-url --torch-backend cpu -o data/feasibility/transformers/transformers.txt data/feasibility/transformers/transformers.in`. Le fichier universel contient **37 pins**, dont colorama conditionné win32 et httpx2-jsfetch conditionné emscripten ; **35 paquets installés sur Linux**. Pas de nvidia/cuda/triton dans le verrou.
- [validation] Installation réussie par `uv pip sync --no-build --torch-backend cpu --python data/engines/transformers/bin/python data/feasibility/transformers/transformers.txt`, puis uv pip check réussi. Roue torch sélectionnée : torch-2.14.1+cpu-cp312-cp312-manylinux_2_28_x86_64.whl, depuis download.pytorch.org/whl/cpu ; aucun extra torchvision/torchaudio/librosa/accelerate ajouté.
- [validation] Contrôle isolé -I -B avec HF_HUB_OFFLINE=1, TRANSFORMERS_OFFLINE=1, HF_HUB_DISABLE_IMPLICIT_TOKEN=1, CUDA_VISIBLE_DEVICES vide, OMP_NUM_THREADS=8 et MKL_NUM_THREADS=8 : torch 2.14.1+cpu, torch.version.cuda=None, torch.cuda.is_available=False ; torch.set_num_threads(8) et get_num_threads=8 ; tenseur CPU minimal réussi. Aucun modèle instancié ou chargé.
- [validation] Classes réellement importables en 5.20.2 : WhisperForConditionalGeneration, WhisperProcessor, ParakeetForTDT, ParakeetProcessor, AutoModelForTDT, AutoProcessor. Cela ne valide ni les poids, ni les fichiers requis des dépôts, ni la transcription, ni le long-form.
- [measurement] Journaux uv : torch187,2Mio, transformers12,2Mio, sympy6,0Mio, networkx2,0Mio, soit207,4Mio visibles ; total estimé210–225Mio (~220–236Mo décimaux), pas une mesure du trafic réseau. Environnement `du -sh` :920M (~920Mio, ~965Mo), torch711M (~711Mio, ~746Mo). Le budget annoncé était250–400Mo de dépendances téléchargées, pas400Mio.
- [validation] Empreintes avant/après identiques pour pyvenv.cfg et les fichiers METADATA du serveur .venv, faster-whisper et transcribe-cpp ; ce contrôle ne couvre pas tous les octets de ces environnements. Le principal a confirmé les empreintes inchangées de uv.lock, pyproject.toml et .python-version, et l'absence de dossier de modèle Transformers.

## Point ouvert prioritaire : transport de l'index CPU
- [blocker] `--emit-index-url` ne conserve dans le candidat que `--index-url https://pypi.org/simple` : l'index ajouté par `--torch-backend cpu` n'est pas émis. La commande de synchronisation réussie dépend donc encore de ce flag. **Le fichier seul n'est pas prêt pour le service d'installation actuel.**
- [provenance] Le worker rapporte qu'un dry-run sans --torch-backend cpu échoue faute de torch==2.14.1+cpu sur PyPI ; son message est cité dans la preuve mais le journal de cet échec précis n'a pas été archivé. Le dry-run verbeux avec backend CPU, lui, conserve l'URL de l'index CPU et la roue retenue.
- [observation] Une variante consignant --extra-index-url https://download.pytorch.org/whl/cpu réussit au dry-run mais sélectionne d'autres versions pour des paquets sans rapport (httpx2 2.3.0 au lieu de2.16.0, idna3.4 au lieu de3.20, packaging24.1 au lieu de26.3, setuptools78.1.0 au lieu de84.2.1, tqdm4.66.5 au lieu de4.70.1). Variante conservée pour analyse, pas retenue ni installée ; aucune décision de modification des specs ou du service.
- [next] Résoudre et vérifier ce transport d'index avant de poursuivre le jalon ou de versionner des requirements/adaptateurs. Ne pas confondre installation CPU locale réussie et résolution complète de la tâche OpenSpec1.2.

## Revue et limites
- [review] Advisor : préparation CPU Linux favorable avec réserves. Il a confirmé les versions, 35 paquets installés, les classes importées, les preuves CPU et le point d'index. Le principal a corrigé les preuves sur37pins/35Linux, les unités, l'interprétation du budget indéterminé avant installation et le statut de la citation de dry-run non archivée.
- [limit] Une requête du script exploratoire tailles-roues.py a reçu HTTP403 ; URL exacte et cause non établies, plusieurs opérations partageant le même bloc d'exception. Ce n'est pas un refus de politique, ni une preuve qu'un HEAD à la bonne URL est interdit. Aucun rejeu pour contourner ce403. Les51Mio connus hors torch incluaient des paquets non Linux/en cache ; le budget total a été estimé a posteriori, pas prouvé entièrement avant téléchargement.
- [limit] Aucun poids ASR, from_pretrained, audio téléchargé ou inférence de modèle ; pas de validation Windows, long-form ou découpage Parakeet. Aucune tâche OpenSpec globale cochée ; specs, code produit et verrou serveur inchangés. Les candidats et preuves sont hors Git sous data/.
- [provenance] Fichiers principaux : `data/feasibility/transformers/transformers.in`, `transformers.txt`, `transformers-variante-extra-index.txt`, `preuves-jalon0-taches-1.2-1.4.json`, `preuves-controle-imports.json`, `controle-imports.py`, `journal-sync.log`, `journal-sync-dry-run-verbose.log`, `empreintes-env-avant.json`, `empreintes-env-apres.json`. La revue n'a relancé ni installation ni inférence.

## Relations
- relates_to [[Décisions du prototype de benchmark]]
- relates_to [[Moteurs et faisabilité technique]]
