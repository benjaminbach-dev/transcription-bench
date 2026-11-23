# Préparation de la vérification Windows de la tâche 4.5 (`ajouter-cli-agent`)

**Statut : préparation, rien n'a été exécuté.** Aucun job CI, aucun run, aucun push,
aucun commit, aucun fichier de workflow créé ou modifié. Les YAML ci-dessous sont des
propositions en ligne, à valider avant tout usage. Préparé le 2026-11-23, à la demande
du propriétaire (décision de ne pas étendre le workflow `moteurs-windows.yml` le
2026-11-13 reste en vigueur : la route A passe par un workflow distinct, à autoriser).

Lecture rapide : la CI Windows a déjà prouvé les **services** du programme ; elle n'a
jamais exercé les **commandes CLI** ni les **signaux**. La route A couvre les commandes
CLI sur `windows-2022` (sauf signaux). La route B couvre les signaux sur un poste
Windows interactif, que la CI ne peut pas reproduire.

---

## 1. État des lieux

### 1.1 Vérifié (preuves existantes)

| Sujet | Preuve | Niveau |
|---|---|---|
| Installation des trois moteurs depuis les verrous, contrôle d'import, runner factice | run `43411758748` (commit `3b11338`, `windows-2022`), via les **services** du programme (`scripts/ci/verifier.py installer`) | CI Windows, services |
| Téléchargement explicite et quatre inférences CPU (un modèle par job) | run `43411758748`, via les services (`verifier.py preparer` puis `inferer`) | CI Windows, services |
| Parole synthétique avec voix système locale | `scripts/ci/generer-parole.ps1`, run `41478535615` | CI Windows |
| Suite de tests factice Linux et Windows | run `41472430238` (commit `d9ee207`, 2026-11-02) | CI Windows, **antérieure au socle CLI** |

Source : `docs/ci-windows.md` (tableau des runs). Les rapports JSON nettoyés de ces runs
sont recopiés localement hors Git sous `data/ci/rapports/`.

### 1.2 Non vérifié sous Windows

