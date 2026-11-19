# Guide utilisateur

Ce guide vous mène, pas à pas, de « rien d'installé » à une première transcription lue, puis à la comparaison de deux résultats. Il s'adresse à une personne à l'aise avec un ordinateur, sans connaissance en programmation, mais prête à copier-coller quelques commandes.

> *Important.* Cet outil est un prototype de comparaison. Il n'est pas validé cliniquement. Une transcription qui se lit bien peut contenir des erreurs : ne l'utilisez jamais comme un texte médical exact sans relecture humaine.

*Niveau de vérification de ce guide.* Une version précédente de ce guide, dont les actions passaient par des pages web aujourd'hui retirées du programme, a été suivie pas à pas le 2026-11-13 sur un PC de test Linux (Manjaro, 64 bits), sur une copie vierge du projet et un dossier de données neuf, de l'obtention du projet (archive ZIP) jusqu'à la comparaison de deux résultats. Depuis, l'interface a changé : les pages web ne servent plus qu'à consulter, et les actions se font par des commandes. Les commandes de ce guide ont été éprouvées une à une le même jour sur le même PC (installation du moteur transcribe.cpp, vérification puis téléchargement du modèle de l'exemple, vérification à blanc, lancement d'exécutions, arrêt par signal) ; le parcours complet de ce guide, dans sa forme actuelle, n'a pas encore été rejoué de bout en bout. Chaque étape porte son niveau réel : « vérifié sous Linux le <date> » ; « contrôlé par la CI Windows » (contrôles automatiques sur les machines de test de GitHub, sans rapport avec votre ordinateur), en précisant ce qui a été contrôlé ; ou « non vérifié ». Sous Windows, la CI a contrôlé la suite de tests, dernière fois le 2026-11-02, puis, le 2026-11-13, l'installation des trois moteurs (aux versions exactes prévues par le projet) et les quatre inférences de démonstration ; ni les commandes du programme, ni l'installeur de `uv`, ni le lancement en console et Ctrl+C ne sont vérifiés sur un poste Windows. Les dates et le détail de chaque validation sont dans [validation-linux.md](validation-linux.md) et [ci-windows.md](ci-windows.md).

## Sommaire

