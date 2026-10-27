"""Tests de la récupération des exécutions restées en cours (tâche 6.5).

Les `run.json` sont produits par le vrai écrivain de la tâche 6.4
(`ConsignateurExecution`), pour que la clôture soit exercée sur le format réel.
Un vrai sous-processus Python sert de moteur survivant : il n'est terminé que si
son identité (PID et heure de création) concorde, et un processus témoin dont
l'identité ne concorde pas n'est jamais tué. La descendance réelle (fils et
petit-fils), la purge sélective de `data/cache` (préfixe des dossiers de travail,
liens jamais suivis) et le journal d'une ligne par exécution sont éprouvés.
Tout vit dans un dossier temporaire et aucun test n'écrit sous le `data/` du
dépôt.
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from datetime import datetime
from pathlib import Path
from typing import Any
from unittest import mock

import psutil

from transcription_bench import recuperation
from transcription_bench.execution_moteur import (
    PREFIXE_DOSSIER_TRAVAIL as PREFIXE_DOSSIER_TRAVAIL_MOTEUR,
    AudioPrepare,
    ResultatAudio,
)
from transcription_bench.executions import DemandeExecution
from transcription_bench.recuperation import (
    PREFIXE_DOSSIER_TRAVAIL,
    EtatAnterieurNonTraitable,
    recuperer_executions_anterieures,
)
from transcription_bench.resultats import (
    ETAT_ABANDONNEE,
    ETAT_EN_COURS,
    ETATS_FINAUX,
    SCHEMA,
    STATUT_NON_TRAITE,
    STATUT_OK,
    ConsignateurExecution,
    metadonnees_moteur,
)

MACHINE = {"os": "Linux", "coeurs_physiques": 4, "ram_totale_octets": 1024}
PROGRAMME = {"nom": "transcription-bench", "version": "0.1.0", "python": "3.12.0"}
MOTEUR = metadonnees_moteur("factice", "Moteur factice", factice=True)
DELAI_PROCESSUS = 30.0
CODE_DORT = "import time; time.sleep(60)"
#: Moteur qui ignore `terminate` : seule la seconde étape (`kill`) le termine.
CODE_INSENSIBLE = """
import signal, sys, time
from pathlib import Path

signal.signal(signal.SIGTERM, signal.SIG_IGN)
Path(sys.argv[1]).write_text("prêt", encoding="utf-8")
time.sleep(60)
"""
#: Moteur qui a un fils, lequel a lui-même un petit-fils : `children(recursive=True)`
#: doit les terminer tous les deux. Le petit-fils écrit son PID via son parent.
CODE_ARBRE = """
import subprocess, sys, time

CODE_FILS = (
    "import subprocess, sys, time\\n"
    "from pathlib import Path\\n"
    "petit = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])\\n"
    "Path(sys.argv[1]).write_text(str(petit.pid), encoding='utf-8')\\n"
    "time.sleep(60)\\n"
)
subprocess.Popen([sys.executable, "-c", CODE_FILS, sys.argv[1]])
time.sleep(60)
"""
#: Processus factice pour les cas qu'aucun vrai processus ne peut produire :
#: il survit à `terminate` comme à `kill`.
PID_FACTICE = 424242


def demande(audios: tuple[str, ...] = ("a.wav", "b.wav")) -> DemandeExecution:
    """Demande d'exécution minimale, sans effet de bord."""
    return DemandeExecution(
        moteur="factice",
        cle="0" * 64,
        identifiant="modèle de test",
        id_resolu="modèle de test",
        commit="aucun",
        famille="factice",
        fichier_gguf=None,
        audios=audios,
        threads=2,
        reglages=(),
        fenetre_fixe_secondes=30.0,
        synthetique=True,
    )


def audio_transcrit(index: int = 0, nom: str = "a.wav") -> ResultatAudio:
    """Audio transcrit, avec des mesures d'événement explicites."""
    return ResultatAudio(
        index=index,
        nom=nom,
        prepare=AudioPrepare(
            index=index,
            nom=nom,
            fichier_brut=f"audio-{index}.f32",
            format="wav",
            taille_octets=100,
            empreinte_sha256="a" * 64,
            duree_indicative=2.0,
            duree_decodee=2.0,
            echantillons=32000,
            temps_decodage=0.25,
        ),
        evenement={
            "type": "audio",
            "index": index,
            "nom": nom,
            "texte": "texte simulé",
            "segments": [],
            "duree_transcription_s": 1.0,
            "pic_memoire_octets": 4096,
            "fenetre_s": 30.0,
            "decoupage": "fenetres-fixes",
            "factice": True,
            "mesures_simulees": True,
        },
        erreur=None,
        factice=True,
        synthetique=True,
    )