| Sujet | État | Source |
|---|---|---|
| Sous-commandes CLI : analyse d'arguments, sorties (texte et `--json`), codes 0/1/2/3 | **Non prouvé** : le harnais CI appelle les services, jamais `transcription-bench` | `openspec/changes/ajouter-cli-agent/tasks.md` 4.5 ; `docs/technique.md` (Limites) |
| Tests unitaires de la CLI sous Windows | **Aucune trace documentée** : la dernière exécution de la suite sous Windows (`41472430238`) précède le socle CLI (`7bb6d00`, 88 commits plus récents que `d9ee207`) | `git log` ; `docs/ci-windows.md` |
| Signaux : `Ctrl+C` (SIGINT) sous Windows ; arrêt de `run start` ; arrêt de `serve` | **Non prouvé** : impossible en CI (« l'annulation d'un job ne vaut pas Ctrl+C interactif ») | `docs/ci-windows.md` ; `transcription_bench/supervision.py` (`signaux_arret_normal` : SIGINT seul sur `nt`) |
| Récupération après terminaison brutale sous Windows | **Non prouvé** : le chemin est « à éprouver sur un PC réel » | `docs/technique.md` (Limites) |
| Verrou d'instance (`msvcrt.locking`) : refus code 2 et libération | **Non prouvé** sous Windows | `transcription_bench/instance.py` |
| Chemins : refus des séparateurs `\`, du `:` et des chemins absolus | **Code présent, non exécuté sous Windows** | `transcription_bench/paths.py` |

### 1.3 Preuves Linux (volet 4.5 renouvelé, 2026-11-23)

Fichier : `data/feasibility/cli-agent/qualification/preuves-4-5-linux-2026-11-23.json`
(+ `journaux/`, `runs/`). Points utiles pour Windows :

- Commandes réelles exécutées, codes observés : `engines install` 0, `models check`
  2 sans `--file` puis 0, `models download` 0, `run check`/`run start` 0, `models delete` 0,
  `extract check llama-cpp` 2 (famille non qualifiée), `extract check factice` 0.
- Arrêt par `SIGTERM` sur `run start` : **code 3 capturé**, moteur tué (code −15), verrou
  libéré, aucun `result.json` fabriqué. Un premier essai (`C3`) a visé un **sous-shell**
  au lieu du CLI : le code n'a pas été capturé. Leçon reprise en route B.
- Isolation réseau : `unshare -rn` prouvé par énumération des interfaces seulement
  (pas de trafic) ; ce n'est pas une coupure réseau prouvée.
- Commit testé : `6b65819` (copie `.scratch-4-5`) ; `HEAD` du dépôt est `3970155`, son fils.
- L'audio `consultation_05m_gemini.wav` a servi aux essais Linux. **Son nom évoque une
  consultation : il ne doit ni être copié sur un poste Windows, ni servir en CI** (statut de
  données personnelles à confirmer par le propriétaire ; par précaution, exclu).

### 1.4 Points de vigilance avant toute qualification

- L'arbre de travail contient des modifications non commitées (`docs/technique.md`,
  `tests/`, `engines/declarations.py`, etc.) : le lot de la tâche 6.2
  (`ajouter-bench-extraction`), qui fixe la liste blanche définitive et qualifie la famille
  `llm-gguf` (`qualifiee=True`, définitif depuis le 2026-11-23, provenance en commentaire).
  **Une qualification Windows doit porter sur un commit propre et fixé**,
  jamais sur l'arbre de travail.
- Le propriétaire doit choisir le commit à qualifier ; le consigner dans chaque rapport.

---

## 2. Route A : runner CI `windows-2022` (manuel)

### 2.1 Ce que la route A prouve et ne prouve pas

- **Prouve** (si les codes observés correspondent aux attendus) : analyse des
  sous-commandes, sorties `--json` (UTF-8, `schema: 1`), codes 0/1/2 des commandes non
  interrompues, refus de chemins Windows, verrou pris et libéré, comportement après
  terminaison brutale d'un processus (pas un signal).
- **Ne prouve pas** : `Ctrl+C`, `SIGINT` ou `SIGTERM`, code 3 sous Windows, coupure
  réseau, performances, qualité des transcriptions, ni le comportement sur le PC utilisateur.

### 2.2 Application des contraintes d'`AGENTS.md` (section « Intégration continue GitHub Actions »)

| Contrainte | Mise en œuvre dans la proposition |
|---|---|
| Tests sans accès réseau externe hors téléchargements explicites | Job `lecture` : `UV_OFFLINE`, `HF_HUB_OFFLINE` ; seul `uv sync --locked` touche PyPI, comme `tests.yml`. Téléchargements uniquement dans l'étape `modele-telechargement`. |
| Parole synthétique créée sur le runner, voix système locale | `generer-parole.ps1` (échec explicite sans voix) ; **placé avant toute installation et tout téléchargement** (ordre de `ci-windows.md`). |
| Un seul modèle par job | Job `modele` : un seul GGUF, `whisper-large-v3-turbo-Q5_K_M.gguf` de `handy-computer/whisper-large-v3-turbo-gguf`, révision figée. C'est le cas `transcribe-gguf` déjà existant. |
| Aucun modèle ni famille supplémentaire | Aucun autre modèle ; `extract start` et llama-cpp exclus. |
| Aucun audio personnel | Seul `parole.wav` (synthétique) est copié dans le dossier d'entrée. |
| Aucun poids, audio, environnement, transcription dans artefacts ou caches | Artefact limité à `data/ci/rapports/cli-*.json`. Sorties CLI conservées sous `data/ci/cli/` (non publié). Aucun cache (`enable-cache: "false"`). |
| Rapports JSON nettoyés = seules preuves | Rapports construits à partir d'un schéma fermé ; aucun texte de sortie CLI, aucun chemin. |
| CPU uniquement | Contrôle du champ `backend` = `CPU` dans `results show` ; aucun GPU. |
| Jobs manuels uniquement | `workflow_dispatch` seul ; entrées booléennes `lecture` et `modele`, défaut prudent. |
| Aucune activation de service par modification locale | Le fichier n'a aucun effet tant qu'il n'est pas créé, poussé et lancé sur autorisation. |
| Annulation ≠ Ctrl+C | Aucune prétention de signal ; la terminaison brutale est un test distinct, nommé comme tel. |
| Consigner commit, image, versions, ressources | `rapport()` de `verifier.py` (commit, `ImageOS`, uv, Python) + versions moteur lues par `engines list --json`. |
| Dépôt public requis, sinon échec explicite | `if: github.event.repository.private == false` et `exiger_ci_publique()` appelé par le driver. |
| Pas de nouvelle dépendance | Driver en stdlib + `psutil` (déjà dépendance serveur) ; réutilise `verifier.py` (`CAS`, `preuve_audio`, `rapport`, `exiger_ci_publique`). |

### 2.3 Contrat du driver proposé (à créer après accord, non écrit)

Fichier proposé : `scripts/ci/cli_windows.py`. Il **n'existe pas encore** : les appels YAML
ci-dessous sont inopérants tant qu'il n'est pas écrit et testé hors réseau.

- Entrée : une phase (`lecture`, `modele-installation`, `modele-telechargement`,
  `modele-execution`). Lancé par `uv run --locked --no-sync python scripts/ci/cli_windows.py <phase>`.
- Lancement de la CLI : `sys.executable -m transcription_bench.cli ...` (le module expose
  `if __name__ == "__main__"`). Pas de trampoline `uv` dans le processus mesuré, et le
  processus n'importe aucune bibliothèque de moteur.
- Sorties : `stdout`/`stderr` écrits en UTF-8 sous `data/ci/cli/<phase>/` ; **jamais
  imprimés** dans le journal du job (le dépôt est public, les journaux le sont aussi).
- Variable `PYTHONIOENCODING` retirée pour une étape témoin (encodage par défaut d'un tube).
- Pour chaque étape : identifiant, arguments fixes, code attendu, `ok`, `schema` lu sur la
  sortie JSON, champ `etat` lu, et `motif` (présence d'une sous-chaîne fixe dans `stderr`,
  booléen seulement). Aucune autre donnée n'est recopiée.
- Une étape d'observation (`attendu: null`) ne fait pas échouer le job ; elle est consignée.
- Échec si une étape ne correspond pas à son attendu, si une sortie `--json` n'est pas un
  objet UTF-8 de `schema: 1`, ou si une étape est **non concluante** (ex. exécution déjà
  terminée au moment de l'arrêt brutal). Une étape non concluante n'est jamais un succès.
- Rapport : `data/ci/rapports/cli-<phase>.json`. La famille `cli` doit être ajoutée à
  `CHAMPS_VERIFICATION` de `scripts/ci/verifier.py` (modification de `verifier.py` à
  autoriser : la liste blanche ne s'élargit pas par héritage). `rapport()` affiche le
  rapport sur la sortie standard : le contenu est limité aux champs de la liste blanche.
- Tests du driver : unitaires, hors réseau, avec une CLI factice (sur le serveur de
  développement, sans moteur réel).

### 2.4 Jobs, phases et étapes

Attendus pris dans le code et `docs/technique.md`. Les codes marqués « à confirmer » doivent
être relus dans `tests/test_commands.py` ou via `--help` avant écriture du driver.

**Job `lecture`** (sans réseau, sans modèle, `timeout 20`) :

| Id | Commande (arguments fixes) | Attendu | Contrôle propre |
|---|---|---|---|
| L01 | `--help` | 0 | `data/` absent avant et après (pas d'écriture) |
| L02 | `serve --help`, `engines install --help`, `run start --help`, `models download --help` | 0 chacun | `data/` absent |
| L03 | `--port 9000 data check` | 2 | `--port` refusé hors `serve` (motif à fixer) |
| L04 | `commande-inexistante` | 2 | argparse |
| L05 | `data check --json` | 0 | `schema: 1`, sortie = un objet UTF-8 |
| L06 | `audios list --json`, `models list --json`, `run options --json`, `results list --json`, `results history --json`, `results explain`, `extract options --json`, `extract list --json`, `grids list --json` | 0 chacun | sorties parsables |
| L07 | `engines list --json` | 0 | transcribe-cpp « non installé » |
| L08 | `grids show NOM` (NOM pris dans `grids list`) | 0 | — |
| L09 | `extract check` avec le modèle factice, grille de `grids list` | 0 | témoin factice, aucun lancement ; options exactes à relever dans `--help` |
| L10 | `extract check` avec une référence non prête (llama-cpp) | 2 | jamais de LLM réel |
| L11 | `run check --model REF-INEXISTANTE --audio ..\x.wav` ; `--audio C:\x.wav` ; `--audio sous\x.wav` | 2 chacun | motif « séparateur » ou « absolu » présent ; **sinon le refus est pour une autre raison** |
| L12 | `models delete transcribe-cpp ..\x` ; `results show ..\x --json` | 2 | refus de chemin sortant |
| L13 | `data check` en texte, `PYTHONIOENCODING` retiré | 0 | `stderr` sans « Traceback » ni « UnicodeEncodeError » |
| L14 | `results list` en texte (accents dans la sortie) | 0 | idem |
| L15 | **Verrou** : `serve --port 8765` lancé en arrière-plan ; attente HTTP 200 sur `127.0.0.1` ; `data check` ; `engines list` | 2, 2 (motif « déjà ce dossier ») | observation |
| L16 | Arrêt brutal de l'arbre du serveur (psutil, pas un signal) ; `data check` puis `engines list` | 0, 0 | verrou libéré par la mort du processus |

Note L15-L16 : la terminaison brutale ne prouve que la **libération du verrou par la mort du
processus** (verrouillage `msvcrt`). Elle ne prouve ni `Ctrl+C` ni le code de sortie d'un signal.
Le code brut relevé est **observé, non asserté**.

**Job `modele`** (un seul modèle, `timeout 60`) :

| Phase | Étape | Commande | Attendu |
|---|---|---|---|
| installation | M01 | copie du seul WAV vérifié (`preuve_audio`) vers `data/audio/parole.wav` | — |
| installation | M02 | `engines install transcribe-cpp` | 0 |
| installation | M03 | `engines list --json` ; `engines log transcribe-cpp --limit 2000 --json` | « prêt » ; 0 |
| telechargement | M04 | `models check REPO --engine transcribe-cpp --revision R` (sans `--file`) | 2, raison `fichier-gguf-non-choisi` |
| telechargement | M05 | même commande avec `--file whisper-large-v3-turbo-Q5_K_M.gguf` | 0 |
| telechargement | M06 | `models download` avec les mêmes arguments (`HF_HUB_OFFLINE=0`) | 0 ; référence locale en dernière ligne |
| telechargement | M07 | `models download` à nouveau | 0, sans transfert (journal « déjà prêt ») |
| telechargement | M08 | `models list --json` | un modèle, `commit` = R |
| execution | X01 | `audios list --json` | exactement `parole.wav` |
| execution | X02 | `run options --json` | référence présente |
| execution | X03 | `run check --model REF --audio parole.wav --threads 4 --json` | 0 ; nombre de résultats inchangé |
| execution | X04 | `run start` (mêmes arguments) `--json` | 0 ; état `completed` ; `backend` = `CPU` (lu dans `results show`) |
| execution | X05 | `results list --json`, `results show ID --json`, `results history --json`, `results list --sort temps --json` | 0 chacun |
| execution | X06 | `results list --sort inconnu` | 2 |
| execution | X07 | `run start --model REF --audio absent.wav` ; `run check ... --setting INCONNU=1` ; `run start ... --audio ..\parole.wav` | 2 chacun (motif fixe présent) |
| execution | X08 | **Terminaison brutale pendant l'inférence** : `run start` en arrière-plan ; attente de la ligne « Modèle chargé » dans la sortie `--json` ; 2 s ; arrêt de l'arbre (psutil) ; aucun processus moteur survivant | arrêt observé (code brut non asserté) |
| execution | X09 | `run check` (récupération) ; `results list --json` | 0 ; dernière exécution `abandoned` ; sinon **non concluant** |
| execution | X10 | `run start` à nouveau | 0 ; nouvel identifiant `completed` |
| execution | X11 | `models delete transcribe-cpp ..\x` ; `models delete transcribe-cpp KEY` ; `results show ID --json` | 2 ; 0 ; 0 (résultats conservés) |
| execution | X12 (observation) | `run check --audio PARole.wav` (fichier `parole.wav`) | observé, non asserté (casse sur NTFS) |

Ordre contraint : X08 avant X11 (il faut le modèle pour X08). `X08` ne doit pas tuer une
exécution déjà terminée : si l'exécution est `completed` à l'arrêt, l'étape est **non concluante**.
Pour fiabiliser X08, l'audio doit durer plus que le délai entre « Modèle chargé » et la fin ;
la durée de la parole synthétique est à mesurer à la première exécution (pas de présomption).

### 2.5 Workflow proposé (à créer après accord, non écrit)

Fichier proposé : `.github/workflows/cli-windows.yml`. Il ne doit pas modifier
`moteurs-windows.yml` (décision du 2026-11-13). Les SHA d'actions sont **ceux déjà épinglés**
dans `tests.yml` et `moteurs-windows.yml` (aucune nouvelle action).

```yaml
name: CLI Windows (manuel)

