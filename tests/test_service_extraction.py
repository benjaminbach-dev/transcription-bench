"""Tests du service serveur d'extraction (tâche 3.4, design D5 à D8).

Les résultats de transcription sont écrits par le vrai écrivain de la tâche 6.4
(`ConsignateurExecution`). Les extractions passent par le vrai service, le
créneau réel et le vrai runner d'extraction dans un sous-processus. Le moteur est
le factice, sauf pour les scénarios d'erreur : une enveloppe de test installe
l'adaptateur de test du runner à la place du factice (erreur de contexte, sortie
non conforme, échec de grammaire, blocage pour l'arrêt). L'interruption brutale
est un vrai processus tué entre deux écritures. Aucun moteur réel, aucun poids,
aucun réseau, aucune écriture sous le `data/` du dépôt : tout est temporaire.
"""

from __future__ import annotations

import contextlib
import dataclasses
import io
import json
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from collections.abc import Callable
from pathlib import Path
from typing import Any
from unittest import mock

import psutil

from engines.declarations import DECLARATION_LLAMA_CPP
from engines.hors_ligne import extraction_runner_command
from engines.protocole import TYPE_AUDIO, analyser_ligne, formater_ligne
from engines.registre import RegistreMoteurs, creer_registre_fourni
from transcription_bench.consignes_grilles import (
    SOURCE_END_MARKER,
    VERSION_CONSIGNES,
    system_message,
)
from transcription_bench import resultats_extraction
from transcription_bench.execution_extraction import (
    MOTIF_DOSSIER_CONSERVE,
    PREFIXE_DOSSIER_TRAVAIL,
    ExtractionExecution,
    ExtractionResult,
    evaluate_extraction_outcome,
    line_rejection_reason,
)
from transcription_bench.execution_launch import (
    EngineNotReady,
    ExecutionAlreadyReserved,
    launch_extraction,
)
from transcription_bench.execution_moteur import (
    ARRET_DEMANDE,
    LONGUEUR_LIGNE_STDERR_MAX,
    AudioPrepare,
    ResultatAudio,
    ResultatExecution,
)
from transcription_bench.executions import (
    CLE_MODELE_FACTICE,
    CLE_MODELE_FACTICE_EXTRACTION,
    DemandeExecution,
)
from transcription_bench.extractions import ExtractionConfiguration
from transcription_bench.gestion_modeles import ModeleLocal
from transcription_bench.grilles import read_grid
from transcription_bench.moteurs import InstallationMoteurs
from transcription_bench.operations import (
    TYPE_VERIFICATION,
    CreneauOccupe,
    CreneauOperations,
    horodatage_iso,
)
from transcription_bench.paths import RACINE_PROJET, ValeurRefusee
from transcription_bench.recuperation import (
    MOTIF_RACINE_EXTRACTIONS_LIEE,
    EtatAnterieurNonTraitable,
    recuperer_executions_anterieures,
)
from transcription_bench.resultats import (
    ETAT_ABANDONNEE,
    ETAT_EN_COURS,
    ConsignateurExecution,
    metadonnees_moteur,
)
from transcription_bench.resultats_extraction import (
    SOURCE_COMPLIANT,
    SOURCE_ERROR,
    SOURCE_NON_COMPLIANT,
    SOURCE_NOT_PROCESSED,
    ExtractionRecorder,
    ResultatImmuable,
    abandon_extraction,
)
from transcription_bench.schema_grilles import grid_schema
from transcription_bench.stockage import ecrire_texte_atomique

MACHINE = {"os": "Linux", "coeurs_physiques": 4, "ram_totale_octets": 1024}
PROGRAMME = {"nom": "transcription-bench", "version": "0.1.0", "python": "3.12.0"}
MOTEUR_FACTICE = metadonnees_moteur("factice", "Moteur factice", factice=True)
MOTEUR_REEL = metadonnees_moteur("faster-whisper", "faster-whisper", factice=False)
BASE_STAMP = "20260101-120000"
DELAY = 60.0
POLL_STEP = 0.02
#: Référence du modèle d'extraction du moteur factice (aucun fichier réel).
EXTRACTION_MODEL_REF = f"factice/{CLE_MODELE_FACTICE_EXTRACTION}"
#: Référence d'un modèle de transcription : refusée à l'extraction.
TRANSCRIPTION_MODEL_REF = f"factice/{CLE_MODELE_FACTICE}"
GRID_SAMPLE = """# Grille d'essai

Consignes : n'extraire que ce qui est dit pendant la consultation.

## Motif de consultation ?

## Symptômes déclarés ?
Liste.
"""
TEXT_A = "Le patient tousse depuis trois jours. MARQUEUR_SOURCE_A"
TEXT_F = "Douleur au genou gauche depuis une semaine. MARQUEUR_SOURCE_F"
TEXT_R = "Fièvre à 38,5 degrés. MARQUEUR_SOURCE_R"
SOURCE_MARKERS = ("MARQUEUR_SOURCE_A", "MARQUEUR_SOURCE_F", "MARQUEUR_SOURCE_R")

#: Gabarit d'une enveloppe : avant le vrai `main`, le sous-processus installe un
#: comportement de test à la place du factice.
WRAPPER_TEMPLATE = """
import json
import sys
import time

sys.path.insert(0, {racine})

import engines.adaptateurs.factice as factice
from engines.runner_extraction import main
from tests import adaptateur_extraction_de_test as adaptateur

{corps}

raise SystemExit(main([sys.argv[1]]))
"""

#: Corps d'enveloppe qui relie le factice à l'adaptateur de test, avec un scénario.
ADAPTER_BODY = """
factice.charger = adaptateur.charger
factice.reinitialiser = adaptateur.reinitialiser
factice.extraire = adaptateur.extraire
"""

#: Processus du serveur qui meurt au moment où le marqueur de la source 2 est
#: écrit : sa sortie brute existe déjà, son `result.json` n'existe pas encore.
INTERRUPTION_CODE = """
import os
import sys

sys.path.insert(0, {racine!r})

from engines.registre import creer_registre_fourni
from transcription_bench import resultats_extraction
from transcription_bench.execution_extraction import ExtractionExecution
from transcription_bench.execution_launch import launch_extraction
from transcription_bench.extractions import ExtractionConfiguration
from transcription_bench.moteurs import InstallationMoteurs
from transcription_bench.operations import CreneauOperations

_ecrire = resultats_extraction.ecrire_json_atomique


def ecrire(chemin, contenu):
    if chemin.name == "result.json" and contenu.get("rang") == 2:
        os._exit(7)
    return _ecrire(chemin, contenu)


resultats_extraction.ecrire_json_atomique = ecrire
registre = creer_registre_fourni()
creneau = CreneauOperations()
configuration = ExtractionConfiguration({donnees!r}, registre, lambda: (), racine_grilles={grilles!r})
execution = ExtractionExecution({donnees!r}, registre, InstallationMoteurs({donnees!r}, registre, creneau))
launch_extraction(configuration, execution, creneau, modele={modele!r}, grille="essai", sources={sources!r})
creneau.attendre_thread(60)
sys.exit(0)
"""

#: Métadonnées de chargement conformes (`meta_moteur`), valeurs fictives.
META_MOTEUR = {
    "threads_appliques": 4,
    "mode_chargement_poids": "mmap",
    "architecture": "mistral3",
    "sha256_gabarit_embarque": "d" * 64,
    "version_format": 1,
    "decodage": "glouton",
    "graine": None,
}
#: Comptes natifs conformes d'une source terminée.
COMPTES_NATIFS = {"tokens_lecture": 812, "tokens_generation": 24}
#: Clés de `consignes.json` à l'admission, puis après le chargement.
CLES_CONSIGNES_ADMISSION = {"version_consignes", "message_systeme"}

_attempts = [0]


def _short_id() -> str:
    """Identifiant court distinct à chaque consignation de test."""
    _attempts[0] += 1
    return f"{_attempts[0]:08x}"


def _audio_prepare(index: int, nom: str) -> AudioPrepare:
    return AudioPrepare(
        index=index,
        nom=nom,
        fichier_brut=f"audio-{index}.f32",
        format="wav",
        taille_octets=100,
        empreinte_sha256=f"{index + 1:x}" * 64,
        duree_indicative=2.0,
        duree_decodee=2.0,
        echantillons=32000,
        temps_decodage=0.25,
    )


def write_transcription_run(
    donnees: Path,
    audios: list[tuple[str, str | None, str]],
    *,
    factice: bool = True,
) -> str:
    """Écrit une exécution de transcription réelle ; renvoie son identifiant.

    Chaque audio est `(nom, texte, état)` avec `état` valant `ok`, `erreur` ou
    `non_traite` ; le texte n'est utilisé que pour un audio `ok`.
    """
    demande = DemandeExecution(
        moteur="factice" if factice else "faster-whisper",
        cle="0" * 64,
        identifiant="modele de test",
        id_resolu="modele de test",
        commit="aucun",
        famille="factice" if factice else "modele",
        fichier_gguf=None,
        audios=tuple(nom for nom, _, _ in audios),
        threads=2,
        reglages=(),
        fenetre_fixe_secondes=30.0,
        synthetique=factice,
    )
    consignateur = ConsignateurExecution(
        donnees,
        demande,
        MOTEUR_FACTICE if factice else MOTEUR_REEL,
        debut=time.perf_counter(),
        machine=MACHINE,
        programme=PROGRAMME,
        base=BASE_STAMP,
        court_id=_short_id(),
    )
    if not consignateur.ouvrir():
        raise AssertionError(consignateur.erreur)
    resultats: list[ResultatAudio] = []
    evenements: list[dict[str, Any]] = []
    for index, (nom, texte, etat) in enumerate(audios):
        evenement: dict[str, Any] | None = None
        erreur: str | None = None
        prepare: AudioPrepare | None = _audio_prepare(index, nom)
        if etat == "ok":
            evenement = {
                "type": TYPE_AUDIO,
                "index": index,
                "nom": nom,
                "texte": texte,
                "segments": [],
                "duree_audio_s": 2.0,
                "duree_transcription_s": 1.0,
                "temps_cpu_s": 1.0,
                "rtf": 0.5,
                "fenetre_s": 30.0,
                "decoupage": "fenetres-fixes",
                "nb_fenetres": 1,
                "pic_memoire_octets": 4096,
                "reglages_effectifs": {},
                "langue_imposee": None,
                "threads_demandes": 2,
                "threads_appliques": None,
                "factice": factice,
                "mesures_simulees": factice,
            }
            evenements.append(evenement)
        elif etat == "erreur":
            erreur = "moteur : échec simulé"
        else:
            prepare = None
        resultat = ResultatAudio(
            index=index,
            nom=nom,
            prepare=prepare,
            evenement=evenement,
            erreur=erreur,
            factice=factice,
            synthetique=factice,
        )
        resultats.append(resultat)
        if not consignateur.enregistrer_audio(resultat):
            raise AssertionError(consignateur.erreur)
    consignateur.clore(
        ResultatExecution(
            etat="terminee",
            factice=factice,
            synthetique=factice,
            moteur=demande.moteur,
            famille=demande.famille,
            modele_identifiant=demande.identifiant,
            threads_demandes=2,
            audios=tuple(resultats),
            evenements=tuple(evenements),
            lignes_parasites=0,
            journal_moteur=(),
        )
    )
    consignateur.fermer()
    if consignateur.erreur is not None:
        raise AssertionError(consignateur.erreur)
    return str(consignateur.identifiant)


