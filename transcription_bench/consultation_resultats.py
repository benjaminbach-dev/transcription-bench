"""Consultation des résultats enregistrés : liste et détail d'une transcription.

Tâche 7.1, format de stockage de D11. Ce module est **strictement en lecture** :
il ne crée, ne réécrit ni ne supprime aucun fichier, et n'appelle aucun moteur.
La comparaison côte à côte relève de la tâche 7.2 et n'est pas ici.

**Source unique** : les exécutions sont relues dans `data/results/*/run.json` et
les transcriptions dans chaque `<n>-<audio>/result.json`. Les lectures passent
par `transcription_bench.stockage.lire_json`, qui prend le verrou commun de
stockage : une page ne lit pas un fichier pendant son remplacement atomique.

**Chemins contrôlés** : seuls les dossiers dont le nom a la forme d'un
identifiant produit par le programme sont interprétés ; un lien symbolique ou un
nom non conforme est ignoré à la liste et refusé au détail. Le dossier d'un audio
est résolu par `paths.resoudre_dans_racine`, qui refuse un chemin absolu, une
remontée `..` ou un lien sortant. Aucun accès hors de `data/results` n'est
possible.

**Refus explicites** : un `run.json` illisible, d'un `schema` inconnu,
incohérent avec son dossier ou portant un état hors des cinq états connus n'est
jamais interprété. La liste le présente comme non interprétable, sans lien, et le
détail répond par un refus (page 422), sans réécrire le fichier ni renvoyer 500.
Un dossier de résultat sans `run.json` (création interrompue) n'est pas une
exécution enregistrée : il est ignoré, comme le fait la récupération de 6.5.

**États et résultats partiels** : une exécution est affichée avec son état
(`running`, `completed`, `interrupted`, `abandoned`, `failed`) et marquée comme
partielle tant qu'elle n'est pas terminée. Les transcriptions déjà écrites
restent alors consultables et sont signalées comme partielles ; un audio sans
résultat est affiché comme non traité, jamais comme un texte vide ou une mesure
à zéro.

**Mesures** : une mesure absente (`null`, non numérique ou non finie) reste
absente et s'affiche « indisponible ». Le RTF est recalculé sur la durée
**décodée** par `resultats.calculer_rtf` : aucun RTF sur une durée nulle ou
absente, et le repère d'objectif (`REPERE_RTF`) n'exclut ni ne bloque jamais une
transcription plus lente.

**Marques** : les marques `factice`, `synthetique` et `mesures_simulees` sont
reprises telles quelles de `run.json` et de chaque `result.json`, et affichées
dans toutes les vues ; aucune n'est déduite.
"""

from __future__ import annotations

import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from transcription_bench.paths import (
    NOM_DOSSIER_RESULTATS,
    ValeurRefusee,
    resoudre_dans_racine,
    resoudre_resultat,
)
from transcription_bench.resultats import (
    ETAT_ABANDONNEE,
    ETAT_ECHOUEE,
    ETAT_EN_COURS,
    ETAT_INTERROMPUE,
    ETAT_TERMINEE,
    MOTIF_IDENTIFIANT,
    NOM_FICHIER_EXECUTION,
    NOM_FICHIER_RESULTAT,
    SCHEMA,
    STATUT_ERREUR,
    STATUT_NON_TRAITE,
    STATUT_OK,
    calculer_rtf,
)
from transcription_bench.stockage import JsonInvalide, lire_json

#: Repère d'objectif du RTF, affiché sans jamais bloquer ni exclure.
REPERE_RTF = 2

LIBELLES_ETATS_EXECUTION: dict[str, str] = {
    ETAT_EN_COURS: "en cours",
    ETAT_TERMINEE: "terminée",
    ETAT_INTERROMPUE: "interrompue",
    ETAT_ABANDONNEE: "abandonnée",
    ETAT_ECHOUEE: "en échec",
}

LIBELLES_STATUTS_AUDIO: dict[str, str] = {
    STATUT_OK: "transcrit",
    STATUT_ERREUR: "erreur",
    STATUT_NON_TRAITE: "non traité",
}

