"""Tests transversaux des commandes CLI (tâche 4.2).

Complément des tests par commande : des gardes qui parcourent le registre des
commandes plutôt qu'une commande isolée, sans moteur réel ni réseau.

- **Processus sans bibliothèque de moteur** : un sous-processus exécute toutes
  les commandes de lecture, une exécution factice et des refus, puis rapporte
  les modules de moteur chargés dans son `sys.modules`.
- **Aucune dépendance ajoutée** : les dépendances déclarées de `pyproject.toml`
  et l'entrée du projet dans `uv.lock` sont verrouillées, et les imports de
  premier niveau des modules du programme restent limités à la bibliothèque
  standard, au projet et aux dépendances déclarées (les imports différés des
  adaptateurs de moteur, faits dans le sous-processus du moteur, sont exclus).
- **Lecture hors ligne** : chaque commande de lecture réussit avec `socket`
  bloqué, donc sans aucune tentative de connexion.
- **Aucune écriture hors `data/`** : l'arborescence et les contenus hors du
  dossier de données sont comparés avant/après, dossier courant compris, y
  compris pour une exécution factice (qui écrit dans `data/`).
- **Chemins sortants refusés** : tout nom, clé ou identifiant hostile donné
  à une commande qui en prend un est refusé (code 2) avec le motif de la
  couche qui contrôle cette position, sans toucher une sentinelle posée hors
  de `data/` et réellement visée : remontée, chemin absolu, lien symbolique
  sortant.
- **Instantanés exhaustifs** : chaque commande enregistrée dans `COMMANDS` doit
  posséder une entrée dans `JSON_SNAPSHOT_KEYS` (les clés de son contrat JSON,
  établies commande par commande dans les tâches 2.x et 3.x) ; une commande
  nouvelle sans instantané fait échouer la suite.
"""

from __future__ import annotations

import ast
import contextlib
import io
import json
import socket
import subprocess
import sys
import tempfile
import tomllib
import unittest
from pathlib import Path
from typing import Any
from unittest import mock

from tests.test_audios import ecrire_wav
from tests.test_cli import PAQUETS_MOTEURS
from tests.test_commands import JSON_SNAPSHOT_KEYS, MARKS_REAL
from tests.test_comparaison_resultats import EMPREINTE_A, resultat_empreinte
from tests.test_consultation_resultats import IDENTIFIANT, ecrire_execution, run_json
from transcription_bench import cli, paths
from transcription_bench.command_session import (
    CODE_REFUS,
    CODE_SUCCESS,
    CommandGroup,
)
from transcription_bench.commands import COMMANDS
from transcription_bench.executions import CLE_MODELE_FACTICE
from transcription_bench.instance import VerrouInstance

#: Racine du dépôt, pour lire `pyproject.toml`, `uv.lock` et les modules.
RACINE = Path(__file__).resolve().parents[1]

#: Référence du modèle synthétique du moteur factice, exécutable sans moteur réel.
REFERENCE_FACTICE = f"factice/{CLE_MODELE_FACTICE}"

#: Modèle d'essai observé, comme les fixtures des commandes « results ».
MODELE_REEL = "org/modele-simule"

#: Deux essais observés d'un même audio (empreinte A), pour « show » et « compare ».
IDENTIFIANT_AUTRE = "20240104-050607-ccddeeff"

#: Placeholder remplacé par chaque valeur hostile dans les commandes
#: ci-dessous : la cible est créée par le test, hors du dossier de données.
HOSTILE = "{hostile}"

#: Commandes de lecture : aucune ne doit toucher le réseau (design D9).
COMMANDES_LECTURE: tuple[list[str], ...] = (
    ["audios", "list"],
    ["data", "check"],
    ["engines", "list"],
    ["engines", "log", "factice"],
    ["models", "list"],
    ["run", "options"],
    ["run", "check", "--model", REFERENCE_FACTICE, "--audio", "a.wav"],
    ["results", "list"],
    ["results", "history"],
    ["results", "explain"],
    ["results", "show", IDENTIFIANT],
    ["compare", EMPREINTE_A, f"{IDENTIFIANT}:1", f"{IDENTIFIANT_AUTRE}:1"],
)

