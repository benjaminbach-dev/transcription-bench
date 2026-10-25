"""Règles de compatibilité des modèles, sans moteur, sans réseau et sans E/S.

Ce module décide si un dépôt Hugging Face correspond au moteur choisi, à partir
de la seule liste de ses fichiers et du contenu déjà lu des petits JSON de
configuration. Il ne lit aucun fichier, n'appelle aucun service, ne télécharge
rien et n'importe aucun paquet moteur : la consultation distante (`model_info`,
lecture des petits JSON) appartient à la tâche 5.3, le choix du fichier GGUF à la
tâche 5.2 et le téléchargement à la tâche 5.4.

Règles implémentées ici, appelées par `DeclarationAdaptateur.regle_compatibilite`
(une seule source de vérité, aucun second registre) :

- `ctranslate2-whisper` (faster-whisper) : format CTranslate2 de la famille
  Whisper. Sont requis `model.bin`, `config.json`, `preprocessor_config.json` et
  `tokenizer.json`, plus, s'ils existent, `vocabulary.json` ou `vocabulary.txt`.
  `tokenizer.json` est exigé parce que son absence fait basculer faster-whisper
  v1.2.1 sur `tokenizers.Tokenizer.from_pretrained("openai/whisper-tiny")`,
  c'est-à-dire sur un accès réseau implicite ; `vocabulary.*` vient de la liste
  `allow_patterns` de `faster_whisper.utils.download_model` (v1.2.1) et reste
  facultatif. La sonde 1.6 doit rejouer ces choix sur PC.
- `transformers-safetensors` (Transformers) : familles Whisper et Parakeet TDT
  seulement, via une correspondance explicite `model_type` → famille
  (`whisper` → `whisper`, `parakeet_tdt` → `parakeet-tdt`). La décision repose sur
  le type de modèle déclaré et sur une liste blanche de fichiers **par famille**,
  jamais sur la seule absence d'`auto_map`. Un `auto_map` dans n'importe lequel
  des petits JSON inspectés (`config.json`, `generation_config.json`,
  `preprocessor_config.json`, `processor_config.json`, `tokenizer_config.json`)
  est un motif de refus.
  - Whisper requiert `config.json`, `generation_config.json`, un prétraitement
    (`preprocessor_config.json`, ou `processor_config.json` portant un
    `feature_extractor` imbriqué), `tokenizer.json` et `tokenizer_config.json`.
    La génération est requise pour la langue : dans `transformers` v5.20.2,
    `generation_whisper.py` (lignes 1411 et 1448) lit la configuration de
    génération pour les horodatages et pour `lang_to_id` en français. Restent
    facultatifs `vocab.json`, `merges.txt`, `normalizer.json`,
    `added_tokens.json` et `special_tokens_map.json`.
  - Parakeet TDT requiert `config.json`, un prétraitement (`processor_config.json`
    avec `feature_extractor`, ou `preprocessor_config.json`), `tokenizer.json` et
    `tokenizer_config.json`. `generation_config.json` reste facultatif mais
    retenu quand il existe, car il porte notamment les paramètres de suppression
    de jetons ; `added_tokens.json` et `special_tokens_map.json` sont facultatifs.
    Les auxiliaires de vocabulaire Whisper (`vocab.json`, `merges.txt`,
    `normalizer.json`) sont ignorés pour cette famille.
  - Seuls les poids safetensors sont retenus, pour les deux familles : soit
    `model.safetensors`, soit `model.safetensors.index.json` avec ses shards
    vérifiés ; `.bin`, `.pt`, `.pth`, `.nemo`, `.gguf`, `.onnx` et `.h5` ne sont
    jamais sélectionnés, et un dépôt sans variante safetensors complète est refusé.

Restrictions fonctionnelles documentaires, non qualifiées ; les listes sont à
confirmer au jalon PC :

1. un tokenizer fourni seulement en `vocab.json` + `merges.txt`, sans
   `tokenizer.json`, est refusé, bien que la bibliothèque sache le lire ;
2. faster-whisper exige `preprocessor_config.json` pour **tous** les points de
   contrôle CTranslate2, ce qui refuse par exemple `Systran/faster-whisper-small`
   alors que la bibliothèque l'accepte, pas uniquement les modèles de type
   large-v3.

Ces restrictions sont documentaires et ne constituent pas une qualification PC.

État de qualification, à ne pas confondre avec un format reconnu : les trois
moteurs réels déclarent leurs familles `qualifiee=False` et aucune durée native
n'est annoncée. Une famille reconnue mais non qualifiée est donc refusée à
l'ajout avec la raison stable `famille-non-qualifiee`, qui reste distincte des
refus de format (`fichiers-manquants`, `whisper-non-converti`,
`poids-safetensors-absents`, `famille-hors-perimetre`, ...) et laisse `famille`
renseignée. Cette garde applique D9/D10 : une architecture non vérifiée reste
refusée à l'ajout. Les tests couvrent les chemins de succès avec des
déclarations synthétiques `qualifiee=True` ; aucune déclaration fournie ne
change de qualification.

Les listes de fichiers ci-dessous sont documentaires (documentation
faster-whisper v1.2.1, arborescences publiques `openai/whisper-large-v3-turbo` et
`nvidia/parakeet-tdt-0.6b-v3`, source `transformers` v5.20.2) : les fichiers
réellement requis, les quantifications acceptées et le comportement long-form
restent à valider par les tâches 1.4 à 1.6 puis 8.x sur PC. Rien ici ne coche un
jalon PC ni ne rend une famille exécutable.

Le contenu des petits JSON est fourni par l'appelant sous forme de texte ou
d'octets UTF-8, et non lu ici. L'inspection d'`auto_map` est un parcours
itératif, linéaire dans le JSON déjà décodé, borné seulement en profondeur : il
n'y a aucun plafond arbitraire de nœuds, car un `tokenizer_config.json` réel
(`openai/whisper-large-v3-turbo`, 1600 entrées `added_tokens_decoder`) dépasse
largement un tel plafond. La limite de taille en octets relève de la lecture
distante (tâche 5.3), pas de cette règle. Un JSON trop profond, ou dont le
décodage lève `RecursionError`, est refusé comme illisible. Les noms de fichiers
viennent du dépôt distant : ils sont validés comme chemins relatifs confinés (ni
absolu, ni remontée, ni séparateur Windows) avant toute sélection, pour que la
future construction de chemins locaux ne dépende pas d'un nom hostile. Ces
contrôles ne constituent pas une sandbox.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from engines.declarations import DeclarationAdaptateur, Famille, declarations_fournies

REGLE_CTRANSLATE2_WHISPER = "ctranslate2-whisper"
REGLE_TRANSFORMERS_SAFETENSORS = "transformers-safetensors"

RAISON_FICHIERS_MANQUANTS = "fichiers-manquants"
RAISON_FAMILLE_HORS_PERIMETRE = "famille-hors-perimetre"
RAISON_FAMILLE_NON_QUALIFIEE = "famille-non-qualifiee"
RAISON_CODE_DISTANT = "code-distant-auto-map"
RAISON_CONFIGURATION_ILLISIBLE = "configuration-illisible"
RAISON_CONFIGURATION_NON_INSPECTEE = "configuration-non-inspectee"
RAISON_WHISPER_NON_CONVERTI = "whisper-non-converti"
RAISON_POIDS_SAFETENSORS_ABSENTS = "poids-safetensors-absents"
RAISON_INDEX_INVALIDE = "index-safetensors-invalide"
RAISON_NOM_FICHIER_REFUSE = "nom-de-fichier-refuse"

RAISONS_REFUS: tuple[str, ...] = (
    RAISON_FICHIERS_MANQUANTS,
    RAISON_FAMILLE_HORS_PERIMETRE,
    RAISON_FAMILLE_NON_QUALIFIEE,
    RAISON_CODE_DISTANT,
    RAISON_CONFIGURATION_ILLISIBLE,
    RAISON_CONFIGURATION_NON_INSPECTEE,
    RAISON_WHISPER_NON_CONVERTI,
    RAISON_POIDS_SAFETENSORS_ABSENTS,
    RAISON_INDEX_INVALIDE,
    RAISON_NOM_FICHIER_REFUSE,
)

# faster-whisper / CTranslate2 (famille Whisper au premier jalon).
FICHIERS_REQUIS_FASTER_WHISPER = (
    "config.json",
    "model.bin",
    "preprocessor_config.json",
    "tokenizer.json",
)
FICHIERS_FACULTATIFS_FASTER_WHISPER = ("vocabulary.json", "vocabulary.txt")

# Transformers (familles Whisper et Parakeet TDT au premier jalon).
MODEL_TYPE_VERS_FAMILLE = {"whisper": "whisper", "parakeet_tdt": "parakeet-tdt"}
FICHIERS_CONFIGURATION_INSPECTES = (
    "config.json",
    "generation_config.json",
    "preprocessor_config.json",
    "processor_config.json",
    "tokenizer_config.json",
)
FICHIER_PREPROCESSEUR = "preprocessor_config.json"
FICHIER_PROCESSOR = "processor_config.json"
CHAMP_FEATURE_EXTRACTOR = "feature_extractor"
INDEX_SAFETENSORS = "model.safetensors.index.json"
POIDS_SAFETENSORS_UNIQUE = "model.safetensors"

# Listes blanches par famille : les auxiliaires Whisper ne valent pas pour Parakeet.
FICHIERS_REQUIS_TRANSFORMERS: dict[str, tuple[str, ...]] = {
    "whisper": (
        "config.json",
        "generation_config.json",
        "tokenizer.json",
        "tokenizer_config.json",
    ),
    "parakeet-tdt": ("config.json", "tokenizer.json", "tokenizer_config.json"),
}
FICHIERS_OPTIONNELS_TRANSFORMERS: dict[str, frozenset[str]] = {
    "whisper": frozenset(
        {
            "vocab.json",
            "merges.txt",
            "normalizer.json",
            "added_tokens.json",
            "special_tokens_map.json",
        }
    ),
    "parakeet-tdt": frozenset(
        {"generation_config.json", "added_tokens.json", "special_tokens_map.json"}
    ),
}
# Fichiers de configuration et de tokenizer communs ; les poids, l'index et les
# shards viennent exclusivement de `_selectionner_poids`, pour ne jamais retenir
# deux variantes de poids à la fois.
FICHIERS_TRANSFORMERS_COMMUNS = frozenset(
    {
        "config.json",
        "preprocessor_config.json",
        "processor_config.json",
        "tokenizer.json",
        "tokenizer_config.json",
    }
)

# Borne de profondeur de l'inspection d'`auto_map` (aucun plafond de nœuds).
PROFONDEUR_MAX_INSPECTION = 8


class RegleCompatibiliteInconnue(ValueError):
    """Règle non implémentée ici : transcribe.cpp (5.2), moteur factice, autre."""


class ResultatCompatibiliteInvalide(ValueError):
    """Résultat incohérent : erreur de programmation, jamais une donnée distante."""


@dataclass(frozen=True)
class ResultatCompatibilite:
    """Verdict stable rendu à l'appelant (routes et service de la tâche 5.3).

    `accepte=True` implique `raison is None` et `fichiers` non vide ;
    `accepte=False` implique une `raison` appartenant à `RAISONS_REFUS`, aucun
    fichier retenu et, quand ils sont connus, `fichiers_manquants`, la `famille`
    détectée et le `moteur_suggere`. Un moteur suggéré est informatif : il reste
    soumis à sa propre règle de compatibilité et à sa qualification.
    """

    accepte: bool
    famille: str | None
    fichiers: tuple[str, ...]
    raison: str | None
    message: str
    moteur_suggere: str | None = None
    fichiers_manquants: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.accepte, bool):
            raise ResultatCompatibiliteInvalide("accepte doit être un booléen")
        if self.accepte:
            if self.raison is not None or not self.fichiers:
                raise ResultatCompatibiliteInvalide(
                    "une acceptation n'a pas de raison de refus et retient des fichiers"
                )
        else:
            if self.raison not in RAISONS_REFUS:
                raise ResultatCompatibiliteInvalide(
                    f"raison de refus inconnue : {self.raison!r}"
                )
            if self.fichiers:
                raise ResultatCompatibiliteInvalide(
                    "un refus ne retient aucun fichier"
                )
        if not isinstance(self.message, str) or not self.message.strip():
            raise ResultatCompatibiliteInvalide("message attendu non vide")


class _Refus(Exception):
    """Refus interne converti en `ResultatCompatibilite`."""

    def __init__(
        self,
        raison: str,
        message: str,
        *,
        manquants: Sequence[str] = (),
        famille: str | None = None,
        moteur_suggere: str | None = None,
    ) -> None:
        super().__init__(message)
        self.raison = raison
        self.message = message
        self.manquants = tuple(manquants)
        self.famille = famille
        self.moteur_suggere = moteur_suggere


def verifier_compatibilite(
    declaration: DeclarationAdaptateur,
    fichiers: Sequence[str],
    *,
    configurations: Mapping[str, str | bytes] | None = None,
    declarations_connues: Sequence[DeclarationAdaptateur] | None = None,
) -> ResultatCompatibilite:
    """Vérifie un dépôt pour un moteur, sans E/S et sans réseau.

    `fichiers` est la liste des noms de fichiers du dépôt ; `configurations`
    associe le nom d'un petit JSON de configuration présent dans le dépôt à son
    contenu brut (texte ou octets UTF-8). Pour Transformers, le contenu de chaque
    JSON inspecté présent dans le dépôt est obligatoire : un fichier non
    inspectable n'est pas accepté. `declarations_connues` sert seulement à
    suggérer un autre moteur et vaut par défaut les déclarations fournies.

    Lève `RegleCompatibiliteInconnue` si la déclaration utilise une règle non
    implémentée ici (transcribe.cpp, moteur factice), et `TypeError` si la
    déclaration ou les tables d'entrée n'ont pas la forme attendue ; un nom de
    fichier non textuel est un refus (`nom-de-fichier-refuse`), pas une erreur.
    """
    if not isinstance(declaration, DeclarationAdaptateur):
        raise TypeError("déclaration d'adaptateur attendue")
    connues = (
        declarations_fournies()
        if declarations_connues is None
        else tuple(declarations_connues)
    )
    if configurations is None:
        contenus: Mapping[str, str | bytes] = {}
    elif isinstance(configurations, Mapping):
        contenus = configurations
    else:
        raise TypeError("configurations attendu sous forme de table nom → contenu")

    try:
        noms = _valider_fichiers(fichiers)
        if declaration.regle_compatibilite == REGLE_CTRANSLATE2_WHISPER:
            famille_id, retenus = _regle_faster_whisper(
                declaration, noms, contenus, connues
            )
        elif declaration.regle_compatibilite == REGLE_TRANSFORMERS_SAFETENSORS:
            famille_id, retenus = _regle_transformers(
                declaration, noms, contenus, connues
            )
        else:
            raise RegleCompatibiliteInconnue(
                "règle de compatibilité non implémentée ici : "
                f"{declaration.regle_compatibilite!r} (transcribe.cpp : tâche 5.2)"
            )
        famille = _famille_declaree(declaration, famille_id)
        if not famille.qualifiee:
            raise _Refus(
                RAISON_FAMILLE_NON_QUALIFIEE,
                f"format reconnu pour la famille {famille_id!r}, mais cette famille "
                f"n'est pas qualifiée pour le moteur {declaration.identifiant!r} : "
                "le jalon 0 sur PC et les tâches 8.x doivent d'abord la valider ; "
                "aucun modèle n'est accepté à l'ajout tant que la qualification "
                "n'est pas faite",
                famille=famille_id,
            )
    except _Refus as refus:
        return ResultatCompatibilite(
            accepte=False,
            famille=refus.famille,
            fichiers=(),
            raison=refus.raison,
            message=refus.message,
            moteur_suggere=refus.moteur_suggere,
            fichiers_manquants=refus.manquants,
        )

    return ResultatCompatibilite(
        accepte=True,
        famille=famille_id,
        fichiers=retenus,
        raison=None,
        message=(
            f"{len(retenus)} fichiers retenus pour la famille {famille_id!r} "
            f"du moteur {declaration.identifiant!r}"
        ),
    )


def _valider_fichiers(fichiers: Sequence[str]) -> tuple[str, ...]:
    """Valide et trie les noms de fichiers reçus du dépôt distant."""
    if isinstance(fichiers, (str, bytes)) or not isinstance(fichiers, Sequence):
        raise TypeError("liste de noms de fichiers attendue")
    noms: list[str] = []
    for nom in fichiers:
        if not isinstance(nom, str):
            raise _Refus(
                RAISON_NOM_FICHIER_REFUSE,
                f"nom de fichier non textuel : {nom!r}",
            )
        if not _nom_relatif_valide(nom):
            raise _Refus(
                RAISON_NOM_FICHIER_REFUSE,
                f"nom de fichier refusé : {nom!r} (chemin absolu, remontée, "
                "séparateur Windows, composant vide ou caractère interdit)",
            )
        noms.append(nom)
    return tuple(sorted(set(noms)))


def _nom_relatif_valide(nom: str) -> bool:
    """Chemin relatif POSIX confiné : ni absolu, ni `..`, ni ambiguïté Windows."""
    if not nom or "\x00" in nom or "\\" in nom or ":" in nom:
        return False
    if nom.startswith("/") or nom.endswith("/"):
        return False
    return all(partie not in ("", ".", "..") for partie in nom.split("/"))


def _lire_configurations(
    noms: Sequence[str],
    contenus: Mapping[str, str | bytes],
    *,
    exiger: bool,
) -> dict[str, Mapping[str, Any]]:
    """Lit les petits JSON inspectés présents et refuse tout `auto_map`.

    `exiger=True` (Transformers) rend obligatoire le contenu de chaque JSON
    inspecté présent dans le dépôt : sans lui, `auto_map` ne peut pas être
    écarté, donc rien n'est accepté. Pour faster-whisper, les contenus sont
    facultatifs et seuls ceux fournis sont inspectés.
    """
    lues: dict[str, Mapping[str, Any]] = {}
    for nom in FICHIERS_CONFIGURATION_INSPECTES:
        if nom not in noms:
            continue
        contenu = contenus.get(nom)
        if contenu is None:
            if exiger:
                raise _Refus(
                    RAISON_CONFIGURATION_NON_INSPECTEE,
                    f"{nom} doit être fourni pour être inspecté : sans son contenu, "
                    "l'absence d'auto_map ne peut pas être établie",
                )
            continue
        objet = _objet_json(contenu, nom)
        if _chercher_auto_map(objet, nom):
            raise _Refus(
                RAISON_CODE_DISTANT,
                f"{nom} déclare un auto_map : le dépôt exige du code personnalisé, "
                "qui n'est jamais exécuté ni téléchargé",
            )
        lues[nom] = objet
    return lues


def _objet_json(contenu: str | bytes, nom: str) -> Mapping[str, Any]:
    """Décode un petit objet JSON ; refuse tout ce qui n'est pas un objet."""
    if isinstance(contenu, bytes):
        try:
            contenu = contenu.decode("utf-8")
        except UnicodeDecodeError:
            raise _Refus(
                RAISON_CONFIGURATION_ILLISIBLE,
                f"{nom} illisible : octets non UTF-8",
            ) from None
    if not isinstance(contenu, str):
        raise _Refus(
            RAISON_CONFIGURATION_ILLISIBLE,
            f"{nom} illisible : contenu JSON attendu en texte ou en octets UTF-8, "
            f"reçu {type(contenu).__name__}",
        )
    try:
        valeur = json.loads(contenu)
    except ValueError:
        raise _Refus(
            RAISON_CONFIGURATION_ILLISIBLE, f"{nom} illisible : JSON invalide"
        ) from None
    except RecursionError:
        raise _Refus(
            RAISON_CONFIGURATION_ILLISIBLE,
            f"{nom} illisible : JSON trop profond pour être décodé",
        ) from None
    if not isinstance(valeur, dict):
        raise _Refus(
            RAISON_CONFIGURATION_ILLISIBLE,
            f"{nom} illisible : objet JSON attendu, reçu {type(valeur).__name__}",
        )
    return valeur


