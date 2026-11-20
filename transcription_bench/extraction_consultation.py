"""Consultation des extractions enregistrées : groupes, indicateurs, détail, comparaison.

Tâche 4.1, design D9. Ce module est **strictement en lecture** : il ne crée, ne
réécrit ni ne supprime aucun fichier, n'appelle aucun moteur et n'ouvre aucune
connexion réseau.

**Source de vérité** : les copies conservées dans
`data/extractions/<identifiant>/` (`run.json`, `grille.md`, `schema.json`,
`consignes.json`, puis par source `source.txt`, `result.json`, et seulement pour
une source publiée `extraction.json` et `sortie_brute.txt`). La grille et le
schéma sont relus depuis leurs copies, jamais depuis `grilles/` ; les résultats
de transcription d'origine ne servent qu'à indiquer s'ils existent encore.

**Publication** : une source n'est publiée que si son `result.json` existe et
correspond à son plan (identifiant, rang, nom, dossier, texte, provenance). Sans
ce marqueur, la source est « non traitée », même si `source.txt` existe ; son
texte copié et sa provenance restent lisibles, rien d'autre n'est lu.

**Groupes** : une entrée par source publiée. Le triplet (empreinte du texte
source, empreinte de la grille copiée, empreinte du schéma copié) définit le
groupe, identifié par `group_key`. Une entrée dont une copie est absente,
modifiée ou incohérente, ou dont la valeur n'est pas conforme au schéma copié,
n'entre dans aucun groupe : son `copy_issue` en nomme la raison. Des versions de
consignes différentes au sein d'un groupe sont signalées, jamais séparées.

**Tris** : `temps` (durée d'extraction), `ram` (pic mémoire), `cpu` (occupation
du moteur) et `recent` (défaut). Une valeur absente ou incohérente vient après
les valeurs valides ; les égalités sont départagées par date décroissante (date
inconnue en fin), puis identifiant décroissant, puis rang croissant.

**Factices** : une entrée portant `FACTICE` ou `MESURES SIMULÉES` (dans
`run.json` ou dans `result.json`, union conservatrice) est classée à part et
n'est jamais comparée à une entrée réelle. `SOURCE FACTICE` signale seulement un
texte issu d'une transcription factice, sans séparer l'entrée.

**Mesures** : une valeur absente, non numérique, booléenne, non finie ou
négative reste `None` ; aucune n'est remplacée par zéro. Les ratios viennent
d'`indicateurs_resultats` sur le matériel consigné de l'extraction.

**Sorties** : la conformité ne mesure que la forme ; aucun score ni classement
de qualité n'est produit.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from transcription_bench.consultation_resultats import (
    CHAMPS_MACHINE,
    CHAMPS_MODELE,
    CHAMPS_MOTEUR,
    CHAMPS_PROGRAMME,
    LIBELLES_ETATS_EXECUTION,
    LIBELLES_TRI,
    MARQUE_FACTICE,
    MARQUE_MESURES_SIMULEES,
    MARQUE_SYNTHETIQUE,
    MARQUES_MESURES_SIMULEES,
    MOTIF_EMPREINTE,
    TRI_CPU,
    TRI_RAM,
    TRI_RECENT,
    TRI_TEMPS,
    LectureResultatsImpossible,
    ResultatIntrouvable,
    ResultatNonInterpretable,
    analyser_selection,
    analyser_tri,
)
from transcription_bench.grilles import Field, Grid, interpret_grid_copy
from transcription_bench.indicateurs_resultats import (
    formater_date_courte,
    ratio_cpu,
    ratio_ram,
)
from transcription_bench.paths import (
    NOM_DOSSIER_EXTRACTIONS,
    ValeurRefusee,
    resoudre_dans_racine,
    resoudre_resultat,
)
from transcription_bench.resultats import (
    ETAT_TERMINEE,
    MOTIF_IDENTIFIANT,
    NOM_FICHIER_EXECUTION,
)
from transcription_bench.resultats_extraction import (
    FILE_EXTRACTION,
    FILE_GRID,
    FILE_INSTRUCTIONS,
    FILE_RAW_OUTPUT,
    FILE_SCHEMA,
    FILE_SOURCE,
    FILE_SOURCE_RESULT,
    EXTRACTION_FILE_TYPE,
    RUN_TYPE_EXTRACTION,
    SCHEMA_EXTRACTION,
    SOURCE_COMPLIANT,
    SOURCE_ERROR,
    SOURCE_NON_COMPLIANT,
    SOURCE_NOT_PROCESSED,
    SOURCE_PUBLISHED_STATES,
    SOURCE_RESULT_TYPE,
    SOURCE_STATES,
)
from transcription_bench.schema_grilles import validate_output
from transcription_bench.stockage import VERROU_STOCKAGE, JsonInvalide, lire_json

#: Nombre minimal et maximal de sélections d'une comparaison d'extractions.
MIN_SELECTIONS = 2
MAX_SELECTIONS = 6

#: Marque d'une extraction dont le texte source vient d'une transcription factice.
MARK_SOURCE_FACTICE = "SOURCE FACTICE"

#: Libellés affichés pour une valeur absente, vide ou sans autre information.
LABEL_NOT_MENTIONED = "non mentionné"
LABEL_EMPTY = "(vide)"
LABEL_NO_OTHER_INFO = "aucune"

#: Libellés des états de source, publiée ou non.
SOURCE_STATE_LABELS: dict[str, str] = {
    SOURCE_COMPLIANT: "conforme",
    SOURCE_NON_COMPLIANT: "non conforme",
    SOURCE_ERROR: "en erreur",
    SOURCE_NOT_PROCESSED: "non traitée",
}

#: Mesures d'exécution affichées en détail, avec leur libellé.
EXTRACTION_MEASURE_FIELDS: tuple[tuple[str, str], ...] = (
    ("duree_chargement_s", "Durée de chargement du modèle (s)"),
    ("duree_processus_s", "Durée du processus moteur (s)"),
    ("duree_operation_s", "Durée totale de l'opération (s)"),
    ("pic_memoire_octets", "Pic de mémoire du moteur (octets)"),
)
#: Identité du modèle consignée au chargement (`meta_moteur`), en plus des champs communs.
EXTRACTION_MODEL_FIELDS: tuple[tuple[str, str], ...] = CHAMPS_MODELE + (
    ("architecture", "Architecture GGUF"),
    ("sha256_gabarit_embarque", "SHA-256 du gabarit embarqué"),
)


@dataclass(frozen=True)
class RunSummary:
    """Ligne de la liste des extractions ; `usable` vaut `False` si `run.json` est refusé.

    Tâche 4.2 : `model`, `engine`, `sources_processed`, `duration_operation_s`,
    `marks` et `partial` complètent la ligne pour l'historique combiné
    (`results history`), comme `ExecutionListee` pour les transcriptions. Tous
    restent `None` (`marks` excepté, `()`) pour une ligne non utilisable : aucun
    fait n'est inventé.
    """

    run_id: str
    state: str | None
    state_label: str
    created_at: str | None
    grid_title: str | None
    sources_total: int | None
    usable: bool
    reason: str | None
    model: str | None
    engine: str | None
    sources_processed: int | None
    duration_operation_s: float | None
    marks: tuple[str, ...] | None
    partial: bool | None


@dataclass(frozen=True)
class Indicators:
    """Indicateurs bruts d'une source extraite, et leurs deux ratios.

    `ram_ratio` et `cpu_occupancy` valent `None` quand le ratio n'est pas
    interprétable (capacité absente, dénominateur nul, ratio supérieur à 100 %).
    Une mesure absente, booléenne, non finie ou négative est `None`, jamais zéro.
    """

    duration_extraction_s: float | None
    time_to_first_token_s: float | None
    generation_duration_s: float | None
    generation_speed_tps: float | None
    read_speed_estimate_tps: float | None
    tokens_in: int | None
    tokens_out: int | None
    cpu_time_s: float | None
    peak_memory_bytes: int | None
    ram_total_bytes: int | None
    ram_ratio: float | None
    cpu_occupancy: float | None


@dataclass(frozen=True)
class Entry:
    """Une source publiée d'une extraction, sélectionnable par `selection`.

    `selection` vaut `identifiant:rang`. `value` n'est renseignée que pour une
    valeur conforme au schéma copié ; sinon elle vaut `None`. `groupable` vaut
    `False` quand une copie empêche le regroupement, `copy_issue` en donne la
    raison.
    """

    selection: str
    run_id: str
    rank: int
    audio_name: str
    state: str
    state_label: str
    partial: bool
    source_state: str
    source_state_label: str
    reason: str | None
    compliant: bool
    created_at: str | None
    created_short: str
    model: str | None
    engine: str | None
    family: str | None
    transcription_run_id: str | None
    transcription_order: int | None
    transcription_model: str | None
    audio_sha256: str | None
    text_sha256: str | None
    marks: tuple[str, ...]
    simulated: bool
    consignes_version: int | None
    format_version: int | None
    indicators: Indicators
    value: Mapping[str, Any] | None = field(repr=False)
    other_info: tuple[tuple[str, str], ...]
    groupable: bool
    copy_issue: str | None


@dataclass(frozen=True)
class Group:
    """Entrées partageant le même triplet d'empreintes : comparables entre elles.

    `entries` garde les entrées réelles d'abord, puis les factices, chaque partie
    classée par le critère demandé. `fields` est l'interprétation de la grille
    copiée. `consignes_diverge` signale des versions de consignes différentes.
    """

    key: str
    text_sha256: str
    grid_sha256: str
    schema_sha256: str
    grid_name: str
    grid_title: str | None
    fields: tuple[Field, ...] = field(repr=False)
    audio_names: tuple[str, ...]
    transcription_models: tuple[str, ...]
    entries: tuple[Entry, ...]
    consignes_versions: tuple[int, ...]
    consignes_diverge: bool

    @property
    def real_entries(self) -> tuple[Entry, ...]:
        """Entrées à mesures observées."""
        return tuple(entry for entry in self.entries if not entry.simulated)

    @property
    def simulated_entries(self) -> tuple[Entry, ...]:
        """Entrées à mesures simulées, jamais comparées aux réelles."""
        return tuple(entry for entry in self.entries if entry.simulated)


@dataclass(frozen=True)
class FillRow:
    """Ligne de la grille remplie : libellé, profondeur, valeur affichable.

    `absent` vaut `True` pour « non mentionné » (valeur `null`), distinct de la
    chaîne vide affichée « (vide) ».
    """

    label: str
    depth: int
    display: str
    absent: bool


@dataclass(frozen=True)
class SourceDetail:
    """Détail d'une source : état, provenance, grille remplie, texte copié.

    `rows` vaut `None` sauf pour une source conforme dont la valeur est valide
    et dont la grille copiée est utilisable ; la sortie brute n'est lue que pour
    une source publiée. `origin_present` indique si le résultat de transcription
    d'origine existe encore (lecture seule, sans lien garanti).
    """

    rank: int
    name: str
    state: str
    state_label: str
    reason: str | None
    origin: Mapping[str, Any] = field(repr=False)
    entry: Entry | None
    rows: tuple[FillRow, ...] | None
    source_text: str | None
    source_copy_ok: bool
    raw_output: str | None
    origin_present: bool
    # Résultat publié brut (result.json) : mesures, comptes natifs, observations.
    raw_result: Mapping[str, Any] | None = field(repr=False)


@dataclass(frozen=True)
class RunDetail:
    """Détail d'une extraction : métadonnées, grille copiée, message système, sources."""

    run_id: str
    state: str
    state_label: str
    created_at: str | None
    finished_at: str | None
    error: str | None
    partial: bool
    grid_name: str
    grid_title: str | None
    grid_copy: str | None
    grid_copy_ok: bool
    system_message: str | None
    consignes_version: int | None
    format_version: int | None
    model: tuple[tuple[str, Any], ...]
    engine: tuple[tuple[str, Any], ...]
    engine_versions: Mapping[str, Any]
    program: tuple[tuple[str, Any], ...]
    machine: tuple[tuple[str, Any], ...]
    measures: tuple[tuple[str, Any], ...]
    settings: tuple[tuple[str, Any], ...]
    threads_requested: int | None
    threads_applied: int | None
    weight_loading_mode: str | None
    effective_settings: Mapping[str, Any]
    marks: tuple[str, ...]
    simulated: bool
    sources: tuple[SourceDetail, ...]
    # Métadonnées complètes de run.json (observations, provenance, sources), sérialisables.
    raw_metadata: Mapping[str, Any] = field(repr=False)