MOTIF_NON_TRAITE = (
    "Audio non traité : aucun résultat n'a été enregistré (exécution non "
    "terminée, arrêt ou échec avant cet audio)"
)
MOTIF_RESULTAT_ABSENT = (
    "Aucun résultat enregistré pour cet audio : rien n'est affiché et aucune "
    "mesure n'est remplacée par zéro"
)
MOTIF_RESULTAT_ILLISIBLE = (
    "Résultat de l'audio illisible (JSON invalide ou fichier inaccessible) : "
    "rien n'est affiché et le fichier n'a pas été modifié"
)
MOTIF_DOSSIER_REFUSE = (
    "Dossier d'audio refusé (chemin hors du dossier de l'exécution) : aucun "
    "fichier n'est lu"
)
MOTIF_FICHIER_REFUSE = (
    "Fichier de résultat refusé (chemin hors du dossier de l'audio) : aucun "
    "fichier n'est lu"
)

#: Champs affichés, avec leur libellé et la conversion appliquée à la lecture.
#: Une valeur `None` s'affiche « indisponible » ; aucune n'est remplacée par 0.
CHAMPS_MODELE: tuple[tuple[str, str], ...] = (
    ("identifiant", "Identifiant demandé"),
    ("id_resolu", "Identifiant canonique"),
    ("commit", "Révision figée"),
    ("cle", "Clé locale"),
    ("fichier_gguf", "Variante GGUF"),
)
CHAMPS_MOTEUR: tuple[tuple[str, str], ...] = (
    ("identifiant", "Identifiant du moteur"),
    ("nom", "Nom du moteur"),
    ("empreinte_verrou", "Empreinte du verrou de dépendances du moteur"),
)
CHAMPS_MACHINE: tuple[tuple[str, str], ...] = (
    ("os", "Système d'exploitation"),
    ("version_os", "Version du système"),
    ("architecture", "Architecture"),
    ("processeur", "Processeur"),
    ("coeurs_physiques", "Cœurs physiques"),
    ("coeurs_logiques", "Cœurs logiques"),
    ("ram_totale_octets", "RAM totale (octets)"),
)
CHAMPS_PROGRAMME: tuple[tuple[str, str], ...] = (
    ("nom", "Programme"),
    ("version", "Version"),
    ("python", "Python"),
    ("empreinte_verrou", "Empreinte de uv.lock"),
    ("pyav", "PyAV"),
)
CHAMPS_PROCESSUS: tuple[tuple[str, str], ...] = (
    ("pid", "PID du moteur"),
    ("lance_a", "Lancé à"),
    ("code_sortie", "Code de sortie"),
)
CHAMPS_AUDIO: tuple[tuple[str, str], ...] = (
    ("nom", "Nom"),
    ("format", "Format"),
    ("taille_octets", "Taille (octets)"),
    ("empreinte_sha256", "Empreinte SHA-256"),
    ("duree_indicative_s", "Durée indicative (s)"),
    ("duree_decodee_s", "Durée décodée (s)"),
    ("echantillons", "Échantillons"),
)

#: Paire libellé / valeur affichable, sans objet imbriqué.
Paire = tuple[str, Any]


class LectureResultatsImpossible(RuntimeError):
    """Le dossier des résultats ne peut pas être listé (droits, E/S)."""


class ResultatIntrouvable(LookupError):
    """Aucune exécution enregistrée sous cet identifiant."""


class ResultatNonInterpretable(ValueError):
    """`run.json` illisible, d'un schéma inconnu ou incohérent : jamais interprété."""


@dataclass(frozen=True)
class ExecutionListee:
    """Ligne de la liste des exécutions, ou en-tête du détail.

    `exploitable` vaut `False` quand `run.json` n'a pas pu être interprété :
    seuls `identifiant` et `motif` sont alors renseignés ; aucune donnée n'est
    inventée et aucun lien de détail n'est proposé. `marques` vaut alors `None`
    (« indisponible »), à distinguer d'une exécution sans aucune marque (`()`).
    """

    identifiant: str
    etat: str | None
    libelle_etat: str
    cree_le: str | None
    modele: str | None
    moteur: str | None
    audios_traites: int | None
    audios_total: int | None
    duree_operation_s: float | None
    partiel: bool
    marques: tuple[str, ...] | None
    exploitable: bool
    motif: str | None


