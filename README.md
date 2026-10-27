# transcription-bench

Prototype local de comparaison de modèles de transcription française, sur CPU
uniquement, sous Linux x64 et Windows x64.

**Ce n'est pas un produit clinique validé.** Une transcription fluide n'est pas
une transcription médicalement correcte : aucun résultat produit ici ne doit
être présenté comme tel.

## État réel du prototype

| Élément | État |
|---|---|
| Serveur web local, interface HTML, moteur factice | développés et testés sur le serveur de développement Linux |
| Moteurs réels (faster-whisper, transcribe.cpp, Transformers) | déclarés mais **non qualifiés** : adaptateurs absents (tâches 8.x), aucun verrou de dépendances validé, installation indisponible |
| Modèles et poids | **aucun** sur le serveur de développement, aucun téléchargement effectué |
| Mesures, textes, RTF | textes et mesures du moteur **simulés** (chargement, transcription, RTF, CPU, mémoire) ; les durées mesurées par le serveur et le décodage restent réelles |
| Validation Linux / Windows sur PC de test | pas encore faite |

Autrement dit : aujourd'hui, seule l'utilisation du **moteur factice** est
possible. Les étapes qui installent un moteur ou téléchargent un modèle
supposent une qualification préalable sur un PC de test (jalon 0 du changement
OpenSpec `add-benchmark-prototype`), puis les adaptateurs réels.

**Règle du serveur de développement** : aucun moteur réel, aucun poids de
modèle et aucune inférence réelle n'y sont installés ni exécutés ; ces
opérations sont réservées à un PC de test explicitement déclaré, dans le
périmètre annoncé (moteurs, modèles, volumes).

## Prérequis

1. Une copie locale du dépôt (le programme utilise la racine du dépôt comme
   dossier de travail, quel que soit le dossier courant).
2. `uv` installé pour l'utilisateur courant, sans droits administrateur.
   Procédure officielle : <https://docs.astral.sh/uv/getting-started/installation/>

   Linux :

   ```sh
   curl -LsSf https://astral.sh/uv/install.sh | sh
   ```

   Windows (PowerShell) :

   ```powershell
   powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
   ```

3. Un accès réseau lorsque des ressources manquent dans le cache de `uv` :
   préparation initiale de `.venv/`, ou resynchronisation ultérieure si `uv`
   doit réinstaller des paquets (dépendances verrouillées du serveur depuis
   PyPI : Flask, Waitress, PyAV, numpy, huggingface_hub, psutil) ou télécharger
   un CPython 3.12 géré. Aucun fonctionnement hors ligne n'est garanti pour le
   lancement ; il ne télécharge en revanche **jamais** de moteur ni de poids de
   modèle.

Il n'est pas nécessaire d'installer Python soi-même : `uv` crée le `.venv/` du
projet avec un Python 3.12 conforme à `.python-version`. Selon ses préférences
d'installation et les interpréteurs déjà présents, il utilise un Python 3.12
existant ou en télécharge un qu'il gère ; `.python-version` ne rend pas cet
interpréteur « géré » par nature. Le Python du système n'est ni modifié ni
remplacé.

## Lancement : une seule commande

Depuis la racine du dépôt :

```sh
uv run --locked transcription-bench
```

Avec un autre port :

```sh
uv run --locked transcription-bench --port 8080
```

- `--locked` impose `uv.lock` : le lancement ne réécrit pas le verrou et
  s'arrête en erreur s'il n'est plus à jour. `uv` synchronise en revanche
  `.venv/` sur les versions verrouillées, en téléchargeant les paquets absents
  du cache.
- Port par défaut : `8765`. Port valide : entier de `1024` à `65535` ; toute
  autre valeur est refusée avec un message explicite (code de sortie `2`).
- Le serveur n'écoute que sur l'adresse de bouclage `127.0.0.1`, puis affiche
  son URL :

  ```
  Interface disponible : http://127.0.0.1:8765
  ```

  Ouvrez cette URL dans un navigateur local. Si le port est déjà utilisé, le
  message le signale et la commande se termine en erreur : relancez-la avec
  `--port N`.