on:
  workflow_dispatch:
    inputs:
      lecture:
        description: Commandes de lecture, refus de syntaxe, chemins Windows et verrou (sans réseau ni modèle)
        type: boolean
        default: true
      modele:
        description: Un seul modèle d'essai (transcribe-cpp, Whisper GGUF Q5_K_M) par les commandes CLI
        type: boolean
        default: false

permissions:
  contents: read

concurrency:
  group: cli-windows-${{ github.ref }}
  cancel-in-progress: true

env:
  PYTHONIOENCODING: utf-8
  HF_HUB_DISABLE_TELEMETRY: "1"
  HF_HUB_DISABLE_IMPLICIT_TOKEN: "1"
  HF_HOME: ${{ github.workspace }}/data/ci/hf
  NUMBA_CACHE_DIR: ${{ github.workspace }}/data/ci/numba
  TB_DEPOT_PUBLIC: ${{ github.event.repository.private == false && 'true' || 'false' }}

jobs:
  lecture:
    if: inputs.lecture && github.event.repository.private == false
    runs-on: windows-2022
    timeout-minutes: 20
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
        with:
          persist-credentials: false
      - uses: astral-sh/setup-uv@68559e99cc807c1eb7e9238fd43a15bba460eec2 # v10.3.3
        with:
          version: "0.11.8"
          enable-cache: "false"
      - name: Installer les seules dépendances serveur verrouillées (comme tests.yml)
        run: uv sync --locked
      - name: Commandes de lecture, refus, chemins Windows, encodage et verrou (sans réseau)
        env:
          UV_OFFLINE: "1"
          UV_PYTHON_DOWNLOADS: never
          HF_HUB_OFFLINE: "1"
        run: uv run --locked --no-sync python scripts/ci/cli_windows.py lecture
      - name: Conserver uniquement le rapport JSON nettoyé
        uses: actions/upload-artifact@cf430e030ddbb5b0abf93d22962f4752f3646cd9 # v7.0.2
        with:
          name: cli-lecture
          path: data/ci/rapports/cli-lecture.json
          retention-days: 14
          if-no-files-found: error

  modele:
    if: inputs.modele && github.event.repository.private == false
    runs-on: windows-2022
    timeout-minutes: 60
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
        with:
          persist-credentials: false
      - uses: astral-sh/setup-uv@68559e99cc807c1eb7e9238fd43a15bba460eec2 # v10.3.3
        with:
          version: "0.11.8"
          enable-cache: "false"
      - run: uv sync --locked
      - name: Vérifier la voix système locale et créer la parole synthétique AVANT tout téléchargement
        shell: powershell
        run: ./scripts/ci/generer-parole.ps1
      - name: Installer transcribe-cpp par la CLI (roue explicite, aucun poids)
        env:
          HF_HUB_OFFLINE: "0"
        run: uv run --locked --no-sync python scripts/ci/cli_windows.py modele-installation
      - name: Vérifier puis télécharger explicitement le seul GGUF d'essai par la CLI
        env:
          HF_HUB_OFFLINE: "0"
        run: uv run --locked --no-sync python scripts/ci/cli_windows.py modele-telechargement
      - name: Exécuter hors ligne par la CLI (lancement, résultats, arrêt brutal, suppression)
        env:
          HF_HUB_OFFLINE: "1"
          UV_OFFLINE: "1"
          UV_PYTHON_DOWNLOADS: never
        run: uv run --locked --no-sync python scripts/ci/cli_windows.py modele-execution
      - name: Conserver uniquement les rapports JSON nettoyés
        uses: actions/upload-artifact@cf430e030ddbb5b0abf93d22962f4752f3646cd9 # v7.0.2
        with:
          name: cli-modele
          path: data/ci/rapports/cli-modele-*.json
          retention-days: 14
          if-no-files-found: error