@dataclass(frozen=True)
class MesuresVue:
    """Mesures globales d'une exécution ; `None` = mesure indisponible."""

    duree_operation_s: float | None
    duree_processus_s: float | None
    duree_chargement_s: float | None
    pic_memoire_octets: int | None
    pic_memoire_partiel: bool | None


@dataclass(frozen=True)
class MesuresAudioVue:
    """Mesures d'une transcription ; `None` = mesure indisponible."""

    temps_decodage_s: float | None
    duree_transcription_s: float | None
    temps_cpu_s: float | None
    rtf: float | None
    pic_memoire_octets: int | None


@dataclass(frozen=True)
class SegmentVue:
    """Segment horodaté fourni par le moteur.

    Une borne non finie (NaN, infini) est acceptée par le runner ; elle est
    conservée comme indisponible (`None`) sans masquer le texte du segment.
    """

    debut_s: float | None
    fin_s: float | None
    texte: str


@dataclass(frozen=True)
class TranscriptionVue:
    """Transcription relue dans le `result.json` d'un audio."""

    statut: str
    ecrit_le: str | None
    texte: str | None
    segments: tuple[SegmentVue, ...]
    marques: tuple[str, ...]
    audio: tuple[Paire, ...]
    mesures: MesuresAudioVue
    reglages_effectifs: tuple[Paire, ...]
    threads: tuple[Paire, ...]
    langue_imposee: str | None
    fenetre: tuple[Paire, ...]
    erreur: str | None


@dataclass(frozen=True)
class AudioVue:
    """Audio d'une exécution : transcription disponible ou motif d'absence."""

    ordre: int
    nom: str
    dossier: str
    statut: str
    libelle_statut: str
    erreur: str | None
    partiel: bool
    motif_indisponible: str | None
    transcription: TranscriptionVue | None


@dataclass(frozen=True)
class DetailExecutionVue:
    """Détail d'une exécution : métadonnées, mesures globales et audios."""

    execution: ExecutionListee
    fin: str | None
    erreur: str | None
    famille: str | None
    threads_demandes: Any
    threads_appliques: Any
    fenetre_fixe_s: Any
    reglages: tuple[Paire, ...]
    reglages_effectifs: tuple[Paire, ...]
    modele: tuple[Paire, ...]
    moteur: tuple[Paire, ...]
    versions_moteur: tuple[Paire, ...]
    machine: tuple[Paire, ...]
    programme: tuple[Paire, ...]
    processus: tuple[Paire, ...]
    mesures: MesuresVue
    audios: tuple[AudioVue, ...]
    partiel: bool


