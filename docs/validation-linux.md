# Vérifications fonctionnelles Linux — 2026-11-02

## Portée

Vérification du programme, pas évaluation des modèles. Client HTTP automatisé
sur le véritable serveur CLI/Waitress, routes Flask et services de production,
avec les trois environnements et quatre modèles locaux existants. Aucune voix,
dépendance ou poids nouveau téléchargé. Les audios sont synthétiques.

Contexte : PC Linux x64 déclaré de test, Manjaro, Ryzen 7 PRO 6850U, environ
30 Gio de RAM, Python 3.12.13 et uv 0.11.8. Le relevé exact du noyau, des
versions et des empreintes de code est dans les preuves locales. Les essais
ont porté sur l'arbre de travail basé sur `1424424`, avant son commit de
transmission vers le dépôt privé.

## Préparation honnête des ressources existantes

Les environnements des sondes ont été contrôlés avec `uv pip sync --dry-run`
hors ligne : aucun changement annoncé. Une synchronisation effective hors
ligne, sans changement de paquet, et un contrôle d'import dans chaque
interpréteur ont ensuite permis de préparer les marqueurs d'installation.
Les SHA-256 des fichiers de modèles ont été revérifiés contre les manifestes
locaux du jalon 0 avant préparation des inventaires du programme.

**Ce n'est pas une validation d'installation vierge par le bouton web.**
Les résultats ne doivent pas être présentés comme tels. Les ressources locales
préparées sont désormais reconnues par l'application normale.

## Scénarios réussis

- Accueil, moteurs, modèles, audios, formulaire d'exécution et résultats : HTTP 200.
- Vérification et lancement via les formulaires : quatre combinaisons réelles
  CPU (faster-whisper/Whisper, transcribe.cpp/GGUF Whisper,
  Transformers/Whisper, Transformers/Parakeet TDT).
- Refus HTTP 409 d'une seconde exécution pendant la première.
- Résultats finalisés, non factices, avec CPU effectif relu ; transcription non
  vide utilisée comme simple contrôle technique, sans mot attendu ni score.
- Consultation des détails et comparaison des quatre résultats sur la même
  empreinte audio : HTTP 200, sans nouvelle inférence.
- Arrêt utilisateur pendant un moteur réel : exécution interrompue, aucun
  processus moteur survivant.
- SIGTERM du serveur pendant une exécution réelle : moteur terminé, résultat
  interrompu, serveur sorti normalement avec code 0.
- Redémarrage : sept résultats restent consultables, fichiers finalisés
  inchangés et verrou d'instance libéré après arrêt.

## Timings natifs transcribe.cpp

Le champ facultatif `timings_natifs` est vérifié de l'adaptateur au fichier
`result.json` et à son tableau HTML. Il garde une entrée par appel dans l'ordre
et l'unité `ms` du moteur, sans somme ni conversion. Les timings ne sont pas
rangés parmi les réglages effectifs, qui restent stables par audio.

Vérifications réelles : un appel natif sur l'audio court ; deux appels de
fenêtres de 30 s pour l'audio synthétique de 47,704 s. Les autres moteurs et
anciens résultats restent consultables sans ce champ ; aucune mesure absente
n'est remplacée par zéro.

## Corrections et tests

La préparation a mis en évidence un défaut du rendu du formulaire natif : un
formatage numérique pouvait recevoir `None`. Le rendu conditionnel et les
messages devenus obsolètes ont été corrigés ; un test couvre affichage et
validation d'une demande native sans lancer de moteur.

Dernière suite complète : **698 tests réussis en 17,002 s**. Les chemins de
compatibilité des anciens résultats et les timings variables par fenêtre sont
couverts par des tests sans moteur réel.

## Preuves et limites

Preuve détaillée :
`data/feasibility/parcours-http/20261102-141608/preuve.json`,
avec le journal de tests voisin `tests-finaux.log`. Ces fichiers, les poids,
les audios et les résultats restent sous `data/`, hors Git.

Pas de contrôle visuel humain, pas de mesure de qualité ou de performance des
modèles. Les options hors ligne ont été appliquées ; aucune coupure réseau OS
n'est revendiquée pour ce parcours HTTP (les essais séparés du runner avaient
leur namespace isolé). Windows et installation vierge
restent non vérifiés par cette passe ; la seconde architecture GGUF (Qwen3-ASR)
a fait l'objet d'une qualification séparée, ci-dessous.

## Seconde architecture GGUF : Qwen3-ASR-0.6B (tâche 8.2) — 2026-11-03

