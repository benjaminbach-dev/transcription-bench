"""Lecture partielle et bornée d'un en-tête GGUF, sans E/S ni paquet moteur.

Le format GGUF (ggml, spécification `docs/gguf.md`) commence par une magie
`GGUF` (4 octets), une `version` (uint32), `tensor_count` (uint64) et
`metadata_kv_count` (uint64), puis `metadata_kv_count` paires clé/valeur : clé
(uint64 longueur + UTF-8), `type` (uint32), valeur. Les types de valeur sont
0 U8, 1 I8, 2 U16, 3 I16, 4 U32, 5 I32, 6 F32, 7 BOOL (0/1), 8 STRING (uint64
longueur + UTF-8), 9 ARRAY (uint32 type des éléments + uint64 nombre d'éléments
+ éléments, imbrication possible), 10 U64, 11 I64 et 12 F64.

La magie est toujours `GGUF`, quel que soit le boutisme. Un fichier
big-endian (permis par la version 3, même schéma en version 2) est reconnu par
les octets de sa `version` : lue en petit boutisme, elle donne une valeur dont
les 16 bits de poids faible sont nuls (`0x03000000` par exemple), ce qui indique
un fichier big-endian ; la même valeur est alors relue en grand boutisme. La
version 1, de structure antérieure, n'est pas décrite ici et est refusée
explicitement plutôt qu'interprétée au hasard.

Ce module ne lit que ce qui est nécessaire pour obtenir
`general.architecture` : il s'arrête dès que cette métadonnée est trouvée, sans
valider les tenseurs, les poids ni le reste du fichier. Il ne connaît ni
`HfFileSystem`, ni le réseau, ni le système de fichiers : le flux binaire est
fourni par l'appelant sous la forme d'une fonction `read(n)` (la méthode `read`
d'un objet fichier convient). Chaque lecture demande un nombre d'octets borné et
la fonction peut en renvoyer moins, cas d'une lecture épisodique. Aucun `read()`
sans argument n'est utilisé : la tâche 5.3 lira ce flux à distance, où une
lecture non bornée du fichier entier serait inacceptable.

Bornes documentées, qui ne constituent ni une qualification PC ni un plafond de
configuration réelle :

- `OCTETS_MAX_ENTETE` (64 Mio) limite le total lu ou sauté pour l'en-tête ;
  c'est une limite de lecture, pas une garantie d'universalité : un fichier
  dont `general.architecture` apparaît au-delà de cette borne est refusé ;
- `TAILLE_BLOC` (64 Kio) borne chaque `read(n)` demandé au flux ;
- `PROFONDEUR_MAX_TABLEAUX` (8) borne l'imbrication des tableaux sautés.

Les chaînes sautées sont lues par blocs et jetées, jamais assemblées en
mémoire : une longueur hostile n'alloue rien et ne fait pas boucler
indéfiniment. Ces contrôles ne constituent pas une sandbox.
"""

from __future__ import annotations

import struct
from collections.abc import Callable
from dataclasses import dataclass

CLE_ARCHITECTURE = "general.architecture"

MAGIE = b"GGUF"
VERSIONS_ACCEPTEES: tuple[int, ...] = (2, 3)

TYPE_U8 = 0
TYPE_I8 = 1
TYPE_U16 = 2
TYPE_I16 = 3
TYPE_U32 = 4
TYPE_I32 = 5
TYPE_F32 = 6
TYPE_BOOL = 7
TYPE_CHAINE = 8
TYPE_TABLEAU = 9
TYPE_U64 = 10
TYPE_I64 = 11
TYPE_F64 = 12

# Taille fixe en octets des types scalaires ; STRING et ARRAY ont une taille
# variable et sont traités à part.
TAILLES_SCALAIRES: dict[int, int] = {
    TYPE_U8: 1,
    TYPE_I8: 1,
    TYPE_U16: 2,
    TYPE_I16: 2,
    TYPE_U32: 4,
    TYPE_I32: 4,
    TYPE_F32: 4,
    TYPE_BOOL: 1,
    TYPE_U64: 8,
    TYPE_I64: 8,
    TYPE_F64: 8,
}

OCTETS_MAX_ENTETE = 64 * 1024 * 1024
TAILLE_BLOC = 64 * 1024
PROFONDEUR_MAX_TABLEAUX = 8

# Taille minimale d'une paire clé/valeur : longueur de clé vide (8) et type (4).
TAILLE_MINIMALE_CLE_VALEUR = 12


class EnteteGGUFInvalide(ValueError):
    """En-tête GGUF illisible : magie, version, structure, encodage ou borne.

    Ce refus ne prouve rien de la validité des tenseurs : le lecteur s'arrête
    avant eux et ne valide jamais les poids.
    """


