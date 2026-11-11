# Guide utilisateur

Ce guide vous mène, pas à pas, de « rien d'installé » à une première transcription lue, puis à la comparaison de deux résultats. Il s'adresse à une personne à l'aise avec un ordinateur, sans connaissance en programmation, mais prête à copier-coller quelques commandes.

> *Important.* Cet outil est un prototype de comparaison. Il n'est pas validé cliniquement. Une transcription qui se lit bien peut contenir des erreurs : ne l'utilisez jamais comme un texte médical exact sans relecture humaine.

*Niveau de vérification de ce guide.* Le parcours complet « à froid » (suivre ce guide sur une copie vierge, de l'installation à la comparaison) n'a pas encore été fait : aucune procédure n'est présentée comme éprouvée à froid. Chaque étape porte son niveau réel : « vérifié sous Linux le <date> », d'après les validations du projet ; « contrôlé par la CI Windows » (contrôles automatiques sur les machines de test de GitHub, sans rapport avec votre ordinateur), en précisant ce qui a été contrôlé ; ou « non vérifié ». Sous Windows, la CI a contrôlé la suite de tests, l'installation des trois moteurs (aux versions exactes prévues par le projet) et des transcriptions courtes ; l'installeur de `uv`, le lancement en console et Ctrl+C restent « non vérifié sur un poste Windows ». Les validations Linux des 2 et 3 novembre 2026, comme les runs de la CI Windows, datent d'avant la refonte de l'interface des 7 et 11 novembre 2026 : elles ont porté sur une version antérieure de l'interface, sans navigateur ni contrôle visuel. L'interface actuelle est couverte par les tests automatiques et par des observations dans un navigateur, sur des données factices, sur le serveur de développement et en thème clair seulement. Les dates et le détail de chaque validation sont dans [validation-linux.md](validation-linux.md) et [ci-windows.md](ci-windows.md).

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
| Obtention du projet (étape 3) | récupérer les fichiers du projet | non mesuré |
| Premier lancement (étape 5) | l'outil de lancement peut télécharger lui-même Python et les éléments dont le programme a besoin ; à confirmer au premier parcours à froid | non mesuré |
| Installation d'un moteur (étape 7) | récupérer les éléments du moteur | non mesuré |
| Vérification d'un modèle (étape 8) | lire la fiche du modèle chez Hugging Face | quelques fichiers de description |
| Téléchargement d'un modèle (étape 8) | récupérer le modèle | environ 620 Mo pour l'exemple de ce guide |

Sauf le premier lancement, rien de tout cela ne se déclenche sans que vous cliquiez ou tapiez une commande. La durée de chaque opération dépend de votre ordinateur et de votre connexion : elle n'a pas été mesurée pour ce guide.

## 1. Ce qu'il faut avoir

- Un ordinateur sous Linux ou Windows (64 bits). Pas de carte graphique nécessaire : l'outil n'utilise que le processeur (le CPU, la puce qui effectue les calculs de l'ordinateur). macOS n'est pas pris en charge.
- De la place sur le disque : l'exemple de ce guide demande environ 620 Mo pour le modèle, plus le moteur et ses éléments (non mesuré). Prévoyez plusieurs Go libres.
- Un navigateur récent. Selon la documentation de la feuille de style utilisée, il faut au moins Chrome ou Edge 111, Firefox 121 ou Safari 16.2 ; avec un navigateur plus ancien les pages restent lisibles, avec des couleurs plus simples (non vérifié ici).
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

Vérification : non vérifié. Ni l'archive ZIP ni le clonage n'ont été suivis.

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

Ouvrez cette adresse dans votre navigateur. La page **Résultats** s'affiche : l'adresse racine (`/`) y mène directement. Le menu propose six rubriques, dans cet ordre : **Résultats**, **Comparaisons**, **Exécutions**, **Modèles**, **Moteurs** et **Audios**. La rubrique de la page où vous êtes est signalée dans le menu.

*Si ce n'est pas le cas.* Voir « port déjà utilisé », « commande introuvable » et « la page ne s'ouvre pas » dans le [dépannage](#13-dépannage). Pour choisir un autre port : `uv run --locked transcription-bench --port 8080`.

Vérification : vérifié sous Linux le 2026-11-02 sur une version antérieure de l'interface, par un client HTTP automatisé, sans navigateur (lancement du serveur et parcours des pages sur un PC de test, avec `uv` déjà installé : ce n'est pas une installation vierge). L'interface actuelle est couverte par les tests automatiques et par une observation dans un navigateur, sur des données factices (voir la note « Niveau de vérification de ce guide »). La CI Windows a contrôlé la suite de tests, serveur compris (run 41472430238, commit d9ee207, le 2026-11-02, avant la refonte de l'interface) ; le lancement en console sur un poste Windows n'est pas vérifié.

## 6. Déposer vos audios

Cette page ne permet pas d'envoyer des fichiers : vous les copiez vous-même dans le dossier `data/audio` du projet (il est créé au premier lancement).

*Faites ceci.*

1. Copiez un ou plusieurs audios dans le dossier `data/audio`, sous un nom simple, sans sous-dossier.
2. Dans le navigateur, ouvrez la page **Audios** puis cliquez sur **Actualiser**.

*Vous devez voir.* Chaque fichier est listé avec son format, sa taille en Mio ou Gio (unités de taille de fichiers ; voir le glossaire) et une durée indicative ; la colonne **Lecture** indique « lisible ». Les tailles exactes en octets restent dans le détail « Tailles exactes des fichiers et dossier d'entrée ». Vos audios ne quittent pas l'ordinateur.

*Si ce n'est pas le cas.* Voir « audio illisible » dans le [dépannage](#13-dépannage).

Vérification : page vérifiée sous Linux le 2026-11-02, sur une version antérieure de l'interface, sans navigateur, avec des audios synthétiques déjà en place. La copie de vos fichiers dans `data/audio` n'a pas été suivie ; l'interface actuelle n'a été vue que sur des données factices (voir la note « Niveau de vérification de ce guide »). Windows : non vérifié sur un poste Windows.

## 7. Installer un moteur

Pour l'exemple de ce guide, il faut le moteur transcribe.cpp.

*Faites ceci.*

1. Ouvrez la page **Moteurs**.
2. Repérez la ligne « transcribe.cpp (GGUF) » dont l'état est « non installé ».
3. Cliquez sur **Installer ce moteur**, puis suivez l'avancement dans **Exécutions**, section **Opération longue** (ou **Consulter le journal d'installation**).