@dataclass(frozen=True)
class CaseRow:
    """Une case de la grille, une valeur par extraction comparée, dans l'ordre reçu.

    `values` vaut `None` pour une extraction sans valeur valide : sa colonne
    renvoie à sa sortie brute, sans valeur inventée.
    """

    label: str
    values: tuple[str | None, ...]
    differs: bool


@dataclass(frozen=True)
class Comparison:
    """Comparaison de 2 à 6 extractions d'un même groupe, dans l'ordre reçu.

    `source_text` est le texte source copié, commun à toutes les entrées du
    groupe (même empreinte de texte) : relu une seule fois depuis la copie
    d'une des sélections comparées, jamais depuis le résultat de transcription
    d'origine. `None` si cette copie n'a pas pu être relue.
    """

    key: str
    entries: tuple[Entry, ...]
    consignes_versions: tuple[int, ...]
    consignes_diverge: bool
    simulated: bool
    cases: tuple[CaseRow, ...]
    other_info: tuple[str | None, ...]
    source_text: str | None


@dataclass(frozen=True)
class _SourceRead:
    """Source relue depuis son dossier. `result` n'est renseigné que si publiée."""

    rank: int
    name: str
    state: str
    reason: str | None
    origin: Mapping[str, Any]
    text: str | None
    text_ok: bool
    result: Mapping[str, Any] | None
    value: Mapping[str, Any] | None
    raw_output: str | None


