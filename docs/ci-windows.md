# Vérifications Windows par GitHub Actions

## État

Dépôt public depuis le 2026-11-02 (décision et audit consignés) ; les jobs
sont exécutés. Preuves au niveau « CI Windows », image `windows-2022`,
conservées en artefacts pendant 14 jours et recopiées localement hors Git :

| Run | Commit | Contenu | Résultat |
|---|---|---|---|
| `41472430238` | `d9ee207` | suite de tests factice, Linux + Windows (698 tests chacun) | succès |
| `41477235301` | `c3f48ca` | imports : installation des trois moteurs depuis les verrous, contrôle d'import, runner factice exercé dans chaque venv | succès |
| `41478535615` | `e5927d8` | parole (voix `Microsoft David Desktop`, culture `en-US`, texte en, langue imposée `fr`, empreinte SHA-256 vérifiée) puis inférence faster-whisper : transcription non vide (165 caractères), CPU relu, 4 threads | succès |
| `41479081739` | `ab92616` | inférence transcribe.cpp GGUF Whisper : transcription non vide, timings natifs consignés, mmap, architecture et variante relues | succès |
| `41480184141` | `930d900` | inférence Transformers Whisper : transcription non vide, CPU relu, 4 threads | succès |
| `41480997693` | `3982ec0` | inférence Transformers Parakeet TDT : transcription non vide, sans langue forcée conformément au design | succès |

Les rapports JSON nettoyés de chaque run (commit, image `20261026.347.1`,
Python 3.12.10, uv 0.11.8, versions des moteurs, empreinte audio, ressources
mesurées vCPU/RAM/disque) sont conservés en artefacts 14 jours et recopiés
sous `data/ci/rapports/<run>/` localement, hors Git — y compris les contextes
`ressources.json` du run de tests et les rapports d'installation du run
d'imports. Roues retenues pour chaque moteur : arrêtées par `uv.lock` et
`requirements/*.txt` versionnés dans le dépôt ; versions principales relues
par l'adaptateur dans `installation-*.json` ; téléchargements observés dans le
journal du run d'imports (extrait local `roues-journaux.txt`, journal complet
sur GitHub pendant 14 jours). Aucun moteur ni poids n'a été installé sur le
serveur de développement : toutes les installations et inférences ont eu lieu
sur les runners éphémères.

Le dépôt avait été privé avant le 2026-11-02 : un run privé (`41461687022`)
s'était terminé « skipped » conformément au gate, sans valeur de preuve.

Écart de procédure à arbitrer (10.9) : les instructions CI ont été relues et
rechargées le 2026-11-02 à 16 h 48 (`c3f48ca`), **avant les jobs moteurs**
conformément à l'intention du contexte, mais **après les premiers runs de la
suite de tests** (16 h 04 et 16 h 31, sur `4905a9b` puis `d9ee207`). La
tâche 10.9 exige la relecture avant la première exécution de tout job CI.
La valeur technique des tests n'est pas annulée ; l'écart est consigné et
soumis à l'arbitrage du propriétaire.

- `.github/workflows/tests.yml` : tests avec moteur factice sous Ubuntu 24.04 et Windows Server 2022, après installation des seules dépendances serveur verrouillées.
- `.github/workflows/moteurs-windows.yml` : déclenchement manuel. Les imports installent les trois moteurs isolément depuis les verrous. Les inférences sélectionnables téléchargent chacune un seul des quatre modèles d'essai.
- `scripts/ci/verifier.py` : appelle les services d'installation, de vérification/téléchargement des modèles et d'exécution du programme ; le runner et les adaptateurs ne sont pas remplacés par une sonde de bibliothèque indépendante.
- `scripts/ci/generer-parole.ps1` : utilise une voix System.Speech locale activée, sans exiger le français. Sélection déterministe : anglais, sinon français, sinon première voix disponible ; texte anglais ou français selon cette sélection. Culture de la voix et langue du texte sont consignées séparément, y compris si elles diffèrent. Sans aucune voix, la sonde échoue avant les poids ; aucun service distant ni nouvelle dépendance n'est ajouté.

## Sécurité et coûts

Runners standards uniquement, image `windows-2022` ; son contenu évolue, d'où la conservation de `ImageOS` et `ImageVersion`. Toutes les actions sont épinglées par SHA, les permissions sont `contents: read`, les identifiants du checkout ne sont pas persistés. Aucun secret applicatif ni jeton Hugging Face n'est utilisé ; l'envoi implicite d'un jeton HF est désactivé. Cache `setup-uv` explicitement désactivé.

Les jobs lourds sont manuels, bornés et annulables lorsqu'une nouvelle exécution les remplace. Aucun poids, audio, environnement ni transcription n'est publié ou mis en cache par ces workflows. Seuls les résumés JSON nettoyés sous `data/ci/rapports/` sont conservés en artefacts pendant 14 jours. Ils consignent commit, image, versions, ressources, empreinte audio et résultat des vérifications, sans texte transcrit. Les données de travail restent sous `data/ci/` dans le job éphémère.

Les jobs sont conditionnés à la visibilité publique : sur dépôt privé ils sont ignorés, ce qui ne constitue jamais une preuve ni un succès de validation Windows. Le harnais refuse en plus les opérations moteurs hors contexte explicite Windows CI public. Ces vérifications sont des garde-fous logiciels, pas une isolation de sécurité. Le workflow de tests pourrait techniquement fonctionner sur un dépôt privé ; son activation privée n'est pas décidée ici. La gratuité du calcul public concerne uniquement les runners standards ; stockage et limites du compte restent à surveiller.