class ConsultationResultats:
    """Lectures des résultats d'un dossier de données, sans aucune écriture.

    `donnees` est la racine `data/` ; le dossier des résultats est
    `donnees/results`. Les méthodes ne lèvent pour un fichier de résultat
    qu'aux endroits prévus : la liste ne lève jamais pour une exécution
    illisible, et le détail lève `ResultatNonInterpretable`.
    """

    def __init__(self, donnees: Path | str) -> None:
        self._donnees = Path(donnees)

    @property
    def dossier_resultats(self) -> Path:
        """Dossier des résultats attendu, qu'il existe ou non."""
        return self._donnees / NOM_DOSSIER_RESULTATS

    def lister(self) -> tuple[ExecutionListee, ...]:
        """Exécutions enregistrées, des plus récentes aux plus anciennes.

        L'ordre suit l'identifiant, qui commence par l'horodatage de création.
        Un dossier au nom non conforme, un lien symbolique ou un dossier sans
        `run.json` est ignoré. Une exécution dont le `run.json` est illisible,
        d'un schéma inconnu ou incohérent est listée comme non interprétable,
        sans empêcher l'affichage des autres. Lève `LectureResultatsImpossible`
        si le dossier des résultats existe mais ne peut pas être parcouru.
        """
        try:
            entrees = sorted(
                self.dossier_resultats.iterdir(),
                key=lambda entree: entree.name,
                reverse=True,
            )
        except FileNotFoundError:
            return ()
        except OSError as erreur:
            raise LectureResultatsImpossible(
                f"dossier des résultats illisible : {_message(erreur)}"
            ) from None
        executions: list[ExecutionListee] = []
        for entree in entrees:
            if not MOTIF_IDENTIFIANT.fullmatch(entree.name):
                continue
            try:
                lecture = self._lire(entree.name)
            except ResultatIntrouvable:
                continue
            except ValeurRefusee:
                # Nom ou lien sortant : ce n'est pas une exécution enregistrée.
                continue
            except ResultatNonInterpretable as refus:
                executions.append(_execution_non_interpretable(entree.name, str(refus)))
                continue
            if lecture is not None:
                executions.append(_resume(lecture[1]))
        return tuple(executions)

    def detail(self, identifiant: str) -> DetailExecutionVue:
        """Détail d'une exécution, transcriptions déjà écrites comprises.

        Lève `ValeurRefusee` pour un identifiant de chemin hostile,
        `ResultatIntrouvable` s'il n'y a pas d'exécution enregistrée sous ce
        nom, et `ResultatNonInterpretable` si son `run.json` n'est pas
        interprétable. Aucun fichier n'est modifié dans tous les cas.
        """
        lecture = self._lire(identifiant)
        if lecture is None:
            raise ResultatIntrouvable(f"exécution inconnue : {identifiant!r}")
        dossier, contenu = lecture
        execution = _resume(contenu)
        demande = _mapping(contenu.get("demande"))
        modele = _mapping(demande.get("modele"))
        moteur = _mapping(contenu.get("moteur"))
        mesure = _mapping(contenu.get("mesures"))
        effectifs = _mapping(contenu.get("effectifs"))
        partiel = contenu["etat"] != ETAT_TERMINEE
        return DetailExecutionVue(
            execution=execution,
            fin=_texte(contenu.get("fin")),
            erreur=_texte(contenu.get("erreur")),
            famille=_texte(demande.get("famille")),
            threads_demandes=_entier(demande.get("threads_demandes")),
            threads_appliques=_entier(effectifs.get("threads_appliques")),
            fenetre_fixe_s=_nombre(demande.get("fenetre_fixe_secondes")),
            reglages=_paires_reglages(demande.get("reglages")),
            reglages_effectifs=_paires_reglages(effectifs.get("reglages_effectifs")),
            modele=_paires(modele, CHAMPS_MODELE),
            moteur=_paires(moteur, CHAMPS_MOTEUR),
            versions_moteur=_paires_versions(moteur.get("versions")),
            machine=_paires(_mapping(contenu.get("machine")), CHAMPS_MACHINE),
            programme=_paires_programme(_mapping(contenu.get("programme"))),
            processus=_paires(
                _mapping(contenu.get("processus_moteur")), CHAMPS_PROCESSUS
            ),
            mesures=MesuresVue(
                duree_operation_s=_nombre(mesure.get("duree_operation_s")),
                duree_processus_s=_nombre(mesure.get("duree_processus_s")),
                duree_chargement_s=_nombre(mesure.get("duree_chargement_s")),
                pic_memoire_octets=_entier(mesure.get("pic_memoire_octets")),
                pic_memoire_partiel=_booleen(mesure.get("pic_memoire_partiel")),
            ),
            audios=tuple(
                _audio(dossier, plan, partiel=partiel) for plan in contenu["audios"]
            ),
            partiel=partiel,
        )

    # -- lecture -------------------------------------------------------------

    def _lire(self, identifiant: str) -> tuple[Path, Mapping[str, Any]] | None:
        """Lit et valide `run.json` ; `None` s'il n'existe pas.

        Lève `ValeurRefusee` pour une forme de chemin refusée,
        `ResultatIntrouvable` si le dossier n'est pas une exécution enregistrée
        (absent, lien symbolique ou nom non conforme), et
        `ResultatNonInterpretable` pour un contenu illisible ou incohérent.
        """
        if not isinstance(identifiant, str) or not identifiant:
            raise ValeurRefusee("identifiant de résultat attendu sous forme de texte")
        dossier = resoudre_resultat(identifiant, self._donnees)
        if not MOTIF_IDENTIFIANT.fullmatch(identifiant):
            raise ResultatIntrouvable(f"exécution inconnue : {identifiant!r}")
        entree = dossier.parent / identifiant
        if entree.is_symlink() or not entree.is_dir():
            raise ResultatIntrouvable(f"exécution inconnue : {identifiant!r}")
        try:
            # Le fichier lui-même est confiné : un `run.json` qui serait un lien
            # sortant n'est pas lu.
            chemin = resoudre_dans_racine(dossier, NOM_FICHIER_EXECUTION)
        except ValeurRefusee:
            raise ResultatNonInterpretable(
                "run.json hors du dossier de l'exécution"
            ) from None
        try:
            contenu = lire_json(chemin)
        except JsonInvalide:
            raise ResultatNonInterpretable("run.json illisible (JSON invalide)") from None
        except OSError:
            raise ResultatNonInterpretable("run.json inaccessible") from None
        if contenu is None:
            return None
        _valider_execution(contenu, identifiant)
        return dossier, contenu


