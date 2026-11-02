"""Tests des adaptateurs réels et du traitement natif du runner, sans moteur réel.

Aucun paquet moteur n'est importé et aucun poids n'est lu : les modules
`faster_whisper`, `transcribe_cpp`, `torch` et `transformers` sont remplacés par
des doublures injectées dans `sys.modules`, qui enregistrent les arguments reçus
et renvoient des sorties contrôlées. Ces tests ne constituent donc pas une
validation PC : les essais réels restent consignés séparément sous `data/`.

Le runner est exercé dans ce processus avec un registre de test dont la famille
est qualifiée et déclare une durée native, puis sans durée native (repli sur les
fenêtres fixes de 30 s). Le moteur factice garde son comportement : ses tests
dédiés (`tests/test_factice.py`, `tests/test_runner.py`) ne sont pas modifiés.
"""

from __future__ import annotations

import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest import mock

import numpy as np

from engines.adaptateurs import faster_whisper, transcribe_cpp, transformers
from engines.declarations import (
    DeclarationAdaptateur,
    DureeNative,
    Famille,
    declarations_fournies,
    motif_famille_non_executable,
)
from engines.hors_ligne import CLE_CACHE_NUMBA, environnement_moteur
from engines.protocole import TYPE_AUDIO, TYPE_FIN, analyser_ligne
from engines.registre import RegistreMoteurs
from engines.runner import FORMAT_AUDIO, executer, charger_job
from transcription_bench.paths import RACINE_PROJET

MOTEUR_NATIF = "moteur-natif-de-test"
FAMILLE_NATIVE = "famille-native"
MODULE_ADAPTATEUR_NATIF = "adaptateur_natif_de_test"
DUREE_NATIVE_TEST_S = 60.0
TAUX = 16000


class _DtypeFp32:
    def __str__(self) -> str:
        return "torch.float32"


def _tensor(forme: tuple[int, ...]) -> np.ndarray:
    """Tableau minimal exposant `shape`, `sum()` et `tolist()` comme un tenseur."""
    return np.zeros(forme, dtype="float32")


def _trames_pour(duree_s: float, minimum: int = 0) -> int:
    """Trames mel au pas de 10 ms, avec le plancher de padding demandé."""
    return max(minimum, round(duree_s * 100))


class _ModeleFactice:
    """Objet moteur minimal : paramètres relus, génération contrôlée."""

    def __init__(self, device: str = "cpu") -> None:
        self.config = SimpleNamespace(
            max_symbols_per_step=10,
            encoder_config={"subsampling_factor": 8},
        )
        self._device = device
        self.mode_eval = False

    def parameters(self):
        return iter([SimpleNamespace(device=self._device, dtype=_DtypeFp32())])

    def eval(self) -> None:
        self.mode_eval = True


class _ProcesseurWhisperFictif:
    """Processor Whisper : formes d'entrée contrôlées et décodage trivial."""

    def __init__(self, trames_max: int | None = None) -> None:
        self.trames_max = trames_max
        self.appels: list[dict[str, object]] = []

    def __call__(self, signal, **options):
        self.appels.append(options)
        trames = _trames_pour(signal.size / TAUX, minimum=3000)
        if self.trames_max is not None:
            trames = min(trames, self.trames_max)
        return {
            "input_features": _tensor((1, 128, trames)),
            "attention_mask": _tensor((1, trames)),
        }

    def batch_decode(self, sequences, skip_special_tokens=True):
        return ["texte whisper"]

    def decode(self, jetons, skip_special_tokens=True):
        return "segment whisper"


class _ModeleWhisperFictif(_ModeleFactice):
    def __init__(self, device: str = "cpu") -> None:
        super().__init__(device)
        self.appels: list[dict[str, object]] = []

    def generate(self, **entree):
        self.appels.append(entree)
        return {
            "sequences": np.zeros((1, 3), dtype="int64"),
            "segments": [
                [{"tokens": [1, 2], "start": 0.0, "end": 1.5}],
            ],
        }


class _ProcesseurParakeetFictif:
    def __init__(self, trames_utiles: int | None = None) -> None:
        self.trames_utiles = trames_utiles
        self.appels: list[dict[str, object]] = []

    def __call__(self, signal, **options):
        self.appels.append(options)
        trames = _trames_pour(signal.size / TAUX)
        utiles = trames if self.trames_utiles is None else self.trames_utiles
        masque = np.zeros((1, trames), dtype="int64")
        masque[0, : min(utiles, trames)] = 1
        return {
            "input_features": _tensor((1, trames, 128)),
            "attention_mask": masque,
        }

    def decode(self, sequences, durations=None, skip_special_tokens=True):
        return (
            ["texte parakeet"],
            [
                [
                    {"token": "Bonjour", "start": 0.0, "end": 0.4},
                    {"token": " le", "start": 0.4, "end": 0.8},
                    {"token": " monde.", "start": 0.8, "end": 1.2},
                    {"token": " Fin", "start": 1.2, "end": 1.6},
                ]
            ],
        )


