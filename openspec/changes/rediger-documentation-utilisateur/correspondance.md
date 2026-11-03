# Correspondance de l'ancien README (350 lignes) vers la documentation

Établi le 2026-11-03 sur le README du commit `5c03627`. « Technique » = `docs/technique.md` (copie conservée telle quelle, sauf corrections notées) ; « Guide » = `docs/guide-utilisateur.md`.

| Section de l'ancien README | Emplacement actuel | Remarque |
|---|---|---|
| Introduction et avertissement clinique | README (court), Guide (début), Technique | reformulée en langage courant dans le guide |
| État réel du prototype | Technique | tableau conservé ; inutile pour l'utilisateur, résumé en une phrase dans le guide |
| Règle du serveur de développement | Technique | sans objet pour l'utilisateur ; le guide parle du « PC de test » seulement dans sa note de vérification |
| Prérequis (uv, accès réseau, Python 3.12) | Guide (prérequis, installation) + Technique | réécrite ; accès réseau décrits tels quels (design D9) ; `winget` ajouté |
| Lancement : une seule commande | Guide (lancement) + Technique | `--port` et port occupé repris dans le guide et le dépannage |
| Dossiers de données | Guide (dépôt des audios) + Technique | formats acceptés repris dans le guide |
| Utilisation avec le moteur factice | Technique | le guide utilise un modèle réel (design D5) ; le moteur factice reste documenté |
| Moteurs et modèles réels | Guide (moteur, modèle) + Technique | |
| Jeton Hugging Face | Technique | |
| Hors ligne | Technique | termes interdits au guide (`HF_HUB_OFFLINE`) |
| Arrêt du serveur | Guide (arrêt, relance) pour l'essentiel + Technique pour le détail | |
| Organisation du code et choix techniques | Technique | ligne « HTML seul, sans CSS ni JavaScript » corrigée (feuilles locales) |
| Limites connues | Guide (limites qui touchent l'utilisateur) + Technique | mention des durées natives corrigée : Qwen3-ASR n'a aucune durée native prouvée |
| Vérifications Windows et publication | Technique | |
| Licence | README + Technique | |

Aucune section n'est déclarée obsolète. Les liens relatifs de `docs/technique.md` ont été réécrits pour son nouvel emplacement.