*Vous devez voir.* À la fin, l'état de « transcribe.cpp (GGUF) » devient « prêt ». L'installation télécharge des éléments : sa durée et sa taille n'ont pas été mesurées pour ce guide.

*Si ce n'est pas le cas.* Voir « moteur non prêt » dans le [dépannage](#13-dépannage).

Vérification : non vérifiée, même sous Linux : l'installation par la page **Moteurs** n'a pas été suivie (les validations Linux partaient de moteurs déjà préparés). La CI Windows a contrôlé le 2026-11-02 l'installation des trois moteurs (aux versions exactes prévues par le projet) puis un contrôle de démarrage (run 41477235301), sur ses propres machines, sans passer par la page.

## 8. Ajouter et télécharger un modèle

Pour l'exemple, utilisez :

| Élément | Valeur |
|---|---|
| Identifiant Hugging Face | `handy-computer/whisper-large-v3-turbo-gguf` |
| Moteur | transcribe.cpp (GGUF) |
| Fichier à choisir | `whisper-large-v3-turbo-Q5_K_M.gguf` |
| Taille à télécharger | environ 620 Mo (valeur indicative, non vérifiée à froid ; la page affiche la taille en Mio ou Gio après la vérification, avant tout téléchargement) |

« Hugging Face » est le site qui héberge ces modèles. La provenance et la licence de ce fichier sont consignées dans [licences-modeles.md](licences-modeles.md).

*Faites ceci.*

1. Ouvrez la page **Modèles**. La liste **Modèles locaux prêts** vient en premier ; juste après, le panneau replié **Ajouter un modèle** contient le formulaire d'ajout. Ouvrez-le : l'ouvrir ne vérifie aucun dépôt et ne télécharge rien.
2. Dans **Vérifier un dépôt**, saisissez l'identifiant ci-dessus dans **Identifiant Hugging Face**, choisissez « transcribe.cpp (GGUF) » dans **Moteur installé**, laissez **Révision facultative** vide.
3. Cliquez sur **Vérifier la compatibilité sans télécharger** : cette étape lit seulement la fiche du dépôt, sans télécharger de poids. La page rouvre le panneau **Ajouter un modèle** et y affiche le résultat. Si plusieurs variantes (une variante est une version du modèle dans un format ou une précision donnés) sont proposées, cliquez sur le bouton qui porte le nom `whisper-large-v3-turbo-Q5_K_M.gguf` (il commence par « Vérifier avec »).
4. Quand la page indique « Dépôt compatible », contrôlez la taille annoncée sous **Taille à télécharger**, en Mio ou Gio. Les valeurs exactes en octets restent dans le détail « Fichiers du modèle et identifiants ». Cliquez ensuite sur **Télécharger ce modèle à la révision vérifiée** : le téléchargement ne commence qu'après ce clic. Suivez l'avancement dans **Exécutions**, section **Opération longue**.

