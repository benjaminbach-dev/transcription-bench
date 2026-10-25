"""Tests du runner et du protocole d'événements, sans moteur réel.

Le runner est exécuté dans ce processus avec un registre de test dont la
déclaration est qualifiée et pointe vers `tests/adaptateur_runner_de_test.py`.
Les audios sont des signaux synthétiques bruts, créés localement. Aucun moteur,
aucun poids, aucun accès réseau : les validations PC restent dues.
"""

from __future__ import annotations

import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import numpy as np

from engines.declarations import DeclarationAdaptateur, Famille
from engines.protocole import (
    PREFIXE_EVENEMENT,
    TYPE_AUDIO,
    TYPE_AUDIO_ERREUR,
    TYPE_CHARGEMENT,
    TYPE_FIN,
    analyser_ligne,
    emettre,
    formater_ligne,
)
from engines.registre import RegistreMoteurs, creer_registre_fourni
from engines.runner import (
    FORMAT_AUDIO,
    ErreurJob,
    ErreurMoteur,
    _pic_memoire_unix,
    _pic_memoire_windows,
    charger_job,
    executer,
    pic_memoire,
)
from tests import adaptateur_runner_de_test as adaptateur
from transcription_bench.paths import RACINE_PROJET

MODULE_ADAPTATEUR = "tests.adaptateur_runner_de_test"
MOTEUR_DE_TEST = "moteur-de-test"
FAMILLE_DE_TEST = "factice"

CODE_SANS_MODULE_SERVEUR = """
import sys

import engines.runner

interdits = ("flask", "waitress", "werkzeug", "jinja2", "transcription_bench")
charges = sorted(module for module in interdits if module in sys.modules)
print("|".join(charges) if charges else "ok")
"""


def registre_de_test() -> RegistreMoteurs:
    registre = RegistreMoteurs()
    registre.enregistrer(
        DeclarationAdaptateur(
            identifiant=MOTEUR_DE_TEST,
            nom="Moteur de test",
            fichier_requirements=None,
            regle_compatibilite="aucune",
            familles=(
                Famille(FAMILLE_DE_TEST, "Famille de test", qualifiee=True),
            ),
            module_adaptateur=MODULE_ADAPTATEUR,
        )
    )
    return registre


def ecrire_signal(
    dossier: Path, nom: str, secondes: float, valeur: float
) -> str:
    """Écrit un signal brut float32 16 kHz mono et renvoie son chemin relatif."""
    echantillons = round(secondes * 16000)
    np.full(echantillons, valeur, dtype="<f4").tofile(dossier / nom)
    return nom


def ecrire_job(
    dossier: Path,
    audios: list[tuple[str, str]],
    *,
    moteur: str = MOTEUR_DE_TEST,
    famille: str = FAMILLE_DE_TEST,
    threads_demandes: int = 4,
    reglages: dict[str, object] | None = None,
) -> Path:
    contenu = {
        "version": 1,
        "moteur": moteur,
        "famille": famille,
        "modele": {
            "identifiant": "test/modele",
            "revision": "abc",
            "chemin": "modele",
        },
        "threads_demandes": threads_demandes,
        "reglages": {} if reglages is None else reglages,
        "format_audio": FORMAT_AUDIO,
        "audios": [
            {"nom": nom, "chemin": chemin} for nom, chemin in audios
        ],
    }
    chemin_job = dossier / "job.json"
    chemin_job.write_text(json.dumps(contenu), encoding="utf-8")
    return chemin_job


def executer_et_lire(
    chemin_job: Path, registre: RegistreMoteurs | None
) -> tuple[list[str], list[dict[str, object]]]:
    """Exécute un job en capturant stdout, comme le ferait le serveur."""
    sortie = io.StringIO()
    with redirect_stdout(sortie):
        executer(charger_job(chemin_job), registre)
    lignes = sortie.getvalue().splitlines()
    evenements = [
        evenement
        for evenement in (analyser_ligne(ligne) for ligne in lignes)
        if evenement is not None
    ]
    return lignes, evenements