```

Points de contrôle du YAML :

- `generer-parole.ps1` est exécuté **avant** l'installation et le téléchargement : sans voix,
  le job échoue avant tout élargissement (procédure de `docs/ci-windows.md`).
- Les étapes `run` utilisent le shell par défaut (`pwsh` sous `windows-2022`) ; le driver
  Python lit chaque code de sortie lui-même et ne compte pas sur `$LASTEXITCODE` implicite.
- `path` des artefacts ne couvre que `data/ci/rapports/`. Les sorties CLI (`data/ci/cli/`),
  `data/audio`, `data/models`, `data/engines`, `data/results` et `.venv` ne sont jamais publiés.
- `if-no-files-found: error` : un rapport absent fait échouer le job.
- Le job `modele` ne contient qu'un moteur (`transcribe-cpp`) et qu'un modèle ; pas de `extract start`.

### 2.6 Points de contrôle Windows propres à la CLI

| Sujet | Contrôle | Risque couvert |
|---|---|---|
| Chemins et séparateurs | L11, L12, X07 : `\`, `:`, chemin absolu, `..` refusés en code 2 avec le motif attendu | Un chemin accepté par erreur hors `data/audio` |
| Shell | Driver Python ; aucune dépendance à `bash` ; `uv run` seulement | Supposer `bash` ou un `$LASTEXITCODE` implicite |
| Encodage des sorties | L13, L14 : tube sans `PYTHONIOENCODING` ; `--json` en UTF-8 | `UnicodeEncodeError` sur console `cp1252` |
| Verrou et libération | L15, L16 (mort du processus) ; `engines list` après chaque échec | Verrou jamais libéré, `msvcrt` mal géré |
| Casse | X12 (observation) | Comportement NTFS insensible à la casse, non documenté |
| Terminaison brutale et récupération | X08, X09 ; code brut observé | Exécution laissée `running`, moteur survivant |
| Processus moteur | X08 : aucun PID de l'arbre ni moteur survivant (psutil) | Moteur orphelin après arrêt |
| Fin de ligne | Parsing ligne à ligne, `splitlines` | `\r\n` dans les journaux `--json` |

### 2.7 Volumes annoncés (route A)

- **Job `lecture`** : `uv sync --locked` (dépendances serveur, PyPI). Aucun modèle, aucun moteur,
  aucun transfert explicite au-delà du cache serveur.
- **Job `modele`** :
  - roues `transcribe-cpp` (`transcribe-cpp-native` ≈ 21,7 Mio, `numpy` ≈ 16 Mio et dépendances) :
    **estimation de l'ordre de 40 à 60 Mio, à relever dans le journal** ;
  - GGUF `whisper-large-v3-turbo-Q5_K_M.gguf` : **590,9 Mio** (mesuré sous Linux), révision figée ;
  - métadonnées Hugging Face : ≈ 1 Mio ; parole synthétique : < 1 Mio.
  - Espace libre contrôlé contre la taille annoncée par `models check` avant téléchargement.
- Durée : non estimée ici. Les durées ne sont pas des performances (ci-dessous).
- Conservation : 14 jours, rapports JSON seulement.

---

## 3. Route B : poste Windows interactif (signaux et observations)

### 3.1 Prérequis

- Poste Windows **déclaré** par le propriétaire comme poste de test (le worker et la CI ne
  le déduisent pas). Version Windows, shell (Windows PowerShell 5.1 ou `pwsh` 7), `chcp`,
  notés dans la fiche.
- Un clone **dédié** du dépôt, sur un commit propre et fixé (pas le dossier de travail
  contenant des données personnelles).
- Autorisations explicites du propriétaire pour : `uv sync --locked` (PyPI),
  `engines install transcribe-cpp` (roues), `models download` du seul GGUF (590,9 Mio),
  inférences CPU sur **parole synthétique uniquement**. Espace libre estimé : au moins 2 Gio
  (estimation, à confirmer sur le poste).
- Audio : uniquement la parole synthétique générée par `scripts/ci/generer-parole.ps1` (ou
  un texte synthétique plus long, créé localement). Pour les interruptions il faut une
  inférence assez longue : l'audio doit durer plus de 60 s. Le script actuel produit une phrase
  courte ; **l'allongement est à décider** (paramètre à ajouter au script, ou répétition
  dans le texte). Aucun audio d'un poste utilisateur ni `consultation_05m_gemini.wav`.
- Aucun secret, aucun jeton Hugging Face : l'accès aux dépôts publics est anonyme.

### 3.2 Règles d'observation (aucun relevé fabriqué)

- Chaque valeur de la fiche (code, extrait, PID) est **copiée depuis l'observation** ; une
  case vide signifie « non observé », jamais « conforme ».
- Le code se relève **immédiatement** après la commande : `echo $LASTEXITCODE` (PowerShell)
  ou `echo %errorlevel%` (cmd).
- Les PID moteurs proviennent de la ligne « Processus moteur lancé (PID n) » du journal.
- Avant tout arrêt de processus : vérifier l'identité (`Get-CimInstance Win32_Process` :
  ligne de commande contenant `transcription_bench` ou `transcription-bench`). Ne jamais
  arrêter un Python dont l'identité n'est pas confirmée.
- Un extrait de journal est limité à dix lignes, sans transcription, avec le nom
  d'utilisateur remplacé par `<utilisateur>` et les chemins personnels masqués.
- Les observations non prévues sont consignées telles quelles, sans correction.

### 3.3 Runbook pas à pas

Dossier de travail : `<clone-de-test>`. Commandes en PowerShell, commande CLI via `uv run`
comme dans `docs/ci-windows.md`.

**B0 — Préparation**
1. `git rev-parse HEAD`, `git status --short` (doit être vide). Consigner commit.
2. `uv --version` (attendu : 0.11.8, version de la CI). Consigner.
3. `uv sync --locked`. Consigner code et durée.
4. Vérifier qu'aucun `data\` n'existe encore (`Test-Path data`).

**B1 — Aide sans écriture**
5. `uv run --locked transcription-bench --help` → code 0 ; `Test-Path data` doit rester `False`.

**B2 — Encodage et chemins (console)**
6. `chcp` puis `uv run --locked transcription-bench data check` → code 0 ; accents visibles ;
   pas de « Traceback ».
7. `uv run --locked transcription-bench run check --model REF --audio ..\x.wav` → 2, motif
   « séparateur » ; idem `--audio C:\x.wav` → 2.
8. Observation de casse : placer le WAV synthétique sous `data\audio\parole-test.wav`, puis
   `run check --audio PARole-TEST.WAV` → **code et message relevés, sans attendu imposé**
   (le comportement n'est pas documenté).

**B3 — Modèle (une fois, explicite)**
9. `engines install transcribe-cpp` → 0 ; `models check ... --revision R` (sans `--file`) → 2 ;
   avec `--file whisper-large-v3-turbo-Q5_K_M.gguf` → 0 ; `models download` → 0 ; relever la
   référence `transcribe-cpp/<hash>`.

**B4 — Ctrl+C pendant `run start` (scénario principal)**
10. Lancer : `uv run --locked transcription-bench run start --model REF --audio <long>.wav --threads 4`
    dans une console dédiée (ne pas en lancer d'autres).
11. Attendre la ligne « Modèle chargé », puis 30 s d'inférence. Relever l'heure et le PID moteur.
12. Appuyer **une seule fois** sur `Ctrl+C`.
13. Attendre la fin, puis `echo $LASTEXITCODE` (**attendu selon `docs/technique.md` : 3**).
    Attendus dans le journal : « arrêt demandé par signal », « Exécution interrompue »,
    « Les résultats reçus sont conservés », « Opération interrompue à la demande de l'utilisateur ».
14. Vérifier le moteur : `Get-Process -Id <PID>` doit échouer (processus disparu). Lecture seule.
15. `uv run --locked transcription-bench run check --model REF --audio parole-test.wav` → 0
    (verrou libéré) ; `results list` montre l'exécution en état « interrompue ».
16. Écart (code ≠ 3, ou verrou tenu) : **noter et ne pas corriger** ; l'écart est soumis au
    propriétaire. Pour isoler `uv`, refaire B4 avec `.venv\Scripts\transcription-bench.exe run start ...`.
    Note : `uv run` sous Windows ignore `Ctrl+C` et le délègue à l'enfant ; la propagation du
    code de sortie n'est pas documentée pour ce cas.

**B5 — Double `Ctrl+C` (second signal)**
17. Nouvelle exécution comme B4 (étapes 10-11). Appuyer deux fois `Ctrl+C` à moins d'une seconde.
18. Attendu : une seule clôture journalisée, pas de trace, code relevé. Le second signal est
    ignoré (`SIG_IGN`). Noter le nombre de lignes « Arrêt demandé » observées.
19. Vérifier le verrou comme en B4-15.

**B6 — `Ctrl+C` sur le serveur**
20. `uv run --locked transcription-bench serve --port 8765` ; vérifier avec
    `Invoke-WebRequest http://127.0.0.1:8765/` (lecture seule, loopback).