class _ModeleParakeetFictif(_ModeleFactice):
    def __init__(self, device: str = "cpu") -> None:
        super().__init__(device)
        self.appels: list[dict[str, object]] = []

    def generate(self, **entree):
        self.appels.append(entree)
        return SimpleNamespace(
            sequences=np.zeros((1, 4), dtype="int64"),
            durations=np.zeros((1, 4), dtype="int64"),
        )


def _module_torch_fictif() -> tuple[ModuleType, dict[str, int]]:
    """Module torch minimal : threads relus, dtype fp32 comparable."""
    etat = {"threads": 1}
    module = ModuleType("torch")
    module.float32 = _DtypeFp32()  # type: ignore[attr-defined]
    module.set_num_threads = lambda nombre: etat.__setitem__("threads", nombre)  # type: ignore[attr-defined]
    module.get_num_threads = lambda: etat["threads"]  # type: ignore[attr-defined]
    return module, etat


def _module_faster_whisper(
    device: str = "cpu", appels: list[dict[str, object]] | None = None
) -> ModuleType:
    """Module faster_whisper minimal, sans poids ni inférence réelle."""
    module = ModuleType("faster_whisper")
    journal = appels if appels is not None else []

    class _WhisperModel:
        def __init__(self, chemin, **options):
            journal.append({"methode": "__init__", "chemin": chemin, **options})
            self.model = SimpleNamespace(
                device=device, compute_type="int8_float32"
            )

        def transcribe(self, signal, **options):
            journal.append(
                {
                    "methode": "transcribe",
                    "echantillons": int(signal.size),
                    **options,
                }
            )

            class _Segment:
                start = 0.0
                end = round(signal.size / TAUX, 3)
                text = " bonjour"

            return iter([_Segment()]), SimpleNamespace(duration=signal.size / TAUX)

    module.WhisperModel = _WhisperModel  # type: ignore[attr-defined]
    return module


_TIMINGS_DEFAUT = object()


def _module_transcribe_cpp(
    *,
    backend: str = "CPU",
    architecture: str = "whisper",
    device_type: str = "cpu",
    observateur: list[dict[str, object]] | None = None,
    timings: object = _TIMINGS_DEFAUT,
) -> ModuleType:
    """Module transcribe_cpp minimal, sans bibliothèque native."""
    module = ModuleType("transcribe_cpp")
    if timings is _TIMINGS_DEFAUT:
        timings = SimpleNamespace(
            load_ms=12.5, mel_ms=3.25, encode_ms=40.0, decode_ms=60.5
        )

    class _WhisperRunOptions:
        def __init__(self, **options):
            self.options = options

    class _Modele:
        def __init__(self, chemin, **options):
            self.chemin = chemin
            self.options = options
            self.backend = backend
            self.arch = architecture
            self.variant = "whisper-large-v3-turbo"
            self.device = SimpleNamespace(device_type=device_type)
            if observateur is not None:
                observateur.append(
                    {
                        cle: os.environ.get(cle)
                        for cle in (
                            "TRANSCRIBE_BACKENDS",
                            "TRANSCRIBE_BACKEND",
                            "CUDA_VISIBLE_DEVICES",
                        )
                    }
                )

        def close(self):
            self.ferme = True

        def session(self, n_threads=0):
            return _Session(n_threads)

    class _Session:
        def __init__(self, n_threads: int) -> None:
            self.n_threads = n_threads

        def run(self, signal, **options):
            return SimpleNamespace(
                text="bonjour",
                language="fr",
                segments=[
                    SimpleNamespace(t0_ms=0.0, t1_ms=1200.0, text=" bonjour"),
                    SimpleNamespace(t0_ms=1200.0, t1_ms=2500.0, text=" monde"),
                ],
                timings=timings,
            )

    module.Model = _Modele  # type: ignore[attr-defined]
    module.WhisperRunOptions = _WhisperRunOptions  # type: ignore[attr-defined]
    return module


