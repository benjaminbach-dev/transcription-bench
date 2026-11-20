"""Tests du moteur factice exécutable de bout en bout, sans moteur réel.

La tâche 4.3 rend le moteur factice exécutable par l'interpréteur du serveur,
avec un texte et des mesures marqués comme factices et simulés. Les tests
lancent exactement `python engines/runner.py job.json` dans un processus réel,
depuis un dossier temporaire, avec un environnement sans `PYTHONPATH` ni
`PYTHONHOME` hérités. Les audios sont des signaux synthétiques créés localement ;
le modèle est un chemin inexistant, ce qui est normal pour ce moteur. Aucun
moteur, aucun poids et aucun accès réseau : aucune validation PC n'est affirmée.

Le lancement `python -S` ne peut pas servir à tester l'indépendance vis-à-vis de
l'installation éditable : il supprime `site-packages`, donc `numpy`, requis par
le runner. Le test dédié copie donc `engines/` hors du clone et retire la racine
du clone de `sys.path` après avoir préchargé `numpy` ; le runner doit alors
importer `engines` depuis sa seule racine calculée par `__file__`.
"""

from __future__ import annotations

import dataclasses
import io
import json
import math
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

import numpy as np
import psutil

import engines.adaptateurs.factice as adaptateur_factice
from engines.declarations import (
    TASK_EXTRACTION,
    TASK_TRANSCRIPTION,
    DeclarationAdaptateur,
    Famille,
    declarations_fournies,
)
from engines.mesures_systeme import (
    PROVENANCE_REELLE,
    PROVENANCE_SIMULEE,
    SIMULATION_CPU_POURCENTAGE,
    SIMULATION_INTERVALLE_CPU_S,
    SIMULATION_MEMOIRE_DISPONIBLE_OCTETS,
    SIMULATION_MEMOIRE_TOTALE_OCTETS,
    SIMULATION_RELEVE_LE,
)
from engines.protocole import (
    PREFIXE_EVENEMENT,
    TYPE_AUDIO,
    TYPE_AUDIO_ERREUR,
    TYPE_CHARGEMENT,
    TYPE_FIN,
    analyser_ligne,
)
from engines.registre import RegistreMoteurs, creer_registre_fourni
from engines.runner import (
    DUREE_CHARGEMENT_SIMULEE_S,
    FACTEUR_TEMPS_CPU_SIMULE,
    FORMAT_AUDIO,
    PIC_MEMOIRE_SIMULE_OCTETS,
    RTF_SIMULE,
    ErreurMoteur,
    charger_job,
    executer,
)
from engines.runner_extraction import (
    CLES_RESULTAT_EXTRACTION,
    DUREE_EXTRACTION_SIMULEE_S,
)
from transcription_bench.consignes_grilles import system_message, user_message
from transcription_bench.executions import CLE_MODELE_FACTICE_EXTRACTION
from transcription_bench.grilles import Grid, read_grid
from transcription_bench.paths import RACINE_PROJET
from transcription_bench.schema_grilles import (
    decode_output,
    grid_schema,
    validate_output,
)

MOTEUR_FACTICE = "factice"
FAMILLE_FACTICE = "factice"

CODE_SANS_RACINE_DU_CLONE = """
import runpy
import sys

import numpy  # fourni par l'environnement du serveur ; `-S` le supprimerait.

racine_clone = {racine!r}
sys.path[:] = [chemin for chemin in sys.path if chemin != racine_clone]
try:
    runpy.run_path({runner!r}, run_name="__main__")
except SystemExit as exception:
    code = exception.code
else:
    code = 0
sys.stderr.write("engines=" + str(sys.modules["engines"].__file__) + "\\n")
raise SystemExit(code)
"""


def ecrire_signal(dossier: Path, nom: str, secondes: float) -> str:
    """Écrit un signal brut float32 16 kHz mono synthétique, relatif au job."""
    np.full(round(secondes * 16000), 0.25, dtype="<f4").tofile(dossier / nom)
    return nom


