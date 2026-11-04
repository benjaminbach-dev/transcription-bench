# Note d'usage : `tts_gemini.py`

Outil annexe, hors benchmark : génère un dialogue français à deux voix avec l'API Gemini (Google AI Studio). Un seul fichier, aucune dépendance.

## Préparer

1. Créer une clé dans Google AI Studio (API keys).
2. La définir dans le terminal, jamais dans un fichier du dépôt :

   ```sh
   export GOOGLE_API_KEY='votre-clé'
   ```

## Écrire le dialogue

Un fichier texte, une réplique par ligne, `A:` ou `B:` en début de ligne :

```
A: Bonjour, vous allez bien ?
B: Très bien, merci.
```

Limite : 1 200 mots (estimation, à valider). Au-delà, le script refuse.

## Lancer

```sh
uv run python scripts/tts_gemini.py dialogue.txt
uv run python scripts/tts_gemini.py dialogue.txt -o data/tts/essai.wav --voix-a Kore --voix-b Puck
uv run python scripts/tts_gemini.py dialogue.txt --dry-run   # affiche la requête, sans clé ni réseau
cat dialogue.txt | uv run python scripts/tts_gemini.py -     # lecture depuis stdin
```

- Sortie par défaut : `data/tts/dialogue.wav` (ignoré par Git).
- Voix : `Kore` (A) et `Puck` (B) par défaut. Les autres voix prébuilt se règlent avec `--voix-a` et `--voix-b`.
- Un `-o` relatif est résolu depuis le répertoire courant.

## Avant d'envoyer

- Utiliser uniquement des dialogues **fictifs**. L'offre gratuite peut servir à améliorer les produits Google.
- L'audio porte SynthID et ne doit pas servir à un usage clinique.
- Les quotas gratuits sont à vérifier dans AI Studio ; un 429 signale un quota atteint.

## Limites connues

- Pas encore testé avec une vraie clé : la forme exacte de la réponse et la qualité des voix françaises restent à valider à l'oreille.
- Maximum deux locuteurs par appel.
- Pas de découpage automatique : un texte trop long est refusé.