def _module_transformers(
    *,
    processeur_whisper=None,
    modele_whisper=None,
    processeur_parakeet=None,
    modele_parakeet=None,
    appels: list[dict[str, object]] | None = None,
) -> ModuleType:
    """Module transformers minimal : classes de chargement instrumentées."""
    module = ModuleType("transformers")
    journal = appels if appels is not None else []

    class _DepuisPretrained:
        _fabrique = staticmethod(lambda: None)

        @classmethod
        def from_pretrained(cls, chemin, **options):
            journal.append(
                {"classe": cls.__name__, "chemin": chemin, **options}
            )
            return cls._fabrique()

    def _classe(nom: str, fabrique):
        return type(nom, (_DepuisPretrained,), {"_fabrique": staticmethod(fabrique)})

    module.WhisperProcessor = _classe(  # type: ignore[attr-defined]
        "WhisperProcessor", lambda: processeur_whisper
    )
    module.WhisperForConditionalGeneration = _classe(  # type: ignore[attr-defined]
        "WhisperForConditionalGeneration", lambda: modele_whisper
    )
    module.ParakeetProcessor = _classe(  # type: ignore[attr-defined]
        "ParakeetProcessor", lambda: processeur_parakeet
    )
    module.ParakeetForTDT = _classe(  # type: ignore[attr-defined]
        "ParakeetForTDT", lambda: modele_parakeet
    )
    return module


def _dossier_modele(base: Path, model_type: str) -> Path:
    dossier = base / "modele"
    dossier.mkdir(parents=True, exist_ok=True)
    (dossier / "config.json").write_text(
        json.dumps({"model_type": model_type}), encoding="utf-8"
    )
    return dossier


def _modele_option(chemin: Path) -> dict[str, object]:
    return {"identifiant": "org/modele", "chemin": str(chemin)}


class ReglagesEtVerrousTest(unittest.TestCase):
    def test_familles_reelles_qualifiees_avec_duree_native(self) -> None:
        attendus = {
            ("faster-whisper", "whisper"),
            ("transcribe-cpp", "whisper"),
            ("transformers", "whisper"),
            ("transformers", "parakeet-tdt"),
        }
        obtenus = set()
        for declaration in declarations_fournies():
            if declaration.factice:
                self.assertEqual(declaration.familles_qualifiees, ())
                self.assertTrue(
                    all(famille.duree_native is None for famille in declaration.familles)
                )
                continue
            for famille in declaration.familles:
                self.assertTrue(famille.qualifiee)
                self.assertIsNotNone(famille.duree_native)
                assert famille.duree_native is not None
                self.assertGreater(famille.duree_native.secondes_max, 0)
                obtenus.add((declaration.identifiant, famille.identifiant))
        self.assertEqual(obtenus, attendus)

    def test_reglages_reels_exposes(self) -> None:
        reglages = {
            (declaration.identifiant, famille.identifiant): tuple(
                reglage.nom for reglage in famille.reglages
            )
            for declaration in declarations_fournies()
            for famille in declaration.familles
        }
        self.assertEqual(
            reglages[("faster-whisper", "whisper")],
            ("compute_type", "beam_size"),
        )
        self.assertEqual(
            reglages[("transcribe-cpp", "whisper")],
            ("no_mmap", "condition_on_prev_tokens"),
        )
        self.assertEqual(reglages[("transformers", "whisper")], ("do_normalize",))
        self.assertEqual(reglages[("transformers", "parakeet-tdt")], ())

    def test_mecanisme_natif_n_est_plus_un_refus(self) -> None:
        declaration = declarations_fournies()[0]
        famille = declaration.familles[0]

        self.assertIsNotNone(famille.duree_native)
        self.assertIsNone(motif_famille_non_executable(declaration, famille))

    def test_famille_non_qualifiee_reste_refusee(self) -> None:
        declaration = declarations_fournies()[0]
        famille = Famille(
            "whisper",
            "Whisper",
            qualifiee=False,
            duree_native=DureeNative(10.0, "appel unique"),
        )

        motif = motif_famille_non_executable(declaration, famille)

        self.assertIn("non qualifiée", motif or "")

    def test_verrous_presents_et_alignes_sur_les_declarations(self) -> None:
        attendus = {
            "faster-whisper": ("faster-whisper==1.2.1", "ctranslate2==4.8.3"),
            "transcribe-cpp": (
                "transcribe-cpp==0.4.1",
                "transcribe-cpp-native==0.4.1",
            ),
            "transformers": (
                "transformers==5.20.2",
                "torch==2.14.1+cpu",
                "librosa==1.0.0",
            ),
        }
        for moteur, epingles in attendus.items():
            with self.subTest(moteur=moteur):
                declaration = next(
                    element
                    for element in declarations_fournies()
                    if element.identifiant == moteur
                )
                assert declaration.fichier_requirements is not None
                verrou = RACINE_PROJET / declaration.fichier_requirements
                declaration_in = verrou.with_suffix(".in")
                self.assertTrue(verrou.is_file(), verrou)
                self.assertTrue(declaration_in.is_file(), declaration_in)
                contenu_txt = verrou.read_text(encoding="utf-8")
                contenu_in = declaration_in.read_text(encoding="utf-8")
                for epingle in epingles:
                    self.assertIn(epingle, contenu_txt)
                    self.assertIn(epingle, contenu_in)
                # Les commentaires peuvent citer data/feasibility, jamais une
                # ligne active : le verrou doit rester auto-porté.
                actives = [
                    ligne
                    for ligne in contenu_txt.splitlines()
                    if ligne.strip() and not ligne.lstrip().startswith("#")
                ]
                self.assertFalse(
                    [ligne for ligne in actives if "data/feasibility" in ligne]
                )
        self.assertIn(
            "--find-links https://download.pytorch.org/whl/cpu/torch/",
            (RACINE_PROJET / "requirements/transformers.txt").read_text(
                encoding="utf-8"
            ),
        )