# -- validation du suivi d'exécution -----------------------------------------


def _valider_execution(contenu: Any, identifiant: str) -> None:
    """Vérifie ce que la consultation interprète : schéma, état, audios.

    Seuls les champs réellement lus sont contrôlés. Un contenu refusé n'est
    jamais réécrit ; les messages ne recopient aucune valeur du fichier.
    """
    if not isinstance(contenu, Mapping):
        raise ResultatNonInterpretable("objet JSON attendu")
    schema = contenu.get("schema")
    if type(schema) is not int or schema != SCHEMA:
        raise ResultatNonInterpretable(
            f"schéma non pris en charge (schéma {SCHEMA} attendu)"
        )
    if contenu.get("identifiant") != identifiant:
        raise ResultatNonInterpretable("identifiant incohérent avec le dossier")
    etat = contenu.get("etat")
    if not isinstance(etat, str) or etat not in LIBELLES_ETATS_EXECUTION:
        raise ResultatNonInterpretable("état d'exécution inconnu")
    audios = contenu.get("audios")
    if not isinstance(audios, list):
        raise ResultatNonInterpretable("clé 'audios' absente ou invalide")
    for plan in audios:
        if not isinstance(plan, Mapping):
            raise ResultatNonInterpretable("plan d'audio invalide")
        ordre = plan.get("ordre")
        if type(ordre) is not int or ordre < 1:
            raise ResultatNonInterpretable("ordre d'audio invalide")
        if not isinstance(plan.get("nom"), str):
            raise ResultatNonInterpretable("nom d'audio invalide")
        dossier = plan.get("dossier")
        if not isinstance(dossier, str) or not dossier:
            raise ResultatNonInterpretable("dossier d'audio invalide")
        statut = plan.get("statut")
        if not isinstance(statut, str) or statut not in LIBELLES_STATUTS_AUDIO:
            raise ResultatNonInterpretable("statut d'audio inconnu")


# -- vues --------------------------------------------------------------------


def _execution_non_interpretable(identifiant: str, motif: str) -> ExecutionListee:
    """Ligne de liste pour un `run.json` refusé : aucun fait n'est inventé."""
    return ExecutionListee(
        identifiant=identifiant,
        etat=None,
        libelle_etat="non interprétable",
        cree_le=None,
        modele=None,
        moteur=None,
        audios_traites=None,
        audios_total=None,
        duree_operation_s=None,
        partiel=False,
        marques=None,
        exploitable=False,
        motif=motif,
    )


