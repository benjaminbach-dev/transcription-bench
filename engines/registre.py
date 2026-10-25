"""Registre de moteurs par instance : déclarations listées, adaptateurs différés.

Le registre est construit une fois au démarrage (les tests en créent d'autres)
puis lu par l'interface. Il ne charge aucun paquet moteur : `enregistrer`,
`lister` et `obtenir` ne manipulent que des déclarations. L'adaptateur
d'exécution n'est importé qu'à la demande explicite (`charger_adaptateur`),
par `importlib`, et le module importé doit faire ses propres imports de
bibliothèques de moteur à l'intérieur de ses fonctions.

La référence de module vient du code du dépôt (`engines/declarations.py`), jamais
d'une entrée utilisateur ou d'un dépôt de modèle : la validation lexicale de la
déclaration écarte chemins et URL, elle ne constitue pas une sandbox.
"""

from __future__ import annotations

import importlib
from types import ModuleType

from engines.declarations import DeclarationAdaptateur, declarations_fournies


class DeclarationRefusee(ValueError):
    """Déclaration refusée, notamment un identifiant déjà enregistré."""


class MoteurInconnu(KeyError):
    """Identifiant absent du registre."""


class AdaptateurIndisponible(RuntimeError):
    """Adaptateur non déclaré, module absent ou import en échec."""


class RegistreMoteurs:
    """Déclarations de moteurs d'une instance, dans leur ordre d'enregistrement.

    Aucun verrou : le registre est rempli au démarrage puis seulement lu. Une
    nouvelle déclaration ne remplace jamais une déclaration existante.
    """

    def __init__(self) -> None:
        self._declarations: dict[str, DeclarationAdaptateur] = {}

    def enregistrer(self, declaration: DeclarationAdaptateur) -> None:
        """Ajoute une déclaration sans charger son adaptateur.

        Lève `DeclarationRefusee` si l'identifiant est déjà enregistré.
        """
        if not isinstance(declaration, DeclarationAdaptateur):
            raise TypeError("déclaration d'adaptateur attendue")
        if declaration.identifiant in self._declarations:
            raise DeclarationRefusee(
                f"moteur déjà enregistré : {declaration.identifiant!r}"
            )
        self._declarations[declaration.identifiant] = declaration

    def lister(self) -> tuple[DeclarationAdaptateur, ...]:
        """Renvoie les déclarations enregistrées, sans charger aucun adaptateur."""
        return tuple(self._declarations.values())

    def obtenir(self, identifiant: str) -> DeclarationAdaptateur:
        """Renvoie la déclaration d'un moteur, ou lève `MoteurInconnu`."""
        try:
            return self._declarations[identifiant]
        except KeyError:
            raise MoteurInconnu(identifiant) from None

    def charger_adaptateur(self, identifiant: str) -> ModuleType:
        """Importe l'adaptateur d'exécution, seulement à la demande.

        Lève `MoteurInconnu` si le moteur n'est pas déclaré et
        `AdaptateurIndisponible` si la déclaration n'a pas d'adaptateur, si le
        module n'existe pas encore ou si un de ses imports échoue.
        """
        declaration = self.obtenir(identifiant)
        if declaration.module_adaptateur is None:
            raise AdaptateurIndisponible(
                f"aucun adaptateur déclaré pour le moteur {identifiant!r}"
            )
        try:
            return importlib.import_module(declaration.module_adaptateur)
        except ImportError as exception:
            raise AdaptateurIndisponible(
                f"adaptateur indisponible pour le moteur {identifiant!r} "
                f"({declaration.module_adaptateur}) : {exception}"
            ) from exception


def creer_registre_fourni() -> RegistreMoteurs:
    """Registre prérempli des quatre déclarations fournies, sans adaptateur chargé."""
    registre = RegistreMoteurs()
    for declaration in declarations_fournies():
        registre.enregistrer(declaration)
    return registre