class ProtocoleTest(unittest.TestCase):
    def test_evenements_prevus_analysables(self) -> None:
        evenements = [
            {"type": TYPE_CHARGEMENT, "duree_s": 1.5, "pic_memoire_octets": None},
            {
                "type": TYPE_AUDIO,
                "index": 0,
                "nom": "a.wav",
                "texte": "bonjour",
                "segments": [],
                "duree_audio_s": 10.0,
                "duree_transcription_s": 2.0,
                "temps_cpu_s": None,
                "rtf": 0.2,
                "fenetre_s": 30.0,
                "decoupage": "fenetres-fixes",
                "nb_fenetres": 1,
                "pic_memoire_octets": 1024,
                "reglages_effectifs": {},
                "langue_imposee": "fr",
                "threads_demandes": 4,
                "threads_appliques": None,
            },
            {"type": TYPE_AUDIO_ERREUR, "index": 1, "nom": "b.wav", "erreur": "échec"},
            {
                "type": TYPE_FIN,
                "duree_chargement_s": 1.5,
                "pic_memoire_octets": 2048,
                "audios_ok": 1,
                "audios_erreur": 1,
            },
        ]
        for evenement in evenements:
            with self.subTest(type_evenement=evenement["type"]):
                self.assertEqual(
                    analyser_ligne(formater_ligne(evenement)), evenement
                )

    def test_lignes_parasites_ignorees(self) -> None:
        parasites = [
            "bavardage de bibliothèque",
            f"{PREFIXE_EVENEMENT}pas du JSON",
            f'{PREFIXE_EVENEMENT}{{"type": "inconnu"}}',
            f'{PREFIXE_EVENEMENT}{{"type": "audio"}}',
            f"{PREFIXE_EVENEMENT}[]",
            "",
        ]
        for ligne in parasites:
            with self.subTest(ligne=ligne):
                self.assertIsNone(analyser_ligne(ligne))

    def test_non_ascii_conserve_et_ligne_unique(self) -> None:
        ligne = formater_ligne(
            {"type": TYPE_AUDIO_ERREUR, "index": 0, "nom": "é", "erreur": "échec"}
        )
        self.assertTrue(ligne.startswith(PREFIXE_EVENEMENT))
        self.assertEqual(ligne.count("\n"), 1)
        self.assertNotIn("\\u00e9", ligne)
        self.assertEqual(analyser_ligne(ligne)["erreur"], "échec")

    def test_emettre_ecrit_et_vide_le_tampon(self) -> None:
        sortie = io.StringIO()
        emettre({"type": TYPE_AUDIO_ERREUR, "index": 0, "nom": "a", "erreur": "x"}, sortie)
        self.assertEqual(sortie.getvalue().count("\n"), 1)
        self.assertIsNone(analyser_ligne("parasite"))