def _resume(contenu: Mapping[str, Any]) -> ExecutionListee:
    """Ligne de liste (ou en-tête du détail) d'un `run.json` déjà validé."""
    demande = _mapping(contenu.get("demande"))
    modele = _mapping(demande.get("modele"))
    moteur = _mapping(contenu.get("moteur"))
    mesure = _mapping(contenu.get("mesures"))
    plans = contenu["audios"]
    etat = contenu["etat"]
    return ExecutionListee(
        identifiant=contenu["identifiant"],
        etat=etat,
        libelle_etat=LIBELLES_ETATS_EXECUTION[etat],
        cree_le=_texte(contenu.get("cree_le")),
        modele=_texte(modele.get("identifiant")) or _texte(modele.get("id_resolu")),
        moteur=_texte(moteur.get("nom")) or _texte(moteur.get("identifiant")),
        audios_traites=sum(1 for plan in plans if plan["statut"] != STATUT_NON_TRAITE),
        audios_total=len(plans),
        duree_operation_s=_nombre(mesure.get("duree_operation_s")),
        partiel=etat != ETAT_TERMINEE,
        marques=_marques(contenu),
        exploitable=True,
        motif=None,
    )


def _audio(
    dossier_execution: Path, plan: Mapping[str, Any], *, partiel: bool
) -> AudioVue:
    """Audio d'une exécution : transcription relue, ou motif d'absence."""
    transcription, motif = _lire_transcription(dossier_execution, plan)
    if transcription is None and plan["statut"] == STATUT_NON_TRAITE:
        motif = MOTIF_NON_TRAITE
    # Le `result.json` fait foi pour son propre audio : `run.json` est réécrit
    # après lui, il peut donc être en retard d'un instant sur une exécution en
    # cours. Sans résultat, c'est le statut du suivi qui est affiché.
    statut = plan["statut"] if transcription is None else transcription.statut
    return AudioVue(
        ordre=plan["ordre"],
        nom=plan["nom"],
        dossier=plan["dossier"],
        statut=statut,
        libelle_statut=LIBELLES_STATUTS_AUDIO[statut],
        erreur=_texte(plan.get("erreur")),
        partiel=partiel and transcription is not None,
        motif_indisponible=motif,
        transcription=transcription,
    )


def _lire_transcription(
    dossier_execution: Path, plan: Mapping[str, Any]
) -> tuple[TranscriptionVue | None, str | None]:
    """Transcription d'un audio, ou motif d'indisponibilité fixe."""
    try:
        dossier_audio = resoudre_dans_racine(dossier_execution, plan["dossier"])
    except ValeurRefusee:
        return None, MOTIF_DOSSIER_REFUSE
    try:
        chemin = resoudre_dans_racine(dossier_audio, NOM_FICHIER_RESULTAT)
    except ValeurRefusee:
        return None, MOTIF_FICHIER_REFUSE
    try:
        contenu = lire_json(chemin)
    except (JsonInvalide, OSError):
        return None, MOTIF_RESULTAT_ILLISIBLE
    if contenu is None:
        return None, MOTIF_RESULTAT_ABSENT
    try:
        return _vue_transcription(contenu, dossier_execution.name, plan), None
    except ResultatNonInterpretable as refus:
        return None, f"Résultat non interprétable : {refus}"