def _chercher_auto_map(valeur: Any, nom: str) -> bool:
    """Cherche une clé `auto_map` imbriquée, sans plafond de nœuds.

    Le parcours est itératif et linéaire dans le JSON déjà décodé : aucune
    récursion Python et aucun plafond arbitraire, pour ne pas refuser un fichier
    réel comme un `tokenizer_config.json` à 1600 entrées d'ajout de jetons. Seule
    la profondeur est bornée, faute de quoi un objet artificiellement profond
    ferait croître la pile de visite sans intérêt.
    """
    a_visiter: list[tuple[Any, int]] = [(valeur, 0)]
    while a_visiter:
        courant, profondeur = a_visiter.pop()
        if profondeur > PROFONDEUR_MAX_INSPECTION:
            raise _Refus(
                RAISON_CONFIGURATION_ILLISIBLE,
                f"{nom} dépasse la profondeur inspectable "
                f"({PROFONDEUR_MAX_INSPECTION} niveaux)",
            )
        if isinstance(courant, Mapping):
            if "auto_map" in courant:
                return True
            enfants: Sequence[Any] = tuple(courant.values())
        elif isinstance(courant, list):
            enfants = courant
        else:
            continue
        for enfant in enfants:
            if isinstance(enfant, (Mapping, list)):
                a_visiter.append((enfant, profondeur + 1))
    return False