def ecrire_job(
    dossier: Path,
    audios: list[tuple[str, str]],
    *,
    moteur: str = MOTEUR_FACTICE,
    famille: str = FAMILLE_FACTICE,
    threads_demandes: int = 3,
    champs_supplementaires: dict[str, object] | None = None,
) -> Path:
    contenu: dict[str, object] = {
        "version": 1,
        "moteur": moteur,
        "famille": famille,
        "modele": {
            "identifiant": "factice/placeholder",
            "revision": "0000",
            # Ce chemin n'existe pas : le moteur factice ne lit aucun modèle.
            "chemin": "modele-absent",
        },
        "threads_demandes": threads_demandes,
        "reglages": {"reglage_factice": "ignore"},
        "format_audio": FORMAT_AUDIO,
        "audios": [{"nom": nom, "chemin": chemin} for nom, chemin in audios],
    }
    if champs_supplementaires:
        contenu.update(champs_supplementaires)
    chemin_job = dossier / "job.json"
    chemin_job.write_text(json.dumps(contenu), encoding="utf-8")
    return chemin_job


def environnement_sans_heritage() -> dict[str, str]:
    """Environnement sans héritage d'interpréteur, à sortie UTF-8 garantie."""
    environnement = {
        cle: valeur
        for cle, valeur in os.environ.items()
        if cle not in ("PYTHONPATH", "PYTHONHOME")
    }
    # L'enfant écrit en UTF-8 même sans PYTHONIOENCODING hérité.
    environnement["PYTHONIOENCODING"] = "utf-8"
    return environnement


def evenements_de(sortie: str) -> list[dict[str, object]]:
    return [
        evenement
        for evenement in (
            analyser_ligne(ligne) for ligne in sortie.splitlines()
        )
        if evenement is not None
    ]


def executer_et_lire(chemin_job: Path) -> list[dict[str, object]]:
    """Exécute un job dans ce processus en capturant les événements."""
    sortie = io.StringIO()
    with redirect_stdout(sortie):
        executer(charger_job(chemin_job), creer_registre_fourni())
    return evenements_de(sortie.getvalue())


class ExecutionCompleteTest(unittest.TestCase):
    """Lot complet exécuté par le vrai interpréteur du serveur."""

    def setUp(self) -> None:
        self._temporaire = tempfile.TemporaryDirectory()
        self.addCleanup(self._temporaire.cleanup)
        self.dossier = Path(self._temporaire.name)

    def test_lot_complet_avec_audio_court_long_et_erreur(self) -> None:
        audios = [
            ("court.wav", ecrire_signal(self.dossier, "court.f32", 2.0)),
            ("vide.wav", "vide.f32"),
            ("long.wav", ecrire_signal(self.dossier, "long.f32", 31.0)),
        ]
        (self.dossier / "vide.f32").write_bytes(b"")
        chemin = ecrire_job(self.dossier, audios)
        resultat = subprocess.run(
            [
                sys.executable,
                str(RACINE_PROJET / "engines" / "runner.py"),
                str(chemin),
            ],
            cwd=self.dossier,
            env=environnement_sans_heritage(),
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=120,
            check=False,
        )
        self.assertEqual(resultat.returncode, 0, resultat.stderr)
        self.assertEqual(resultat.stderr, "")
        self.assertEqual(
            [
                ligne
                for ligne in resultat.stdout.splitlines()
                if not ligne.startswith(PREFIXE_EVENEMENT)
            ],
            [],
        )
        evenements = evenements_de(resultat.stdout)
        self.assertEqual(
            [evenement["type"] for evenement in evenements],
            [
                TYPE_CHARGEMENT,
                TYPE_AUDIO,
                TYPE_AUDIO_ERREUR,
                TYPE_AUDIO,
                TYPE_FIN,
            ],
        )
        # Un seul chargement pour tout le lot, et provenance explicite partout.
        self.assertEqual(
            [evenement["type"] for evenement in evenements].count(TYPE_CHARGEMENT),
            1,
        )
        for evenement in evenements:
            with self.subTest(type_evenement=evenement["type"]):
                self.assertIs(evenement["factice"], True)
                self.assertIs(evenement["mesures_simulees"], True)

        chargement = evenements[0]
        self.assertEqual(chargement["duree_s"], DUREE_CHARGEMENT_SIMULEE_S)
        self.assertEqual(
            chargement["pic_memoire_octets"], PIC_MEMOIRE_SIMULE_OCTETS
        )

        court = evenements[1]
        self.assertEqual(court["duree_audio_s"], 2.0)
        self.assertEqual(court["nb_fenetres"], 1)
        self.assertEqual(court["fenetre_s"], 30.0)
        self.assertEqual(court["decoupage"], "fenetres-fixes")
        self.assertTrue(court["texte"].startswith("[FACTICE]"))
        self.assertIn("simulée", court["texte"])
        self.assertEqual(court["segments"][0]["fin_s"], 2.0)
        self.assertEqual(court["rtf"], RTF_SIMULE)
        self.assertEqual(
            court["duree_transcription_s"], 2.0 * RTF_SIMULE
        )
        self.assertEqual(
            court["temps_cpu_s"],
            court["duree_transcription_s"] * FACTEUR_TEMPS_CPU_SIMULE,
        )
        self.assertEqual(
            court["pic_memoire_octets"], PIC_MEMOIRE_SIMULE_OCTETS
        )

        erreur = evenements[2]
        self.assertEqual(erreur["index"], 1)
        self.assertEqual(erreur["nom"], "vide.wav")
        self.assertIn("durée décodée nulle", erreur["erreur"])

        long = evenements[3]
        self.assertEqual(long["duree_audio_s"], 31.0)
        self.assertEqual(long["nb_fenetres"], 2)
        self.assertEqual(long["texte"].count("[FACTICE]"), 2)
        self.assertEqual(
            [(segment["debut_s"], segment["fin_s"]) for segment in long["segments"]],
            [(0.0, 30.0), (30.0, 31.0)],
        )
        self.assertEqual(long["rtf"], RTF_SIMULE)

        # Les métadonnées d'adaptateur restent identiques entre fenêtres et audios.
        for audio in (court, long):
            with self.subTest(nom=audio["nom"]):
                self.assertEqual(audio["reglages_effectifs"], {})
                self.assertIsNone(audio["langue_imposee"])
                self.assertIsNone(audio["threads_appliques"])
                self.assertEqual(audio["threads_demandes"], 3)

        fin = evenements[-1]
        self.assertEqual(fin["duree_chargement_s"], DUREE_CHARGEMENT_SIMULEE_S)
        self.assertEqual(fin["pic_memoire_octets"], PIC_MEMOIRE_SIMULE_OCTETS)
        self.assertEqual(fin["audios_ok"], 2)
        self.assertEqual(fin["audios_erreur"], 1)