class LectureJobTest(unittest.TestCase):
    def setUp(self) -> None:
        self._temporaire = tempfile.TemporaryDirectory()
        self.addCleanup(self._temporaire.cleanup)
        self.dossier = Path(self._temporaire.name)

    def test_job_valide_et_chemins_resolus(self) -> None:
        ecrire_signal(self.dossier, "a.f32", 1.0, 1.0)
        chemin = ecrire_job(
            self.dossier,
            [("a.wav", "a.f32")],
            threads_demandes=2,
            reglages={"bruit": "faible"},
        )
        job = charger_job(chemin)
        self.assertEqual(job.moteur, MOTEUR_DE_TEST)
        self.assertEqual(job.famille, FAMILLE_DE_TEST)
        self.assertEqual(job.threads_demandes, 2)
        self.assertEqual(job.reglages, {"bruit": "faible"})
        self.assertEqual(job.audios[0].nom, "a.wav")
        self.assertEqual(job.audios[0].chemin, (self.dossier / "a.f32").resolve())
        self.assertEqual(
            Path(job.modele["chemin"]), (self.dossier / "modele").resolve()
        )

    def test_job_invalide_refuse(self) -> None:
        contenu_valide = {
            "version": 1,
            "moteur": MOTEUR_DE_TEST,
            "famille": FAMILLE_DE_TEST,
            "modele": {"identifiant": "test/modele", "chemin": "modele"},
            "threads_demandes": 4,
            "reglages": {},
            "format_audio": FORMAT_AUDIO,
            "audios": [{"nom": "a.wav", "chemin": "a.f32"}],
        }
        mutations = {
            "version": {"version": 2},
            "format audio": {"format_audio": "wav"},
            "moteur vide": {"moteur": ""},
            "threads nuls": {"threads_demandes": 0},
            "threads booléens": {"threads_demandes": True},
            "audios vides": {"audios": []},
            "reglages non objet": {"reglages": []},
            "modele sans identifiant": {"modele": {"chemin": "modele"}},
            "audio sans nom": {"audios": [{"chemin": "a.f32"}]},
        }
        for libelle, changement in mutations.items():
            with self.subTest(cas=libelle):
                contenu = dict(contenu_valide)
                contenu.update(changement)
                chemin = self.dossier / "job.json"
                chemin.write_text(json.dumps(contenu), encoding="utf-8")
                with self.assertRaises(ErreurJob):
                    charger_job(chemin)

        chemin = self.dossier / "job.json"
        chemin.write_text("{", encoding="utf-8")
        with self.assertRaises(ErreurJob):
            charger_job(chemin)
        with self.assertRaises(ErreurJob):
            charger_job(self.dossier / "absent.json")