def loading_event() -> dict[str, Any]:
    """Événement `chargement` synthétique, de provenance factice."""
    return {
        "type": "chargement",
        "duree_s": 0.5,
        "pic_memoire_octets": 1000,
        "factice": True,
        "mesures_simulees": True,
    }


def source_event(index: int, nom: str, *, conforme: bool = True) -> dict[str, Any]:
    """Événement `extraction` synthétique, complet et de provenance factice."""
    return {
        "type": "extraction",
        "index": index,
        "nom": nom,
        "conforme": conforme,
        "motif": None if conforme else "clé inconnue de la grille",
        "valeur": {"motif_de_consultation": None} if conforme else None,
        "sortie_brute": '{"motif_de_consultation": null}',
        "tokens_entree": 812,
        "tokens_sortie": 9,
        "delai_premier_token_s": 1.25,
        "duree_generation_s": 0.5,
        "duree_extraction_s": 2.0,
        "vitesse_generation_tps": 16.0,
        "vitesse_lecture_estimee_tps": 649.6,
        "temps_cpu_s": 2.6,
        "pic_memoire_octets": 2000,
        "fin": "arret",
        "factice": True,
        "mesures_simulees": True,
    }


def out_of_scope_audio_line() -> str:
    """Événement `audio` valide au protocole de transcription, hors tâche d'extraction."""
    champs: dict[str, Any] = {
        "type": TYPE_AUDIO,
        "index": 0,
        "nom": "consultation-a.wav",
        "texte": "MARQUEUR_AUDIO_9001",
    }
    for champ in (
        "segments",
        "duree_audio_s",
        "duree_transcription_s",
        "temps_cpu_s",
        "rtf",
        "fenetre_s",
        "decoupage",
        "nb_fenetres",
        "pic_memoire_octets",
        "reglages_effectifs",
        "langue_imposee",
        "threads_demandes",
        "threads_appliques",
    ):
        champs[champ] = None
    champs.update({"factice": True, "mesures_simulees": True})
    return formater_ligne(champs).rstrip("\n")


def invalid_extraction_line() -> str:
    """Événement `extraction` incomplet : refusé par le protocole strict."""
    return formater_ligne(
        {
            "type": "extraction",
            "index": 0,
            "nom": "consultation-a.wav",
            "valeur": "MARQUEUR_VALEUR_8123",
            "factice": True,
            "mesures_simulees": True,
        }
    ).rstrip("\n")


def _kill(enfant: subprocess.Popen[bytes]) -> None:
    """Filet de sécurité : aucun témoin ne survit au test."""
    if enfant.poll() is None:
        enfant.kill()
        enfant.wait()


class ExtractionBench(unittest.TestCase):
    """Dossiers temporaires, registre réel et services réels, sans moteur réel."""

    def setUp(self) -> None:
        temporaire = tempfile.TemporaryDirectory()
        self.addCleanup(temporaire.cleanup)
        racine = Path(temporaire.name).resolve()
        self.donnees = racine / "data"
        self.projet = racine / "projet"
        (self.projet / "grilles").mkdir(parents=True)
        (self.projet / "grilles" / "essai.md").write_text(GRID_SAMPLE, encoding="utf-8")
        self.dossier = racine / "essais"
        self.dossier.mkdir()
        self.registre = creer_registre_fourni()
        self.creneau = CreneauOperations()
        self.moteurs = InstallationMoteurs(self.donnees, self.registre, self.creneau)
        self.configuration = ExtractionConfiguration(
            self.donnees, self.registre, lambda: (), racine_grilles=self.projet
        )
        self.enveloppes = 0
        # Transcriptions réelles écrites par le vrai écrivain de la tâche 6.4.
        self.identifiant_a = write_transcription_run(
            self.donnees,
            [
                ("consultation-a.wav", TEXT_A, "ok"),
                ("consultation-b.wav", None, "erreur"),
                ("consultation-c.wav", None, "non_traite"),
                ("consultation-d.wav", "", "ok"),
                ("consultation-e.wav", "Texte avec " + SOURCE_END_MARKER, "ok"),
                ("consultation-f.wav", TEXT_F, "ok"),
            ],
        )
        self.identifiant_r = write_transcription_run(
            self.donnees,
            [("consultation-r.wav", TEXT_R, "ok")],
            factice=False,
        )
        #: Lot de trois sources distinctes, dont une d'une transcription réelle.
        self.lot = [
            f"{self.identifiant_a}:1",
            f"{self.identifiant_a}:6",
            f"{self.identifiant_r}:1",
        ]

    # -- outillage ---------------------------------------------------------

    def request_for(self, sources: list[str], **options: Any) -> Any:
        """Demande validée par le vrai service de validation."""
        return self.configuration.valider(
            modele=EXTRACTION_MODEL_REF, grille="essai", sources=sources, **options
        )

    def make_execution(
        self, construire: Callable[[Any, Any], list[str]] | None = None
    ) -> ExtractionExecution:
        return ExtractionExecution(
            self.donnees,
            self.registre,
            self.moteurs,
            construire_commande=construire or extraction_runner_command,
        )

    def run_extraction(
        self,
        sources: list[str],
        *,
        construire: Callable[[Any, Any], list[str]] | None = None,
        reglages: dict[str, str] | None = None,
    ) -> ExtractionResult:
        """Lance une extraction réelle, attend sa fin et renvoie son issue."""
        execution = self.make_execution(construire)
        launch_extraction(
            self.configuration,
            execution,
            self.creneau,
            modele=EXTRACTION_MODEL_REF,
            grille="essai",
            sources=sources,
            reglages=reglages,
        )
        self.assertTrue(self.creneau.attendre_thread(DELAY))
        resultat = execution.derniere_execution()
        self.assertIsNotNone(resultat)
        assert resultat is not None
        return resultat

    def wrapper_command(self, corps: str) -> Callable[[Any, Any], list[str]]:
        """Commande dont le runner exécute `corps` avant le vrai `main`."""
        self.enveloppes += 1
        chemin = self.dossier / f"enveloppe-{self.enveloppes}.py"
        chemin.write_text(
            WRAPPER_TEMPLATE.format(racine=repr(str(RACINE_PROJET)), corps=corps),
            encoding="utf-8",
        )

        def construire(interpreteur: Any, job: Any) -> list[str]:
            return [str(interpreteur), str(chemin), str(job)]

        return construire

    def folder_of(self, resultat: ExtractionResult) -> Path:
        assert resultat.identifiant_resultat is not None
        return self.donnees / "extractions" / resultat.identifiant_resultat

    def extraction_folders(self) -> list[Path]:
        racine = self.donnees / "extractions"
        if not racine.is_dir():
            return []
        return sorted(chemin for chemin in racine.iterdir() if chemin.is_dir())

    def read_json(self, chemin: Path) -> Any:
        return json.loads(chemin.read_text(encoding="utf-8"))

    def read_run(self, dossier: Path) -> dict[str, Any]:
        return self.read_json(dossier / "run.json")

    def source_plan(self, dossier: Path, rang: int) -> dict[str, Any]:
        """Plan d'une source dans `run.json` (rang 1-based)."""
        return self.read_run(dossier)["sources"][rang - 1]

    def source_folder(self, dossier: Path, rang: int) -> Path:
        return dossier / self.source_plan(dossier, rang)["dossier"]

    def snapshot(self, dossier: Path) -> dict[str, bytes]:
        """Instantané octet pour octet de tous les fichiers d'une extraction."""
        return {
            str(chemin.relative_to(dossier)): chemin.read_bytes()
            for chemin in sorted(dossier.rglob("*"))
            if chemin.is_file()
        }

    def wait_until(self, condition: Callable[[], bool]) -> None:
        """Attend une condition observable, sans durée supposée."""
        echeance = time.monotonic() + DELAY
        while time.monotonic() < echeance:
            if condition():
                return
            time.sleep(POLL_STEP)
        self.fail("condition non atteinte dans le délai")


