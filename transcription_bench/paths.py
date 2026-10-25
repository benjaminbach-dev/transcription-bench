"""Dossiers de données locaux et résolution contrôlée des noms et identifiants.

Les dossiers de données vivent sous `data/` à la racine du projet, et non sous
le dossier courant : lancer la commande depuis un sous-dossier ne disperse pas
les données. La base reste hors Git. Ce module fournit la préparation de ces
dossiers ainsi que la résolution des noms d'audios, des identifiants de
résultats et des identifiants de modèles reçus plus tard de l'utilisateur.

Point d'intégration des lots suivants : aucune route ni aucun service actuel ne
reçoit de nom de fichier ou d'identifiant. Les couches modèles (lot 5), audios et
exécutions (lot 6) puis résultats (lot 7) appelleront `resoudre_audio`,
`resoudre_resultat` et `valider_identifiant_modele` avec le dossier de données
de la configuration, avant tout accès au système de fichiers, et traduiront
`ValeurRefusee` en réponse 4xx sans action.

Ces contrôles ne constituent pas une sandbox : ils refusent les formes
dangereuses connues et renvoient le chemin déjà résolu avant l'accès, sans
prétendre protéger contre une modification concurrente du système de fichiers
(TOCTOU). La menace visée reste celle d'un outil local mono-utilisateur.
"""

from __future__ import annotations

import re
from pathlib import Path, PurePosixPath, PureWindowsPath

RACINE_PROJET = Path(__file__).resolve().parent.parent
DOSSIER_DATA = RACINE_PROJET / "data"

NOM_DOSSIER_AUDIO = "audio"
NOM_DOSSIER_MODELES = "models"
NOM_DOSSIER_MOTEURS = "engines"
NOM_DOSSIER_RESULTATS = "results"
DOSSIERS_DATA = (
    NOM_DOSSIER_AUDIO,
    NOM_DOSSIER_MODELES,
    NOM_DOSSIER_MOTEURS,
    NOM_DOSSIER_RESULTATS,
)

# Composant d'identifiant Hugging Face : 1 à 96 caractères ASCII, commençant et
# finissant par une lettre, un chiffre ou un souligné, comme le client
# huggingface_hub 2.3 (règle documentée de `validate_repo_id`).
_MOTIF_COMPOSANT_MODELE = re.compile(r"\w(?:[\w.-]{0,94}\w)?", re.ASCII)


class ValeurRefusee(ValueError):
    """Nom, chemin ou identifiant refusé avant tout accès au système de fichiers.

    Hérite de `ValueError` : un appelant qui attrape `ValueError` reste correct,
    tandis que les couches futures peuvent distinguer un refus explicite d'une
    autre erreur de valeur.
    """


def preparer_dossiers_data(base: Path | str | None = None) -> dict[str, Path]:
    """Crée les dossiers de données manquants et renvoie leurs chemins.

    `base` vaut `DOSSIER_DATA` (`data/` à la racine du projet) par défaut ; il
    n'est fourni que par les tests. Idempotent : un dossier existant est
    conservé tel quel et aucun fichier qu'il contient n'est écrasé.
    """
    racine = DOSSIER_DATA if base is None else Path(base)
    chemins: dict[str, Path] = {}
    for nom in DOSSIERS_DATA:
        chemin = racine / nom
        chemin.mkdir(parents=True, exist_ok=True)
        chemins[nom] = chemin
    return chemins


def resoudre_audio(nom: str, donnees: Path | str | None = None) -> Path:
    """Résout un nom d'audio sous `data/audio` (ou sous `donnees/audio`).

    `donnees` est la racine des données (`data/`) ; sa valeur par défaut est
    celle du projet. Aucun fichier n'est créé ni lu ici : le chemin renvoyé est
    absolu, résolu et vérifié comme restant sous le dossier autorisé.
    """
    racine = _racine_donnees(donnees) / NOM_DOSSIER_AUDIO
    return resoudre_dans_racine(racine, nom)


