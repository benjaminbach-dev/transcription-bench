"""Tests des commandes publiques de lecture (tâches 2.1 à 2.6).

Chaque commande est exécutée par `cli.main` dans une vraie session (verrou,
récupération, préparation de `data/`) sur un dossier temporaire : les audios
sont des WAV synthétiques du harnais existant, aucun moteur, aucun réseau.
Les instantanés verrouillent les clés JSON de chaque commande et leurs valeurs
réelles ; les validations des services (`lister_audios`,
`preparer_dossiers_data`, `InstallationMoteurs`) restent couvertes par leurs
tests propres — seules les traductions propres à la commande sont testées ici.
Les moteurs viennent du registre fourni : le moteur factice est prêt, les
moteurs réels non installés, et un journal sans environnement donne l'état
échec du service. Les modèles locaux sont écrits sur disque (manifeste et
fichiers simulés, sans poids réels) puis relus par le service d'inventaire.
"""

from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tests.test_comparaison_resultats import (
    EMPREINTE_A,
    EMPREINTE_B,
    resultat_empreinte,
)
from tests.test_consultation_observations_systeme import cpu_systeme, observation
from tests.test_consultation_resultats import (
    IDENTIFIANT,
    IDENTIFIANT_ANCIEN,
    ecrire_execution,
    execution_complete,
    run_json,
)
from tests.test_audios import ecrire_wav
from engines.declarations import (
    DECLARATION_FACTICE,
    DeclarationAdaptateur,
    Famille,
)
from engines.mesures_systeme import PROVENANCE_REELLE
from engines.registre import RegistreMoteurs
from transcription_bench import cli, commands, composition, paths
from transcription_bench.executions import (
    CLE_MODELE_FACTICE,
    LIBELLE_MODELE_FACTICE,
    threads_par_defaut,
)
from transcription_bench.gestion_modeles import (
    NOM_DOSSIER_FICHIERS,
    NOM_MARQUEUR,
    cle_stockage,
)
from transcription_bench.instance import VerrouInstance
from transcription_bench.consultation_resultats import CLE_OBSERVATION_AUDIO
from transcription_bench.moteurs import SUFFIXE_JOURNAL
from transcription_bench.output import DIAGNOSTIC_PREFIX
from transcription_bench.resultats import (
    ETAT_ABANDONNEE,
    ETAT_INTERROMPUE,
    ETAT_TERMINEE,
    STATUT_NON_TRAITE,
)
from transcription_bench.web.app import MESSAGE_RESULTAT_NON_INTERPRETABLE

#: Clés d'une entrée d'audio, dans l'ordre du sérialiseur (tâche 1.4).
AUDIO_ENTRY_KEYS = ["nom", "format", "taille_octets", "duree_indicative", "erreur", "readable"]
#: Clés d'un état de moteur, dans l'ordre du sérialiseur (tâche 1.4).
ENGINE_STATE_KEYS = [
    "identifiant",
    "nom",
    "etat",
    "factice",
    "installable",
    "note",
    "date_installation",
    "versions",
]
#: Clés d'un modèle local, dans l'ordre du sérialiseur (tâche 2.3).
LOCAL_MODEL_KEYS = [
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
]
#: Clés d'un détail d'exécution, dans l'ordre du sérialiseur (tâche 2.6).
RUN_DETAIL_KEYS = [
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
]
#: Clés d'une comparaison, dans l'ordre du sérialiseur (tâche 2.6).
COMPARISON_KEYS = [
    "empreinte",
    "noms",
    "colonnes",
    "lignes",
    "factice",
    "partiel",
    "cartes",
    "synthese",
]
JSON_SNAPSHOT_KEYS = {
    ("audios", "list"): ["schema", "input_dir", "audios"],
    ("data", "check"): ["schema", "data_dir", "folders"],
    ("engines", "list"): ["schema", "engines"],
    ("engines", "log"): ["schema", "engine", "name", "factice", "limit", "lines"],
    ("models", "list"): ["schema", "models"],
    ("run", "options"): [
        "schema",
        "models",
        "audios",
        "preparation",
        "boolean_values",
    ],
    ("results", "list"): ["schema", "sort", "groups"],
    ("results", "history"): ["schema", "executions"],
    ("results", "explain"): ["schema", "title", "intro", "sections"],
    ("results", "show"): ["schema", *RUN_DETAIL_KEYS],
    ("compare",): ["schema", *COMPARISON_KEYS],
}
#: Clés d'un modèle proposable, dans l'ordre du sérialiseur (tâche 2.4).
MODEL_OPTION_KEYS = [
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
]
#: Clés d'un réglage déclaré, dans l'ordre du sérialiseur (tâche 2.4).
SETTING_KEYS = ["nom", "libelle", "type_valeur", "defaut", "description", "valeurs"]
#: Clés d'une préparation appliquée, dans l'ordre du sérialiseur (tâche 2.4).
PREPARATION_KEYS = [
    "modele",
    "moteur",
    "audios",
    "notice",
    "threads",
    "reglages",
    "reinitialisation",
    "applicable",
    "reference",
]
#: Clés d'une ligne de la liste des exécutions (tâche 2.5).
EXECUTION_LISTING_KEYS = [
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
]
#: Clés d'un groupe d'empreinte, dans l'ordre du sérialiseur (tâche 2.5).
HASH_GROUP_KEYS = [
    "empreinte",
    "noms",
    "duree_decodee_commune_s",
    "durees_divergentes",
    "entrees_reelles",
    "entrees_simulees",
]
#: Clés d'un essai groupé par empreinte, dans l'ordre du sérialiseur (tâche 2.5).
HASH_ENTRY_KEYS = [
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
]
#: Clés d'une portion de texte de l'aide, dans l'ordre du module (tâche 2.5).
HELP_PART_KEYS = ["kind", "text"]


class CommandTestCase(unittest.TestCase):
    """Dossier de données temporaire et exécution réelle des commandes."""

    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name) / "data-projet"

    def run_command(self, argv: list[str]) -> tuple[int, str, str]:
        """Exécute une commande par `cli.main`, sorties capturées."""
        stdout, stderr = io.StringIO(), io.StringIO()
        with (
            mock.patch.object(paths, "DOSSIER_DATA", self.base),
            contextlib.redirect_stdout(stdout),
            contextlib.redirect_stderr(stderr),
        ):
            code = cli.main(argv)
        return code, stdout.getvalue(), stderr.getvalue()

    def assert_unlocked(self) -> None:
        """Le verrou d'instance est libéré : une autre session peut démarrer."""
        VerrouInstance(self.base).acquerir().liberer()