@dataclass(frozen=True)
class _RunRead:
    """Extraction relue : `run.json`, copies de la grille, du schéma et des consignes."""

    run_id: str
    contenu: Mapping[str, Any]
    grid_name: str
    grid_title: str | None
    grid_copy: str | None
    grid: Grid | None
    grid_sha256: str | None
    grid_usable: bool
    schema: Mapping[str, Any] | None
    schema_sha256: str | None
    consignes: Mapping[str, Any]
    sources: tuple[_SourceRead, ...]


class ExtractionConsultation:
    """Lectures des extractions d'un dossier de données, sans aucune écriture.

    `donnees` est la racine `data/` ; les extractions sont sous
    `donnees/extractions`. Une extraction illisible n'empêche jamais la lecture
    des autres. Le détail et la comparaison lèvent `ValeurRefusee`,
    `ResultatIntrouvable` ou `ResultatNonInterpretable`, comme la consultation
    des transcriptions.
    """

    def __init__(self, donnees: Path | str) -> None:
        self._donnees = Path(donnees)

    @property
    def extractions_dir(self) -> Path:
        """Dossier des extractions attendu, qu'il existe ou non."""
        return self._donnees / NOM_DOSSIER_EXTRACTIONS

    def list_runs(self) -> tuple[RunSummary, ...]:
        """Extractions enregistrées, des plus récentes aux plus anciennes.

        Un dossier sans `run.json` ou au nom non conforme est ignoré ; un
        `run.json` refusé est listé comme non utilisable, avec son motif.
        """
        summaries: list[RunSummary] = []
        for run_id in self._run_ids():
            try:
                contenu = self._read_run_json(run_id)
            except ResultatIntrouvable:
                continue
            except ResultatNonInterpretable as refus:
                summaries.append(_refused_run_summary(run_id, str(refus)))
                continue
            summaries.append(_run_summary(run_id, contenu))
        return tuple(summaries)

    def groups(self, tri: str = TRI_RECENT) -> tuple[Group, ...]:
        """Groupes comparables, les plus récents d'abord.

        `tri` classe les entrées à l'intérieur de chaque groupe ; il ne change
        pas l'ordre des groupes, qui suit leur extraction la plus récente.
        Lève `ValeurRefusee` pour un critère inconnu.
        """
        groupes, _index = self._collect_groups(analyser_tri(tri, defaut=TRI_RECENT))
        return groupes

    def detail(self, run_id: str) -> RunDetail:
        """Détail d'une extraction : grille copiée, sources, indicateurs.

        Lève `ValeurRefusee` pour un identifiant hostile, `ResultatIntrouvable`
        si aucune extraction n'existe sous ce nom, et `ResultatNonInterpretable`
        si son `run.json` n'est pas interprétable.
        """
        run = self._read_run(run_id)
        contenu = run.contenu
        demande = _mapping(contenu.get("demande"))
        modele = _mapping(contenu.get("modele"))
        mesures = _mapping(contenu.get("mesures"))
        effectifs = _mapping(contenu.get("effectifs"))
        marques = _marks(contenu, None)
        return RunDetail(
            run_id=run.run_id,
            state=contenu["etat"],
            state_label=LIBELLES_ETATS_EXECUTION[contenu["etat"]],
            created_at=_text(contenu.get("cree_le")),
            finished_at=_text(contenu.get("fin")),
            error=_text(contenu.get("erreur")),
            partial=contenu["etat"] != ETAT_TERMINEE,
            grid_name=run.grid_name,
            grid_title=run.grid_title,
            grid_copy=run.grid_copy,
            grid_copy_ok=run.grid_sha256 is not None,
            system_message=_text(run.consignes.get("message_systeme")),
            consignes_version=_int_or_none(run.consignes.get("version_consignes")),
            format_version=_int_or_none(run.consignes.get("version_format")),
            model=_pairs(modele, EXTRACTION_MODEL_FIELDS),
            engine=_pairs(_mapping(contenu.get("moteur")), CHAMPS_MOTEUR),
            engine_versions=dict(_mapping(_mapping(contenu.get("moteur")).get("versions"))),
            program=_pairs(_mapping(contenu.get("programme")), CHAMPS_PROGRAMME),
            machine=_pairs(_mapping(contenu.get("machine")), CHAMPS_MACHINE),
            measures=_pairs(mesures, EXTRACTION_MEASURE_FIELDS),
            settings=tuple(sorted(_mapping(demande.get("reglages")).items())),
            threads_requested=_int_or_none(demande.get("threads_demandes")),
            threads_applied=_int_or_none(effectifs.get("threads_appliques")),
            weight_loading_mode=_text(effectifs.get("mode_chargement_poids")),
            effective_settings=dict(_mapping(effectifs.get("reglages_effectifs"))),
            marks=marques,
            simulated=_is_simulated(marques),
            sources=tuple(self._source_detail(run, source) for source in run.sources),
            raw_metadata=dict(contenu),
        )

    def compare(self, key: str, selections: Sequence[str]) -> Comparison:
        """Comparaison de 2 à 6 extractions d'un même groupe, dans l'ordre reçu.

        `key` est la clé de groupe (`group_key`) et `selections` des sélections
        `identifiant:rang`. Au-delà de six sélections reçues, la demande est
        refusée avant toute lecture ; les doublons sont ensuite retirés.
        Lève `ValeurRefusee` pour une clé ou une sélection mal formée, une
        sélection hors du groupe, ou un mélange d'extractions factices et
        réelles ; `ResultatIntrouvable` pour une clé ou une extraction inconnue.
        """
        if not isinstance(key, str) or not MOTIF_EMPREINTE.fullmatch(key):
            raise ValeurRefusee("clé de groupe invalide : comparaison refusée")
        if len(selections) > MAX_SELECTIONS:
            raise ValeurRefusee(
                f"sélections refusées : {MAX_SELECTIONS} au maximum par comparaison"
            )
        choix: list[tuple[str, int]] = []
        for texte in selections:
            selection = analyser_selection(texte)
            if selection not in choix:
                choix.append(selection)
        if not MIN_SELECTIONS <= len(choix) <= MAX_SELECTIONS:
            raise ValeurRefusee(
                f"entre {MIN_SELECTIONS} et {MAX_SELECTIONS} extractions différentes "
                "sont nécessaires"
            )
        groupes, index = self._collect_groups(TRI_RECENT)
        groupe = next((candidat for candidat in groupes if candidat.key == key), None)
        if groupe is None:
            raise ResultatIntrouvable(f"groupe d'extractions inconnu : {key!r}")
        par_selection = {entry.selection: entry for entry in groupe.entries}
        entrees: list[Entry] = []
        for identifiant, rang in choix:
            selection = f"{identifiant}:{rang}"
            entry = par_selection.get(selection)
            if entry is None:
                if selection in index:
                    raise ValeurRefusee(
                        "sélection hors du groupe demandé : extractions non comparables"
                    )
                raise ResultatIntrouvable(
                    f"extraction inconnue ou non comparable : {selection!r}"
                )
            entrees.append(entry)
        if len({entry.simulated for entry in entrees}) > 1:
            raise ValeurRefusee(
                "extractions factices et réelles mêlées : comparaison refusée"
            )
        entrees_t = tuple(entrees)
        return _comparison(groupe, entrees_t, self._comparison_source_text(entrees_t[0]))

    def _comparison_source_text(self, entry: Entry) -> str | None:
        """Texte source copié, relu une seule fois pour tout le groupe comparé.

        Toutes les entrées d'un groupe partagent la même empreinte de texte
        (définition du groupe) : une seule relecture suffit, depuis la copie de
        l'extraction `entry`, jamais depuis le résultat de transcription
        d'origine. `None` si cette copie n'est plus lisible ou cohérente.
        """
        try:
            run = self._read_run(entry.run_id)
        except (ResultatIntrouvable, ResultatNonInterpretable, ValeurRefusee):
            return None
        source = next((candidate for candidate in run.sources if candidate.rank == entry.rank), None)
        if (
            source is None
            or not source.text_ok
            or source.text is None
            or _sha256(source.text.encode("utf-8")) != entry.text_sha256
        ):
            return None
        return source.text

    # -- regroupement ----------------------------------------------------------

    def _collect_groups(self, tri: str) -> tuple[tuple[Group, ...], dict[str, str]]:
        """Groupes et index `sélection -> clé` de toutes les extractions lisibles."""
        buckets: dict[str, list[tuple[Entry, _RunRead]]] = {}
        for run_id in self._run_ids():
            try:
                run = self._read_run(run_id)
            except (ResultatIntrouvable, ResultatNonInterpretable, ValeurRefusee):
                continue
            if run.grid is None or run.grid_sha256 is None or run.schema_sha256 is None:
                continue
            for source in run.sources:
                entry = self._entry_of(run, source)
                if entry is None or not entry.groupable or entry.text_sha256 is None:
                    continue
                key = group_key(entry.text_sha256, run.grid_sha256, run.schema_sha256)
                buckets.setdefault(key, []).append((entry, run))
        groupes: list[Group] = []
        index: dict[str, str] = {}
        for key, paires in buckets.items():
            run = paires[0][1]
            if run.grid is None or run.grid_sha256 is None or run.schema_sha256 is None:
                continue
            classees = sort_entries([entry for entry, _ in paires], tri)
            entrees = tuple(sorted(classees, key=lambda entry: entry.simulated))
            versions = tuple(
                sorted(
                    {
                        entry.consignes_version
                        for entry in entrees
                        if entry.consignes_version is not None
                    }
                )
            )
            groupes.append(
                Group(
                    key=key,
                    text_sha256=entrees[0].text_sha256 or "",
                    grid_sha256=run.grid_sha256,
                    schema_sha256=run.schema_sha256,
                    grid_name=run.grid_name,
                    grid_title=run.grid_title,
                    fields=run.grid.fields,
                    audio_names=tuple(sorted({entry.audio_name for entry in entrees})),
                    transcription_models=tuple(
                        sorted(
                            {
                                entry.transcription_model
                                for entry in entrees
                                if entry.transcription_model is not None
                            }
                        )
                    ),
                    entries=entrees,
                    consignes_versions=versions,
                    consignes_diverge=len(versions) > 1,
                )
            )
            for entry in entrees:
                index[entry.selection] = key
        groupes.sort(key=_recency_key, reverse=True)
        return tuple(groupes), index

    # -- lecture ---------------------------------------------------------------

    def _run_ids(self) -> tuple[str, ...]:
        """Identifiants des dossiers d'extraction conformes, plus récents d'abord."""
        try:
            entrees = sorted(
                self.extractions_dir.iterdir(), key=lambda entree: entree.name, reverse=True
            )
        except FileNotFoundError:
            return ()
        except OSError as erreur:
            raise LectureResultatsImpossible(
                f"dossier des extractions illisible : {_message(erreur)}"
            ) from None
        return tuple(
            entree.name
            for entree in entrees
            if MOTIF_IDENTIFIANT.fullmatch(entree.name)
            and not entree.is_symlink()
            and entree.is_dir()
        )

    def _run_folder(self, run_id: str) -> Path:
        """Dossier confiné d'une extraction ; lève `ValeurRefusee` ou `ResultatIntrouvable`."""
        if not isinstance(run_id, str) or not MOTIF_IDENTIFIANT.fullmatch(run_id):
            raise ValeurRefusee("identifiant d'extraction refusé : forme attendue")
        dossier = resoudre_dans_racine(self.extractions_dir, run_id)
        if (self.extractions_dir / run_id).is_symlink() or not dossier.is_dir():
            raise ResultatIntrouvable(f"extraction inconnue : {run_id!r}")
        return dossier

    def _read_run_json(self, run_id: str) -> Mapping[str, Any]:
        """`run.json` validé ; `ResultatIntrouvable` si le dossier n'en a pas."""
        dossier = self._run_folder(run_id)
        try:
            chemin = resoudre_dans_racine(dossier, NOM_FICHIER_EXECUTION)
        except ValeurRefusee:
            raise ResultatNonInterpretable(
                "run.json hors du dossier de l'extraction"
            ) from None
        try:
            contenu = lire_json(chemin)
        except JsonInvalide:
            raise ResultatNonInterpretable("run.json illisible (JSON invalide)") from None
        except OSError:
            raise ResultatNonInterpretable("run.json inaccessible") from None
        if contenu is None:
            raise ResultatIntrouvable(f"extraction sans run.json : {run_id!r}")
        _validate_run(contenu, run_id)
        return contenu

    def _read_run(self, run_id: str) -> _RunRead:
        """Extraction relue entièrement depuis ses copies conservées."""
        contenu = self._read_run_json(run_id)
        dossier = self._run_folder(run_id)
        grille = _mapping(contenu.get("grille"))
        octets_grille = _bounded_bytes(dossier, FILE_GRID)
        grille_objet = (
            None if octets_grille is None else interpret_grid_copy(grille["nom"], octets_grille)
        )
        empreinte_grille = _sha256(octets_grille)
        grille_coherente = empreinte_grille == grille["sha256"]
        octets_schema = _bounded_bytes(dossier, FILE_SCHEMA)
        schema = _json_object_from_bytes(octets_schema)
        sources = tuple(
            self._read_source(run_id, dossier, plan)
            for plan in sorted(contenu["sources"], key=lambda plan: plan["rang"])
        )
        return _RunRead(
            run_id=run_id,
            contenu=contenu,
            grid_name=grille["nom"],
            grid_title=(
                grille_objet.title
                if grille_objet is not None and grille_objet.title is not None
                else _text(grille.get("titre"))
            ),
            grid_copy=_decode_utf8(octets_grille),
            grid=grille_objet,
            grid_sha256=empreinte_grille if grille_coherente else None,
            grid_usable=(
                grille_coherente and grille_objet is not None and grille_objet.valid
            ),
            schema=schema,
            schema_sha256=_sha256(octets_schema) if schema is not None else None,
            consignes=_json_object(dossier, FILE_INSTRUCTIONS),
            sources=sources,
        )

    def _read_source(self, run_id: str, dossier: Path, plan: Mapping[str, Any]) -> _SourceRead:
        """Source relue : texte copié et provenance dans tous les cas, résultat si publié."""
        rang = plan["rang"]
        nom = plan["nom"]
        origine = _mapping(plan.get("source"))
        try:
            dossier_source = resoudre_dans_racine(dossier, plan["dossier"])
        except ValeurRefusee:
            return _unpublished_source(
                rang, nom, origine, "dossier de source refusé (hors de l'extraction)"
            )
        octets_texte = _bounded_bytes(dossier_source, FILE_SOURCE)
        texte_ok = octets_texte is not None and _mapping(plan.get("texte")).get(
            "empreinte_sha256"
        ) == _sha256(octets_texte)
        texte = _decode_utf8(octets_texte)
        try:
            resultat = lire_json(resoudre_dans_racine(dossier_source, FILE_SOURCE_RESULT))
        except (ValeurRefusee, JsonInvalide, OSError):
            return _unpublished_source(
                rang, nom, origine, "résultat de source illisible", texte, texte_ok
            )
        if resultat is None:
            # Marqueur absent : la source est non traitée, même si le texte est copié.
            return _unpublished_source(rang, nom, origine, None, texte, texte_ok)
        if not _source_result_valid(resultat, run_id, plan):
            return _unpublished_source(
                rang, nom, origine, "résultat de source non interprétable", texte, texte_ok
            )
        valeur: Mapping[str, Any] | None = None
        if resultat["etat"] == SOURCE_COMPLIANT:
            extraction = _json_object(dossier_source, FILE_EXTRACTION)
            if (
                type(extraction.get("schema")) is int
                and extraction["schema"] == SCHEMA_EXTRACTION
                and extraction.get("type") == EXTRACTION_FILE_TYPE
                and type(extraction.get("rang")) is int
                and extraction["rang"] == rang
                and isinstance(extraction.get("valeur"), Mapping)
            ):
                valeur = extraction["valeur"]
        sortie = None
        if resultat.get("sortie_brute") == FILE_RAW_OUTPUT:
            sortie = _decode_utf8(_bounded_bytes(dossier_source, FILE_RAW_OUTPUT))
        return _SourceRead(
            rank=rang,
            name=nom,
            state=resultat["etat"],
            reason=_text(resultat.get("motif")),
            origin=origine,
            text=texte,
            text_ok=texte_ok,
            result=resultat,
            value=valeur,
            raw_output=sortie,
        )

    def _entry_of(self, run: _RunRead, source: _SourceRead) -> Entry | None:
        """Entrée d'une source publiée, avec sa raison de regroupement éventuelle."""
        resultat = source.result
        if resultat is None:
            return None
        contenu = run.contenu
        audio = _mapping(source.origin.get("audio"))
        mesures = _mapping(resultat.get("mesures"))
        machine = _mapping(contenu.get("machine"))
        modele_run = _mapping(contenu.get("modele"))
        marques = _marks(contenu, resultat)
        version_consignes = _int_or_none(run.consignes.get("version_consignes"))
        compliant = source.state == SOURCE_COMPLIANT
        valeur_valide = (
            compliant
            and source.value is not None
            and run.schema is not None
            and _value_conforms(source.value, run.schema)
        )
        raison = None
        if not source.text_ok:
            raison = "copie du texte source absente ou modifiée"
        elif not run.grid_usable:
            raison = "copie de la grille absente, modifiée ou non interprétable"
        elif run.schema is None or run.schema_sha256 is None:
            raison = "copie du schéma absente ou illisible"
        elif version_consignes is None:
            raison = "consignes copiées illisibles"
        elif compliant and not valeur_valide:
            raison = "valeur extraite absente ou incohérente avec le schéma copié"
        etat_run = contenu["etat"]
        return Entry(
            selection=f"{run.run_id}:{source.rank}",
            run_id=run.run_id,
            rank=source.rank,
            audio_name=_text(audio.get("nom")) or source.name,
            state=etat_run,
            state_label=LIBELLES_ETATS_EXECUTION[etat_run],
            partial=etat_run != ETAT_TERMINEE,
            source_state=source.state,
            source_state_label=SOURCE_STATE_LABELS[source.state],
            reason=source.reason,
            compliant=compliant,
            created_at=_text(contenu.get("cree_le")),
            created_short=formater_date_courte(contenu.get("cree_le")),
            model=_text(modele_run.get("identifiant")) or _text(modele_run.get("id_resolu")),
            engine=_text(_mapping(contenu.get("moteur")).get("nom")),
            family=_text(modele_run.get("famille")),
            transcription_run_id=_text(source.origin.get("execution")),
            transcription_order=_int_or_none(source.origin.get("ordre")),
            transcription_model=_text(source.origin.get("modele")),
            audio_sha256=_sha256_or_none(audio.get("empreinte_sha256")),
            text_sha256=_sha256_or_none(_mapping(resultat.get("texte")).get("empreinte_sha256")),
            marks=marques,
            simulated=_is_simulated(marques),
            consignes_version=version_consignes,
            format_version=_int_or_none(run.consignes.get("version_format")),
            indicators=_indicators(
                mesures,
                _count(machine.get("ram_totale_octets")),
                _count(machine.get("coeurs_logiques")),
            ),
            value=source.value if valeur_valide else None,
            other_info=_other_information(source.value) if valeur_valide else (),
            groupable=raison is None,
            copy_issue=raison,
        )

    def _source_detail(self, run: _RunRead, source: _SourceRead) -> SourceDetail:
        """Détail d'une source ; la grille n'est remplie que si elle est fiable."""
        entry = self._entry_of(run, source)
        rows = None
        if (
            entry is not None
            and entry.value is not None
            and run.grid is not None
            and run.grid_usable
        ):
            rows = _fill_rows(run.grid.fields, entry.value)
        return SourceDetail(
            rank=source.rank,
            name=source.name,
            state=source.state,
            state_label=SOURCE_STATE_LABELS[source.state],
            reason=source.reason,
            origin=source.origin,
            entry=entry,
            rows=rows,
            source_text=source.text,
            source_copy_ok=source.text_ok,
            raw_output=source.raw_output,
            origin_present=_origin_present(
                self._donnees, _text(source.origin.get("execution"))
            ),
            raw_result=None if source.result is None else dict(source.result),
        )


