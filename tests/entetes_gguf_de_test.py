"""En-têtes GGUF synthétiques pour les tests, générés localement.

Aucun fichier de modèle, aucun poids et aucun accès réseau : les octets sont
assemblés ici selon la spécification ggml (`docs/gguf.md`), versions 2 et 3,
petit ou grand boutisme. Les valeurs sont décrites par des noms de type du
format (`u32`, `string`, `array`, ...) pour que les tests restent lisibles.

La quantification n'est jamais écrite dans un champ GGUF : seul le nom de
fichier peut la suggérer, et ces tests ne s'appuient pas dessus.
"""

from __future__ import annotations

import struct
from typing import Any

TYPES_GGUF: dict[str, int] = {
    "u8": 0,
    "i8": 1,
    "u16": 2,
    "i16": 3,
    "u32": 4,
    "i32": 5,
    "f32": 6,
    "bool": 7,
    "string": 8,
    "array": 9,
    "u64": 10,
    "i64": 11,
    "f64": 12,
}

FORMATS_SCALAIRES: dict[str, str] = {
    "u8": "B",
    "i8": "b",
    "u16": "H",
    "i16": "h",
    "u32": "I",
    "i32": "i",
    "f32": "f",
    "bool": "?",
    "u64": "Q",
    "i64": "q",
    "f64": "d",
}

MAGIE_GGUF = b"GGUF"


def ordre_de(boutisme: str) -> str:
    return "<" if boutisme == "petit" else ">"


def chaine_gguf(texte: str, ordre: str) -> bytes:
    octets = texte.encode("utf-8")
    return struct.pack(ordre + "Q", len(octets)) + octets


def valeur_gguf(type_valeur: str, valeur: Any, ordre: str) -> bytes:
    if type_valeur == "string":
        return chaine_gguf(valeur, ordre)
    if type_valeur == "array":
        type_element, elements = valeur
        elements_encodes = b"".join(
            valeur_gguf(type_element, element, ordre) for element in elements
        )
        return (
            struct.pack(ordre + "I", TYPES_GGUF[type_element])
            + struct.pack(ordre + "Q", len(elements))
            + elements_encodes
        )
    return struct.pack(ordre + FORMATS_SCALAIRES[type_valeur], valeur)


def entete_gguf(
    *metadonnees: tuple[str, str, Any],
    version: int = 3,
    boutisme: str = "petit",
    magie: bytes | None = None,
    tensor_count: int = 0,
    nombre_metadonnees: int | None = None,
) -> bytes:
    """Assemble un en-tête GGUF : magie, version, compteurs, puis métadonnées.

    La magie est toujours `GGUF`, quel que soit le boutisme : c'est la version
    qui indique l'ordre d'octets, comme dans la spécification ggml.
    """
    ordre = ordre_de(boutisme)
    if magie is None:
        magie = MAGIE_GGUF
    morceaux = [
        magie,
        struct.pack(ordre + "I", version),
        struct.pack(ordre + "Q", tensor_count),
        struct.pack(
            ordre + "Q",
            len(metadonnees) if nombre_metadonnees is None else nombre_metadonnees,
        ),
    ]
    for cle, type_valeur, valeur in metadonnees:
        morceaux.append(chaine_gguf(cle, ordre))
        morceaux.append(struct.pack(ordre + "I", TYPES_GGUF[type_valeur]))
        morceaux.append(valeur_gguf(type_valeur, valeur, ordre))
    return b"".join(morceaux)


def source_de(
    octets: bytes,
    *,
    demandes: list[int] | None = None,
    pas_max: int | None = None,
):
    """Flux `read(n)` sur des octets, avec relevé des demandes et lectures courtes.

    La fonction n'accepte qu'un argument : un appel `read()` sans borne lèverait
    une `TypeError`, ce qui garantit qu'aucun test ne laisse passer une lecture
    non bornée.
    """
    position = 0

    def lire(nombre: int) -> bytes:
        nonlocal position
        if demandes is not None:
            demandes.append(nombre)
        demande = nombre if pas_max is None else min(nombre, pas_max)
        bloc = octets[position : position + demande]
        position += len(bloc)
        return bloc

    return lire