class AudiosListTest(CommandTestCase):
    """« audios list » : audios lisibles, illisibles, dossier absent, refus."""

    def create_audios(self) -> Path:
        """Un WAV lisible et un fichier .wav illisible, comme les tests du service."""
        folder = self.base / "audio"
        folder.mkdir(parents=True)
        ecrire_wav(folder / "b.wav", duree=0.5)
        (folder / "a.wav").write_bytes(b"pas de l'audio du tout" * 8)
        return folder

    def test_json_snapshot_keys_and_real_values(self) -> None:
        folder = self.create_audios()
        unreadable = folder / "a.wav"

        code, stdout, stderr = self.run_command(["audios", "list", "--json"])

        self.assertEqual(code, 0)
        self.assertEqual(stderr, "")
        lines = [line for line in stdout.splitlines() if line]
        self.assertEqual(len(lines), 1, "un seul objet JSON sur la sortie standard")
        data = json.loads(lines[0])
        self.assertEqual(list(data.keys()), JSON_SNAPSHOT_KEYS[("audios", "list")])
        self.assertEqual(data["schema"], 1)
        self.assertEqual(data["input_dir"], str(folder))
        self.assertEqual(
            [entry["nom"] for entry in data["audios"]], ["a.wav", "b.wav"]
        )
        unreadable_entry, readable_entry = data["audios"]
        self.assertEqual(list(unreadable_entry.keys()), AUDIO_ENTRY_KEYS)
        self.assertFalse(unreadable_entry["readable"])
        self.assertIn("lecture impossible", unreadable_entry["erreur"])
        self.assertEqual(unreadable_entry["taille_octets"], unreadable.stat().st_size)
        self.assertIsNone(unreadable_entry["duree_indicative"])
        self.assertTrue(readable_entry["readable"])
        self.assertIsNone(readable_entry["erreur"])
        self.assertAlmostEqual(readable_entry["duree_indicative"], 0.5, places=2)
        self.assert_unlocked()

    def test_text_output_lists_names_and_errors(self) -> None:
        folder = self.create_audios()

        code, stdout, stderr = self.run_command(["audios", "list"])

        self.assertEqual(code, 0)
        self.assertEqual(stderr, "")
        self.assertIn(f"Dossier d'entrée : {folder}", stdout)
        self.assertIn("b.wav", stdout)
        self.assertIn("lisible", stdout)
        self.assertIn("a.wav", stdout)
        self.assertIn("lecture impossible", stdout)

    def test_absent_input_folder_yields_empty_list(self) -> None:
        # La préparation de la session est neutralisée : le dossier d'entrée
        # n'existe pas, comme sur la page avant toute préparation, et la
        # commande le signale par une liste vide sans le créer.
        with mock.patch.object(paths, "preparer_dossiers_data", lambda base: {}):
            code, stdout, stderr = self.run_command(["audios", "list", "--json"])

        self.assertEqual(code, 0)
        data = json.loads(stdout)
        self.assertEqual(data["audios"], [])
        self.assertFalse((self.base / "audio").exists())

    def test_unreadable_folder_is_refused_like_the_page(self) -> None:
        (self.base / "audio").mkdir(parents=True)
        # Traduction propre à la commande d'une erreur d'accès au dossier : même
        # message que la page, diagnostic sans trace sur l'erreur standard, refus.
        with mock.patch.object(
            commands, "lister_audios", side_effect=PermissionError("refus simulé")
        ):
            code, stdout, stderr = self.run_command(["audios", "list", "--json"])

        self.assertEqual(code, cli.CODE_REFUS)
        self.assertEqual(stdout, "")
        self.assertIn("dossier d'entrée n'a pas pu être lu", stderr)
        self.assertNotIn("Traceback", stderr)
        self.assert_unlocked()


class DataCheckTest(CommandTestCase):
    """« data check » : préparation puis état des dossiers attendus."""

    def test_json_snapshot_keys_and_folder_state(self) -> None:
        code, stdout, stderr = self.run_command(["data", "check", "--json"])

        self.assertEqual(code, 0)
        self.assertEqual(stderr, "")
        data = json.loads(stdout)
        self.assertEqual(list(data.keys()), JSON_SNAPSHOT_KEYS[("data", "check")])
        self.assertEqual(data["schema"], 1)
        self.assertEqual(data["data_dir"], str(self.base))
        self.assertEqual(
            [folder["name"] for folder in data["folders"]], list(paths.DOSSIERS_DATA)
        )
        for folder in data["folders"]:
            self.assertEqual(list(folder.keys()), ["name", "path", "exists"])
            self.assertTrue(folder["exists"])
            self.assertEqual(folder["path"], str(self.base / folder["name"]))
        self.assert_unlocked()

    def test_text_output_reports_each_folder(self) -> None:
        code, stdout, stderr = self.run_command(["data", "check"])

        self.assertEqual(code, 0)
        self.assertEqual(stderr, "")
        self.assertIn("Dossiers de données vérifiés.", stdout)
        for name in paths.DOSSIERS_DATA:
            self.assertIn(f"{name} : {self.base / name}", stdout)
        self.assertIn("(présent)", stdout)
        self.assertNotIn("(absent)", stdout)


class EnginesListTest(CommandTestCase):
    """« engines list » : états du service, moteur factice signalé."""

    def create_failed_engine_journal(self) -> None:
        """Journal sans environnement : état échec du service, sans installation."""
        engines_dir = self.base / paths.NOM_DOSSIER_MOTEURS
        engines_dir.mkdir(parents=True)
        (engines_dir / f"faster-whisper{SUFFIXE_JOURNAL}").write_text(
            "2026-10-25T12:00:00+02:00 Installation de faster-whisper.\n",
            encoding="utf-8",
        )

    def test_json_snapshot_keys_and_real_states(self) -> None:
        self.create_failed_engine_journal()

        code, stdout, stderr = self.run_command(["engines", "list", "--json"])

        self.assertEqual(code, 0)
        self.assertEqual(stderr, "")
        data = json.loads(stdout)
        self.assertEqual(list(data.keys()), JSON_SNAPSHOT_KEYS[("engines", "list")])
        self.assertEqual(data["schema"], 1)
        states = {state["identifiant"]: state for state in data["engines"]}
        self.assertEqual(
            [state["identifiant"] for state in data["engines"]],
            ["faster-whisper", "transcribe-cpp", "transformers", "factice"],
        )
        # Trois états du service dans un même scénario : échec (journal sans
        # environnement), non installé, prêt (moteur factice signalé).
        self.assertEqual(states["faster-whisper"]["etat"], "echec")
        self.assertIn("réinstallation", states["faster-whisper"]["note"])
        self.assertEqual(states["transcribe-cpp"]["etat"], "non-installe")
        self.assertEqual(states["transformers"]["etat"], "non-installe")
        fake_state = states["factice"]
        self.assertEqual(list(fake_state.keys()), ENGINE_STATE_KEYS)
        self.assertEqual(fake_state["etat"], "pret")
        self.assertTrue(fake_state["factice"])
        self.assertFalse(fake_state["installable"])
        self.assertIn("factice", fake_state["note"])
        self.assertIsNone(fake_state["date_installation"])
        self.assertEqual(fake_state["versions"], [])
        self.assert_unlocked()

    def test_text_output_reports_each_engine_state(self) -> None:
        self.create_failed_engine_journal()

        code, stdout, stderr = self.run_command(["engines", "list"])

        self.assertEqual(code, 0)
        self.assertEqual(stderr, "")
        for identifiant in ("faster-whisper", "transcribe-cpp", "transformers", "factice"):
            self.assertIn(identifiant, stdout)
        self.assertIn("échec", stdout)
        self.assertIn("non installé", stdout)
        self.assertIn("prêt", stdout)
        self.assertIn("FACTICE", stdout)
        self.assertIn("réinstallation explicite nécessaire", stdout)