class EnvironnementNumbaTest(unittest.TestCase):
    def test_cache_numba_par_defaut_sous_data(self) -> None:
        env = environnement_moteur({})

        self.assertEqual(
            Path(env[CLE_CACHE_NUMBA]),
            RACINE_PROJET / "data" / "cache-numba",
        )

    def test_cache_numba_remplaçable_par_l_appelant(self) -> None:
        env = environnement_moteur({}, dossier_cache_numba="/tmp/data-test/cache-numba")

        self.assertEqual(env[CLE_CACHE_NUMBA], "/tmp/data-test/cache-numba")


class FasterWhisperAdaptateurTest(unittest.TestCase):
    def _charger(
        self,
        *,
        device: str = "cpu",
        reglages: dict[str, object] | None = None,
        local_files_only: object = None,
    ):
        appels: list[dict[str, object]] = []
        module = _module_faster_whisper(device, appels)
        with tempfile.TemporaryDirectory() as temporaire:
            dossier = Path(temporaire) / "modele"
            dossier.mkdir()
            (dossier / "model.bin").write_bytes(b"poids factices")
            modele = _modele_option(dossier)
            if local_files_only is not None:
                modele["local_files_only"] = local_files_only
            with mock.patch.dict(sys.modules, {"faster_whisper": module}):
                contexte = faster_whisper.charger(
                    modele, 4, {} if reglages is None else reglages
                )
        return contexte, appels

    def test_chargement_cpu_explicite_et_valeurs_relues(self) -> None:
        contexte, appels = self._charger()
        chargement = next(
            appel for appel in appels if appel["methode"] == "__init__"
        )

        self.assertEqual(chargement["device"], "cpu")
        self.assertEqual(chargement["compute_type"], "int8")
        self.assertEqual(chargement["cpu_threads"], 4)
        self.assertEqual(chargement["num_workers"], 1)
        self.assertIs(chargement["local_files_only"], True)
        effectifs = contexte["reglages_effectifs"]
        self.assertEqual(effectifs["device_relu"], "cpu")
        self.assertEqual(effectifs["compute_type_relu"], "int8_float32")
        self.assertEqual(effectifs["langue_imposee"], "fr")
        self.assertIsNone(contexte["threads_appliques"])

    def test_reglages_transmis(self) -> None:
        contexte, appels = self._charger(
            reglages={"compute_type": "float32", "beam_size": 3}
        )
        chargement = next(
            appel for appel in appels if appel["methode"] == "__init__"
        )

        self.assertEqual(chargement["compute_type"], "float32")
        self.assertEqual(contexte["beam_size"], 3)

    def test_type_de_calcul_inconnu_refuse(self) -> None:
        with self.assertRaises(ValueError):
            self._charger(reglages={"compute_type": "int4"})

    def test_peripherique_non_cpu_refuse(self) -> None:
        with self.assertRaises(RuntimeError):
            self._charger(device="cuda")

    def test_chargement_local_impose(self) -> None:
        with self.assertRaises(RuntimeError):
            self._charger(local_files_only=False)

    def test_transcription_langue_parametres_et_segments(self) -> None:
        contexte, appels = self._charger()

        resultat = faster_whisper.transcrire(
            contexte, np.zeros(TAUX, dtype="<f4"), TAUX, {}
        )

        self.assertEqual(resultat["texte"], "bonjour")
        self.assertEqual(resultat["segments"][0]["texte"], "bonjour")
        self.assertEqual(resultat["langue_imposee"], "fr")
        self.assertIsNone(resultat["threads_appliques"])
        self.assertEqual(
            resultat["reglages_effectifs"], contexte["reglages_effectifs"]
        )
        appel = next(
            appel for appel in appels if appel["methode"] == "transcribe"
        )
        self.assertEqual(appel["language"], "fr")
        self.assertEqual(appel["beam_size"], 5)
        self.assertEqual(appel["temperature"], 0.0)
        self.assertIs(appel["vad_filter"], False)
        self.assertIs(appel["condition_on_previous_text"], False)

    def test_frequence_inattendue_refusee(self) -> None:
        contexte, _appels = self._charger()

        with self.assertRaises(ValueError):
            faster_whisper.transcrire(
                contexte, np.zeros(1600, dtype="<f4"), 8000, {}
            )


