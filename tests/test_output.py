"""Tests de la couche de sortie (tâche 1.4) : texte, JSON `schema: 1`, UTF-8.

Couvre les instantanés des clés de chaque sérialiseur de vue (ordre compris),
les propriétés calculées (`simule`, `annotation_ram`, indicateurs, sélection),
la normalisation explicite des valeurs (non finis, chemins, énumérations, types
refusés), la règle « JSON seul sur la sortie standard », l'UTF-8 forcé sur un
flux à encodage local limité, la redirection réelle d'un sous-processus, et
l'option `--json` ajoutée aux commandes sans l'accepter sur `serve`.

Aucune commande métier n'est enregistrée ; les vues sont construites à la main.
Aucun moteur, aucun réseau, aucune donnée hors dossier temporaire.
"""

from __future__ import annotations

import argparse
import contextlib
import enum
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from engines.declarations import Reglage
from transcription_bench import cli, paths
from transcription_bench.compatibilite_modeles import RAISON_FICHIER_GGUF_NON_CHOISI
from transcription_bench.audios import AudioListe
from transcription_bench.command_session import CommandSpec
from transcription_bench.consultation_resultats import (
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
from transcription_bench.executions import DemandeExecution, ModelePropose, PreparationExecution, ReglageValide
from transcription_bench.execution_moteur import (
    AudioPrepare,
    ResultatAudio,
    ResultatExecution,
)
from transcription_bench.gestion_modeles import ModeleLocal
from transcription_bench.moteurs import EtatMoteur
from transcription_bench.operations import InstantaneCreneau
from transcription_bench.output import (
    OUTPUT_SCHEMA_VERSION,
    CommandOutput,
    add_json_option,
    configure_utf8_streams,
    json_line,
    output_from_arguments,
    serialize_audio_entry,
    serialize_audio_measures,
    serialize_audio_view,
    serialize_comparison,
    serialize_engine_state,
    serialize_execution_listing,
    serialize_hash_entry,
    serialize_hash_group,
    serialize_indicators,
    serialize_local_model,
    serialize_model_option,
    serialize_operation_state,
    serialize_pairs,
    serialize_preparation,
    serialize_run_detail,
    serialize_run_request,
    serialize_run_result,
    serialize_system_observation,
    serialize_transcription,
    serialize_verification_result,
    to_json_value,
    with_schema,
)
from transcription_bench.verification_modeles import FichierVerifie, ResultatVerification

RACINE_DEPOT = Path(__file__).resolve().parents[1]
EMPREINTE = "a" * 64
COMMIT = "b" * 40


def _observation(*, simulee: bool = False) -> ObservationSystemeVue:
    """Observation lisible, réelle ou simulée, avec CPU et mémoire consignés."""
    return ObservationSystemeVue(
        etat=None,
        cle_presente=True,
        provenance="simulee" if simulee else "reelle",
        version=1,
        methode_cpu="psutil",
        version_psutil="6.0.0",
        cpu=CpuSystemeVue(pourcentage_moyen=12.5, intervalle_s=2.0, motif=None),
        memoire_apres=MemoireSystemeVue(
            releve_le="2024-01-01T00:00:00+00:00",
            totale_octets=16,
            disponible_octets=8,
            motif=None,
        ),
    )


def _mesures_audio(*, rtf: float | None = 0.5) -> MesuresAudioVue:
    return MesuresAudioVue(
        temps_decodage_s=0.1,
        duree_transcription_s=2.0,
        temps_cpu_s=1.5,
        rtf=rtf,
        pic_memoire_octets=4,
    )


def _materiel() -> MaterielVue:
    return MaterielVue(
        os="Linux",
        version_os="6.1",
        architecture="x86_64",
        processeur="CPU",
        coeurs_physiques=4,
        coeurs_logiques=8,
        ram_totale_octets=16,
    )


def _transcription(*, marques: tuple[str, ...] = ()) -> TranscriptionVue:
    return TranscriptionVue(
        statut="ok",
        ecrit_le="2024-01-01T00:00:00+00:00",
        texte="Bonjour à tous",
        segments=(SegmentVue(debut_s=0.0, fin_s=1.0, texte="Bonjour"),),
        marques=marques,
        audio=(("Nom", "a.wav"),),
        empreinte_sha256=EMPREINTE,
        duree_indicative_s=2.0,
        duree_decodee_s=2.0,
        mesures=_mesures_audio(),
        timings_natifs=(
            TimingsNatifVue(unite="ms", chargement=1.0, mel=None, encodage=2.0, decodage=3.0),
        ),
        reglages=(("Threads", "4"),),
        reglages_bruts={"threads": 4},
        reglages_effectifs=(("Threads", "4"),),
        reglages_effectifs_bruts={"threads": 4},
        threads=(("Threads", "4"),),
        langue_imposee="fr",
        fenetre=(("Fenêtre", "30 s"),),
        modele=(("Modèle", "tiny"),),
        moteur=(("Moteur", "factice"),),
        famille="famille",
        erreur=None,
        observation_systeme=_observation(),
    )


def _execution_listee(marques: tuple[str, ...] | None = ()) -> ExecutionListee:
    return ExecutionListee(
        identifiant="20240101-000000-abc",
        etat="completed",
        libelle_etat="terminée",
        cree_le="2024-01-01T00:00:00+00:00",
        modele="tiny",
        moteur="factice",
        audios_traites=1,
        audios_total=1,
        duree_operation_s=2.5,
        partiel=False,
        marques=marques,
        exploitable=True,
        motif=None,
    )


def _audio_vue() -> AudioVue:
    return AudioVue(
        ordre=2,
        nom="a.wav",
        dossier="2-a",
        statut="ok",
        libelle_statut="transcrit",
        erreur=None,
        partiel=False,
        motif_indisponible=None,
        transcription=_transcription(),
        indicateurs=IndicateursAudio(duree_transcription_s=2.0, part_ram=0.25),
        annotation_ram="pic cumulatif",
        materiel_alerte=None,
        observation_systeme=_observation(),
    )


def _entree(*, ordre: int = 1, marques: tuple[str, ...] = ()) -> EntreeEmpreinte:
    return EntreeEmpreinte(
        execution="20240101-000000-abc",
        ordre=ordre,
        nom="a.wav",
        empreinte=EMPREINTE,
        statut="ok",
        libelle_statut="transcrit",
        libelle_etat="terminée",
        partiel=False,
        marques=marques,
        modele="tiny",
        moteur="factice",
        mesures=_mesures_audio(),
        materiel=_materiel(),
        date_essai="2024-01-01T00:00:00+00:00",
        etat="completed",
        reglages=(("Threads", "4"),),
        reglages_bruts={"threads": 4},
        reglages_distinctifs=(),
        variante=None,
        revision=COMMIT,
        duree_decodee_s=2.0,
        materiel_alerte=None,
        observation_systeme=_observation(),
        observation_chargement=ObservationSystemeVue(etat="absent"),
    )


def _reglage() -> Reglage:
    return Reglage(
        nom="temperature",
        libelle="Température",
        type_valeur="entier",
        defaut=0,
        description="Réglage de test.",
    )


def _modele_propose() -> ModelePropose:
    return ModelePropose(
        moteur="factice",
        nom_moteur="Moteur factice",
        cle="synthetique",
        identifiant="factice/synthetique",
        id_resolu="factice/synthetique",
        commit=COMMIT,
        famille="famille",
        libelle_famille="Famille",
        qualifiee=False,
        fichier_gguf=None,
        reglages=(_reglage(),),
        fenetre_fixe_secondes=30.0,
        synthetique=True,
    )


def _demande() -> DemandeExecution:
    return DemandeExecution(
        moteur="factice",
        cle="synthetique",
        identifiant="factice/synthetique",
        id_resolu="factice/synthetique",
        commit=COMMIT,
        famille="famille",
        fichier_gguf=None,
        audios=("a.wav", "b.wav"),
        threads=4,
        reglages=(ReglageValide(nom="temperature", valeur=0),),
        fenetre_fixe_secondes=30.0,
        synthetique=True,
    )


def _resultat_execution() -> ResultatExecution:
    prepare = AudioPrepare(
        index=1,
        nom="a.wav",
        fichier_brut="/chemin/interne/a.raw",
        format="wav",
        taille_octets=10,
        empreinte_sha256=EMPREINTE,
        duree_indicative=2.0,
        duree_decodee=2.0,
        echantillons=32000,
        temps_decodage=0.1,
    )
    audio = ResultatAudio(
        index=1,
        nom="a.wav",
        prepare=prepare,
        evenement={"type": "audio", "texte": "Bonjour"},
        erreur=None,
        factice=True,
        synthetique=True,
    )
    return ResultatExecution(
        etat="completed",
        factice=True,
        synthetique=True,
        moteur="factice",
        famille="famille",
        modele_identifiant="factice/synthetique",
        threads_demandes=4,
        audios=(audio,),
        evenements=({"type": "audio"},),
        lignes_parasites=0,
        journal_moteur=("ligne",),
        identifiant_resultat="20240101-000000-abc",
    )


class SerializerKeySnapshotTests(unittest.TestCase):
    """Instantanés des clés, dans l'ordre, de chaque sérialiseur de vue."""

    def assertKeys(self, data: dict, expected: list[str]) -> None:
        self.assertEqual(list(data.keys()), expected)

    def test_indicators_keys(self) -> None:
        self.assertKeys(
            serialize_indicators(IndicateursAudio()),
            [
                "duree_transcription_s",
                "pic_memoire_octets",
                "ram_totale_octets",
                "temps_cpu_s",
                "part_ram",
                "occupation_cpu",
            ],
        )

    def test_system_observation_keys_and_computed_flags(self) -> None:
        data = serialize_system_observation(_observation(simulee=True))
        self.assertKeys(
            data,
            [
                "etat",
                "lisible",
                "cle_presente",
                "ecarte_a_l_ecriture",
                "motif",
                "provenance",
                "simulee",
                "version",
                "methode_cpu",
                "version_psutil",
                "cpu",
                "memoire_apres",
            ],
        )
        self.assertTrue(data["lisible"])
        self.assertTrue(data["simulee"])
        self.assertEqual(data["cpu"]["pourcentage_moyen"], 12.5)
        self.assertEqual(data["memoire_apres"]["disponible_octets"], 8)

    def test_audio_measures_keys(self) -> None:
        self.assertKeys(
            serialize_audio_measures(_mesures_audio()),
            [
                "temps_decodage_s",
                "duree_transcription_s",
                "temps_cpu_s",
                "rtf",
                "pic_memoire_octets",
            ],
        )

    def test_transcription_keys_and_simulated_mark(self) -> None:
        data = serialize_transcription(_transcription(marques=("FACTICE",)))
        self.assertKeys(
            data,
            [
                "statut",
                "ecrit_le",
                "texte",
                "segments",
                "marques",
                "audio",
                "empreinte_sha256",
                "duree_indicative_s",
                "duree_decodee_s",
                "mesures",
                "timings_natifs",
                "reglages",
                "reglages_bruts",
                "reglages_effectifs",
                "reglages_effectifs_bruts",
                "threads",
                "langue_imposee",
                "fenetre",
                "modele",
                "moteur",
                "famille",
                "erreur",
                "observation_systeme",
                "simule",
            ],
        )
        self.assertTrue(data["simule"])
        self.assertEqual(data["audio"], [{"label": "Nom", "value": "a.wav"}])
        self.assertEqual(data["segments"][0]["debut_s"], 0.0)

    def test_audio_view_keys_and_computed_indicators(self) -> None:
        data = serialize_audio_view(_audio_vue())
        self.assertKeys(
            data,
            [
                "ordre",
                "nom",
                "dossier",
                "statut",
                "libelle_statut",
                "erreur",
                "partiel",
                "motif_indisponible",
                "transcription",
                "indicateurs",
                "annotation_ram",
                "materiel_alerte",
                "observation_systeme",
            ],
        )
        self.assertEqual(data["indicateurs"]["part_ram"], 0.25)
        self.assertEqual(data["annotation_ram"], "pic cumulatif")

    def test_run_detail_keys(self) -> None:
        detail = DetailExecutionVue(
            execution=_execution_listee(("FACTICE",)),
            fin=None,
            erreur=None,
            famille="famille",
            threads_demandes=4,
            threads_appliques=4,
            fenetre_fixe_s=30,
            reglages=(),
            reglages_effectifs=(),
            modele=(),
            moteur=(),
            versions_moteur=(),
            machine=(),
            programme=(),
            processus=(),
            mesures=MesuresVue(
                duree_operation_s=2.5,
                duree_processus_s=2.0,
                duree_chargement_s=0.5,
                pic_memoire_octets=None,
                pic_memoire_partiel=None,
            ),
            audios=(_audio_vue(),),
            partiel=False,
        )
        data = serialize_run_detail(detail)
        self.assertKeys(
            data,
            [
                "execution",
                "fin",
                "erreur",
                "famille",
                "threads_demandes",
                "threads_appliques",
                "fenetre_fixe_s",
                "reglages",
                "reglages_effectifs",
                "modele",
                "moteur",
                "versions_moteur",
                "machine",
                "programme",
                "processus",
                "mesures",
                "audios",
                "partiel",
                "libelle_modele",
                "simule",
            ],
        )
        self.assertTrue(data["simule"])
        self.assertIsNone(data["mesures"]["pic_memoire_octets"])
        self.assertEqual(data["mesures"]["observation_chargement"]["etat"], "absent")

    def test_execution_listing_keys_and_unreadable_marks_stay_null(self) -> None:
        data = serialize_execution_listing(_execution_listee(None))
        self.assertKeys(
            data,
            [
                "identifiant",
                "etat",
                "libelle_etat",
                "cree_le",
                "modele",
                "moteur",
                "audios_traites",
                "audios_total",
                "duree_operation_s",
                "partiel",
                "marques",
                "exploitable",
                "motif",
                "simule",
            ],
        )
        self.assertIsNone(data["marques"])
        self.assertIsNone(data["simule"])

    def test_hash_entry_keys_selection_and_annotation(self) -> None:
        data = serialize_hash_entry(_entree(ordre=2, marques=("MESURES SIMULÉES",)))
        self.assertKeys(
            data,
            [
                "execution",
                "ordre",
                "selection",
                "nom",
                "empreinte",
                "statut",
                "libelle_statut",
                "libelle_etat",
                "etat",
                "partiel",
                "marques",
                "modele",
                "moteur",
                "mesures",
                "materiel",
                "date_essai",
                "reglages",
                "reglages_bruts",
                "reglages_distinctifs",
                "variante",
                "revision",
                "duree_decodee_s",
                "materiel_alerte",
                "observation_systeme",
                "observation_chargement",
                "indicateurs",
                "annotation_ram",
                "simule",
            ],
        )
        self.assertEqual(data["selection"], "20240101-000000-abc:2")
        self.assertTrue(data["simule"])
        self.assertIsNotNone(data["annotation_ram"])
        self.assertIsNone(serialize_hash_entry(_entree(ordre=1))["annotation_ram"])

    def test_hash_group_keys_split_real_and_simulated(self) -> None:
        groupe = GroupeEmpreinte(
            empreinte=EMPREINTE,
            noms=("a.wav",),
            entrees=(_entree(ordre=1), _entree(ordre=2, marques=("FACTICE",))),
        )
        data = serialize_hash_group(groupe)
        self.assertKeys(
            data,
            [
                "empreinte",
                "noms",
                "duree_decodee_commune_s",
                "durees_divergentes",
                "entrees_reelles",
                "entrees_simulees",
            ],
        )
        self.assertEqual([e["selection"] for e in data["entrees_reelles"]], ["20240101-000000-abc:1"])
        self.assertEqual([e["selection"] for e in data["entrees_simulees"]], ["20240101-000000-abc:2"])

    def test_comparison_keys_card_and_line_cells(self) -> None:
        entree = _entree(ordre=1)
        carte = CarteComparaison(
            entree=entree,
            libelle="tiny",
            texte="Bonjour",
            duree_transcription_s=2.0,
            pic_memoire_octets=4,
            ram_totale_octets=16,
            temps_cpu_s=1.5,
            part_ram=0.25,
            occupation_cpu=0.4,
            annotation_ram=None,
        )
        comparaison = ComparaisonVue(
            empreinte=EMPREINTE,
            noms=("a.wav",),
            colonnes=(entree,),
            lignes=(
                LigneComparaison(
                    libelle="Texte",
                    nature="texte",
                    cellules=(CelluleComparaison(presente=True, valeur="Bonjour", brut="Bonjour"),),
                    differents=False,
                ),
            ),
            factice=False,
            partiel=False,
            cartes=(carte,),
            synthese=SyntheseComparaison(plus_rapides=("tiny",)),
        )
        data = serialize_comparison(comparaison)
        self.assertKeys(
            data,
            [
                "empreinte",
                "noms",
                "colonnes",
                "lignes",
                "factice",
                "partiel",
                "cartes",
                "synthese",
            ],
        )
        self.assertKeys(
            data["cartes"][0],
            [
                "selection",
                "libelle",
                "texte",
                "indicateurs",
                "annotation_ram",
                "materiel_alerte",
                "erreur",
                "partiel",
                "simule",
            ],
        )
        self.assertKeys(data["lignes"][0], ["libelle", "nature", "cellules", "differents"])
        self.assertKeys(data["lignes"][0]["cellules"][0], ["presente", "valeur", "brut"])
        self.assertEqual(data["cartes"][0]["selection"], "20240101-000000-abc:1")
        self.assertEqual(data["synthese"], {"plus_rapides": ["tiny"], "moins_de_ram": [], "exclues": []})

    def test_model_option_keys_with_reference_and_settings(self) -> None:
        data = serialize_model_option(_modele_propose())
        self.assertKeys(
            data,
            [
                "reference",
                "moteur",
                "nom_moteur",
                "cle",
                "identifiant",
                "id_resolu",
                "commit",
                "famille",
                "libelle_famille",
                "qualifiee",
                "fichier_gguf",
                "reglages",
                "fenetre_fixe_secondes",
                "executable",
                "motif_non_executable",
                "synthetique",
            ],
        )
        self.assertEqual(data["reference"], "factice/synthetique")
        self.assertKeys(
            data["reglages"][0],
            ["nom", "libelle", "type_valeur", "defaut", "description", "valeurs"],
        )

    def test_local_model_keys_and_absent_size_stays_null(self) -> None:
        modele = ModeleLocal(
            moteur="factice",
            cle="synthetique",
            identifiant="factice/synthetique",
            id_resolu="factice/synthetique",
            commit=COMMIT,
            famille="famille",
            fichier_gguf=None,
            fichiers=(FichierVerifie(nom="modele.bin", taille=None),),
            taille_disque=None,
            date="2024-01-01",
        )
        data = serialize_local_model(modele)
        self.assertEqual(data["reference"], "factice/synthetique")
        self.assertKeys(
            data,
            [
                "reference",
                "moteur",
                "cle",
                "identifiant",
                "id_resolu",
                "commit",
                "famille",
                "fichier_gguf",
                "fichiers",
                "taille_disque",
                "taille_distante",
                "date",
            ],
        )
        self.assertIsNone(data["taille_distante"])
        self.assertIsNone(data["fichiers"][0]["taille"])

    def test_preparation_keeps_defaults_and_notices(self) -> None:
        model = _modele_propose()
        setting = model.reglages[0]
        view = PreparationExecution(
            modele=model, moteur=model.moteur, audios=("a.wav",),
            notice="Sélection actualisée", threads=3,
            reglages=((setting, setting.defaut),), reinitialisation="Défauts rétablis",
        )
        data = serialize_preparation(view)
        self.assertKeys(data, [
            "modele", "moteur", "audios", "notice", "threads", "reglages",
            "reinitialisation", "applicable", "reference",
        ])
        self.assertEqual(data["threads"], 3)
        self.assertEqual(data["notice"], view.notice)
        self.assertEqual(data["reinitialisation"], view.reinitialisation)
        self.assertEqual(data["reference"], model.reference)
        self.assertTrue(data["applicable"])
        self.assertEqual(data["reglages"][0]["valeur"], setting.defaut)

    def test_verification_result_keys_keep_refusal_reason(self) -> None:
        resultat = ResultatVerification(
            accepte=False,
            identifiant="depot/modele",
            moteur="transcribe.cpp",
            famille=None,
            commit=None,
            raison=RAISON_FICHIER_GGUF_NON_CHOISI,
            message="Plusieurs fichiers GGUF.",
            gguf_candidats=("a.gguf", "b.gguf"),
        )
        data = serialize_verification_result(resultat)
        self.assertKeys(
            data,
            [
                "accepte",
                "identifiant",
                "moteur",
                "famille",
                "commit",
                "id_resolu",
                "fichiers",
                "taille_totale",
                "gguf_candidats",
                "fichier_gguf",
                "raison",
                "message",
                "fichiers_manquants",
                "moteur_suggere",
            ],
        )
        self.assertEqual(data["raison"], "fichier-gguf-non-choisi")
        self.assertEqual(data["gguf_candidats"], ["a.gguf", "b.gguf"])

    def test_engine_state_keys_and_versions_as_objects(self) -> None:
        etat = EtatMoteur(
            identifiant="factice",
            nom="Moteur factice",
            etat="pret",
            factice=True,
            versions=(("module", None),),
        )
        data = serialize_engine_state(etat)
        self.assertKeys(
            data,
            [
                "identifiant",
                "nom",
                "etat",
                "factice",
                "installable",
                "note",
                "date_installation",
                "versions",
            ],
        )
        self.assertEqual(data["versions"], [{"module": "module", "version": None}])

    def test_audio_entry_keys_and_readable_flag(self) -> None:
        ok = serialize_audio_entry(AudioListe(nom="a.wav", format="wav", taille_octets=3, duree_indicative=None))
        ko = serialize_audio_entry(
            AudioListe(nom="b.wav", format="wav", taille_octets=3, duree_indicative=None, erreur="illisible")
        )
        self.assertKeys(ok, ["nom", "format", "taille_octets", "duree_indicative", "erreur", "readable"])
        self.assertTrue(ok["readable"])
        self.assertFalse(ko["readable"])

    def test_operation_state_keys_keep_full_journal(self) -> None:
        instantane = InstantaneCreneau(
            etat="terminee",
            arrete=False,
            type_operation="installation",
            cible="factice",
            debut="2024-01-01T00:00:00+00:00",
            fin="2024-01-01T00:00:01+00:00",
            erreur=None,
            journal=("un", "deux"),
            generation=3,
        )
        data = serialize_operation_state(instantane)
        self.assertKeys(
            data,
            [
                "etat",
                "arrete",
                "type_operation",
                "cible",
                "debut",
                "fin",
                "erreur",
                "journal",
                "generation",
            ],
        )
        self.assertEqual(data["journal"], ["un", "deux"])

    def test_run_request_keys_and_reference(self) -> None:
        data = serialize_run_request(_demande())
        self.assertKeys(
            data,
            [
                "reference",
                "moteur",
                "cle",
                "identifiant",
                "id_resolu",
                "commit",
                "famille",
                "fichier_gguf",
                "audios",
                "threads",
                "reglages",
                "fenetre_fixe_secondes",
                "synthetique",
            ],
        )
        self.assertEqual(data["audios"], ["a.wav", "b.wav"])
        self.assertEqual(data["reglages"], [{"nom": "temperature", "valeur": 0}])

    def test_run_result_keys_omit_internal_paths_and_raw_events(self) -> None:
        data = serialize_run_result(_resultat_execution())
        self.assertKeys(
            data,
            [
                "etat",
                "factice",
                "synthetique",
                "moteur",
                "famille",
                "modele_identifiant",
                "threads_demandes",
                "audios",
                "lignes_parasites",
                "journal_moteur",
                "erreur",
                "code_sortie",
                "pid",
                "arret_demande",
                "identifiant_resultat",
                "duree_operation_s",
                "duree_processus_s",
                "audios_en_erreur",
                "audios_non_traites",
            ],
        )
        audio = data["audios"][0]
        self.assertKeys(
            audio,
            ["index", "nom", "prepare", "evenement", "erreur", "factice", "synthetique", "non_traite"],
        )
        self.assertKeys(
            audio["prepare"],
            [
                "index",
                "nom",
                "format",
                "taille_octets",
                "empreinte_sha256",
                "duree_indicative",
                "duree_decodee",
                "echantillons",
                "temps_decodage",
            ],
        )
        self.assertNotIn("fichier_brut", json.dumps(data))
        self.assertFalse(audio["non_traite"])


class NormalisationTests(unittest.TestCase):
    """Normalisation explicite des valeurs : rien d'inventé, rien d'aveugle."""

    def test_non_finite_numbers_become_null_never_zero(self) -> None:
        mesures = serialize_audio_measures(_mesures_audio(rtf=float("nan")))
        self.assertIsNone(mesures["rtf"])
        self.assertIsNone(to_json_value(float("inf")))
        self.assertIsNone(to_json_value(float("-inf")))
        self.assertEqual(serialize_pairs((("Borne", float("nan")),)), [{"label": "Borne", "value": None}])

    def test_absent_measures_stay_null(self) -> None:
        self.assertIsNone(serialize_audio_measures(None))
        self.assertIsNone(serialize_transcription(None))

    def test_special_types_are_converted_explicitly(self) -> None:
        class Couleur(enum.Enum):
            VERT = "vert"

        converti = to_json_value(
            {"chemin": Path("data") / "x", "liste": (1, 2.5, True), Couleur.VERT: Couleur.VERT}
        )
        self.assertEqual(converti, {"chemin": str(Path("data") / "x"), "liste": [1, 2.5, True], "Couleur.VERT": "vert"})

    def test_unknown_type_is_refused_instead_of_guessed(self) -> None:
        with self.assertRaises(TypeError):
            to_json_value(object())

    def test_schema_is_first_and_cannot_be_overridden(self) -> None:
        objet = with_schema({"zeta": 1, "alpha": "é"})
        self.assertEqual(list(objet.keys()), ["schema", "zeta", "alpha"])
        self.assertEqual(objet["schema"], OUTPUT_SCHEMA_VERSION)
        with self.assertRaises(ValueError):
            with_schema({"schema": 2})


class CommandOutputTests(unittest.TestCase):
    """Sortie texte ou JSON, et règle « rien d'autre sur la sortie standard »."""

    def test_json_line_is_one_complete_object_with_accents(self) -> None:
        ligne = json_line({"texte": "Élève « ça » 中文"})
        self.assertNotIn("\n", ligne)
        self.assertIn("Élève", ligne)
        self.assertEqual(json.loads(ligne), {"schema": 1, "texte": "Élève « ça » 中文"})

    def test_json_mode_writes_only_the_object_on_stdout(self) -> None:
        sortie, erreur = io.StringIO(), io.StringIO()
        commande = CommandOutput(json_mode=True, stdout=sortie, stderr=erreur)
        commande.result({"valeur": 1}, text_lines=("texte ignoré",))
        commande.diagnostic("message")

        self.assertEqual(json.loads(sortie.getvalue()), {"schema": 1, "valeur": 1})
        self.assertEqual(sortie.getvalue().count("\n"), 1)
        self.assertNotIn("texte ignoré", sortie.getvalue())
        self.assertEqual(erreur.getvalue(), "transcription-bench : message\n")

    def test_text_mode_writes_lines_and_no_json(self) -> None:
        sortie, erreur = io.StringIO(), io.StringIO()
        commande = CommandOutput(json_mode=False, stdout=sortie, stderr=erreur)
        commande.result({"valeur": 1}, text_lines=("première ligne", "deuxième"))

        self.assertEqual(sortie.getvalue(), "première ligne\ndeuxième\n")
        self.assertEqual(erreur.getvalue(), "")

    def test_output_from_arguments_reads_json_option(self) -> None:
        sortie = io.StringIO()
        arguments = type("Arguments", (), {"json": True})()
        output_from_arguments(arguments, stdout=sortie).result({"a": 1})
        self.assertEqual(json.loads(sortie.getvalue())["schema"], 1)
        self.assertFalse(output_from_arguments(object(), stdout=io.StringIO()).json_mode)


class Utf8StreamTests(unittest.TestCase):
    """UTF-8 forcé sur un flux à encodage local limité, sans échec d'écriture."""

    def test_limited_local_encoding_is_replaced_by_utf8(self) -> None:
        flux = io.TextIOWrapper(io.BytesIO(), encoding="ascii")
        configure_utf8_streams(flux)
        flux.write("Élève 中文\n")
        flux.flush()
        self.assertEqual(flux.buffer.getvalue().decode("utf-8"), "Élève 中文\n")

    def test_unencodable_surrogate_stays_valid_json(self) -> None:
        flux = io.TextIOWrapper(io.BytesIO(), encoding="ascii")
        configure_utf8_streams(flux)
        commande = CommandOutput(json_mode=True, stdout=flux, stderr=io.StringIO())
        commande.result({"texte": "x\ud800y"})
        flux.flush()
        objet = json.loads(flux.buffer.getvalue().decode("utf-8"))
        self.assertEqual(objet["texte"], "x\ud800y")

    def test_streams_without_reconfigure_are_left_untouched(self) -> None:
        configure_utf8_streams(io.StringIO(), None)

    def test_redirected_subprocess_writes_utf8_under_ascii_locale(self) -> None:
        code = (
            "import sys, tempfile\n"
            "from pathlib import Path\n"
            "from transcription_bench import cli, paths\n"
            "from transcription_bench.command_session import CommandSpec\n"
            "from transcription_bench.output import output_from_arguments\n"
            "def run(args, services, drapeau):\n"
            "    output = output_from_arguments(args)\n"
            "    output.result({'texte': 'Élève 中文 😀'})\n"
            "    output.diagnostic('é 中文')\n"
            "    return 0\n"
            "with tempfile.TemporaryDirectory() as folder:\n"
            "    paths.DOSSIER_DATA = Path(folder) / 'data'\n"
            "    command = CommandSpec('probe', 'Sonde', lambda parser: None, run)\n"
            "    raise SystemExit(cli.main(['probe', '--json'], commands=(command,)))\n"
        )
        env = {**os.environ, "PYTHONIOENCODING": "ascii", "PYTHONUTF8": "0"}
        with tempfile.TemporaryDirectory() as dossier:
            sortie = Path(dossier) / "sortie.json"
            erreur = Path(dossier) / "erreur.txt"
            with sortie.open("wb") as flux_sortie, erreur.open("wb") as flux_erreur:
                resultat = subprocess.run(
                    [sys.executable, "-c", code],
                    stdout=flux_sortie,
                    stderr=flux_erreur,
                    env=env,
                    cwd=RACINE_DEPOT,
                    timeout=60,
                    check=False,
                )
            self.assertEqual(resultat.returncode, 0)
            objet = json.loads(sortie.read_bytes().decode("utf-8"))
            self.assertEqual(objet, {"schema": 1, "texte": "Élève 中文 😀"})
            self.assertEqual(erreur.read_bytes().decode("utf-8"), "transcription-bench : é 中文\n")


class JsonOptionTests(unittest.TestCase):
    """`--json` existe sur les commandes et jamais sur `serve`."""

    def _commande(self) -> CommandSpec:
        return CommandSpec(
            name="essai",
            help_text="commande de test",
            configure=lambda analyseur: analyseur.add_argument("--valeur"),
            run=lambda arguments, services, drapeau: 0,
        )

    def test_json_option_is_accepted_by_commands_only(self) -> None:
        analyseur = cli.construire_analyseur((self._commande(),))
        self.assertTrue(analyseur.parse_args(["essai", "--json"]).json)
        self.assertFalse(analyseur.parse_args(["essai"]).json)
        with self.assertRaises(SystemExit) as fin, contextlib.redirect_stderr(io.StringIO()):
            analyseur.parse_args(["serve", "--json"])
        self.assertEqual(fin.exception.code, 2)

    def test_json_option_helper_registers_store_true(self) -> None:
        analyseur = argparse.ArgumentParser()
        add_json_option(analyseur)
        self.assertTrue(analyseur.parse_args(["--json"]).json)

    def test_command_json_output_reaches_stdout_only_through_main(self) -> None:
        def action(arguments, services, drapeau):
            commande = output_from_arguments(arguments)
            commande.result({"valeur": arguments.valeur})
            return 0

        spec = CommandSpec(
            name="essai",
            help_text="commande de test",
            configure=lambda analyseur: analyseur.add_argument("--valeur", default="7"),
            run=action,
        )
        with tempfile.TemporaryDirectory() as dossier:
            sortie, erreur = io.StringIO(), io.StringIO()
            with (
                mock.patch.object(paths, "DOSSIER_DATA", Path(dossier)),
                contextlib.redirect_stdout(sortie),
                contextlib.redirect_stderr(erreur),
            ):
                code = cli.main(
                    ["essai", "--json"],
                    commands=(spec,),
                    recuperer=lambda _dossier: None,
                )
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(sortie.getvalue()), {"schema": 1, "valeur": "7"})
        self.assertEqual(erreur.getvalue(), "")


if __name__ == "__main__":
    unittest.main()
