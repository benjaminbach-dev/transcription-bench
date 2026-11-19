"""Schéma JSON des grilles d'extraction : génération, décodage, validation.

Tâche 1.2 du change `ajouter-bench-extraction` : convertir une grille valide
(module `grilles`, décision D1) en un schéma JSON déterministe (décision D2),
décoder strictement une sortie brute du modèle et valider la sortie décodée
contre ce schéma. Sans écriture de fichier, sans réseau, sans dépendance :
la contrainte imposée au moteur n'est pas tenue pour une preuve, le
programme contrôle lui-même la forme de chaque sortie.

Sous-ensemble D2, le seul admissible dans les schémas produits : objets,
tableaux, chaînes, `null`, `anyOf`, `minItems`, `required` et
`additionalProperties: false`. Toutes les clés sont requises et `null`
signifie « non mentionné ». Une chaîne vide est conforme, une liste vide ne
l'est pas (`minItems`), sauf la section `autres_informations`, ajoutée
d'office en dernier : un tableau non « null-able », éventuellement vide,
d'entrées à deux chaînes requises (`intitule`, `valeur`).

Génération déterministe : les clés suivent l'ordre des cases de la grille et
de leurs sous-cases, `autres_informations` en dernier ; les dictionnaires
sont construits dans cet ordre et la sérialisation canonique
(`schema_to_json`) est reproductible octet pour octet.

Décodage strict (`decode_output`) : les clés JSON dupliquées sont refusées
avec un motif propre (`cle_dupliquee`), distinct de l'erreur de syntaxe
(`json_invalide`) ; les deux rendent un échec nommé, jamais une exception.

Validation interne (`validate_output`) : la sortie décodée est parcourue
contre le schéma et le verdict rend la première non-conformité avec son
chemin (`$.case`, `$.liste[0].sous_case`) et son motif, sans exception pour
les cas de non-conformité. Conformité ≠ exactitude : elle ne dit que la
forme.

Choix assumés là où le design ne tranche pas (les plus simples, documentés
pour être rediscutables) : la génération d'un schéma exige une grille valide
(`ValueError`, cas impossible pour un appelant qui n'exécute que des grilles
valides) ; la première erreur suffit et l'ordre de parcours est fixe — clés
exigées dans l'ordre du schéma, clés inconnues dans l'ordre du document, puis
valeurs case par case dans l'ordre du schéma ; le motif d'une clé dupliquée
nomme la clé en cause, sans chemin complet, l'information de position fiable
étant celle du décodeur pour la syntaxe ; quand aucune alternative d'un
`anyOf` ne convient, l'erreur du type correspondant à la forme de la valeur
est rendue (liste vide, sous-case manquante…), sinon le motif résume les
formes attendues. Ce contrôle ne constitue pas une preuve sémantique : une
sortie conforme peut être fausse médicalement.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, NoReturn

from transcription_bench.grilles import RESERVED_KEY, Field, Grid

# Motifs de refus du décodage (identifiants stables, texte français).
DECODE_JSON_INVALID = "json_invalide"
DECODE_DUPLICATE_KEY = "cle_dupliquee"

# Motifs de non-conformité (identifiants stables, texte français).
REASON_MISSING_KEY = "cle_manquante"
REASON_UNKNOWN_KEY = "cle_inconnue"
REASON_WRONG_TYPE = "mauvais_type"
REASON_NULL_NOT_ALLOWED = "null_non_admis"
REASON_EMPTY_LIST = "liste_vide"

# Libellés français des types JSON, pour les motifs d'erreur.
_TYPE_LABELS = {"string": "texte", "array": "liste", "object": "objet", "null": "null"}


@dataclass(frozen=True)
class SchemaIssue:
    """Première non-conformité d'une sortie, avec son chemin et son motif.

    `path` localise l'erreur (`$` pour la racine, `$.case`, `$.liste[0]`,
    `$.case.sous_case`) ; `reason` est l'identifiant stable du motif
    (constantes `REASON_*`) ; `message` le texte complet prêt à afficher.
    """

    path: str
    reason: str
    message: str


@dataclass(frozen=True)
class ValidationResult:
    """Verdict de conformité d'une sortie décodée contre un schéma D2.

    `issue` vaut `None` quand la sortie est conforme ; sinon il porte la
    première non-conformité trouvée — jamais une exception.
    """

    issue: SchemaIssue | None

    @property
    def valid(self) -> bool:
        """Vrai quand la sortie respecte le schéma."""
        return self.issue is None


@dataclass(frozen=True)
class DecodeResult:
    """Verdict du décodage strict d'une sortie brute du modèle.

    `value` est la valeur décodée quand `ok` est vrai (sinon `None`) ;
    `reason` est le motif stable du refus (constantes `DECODE_*`) sinon,
    `message` le texte complet prêt à afficher.
    """

    ok: bool
    value: Any
    reason: str | None
    message: str | None


class _DuplicateKeyError(Exception):
    """Clé dupliquée rencontrée pendant le décodage (usage interne)."""

    def __init__(self, key: str) -> None:
        super().__init__(key)
        self.key = key


class _NonFiniteConstantError(Exception):
    """Constante `NaN`, `Infinity` ou `-Infinity` rencontrée (usage interne)."""

    def __init__(self, constant: str) -> None:
        super().__init__(constant)
        self.constant = constant


def grid_schema(grid: Grid) -> dict[str, Any]:
    """Schéma D2 d'une grille valide : toutes les clés requises, ordre fixe.

    Les cases de la grille viennent dans leur ordre, chacune typée selon le
    tableau D2 (texte, liste de textes, composée, liste composée), puis la
    section réservée `autres_informations` en dernier. Une grille invalide
    n'a pas de schéma : c'est un cas impossible pour l'exécution, refusé
    ici par `ValueError`.
    """
    if not grid.valid:
        detail = grid.error.message if grid.error else "raison inconnue"
        raise ValueError(f"grille invalide ({grid.name}) : {detail}")
    properties: dict[str, Any] = {}
    required: list[str] = []
    for field in grid.fields:
        properties[field.key] = _field_schema(field)
        required.append(field.key)
    properties[RESERVED_KEY] = _other_info_schema()
    required.append(RESERVED_KEY)
    return {
        "type": "object",
        "properties": properties,
        "required": required,
        "additionalProperties": False,
    }


def schema_to_json(schema: dict[str, Any]) -> str:
    """Sérialisation canonique d'un schéma, reproductible octet pour octet.

    Les dictionnaires étant construits dans l'ordre des cases, aucun tri
    n'est nécessaire : `json.dumps` conserve l'ordre d'insertion et deux
    générations successives donnent le même texte.
    """
    return json.dumps(schema, indent=2)


def decode_output(raw: str) -> DecodeResult:
    """Décode une sortie brute en JSON, en refusant les clés dupliquées.

    Le refus est un verdict, pas une exception. Une clé dupliquée rend
    `ok` faux avec le motif `cle_dupliquee` et le nom de la première clé
    en cause ; un JSON indécodable rend `ok` faux avec le motif
    `json_invalide` et la position de l'erreur de syntaxe. Les constantes hors
    JSON strict (`NaN`, `Infinity`, `-Infinity`) et une imbrication trop
    profonde pour le décodeur (`RecursionError`) rendent aussi `json_invalide`,
    avec un message dédié.
    """
    try:
        value = json.loads(
            raw,
            object_pairs_hook=_pairs_without_duplicate,
            parse_constant=_refuse_constant,
        )
    except _DuplicateKeyError as error:
        return DecodeResult(
            ok=False,
            value=None,
            reason=DECODE_DUPLICATE_KEY,
            message=f"clé dupliquée : {error.key!r}",
        )
    except _NonFiniteConstantError as error:
        return DecodeResult(
            ok=False,
            value=None,
            reason=DECODE_JSON_INVALID,
            message=(
                f"JSON indécodable : constante {error.constant} non admise "
                "(JSON strict)"
            ),
        )
    except RecursionError:
        return DecodeResult(
            ok=False,
            value=None,
            reason=DECODE_JSON_INVALID,
            message="JSON indécodable : structure trop profondément imbriquée",
        )
    except json.JSONDecodeError as error:
        return DecodeResult(
            ok=False,
            value=None,
            reason=DECODE_JSON_INVALID,
            message=(
                f"JSON indécodable : {error.msg.lower()} "
                f"(ligne {error.lineno}, colonne {error.colno})"
            ),
        )
    except ValueError as error:
        # Littéral numérique hors des limites de conversion de l'interpréteur :
        # Python refuse les entiers de plusieurs milliers de chiffres. Le
        # décodage reste total : tout échec rend un verdict, jamais une
        # exception qui remonterait jusqu'à l'exécution.
        return DecodeResult(
            ok=False,
            value=None,
            reason=DECODE_JSON_INVALID,
            message=f"JSON indécodable : nombre hors des limites ({error})",
        )
    return DecodeResult(ok=True, value=value, reason=None, message=None)


def validate_output(value: Any, schema: dict[str, Any]) -> ValidationResult:
    """Valide une sortie décodée contre un schéma du sous-ensemble D2.

    Le parcours s'arrête à la première non-conformité, dans un ordre fixe :
    clés exigées dans l'ordre du schéma, clés inconnues dans l'ordre du
    document, puis valeurs case par case dans l'ordre du schéma. Le verdict
    est un objet, jamais une exception pour une sortie non conforme.
    """
    return ValidationResult(issue=_check_node(value, schema, "$"))


def _field_schema(field: Field) -> dict[str, Any]:
    """Schéma de la valeur d'une case, selon son type dans le tableau D2.

    Une case avec sous-cases est composée (objet), ou liste composée quand
    elle est aussi une liste ; une case liste sans sous-case est une liste de
    textes ; toute autre case est un texte. Chaque case admet `null` (non
    mentionné) à la place de sa valeur.
    """
    if field.subfields:
        body = _object_schema(field.subfields)
        if field.is_list:
            return _nullable(_array_schema(body))
        return _nullable(body)
    if field.is_list:
        return _nullable(_array_schema({"type": "string"}))
    return _nullable({"type": "string"})


def _nullable(schema: dict[str, Any]) -> dict[str, Any]:
    """`null` (non mentionné) admis à la place du schéma donné."""
    return {"anyOf": [schema, {"type": "null"}]}


def _array_schema(item: dict[str, Any]) -> dict[str, Any]:
    """Tableau d'au moins une entrée de `item` (`minItems` 1, jamais vide)."""
    return {"type": "array", "items": item, "minItems": 1}


