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

from engines.declarations import (
    DeclarationAdaptateur,
    Famille,
    declarations_fournies,
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
from transcription_bench.paths import RACINE_PROJET

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
            if declaration.factice:
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


if __name__ == "__main__":
    unittest.main()