21. `Ctrl+C` une fois : attendu « Arrêt du serveur. » ; code relevé (les codes du serveur sont
    0, 1, 2 selon `docs/technique.md` ; la valeur attendue pour un signal reste à observer).
22. `uv run --locked transcription-bench data check` → 0 (verrou libéré).

**B7 — `Ctrl+C` pendant un téléchargement (facultatif, à décider par le propriétaire)**
23. Lancer `models download` sur le GGUF (ou sur un modèle déjà présent : attendu « déjà prêt »,
    donc pas de transfert). Le téléchargement n'est pas annulable : attendre la fin réelle du
    processus, sans `Stop-Process`. Relever si le verrou reste tenu jusqu'à la fin.

**B8 — Terminaison brutale (pas un signal)**
24. Nouvelle exécution `run start`, attendre « Modèle chargé ». Identifier le processus Python
    (identité confirmée). Terminer ce seul processus via le gestionnaire de tâches ou
    `Stop-Process -Id <PID>`. **Relever le code de sortie observé** (non attendu par la doc).
25. Vérifier : PID moteur encore présent ? (`Get-Process`). S'il survit, le noter : aucun
    arrêt manuel sans accord, sauf identité confirmée et accord du propriétaire.
26. `uv run --locked transcription-bench results list` : récupération attendue (exécution
    « abandonnée »). Relever l'état et le code de la commande.