class ExtractionValidationTest(ExtractionBench):
    """Validation de la demande : refus nommés, sans réservation ni écriture."""

    def test_valid_batch_keeps_provenance_and_defaults(self) -> None:
        demande = self.request_for([f"{self.identifiant_a}:1", f"{self.identifiant_r}:1"])
        self.assertEqual([source.rang for source in demande.sources], [1, 2])
        premiere = demande.sources[0]
        self.assertEqual(premiere.identifiant, self.identifiant_a)
        self.assertEqual(premiere.ordre, 1)
        self.assertEqual(premiere.nom, "consultation-a.wav")
        self.assertEqual(premiere.texte, TEXT_A)
        self.assertTrue(premiere.factice)
        self.assertEqual(premiere.moteur, "factice")
        self.assertEqual(len(premiere.empreinte_texte), 64)
        # La famille factice d'extraction ne déclare aucun réglage (tâche 2.1) :
        # les défauts `contexte` et `sortie_max` sont vérifiés plus bas, sur la
        # déclaration llama.cpp.
        self.assertEqual(demande.reglages, ())
        self.assertGreaterEqual(demande.threads, 1)
        self.assertTrue(demande.synthetique)
        self.assertEqual(demande.grille.version_consignes, VERSION_CONSIGNES)
        self.assertEqual(demande.grille.schema["required"][-1], "autres_informations")
        self.assertFalse(demande.sources[1].factice)
        self.assertEqual(demande.sources[1].moteur, "faster-whisper")

    def test_source_text_absent_from_representations(self) -> None:
        demande = self.request_for([f"{self.identifiant_a}:1"])
        self.assertNotIn("MARQUEUR_SOURCE_A", repr(demande))
        self.assertNotIn("MARQUEUR_SOURCE_A", repr(demande.sources[0]))

    def test_error_or_unprocessed_source_refused_by_name(self) -> None:
        for reference, motif in (
            (f"{self.identifiant_a}:2", "en erreur"),
            (f"{self.identifiant_a}:3", "non traité"),
        ):
            with self.subTest(reference=reference):
                with self.assertRaises(ValeurRefusee) as contexte:
                    self.request_for([reference])
                self.assertIn(repr(reference), str(contexte.exception))
                self.assertIn(motif, str(contexte.exception))

    def test_empty_or_marked_source_refused_without_crash(self) -> None:
        with self.assertRaisesRegex(ValeurRefusee, "texte transcrit vide"):
            self.request_for([f"{self.identifiant_a}:4"])
        with self.assertRaises(ValeurRefusee) as contexte:
            self.request_for([f"{self.identifiant_a}:5"])
        self.assertIn("marqueur", str(contexte.exception))
        self.assertIn(repr(f"{self.identifiant_a}:5"), str(contexte.exception))

    def test_missing_source_refused_by_name(self) -> None:
        for reference in (f"{self.identifiant_a}:9", "20260101-000000-deadbeef:1"):
            with self.subTest(reference=reference):
                with self.assertRaises(ValeurRefusee) as contexte:
                    self.request_for([reference])
                self.assertIn(repr(reference), str(contexte.exception))

    def test_malformed_source_and_outgoing_identifier_refused(self) -> None:
        for reference in (self.identifiant_a, "../evil:1", "a:b", f"{self.identifiant_a}:0"):
            with self.subTest(reference=reference):
                with self.assertRaises(ValeurRefusee):
                    self.request_for([reference])

    def test_duplicate_and_empty_source_list_refused(self) -> None:
        with self.assertRaisesRegex(ValeurRefusee, "en double"):
            self.request_for([f"{self.identifiant_a}:1", f"{self.identifiant_a}:1"])
        with self.assertRaisesRegex(ValeurRefusee, "aucune source"):
            self.request_for([])

    def test_duplicate_source_in_two_writings_refused(self) -> None:
        # `:1` et `:01` désignent le même ordre : le doublon porte sur le couple
        # normalisé (identifiant, ordre), pas sur l'écriture brute reçue.
        premiere = f"{self.identifiant_a}:1"
        seconde = f"{self.identifiant_a}:01"
        with self.assertRaises(ValeurRefusee) as contexte:
            self.request_for([premiere, seconde])
        message = str(contexte.exception)
        self.assertIn("source en double", message)
        self.assertIn(repr(premiere), message)
        self.assertIn(repr(seconde), message)
        self.assertNotIn("MARQUEUR_SOURCE_A", message)

    def test_transcription_model_refused_for_extraction(self) -> None:
        with self.assertRaisesRegex(ValeurRefusee, "modèle de transcription"):
            self.configuration.valider(
                modele=TRANSCRIPTION_MODEL_REF,
                grille="essai",
                sources=[f"{self.identifiant_a}:1"],
            )

    def test_engine_inconsistent_with_reference_refused(self) -> None:
        with self.assertRaisesRegex(ValeurRefusee, "moteur incompatible"):
            self.request_for([f"{self.identifiant_a}:1"], moteur="faster-whisper")

    def test_invalid_grid_refused_with_reason(self) -> None:
        (self.projet / "grilles" / "sans-titre.md").write_text(
            "## Motif de consultation ?\n", encoding="utf-8"
        )
        with self.assertRaises(ValeurRefusee) as contexte:
            self.configuration.valider(
                modele=EXTRACTION_MODEL_REF,
                grille="sans-titre",
                sources=[f"{self.identifiant_a}:1"],
            )
        self.assertIn("grille invalide (sans-titre)", str(contexte.exception))
        self.assertIn("titre", str(contexte.exception))

    def test_unknown_or_invalid_grid_name_refused(self) -> None:
        with self.assertRaisesRegex(ValeurRefusee, "grille inconnue"):
            self.configuration.valider(
                modele=EXTRACTION_MODEL_REF, grille="absente", sources=[f"{self.identifiant_a}:1"]
            )
        with self.assertRaisesRegex(ValeurRefusee, "nom non conforme"):
            self.configuration.valider(
                modele=EXTRACTION_MODEL_REF, grille="../essai", sources=[f"{self.identifiant_a}:1"]
            )

    def test_settings_and_threads(self) -> None:
        with self.assertRaisesRegex(ValeurRefusee, "réglage non déclaré"):
            self.request_for([f"{self.identifiant_a}:1"], reglages={"contexte": "1"})
        with self.assertRaisesRegex(ValeurRefusee, "threads"):
            self.request_for([f"{self.identifiant_a}:1"], threads="0")
        demande = self.request_for([f"{self.identifiant_a}:1"], threads="3")
        self.assertEqual(demande.threads, 3)

    def test_llama_cpp_family_setting_defaults(self) -> None:
        """`contexte` et `sortie_max` : défauts de la déclaration llama.cpp (D4)."""
        famille = dataclasses.replace(DECLARATION_LLAMA_CPP.familles[0], qualifiee=True)
        registre = RegistreMoteurs()
        registre.enregistrer(dataclasses.replace(DECLARATION_LLAMA_CPP, familles=(famille,)))
        modele = ModeleLocal(
            moteur="llama-cpp",
            cle="a" * 64,
            identifiant="org/modele",
            id_resolu="org/modele",
            commit="c" * 40,
            famille="llm-gguf",
            fichier_gguf="modele.gguf",
            fichiers=(),
            taille_disque=None,
            date="2026-01-01",
        )
        configuration = ExtractionConfiguration(
            self.donnees, registre, lambda: (modele,), racine_grilles=self.projet
        )
        proposition = configuration.modeles_proposables()[0]
        self.assertEqual(
            [(reglage.nom, reglage.defaut) for reglage in proposition.reglages],
            [("contexte", 16384), ("sortie_max", 4096)],
        )
        with self.assertRaisesRegex(ValeurRefusee, "réglage 'contexte' invalide"):
            configuration.valider(
                modele=f"llama-cpp/{'a' * 64}",
                grille="essai",
                sources=[f"{self.identifiant_a}:1"],
                reglages={"contexte": "beaucoup"},
            )
        demande = configuration.valider(
            modele=f"llama-cpp/{'a' * 64}",
            grille="essai",
            sources=[f"{self.identifiant_a}:1"],
            reglages={"sortie_max": "512"},
        )
        self.assertEqual(demande.reglage("contexte"), 16384)
        self.assertEqual(demande.reglage("sortie_max"), 512)

    def test_validation_has_no_side_effect(self) -> None:
        self.request_for([f"{self.identifiant_a}:1"])
        self.assertFalse((self.donnees / "extractions").exists())
        self.assertEqual(self.creneau.instantane().etat, "libre")

    def test_source_refused_if_run_or_result_is_outgoing_symlink(self) -> None:
        # Contre-revue : les fichiers lus d'une exécution source sont confinés.
        # Un lien symbolique posé sur `result.json` ou `run.json` et pointant
        # hors du dossier autorisé fait refuser la source SANS lire la cible —
        # ici une copie pourtant valide du vrai fichier, que la lecture aurait
        # acceptée.
        identifiant = self.identifiant_a
        dossier = self.donnees / "results" / identifiant
        plan = self.read_json(dossier / "run.json")["audios"][0]
        chemin_resultat = dossier / plan["dossier"] / "result.json"
        cible_resultat = self.donnees.parent / "resultat-exterieur.json"
        cible_resultat.write_bytes(chemin_resultat.read_bytes())
        chemin_resultat.unlink()
        chemin_resultat.symlink_to(cible_resultat)
        with self.assertRaises(ValeurRefusee) as contexte:
            self.request_for([f"{identifiant}:1"])
        message = str(contexte.exception)
        self.assertIn("résultat de l'audio hors du dossier autorisé", message)
        self.assertIn(repr(f"{identifiant}:1"), message)
        self.assertNotIn("MARQUEUR_SOURCE_A", message)

        chemin_run = dossier / "run.json"
        cible_run = self.donnees.parent / "run-exterieur.json"
        cible_run.write_bytes(chemin_run.read_bytes())
        chemin_run.unlink()
        chemin_run.symlink_to(cible_run)
        with self.assertRaises(ValeurRefusee) as contexte:
            self.request_for([f"{identifiant}:6"])
        message = str(contexte.exception)
        self.assertIn("exécution de transcription hors du dossier autorisé", message)
        self.assertNotIn("MARQUEUR_SOURCE_F", message)