class DeclarationFacticeTest(unittest.TestCase):
    def setUp(self) -> None:
        self._temporaire = tempfile.TemporaryDirectory()
        self.addCleanup(self._temporaire.cleanup)
        self.dossier = Path(self._temporaire.name)

    def test_garde_fou_non_qualifiee_et_familles_reelles_qualifiees(self) -> None:
        # Les familles réelles sont qualifiées après validation Linux : le
        # moteur factice n'est plus le seul exécutable, mais il reste le seul
        # à ne demander aucune qualification ni aucun modèle.
        registre = RegistreMoteurs()
        for declaration in declarations_fournies():
            # llama-cpp n'est pas encore qualifié sur PC (tâches 6.x).
            if declaration.factice or declaration.identifiant == "llama-cpp":
                continue
            self.assertTrue(declaration.familles_qualifiees)
            registre.enregistrer(
                dataclasses.replace(
                    declaration,
                    familles=tuple(
                        dataclasses.replace(
                            famille, qualifiee=False, duree_native=None
                        )
                        for famille in declaration.familles
                    ),
                )
            )
        for moteur, famille in (
            ("faster-whisper", "whisper"),
            ("transcribe-cpp", "whisper"),
            ("transformers", "whisper"),
            ("transformers", "parakeet-tdt"),
        ):
            with self.subTest(moteur=moteur, famille=famille):
                chemin = ecrire_job(
                    self.dossier,
                    [("a.wav", "a.f32")],
                    moteur=moteur,
                    famille=famille,
                )
                with self.assertRaises(ErreurMoteur) as contexte:
                    executer(charger_job(chemin), registre)
                self.assertIn("non qualifiée", str(contexte.exception))

    def test_le_job_ne_peut_pas_injecter_le_drapeau_factice(self) -> None:
        (self.dossier / "a.f32").write_bytes(b"\x00\x00\x00\x00")
        chemin = ecrire_job(
            self.dossier,
            [("a.wav", "a.f32")],
            moteur="faster-whisper",
            famille="whisper",
            champs_supplementaires={"factice": True, "mesures_simulees": True},
        )
        with self.assertRaises(ErreurMoteur):
            executer(charger_job(chemin), creer_registre_fourni())

        # Un job qui prétend le contraire ne change rien : le drapeau vient de
        # la déclaration du code, pas du job.
        chemin = ecrire_job(
            self.dossier,
            [("a.wav", "a.f32")],
            champs_supplementaires={"factice": False, "mesures_simulees": False},
        )
        evenements = executer_et_lire(chemin)
        self.assertEqual(evenements[0]["type"], TYPE_CHARGEMENT)
        self.assertIs(evenements[0]["factice"], True)
        self.assertIs(evenements[0]["mesures_simulees"], True)

    def test_identifiant_factice_sans_drapeau_reste_refuse(self) -> None:
        registre = RegistreMoteurs()
        registre.enregistrer(
            DeclarationAdaptateur(
                identifiant=MOTEUR_FACTICE,
                nom="Moteur factice sans drapeau",
                fichier_requirements=None,
                regle_compatibilite="aucune",
                familles=(Famille(FAMILLE_FACTICE, "Moteur factice"),),
                module_adaptateur="engines.adaptateurs.factice",
            )
        )
        chemin = ecrire_job(self.dossier, [("a.wav", "a.f32")])
        with self.assertRaises(ErreurMoteur) as contexte:
            executer(charger_job(chemin), registre)
        self.assertIn("non qualifiée", str(contexte.exception))

    def test_aucune_connexion_reseau(self) -> None:
        (self.dossier / "a.f32").write_bytes(b"\x00\x00\x00\x00")
        chemin = ecrire_job(self.dossier, [("a.wav", "a.f32")])

        def interdire(*args: object, **kwargs: object) -> None:
            raise AssertionError("aucune connexion réseau n'est autorisée")

        with (
            mock.patch.object(socket, "socket", interdire),
            mock.patch.object(socket, "create_connection", interdire),
            mock.patch.object(socket, "getaddrinfo", interdire),
        ):
            evenements = executer_et_lire(chemin)
        self.assertEqual(evenements[0]["type"], TYPE_CHARGEMENT)
        self.assertEqual(evenements[-1]["type"], TYPE_FIN)