class EnginesLogTest(CommandTestCase):
    """« engines log » : limite, défaut, moteur inconnu, moteur factice."""

    def create_journal(self, line_count: int, engine: str = "faster-whisper") -> None:
        engines_dir = self.base / paths.NOM_DOSSIER_MOTEURS
        engines_dir.mkdir(parents=True)
        (engines_dir / f"{engine}{SUFFIXE_JOURNAL}").write_text(
            "\n".join(f"ligne {index}" for index in range(line_count)) + "\n",
            encoding="utf-8",
        )

    def test_json_snapshot_keys_limit_and_lines(self) -> None:
        self.create_journal(line_count=5)

        code, stdout, stderr = self.run_command(
            ["engines", "log", "faster-whisper", "--limit", "3", "--json"]
        )

        self.assertEqual(code, 0)
        self.assertEqual(stderr, "")
        data = json.loads(stdout)
        self.assertEqual(list(data.keys()), JSON_SNAPSHOT_KEYS[("engines", "log")])
        self.assertEqual(data["schema"], 1)
        self.assertEqual(data["engine"], "faster-whisper")
        self.assertFalse(data["factice"])
        self.assertEqual(data["limit"], 3)
        self.assertEqual(data["lines"], ["ligne 2", "ligne 3", "ligne 4"])
        arguments = cli.construire_analyseur(cli.COMMANDS).parse_args(
            ["engines", "log", "faster-whisper"]
        )
        self.assertEqual(arguments.limit, 2000)
        code, text, stderr = self.run_command(
            ["engines", "log", "faster-whisper", "--limit", "3"]
        )
        self.assertEqual((code, stderr), (0, ""))
        self.assertEqual(text.splitlines(), data["lines"])

    def test_unknown_engine_is_refused_without_trace(self) -> None:
        code, stdout, stderr = self.run_command(
            ["engines", "log", "moteur-inconnu", "--json"]
        )

        self.assertEqual(code, cli.CODE_REFUS)
        self.assertEqual(stdout, "")
        self.assertIn("moteur inconnu", stderr)
        self.assertNotIn("Traceback", stderr)
        self.assert_unlocked()

    def test_fake_engine_has_no_journal(self) -> None:
        code, stdout, stderr = self.run_command(["engines", "log", "factice", "--json"])

        self.assertEqual(code, 0)
        data = json.loads(stdout)
        self.assertTrue(data["factice"])
        self.assertEqual(data["lines"], [])

        code, stdout, _ = self.run_command(["engines", "log", "factice"])

        self.assertEqual(code, 0)
        self.assertIn(commands.FAKE_ENGINE_JOURNAL_MESSAGE, stdout)

    def test_limit_below_one_is_refused_at_parsing(self) -> None:
        # Une limite de 0 rendrait toutes les lignes (dernières lignes du
        # service) : refusée à l'analyse, code 2, avant toute session.
        with self.assertRaises(SystemExit) as exit_error:
            self.run_command(["engines", "log", "factice", "--limit", "0"])

        self.assertEqual(exit_error.exception.code, 2)


class ModelsListTest(CommandTestCase):
    """« models list » : inventaire mixte (prêt + manifeste incohérent), vide."""

    #: Dépôt et révision du modèle simulé : identifiants valides pour le service.
    MODEL_REPO = "org/modele-simule"
    MODEL_COMMIT = "0123456789abcdef0123456789abcdef01234567"
    MODEL_ENGINE = "faster-whisper"
    MODEL_DATE = "2026-11-12"
    MODEL_FILES = {"config.json": b"{}", "model.bin": b"poids-simule"}

    def write_local_model(self) -> str:
        """Écrit un modèle local prêt : manifeste cohérent et fichiers présents."""
        key = cle_stockage(self.MODEL_REPO, self.MODEL_COMMIT)
        model_dir = (
            self.base
            / paths.NOM_DOSSIER_MODELES
            / self.MODEL_ENGINE
            / key
        )
        files_dir = model_dir / NOM_DOSSIER_FICHIERS
        files_dir.mkdir(parents=True)
        for name, payload in self.MODEL_FILES.items():
            (files_dir / name).write_bytes(payload)
        manifest = {
            "moteur": self.MODEL_ENGINE,
            "cle": key,
            "identifiant": self.MODEL_REPO,
            "id_resolu": self.MODEL_REPO,
            "commit": self.MODEL_COMMIT,
            "famille": "whisper",
            "fichier_gguf": None,
            "fichiers": [
                {"nom": name, "taille": len(payload)}
                for name, payload in self.MODEL_FILES.items()
            ],
            "date": self.MODEL_DATE,
        }
        (model_dir / NOM_MARQUEUR).write_text(
            json.dumps(manifest), encoding="utf-8"
        )
        return key

    def write_inconsistent_model(self) -> None:
        """Manifeste incohérent : fichiers attendus absents, donc non prêt."""
        key = cle_stockage(self.MODEL_REPO, "fedcba9876543210fedcba9876543210fedcba98")
        model_dir = (
            self.base
            / paths.NOM_DOSSIER_MODELES
            / self.MODEL_ENGINE
            / key
        )
        model_dir.mkdir(parents=True)
        (model_dir / NOM_MARQUEUR).write_text(
            json.dumps(
                {
                    "moteur": self.MODEL_ENGINE,
                    "cle": key,
                    "identifiant": self.MODEL_REPO,
                    "id_resolu": self.MODEL_REPO,
                    "commit": "fedcba9876543210fedcba9876543210fedcba98",
                    "famille": "whisper",
                    "fichier_gguf": None,
                    "fichiers": [
                        {"nom": "model.bin", "taille": 14}
                    ],
                    "date": self.MODEL_DATE,
                }
            ),
            encoding="utf-8",
        )

    def test_json_snapshot_mixed_inventory_and_text_output(self) -> None:
        # Un seul scénario : modèle valide et manifeste incohérent côte à côte.
        # Le service ignore l'incohérence (défaut de fichier, déjà couvert par
        # ses tests propres) : la commande liste le modèle prêt, code 0, sans
        # diagnostic — comme la page Modèles.
        key = self.write_local_model()
        self.write_inconsistent_model()

        code, stdout, stderr = self.run_command(["models", "list", "--json"])

        self.assertEqual(code, 0)
        self.assertEqual(stderr, "")
        lines = [line for line in stdout.splitlines() if line]
        self.assertEqual(len(lines), 1, "un seul objet JSON sur la sortie standard")
        data = json.loads(lines[0])
        self.assertEqual(list(data.keys()), JSON_SNAPSHOT_KEYS[("models", "list")])
        self.assertEqual(data["schema"], 1)
        self.assertEqual(len(data["models"]), 1)
        model = data["models"][0]
        self.assertEqual(list(model.keys()), LOCAL_MODEL_KEYS)
        self.assertEqual(
            model["reference"], f"{self.MODEL_ENGINE}/{key}"
        )
        self.assertEqual(model["moteur"], self.MODEL_ENGINE)
        self.assertEqual(model["cle"], key)
        self.assertEqual(model["identifiant"], self.MODEL_REPO)
        self.assertEqual(model["id_resolu"], self.MODEL_REPO)
        self.assertEqual(model["commit"], self.MODEL_COMMIT)
        self.assertEqual(model["famille"], "whisper")
        self.assertIsNone(model["fichier_gguf"])
        self.assertEqual(
            model["fichiers"],
            [
                {"nom": name, "taille": len(payload)}
                for name, payload in self.MODEL_FILES.items()
            ],
        )
        self.assertEqual(
            model["taille_disque"],
            sum(
                chemin.stat().st_size
                for chemin in (
                    self.base
                    / paths.NOM_DOSSIER_MODELES
                    / self.MODEL_ENGINE
                    / key
                ).rglob("*")
                if chemin.is_file() and not chemin.is_symlink()
            ),
        )
        self.assertEqual(
            model["taille_distante"], sum(len(p) for p in self.MODEL_FILES.values())
        )
        self.assertEqual(model["date"], self.MODEL_DATE)

        code, text, stderr = self.run_command(["models", "list"])

        self.assertEqual((code, stderr), (0, ""))
        self.assertIn(self.MODEL_REPO, text)
        self.assertIn(f"moteur {self.MODEL_ENGINE}", text)
        self.assertIn("famille whisper", text)
        self.assertIn(f"référence : {self.MODEL_ENGINE}/{key}", text)
        self.assertIn(f"révision : {self.MODEL_COMMIT}", text)
        self.assertIn("fichier : model.bin", text)
        self.assertIn(f"ajouté le {self.MODEL_DATE}", text)
        self.assertNotIn("fedcba", text)
        self.assert_unlocked()

    def test_empty_inventory_lists_nothing(self) -> None:
        code, stdout, stderr = self.run_command(["models", "list", "--json"])

        self.assertEqual(code, 0)
        self.assertEqual(stderr, "")
        data = json.loads(stdout)
        self.assertEqual(list(data.keys()), JSON_SNAPSHOT_KEYS[("models", "list")])
        self.assertEqual(data["models"], [])

        code, text, stderr = self.run_command(["models", "list"])

        self.assertEqual((code, stderr), (0, ""))
        self.assertIn(commands.NO_MODEL_MESSAGE, text)
        self.assert_unlocked()


