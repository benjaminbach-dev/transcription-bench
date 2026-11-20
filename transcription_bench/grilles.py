"""Grilles d'extraction : découverte confinée, lecture bornée et interprétation.

Ce service couvre la tâche 1.1 du change `ajouter-bench-extraction` : lire les
grilles Markdown versionnées sous `grilles/` et les interpréter selon la
décision D1, sans écrire de fichier, sans réseau et sans dépendance. La
conversion en schéma (1.2), le gabarit de consignes (1.3), la grille d'exemple
et les commandes (1.4) consomment ce module et ne sont pas concernés ici.

Règles d'interprétation (design D1) :

- une grille est un fichier `grilles/<nom>.md`, UTF-8, au plus 64 Kio, dont le
  nom (sans extension) fait 1 à 64 caractères `[a-z0-9-]` en commençant par une
  lettre ou un chiffre. Le dossier `grilles/` est versionné : absent, il
  signifie « aucune grille » et n'est jamais créé ici ;
- le premier contenu non vide est un titre `# ` unique, le titre de la grille ;
  le texte avant le premier `## ` forme les consignes générales (facultatives) ;
- `## Libellé` ouvre une case, `### Libellé` sous une case ouvre une sous-case
  (la case devient composée) ; une case ou sous-case est une liste si la
  première ligne non vide de sa consigne, blancs de tête retirés, commence par
  le mot « Liste » (casse ignorée) suivi d'espaces facultatifs puis de `.` ou
  de `:`. `####` et plus profond, un `###` avant tout `##`, un second `#` ou
  l'absence de toute case sont refusés ;
- une ligne commençant (après au plus trois espaces) par ``` ou ~~~ ouvre un
  bloc de code fermé par une ligne commençant par la même clôture : les titres
  qu'il contient ne sont pas interprétés et restent du texte de consigne. Un
  bloc non fermé rend la grille invalide ;
- la clé de chaque case et sous-case suit la normalisation D1 (NFKD, marques
  diacritiques retirées, `œ`→`oe`, `æ`→`ae`, `ß`→`ss`, minuscules, suites hors
  `[a-z0-9]` réduites à un `_`, `_` de bord retirés). Une clé vide, un doublon
  au même niveau ou la clé réservée `autres_informations` sont refusés ; au
  plus 60 cases et sous-cases au total.

Une grille **invalide** n'est jamais une exception : la lecture rend un objet
portant l'état invalide avec son motif (ligne et règle en cause), et l'appelant
décide de ne pas la proposer à l'exécution. Les exceptions restent réservées
aux cas impossibles : `ValeurRefusee` (paths) pour un nom qui n'est pas une
grille du dossier, `GridUnreadable` pour un fichier impossible à lire. Une
seule erreur est rapportée, la première rencontrée ; les champs déjà
interprétés avant elle restent remplis dans l'objet rendu.

Choix assumés là où le design ne tranche pas (les plus simples, documentés
pour être rediscutables) : les titres ne sont reconnus qu'en début de ligne,
avec au moins un espace après les `#` et un libellé non vide (une ligne `##`
seule, `##Libellé` ou un titre indenté reste du texte de consigne, à la façon
de CommonMark) ; une ligne ferme un bloc dès qu'elle commence par la même
clôture, le reste de la ligne étant ignoré, et les lignes de délimitation
appartiennent au texte de consigne ; la clé réservée est refusée aussi pour
une sous-case ; le contenu est décodé en UTF-8 avec un éventuel BOM retiré
(`utf-8-sig`), l'empreinte portant toujours sur les octets bruts du fichier ;
les lignes sont découpées sur le seul saut de ligne LF, un retour chariot final étant
retiré (fins CRLF admises), de sorte que U+2028 ou U+0085 ne coupent jamais une
ligne et que les numéros de ligne suivent le fichier ; le texte des consignes
est conservé à l'identique, seuls les blancs et lignes vides des extrémités
étant retirés ; seule l'extension exacte `.md` désigne une grille. Ces
contrôles ne constituent pas une sandbox et ne couvrent pas une course TOCTOU :
un fichier peut changer entre la découverte, la lecture et l'exécution, comme
pour les audios.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import NoReturn

from transcription_bench.paths import (
    RACINE_PROJET,
    ValeurRefusee,
    resoudre_dans_racine,
)

#: Dossier versionné des grilles, à la racine du projet (jamais créé ici).
GRID_DIR_NAME = "grilles"
#: Nom d'une grille sans extension : 1 à 64 caractères, sans tiret en tête.
GRID_NAME_PATTERN = re.compile(r"[a-z0-9][a-z0-9-]{0,63}", re.ASCII)
#: Taille maximale d'un fichier de grille, en octets (64 Kio).
MAX_GRID_BYTES = 64 * 1024
#: Nombre maximal de cases et sous-cases, comptées ensemble.
MAX_FIELDS = 60
#: Clé réservée : la section « autres informations » est ajoutée d'office.
RESERVED_KEY = "autres_informations"
#: Erreur affichée pour un fichier `.md` du dossier au nom ou à la cible
#: refusés : il reste listé, jamais lu et jamais proposé à l'exécution.
NAME_REJECTED_ERROR = "nom refusé"
#: Bloc de lecture de l'empreinte, au-delà du premier tronçon borné.
_READ_BLOCK_BYTES = 1024 * 1024
#: Motif d'un fichier au-delà de `MAX_GRID_BYTES`, lu ou seulement listé.
_OVERSIZE_MESSAGE = (
    "fichier trop volumineux : plus de "
    f"{MAX_GRID_BYTES} octets (64 Kio) admis"
)

# Identifiants stables des règles D1, cités par chaque refus.
RULE_TITLE = "titre"
RULE_NO_FIELD = "case_requise"
RULE_HEADING_DEPTH = "profondeur"
RULE_ORPHAN_SUBFIELD = "sous_case_orpheline"
RULE_UNCLOSED_BLOCK = "bloc_non_ferme"
RULE_EMPTY_KEY = "cle_vide"
RULE_DUPLICATE_KEY = "cle_dupliquee"
RULE_RESERVED_KEY = "cle_reservee"
RULE_FIELD_LIMIT = "limite_cases"
RULE_SIZE_LIMIT = "taille_max"
RULE_ENCODING = "encodage"

# Mot « Liste » en tête de consigne, ASCII seul : espaces Unicode facultatifs
# puis `.` ou `:`.
_LIST_LINE = re.compile(r"(?a:liste)\s*[.:]", re.IGNORECASE)
#: Description commune des refus de titre manquant (règle du `#` unique).
_TITLE_REQUIRED = "un titre `#` est requis comme premier contenu non vide"
# Titre ATX : `#` en début de ligne, au moins un espace, libellé non vide.
_HEADING_LINE = re.compile(r"(#+)[ \t]+(\S.*)")
# Clôture de bloc de code après au plus trois espaces de tête.
_BLOCK_OPENING = re.compile(r" {0,3}(```|~~~)")
#: Motif de fermeture par clôture : une ligne commençant par la même clôture.
_BLOCK_CLOSERS = {
    "```": re.compile(r" {0,3}```"),
    "~~~": re.compile(r" {0,3}~~~"),
}
# Toute suite de caractères hors `[a-z0-9]`, réduite à un seul `_`.
_NON_ALNUM = re.compile(r"[^a-z0-9]+")


class GridUnreadable(Exception):
    """Fichier de grille impossible à lire (cas « impossible », pas invalide).

    Les messages ne citent que le nom de la grille, jamais un chemin absolu
    ni de trace d'exception. Une grille au contenu invalide ne lève jamais
    cette exception : elle est rendue avec son motif d'invalidité.
    """


@dataclass(frozen=True)
class GridError:
    """Refus d'interprétation d'une grille, avec la ligne et la règle en cause.

    `line` est le numéro de la ligne en cause (la première ligne du fichier
    porte le numéro 1), ou `None` quand aucune ligne ne l'est : fichier vide,
    taille maximale dépassée, absence de toute case. `rule` est l'identifiant
    stable de la règle violée (constantes `RULE_*`), `message` le texte
    complet prêt à afficher, qui nomme lui-même la ou les lignes en cause
    (un doublon cite ses deux lignes).
    """

    line: int | None
    rule: str
    message: str


@dataclass(frozen=True)
class Field:
    """Case ou sous-case interprétée d'une grille.

    `key` suit la normalisation D1 ; `label` reprend le libellé du titre tel
    qu'écrit ; `instructions` est la consigne (texte jusqu'au titre suivant,
    bords retirés) ou `None` si la case n'en a pas ; `line` est la ligne du
    titre qui ouvre la case ; `is_list` marque une case liste (règle
    « Liste. ») ; `subfields` contient, dans l'ordre, les sous-cases d'une
    case composée et reste vide pour une sous-case. Une case à la fois liste
    et composée est une liste composée (design D2) ; une case composée garde
    sa propre consigne, figée à l'arrivée de son premier `###`.
    """

    key: str
    label: str
    instructions: str | None
    line: int
    is_list: bool = False
    subfields: tuple[Field, ...] = ()

    @property
    def composed(self) -> bool:
        """Case composée : au moins une sous-case lui appartient."""
        return bool(self.subfields)


@dataclass(frozen=True)
class Grid:
    """Grille lue et interprétée, valide ou non.

    `error` vaut `None` pour une grille valide ; sinon il porte la première
    erreur rencontrée et la grille n'est jamais proposée à l'exécution. Les
    autres champs sont remplis jusqu'à cette erreur — titre lu, cases déjà
    fermées — et ne doivent être consommés que si `valid` est vrai.
    `sha256` est l'empreinte des octets du fichier, renseignée pour tout
    fichier lu dans la limite ; absente quand le fichier est refusé avant
    lecture pour cause de taille excessive.
    """

    name: str
    sha256: str | None
    title: str | None
    general_instructions: str | None
    fields: tuple[Field, ...]
    error: GridError | None

    @property
    def valid(self) -> bool:
        """Vrai quand aucune règle n'a été violée."""
        return self.error is None