class EventFilterTest(unittest.TestCase):
    """Filtrage pur des lignes du moteur et issue d'une extraction."""

    def test_out_of_scope_type_and_content_never_copied(self) -> None:
        ligne = out_of_scope_audio_line()
        self.assertEqual(
            line_rejection_reason(
                ligne,
                analyser_ligne(ligne),
                factice=True,
                noms_sources=["consultation-a.wav"],
                vus=set(),
                chargement_recu=True,
                fin_recue=False,
            ),
            "type hors tâche d'extraction : audio",
        )
        invalide = invalid_extraction_line()
        self.assertEqual(
            line_rejection_reason(
                invalide,
                analyser_ligne(invalide),
                factice=True,
                noms_sources=["consultation-a.wav"],
                vus=set(),
                chargement_recu=True,
                fin_recue=False,
            ),
            "événement extraction non conforme au protocole",
        )
        self.assertEqual(
            line_rejection_reason(
                "MARQUEUR_HORS_PROTOCOLE_77",
                None,
                factice=True,
                noms_sources=[],
                vus=set(),
                chargement_recu=False,
                fin_recue=False,
            ),
            "sortie hors protocole",
        )

    def test_bare_marker_line_masked_without_copy(self) -> None:
        # Contre-revue : une ligne qui commence par le marqueur nu
        # `##TB-EVENT##`, sans l'espace de séparation, n'est pas un événement
        # analysable, mais elle reste une ligne d'événement : le motif rendu
        # est fixe et ne recopie jamais son contenu.
        ligne = '##TB-EVENT##{"nom": "SENTINELLE-FUITE"}'
        self.assertIsNone(analyser_ligne(ligne))
        motif = line_rejection_reason(
            ligne,
            analyser_ligne(ligne),
            factice=True,
            noms_sources=["consultation-a.wav"],
            vus=set(),
            chargement_recu=True,
            fin_recue=False,
        )
        self.assertEqual(motif, "type d'événement inconnu")
        self.assertNotIn("SENTINELLE-FUITE", motif or "")

    def test_deeply_nested_line_ignored_without_exception(self) -> None:
        # Contre-revue : un JSON imbriqué au-delà de la limite de récursion du
        # décodeur lève `RecursionError` — la ligne est ignorée proprement,
        # motif fixe, jamais une exception.
        ligne = "##TB-EVENT## " + "[" * 100_000 + "]" * 100_000
        self.assertIsNone(analyser_ligne(ligne))
        self.assertEqual(
            line_rejection_reason(
                ligne,
                None,
                factice=True,
                noms_sources=[],
                vus=set(),
                chargement_recu=False,
                fin_recue=False,
            ),
            "événement illisible (JSON invalide)",
        )

    def test_event_before_loading_and_unknown_source_refused(self) -> None:
        self.assertEqual(
            line_rejection_reason(
                "x",
                source_event(0, "consultation-a.wav"),
                factice=True,
                noms_sources=["consultation-a.wav"],
                vus=set(),
                chargement_recu=False,
                fin_recue=False,
            ),
            "extraction reçu avant le chargement",
        )
        self.assertEqual(
            line_rejection_reason(
                "x",
                source_event(3, "consultation-a.wav"),
                factice=True,
                noms_sources=["consultation-a.wav"],
                vus=set(),
                chargement_recu=True,
                fin_recue=False,
            ),
            "index de source hors de l'extraction",
        )

    def test_outcome_missing_loading_end_and_stop(self) -> None:
        self.assertEqual(
            evaluate_extraction_outcome(
                code_sortie=3,
                arret_demande=False,
                evenements=[],
                nombre_sources=2,
                motif_moteur="moteur indisponible : chargement impossible",
            ),
            ("echouee", "moteur indisponible : chargement impossible"),
        )
        etat, motif = evaluate_extraction_outcome(
            code_sortie=0,
            arret_demande=False,
            evenements=[loading_event(), source_event(0, "a.wav")],
            nombre_sources=2,
            motif_moteur=None,
        )
        self.assertEqual(etat, "echouee")
        self.assertIn("fin absent", motif or "")
        etat, _ = evaluate_extraction_outcome(
            code_sortie=0,
            arret_demande=True,
            evenements=[],
            nombre_sources=2,
            motif_moteur=None,
        )
        self.assertEqual(etat, "interrompue")

    def test_extraction_runner_command(self) -> None:
        commande = extraction_runner_command("python-x", "job.json")
        self.assertEqual(Path(commande[1]).name, "runner_extraction.py")
        self.assertEqual(commande[0], "python-x")