def _famille_declaree(declaration: DeclarationAdaptateur, famille_id: str) -> Famille:
    for famille in declaration.familles:
        if famille.identifiant == famille_id:
            return famille
    raise _Refus(
        RAISON_FAMILLE_HORS_PERIMETRE,
        f"la famille {famille_id!r} n'est pas déclarée par le moteur "
        f"{declaration.identifiant!r}",
        famille=famille_id,
    )


def _regle_faster_whisper(
    declaration: DeclarationAdaptateur,
    noms: Sequence[str],
    contenus: Mapping[str, str | bytes],
    connues: Sequence[DeclarationAdaptateur],
) -> tuple[str, tuple[str, ...]]:
    """Format CTranslate2 Whisper : `model.bin` et fichiers requis présents."""
    famille_id = "whisper"
    if not any(famille.identifiant == famille_id for famille in declaration.familles):
        raise _Refus(
            RAISON_FAMILLE_HORS_PERIMETRE,
            f"la famille {famille_id!r} n'est pas déclarée par le moteur "
            f"{declaration.identifiant!r} : aucune règle CTranslate2 à appliquer",
            famille=famille_id,
            moteur_suggere=_suggerer_moteur(famille_id, declaration, connues),
        )

    configurations = _lire_configurations(noms, contenus, exiger=False)
    manquants = tuple(nom for nom in FICHIERS_REQUIS_FASTER_WHISPER if nom not in noms)
    if manquants:
        if "model.bin" in manquants and _depot_whisper_transformers(
            noms, configurations
        ):
            raise _Refus(
                RAISON_WHISPER_NON_CONVERTI,
                "dépôt Whisper au format Transformers (config.json Whisper et poids "
                "safetensors) proposé à faster-whisper : aucune conversion n'est "
                "lancée et model.bin CTranslate2 est requis",
                manquants=manquants,
                famille=famille_id,
                moteur_suggere=_suggerer_transformers(declaration, connues),
            )
        raise _Refus(
            RAISON_FICHIERS_MANQUANTS,
            "dépôt CTranslate2 incomplet pour faster-whisper : "
            + ", ".join(manquants),
            manquants=manquants,
            famille=famille_id,
        )

    retenus = tuple(
        nom
        for nom in noms
        if nom in FICHIERS_REQUIS_FASTER_WHISPER
        or nom in FICHIERS_FACULTATIFS_FASTER_WHISPER
    )
    return famille_id, retenus