@dataclass(frozen=True)
class GridSummary:
    """Entrée de la liste des grilles, sans jamais proposer une grille invalide.

    `name` est le nom sans extension d'une grille résolue, ou le nom du
    fichier pour une entrée au nom refusé (identifiable sur disque, mais sans
    action possible). `sha256`, `title` et `field_count` (cases de premier
    niveau) valent `None` quand l'entrée n'a pas été lue ou interprétée
    jusqu'ici. `error` vaut `None` pour une grille valide, sinon le motif
    complet (« ligne N : … », « nom refusé » ou taille maximale dépassée).
    """

    name: str
    sha256: str | None
    title: str | None
    field_count: int | None
    error: str | None


@dataclass
class _FieldDraft:
    """Case en construction pendant l'interprétation (usage interne)."""

    key: str
    label: str
    line: int
    instructions: str | None = None
    instructions_closed: bool = False
    subfields: list[Field] = field(default_factory=list)
    keys: dict[str, tuple[int, str]] = field(default_factory=dict)


class _InterpretationError(Exception):
    """Transport interne d'un refus D1 vers l'objet `Grid` rendu."""

    def __init__(self, error: GridError) -> None:
        super().__init__(error.message)
        self.error = error


def grid_key(label: str) -> str:
    """Clé stable d'un libellé de case, selon la normalisation D1.

    Décomposition Unicode NFKD, marques diacritiques retirées, minuscules,
    puis `œ`→`oe`, `æ`→`ae`, `ß`→`ss` (la mise en minuscules passe avant pour
    que `ẞ` donne aussi `ss`), toute suite de caractères hors `[a-z0-9]`
    réduite à un seul `_`, `_` retirés en tête et en fin. Exemples du design :
    `Examens pratiqués ?` → `examens_pratiques` ; `Œdème / douleur !!` →
    `oedeme_douleur`. Un libellé sans aucun caractère alphanumérique donne une
    clé vide, refusée par l'interprétation.
    """
    decomposed = unicodedata.normalize("NFKD", label)
    without_accents = "".join(
        character
        for character in decomposed
        if not unicodedata.combining(character)
    )
    lowered = without_accents.lower()
    without_ligatures = (
        lowered.replace("œ", "oe")
        .replace("æ", "ae")
        .replace("ß", "ss")
    )
    return _NON_ALNUM.sub("_", without_ligatures).strip("_")