class BootstrapSansInstallationEditableTest(unittest.TestCase):
    """Le runner trouve sa racine par `__file__`, pas par l'installation éditable."""

    def setUp(self) -> None:
        self._temporaire = tempfile.TemporaryDirectory()
        self.addCleanup(self._temporaire.cleanup)
        # Chemin résolu : l'enfant résout les siens ; sous Windows, le dossier
        # temporaire peut être rendu en chemin court (8.3).
        self.racine = Path(self._temporaire.name).resolve()
        self.copie = self.racine / "copie"
        self.travail = self.racine / "travail"
        self.travail.mkdir()
        shutil.copytree(
            RACINE_PROJET / "engines",
            self.copie / "engines",
            ignore=shutil.ignore_patterns("__pycache__"),
        )

    def test_racine_calculee_depuis_file_sans_racine_du_clone(self) -> None:
        audio = ecrire_signal(self.travail, "a.f32", 1.0)
        chemin = ecrire_job(self.travail, [("a.wav", audio)])
        code = CODE_SANS_RACINE_DU_CLONE.format(
            racine=str(RACINE_PROJET),
            runner=str(self.copie / "engines" / "runner.py"),
        )
        resultat = subprocess.run(
            [sys.executable, "-c", code, str(chemin)],
            cwd=self.travail,
            env=environnement_sans_heritage(),
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=120,
            check=False,
        )
        self.assertEqual(resultat.returncode, 0, resultat.stderr)
        self.assertEqual(
            [evenement["type"] for evenement in evenements_de(resultat.stdout)],
            [TYPE_CHARGEMENT, TYPE_AUDIO, TYPE_FIN],
        )
        # La copie, et non le clone installé en éditable, a fourni `engines`.
        self.assertIn(
            f"engines={(self.copie / 'engines' / '__init__.py')}\n",
            resultat.stderr,
        )


