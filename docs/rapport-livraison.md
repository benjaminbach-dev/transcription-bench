# Rapport de livraison — prototype transcription-bench

Date : 2026-11-02, mis à jour le 2026-11-03 (8.2, revue advisor). Ce rapport constate l'état de livraison au niveau de chaque
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
| Installation des trois moteurs depuis les verrous, imports, runner et adaptateurs exercés | CI Windows | run `41477235301` (`c3f48ca`), trois jobs succès, rapports `installation-*.json` ; roues arrêtées par `uv.lock` versionné, téléchargements relevés dans le journal du run |
| Sonde voix système avant inférence | CI Windows | job `parole` des runs `41478535615` à `41480997693` : voix `Microsoft David Desktop`, culture `en-US`, texte `en`, empreinte SHA-256 vérifiée |
| Inférence courte des quatre combinaisons | CI Windows | runs `41478535615` (faster-whisper), `41479081739` (transcribe.cpp GGUF Whisper), `41480184141` (Transformers Whisper), `41480997693` (Transformers Parakeet TDT) : transcriptions non vides, CPU relu, 4 threads, timings natifs conservés pour transcribe.cpp |
| Adaptateurs réels sous Linux (8.1 à 8.3) | qualification Linux sur PC de test | parcours du jalon 0 consignés dans `docs/validation-linux.md` et la mémoire projet ; six exécutions réelles hors ligne, verrous et empreintes ; seconde architecture GGUF Qwen3-ASR-0.6B qualifiée le 2026-11-03 (`docs/validation-linux.md`) |
| Qualification Linux du serveur, arrêts, refus de concurrence | qualification Linux sur PC de test | `docs/validation-linux.md` (PC, 2026-11-02) ; limites : PTY automatisé, pas de console humaine |
| Preuves CI consignées | CI Windows | tableau des runs et rapports JSON dans `docs/ci-windows.md`, artéfacts 14 jours, copies locales `data/ci/rapports/` hors Git |
| Documentation de lancement | documentaire | `README.md` à jour, `AGENTS.md` adapté au contexte CI relu puis rechargé ; `openspec validate add-benchmark-prototype --strict` sans erreur |
| Limites hors CI consignées avec procédure | documentaire | `docs/ci-windows.md`, sections « Limites » et « Procédure de levée » (10.8) |
| Audit de publication et gate | décision utilisateur | `docs/audits/publication-2026-11-02.md` avec conclusion après publication (contrôles exécutés, risques assumés, contrôles non exécutés) ; décisions consignées dans la mémoire projet : publication de l'historique existant assumée, dépôt public depuis le 2026-11-02 |

## État : critères satisfaits, clôture en attente de décision

Mise à jour du 2026-11-03. Le reliquat 8.2 est levé : la seconde architecture
GGUF de transcribe.cpp, **Qwen3-ASR-0.6B (Q8_0)**, choisie par l'utilisateur, a
été téléchargée et qualifiée sur le PC Linux de test (vérification,
téléchargement et deux exécutions par les formulaires HTTP, dont une dans un
namespace réseau isolé ; voir `docs/validation-linux.md`). 11.4 est recochée
et les 55 tâches sont cochées. Tous les critères de la section 11 sont donc
satisfaits **à leur niveau de preuve**, ce qui n'est pas une validation
clinique ni une qualification du PC Windows de l'utilisateur.

Limites propres à cette qualification : Qwen3-ASR n'est vérifiée que sous
Linux (aucun job CI Windows, le périmètre CI de 10.6 restant les quatre
combinaisons d'origine) ; aucune durée native n'est déclarée (un appel unique
de 45 s a été arrêté par le moteur pour répétition) et l'audio est découpé en
fenêtres de 30 s ; elle n'a ni horodatage ni segment ; la langue est imposée à
`fr` ; la qualité n'est pas évaluée. La coche de 11.4 est maintenue après la
revue advisor du 2026-11-03 ; seuls restent en attente la relecture de
l'utilisateur et la clôture du change (archivage OpenSpec), qui n'a lieu que sur
sa décision explicite.

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

## Note du 2026-11-03

Le lancement et l'usage de l'outil sont désormais décrits dans le [guide utilisateur](guide-utilisateur.md) ; la ligne « Documentation de lancement » du tableau ci-dessus est une preuve historique du 2026-11-02 et renvoie à l'ancien `README.md`, dont le contenu technique a été repris dans [la documentation technique](technique.md).