def read_grid(name: str, base: Path | str | None = None) -> Grid:
    """Lit et interprète la grille `name` du dossier versionné `grilles/`.

    `base` est la racine contenant `grilles/` (celle du projet par défaut) ;
    elle n'est fournie que par les tests. Le nom est contrôlé avant tout
    accès au système de fichiers : un nom non conforme, contenant un
    séparateur, une remontée `..` ou désignant un lien symbolique sortant est
    refusé (`ValeurRefusee`) sans lire le fichier, de même qu'un nom inconnu
    ou une cible qui n'est pas un fichier ordinaire. Le fichier est ensuite
    lu borné : sa taille est contrôlée avant toute lecture (un fichier
    dépassant la limite rend une `Grid` invalide sans être lu), puis lu au
    plus `MAX_GRID_BYTES` + 1 octets, l'empreinte restant complète : un
    fichier illisible lève `GridUnreadable`, tout le reste — contenu non
    UTF-8, règles D1 violées — rend une `Grid` invalide sans exception.
    """
    try:
        path = _grid_path(name, base)
        if path.stat().st_size > MAX_GRID_BYTES:
            return _invalid_grid(
                name,
                None,
                GridError(
                    line=None,
                    rule=RULE_SIZE_LIMIT,
                    message=_OVERSIZE_MESSAGE,
                ),
            )
    except OSError as error:
        # Toute erreur système au moment de la lecture (fichier retiré entre
        # la découverte et la lecture, erreur d'accès) : la découverte et la
        # commande listent l'erreur sans faire échouer la liste.
        raise GridUnreadable(
            f"grille « {name} » illisible au moment de la lecture : {error}"
        ) from error
    data, digest = _read_file(path, name)
    return _interpret_bytes(name, data, digest)


