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
leur namespace isolé). Windows, installation vierge et seconde architecture
GGUF restent non vérifiés par cette passe.