class ExtractionRunTest(ExtractionBench):
    """Exécutions réelles : runner en sous-processus, créneau et stockage réels."""

    def test_three_source_batch_complete_folder(self) -> None:
        resultat = self.run_extraction(self.lot)
        self.assertEqual(resultat.etat, "terminee")
        self.assertIsNone(resultat.erreur)
        self.assertEqual(resultat.summary["conformes"], 3)
        # Purge réussie : aucun reste à signaler sur la ligne de résultat.
        self.assertFalse(resultat.dossier_travail_conserve)
        dossier = self.folder_of(resultat)
        run = self.read_run(dossier)
        self.assertEqual(run["schema"], 1)
        self.assertEqual(run["type"], "extraction")
        self.assertEqual(run["etat"], "completed")
        self.assertTrue(run["factice"])
        self.assertEqual(run["progression"], {"sources_traitees": 3, "sources_total": 3})
        self.assertEqual(run["grille"]["nom"], "essai")
        self.assertEqual(run["consignes"]["version_consignes"], VERSION_CONSIGNES)
        self.assertEqual(run["demande"]["sources"], self.lot)
        self.assertEqual(run["moteur"]["identifiant"], "factice")
        self.assertIsNone(run["effectifs"]["threads_appliques"])
        self.assertIsNone(run["effectifs"]["mode_chargement_poids"])
        measures = run["mesures"]
        self.assertIsNotNone(measures["duree_chargement_s"])
        self.assertIsNotNone(measures["duree_processus_s"])
        self.assertIsNotNone(measures["duree_operation_s"])
        self.assertIsNotNone(measures["pic_memoire_octets"])
        self.assertIs(measures["pic_memoire_partiel"], False)
        self.assertIsNotNone(measures["observation_systeme_chargement"])
        self.assertEqual(
            [plan["dossier"] for plan in run["sources"]],
            ["1-consultation-a.wav", "2-consultation-f.wav", "3-consultation-r.wav"],
        )
        self.assertEqual([plan["etat"] for plan in run["sources"]], [SOURCE_COMPLIANT] * 3)
        premiere = self.source_plan(dossier, 1)
        self.assertEqual(premiere["source"]["execution"], self.identifiant_a)
        self.assertEqual(premiere["source"]["ordre"], 1)
        self.assertTrue(premiere["source"]["factice"])
        self.assertIsNotNone(premiere["mesures"]["tokens_entree"])
        self.assertEqual(self.source_plan(dossier, 3)["source"]["moteur"], "faster-whisper")
        self.assertFalse(self.source_plan(dossier, 3)["source"]["factice"])
        for rang in (1, 2, 3):
            source_dir = self.source_folder(dossier, rang)
            for nom in ("source.txt", "sortie_brute.txt", "extraction.json", "result.json"):
                self.assertTrue((source_dir / nom).is_file(), f"{nom} source {rang}")
        self.assertEqual(
            (self.source_folder(dossier, 1) / "source.txt").read_text(encoding="utf-8"),
            TEXT_A,
        )
        valeur = self.read_json(self.source_folder(dossier, 1) / "extraction.json")["valeur"]
        self.assertTrue(valeur["motif_de_consultation"].startswith("[FACTICE]"))
        self.assertEqual(self.extraction_folders(), [dossier])

    def test_result_identifier_published_only_for_admitted_operation(self) -> None:
        execution = self.make_execution()
        launch_extraction(
            self.configuration,
            execution,
            self.creneau,
            modele=EXTRACTION_MODEL_REF,
            grille="essai",
            sources=self.lot,
        )
        self.assertTrue(self.creneau.attendre_thread(DELAY))
        resultat = execution.derniere_execution()
        assert resultat is not None and resultat.identifiant_resultat is not None
        generation = self.creneau.instantane().generation
        self.assertEqual(
            execution.identifiant_resultat(generation), resultat.identifiant_resultat
        )
        self.assertIsNone(execution.identifiant_resultat(generation + 1))
        self.assertIsNone(execution.identifiant_resultat(None))
        self.assertEqual(self.read_run(self.folder_of(resultat))["modele"]["architecture"], None)

    def test_grid_schema_and_instructions_copied_exactly(self) -> None:
        resultat = self.run_extraction(self.lot)
        dossier = self.folder_of(resultat)
        self.assertEqual(
            (dossier / "grille.md").read_bytes(),
            (self.projet / "grilles" / "essai.md").read_bytes(),
        )
        self.assertEqual(
            self.read_json(dossier / "schema.json"),
            grid_schema(read_grid("essai", self.projet)),
        )
        consignes = self.read_json(dossier / "consignes.json")
        self.assertEqual(consignes["version_consignes"], VERSION_CONSIGNES)
        self.assertEqual(
            consignes["message_systeme"],
            system_message(read_grid("essai", self.projet)).text,
        )

    def test_source_in_error_insufficient_context(self) -> None:
        construire = self.wrapper_command(
            "adaptateur.configurer(scenario=[{'tokens_entree': 16000}])\n"
            + ADAPTER_BODY
        )
        resultat = self.run_extraction(self.lot, construire=construire)
        self.assertEqual(resultat.etat, "terminee")
        dossier = self.folder_of(resultat)
        erreur = self.source_plan(dossier, 1)
        self.assertEqual(erreur["etat"], SOURCE_ERROR)
        self.assertIn("contexte insuffisant", erreur["motif"])
        self.assertIn("16000", erreur["motif"])
        self.assertIsNone(erreur["mesures"]["tokens_entree"])
        self.assertEqual(self.source_plan(dossier, 2)["etat"], SOURCE_COMPLIANT)
        source_dir = self.source_folder(dossier, 1)
        self.assertTrue((source_dir / "source.txt").is_file())
        self.assertFalse((source_dir / "sortie_brute.txt").exists())
        self.assertFalse((source_dir / "extraction.json").exists())
        self.assertTrue((source_dir / "result.json").is_file())

    def test_non_compliant_source_keeps_raw_output_without_value(self) -> None:
        brut = {
            "sortie_brute": '{"inconnue": "MARQUEUR_SORTIE_4411"}',
            "tokens_entree": 800,
            "tokens_sortie": 9,
            "fin": "arret",
            "delai_premier_token_s": 1.0,
            "duree_generation_s": 1.0,
            "temps_cpu_s": 1.0,
        }
        construire = self.wrapper_command(
            f"adaptateur.configurer(scenario=[{{'brut': {brut!r}}}])\n" + ADAPTER_BODY
        )
        resultat = self.run_extraction(self.lot, construire=construire)
        dossier = self.folder_of(resultat)
        plan = self.source_plan(dossier, 1)
        self.assertEqual(plan["etat"], SOURCE_NON_COMPLIANT)
        # Première non-conformité dans l'ordre fixe du schéma : la clé attendue manque.
        self.assertEqual(plan["motif"], "clé de la grille absente ($.motif_de_consultation)")
        source_dir = self.source_folder(dossier, 1)
        self.assertEqual(
            (source_dir / "sortie_brute.txt").read_text(encoding="utf-8"),
            brut["sortie_brute"],
        )
        self.assertFalse((source_dir / "extraction.json").exists())
        self.assertEqual(self.source_plan(dossier, 2)["etat"], SOURCE_COMPLIANT)
        self.assertEqual(resultat.etat, "terminee")
        self.assertNotIn("MARQUEUR_SORTIE_4411", (dossier / "run.log").read_text(encoding="utf-8"))

    def test_grammar_failure_without_generation_or_publication(self) -> None:
        construire = self.wrapper_command(
            "adaptateur.configurer(echec_charger='grammaire refusée (schéma)')\n"
            + ADAPTER_BODY
        )
        resultat = self.run_extraction(self.lot, construire=construire)
        self.assertEqual(resultat.etat, "echouee")
        self.assertIn("chargement du modèle impossible", resultat.erreur or "")
        dossier = self.folder_of(resultat)
        run = self.read_run(dossier)
        self.assertEqual(run["etat"], "failed")
        self.assertEqual([plan["etat"] for plan in run["sources"]], [SOURCE_NOT_PROCESSED] * 3)
        self.assertEqual(list(dossier.rglob("result.json")), [])
        self.assertEqual(list(dossier.rglob("sortie_brute.txt")), [])
        self.assertIn(
            "chargement du modèle impossible",
            (dossier / "run.log").read_text(encoding="utf-8"),
        )

    def test_stop_after_first_source(self) -> None:
        marque = self.dossier / "bloque.txt"
        construire = self.wrapper_command(
            f"""
_original = factice.extraire
_appels = [0]


def extraire(moteur, messages, reglages):
    _appels[0] += 1
    if _appels[0] == 2:
        with open({str(marque)!r}, "w", encoding="utf-8") as fichier:
            fichier.write("bloque")
        time.sleep(60)
    return _original(moteur, messages, reglages)


factice.extraire = extraire
"""
        )
        execution = self.make_execution(construire)
        launch_extraction(
            self.configuration,
            execution,
            self.creneau,
            modele=EXTRACTION_MODEL_REF,
            grille="essai",
            sources=self.lot,
        )
        # Arrêt observé après la publication de la première source, comme l'utilisateur.
        self.wait_until(
            lambda: marque.exists() and any(self.donnees.glob("extractions/*/1-*/result.json"))
        )
        self.assertEqual(execution.arreter_execution(), ARRET_DEMANDE)
        self.assertTrue(self.creneau.attendre_thread(DELAY))
        resultat = execution.derniere_execution()
        assert resultat is not None
        self.assertEqual(resultat.etat, "interrompue")
        self.assertEqual(self.creneau.instantane().etat, "interrompue")
        dossier = self.folder_of(resultat)
        run = self.read_run(dossier)
        self.assertEqual(run["etat"], "interrupted")
        self.assertEqual(self.source_plan(dossier, 1)["etat"], SOURCE_COMPLIANT)
        self.assertEqual(self.source_plan(dossier, 2)["etat"], SOURCE_NOT_PROCESSED)
        self.assertEqual(self.source_plan(dossier, 3)["etat"], SOURCE_NOT_PROCESSED)
        self.assertFalse((self.source_folder(dossier, 2) / "result.json").exists())
        self.assertEqual(
            (self.source_folder(dossier, 2) / "source.txt").read_text(encoding="utf-8"),
            TEXT_F,
        )
        self.assertEqual(list(self.donnees.glob("cache/execution-*")), [])

    def test_out_of_scope_or_invalid_engine_lines_without_leak(self) -> None:
        lignes = [
            out_of_scope_audio_line(),
            invalid_extraction_line(),
            "MARQUEUR_HORS_PROTOCOLE_77 texte libre",
        ]
        construire = self.wrapper_command(
            f"""
_original = factice.extraire
_lignes = {lignes!r}


def extraire(moteur, messages, reglages):
    for ligne in _lignes:
        sys.stdout.write(ligne + "\\n")
    sys.stdout.flush()
    return _original(moteur, messages, reglages)


factice.extraire = extraire
"""
        )
        resultat = self.run_extraction([f"{self.identifiant_a}:1"], construire=construire)
        self.assertEqual(resultat.etat, "terminee")
        dossier = self.folder_of(resultat)
        journal = (dossier / "run.log").read_text(encoding="utf-8")
        self.assertIn("type hors tâche d'extraction : audio", journal)
        self.assertIn("événement extraction non conforme au protocole", journal)
        self.assertIn("sortie hors protocole", journal)
        contenus = json.dumps(self.read_run(dossier), ensure_ascii=False) + journal
        for marqueur in ("MARQUEUR_AUDIO_9001", "MARQUEUR_VALEUR_8123", "MARQUEUR_HORS_PROTOCOLE_77"):
            self.assertNotIn(marqueur, contenus)
        self.assertEqual(self.read_run(dossier)["progression"]["sources_traitees"], 1)
        self.assertEqual(self.source_plan(dossier, 1)["etat"], SOURCE_COMPLIANT)

    def test_invalid_event_lines_with_sentinel_never_leak(self) -> None:
        # Contre-revue : une ligne d'événement invalide portant une sentinelle
        # (JSON tronqué, événement incomplet, entier démesuré) n'est jamais
        # recopiée — ni dans run.log, ni au journal de l'opération.
        lignes = [
            '##TB-EVENT## {"type": "extraction", "nom": "SENTINELLE-FUITE", "tru',
            '##TB-EVENT## {"type": "extraction", "index": 0,'
            ' "nom": "SENTINELLE-FUITE", "conforme": false}',
            '##TB-EVENT## {"type": "chargement", "duree_s": ' + "9" * 5000 + "}",
            # Marqueur nu, sans l'espace de séparation : pas un événement
            # analysable, mais une ligne d'événement — masquée, jamais recopiée.
            '##TB-EVENT##{"nom": "SENTINELLE-FUITE"}',
        ]
        construire = self.wrapper_command(
            f"""
_original = factice.extraire
_lignes = {lignes!r}


def extraire(moteur, messages, reglages):
    for ligne in _lignes:
        sys.stdout.write(ligne + "\\n")
    sys.stdout.flush()
    return _original(moteur, messages, reglages)


factice.extraire = extraire
"""
        )
        resultat = self.run_extraction(
            [f"{self.identifiant_a}:1"], construire=construire
        )

        self.assertEqual(resultat.etat, "terminee")
        dossier = self.folder_of(resultat)
        journal = (dossier / "run.log").read_text(encoding="utf-8")
        self.assertIn("événement illisible (JSON invalide)", journal)
        self.assertIn("événement extraction non conforme au protocole", journal)
        self.assertIn("type d'événement inconnu", journal)
        contenus = (
            journal
            + json.dumps(self.read_run(dossier), ensure_ascii=False)
            + "\n".join(self.creneau.instantane().journal)
        )
        self.assertNotIn("SENTINELLE-FUITE", contenus)
        self.assertEqual(self.source_plan(dossier, 1)["etat"], SOURCE_COMPLIANT)

    def test_log_and_publications_without_source_text_or_output(self) -> None:
        resultat = self.run_extraction(self.lot)
        dossier = self.folder_of(resultat)
        textes = [
            (dossier / "run.log").read_text(encoding="utf-8"),
            json.dumps(self.read_run(dossier), ensure_ascii=False),
        ]
        for nom in ("result.json", "extraction.json"):
            textes += [chemin.read_text(encoding="utf-8") for chemin in dossier.rglob(nom)]
        for texte in textes:
            for marqueur in SOURCE_MARKERS:
                self.assertNotIn(marqueur, texte)
        # Positif : le texte source n'existe que dans les copies `source.txt`.
        copies = [chemin.read_text(encoding="utf-8") for chemin in dossier.rglob("source.txt")]
        self.assertEqual(len(copies), 3)
        self.assertIn(TEXT_A, copies)

    def test_source_copies_written_at_admission(self) -> None:
        construire = self.wrapper_command(
            "adaptateur.configurer(echec_charger='grammaire refusée')\n" + ADAPTER_BODY
        )
        resultat = self.run_extraction(self.lot, construire=construire)
        dossier = self.folder_of(resultat)
        self.assertEqual(
            (self.source_folder(dossier, 1) / "source.txt").read_text(encoding="utf-8"),
            TEXT_A,
        )
        self.assertEqual(
            (self.source_folder(dossier, 3) / "source.txt").read_text(encoding="utf-8"),
            TEXT_R,
        )
        # Le texte est une copie : il survit à la disparition des transcriptions.
        shutil.rmtree(self.donnees / "results")
        self.assertEqual(
            (self.source_folder(dossier, 1) / "source.txt").read_text(encoding="utf-8"),
            TEXT_A,
        )

    def test_source_copy_survives_deletion_of_published_result(self) -> None:
        resultat = self.run_extraction(self.lot)
        dossier = self.folder_of(resultat)
        source_dir = self.source_folder(dossier, 1)
        (source_dir / "result.json").unlink()
        self.assertEqual((source_dir / "source.txt").read_text(encoding="utf-8"), TEXT_A)

    def test_immutability_and_rerun_without_overwrite(self) -> None:
        premiere = self.run_extraction(self.lot)
        dossier = self.folder_of(premiere)
        avant = self.snapshot(dossier)
        seconde = self.run_extraction(self.lot)
        self.assertNotEqual(self.folder_of(seconde), dossier)
        self.assertEqual(self.snapshot(dossier), avant)
        self.assertEqual(len(self.extraction_folders()), 2)

    def test_published_result_never_rewritten_and_final_run_immutable(self) -> None:
        consignateur = ExtractionRecorder(
            self.donnees,
            self.request_for(self.lot),
            MOTEUR_FACTICE,
            debut=time.perf_counter(),
            machine=MACHINE,
            programme=PROGRAMME,
            base=BASE_STAMP,
            court_id=_short_id(),
        )
        self.assertTrue(consignateur.ouvrir(), consignateur.erreur)
        self.assertTrue(consignateur.record_event(loading_event()))
        self.assertTrue(consignateur.record_event(source_event(0, "consultation-a.wav")))
        self.assertFalse(consignateur.record_event(source_event(0, "consultation-a.wav")))
        self.assertTrue(consignateur.clore(etat="terminee", erreur=None, code_sortie=0))
        with self.assertRaises(ResultatImmuable):
            consignateur.record_event(loading_event())
        with self.assertRaises(ResultatImmuable):
            consignateur.clore(etat="terminee", erreur=None, code_sortie=0)
        assert consignateur.dossier is not None
        with self.assertRaises(ValueError):
            abandon_extraction(consignateur.dossier, self.read_run(consignateur.dossier))

    def test_echec_de_copie_source_clot_l_extraction_sans_dossier_orphelin(
        self,
    ) -> None:
        ecritures_source: list[bool] = []

        def ecrire_sauf_source(chemin: Path, contenu: str) -> None:
            if chemin.name == "source.txt":
                # `run.json` doit déjà exister : le dossier a un état avant les copies.
                ecritures_source.append((chemin.parent.parent / "run.json").is_file())
                raise OSError(28, "espace insuffisant sur le périphérique")
            ecrire_texte_atomique(chemin, contenu)

        consignateur = ExtractionRecorder(
            self.donnees,
            self.request_for(self.lot),
            MOTEUR_FACTICE,
            debut=time.perf_counter(),
            machine=MACHINE,
            programme=PROGRAMME,
            base=BASE_STAMP,
            court_id=_short_id(),
        )
        with mock.patch(
            "transcription_bench.resultats_extraction.ecrire_texte_atomique",
            side_effect=ecrire_sauf_source,
        ):
            self.assertFalse(consignateur.ouvrir())

        self.assertEqual(ecritures_source, [True])
        self.assertIn("espace insuffisant", consignateur.erreur or "")
        assert consignateur.dossier is not None
        run = self.read_run(consignateur.dossier)
        self.assertEqual(run["etat"], "failed")
        self.assertIn("espace insuffisant", run["erreur"])
        # Aucun dossier d'extraction n'est orphelin : chacun porte un `run.json`.
        dossiers = self.extraction_folders()
        self.assertEqual(len(dossiers), 1)
        self.assertTrue(all((d / "run.json").is_file() for d in dossiers))

    def test_dossier_de_travail_non_supprime_journalise_sans_chemin(self) -> None:
        suppression_reelle = shutil.rmtree

        def rmtree_sauf_travail(chemin: Any, *args: Any, **kwargs: Any) -> None:
            # Simule un échec de suppression du dossier de travail (job, textes).
            if Path(chemin).name.startswith(PREFIXE_DOSSIER_TRAVAIL):
                return None
            return suppression_reelle(chemin, *args, **kwargs)

        with mock.patch(
            "transcription_bench.execution_extraction.shutil.rmtree",
            side_effect=rmtree_sauf_travail,
        ):
            resultat = self.run_extraction(self.lot)

        self.assertEqual(resultat.etat, "terminee")
        self.assertEqual(resultat.summary["conformes"], 3)
        # D7 : le reste est porté par l'issue — l'état reste `terminee` et le
        # code de sortie reste celui des sources, la purge échouée est signalée.
        self.assertTrue(resultat.dossier_travail_conserve)
        journal = (self.folder_of(resultat) / "run.log").read_text(encoding="utf-8")
        self.assertIn(MOTIF_DOSSIER_CONSERVE, journal)
        self.assertNotIn(str(self.donnees), journal)

    def test_busy_slot_refused_without_admission(self) -> None:
        liberation = threading.Event()
        self.creneau.demarrer(
            TYPE_VERIFICATION, lambda worker: liberation.wait(DELAY), cible="occupe"
        )
        execution = self.make_execution()
        with self.assertRaises(CreneauOccupe):
            launch_extraction(
                self.configuration,
                execution,
                self.creneau,
                modele=EXTRACTION_MODEL_REF,
                grille="essai",
                sources=self.lot,
            )
        self.assertFalse(execution.en_cours())
        self.assertEqual(self.extraction_folders(), [])
        liberation.set()
        self.assertTrue(self.creneau.attendre_thread(DELAY))

    def test_existing_reservation_refused_without_cancellation(self) -> None:
        execution = self.make_execution()
        execution.reserver()
        with self.assertRaises(ExecutionAlreadyReserved):
            launch_extraction(
                self.configuration,
                execution,
                self.creneau,
                modele=EXTRACTION_MODEL_REF,
                grille="essai",
                sources=self.lot,
            )
        self.assertTrue(execution.en_cours())
        execution.annuler_reservation()

    def test_engine_not_ready_refused_before_reservation(self) -> None:
        # Un modèle llama.cpp relu de l'inventaire, famille déclarée qualifiée pour
        # ce seul essai : le moteur n'est pas installé, donc refusé au lancement.
        famille = dataclasses.replace(DECLARATION_LLAMA_CPP.familles[0], qualifiee=True)
        registre = RegistreMoteurs()
        registre.enregistrer(dataclasses.replace(DECLARATION_LLAMA_CPP, familles=(famille,)))
        modele = ModeleLocal(
            moteur="llama-cpp",
            cle="a" * 64,
            identifiant="org/modele",
            id_resolu="org/modele",
            commit="c" * 40,
            famille="llm-gguf",
            fichier_gguf="modele.gguf",
            fichiers=(),
            taille_disque=None,
            date="2026-01-01",
        )
        configuration = ExtractionConfiguration(
            self.donnees, registre, lambda: (modele,), racine_grilles=self.projet
        )
        self.assertEqual(
            [propose.famille for propose in configuration.modeles_proposables()],
            [famille.identifiant],
        )
        execution = ExtractionExecution(self.donnees, registre, self.moteurs)
        with self.assertRaises(EngineNotReady):
            launch_extraction(
                configuration,
                execution,
                self.creneau,
                modele=f"llama-cpp/{'a' * 64}",
                grille="essai",
                sources=self.lot,
            )
        self.assertFalse(execution.en_cours())
        self.assertEqual(self.creneau.instantane().etat, "libre")
        self.assertEqual(self.extraction_folders(), [])

    def test_linked_cache_refused_before_any_job_written(self) -> None:
        # Contre-revue : si le dossier de cache est un lien symbolique, le
        # dossier de travail — et le `job.json` qui contient les textes — ne
        # doit pas être écrit dans sa cible : la demande est refusée avant la
        # réservation (refus code 2 côté commande), sans opération ni dossier,
        # et la cible reste intacte.
        cible = self.donnees.parent / "cible-cache"
        piege = cible / "execution-piege"
        piege.mkdir(parents=True)
        (piege / "job.json").write_text(
            '{"sources": "MARQUEUR_TRAVAIL_9"}', encoding="utf-8"
        )
        cache = self.donnees / "cache"
        cache.symlink_to(cible, target_is_directory=True)
        execution = self.make_execution()
        with self.assertRaises(EngineNotReady) as contexte:
            launch_extraction(
                self.configuration,
                execution,
                self.creneau,
                modele=EXTRACTION_MODEL_REF,
                grille="essai",
                sources=[f"{self.identifiant_a}:1"],
            )
        self.assertIn("lien symbolique", str(contexte.exception))
        self.assertFalse(execution.en_cours())
        self.assertEqual(self.creneau.instantane().etat, "libre")
        self.assertEqual(self.extraction_folders(), [])
        self.assertEqual(
            (piege / "job.json").read_text(encoding="utf-8"),
            '{"sources": "MARQUEUR_TRAVAIL_9"}',
        )
        self.assertEqual(list(cible.iterdir()), [piege])


