# Instructions — transcription-bench

## Périmètre et état

Répondre et documenter en français. Dépôt exploratoire destiné à un futur benchmark portable de transcription médicale locale. Aucun prototype, modèle ou résultat n’est encore livré. Ne pas choisir de pile, installer des dépendances, télécharger des poids, entraîner ou traiter des données médicales sans demande couvrant ces opérations.

Distinguer systématiquement : demande utilisateur, hypothèse produit, information publiée par un auteur, estimation et mesure locale. Les chiffres RAM/vitesse de la première conversation ne sont pas des résultats de benchmark. Ne pas transformer les propositions d’architecture en décisions validées.

## Mémoire du projet

Notes durables dans `.basic-memory/`, suivies par Git sur ce dépôt GitHub personnel. Utiliser le serveur MCP global `basic-memory` avec **`project: transcription-bench`** à chaque appel. Pas de second serveur MCP, ni configuration absolue propre à une machine dans le dépôt. Sur un autre poste, enregistrer ce projet vers le dossier `.basic-memory/` du clone ; l’enregistrement local ne voyage pas par Git.

Consulter d’abord `.basic-memory/projet/Cadrage et suite.md`, puis les notes pertinentes ; rechercher les doublons avant création et vérifier les faits actuels. `main` reste réservé au savoir transversal. Le principal seul écrit la mémoire ; les sous-agents reçoivent les extraits utiles. Aucun secret, transcript brut ou donnée patient dans les notes.

## Garde-fous

- Transcription, alignement temporel, diarisation et synthèse sont des fonctions distinctes.
- Ne pas promettre une précision clinique, un fonctionnement temps réel ou une compatibilité 8/16 Go sans mesure.
- Ne pas présenter « médical », « plusieurs passes » ou « contenu synthétique vérifié » comme une garantie de fidélité.
- Aucun audio, identifiant patient, poids ou résultat sensible dans Git. Utiliser les répertoires locaux ignorés et vérifier les ajouts explicitement.
- Ne pas envoyer d’audio ou de données médicales à un service externe sans autorisation spécifique.
- Aucun commit/push automatique : demander une autorisation explicite pour l’opération et la portée. Le premier push est prévu ultérieurement, pas autorisé par l’initialisation.

## Prochaine étape

Cadrer le prototype minimal : OS cibles, moteurs, formats, corpus autorisé, métriques, installation et reproductibilité. Pas de refonte produit ou d’entraînement par anticipation.

Après modification de ces instructions ou du MCP, demander `/reload`, puis vérifier dans la session rechargée ; ne pas lancer de session de test spontanée.