*Vous devez voir.* Le panneau **Ajouter un modèle** reste ouvert tant qu'une vérification a un résultat, puis le modèle apparaît dans **Modèles locaux prêts**.

*Utiliser un modèle prêt.* Chaque modèle de la liste propose **Utiliser** : la page **Exécutions** s'ouvre avec ce modèle déjà choisi, prête à préparer une exécution.

*Supprimer un modèle.* Le détail « Révision, fichiers et suppression » de chaque modèle contient **Supprimer ce modèle local**. Ce bouton reste indisponible pendant une opération ou après un arrêt du serveur, avec le motif affiché juste au-dessus ; la suppression retire les fichiers locaux et les résultats déjà produits restent consultables.

*Si ce n'est pas le cas.* Voir « modèle refusé ou introuvable », « téléchargement interrompu » et « pas de connexion Internet » dans le [dépannage](#13-dépannage).

Autres modèles essayés avec succès par le projet (liste complète des licences : [licences-modeles.md](licences-modeles.md)) :

| Moteur | Identifiant | Taille indicative | Remarque |
|---|---|---|---|
| faster-whisper (CTranslate2) | `dropbox-dash/faster-whisper-large-v3-turbo` | environ 1,6 Go | essai Linux le 2026-11-02 ; CI Windows |
| Hugging Face Transformers | `openai/whisper-large-v3-turbo` | non mesurée | essai Linux le 2026-11-02 ; CI Windows |
| Hugging Face Transformers | `nvidia/parakeet-tdt-0.6b-v3` | non mesurée | essai Linux le 2026-11-02 ; CI Windows |
| transcribe.cpp (GGUF) | `handy-computer/Qwen3-ASR-0.6B-gguf` (fichier `Qwen3-ASR-0.6B-Q8_0.gguf`) | environ 850 Mo | essai Linux seulement (2026-11-03) |

Vérification : exécution de ce modèle vérifiée sous Linux le 2026-11-02 et par la CI Windows le même jour (voir [validation-linux.md](validation-linux.md) et [ci-windows.md](ci-windows.md)) ; dans les deux cas sur une version antérieure de l'interface, et sous Linux avec des ressources préparées par le projet. La CI a aussi vérifié puis téléchargé ce modèle, à révision figée. La page **Modèles** n'a été suivie sous Linux que le 2026-11-03, sur une version antérieure de l'interface, par les formulaires HTTP et pour un autre modèle : l'ajout de ce modèle par la page n'est pas vérifié, ni sous Windows.

## 9. Lancer une transcription

*Faites ceci.*

1. Ouvrez la page **Exécutions**, section **Préparation d'une exécution**. Un seul panneau présente **Modèle**, **Audio** et **Moteur**, puis les actions ; un modèle exécutable et un audio lisible y sont déjà choisis.
2. Choisissez votre modèle dans **Modèle** et votre fichier dans **Audio**. Dans le cas courant, un seul audio est proposé. Pour traiter plusieurs audios, ouvrez **Plusieurs audios, dans cet ordre (facultatif)** et cochez-les : ils forment un lot, traité audio après audio dans l'ordre de cette liste (le même ordre est rappelé dans la préparation appliquée). Si vous changez un choix, la préparation se met à jour automatiquement, sans rien lancer. Les réglages avancés encore applicables sont conservés ; si la famille du modèle change, les autres reviennent à leurs valeurs par défaut et la page le signale.
3. Vérifiez la ligne **Préparation appliquée** : elle nomme le modèle, le moteur et les audios qui seront réellement lancés. Les **Réglages avancés (facultatif)**, dont **Threads demandés** (les threads sont des calculs menés en parallèle par le processeur), restent fermés ; leurs valeurs par défaut suffisent.
4. Cliquez sur **Lancer l'exécution**, placé avant les réglages avancés (le bouton **Vérifier la demande (aucun lancement)** sert seulement à contrôler la demande).
5. Suivez l'avancement dans **Exécutions**, section **Opération longue** : l'état se met à jour automatiquement toutes les 3 secondes tant que l'opération est active. Si le suivi automatique s'interrompt, le lien **Actualiser** recharge l'état ; le journal technique reste replié et s'ouvre sur demande.

