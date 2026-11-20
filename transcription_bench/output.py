"""Couche de sortie des commandes : texte par défaut, JSON stable (tâche 1.4).

Trois pièces, sans aucune commande métier :

1. `CommandOutput` écrit un résultat soit en texte français (lignes fournies par
   la commande), soit en un objet JSON unique portant `schema: 1`. En mode JSON,
   rien d'autre n'est écrit sur la sortie standard : les diagnostics vont sur la
   sortie d'erreur, préfixés comme ceux de la CLI.
2. `configure_utf8_streams` force l'UTF-8 sur les flux, avec remplacement
   `backslashreplace` : un caractère non encodable ne fait jamais échouer une
   commande, et une chaîne contenant une substitution de substitut reste un
   JSON valide (la séquence d'échappement est écrite telle quelle).
3. Les `serialize_*` construisent les objets JSON **vue par vue**, en listant les
   champs de chaque vue typée et leurs propriétés calculées (indicateurs,
   marque de simulation, annotation RAM). Aucun `asdict` aveugle : un champ
   ajouté à une vue n'entre dans le contrat qu'après un choix explicite ici.

Les noms des champs JSON reprennent ceux des vues existantes (français, unités
dans le nom) ; les clés nouvelles sont en anglais. Une valeur non finie
(`NaN`, infini) est sérialisée `null` : une mesure absente n'est jamais zéro.
Les résultats d'exécution omettent les fichiers internes (`fichier_brut`) et
le flux brut d'événements (`evenements`) ; leur journal borné est conservé.
"""

from __future__ import annotations

import json
import math
import sys
from collections.abc import Iterable, Mapping, Sequence
from enum import Enum
from pathlib import Path
from typing import Any, TextIO

from engines.declarations import Reglage
from transcription_bench.audios import AudioListe
from transcription_bench.consultation_resultats import (
    MARQUES_MESURES_SIMULEES,
    SEPARATEUR_SELECTION,
    AudioVue,
    CarteComparaison,
    CelluleComparaison,
    ComparaisonVue,
    CpuSystemeVue,
    DetailExecutionVue,
    EntreeEmpreinte,
    ExecutionListee,
    GroupeEmpreinte,
    IndicateursAudio,
    LigneComparaison,
    MaterielVue,
    MemoireSystemeVue,
    MesuresAudioVue,
    MesuresVue,
    ObservationSystemeVue,
    SegmentVue,
    SyntheseComparaison,
    TimingsNatifVue,
    TranscriptionVue,
)
from transcription_bench.executions import (
    SEPARATEUR_REFERENCE_MODELE,
    DemandeExecution,
    ModelePropose,
    PreparationExecution,
)
from transcription_bench.execution_extraction import ExtractionResult
from transcription_bench.execution_moteur import (
    AudioPrepare,
    ResultatAudio,
    ResultatExecution,
)
from transcription_bench.extraction_consultation import (
    CaseRow,
    Comparison,
    Entry,
    FillRow,
    Group,
    Indicators as ExtractionIndicators,
    RunDetail as ExtractionRunDetail,
    RunSummary,
    SourceDetail,
)
from transcription_bench.extractions import ExtractionRequest, ExtractionSource
from transcription_bench.gestion_modeles import ModeleLocal
from transcription_bench.historique import HISTORY_TYPE_TRANSCRIPTION, HistoryEntry
from transcription_bench.moteurs import EtatMoteur
from transcription_bench.operations import InstantaneCreneau
from transcription_bench.verification_modeles import FichierVerifie, ResultatVerification

#: Version du contrat JSON, portée par chaque objet de sortie.
OUTPUT_SCHEMA_VERSION = 1
SCHEMA_KEY = "schema"
JSON_OPTION = "--json"
UTF8_ENCODING = "utf-8"
#: Remplacement des caractères non encodables : jamais d'exception à l'écriture.
UNENCODABLE_REPLACEMENT = "backslashreplace"
DIAGNOSTIC_PREFIX = "transcription-bench : "

def add_json_option(parser: Any) -> None:
    """Ajoute `--json` à un sous-analyseur de commande (jamais à `serve`)."""
    parser.add_argument(
        JSON_OPTION,
        action="store_true",
        default=False,
        help="écrit un objet JSON (schéma 1) sur la sortie standard",
    )


def configure_utf8_streams(*streams: TextIO | None) -> None:
    """Force UTF-8 sur les flux qui le permettent, sans échec sur les autres.

    Un flux sans `reconfigure` (capture de test, `StringIO`, absence de console)
    est laissé tel quel : il ne peut pas imposer d'encodage.
    """
    for stream in streams:
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding=UTF8_ENCODING, errors=UNENCODABLE_REPLACEMENT)