class ExecutionTest(unittest.TestCase):
    def setUp(self) -> None:
        self._temporaire = tempfile.TemporaryDirectory()
        self.addCleanup(self._temporaire.cleanup)
        self.dossier = Path(self._temporaire.name)
        adaptateur.reinitialiser()
        self.registre = registre_de_test()

    def test_chargement_unique_et_ordre_des_audios(self) -> None:
        audios = [
            ("un.wav", ecrire_signal(self.dossier, "un.f32", 1.0, 1.0)),
            ("deux.wav", ecrire_signal(self.dossier, "deux.f32", 1.0, 2.0)),
            ("trois.wav", ecrire_signal(self.dossier, "trois.f32", 1.0, 3.0)),
        ]
        chemin = ecrire_job(self.dossier, audios, reglages={"bruit": "faible"})
        _, evenements = executer_et_lire(chemin, self.registre)

        self.assertEqual(
            [evenement["type"] for evenement in evenements],
            [TYPE_CHARGEMENT, TYPE_AUDIO, TYPE_AUDIO, TYPE_AUDIO, TYPE_FIN],
        )
        self.assertEqual(adaptateur.compteur_chargements, 1)
        self.assertEqual(
            [appel["premier_echantillon"] for appel in adaptateur.appels],
            [1.0, 2.0, 3.0],
        )
        self.assertEqual(
            adaptateur.derniere_consigne["modele"]["identifiant"], "test/modele"
        )
        self.assertEqual(adaptateur.derniere_consigne["threads_demandes"], 4)
        for appel in adaptateur.appels:
            self.assertFalse(appel["modifiable"])
            self.assertEqual(appel["reglages"], {"bruit": "faible"})
            self.assertEqual(appel["taux_echantillonnage"], 16000)
        for position, evenement in enumerate(evenements[1:4]):
            with self.subTest(index=position):
                self.assertEqual(evenement["index"], position)
                self.assertEqual(evenement["nom"], audios[position][0])
                self.assertEqual(evenement["threads_demandes"], 4)
                self.assertIsNone(evenement["threads_appliques"])
                self.assertEqual(evenement["langue_imposee"], "fr")
                self.assertEqual(
                    evenement["reglages_effectifs"], {"modele": "test"}
                )
        self.assertEqual(evenements[-1]["audios_ok"], 3)
        self.assertEqual(evenements[-1]["audios_erreur"], 0)

    def test_fenetres_de_30_s_et_horodatages_decales(self) -> None:
        chemin = ecrire_job(
            self.dossier,
            [("long.wav", ecrire_signal(self.dossier, "long.f32", 31.0, 7.0))],
        )
        _, evenements = executer_et_lire(chemin, self.registre)
        audio = evenements[1]

        self.assertEqual(
            [appel["echantillons"] for appel in adaptateur.appels], [480000, 16000]
        )
        self.assertEqual(audio["nb_fenetres"], 2)
        self.assertEqual(audio["fenetre_s"], 30.0)
        self.assertEqual(audio["decoupage"], "fenetres-fixes")
        self.assertEqual(audio["duree_audio_s"], 31.0)
        self.assertEqual(audio["texte"], "héllo 480000 héllo 16000")
        self.assertEqual(len(audio["segments"]), 2)
        self.assertEqual(audio["segments"][0]["debut_s"], 0.0)
        self.assertEqual(audio["segments"][0]["fin_s"], 30.0)
        self.assertEqual(audio["segments"][1]["debut_s"], 30.0)
        self.assertEqual(audio["segments"][1]["fin_s"], 31.0)

    def test_audio_court_une_seule_fenetre(self) -> None:
        chemin = ecrire_job(
            self.dossier,
            [("court.wav", ecrire_signal(self.dossier, "court.f32", 10.0, 4.0))],
        )
        _, evenements = executer_et_lire(chemin, self.registre)
        audio = evenements[1]
        self.assertEqual(audio["nb_fenetres"], 1)
        self.assertEqual(audio["duree_audio_s"], 10.0)
        self.assertEqual(audio["segments"][0]["fin_s"], 10.0)

    def test_erreur_audio_puis_audios_suivants(self) -> None:
        adaptateur.reinitialiser(echec_appel=2)
        audios = [
            ("un.wav", ecrire_signal(self.dossier, "un.f32", 1.0, 1.0)),
            ("deux.wav", ecrire_signal(self.dossier, "deux.f32", 1.0, 2.0)),
            ("trois.wav", ecrire_signal(self.dossier, "trois.f32", 1.0, 3.0)),
        ]
        chemin = ecrire_job(self.dossier, audios)
        _, evenements = executer_et_lire(chemin, self.registre)

        self.assertEqual(
            [evenement["type"] for evenement in evenements],
            [TYPE_CHARGEMENT, TYPE_AUDIO, TYPE_AUDIO_ERREUR, TYPE_AUDIO, TYPE_FIN],
        )
        erreur = evenements[2]
        self.assertEqual(erreur["index"], 1)
        self.assertEqual(erreur["nom"], "deux.wav")
        self.assertIn("échec simulé", erreur["erreur"])
        self.assertNotIn("rtf", erreur)
        self.assertEqual(
            [appel["premier_echantillon"] for appel in adaptateur.appels],
            [1.0, 2.0, 3.0],
        )
        self.assertEqual(evenements[-1]["audios_ok"], 2)
        self.assertEqual(evenements[-1]["audios_erreur"], 1)

    def test_duree_nulle_est_une_erreur_sans_rtf(self) -> None:
        (self.dossier / "vide.f32").write_bytes(b"")
        chemin = ecrire_job(
            self.dossier,
            [
                ("vide.wav", "vide.f32"),
                ("ok.wav", ecrire_signal(self.dossier, "ok.f32", 1.0, 1.0)),
            ],
        )
        _, evenements = executer_et_lire(chemin, self.registre)

        erreur = evenements[1]
        self.assertEqual(erreur["type"], TYPE_AUDIO_ERREUR)
        self.assertIn("durée décodée nulle", erreur["erreur"])
        self.assertEqual(evenements[2]["type"], TYPE_AUDIO)
        self.assertEqual(len(adaptateur.appels), 1)

    def test_resultat_d_adaptateur_invalide_est_une_erreur_audio(self) -> None:
        adaptateur.reinitialiser(resultat_invalide=True)
        chemin = ecrire_job(
            self.dossier,
            [
                ("un.wav", ecrire_signal(self.dossier, "un.f32", 1.0, 1.0)),
                ("deux.wav", ecrire_signal(self.dossier, "deux.f32", 1.0, 2.0)),
            ],
        )
        _, evenements = executer_et_lire(chemin, self.registre)

        self.assertEqual(
            [evenement["type"] for evenement in evenements],
            [TYPE_CHARGEMENT, TYPE_AUDIO_ERREUR, TYPE_AUDIO, TYPE_FIN],
        )
        self.assertIn("dict", evenements[1]["erreur"])
        self.assertEqual(evenements[2]["nom"], "deux.wav")

    def test_taille_non_multiple_de_4_est_une_erreur_audio(self) -> None:
        (self.dossier / "tronque.f32").write_bytes(b"0123456789")
        chemin = ecrire_job(
            self.dossier,
            [
                ("tronque.wav", "tronque.f32"),
                ("ok.wav", ecrire_signal(self.dossier, "ok.f32", 1.0, 1.0)),
            ],
        )
        _, evenements = executer_et_lire(chemin, self.registre)

        erreur = evenements[1]
        self.assertEqual(erreur["type"], TYPE_AUDIO_ERREUR)
        self.assertIn("multiple de 4", erreur["erreur"])
        self.assertNotIn("rtf", erreur)
        self.assertEqual(evenements[2]["type"], TYPE_AUDIO)
        self.assertEqual(adaptateur.appels[0]["premier_echantillon"], 1.0)

    def test_metadonnees_divergentes_entre_fenetres(self) -> None:
        for divergence in ("effectifs", "langue", "threads"):
            with self.subTest(divergence=divergence):
                adaptateur.reinitialiser(divergence=divergence)
                chemin = ecrire_job(
                    self.dossier,
                    [
                        (
                            "long.wav",
                            ecrire_signal(self.dossier, "long.f32", 31.0, 7.0),
                        )
                    ],
                )
                _, evenements = executer_et_lire(chemin, self.registre)

                self.assertEqual(
                    [evenement["type"] for evenement in evenements],
                    [TYPE_CHARGEMENT, TYPE_AUDIO_ERREUR, TYPE_FIN],
                )
                self.assertIn("divergentes", evenements[1]["erreur"])
                self.assertNotIn("rtf", evenements[1])
                self.assertEqual(evenements[-1]["audios_erreur"], 1)

    def test_sortie_parasite_journalisee_sans_interruption(self) -> None:
        adaptateur.reinitialiser(parasite=True)
        chemin = ecrire_job(
            self.dossier,
            [
                ("un.wav", ecrire_signal(self.dossier, "un.f32", 1.0, 1.0)),
                ("deux.wav", ecrire_signal(self.dossier, "deux.f32", 1.0, 2.0)),
            ],
        )
        lignes, evenements = executer_et_lire(chemin, self.registre)

        parasites = [ligne for ligne in lignes if not ligne.startswith(PREFIXE_EVENEMENT)]
        self.assertEqual(parasites, ["bavardage de bibliothèque sans préfixe"])
        self.assertEqual(
            [evenement["type"] for evenement in evenements],
            [TYPE_CHARGEMENT, TYPE_AUDIO, TYPE_AUDIO, TYPE_FIN],
        )
        self.assertEqual(evenements[1]["texte"], "héllo 16000")

    def test_mesures_brutes_avec_unites(self) -> None:
        chemin = ecrire_job(
            self.dossier,
            [("un.wav", ecrire_signal(self.dossier, "un.f32", 1.0, 1.0))],
        )
        _, evenements = executer_et_lire(chemin, self.registre)
        audio = evenements[1]

        for cle in audio:
            self.assertNotIn("%", cle)
            self.assertNotIn("pourcent", cle)
            self.assertNotIn("swap", cle)
        self.assertGreaterEqual(audio["duree_transcription_s"], 0.0)
        self.assertGreaterEqual(audio["temps_cpu_s"], 0.0)
        self.assertGreater(audio["duree_audio_s"], 0.0)
        self.assertAlmostEqual(
            audio["rtf"], audio["duree_transcription_s"] / audio["duree_audio_s"]
        )
        self.assertIsInstance(audio["pic_memoire_octets"], int)
        self.assertGreater(audio["pic_memoire_octets"], 0)
        self.assertIsInstance(evenements[-1]["pic_memoire_octets"], int)