class ExtractionMetaTest(ExtractionBench):
    """Métadonnées du chargement, compteurs natifs et `run.log` borné (D6, D7)."""

    def consignateur(self) -> ExtractionRecorder:
        """Consignation admise sans moteur, pour alimenter le chargement directement."""
        consignateur = ExtractionRecorder(
            self.donnees,
            self.request_for(self.lot),
            MOTEUR_FACTICE,
            debut=time.perf_counter(),
            machine=MACHINE,
            programme=PROGRAMME,
            base=BASE_STAMP,
            court_id=_short_id(),
        )
        self.assertTrue(consignateur.ouvrir(), consignateur.erreur)
        return consignateur

    def test_meta_et_compteurs_persistes_dans_run_et_resultats(self) -> None:
        construire = self.wrapper_command(
            f"adaptateur.configurer(meta={META_MOTEUR!r}, "
            f"scenario=[{{'comptes_natifs': {COMPTES_NATIFS!r}}}, {{}}, {{}}])\n"
            + ADAPTER_BODY
        )
        resultat = self.run_extraction(self.lot, construire=construire)
        self.assertEqual(resultat.etat, "terminee")
        dossier = self.folder_of(resultat)
        run = self.read_run(dossier)
        self.assertEqual(run["effectifs"]["threads_appliques"], 4)
        self.assertEqual(run["effectifs"]["mode_chargement_poids"], "mmap")
        self.assertEqual(
            run["effectifs"]["reglages_effectifs"],
            {"decodage": "glouton", "graine": None},
        )
        self.assertEqual(run["modele"]["architecture"], "mistral3")
        self.assertEqual(run["modele"]["sha256_gabarit_embarque"], "d" * 64)
        self.assertEqual(run["consignes"]["version_format"], 1)
        consignes = self.read_json(dossier / "consignes.json")
        self.assertEqual(set(consignes), CLES_CONSIGNES_ADMISSION | {"version_format"})
        self.assertEqual(consignes["version_format"], 1)
        # Comptes sous leur nom, dans les mesures de la seule source qui les porte.
        self.assertEqual(
            self.source_plan(dossier, 1)["mesures"]["comptes_natifs"], COMPTES_NATIFS
        )
        self.assertNotIn("comptes_natifs", self.source_plan(dossier, 2)["mesures"])
        self.assertEqual(
            self.read_json(self.source_folder(dossier, 1) / "result.json")["mesures"][
                "comptes_natifs"
            ],
            COMPTES_NATIFS,
        )
        self.assertNotIn(
            "comptes_natifs",
            self.read_json(self.source_folder(dossier, 2) / "result.json")["mesures"],
        )
        journal = (dossier / "run.log").read_text(encoding="utf-8")
        self.assertIn("métadonnées du chargement enregistrées", journal)
        self.assertIn("compteurs natifs source 1 enregistrés", journal)
        self.assertNotIn("compteurs natifs source 2", journal)
        for marqueur in SOURCE_MARKERS:
            self.assertNotIn(marqueur, journal)

    def test_factice_sans_meta_champs_a_none_et_consignes_inchanges(self) -> None:
        resultat = self.run_extraction(self.lot)
        dossier = self.folder_of(resultat)
        run = self.read_run(dossier)
        self.assertIsNone(run["effectifs"]["threads_appliques"])
        self.assertIsNone(run["effectifs"]["mode_chargement_poids"])
        self.assertEqual(run["effectifs"]["reglages_effectifs"], {})
        self.assertIsNone(run["modele"]["architecture"])
        self.assertIsNone(run["modele"]["sha256_gabarit_embarque"])
        self.assertIsNone(run["consignes"]["version_format"])
        self.assertEqual(
            set(self.read_json(dossier / "consignes.json")), CLES_CONSIGNES_ADMISSION
        )
        self.assertNotIn("comptes_natifs", self.source_plan(dossier, 1)["mesures"])

    def test_meta_non_conforme_ecartee_sans_arreter_le_run(self) -> None:
        sentinelle = "SENTINELLE-META-9"
        meta = {**META_MOTEUR, "sha256_gabarit_embarque": sentinelle}
        construire = self.wrapper_command(
            f"adaptateur.configurer(meta={meta!r})\n" + ADAPTER_BODY
        )
        resultat = self.run_extraction(self.lot, construire=construire)
        self.assertEqual(resultat.etat, "terminee")
        dossier = self.folder_of(resultat)
        run = self.read_run(dossier)
        self.assertIsNone(run["effectifs"]["threads_appliques"])
        self.assertIsNone(run["modele"]["architecture"])
        self.assertEqual(
            set(self.read_json(dossier / "consignes.json")), CLES_CONSIGNES_ADMISSION
        )
        self.assertEqual(run["progression"], {"sources_traitees": 3, "sources_total": 3})
        journal = (dossier / "run.log").read_text(encoding="utf-8")
        self.assertIn("Métadonnées du moteur ignorées", journal)
        contenus = journal + json.dumps(run, ensure_ascii=False)
        contenus += "\n".join(self.creneau.instantane().journal)
        self.assertNotIn(sentinelle, contenus)

    def test_meta_moteur_invalide_ecartee_par_le_serveur(self) -> None:
        # Un émetteur qui contourne le runner : le serveur valide à son tour, et
        # écarte l'objet entier, sans rien persister de ses valeurs.
        consignateur = self.consignateur()
        sentinelle = "SENTINELLE-META-10"
        evenement = {
            **loading_event(),
            "meta_moteur": {**META_MOTEUR, "architecture": sentinelle, "graine": 3},
        }
        self.assertTrue(consignateur.record_event(evenement))
        dossier = consignateur.dossier
        assert dossier is not None
        run = self.read_run(dossier)
        self.assertIsNone(run["modele"]["architecture"])
        self.assertIsNone(run["effectifs"]["threads_appliques"])
        self.assertEqual(
            set(self.read_json(dossier / "consignes.json")), CLES_CONSIGNES_ADMISSION
        )
        journal = (dossier / "run.log").read_text(encoding="utf-8")
        self.assertIn(
            "Métadonnées du chargement ignorées : "
            "métadonnée du moteur non conforme : graine.",
            journal,
        )
        self.assertNotIn(sentinelle, journal + json.dumps(run, ensure_ascii=False))
        self.assertTrue(consignateur.clore(etat="terminee", erreur=None, code_sortie=0))

    def test_echec_d_ecriture_des_consignes_clot_en_echec(self) -> None:
        consignateur = self.consignateur()
        ecriture = resultats_extraction.ecrire_json_atomique

        def ecrire_sans_consignes(chemin: Path, contenu: Any) -> None:
            if chemin.name == "consignes.json" and "version_format" in contenu:
                raise OSError("disque plein simulé")
            return ecriture(chemin, contenu)

        evenement = {**loading_event(), "meta_moteur": META_MOTEUR}
        with mock.patch.object(
            resultats_extraction, "ecrire_json_atomique", ecrire_sans_consignes
        ):
            self.assertFalse(consignateur.record_event(evenement))
        self.assertIsNotNone(consignateur.erreur)
        self.assertTrue(consignateur.clore(etat="terminee", erreur=None, code_sortie=0))
        assert consignateur.dossier is not None
        self.assertEqual(self.read_run(consignateur.dossier)["etat"], "failed")
        self.assertEqual(
            set(self.read_json(consignateur.dossier / "consignes.json")),
            CLES_CONSIGNES_ADMISSION,
        )

    def test_ligne_stderr_longue_tronquee_dans_run_log(self) -> None:
        construire = self.wrapper_command(
            """
_original = factice.extraire


def extraire(moteur, messages, reglages):
    sys.stderr.write("DEBUT-LONG " + "y" * 1000 + " FIN-LONG-SENTINELLE\\n")
    sys.stderr.flush()
    return _original(moteur, messages, reglages)


factice.extraire = extraire
"""
        )
        resultat = self.run_extraction(
            [f"{self.identifiant_a}:1"], construire=construire
        )
        self.assertEqual(resultat.etat, "terminee")
        dossier = self.folder_of(resultat)
        lignes = (dossier / "run.log").read_text(encoding="utf-8").splitlines()
        longues = [ligne for ligne in lignes if "DEBUT-LONG" in ligne]
        self.assertEqual(len(longues), 1)
        self.assertLessEqual(len(longues[0]), LONGUEUR_LIGNE_STDERR_MAX)
        self.assertIn("(ligne tronquée, ", longues[0])
        self.assertLessEqual(max(len(ligne) for ligne in lignes), LONGUEUR_LIGNE_STDERR_MAX)
        self.assertNotIn("FIN-LONG-SENTINELLE", "\n".join(lignes))
        self.assertNotIn("FIN-LONG-SENTINELLE", "\n".join(self.creneau.instantane().journal))


