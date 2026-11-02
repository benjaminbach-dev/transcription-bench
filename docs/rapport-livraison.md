# Rapport de livraison — prototype transcription-bench

Date : 2026-11-02. Ce rapport constate l'état de livraison au niveau de chaque
preuve, conformément aux critères vérifiables du change OpenSpec
`add-benchmark-prototype`. Le prototype reste un outil de comparaison locale de
modèles de transcription sur CPU ; **ce n'est pas un produit clinique validé**
et aucune transcription fluide ne doit être présentée comme médicalement
correcte.

## Critères et preuves

| Critère | Niveau de preuve | Preuve |
|---|---|---|
| Suite de tests sous Linux | serveur de développement (moteur factice) | 698 tests OK en local à chaque itération, suite `unittest`, hors ligne |
| Suite de tests sous Windows CI | CI Windows | run `41472430238` (`d9ee207`), `ubuntu-24.04` + `windows-2022`, 698 tests chacun, succès |
| Installation des trois moteurs depuis les verrous, imports, runner et adaptateurs exercés | CI Windows | run `41477235301` (`e5927d8`), trois jobs succès, rapports `installation-*.json` |
| Sonde voix système avant inférence | CI Windows | job `parole` des runs `41478535615` à `41480997693` : voix `Microsoft David Desktop`, culture `en-US`, texte `en`, empreinte SHA-256 vérifiée |
| Inférence courte des quatre combinaisons | CI Windows | runs `41478535615` (faster-whisper), `41479081739` (transcribe.cpp GGUF Whisper), `41480184141` (Transformers Whisper), `41480997693` (Transformers Parakeet TDT) : transcriptions non vides, CPU relu, 4 threads, timings natifs conservés pour transcribe.cpp |
| Adaptateurs réels sous Linux (8.1, 8.3) | qualification Linux sur PC de test | parcours du jalon 0 consignés dans `docs/validation-linux.md` et la mémoire projet ; six exécutions réelles hors ligne, verrous et empreintes |
| Qualification Linux du serveur, arrêts, refus de concurrence | qualification Linux sur PC de test | `docs/validation-linux.md` (PC, 2026-11-02) ; limites : PTY automatisé, pas de console humaine |
| Preuves CI consignées | CI Windows | tableau des runs et rapports JSON dans `docs/ci-windows.md`, artéfacts 14 jours, copies locales `data/ci/rapports/` hors Git |
| Documentation de lancement | documentaire | `README.md` à jour, `AGENTS.md` adapté au contexte CI relu puis rechargé ; `openspec validate add-benchmark-prototype --strict` sans erreur |
| Limites hors CI consignées avec procédure | documentaire | `docs/ci-windows.md`, sections « Limites » et « Procédure de levée » (10.8) |
| Audit de publication et gate | décision utilisateur | `docs/audits/publication-2026-11-02.md`, décisions consignées dans la mémoire projet : publication de l'historique existant assumée, dépôt public depuis le 2026-11-02 |

## État : partiel, un reliquat ouvert

Tous les critères de livraison vérifiables (11.1 à 11.6) sont satisfaits. Un
point reste ouvert : **8.2**, en son seul reliquat identifié par la note de
reprise : la seconde architecture GGUF de transcribe.cpp (Qwen3-ASR ou
Parakeet) à choisir et qualifier sur le PC de test, ou à reporter explicitement.
L'adaptateur transcribe.cpp et la vérification GGUF Whisper sont déjà écrits et
validés ; la CI a d'ailleurs exécuté cette combinaison avec succès. En
conséquence :

- la livraison est **partielle**, aucun critère manquant n'est présenté comme
  couvert, aucune clôture automatique n'a lieu ;
- la décision de réviser le périmètre (report de 8.2 ou exécution sur PC)
  appartient à l'utilisateur.

## Garanties non fournies

Aucune performance CI n'est représentative d'un PC utilisateur ; aucune mesure
n'est une promesse de résultat de transcription. Les vérifications CI
n'exercent que les options hors ligne, sans preuve de coupure réseau ; Ctrl+C
en console Windows réelle et coupure réseau système restent non couverts, avec
leur procédure de levée consignée. Le PC Windows de l'utilisateur n'est pas
qualifié. Les essais CI vérifient le logiciel, jamais la qualité des modèles :
transcription non vide comme contrôle technique, sans mot attendu ni score.

## Preuves brutes

Artéfacts GitHub Actions des runs listés (14 jours), copies locales sous
`data/ci/rapports/<run>/` (hors Git), compte rendu Linux dans
`docs/validation-linux.md`, audits dans `docs/audits/`.