def _depot_whisper_transformers(
    noms: Sequence[str], configurations: Mapping[str, Mapping[str, Any]]
) -> bool:
    """Le dépôt ressemble-t-il à un Whisper Hugging Face non converti ?"""
    if any(nom.endswith(".safetensors") for nom in noms):
        return True
    return configurations.get("config.json", {}).get("model_type") == "whisper"


def _regle_transformers(
    declaration: DeclarationAdaptateur,
    noms: Sequence[str],
    contenus: Mapping[str, str | bytes],
    connues: Sequence[DeclarationAdaptateur],
) -> tuple[str, tuple[str, ...]]:
    """Safetensors + `model_type` Whisper ou Parakeet TDT, liste blanche de famille."""
    if "config.json" not in noms:
        raise _Refus(
            RAISON_FICHIERS_MANQUANTS,
            "dépôt incomplet pour Transformers : config.json manquant",
            manquants=("config.json",),
        )
    configurations = _lire_configurations(noms, contenus, exiger=True)
    config = configurations["config.json"]
    type_modele = config.get("model_type")
    if not isinstance(type_modele, str) or not type_modele.strip():
        raise _Refus(
            RAISON_FAMILLE_HORS_PERIMETRE,
            "config.json sans model_type : la famille ne peut pas être vérifiée, "
            "et l'absence d'auto_map ne suffit pas à prouver la compatibilité",
        )
    famille_id = MODEL_TYPE_VERS_FAMILLE.get(type_modele)
    if famille_id is None:
        raise _Refus(
            RAISON_FAMILLE_HORS_PERIMETRE,
            f"type de modèle {type_modele!r} hors périmètre de l'adaptateur "
            "Transformers (Whisper et Parakeet TDT seulement au premier jalon) : "
            "extension future",
        )
    if not any(famille.identifiant == famille_id for famille in declaration.familles):
        raise _Refus(
            RAISON_FAMILLE_HORS_PERIMETRE,
            f"la famille {famille_id!r} n'est pas déclarée par le moteur "
            f"{declaration.identifiant!r}",
            famille=famille_id,
            moteur_suggere=_suggerer_moteur(famille_id, declaration, connues),
        )

    poids = _selectionner_poids(noms, contenus)
    _verifier_fichiers_requis_transformers(noms, configurations, famille_id)

    autorises = (
        FICHIERS_TRANSFORMERS_COMMUNS
        | set(FICHIERS_REQUIS_TRANSFORMERS[famille_id])
        | FICHIERS_OPTIONNELS_TRANSFORMERS[famille_id]
        | set(poids)
    )
    retenus = tuple(nom for nom in noms if nom in autorises)
    return famille_id, retenus