def _object_schema(fields: tuple[Field, ...]) -> dict[str, Any]:
    """Objet d'une case composée : sous-cases requises, ordre conservé."""
    properties = {field.key: _field_schema(field) for field in fields}
    return {
        "type": "object",
        "properties": properties,
        "required": list(properties),
        "additionalProperties": False,
    }


def _other_info_schema() -> dict[str, Any]:
    """Section `autres_informations` : hors grille, jamais « null ».

    Tableau éventuellement vide (seule case sans `minItems`) d'entrées à deux
    chaînes requises, destinées aux informations utiles absentes de la
    grille.
    """
    return {
        "type": "array",
        "items": {
            "type": "object",
            "properties": {
                "intitule": {"type": "string"},
                "valeur": {"type": "string"},
            },
            "required": ["intitule", "valeur"],
            "additionalProperties": False,
        },
    }


def _refuse_constant(constant: str) -> NoReturn:
    """Refuse `NaN`, `Infinity` et `-Infinity` : hors JSON strict."""
    raise _NonFiniteConstantError(constant)


def _pairs_without_duplicate(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    """Dictionnaire depuis les paires d'un objet JSON, doublons refusés."""
    seen: set[str] = set()
    for key, _ in pairs:
        if key in seen:
            raise _DuplicateKeyError(key)
        seen.add(key)
    return dict(pairs)


def _check_node(value: Any, schema: dict[str, Any], path: str) -> SchemaIssue | None:
    """Conformité d'une valeur à un nœud du sous-ensemble, ou l'erreur."""
    alternatives = schema.get("anyOf")
    if alternatives is not None:
        return _check_any_of(value, alternatives, path)
    node_type = schema.get("type")
    if node_type == "object":
        return _check_object(value, schema, path)
    if node_type == "array":
        return _check_array(value, schema, path)
    if node_type == "string":
        return _check_string(value, path)
    if node_type == "null":
        if value is None:
            return None
        return SchemaIssue(
            path, REASON_WRONG_TYPE, f"null attendu, reçu {_type_label(value)}"
        )
    raise ValueError(f"schéma hors sous-ensemble D2 : type {node_type!r}")


def _check_string(value: Any, path: str) -> SchemaIssue | None:
    """Une chaîne est exigée : vide admis, `null` refusé à cet endroit."""
    if isinstance(value, str):
        return None
    return _type_issue(value, path, "texte")


def _check_object(
    value: Any, schema: dict[str, Any], path: str
) -> SchemaIssue | None:
    """Objet exigé : clés requises présentes, aucune inconnue, valeurs valides."""
    if not isinstance(value, dict):
        return _type_issue(value, path, "objet")
    for key in schema.get("required", ()):
        if key not in value:
            return SchemaIssue(
                f"{path}.{key}",
                REASON_MISSING_KEY,
                f"case manquante : {key!r} est absente",
            )
    properties = schema.get("properties", {})
    for key in value:
        if key not in properties:
            return SchemaIssue(
                f"{path}.{key}",
                REASON_UNKNOWN_KEY,
                f"clé inconnue : {key!r} n'est pas dans la grille",
            )
    for key, subschema in properties.items():
        issue = _check_node(value[key], subschema, f"{path}.{key}")
        if issue is not None:
            return issue
    return None


def _check_array(value: Any, schema: dict[str, Any], path: str) -> SchemaIssue | None:
    """Tableau exigé : jamais vide si `minItems` l'impose, entrées valides."""
    if not isinstance(value, list):
        return _type_issue(value, path, "liste")
    min_items = schema.get("minItems")
    if min_items is not None and len(value) < min_items:
        return SchemaIssue(
            path,
            REASON_EMPTY_LIST,
            "liste vide : au moins une entrée est attendue",
        )
    items_schema = schema.get("items")
    if items_schema is None:
        return None
    for index, item in enumerate(value):
        issue = _check_node(item, items_schema, f"{path}[{index}]")
        if issue is not None:
            return issue
    return None


def _check_any_of(
    value: Any, alternatives: list[dict[str, Any]], path: str
) -> SchemaIssue | None:
    """Au moins une alternative doit convenir, sinon l'erreur la plus parlante.

    Les schémas D2 alternent toujours un type et `null` : quand la valeur a
    la forme d'un type proposé, son erreur propre est rendue (liste vide,
    sous-case manquante…) ; sinon le motif résume les formes attendues.
    """
    failures: list[SchemaIssue] = []
    for alternative in alternatives:
        failure = _check_node(value, alternative, path)
        if failure is None:
            return None
        failures.append(failure)
    shape = _shape_keyword(value)
    if shape is not None:
        for alternative, failure in zip(alternatives, failures):
            if alternative.get("type") == shape:
                return failure
    expected = " ou ".join(_TYPE_LABELS.get(alt.get("type"), str(alt.get("type")))
                            for alt in alternatives)
    return SchemaIssue(
        path,
        REASON_WRONG_TYPE,
        f"valeur non conforme : {expected} attendu, reçu {_type_label(value)}",
    )


def _type_issue(value: Any, path: str, expected: str) -> SchemaIssue:
    """Erreur de type à `path` ; `null` au mauvais endroit a son motif propre."""
    if value is None:
        return SchemaIssue(
            path, REASON_NULL_NOT_ALLOWED, f"null non admis : {expected} attendu"
        )
    return SchemaIssue(
        path,
        REASON_WRONG_TYPE,
        f"type attendu : {expected}, reçu {_type_label(value)}",
    )


def _shape_keyword(value: Any) -> str | None:
    """Mot-clé `type` du schéma correspondant à la forme de `value`, sinon `None`."""
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return None


def _type_label(value: Any) -> str:
    """Nom français du type JSON d'une valeur décodée, pour les motifs."""
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "booléen"
    if isinstance(value, str):
        return "texte"
    if isinstance(value, (int, float)):
        return "nombre"
    if isinstance(value, list):
        return "liste"
    if isinstance(value, dict):
        return "objet"
    return "valeur inattendue"