**B9 — Relance**
27. `uv run --locked transcription-bench run start --model REF --audio parole-test.wav --threads 4`
    → code attendu 0, nouvel identifiant. Relever.

**B10 — Nettoyage**
28. Suppression du clone et des données de test : **uniquement sur accord explicite** (suppression
    hors dépôt). Sans accord, rien n'est supprimé.

### 3.4 Fiche d'observation à remplir

| Champ | Valeur (observée) |
|---|---|
| Date et heure (fuseau) | |
| Version de Windows, édition, build | |
| Shell et version (PowerShell 5.1 / pwsh 7) ; `chcp` | |
| Commit testé ; `git status` propre | |
| Version uv ; version Python du `.venv` | |
| Étape (B0 à B10) ; commande exacte (chemins personnels masqués) | |
| Code relevé immédiatement (`$LASTEXITCODE`) | |
| Attendu (doc) et écart éventuel | |
| PID moteur ; présence après l'événement (`Get-Process`) | |
| Extrait de journal (≤ 10 lignes, sans transcription) | |
| Verrou : code de `data check` ou `run check` après l'événement | |
| Observations non prévues | |

Ce que le propriétaire doit relever pour chaque scénario : commande, code, extrait de journal,
PID, état final. Il reporte l'écart, sans conclusion par anticipation.

