## MODIFIED Requirements

### Requirement: Règles de compatibilité par moteur
Pour faster-whisper, le dépôt MUST être au format CTranslate2. Pour transcribe.cpp, il MUST contenir un fichier GGUF d'une architecture de transcription prise en charge. Pour llama.cpp, le fichier GGUF choisi MUST déclarer dans `general.architecture` une architecture de la liste blanche du moteur, c'est-à-dire disposant d'un format de conversation maintenu localement ; les fichiers auxiliaires (projecteurs multimodaux, têtes de prédiction multi-token) et les dépôts à accès restreint MUST être refusés pour ce moteur, sans changer la politique des moteurs de transcription. Pour Transformers, son type de modèle MUST appartenir aux familles prises en charge par l'adaptateur, soit Whisper et Parakeet TDT.

#### Scenario: Poids CTranslate2
- **WHEN** un dépôt CTranslate2 compatible contient `model.bin` et les fichiers requis pour faster-whisper
- **THEN** il est accepté pour faster-whisper ; la restriction safetensors s'applique uniquement à Transformers

#### Scenario: Whisper au format Transformers proposé à faster-whisper
- **WHEN** l'utilisateur choisit faster-whisper pour un dépôt Whisper non converti en CTranslate2
- **THEN** l'ajout est refusé, aucune conversion n'est lancée, et Transformers est indiqué comme moteur possible

#### Scenario: Dépôt GGUF à plusieurs quantifications
- **WHEN** un dépôt pour transcribe.cpp ou llama.cpp contient plusieurs fichiers GGUF
- **THEN** l'utilisateur choisit le fichier avec `--file` et seule cette variante est téléchargée

#### Scenario: Famille Transformers hors périmètre
- **WHEN** le type de modèle du dépôt n'est ni Whisper ni Parakeet TDT
- **THEN** l'ajout pour Transformers est refusé et la famille est annoncée comme extension future

#### Scenario: Architecture LLM non qualifiée
- **WHEN** un fichier GGUF proposé à llama.cpp déclare une architecture absente de la liste blanche
- **THEN** l'ajout est refusé en nommant l'architecture lue, sans télécharger les poids

#### Scenario: Dépôt restreint proposé à llama.cpp
- **WHEN** un dépôt exigeant l'acceptation de conditions est proposé à llama.cpp
- **THEN** l'ajout est refusé avec ce motif, sans téléchargement, même si un jeton est configuré

#### Scenario: Fichier auxiliaire choisi
- **WHEN** l'utilisateur choisit pour llama.cpp un fichier `mmproj-*` ou `mtp-*`, ou un GGUF d'architecture `clip`
- **THEN** l'ajout est refusé avec ce motif

#### Scenario: Modèle d'extraction proposé à un moteur de transcription
- **WHEN** un dépôt GGUF de LLM est proposé à transcribe.cpp
- **THEN** l'ajout est refusé et llama.cpp est indiqué comme moteur possible si l'architecture y est admise