# -- fonctions publiques ------------------------------------------------------


def group_key(text_sha256: str, grid_sha256: str, schema_sha256: str) -> str:
    """Clé d'un groupe : SHA-256 du triplet (texte, grille, schéma), en hexadécimal.

    Deux extractions ne sont comparables que si les trois empreintes sont
    identiques. La clé ne dépend d'aucun chemin ni d'aucune date.
    """
    contenu = "\n".join((text_sha256, grid_sha256, schema_sha256))
    return hashlib.sha256(contenu.encode("ascii")).hexdigest()


def sort_entries(entries: Sequence[Entry], tri: str = TRI_RECENT) -> tuple[Entry, ...]:
    """Entrées classées par `tri`, valeurs absentes en dernier.

    Départage : date d'extraction décroissante (inconnue en fin), puis
    identifiant d'extraction décroissant, puis rang croissant. `recent` classe
    par date seule. Lève `ValeurRefusee` pour un critère inconnu.
    """
    if tri not in LIBELLES_TRI:
        raise ValeurRefusee(
            "tri refusé : critère inconnu (temps, ram, cpu ou recent attendu)"
        )
    ordonnees = sorted(entries, key=lambda entry: entry.rank)
    ordonnees.sort(key=lambda entry: entry.run_id, reverse=True)
    ordonnees.sort(key=lambda entry: _date_key(entry.created_at), reverse=True)
    if tri != TRI_RECENT:
        ordonnees.sort(key=lambda entry: _measure_key(entry, tri))
    return tuple(ordonnees)