class TranscribeCppAdaptateurTest(unittest.TestCase):
    def _chemin(self, base: Path) -> Path:
        chemin = base / "modele.gguf"
        chemin.write_bytes(b"GGUF")
        return chemin

    def _charger(self, **options):
        observateur: list[dict[str, object]] = []
        module = _module_transcribe_cpp(observateur=observateur, **options)
        with tempfile.TemporaryDirectory() as temporaire:
            chemin = self._chemin(Path(temporaire))
            with mock.patch.dict(sys.modules, {"transcribe_cpp": module}):
                contexte = transcribe_cpp.charger(_modele_option(chemin), 4, {})
        return contexte, observateur

    def test_backend_cpu_force_pendant_le_chargement_puis_restaure(self) -> None:
        with mock.patch.dict(
            os.environ,
            {"TRANSCRIBE_BACKENDS": "auto", "CUDA_VISIBLE_DEVICES": "0"},
        ):
            contexte, observateur = self._charger()
            self.assertEqual(os.environ["TRANSCRIBE_BACKENDS"], "auto")
            self.assertEqual(os.environ["CUDA_VISIBLE_DEVICES"], "0")

        self.assertEqual(
            observateur[0],
            {
                "TRANSCRIBE_BACKENDS": "cpu",
                "TRANSCRIBE_BACKEND": "cpu",
                "CUDA_VISIBLE_DEVICES": "",
            },
        )
        effectifs = contexte["reglages_effectifs"]
        self.assertEqual(effectifs["backend_relu"], "CPU")
        self.assertEqual(effectifs["device_type_relu"], "cpu")
        self.assertEqual(effectifs["architecture_relue"], "whisper")
        self.assertIs(effectifs["no_mmap"], False)
        self.assertIsNone(contexte["threads_appliques"])

    def test_backend_non_cpu_refuse(self) -> None:
        with self.assertRaises(RuntimeError):
            self._charger(backend="CUDA")

    def test_architecture_non_whisper_refusee(self) -> None:
        with self.assertRaises(RuntimeError):
            self._charger(architecture="qwen3-asr")

    def test_reglage_no_mmap_transmis(self) -> None:
        module = _module_transcribe_cpp()
        with tempfile.TemporaryDirectory() as temporaire:
            chemin = self._chemin(Path(temporaire))
            with mock.patch.dict(sys.modules, {"transcribe_cpp": module}):
                contexte = transcribe_cpp.charger(
                    _modele_option(chemin), 4, {"no_mmap": True}
                )
        self.assertIs(contexte["reglages_effectifs"]["no_mmap"], True)

    def test_transcription_segments_et_langue(self) -> None:
        contexte, _observateur = self._charger()

        resultat = transcribe_cpp.transcrire(
            contexte, np.zeros(TAUX, dtype="<f4"), TAUX, {}
        )

        self.assertEqual(resultat["texte"], "bonjour")
        self.assertEqual(
            [segment["debut_s"] for segment in resultat["segments"]], [0.0, 1.2]
        )
        self.assertEqual(resultat["segments"][1]["texte"], "monde")
        self.assertEqual(resultat["langue_imposee"], "fr")

    def test_timings_natifs_par_appel_en_millisecondes(self) -> None:
        contexte, _observateur = self._charger()

        resultat = transcribe_cpp.transcrire(
            contexte, np.zeros(TAUX, dtype="<f4"), TAUX, {}
        )

        self.assertEqual(
            resultat["timings_natifs"],
            [
                {
                    "unite": "ms",
                    "load_ms": 12.5,
                    "mel_ms": 3.25,
                    "encode_ms": 40.0,
                    "decode_ms": 60.5,
                }
            ],
        )

    def test_timings_natifs_absents_restent_none(self) -> None:
        module = _module_transcribe_cpp(timings=None)
        with tempfile.TemporaryDirectory() as temporaire:
            chemin = self._chemin(Path(temporaire))
            with mock.patch.dict(sys.modules, {"transcribe_cpp": module}):
                contexte = transcribe_cpp.charger(_modele_option(chemin), 4, {})
            resultat = transcribe_cpp.transcrire(
                contexte, np.zeros(TAUX, dtype="<f4"), TAUX, {}
            )

        self.assertIsNone(resultat["timings_natifs"])

    def test_fichier_gguf_absent_refuse(self) -> None:
        with tempfile.TemporaryDirectory() as temporaire:
            with self.assertRaises(RuntimeError):
                transcribe_cpp.charger(
                    _modele_option(Path(temporaire) / "absent.gguf"), 4, {}
                )