#: Refus attendus dans le sous-processus : arguments hostiles ou ressources
#: inconnues, choisis pour ne déclencher ni réseau ni installation réelle.
COMMANDES_REFUSEES: tuple[list[str], ...] = (
    ["engines", "install", "moteur-inconnu"],
    ["models", "check", "../secret", "--engine", "faster-whisper"],
    ["models", "download", "../secret", "--engine", "faster-whisper"],
    ["models", "delete", "factice", "cle-invalide"],
)

#: Chaque commande prenant un nom, une clé ou un identifiant, avec `HOSTILE`
#: dans cette position et le motif de refus attendu sur la sortie d'erreur :
#: la couche qui contrôle cette position (registre des moteurs, forme de
#: référence, liste des audios lisibles, résolution de chemin) refuse avant
#: tout accès au système de fichiers — jamais un « introuvable » obtenu en
#: suivant le chemin hors du dossier autorisé. Une commande future qui en
#: prend un doit s'ajouter ici pour que le refus reste garanti.
COMMANDES_NOM_CLE_IDENTIFIANT: tuple[tuple[str, list[str], tuple[str, ...]], ...] = (
    ("engines log, identifiant", ["engines", "log", HOSTILE], ("moteur inconnu",)),
    ("engines install, identifiant", ["engines", "install", HOSTILE], ("moteur inconnu",)),
    (
        "models check, dépôt",
        ["models", "check", HOSTILE, "--engine", "faster-whisper"],
        ("identifiant de modèle refusé",),
    ),
    (
        "models check, moteur",
        ["models", "check", "org/modele", "--engine", HOSTILE],
        ("moteur inconnu",),
    ),
    (
        "models download, dépôt",
        ["models", "download", HOSTILE, "--engine", "faster-whisper"],
        ("identifiant de modèle refusé",),
    ),
    (
        "models download, moteur",
        ["models", "download", "org/modele", "--engine", HOSTILE],
        ("moteur inconnu",),
    ),
    ("models delete, moteur", ["models", "delete", HOSTILE, "cle-invalide"], ("moteur inconnu",)),
    ("models delete, clé", ["models", "delete", "factice", HOSTILE], ("clé de modèle invalide",)),
    ("run options, modèle", ["run", "options", "--model", HOSTILE], ("introuvable, périmé ou non exécutable",)),
    (
        "run options, audio",
        ["run", "options", "--audio", HOSTILE],
        ("absent de la liste des audios lisibles",),
    ),
    (
        "run check, modèle",
        ["run", "check", "--model", HOSTILE, "--audio", "a.wav"],
        ("référence de modèle invalide",),
    ),
    (
        "run check, audio",
        ["run", "check", "--model", REFERENCE_FACTICE, "--audio", HOSTILE],
        ("hors de la liste du dossier d'entrée",),
    ),
    (
        "run start, modèle",
        ["run", "start", "--model", HOSTILE, "--audio", "a.wav"],
        ("référence de modèle invalide",),
    ),
    (
        "run start, audio",
        ["run", "start", "--model", REFERENCE_FACTICE, "--audio", HOSTILE],
        ("hors de la liste du dossier d'entrée",),
    ),
    ("results show, identifiant", ["results", "show", HOSTILE], ("chemin refusé", "chemin absolu refusé")),
    (
        "compare, empreinte",
        ["compare", HOSTILE, f"{IDENTIFIANT}:1", f"{IDENTIFIANT_AUTRE}:1"],
        ("empreinte SHA-256 invalide",),
    ),
    (
        "compare, sélection",
        ["compare", EMPREINTE_A, f"{HOSTILE}:1", f"{IDENTIFIANT}:1"],
        ("sélection refusée",),
    ),
)