class RunOptionsTest(CommandTestCase):
    """« run options » : inventaire, préparation, sélection ordonnée, refus.

    Les modèles locaux sont écrits sur disque (manifestes cohérents, fichiers
    simulés) puis relus par le service de préparation ; la validation des
    valeurs périmées reste celle du service, couverte par ses tests propres —
    seule la traduction CLI (clés JSON, texte, code 2 du `notice`) est testée.
    """

    FW_ENGINE = "faster-whisper"
    FW_REPO = "org/modele-simule"
    FW_COMMIT = "0123456789abcdef0123456789abcdef01234567"
    TD_ENGINE = "transformers"
    TD_REPO = "org/modele-parakeet"
    TD_COMMIT = "89abcdef0123456789abcdef0123456789abcdef"
    TC_ENGINE = "transcribe-cpp"
    TC_REPO = "org/modele-gguf"
    TC_COMMIT = "00112233445566778899aabbccddeeff00112233"
    MODEL_FILES = {"config.json": b"{}", "model.bin": b"poids-simule"}

    def write_local_model(
        self, engine: str, family: str, repo: str, commit: str
    ) -> str:
        """Écrit un modèle local prêt pour un moteur et une famille donnés."""
        key = cle_stockage(repo, commit)
        model_dir = self.base / paths.NOM_DOSSIER_MODELES / engine / key
        files_dir = model_dir / NOM_DOSSIER_FICHIERS
        files_dir.mkdir(parents=True)
        for name, payload in self.MODEL_FILES.items():
            (files_dir / name).write_bytes(payload)
        manifest = {
            "moteur": engine,
            "cle": key,
            "identifiant": repo,
            "id_resolu": repo,
            "commit": commit,
            "famille": family,
            "fichier_gguf": None,
            "fichiers": [
                {"nom": name, "taille": len(payload)}
                for name, payload in self.MODEL_FILES.items()
            ],
            "date": "2026-11-12",
        }
        (model_dir / NOM_MARQUEUR).write_text(
            json.dumps(manifest), encoding="utf-8"
        )
        return key

    def write_readable_audios(self, *names: str) -> None:
        """Écrit des WAV lisibles dans le dossier d'entrée."""
        folder = self.base / "audio"
        folder.mkdir(parents=True)
        for name in names:
            ecrire_wav(folder / name, duree=0.5)

    def test_json_snapshot_inventory_defaults_and_synthetic_model(self) -> None:
        # Familles réelles avec réglages (faster-whisper/whisper) et sans
        # réglage (transformers/parakeet-tdt), plus le modèle synthétique du
        # moteur factice ajouté par le service ; un .wav illisible n'est pas
        # proposable, contrairement à « audios list ».
        fw_key = self.write_local_model(
            self.FW_ENGINE, "whisper", self.FW_REPO, self.FW_COMMIT
        )
        td_key = self.write_local_model(
            self.TD_ENGINE, "parakeet-tdt", self.TD_REPO, self.TD_COMMIT
        )
        folder = self.base / "audio"
        folder.mkdir(parents=True)
        ecrire_wav(folder / "a.wav", duree=0.5)
        (folder / "b.wav").write_bytes(b"pas de l'audio du tout" * 8)

        code, stdout, stderr = self.run_command(["run", "options", "--json"])

        self.assertEqual(code, 0)
        self.assertEqual(stderr, "")
        lines = [line for line in stdout.splitlines() if line]
        self.assertEqual(len(lines), 1, "un seul objet JSON sur la sortie standard")
        data = json.loads(lines[0])
        self.assertEqual(list(data.keys()), JSON_SNAPSHOT_KEYS[("run", "options")])
        self.assertEqual(data["schema"], 1)
        self.assertEqual(
            data["boolean_values"], {"true": "oui", "false": "non"}
        )
        self.assertEqual(
            [model["reference"] for model in data["models"]],
            [
                f"{self.FW_ENGINE}/{fw_key}",
                f"{self.TD_ENGINE}/{td_key}",
                f"factice/{CLE_MODELE_FACTICE}",
            ],
        )
        fw_model, td_model, synthetic_model = data["models"]
        self.assertEqual(list(fw_model.keys()), MODEL_OPTION_KEYS)
        self.assertTrue(fw_model["executable"])
        self.assertIsNone(fw_model["motif_non_executable"])
        self.assertFalse(fw_model["synthetique"])
        self.assertEqual(len(fw_model["reglages"]), 2)
        compute_type, beam_size = fw_model["reglages"]
        self.assertEqual(list(compute_type.keys()), SETTING_KEYS)
        self.assertEqual(compute_type["nom"], "compute_type")
        self.assertEqual(compute_type["type_valeur"], "choix")
        self.assertEqual(compute_type["defaut"], "int8")
        self.assertEqual(compute_type["valeurs"], ["int8", "float32"])
        self.assertEqual(beam_size["nom"], "beam_size")
        self.assertEqual(beam_size["type_valeur"], "entier")
        self.assertEqual(beam_size["defaut"], 5)
        # Famille sans réglage : la liste est vide, jamais inventée.
        self.assertEqual(td_model["famille"], "parakeet-tdt")
        self.assertEqual(td_model["reglages"], [])
        self.assertEqual(synthetic_model["synthetique"], True)
        self.assertEqual(synthetic_model["identifiant"], LIBELLE_MODELE_FACTICE)
        self.assertEqual(synthetic_model["commit"], "aucun")
        self.assertTrue(synthetic_model["executable"])
        # Seuls les audios lisibles sont proposables : b.wav illisible est exclu.
        self.assertEqual(len(data["audios"]), 1)
        self.assertEqual(list(data["audios"][0].keys()), AUDIO_ENTRY_KEYS)
        self.assertEqual(data["audios"][0]["nom"], "a.wav")
        self.assertTrue(data["audios"][0]["readable"])
        preparation = data["preparation"]
        self.assertEqual(list(preparation.keys()), PREPARATION_KEYS)
        self.assertTrue(preparation["applicable"])
        self.assertIsNone(preparation["notice"])
        self.assertIsNone(preparation["reinitialisation"])
        self.assertEqual(preparation["reference"], f"{self.FW_ENGINE}/{fw_key}")
        self.assertEqual(preparation["moteur"], self.FW_ENGINE)
        self.assertEqual(preparation["audios"], ["a.wav"])
        self.assertEqual(preparation["threads"], threads_par_defaut())
        self.assertEqual(
            preparation["reglages"],
            [
                {"reglage": compute_type, "valeur": "int8"},
                {"reglage": beam_size, "valeur": 5},
            ],
        )
        self.assert_unlocked()

    def test_json_selection_keeps_reference_and_audio_order(self) -> None:
        td_key = self.write_local_model(
            self.TD_ENGINE, "parakeet-tdt", self.TD_REPO, self.TD_COMMIT
        )
        self.write_readable_audios("a.wav", "b.wav")

        code, stdout, stderr = self.run_command(
            [
                "run",
                "options",
                "--model",
                f"{self.TD_ENGINE}/{td_key}",
                "--audio",
                "b.wav",
                "--audio",
                "a.wav",
                "--json",
            ]
        )

        # Commande propre : l'ordre des --audio reçus est conservé (lot
        # ordonné de la page), la famille sans réglage reste vide.
        self.assertEqual((code, stderr), (0, ""))
        preparation = json.loads(stdout)["preparation"]
        self.assertEqual(preparation["reference"], f"{self.TD_ENGINE}/{td_key}")
        self.assertEqual(preparation["moteur"], self.TD_ENGINE)
        self.assertEqual(preparation["audios"], ["b.wav", "a.wav"])
        self.assertEqual(preparation["reglages"], [])
        self.assertTrue(preparation["applicable"])

    def test_text_output_reports_inventory_threads_and_boolean_syntax(self) -> None:
        self.write_local_model(
            self.FW_ENGINE, "whisper", self.FW_REPO, self.FW_COMMIT
        )
        tc_key = self.write_local_model(
            self.TC_ENGINE, "whisper", self.TC_REPO, self.TC_COMMIT
        )
        self.write_readable_audios("a.wav")

        code, stdout, stderr = self.run_command(
            [
                "run",
                "options",
                "--model",
                f"{self.TC_ENGINE}/{tc_key}",
                "--audio",
                "a.wav",
            ]
        )

        self.assertEqual((code, stderr), (0, ""))
        self.assertIn("Modèles proposables :", stdout)
        self.assertIn(f"{self.TC_ENGINE}/{tc_key}", stdout)
        self.assertIn(f"factice/{CLE_MODELE_FACTICE}", stdout)
        self.assertIn(LIBELLE_MODELE_FACTICE, stdout)
        self.assertIn("modèle synthétique (moteur factice)", stdout)
        self.assertIn("Audios proposables :", stdout)
        self.assertIn("a.wav", stdout)
        self.assertIn(f"Threads par défaut : {threads_par_defaut()}", stdout)
        self.assertIn("Préparation appliquée :", stdout)
        self.assertIn("ordre de traitement : a.wav", stdout)
        # Réglages booléens : valeur et syntaxe du formulaire (oui/non).
        self.assertIn(
            "réglage no_mmap (Sans mmap) : non (booléen : oui ou non)", stdout
        )
        self.assertIn("réglage condition_on_prev_tokens", stdout)

    def test_stale_reference_is_replaced_then_refused_like_the_page(self) -> None:
        # Valeur nommée périmée : remplacée par le choix applicable, annoncée
        # par le `notice` du service, code 2 comme le statut 400 de la page —
        # le refus lui-même reste couvert par les tests du service.
        fw_key = self.write_local_model(
            self.FW_ENGINE, "whisper", self.FW_REPO, self.FW_COMMIT
        )
        self.write_readable_audios("a.wav")

        code, stdout, stderr = self.run_command(
            ["run", "options", "--model", f"{self.FW_ENGINE}/{'0' * 64}", "--json"]
        )

        self.assertEqual(code, cli.CODE_REFUS)
        self.assertIn("introuvable, périmé ou non exécutable", stderr)
        self.assertNotIn("Traceback", stderr)
        lines = [line for line in stdout.splitlines() if line]
        self.assertEqual(len(lines), 1, "le résultat reste écrit pour enchaîner")
        preparation = json.loads(lines[0])["preparation"]
        self.assertIn("introuvable, périmé ou non exécutable", preparation["notice"])
        self.assertEqual(preparation["reference"], f"{self.FW_ENGINE}/{fw_key}")
        self.assert_unlocked()

    def test_non_executable_model_shows_reason_and_is_refused_when_selected(self) -> None:
        # Registre injecté : une famille réelle non qualifiée donne un modèle
        # non exécutable avec son motif, le modèle synthétique restant le seul
        # exécutable ; le sélectionner revient au refus de la page (code 2).
        declaration = DeclarationAdaptateur(
            identifiant="moteur-test",
            nom="Moteur de test",
            fichier_requirements=None,
            regle_compatibilite="transformers-safetensors",
            familles=(Famille("famille-test", "Famille de test", qualifiee=False),),
        )
        registry = RegistreMoteurs()
        registry.enregistrer(declaration)
        registry.enregistrer(DECLARATION_FACTICE)
        test_key = self.write_local_model(
            "moteur-test", "famille-test", "org/modele-test", self.FW_COMMIT
        )
        self.write_readable_audios("a.wav")

        with mock.patch.object(
            composition, "creer_registre_fourni", lambda: registry
        ):
            code, stdout, stderr = self.run_command(["run", "options", "--json"])

        self.assertEqual((code, stderr), (0, ""))
        data = json.loads(stdout)
        test_model = data["models"][0]
        self.assertFalse(test_model["executable"])
        self.assertIn("non qualifiée", test_model["motif_non_executable"])
        # Le modèle synthétique est le seul exécutable : préparation par défaut.
        self.assertEqual(
            data["preparation"]["reference"], f"factice/{CLE_MODELE_FACTICE}"
        )

        with mock.patch.object(
            composition, "creer_registre_fourni", lambda: registry
        ):
            code, text, stderr = self.run_command(
                ["run", "options", "--model", f"moteur-test/{test_key}"]
            )

        self.assertEqual(code, cli.CODE_REFUS)
        self.assertIn("introuvable, périmé ou non exécutable", stderr)
        self.assertIn("NON EXÉCUTABLE", text)
        self.assertIn("non qualifiée", text)
        self.assert_unlocked()