class ObservationsSimuleesTest(unittest.TestCase):
    """Scénario simulé déterministe des relevés système (tâche 1.2).

    Le moteur factice n'exécute aucune collecte réelle : les observations sont
    des valeurs fixes marquées `simulee`, reproductibles d'une exécution à
    l'autre, et aucune fonction de mesure de psutil n'est appelée.
    """

    def setUp(self) -> None:
        self._temporaire = tempfile.TemporaryDirectory()
        self.addCleanup(self._temporaire.cleanup)
        self.dossier = Path(self._temporaire.name)

    def _evenements(self) -> list[dict[str, object]]:
        chemin = ecrire_job(
            self.dossier,
            [
                ("court.wav", ecrire_signal(self.dossier, "court.f32", 2.0)),
                ("long.wav", ecrire_signal(self.dossier, "long.f32", 31.0)),
            ],
        )
        return executer_et_lire(chemin)

    def test_deux_executions_donnent_des_observations_identiques(self) -> None:
        premieres = self._evenements()
        secondes = self._evenements()

        # Toutes les mesures, observations simulées comprises, sont fixes : les
        # deux exécutions produisent exactement les mêmes événements.
        self.assertEqual(premieres, secondes)
        self.assertEqual(
            [evenement["type"] for evenement in premieres],
            [TYPE_CHARGEMENT, TYPE_AUDIO, TYPE_AUDIO, TYPE_FIN],
        )

        chargement = premieres[0]["observation_systeme"]
        self.assertEqual(chargement["provenance"], PROVENANCE_SIMULEE)
        self.assertNotIn("cpu", chargement)
        self.assertEqual(
            chargement["memoire_apres"]["totale_octets"],
            SIMULATION_MEMOIRE_TOTALE_OCTETS,
        )
        self.assertEqual(
            chargement["memoire_apres"]["disponible_octets"],
            SIMULATION_MEMOIRE_DISPONIBLE_OCTETS,
        )
        self.assertEqual(
            chargement["memoire_apres"]["releve_le"], SIMULATION_RELEVE_LE
        )

        for evenement in premieres[1:3]:
            with self.subTest(index=evenement["index"]):
                observation = evenement["observation_systeme"]
                self.assertEqual(observation["provenance"], PROVENANCE_SIMULEE)
                self.assertEqual(
                    observation["cpu"]["pourcentage_moyen"],
                    SIMULATION_CPU_POURCENTAGE,
                )
                self.assertEqual(
                    observation["cpu"]["intervalle_s"],
                    SIMULATION_INTERVALLE_CPU_S,
                )
                self.assertIsNone(observation["cpu"]["motif"])
                self.assertEqual(
                    observation["memoire_apres"]["disponible_octets"],
                    SIMULATION_MEMOIRE_DISPONIBLE_OCTETS,
                )

        # La provenance de chaque observation est cohérente avec la marque
        # `mesures_simulees` de l'événement qui la porte.
        for evenement in premieres:
            if "observation_systeme" not in evenement:
                continue
            with self.subTest(type_evenement=evenement["type"]):
                attendue = (
                    PROVENANCE_SIMULEE
                    if evenement["mesures_simulees"]
                    else PROVENANCE_REELLE
                )
                self.assertEqual(
                    evenement["observation_systeme"]["provenance"], attendue
                )

    def test_aucune_mesure_psutil_reelle(self) -> None:
        def interdire(*arguments: object, **options: object) -> None:
            raise AssertionError("aucune mesure psutil réelle en mode factice")

        with (
            mock.patch.object(psutil, "cpu_percent", interdire),
            mock.patch.object(psutil, "virtual_memory", interdire),
        ):
            evenements = self._evenements()

        self.assertEqual(
            [evenement["type"] for evenement in evenements],
            [TYPE_CHARGEMENT, TYPE_AUDIO, TYPE_AUDIO, TYPE_FIN],
        )
        for evenement in evenements[:3]:
            with self.subTest(type_evenement=evenement["type"]):
                self.assertEqual(
                    evenement["observation_systeme"]["provenance"],
                    PROVENANCE_SIMULEE,
                )


#: Modèle synthétique d'extraction : le chemin n'existe pas, normal pour le factice.
MODELE_EXTRACTION_FACTICE = {
    "identifiant": f"factice/{CLE_MODELE_FACTICE_EXTRACTION}",
    "revision": "0000",
    "chemin": "modele-absent",
}


def ecrire_grille_types(dossier: Path) -> Grid:
    """Grille temporaire couvrant les quatre types D2, lue par le parseur réel."""
    (dossier / "grilles").mkdir()
    (dossier / "grilles" / "types-factices.md").write_text(
        "# Grille de types\n"
        "\n"
        "## Texte ?\n"
        "Consigne simple.\n"
        "\n"
        "## Liste ?\n"
        "Liste.\n"
        "\n"
        "## Composee ?\n"
        "### Libelle ?\n"
        "### Valeurs ?\n"
        "Liste.\n"
        "\n"
        "## Liste composee ?\n"
        "Liste :\n"
        "### Nom ?\n",
        encoding="utf-8",
    )
    return read_grid("types-factices", base=dossier)