# -- comparaison, grille remplie, indicateurs ---------------------------------


def _comparison(
    groupe: Group, entrees: tuple[Entry, ...], source_text: str | None
) -> Comparison:
    """Table de comparaison : une ligne par case de la grille, une colonne par entrée."""
    cases: list[CaseRow] = []
    for champ in groupe.fields:
        valeurs: tuple[str | None, ...] = tuple(
            None if entry.value is None else _compact(champ, entry.value.get(champ.key))
            for entry in entrees
        )
        cases.append(CaseRow(label=champ.label, values=valeurs, differs=len(set(valeurs)) > 1))
    autres = tuple(
        None
        if entry.value is None
        else " ; ".join(f"{intitule} : {valeur}" for intitule, valeur in entry.other_info)
        or LABEL_NO_OTHER_INFO
        for entry in entrees
    )
    versions = tuple(
        sorted({entry.consignes_version for entry in entrees if entry.consignes_version is not None})
    )
    return Comparison(
        key=groupe.key,
        entries=entrees,
        consignes_versions=versions,
        consignes_diverge=len(versions) > 1,
        simulated=any(entry.simulated for entry in entrees),
        cases=tuple(cases),
        other_info=autres,
        source_text=source_text,
    )


def _compact(champ: Field, valeur: Any) -> str:
    """Valeur d'une case sur une seule ligne, pour la table de comparaison."""
    if champ.is_list:
        if not isinstance(valeur, list):
            return LABEL_NOT_MENTIONED
        if not valeur:
            return LABEL_EMPTY
        if champ.composed:
            return " | ".join(_compact_object(champ.subfields, element) for element in valeur)
        return " ; ".join(_display(element)[0] for element in valeur)
    if champ.composed:
        if not isinstance(valeur, Mapping):
            return LABEL_NOT_MENTIONED
        return _compact_object(champ.subfields, valeur)
    return _display(valeur)[0]