#: Marques d'un essai observé : pas de moteur factice ni de mesures simulées.
MARKS_REAL = {"factice": False, "synthetique": True, "mesures_simulees": False}


class ResultsCommandsSocle(CommandTestCase):
    """Socle des commandes « results » : résultats synthétiques sur disque.

    Les fichiers de résultat sont les JSON synthétiques du harnais de la
    consultation (aucun moteur, aucun réseau) : le regroupement, les tris et la
    séparation observées/simulées restent couverts par les tests du service —
    seules les traductions propres à la commande y sont éprouvées ici.
    """

    REAL_MODEL = "org/modele-simule"
    INTERRUPTED_ID = "20240103-040506-aabbccdd"
    LATER_ID = "20240104-050607-ccddeeff"

    def write_real_execution(
        self,
        identifiant: str,
        *,
        etat: str = ETAT_TERMINEE,
        observation_audio=None,
        duree_transcription: float = 1.0,
        mesures_extra: dict | None = None,
    ) -> None:
        """Écrit un essai observé du même audio (empreinte A), complet ou non."""
        run = run_json(identifiant, etat=etat, **MARKS_REAL)
        run["demande"]["modele"]["identifiant"] = self.REAL_MODEL
        run["demande"]["modele"]["id_resolu"] = self.REAL_MODEL
        options: dict = dict(MARKS_REAL, duree_transcription=duree_transcription)
        extra = dict(mesures_extra or {})
        if observation_audio is not None:
            extra[CLE_OBSERVATION_AUDIO] = observation_audio
        if extra:
            options["mesures_extra"] = extra
        ecrire_execution(
            self.base,
            run,
            (resultat_empreinte(run, run["audios"][0], EMPREINTE_A, **options),),
        )

    def write_fake_execution(
        self, identifiant: str, *, etat: str = ETAT_TERMINEE
    ) -> None:
        """Écrit un essai factice du même audio : mesures simulées par défaut."""
        run = run_json(identifiant, etat=etat)
        ecrire_execution(
            self.base, run, (resultat_empreinte(run, run["audios"][0], EMPREINTE_A),)
        )


