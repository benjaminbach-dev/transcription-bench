"""Déclarations d'adaptateurs de moteurs, sans aucune dépendance moteur.

Une déclaration décrit ce qu'un moteur expose au reste du programme :
identifiant stable, nom lisible, fichier de dépendances verrouillées, règle de
compatibilité des modèles, familles prises en charge avec leur durée native et
leurs réglages. Elle ne fait que des imports de la bibliothèque standard et ne
charge aucun paquet moteur : c'est le serveur qui l'importe, pas le processus du
moteur.

L'état de qualification reflète les preuves disponibles, sans les dépasser :
les familles validées sur le PC Linux de test (jalon 0 du 2026-11-01, puis
adaptateurs des tâches 8.1 à 8.3) portent `qualifiee=True` et déclarent la durée
native réellement prouvée. La qualification Windows reste due à la CI (tâches
10.5 et 10.6) : elle n'est ni annoncée ni déduite d'une mesure Linux. Sans durée
native déclarée, le runner applique les fenêtres fixes de 30 s ; avec une durée
native, il traite l'audio en un appel jusqu'à cette durée et découpe au-delà
(D9). Les réglages exposés sont ceux que l'adaptateur applique réellement, avec
les défauts mesurés. Les fichiers `requirements/*.txt` sont les verrous validés
au jalon 0 et repris à l'identique sous `requirements/`.

Le moteur factice est le seul dont la déclaration porte `factice=True` (tâche
4.3). Ce drapeau, fixé par le code du dépôt et jamais par un job, autorise le
runner à exécuter ses familles non qualifiées et à marquer ses textes et
mesures comme simulés. Il ne vaut pas qualification PC : aucune inférence
réelle n'est effectuée. Les trois moteurs réels sont qualifiés séparément, après
validation sur le PC Linux de test ; cette qualification ne vaut pas Windows.

La référence `module_adaptateur` pointe vers du code de ce dépôt uniquement
(`engines.adaptateurs.*`) ; elle est importée à la demande par le registre.
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
    l'API ou la stratégie employée. Elle ne dépasse jamais la durée réellement
    prouvée sur PC. Laisser `Famille.duree_native` à `None` signifie que le
    mécanisme reste non prouvé et que le runner découpera en fenêtres fixes de
    30 s ; au-delà de `secondes_max`, le runner découpe aussi en fenêtres fixes.
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
    jamais annoncée comme opérationnelle. `qualifiee=True` s'appuie sur une
    validation Linux consignée ; elle ne vaut pas validation Windows. Les réglages appartiennent à la famille
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
    pour `choix`. Les réglages fournis sont exactement ceux que l'adaptateur du
    moteur applique ; le défaut est la valeur mesurée au jalon 0, ou la valeur
    documentée quand aucune mesure n'existe.
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

    `modules_verification` énumère les noms de modules Python (bibliothèque
    standard comprise) que le contrôle d'import exécute dans l'environnement du
    moteur, avec l'interpréteur de cet environnement. Ces noms viennent du code
    du dépôt, jamais d'une requête ou d'un job, et ne portent aucune version :
    ils permettent de vérifier le bon environnement sans importer de paquet
    moteur dans le serveur et sans supposer une version avant validation PC.

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
    modules_verification: tuple[str, ...] = ()
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
        if not isinstance(self.modules_verification, tuple):
            raise ValueError("modules_verification attendu sous forme de tuple")
        for module in self.modules_verification:
            if not isinstance(module, str) or not _MOTIF_MODULE.fullmatch(module):
                raise ValueError(
                    "module de vérification attendu sous forme de nom Python "
                    f"pointé : {module!r}"
                )
        if len(set(self.modules_verification)) != len(self.modules_verification):
            raise ValueError("modules de vérification en double")
        if self.fichier_requirements is not None and not self.modules_verification:
            raise ValueError(
                "une déclaration installable doit préciser au moins un module de "
                "vérification pour contrôler son environnement"
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


def motif_famille_non_executable(
    declaration: DeclarationAdaptateur, famille: Famille
) -> str | None:
    """Motif pour lequel le runner refuserait cette famille, ou `None`.

    Règle unique, partagée par `engines.runner` et par le service des demandes
    d'exécution : une famille n'est exécutable que si la déclaration est
    factice (`factice=True`, sans qualification PC) ou si la famille est
    qualifiée sur PC. Une durée native déclarée n'est pas un refus : le runner
    l'applique tant que la durée décodée ne la dépasse pas, et découpe sinon en
    fenêtres fixes de 30 s (D9). Le motif renvoyé est un texte prêt à afficher ;
    il ne contient ni chemin ni donnée d'exécution.
    """
    if not famille.qualifiee and not declaration.factice:
        return (
            f"famille {famille.identifiant!r} du moteur "
            f"{declaration.identifiant!r} non qualifiée sur PC "
            "(jalon 0 et tâches 8.x)"
        )
    return None


#: Durée native prouvée des deux moteurs GGUF/CT2 (audio long du jalon 0 :
#: 47,703 688 s décodées, transcrites en un seul appel). Volontairement arrondie
#: vers le bas à 47,7 s : un audio de 47,703 688 s bascule donc sur les fenêtres
#: fixes de 30 s, choix conservateur qui ne dépasse jamais la durée prouvée.
DUREE_NATIVE_AUDIO_LONG_S = 47.7
#: Durée native prouvée des deux familles Transformers : 300,884 813 s
#: décodées, sous le plafond de 12 Gio (5 min), arrondie vers le bas par le
#: même choix conservateur.
DUREE_NATIVE_TRANSFORMERS_S = 300.0

DECLARATION_FASTER_WHISPER = DeclarationAdaptateur(
    identifiant="faster-whisper",
    nom="faster-whisper (CTranslate2)",
    fichier_requirements="requirements/faster-whisper.txt",
    regle_compatibilite="ctranslate2-whisper",
    familles=(
        Famille(
            "whisper",
            "Whisper",
            qualifiee=True,
            duree_native=DureeNative(
                DUREE_NATIVE_AUDIO_LONG_S,
                "transcription en un appel faster-whisper (audio long de "
                "47,7 s prouvé au jalon 0 Linux)",
            ),
            reglages=(
                Reglage(
                    "compute_type",
                    "Type de calcul",
                    TYPE_CHOIX,
                    "int8",
                    "Type de calcul CTranslate2 ; int8 est la seule valeur "
                    "mesurée au jalon 0 (relue int8_float32).",
                    valeurs=("int8", "float32"),
                ),
                Reglage(
                    "beam_size",
                    "Faisceau de décodage",
                    TYPE_ENTIER,
                    5,
                    "Taille du faisceau ; 5 au jalon 0.",
                ),
            ),
        ),
    ),
    module_adaptateur="engines.adaptateurs.faster_whisper",
    modules_verification=("faster_whisper", "numpy"),
)

DECLARATION_TRANSCRIBE_CPP = DeclarationAdaptateur(
    identifiant="transcribe-cpp",
    nom="transcribe.cpp (GGUF)",
    fichier_requirements="requirements/transcribe-cpp.txt",
    regle_compatibilite="transcribe-cpp-gguf",
    familles=(
        Famille(
            "whisper",
            "Whisper",
            qualifiee=True,
            duree_native=DureeNative(
                DUREE_NATIVE_AUDIO_LONG_S,
                "session.run en un appel transcribe.cpp (audio long de "
                "47,7 s prouvé au jalon 0 Linux)",
            ),
            reglages=(
                Reglage(
                    "no_mmap",
                    "Sans mmap",
                    TYPE_BOOLEEN,
                    False,
                    "Copier les poids en mémoire au lieu de les mmapser ; "
                    "le mode effectif est consigné.",
                ),
                Reglage(
                    "condition_on_prev_tokens",
                    "Contexte des jetons précédents",
                    TYPE_BOOLEEN,
                    False,
                    "Conditionner sur les jetons précédents ; désactivé au "
                    "jalon 0.",
                ),
            ),
        ),
    ),
    module_adaptateur="engines.adaptateurs.transcribe_cpp",
    modules_verification=("transcribe_cpp", "numpy"),
)

DECLARATION_TRANSFORMERS = DeclarationAdaptateur(
    identifiant="transformers",
    nom="Hugging Face Transformers",
    fichier_requirements="requirements/transformers.txt",
    regle_compatibilite="transformers-safetensors",
    familles=(
        Famille(
            "whisper",
            "Whisper",
            qualifiee=True,
            duree_native=DureeNative(
                DUREE_NATIVE_TRANSFORMERS_S,
                "long-form natif Transformers (truncation=False, "
                "attention_mask), 5 min prouvées au jalon 0 Linux",
            ),
            reglages=(
                Reglage(
                    "do_normalize",
                    "Normalisation audio",
                    TYPE_BOOLEEN,
                    False,
                    "Normaliser le signal avant l'extraction mel ; désactivée "
                    "au jalon 0 (aucun effet observé sur l'audio de synthèse).",
                ),
            ),
        ),
        Famille(
            "parakeet-tdt",
            "Parakeet TDT",
            qualifiee=True,
            duree_native=DureeNative(
                DUREE_NATIVE_TRANSFORMERS_S,
                "une passe native TDT, 5 min prouvées au jalon 0 Linux "
                "(attention non fenêtrée)",
            ),
        ),
    ),
    module_adaptateur="engines.adaptateurs.transformers",
    modules_verification=("transformers", "numpy"),
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
    pas installés : le lot 4.4 affiche leur état, et leurs adaptateurs sont
    fournis par les tâches 8.x. Le moteur factice reste exécutable sans modèle ni
    qualification PC.
    """
    return DECLARATIONS_FOURNIES