*Remarque.* Sans JavaScript (le langage qui rend les pages réactives dans le navigateur), la mise à jour des choix n'est pas automatique : le bouton **Appliquer les choix** recharge la préparation, sans rien lancer. Les réglages saisis reviennent alors à leurs valeurs par défaut.

*Vous devez voir.* L'état passe à « en cours », puis à « terminée ». Une seule transcription tourne à la fois. Le temps nécessaire dépend de la longueur de l'audio et de votre ordinateur (non mesuré pour ce guide).

*Si ce n'est pas le cas.* Si la page affiche **Aucun modèle exécutable** ou **Aucun audio lisible**, son explication indique la page à ouvrir : **Modèles** pour un modèle prêt, **Audios** pour un fichier lisible. Si un choix a expiré (modèle supprimé, audio déplacé), un message le signale : les choix valides restent affichés, les autres reviennent aux valeurs par défaut. Un refus au lancement ramène aussi à cette page, sans annoncer un lancement qui n'a pas eu lieu. Voir « texte vide ou exécution interrompue » dans le [dépannage](#13-dépannage). Le bouton **Arrêter l'exécution** (page **Exécutions**) interrompt une exécution : les résultats déjà obtenus sont conservés.

Vérification : lancement par les formulaires vérifié sous Linux le 2026-11-02 (quatre combinaisons réelles, dont transcribe.cpp avec Whisper GGUF), sur une version antérieure de l'interface et par un client HTTP automatisé : pas d'observation à l'écran. La CI Windows a contrôlé les mêmes inférences le 2026-11-02. Le panneau unique, l'audio unique par défaut, le lot ordonné, les choix par défaut, le repli sans JavaScript et la mise à jour automatique des sélections sont couverts par des tests automatiques sur des pages simulées, pas par une observation dans un navigateur.

## 10. Lire un résultat

*Faites ceci.* Ouvrez la page **Résultats**. Les essais sont regroupés par audio : le nom du fichier et sa durée figurent en titre de chaque groupe. Le tri par défaut présente les essais les plus récents en premier dans chaque groupe ; les liens Plus rapides, Moins de RAM et CPU le moins occupé changent l'ordre des essais de chaque groupe, jamais l'ordre des audios. Cliquez sur le nom d'un modèle pour ouvrir le texte et le détail de cet essai : dans un lot, le lien ouvre directement l'audio concerné. Pour comprendre les repères, ouvrez **Comprendre les indicateurs** depuis la page.

*Vous devez voir.* Une ligne par essai : le modèle (et sa variante GGUF si elle est consignée), puis **Transcription**, **RAM moteur** et **CPU moteur**, le moteur et la date courte. Si les durées décodées d'un audio divergent, le groupe le signale et chaque ligne donne la durée de son propre essai ; deux fichiers de même nom se distinguent par leur empreinte courte (l'empreinte est un identifiant unique calculé à partir du contenu du fichier). Les états restent visibles sur la ligne : résultat en erreur, exécution interrompue, marques. Les mesures simulées sont classées à part, sous leur propre titre. Les mesures dépendent de votre ordinateur : elles ne disent rien de la qualité du texte ni des performances d'un autre poste.

*Si ce n'est pas le cas.* Voir « texte vide ou exécution interrompue » dans le [dépannage](#13-dépannage) ; si la page elle-même ne s'affiche pas, voir « la page ne s'ouvre pas ».

Une marque **SYNTHÉTIQUE** seule signale un audio ou un texte de test : elle ne dit rien du moteur ni des mesures. Les marques **FACTICE** ou **MESURES SIMULÉES** signalent, elles, un moteur factice (un moteur de substitution utilisé par les tests) ou des valeurs simulées.

