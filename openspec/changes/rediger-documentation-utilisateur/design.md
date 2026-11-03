## Context

`README.md` : 350 lignes, 14 sections, dont le mode d'emploi réel tient dans « Prérequis », « Lancement », « Dossiers de données », « Utilisation avec le moteur factice » et « Moteurs et modèles réels ». Le reste (« État réel du prototype », « Organisation du code », « Vérifications Windows et publication », jeton Hugging Face, mode hors ligne, durées natives, `langue_imposee`…) s'adresse à des développeurs. Les messages de l'interface elle-même sont techniques (« empreinte SHA-256 », « threads », « créneau »), mais les modifier n'est pas l'objet de ce change.

Le parcours utilisateur réel, tel que l'application le propose aujourd'hui : installer `uv` (installeur officiel, une commande, différente sous Linux et Windows) ; ouvrir un terminal dans le dossier du projet ; `uv run --locked transcription-bench` ; ouvrir `http://127.0.0.1:8765` ; copier des audios dans `data/audio` (aucun envoi par la page) ; page `Moteurs` → installer un moteur ; page `Modèles` → saisir un identifiant Hugging Face, choisir le moteur, vérifier, télécharger ; page `Exécutions` → choisir modèle, audios, threads → lancer ; page `Opération` → suivre ; pages `Résultats` et `Comparaisons` → lire et comparer ; `Ctrl+C` dans le terminal pour arrêter.

Ce qu'on sait fiable pour un exemple concret (tel que vérifié, `docs/validation-linux.md`, `docs/licences-modeles.md`, mémoire projet) : cinq modèles d'essai ont tourné de bout en bout : `dropbox-dash/faster-whisper-large-v3-turbo` (faster-whisper, ≈ 1,6 Go), `handy-computer/whisper-large-v3-turbo-gguf` (transcribe.cpp, fichier Q5_K_M, ≈ 620 Mo), `openai/whisper-large-v3-turbo` et `nvidia/parakeet-tdt-0.6b-v3` (Transformers), `handy-computer/Qwen3-ASR-0.6B-gguf` (transcribe.cpp, fichier Q8_0, ≈ 850 Mo). Aucune installation vierge par l'interface n'a été essayée de bout en bout : c'est précisément ce que la validation du guide doit faire.

## Goals / Non-Goals

**Goals:**
- Quelqu'un qui n'a jamais ouvert le projet réussit sa première transcription en suivant le guide, sans aide.
- Chaque terme technique est soit évité, soit expliqué en une phrase au premier emploi et dans un glossaire.
- Le guide ne ment pas : ce qui a été vérifié (et sur quel système) est dit ; ce qui ne l'a pas été est signalé.
- Le README devient une porte d'entrée lisible en moins d'une minute.
- Aucune information du README actuel n'est perdue.

**Non-Goals:**
- Changer l'application, ses libellés ou ses messages ; créer des scripts de lancement ; captures d'écran ou vidéos ; documenter pour des développeurs ou contributeurs au-delà du déplacement.
- Évaluer ou conseiller des modèles (le guide dit comment comparer, pas lequel choisir ni que le résultat est « bon »).

## Decisions

### D1. Trois niveaux, trois fichiers
`README.md` (court, porte d'entrée) → `docs/guide-utilisateur.md` (pas à pas + glossaire + dépannage) → `docs/technique.md` (ancien contenu du README, pour développeurs et agents). Le guide ne renvoie vers la documentation technique que dans une dernière section « Pour aller plus loin ».
*Alternative écartée* : tout garder dans le README avec des sections repliables — le README resterait long et mélangé.

### D2. Ton et langage
Vouvoiement, français courant, phrases courtes, une action par étape numérotée, verbes à l'impératif. Interdire le jargon par défaut plutôt que l'expliquer partout : si un terme est inévitable (« moteur », « modèle », « terminal »), il est défini à sa première apparition **et** dans le glossaire. Les libellés exacts de l'interface sont écrits en **gras** (et le gras ne sert qu'à eux), ce qui permet de les contrôler automatiquement. Les guillemets français restent libres : les gabarits en contiennent déjà (« Une opération « … » est en cours »), ce qui rendrait la règle des guillemets ambiguë. Un libellé dynamique (« Vérifier avec {{ candidat }} ») se cite par sa partie fixe ou figure dans la liste blanche.