---

## 4. Critères d'acceptation

### 4.1 Route A (CI)

- Chaque étape obtient son code attendu (ou la valeur d'une observation consignée) ;
  toute étape `non concluante` ou en écart fait échouer le scénario, pas de succès implicite.
- Chaque sortie `--json` est un objet UTF-8 unique ou une suite de lignes JSON, avec `schema: 1`.
- Le rapport `cli-*.json` ne contient que les champs de la liste blanche : aucun texte de
  sortie, aucun chemin, aucune donnée système brute. Vérification : l'artefact ne contient
  aucun mot du texte synthétique (texte de `generer-parole.ps1`).
- Le journal public du job ne contient ni transcription ni chemin personnel (relecture humaine).
- Le verrou est pris puis libéré après `serve` terminé brutalement (L16) et après X08/X09.
- Commit, image, versions consignés.
- Conclusion limitée à « CLI exécutée sur `windows-2022`, codes conformes, arrêt brutal observé ».
  Aucune mention de `Ctrl+C`, de code 3 sous Windows ni de performance.

### 4.2 Route B (poste interactif)

- Chaque scénario B4, B5, B6, B8 est documenté par une fiche complète (commande, code relevé,
  extrait de journal, PID, état final).
- Le code 3 pour `Ctrl+C` est **observé** ; s'il diffère, le scénario est en écart et n'est pas
  accepté avant arbitrage du propriétaire.
- Aucune case de fiche remplie hors observation.
- Le moteur n'est plus présent après un arrêt (vérification par PID) ; sinon, écart consigné.

### 4.3 Ce qui n'est jamais acceptable comme preuve

- Un job ignoré (dépôt privé) : ce n'est pas un succès.
- Une annulation GitHub (`cancel-in-progress`) : ce n'est pas un `Ctrl+C`.
- Une valeur recopiée depuis la documentation ou depuis Linux.
- Des chiffres de durée ou de RAM présentés comme performance.

---

## 5. Checklist de décision du propriétaire

Chaque point doit être autorisé **explicitement** ; aucun n'est implicite.

- [ ] **Création du workflow** `.github/workflows/cli-windows.yml` (nouveau fichier, distinct de
  `moteurs-windows.yml`), avec les entrées `lecture` et `modele` (défaut `lecture` seul).
- [ ] **Création du driver** `scripts/ci/cli_windows.py` et ajout d'une famille `cli` dans
  `scripts/ci/verifier.py` (`CHAMPS_VERIFICATION`), avec tests unitaires hors réseau.
- [ ] **Commit** du changement (aucun commit sans demande explicite) et **push** vers le remote :
  indispensable pour qu'un run GitHub existe. Vérifier identité, remote et branche avant.
- [ ] **Lancement** du run `cli-windows` avec `lecture` seul.
- [ ] **Lancement** du run avec `modele` (un seul modèle, ≈ 0,6 Gio de téléchargement et une
  inférence CPU sur parole synthétique), séparément du précédent.
- [ ] **Lancement préalable** de `tests.yml` (workflow existant, `workflow_dispatch`) sur le même
  commit pour exécuter la suite factice CLI sous `windows-2022` : aucune trace n'existe après
  l'ajout de la CLI.
- [ ] **Publication des preuves** : les rapports JSON restent en artefacts 14 jours. Toute
  copie durable (`data/ci/rapports/` local, ou tout document) est une décision distincte.
- [ ] **Prêt d'un poste Windows** (route B) : poste déclaré, dossier de test dédié, volumes
  annoncés (§3.1), et qui conduit les manipulations (humain).
- [ ] **Audio** : confirmer qu'aucun audio personnel ni `consultation_05m_gemini.wav` ne sera
  utilisé sur CI ni sur le poste.
- [ ] **Scénarios facultatifs** : B7 (interruption d'un téléchargement) ; allongement de l'audio
  synthétique (modification de `generer-parole.ps1`, à décider).
- [ ] **Commit à qualifier** fixé, arbre propre : le lot de la tâche 6.2 (qualification
  `llm-gguf`, liste blanche définitive) doit être commité avant ; sinon la qualification
  porterait sur un état provisoire.
- [ ] **Cocher la tâche 4.5** : seulement après les preuves de la route A et de la route B,
  et sur décision du propriétaire (le worker ne modifie pas `tasks.md`).

Hors périmètre, à refuser sans nouvel accord : `extract start`, llama-cpp en CI, tout autre
modèle ou famille, coupure réseau réelle, Ctrl+C simulé en CI, suppression hors dépôt.

---

## 6. Limites

- Aucune extrapolation Linux → Windows : les preuves Linux ne valent pas pour Windows.
- Aucune extrapolation CI → PC utilisateur : la CI tourne sur un runner éphémère, avec une
  image Visual C++ qui ne représente pas un PC neuf.
- Les performances CI (durées, RAM, CPU) ne sont pas des mesures du PC utilisateur ni des
  performances attendues.
- La CI ne couvre pas les signaux : ni `Ctrl+C`, ni `SIGINT`, ni `SIGTERM`, ni code 3 sous Windows.
- La terminaison brutale testée en CI (psutil) n'est pas un signal ; elle ne remplace pas la route B.
- Les options hors ligne (`HF_HUB_OFFLINE`, `UV_OFFLINE`) ne sont pas une coupure réseau prouvée.
- Le driver, le workflow et la famille `cli` n'existent pas encore : cette préparation n'a rien
  exécuté ni testé. Les codes marqués « à confirmer » sont à vérifier avant écriture.
- Le comportement de `uv run` sous Windows face à `Ctrl+C` (code relayé) n'est pas documenté ;
  la route B le consigne et ne le suppose pas.
- La casse des chemins sous NTFS est une observation sans attendu.
- Le run `43411758748` et la suite `41472430238` restent les seules preuves Windows, au niveau
  services ou tests factices antérieurs à la CLI.

---

## 7. Sources

- `openspec/changes/ajouter-cli-agent/tasks.md` (tâche 4.5 et notes d'état).
- `docs/technique.md` : « Utiliser le programme en commande (agents) », codes et signaux, limites.
- `docs/ci-windows.md` : runs CI, procédure de levée des limites hors CI.
- `docs/proposition-contexte-ci.md` : contexte CI proposé.
- `.github/workflows/moteurs-windows.yml` et `.github/workflows/tests.yml` : SHA épinglés et structure.
- `scripts/ci/verifier.py`, `scripts/ci/generer-parole.ps1` : services, liste blanche, parole.
- `transcription_bench/supervision.py`, `processus.py`, `instance.py`, `paths.py`, `output.py` : comportements Windows.
- `data/feasibility/cli-agent/qualification/preuves-4-5-linux-2026-11-23.json` : preuves Linux.
- Documentation uv, « Running commands » (https://docs.astral.sh/uv/concepts/projects/run/) :
  sur Windows, uv ignore `Ctrl-C` et le délègue à l'enfant.
- Mémoire projet `transcription-bench` : notes « Socle des commandes CLI » et « Qualification Linux
  CLI et charge système, 2026-11-13 » (lecture seule, sources et non preuves).