class InterruptionRecoveryTest(ExtractionBench):
    """Interruption réelle entre deux écritures, abandon et récupération au démarrage."""

    def test_interruption_between_two_writes_then_recovery(self) -> None:
        script = self.dossier / "interruption.py"
        script.write_text(
            INTERRUPTION_CODE.format(
                racine=str(RACINE_PROJET),
                donnees=str(self.donnees),
                grilles=str(self.projet),
                modele=EXTRACTION_MODEL_REF,
                sources=self.lot,
            ),
            encoding="utf-8",
        )
        sortie = subprocess.run(
            [sys.executable, str(script)],
            capture_output=True,
            text=True,
            timeout=DELAY,
            check=False,
        )
        self.assertEqual(sortie.returncode, 7, sortie.stderr)
        extractions = self.extraction_folders()
        self.assertEqual(len(extractions), 1)
        dossier = extractions[0]
        # Avant récupération : run en cours, source 2 avec sa sortie brute mais sans
        # marqueur de publication, et le fichier de travail contient les textes.
        self.assertEqual(self.read_run(dossier)["etat"], ETAT_EN_COURS)
        self.assertTrue((self.source_folder(dossier, 2) / "sortie_brute.txt").is_file())
        self.assertFalse((self.source_folder(dossier, 2) / "result.json").exists())
        self.assertTrue((self.source_folder(dossier, 1) / "result.json").is_file())
        self.assertTrue(any(self.donnees.glob("cache/execution-*")))

        sortie_recuperation = io.StringIO()
        with contextlib.redirect_stderr(sortie_recuperation):
            recuperer_executions_anterieures(self.donnees, delai_terminaison=5.0)
        self.assertIn("close en abandonnée", sortie_recuperation.getvalue())

        run = self.read_run(dossier)
        self.assertEqual(run["etat"], ETAT_ABANDONNEE)
        self.assertIsNone(run["mesures"]["duree_operation_s"])
        self.assertIsNone(run["mesures"]["duree_processus_s"])
        self.assertEqual(
            [plan["etat"] for plan in run["sources"]],
            [SOURCE_COMPLIANT, SOURCE_NOT_PROCESSED, SOURCE_NOT_PROCESSED],
        )
        self.assertEqual(run["progression"]["sources_traitees"], 1)
        self.assertEqual(list(self.donnees.glob("cache/execution-*")), [])
        self.assertFalse((self.source_folder(dossier, 2) / "result.json").exists())
        for chemin in dossier.rglob("*.json"):
            self.read_json(chemin)  # aucun JSON tronqué

    def test_abandon_then_recovery_terminates_live_engine_and_purges_work(self) -> None:
        temoin = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
        self.addCleanup(_kill, temoin)
        consignateur = ExtractionRecorder(
            self.donnees,
            self.request_for(self.lot),
            MOTEUR_FACTICE,
            debut=time.perf_counter(),
            machine=MACHINE,
            programme=PROGRAMME,
            base=BASE_STAMP,
            court_id=_short_id(),
        )
        self.assertTrue(consignateur.ouvrir(), consignateur.erreur)
        self.addCleanup(consignateur.fermer)
        self.assertTrue(
            consignateur.enregistrer_processus(
                pid=temoin.pid,
                heure_creation=psutil.Process(temoin.pid).create_time(),
                source="psutil",
                lance_a=horodatage_iso(),
            )
        )
        consignateur.record_event(loading_event())
        consignateur.record_event(source_event(0, "consultation-a.wav"))
        # Pas de clôture : l'extraction est abandonnée en cours d'exécution.
        travail = self.donnees / "cache" / "execution-abandon"
        travail.mkdir(parents=True)
        (travail / "job.json").write_text('{"sources": "MARQUEUR_TRAVAIL_5"}', encoding="utf-8")
        dossier = consignateur.dossier
        assert dossier is not None
        sortie = io.StringIO()
        with contextlib.redirect_stderr(sortie):
            recuperer_executions_anterieures(self.donnees, delai_terminaison=5.0)
        self.assertIsNotNone(temoin.wait(DELAY))
        run = self.read_run(dossier)
        self.assertEqual(run["etat"], ETAT_ABANDONNEE)
        self.assertIs(run["mesures"]["pic_memoire_partiel"], True)
        self.assertEqual(run["sources"][0]["etat"], SOURCE_COMPLIANT)
        self.assertEqual(run["sources"][1]["etat"], SOURCE_NOT_PROCESSED)
        self.assertFalse(travail.exists())
        self.assertTrue((self.source_folder(dossier, 1) / "result.json").is_file())
        self.assertNotIn("MARQUEUR_TRAVAIL_5", sortie.getvalue())

    def test_final_extraction_unchanged_by_recovery(self) -> None:
        resultat = self.run_extraction(self.lot)
        dossier = self.folder_of(resultat)
        avant = self.snapshot(dossier)
        recuperer_executions_anterieures(self.donnees, delai_terminaison=5.0)
        self.assertEqual(self.snapshot(dossier), avant)

    def test_stateless_extraction_folder_purged_silently_by_recovery(self) -> None:
        # Contre-revue : un arrêt entre la création du dossier d'extraction et
        # la première écriture peut laisser un dossier sans `run.json`. Sans
        # état ni copie `source.txt`, il est purgé silencieusement ; un nom hors
        # du format du programme n'est jamais touché.
        extractions = self.donnees / "extractions"
        vide = extractions / "20260101-120000-0000beef"
        vide.mkdir(parents=True)
        avec_journal = extractions / "20260101-120001-0000feed"
        avec_journal.mkdir()
        (avec_journal / "run.log").write_text("sans état\n", encoding="utf-8")
        etranger = extractions / "notes-perso"
        (etranger / "sous-dossier").mkdir(parents=True)
        (etranger / "sous-dossier" / "source.txt").write_text(
            "texte d'un tiers", encoding="utf-8"
        )

        sortie = io.StringIO()
        with contextlib.redirect_stderr(sortie):
            recuperer_executions_anterieures(self.donnees, delai_terminaison=5.0)

        self.assertFalse(vide.exists())
        self.assertFalse(avec_journal.exists())
        self.assertTrue((etranger / "sous-dossier" / "source.txt").is_file())
        contenu = sortie.getvalue()
        self.assertNotIn(vide.name, contenu)
        self.assertNotIn(avec_journal.name, contenu)
        self.assertNotIn(etranger.name, contenu)

    def test_extraction_folder_with_copies_but_no_run_closed_abandoned(self) -> None:
        # Cas défensif : des copies `source.txt` sans `run.json` (antérieures
        # au correctif « run.json d'abord »). Les textes restent en place et le
        # dossier est clôturé en état abandonné, jamais purgé.
        extractions = self.donnees / "extractions"
        dossier = extractions / "20260101-120002-0000baaf"
        dossier_source = dossier / "1-consultation-a.wav"
        dossier_source.mkdir(parents=True)
        (dossier_source / "source.txt").write_text(TEXT_A, encoding="utf-8")

        sortie = io.StringIO()
        with contextlib.redirect_stderr(sortie):
            recuperer_executions_anterieures(self.donnees, delai_terminaison=5.0)

        run = self.read_run(dossier)
        self.assertEqual(run["schema"], 1)
        self.assertEqual(run["type"], "extraction")
        self.assertEqual(run["etat"], ETAT_ABANDONNEE)
        self.assertEqual(run["identifiant"], dossier.name)
        self.assertEqual(run["sources"], [])
        self.assertEqual(
            run["progression"], {"sources_traitees": 0, "sources_total": 0}
        )
        self.assertIsNone(run["mesures"]["duree_operation_s"])
        self.assertIsNone(run["mesures"]["pic_memoire_octets"])
        self.assertEqual(
            (dossier_source / "source.txt").read_text(encoding="utf-8"), TEXT_A
        )
        contenu = sortie.getvalue()
        self.assertIn("close en abandonnée", contenu)
        self.assertIn(dossier.name, contenu)
        self.assertNotIn("MARQUEUR_SOURCE_A", contenu)
        # Idempotent : la seconde récupération ne réécrit pas l'état final.
        recuperer_executions_anterieures(self.donnees, delai_terminaison=5.0)
        self.assertEqual(self.read_run(dossier)["etat"], ETAT_ABANDONNEE)

    def test_inconsistent_running_run_refused_without_rewrite(self) -> None:
        dossier = self.donnees / "extractions" / "20260101-120000-0000beef"
        dossier.mkdir(parents=True)
        chemin = dossier / "run.json"
        chemin.write_text(
            json.dumps(
                {
                    "schema": 1,
                    "type": "extraction",
                    "identifiant": dossier.name,
                    "etat": ETAT_EN_COURS,
                    "processus_moteur": {"pid": None},
                    "sources": [{"dossier": "1-a.wav", "etat": "inconnu"}],
                }
            ),
            encoding="utf-8",
        )
        avant = chemin.read_bytes()
        with self.assertRaises(EtatAnterieurNonTraitable):
            recuperer_executions_anterieures(self.donnees, delai_terminaison=5.0)
        self.assertEqual(chemin.read_bytes(), avant)

    def test_running_extraction_with_outgoing_run_link_ignored_unread(self) -> None:
        # Contre-revue : un lien symbolique posé sur le `run.json` d'une
        # extraction en cours et pointant hors du dossier autorisé n'est
        # jamais lu : la récupération ignore l'exécution — elle reste en
        # l'état, sans clôture ni purge — et ne lève pas. La cible est un JSON
        # qui n'est pas un objet : sa lecture aurait refusé le démarrage.
        consignateur = ExtractionRecorder(
            self.donnees,
            self.request_for(self.lot),
            MOTEUR_FACTICE,
            debut=time.perf_counter(),
            machine=MACHINE,
            programme=PROGRAMME,
            base=BASE_STAMP,
            court_id=_short_id(),
        )
        self.assertTrue(consignateur.ouvrir(), consignateur.erreur)
        self.addCleanup(consignateur.fermer)
        dossier = consignateur.dossier
        assert dossier is not None
        run_json = dossier / "run.json"
        cible = self.donnees.parent / "run-piege.json"
        cible.write_text("[1, 2, 3]", encoding="utf-8")
        run_json.unlink()
        run_json.symlink_to(cible)

        sortie = io.StringIO()
        with contextlib.redirect_stderr(sortie):
            recuperer_executions_anterieures(self.donnees, delai_terminaison=5.0)

        # Le lien est intact, la cible n'a été ni lue ni réécrite, aucune
        # clôture n'a eu lieu : l'extraction reste ignorée, en l'état — et le
        # refus de confinement est rendu visible au lieu d'être silencieux.
        self.assertTrue(run_json.is_symlink())
        self.assertEqual(self.read_json(run_json), [1, 2, 3])
        self.assertEqual(self.extraction_folders(), [dossier])
        contenu = sortie.getvalue()
        self.assertNotIn("close en abandonnée", contenu)
        self.assertIn("laissée en l'état", contenu)
        self.assertIn("jamais lu", contenu)

    def test_broken_run_link_is_never_a_stateless_folder(self) -> None:
        # Contre-revue finale : un `run.json` LIÉ CASSÉ (cible absente) ne doit
        # pas faire passer le dossier pour « sans état » dans la seconde
        # passe — ni purge ni clôture : le dossier reste en l'état, avec le
        # diagnostic de confinement de la première passe.
        dossier = self.donnees / "extractions" / "20260101-130000-0000beef"
        dossier.mkdir(parents=True)
        (dossier / "run.json").symlink_to(
            self.donnees.parent / "cible-inexistante.json"
        )

        sortie = io.StringIO()
        with contextlib.redirect_stderr(sortie):
            recuperer_executions_anterieures(self.donnees, delai_terminaison=5.0)

        # Le dossier n'est ni purgé ni clôturé : le lien, même cassé, prouve
        # qu'un état existe potentiellement et la cible n'est jamais lue.
        self.assertTrue((dossier / "run.json").is_symlink())
        self.assertEqual(self.extraction_folders(), [dossier])
        self.assertNotIn("close en abandonnée", sortie.getvalue())
        self.assertIn("laissée en l'état", sortie.getvalue())

    def test_abandon_ignores_outgoing_link_on_source_result(self) -> None:
        # Contre-revue : à la clôture d'abandon, le `result.json` d'une source
        # non traitée est résolu confiné : un lien sortant n'est jamais lu, la
        # source reste non traitée même si sa cible est un résultat publié
        # qui ferait foi.
        consignateur = ExtractionRecorder(
            self.donnees,
            self.request_for(self.lot),
            MOTEUR_FACTICE,
            debut=time.perf_counter(),
            machine=MACHINE,
            programme=PROGRAMME,
            base=BASE_STAMP,
            court_id=_short_id(),
        )
        self.assertTrue(consignateur.ouvrir(), consignateur.erreur)
        self.addCleanup(consignateur.fermer)
        self.assertTrue(consignateur.record_event(loading_event()))
        self.assertTrue(
            consignateur.record_event(source_event(0, "consultation-a.wav"))
        )
        dossier = consignateur.dossier
        assert dossier is not None
        plan = self.read_run(dossier)["sources"][1]
        cible = self.donnees.parent / "resultat-piege.json"
        cible.write_text(
            json.dumps(
                {
                    "schema": 1,
                    "etat": SOURCE_COMPLIANT,
                    "motif": None,
                    "mesures": {},
                    "fin": "arret",
                }
            ),
            encoding="utf-8",
        )
        (dossier / plan["dossier"] / "result.json").symlink_to(cible)

        final = abandon_extraction(dossier, self.read_run(dossier))

        self.assertEqual(final["sources"][0]["etat"], SOURCE_COMPLIANT)
        self.assertEqual(final["sources"][1]["etat"], SOURCE_NOT_PROCESSED)

    def test_linked_extractions_root_never_walked_nor_purged(self) -> None:
        # Contre-revue : si `data/extractions` est lui-même un lien symbolique,
        # la récupération ne parcourt jamais sa cible : aucune lecture, aucune
        # clôture, aucune purge n'y a lieu — même pour un `run.json` d'extraction
        # « en cours » qui y serait déposé (première passe incluse) ; un
        # diagnostic fixe, sans chemin, signale le lien au démarrage.
        cible = self.donnees.parent / "cible-extractions"
        sans_copie = cible / "20260101-120000-0000beef"
        sans_copie.mkdir(parents=True)
        avec_copie = cible / "20260101-120001-0000feed"
        dossier_source = avec_copie / "1-consultation-a.wav"
        dossier_source.mkdir(parents=True)
        (dossier_source / "source.txt").write_text(
            "copie d'un tiers", encoding="utf-8"
        )
        # Un `run.json` d'extraction en cours, contrefait mais cohérent : s'il
        # était lu, la boucle de récupération le clôturerait en abandonné.
        en_cours = cible / "20260101-120002-0000abcd"
        en_cours.mkdir()
        (en_cours / "run.json").write_text(
            json.dumps(
                {
                    "schema": 1,
                    "type": "extraction",
                    "etat": "running",
                    "sources": [
                        {"dossier": "1-consultation-a.wav", "etat": SOURCE_NOT_PROCESSED}
                    ],
                    "processus_moteur": {"pid": None, "heure_creation": None},
                }
            ),
            encoding="utf-8",
        )
        extractions = self.donnees / "extractions"
        try:
            extractions.symlink_to(cible, target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("les liens symboliques ne sont pas disponibles ici")

        sortie = io.StringIO()
        with contextlib.redirect_stderr(sortie):
            recuperer_executions_anterieures(self.donnees, delai_terminaison=5.0)

        # La cible est intacte : le dossier sans copie n'a pas été purgé, celui
        # avec copie n'a pas été clôturé, l'extraction « en cours » n'a pas été
        # lue ni clôturée, aucun fichier n'a été écrit.
        self.assertTrue(sans_copie.is_dir())
        self.assertFalse((avec_copie / "run.json").exists())
        self.assertEqual(
            (dossier_source / "source.txt").read_text(encoding="utf-8"),
            "copie d'un tiers",
        )
        self.assertEqual(
            json.loads((en_cours / "run.json").read_text(encoding="utf-8"))["etat"],
            "running",
        )
        contenu = sortie.getvalue()
        self.assertIn(MOTIF_RACINE_EXTRACTIONS_LIEE, contenu)
        self.assertNotIn(str(cible), contenu)
        self.assertNotIn(str(self.donnees), contenu)
        self.assertNotIn("0000abcd", contenu)

        # La racine liée n'empêche pas le reste : les transcriptions du dossier
        # de données restent récupérables au même démarrage.
        self.assertTrue(extractions.is_symlink())


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