class MoteurRefuseTest(unittest.TestCase):
    def setUp(self) -> None:
        self._temporaire = tempfile.TemporaryDirectory()
        self.addCleanup(self._temporaire.cleanup)
        self.dossier = Path(self._temporaire.name)

    def test_moteur_reel_non_qualifie_refuse(self) -> None:
        chemin = ecrire_job(
            self.dossier,
            [("a.wav", "a.f32")],
            moteur="faster-whisper",
            famille="whisper",
        )
        with self.assertRaises(ErreurMoteur) as contexte:
            executer(charger_job(chemin), creer_registre_fourni())
        self.assertIn("non qualifiée", str(contexte.exception))

    def test_moteur_ou_famille_inconnus(self) -> None:
        chemin = ecrire_job(
            self.dossier, [("a.wav", "a.f32")], moteur="inconnu"
        )
        with self.assertRaises(ErreurMoteur):
            executer(charger_job(chemin), creer_registre_fourni())
        chemin = ecrire_job(
            self.dossier, [("a.wav", "a.f32")], famille="autre"
        )
        with self.assertRaises(ErreurMoteur):
            executer(charger_job(chemin), registre_de_test())


class MesureMemoireTest(unittest.TestCase):
    def test_pic_linux_en_octets(self) -> None:
        import resource

        attendu = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss) * 1024
        self.assertEqual(_pic_memoire_unix(), attendu)
        self.assertIsInstance(pic_memoire(), int)
        self.assertGreater(pic_memoire(), 0)

    def test_pic_windows_via_faux_psutil(self) -> None:
        class FauxProcessus:
            def __init__(self, memoire: object) -> None:
                self._memoire = memoire

            def memory_info(self) -> object:
                return self._memoire

        def faux_psutil(memoire: object) -> SimpleNamespace:
            return SimpleNamespace(Process=lambda: FauxProcessus(memoire))

        cas = {
            "peak_wset": (SimpleNamespace(peak_wset=123456), 123456),
            "aucun pic": (SimpleNamespace(rss=10), None),
        }
        for libelle, (memoire, attendu) in cas.items():
            with self.subTest(cas=libelle):
                with mock.patch.dict(sys.modules, {"psutil": faux_psutil(memoire)}):
                    self.assertEqual(_pic_memoire_windows(), attendu)

        with mock.patch.dict(sys.modules, {"psutil": None}):
            self.assertIsNone(_pic_memoire_windows())