#: Dépendances déclarées du programme : en ajouter une est une décision
#: explicite, qui doit passer par ce verrou (design D9, aucune dépendance
#: nouvelle sans accord).
DEPENDANCES_ATTENDUES = (
    "av",
    "flask==3.1.3",
    "huggingface_hub",
    "numpy",
    "psutil",
    "waitress==3.0.2",
)
NOMS_DEPENDANCES = ("av", "flask", "huggingface-hub", "numpy", "psutil", "waitress")
#: Noms de modules des dépendances déclarées, pour le garde des imports.
MODULES_DEPENDANCES = ("av", "flask", "huggingface_hub", "numpy", "psutil", "waitress")
#: Dépendances transitives déjà importées par le code existant avant les
#: commandes : `httpx2` (via huggingface-hub, dans les clients de vérification
#: et de téléchargement) et `werkzeug` (via flask, dans l'application web).
#: Elles restent hors `pyproject.toml` ; ce garde signale tout autre import
#: tierce, qui devra être déclaré — et donc passer le verrou précédent.
MODULES_TRANSITIFS_IMPORTES = ("httpx2", "werkzeug")

#: Délai borné du sous-processus qui exécute les commandes, comme `test_cli`.
DELAI_PROCESSUS = 120.0

#: Code exécuté dans un processus neuf : toutes les commandes de lecture, une
#: exécution factice puis des refus, puis le rapport des modules de moteur
#: chargés dans le processus. Les sorties des commandes sont capturées : seul
#: le rapport final va sur la sortie standard, les diagnostics restent capturés.
CODE_COMMANDES = """
import contextlib, io, json, sys
from pathlib import Path
from transcription_bench import cli, paths

paths.DOSSIER_DATA = Path(sys.argv[1])
codes = []
for argv in json.loads(sys.argv[2]):
    sortie, erreur = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(sortie), contextlib.redirect_stderr(erreur):
        codes.append(cli.main(argv))
moteurs = sorted(m for m in sys.modules if m.split(".")[0] in __PAQUETS__)
print(json.dumps({"codes": codes, "moteurs": moteurs}))
""".replace("__PAQUETS__", repr(PAQUETS_MOTEURS))