*Contexte de l'ordinateur.* Le détail d'un essai et la comparaison sélectionnée proposent un bloc repliable **Contexte de l'ordinateur**, séparé des indicateurs du moteur ; dans le détail d'un essai, il porte le titre « Relevés système de cette exécution ». Il donne le CPU total moyen pendant la transcription, la RAM disponible après l'audio et la RAM disponible après le chargement du modèle. Le CPU total inclut les autres programmes de l'ordinateur, pas seulement celui du moteur. La RAM disponible est une estimation du système à un instant donné : ce n'est ni le minimum resté pendant la transcription, ni la part consommée par le moteur. Les pourcentages reposent sur les ressources visibles par le système : sur un ordinateur partagé ou virtualisé, ils ne décrivent pas une capacité matérielle garantie. Ces valeurs décrivent cet essai, sur cet ordinateur : elles ne disent rien du modèle, ne garantissent ni fluidité ni confort d'usage et ne prouvent rien pour un autre ordinateur. Quand un relevé manque, le bloc affiche « non mesuré ». Le lien **Comprendre les indicateurs** détaille ces limites.

*Historique.* Tous les essais, y compris les échecs, les interruptions et les résultats non interprétables, restent dans **Exécutions**, sous **Historique complet des exécutions** ; le lien *historique complet des exécutions* de la page **Résultats** y mène. Chaque exécution exploitable y ouvre son détail. Dans ce détail, le texte complet vient après le modèle et les mesures ; les mesures détaillées, les segments et les informations de l'exécution suivent dans des blocs que vous pouvez ouvrir.

Relisez toujours le texte en écoutant l'audio. Une phrase fluide peut être fausse.

Vérification : consultation des résultats et de leurs détails vérifiée sous Linux le 2026-11-02, sur une version antérieure de l'interface, sans observation humaine à l'écran. Le bloc **Contexte de l'ordinateur** de l'interface actuelle est couvert par les tests automatiques et par une observation dans un navigateur, sur des données factices (thème clair seulement ; voir la note « Niveau de vérification de ce guide »). Windows : non vérifié sur un poste ; la CI a contrôlé la suite de tests, avant la refonte de l'interface.

## 11. Comparer deux résultats

On compare deux transcriptions d'un même audio, obtenues avec deux modèles (ou deux exécutions du même modèle).

*Faites ceci.*

1. Lancez une seconde exécution (étape 9) sur le même audio, avec un autre modèle ou le même.
2. Ouvrez la page **Comparaisons** (ou, dans **Résultats**, le lien **Comparer**).
3. Dans le groupe de votre audio, cochez les cases à côté des noms des modèles, puis cliquez sur **Comparer les transcriptions sélectionnées**. Changer le classement conserve les cases cochées, même sans JavaScript ; une comparaison accepte jusqu'à 64 sélections d'un même audio.

*Vous devez voir.* La durée audio commune dans l'en-tête, puis une carte par transcription : modèle, temps de transcription, RAM, CPU, moteur et date, suivis du texte entier. Si les durées consignées divergent, chaque carte indique la sienne. La meilleure valeur observée de temps et de mémoire est signalée près de sa mesure par un libellé court (« meilleur temps », « meilleure RAM »), égalités comprises, sans phrase de synthèse désignant un vainqueur ; le CPU ne reçoit aucune distinction, et les mesures simulées ou partielles non plus. Les blocs **Ce qui diffère** puis **Toutes les mesures et informations** donnent les valeurs distinctes, puis l'ensemble des mesures et métadonnées, y compris le rapport de vitesse et son repère. Le lien **Comprendre les indicateurs** explique les calculs et les limites.

*Si ce n'est pas le cas.* Vérifiez que deux essais terminés du même audio existent (étapes 9 et 10) ; pour un texte vide ou une exécution interrompue, voir le [dépannage](#13-dépannage).

*Ce que cela ne dit pas.* Le texte le plus fluide n'est pas forcément le plus exact, et l'outil ne désigne aucun « meilleur » modèle. La comparaison sert à repérer des différences ; c'est à vous de juger, en réécoutant l'audio.

Vérification : comparaison de quatre résultats d'un même audio vérifiée sous Linux le 2026-11-02, sur une version antérieure de l'interface, par un client HTTP automatisé, sans observation humaine à l'écran. Windows : non vérifié sur un poste ; la CI a contrôlé la suite de tests, avant la refonte de l'interface.

## 12. Arrêter et relancer