class ResultsListTest(ResultsCommandsSocle):
    """« results list » : groupes, sélections, états, mesures et tri."""

    def test_json_snapshot_groups_selections_and_measures(self) -> None:
        # Un seul scénario groupé : un essai observé avec observation système,
        # un essai interrompu (résultat partiel) et un essai factice, tous du
        # même audio (même empreinte) — réels et factices séparés.
        self.write_real_execution(
            IDENTIFIANT,
            observation_audio=observation(
                provenance=PROVENANCE_REELLE, cpu=cpu_systeme()
            ),
        )
        self.write_real_execution(self.INTERRUPTED_ID, etat=ETAT_INTERROMPUE)
        self.write_fake_execution(IDENTIFIANT_ANCIEN)

        code, stdout, stderr = self.run_command(["results", "list", "--json"])

        self.assertEqual(code, 0)
        self.assertEqual(stderr, "")
        lines = [line for line in stdout.splitlines() if line]
        self.assertEqual(len(lines), 1, "un seul objet JSON sur la sortie standard")
        data = json.loads(lines[0])
        self.assertEqual(list(data.keys()), JSON_SNAPSHOT_KEYS[("results", "list")])
        self.assertEqual(data["schema"], 1)
        self.assertEqual(data["sort"], "recent")
        self.assertEqual(len(data["groups"]), 1)
        group = data["groups"][0]
        self.assertEqual(list(group.keys()), HASH_GROUP_KEYS)
        self.assertEqual(group["empreinte"], EMPREINTE_A)
        self.assertEqual(group["noms"], ["a.wav"])
        self.assertEqual(group["duree_decodee_commune_s"], 2.0)
        self.assertFalse(group["durees_divergentes"])
        # Réels (complet et interrompu) séparés des mesures simulées.
        self.assertEqual(
            [entry["execution"] for entry in group["entrees_reelles"]],
            [self.INTERRUPTED_ID, IDENTIFIANT],
        )
        self.assertEqual(
            [entry["execution"] for entry in group["entrees_simulees"]],
            [IDENTIFIANT_ANCIEN],
        )
        interrupted, real = group["entrees_reelles"]
        self.assertEqual(list(real.keys()), HASH_ENTRY_KEYS)
        # Sélection `identifiant:ordre` de chaque essai : de quoi enchaîner.
        self.assertEqual(real["selection"], f"{IDENTIFIANT}:1")
        self.assertEqual(real["ordre"], 1)
        self.assertFalse(real["partiel"])
        self.assertFalse(real["simule"])
        self.assertEqual(real["modele"], self.REAL_MODEL)
        self.assertEqual(real["indicateurs"]["pic_memoire_octets"], 2048)
        # L'essai interrompu reste un résultat partiel, état explicite.
        self.assertTrue(interrupted["partiel"])
        self.assertEqual(interrupted["etat"], ETAT_INTERROMPUE)
        self.assertEqual(interrupted["libelle_etat"], "interrompue")
        # Mesures du moteur et contexte de l'ordinateur distincts : le pic du
        # moteur vaut 2048 octets, le CPU total de l'ordinateur 90 %.
        self.assertEqual(real["mesures"]["pic_memoire_octets"], 2048)
        system_observation = real["observation_systeme"]
        self.assertIsNone(system_observation["etat"])
        self.assertTrue(system_observation["lisible"])
        self.assertEqual(system_observation["cpu"]["pourcentage_moyen"], 90.0)
        # L'essai factice porte les marques consignées, sans être un zéro.
        fake = group["entrees_simulees"][0]
        self.assertTrue(fake["simule"])
        self.assertIn("MESURES SIMULÉES", fake["marques"])
        self.assertIn("FACTICE", fake["marques"])
        self.assertFalse(fake["partiel"])
        self.assert_unlocked()

    def test_sort_criterion_orders_essays_within_group(self) -> None:
        # Le critère reçu part au service : « temps » classe le plus rapide
        # d'abord, « recent » le plus récent d'abord ; les deux ordres diffèrent.
        self.write_real_execution(IDENTIFIANT, duree_transcription=1.0)
        self.write_real_execution(self.LATER_ID, duree_transcription=3.0)

        orders = {}
        for sort in ("temps", "recent"):
            with self.subTest(sort=sort):
                code, stdout, stderr = self.run_command(
                    ["results", "list", "--sort", sort, "--json"]
                )
                self.assertEqual((code, stderr), (0, ""))
                group = json.loads(stdout)["groups"][0]
                orders[sort] = [
                    entry["execution"] for entry in group["entrees_reelles"]
                ]
        self.assertEqual(orders["temps"], [IDENTIFIANT, self.LATER_ID])
        self.assertEqual(orders["recent"], [self.LATER_ID, IDENTIFIANT])
        self.assert_unlocked()

    def test_abandoned_essay_is_flagged_partial_in_list(self) -> None:
        self.write_real_execution(IDENTIFIANT, etat=ETAT_ABANDONNEE)

        code, stdout, stderr = self.run_command(["results", "list", "--json"])

        self.assertEqual((code, stderr), (0, ""))
        entry = json.loads(stdout)["groups"][0]["entrees_reelles"][0]
        self.assertEqual(entry["etat"], ETAT_ABANDONNEE)
        self.assertEqual(entry["libelle_etat"], "abandonnée")
        self.assertTrue(entry["partiel"])
        self.assert_unlocked()

    def test_text_output_groups_selections_and_states(self) -> None:
        self.write_real_execution(IDENTIFIANT)
        self.write_fake_execution(IDENTIFIANT_ANCIEN)
        self.write_real_execution(self.INTERRUPTED_ID, etat=ETAT_INTERROMPUE)

        code, stdout, stderr = self.run_command(["results", "list"])

        self.assertEqual((code, stderr), (0, ""))
        self.assertIn("Tri des essais : Plus récents", stdout)
        self.assertIn(f"Audio a.wav — empreinte {EMPREINTE_A}", stdout)
        self.assertIn("essais observés :", stdout)
        self.assertIn("mesures simulées :", stdout)
        self.assertIn(f"{IDENTIFIANT}:1 : {self.REAL_MODEL}", stdout)
        self.assertIn("interrompue", stdout)
        self.assertIn("MESURES SIMULÉES", stdout)
        # Mesures de premier niveau : valeurs absentes jamais remplacées par zéro.
        self.assertIn("transcription 1 s", stdout)
        self.assertIn("RAM moteur < 0,1 Mo", stdout)
        self.assertIn("CPU moteur 18 %", stdout)

    def test_empty_results_list_reports_nothing_to_group(self) -> None:
        code, stdout, stderr = self.run_command(["results", "list"])

        self.assertEqual((code, stderr), (0, ""))
        self.assertIn(commands.NO_GROUP_MESSAGE, stdout)

        code, stdout, stderr = self.run_command(["results", "list", "--json"])

        self.assertEqual(code, 0)
        data = json.loads(stdout)
        self.assertEqual(data["groups"], [])
        self.assert_unlocked()

    def test_sort_defaults_to_recent_and_ram_is_passed_through(self) -> None:
        # Le contrat propre à la commande : défaut « recent » comme la page et
        # critère transmis au service ; les tris eux-mêmes restent couverts par
        # les tests du service.
        arguments = cli.construire_analyseur(cli.COMMANDS).parse_args(
            ["results", "list"]
        )
        self.assertEqual(arguments.sort, "recent")

        self.write_real_execution(IDENTIFIANT)
        code, stdout, stderr = self.run_command(
            ["results", "list", "--sort", "ram", "--json"]
        )

        self.assertEqual((code, stderr), (0, ""))
        data = json.loads(stdout)
        self.assertEqual(data["sort"], "ram")

    def test_unknown_sort_is_refused_at_parsing_without_io(self) -> None:
        # Refus du tri inconnu à l'analyse : code 2 avant toute session, aucun
        # dossier de données créé ni lu.
        self.assertFalse(self.base.exists())
        with self.assertRaises(SystemExit) as exit_error:
            self.run_command(["results", "list", "--sort", "vitesse"])

        self.assertEqual(exit_error.exception.code, 2)
        self.assertFalse(self.base.exists())

    def test_reading_commands_never_rewrite_result_files(self) -> None:
        # « Aucune écriture hors récupération » : les commandes de lecture ne
        # touchent à aucun fichier du dossier des résultats.
        self.write_real_execution(IDENTIFIANT)
        self.write_fake_execution(IDENTIFIANT_ANCIEN)
        results_dir = self.base / "results"
        before = {
            chemin: chemin.read_bytes()
            for chemin in sorted(results_dir.rglob("*"))
            if chemin.is_file()
        }
        self.assertGreater(len(before), 2)

        for argv in (
            ["results", "list"],
            ["results", "list", "--sort", "ram", "--json"],
            ["results", "history", "--json"],
            ["results", "explain"],
            ["results", "show", IDENTIFIANT],
            ["compare", EMPREINTE_A, f"{IDENTIFIANT}:1", f"{IDENTIFIANT_ANCIEN}:1"],
        ):
            with self.subTest(argv=argv):
                code, _stdout, stderr = self.run_command(argv)
                self.assertEqual((code, stderr), (0, ""))

        after = {
            chemin: chemin.read_bytes()
            for chemin in sorted(results_dir.rglob("*"))
            if chemin.is_file()
        }
        self.assertEqual(after, before)
        self.assert_unlocked()