class TransversalSocle(unittest.TestCase):
    """Dossier de données temporaire, dossier courant séparé, exécution des commandes.

    Le dossier courant est un répertoire vide distinct de `data/` : toute
    écriture accidentelle « à l'endroit où la commande a été lancée » y serait
    visible. Les fixtures sont l'audio et les essais synthétiques du harnais
    existant, sans moteur ni réseau.
    """

    def setUp(self) -> None:
        temporaire = tempfile.TemporaryDirectory()
        self.addCleanup(temporaire.cleanup)
        self.root = Path(temporaire.name)
        self.base = self.root / "data-projet"
        self.cwd = self.cwd_dir()
        self.ecrire_fixtures()

    def cwd_dir(self) -> Path:
        """Crée le dossier courant vide, hors du dossier de données."""
        dossier = self.root / "dossier-courant"
        dossier.mkdir()
        return dossier

    def ecrire_fixtures(self) -> None:
        """Un audio lisible et deux essais observés d'une même empreinte."""
        dossier_audio = self.base / "audio"
        dossier_audio.mkdir(parents=True)
        ecrire_wav(dossier_audio / "a.wav", duree=0.5)
        for identifiant in (IDENTIFIANT, IDENTIFIANT_AUTRE):
            run = run_json(identifiant, **MARKS_REAL)
            run["demande"]["modele"]["identifiant"] = MODELE_REEL
            run["demande"]["modele"]["id_resolu"] = MODELE_REEL
            ecrire_execution(
                self.base,
                run,
                (
                    resultat_empreinte(
                        run,
                        run["audios"][0],
                        EMPREINTE_A,
                        **dict(MARKS_REAL, duree_transcription=1.0),
                    ),
                ),
            )

    def run_command(self, argv: list[str]) -> tuple[int, str, str]:
        """Exécute une commande par `cli.main` depuis le dossier courant vide.

        Un refus à l'analyse des arguments lève `SystemExit` (code 2 d'argparse) :
        il est ramené au code de retour pour l'homogénéité des assertions.
        """
        stdout, stderr = io.StringIO(), io.StringIO()
        with (
            mock.patch.object(paths, "DOSSIER_DATA", self.base),
            contextlib.chdir(self.cwd),
            contextlib.redirect_stdout(stdout),
            contextlib.redirect_stderr(stderr),
        ):
            try:
                code = cli.main(argv)
            except SystemExit as sortie_analyse:
                code = sortie_analyse.code
        return code, stdout.getvalue(), stderr.getvalue()

    def empreinte_hors_data(self) -> tuple[dict[str, bytes], frozenset[str]]:
        """Fichiers (contenu compris) et dossiers hors du dossier de données."""
        fichiers: dict[str, bytes] = {}
        dossiers: set[str] = set()
        for chemin in self.root.rglob("*"):
            if chemin == self.base or self.base in chemin.parents:
                continue
            relatif = chemin.relative_to(self.root).as_posix()
            if chemin.is_dir():
                dossiers.add(relatif)
            elif chemin.is_file():
                fichiers[relatif] = chemin.read_bytes()
        return fichiers, frozenset(dossiers)

    def result_ids(self) -> frozenset[str]:
        """Identifiants d'exécution actuellement présents sous `data/results`."""
        return frozenset(chemin.name for chemin in (self.base / "results").iterdir())

    def assert_unlocked(self) -> None:
        """Le verrou d'instance est libéré : une autre session peut démarrer."""
        VerrouInstance(self.base).acquerir().liberer()


class LectureHorsLigneEtEcrituresTest(TransversalSocle):
    """Commandes de lecture : hors réseau, sans écriture hors `data/`."""

    def test_les_commandes_de_lecture_reussissent_sans_acces_reseau(self) -> None:
        appels: list[str] = []

        def bloquer(nom: str):
            def refuser(*args: Any, **kwargs: Any) -> None:
                appels.append(nom)
                raise OSError(f"accès réseau bloqué pendant le test : {nom}")

            return refuser

        with (
            mock.patch("socket.socket", bloquer("socket")),
            mock.patch("socket.getaddrinfo", bloquer("getaddrinfo")),
        ):
            for argv in COMMANDES_LECTURE:
                with self.subTest(commande=" ".join(argv)):
                    code, stdout, stderr = self.run_command(argv)
                    self.assertEqual(code, CODE_SUCCESS, stderr)
                    self.assertEqual(stderr, "")
        self.assertEqual(
            appels, [], "tentative d'accès réseau pendant une commande de lecture"
        )
        self.assert_unlocked()

    def test_les_commandes_n_ecrivent_rien_hors_du_dossier_data(self) -> None:
        sentinelle = self.root / "sentinelle"
        sentinelle.mkdir()
        (sentinelle / "fichier.txt").write_text("preuve", encoding="utf-8")
        commandes = [
            *COMMANDES_LECTURE,
            ["run", "start", "--model", REFERENCE_FACTICE, "--audio", "a.wav"],
        ]
        identifiants_avant = self.result_ids()
        sorties: list[str] = []
        for argv in commandes:
            with self.subTest(commande=" ".join(argv)):
                avant = self.empreinte_hors_data()
                code, stdout, stderr = self.run_command(argv)
                sorties.append(stdout)
                self.assertEqual((code, stderr), (CODE_SUCCESS, ""))
                self.assertEqual(
                    self.empreinte_hors_data(),
                    avant,
                    "fichier ou dossier créé, modifié ou supprimé hors du dossier de données",
                )
                self.assertEqual(list(self.cwd.iterdir()), [], "dossier courant")
        # L'exécution factice a bien écrit dans `data/` : le garde n'est pas
        # creux. Un seul nouveau résultat, et son identifiant est rendu par la
        # sortie de « run start » (contrat d'enchaînement des commandes).
        nouveaux = self.result_ids() - identifiants_avant
        self.assertEqual(
            len(nouveaux), 1, "exécution factice sans résultat écrit dans data/"
        )
        self.assertIn(next(iter(nouveaux)), sorties[-1])
        self.assert_unlocked()