def lancer_temoin(code: str = CODE_DORT, *arguments: str) -> subprocess.Popen[bytes]:
    """Lance un vrai sous-processus Python, utilisé comme moteur ou témoin."""
    return subprocess.Popen([sys.executable, "-c", code, *arguments])


def iso(epoch: float) -> str:
    """Horodatage ISO local à la seconde, comme `lance_a` du serveur."""
    return datetime.fromtimestamp(epoch).astimezone().isoformat(timespec="seconds")


class RecuperationTest(unittest.TestCase):
    """Base : dossier de données temporaire, témoins nettoyés après le test."""

    def setUp(self) -> None:
        temporaire = tempfile.TemporaryDirectory()
        self.addCleanup(temporaire.cleanup)
        self.donnees = Path(temporaire.name) / "data-projet"
        self._essai = 0

    # -- outillage ---------------------------------------------------------

    def ouvrir_consignation(
        self,
        audios: tuple[str, ...] = ("a.wav", "b.wav"),
        *,
        pid: int | None = None,
        creation: float | None = None,
        source: str = "psutil",
        lance_a: str | None = None,
    ) -> ConsignateurExecution:
        """Crée un `run.json` `running` avec le vrai écrivain de la tâche 6.4."""
        self._essai += 1
        consignateur = ConsignateurExecution(
            self.donnees,
            demande(audios),
            MOTEUR,
            debut=time.perf_counter(),
            machine=MACHINE,
            programme=PROGRAMME,
            base="20260101-120000",
            court_id=f"{self._essai:08x}",
        )
        self.assertTrue(consignateur.ouvrir(), consignateur.erreur)
        self.addCleanup(consignateur.fermer)
        if pid is not None:
            self.assertTrue(
                consignateur.enregistrer_processus(
                    pid=pid,
                    heure_creation=creation,
                    source=source,
                    lance_a=iso(time.time()) if lance_a is None else lance_a,
                )
            )
        return consignateur

    def ecrire_run(self, nom: str, contenu: object) -> Path:
        """Écrit un `run.json` brut, pour les cas que l'écrivain ne produit pas."""
        dossier = self.donnees / "results" / nom
        dossier.mkdir(parents=True)
        run_json = dossier / "run.json"
        if isinstance(contenu, str):
            run_json.write_text(contenu, encoding="utf-8")
        else:
            run_json.write_text(json.dumps(contenu), encoding="utf-8")
        return run_json

    def run_json(self, consignateur: ConsignateurExecution) -> Path:
        return Path(consignateur.dossier) / "run.json"

    def lire(self, chemin: Path) -> dict[str, Any]:
        return json.loads(chemin.read_text(encoding="utf-8"))

    def arborescence(self) -> dict[str, bytes]:
        return {
            str(chemin.relative_to(self.donnees)): chemin.read_bytes()
            for chemin in sorted(self.donnees.rglob("*"))
            if chemin.is_file()
        }

    def attendre_mort(self, enfant: subprocess.Popen[bytes]) -> None:
        """Attend la sortie du témoin et vérifie qu'il n'est plus vivant."""
        try:
            enfant.wait(timeout=DELAI_PROCESSUS)
        except subprocess.TimeoutExpired:
            enfant.kill()
            enfant.wait()
            self.fail("le processus n'a pas été terminé par la récupération")

    def attendre_disparu(self, pid: int) -> None:
        """Attend la disparition d'un PID, ou qu'il devienne un zombie non collecté."""
        echeance = time.monotonic() + DELAI_PROCESSUS
        while time.monotonic() < echeance:
            try:
                if psutil.Process(pid).status() == psutil.STATUS_ZOMBIE:
                    return
            except (psutil.NoSuchProcess, psutil.ZombieProcess):
                return
            time.sleep(0.02)
        self.fail(f"le processus {pid} a survécu à la récupération")

    def recuperer(self, **options: Any) -> str:
        """Récupère en capturant le journal ; renvoie la sortie d'erreur."""
        sortie = io.StringIO()
        with contextlib.redirect_stderr(sortie):
            recuperer_executions_anterieures(self.donnees, **options)
        return sortie.getvalue()

    def donnees_neuves(self) -> Path:
        """Nouveau dossier de données, pour isoler les cas d'un même test."""
        temporaire = tempfile.TemporaryDirectory()
        self.addCleanup(temporaire.cleanup)
        return Path(temporaire.name) / "data-projet"

    def ecrire_processus(
        self, consignateur: ConsignateurExecution, **champs: Any
    ) -> Path:
        """Remplace `processus_moteur` dans `run.json`, pour les états dégradés."""
        run_json = self.run_json(consignateur)
        contenu = self.lire(run_json)
        contenu["processus_moteur"] = champs
        run_json.write_text(json.dumps(contenu), encoding="utf-8")
        return run_json

    def nettoyer(self, enfant: subprocess.Popen[bytes]) -> None:
        """Filet de sécurité : aucun témoin ne doit survivre au test."""
        if enfant.poll() is None:
            enfant.kill()
            enfant.wait()

    def nettoyer_pid(self, pid: int) -> None:
        """Filet de sécurité pour un processus repéré par son seul PID."""
        try:
            psutil.Process(pid).kill()
        except (psutil.NoSuchProcess, psutil.ZombieProcess, psutil.AccessDenied):
            pass

    def temoin(self, code: str = CODE_DORT, *arguments: str) -> subprocess.Popen[bytes]:
        """Sous-processus Python vivant, nettoyé en fin de test."""
        enfant = lancer_temoin(code, *arguments)
        self.addCleanup(self.nettoyer, enfant)
        return enfant

    # -- moteur survivant --------------------------------------------------

    def test_moteur_survivant_identifie_est_termine_puis_abandonne(self) -> None:
        enfant = self.temoin()
        creation = psutil.Process(enfant.pid).create_time()
        consignateur = self.ouvrir_consignation(
            pid=enfant.pid, creation=creation, source="psutil"
        )
        run_json = self.run_json(consignateur)

        journal = self.recuperer()

        self.attendre_mort(enfant)
        contenu = self.lire(run_json)
        self.assertEqual(contenu["etat"], ETAT_ABANDONNEE)
        self.assertEqual(contenu["processus_moteur"]["pid"], enfant.pid)
        # Une ligne pour le moteur terminé, une pour la clôture, sans secret.
        self.assertIn(f"moteur PID {enfant.pid} terminé", journal)
        self.assertIn(f"exécution {run_json.parent.name} close en abandonnée", journal)

    def test_descendance_reelle_est_terminee(self) -> None:
        marqueur = self.donnees / "petit-fils"
        marqueur.parent.mkdir(parents=True, exist_ok=True)
        enfant = self.temoin(CODE_ARBRE, str(marqueur))
        echeance = time.monotonic() + DELAI_PROCESSUS
        while not marqueur.exists() and time.monotonic() < echeance:
            time.sleep(0.02)
        self.assertTrue(marqueur.exists(), "l'arbre de processus n'a pas démarré")
        petit_fils = int(marqueur.read_text(encoding="utf-8"))
        self.addCleanup(self.nettoyer_pid, petit_fils)
        creation = psutil.Process(enfant.pid).create_time()
        consignateur = self.ouvrir_consignation(
            pid=enfant.pid, creation=creation, source="psutil"
        )

        self.recuperer()

        self.attendre_mort(enfant)
        self.attendre_disparu(petit_fils)
        self.assertEqual(self.lire(self.run_json(consignateur))["etat"], ETAT_ABANDONNEE)

    def test_heure_de_creation_du_serveur_en_repli(self) -> None:
        enfant = self.temoin()
        creation = psutil.Process(enfant.pid).create_time()
        consignateur = self.ouvrir_consignation(
            pid=enfant.pid,
            creation=None,
            source="serveur",
            lance_a=iso(creation),
        )

        self.recuperer()

        self.attendre_mort(enfant)
        self.assertEqual(self.lire(self.run_json(consignateur))["etat"], ETAT_ABANDONNEE)

    def test_pid_reutilise_ou_heure_differente_n_est_jamais_tue(self) -> None:
        temoin = self.temoin()
        creation = psutil.Process(temoin.pid).create_time()
        cas = {
            "heure-differente": {
                "creation": creation - 3600.0,
                "source": "psutil",
                "lance_a": None,
            },
            "lance_a-differente": {
                "creation": None,
                "source": "serveur",
                "lance_a": iso(creation - 3600.0),
            },
        }
        for nom, reglages in cas.items():
            with self.subTest(nom):
                self._essai += 1
                consignateur = self.ouvrir_consignation(
                    ("a.wav",), pid=temoin.pid, **reglages
                )

                journal = self.recuperer()

                self.assertIsNone(temoin.poll(), "un processus non identifié a été tué")
                contenu = self.lire(self.run_json(consignateur))
                self.assertEqual(contenu["etat"], ETAT_ABANDONNEE)
                self.assertIn(
                    f"PID {temoin.pid} ignoré : identité différente", journal
                )

    @unittest.skipIf(os.name == "nt", "SIGTERM ne peut pas être ignoré sous Windows")
    def test_moteur_insensible_a_terminate_est_tue(self) -> None:
        marqueur = self.donnees / "pret"
        marqueur.parent.mkdir(parents=True, exist_ok=True)
        enfant = self.temoin(CODE_INSENSIBLE, str(marqueur))
        echeance = time.monotonic() + DELAI_PROCESSUS
        while not marqueur.exists() and time.monotonic() < echeance:
            time.sleep(0.02)
        self.assertTrue(marqueur.exists(), "le témoin n'a pas démarré")
        creation = psutil.Process(enfant.pid).create_time()
        consignateur = self.ouvrir_consignation(
            ("a.wav",), pid=enfant.pid, creation=creation, source="psutil"
        )

        self.recuperer(delai_terminaison=0.3)

        self.attendre_mort(enfant)
        self.assertEqual(self.lire(self.run_json(consignateur))["etat"], ETAT_ABANDONNEE)

    def test_moteur_deja_mort_est_abandonne_sans_erreur(self) -> None:
        disparu = subprocess.Popen([sys.executable, "-c", "pass"])
        disparu.wait(timeout=DELAI_PROCESSUS)
        consignateur = self.ouvrir_consignation(
            pid=disparu.pid, creation=time.time(), source="psutil"
        )

        self.recuperer()

        self.assertEqual(self.lire(self.run_json(consignateur))["etat"], ETAT_ABANDONNEE)

    def test_pid_du_serveur_n_est_jamais_tue(self) -> None:
        consignateur = self.ouvrir_consignation(
            pid=os.getpid(),
            creation=psutil.Process().create_time(),
            source="psutil",
        )

        journal = self.recuperer()

        self.assertIn(f"PID {os.getpid()} ignoré : identité différente", journal)
        self.assertEqual(self.lire(self.run_json(consignateur))["etat"], ETAT_ABANDONNEE)

    def test_moteur_jamais_lance_est_abandonne_sans_erreur(self) -> None:
        consignateur = self.ouvrir_consignation()

        self.recuperer()

        contenu = self.lire(self.run_json(consignateur))
        self.assertEqual(contenu["etat"], ETAT_ABANDONNEE)
        self.assertIsNone(contenu["processus_moteur"]["pid"])

    # -- identification impossible ou incomplète ---------------------------

    def test_identite_non_verifiable_refuse_sans_tuer(self) -> None:
        enfant = self.temoin()
        consignateur = self.ouvrir_consignation(
            ("a.wav",), pid=enfant.pid, creation=None, source="serveur"
        )
        # Ni heure de création système, ni `lance_a` : aucune preuve possible.
        run_json = self.ecrire_processus(
            consignateur,
            pid=enfant.pid,
            heure_creation=None,
            heure_creation_source="serveur",
        )
        avant = run_json.read_bytes()

        with self.assertRaises(EtatAnterieurNonTraitable) as capture:
            self.recuperer()

        message = str(capture.exception)
        self.assertIn("non vérifiable", message)
        self.assertIn(str(enfant.pid), message)
        self.assertIn(str(run_json), message)
        self.assertIsNone(enfant.poll(), "un processus non identifié a été tué")
        self.assertEqual(run_json.read_bytes(), avant)

    def test_processus_inaccessible_refuse_le_demarrage(self) -> None:
        consignateur = self.ouvrir_consignation(
            ("a.wav",), pid=PID_FACTICE, creation=time.time(), source="psutil"
        )
        run_json = self.run_json(consignateur)
        avant = run_json.read_bytes()

        with mock.patch.object(
            recuperation.psutil,
            "Process",
            side_effect=psutil.AccessDenied(pid=PID_FACTICE),
        ):
            with self.assertRaises(EtatAnterieurNonTraitable) as capture:
                self.recuperer()

        message = str(capture.exception)
        self.assertIn("inaccessible", message)
        self.assertIn(str(PID_FACTICE), message)
        self.assertIn(str(run_json), message)
        self.assertEqual(run_json.read_bytes(), avant)

    def test_erreur_systeme_inattendue_refuse_sans_trace(self) -> None:
        consignateur = self.ouvrir_consignation(
            ("a.wav",), pid=PID_FACTICE, creation=time.time(), source="psutil"
        )
        run_json = self.run_json(consignateur)
        avant = run_json.read_bytes()

        panne = psutil.Error()
        panne.msg = "panne simulée"
        with mock.patch.object(recuperation.psutil, "Process", side_effect=panne):
            with self.assertRaises(EtatAnterieurNonTraitable) as capture:
                self.recuperer()

        message = str(capture.exception)
        self.assertIn("impossible", message)
        self.assertIn("panne simulée", message)
        self.assertIn(str(run_json), message)
        self.assertEqual(run_json.read_bytes(), avant)

    def test_survivant_apres_kill_refuse_le_demarrage(self) -> None:
        consignateur = self.ouvrir_consignation(
            ("a.wav",), pid=PID_FACTICE, creation=time.time(), source="psutil"
        )
        run_json = self.run_json(consignateur)
        avant = run_json.read_bytes()
        factice = mock.Mock()
        factice.pid = PID_FACTICE
        factice.status.return_value = "sleeping"
        factice.is_running.return_value = True
        factice.create_time.return_value = time.time()
        factice.children.return_value = []

        with (
            mock.patch.object(recuperation.psutil, "Process", return_value=factice),
            mock.patch.object(recuperation.psutil, "wait_procs", return_value=([], [])),
        ):
            with self.assertRaises(EtatAnterieurNonTraitable) as capture:
                self.recuperer(delai_terminaison=0.01)

        message = str(capture.exception)
        self.assertIn("résiste", message)
        self.assertIn(str(PID_FACTICE), message)
        self.assertIn(str(run_json), message)
        self.assertEqual(factice.terminate.call_count, 1)
        self.assertEqual(factice.kill.call_count, 1)
        self.assertEqual(run_json.read_bytes(), avant)

    # -- état abandonné ----------------------------------------------------

    def test_etat_abandonne_conserve_les_resultats_et_marque_les_absents(self) -> None:
        consignateur = self.ouvrir_consignation(("a.wav", "b.wav", "c.wav"))
        consignateur.mesures.duree_operation_s = 12.5
        consignateur.mesures.duree_processus_s = 11.0
        consignateur.mesures.duree_chargement_s = 3.25
        consignateur.mesures.pic_memoire_octets = 4096
        self.assertTrue(consignateur.enregistrer_audio(audio_transcrit(0, "a.wav")))
        run_json = self.run_json(consignateur)
        resultat_premier = Path(consignateur.dossier) / "1-a.wav" / "result.json"
        avant = (resultat_premier.read_bytes(), resultat_premier.stat().st_mtime_ns)
        transcription = Path(consignateur.dossier) / "1-a.wav" / "transcription.txt"
        avant_transcription = (
            transcription.read_bytes(),
            transcription.stat().st_mtime_ns,
        )

        self.recuperer()

        contenu = self.lire(run_json)
        self.assertEqual(contenu["etat"], ETAT_ABANDONNEE)
        self.assertIsNotNone(contenu["fin"])
        # Durées finales inconnues, mesures d'audio conservées, pic partiel.
        self.assertIsNone(contenu["mesures"]["duree_operation_s"])
        self.assertIsNone(contenu["mesures"]["duree_processus_s"])
        self.assertEqual(contenu["mesures"]["duree_chargement_s"], 3.25)
        self.assertEqual(contenu["mesures"]["pic_memoire_octets"], 4096)
        self.assertIs(contenu["mesures"]["pic_memoire_partiel"], True)
        # Statuts : le premier audio garde son résultat, les autres sont absents.
        statuts = [plan["statut"] for plan in contenu["audios"]]
        self.assertEqual(statuts, [STATUT_OK, STATUT_NON_TRAITE, STATUT_NON_TRAITE])
        self.assertEqual(contenu["progression"]["audios_traites"], 1)
        self.assertEqual(contenu["progression"]["audios_total"], 3)
        # Aucun résultat existant n'est réécrit.
        self.assertEqual(
            (resultat_premier.read_bytes(), resultat_premier.stat().st_mtime_ns), avant
        )
        self.assertEqual(
            (transcription.read_bytes(), transcription.stat().st_mtime_ns),
            avant_transcription,
        )

    def test_resultat_present_mais_non_encore_reflete_fait_foi(self) -> None:
        consignateur = self.ouvrir_consignation(("a.wav", "b.wav"))
        consignateur.enregistrer_audio(audio_transcrit(0, "a.wav"))
        run_json = self.run_json(consignateur)
        # État courant relu puis réécrit avec un statut resté non traité, comme
        # après une écriture de `result.json` non suivie de celle de `run.json`.
        contenu = self.lire(run_json)
        contenu["audios"][0]["statut"] = STATUT_NON_TRAITE
        run_json.write_text(json.dumps(contenu), encoding="utf-8")

        self.recuperer()

        plan = self.lire(run_json)["audios"][0]
        self.assertEqual(plan["statut"], STATUT_OK)
        self.assertEqual(plan["fenetre_s"], 30.0)

    def test_pic_memoire_absent_reste_absent(self) -> None:
        consignateur = self.ouvrir_consignation(("a.wav",))

        self.recuperer()

        mesures = self.lire(self.run_json(consignateur))["mesures"]
        self.assertIsNone(mesures["pic_memoire_octets"])
        self.assertIsNone(mesures["pic_memoire_partiel"])

    # -- immuabilité et rejouabilité ---------------------------------------

    def test_execution_finale_n_est_jamais_modifiee(self) -> None:
        for etat in sorted(ETATS_FINAUX):
            self.ecrire_run(f"20260101-1200{len(etat)}-{etat}", {"etat": etat})
        # Le refus pour schéma inconnu ou contenu incohérent ne vaut que pour une
        # exécution `running` : une exécution finale n'est jamais interprétée.
        self.ecrire_run(
            "20260101-120000-finale-incoherente",
            {"etat": ETAT_ABANDONNEE, "schema": 99, "audios": "incohérent"},
        )
        avant = self.arborescence()
        horodatages = {
            chemin: chemin.stat().st_mtime_ns
            for chemin in self.donnees.rglob("run.json")
        }

        self.recuperer()

        self.assertEqual(self.arborescence(), avant)
        for chemin, mtime in horodatages.items():
            self.assertEqual(chemin.stat().st_mtime_ns, mtime)

    def test_recuperation_rejouable(self) -> None:
        consignateur = self.ouvrir_consignation(("a.wav",))
        run_json = self.run_json(consignateur)

        self.recuperer()
        apres = (run_json.read_bytes(), run_json.stat().st_mtime_ns)
        self.recuperer()

        self.assertEqual((run_json.read_bytes(), run_json.stat().st_mtime_ns), apres)

    def test_dossier_sans_run_json_est_ignore(self) -> None:
        orphelin = self.donnees / "results" / "20260101-120000-aaaaaaaa" / "1-a.wav"
        orphelin.mkdir(parents=True)

        self.recuperer()

        self.assertTrue(orphelin.is_dir())

    def test_sans_dossier_de_resultats_aucune_creation(self) -> None:
        self.recuperer()

        self.assertFalse(self.donnees.exists())

    # -- refus de démarrer -------------------------------------------------

    def test_run_json_illisible_refuse_sans_modification(self) -> None:
        run_json = self.ecrire_run("20260101-120000-casse", "{ pas du json")
        avant = self.arborescence()

        with self.assertRaises(EtatAnterieurNonTraitable) as capture:
            self.recuperer()

        message = str(capture.exception)
        self.assertIn("illisible", message)
        self.assertIn(str(run_json), message)
        self.assertIn("Aucun fichier n'a été modifié", message)
        self.assertEqual(self.arborescence(), avant)

    def test_run_json_incoherent_ou_schema_inconnu_refuse(self) -> None:
        # Chaque cas ne pèche que par son contrôle : tous les autres champs sont
        # valides, et le message attendu est propre à ce contrôle. Si l'un d'eux
        # disparaissait, le cas serait traité (ou refusé autrement) et le test
        # échouerait.
        valide = {"schema": SCHEMA, "etat": ETAT_EN_COURS}
        cas: dict[str, tuple[object, str]] = {
            "sans-etat": (
                {"schema": SCHEMA, "processus_moteur": {"pid": None}, "audios": []},
                "clé 'etat' absente ou invalide",
            ),
            "etat-vide": (
                {
                    "schema": SCHEMA,
                    "etat": "",
                    "processus_moteur": {"pid": None},
                    "audios": [],
                },
                "clé 'etat' absente ou invalide",
            ),
            "etat-inconnu": (
                {
                    **valide,
                    "etat": "en-cours-peut-etre",
                    "processus_moteur": {"pid": None},
                    "audios": [],
                },
                "état inconnu",
            ),
            "liste": ([], "objet JSON attendu"),
            "schema-inconnu": (
                {
                    **valide,
                    "schema": 99,
                    "processus_moteur": {"pid": None},
                    "audios": [],
                },
                "schéma non pris en charge",
            ),
            "schema-texte": (
                {
                    **valide,
                    "schema": "1",
                    "processus_moteur": {"pid": None},
                    "audios": [],
                },
                "schéma non pris en charge",
            ),
            "sans-schema": (
                {
                    "etat": ETAT_EN_COURS,
                    "processus_moteur": {"pid": None},
                    "audios": [],
                },
                "schéma non pris en charge",
            ),
            "sans-processus": (
                {**valide, "audios": []},
                "clé 'processus_moteur' absente ou invalide",
            ),
            "processus-non-objet": (
                {**valide, "processus_moteur": [1], "audios": []},
                "clé 'processus_moteur' absente ou invalide",
            ),
            "pid-invalide": (
                {**valide, "processus_moteur": {"pid": "12"}, "audios": []},
                "PID consigné invalide",
            ),
            "pid-nul": (
                {**valide, "processus_moteur": {"pid": 0}, "audios": []},
                "PID consigné invalide",
            ),
            "heure-booleenne": (
                {
                    **valide,
                    "processus_moteur": {"pid": None, "heure_creation": True},
                    "audios": [],
                },
                "heure de création consignée invalide",
            ),
            "heure-texte": (
                {
                    **valide,
                    "processus_moteur": {"pid": None, "heure_creation": "hier"},
                    "audios": [],
                },
                "heure de création consignée invalide",
            ),
            "heure-nan": (
                {
                    **valide,
                    "processus_moteur": {"pid": None, "heure_creation": float("nan")},
                    "audios": [],
                },
                "heure de création consignée invalide",
            ),
            "heure-infinie": (
                {
                    **valide,
                    "processus_moteur": {"pid": None, "heure_creation": float("inf")},
                    "audios": [],
                },
                "heure de création consignée invalide",
            ),
            "source-non-texte": (
                {
                    **valide,
                    "processus_moteur": {"pid": None, "heure_creation_source": 3},
                    "audios": [],
                },
                "source de l'heure de création invalide",
            ),
            "lance_a-non-texte": (
                {
                    **valide,
                    "processus_moteur": {"pid": None, "lance_a": 12},
                    "audios": [],
                },
                "heure de lancement consignée invalide",
            ),
            "sans-audios": (
                {**valide, "processus_moteur": {"pid": None}},
                "clé 'audios' absente ou invalide",
            ),
            "audio-sans-dossier": (
                {
                    **valide,
                    "processus_moteur": {"pid": None},
                    "audios": [{"statut": STATUT_NON_TRAITE}],
                },
                "plan d'audio sans dossier",
            ),
            "audio-non-objet": (
                {**valide, "processus_moteur": {"pid": None}, "audios": ["a.wav"]},
                "plan d'audio invalide",
            ),
            "audio-statut-inconnu": (
                {
                    **valide,
                    "processus_moteur": {"pid": None},
                    "audios": [{"dossier": "1-a.wav", "statut": "peut-etre"}],
                },
                "plan d'audio au statut inconnu",
            ),
        }
        for nom, (contenu, detail) in cas.items():
            with self.subTest(nom):
                # Dossier neuf par cas : chaque contrôle est bien atteint, et le
                # message doit citer le `run.json` de ce cas précis.
                self.donnees = self.donnees_neuves()
                run_json = self.ecrire_run(f"20260101-120000-{nom}", contenu)
                avant = self.arborescence()

                with self.assertRaises(EtatAnterieurNonTraitable) as capture:
                    self.recuperer()

                message = str(capture.exception)
                self.assertIn(str(run_json), message)
                self.assertIn(detail, message)
                self.assertEqual(self.arborescence(), avant)

    # -- dossier de travail ------------------------------------------------

    def test_prefixe_dossier_travail_identique_au_moteur(self) -> None:
        # Sans importer `execution_moteur` dans la récupération (numpy, moteurs).
        self.assertEqual(PREFIXE_DOSSIER_TRAVAIL, PREFIXE_DOSSIER_TRAVAIL_MOTEUR)

    def test_seuls_les_dossiers_de_travail_sont_supprimes(self) -> None:
        cache = self.donnees / "cache"
        reste = cache / "execution-abandonnee" / "audio-0.f32"
        reste.parent.mkdir(parents=True)
        reste.write_bytes(b"\0" * 16)
        (cache / "execution-vide").mkdir()
        etranger = cache / "notes.txt"
        etranger.write_text("à garder", encoding="utf-8")
        dossier_etranger = cache / "autre-dossier"
        dossier_etranger.mkdir()
        (dossier_etranger / "garde").write_text("à garder", encoding="utf-8")
        cible = self.donnees / "hors-cache"
        cible.mkdir()
        (cible / "garde").write_text("à garder", encoding="utf-8")
        lien = cache / "execution-lien"
        try:
            lien.symlink_to(cible, target_is_directory=True)
            lien_fichier = cache / "execution-lien-fichier"
            lien_fichier.symlink_to(etranger)
        except (OSError, NotImplementedError):
            lien = None

        self.recuperer()

        self.assertFalse((cache / "execution-abandonnee").exists())
        self.assertFalse((cache / "execution-vide").exists())
        self.assertEqual(etranger.read_text(encoding="utf-8"), "à garder")
        self.assertEqual(
            (dossier_etranger / "garde").read_text(encoding="utf-8"), "à garder"
        )
        self.assertEqual((cible / "garde").read_text(encoding="utf-8"), "à garder")
        if lien is not None:
            self.assertTrue(lien.is_symlink(), "un lien de dossier a été supprimé")
            self.assertTrue(
                lien_fichier.is_symlink(), "un lien de fichier a été supprimé"
            )

    def test_cache_lien_symbolique_n_est_pas_purge(self) -> None:
        cible = self.donnees / "ailleurs"
        reste = cible / "execution-abandonnee"
        reste.mkdir(parents=True)
        (reste / "audio-0.f32").write_bytes(b"\0" * 16)
        cache = self.donnees / "cache"
        try:
            cache.symlink_to(cible, target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("les liens symboliques ne sont pas disponibles ici")

        self.recuperer()

        self.assertTrue((reste / "audio-0.f32").is_file())

    def test_cache_intact_apres_refus_de_demarrage(self) -> None:
        reste = self.donnees / "cache" / "execution-en-cours" / "audio-0.f32"
        reste.parent.mkdir(parents=True)
        reste.write_bytes(b"\0" * 16)
        self.ecrire_run("20260101-120000-incoherent", {"etat": ETAT_EN_COURS})

        with self.assertRaises(EtatAnterieurNonTraitable):
            self.recuperer()

        self.assertTrue(reste.is_file(), "le cache a été purgé malgré le refus")

    def test_cache_absent_n_est_pas_cree(self) -> None:
        consignateur = self.ouvrir_consignation(("a.wav",))

        self.recuperer()

        self.assertFalse((self.donnees / "cache").exists())
        self.assertEqual(self.lire(self.run_json(consignateur))["etat"], ETAT_ABANDONNEE)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