def _compact_object(sous_cases: Sequence[Field], objet: Any) -> str:
    """Sous-cases d'un objet sur une ligne : « libellé : valeur » séparés par « ; »."""
    contenu = objet if isinstance(objet, Mapping) else {}
    return " ; ".join(
        f"{sous_case.label} : {_compact(sous_case, contenu.get(sous_case.key))}"
        for sous_case in sous_cases
    )


def _fill_rows(champs: Sequence[Field], valeurs: Any, profondeur: int = 0) -> tuple[FillRow, ...]:
    """Lignes de la grille remplie, dans l'ordre de la grille."""
    contenu = valeurs if isinstance(valeurs, Mapping) else {}
    lignes: list[FillRow] = []
    for champ in champs:
        lignes.extend(_field_rows(champ, contenu.get(champ.key), profondeur))
    return tuple(lignes)


def _field_rows(champ: Field, valeur: Any, profondeur: int) -> tuple[FillRow, ...]:
    """Lignes d'une case : texte, liste, composée ou liste composée."""
    if champ.is_list:
        if not isinstance(valeur, list):
            return (FillRow(champ.label, profondeur, LABEL_NOT_MENTIONED, True),)
        if not valeur:
            return (FillRow(champ.label, profondeur, LABEL_EMPTY, False),)
        lignes: list[FillRow] = []
        for numero, element in enumerate(valeur, 1):
            titre = f"{champ.label} ({numero})"
            if champ.composed:
                lignes.append(FillRow(titre, profondeur, "", False))
                lignes.extend(_fill_rows(champ.subfields, element, profondeur + 1))
            else:
                texte, absent = _display(element)
                lignes.append(FillRow(titre, profondeur, texte, absent))
        return tuple(lignes)
    if champ.composed:
        if not isinstance(valeur, Mapping):
            return (FillRow(champ.label, profondeur, LABEL_NOT_MENTIONED, True),)
        return (FillRow(champ.label, profondeur, "", False),) + _fill_rows(
            champ.subfields, valeur, profondeur + 1
        )
    texte, absent = _display(valeur)
    return (FillRow(champ.label, profondeur, texte, absent),)


def _display(valeur: Any) -> tuple[str, bool]:
    """Texte affichable d'une valeur de case, et indicateur « non mentionné »."""
    if valeur is None:
        return LABEL_NOT_MENTIONED, True
    if valeur == "":
        return LABEL_EMPTY, False
    return str(valeur), False


def _other_information(valeur: Mapping[str, Any] | None) -> tuple[tuple[str, str], ...]:
    """Paires « intitulé, valeur » de la section hors grille, ou `()`."""
    if valeur is None:
        return ()
    entrees = valeur.get("autres_informations")
    if not isinstance(entrees, list):
        return ()
    return tuple(
        (entree["intitule"], str(entree.get("valeur", "")))
        for entree in entrees
        if isinstance(entree, Mapping) and isinstance(entree.get("intitule"), str)
    )