- Une seule instance par dossier de données : un second lancement est refusé
  avant toute autre opération, avec le chemin du verrou d'instance
  (`data/instance.lock`).

Cette commande est le **seul** lancement supporté. N'utilisez ni `flask run`,
ni `app.run`, ni le mode debug, ni le reloader, ni plusieurs workers : la
supervision d'arrêt, le verrou d'instance et le jeton anti-CSRF en dépendent.
Aucun autre lanceur n'est fourni.

## Dossiers de données

Les données sont ancrées sous `data/`, à la racine du projet, et ne suivent pas
le dossier courant. Elles sont exclues de Git.

| Dossier | Contenu |
|---|---|
| `data/audio` | audios d'entrée, **déposés par copie de fichier** ; formats acceptés : `wav`, `mp3`, `m4a`, `ogg`, `opus`, `flac` ; aucun envoi par l'interface |
| `data/models` | modèles téléchargés explicitement, avec leur inventaire local |
| `data/engines` | environnements isolés des moteurs et journaux d'installation |
| `data/results` | résultats des exécutions, conservés sans écrasement |
| `data/cache` | fichiers de travail décodés, créés à la demande et supprimés en fin d'exécution |

`audio`, `models`, `engines` et `results` sont créés au démarrage ;
`data/cache` ne l'est qu'au lancement d'une exécution. La page d'accueil affiche
leur emplacement et leur présence.

## Utilisation avec le moteur factice

1. Copiez un audio d'essai (par exemple un WAV synthétique produit localement)
   dans `data/audio`, sous un nom simple, sans sous-dossier.
2. Lancez la commande de lancement et ouvrez l'URL affichée.
3. `Audios` liste les fichiers présents, le format et une durée indicative
   lue dans l'en-tête.
4. `Exécutions` propose le moteur factice avec un **modèle synthétique** :
   aucun fichier, aucun poids, aucun téléchargement. Sélectionnez un ou
   plusieurs audios, le nombre de threads demandé, puis lancez.