class ResultsHistoryTest(ResultsCommandsSocle):
    """« results history » : historique complet, états et non interprétables."""

    BAD_SCHEMA_ID = "20240104-050607-99aabbcc"

    def write_history(self) -> None:
        """Une exécution terminée, une abandonnée et une non interprétable."""
        execution_complete(self.base)
        ecrire_execution(
            self.base,
            run_json(
                IDENTIFIANT_ANCIEN,
                etat=ETAT_ABANDONNEE,
                audios=(("a.wav", STATUT_NON_TRAITE),),
            ),
        )
        ecrire_execution(self.base, run_json(self.BAD_SCHEMA_ID, schema=999))

    def test_json_snapshot_states_and_marks(self) -> None:
        self.write_history()

        code, stdout, stderr = self.run_command(["results", "history", "--json"])

        self.assertEqual(code, 0)
        self.assertEqual(stderr, "")
        lines = [line for line in stdout.splitlines() if line]
        self.assertEqual(len(lines), 1, "un seul objet JSON sur la sortie standard")
        data = json.loads(lines[0])
        self.assertEqual(list(data.keys()), JSON_SNAPSHOT_KEYS[("results", "history")])
        self.assertEqual(data["schema"], 1)
        self.assertEqual(
            [execution["identifiant"] for execution in data["executions"]],
            [self.BAD_SCHEMA_ID, IDENTIFIANT, IDENTIFIANT_ANCIEN],
        )
        non_interpretable, completed, abandoned = data["executions"]
        self.assertEqual(list(completed.keys()), EXECUTION_LISTING_KEYS)
        # Non interprétable : aucun fait inventé, motif du service conservé.
        self.assertFalse(non_interpretable["exploitable"])
        self.assertEqual(non_interpretable["libelle_etat"], "non interprétable")
        self.assertIsNone(non_interpretable["etat"])
        self.assertIsNone(non_interpretable["marques"])
        self.assertIsNone(non_interpretable["simule"])
        self.assertIn("schéma", non_interpretable["motif"])
        # Terminée, marquée factice et simulée : aucune omission.
        self.assertTrue(completed["exploitable"])
        self.assertEqual(completed["etat"], ETAT_TERMINEE)
        self.assertEqual(completed["libelle_etat"], "terminée")
        self.assertFalse(completed["partiel"])
        self.assertTrue(completed["simule"])
        self.assertIn("MESURES SIMULÉES", completed["marques"])
        self.assertEqual(completed["audios_traites"], 1)
        self.assertEqual(completed["audios_total"], 1)
        # Abandonnée : résultat partiel, audio non traité.
        self.assertEqual(abandoned["etat"], ETAT_ABANDONNEE)
        self.assertEqual(abandoned["libelle_etat"], "abandonnée")
        self.assertTrue(abandoned["partiel"])
        self.assertEqual(abandoned["audios_traites"], 0)
        self.assertEqual(abandoned["audios_total"], 1)
        self.assert_unlocked()

    def test_text_output_reports_states_in_recency_order(self) -> None:
        self.write_history()

        code, stdout, stderr = self.run_command(["results", "history"])

        self.assertEqual((code, stderr), (0, ""))
        self.assertIn("De la plus récente à la plus ancienne :", stdout)
        self.assertIn(f"{IDENTIFIANT} : terminée", stdout)
        self.assertIn(f"{IDENTIFIANT_ANCIEN} : abandonnée (résultats partiels)", stdout)
        self.assertIn(f"{self.BAD_SCHEMA_ID} : non interprétable", stdout)
        self.assertIn("schéma", stdout)
        self.assertIn("marques : FACTICE", stdout)

    def test_empty_history(self) -> None:
        code, stdout, stderr = self.run_command(["results", "history"])

        self.assertEqual((code, stderr), (0, ""))
        self.assertIn(commands.NO_EXECUTION_MESSAGE, stdout)


class ResultsExplainTest(ResultsCommandsSocle):
    """« results explain » : la source unique d'aide, texte et JSON."""

    def test_json_snapshot_help_structure(self) -> None:
        code, stdout, stderr = self.run_command(["results", "explain", "--json"])

        self.assertEqual(code, 0)
        self.assertEqual(stderr, "")
        lines = [line for line in stdout.splitlines() if line]
        self.assertEqual(len(lines), 1, "un seul objet JSON sur la sortie standard")
        data = json.loads(lines[0])
        self.assertEqual(list(data.keys()), JSON_SNAPSHOT_KEYS[("results", "explain")])
        self.assertEqual(data["schema"], 1)
        self.assertEqual(data["title"], "Comprendre les indicateurs")
        # Introduction : portions typées, texte intégral de la page d'aide.
        self.assertEqual(len(data["intro"]), 1)
        self.assertEqual(list(data["intro"][0].keys()), HELP_PART_KEYS)
        self.assertIn("trois repères des cartes", data["intro"][0]["text"])
        sections = data["sections"]
        self.assertGreater(len(sections), 8)
        self.assertEqual(list(sections[0].keys()), ["title", "blocks"])
        titles = [section["title"] for section in sections]
        self.assertIn("Contexte de l'ordinateur", titles)
        self.assertIn("Limites d'interprétation", titles)
        # Blocs typés : paragraphe, définitions et liste.
        blocks = {
            block["type"]: block
            for section in sections
            for block in section["blocks"]
        }
        self.assertEqual(
            set(blocks), {"paragraph", "definitions", "list"},
            "les trois natures de bloc de la source unique",
        )
        definitions = blocks["definitions"]["entries"]
        terms = [entry["term"][0]["text"] for entry in definitions]
        self.assertEqual(terms, ["Transcription", "Mémoire max", "CPU du moteur"])
        self.assert_unlocked()

    def test_text_output_prints_the_shared_help(self) -> None:
        # Même source que la page web : les phrases clés de l'aide s'y
        # retrouvent, preuves visibles de l'absence de copie parallèle.
        code, stdout, stderr = self.run_command(["results", "explain"])

        self.assertEqual((code, stderr), (0, ""))
        self.assertIn("Comprendre les indicateurs", stdout)
        self.assertIn(
            "sans rien mesurer sur l'ordinateur qui consulte", stdout
        )
        self.assertIn("100 × temps CPU", stdout)
        self.assertIn("Le CPU total inclut les autres programmes", stdout)
        self.assertIn("n'est jamais remplacée par zéro", stdout)
        self.assertIn("Le repère d'objectif est 2", stdout)
        # Exemples produits par les mêmes formateurs que la page.
        self.assertIn("< 0,1 s", stdout)
        self.assertIn("2,4 Go", stdout)