## Procédure après publication autorisée

1. Exécuter les tests Linux/Windows ; relever le commit, l'image et ses versions.
2. Déclencher le workflow moteurs avec les imports seuls (combinaison `aucune`). Un environnement est prêt seulement après synchronisation depuis son verrou et contrôle d'import, puis protocole du runner factice dans ce même environnement.
3. Sélectionner une combinaison réelle. Vérifier d'abord la présence d'une voix système locale, quelle que soit sa langue ; aucune voix française n'est requise. Sans voix, décider de la solution avant tout élargissement d'installation.
4. Le job vérifie et télécharge le modèle à révision figée par les services du programme. L'espace libre est contrôlé contre la taille connue avant téléchargement, sans garantir la marge nécessaire aux métadonnées et fichiers temporaires.
5. Le job crée sa propre parole synthétique et ses métadonnées JSON, puis lance le programme avec les options hors ligne. Le harnais vérifie l'empreinte du WAV et sa durée ; les preuves distinguent culture de voix, langue du texte et langue réellement imposée par le moteur. Une transcription non vide est un contrôle de fonctionnement uniquement : aucun mot attendu, score, comparaison de langue ou jugement sur le modèle. Une sortie vide rend le contrôle non concluant, sans diagnostiquer une mauvaise qualité du modèle. Les réglages de langue du programme restent inchangés.
6. Consigner les preuves ; ne cocher aucune tâche Windows avant les exécutions correspondantes. Une erreur de roue, d'import, de voix, de téléchargement ou d'inférence reste un échec, jamais un succès ignoré.

## Limites

L'image contient notamment des composants Visual C++ et ne représente pas un PC Windows neuf. Les imports réussis ne prouvent donc pas l'absence de prérequis système. Les options hors ligne ne constituent pas une coupure réseau. Une annulation GitHub n'est pas un test de Ctrl+C interactif. Les performances CI ne sont pas représentatives du PC utilisateur.

## Écarts constatés et corrections (8.4)

Premier passage de la suite sous Windows (`41467927122`, 20 échecs) puis
convergence en trois commits de correction (`c309448`, `13249ae`, `d9ee207`,
consignations ensuite) :

- Produit : `os.replace` du stockage atomique retenté sur `PermissionError`
  (un lecteur Windows peut détenir le fichier un instant) — c'est la protection
  des lectures/écritures visée par 10.3, exercée ensuite avec succès.
- Tests : encodage UTF-8 explicite des sorties de sous-processus ; chemins
  temporaires résolus (forme 8.3) ; `resource` réservé à Linux ; `CON.wav`
  créé et supprimé par préfixe `\\?\` ; PID du trampoline uv (parent de
  l'interpréteur réel) accepté ; codes de sortie Windows d'un arrêt (15, 1) ;
  attendu d'échappement web calculé depuis le chemin joint ; cache numba
  comparé par chemin.
- Specs : exigences de `platform-verification` scindées pour la validation
  OpenSpec stricte (11.6), sans changement de fond.

Aucun écart fonctionnel n'a été constaté entre les exigences et le comportement
observé sous Windows après ces corrections ; les limites ci-dessus restent
les bornes assumées.

## Procédure de levée des limites hors CI (non exécutée)

Si une console Windows interactive devient disponible, consigner OS, machine,
commit et versions, puis lancer `uv run --locked transcription-bench`. Démarrer
une opération factice sur audio synthétique ; envoyer Ctrl+C depuis le clavier,
puis refaire le scénario avec deux Ctrl+C rapprochés. Vérifier la clôture unique,
l'état interrompu, la libération du verrou et l'absence des seuls PID moteurs
suivis par le programme ; redémarrer sans intervention sur le fichier de verrou.
Ne pas arrêter des processus Python sans en avoir confirmé l'identité. Une
annulation Actions ne remplace pas ces manipulations. Leur état reste **non
exécuté sous Windows**.

Pour une coupure réseau réelle, installer et télécharger auparavant les seules
ressources autorisées. Après accord explicite sur l'opération système, isoler
la machine de ses interfaces réseau (méthode à définir sur ce Windows sans
couper une connexion distante nécessaire), constater l'absence de connectivité
externe, puis exécuter une transcription synthétique locale. Consigner méthode,
options hors ligne, résultat et limites, et rétablir la connexion selon l'accord.
Cette coupure Windows n'a pas été exécutée. Le niveau acquis en CI restera celui
des options hors ligne tant qu'aucune sonde d'isolation dédiée n'est validée.

## Sources documentaires

- [Runners hébergés](https://docs.github.com/en/actions/reference/runners/github-hosted-runners)
- [Image Windows 2022](https://github.com/actions/runner-images/blob/main/images/windows/Windows2022-Readme.md)
- [Intégration uv](https://docs.astral.sh/uv/guides/integration/github/)
- [Annulation des workflows](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-cancellation)

Les SHA d'actions ont été contrôlés sur les dépôts officiels pendant la préparation du 2026-11-02. La préparation statique et les tests locaux du harnais ne valent pas exécution de ces actions.