def interpret_grid_copy(name: str, data: bytes) -> Grid:
    """Interprète une copie conservée de grille, à partir de ses octets complets.

    Sert à la consultation des extractions : la grille relue est celle copiée
    dans le dossier de l'extraction (design D7), jamais celle de `grilles/` au
    moment de la consultation. Taille, décodage et règles sont ceux de
    `read_grid` ; l'empreinte est celle des octets fournis.
    """
    return _interpret_bytes(name, data, hashlib.sha256(data).hexdigest())


def _interpret_bytes(name: str, data: bytes, digest: str) -> Grid:
    """Taille maximale, décodage UTF-8 puis interprétation ; rend toujours une `Grid`."""
    if len(data) > MAX_GRID_BYTES:
        return _invalid_grid(
            name,
            digest,
            GridError(
                line=None,
                rule=RULE_SIZE_LIMIT,
                message=_OVERSIZE_MESSAGE,
            ),
        )
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        line = data.count(b"\n", 0, error.start) + 1
        return _invalid_grid(
            name,
            digest,
            GridError(
                line=line,
                rule=RULE_ENCODING,
                message=f"ligne {line} : contenu non décodable en UTF-8",
            ),
        )
    return _interpret(name, digest, text)


def discover_grids(base: Path | str | None = None) -> tuple[GridSummary, ...]:
    """Liste les grilles de `grilles/` : nom, titre, cases, empreinte, état.

    Un dossier `grilles/` absent signifie « aucune grille » : la liste est
    vide et le dossier n'est jamais créé. Chaque fichier d'extension exacte
    `.md` directement sous le dossier est examiné : nom conforme et cible
    confinée donnent une grille lue et interprétée (valide ou motif
    d'invalidité) ; un nom ou une cible refusés donnent une entrée
    « nom refusé », listée mais jamais lue ni proposée à une exécution ;
    un fichier au-delà de `MAX_GRID_BYTES` est listé avec ce motif, sans
    empreinte, et n'est pas lu en entier ; un fichier d'une autre extension
    ou un répertoire n'est pas une grille et n'est pas listé. Une erreur de
    lecture inattendue ne fait pas échouer la liste : l'entrée concernée porte
    l'erreur. Les entrées sont triées par nom.
    """
    directory = _grids_dir(base)
    try:
        entries = sorted(directory.iterdir(), key=lambda entry: entry.name)
    except (FileNotFoundError, NotADirectoryError):
        return ()

    summaries: list[GridSummary] = []
    for entry in entries:
        file_name = entry.name
        if not file_name.endswith(".md") or file_name == ".md":
            continue
        try:
            if entry.is_dir():
                continue
        except OSError:
            pass  # cible illisible : la résolution ci-dessous tranche
        name = file_name[: -len(".md")]
        if not GRID_NAME_PATTERN.fullmatch(name):
            summaries.append(_rejected_entry(file_name))
            continue
        try:
            _grid_path(name, base)
        except ValeurRefusee:
            summaries.append(_rejected_entry(file_name))
            continue
        except OSError as error:
            # Cible devenue illisible (retirée ou inacessible au moment de la
            # vérification) : l'entrée porte l'erreur, la liste continue.
            summaries.append(
                GridSummary(
                    name=name,
                    sha256=None,
                    title=None,
                    field_count=None,
                    error=f"grille « {name} » illisible : {error}",
                )
            )
            continue
        try:
            oversized = entry.stat().st_size > MAX_GRID_BYTES
        except OSError:
            oversized = False  # la lecture ci-dessous rapporte l'erreur
        if oversized:
            summaries.append(
                GridSummary(
                    name=name,
                    sha256=None,
                    title=None,
                    field_count=None,
                    error=_OVERSIZE_MESSAGE,
                )
            )
            continue
        try:
            grid = read_grid(name, base)
        except GridUnreadable as error:
            summaries.append(
                GridSummary(
                    name=name,
                    sha256=None,
                    title=None,
                    field_count=None,
                    error=str(error),
                )
            )
            continue
        summaries.append(
            GridSummary(
                name=name,
                sha256=grid.sha256,
                title=grid.title,
                field_count=len(grid.fields) if grid.valid else None,
                error=None if grid.error is None else grid.error.message,
            )
        )
    return tuple(summaries)