@dataclass(frozen=True)
class EnteteGGUF:
    """Ce que l'en-tête a livré avant l'arrêt du lecteur.

    `architecture` provient de la métadonnée `general.architecture` et vaut
    `None` si la clé est absente de l'en-tête : le nom du fichier ne la remplace
    jamais. `boutisme` vaut `"petit"` ou `"grand"`, et `octets_lus` donne le
    nombre d'octets effectivement consommés, ce qui montre que le lecteur s'est
    arrêté à l'architecture et n'a pas parcouru les poids.
    """

    version: int
    boutisme: str
    architecture: str | None
    octets_lus: int

    def __post_init__(self) -> None:
        if self.version not in VERSIONS_ACCEPTEES:
            raise ValueError(f"version GGUF inattendue : {self.version!r}")
        if self.boutisme not in ("petit", "grand"):
            raise ValueError(f"boutisme inattendu : {self.boutisme!r}")
        if self.architecture is not None and (
            not isinstance(self.architecture, str) or not self.architecture
        ):
            raise ValueError("architecture attendue absente ou non vide")


class _Flux:
    """Lectures bornées sur une fonction `read(n)` fournie par l'appelant."""

    def __init__(
        self,
        source: Callable[[int], bytes],
        *,
        octets_max: int,
        taille_bloc: int,
    ) -> None:
        if not callable(source):
            raise TypeError("flux attendu sous forme de fonction read(n)")
        if not isinstance(octets_max, int) or isinstance(octets_max, bool):
            raise ValueError("octets_max doit être un entier")
        if octets_max <= 0:
            raise ValueError("octets_max doit être strictement positif")
        if not isinstance(taille_bloc, int) or isinstance(taille_bloc, bool):
            raise ValueError("taille_bloc doit être un entier")
        if taille_bloc <= 0:
            raise ValueError("taille_bloc doit être strictement positif")
        self._source = source
        self._octets_max = octets_max
        self._taille_bloc = min(taille_bloc, octets_max)
        self.octets_lus = 0

    def _demander(self, nombre: int) -> bytes:
        """Demande au plus `nombre` octets au flux, jamais plus qu'un bloc."""
        demande = min(nombre, self._taille_bloc, self._octets_max - self.octets_lus)
        if demande <= 0:
            raise EnteteGGUFInvalide(
                f"en-tête au-delà de la limite de {self._octets_max} octets lus"
            )
        bloc = self._source(demande)
        if not isinstance(bloc, (bytes, bytearray, memoryview)):
            raise EnteteGGUFInvalide(
                f"le flux doit renvoyer des octets, reçu {type(bloc).__name__}"
            )
        octets = bytes(bloc)
        if len(octets) > demande:
            raise EnteteGGUFInvalide(
                f"le flux a renvoyé {len(octets)} octets pour {demande} demandés"
            )
        self.octets_lus += len(octets)
        return octets

    def _verifier_budget(self, nombre: int) -> None:
        if nombre < 0:
            raise EnteteGGUFInvalide(f"longueur négative : {nombre}")
        if self.octets_lus + nombre > self._octets_max:
            raise EnteteGGUFInvalide(
                f"en-tête au-delà de la limite de {self._octets_max} octets lus"
            )

    def lire(self, nombre: int) -> bytes:
        """Lit exactement `nombre` octets, en assemblant des lectures bornées."""
        self._verifier_budget(nombre)
        morceaux = bytearray()
        while len(morceaux) < nombre:
            bloc = self._demander(nombre - len(morceaux))
            if not bloc:
                raise EnteteGGUFInvalide(
                    f"flux tronqué : {nombre} octets attendus, "
                    f"{len(morceaux)} reçus"
                )
            morceaux += bloc
        return bytes(morceaux)

    def sauter(self, nombre: int) -> None:
        """Ignore `nombre` octets par blocs, sans les assembler en mémoire."""
        self._verifier_budget(nombre)
        reste = nombre
        while reste:
            bloc = self._demander(reste)
            if not bloc:
                raise EnteteGGUFInvalide(
                    f"flux tronqué : {nombre} octets à ignorer, "
                    f"{nombre - reste} lus"
                )
            reste -= len(bloc)


def _entier(flux: _Flux, format_: str, ordre: str) -> int:
    taille = struct.calcsize(format_)
    return struct.unpack(ordre + format_, flux.lire(taille))[0]


def _chaine(flux: _Flux, ordre: str, quoi: str) -> str:
    longueur = _entier(flux, "Q", ordre)
    octets = flux.lire(longueur)
    try:
        return octets.decode("utf-8")
    except UnicodeDecodeError:
        raise EnteteGGUFInvalide(f"{quoi} non UTF-8") from None