class CheminsSortantsRefusesTest(TransversalSocle):
    """Tout nom, clé ou identifiant hostile est refusé, sans effet de bord."""

    def test_les_chemins_sortants_sont_refuses_pour_toute_commande(self) -> None:
        sentinelle = self.root / "sentinelle"
        sentinelle.mkdir()
        (sentinelle / "fichier.txt").write_text("preuve", encoding="utf-8")
        for forme, valeur in self.hostile_values(sentinelle).items():
            for libelle, gabarit, motifs in COMMANDES_NOM_CLE_IDENTIFIANT:
                argv = [morceau.replace(HOSTILE, valeur) for morceau in gabarit]
                with self.subTest(forme=forme, refus=libelle):
                    code, stdout, stderr = self.run_command(argv)

                    self.assertEqual(code, CODE_REFUS)
                    # Le refus porte le motif de la couche qui contrôle cette
                    # position, pas un « introuvable » d'un accès suivi hors du
                    # dossier autorisé ; jamais une trace ni un contenu lu.
                    self.assertTrue(
                        any(motif in stderr for motif in motifs),
                        f"motif attendu {motifs!r} absent du refus : {stderr!r}",
                    )
                    self.assertNotIn("Traceback", stderr)
                    self.assertNotIn("preuve", stdout + stderr)
                    self.assertEqual(
                        (sentinelle / "fichier.txt").read_text(encoding="utf-8"), "preuve"
                    )
                    self.assertEqual(list(self.cwd.iterdir()), [], "dossier courant")
                    self.assert_unlocked()

    def test_outgoing_symlinks_are_refused_without_side_effect(self) -> None:
        """Un lien symbolique sortant de `data/` est refusé, sans le suivre.

        `results show` et `compare` résolvent le chemin nommé : le lien
        sortant est refusé par la résolution contrôlée. Les commandes
        d'exécution ne prennent que les audios de la liste des audios
        lisibles : le lien n'y figure jamais. Les autres positions
        identifient leur ressource avant toute résolution de chemin.
        """
        sentinelle = self.root / "sentinelle"
        sentinelle.mkdir()
        (sentinelle / "fichier.txt").write_text("preuve", encoding="utf-8")
        (self.base / "audio" / "vers-dehors").symlink_to(
            sentinelle, target_is_directory=True
        )
        identifiant_lien = "20240109-000000-abcdef01"
        (self.base / "results" / identifiant_lien).symlink_to(
            sentinelle, target_is_directory=True
        )
        cas = (
            (
                "results show, lien sortant",
                ["results", "show", identifiant_lien],
                ("chemin refusé : sort du dossier autorisé",),
            ),
            (
                "compare, sélection par lien sortant",
                ["compare", EMPREINTE_A, f"{identifiant_lien}:1", f"{IDENTIFIANT}:1"],
                ("chemin refusé : sort du dossier autorisé",),
            ),
            (
                "run check, audio par lien sortant",
                [
                    "run",
                    "check",
                    "--model",
                    REFERENCE_FACTICE,
                    "--audio",
                    "vers-dehors/fichier.txt",
                ],
                ("hors de la liste du dossier d'entrée",),
            ),
            (
                "run start, audio par lien sortant",
                [
                    "run",
                    "start",
                    "--model",
                    REFERENCE_FACTICE,
                    "--audio",
                    "vers-dehors/fichier.txt",
                ],
                ("hors de la liste du dossier d'entrée",),
            ),
        )
        for libelle, argv, motifs in cas:
            with self.subTest(refus=libelle):
                code, stdout, stderr = self.run_command(argv)

                self.assertEqual(code, CODE_REFUS)
                self.assertTrue(
                    any(motif in stderr for motif in motifs),
                    f"motif attendu {motifs!r} absent du refus : {stderr!r}",
                )
                self.assertNotIn("Traceback", stderr)
                self.assertNotIn("preuve", stdout + stderr)
                self.assertEqual(
                    (sentinelle / "fichier.txt").read_text(encoding="utf-8"), "preuve"
                )
                self.assertEqual(list(self.cwd.iterdir()), [], "dossier courant")
                self.assert_unlocked()

    def hostile_values(self, sentinelle: Path) -> dict[str, str]:
        """Valeurs hostiles ciblant réellement la sentinelle hors de `data/`.

        Un seul `..` resterait sous `data/` : depuis n'importe quel sous-dossier
        de résolution, deux niveaux de remontée atteignent la sentinelle. Le
        chemin absolu vise le même fichier existant.
        """
        return {
            "remontée": "../../sentinelle/fichier.txt",
            "chemin absolu": str(sentinelle / "fichier.txt"),
        }