class TransformersAdaptateurTest(unittest.TestCase):
    def _charger_whisper(self, processeur=None, modele=None):
        processeur = processeur or _ProcesseurWhisperFictif()
        modele = modele or _ModeleWhisperFictif()
        torch, etat = _module_torch_fictif()
        appels: list[dict[str, object]] = []
        module = _module_transformers(
            processeur_whisper=processeur,
            modele_whisper=modele,
            appels=appels,
        )
        with tempfile.TemporaryDirectory() as temporaire:
            chemin = _dossier_modele(Path(temporaire), "whisper")
            with mock.patch.dict(
                sys.modules, {"torch": torch, "transformers": module}
            ):
                contexte = transformers.charger(_modele_option(chemin), 4, {})
        return contexte, processeur, modele, appels, etat

    def test_chargement_whisper_fp32_safetensors_et_threads(self) -> None:
        contexte, _processeur, _modele, appels, etat = self._charger_whisper()

        chargement = next(
            appel
            for appel in appels
            if appel["classe"] == "WhisperForConditionalGeneration"
        )
        self.assertIs(chargement["use_safetensors"], True)
        self.assertIs(chargement["local_files_only"], True)
        self.assertIs(chargement["trust_remote_code"], False)
        self.assertEqual(str(chargement["dtype"]), "torch.float32")
        self.assertEqual(etat["threads"], 4)
        effectifs = contexte["reglages_effectifs"]
        self.assertEqual(effectifs["famille_locale"], "whisper")
        self.assertEqual(effectifs["device_relu"], "cpu")
        self.assertEqual(effectifs["dtype_relu"], "torch.float32")
        self.assertEqual(effectifs["threads_appliques"], 4)
        self.assertIs(effectifs["do_normalize"], False)
        self.assertIs(effectifs["truncation"], False)
        self.assertEqual(effectifs["langue_imposee"], "fr")

    def test_chargement_whisper_non_cpu_refuse(self) -> None:
        with self.assertRaises(RuntimeError):
            self._charger_whisper(modele=_ModeleWhisperFictif(device="cuda"))

    def test_famille_inconnue_refusee(self) -> None:
        torch, _etat = _module_torch_fictif()
        module = _module_transformers()
        with tempfile.TemporaryDirectory() as temporaire:
            chemin = _dossier_modele(Path(temporaire), "voxtral")
            with mock.patch.dict(
                sys.modules, {"torch": torch, "transformers": module}
            ):
                with self.assertRaises(RuntimeError):
                    transformers.charger(_modele_option(chemin), 4, {})

    def test_transcription_whisper_options_long_form(self) -> None:
        contexte, processeur, modele, _appels, _etat = self._charger_whisper()

        resultat = transformers.transcrire(
            contexte, np.zeros(TAUX, dtype="<f4"), TAUX, {}
        )

        self.assertEqual(resultat["texte"], "texte whisper")
        self.assertEqual(resultat["segments"][0]["texte"], "segment whisper")
        self.assertEqual(resultat["langue_imposee"], "fr")
        options = processeur.appels[0]
        self.assertIs(options["truncation"], False)
        self.assertEqual(options["padding"], "longest")
        self.assertIs(options["return_attention_mask"], True)
        self.assertIs(options["do_normalize"], False)
        self.assertEqual(options["sampling_rate"], TAUX)
        generation = modele.appels[0]
        self.assertEqual(generation["language"], "fr")
        self.assertEqual(generation["task"], "transcribe")
        self.assertIs(generation["return_timestamps"], True)

    def test_entree_whisper_tronquee_refusee(self) -> None:
        processeur = _ProcesseurWhisperFictif(trames_max=500)
        contexte, *_ = self._charger_whisper(processeur=processeur)

        with self.assertRaises(RuntimeError):
            transformers.transcrire(
                contexte, np.zeros(TAUX * 10, dtype="<f4"), TAUX, {}
            )

    def test_chargement_parakeet_et_max_length_borne(self) -> None:
        processeur = _ProcesseurParakeetFictif()
        modele = _ModeleParakeetFictif()
        torch, _etat = _module_torch_fictif()
        appels: list[dict[str, object]] = []
        module = _module_transformers(
            processeur_parakeet=processeur,
            modele_parakeet=modele,
            appels=appels,
        )
        with tempfile.TemporaryDirectory() as temporaire:
            chemin = _dossier_modele(Path(temporaire), "parakeet_tdt")
            with mock.patch.dict(
                sys.modules, {"torch": torch, "transformers": module}
            ):
                contexte = transformers.charger(_modele_option(chemin), 4, {})
                resultat = transformers.transcrire(
                    contexte, np.zeros(TAUX, dtype="<f4"), TAUX, {}
                )

        effectifs = contexte["reglages_effectifs"]
        self.assertEqual(effectifs["famille_locale"], "parakeet-tdt")
        self.assertIn("trames_encodeur", effectifs["max_length_regle"])
        # L'API TDT n'expose aucune option de langue : rien n'est imposé.
        self.assertIsNone(effectifs["langue_imposee"])
        self.assertEqual(resultat["texte"], "texte parakeet")
        self.assertIsNone(resultat["langue_imposee"])
        # 1 s = 100 trames mel ; 100 / 8 = 13 trames encodeur ; 10 x 13 + 10.
        self.assertEqual(modele.appels[0]["max_length"], 140)
        self.assertEqual(
            [segment["texte"] for segment in resultat["segments"]],
            ["Bonjour le monde.", "Fin"],
        )

    def test_borne_max_length_atteinte_detectee(self) -> None:
        processeur = _ProcesseurParakeetFictif()
        modele = _ModeleParakeetFictif()
        modele.generate = lambda **entree: SimpleNamespace(  # type: ignore[method-assign]
            sequences=np.zeros((1, 140), dtype="int64"),
            durations=np.zeros((1, 140), dtype="int64"),
        )
        torch, _etat = _module_torch_fictif()
        module = _module_transformers(
            processeur_parakeet=processeur, modele_parakeet=modele
        )
        with tempfile.TemporaryDirectory() as temporaire:
            chemin = _dossier_modele(Path(temporaire), "parakeet_tdt")
            with mock.patch.dict(
                sys.modules, {"torch": torch, "transformers": module}
            ):
                contexte = transformers.charger(_modele_option(chemin), 4, {})
                with self.assertRaises(RuntimeError):
                    transformers.transcrire(
                        contexte, np.zeros(TAUX, dtype="<f4"), TAUX, {}
                    )

    def test_masque_parakeet_trop_court_refuse(self) -> None:
        processeur = _ProcesseurParakeetFictif(trames_utiles=10)
        torch, _etat = _module_torch_fictif()
        module = _module_transformers(
            processeur_parakeet=processeur,
            modele_parakeet=_ModeleParakeetFictif(),
        )
        with tempfile.TemporaryDirectory() as temporaire:
            chemin = _dossier_modele(Path(temporaire), "parakeet_tdt")
            with mock.patch.dict(
                sys.modules, {"torch": torch, "transformers": module}
            ):
                contexte = transformers.charger(_modele_option(chemin), 4, {})
                with self.assertRaises(RuntimeError):
                    transformers.transcrire(
                        contexte, np.zeros(TAUX * 2, dtype="<f4"), TAUX, {}
                    )


