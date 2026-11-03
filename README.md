# transcription-bench

Outil local pour **comparer des modèles de transcription de la parole en français**.
Vous déposez des enregistrements, vous lancez la transcription avec un ou plusieurs
modèles, puis vous comparez les textes obtenus dans une page web ouverte sur votre
propre ordinateur. Tout le travail se fait sur le processeur, sous Linux ou Windows
(64 bits), sans carte graphique.

**Ce n'est pas un produit clinique validé.** Une transcription qui se lit bien peut
être fausse : aucun résultat produit ici ne doit être présenté comme médicalement
correct. Vos audios et vos transcriptions ne sont envoyés à aucun service ; Internet
ne sert qu'à installer l'outil, à installer un moteur (le programme qui fait tourner
un modèle) et à vérifier puis télécharger les modèles (le guide détaille chaque cas).

## Pour commencer

Lisez le [guide utilisateur](docs/guide-utilisateur.md) : il explique, étape par
étape, comment installer, lancer, transcrire un premier audio et comparer deux
résultats, avec un glossaire et un dépannage.

Une fois l'outil de lancement `uv` installé, la commande de lancement est, depuis le
dossier du projet :

```sh
uv run --locked transcription-bench
```

Elle affiche une adresse (`http://127.0.0.1:8765`) à ouvrir dans votre navigateur.

## Pour les développeurs

- [Documentation technique](docs/technique.md) : état des validations, choix
  techniques, arrêt du serveur, limites, vérifications Windows et publication.
- [Licences et provenances des modèles et des feuilles de style](docs/licences-modeles.md).

## Licence

Le code est distribué sous [licence MIT](LICENSE). Les dépendances et les modèles
conservent leurs propres licences ; aucun modèle n'est redistribué dans ce dépôt.