5. `Opération` affiche l'état de l'opération longue (une seule à la fois, sans
   file d'attente) ; `Résultats` liste les exécutions enregistrées et le détail
   de chaque transcription ; `Résultats > comparaison` regroupe les
   transcriptions d'un **même fichier audio** repéré par son empreinte SHA-256
   et les affiche côte à côte.

Les textes du moteur factice portent le marqueur `[FACTICE]`. Les mesures
relevées par le serveur restent réelles (durée décodée, temps de décodage,
durée totale de l'opération, durée du processus moteur) ; celles produites par
le processus moteur sont simulées (temps de chargement, durée de transcription
et RTF qui en dérive, temps CPU, pic mémoire). Les audios longs y sont découpés
en fenêtres fixes de 30 s. **Aucune qualité de transcription n'est garantie ni
évaluée** : ni score, ni texte de référence, ni diarisation.

## Moteurs et modèles réels

Ils ne sont pas utilisables sur le serveur de développement : la page
`Moteurs` les affiche comme non installés et leur installation est aujourd'hui
indisponible, faute de fichiers de dépendances validés
(`requirements/<moteur>.txt`, absents du dépôt à ce stade). La procédure
prévue, une fois les moteurs qualifiés sur PC de test, est explicite à chaque
étape :

- installation d'un moteur depuis la page `Moteurs` (environnement isolé créé
  par `uv`, contrôle d'import, marqueur d'installation) ;
- vérification puis téléchargement d'un modèle depuis la page `Modèles`, à
  révision figée, avec inventaire local ; inférence strictement à partir des
  fichiers locaux.

Rien de tout cela ne se déclenche au lancement du serveur.

### Jeton Hugging Face

Pour les dépôts restreints, configurez un jeton par les **mécanismes standards**
du client `huggingface_hub` (par exemple la variable d'environnement `HF_TOKEN`
ou le fichier de configuration écrit par son outil de connexion). Le programme
ne demande, n'affiche, ne journalise et n'enregistre jamais ce jeton : il n'est
ni dans les résultats, ni dans les journaux.

### Hors ligne

Le mode hors ligne s'applique au **processus du moteur**, pas au serveur : la
variable d'environnement `HF_HUB_OFFLINE=1` lui est transmise. `local_files_only`
et `trust_remote_code` ne sont pas des variables d'environnement mais des
**options de chargement** à passer aux API du moteur (`True` et `False`). Les
adaptateurs réels restent à écrire et à éprouver (tâches 8.x) : leur application
effective sera vérifiée sur PC.

Le serveur, lui, n'accède au réseau que sur action explicite de l'utilisateur
(installation d'un moteur, vérification ou téléchargement d'un modèle). Aucune
donnée audio ni transcription n'est envoyée à un service externe.

## Arrêt du serveur

Arrêt normal : `Ctrl+C` sous Linux et Windows, `SIGTERM` sous Linux.

- À la sortie de `waitress.serve`, la CLI affiche `Arrêt du serveur.` **avant**
  le nettoyage ; le service HTTP a rendu la main, donc l'interface n'est plus
  garantie disponible pendant l'arrêt.
- Le nettoyage passe le créneau à l'état d'arrêt, termine le moteur d'exécution
  et le sous-processus d'installation en cours, attend la clôture de l'opération
  de façon bornée, puis libère le verrou d'instance.
- Code de sortie : `0` si le nettoyage aboutit (opération close, verrou
  libéré), `1` sinon, avec un message explicite (opération non close, verrou
  conservé jusqu'à la fin du processus, échec de clôture).
- Descendance du moteur : la terminaison est un « au mieux ». Sous Linux, le
  groupe est signalé puis sa descendance relevée ; sous Windows, l'arborescence
  de processus connue est parcourue. Un descendant non relevé, créé après ce
  relevé ou détaché de l'arborescence peut survivre : il n'est alors ni suivi
  ni arrêté, et il ne garde pas le créneau occupé.
- Autre cas, distinct : si le **processus moteur principal** survit au signal de
  forçage, le créneau reste occupé jusqu'à sa fin réelle, le verrou d'instance
  est conservé et la commande se termine en code `1`.
- Les signaux suivants sont **ignorés** : un second `Ctrl+C` n'interrompt pas la
  clôture en cours.
- Les résultats déjà écrits restent consultables ; l'exécution est marquée
  interrompue ; une installation ou un téléchargement interrompu reste non prêt.
- Le verrou d'instance n'est libéré que lorsque le thread d'opération est
  réellement terminé. Sinon il reste détenu jusqu'à la fin réelle du processus
  (aucun thread n'est tué).

Limite assumée : **aucun délai global de sortie n'est garanti pendant un
téléchargement**, qui peut encore attendre ses entrées/sorties réseau.

Arrêt brutal : tuer le processus, fermer la console ou utiliser un signal non
prévu (par exemple `SIGKILL`). Au démarrage suivant, la récupération :

- termine le moteur survivant seulement si son PID et son heure de création
  concordent avec ceux enregistrés ;
- clôt en « abandonnée » toute exécution restée en cours, sans reprise
  d'inférence ; les audios sans résultat sont signalés non traités ;
- nettoie les dossiers de travail restants sous `data/cache`.

Si un état antérieur n'est pas traitable sans risque (moteur non identifiable,
inaccessible ou survivant à l'arrêt, `run.json` illisible, d'un schéma inconnu
ou incohérent), le démarrage est **refusé** : message explicite, code de sortie
`2`, le résultat concerné reste inchangé et l'exécution concernée n'est pas
close. Traitez la situation, puis relancez la commande.

Une exécution abandonnée se relance donc par une nouvelle exécution, avec un
nouveau chargement de modèle et de nouvelles mesures.

Les comportements `Ctrl+C` avec `uv run`, `SIGTERM` et l'arrêt sur PC Windows
restent à éprouver sur les PC de test : les tests du serveur de développement
ne valent pas validation Windows.

## Organisation du code et choix techniques

```
transcription_bench/
  cli.py                   point d'entrée, port, verrou d'instance, récupération, waitress.serve
  supervision.py           signaux d'arrêt et nettoyage idempotent, hors de Flask
  instance.py              verrou système d'une seule instance
  recuperation.py          clôture des exécutions abandonnées au démarrage
  web/app.py               fabrique create_app, routes minces, contrôles globaux, erreurs HTML
  web/templates/           gabarit de base et pages .html (Jinja2, échappement automatique)
  operations.py            créneau unique d'opération longue
  moteurs.py               installation des moteurs (états, marqueur, journal)
  verification_modeles.py  vérification distante et compatibilité
  compatibilite_modeles.py règles de compatibilité des dépôts Hugging Face
  gguf.py                  lecture partielle d'en-tête GGUF
  gestion_modeles.py       téléchargement explicite et inventaire local
  audios.py                liste des audios, décodage PyAV, empreinte SHA-256
  executions.py            formulaire d'exécution et demande validée
  execution_moteur.py      lancement et supervision du processus moteur
  resultats.py             stockage atomique des résultats
  consultation_resultats.py lecture des résultats et comparaison
  stockage.py, paths.py, processus.py  écriture atomique, chemins contrôlés, processus
engines/
  declarations.py          déclarations des quatre moteurs (familles, réglages, fichiers de dépendances attendus)
  registre.py              registre sans import de paquet moteur (imports différés)
  protocole.py             contrat d'événements runner ↔ serveur (lignes préfixées)
  runner.py                exécution dans le processus du moteur, événements préfixés
  hors_ligne.py            environnement hors ligne du moteur
  adaptateurs/factice.py   moteur factice
tests/                     tests unittest, sans réseau
```

- **Flask + Jinja2 + Waitress** plutôt qu'un serveur et un rendu maison :
  routage, lecture des formulaires, redirections, client de test et échappement
  automatique sont fournis ; Waitress est en Python pur, compatible Windows et
  Linux, et sert l'application en un seul processus, `127.0.0.1`, quatre
  threads de requêtes, corps limité à 1 Mio.
- **Routes minces, métier hors Flask** : la fabrique `create_app` ne prend aucun
  verrou, ne démarre ni thread ni serveur et n'écrit aucun fichier ; les routes
  valident la demande puis appellent les services. Le créneau d'opération, les
  moteurs et le stockage ne dépendent pas de Flask.
- **Contrôles globaux** avant tout effet de bord : `Host` local exact avec le
  port, `Origin` local s'il est présent, formulaires urlencoded d'au plus
  64 Kio, jeton anti-CSRF renouvelé à chaque démarrage, sans session ni cookie.
- **HTML seul**, sans CSS ni JavaScript ; les actions passent par des liens et
  des formulaires, les contenus affichés sont échappés.
- **Tests `unittest`** via le client de test Flask et le moteur factice, sans
  réseau :

  ```sh
  uv run --locked python -m unittest discover -s tests -t .
  ```

## Limites connues

- Prototype non clinique, non destiné à un usage de soin.
- CPU uniquement ; pas de GPU, de Vulkan ni de macOS.
- Validation Linux et Windows sur PC de test non effectuée ; les tests du
  serveur de développement ne valent pas validation.
- Moteurs réels non installables pour l'instant (adaptateurs 8.x et verrous
  absents) ; aucune mesure réelle disponible.
- Un seul utilisateur, aucune authentification, aucune file d'attente : une
  seule opération longue à la fois.
- Pas d'évaluation automatique de la qualité (score, texte de référence,
  diarisation, correction par LLM), pas de streaming.
- Les contrôles de chemins et de formulaires sont des garde-fous, pas une
  isolation technique.