def to_json_value(value: Any) -> Any:
    """Convertit une valeur de vue en valeur JSON, sans rien inventer.

    Non finis → `None` (mesure indisponible) ; `Path` → texte ; `Enum` → sa
    valeur ; tuples et listes → listes ; mappings → objets à clés textuelles.
    Tout autre type lève `TypeError` : une vue qui en contient un est un bogue
    à corriger ici, pas une valeur à deviner.
    """
    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, Enum):
        return to_json_value(value.value)
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Mapping):
        return {str(key): to_json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [to_json_value(item) for item in value]
    raise TypeError(f"valeur non sérialisable en JSON : {type(value).__name__}")


def with_schema(data: Mapping[str, Any]) -> dict[str, Any]:
    """Ajoute `schema` en tête d'un objet de sortie, refusant un doublon."""
    if SCHEMA_KEY in data:
        raise ValueError(f"clé réservée dans la sortie : {SCHEMA_KEY!r}")
    return {SCHEMA_KEY: OUTPUT_SCHEMA_VERSION, **to_json_value(data)}


def json_line(data: Mapping[str, Any]) -> str:
    """Une ligne JSON complète : objet versionné, sans NaN, accents conservés."""
    return json.dumps(with_schema(data), ensure_ascii=False, allow_nan=False)


class CommandOutput:
    """Écrit le résultat d'une commande en texte ou en JSON, sans autre sortie.

    `result` reçoit l'objet JSON de la commande et les lignes de texte qui le
    présentent : seule l'une des deux formes est écrite selon le mode. Les
    diagnostics vont toujours sur la sortie d'erreur.
    """

    def __init__(
        self,
        *,
        json_mode: bool,
        stdout: TextIO | None = None,
        stderr: TextIO | None = None,
    ) -> None:
        self._json_mode = json_mode
        self._stdout = sys.stdout if stdout is None else stdout
        self._stderr = sys.stderr if stderr is None else stderr

    @property
    def json_mode(self) -> bool:
        """Vrai quand la sortie standard ne reçoit que l'objet JSON."""
        return self._json_mode

    def result(self, data: Mapping[str, Any], text_lines: Iterable[str] = ()) -> None:
        """Écrit l'objet JSON en mode JSON, sinon les lignes de texte."""
        if self._json_mode:
            self._write(self._stdout, json_line(data))
            return
        for line in text_lines:
            self._write(self._stdout, line)

    def event(self, data: Mapping[str, Any], text: str) -> None:
        """Écrit un événement de journal : une ligne JSON complète, ou le texte seul.

        Chaque appel écrit une ligne entière puis vide le flux : une ligne n'est
        jamais tronquée, même si la commande est interrompue ensuite.
        """
        if self._json_mode:
            self._write(self._stdout, json_line(data))
            return
        self._write(self._stdout, text)

    def diagnostic(self, message: str) -> None:
        """Écrit un diagnostic sur la sortie d'erreur, sans trace."""
        self._write(self._stderr, f"{DIAGNOSTIC_PREFIX}{message}")

    @staticmethod
    def _write(stream: TextIO, text: str) -> None:
        stream.write(text + "\n")
        stream.flush()


def output_from_arguments(
    arguments: Any,
    *,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
) -> CommandOutput:
    """Construit la sortie d'une commande à partir de son option `--json`."""
    return CommandOutput(
        json_mode=bool(getattr(arguments, "json", False)),
        stdout=stdout,
        stderr=stderr,
    )


# --- Sérialiseurs par vue -------------------------------------------------
#
# Chaque sérialiseur liste ses champs explicitement et lit les propriétés
# calculées disponibles. Pour une liste d'exécutions, la marque de simulation
# est dérivée des marques existantes, sans conclure si elles sont inconnues.


def _simulated(markers: Sequence[str] | None) -> bool | None:
    """Marque de simulation, inconnue si l'exécution est illisible."""
    if markers is None:
        return None
    return any(marker in MARQUES_MESURES_SIMULEES for marker in markers)


def serialize_pairs(pairs: Iterable[tuple[str, Any]]) -> list[dict[str, Any]]:
    """Paires libellé / valeur d'affichage, valeur formatée et conservée telle quelle."""
    return [{"label": label, "value": to_json_value(value)} for label, value in pairs]


def serialize_indicators(indicators: IndicateursAudio) -> dict[str, Any]:
    """Trois indicateurs de premier niveau, valeurs brutes et ratios."""
    return {
        "duree_transcription_s": to_json_value(indicators.duree_transcription_s),
        "pic_memoire_octets": to_json_value(indicators.pic_memoire_octets),
        "ram_totale_octets": to_json_value(indicators.ram_totale_octets),
        "temps_cpu_s": to_json_value(indicators.temps_cpu_s),
        "part_ram": to_json_value(indicators.part_ram),
        "occupation_cpu": to_json_value(indicators.occupation_cpu),
    }


def serialize_cpu_system(view: CpuSystemeVue | None) -> dict[str, Any] | None:
    """Occupation CPU globale de l'ordinateur pendant un audio."""
    if view is None:
        return None
    return {
        "pourcentage_moyen": to_json_value(view.pourcentage_moyen),
        "intervalle_s": to_json_value(view.intervalle_s),
        "motif": to_json_value(view.motif),
    }


def serialize_memory_system(view: MemoireSystemeVue | None) -> dict[str, Any] | None:
    """Instantané de RAM disponible et capacité totale au même instant."""
    if view is None:
        return None
    return {
        "releve_le": to_json_value(view.releve_le),
        "totale_octets": to_json_value(view.totale_octets),
        "disponible_octets": to_json_value(view.disponible_octets),
        "motif": to_json_value(view.motif),
    }


def serialize_system_observation(view: ObservationSystemeVue) -> dict[str, Any]:
    """Observation système relue, avec son état calculé et sa provenance."""
    return {
        "etat": to_json_value(view.etat),
        "lisible": view.lisible,
        "cle_presente": view.cle_presente,
        "ecarte_a_l_ecriture": view.ecarte_a_l_ecriture,
        "motif": to_json_value(view.motif),
        "provenance": to_json_value(view.provenance),
        "simulee": view.simulee,
        "version": to_json_value(view.version),
        "methode_cpu": to_json_value(view.methode_cpu),
        "version_psutil": to_json_value(view.version_psutil),
        "cpu": serialize_cpu_system(view.cpu),
        "memoire_apres": serialize_memory_system(view.memoire_apres),
    }


def serialize_audio_measures(view: MesuresAudioVue | None) -> dict[str, Any] | None:
    """Mesures d'une transcription ; `None` (mesure indisponible) n'est jamais zéro."""
    if view is None:
        return None
    return {
        "temps_decodage_s": to_json_value(view.temps_decodage_s),
        "duree_transcription_s": to_json_value(view.duree_transcription_s),
        "temps_cpu_s": to_json_value(view.temps_cpu_s),
        "rtf": to_json_value(view.rtf),
        "pic_memoire_octets": to_json_value(view.pic_memoire_octets),
    }


def serialize_hardware(view: MaterielVue | None) -> dict[str, Any] | None:
    """Matériel consigné pour un essai, jamais celui du poste qui consulte."""
    if view is None:
        return None
    return {
        "os": to_json_value(view.os),
        "version_os": to_json_value(view.version_os),
        "architecture": to_json_value(view.architecture),
        "processeur": to_json_value(view.processeur),
        "coeurs_physiques": to_json_value(view.coeurs_physiques),
        "coeurs_logiques": to_json_value(view.coeurs_logiques),
        "ram_totale_octets": to_json_value(view.ram_totale_octets),
    }


def serialize_native_timings(view: TimingsNatifVue) -> dict[str, Any]:
    """Timings d'un appel natif, unité transmise par le moteur."""
    return {
        "unite": to_json_value(view.unite),
        "chargement": to_json_value(view.chargement),
        "mel": to_json_value(view.mel),
        "encodage": to_json_value(view.encodage),
        "decodage": to_json_value(view.decodage),
    }


def serialize_segment(view: SegmentVue) -> dict[str, Any]:
    """Segment horodaté ; une borne non finie reste `None`."""
    return {
        "debut_s": to_json_value(view.debut_s),
        "fin_s": to_json_value(view.fin_s),
        "texte": to_json_value(view.texte),
    }


def serialize_transcription(view: TranscriptionVue | None) -> dict[str, Any] | None:
    """Transcription relue d'un audio, avec son état et ses marques."""
    if view is None:
        return None
    return {
        "statut": to_json_value(view.statut),
        "ecrit_le": to_json_value(view.ecrit_le),
        "texte": to_json_value(view.texte),
        "segments": [serialize_segment(segment) for segment in view.segments],
        "marques": to_json_value(view.marques),
        "audio": serialize_pairs(view.audio),
        "empreinte_sha256": to_json_value(view.empreinte_sha256),
        "duree_indicative_s": to_json_value(view.duree_indicative_s),
        "duree_decodee_s": to_json_value(view.duree_decodee_s),
        "mesures": serialize_audio_measures(view.mesures),
        "timings_natifs": [serialize_native_timings(t) for t in view.timings_natifs],
        "reglages": serialize_pairs(view.reglages),
        "reglages_bruts": to_json_value(view.reglages_bruts),
        "reglages_effectifs": serialize_pairs(view.reglages_effectifs),
        "reglages_effectifs_bruts": to_json_value(view.reglages_effectifs_bruts),
        "threads": serialize_pairs(view.threads),
        "langue_imposee": to_json_value(view.langue_imposee),
        "fenetre": serialize_pairs(view.fenetre),
        "modele": serialize_pairs(view.modele),
        "moteur": serialize_pairs(view.moteur),
        "famille": to_json_value(view.famille),
        "erreur": to_json_value(view.erreur),
        "observation_systeme": serialize_system_observation(view.observation_systeme),
        "simule": view.simule_mesures,
    }


def serialize_audio_view(view: AudioVue) -> dict[str, Any]:
    """Audio d'une exécution : transcription, indicateurs et annotations."""
    return {
        "ordre": view.ordre,
        "nom": view.nom,
        "dossier": view.dossier,
        "statut": view.statut,
        "libelle_statut": view.libelle_statut,
        "erreur": to_json_value(view.erreur),
        "partiel": view.partiel,
        "motif_indisponible": to_json_value(view.motif_indisponible),
        "transcription": serialize_transcription(view.transcription),
        "indicateurs": serialize_indicators(view.indicateurs),
        "annotation_ram": to_json_value(view.annotation_ram),
        "materiel_alerte": to_json_value(view.materiel_alerte),
        "observation_systeme": serialize_system_observation(view.observation_systeme),
    }


def serialize_run_measures(view: MesuresVue) -> dict[str, Any]:
    """Mesures globales d'une exécution ; `None` = indisponible."""
    return {
        "duree_operation_s": to_json_value(view.duree_operation_s),
        "duree_processus_s": to_json_value(view.duree_processus_s),
        "duree_chargement_s": to_json_value(view.duree_chargement_s),
        "pic_memoire_octets": to_json_value(view.pic_memoire_octets),
        "pic_memoire_partiel": to_json_value(view.pic_memoire_partiel),
        "observation_chargement": serialize_system_observation(
            view.observation_chargement
        ),
    }


def serialize_execution_listing(view: ExecutionListee) -> dict[str, Any]:
    """Ligne de la liste des exécutions, ou en-tête de détail."""
    return {
        "identifiant": view.identifiant,
        "etat": to_json_value(view.etat),
        "libelle_etat": view.libelle_etat,
        "cree_le": to_json_value(view.cree_le),
        "modele": to_json_value(view.modele),
        "moteur": to_json_value(view.moteur),
        "audios_traites": to_json_value(view.audios_traites),
        "audios_total": to_json_value(view.audios_total),
        "duree_operation_s": to_json_value(view.duree_operation_s),
        "partiel": view.partiel,
        "marques": to_json_value(view.marques),
        "exploitable": view.exploitable,
        "motif": to_json_value(view.motif),
        "simule": _simulated(view.marques),
    }


def serialize_run_detail(view: DetailExecutionVue) -> dict[str, Any]:
    """Détail d'une exécution : métadonnées, mesures globales et audios."""
    return {
        "execution": serialize_execution_listing(view.execution),
        "fin": to_json_value(view.fin),
        "erreur": to_json_value(view.erreur),
        "famille": to_json_value(view.famille),
        "threads_demandes": to_json_value(view.threads_demandes),
        "threads_appliques": to_json_value(view.threads_appliques),
        "fenetre_fixe_s": to_json_value(view.fenetre_fixe_s),
        "reglages": serialize_pairs(view.reglages),
        "reglages_effectifs": serialize_pairs(view.reglages_effectifs),
        "modele": serialize_pairs(view.modele),
        "moteur": serialize_pairs(view.moteur),
        "versions_moteur": serialize_pairs(view.versions_moteur),
        "machine": serialize_pairs(view.machine),
        "programme": serialize_pairs(view.programme),
        "processus": serialize_pairs(view.processus),
        "mesures": serialize_run_measures(view.mesures),
        "audios": [serialize_audio_view(audio) for audio in view.audios],
        "partiel": view.partiel,
        "libelle_modele": view.libelle_modele,
        "simule": view.simule_mesures,
    }


def serialize_hash_entry(view: EntreeEmpreinte) -> dict[str, Any]:
    """Transcription rattachée à l'empreinte de son audio, avec sa sélection."""
    return {
        "execution": view.execution,
        "ordre": view.ordre,
        "selection": f"{view.execution}{SEPARATEUR_SELECTION}{view.ordre}",
        "nom": view.nom,
        "empreinte": view.empreinte,
        "statut": view.statut,
        "libelle_statut": view.libelle_statut,
        "libelle_etat": view.libelle_etat,
        "etat": to_json_value(view.etat),
        "partiel": view.partiel,
        "marques": to_json_value(view.marques),
        "modele": to_json_value(view.modele),
        "moteur": to_json_value(view.moteur),
        "mesures": serialize_audio_measures(view.mesures),
        "materiel": serialize_hardware(view.materiel),
        "date_essai": to_json_value(view.date_essai),
        "reglages": serialize_pairs(view.reglages),
        "reglages_bruts": to_json_value(view.reglages_bruts),
        "reglages_distinctifs": serialize_pairs(view.reglages_distinctifs),
        "variante": to_json_value(view.variante),
        "revision": to_json_value(view.revision),
        "duree_decodee_s": to_json_value(view.duree_decodee_s),
        "materiel_alerte": to_json_value(view.materiel_alerte),
        "observation_systeme": serialize_system_observation(view.observation_systeme),
        "observation_chargement": serialize_system_observation(
            view.observation_chargement
        ),
        "indicateurs": serialize_indicators(view.indicateurs),
        "annotation_ram": to_json_value(view.annotation_ram),
        "simule": view.simule,
    }


def serialize_hash_group(view: GroupeEmpreinte) -> dict[str, Any]:
    """Groupe d'un même audio : mesures observées et simulées séparées."""
    return {
        "empreinte": view.empreinte,
        "noms": to_json_value(view.noms),
        "duree_decodee_commune_s": to_json_value(view.duree_decodee_commune_s),
        "durees_divergentes": view.durees_divergentes,
        "entrees_reelles": [serialize_hash_entry(e) for e in view.entrees_reelles],
        "entrees_simulees": [serialize_hash_entry(e) for e in view.entrees_simulees],
    }


def serialize_comparison_cell(view: CelluleComparaison) -> dict[str, Any]:
    """Cellule de comparaison : absence distinguée, valeur brute pour les écarts."""
    return {
        "presente": view.presente,
        "valeur": to_json_value(view.valeur),
        "brut": to_json_value(view.brut),
    }


def serialize_comparison_line(view: LigneComparaison) -> dict[str, Any]:
    """Ligne de la table de comparaison, une cellule par transcription."""
    return {
        "libelle": view.libelle,
        "nature": view.nature,
        "cellules": [serialize_comparison_cell(c) for c in view.cellules],
        "differents": view.differents,
    }


def serialize_comparison_card(view: CarteComparaison) -> dict[str, Any]:
    """Carte de premier niveau : indicateurs, annotations et texte complet."""
    return {
        "selection": f"{view.entree.execution}{SEPARATEUR_SELECTION}{view.entree.ordre}",
        "libelle": view.libelle,
        "texte": to_json_value(view.texte),
        "indicateurs": serialize_indicators(view.indicateurs),
        "annotation_ram": to_json_value(view.annotation_ram),
        "materiel_alerte": to_json_value(view.materiel_alerte),
        "erreur": to_json_value(view.erreur),
        "partiel": view.entree.partiel,
        "simule": view.entree.simule,
    }


def serialize_comparison_summary(view: SyntheseComparaison) -> dict[str, Any]:
    """Synthèse descriptive, sans score global ni vainqueur CPU."""
    return {
        "plus_rapides": to_json_value(view.plus_rapides),
        "moins_de_ram": to_json_value(view.moins_de_ram),
        "exclues": to_json_value(view.exclues),
    }


def serialize_comparison(view: ComparaisonVue) -> dict[str, Any]:
    """Comparaison côte à côte de transcriptions d'un même audio."""
    return {
        "empreinte": view.empreinte,
        "noms": to_json_value(view.noms),
        "colonnes": [serialize_hash_entry(entree) for entree in view.colonnes],
        "lignes": [serialize_comparison_line(ligne) for ligne in view.lignes],
        "factice": view.factice,
        "partiel": view.partiel,
        "cartes": [serialize_comparison_card(carte) for carte in view.cartes],
        "synthese": serialize_comparison_summary(view.synthese),
    }


def serialize_setting(view: Reglage) -> dict[str, Any]:
    """Réglage déclaré par la famille d'un modèle, avec son défaut."""
    return {
        "nom": view.nom,
        "libelle": view.libelle,
        "type_valeur": view.type_valeur,
        "defaut": to_json_value(view.defaut),
        "description": view.description,
        "valeurs": to_json_value(view.valeurs),
    }


def serialize_model_option(view: ModelePropose) -> dict[str, Any]:
    """Modèle proposé à l'exécution, exécutable ou avec son motif."""
    return {
        "reference": view.reference,
        "moteur": view.moteur,
        "nom_moteur": view.nom_moteur,
        "cle": view.cle,
        "identifiant": view.identifiant,
        "id_resolu": view.id_resolu,
        "commit": view.commit,
        "famille": view.famille,
        "libelle_famille": view.libelle_famille,
        "qualifiee": view.qualifiee,
        "fichier_gguf": to_json_value(view.fichier_gguf),
        "reglages": [serialize_setting(reglage) for reglage in view.reglages],
        "fenetre_fixe_secondes": to_json_value(view.fenetre_fixe_secondes),
        "executable": view.executable,
        "motif_non_executable": to_json_value(view.motif_non_executable),
        "synthetique": view.synthetique,
    }


def serialize_preparation(view: PreparationExecution) -> dict[str, Any]:
    """Préparation appliquée, défauts et messages de repli compris."""
    return {
        "modele": None if view.modele is None else serialize_model_option(view.modele),
        "moteur": view.moteur,
        "audios": to_json_value(view.audios),
        "notice": view.notice,
        "threads": view.threads,
        "reglages": [
            {"reglage": serialize_setting(setting), "valeur": to_json_value(value)}
            for setting, value in view.reglages
        ],
        "reinitialisation": view.reinitialisation,
        "applicable": view.applicable,
        "reference": view.reference,
    }


def serialize_extraction_source(view: ExtractionSource) -> dict[str, Any]:
    """Source d'extraction : provenance et empreintes, jamais le texte source."""
    return {
        "reference": view.reference,
        "identifiant": view.identifiant,
        "ordre": view.ordre,
        "nom": view.nom,
        "empreinte_audio": to_json_value(view.empreinte_audio),
        "empreinte_texte": view.empreinte_texte,
        "caracteres": view.caracteres,
        "moteur": to_json_value(view.moteur),
        "modele": to_json_value(view.modele),
        "factice": view.factice,
    }


def serialize_extraction_request(view: ExtractionRequest) -> dict[str, Any]:
    """Demande d'extraction validée : modèle, grille, sources et réglages effectifs."""
    modele = view.modele
    grille = view.grille
    return {
        "reference": modele.reference,
        "moteur": view.moteur,
        "cle": modele.cle,
        "identifiant": modele.identifiant,
        "id_resolu": modele.id_resolu,
        "commit": modele.commit,
        "famille": modele.famille,
        "fichier_gguf": to_json_value(modele.fichier_gguf),
        "synthetique": view.synthetique,
        "grid": {
            "name": grille.nom,
            "title": grille.titre,
            "sha256": grille.sha256,
            "field_count": grille.nombre_cases,
            "version_consignes": grille.version_consignes,
        },
        "sources": [serialize_extraction_source(source) for source in view.sources],
        "threads": view.threads,
        "reglages": [
            {"nom": reglage.nom, "valeur": to_json_value(reglage.valeur)}
            for reglage in view.reglages
        ],
    }


def serialize_extraction_result(view: ExtractionResult) -> dict[str, Any]:
    """Issue d'une extraction : compte et état de chaque source, sans texte ni sortie.

    `dossier_travail_conserve` signale un reste de purge (D7) : diagnostic
    uniquement, sans chemin, qui ne change ni l'état ni le code de sortie.
    """
    return {
        "etat": view.etat,
        "factice": view.factice,
        "moteur": view.moteur,
        "famille": view.famille,
        "modele_identifiant": view.modele_identifiant,
        "nombre_sources": view.nombre_sources,
        "erreur": to_json_value(view.erreur),
        "code_sortie": to_json_value(view.code_sortie),
        "pid": to_json_value(view.pid),
        "arret_demande": view.arret_demande,
        "identifiant_resultat": to_json_value(view.identifiant_resultat),
        "duree_operation_s": to_json_value(view.duree_operation_s),
        "duree_processus_s": to_json_value(view.duree_processus_s),
        "summary": to_json_value(view.summary),
        "sources": to_json_value(view.sources),
        "dossier_travail_conserve": view.dossier_travail_conserve,
    }


def serialize_verified_file(view: FichierVerifie) -> dict[str, Any]:
    """Fichier retenu par une vérification, taille absente non remplacée."""
    return {"nom": view.nom, "taille": to_json_value(view.taille)}


def serialize_local_model(view: ModeleLocal) -> dict[str, Any]:
    """Modèle prêt, relu depuis son manifeste cohérent."""
    return {
        "reference": f"{view.moteur}{SEPARATEUR_REFERENCE_MODELE}{view.cle}",
        "moteur": view.moteur,
        "cle": view.cle,
        "identifiant": view.identifiant,
        "id_resolu": view.id_resolu,
        "commit": view.commit,
        "famille": view.famille,
        "fichier_gguf": to_json_value(view.fichier_gguf),
        "fichiers": [serialize_verified_file(f) for f in view.fichiers],
        "taille_disque": to_json_value(view.taille_disque),
        "taille_distante": to_json_value(view.taille_distante),
        "date": view.date,
    }


def serialize_verification_result(view: ResultatVerification) -> dict[str, Any]:
    """Résultat de vérification d'un dépôt, accepté ou refusé avec sa raison."""
    return {
        "accepte": view.accepte,
        "identifiant": view.identifiant,
        "moteur": view.moteur,
        "famille": to_json_value(view.famille),
        "commit": to_json_value(view.commit),
        "id_resolu": to_json_value(view.id_resolu),
        "fichiers": [serialize_verified_file(f) for f in view.fichiers],
        "taille_totale": to_json_value(view.taille_totale),
        "gguf_candidats": to_json_value(view.gguf_candidats),
        "fichier_gguf": to_json_value(view.fichier_gguf),
        "raison": to_json_value(view.raison),
        "message": view.message,
        "fichiers_manquants": to_json_value(view.fichiers_manquants),
        "moteur_suggere": to_json_value(view.moteur_suggere),
    }


def serialize_engine_state(view: EtatMoteur) -> dict[str, Any]:
    """État d'un moteur ; une version absente reste `null`, jamais inventée."""
    return {
        "identifiant": view.identifiant,
        "nom": view.nom,
        "tasks": list(view.tasks),
        "etat": view.etat,
        "factice": view.factice,
        "installable": view.installable,
        "note": to_json_value(view.note),
        "date_installation": to_json_value(view.date_installation),
        "versions": [
            {"module": module, "version": to_json_value(version)}
            for module, version in view.versions
        ],
    }


def serialize_audio_entry(view: AudioListe) -> dict[str, Any]:
    """Audio d'entrée ; une entrée en erreur n'est jamais proposée à une exécution."""
    return {
        "nom": view.nom,
        "format": view.format,
        "taille_octets": to_json_value(view.taille_octets),
        "duree_indicative": to_json_value(view.duree_indicative),
        "erreur": to_json_value(view.erreur),
        "readable": view.erreur is None,
    }


def serialize_operation_state(view: InstantaneCreneau) -> dict[str, Any]:
    """Copie de l'état du créneau d'opération, avec son journal complet."""
    return {
        "etat": view.etat,
        "arrete": view.arrete,
        "type_operation": to_json_value(view.type_operation),
        "cible": to_json_value(view.cible),
        "debut": to_json_value(view.debut),
        "fin": to_json_value(view.fin),
        "erreur": to_json_value(view.erreur),
        "journal": to_json_value(view.journal),
        "generation": view.generation,
    }


def serialize_run_request(view: DemandeExecution) -> dict[str, Any]:
    """Demande d'exécution validée, réglages effectifs compris."""
    return {
        "reference": f"{view.moteur}{SEPARATEUR_REFERENCE_MODELE}{view.cle}",
        "moteur": view.moteur,
        "cle": view.cle,
        "identifiant": view.identifiant,
        "id_resolu": view.id_resolu,
        "commit": view.commit,
        "famille": view.famille,
        "fichier_gguf": to_json_value(view.fichier_gguf),
        "audios": to_json_value(view.audios),
        "threads": view.threads,
        "reglages": [
            {"nom": reglage.nom, "valeur": to_json_value(reglage.valeur)}
            for reglage in view.reglages
        ],
        "fenetre_fixe_secondes": to_json_value(view.fenetre_fixe_secondes),
        "synthetique": view.synthetique,
    }


def serialize_audio_prepare(view: AudioPrepare | None) -> dict[str, Any] | None:
    """Métadonnées d'un audio décodé ; le fichier de travail n'est pas exposé."""
    if view is None:
        return None
    return {
        "index": view.index,
        "nom": view.nom,
        "format": view.format,
        "taille_octets": view.taille_octets,
        "empreinte_sha256": view.empreinte_sha256,
        "duree_indicative": to_json_value(view.duree_indicative),
        "duree_decodee": view.duree_decodee,
        "echantillons": view.echantillons,
        "temps_decodage": to_json_value(view.temps_decodage),
    }


def serialize_run_audio_result(view: ResultatAudio) -> dict[str, Any]:
    """Issue d'un audio : `non_traite` est calculé, jamais déduit d'un zéro."""
    return {
        "index": view.index,
        "nom": view.nom,
        "prepare": serialize_audio_prepare(view.prepare),
        "evenement": to_json_value(view.evenement),
        "erreur": to_json_value(view.erreur),
        "factice": view.factice,
        "synthetique": view.synthetique,
        "non_traite": view.non_traite,
    }


def serialize_run_result(view: ResultatExecution) -> dict[str, Any]:
    """Issue d'une exécution ; les événements bruts restent dans `run.log`."""
    return {
        "etat": view.etat,
        "factice": view.factice,
        "synthetique": view.synthetique,
        "moteur": view.moteur,
        "famille": view.famille,
        "modele_identifiant": view.modele_identifiant,
        "threads_demandes": view.threads_demandes,
        "audios": [serialize_run_audio_result(audio) for audio in view.audios],
        "lignes_parasites": view.lignes_parasites,
        "journal_moteur": to_json_value(view.journal_moteur),
        "erreur": to_json_value(view.erreur),
        "code_sortie": to_json_value(view.code_sortie),
        "pid": to_json_value(view.pid),
        "arret_demande": view.arret_demande,
        "identifiant_resultat": to_json_value(view.identifiant_resultat),
        "duree_operation_s": to_json_value(view.duree_operation_s),
        "duree_processus_s": to_json_value(view.duree_processus_s),
        "audios_en_erreur": to_json_value(view.audios_en_erreur),
        "audios_non_traites": to_json_value(view.audios_non_traites),
    }


# --- Sérialiseurs de la consultation des extractions (tâche 4.2, design D9) -
#
# Mêmes principes que ci-dessus : champs listés explicitement, aucun `asdict`
# aveugle. Les noms de champs reprennent ceux des vues de `extraction_consultation`
# (anglais, tâche 4.1) ; les regroupements affichables (modèle, moteur, machine,
# mesures, programme) réutilisent `serialize_pairs`, comme pour les résultats de
# transcription.


def serialize_extraction_indicators(view: ExtractionIndicators) -> dict[str, Any]:
    """Indicateurs bruts d'une source d'extraction, et leurs deux ratios."""
    return {
        "duration_extraction_s": to_json_value(view.duration_extraction_s),
        "time_to_first_token_s": to_json_value(view.time_to_first_token_s),
        "generation_duration_s": to_json_value(view.generation_duration_s),
        "generation_speed_tps": to_json_value(view.generation_speed_tps),
        "read_speed_estimate_tps": to_json_value(view.read_speed_estimate_tps),
        "tokens_in": to_json_value(view.tokens_in),
        "tokens_out": to_json_value(view.tokens_out),
        "cpu_time_s": to_json_value(view.cpu_time_s),
        "peak_memory_bytes": to_json_value(view.peak_memory_bytes),
        "ram_total_bytes": to_json_value(view.ram_total_bytes),
        "ram_ratio": to_json_value(view.ram_ratio),
        "cpu_occupancy": to_json_value(view.cpu_occupancy),
    }


def serialize_extraction_entry(view: Entry) -> dict[str, Any]:
    """Source publiée d'une extraction : état, provenance, valeur et autres informations."""
    return {
        "selection": view.selection,
        "run_id": view.run_id,
        "rank": view.rank,
        "audio_name": view.audio_name,
        "state": view.state,
        "state_label": view.state_label,
        "partial": view.partial,
        "source_state": view.source_state,
        "source_state_label": view.source_state_label,
        "reason": to_json_value(view.reason),
        "compliant": view.compliant,
        "created_at": to_json_value(view.created_at),
        "created_short": view.created_short,
        "model": to_json_value(view.model),
        "engine": to_json_value(view.engine),
        "family": to_json_value(view.family),
        "transcription_run_id": to_json_value(view.transcription_run_id),
        "transcription_order": to_json_value(view.transcription_order),
        "transcription_model": to_json_value(view.transcription_model),
        "audio_sha256": to_json_value(view.audio_sha256),
        "text_sha256": to_json_value(view.text_sha256),
        "marks": to_json_value(view.marks),
        "simulated": view.simulated,
        "consignes_version": to_json_value(view.consignes_version),
        "format_version": to_json_value(view.format_version),
        "indicators": serialize_extraction_indicators(view.indicators),
        "value": to_json_value(view.value),
        "other_info": serialize_pairs(view.other_info),
        "groupable": view.groupable,
        "copy_issue": to_json_value(view.copy_issue),
    }


def serialize_extraction_group(view: Group) -> dict[str, Any]:
    """Groupe d'extractions comparables : entrées réelles puis simulées, dans l'ordre reçu."""
    return {
        "key": view.key,
        "text_sha256": view.text_sha256,
        "grid_sha256": view.grid_sha256,
        "schema_sha256": view.schema_sha256,
        "grid_name": view.grid_name,
        "grid_title": to_json_value(view.grid_title),
        "audio_names": to_json_value(view.audio_names),
        "transcription_models": to_json_value(view.transcription_models),
        "entries": [serialize_extraction_entry(entry) for entry in view.entries],
        "consignes_versions": to_json_value(view.consignes_versions),
        "consignes_diverge": view.consignes_diverge,
    }


def serialize_fill_row(view: FillRow) -> dict[str, Any]:
    """Ligne de la grille remplie : libellé, profondeur et valeur affichable."""
    return {
        "label": view.label,
        "depth": view.depth,
        "display": view.display,
        "absent": view.absent,
    }


def serialize_extraction_source_detail(view: SourceDetail) -> dict[str, Any]:
    """Détail d'une source : état, grille remplie ou sortie brute, texte source."""
    return {
        "rank": view.rank,
        "name": view.name,
        "state": view.state,
        "state_label": view.state_label,
        "reason": to_json_value(view.reason),
        "origin": to_json_value(view.origin),
        "entry": None if view.entry is None else serialize_extraction_entry(view.entry),
        "rows": (
            None if view.rows is None else [serialize_fill_row(row) for row in view.rows]
        ),
        "source_text": to_json_value(view.source_text),
        "source_copy_ok": view.source_copy_ok,
        "raw_output": to_json_value(view.raw_output),
        "origin_present": view.origin_present,
        "raw_result": to_json_value(view.raw_result),
    }


def serialize_extraction_run_detail(view: ExtractionRunDetail) -> dict[str, Any]:
    """Détail d'une extraction : métadonnées complètes, grille copiée et sources."""
    return {
        "run_id": view.run_id,
        "state": view.state,
        "state_label": view.state_label,
        "created_at": to_json_value(view.created_at),
        "finished_at": to_json_value(view.finished_at),
        "error": to_json_value(view.error),
        "partial": view.partial,
        "grid_name": view.grid_name,
        "grid_title": to_json_value(view.grid_title),
        "grid_copy": to_json_value(view.grid_copy),
        "grid_copy_ok": view.grid_copy_ok,
        "system_message": to_json_value(view.system_message),
        "consignes_version": to_json_value(view.consignes_version),
        "format_version": to_json_value(view.format_version),
        "model": serialize_pairs(view.model),
        "engine": serialize_pairs(view.engine),
        "engine_versions": to_json_value(view.engine_versions),
        "program": serialize_pairs(view.program),
        "machine": serialize_pairs(view.machine),
        "measures": serialize_pairs(view.measures),
        "settings": [
            {"name": name, "value": to_json_value(value)} for name, value in view.settings
        ],
        "threads_requested": to_json_value(view.threads_requested),
        "threads_applied": to_json_value(view.threads_applied),
        "weight_loading_mode": to_json_value(view.weight_loading_mode),
        "effective_settings": to_json_value(view.effective_settings),
        "marks": to_json_value(view.marks),
        "simulated": view.simulated,
        "sources": [serialize_extraction_source_detail(source) for source in view.sources],
        "raw_metadata": to_json_value(view.raw_metadata),
    }


def serialize_case_row(view: CaseRow) -> dict[str, Any]:
    """Ligne de comparaison d'une case de grille, une valeur par extraction."""
    return {
        "label": view.label,
        "values": to_json_value(view.values),
        "differs": view.differs,
    }


def serialize_extraction_comparison(view: Comparison) -> dict[str, Any]:
    """Comparaison de 2 à 6 extractions d'un même groupe, dans l'ordre reçu.

    `source_text` est le texte source copié, commun au groupe et exposé une
    seule fois, jamais répété par entrée (design D9).
    """
    return {
        "key": view.key,
        "entries": [serialize_extraction_entry(entry) for entry in view.entries],
        "consignes_versions": to_json_value(view.consignes_versions),
        "consignes_diverge": view.consignes_diverge,
        "simulated": view.simulated,
        "cases": [serialize_case_row(case) for case in view.cases],
        "other_info": to_json_value(view.other_info),
        "source_text": to_json_value(view.source_text),
    }


def serialize_history_entry(view: HistoryEntry) -> dict[str, Any]:
    """Historique typé ; les clés audios_* de schema 1 restent pour les transcriptions."""
    return {
        "type": view.type,
        "identifiant": view.identifiant,
        "etat": to_json_value(view.etat),
        "libelle_etat": view.libelle_etat,
        "cree_le": to_json_value(view.cree_le),
        "modele": to_json_value(view.modele),
        "moteur": to_json_value(view.moteur),
        "audios_traites": (
            to_json_value(view.items_processed) if view.type == HISTORY_TYPE_TRANSCRIPTION else None
        ),
        "audios_total": (
            to_json_value(view.items_total) if view.type == HISTORY_TYPE_TRANSCRIPTION else None
        ),
        "items_processed": to_json_value(view.items_processed),
        "items_total": to_json_value(view.items_total),
        "duree_operation_s": to_json_value(view.duree_operation_s),
        "partiel": to_json_value(view.partiel),
        "marques": to_json_value(view.marques),
        "exploitable": view.exploitable,
        "motif": to_json_value(view.motif),
        "simule": _simulated(view.marques),
    }