def resoudre_resultat(identifiant: str, donnees: Path | str | None = None) -> Path:
    """Résout un identifiant de résultat sous `data/results`.

    L'identifiant d'une exécution créée par le programme est un simple nom de
    dossier (`AAAAMMJJ-HHMMSS-<court-id>`) ; les fichiers internes déjà nommés
    par le programme (par exemple `run.json`) peuvent être ajoutés en chemin
    relatif. Dans tous les cas, le résultat reste sous le dossier des résultats.
    """
    racine = _racine_donnees(donnees) / NOM_DOSSIER_RESULTATS
    return resoudre_dans_racine(racine, identifiant)


def resoudre_dans_racine(racine: Path | str, chemin_relatif: str) -> Path:
    """Résout `chemin_relatif` et vérifie qu'il reste sous `racine`.

    Refusés : chemin absolu (POSIX ou Windows, y compris lecteur et UNC),
    séparateur Windows `\\` (ambiguïté entre plateformes), composant vide, `.`
    ou `..` même si la remontée aboutissait encore dans la racine, et lien
    symbolique sortant. Renvoie un chemin absolu résolu, avant tout accès.
    """
    parties = _parties_relatives(chemin_relatif)
    try:
        racine_resolue = Path(racine).resolve()
        cible = racine_resolue.joinpath(*parties).resolve()
    except (OSError, RuntimeError):
        raise ValeurRefusee(
            f"chemin refusé : racine ou lien symbolique non résoluble ({chemin_relatif!r})"
        ) from None
    if not cible.is_relative_to(racine_resolue):
        raise ValeurRefusee(
            f"chemin refusé : sort du dossier autorisé ({chemin_relatif!r})"
        )
    return cible


def valider_identifiant_modele(identifiant: str) -> str:
    """Valide un identifiant Hugging Face `nom` ou `org/nom` et le renvoie.

    Reprend les règles documentées du client huggingface_hub 2.3 : un ou deux
    composants de 1 à 96 caractères ASCII (`[A-Za-z0-9_.-]`), sans `--`, `..`
    ni suffixe `.git`, sans espace ni caractère non ASCII ni traversée de
    chemin. Le stockage local et la conversion éventuelle des identifiants sans
    organisation seront fixés avec le lot 5 ; rien n'en est déduit ici.
    """
    if not isinstance(identifiant, str):
        raise ValeurRefusee("identifiant de modèle attendu sous forme de texte")
    parties = identifiant.split("/")
    if len(parties) not in (1, 2):
        raise ValeurRefusee(
            f"identifiant de modèle refusé : forme 'nom' ou 'organisation/nom' attendue ({identifiant!r})"
        )
    if not all(_MOTIF_COMPOSANT_MODELE.fullmatch(partie) for partie in parties):
        raise ValeurRefusee(
            "identifiant de modèle refusé : 1 à 96 caractères ASCII "
            "alphanumériques, '_', '-' ou '.' par composant, sans espace "
            f"({identifiant!r})"
        )
    if "--" in identifiant or ".." in identifiant or identifiant.endswith(".git"):
        raise ValeurRefusee(
            f"identifiant de modèle refusé : '--', '..' ou suffixe '.git' ({identifiant!r})"
        )
    return identifiant


def _racine_donnees(donnees: Path | str | None) -> Path:
    return DOSSIER_DATA if donnees is None else Path(donnees)


def _parties_relatives(chemin: str) -> tuple[str, ...]:
    """Découpe un chemin relatif portable, en refusant les formes ambiguës."""
    if not isinstance(chemin, str):
        raise ValeurRefusee("nom de fichier attendu sous forme de texte")
    if not chemin or "\x00" in chemin:
        raise ValeurRefusee("nom de fichier vide ou invalide")
    if "\\" in chemin:
        raise ValeurRefusee(
            f"nom refusé : séparateur Windows '\\' interdit ({chemin!r})"
        )
    if ":" in chemin:
        raise ValeurRefusee(
            f"nom refusé : ':' interdit (lecteur, flux ou ambiguïté Windows) ({chemin!r})"
        )
    if PurePosixPath(chemin).is_absolute() or PureWindowsPath(chemin).is_absolute():
        raise ValeurRefusee(f"chemin absolu refusé ({chemin!r})")
    parties = chemin.split("/")
    if any(partie in ("", ".", "..") for partie in parties):
        raise ValeurRefusee(
            f"chemin refusé : composant vide, '.' ou '..' ({chemin!r})"
        )
    return tuple(parties)