class IsolementTest(unittest.TestCase):
    def setUp(self) -> None:
        self._temporaire = tempfile.TemporaryDirectory()
        self.addCleanup(self._temporaire.cleanup)
        self.dossier = Path(self._temporaire.name)

    def test_runner_n_importe_aucun_module_serveur(self) -> None:
        resultat = subprocess.run(
            [sys.executable, "-c", CODE_SANS_MODULE_SERVEUR],
            cwd=RACINE_PROJET,
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        self.assertEqual(
            resultat.returncode,
            0,
            f"modules serveur chargés : {resultat.stdout.strip()} {resultat.stderr}",
        )
        self.assertEqual(resultat.stdout.strip(), "ok")

    def test_lancement_depuis_un_dossier_courant_quelconque(self) -> None:
        chemin = ecrire_job(
            self.dossier,
            [("a.wav", "a.f32")],
            moteur="faster-whisper",
            famille="whisper",
        )
        environ = {
            cle: valeur
            for cle, valeur in os.environ.items()
            if cle != "PYTHONPATH"
        }
        resultat = subprocess.run(
            [
                sys.executable,
                str(RACINE_PROJET / "engines" / "runner.py"),
                str(chemin),
            ],
            cwd=self.dossier,
            env=environ,
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        self.assertEqual(resultat.returncode, 3, resultat.stderr)
        self.assertEqual(resultat.stdout, "")
        self.assertIn("non qualifiée", resultat.stderr)


if __name__ == "__main__":
    unittest.main()