APPELS_ADAPTATEUR_NATIF: list[dict[str, object]] = []


def _module_adaptateur_natif() -> ModuleType:
    """Adaptateur de test enregistré comme module, sans moteur réel."""
    module = ModuleType(MODULE_ADAPTATEUR_NATIF)

    def charger(modele, threads_demandes, reglages):
        APPELS_ADAPTATEUR_NATIF.clear()
        return {"threads_demandes": threads_demandes}

    def transcrire(moteur, signal, taux, reglages):
        duree = signal.size / taux
        APPELS_ADAPTATEUR_NATIF.append(
            {"echantillons": int(signal.size), "duree_s": duree}
        )
        return {
            "texte": "segment",
            "segments": [{"debut_s": 0.0, "fin_s": duree, "texte": "segment"}],
            "reglages_effectifs": {"moteur": "test"},
            "langue_imposee": "fr",
            "threads_appliques": None,
        }

    module.charger = charger  # type: ignore[attr-defined]
    module.transcrire = transcrire  # type: ignore[attr-defined]
    return module


class RunnerDureeNativeTest(unittest.TestCase):
    def registre(self, duree_native: DureeNative | None) -> RegistreMoteurs:
        registre = RegistreMoteurs()
        registre.enregistrer(
            DeclarationAdaptateur(
                identifiant=MOTEUR_NATIF,
                nom="Moteur natif de test",
                fichier_requirements=None,
                regle_compatibilite="aucune",
                familles=(
                    Famille(
                        FAMILLE_NATIVE,
                        "Famille native de test",
                        qualifiee=True,
                        duree_native=duree_native,
                    ),
                ),
                module_adaptateur=MODULE_ADAPTATEUR_NATIF,
            )
        )
        return registre

    def executer(self, secondes: float, duree_native: DureeNative | None):
        with tempfile.TemporaryDirectory() as temporaire:
            dossier = Path(temporaire)
            np.full(round(secondes * TAUX), 0.25, dtype="<f4").tofile(
                dossier / "audio.f32"
            )
            job = {
                "version": 1,
                "moteur": MOTEUR_NATIF,
                "famille": FAMILLE_NATIVE,
                "modele": {
                    "identifiant": "test/modele",
                    "revision": "abc",
                    "chemin": "modele",
                },
                "threads_demandes": 4,
                "reglages": {},
                "format_audio": FORMAT_AUDIO,
                "audios": [{"nom": "audio.wav", "chemin": "audio.f32"}],
            }
            chemin_job = dossier / "job.json"
            chemin_job.write_text(json.dumps(job), encoding="utf-8")
            sortie = io.StringIO()
            with mock.patch.dict(
                sys.modules, {MODULE_ADAPTATEUR_NATIF: _module_adaptateur_natif()}
            ):
                with redirect_stdout(sortie):
                    executer(
                        charger_job(chemin_job),
                        self.registre(duree_native),
                    )
        evenements = [
            evenement
            for evenement in (
                analyser_ligne(ligne) for ligne in sortie.getvalue().splitlines()
            )
            if evenement is not None
        ]
        audio = next(
            evenement for evenement in evenements if evenement["type"] == TYPE_AUDIO
        )
        return evenements, audio

    def test_audio_dans_la_duree_native_en_un_appel(self) -> None:
        evenements, audio = self.executer(
            10.0, DureeNative(DUREE_NATIVE_TEST_S, "appel unique")
        )

        self.assertEqual(len(APPELS_ADAPTATEUR_NATIF), 1)
        self.assertEqual(audio["decoupage"], "natif")
        self.assertAlmostEqual(audio["fenetre_s"], 10.0, places=3)
        self.assertEqual(audio["nb_fenetres"], 1)
        self.assertEqual(audio["segments"][0]["debut_s"], 0.0)
        self.assertEqual(evenements[-1]["type"], TYPE_FIN)

    def test_audio_au_dela_de_la_duree_native_en_fenetres_fixes(self) -> None:
        _evenements, audio = self.executer(
            70.0, DureeNative(DUREE_NATIVE_TEST_S, "appel unique")
        )

        self.assertEqual(len(APPELS_ADAPTATEUR_NATIF), 3)
        self.assertEqual(audio["decoupage"], "fenetres-fixes")
        self.assertEqual(audio["fenetre_s"], 30.0)
        self.assertEqual(audio["nb_fenetres"], 3)
        # Les horodatages des fenêtres suivantes sont décalés.
        debuts = [segment["debut_s"] for segment in audio["segments"]]
        self.assertEqual(debuts, [0.0, 30.0, 60.0])

    def test_sans_duree_native_fenetres_fixes_inchangees(self) -> None:
        _evenements, audio = self.executer(10.0, None)

        self.assertEqual(audio["decoupage"], "fenetres-fixes")
        self.assertEqual(audio["fenetre_s"], 30.0)
        self.assertEqual(audio["nb_fenetres"], 1)


if __name__ == "__main__":
    unittest.main()
