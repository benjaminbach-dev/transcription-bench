# Transcription bench

Exploration d’une application de transcription médicale française entièrement locale et préparation d’un futur benchmark portable.

## État

Socle documentaire uniquement : aucun moteur installé, modèle téléchargé ou benchmark exécuté. Aucun résultat de performance n’est disponible. La pile technique et les systèmes cibles restent à choisir.

## Point d’entrée pour un agent

Lire `AGENTS.md`, puis les notes Markdown de `.basic-memory/` :

- `.basic-memory/projet/Cadrage et suite.md` : objectif, évolution du besoin, prochaine étape ;
- `.basic-memory/recherche/Écueils et arbitrages.md` : risques et corrections des hypothèses initiales ;
- `.basic-memory/recherche/Modèles et sources.md` : candidats et sources à revérifier ;
- `.basic-memory/bench/Protocole à définir.md` : questions et mesures du futur prototype.

Les notes sont versionnables et lisibles sans Basic Memory. L’enregistrement du projet auprès du serveur MCP est local à chaque machine, pas transporté par Git. Utiliser le serveur Basic Memory existant avec `project: transcription-bench` ; ne pas ajouter de serveur MCP dédié.

## Données et artefacts

Aucun audio de consultation, identifiant patient, secret, poids de modèle ou résultat brut sensible ne doit être committé. Les répertoires `data/`, `models/`, `results/`, `runs/` et `artifacts/` sont réservés aux fichiers locaux ignorés. L’ignorance Git n’est pas une protection de confidentialité suffisante : contrôler chaque ajout avant commit.

## Suite

Définir avec l’utilisateur le périmètre minimal du benchmark portable avant d’implémenter. L’application produit, le streaming et le fine-tuning ne sont pas des travaux autorisés par cette initialisation.