def _grids_dir(base: Path | str | None) -> Path:
    """Dossier versionné `grilles/` sous la racine (jamais créé ici)."""
    root = RACINE_PROJET if base is None else Path(base)
    return root / GRID_DIR_NAME


def _grid_path(name: str, base: Path | str | None) -> Path:
    """Résout un nom de grille admis et renvoie son chemin, sans le lire.

    Le nom (sans extension) doit être conforme, et la cible rester un
    fichier ordinaire confiné au dossier `grilles/` : un séparateur de
    chemin, une remontée, un lien symbolique sortant ou un nom non conforme
    est refusé (`ValeurRefusee`) avant toute lecture du fichier.
    """
    if not isinstance(name, str):
        raise ValeurRefusee("nom de grille attendu sous forme de texte")
    if not GRID_NAME_PATTERN.fullmatch(name):
        raise ValeurRefusee(
            f"grille refusée : nom non conforme ({name!r}) : 1 à 64 "
            "caractères [a-z0-9-], sans extension, commençant par une lettre "
            "ou un chiffre"
        )
    path = resoudre_dans_racine(_grids_dir(base), f"{name}.md")
    if not path.exists():
        raise ValeurRefusee(f"grille inconnue : {name}")
    if not path.is_file():
        raise ValeurRefusee(
            f"grille refusée : fichier ordinaire attendu ({name}.md)"
        )
    return path


def grid_path(name: str, base: Path | str | None = None) -> Path:
    """Chemin confiné d'une grille admise, sans la lire.

    Même contrôle que `read_grid` (nom, confinement, fichier ordinaire). Le
    service d'extraction s'en sert pour recopier octet pour octet la grille
    validée dans son dossier de résultat (tâche 3.4, D7).
    """
    return _grid_path(name, base)


def _read_file(path: Path, name: str) -> tuple[bytes, str]:
    """Lit le fichier borné et rend (octets, empreinte SHA-256 complète).

    Au plus `MAX_GRID_BYTES` + 1 octets sont conservés — assez pour constater
    un dépassement sans jamais charger un fichier démesuré — tandis que
    l'empreinte couvre tout le fichier, lue par blocs. Une erreur système
    d'ouverture ou de lecture lève `GridUnreadable` : c'est un cas impossible
    à interpréter, distinct d'une grille au contenu invalide.
    """
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            data = handle.read(MAX_GRID_BYTES + 1)
            digest.update(data)
            while chunk := handle.read(_READ_BLOCK_BYTES):
                digest.update(chunk)
    except OSError as error:
        raise GridUnreadable(
            f"lecture impossible : {name} ({_explanation(error)})"
        ) from None
    return data, digest.hexdigest()