Même PC Linux de test (contexte déclaré par l'utilisateur dans la session),
transcribe.cpp 0.4.1 et environnement moteur existants. Modèle choisi par
l'utilisateur : `handy-computer/Qwen3-ASR-0.6B-gguf`, commit
`7e7c69a577fa2725dfedbe34b5e999336e30a19b`, licence Apache-2.0 (carte, LICENSE
et NOTICE du dépôt), fichier `Qwen3-ASR-0.6B-Q8_0.gguf` (850 423 456 octets,
SHA-256 `f081b2d5e23bd669d92cc331d722a8a0681943b8e6f34b48996fd5c319b5acd8`,
identique à l'empreinte LFS publiée). Seul ce fichier a été téléchargé, par le
bouton du serveur après vérification de compatibilité.

- L'en-tête GGUF porte `general.architecture = qwen3_asr` ; la correspondance
  explicite vers la famille `qwen3-asr` a été ajoutée (un identifiant de famille
  n'admet pas de soulignés).
- Premières exécutions par les formulaires HTTP (10,673 s en natif et 47,704 s
  en deux fenêtres ; une en réseau normal, une dans un namespace réseau isolé) :
  elles déclaraient encore une durée native de 47,7 s et sont **dépassées**.
  Un appel natif unique sur un recadrage de 45 s de parole synthétique répétitive
  a ensuite été arrêté par le moteur (« output repetition », statut 19) : la
  durée native a donc été **retirée** et le runner découpe en fenêtres de 30 s.
- Configuration finale, `rejouer-hors-ligne.sh` : namespace réseau Linux isolé
  (`unshare -rn`, accès externe vérifié impossible : code HTTP 000, consigné dans
  `rejeu-fenetres.log`), serveur `uv run --offline`, trois audios (10,7 s, 45 s
  recadrés, 47,7 s) tous en fenêtres de 30 s (1, 2 et 2 fenêtres), exécution
  `20261103-150154-1bb5e17b` : statut `ok` partout, RTF ≈ 0,16–0,17, pic mémoire
  ≈ 1,4 Gio, 4 threads demandés, backend et périphérique relus CPU.
- Transcription non vide comme contrôle technique ; **aucune évaluation de la
  qualité** (le texte français est approximatif sur la parole synthétique).
- Limites : pas d'horodatage ni de segments (capacité du moteur `none`) ; langue
  imposée `fr` plutôt qu'auto-détection ; décodage laissé aux défauts du moteur
  (consigné) ; risque résiduel d'arrêt par détection de répétition sur une
  fenêtre ; aucune durée native ; pas de contrôle visuel humain ; Windows non
  couvert (aucun job CI Qwen3-ASR).
- Preuves locales, hors Git : `data/feasibility/validation-qwen3-asr/`.

## Parcours à froid du guide utilisateur — 2026-11-13

PC de test Linux déclaré (Manjaro x86_64, noyau 6.18.55-1-MANJARO, T14s,
Ryzen 7 PRO 6850U, 32 Gio de RAM), lot accepté par le propriétaire :
transcribe.cpp, `handy-computer/whisper-large-v3-turbo-gguf` fichier
`whisper-large-v3-turbo-Q5_K_M.gguf`, audio synthétique, copie vierge du
dépôt (archive ZIP de 1,1 Mo téléchargée depuis GitHub, décompressée), dossier
de données neuf. `uv` 0.11.8 déjà installé (son installation n'a pas été
suivie). Suivi intégral de `docs/guide-utilisateur.md`, étapes 3 à 12 ;
parties navigateur (étapes 6 à 11) suivies dans un navigateur réel.

- Étape 5 : premier lancement (`uv run --locked transcription-bench`) —
  environnement préparé (Python 3.12.13, 26 éléments, tous pris dans le cache
  local de la machine, aucun téléchargement visible), ligne « Interface
  disponible » affichée. Constat utile : le port 8765 était occupé par un
  autre programme de la machine (Thunderbird) — le cas de dépannage du guide,
  rencontré pour de vrai ; message réel « impossible d'écouter sur
  http://127.0.0.1:8765 : [Errno 98] Address already in use. Vérifiez qu'aucun
  autre programme n'utilise ce port… ». Solution du guide appliquée
  (`--port 8080`), sans toucher à l'autre programme.
- Étapes 6 à 11 dans le navigateur : `essai.wav` (10,7 s) listé après
  **Actualiser** ; installation de transcribe.cpp par la page ≈ 1 s (éléments
  en cache) ; vérification du dépôt ≈ 40 s, première réponse « Dépôt refusé
  (fichier-gguf-non-choisi) » avec les cinq variantes — déroulement normal,
  pas une erreur ; vérification de la variante ≈ 50 s ; téléchargement des
  590,9 Mio en ≈ 6 s ; deux exécutions du même modèle sur le même audio
  (5,841 s et 5,923 s, aucun second téléchargement) ; lecture du résultat
  (texte ≈ 230 caractères, lisible) ; comparaison des deux essais.
- Étape 12 : arrêt par le signal d'interruption de Ctrl+C — message
  « Arrêt du serveur. » vérifié, port libéré.
- Réseau réel observé : archive ZIP GitHub ≈ 1 Mo ; premier lancement et
  installation du moteur sans téléchargement visible (cache de la machine) ;
  lectures distantes pour la vérification du modèle (Hugging Face) ;
  téléchargement de 590,9 Mio. Aucun audio ni transcription n'a quitté la
  machine.

Écarts relevés entre le guide et l'application, tous corrigés dans le guide :
panneau **Ajouter un modèle** refermé après la vérification (résultat après
**Actualiser**), attente des vérifications distantes, déroulement normal « Dépôt
refusé (fichier-gguf-non-choisi) », emplacement de « Consulter le journal
d'installation » (bloc « Versions installées »), bouton **Installer ce moteur**
restant affiché sur un moteur prêt, libellé « Utiliser ce modèle pour préparer
une exécution. », durées désormais mesurées, distinction « meilleur temps » sur
valeurs exactes malgré un affichage arrondi identique, libellé réel « RTF
(durée de transcription / durée décodée) » au lieu de « rapport de vitesse »,
tri par défaut « Plus rapides » sur la page de comparaison, durée d'exécution
lisible dans l'historique (« Début » sans « Fin » dans l'opération), décalage
passager entre historique et section **Opération longue**.

Limites : `uv` déjà installé (installation non suivie) ; décompression par
l'explorateur non suivie ; clonage Git non suivi ; Windows hors de ce parcours ;
durées propres à cette machine et à cette connexion ; qualités de transcription
non évaluées. Éléments du journal d'installation : deux lignes Vulkan
(`ggml_vulkan`, GPU AMD Radeon) signalées par la roue native — exécution CPU
confirmée par les relevés du projet, conformément à `licences-modeles.md`.