def _vue_transcription(
    contenu: Any, execution: str, plan: Mapping[str, Any]
) -> TranscriptionVue:
    """Vue d'un `result.json`, confiné et identifié avec son plan d'audio.

    Refuse un schéma inconnu, un statut inconnu ou un résultat qui ne décrit pas
    cet audio de cette exécution : une transcription n'est jamais attribuée à un
    autre audio.
    """
    if not isinstance(contenu, Mapping):
        raise ResultatNonInterpretable("objet JSON attendu")
    schema = contenu.get("schema")
    if type(schema) is not int or schema != SCHEMA:
        raise ResultatNonInterpretable(
            f"schéma non pris en charge (schéma {SCHEMA} attendu)"
        )
    statut = contenu.get("statut")
    if not isinstance(statut, str) or statut not in LIBELLES_STATUTS_AUDIO:
        raise ResultatNonInterpretable("statut de résultat inconnu")
    if contenu.get("execution") != execution:
        raise ResultatNonInterpretable("exécution incohérente avec le dossier")
    ordre = contenu.get("ordre")
    if type(ordre) is not int or ordre != plan["ordre"]:
        raise ResultatNonInterpretable("ordre incohérent avec le suivi de l'exécution")
    if contenu.get("nom") != plan["nom"]:
        raise ResultatNonInterpretable("nom incohérent avec le suivi de l'exécution")
    if contenu.get("dossier") != plan["dossier"]:
        raise ResultatNonInterpretable("dossier incohérent avec le suivi de l'exécution")
    transcription = _mapping(contenu.get("transcription"))
    mesures = _mapping(contenu.get("mesures"))
    duree_transcription = _nombre(mesures.get("duree_transcription_s"))
    audio = _mapping(contenu.get("audio"))
    return TranscriptionVue(
        statut=statut,
        ecrit_le=_texte(contenu.get("ecrit_le")),
        texte=_texte_brut(transcription.get("texte")),
        segments=_segments(transcription.get("segments")),
        marques=_marques(contenu),
        audio=_paires(audio, CHAMPS_AUDIO),
        mesures=MesuresAudioVue(
            temps_decodage_s=_nombre(mesures.get("temps_decodage_s")),
            duree_transcription_s=duree_transcription,
            temps_cpu_s=_nombre(mesures.get("temps_cpu_s")),
            # RTF recalculé sur la durée décodée : jamais sur l'indicative, et
            # jamais sur une durée nulle ou absente.
            rtf=calculer_rtf(duree_transcription, _nombre(audio.get("duree_decodee_s"))),
            pic_memoire_octets=_entier(mesures.get("pic_memoire_octets")),
        ),
        reglages_effectifs=_paires_reglages(contenu.get("reglages_effectifs")),
        threads=_paires(
            _mapping(contenu.get("threads")),
            (("demandes", "Threads demandés"), ("appliques", "Threads appliqués")),
        ),
        langue_imposee=_texte(contenu.get("langue_imposee")),
        fenetre=_paires(
            _mapping(contenu.get("fenetre")),
            (
                ("duree_s", "Durée de fenêtre (s)"),
                ("decoupage", "Méthode de découpage"),
                ("nb_fenetres", "Nombre de fenêtres"),
            ),
        ),
        erreur=_texte(contenu.get("erreur")),
    )


def _segments(valeur: Any) -> tuple[SegmentVue, ...]:
    """Segments horodatés ; une forme inattendue est refusée.

    Le runner accepte des bornes non finies (NaN, infini). Elles ne sont ni un
    texte ni une mesure à masquer : la borne devient `None` (indisponible) et le
    texte du segment reste affiché. Une borne non numérique, un segment qui
    n'est pas un objet ou un texte absent restent refusés.
    """
    if valeur is None:
        return ()
    if not isinstance(valeur, list):
        raise ResultatNonInterpretable("segments invalides")
    segments: list[SegmentVue] = []
    for segment in valeur:
        if not isinstance(segment, Mapping):
            raise ResultatNonInterpretable("segment invalide")
        debut = segment.get("debut_s")
        fin = segment.get("fin_s")
        texte = _texte_brut(segment.get("texte"))
        if not _numerique(debut) or not _numerique(fin) or texte is None:
            raise ResultatNonInterpretable("segment invalide")
        segments.append(
            SegmentVue(debut_s=_position(debut), fin_s=_position(fin), texte=texte)
        )
    return tuple(segments)


def _marques(contenu: Mapping[str, Any]) -> tuple[str, ...]:
    """Marques explicitement consignées, reprises sans être déduites."""
    marques = []
    if contenu.get("factice") is True:
        marques.append("FACTICE")
    if contenu.get("synthetique") is True:
        marques.append("SYNTHÉTIQUE")
    if contenu.get("mesures_simulees") is True:
        marques.append("MESURES SIMULÉES")
    return tuple(marques)


def _paires(
    contenu: Mapping[str, Any], champs: Sequence[tuple[str, str]]
) -> tuple[Paire, ...]:
    """Paires libellé / valeur d'un sous-objet, valeurs non affichables retirées."""
    return tuple(
        (libelle, _scalaire(contenu.get(cle))) for cle, libelle in champs
    )


def _paires_programme(programme: Mapping[str, Any]) -> tuple[Paire, ...]:
    """Métadonnées du programme, version de FFmpeg comprise (objet imbriqué)."""
    paires = _paires(programme, CHAMPS_PROGRAMME)
    ffmpeg = _mapping(programme.get("ffmpeg"))
    return paires + (("FFmpeg", _texte(ffmpeg.get("version"))),)