### D3. Chaque étape a trois parties
« Faites ceci » (commande ou clic, copiable), « Vous devez voir » (résultat observable, texte de l'interface), « Si ce n'est pas le cas » (renvoi vers le dépannage). Les commandes à copier sont données pour Linux et pour Windows côte à côte ; l'ouverture du terminal (PowerShell sous Windows, application Terminal sous Linux) est expliquée.

### D4. Honnêteté sur la vérification
Chaque bloc de commandes porte sa preuve : « vérifié sous Linux le <date> » ou « non vérifié sur un poste Windows ; la CI Windows a contrôlé <ce qui l'a été> ». Pas de formule vague (« devrait fonctionner »). Le guide rappelle en tête que l'outil n'est pas validé cliniquement et qu'une transcription fluide n'est pas forcément exacte.

### D5. Exemple concret, pas abstrait
Le parcours principal utilise `handy-computer/whisper-large-v3-turbo-gguf` (moteur transcribe.cpp, fichier `whisper-large-v3-turbo-Q5_K_M.gguf`, ≈ 620 Mo) : le plus léger des modèles vérifiés (Qwen3-ASR ≈ 850 Mo n'est qualifié que sous Linux, sans CI) et celui qu'a contrôlé la CI Windows. Le guide donne son moteur, son identifiant exact, le fichier à choisir, la taille à télécharger et ce que l'on doit voir. Durée, mémoire et espace disque ne sont indiqués que s'ils ont été mesurés, avec la machine de mesure ; sinon « non mesuré ». Les autres modèles vérifiés sont listés dans un tableau (moteur, identifiant, taille, remarque), avec renvoi vers `docs/licences-modeles.md` pour les licences.

### D6. Contrôles automatiques légers, dans la suite de tests existante
Un seul module de test, sans nouvelle dépendance : (a) tout texte en gras du guide est un libellé présent (en sous-chaîne) dans les gabarits ou les chaînes Python de `transcription_bench/web` (messages d'action et d'erreur inclus), dans le titre d'une page, ou dans une liste blanche explicite ; (b) les liens relatifs du README et des documents `docs/` pointent vers des fichiers existants (les ancres ne sont pas contrôlées : le calcul des ancres GitHub avec accents est fragile) ; (c) une liste de termes interdits hors glossaire et hors « » (CSRF, WSGI, Flask, Jinja, venv, namespace, mmap, RTF, HF_HUB_OFFLINE, etc.) n'apparaît pas dans le guide ni le README. Les fichiers sont lus en UTF-8 explicite (Windows). Le glossaire a un titre fixe (« Glossaire »), que le test exclut de la liste d'interdits. Le texte du guide n'est jamais comparé à un gabarit « attendu ».
*Alternative écartée* : évaluer la lisibilité par un score automatique (Flesch en français peu fiable).

### D7. Validation par un parcours à froid
La preuve principale de la clarté est humaine : suivre le guide sur une copie vierge du dépôt (dossier de données neuf), avec uniquement ce que le guide demande, jusqu'à une première transcription lue et une comparaison. Ce parcours exige installation de moteur, téléchargement et inférence réelle : il n'a lieu que sur un **PC de test déclaré explicitement** (jamais sur le serveur de développement), avec un audio synthétique ou non personnel, et consigne OS, machine, versions et dépendances. Pour la comparaison, deux exécutions du même modèle sur le même audio suffisent : pas de second téléchargement. L'écart entre ce qui est écrit et ce qui se passe est corrigé dans le guide, pas contourné. La relecture finale revient au propriétaire.

### D8. Critères de relecture, propriétés testables et procédure
Le vouvoiement, les phrases courtes, les sigles développés et la clarté sont des **critères de relecture** (tâche 4.3), pas des exigences testées : seuls la liste d'interdits, les libellés et les liens sont automatisés. Les propriétés de procédure (tableau de correspondance README → documentation, parcours à froid, relecture du propriétaire) vivent dans les tâches et ce design, pas dans la spec : elles ne seraient plus vérifiables après archivage. La spec ne garde que les propriétés du livrable (structure, niveaux de vérification affichés, liens, libellés, accès réseau décrits).

### D9. Accès réseau décrits tels qu'ils sont
Le guide ne dit pas « seuls les téléchargements d'outils et de modèles utilisent Internet » : la vérification distante d'un modèle utilise aussi le réseau, et le premier `uv run --locked` télécharge probablement Python 3.12 géré et les dépendances (à confirmer au parcours à froid). Le guide liste les accès réels (installation de uv, obtention du projet, premier lancement, installation d'un moteur, vérification et téléchargement d'un modèle) et dit que les audios et transcriptions ne quittent jamais l'ordinateur.

### D10. Windows : preuves existantes seulement
La CI ne vérifie ni l'installeur de uv, ni le lancement en console, ni Ctrl+C (limite déjà reconnue par `platform-verification`). Le guide réutilise les preuves CI existantes, sans nouveau job (qui exigerait un accord explicite), et marque le reste « non vérifié sur un poste Windows ». Pour l'installation de uv sous Windows, il présente aussi `winget` en alternative à l'installeur en ligne de commande qui exécute un script distant, et pour obtenir le projet l'archive ZIP du dépôt public en alternative à Git.

## Risks / Trade-offs

- **Le guide vieillit avec l'interface** → les contrôles de libellés échouent dès qu'un libellé change ; coût accepté. Les procédures non vérifiables automatiquement (téléchargements, tailles) portent leur date.
- **Windows non vérifié sur poste réel** → annoncé tel quel ; seules les commandes réellement contrôlées par la CI sont décrites comme telles.
- **Le vocabulaire de l'interface reste technique** → le guide traduit au moment où l'utilisateur voit le terme (« Empreinte SHA-256 : un identifiant unique du fichier, utile pour savoir si deux résultats portent sur le même audio »), sans changer la page. À long terme, simplifier les pages serait plus efficace (voir questions ouvertes).
- **Téléchargements** pour valider le guide : volumes importants (centaines de Mo à plusieurs Go) → lot annoncé et accepté avant exécution.

## Migration Plan

0. Préalable : `habiller-interface-sumi` implémenté (navigation, libellés et navigateurs minimaux définitifs).
1. Cartographier chaque section du README actuel (reste, déplacé vers `docs/technique.md`, ou réécrit dans le guide) dans un tableau de correspondance sans perte.
2. Écrire le guide, le glossaire, le dépannage ; réduire le README.
3. Corriger dans `docs/technique.md` ce qui est périmé (par exemple la mention des durées natives, qui ne couvre plus Qwen3-ASR sans durée native).
4. Ajouter les contrôles, suivre le guide à froid, corriger, faire relire.

## Open Questions

- Public précis : « personne à l'aise avec un ordinateur, sans notion de programmation, mais prête à copier-coller des commandes » est l'hypothèse de travail. Une personne qui ne veut aucune commande exigerait des scripts à double-clic (changement de produit, hors périmètre).
- Captures d'écran : très utiles pour des non-techniciens ; à prendre sur données synthétiques après l'habillage. Non incluses ici faute de décision (poids dans Git, maintenance à chaque changement d'interface).
- Vocabulaire des pages de l'application : à simplifier dans un autre change si le guide montre que la traduction à la volée ne suffit pas.