def _interpret(name: str, sha256: str, text: str) -> Grid:
    """Applique les règles D1 ligne à ligne et rend toujours une `Grid`.

    Le premier contenu non vide doit être le titre `#` unique. Le texte
    collecté avant le premier `## ` forme les consignes générales ; chaque
    `##` ouvre une case, chaque `###` sous une case une sous-case, et le
    texte suivant appartient à la consigne en cours, blocs de code compris.
    La première erreur lève `_InterpretationError`, convertie en `Grid`
    invalide : les champs déjà interprétés restent remplis, l'erreur porte
    la ligne et la règle en cause.
    """
    title: str | None = None
    title_line: int = 0
    general: str | None = None
    cases: list[Field] = []
    case_keys: dict[str, tuple[int, str]] = {}
    case: _FieldDraft | None = None
    subfield: _FieldDraft | None = None
    span: list[str] = []
    block: tuple[str, int] | None = None
    total = 0

    def reject(rule: str, line: int | None, description: str) -> NoReturn:
        message = (
            description if line is None else f"ligne {line} : {description}"
        )
        raise _InterpretationError(
            GridError(line=line, rule=rule, message=message)
        )

    def count_field(number: int) -> None:
        nonlocal total
        total += 1
        if total > MAX_FIELDS:
            reject(
                RULE_FIELD_LIMIT,
                number,
                f"plus de {MAX_FIELDS} cases et sous-cases au total",
            )

    def open_key(
        label: str, number: int, keys: dict[str, tuple[int, str]]
    ) -> str:
        key = grid_key(label)
        if not key:
            reject(
                RULE_EMPTY_KEY,
                number,
                f"clé vide : le libellé {label!r} ne donne aucun "
                "caractère [a-z0-9]",
            )
        if key == RESERVED_KEY:
            reject(
                RULE_RESERVED_KEY,
                number,
                f"clé réservée {RESERVED_KEY!r} : la section « autres "
                "informations » est ajoutée d'office par le programme",
            )
        if key in keys:
            previous_line, _ = keys[key]
            reject(
                RULE_DUPLICATE_KEY,
                number,
                f"clé {key!r} déjà définie au même niveau (ligne "
                f"{previous_line})",
            )
        keys[key] = (number, label)
        return key

    def close_subfield() -> None:
        nonlocal subfield, span
        assert subfield is not None and case is not None
        instructions = _instructions(span)
        span = []
        case.subfields.append(
            Field(
                key=subfield.key,
                label=subfield.label,
                instructions=instructions,
                line=subfield.line,
                is_list=_starts_with_list(instructions),
            )
        )
        subfield = None

    def close_field() -> None:
        nonlocal case, span
        assert case is not None
        if not case.instructions_closed:
            case.instructions = _instructions(span)
            span = []
        cases.append(
            Field(
                key=case.key,
                label=case.label,
                instructions=case.instructions,
                line=case.line,
                is_list=_starts_with_list(case.instructions),
                subfields=tuple(case.subfields),
            )
        )
        case = None

    try:
        for number, line in enumerate(_split_lines(text), start=1):
            if block is not None:
                if _closes_block(line, block[0]):
                    block = None
                span.append(line)
                continue
            closer = _opens_block(line)
            if closer is not None:
                if title is None:
                    reject(RULE_TITLE, number, _TITLE_REQUIRED)
                block = (closer, number)
                span.append(line)
                continue
            heading = _parse_heading(line)
            if heading is not None:
                level, label = heading
                if title is None:
                    if level != 1:
                        # Un titre de case avant le titre de la grille n'est
                        # pas interprété : c'est un contenu non vide sans `#`.
                        reject(RULE_TITLE, number, _TITLE_REQUIRED)
                    title, title_line = label, number
                    continue
                if level == 1:
                    reject(
                        RULE_TITLE,
                        number,
                        "un seul titre `#` est admis (premier en ligne "
                        f"{title_line})",
                    )
                elif level >= 4:
                    reject(
                        RULE_HEADING_DEPTH,
                        number,
                        f"titre de profondeur {level} ({'#' * level!r}) "
                        "refusé : la profondeur maximale est `###`",
                    )
                elif level == 2:
                    if case is None:
                        general = _instructions(span)
                        span = []
                    else:
                        if subfield is not None:
                            close_subfield()
                        close_field()
                    key = open_key(label, number, case_keys)
                    count_field(number)
                    case = _FieldDraft(key=key, label=label, line=number)
                    subfield = None
                else:
                    if case is None:
                        reject(
                            RULE_ORPHAN_SUBFIELD,
                            number,
                            "sous-case `###` sans case ouverte : un titre `##` "
                            "doit la précéder",
                        )
                    if subfield is not None:
                        close_subfield()
                    elif not case.instructions_closed:
                        case.instructions = _instructions(span)
                        case.instructions_closed = True
                        span = []
                    key = open_key(label, number, case.keys)
                    count_field(number)
                    subfield = _FieldDraft(key=key, label=label, line=number)
                continue
            if title is None:
                if line.strip():
                    reject(RULE_TITLE, number, _TITLE_REQUIRED)
                continue
            span.append(line)
        if block is not None:
            reject(
                RULE_UNCLOSED_BLOCK,
                block[1],
                f"bloc de code ouvert par {block[0]!r} non fermé",
            )
        if subfield is not None:
            close_subfield()
        if case is not None:
            close_field()
        if not cases:
            if title is None:
                reject(RULE_TITLE, None, "aucun titre `#` : la grille est vide")
            reject(
                RULE_NO_FIELD,
                None,
                "aucune case : au moins un titre `##` est requis",
            )
    except _InterpretationError as refusal:
        return Grid(
            name=name,
            sha256=sha256,
            title=title,
            general_instructions=general,
            fields=tuple(cases),
            error=refusal.error,
        )
    return Grid(
        name=name,
        sha256=sha256,
        title=title,
        general_instructions=general,
        fields=tuple(cases),
        error=None,
    )


