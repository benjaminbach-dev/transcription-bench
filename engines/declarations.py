"""Déclarations d'adaptateurs de moteurs, sans aucune dépendance moteur.

Une déclaration décrit ce qu'un moteur expose au reste du programme :
identifiant stable, nom lisible, fichier de dépendances verrouillées, règle de
compatibilité des modèles, familles prises en charge avec leur durée native et
leurs réglages. Elle ne fait que des imports de la bibliothèque standard et ne
charge aucun paquet moteur : c'est le serveur qui l'importe, pas le processus du
moteur.

Aucune capacité réelle n'est qualifiée ici. Les familles restent
`qualifiee=False` et aucune durée native n'est annoncée tant que le jalon 0 sur
PC n'a pas prouvé le mécanisme correspondant ; sans durée native déclarée, le
runner appliquera les fenêtres fixes de 30 s. Aucun réglage réel n'est fourni :
les réglages réellement exposés par famille seront fixés par le jalon PC et les
tâches 8.x. Les fichiers `requirements/*.txt` sont déclarés par leur chemin
conventionnel mais ne sont pas créés ici : les verrous ne sont pas encore
validés.

Le moteur factice est le seul dont la déclaration porte `factice=True` (tâche
4.3). Ce drapeau, fixé par le code du dépôt et jamais par un job, autorise le
runner à exécuter ses familles non qualifiées et à marquer ses textes et
mesures comme simulés. Il ne vaut pas qualification PC : aucune inférence
réelle n'est effectuée et les trois moteurs réels restent refusés tant que le
jalon PC et les tâches 8.x ne les ont pas prouvés.

La référence `module_adaptateur` pointe vers du code de ce dépôt uniquement
(`engines.adaptateurs.*`) ; elle est importée à la demande par le registre, et
les modules correspondants n'existent pas encore à ce stade.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass

TYPE_ENTIER = "entier"
TYPE_BOOLEEN = "booleen"
TYPE_TEXTE = "texte"
TYPE_CHOIX = "choix"

TYPES_REGLAGE = (TYPE_ENTIER, TYPE_BOOLEEN, TYPE_TEXTE, TYPE_CHOIX)

# Identifiant de moteur ou de famille : minuscules ASCII, chiffres et tirets.
_MOTIF_IDENTIFIANT = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*", re.ASCII)
# Nom de réglage : minuscules ASCII, chiffres et soulignés (futur mot-clé du moteur).
_MOTIF_NOM_REGLAGE = re.compile(r"[a-z][a-z0-9_]*", re.ASCII)
# Nom pointé de module Python, sans chemin, URL ni remontée.
_MOTIF_MODULE = re.compile(r"[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*", re.ASCII)
# Fichier de verrou conventionnel, relatif à la racine du projet.
_MOTIF_REQUIREMENTS = re.compile(r"requirements/[a-z0-9-]+\.txt", re.ASCII)


def _exiger_identifiant(valeur: str, champ: str) -> None:
    if not isinstance(valeur, str) or not _MOTIF_IDENTIFIANT.fullmatch(valeur):
        raise ValueError(
            f"{champ} invalide : {valeur!r} "
            "(attendu : minuscules ASCII, chiffres et tirets)"
        )


def _exiger_nom_reglage(valeur: str) -> None:
    if not isinstance(valeur, str) or not _MOTIF_NOM_REGLAGE.fullmatch(valeur):
        raise ValueError(
            f"nom de réglage invalide : {valeur!r} "
            "(attendu : minuscules ASCII, chiffres et soulignés)"
        )


def _exiger_texte_non_vide(valeur: str, champ: str) -> None:
    if not isinstance(valeur, str) or not valeur.strip():
        raise ValueError(f"{champ} attendu non vide")


@dataclass(frozen=True)
class DureeNative:
    """Mécanisme natif d'audio long, déclaré seulement s'il est prouvé.

    `secondes_max` est la durée maximale traitée en un appel natif et `methode`
    l'API ou la stratégie employée. Aucune déclaration fournie n'en contient :
    laisser `Famille.duree_native` à `None` signifie que le mécanisme reste non
    prouvé et que le runner découpera en fenêtres fixes de 30 s.
    """

    secondes_max: float
    methode: str

    def __post_init__(self) -> None:
        if not isinstance(self.secondes_max, (int, float)) or isinstance(
            self.secondes_max, bool
        ):
            raise ValueError("secondes_max doit être un nombre")
        if not math.isfinite(self.secondes_max) or self.secondes_max <= 0:
            raise ValueError("secondes_max doit être un nombre fini strictement positif")
        _exiger_texte_non_vide(self.methode, "méthode de durée native")


@dataclass(frozen=True)
class Famille:
    """Famille de modèles prise en charge par un moteur.

    `qualifiee=False` signifie que la famille n'a pas été validée sur PC (jalon
    0 puis tâches 8.x) : elle est déclarée pour la structure et l'interface,
    jamais annoncée comme opérationnelle. Les réglages appartiennent à la famille
    qui les expose ; leurs noms y sont uniques.

    Cette valeur reste `False` pour la famille factice : exécuter le moteur
    factice ne demande aucune validation PC, car il ne charge aucun modèle et
    n'effectue aucune inférence. Le runner s'appuie pour cela sur
    `DeclarationAdaptateur.factice`, jamais sur cet indicateur de qualification.
    """

    identifiant: str
    libelle: str
    qualifiee: bool = False
    duree_native: DureeNative | None = None
    reglages: tuple[Reglage, ...] = ()

    def __post_init__(self) -> None:
        _exiger_identifiant(self.identifiant, "identifiant de famille")
        _exiger_texte_non_vide(self.libelle, "libellé de famille")
        noms_reglages = [reglage.nom for reglage in self.reglages]
        if len(set(noms_reglages)) != len(noms_reglages):
            raise ValueError("noms de réglage en double dans la famille")


@dataclass(frozen=True)
class Reglage:
    """Réglage proposé pour une exécution avec une famille de modèles.

    `type_valeur` appartient à `TYPES_REGLAGE` ; `valeurs` n'est renseigné que
    pour `choix`. Aucun réglage réel n'est fourni par les déclarations : les
    tâches 8.x fixent ceux qui seront effectivement exposés.
    """

    nom: str
    libelle: str
    type_valeur: str
    defaut: int | bool | str
    description: str
    valeurs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _exiger_nom_reglage(self.nom)
        _exiger_texte_non_vide(self.libelle, "libellé de réglage")
        _exiger_texte_non_vide(self.description, "description de réglage")
        if self.type_valeur not in TYPES_REGLAGE:
            raise ValueError(
                f"type de réglage inconnu : {self.type_valeur!r} "
                f"(attendu : {', '.join(TYPES_REGLAGE)})"
            )
        if self.type_valeur == TYPE_CHOIX:
            if not self.valeurs or len(set(self.valeurs)) != len(self.valeurs):
                raise ValueError("un réglage de type choix exige des valeurs uniques")
            if self.defaut not in self.valeurs:
                raise ValueError("le défaut d'un choix doit appartenir à ses valeurs")
        elif self.valeurs:
            raise ValueError("valeurs n'est autorisé que pour un réglage de type choix")
        elif self.type_valeur == TYPE_ENTIER:
            if not isinstance(self.defaut, int) or isinstance(self.defaut, bool):
                raise ValueError("le défaut d'un réglage entier doit être un entier")
        elif self.type_valeur == TYPE_BOOLEEN:
            if not isinstance(self.defaut, bool):
                raise ValueError("le défaut d'un réglage booléen doit être un booléen")
        elif not isinstance(self.defaut, str):
            raise ValueError("le défaut d'un réglage texte doit être un texte")


@dataclass(frozen=True)
class DeclarationAdaptateur:
    """Description complète d'un moteur, importable sans paquet moteur.

    `fichier_requirements` est le chemin conventionnel du verrou (ou `None` pour
    le moteur factice, qui utilise l'interpréteur du serveur). `regle_compatibilite`
    désigne la règle de compatibilité implémentée aux tâches 5.x. `module_adaptateur`
    est une référence pointée vers du code local, importée seulement au moment
    où une exécution est demandée (`RegistreMoteurs.charger_adaptateur`).

    `factice=True` est réservé au moteur factice du dépôt : le runner exécute
    alors ses familles malgré `qualifiee=False` et marque textes et mesures comme
    simulés. Ce drapeau n'est jamais lu depuis un job et ne se déduit pas d'un
    identifiant fourni : une déclaration qui ne le porte pas reste soumise à la
    qualification PC, même si elle s'appelle « factice ».
    """

    identifiant: str
    nom: str
    fichier_requirements: str | None
    regle_compatibilite: str
    familles: tuple[Famille, ...]
    module_adaptateur: str | None = None
    factice: bool = False

    def __post_init__(self) -> None:
        _exiger_identifiant(self.identifiant, "identifiant de moteur")
        if not isinstance(self.factice, bool):
            raise ValueError("factice doit être un booléen")
        _exiger_texte_non_vide(self.nom, "nom de moteur")
        _exiger_identifiant(self.regle_compatibilite, "règle de compatibilité")
        if self.fichier_requirements is not None and not _MOTIF_REQUIREMENTS.fullmatch(
            self.fichier_requirements
        ):
            raise ValueError(
                "fichier de dépendances attendu sous la forme "
                f"'requirements/<moteur>.txt' : {self.fichier_requirements!r}"
            )
        if self.module_adaptateur is not None and not _MOTIF_MODULE.fullmatch(
            self.module_adaptateur
        ):
            raise ValueError(
                "référence d'adaptateur attendue sous forme de module Python "
                f"local, sans chemin ni URL : {self.module_adaptateur!r}"
            )
        if not self.familles:
            raise ValueError("une déclaration doit mentionner au moins une famille")
        identifiants_familles = [famille.identifiant for famille in self.familles]
        if len(set(identifiants_familles)) != len(identifiants_familles):
            raise ValueError("identifiants de famille en double")

    @property
    def familles_qualifiees(self) -> tuple[Famille, ...]:
        """Familles validées sur PC ; vide tant que le jalon 0 n'a pas conclu."""
        return tuple(famille for famille in self.familles if famille.qualifiee)


DECLARATION_FASTER_WHISPER = DeclarationAdaptateur(
    identifiant="faster-whisper",
    nom="faster-whisper (CTranslate2)",
    fichier_requirements="requirements/faster-whisper.txt",
    regle_compatibilite="ctranslate2-whisper",
    familles=(Famille("whisper", "Whisper", qualifiee=False),),
    module_adaptateur="engines.adaptateurs.faster_whisper",
)

DECLARATION_TRANSCRIBE_CPP = DeclarationAdaptateur(
    identifiant="transcribe-cpp",
    nom="transcribe.cpp (GGUF)",
    fichier_requirements="requirements/transcribe-cpp.txt",
    regle_compatibilite="transcribe-cpp-gguf",
    familles=(Famille("whisper", "Whisper", qualifiee=False),),
    module_adaptateur="engines.adaptateurs.transcribe_cpp",
)

DECLARATION_TRANSFORMERS = DeclarationAdaptateur(
    identifiant="transformers",
    nom="Hugging Face Transformers",
    fichier_requirements="requirements/transformers.txt",
    regle_compatibilite="transformers-safetensors",
    familles=(
        Famille("whisper", "Whisper", qualifiee=False),
        Famille("parakeet-tdt", "Parakeet TDT", qualifiee=False),
    ),
    module_adaptateur="engines.adaptateurs.transformers",
)

DECLARATION_FACTICE = DeclarationAdaptateur(
    identifiant="factice",
    nom="Moteur factice (développement)",
    fichier_requirements=None,
    regle_compatibilite="aucune",
    familles=(Famille("factice", "Moteur factice", qualifiee=False),),
    module_adaptateur="engines.adaptateurs.factice",
    factice=True,
)

DECLARATIONS_FOURNIES: tuple[DeclarationAdaptateur, ...] = (
    DECLARATION_FASTER_WHISPER,
    DECLARATION_TRANSCRIBE_CPP,
    DECLARATION_TRANSFORMERS,
    DECLARATION_FACTICE,
)


def declarations_fournies() -> tuple[DeclarationAdaptateur, ...]:
    """Renvoie les quatre déclarations fournies, dans un ordre stable.

    Les trois moteurs réels sont déclarés même si leurs environnements ne sont
    pas installés : le lot 4.4 affichera leur état, et leurs adaptateurs seront
    ajoutés aux tâches 8.x. Le moteur factice est exécutable sans modèle ni
    qualification PC ; son adaptateur est ajouté en 4.3.
    """
    return DECLARATIONS_FOURNIES