class AdaptateurFacticeExtractionTest(unittest.TestCase):
    """Contrat d'extraction de l'adaptateur factice, appelé directement."""

    def setUp(self) -> None:
        self._temporaire = tempfile.TemporaryDirectory()
        self.addCleanup(self._temporaire.cleanup)
        self.dossier = Path(self._temporaire.name)
        self.grille = read_grid("consultation-generale")
        self.schema = grid_schema(self.grille)
        self.messages = [
            {"role": "system", "content": system_message(self.grille).text},
            {
                "role": "user",
                "content": user_message(
                    "Le patient décrit une toux depuis trois jours."
                ),
            },
        ]

    def _moteur(self, schema: dict[str, object] | None = None) -> dict[str, object]:
        return adaptateur_factice.charger(
            MODELE_EXTRACTION_FACTICE,
            3,
            {},
            self.schema if schema is None else schema,
        )

    def test_sortie_conforme_au_schema_reel_et_deterministe(self) -> None:
        moteur = self._moteur()
        premier = adaptateur_factice.extraire(moteur, self.messages, {})
        second = adaptateur_factice.extraire(moteur, self.messages, {})

        # Deux exécutions identiques, octet pour octet.
        self.assertEqual(premier, second)
        self.assertEqual(
            premier["sortie_brute"].encode("utf-8"),
            second["sortie_brute"].encode("utf-8"),
        )
        # JSON compact, passant le décodage et la validation réels.
        self.assertNotIn(": ", premier["sortie_brute"])
        decodage = decode_output(premier["sortie_brute"])
        self.assertTrue(decodage.ok, decodage.message)
        self.assertIsNone(validate_output(decodage.value, self.schema).issue)

    def test_chaque_type_de_case_rempli_comme_decrit(self) -> None:
        sortie = adaptateur_factice.extraire(self._moteur(), self.messages, {})
        valeur = json.loads(sortie["sortie_brute"])

        # Texte : chaîne portant la marque factice et la clé.
        self.assertEqual(valeur["qui"], "[FACTICE] contenu factice de qui")
        self.assertEqual(
            valeur["doute_restant"],
            "[FACTICE] contenu factice de doute_restant",
        )
        # Liste de textes : une entrée unique de même forme.
        self.assertEqual(
            valeur["symptomes_declares"],
            ["[FACTICE] contenu factice de symptomes_declares"],
        )
        # Liste composée : une entrée unique remplie sous-case par sous-case.
        self.assertEqual(
            valeur["prescription"],
            [
                {
                    "medicament": "[FACTICE] contenu factice de medicament",
                    "posologie": "[FACTICE] contenu factice de posologie",
                    "duree": "[FACTICE] contenu factice de duree",
                }
            ],
        )
        # Section réservée : liste vide, conforme.
        self.assertEqual(valeur["autres_informations"], [])
        self.assertEqual(list(valeur), list(self.schema["properties"]))

    def test_composee_et_liste_composee_de_la_grille_de_types(self) -> None:
        grille = ecrire_grille_types(self.dossier)
        schema = grid_schema(grille)
        sortie = adaptateur_factice.extraire(self._moteur(schema), self.messages, {})
        valeur = json.loads(sortie["sortie_brute"])

        self.assertEqual(
            valeur,
            {
                "texte": "[FACTICE] contenu factice de texte",
                "liste": ["[FACTICE] contenu factice de liste"],
                "composee": {
                    "libelle": "[FACTICE] contenu factice de libelle",
                    "valeurs": ["[FACTICE] contenu factice de valeurs"],
                },
                "liste_composee": [
                    {"nom": "[FACTICE] contenu factice de nom"}
                ],
                "autres_informations": [],
            },
        )
        decodage = decode_output(sortie["sortie_brute"])
        self.assertIsNone(validate_output(decodage.value, schema).issue)

    def test_sortie_independante_du_texte_source(self) -> None:
        moteur = self._moteur()
        autres = [
            self.messages[0],
            {
                "role": "user",
                "content": user_message(
                    "Autre texte, sans rapport, avec 42 mots nouveaux."
                ),
            },
        ]
        premiere = adaptateur_factice.extraire(moteur, self.messages, {})
        seconde = adaptateur_factice.extraire(moteur, autres, {})

        self.assertEqual(premiere["sortie_brute"], seconde["sortie_brute"])
        self.assertNotIn("toux", premiere["sortie_brute"])
        self.assertNotIn("42 mots", seconde["sortie_brute"])

    def test_fin_arret_et_contrat_exact_des_sept_cles(self) -> None:
        resultat = adaptateur_factice.extraire(self._moteur(), self.messages, {})

        self.assertEqual(set(resultat), set(CLES_RESULTAT_EXTRACTION))
        self.assertEqual(len(resultat), 7)
        self.assertEqual(resultat["fin"], "arret")
        self.assertIsInstance(resultat["sortie_brute"], str)
        self.assertIsInstance(resultat["tokens_entree"], int)
        self.assertIsInstance(resultat["tokens_sortie"], int)
        self.assertIsInstance(resultat["delai_premier_token_s"], float)
        self.assertIsInstance(resultat["duree_generation_s"], float)
        self.assertIsInstance(resultat["temps_cpu_s"], float)

    def test_mesures_simulees_deterministes_et_derivees_des_comptages(self) -> None:
        messages = [
            {"role": "system", "content": "a" * 600},
            {"role": "user", "content": "b" * 200},
        ]
        resultat = adaptateur_factice.extraire(self._moteur(), messages, {})

        # 800 caractères de prompt : 200 tokens simulés, lus à 400 tokens/s.
        self.assertEqual(resultat["tokens_entree"], 200)
        self.assertEqual(resultat["delai_premier_token_s"], 0.5)
        # Sortie comptée à 4 caractères par token, au moins un token.
        sortie = resultat["sortie_brute"]
        self.assertEqual(resultat["tokens_sortie"], math.ceil(len(sortie) / 4))
        self.assertEqual(
            resultat["duree_generation_s"],
            round((resultat["tokens_sortie"] - 1) / 20.0, 3),
        )
        self.assertEqual(
            resultat["temps_cpu_s"],
            round(
                (resultat["delai_premier_token_s"] + resultat["duree_generation_s"])
                * 1.5,
                3,
            ),
        )
        # Aucune mesure réelle : un second appel rend les mêmes valeurs.
        self.assertEqual(
            resultat, adaptateur_factice.extraire(self._moteur(), messages, {})
        )

    def test_reinitialiser_sans_effet_sur_le_moteur_ni_les_resultats(self) -> None:
        moteur = self._moteur()
        avant = adaptateur_factice.extraire(moteur, self.messages, {})
        copie = dict(moteur)

        self.assertIsNone(adaptateur_factice.reinitialiser(moteur))
        self.assertEqual(moteur, copie)
        self.assertEqual(adaptateur_factice.extraire(moteur, self.messages, {}), avant)

    def test_charger_sans_schema_garde_le_contexte_de_transcription(self) -> None:
        contexte = adaptateur_factice.charger(
            {"identifiant": "factice/placeholder", "chemin": "absent"}, 3, {}
        )
        self.assertEqual(
            contexte, {"modele": "factice/placeholder", "threads_demandes": 3}
        )

    def test_extraire_sans_schema_refuse(self) -> None:
        moteur = adaptateur_factice.charger(MODELE_EXTRACTION_FACTICE, 3, {})
        with self.assertRaises(ValueError):
            adaptateur_factice.extraire(moteur, self.messages, {})

    def test_jamais_d_erreur_de_contexte(self) -> None:
        # Le factice n'a pas de vraie limite de contexte : même avec un contexte
        # minuscule et un prompt énorme, il rend un résultat sans lever d'erreur.
        messages = [
            {"role": "system", "content": "a" * 400_000},
            {"role": "user", "content": user_message("b" * 100_000)},
        ]
        resultat = adaptateur_factice.extraire(
            self._moteur(), messages, {"contexte": 16, "sortie_max": 4096}
        )
        self.assertEqual(resultat["fin"], "arret")
        self.assertGreater(resultat["tokens_entree"], 16)