- Arrêter : dans le terminal où tourne l'application, appuyez sur `Ctrl+C`. Le message `Arrêt du serveur.` s'affiche. Attendez la fin avant de fermer le terminal. Les résultats déjà obtenus restent consultables ; une exécution en cours est marquée « interrompue ».
- Relancer plus tard : rouvrez un terminal dans le dossier du projet et retapez `uv run --locked transcription-bench` (étape 5). Vos audios, moteurs, modèles et résultats sont conservés dans le dossier `data/`.

*Si ce n'est pas le cas.* Si le message ne s'affiche pas, attendez la fin du travail en cours. Si vous fermez le terminal sans attendre, l'exécution en cours sera marquée « abandonnée » au prochain démarrage (voir le [dépannage](#13-dépannage)).

Vérification : arrêt du serveur pendant une exécution réelle, puis redémarrage avec conservation des résultats, vérifiés sous Linux le 2026-11-02 sur une version antérieure de l'interface (l'arrêt a été demandé au programme, pas par Ctrl+C au clavier). Sous Windows, Ctrl+C n'est pas vérifié sur un poste réel ; l'annulation d'un job CI n'est pas un Ctrl+C.

## 13. Dépannage

Pour chaque cas : ce que vous voyez, la cause probable, que faire.

| Ce que vous voyez | Cause probable | Que faire |
|---|---|---|
| Le terminal affiche « impossible d'écouter sur http://127.0.0.1:8765 » et « Vérifiez qu'aucun autre programme n'utilise ce port » | Une autre application (ou une autre copie de ce programme) utilise déjà ce port | Fermez l'autre programme, ou relancez avec `uv run --locked transcription-bench --port 8080` |
| « port invalide » | Le port donné n'est pas un nombre entre 1024 et 65535 | Choisissez un port dans cet intervalle |
| Un message du système signale que la commande est introuvable ou qu'elle n'est pas reconnue (message système non relevé lors d'un essai ; la formulation dépend de votre système) | L'outil de lancement n'est pas installé, ou le terminal n'a pas été rouvert après son installation | Refaites l'étape 2, fermez puis rouvrez le terminal |
| La page ne s'ouvre pas dans le navigateur | Le programme n'est pas lancé (ou s'est arrêté sur une erreur après avoir affiché « Interface disponible », par exemple un port occupé), ou l'adresse est différente de celle affichée | Lisez les dernières lignes du terminal, recopiez l'adresse exacte (avec le bon port) ; n'utilisez pas une autre adresse de l'ordinateur |
| « Requête refusée : adresse, origine ou jeton invalide. » | L'adresse tapée n'est pas celle affichée par le terminal (`http://127.0.0.1:` ou `http://localhost:` suivi du port), ou la page est restée ouverte d'une session précédente | Rouvrez l'adresse affichée par le terminal et rechargez la page |
| « Le moteur demandé n'est pas prêt pour une exécution » ou état « échec » dans **Moteurs** | Le moteur n'est pas installé, ou son installation a échoué | Ouvrez **Moteurs**, cliquez sur **Consulter le journal d'installation** pour lire la cause (par exemple pas de connexion), corrigez, puis cliquez sur **Installer ce moteur** |
| « Dépôt refusé » dans **Modèles** | L'identifiant est faux, le modèle n'est pas pris en charge par ce moteur ou il manque des fichiers | Vérifiez l'identifiant (aucune faute, pas d'espace) ; la page indique le motif et parfois un moteur possible |
| « Variantes GGUF proposées » | Le dépôt contient plusieurs fichiers ; il faut en choisir un seul | Cliquez sur le bouton « Vérifier avec » qui porte le nom du fichier voulu |
| Téléchargement interrompu, ou modèle absent de **Modèles locaux prêts** | Connexion coupée, application arrêtée, ou disque plein | Relancez le téléchargement depuis la page **Modèles** ; un modèle incomplet n'est jamais proposé comme prêt ; libérez de la place si le disque est plein |
| Pas de connexion Internet | Réseau coupé | Reconnectez-vous : moteur, vérification et téléchargement de modèle en ont besoin ; une fois tout installé, une transcription n'en a plus besoin |
| Un audio est listé avec une erreur, ou « lecture impossible » | Fichier abîmé, vide, ou format non pris en charge | Vérifiez que le format est wav, mp3, m4a, ogg, opus ou flac ; réexportez le fichier |
| « nom refusé » | Le nom ou la cible du fichier n'est pas accepté | Renommez le fichier simplement, sans sous-dossier ni lien |
| Texte vide ou exécution « interrompue » ou « échouée » | Audio sans parole décodable, arrêt demandé, application fermée pendant le travail | Relancez une exécution ; la page **Exécutions** affiche la dernière erreur |
| « une autre instance utilise déjà ce dossier de données » dans le terminal | L'application est déjà lancée dans un autre terminal | Fermez l'autre instance (`Ctrl+C` dans son terminal), puis relancez |
| Exécution marquée « abandonnée » dans **Résultats** | L'application a été fermée brutalement pendant le travail | Relancez l'application, puis une nouvelle exécution ; les audios sans résultat sont signalés non traités |
| « Une opération longue est déjà en cours » | Une seule opération à la fois | Attendez la fin ou arrêtez-la depuis **Exécutions** |

## Glossaire

- Audio : un fichier d'enregistrement (voix) à transcrire.
- CI : contrôles automatiques exécutés sur des machines Windows et Linux de test, sans rapport avec votre ordinateur.
- CPU (processeur) : la puce de l'ordinateur qui effectue les calculs ; ses « cœurs » sont ses unités de calcul.
- RAM (mémoire vive) : l'espace de travail rapide de l'ordinateur, où sont chargés les programmes en cours.
- Mo, Go, Mio, Gio : unités de taille des fichiers. Un mégaoctet (Mo) vaut un million d'octets, un gigaoctet (Go) mille Mo ; un mébioctet (Mio) vaut 1 048 576 octets, un Gio mille vingt-quatre Mio. Les sites de modèles annoncent souvent des Mo ou des Go ; les pages de l'outil affichent des Mio ou des Gio.
- Empreinte SHA-256 : un identifiant unique calculé à partir du contenu d'un fichier ; deux audios identiques ont la même empreinte, abrégée en « empreinte courte » à l'affichage. Elle permet de regrouper les transcriptions d'un même audio.
- Git : outil qui télécharge un projet et suit son historique ; « cloner » un projet en récupère une copie.
- JavaScript : langage intégré au navigateur, qui rend les pages réactives ; l'outil reste utilisable sans lui, en rechargeant la page.
- Lot : plusieurs audios traités par une même exécution, l'un après l'autre.
- Mesures simulées : valeurs produites par le moteur factice ou de test, jamais représentatives d'un ordinateur réel. Une marque synthétique seule ne signifie pas que les mesures sont simulées.
- Moteur factice : moteur de substitution utilisé par les tests du projet ; il produit des transcriptions et des mesures simulées, sans reconnaître la parole.
- Variante : version du fichier d'un même modèle, dans un format ou une précision donnée (par exemple Q5_K_M) ; pour un modèle GGUF, c'est le fichier à choisir.
- Exécution : une transcription d'un ou plusieurs audios avec un modèle donné.
- Hors ligne : sans connexion Internet. Une fois le moteur et le modèle installés, la transcription se fait hors ligne ; les autres cas où Internet est utilisé sont listés dans le tableau de la section « Ce que fait l'outil, et ce qu'il envoie sur Internet ».
- Hugging Face : site qui héberge de nombreux modèles de reconnaissance de la parole.
- Modèle : le fichier (volumineux) qui contient ce que la machine a appris pour transcrire la voix.
- Moteur : le programme qui fait tourner un modèle.
- Dépôt, révision : sur Hugging Face, un dépôt est la page d'un modèle et une révision une version précise de ce modèle.
- GGUF : format de fichier de modèle utilisé par le moteur transcribe.cpp.
- Port : numéro qui termine l'adresse locale de l'application (8765 par défaut).
- Python : langage de programmation dans lequel l'outil est écrit ; l'outil de lancement le prépare tout seul.
- Terminal : fenêtre dans laquelle on tape des commandes (Terminal sous Linux, PowerShell sous Windows).
- Threads : nombre de calculs menés en parallèle par le processeur ; la valeur proposée par défaut convient pour commencer.

## Pour aller plus loin

- Détails du fonctionnement, de l'arrêt, des limites et de la CI : [documentation technique](technique.md).
- Licences des modèles et des outils : [licences-modeles.md](licences-modeles.md).
- Comment les validations ont été menées : [validation-linux.md](validation-linux.md) et [ci-windows.md](ci-windows.md).