class ResultsShowTest(ResultsCommandsSocle):
    """« results show » : détail JSON ordonné, texte complet et refus à code 2."""

    BROKEN_ID = "20240106-070809-33334444"

    def test_json_snapshot_keeps_engine_and_computer_measures_apart(self) -> None:
        self.write_real_execution(
            IDENTIFIANT,
            observation_audio=observation(
                provenance=PROVENANCE_REELLE, cpu=cpu_systeme()
            ),
        )

        code, stdout, stderr = self.run_command(
            ["results", "show", IDENTIFIANT, "--json"]
        )

        self.assertEqual((code, stderr), (0, ""))
        lines = [line for line in stdout.splitlines() if line]
        self.assertEqual(len(lines), 1, "un seul objet JSON sur la sortie standard")
        data = json.loads(lines[0])
        self.assertEqual(list(data.keys()), JSON_SNAPSHOT_KEYS[("results", "show")])
        self.assertEqual(data["schema"], 1)
        self.assertEqual(data["execution"]["identifiant"], IDENTIFIANT)
        self.assertFalse(data["partiel"])
        self.assertFalse(data["simule"])
        audio = data["audios"][0]
        # Transcription complète, sans troncature.
        self.assertEqual(
            audio["transcription"]["texte"], "transcription simulée de test"
        )
        # Mesures du moteur et contexte de l'ordinateur : deux objets distincts.
        self.assertEqual(audio["indicateurs"]["pic_memoire_octets"], 2048)
        self.assertEqual(
            audio["observation_systeme"]["cpu"]["pourcentage_moyen"], 90.0
        )
        self.assert_unlocked()

    def test_absent_engine_measure_stays_null_not_zero(self) -> None:
        self.write_real_execution(
            IDENTIFIANT, mesures_extra={"pic_memoire_octets": None}
        )

        code, stdout, stderr = self.run_command(
            ["results", "show", IDENTIFIANT, "--json"]
        )

        self.assertEqual((code, stderr), (0, ""))
        audio = json.loads(stdout)["audios"][0]
        self.assertIsNone(audio["indicateurs"]["pic_memoire_octets"])
        code, stdout, stderr = self.run_command(["results", "show", IDENTIFIANT])
        self.assertIn("RAM moteur non mesuré", stdout)
        self.assertNotIn("RAM moteur 0", stdout)
        self.assert_unlocked()

    def test_text_output_flags_simulated_and_partial_with_full_text(self) -> None:
        self.write_fake_execution(IDENTIFIANT, etat=ETAT_INTERROMPUE)

        code, stdout, stderr = self.run_command(["results", "show", IDENTIFIANT])

        self.assertEqual((code, stderr), (0, ""))
        self.assertIn(
            f"Exécution {IDENTIFIANT} : interrompue (résultats partiels)", stdout
        )
        self.assertIn(commands.SIMULATED_MEASURES_MESSAGE, stdout)
        self.assertIn("Audio 1 : a.wav", stdout)
        self.assertIn(
            "Transcription complète :\ntranscription simulée de test", stdout
        )
        # Aucun relevé de l'ordinateur consigné : dit tel quel, jamais inventé.
        self.assertIn("Contexte de l'ordinateur : aucun relevé consigné", stdout)
        self.assert_unlocked()

    def test_refused_identifiers_exit_2_without_result_output(self) -> None:
        ecrire_execution(self.base, run_json(self.BROKEN_ID, schema=999))
        refused = (
            ("absent", "20240109-000000-deadbeef"),
            ("hostile", "../secret"),
            ("non interprétable", self.BROKEN_ID),
        )
        for label, identifiant in refused:
            with self.subTest(label):
                code, stdout, stderr = self.run_command(
                    ["results", "show", identifiant]
                )
                self.assertEqual(code, 2)
                self.assertEqual(stdout, "")
                self.assertTrue(stderr.startswith(DIAGNOSTIC_PREFIX))
        self.assertIn(MESSAGE_RESULTAT_NON_INTERPRETABLE, stderr)
        self.assert_unlocked()


class CompareTest(ResultsCommandsSocle):
    """« compare » : ordre reçu, contrat JSON et refus à code 2."""

    OTHER_HASH_ID = "20240105-060708-11112222"

    def test_json_snapshot_keeps_received_order(self) -> None:
        self.write_real_execution(IDENTIFIANT)
        self.write_real_execution(self.LATER_ID, duree_transcription=3.0)
        selections = [f"{self.LATER_ID}:1", f"{IDENTIFIANT}:1"]

        code, stdout, stderr = self.run_command(
            ["compare", EMPREINTE_A, *selections, "--json"]
        )

        self.assertEqual((code, stderr), (0, ""))
        data = json.loads(stdout)
        self.assertEqual(list(data.keys()), JSON_SNAPSHOT_KEYS[("compare",)])
        self.assertEqual(data["schema"], 1)
        self.assertEqual(data["empreinte"], EMPREINTE_A)
        # Ordre reçu conservé, dans les colonnes comme dans les cartes.
        self.assertEqual([card["selection"] for card in data["cartes"]], selections)
        self.assertEqual(
            [column["selection"] for column in data["colonnes"]], selections
        )
        self.assertEqual(data["cartes"][0]["texte"], "transcription simulée de test")
        self.assertEqual(
            data["cartes"][0]["indicateurs"]["duree_transcription_s"], 3.0
        )
        self.assertFalse(data["factice"])
        self.assertFalse(data["partiel"])
        self.assert_unlocked()

    def test_text_output_flags_simulated_and_partial_cards(self) -> None:
        self.write_real_execution(IDENTIFIANT)
        self.write_fake_execution(self.INTERRUPTED_ID, etat=ETAT_INTERROMPUE)

        code, stdout, stderr = self.run_command(
            ["compare", EMPREINTE_A, f"{IDENTIFIANT}:1", f"{self.INTERRUPTED_ID}:1"]
        )

        self.assertEqual((code, stderr), (0, ""))
        self.assertIn(commands.SIMULATED_COMPARISON_MESSAGE, stdout)
        self.assertIn(commands.PARTIAL_COMPARISON_MESSAGE, stdout)
        # Une seule mesure observée comparable : aucune distinction attribuée.
        self.assertIn(commands.NO_SYNTHESIS_MESSAGE, stdout)
        self.assertIn("Exclues de la synthèse", stdout)
        # Chaque essai garde son texte complet, dans l'ordre reçu.
        self.assertEqual(stdout.count("transcription simulée de test"), 2)
        self.assertLess(
            stdout.index(f"1. {IDENTIFIANT}:1"),
            stdout.index(f"2. {self.INTERRUPTED_ID}:1"),
        )
        self.assert_unlocked()

    def test_refused_selections_and_hashes_exit_2_without_output(self) -> None:
        self.write_real_execution(IDENTIFIANT)
        self.write_real_execution(self.LATER_ID)
        # Un essai d'un autre fichier audio (empreinte B), hors du groupe A.
        other = run_json(self.OTHER_HASH_ID)
        ecrire_execution(
            self.base,
            other,
            (resultat_empreinte(other, other["audios"][0], EMPREINTE_B),),
        )
        un_seul = f"{IDENTIFIANT}:1"
        refused = (
            ("une seule sélection", ["compare", EMPREINTE_A, un_seul]),
            (
                "même essai deux fois",
                ["compare", EMPREINTE_A, un_seul, un_seul],
            ),
            (
                "hors du groupe",
                ["compare", EMPREINTE_A, un_seul, f"{self.OTHER_HASH_ID}:1"],
            ),
            (
                "ordre inconnu",
                ["compare", EMPREINTE_A, un_seul, f"{IDENTIFIANT}:9"],
            ),
            (
                "empreinte invalide",
                ["compare", "non-sha", un_seul, f"{self.LATER_ID}:1"],
            ),
            (
                "plus de 64 sélections",
                ["compare", EMPREINTE_A, *([un_seul] * 65)],
            ),
        )
        for label, argv in refused:
            with self.subTest(label):
                code, stdout, stderr = self.run_command(argv)
                self.assertEqual(code, 2)
                self.assertEqual(stdout, "")
                self.assertTrue(stderr.startswith(DIAGNOSTIC_PREFIX))
        self.assert_unlocked()

    def test_malformed_selection_is_refused_at_parsing_without_io(self) -> None:
        self.assertFalse(self.base.exists())
        for selection in ("sans-separateur", f"{IDENTIFIANT}:0", f"{IDENTIFIANT}:1:2"):
            with self.subTest(selection=selection):
                with self.assertRaises(SystemExit) as exit_error:
                    self.run_command(["compare", EMPREINTE_A, selection, selection])
                self.assertEqual(exit_error.exception.code, 2)
        self.assertFalse(self.base.exists())


if __name__ == "__main__":
    unittest.main()