def _verifier_fichiers_requis_transformers(
    noms: Sequence[str],
    configurations: Mapping[str, Mapping[str, Any]],
    famille_id: str,
) -> None:
    """Exige les fichiers de la famille et un prétraitement utilisable."""
    requis = FICHIERS_REQUIS_TRANSFORMERS[famille_id]
    manquants = [nom for nom in requis if nom not in noms]
    if FICHIER_PREPROCESSEUR not in noms:
        processeur = configurations.get(FICHIER_PROCESSOR)
        if processeur is None or not isinstance(
            processeur.get(CHAMP_FEATURE_EXTRACTOR), Mapping
        ):
            manquants.append(FICHIER_PREPROCESSEUR)
    if manquants:
        raise _Refus(
            RAISON_FICHIERS_MANQUANTS,
            f"dépôt Transformers incomplet pour la famille {famille_id!r} : "
            + ", ".join(manquants)
            + (
                f" (ni {FICHIER_PREPROCESSEUR} ni "
                f"{CHAMP_FEATURE_EXTRACTOR} dans {FICHIER_PROCESSOR})"
                if FICHIER_PREPROCESSEUR in manquants
                else ""
            ),
            manquants=tuple(manquants),
        )


def _selectionner_poids(
    noms: Sequence[str], contenus: Mapping[str, str | bytes]
) -> tuple[str, ...]:
    """Retient les seuls poids safetensors, index et shards vérifiés compris."""
    if INDEX_SAFETENSORS in noms:
        contenu = contenus.get(INDEX_SAFETENSORS)
        if contenu is None:
            raise _Refus(
                RAISON_CONFIGURATION_NON_INSPECTEE,
                f"{INDEX_SAFETENSORS} doit être fourni pour vérifier ses shards",
            )
        index = _objet_json(contenu, INDEX_SAFETENSORS)
        poids_map = index.get("weight_map")
        if not isinstance(poids_map, Mapping) or not poids_map:
            raise _Refus(
                RAISON_INDEX_INVALIDE,
                f"{INDEX_SAFETENSORS} invalide : weight_map objet non vide attendu",
            )
        shards: list[str] = []
        for tenseur, shard in poids_map.items():
            if not isinstance(tenseur, str) or not isinstance(shard, str):
                raise _Refus(
                    RAISON_INDEX_INVALIDE,
                    f"{INDEX_SAFETENSORS} invalide : entrées weight_map attendues "
                    "sous forme de textes",
                )
            if not shard.endswith(".safetensors") or not _nom_relatif_valide(shard):
                raise _Refus(
                    RAISON_INDEX_INVALIDE,
                    f"{INDEX_SAFETENSORS} invalide : nom de shard refusé ({shard!r})",
                )
            shards.append(shard)
        manquants = tuple(sorted(set(shards) - set(noms)))
        if manquants:
            raise _Refus(
                RAISON_INDEX_INVALIDE,
                f"{INDEX_SAFETENSORS} incomplet : shards manquants",
                manquants=manquants,
            )
        return tuple(sorted({INDEX_SAFETENSORS, *shards}))
    if POIDS_SAFETENSORS_UNIQUE in noms:
        return (POIDS_SAFETENSORS_UNIQUE,)
    raise _Refus(
        RAISON_POIDS_SAFETENSORS_ABSENTS,
        "dépôt Transformers sans poids safetensors : un fichier model.safetensors "
        f"ou un index {INDEX_SAFETENSORS} avec ses shards est requis ; les variantes "
        ".bin, .pt, .pth, .nemo, .gguf, .onnx et .h5 ne sont ni téléchargés "
        "ni chargés",
    )


def _suggerer_moteur(
    famille_id: str,
    declaration: DeclarationAdaptateur,
    connues: Sequence[DeclarationAdaptateur],
) -> str | None:
    """Premier autre moteur déclarant cette famille, à titre d'indication."""
    for candidate in connues:
        if candidate.identifiant == declaration.identifiant:
            continue
        if any(famille.identifiant == famille_id for famille in candidate.familles):
            return candidate.identifiant
    return None


def _suggerer_transformers(
    declaration: DeclarationAdaptateur, connues: Sequence[DeclarationAdaptateur]
) -> str | None:
    """Moteur Transformers déclarant Whisper, pour un dépôt au format HF."""
    for candidate in connues:
        if candidate.identifiant == declaration.identifiant:
            continue
        if candidate.regle_compatibilite != REGLE_TRANSFORMERS_SAFETENSORS:
            continue
        if any(famille.identifiant == "whisper" for famille in candidate.familles):
            return candidate.identifiant
    return None