def _invalid_grid(name: str, sha256: str | None, error: GridError) -> Grid:
    """Grille invalide avant interprétation (taille, encodage)."""
    return Grid(
        name=name,
        sha256=sha256,
        title=None,
        general_instructions=None,
        fields=(),
        error=error,
    )


def _split_lines(text: str) -> list[str]:
    """Lignes d'un texte, découpées sur le seul LF, `\\r` final retiré.

    Contrairement à `str.splitlines`, U+2028, U+0085 et les autres séparateurs
    ne coupent pas une ligne : les numéros de ligne suivent le découpage du
    fichier sur ses sauts de ligne LF, fins CRLF comprises.
    """
    return [
        line[:-1] if line.endswith("\r") else line
        for line in text.split("\n")
    ]


def _parse_heading(line: str) -> tuple[int, str] | None:
    """Renvoie (niveau, libellé) pour un titre ATX non indenté, ou `None`.

    Un titre exige des `#` en tout début de ligne, puis au moins un espace,
    puis un libellé non vide : `##Libellé` sans espace, une ligne indentée ou
    un titre vide restent du texte de consigne (le design n'autorise
    l'indentation que pour les blocs de code). Le libellé garde ses espaces
    internes, seuls ceux de fin sont retirés.
    """
    match = _HEADING_LINE.match(line)
    if match is None:
        return None
    return len(match.group(1)), match.group(2).rstrip()


def _opens_block(line: str) -> str | None:
    """Clôture (``` ou ~~~) si la ligne ouvre un bloc de code, sinon `None`."""
    match = _BLOCK_OPENING.match(line)
    if match is None:
        return None
    return match.group(1)


def _closes_block(line: str, closer: str) -> bool:
    """Vrai si la ligne ferme le bloc ouvert par `closer` (même clôture).

    Lecture littérale du design : la ligne doit commencer par la même
    clôture après au plus trois espaces ; le reste de la ligne est ignoré.
    """
    return bool(_BLOCK_CLOSERS[closer].match(line))


def _starts_with_list(instructions: str | None) -> bool:
    """Vrai si la consigne commence par « Liste » puis `.` ou `:` (D1).

    La première ligne non vide est examinée, blancs de tête retirés ; la
    casse est ignorée et des espaces, y compris Unicode (insécables compris),
    sont admis avant le signe. « Listes », « Liste des… » ou « Liste » sans
    signe laissent une case texte, et « liſte. » (ſ long) n'est pas une liste.
    """
    if instructions is None:
        return False
    for line in _split_lines(instructions):
        if not line.strip():
            continue
        return bool(_LIST_LINE.match(line.lstrip()))
    return False


def _instructions(span: list[str]) -> str | None:
    """Texte d'une plage de lignes, bords (blancs, lignes vides) retirés.

    Le contenu interne est conservé à l'identique, délimiteurs de blocs de
    code compris, pour que la consigne envoyée au modèle reste fidèle.
    """
    text = "\n".join(span).strip()
    return text or None


def _rejected_entry(file_name: str) -> GridSummary:
    """Entrée au nom ou à la cible refusés : listée, jamais lue ni proposée."""
    return GridSummary(
        name=file_name,
        sha256=None,
        title=None,
        field_count=None,
        error=NAME_REJECTED_ERROR,
    )


def _explanation(error: BaseException) -> str:
    """Texte court de l'erreur, sans chemin absolu ni trace d'exception."""
    text = getattr(error, "strerror", None)
    return text if text else type(error).__name__