def _paires_reglages(valeur: Any) -> tuple[Paire, ...]:
    """Réglages d'un objet JSON, triés par nom, sans perdre listes ni objets.

    Un réglage comme la température faster-whisper est une liste : il est
    affiché en JSON compact, échappé par Jinja comme le reste. Une valeur
    absente ou un nombre non fini au premier niveau reste « indisponible » ; un
    nombre non fini imbriqué devient `null` dans le texte JSON, jamais `NaN`.
    """
    contenu = _mapping(valeur)
    return tuple(
        (nom, _valeur_reglage(reglage)) for nom, reglage in sorted(contenu.items())
    )


def _paires_versions(valeur: Any) -> tuple[Paire, ...]:
    """Versions relues du moteur, triées par module."""
    contenu = _mapping(valeur)
    return tuple(
        (module, _texte(version)) for module, version in sorted(contenu.items())
    )


# -- conversions -------------------------------------------------------------


def _mapping(valeur: Any) -> Mapping[str, Any]:
    """Sous-objet JSON, vide s'il n'a pas la forme attendue."""
    return valeur if isinstance(valeur, Mapping) else {}


def _valeur_reglage(valeur: Any) -> Any:
    """Valeur de réglage affichable : scalaire, ou JSON compact d'une liste/objet."""
    if isinstance(valeur, (Mapping, list, tuple)):
        return json.dumps(
            _sans_non_finis(valeur),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    return _scalaire(valeur)


def _sans_non_finis(valeur: Any) -> Any:
    """Copie compatible JSON : un nombre non fini devient `null`, jamais `NaN`."""
    if valeur is None or isinstance(valeur, (bool, str)) or type(valeur) is int:
        return valeur
    if isinstance(valeur, float):
        return valeur if math.isfinite(valeur) else None
    if isinstance(valeur, Mapping):
        return {
            str(cle): _sans_non_finis(sous_valeur)
            for cle, sous_valeur in valeur.items()
        }
    if isinstance(valeur, (list, tuple)):
        return [_sans_non_finis(element) for element in valeur]
    return None


def _scalaire(valeur: Any) -> Any:
    """Valeur affichable sans objet imbriqué ; `None` si elle n'en est pas une."""
    if isinstance(valeur, (str, bool)) or type(valeur) is int:
        return valeur
    if isinstance(valeur, float):
        return valeur if math.isfinite(valeur) else None
    return None


def _texte(valeur: Any) -> str | None:
    """Texte non vide, ou `None` (métadonnée indisponible)."""
    return valeur if isinstance(valeur, str) and valeur.strip() else None


def _texte_brut(valeur: Any) -> str | None:
    """Texte tel quel, y compris vide ; `None` si ce n'est pas un texte."""
    return valeur if isinstance(valeur, str) else None


def _numerique(valeur: Any) -> bool:
    """Nombre au sens JSON (entier ou flottant, fini ou non), hors booléens."""
    return isinstance(valeur, (int, float)) and not isinstance(valeur, bool)


def _position(valeur: Any) -> float | None:
    """Horodatage en secondes, ou `None` si la valeur est non finie."""
    nombre = _nombre(valeur)
    return None if nombre is None else float(nombre)


def _nombre(valeur: Any) -> float | int | None:
    """Nombre fini, ou `None` : NaN, infini et booléens ne sont pas des mesures."""
    if isinstance(valeur, bool) or not isinstance(valeur, (int, float)):
        return None
    try:
        return valeur if math.isfinite(valeur) else None
    except OverflowError:
        return None


def _entier(valeur: Any) -> int | None:
    """Entier strict, ou `None`."""
    return valeur if type(valeur) is int else None


def _booleen(valeur: Any) -> bool | None:
    """Booléen strict, ou `None`."""
    return valeur if isinstance(valeur, bool) else None


def _message(erreur: BaseException) -> str:
    """Texte court d'une erreur, sans message vide."""
    texte = str(erreur).strip()
    return texte if texte else type(erreur).__name__