def _indicators(mesures: Mapping[str, Any], ram_totale: int | None, coeurs: int | None) -> Indicators:
    """Indicateurs bruts d'une source, et ratios sur le matériel consigné."""
    duree = _number(mesures.get("duree_extraction_s"))
    pic = _count(mesures.get("pic_memoire_octets"))
    cpu = _number(mesures.get("temps_cpu_s"))
    return Indicators(
        duration_extraction_s=duree,
        time_to_first_token_s=_number(mesures.get("delai_premier_token_s")),
        generation_duration_s=_number(mesures.get("duree_generation_s")),
        generation_speed_tps=_number(mesures.get("vitesse_generation_tps")),
        read_speed_estimate_tps=_number(mesures.get("vitesse_lecture_estimee_tps")),
        tokens_in=_count(mesures.get("tokens_entree")),
        tokens_out=_count(mesures.get("tokens_sortie")),
        cpu_time_s=cpu,
        peak_memory_bytes=pic,
        ram_total_bytes=ram_totale if ram_totale else None,
        ram_ratio=ratio_ram(pic, ram_totale),
        cpu_occupancy=ratio_cpu(cpu, duree, coeurs),
    )


def _measure_key(entry: Entry, tri: str) -> tuple[int, float | int]:
    """Clé de tri : valeurs valides d'abord, absentes ensuite."""
    indicateurs = entry.indicators
    if tri == TRI_TEMPS:
        valeur: float | int | None = indicateurs.duration_extraction_s
    elif tri == TRI_RAM:
        valeur = indicateurs.peak_memory_bytes
    elif tri == TRI_CPU:
        valeur = indicateurs.cpu_occupancy
    else:
        return (1, 0.0)
    return (1, 0.0) if valeur is None else (0, valeur)


def _date_key(valeur: Any) -> tuple[int, float]:
    """Clé de date : une date connue (`1`) passe avant une date inconnue (`0`)."""
    if not isinstance(valeur, str):
        return (0, 0.0)
    try:
        date = datetime.fromisoformat(valeur)
    except ValueError:
        return (0, 0.0)
    if date.tzinfo is None:
        date = date.replace(tzinfo=timezone.utc)
    try:
        return (1, date.timestamp())
    except (OverflowError, OSError, ValueError):
        return (0, 0.0)


def _recency_key(groupe: Group) -> tuple[tuple[int, float], str]:
    """Clé d'ordre d'un groupe : son extraction la plus récente."""
    return max((_date_key(entry.created_at), entry.run_id) for entry in groupe.entries)


# -- validation des fichiers --------------------------------------------------


def _validate_run(contenu: Any, identifiant: str) -> None:
    """Vérifie ce que la consultation interprète ; un type inattendu est refusé, jamais levé."""
    if not isinstance(contenu, Mapping):
        raise ResultatNonInterpretable("objet JSON attendu")
    schema = contenu.get("schema")
    if type(schema) is not int or schema != SCHEMA_EXTRACTION:
        raise ResultatNonInterpretable(
            f"schéma non pris en charge (schéma {SCHEMA_EXTRACTION} attendu)"
        )
    if contenu.get("type") != RUN_TYPE_EXTRACTION:
        raise ResultatNonInterpretable("type d'exécution attendu : extraction")
    if contenu.get("identifiant") != identifiant:
        raise ResultatNonInterpretable("identifiant incohérent avec le dossier")
    etat = contenu.get("etat")
    if not isinstance(etat, str) or etat not in LIBELLES_ETATS_EXECUTION:
        raise ResultatNonInterpretable("état d'extraction inconnu")
    grille = contenu.get("grille")
    if (
        not isinstance(grille, Mapping)
        or not isinstance(grille.get("nom"), str)
        or not isinstance(grille.get("sha256"), str)
    ):
        raise ResultatNonInterpretable("grille de l'extraction non interprétable")
    sources = contenu.get("sources")
    if not isinstance(sources, list):
        raise ResultatNonInterpretable("clé 'sources' absente ou invalide")
    rangs: set[int] = set()
    for plan in sources:
        if not isinstance(plan, Mapping):
            raise ResultatNonInterpretable("plan de source invalide")
        rang = plan.get("rang")
        if type(rang) is not int or rang < 1 or rang in rangs:
            raise ResultatNonInterpretable("rang de source invalide ou dupliqué")
        rangs.add(rang)
        if not isinstance(plan.get("dossier"), str) or not plan["dossier"]:
            raise ResultatNonInterpretable("dossier de source invalide")
        if not isinstance(plan.get("nom"), str):
            raise ResultatNonInterpretable("nom de source invalide")
        if not isinstance(plan.get("source"), Mapping) or not isinstance(plan.get("texte"), Mapping):
            raise ResultatNonInterpretable("provenance ou texte de source invalide")
        etat_source = plan.get("etat")
        if not isinstance(etat_source, str) or etat_source not in SOURCE_STATES:
            raise ResultatNonInterpretable("état de source inconnu")


def _source_result_valid(resultat: Any, run_id: str, plan: Mapping[str, Any]) -> bool:
    """Vrai si `result.json` est publié et cohérent avec son plan et son extraction.

    Le rang et le schéma sont comparés strictement (un booléen n'est jamais un
    entier). La provenance et le texte consignés doivent être identiques à ceux
    du plan : un résultat d'une autre extraction ou d'un autre audio est refusé.
    """
    if not isinstance(resultat, Mapping):
        return False
    schema = resultat.get("schema")
    etat = resultat.get("etat")
    rang = resultat.get("rang")
    return (
        type(schema) is int
        and schema == SCHEMA_EXTRACTION
        and resultat.get("type") == SOURCE_RESULT_TYPE
        and resultat.get("identifiant") == run_id
        and type(rang) is int
        and rang == plan["rang"]
        and resultat.get("nom") == plan["nom"]
        and resultat.get("dossier") == plan["dossier"]
        and isinstance(etat, str)
        and etat in SOURCE_PUBLISHED_STATES
        and resultat.get("texte") == plan.get("texte")
        and resultat.get("source") == plan.get("source")
    )


def _value_conforms(valeur: Mapping[str, Any], schema: Mapping[str, Any]) -> bool:
    """Vrai si la valeur extraite respecte le schéma copié (validateur interne D2).

    Un schéma ou une valeur de forme inattendue donne « non conforme », jamais une
    exception ni une valeur remplie avec des `null` inventés.
    """
    try:
        return validate_output(dict(valeur), dict(schema)).valid
    except (TypeError, KeyError, ValueError, AttributeError, IndexError):
        return False


# -- métadonnées, résumés et provenance ---------------------------------------


def _run_summary(run_id: str, contenu: Mapping[str, Any]) -> RunSummary:
    """Ligne de liste d'une extraction dont `run.json` est interprétable."""
    etat = contenu["etat"]
    modele = _mapping(contenu.get("modele"))
    moteur = _mapping(contenu.get("moteur"))
    mesures = _mapping(contenu.get("mesures"))
    sources = contenu["sources"]
    return RunSummary(
        run_id=run_id,
        state=etat,
        state_label=LIBELLES_ETATS_EXECUTION[etat],
        created_at=_text(contenu.get("cree_le")),
        grid_title=_text(_mapping(contenu.get("grille")).get("titre")),
        sources_total=len(sources),
        usable=True,
        reason=None,
        model=_text(modele.get("identifiant")) or _text(modele.get("id_resolu")),
        engine=_text(moteur.get("nom")) or _text(moteur.get("identifiant")),
        sources_processed=sum(1 for plan in sources if plan["etat"] != SOURCE_NOT_PROCESSED),
        duration_operation_s=_number(mesures.get("duree_operation_s")),
        marks=_marks(contenu, None),
        partial=etat != ETAT_TERMINEE,
    )