class ProcessusSansBibliothequeMoteurTest(TransversalSocle):
    """Le processus d'une commande n'importe aucune bibliothèque de moteur."""

    def test_le_processus_des_commandes_n_importe_aucun_paquet_moteur(self) -> None:
        commandes = [
            *COMMANDES_LECTURE,
            ["run", "start", "--model", REFERENCE_FACTICE, "--audio", "a.wav"],
            *COMMANDES_REFUSEES,
        ]
        attendus = [CODE_SUCCESS] * (len(COMMANDES_LECTURE) + 1) + [CODE_REFUS] * len(
            COMMANDES_REFUSEES
        )
        resultat = subprocess.run(
            [
                sys.executable,
                "-c",
                CODE_COMMANDES,
                str(self.base),
                json.dumps(commandes),
            ],
            capture_output=True,
            text=True,
            check=True,
            encoding="utf-8",
            cwd=str(self.cwd),
            timeout=DELAI_PROCESSUS,
        )
        self.assertEqual(resultat.stderr, "")
        rapport = json.loads(resultat.stdout)
        self.assertEqual(rapport["codes"], attendus)
        self.assertEqual(rapport["moteurs"], [], "bibliothèque de moteur chargée")
        self.assertEqual(list(self.cwd.iterdir()), [], "dossier courant")
        self.assert_unlocked()