class RegistreFacticeExtractionTest(unittest.TestCase):
    """Un seul module pour les deux tâches, sans import supplémentaire."""

    def test_registre_charge_le_meme_module_pour_les_deux_taches(self) -> None:
        registre = creer_registre_fourni()
        declaration = registre.obtenir("factice")

        self.assertEqual(
            declaration.module_adaptateur, "engines.adaptateurs.factice"
        )
        self.assertEqual(declaration.tasks, (TASK_TRANSCRIPTION, TASK_EXTRACTION))
        self.assertIs(registre.charger_adaptateur("factice"), adaptateur_factice)
        for nom in ("charger", "reinitialiser", "extraire", "transcrire"):
            with self.subTest(fonction=nom):
                self.assertTrue(callable(getattr(adaptateur_factice, nom)))

    def test_import_du_module_sans_dependance_supplementaire(self) -> None:
        code = (
            "import json, sys\n"
            "import engines.adaptateurs.factice\n"
            "print(json.dumps(sorted(\n"
            "    module for module in sys.modules\n"
            "    if module.split('.')[0] in\n"
            "    ('engines', 'transcription_bench', 'numpy', 'psutil')\n"
            ")))\n"
        )
        resultat = subprocess.run(
            [sys.executable, "-c", code],
            cwd=RACINE_PROJET,
            env=environnement_sans_heritage(),
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=120,
            check=False,
        )
        self.assertEqual(resultat.returncode, 0, resultat.stderr)
        self.assertEqual(
            json.loads(resultat.stdout),
            ["engines", "engines.adaptateurs", "engines.adaptateurs.factice"],
        )