def _refused_run_summary(run_id: str, motif: str) -> RunSummary:
    """Ligne de liste pour un `run.json` refusé : aucun fait n'est inventé."""
    return RunSummary(
        run_id=run_id,
        state=None,
        state_label="non interprétable",
        created_at=None,
        grid_title=None,
        sources_total=None,
        usable=False,
        reason=motif,
        model=None,
        engine=None,
        sources_processed=None,
        duration_operation_s=None,
        marks=None,
        partial=None,
    )


def _unpublished_source(
    rang: int,
    nom: str,
    origine: Mapping[str, Any],
    motif: str | None,
    texte: str | None = None,
    texte_ok: bool = False,
) -> _SourceRead:
    """Source sans résultat publié : état `non_traitee`, copie du texte seulement."""
    return _SourceRead(
        rank=rang,
        name=nom,
        state=SOURCE_NOT_PROCESSED,
        reason=motif,
        origin=origine,
        text=texte,
        text_ok=texte_ok,
        result=None,
        value=None,
        raw_output=None,
    )


def _marks(contenu: Mapping[str, Any], resultat: Mapping[str, Any] | None) -> tuple[str, ...]:
    """Marques consignées, union conservatrice de `run.json` et de `result.json`.

    Une marque de mesures simulées présente dans l'un ou l'autre suffit à classer
    l'entrée à part : rien n'est déduit du moteur, de la famille ou des valeurs.
    """
    sources = [contenu] if resultat is None else [contenu, resultat]
    origine = _mapping(None if resultat is None else resultat.get("source"))
    marques: list[str] = []
    if any(source.get("factice") is True for source in sources):
        marques.append(MARQUE_FACTICE)
    if contenu.get("synthetique") is True:
        marques.append(MARQUE_SYNTHETIQUE)
    if any(source.get("mesures_simulees") is True for source in sources):
        marques.append(MARQUE_MESURES_SIMULEES)
    if origine.get("factice") is True:
        marques.append(MARK_SOURCE_FACTICE)
    return tuple(marques)


def _is_simulated(marques: Sequence[str]) -> bool:
    """Vrai si une marque de mesures simulées est consignée (`SYNTHÉTIQUE` seul non)."""
    return any(marque in MARQUES_MESURES_SIMULEES for marque in marques)


def _origin_present(donnees: Path, identifiant: str | None) -> bool:
    """Vrai si le dossier de la transcription d'origine existe encore (lecture seule)."""
    if identifiant is None or not MOTIF_IDENTIFIANT.fullmatch(identifiant):
        return False
    try:
        dossier = resoudre_resultat(identifiant, donnees)
    except ValeurRefusee:
        return False
    return dossier.is_dir() and (dossier / NOM_FICHIER_EXECUTION).is_file()


def _bounded_bytes(base: Path, nom: str) -> bytes | None:
    """Octets complets d'une copie confinée ; `None` si absente ou illisible."""
    try:
        chemin = resoudre_dans_racine(base, nom)
    except ValeurRefusee:
        return None
    try:
        with VERROU_STOCKAGE:
            if not chemin.is_file():
                return None
            return chemin.read_bytes()
    except OSError:
        return None


def _json_object(base: Path, nom: str) -> Mapping[str, Any]:
    """Objet JSON d'une copie confinée ; `{}` si absent, illisible ou non objet."""
    try:
        valeur = lire_json(resoudre_dans_racine(base, nom))
    except (ValeurRefusee, JsonInvalide, OSError):
        return {}
    return valeur if isinstance(valeur, Mapping) else {}


def _json_object_from_bytes(octets: bytes | None) -> Mapping[str, Any] | None:
    """Objet JSON lu depuis des octets déjà copiés, ou `None` si invalide."""
    texte = _decode_utf8(octets)
    if texte is None:
        return None
    try:
        valeur = json.loads(texte)
    except ValueError:
        return None
    return valeur if isinstance(valeur, Mapping) else None


def _decode_utf8(octets: bytes | None) -> str | None:
    """Texte UTF-8 d'une copie, ou `None` si absente ou non décodable."""
    if octets is None:
        return None
    try:
        return octets.decode("utf-8")
    except UnicodeDecodeError:
        return None


def _sha256(octets: bytes | None) -> str | None:
    """Empreinte SHA-256 hexadécimale des octets, ou `None`."""
    return None if octets is None else hashlib.sha256(octets).hexdigest()


def _pairs(contenu: Mapping[str, Any], champs: Sequence[tuple[str, str]]) -> tuple[tuple[str, Any], ...]:
    """Paires libellé / valeur scalaire, valeurs absentes ou non scalaires à `None`."""
    return tuple((libelle, _scalar(contenu.get(cle))) for cle, libelle in champs)


def _mapping(valeur: Any) -> Mapping[str, Any]:
    """Sous-objet JSON, vide s'il n'a pas la forme attendue."""
    return valeur if isinstance(valeur, Mapping) else {}


def _scalar(valeur: Any) -> Any:
    """Valeur scalaire affichable ; `None` pour un nombre non fini ou un objet."""
    if isinstance(valeur, (str, bool)) or type(valeur) is int:
        return valeur
    if isinstance(valeur, float) and math.isfinite(valeur):
        return valeur
    return None


def _text(valeur: Any) -> str | None:
    """Texte non vide, ou `None`."""
    return valeur if isinstance(valeur, str) and valeur.strip() else None


def _sha256_or_none(valeur: Any) -> str | None:
    """Empreinte SHA-256 en minuscules hexadécimales, ou `None` si invalide."""
    if not isinstance(valeur, str):
        return None
    empreinte = valeur.lower()
    return empreinte if MOTIF_EMPREINTE.fullmatch(empreinte) else None


def _number(valeur: Any) -> float | None:
    """Nombre fini et non négatif, ou `None` : booléens, NaN, infinis et négatifs exclus."""
    if isinstance(valeur, bool) or not isinstance(valeur, (int, float)):
        return None
    try:
        nombre = float(valeur)
    except OverflowError:
        return None
    if not math.isfinite(nombre) or nombre < 0:
        return None
    return nombre


def _count(valeur: Any) -> int | None:
    """Entier strict positif ou nul, ou `None` (booléens exclus)."""
    return valeur if type(valeur) is int and valeur >= 0 else None


def _int_or_none(valeur: Any) -> int | None:
    """Entier strict, ou `None`."""
    return valeur if type(valeur) is int else None


def _message(erreur: BaseException) -> str:
    """Texte court d'une erreur, sans message vide."""
    texte = str(erreur).strip()
    return texte if texte else type(erreur).__name__