class DependancesTest(unittest.TestCase):
    """Aucune dépendance ajoutée au programme par les commandes."""

    def test_pyproject_ne_declare_que_les_dependances_attendues(self) -> None:
        with (RACINE / "pyproject.toml").open("rb") as fichier:
            contenu = tomllib.load(fichier)
        self.assertEqual(
            sorted(contenu["project"]["dependencies"]),
            sorted(DEPENDANCES_ATTENDUES),
            "dépendance ajoutée ou retirée : décision explicite à consigner",
        )
        self.assertEqual(
            contenu["build-system"]["requires"], ["uv_build>=0.13.5,<0.14"]
        )
        self.assertEqual(
            contenu["project"]["scripts"],
            {"transcription-bench": "transcription_bench.cli:main"},
            "le point d'entrée reste l'unique programme (design D1)",
        )

    def test_uv_lock_n_ajoute_aucune_dependance_au_projet(self) -> None:
        with (RACINE / "uv.lock").open("rb") as fichier:
            contenu = tomllib.load(fichier)
        paquet = next(
            paquet
            for paquet in contenu["package"]
            if paquet.get("name") == "transcription-bench"
        )
        noms_resolus = sorted(dep["name"] for dep in paquet["dependencies"])
        self.assertEqual(noms_resolus, sorted(NOMS_DEPENDANCES))
        noms_declares = sorted(
            dep["name"] for dep in paquet["metadata"]["requires-dist"]
        )
        self.assertEqual(noms_declares, sorted(NOMS_DEPENDANCES))

    def test_les_imports_de_premier_niveau_restent_dans_les_dependances(self) -> None:
        """Imports de premier niveau des modules du programme, hors moteurs.

        Seul le premier niveau des modules est parcouru, y compris dans les
        blocs de premier niveau (`try`, `if`, `with`…) et leurs branches : les
        adaptateurs de moteur importent leurs bibliothèques dans des fonctions
        (import différé), exécutées dans le sous-processus du moteur, jamais
        dans le processus du serveur ou d'une commande.
        """
        autorises = (
            set(sys.stdlib_module_names)
            | {"transcription_bench", "engines"}
            | set(MODULES_DEPENDANCES)
            | set(MODULES_TRANSITIFS_IMPORTES)
        )
        interdits: dict[str, list[str]] = {}
        for dossier in ("transcription_bench", "engines"):
            for fichier in (RACINE / dossier).rglob("*.py"):
                arbre = ast.parse(fichier.read_text(encoding="utf-8"))
                for racine in self.top_level_imports(arbre):
                    if racine not in autorises:
                        interdits.setdefault(racine, []).append(
                            fichier.relative_to(RACINE).as_posix()
                        )
        self.assertEqual(
            interdits,
            {},
            "import tiers hors dépendances déclarées : déclarer la dépendance "
            "(et passer le verrou de pyproject) ou ne pas l'importer",
        )

    def top_level_imports(self, arbre: ast.Module) -> list[str]:
        """Noms racines importés au premier niveau, fonctions et classes exclues.

        Les blocs composés de premier niveau (`try` et ses branches,
        `if`/`else`, `with`, `for`…) sont parcourus ; les corps de fonctions,
        de méthodes et de classes ne le sont pas : leurs imports sont différés.
        """
        racines: list[str] = []

        def visiter(instructions: list[ast.stmt]) -> None:
            for node in instructions:
                if isinstance(
                    node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
                ):
                    continue
                if isinstance(node, ast.Import):
                    racines.extend(alias.name.split(".")[0] for alias in node.names)
                elif isinstance(node, ast.ImportFrom):
                    if node.level == 0 and node.module:
                        racines.append(node.module.split(".")[0])
                else:
                    for champ in ("body", "orelse", "finalbody"):
                        sous_blocs = getattr(node, champ, None)
                        if isinstance(sous_blocs, list):
                            visiter(sous_blocs)
                    for handler in getattr(node, "handlers", []):
                        visiter(handler.body)

        visiter(arbre.body)
        return racines


class InstantanesClesJsonTest(unittest.TestCase):
    """Chaque commande enregistrée possède un instantané de ses clés JSON."""

    def test_chaque_commande_enregistree_a_un_instantané(self) -> None:
        enregistrees: set[tuple[str, ...]] = set()
        for command in COMMANDS:
            if isinstance(command, CommandGroup):
                for leaf in command.commands:
                    enregistrees.add((command.name, leaf.name))
            else:
                enregistrees.add((command.name,))
        instantanees = set(JSON_SNAPSHOT_KEYS)
        self.assertEqual(
            enregistrees - instantanees,
            set(),
            "commandes enregistrées sans instantané de clés JSON : "
            + repr(sorted(" ".join(chemin) for chemin in enregistrees - instantanees)),
        )
        self.assertEqual(
            instantanees - enregistrees,
            set(),
            "instantanés sans commande enregistrée : "
            + repr(sorted(" ".join(chemin) for chemin in instantanees - enregistrees)),
        )

    def test_chaque_instantané_commence_par_schema(self) -> None:
        for chemin, cles in JSON_SNAPSHOT_KEYS.items():
            with self.subTest(commande=" ".join(chemin)):
                self.assertTrue(cles, "instantané vide")
                self.assertEqual(cles[0], "schema", "le contrat JSON porte schema: 1")


if __name__ == "__main__":
    unittest.main()