def _sauter_valeur(flux: _Flux, ordre: str, type_valeur: int, profondeur: int) -> None:
    """Ignore une valeur de type connu, sans en conserver le contenu."""
    taille = TAILLES_SCALAIRES.get(type_valeur)
    if taille is not None:
        flux.sauter(taille)
        return
    if type_valeur == TYPE_CHAINE:
        flux.sauter(_entier(flux, "Q", ordre))
        return
    if type_valeur == TYPE_TABLEAU:
        if profondeur >= PROFONDEUR_MAX_TABLEAUX:
            raise EnteteGGUFInvalide(
                f"tableaux imbriqués au-delà de {PROFONDEUR_MAX_TABLEAUX} niveaux"
            )
        type_element = _entier(flux, "I", ordre)
        nombre = _entier(flux, "Q", ordre)
        taille = TAILLES_SCALAIRES.get(type_element)
        if taille is not None:
            flux.sauter(nombre * taille)
            return
        if type_element not in (TYPE_CHAINE, TYPE_TABLEAU):
            raise EnteteGGUFInvalide(f"type de métadonnée inconnu : {type_element}")
        # Chaque élément consomme au moins 8 octets (longueur de chaîne) ou
        # 12 octets (en-tête de tableau) : la borne d'octets arrête la boucle.
        for _ in range(nombre):
            _sauter_valeur(flux, ordre, type_element, profondeur + 1)
        return
    raise EnteteGGUFInvalide(f"type de métadonnée inconnu : {type_valeur}")


def lire_entete_gguf(
    source: Callable[[int], bytes],
    *,
    octets_max: int = OCTETS_MAX_ENTETE,
    taille_bloc: int = TAILLE_BLOC,
) -> EnteteGGUF:
    """Extrait `general.architecture` d'un en-tête GGUF version 2 ou 3.

    "source" est appelée uniquement sous la forme `source(n)` avec `0 < n <=
    taille_bloc`, jamais sans argument. Une source qui renvoie moins d'octets que
    demandé est acceptée tant que le flux n'est pas épuisé. La magie attendue est
    toujours `GGUF` ; le boutisme est déduit des octets de la version, jamais de
    la magie. Le lecteur s'arrête dès que `general.architecture` est trouvée : le
    reste du fichier, tenseurs compris, n'est ni lu ni validé.

    Lève `EnteteGGUFInvalide` si la magie, la version, la structure ou l'encodage
    ne sont pas exploitables, si le flux est tronqué ou si la borne d'octets est
    atteinte, et `TypeError` si `source` n'est pas appelable. Une architecture
    absente n'est pas une exception : le résultat porte `architecture=None`.
    """
    flux = _Flux(source, octets_max=octets_max, taille_bloc=taille_bloc)
    magie = flux.lire(4)
    if magie != MAGIE:
        raise EnteteGGUFInvalide(
            f"magie GGUF absente : {magie!r} (attendu {MAGIE!r} quel que soit le "
            "boutisme)"
        )
    # Le boutisme se lit sur les octets de la version, pas sur ceux de la magie.
    octets_version = flux.lire(4)
    version = struct.unpack("<I", octets_version)[0]
    if version & 0xFFFF == 0:
        ordre, boutisme = ">", "grand"
        version = struct.unpack(">I", octets_version)[0]
    else:
        ordre, boutisme = "<", "petit"
    if version not in VERSIONS_ACCEPTEES:
        raise EnteteGGUFInvalide(
            f"version GGUF {version} non prise en charge : versions "
            f"{' et '.join(str(acceptee) for acceptee in VERSIONS_ACCEPTEES)} "
            "seulement (la version 1 a une structure antérieure et n'est pas lue)"
        )
    # tensor_count n'apprend rien sur l'architecture et n'est pas validé.
    flux.sauter(8)
    nombre_metadonnees = _entier(flux, "Q", ordre)
    if nombre_metadonnees * TAILLE_MINIMALE_CLE_VALEUR > octets_max:
        raise EnteteGGUFInvalide(
            f"nombre de métadonnées incompatible avec la limite de {octets_max} "
            "octets lus : l'architecture ne peut pas être trouvée dans cet en-tête"
        )
    for _ in range(nombre_metadonnees):
        cle = _chaine(flux, ordre, "clé de métadonnée")
        type_valeur = _entier(flux, "I", ordre)
        if cle != CLE_ARCHITECTURE:
            _sauter_valeur(flux, ordre, type_valeur, 0)
            continue
        if type_valeur != TYPE_CHAINE:
            raise EnteteGGUFInvalide(
                f"{CLE_ARCHITECTURE} de type {type_valeur} : chaîne attendue"
            )
        architecture = _chaine(flux, ordre, CLE_ARCHITECTURE)
        if not architecture:
            raise EnteteGGUFInvalide(f"{CLE_ARCHITECTURE} vide")
        return EnteteGGUF(
            version=version,
            boutisme=boutisme,
            architecture=architecture,
            octets_lus=flux.octets_lus,
        )
    return EnteteGGUF(
        version=version,
        boutisme=boutisme,
        architecture=None,
        octets_lus=flux.octets_lus,
    )