1. [Ce qu'il faut avoir](#1-ce-quil-faut-avoir)
2. [Installer l'outil de lancement](#2-installer-loutil-de-lancement)
3. [Obtenir le projet](#3-obtenir-le-projet)
4. [Ouvrir un terminal](#4-ouvrir-un-terminal)
5. [Lancer l'application](#5-lancer-lapplication)
6. [Déposer vos audios](#6-déposer-vos-audios)
7. [Installer un moteur](#7-installer-un-moteur)
8. [Ajouter et télécharger un modèle](#8-ajouter-et-télécharger-un-modèle)
9. [Lancer une transcription](#9-lancer-une-transcription)
10. [Lire un résultat](#10-lire-un-résultat)
11. [Comparer deux résultats](#11-comparer-deux-résultats)
12. [Arrêter et relancer](#12-arrêter-et-relancer)
13. [Dépannage](#13-dépannage)
14. [Glossaire](#glossaire)
15. [Pour aller plus loin](#pour-aller-plus-loin)

## Ce que fait l'outil, et ce qu'il envoie sur Internet

L'outil transcrit des enregistrements en français et vous permet de comparer le travail de plusieurs modèles. Tout le travail se fait sur votre ordinateur : vos audios et vos transcriptions ne sont envoyés à aucun service.

Vous pilotez l'outil en tapant des commandes dans un terminal ; la page web, elle, ne sert qu'à consulter et comparer les résultats déjà enregistrés. Une commande est une instruction tapée dans le terminal, qui agit puis rend la main.

Quelques mots à connaître (repris dans le [glossaire](#glossaire)) :

- Un modèle est le fichier volumineux qui contient ce que la machine a appris pour transcrire la voix.
- Un moteur est le programme qui fait tourner un modèle.
- Un terminal est une fenêtre dans laquelle on tape des commandes.
- Hugging Face est le site qui héberge les modèles ; un dépôt est la page d'un modèle sur ce site, et une révision en est une version précise.
- GGUF est un format de fichier de modèle ; Python est le langage dans lequel le programme est écrit (l'outil de lancement s'en charge, vous n'avez rien à installer).
- Mo, Go, Mio et Gio sont des unités de taille de fichiers ; le glossaire les définit.
- Un port est le numéro qui termine l'adresse de la page, par exemple 8765 dans `http://127.0.0.1:8765`.

Internet n'est utilisé que dans ces cas :

| Quand | Pourquoi | Quelle quantité |
|---|---|---|
| Installation de l'outil de lancement (étape 2) | récupérer l'outil | non mesuré |
| Obtention du projet (étape 3) | récupérer les fichiers du projet | environ 1 Mo pour l'archive du projet (mesuré le 2026-11-13) |
| Premier lancement (étape 5) | l'outil de lancement peut télécharger lui-même Python et les éléments dont le programme a besoin | non mesuré : le 2026-11-13, ces éléments venaient tous du cache de la machine de test, sans téléchargement visible |
| Installation d'un moteur (étape 7, commande) | récupérer les éléments du moteur | non mesuré en commande (l'ancien parcours par page mesurait environ une seconde le 2026-11-13, éléments pris dans le cache de la machine de test) |
| Vérification d'un modèle (étape 8, commande) | lire la fiche du modèle chez Hugging Face | quelques fichiers de description ; durée de la commande non consignée (l'ancien parcours par page mesurait environ 40 à 50 secondes par vérification le 2026-11-13) |
| Téléchargement d'un modèle (étape 8, commande) | récupérer le modèle | 590,9 Mio (affichés par l'outil), soit environ 620 Mo ; environ 12 secondes en commande le 2026-11-13 (l'ancien parcours par page mesurait environ 6 secondes) |

Sauf le premier lancement, rien de tout cela ne se déclenche sans que vous tapiez une commande : les pages web de l'outil ne lancent rien et ne téléchargent rien. Les durées citées dans ce guide sont celles du PC de test du 2026-11-13 (un ordinateur portable récent, sur une connexion domestique) ; sur votre ordinateur et votre connexion, elles seront différentes. Quand une durée ou une taille n'a pas été mesurée, le guide l'écrit « non mesuré ».

## 1. Ce qu'il faut avoir

- Un ordinateur sous Linux ou Windows (64 bits). Pas de carte graphique nécessaire : l'outil n'utilise que le processeur (le CPU, la puce qui effectue les calculs de l'ordinateur). macOS n'est pas pris en charge.
- De la place sur le disque : l'exemple de ce guide demande environ 620 Mo pour le modèle (590,9 Mio affichés par l'outil), environ 125 Mo pour le moteur transcribe.cpp et ses éléments, et un peu plus pour le programme lui-même (mesurés le 2026-11-13). Prévoyez plusieurs Go libres.
- Un navigateur récent, pour consulter les résultats. Selon la documentation de la feuille de style utilisée, il faut au moins Chrome ou Edge 111, Firefox 121 ou Safari 16.2 ; avec un navigateur plus ancien les pages restent lisibles, avec des couleurs plus simples (non vérifié ici).
- Une connexion Internet pour les étapes de téléchargement (voir le tableau ci-dessus).
- Quelques audios en français à tester (formats `wav`, `mp3`, `m4a`, `ogg`, `opus` ou `flac`). N'utilisez pas d'enregistrements de patients pour vos premiers essais ; pour des enregistrements réels, assurez-vous d'y être autorisé : préférez un enregistrement de test.

Une seule transcription peut tourner à la fois. Plus l'ordinateur a de mémoire vive (la RAM, son espace de travail rapide) et de cœurs de processeur, plus c'est rapide : la mémoire nécessaire n'a pas été mesurée pour ce guide.

## 2. Installer l'outil de lancement

L'outil de lancement s'appelle `uv`. Il prépare tout seul ce dont le programme a besoin ; vous n'avez pas à installer Python vous-même.

*Faites ceci.* Ouvrez un terminal (étape 4) ; le dossier ouvert dans le terminal n'a pas d'importance à cette étape. Puis :

- Linux :

  ```sh
  curl -LsSf https://astral.sh/uv/install.sh | sh
  ```

- Windows (PowerShell) :

  ```powershell
  powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
  ```

  Cette commande télécharge puis exécute un script. Si vous préférez, installez `uv` avec la commande `winget install --id=astral-sh.uv -e`.

Procédure officielle : <https://docs.astral.sh/uv/getting-started/installation/>.

*Vous devez voir.* Le terminal affiche que `uv` est installé. Fermez puis rouvrez le terminal, puis tapez `uv --version` : un numéro de version s'affiche.

*Si ce n'est pas le cas.* Voir « commande introuvable » dans le [dépannage](#13-dépannage).

Vérification : non vérifié. Ni l'installation de `uv` ni celle par `winget` n'ont été suivies, sous Linux comme sous Windows.

## 3. Obtenir le projet

*Faites ceci.* Le projet est public : <https://github.com/benjaminbach-dev/transcription-bench>.

- Sans connaissance particulière : sur cette page, cliquez sur le bouton vert « Code », puis « Download ZIP » (ou « Télécharger le ZIP »). Décompressez l'archive dans un dossier de votre choix, par exemple dans vos documents.
- Avec Git (l'outil qui télécharge un projet et suit son historique) : `git clone https://github.com/benjaminbach-dev/transcription-bench.git`

*Vous devez voir.* Un dossier `transcription-bench` (ou `transcription-bench-main`) contenant notamment les fichiers `README.md` et `pyproject.toml`.

*Si ce n'est pas le cas.* Vérifiez que l'archive est bien décompressée (ouvrez-la dans l'explorateur de fichiers).

Vérification : l'archive ZIP suivie le 2026-11-13 (environ 1 Mo, téléchargement et décompression en une seconde) ; la décompression par l'explorateur de fichiers n'a pas été suivie (elle a été faite en commande). Le clonage avec Git n'est pas vérifié.

## 4. Ouvrir un terminal

Un terminal est une fenêtre dans laquelle on tape des commandes.

- Linux : ouvrez l'application « Terminal ».
- Windows : ouvrez « PowerShell » (menu Démarrer, tapez `PowerShell`).

Placez-vous ensuite dans le dossier du projet :

- Linux : `cd ~/Documents/transcription-bench` (adaptez le chemin).
- Windows : `cd $HOME\Documents\transcription-bench` (adaptez le chemin).

*Vous devez voir.* En tapant `ls` (Linux) ou `dir` (Windows), la liste contient `pyproject.toml`.

*Si ce n'est pas le cas.* Vous n'êtes pas dans le bon dossier : vérifiez le chemin avec l'explorateur de fichiers.

Vérification : non vérifié. Windows : non vérifié sur un poste Windows.

Les commandes du programme, dans les étapes qui suivent, sont identiques sous Linux et sous Windows : seul le terminal diffère.

## 5. Lancer l'application

*Faites ceci.* Dans le terminal, depuis le dossier du projet :

```sh
uv run --locked transcription-bench
```

La commande est la même sous Linux et sous Windows. Gardez ce terminal ouvert : c'est lui qui fait tourner l'application. La première fois, la préparation peut prendre un moment et télécharger des éléments.

*Vous devez voir.* Une ligne de ce type :

```
Interface disponible : http://127.0.0.1:8765
```

Ouvrez cette adresse dans votre navigateur. La page **Résultats** s'affiche : l'adresse racine (`/`) y mène directement. Le menu propose trois rubriques, dans cet ordre : **Résultats**, **Comparaisons** et **Historique**. La rubrique de la page où vous êtes est signalée dans le menu. Sans résultat, la page **Résultats** affiche : « Aucune transcription à regrouper par audio pour l'instant. Lancez une exécution avec la commande « run start » ; ses résultats apparaîtront ici. »

*Une seule instance à la fois.* La page web ne lance aucune action : installer un moteur, ajouter un modèle et lancer une transcription se font en tapant des commandes. L'application et les commandes ne peuvent pas travailler en même temps sur le même dossier de données : si vous tapez une commande pendant que l'application tourne, elle est refusée (voir le [dépannage](#13-dépannage)). Pour suivre les étapes suivantes, arrêtez l'application en appuyant sur `Ctrl+C` dans son terminal (étape 12) ; vous la relancerez à l'étape 10 pour consulter vos résultats.

*Si ce n'est pas le cas.* Voir « port déjà utilisé », « commande introuvable » et « la page ne s'ouvre pas » dans le [dépannage](#13-dépannage). Pour choisir un autre port : `uv run --locked transcription-bench --port 8080`.

Vérification : premier lancement sur une copie vierge vérifié sous Linux le 2026-11-13 : la ligne « Interface disponible » s'affiche et la page s'ouvre. La première fois, la préparation a demandé quelques secondes (les éléments nécessaires venaient du cache de la machine ; une machine neuve les télécharge, durée non mesurée). `uv` était déjà installé sur cette machine : son installation n'est pas vérifiée (étape 2). La navigation à trois rubriques (**Résultats**, **Comparaisons**, **Historique**) et les états vides actuels sont couverts par les tests automatiques du projet ; le parcours à froid du 13 novembre montrait six rubriques, supprimées depuis. La CI Windows a contrôlé la suite de tests, serveur compris, dernière fois le 2026-11-02 (voir [ci-windows.md](ci-windows.md)) ; le lancement en console sur un poste Windows n'est pas vérifié.

## 6. Déposer vos audios

Les fichiers ne s'envoient pas par une page : vous les copiez vous-même dans le dossier `data/audio` du projet (il est créé au premier lancement ou à la première commande).

*Faites ceci.*

1. Copiez un ou plusieurs audios dans le dossier `data/audio`, sous un nom simple, sans sous-dossier.
2. Dans le terminal (l'application doit être arrêtée, voir étape 5), tapez :

   ```sh
   uv run --locked transcription-bench audios list
   ```

*Vous devez voir.* Une ligne « Dossier d'entrée : … » avec le chemin du dossier, puis une ligne par fichier : son nom, son format, sa taille en octets, sa durée indicative, et le mot « lisible » si le fichier peut être décodé. Un fichier illisible apparaît avec son erreur, sans empêcher la liste des autres. Vos audios ne quittent pas l'ordinateur.

*Si ce n'est pas le cas.* Si la commande affiche « Aucun fichier audio dans le dossier d'entrée. », les fichiers ne sont pas au bon endroit. Pour un fichier signalé avec une erreur, voir « audio illisible » dans le [dépannage](#13-dépannage).

Vérification : le dépôt des fichiers par copie est vérifié sous Linux le 2026-11-13 (parcours d'alors, dans un navigateur via une page aujourd'hui retirée) ; la commande `audios list` est couverte par les tests automatiques du projet, sans parcours manuel en l'état. Windows : non vérifié sur un poste Windows.

## 7. Installer un moteur

Pour l'exemple de ce guide, il faut le moteur transcribe.cpp.

*Faites ceci.* Dans le terminal, depuis le dossier du projet :

1. Listez les moteurs pour repérer le vôtre :

   ```sh
   uv run --locked transcription-bench engines list
   ```

   La ligne qui nous intéresse est : « transcribe-cpp : transcribe.cpp (GGUF) — non installé ».

2. Installez-le :

   ```sh
   uv run --locked transcription-bench engines install transcribe-cpp
   ```

   Le déroulement s'écrit au fil de l'eau dans le terminal. Attendez la fin : la commande ne rend la main qu'une fois l'installation terminée.

*Vous devez voir.* À la fin, deux lignes de ce type :

```
Opération « installation » : terminée
Moteur transcribe-cpp : prêt
```

L'installation récupère des éléments sur Internet (ou dans le cache de l'outil de lancement, s'il les a déjà). Elle a pris environ une seconde ce jour-là, les éléments étant déjà dans le cache de la machine (mesure de l'ancien parcours par page web ; la durée de la commande n'est pas consignée) ; sur une machine neuve, elle télécharge et demande plus de temps (non mesuré). Pour revoir l'état, tapez à nouveau `engines list` : la ligne se termine alors par « prêt ».

*Si ce n'est pas le cas.* Si la dernière ligne affiche « échec », lisez la cause dans le journal d'installation :

```sh
uv run --locked transcription-bench engines log transcribe-cpp
```

Corrigez (par exemple rétablissez la connexion), puis relancez l'installation. Voir « moteur non prêt » dans le [dépannage](#13-dépannage).

Vérification : installation par la commande `engines install` vérifiée sous Linux le 2026-11-13, sur le PC de test : la roue du moteur était déjà dans le cache de la machine (aucun téléchargement réseau du moteur observé, durée de la commande non consignée). La CI Windows contrôle l'installation des trois moteurs depuis leurs verrous, dernière fois le 2026-11-13, sur ses propres machines, sans passer par les commandes du programme (voir [ci-windows.md](ci-windows.md)).

## 8. Ajouter et télécharger un modèle

Pour l'exemple, utilisez :

| Élément | Valeur |
|---|---|
| Identifiant Hugging Face | `handy-computer/whisper-large-v3-turbo-gguf` |
| Moteur | transcribe.cpp (GGUF) |
| Fichier à choisir | `whisper-large-v3-turbo-Q5_K_M.gguf` |
| Taille à télécharger | environ 620 Mo, soit 590,9 Mio affichés par l'outil (vérifié le 2026-11-13) |

« Hugging Face » est le site qui héberge ces modèles. La provenance et la licence de ce fichier sont consignées dans [licences-modeles.md](licences-modeles.md).

*Faites ceci.*

1. Vérifiez le dépôt, sans rien télécharger :

   ```sh
   uv run --locked transcription-bench models check handy-computer/whisper-large-v3-turbo-gguf --engine transcribe-cpp
   ```

   La commande lit la fiche du dépôt chez Hugging Face, puis affiche son verdict (la commande ne rend la main qu'à la fin ; l'ancien parcours par page mesurait environ 40 secondes, la durée de la commande n'est pas consignée).

2. Ce dépôt contient plusieurs variantes (une variante est une version du modèle dans un format ou une précision donnés) : la première vérification répond donc :

   ```
   Dépôt refusé (fichier-gguf-non-choisi) : dépôt à plusieurs fichiers GGUF : la variante de quantification à télécharger doit être choisie explicitement ; variantes proposées : …
   ```

   Ce n'est pas une erreur : c'est la façon normale de choisir. Refaites la commande en ajoutant l'option (un complément facultatif collé à la commande) `--file` suivi du nom du fichier :

   ```sh
   uv run --locked transcription-bench models check handy-computer/whisper-large-v3-turbo-gguf --engine transcribe-cpp --file whisper-large-v3-turbo-Q5_K_M.gguf
   ```

3. La commande doit maintenant répondre « Dépôt compatible : … », puis la révision résolue (la version précise retenue), la variante GGUF retenue, les fichiers à télécharger et leur taille totale : « Taille totale : 590,9 Mio ». Elle se termine par « Aucun poids n'a été téléchargé : vérification seulement. »

4. Téléchargez le modèle :

   ```sh
   uv run --locked transcription-bench models download handy-computer/whisper-large-v3-turbo-gguf --engine transcribe-cpp --file whisper-large-v3-turbo-Q5_K_M.gguf
   ```

   La commande vérifie à nouveau le dépôt (c'est son point de départ), affiche « Révision résolue : …, taille totale : 590,9 Mio », puis télécharge (environ 12 secondes en commande le 2026-11-13 ; l'ancien parcours par page mesurait environ 6 secondes). Le téléchargement ne commence qu'après votre commande, et un modèle interrompu n'est jamais proposé comme prêt.

5. Contrôlez le résultat :

   ```sh
   uv run --locked transcription-bench models list
   ```

*Vous devez voir.* Après le téléchargement, le modèle apparaît dans la liste : son identifiant, son moteur, sa famille, sa variante GGUF, sa taille, et surtout sa ligne « référence : transcribe-cpp/… », un identifiant local de la forme moteur/clé qui sert à l'étape 9.

*Supprimer un modèle.* La commande `models delete`, suivie du moteur et de la clé affichés par `models list`, supprime les fichiers locaux du modèle. La commande ne pose aucune question : le fait de la taper vaut confirmation. Les résultats déjà produits restent consultables.

*Si ce n'est pas le cas.* Voir « modèle refusé ou introuvable », « téléchargement interrompu » et « pas de connexion Internet » dans le [dépannage](#13-dépannage).

Autres modèles essayés avec succès par le projet (liste complète des licences : [licences-modeles.md](licences-modeles.md)) :

| Moteur | Identifiant | Taille indicative | Remarque |
|---|---|---|---|
| faster-whisper (CTranslate2) | `dropbox-dash/faster-whisper-large-v3-turbo` | environ 1,6 Go | essai Linux le 2026-11-02 ; CI Windows |
| Hugging Face Transformers | `openai/whisper-large-v3-turbo` | non mesurée | essai Linux le 2026-11-02 ; CI Windows |
| Hugging Face Transformers | `nvidia/parakeet-tdt-0.6b-v3` | non mesurée | essai Linux le 2026-11-02 ; CI Windows |
| transcribe.cpp (GGUF) | `handy-computer/Qwen3-ASR-0.6B-gguf` (fichier `Qwen3-ASR-0.6B-Q8_0.gguf`) | environ 850 Mo | essai Linux seulement (2026-11-03) |

Vérification : les commandes `models check` et `models download` ont été éprouvées en commande sur le PC de test Linux le 2026-11-13 : vérification de la variante `whisper-large-v3-turbo-Q5_K_M.gguf` parmi les cinq proposées, puis téléchargement des 590,9 Mio en environ 12 secondes ; le modèle était ensuite prêt (durée de la vérification non consignée). L'ancien parcours par page web, le même jour, mesurait environ 40 secondes par vérification, environ 50 secondes pour la variante et environ 6 secondes de téléchargement : ordre de grandeur de l'interface d'alors, repris dans le tableau du début, pas une mesure des commandes. `models list` et `models delete` sont couvertes par les tests automatiques du projet (`models delete` a aussi été éprouvée en commande le 2026-11-13). La CI Windows a aussi vérifié puis téléchargé ce modèle à révision figée le 2026-11-13, sans passer par les commandes du programme (voir [validation-linux.md](validation-linux.md) et [ci-windows.md](ci-windows.md)).

## 9. Lancer une transcription

Une exécution est la transcription d'un ou plusieurs audios avec un modèle donné.

*Faites ceci.*

1. Présentez la préparation d'une exécution (aucun lancement, aucun téléchargement) :

   ```sh
   uv run --locked transcription-bench run options
   ```

   La commande affiche les modèles proposables avec leur référence (l'identifiant local de l'étape 8, de la forme `transcribe-cpp/<clé>`), les audios proposables, le nombre de threads par défaut (les threads sont des calculs menés en parallèle par le processeur ; la valeur par défaut convient pour commencer) et les réglages propres au modèle avec leurs valeurs par défaut. Notez la référence de votre modèle.

2. Lancez l'exécution en donnant la référence du modèle et le nom de votre audio :

   ```sh
   uv run --locked transcription-bench run start --model transcribe-cpp/<clé> --audio essai.wav
   ```

   Remplacez `transcribe-cpp/<clé>` par la référence notée, et `essai.wav` par le nom de votre fichier.

3. Suivez l'avancement : le déroulement s'écrit au fil de l'eau dans le terminal. La commande ne rend la main qu'à la fin ; une seule exécution tourne à la fois.

*Vous devez voir.* À la fin, des lignes de ce type :

```
Opération « exécution » : terminée
Résultat enregistré : <identifiant>
Audios :
  essai.wav : traité
```

L'identifiant du résultat (noté entre les mots « Résultat enregistré : » et la ligne des audios) sert à lire le résultat à l'étape suivante. Le temps nécessaire dépend de la longueur de l'audio et de votre ordinateur (l'ancien parcours par page mesurait environ 6 secondes pour un audio de 10 secondes le 2026-11-13 ; la durée de la commande n'est pas consignée).

*Plusieurs audios.* Répétez l'option `--audio` : ils forment un lot, traité audio après audio, dans l'ordre exact où vous les avez écrits. Exemple : `--audio essai.wav --audio second.wav`. Chaque résultat est enregistré dès qu'il est produit : une interruption conserve les audios déjà transcrits.

*Choix avancés, facultatifs.* L'option `--threads` fixe le nombre de threads ; l'option `--setting NOM=VALEUR` change un réglage affiché par `run options` (le nom et la valeur acceptée y sont indiqués). Sans ces options, les valeurs par défaut s'appliquent.

*Contrôler sans lancer.* La commande `run check` accepte les mêmes options que `run start` et se contente de vérifier la demande : elle affiche « Demande valide : aucune exécution lancée, aucun résultat écrit. »

*Arrêter une exécution.* Appuyez sur `Ctrl+C` dans le terminal de la commande : la commande affiche « arrêt demandé par signal : clôture de l'opération en cours. », l'exécution est marquée interrompue et les résultats déjà écrits sont conservés.

*Si ce n'est pas le cas.* Si la préparation affiche « Aucun modèle proposable. » ou « Aucun audio lisible dans le dossier d'entrée. », retournez aux étapes 7, 8 et 6. Si le lancement est refusé avec « moteur non prêt (état : …) », retournez à l'étape 7. Voir « texte vide ou exécution interrompue » dans le [dépannage](#13-dépannage).

Vérification : les commandes `run check` et `run start` ont été éprouvées en commande sous Linux le 2026-11-13 sur le PC de test (moteur transcribe.cpp, famille Whisper) : une exécution complète à réglages par défaut (durée non consignée). L'ancien parcours par page web, le même jour, mesurait deux exécutions d'un audio de 10 secondes en 5,8 et 5,9 secondes : ordre de grandeur de l'interface d'alors, pas une mesure des commandes. Les quatre combinaisons de moteurs ont aussi tourné le 2026-11-02 (par les formulaires de l'interface d'alors) et dans la CI Windows, dernière fois le 2026-11-13. Les refus (modèle non prêt, audio illisible, réglage inapplicable, seconde opération pendant la première) sont couverts par les tests automatiques du projet.

## 10. Lire un résultat

Deux moyens de lire un résultat : dans le terminal, ou dans le navigateur, en relançant l'application.

*Faites ceci.*

1. Dans le terminal, tapez :

   ```sh
   uv run --locked transcription-bench results show <identifiant>
   ```

   en remplaçant `<identifiant>` par celui noté à l'étape 9. La commande affiche l'état de l'exécution, le modèle, les mesures, puis la transcription complète, audio par audio.

2. Pour une lecture confortable, relancez l'application (étape 5) et ouvrez la page **Résultats**. Les essais sont regroupés par audio : le nom du fichier et sa durée figurent en titre de chaque groupe. Le tri par défaut présente les essais les plus récents en premier dans chaque groupe ; les liens Plus rapides, Moins de RAM et CPU le moins occupé changent l'ordre des essais de chaque groupe, jamais l'ordre des audios. Cliquez sur le nom d'un modèle pour ouvrir le texte et le détail de cet essai : dans un lot, le lien ouvre directement l'audio concerné. Pour comprendre les repères, ouvrez **Comprendre les indicateurs** depuis la page.

*Vous devez voir.* Une ligne par essai : le modèle (et sa variante GGUF si elle est consignée), puis **Transcription**, **RAM moteur** et **CPU moteur**, le moteur et la date courte. Si les durées décodées d'un audio divergent, le groupe le signale et chaque ligne donne la durée de son propre essai ; deux fichiers de même nom se distinguent par leur empreinte courte (l'empreinte est un identifiant unique calculé à partir du contenu du fichier). Les états restent visibles sur la ligne : résultat en erreur, exécution interrompue, marques. Les mesures simulées sont classées à part, sous leur propre titre. Les mesures dépendent de votre ordinateur : elles ne disent rien de la qualité du texte ni des performances d'un autre poste.

*Si ce n'est pas le cas.* Voir « texte vide ou exécution interrompue » dans le [dépannage](#13-dépannage) ; si la page elle-même ne s'affiche pas, voir « la page ne s'ouvre pas ».

Une marque **SYNTHÉTIQUE** seule signale un audio ou un texte de test : elle ne dit rien du moteur ni des mesures. Les marques **FACTICE** ou **MESURES SIMULÉES** signalent, elles, un moteur factice (un moteur de substitution utilisé par les tests) ou des valeurs simulées.

*Contexte de l'ordinateur.* Le détail d'un essai et la comparaison sélectionnée proposent un bloc repliable **Contexte de l'ordinateur**, séparé des indicateurs du moteur ; dans le détail d'un essai, il porte le titre « Relevés système de cette exécution ». Il donne le CPU total moyen pendant la transcription, la RAM disponible après l'audio et la RAM disponible après le chargement du modèle. Le CPU total inclut les autres programmes de l'ordinateur, pas seulement celui du moteur. La RAM disponible est une estimation du système à un instant donné : ce n'est ni le minimum resté pendant la transcription, ni la part consommée par le moteur. Les pourcentages reposent sur les ressources visibles par le système : sur un ordinateur partagé ou virtualisé, ils ne décrivent pas une capacité matérielle garantie. Ces valeurs décrivent cet essai, sur cet ordinateur : elles ne disent rien du modèle, ne garantissent ni fluidité ni confort d'usage et ne prouvent rien pour un autre ordinateur. Quand un relevé manque, le bloc affiche « non mesuré ». Le lien **Comprendre les indicateurs** détaille ces limites. La commande `results show` affiche les mêmes relevés dans le terminal, sous « Contexte de l'ordinateur : ».

*Historique.* Tous les essais, y compris les échecs, les interruptions et les résultats non interprétables, restent dans la page **Historique** ; le lien *historique complet des exécutions* de la page **Résultats** y mène. Chaque exécution exploitable y ouvre son détail. Dans ce détail, le texte complet vient après le modèle et les mesures ; les mesures détaillées, les segments et les informations de l'exécution suivent dans des blocs que vous pouvez ouvrir. La commande `results history` donne la même liste dans le terminal.

Relisez toujours le texte en écoutant l'audio. Une phrase fluide peut être fausse.

Vérification : consultation dans un navigateur vérifiée sous Linux le 2026-11-13, sur les pages conservées depuis : texte affiché et lisible, mesures du moteur et bloc **Contexte de l'ordinateur** présents avec les valeurs réelles de l'essai. Le contenu de ces pages n'a pas changé depuis ; la navigation à trois rubriques et les états vides actuels sont couverts par les tests automatiques du projet. La commande `results show` est couverte par les tests automatiques, sans parcours manuel en l'état. Windows : non vérifié sur un poste ; la CI contrôle la suite de tests.

## 11. Comparer deux résultats

On compare deux transcriptions d'un même audio, obtenues avec deux modèles (ou deux exécutions du même modèle).

*Faites ceci.*

1. Lancez une seconde exécution (étape 9) sur le même audio, avec un autre modèle ou le même. L'application doit être arrêtée pendant ce temps ; aucun second téléchargement n'a lieu avec le même modèle.
2. Relancez l'application (étape 5) et ouvrez la page **Comparaisons** (ou, dans **Résultats**, le lien **Comparer**).
3. Dans le groupe de votre audio, cochez les cases à côté des noms des modèles, puis cliquez sur **Comparer les transcriptions sélectionnées**. Changer le classement conserve les cases cochées ; une comparaison accepte jusqu'à 64 sélections d'un même audio.

*Vous devez voir.* La durée audio commune dans l'en-tête, puis une carte par transcription : modèle, temps de transcription, RAM, CPU, moteur et date, suivis du texte entier. Si les durées consignées divergent, chaque carte indique la sienne. La page propose par défaut le tri « Plus rapides » (la page **Résultats**, elle, présente d'abord « Plus récents ») ; changer de tri conserve les cases cochées. La meilleure valeur observée de temps et de mémoire est signalée près de sa mesure par un libellé court (« meilleur temps », « meilleure RAM »), égalités comprises, sans phrase de synthèse désignant un vainqueur ; quand deux durées s'affichent arrondies à la même seconde (par exemple « 5 s » toutes les deux), la distinction suit les valeurs exactes, visibles dans **Ce qui diffère** ; le CPU ne reçoit aucune distinction, et les mesures simulées ou partielles non plus. Les blocs **Ce qui diffère** puis **Toutes les mesures et informations** donnent les valeurs distinctes, puis l'ensemble des mesures et métadonnées, y compris le rapport **RTF (durée de transcription / durée décodée)** et son « repère d'objectif 2, non bloquant ». Le lien **Comprendre les indicateurs** explique les calculs et les limites.

*Comparer dans le terminal.* La commande `results list` affiche l'empreinte de chaque groupe d'audio, puis la sélection de chaque essai, sous la forme `identifiant:ordre` ; la commande `compare`, suivie de l'empreinte puis des sélections, affiche la même comparaison dans le terminal :

```sh
uv run --locked transcription-bench compare <empreinte> <identifiant>:<ordre> <identifiant>:<ordre>
```

*Si ce n'est pas le cas.* Vérifiez que deux essais terminés du même audio existent (étapes 9 et 10) ; pour un texte vide ou une exécution interrompue, voir le [dépannage](#13-dépannage).

*Ce que cela ne dit pas.* Le texte le plus fluide n'est pas forcément le plus exact, et l'outil ne désigne aucun « meilleur » modèle. La comparaison sert à repérer des différences ; c'est à vous de juger, en réécoutant l'audio.

Vérification : comparaison de deux exécutions du même modèle sur le même audio vérifiée sous Linux le 2026-11-13 dans un navigateur (la seconde exécution n'a demandé aucun second téléchargement) ; comparaison plus ancienne de quatre résultats d'un même audio le 2026-11-02, par l'interface d'alors. La page conservée n'a pas changé depuis ; la commande `compare` est couverte par les tests automatiques du projet, sans parcours manuel en l'état. Windows : non vérifié sur un poste ; la CI contrôle la suite de tests.

## 12. Arrêter et relancer

- Arrêter l'application : dans le terminal où elle tourne, appuyez sur `Ctrl+C`. Le message `Arrêt du serveur.` s'affiche. Attendez la fin avant de fermer le terminal. Les résultats déjà obtenus restent consultables ; l'application ne lance aucune opération, il n'y a rien d'autre à terminer.
- Arrêter une commande longue (exécution, installation, téléchargement) : appuyez sur `Ctrl+C` dans le terminal de la commande. Elle affiche « arrêt demandé par signal : clôture de l'opération en cours. » puis s'arrête : l'exécution est marquée interrompue, les résultats déjà écrits sont conservés, une installation ou un téléchargement interrompu reste non prêt. Un second `Ctrl+C` pendant l'arrêt est ignoré. Un téléchargement n'est pas annulable : si le transfert tarde à se terminer, la commande le signale et le verrou reste tenu jusqu'à la fin réelle du processus.
- Relancer plus tard : rouvrez un terminal dans le dossier du projet et retapez la commande de lancement (étape 5). Vos audios, moteurs, modèles et résultats sont conservés dans le dossier `data/`.

Le programme répond aussi par un code de sortie (un nombre que le terminal ou un script peut lire) : `0` quand tout s'est bien passé, `1` pour un échec, `2` pour un refus, `3` pour un arrêt demandé par `Ctrl+C` ou un signal équivalent.

*Si ce n'est pas le cas.* Si le message ne s'affiche pas, attendez la fin du travail en cours. Si vous fermez le terminal sans attendre, ou si l'ordinateur s'éteint brutalement pendant une commande, l'exécution en cours sera marquée « abandonnée » au prochain démarrage (voir le [dépannage](#13-dépannage)).

Vérification : le message « Arrêt du serveur. » est vérifié sous Linux le 2026-11-13, par le signal d'interruption qu'envoie Ctrl+C (le clavier physique n'a pas été observé). L'arrêt d'une commande en cours a été vérifié le même jour par le signal SIGTERM (code `3`, verrou libéré) ; Ctrl+C physique sur une commande n'a pas été observé. L'arrêt pendant une exécution réelle, puis le redémarrage avec conservation des résultats, sont vérifiés sous Linux le 2026-11-02 (version antérieure de l'interface). Sous Windows, Ctrl+C n'est pas vérifié sur un poste réel ; l'annulation d'un job CI n'est pas un Ctrl+C.

## 13. Dépannage

Pour chaque cas : ce que vous voyez, la cause probable, que faire.

| Ce que vous voyez | Cause probable | Que faire |
|---|---|---|
| Le terminal affiche « impossible d'écouter sur http://127.0.0.1:8765 » et « Vérifiez qu'aucun autre programme n'utilise ce port » | Une autre application (ou une autre copie de ce programme) utilise déjà ce port | Fermez l'autre programme, ou relancez avec `uv run --locked transcription-bench --port 8080` |
| « port invalide » | Le port donné n'est pas un nombre entre 1024 et 65535 | Choisissez un port dans cet intervalle |
| Un message du système signale que la commande est introuvable ou qu'elle n'est pas reconnue (message système non relevé lors d'un essai ; la formulation dépend de votre système) | L'outil de lancement n'est pas installé, ou le terminal n'a pas été rouvert après son installation | Refaites l'étape 2, fermez puis rouvrez le terminal |
| La page ne s'ouvre pas dans le navigateur | Le programme n'est pas lancé (ou s'est arrêté sur une erreur après avoir affiché « Interface disponible », par exemple un port occupé), ou l'adresse est différente de celle affichée | Lisez les dernières lignes du terminal, recopiez l'adresse exacte (avec le bon port) ; n'utilisez pas une autre adresse de l'ordinateur |
| « Requête refusée : adresse invalide. » | L'adresse tapée n'est pas celle affichée par le terminal (`http://127.0.0.1:` ou `http://localhost:` suivi du port) | Rouvrez l'adresse affichée par le terminal et rechargez la page |
| « une autre instance utilise déjà ce dossier de données » | L'application ou une autre commande tourne déjà : une seule instance à la fois | Attendez la fin de la commande en cours, ou arrêtez l'application (`Ctrl+C` dans son terminal), puis retapez votre commande |
| « moteur non prêt (état : …) » au lancement, ou moteur à l'état « échec » dans `engines list` | Le moteur n'est pas installé, ou son installation a échoué | Relisez `engines list`, la cause dans `engines log <moteur>` (par exemple pas de connexion), corrigez, puis relancez `engines install <moteur>` |
| « Dépôt refusé (fichier-gguf-non-choisi) » à la commande `models check` ou `models download` | Ce n'est pas une erreur : le dépôt propose plusieurs variantes et il faut en choisir une | Refaites la commande avec l'option `--file` suivie du nom du fichier voulu (étape 8) |
| « Dépôt refusé » avec un autre motif | L'identifiant est faux, le modèle n'est pas pris en charge par ce moteur ou il manque des fichiers | Vérifiez l'identifiant (aucune faute, pas d'espace) ; la commande affiche le motif du refus, et sa sortie `--json` cite parfois un moteur possible |
| Téléchargement interrompu, ou modèle absent de `models list` | Connexion coupée, commande arrêtée, ou disque plein | Relancez `models download` ; un modèle incomplet n'est jamais proposé comme prêt ; libérez de la place si le disque est plein |
| Pas de connexion Internet | Réseau coupé | Reconnectez-vous : l'installation du moteur et la vérification ou le téléchargement d'un modèle en ont besoin ; une fois tout installé, une transcription n'en a plus besoin |
| Un audio apparaît avec un message d'erreur dans `audios list` | Fichier abîmé, vide, ou format non pris en charge | Vérifiez que le format est wav, mp3, m4a, ogg, opus ou flac ; réexportez le fichier ; renommez-le simplement, sans sous-dossier |
| Texte vide ou exécution « interrompue » ou « échouée » | Audio sans parole décodable, arrêt demandé (`Ctrl+C`), terminal fermé pendant le travail | Relancez une exécution ; l'état de chaque exécution se lit dans `results history` ou dans la page **Historique** |
| Exécution marquée « abandonnée » | L'ordinateur a été éteint ou le terminal fermé brutalement pendant le travail | Relancez une exécution ; les audios sans résultat sont signalés non traités |
| La commande affiche « Aucun modèle proposable. » | Aucun modèle prêt : moteur non installé ou modèle non téléchargé | Faites les étapes 7 et 8, puis relancez `run options` |

## Glossaire

- Audio : un fichier d'enregistrement (voix) à transcrire.
- CI : contrôles automatiques exécutés sur des machines Windows et Linux de test, sans rapport avec votre ordinateur.
- Code de sortie : le nombre que le programme renvoie au terminal quand il se termine ; `0` indique que tout s'est bien passé, `1` un échec, `2` un refus, `3` un arrêt demandé.
- Commande : une instruction tapée dans le terminal ; elle agit puis rend la main.
- CPU (processeur) : la puce de l'ordinateur qui effectue les calculs ; ses « cœurs » sont ses unités de calcul.
- RAM (mémoire vive) : l'espace de travail rapide de l'ordinateur, où sont chargés les programmes en cours.
- Mo, Go, Mio, Gio : unités de taille des fichiers. Un mégaoctet (Mo) vaut un million d'octets, un gigaoctet (Go) mille Mo ; un mébioctet (Mio) vaut 1 048 576 octets, un Gio mille vingt-quatre Mio. Les sites de modèles annoncent souvent des Mo ou des Go ; l'outil affiche des Mio ou des Gio pour les modèles, et des octets dans `audios list`.
- Empreinte SHA-256 : un identifiant unique calculé à partir du contenu d'un fichier ; deux audios identiques ont la même empreinte, abrégée en « empreinte courte » à l'affichage. Elle permet de regrouper les transcriptions d'un même audio.
- Git : outil qui télécharge un projet et suit son historique ; « cloner » un projet en récupère une copie.
- JavaScript : langage intégré au navigateur, qui rend certaines pages web réactives ; les pages de l'outil n'en utilisent aucune, elles fonctionnent de la même façon quel que soit votre navigateur.
- Lot : plusieurs audios traités par une même exécution, l'un après l'autre, dans l'ordre où leurs noms ont été donnés à la commande.
- Mesures simulées : valeurs produites par le moteur factice ou de test, jamais représentatives d'un ordinateur réel. Une marque synthétique seule ne signifie pas que les mesures sont simulées.
- Moteur factice : moteur de substitution utilisé par les tests du projet ; il produit des transcriptions et des mesures simulées, sans reconnaître la parole.
- Option : un complément facultatif collé à une commande (par exemple `--file` suivi d'un nom de fichier) ; il précise ou limite ce que la commande fait.
- Variante : version du fichier d'un même modèle, dans un format ou une précision donnés (par exemple Q5_K_M) ; pour un modèle GGUF, c'est le fichier à choisir.
- Exécution : une transcription d'un ou plusieurs audios avec un modèle donné.
- Hors ligne : sans connexion Internet. Une fois le moteur et le modèle installés, la transcription se fait hors ligne ; les autres cas où Internet est utilisé sont listés dans le tableau de la section « Ce que fait l'outil, et ce qu'il envoie sur Internet ».
- Hugging Face : site qui héberge de nombreux modèles de reconnaissance de la parole.
- Modèle : le fichier (volumineux) qui contient ce que la machine a appris pour transcrire la voix.
- Moteur : le programme qui fait tourner un modèle.
- Dépôt, révision : sur Hugging Face, un dépôt est la page d'un modèle et une révision une version précise de ce modèle.
- Référence d'un modèle : l'identifiant local d'un modèle prêt, de la forme moteur/clé, affiché par `models list` et à donner à l'option `--model` pour lancer une exécution.
- GGUF : format de fichier de modèle utilisé par le moteur transcribe.cpp.
- Port : numéro qui termine l'adresse locale de l'application (8765 par défaut).
- Python : langage de programmation dans lequel l'outil est écrit ; l'outil de lancement le prépare tout seul.
- Terminal : fenêtre dans laquelle on tape des commandes (Terminal sous Linux, PowerShell sous Windows).
- Threads : nombre de calculs menés en parallèle par le processeur ; la valeur proposée par défaut convient pour commencer.
- RTF : rapport entre la durée de transcription et la durée de l'audio ; il est affiché avec un « repère d'objectif 2, non bloquant », qui n'est ni un seuil ni une note de qualité.

## Pour aller plus loin

- Détails du fonctionnement, de l'arrêt, des limites et de la CI : [documentation technique](technique.md).
- Pilotage avancé du programme en commande (sortie JSON, codes de sortie, signaux) : la section « Utiliser le programme en commande » de la [documentation technique](technique.md#utiliser-le-programme-en-commande-agents).
- Licences des modèles et des outils : [licences-modeles.md](licences-modeles.md).
- Comment les validations ont été menées : [validation-linux.md](validation-linux.md) et [ci-windows.md](ci-windows.md).