class ExecutionExtractionFacticeTest(unittest.TestCase):
    """Job d'extraction complet, lancé par le vrai runner en sous-processus."""

    def setUp(self) -> None:
        self._temporaire = tempfile.TemporaryDirectory()
        self.addCleanup(self._temporaire.cleanup)
        self.dossier = Path(self._temporaire.name)
        self.grille = read_grid("consultation-generale")
        self.schema = grid_schema(self.grille)

    def _lancer(self, chemin_job: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                sys.executable,
                str(RACINE_PROJET / "engines" / "runner_extraction.py"),
                str(chemin_job),
            ],
            cwd=self.dossier,
            env=environnement_sans_heritage(),
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=120,
            check=False,
        )

    def _job(self) -> Path:
        contenu = {
            "version": 1,
            "tache": "extraction",
            "moteur": "factice",
            "famille": "factice-extraction",
            "modele": MODELE_EXTRACTION_FACTICE,
            "threads_demandes": 3,
            "reglages": {},
            "schema": self.schema,
            "message_systeme": system_message(self.grille).text,
            "sources": [
                {
                    "texte": "Le patient tousse depuis trois jours.",
                    "ordre": 0,
                    "nom": "premiere.wav",
                },
                {
                    "texte": "Aucune douleur signalée, rendez-vous dans un mois.",
                    "ordre": 1,
                    "nom": "seconde.wav",
                },
            ],
        }
        chemin = self.dossier / "job.json"
        chemin.write_text(json.dumps(contenu), encoding="utf-8")
        return chemin

    def test_lot_conforme_deterministe_et_mesures_simulees(self) -> None:
        chemin = self._job()
        premiere = self._lancer(chemin)
        seconde = self._lancer(chemin)

        self.assertEqual(premiere.returncode, 0, premiere.stderr)
        # Deux exécutions : sorties du protocole identiques, octet pour octet.
        self.assertEqual(premiere.stdout, seconde.stdout)
        evenements = evenements_de(premiere.stdout)
        self.assertEqual(
            [evenement["type"] for evenement in evenements],
            ["chargement", "extraction", "extraction", "fin"],
        )
        self.assertEqual(evenements[-1]["audios_ok"], 2)
        self.assertEqual(evenements[-1]["audios_erreur"], 0)

        extractions = evenements[1:3]
        for evenement in evenements:
            with self.subTest(type_evenement=evenement["type"]):
                self.assertIs(evenement["factice"], True)
                self.assertIs(evenement["mesures_simulees"], True)
        for evenement in extractions:
            with self.subTest(nom=evenement["nom"]):
                self.assertIs(evenement["conforme"], True)
                self.assertIsNone(evenement["motif"])
                self.assertEqual(evenement["fin"], "arret")
                self.assertEqual(
                    evenement["duree_extraction_s"], DUREE_EXTRACTION_SIMULEE_S
                )
                self.assertEqual(
                    evenement["valeur"], json.loads(evenement["sortie_brute"])
                )
                self.assertIsNone(
                    validate_output(evenement["valeur"], self.schema).issue
                )
                self.assertGreater(evenement["tokens_entree"], 0)
                self.assertGreater(evenement["tokens_sortie"], 0)
        # Sortie dérivée du schéma seul : identique pour deux sources différentes.
        self.assertEqual(extractions[0]["sortie_brute"], extractions[1]["sortie_brute"])
        # Le journal et la sortie d'événements ne recopient jamais le texte source.
        for texte_source in ("tousse depuis trois jours", "rendez-vous dans un mois"):
            with self.subTest(texte_source=texte_source):
                self.assertNotIn(texte_source, premiere.stdout)
                self.assertNotIn(texte_source, premiere.stderr)


if __name__ == "__main__":
    unittest.main()
