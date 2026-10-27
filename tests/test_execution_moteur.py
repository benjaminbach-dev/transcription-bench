"""Tests du lancement supervisé d'une exécution (tâche 6.3).

Les tests exécutent le vrai `engines/runner.py` avec l'interpréteur du serveur et
le moteur factice : aucun moteur réel, aucun poids, aucun réseau et aucune
inférence réelle. Les audios sont des WAV synthétiques générés localement ; les
mesures reçues sont simulées et ne représentent aucun PC. Aucun test n'écrit
sous le `data/` du dépôt : le dossier de données est temporaire.

Pour rendre les cas d'arrêt, d'occupation du créneau et de plantage
déterministes sans couture de rappel, deux commandes de test enveloppent le
runner avec le même interpréteur : l'une bloque dans l'adaptateur factice
jusqu'à ce que le test écrive un fichier de libération (paliers), l'autre émet
chaque événement deux fois. Le chemin nominal utilise `commande_runner` sans
enveloppe.
"""

from __future__ import annotations

import os
import sys
import html
import tempfile
import threading
import time
import unittest
from pathlib import Path
from typing import Any
from unittest import mock

import psutil

from engines.hors_ligne import commande_runner, environnement_moteur
from engines.protocole import (
    TYPE_AUDIO,
    TYPE_AUDIO_ERREUR,
    TYPE_CHARGEMENT,
    TYPE_FIN,
)
from engines.registre import creer_registre_fourni
from engines.runner import FORMAT_AUDIO, VERSION_JOB as VERSION_JOB_RUNNER
from tests.test_audios import ecrire_wav
from tests.test_executions import declaration_avec_reglages, modele_prete
from transcription_bench.audios import decoder_audio, lister_audios
from transcription_bench import execution_moteur as module_execution_moteur
from transcription_bench.execution_moteur import (
    ARRET_AUCUN,
    ARRET_DEMANDE,
    ARRET_SURVIVANT,
    ETAT_ECHOUEE,
    ETAT_INTERROMPUE,
    ETAT_TERMINEE,
    FORMAT_AUDIO_BRUT,
    VERSION_JOB,
    ExecutionImpossible,
    ExecutionMoteur,
    ProcessusMoteur,
    evaluer_issue,
)
from transcription_bench.executions import (
    CLE_MODELE_FACTICE,
    FENETRE_FIXE_SECONDES,
    LIBELLE_MODELE_FACTICE,
    ConfigurationExecutions,
    DemandeExecution,
)
from transcription_bench.moteurs import InstallationMoteurs
from transcription_bench.operations import (
    ETAT_ECHOUEE as ETAT_CRENEAU_ECHOUEE,
    ETAT_EN_COURS,
    ETAT_INTERROMPUE as ETAT_CRENEAU_INTERROMPUE,
    ETAT_LIBRE,
    TYPE_EXECUTION,
    TYPE_VERIFICATION,
    CreneauOccupe,
    CreneauOperations,
    ServiceArrete,
)
from transcription_bench.web import (
    NOM_CHAMP_JETON,
    ConfigApplication,
    ServicesApplication,
    create_app,
)

DELAI = 60.0
SECONDES_AUDIO = 0.2
#: Intervalle de sondage des marqueurs de test : aucune durée n'est supposée.
PAS_SONDAGE_TEST = 0.01

CODE_MOTEUR_PALIER = """
import os
import runpy
import sys
import time

import engines.adaptateurs.factice as factice

_original = factice.transcrire
dossier = {dossier!r}
appels = [0]
LIMITE_PALIER = 120.0


def transcrire(*arguments, **options):
    appels[0] += 1
    marque = os.path.join(dossier, "palier-%d" % appels[0])
    with open(marque, "w", encoding="utf-8") as fichier:
        fichier.write("ok")
    liberation = marque + ".liberer"
    limite = time.monotonic() + LIMITE_PALIER
    while not os.path.exists(liberation):
        if time.monotonic() > limite:
            raise SystemExit("palier jamais libéré")
        time.sleep(0.01)
    return _original(*arguments, **options)


factice.transcrire = transcrire
chemin_job, chemin_runner = sys.argv[1], sys.argv[2]
sys.argv = ["runner.py", chemin_job]
runpy.run_path(chemin_runner, run_name="__main__")
"""

CODE_EVENEMENTS_DOUBLES = """
import runpy
import sys

import engines.protocole as protocole

_emettre = protocole.emettre


def emettre(evenement, flux=None):
    _emettre(evenement, flux)
    _emettre(dict(evenement), flux)


protocole.emettre = emettre
chemin_job, chemin_runner = sys.argv[1], sys.argv[2]
sys.argv = ["runner.py", chemin_job]
runpy.run_path(chemin_runner, run_name="__main__")
"""

CODE_LIGNES_PARASITES = """
import runpy
import sys

print("bavardage de bibliothèque sans préfixe")
print("##TB-EVENT## pas un objet JSON")
print(
    '##TB-EVENT## {"type":"chargement","duree_s":0.1,'
    '"pic_memoire_octets":1,"factice":false,"mesures_simulees":false}'
)
chemin_job, chemin_runner = sys.argv[1], sys.argv[2]
sys.argv = ["runner.py", chemin_job]
runpy.run_path(chemin_runner, run_name="__main__")
"""

CODE_PROCESSUS_RECALCITRANT = """
import signal
import time

signal.signal(signal.SIGTERM, signal.SIG_IGN)
print("pret", flush=True)
time.sleep(120)
"""


def commande_enveloppee(code: str):
    """Commande de test : interpréteur du serveur, code enveloppe, job, runner."""

    def construire(interpreteur: str | Path, chemin_job: str | Path) -> list[str]:
        commande = commande_runner(interpreteur, chemin_job)
        return [commande[0], "-c", code, commande[2], commande[1]]

    return construire


def attendre_condition(condition, description: str, delai: float = DELAI) -> None:
    """Attend qu'une condition devienne vraie, sans supposer de durée."""
    echeance = time.monotonic() + delai
    while time.monotonic() < echeance:
        if condition():
            return
        time.sleep(PAS_SONDAGE_TEST)
    raise AssertionError(description)


def attendre_fichier(chemin: Path) -> None:
    """Attend l'apparition d'un marqueur écrit par le processus enfant."""
    attendre_condition(chemin.exists, f"marqueur jamais créé : {chemin.name}")


def attendre_journal(creneau: CreneauOperations, extrait: str) -> None:
    """Attend qu'une ligne du journal du créneau contienne `extrait`."""
    attendre_condition(
        lambda: any(extrait in ligne for ligne in creneau.instantane().journal),
        f"ligne de journal jamais reçue : {extrait}",
    )


class ProcessusQuiResiste:
    """Faux processus moteur : l'arrêt échoue et la fin réelle est différée.

    Utilisé à la place de `ProcessusMoteur` pour vérifier qu'une exception, avec
    un processus qui résiste à `kill`, laisse le créneau occupé jusqu'à sa fin
    réelle (et non jusqu'au retour de `arreter`).
    """

    dernier: "ProcessusQuiResiste | None" = None

    def __init__(self, **options: Any) -> None:
        self.options = options
        self.pid: int | None = None
        self.attente_demandee = threading.Event()
        self.fin_reelle = threading.Event()
        self.ferme = False
        ProcessusQuiResiste.dernier = self

    def lancer(self, *arguments: Any, **options: Any):
        raise RuntimeError("panne imprévue au lancement du processus")

    def arreter(self) -> bool:
        return False

    def attendre_fin(self) -> None:
        self.attente_demandee.set()
        self.fin_reelle.wait(DELAI)

    def fermer(self) -> None:
        self.ferme = True


class SocleExecutionTest(unittest.TestCase):
    """Service d'exécution sur un dossier de données temporaire et des WAV locaux."""

    def setUp(self) -> None:
        temporaire = tempfile.TemporaryDirectory()
        self.addCleanup(temporaire.cleanup)
        self.racine = Path(temporaire.name)
        self.dossier_data = self.racine / "data"
        self.dossier_audio = self.dossier_data / "audio"
        self.dossier_audio.mkdir(parents=True)
        # Dossier de travail par défaut du service, sous le `data/` temporaire.
        self.cache = self.dossier_data / "cache"
        self.registre = creer_registre_fourni()
        self.creneau = CreneauOperations()
        self.moteurs = InstallationMoteurs(
            self.dossier_data, self.registre, self.creneau
        )
        self.service = self.creer_service()
        self.addCleanup(self.arreter_execution)

    def creer_service(self, **options: Any) -> ExecutionMoteur:
        options.setdefault("interpreteur_serveur", sys.executable)
        return ExecutionMoteur(
            self.dossier_data, self.registre, self.moteurs, **options
        )

    def arreter_execution(self) -> None:
        """Aucun processus ne doit survivre à un test, même en cas d'échec."""
        self.service.arreter_execution()
        fil = self.creneau.thread_travailleur
        if fil is not None:
            fil.join(DELAI)
        self.creneau.arreter(1.0)

    def dossiers_de_travail(self) -> list[str]:
        """Noms des dossiers de travail encore présents sous `data/cache`."""
        if not self.cache.exists():
            return []
        return [chemin.name for chemin in self.cache.iterdir()]

    def assertCacheNettoye(self) -> None:
        """Aucun dossier de travail ni signal décodé ne subsiste sous `data/cache`."""
        self.assertEqual(self.dossiers_de_travail(), [])

    def assertTerminee(self, resultat) -> None:
        """Issue terminée, avec la sortie d'erreur du moteur en cas d'échec.

        Le message d'échec porte les dernières lignes du moteur : un incident
        d'environnement n'est pas confondu avec une régression du service.
        """
        self.assertEqual(
            (resultat.etat, resultat.code_sortie, resultat.erreur),
            (ETAT_TERMINEE, 0, None),
            msg="\n".join(resultat.journal_moteur[-5:]),
        )

    def ecrire_audio(self, nom: str, duree: float = SECONDES_AUDIO) -> None:
        ecrire_wav(self.dossier_audio / nom, duree=duree)

    def ecrire_fichier_illisible(self, nom: str = "casse.wav") -> None:
        (self.dossier_audio / nom).write_bytes(b"pas un conteneur audio" * 20)

    def paliers(self) -> Path:
        """Dossier des marqueurs écrits par l'enveloppe `CODE_MOTEUR_PALIER`."""
        dossier = self.racine / "paliers"
        dossier.mkdir(exist_ok=True)
        return dossier

    def liberer_paliers(self, dossier: Path, *numeros: int) -> None:
        for numero in numeros:
            (dossier / f"palier-{numero}.liberer").write_text("ok", encoding="utf-8")

    def service_a_paliers(self) -> tuple[ExecutionMoteur, Path]:
        """Service dont le moteur enfant bloque à chaque palier d'audio."""
        dossier = self.paliers()
        service = self.creer_service(
            construire_commande=commande_enveloppee(
                CODE_MOTEUR_PALIER.format(dossier=str(dossier))
            )
        )
        return service, dossier

    def demande(
        self,
        audios: tuple[str, ...],
        *,
        threads: int = 2,
        moteur: str = "factice",
        cle: str = CLE_MODELE_FACTICE,
        identifiant: str = LIBELLE_MODELE_FACTICE,
        famille: str = "factice",
        synthetique: bool = True,
    ) -> DemandeExecution:
        return DemandeExecution(
            moteur=moteur,
            cle=cle,
            identifiant=identifiant,
            id_resolu=identifiant,
            commit="aucun",
            famille=famille,
            fichier_gguf=None,
            audios=audios,
            threads=threads,
            reglages=(),
            fenetre_fixe_secondes=FENETRE_FIXE_SECONDES,
            synthetique=synthetique,
        )

    def executer(
        self, demande: DemandeExecution, service: ExecutionMoteur | None = None
    ):
        """Réserve, lance dans le créneau et attend la fin réelle."""
        service = service or self.service
        service.reserver()
        self.creneau.demarrer(
            TYPE_EXECUTION,
            lambda travailleur: service.lancer(demande, travailleur),
            cible=demande.identifiant,
        )
        fil = self.creneau.thread_travailleur
        fil.join(DELAI)
        self.assertFalse(fil.is_alive(), "l'exécution n'est pas close dans le délai")
        return service.derniere_execution()


class ExecutionCompleteTest(SocleExecutionTest):
    def test_execution_complete_par_lot(self) -> None:
        self.ecrire_audio("a.wav", 0.25)
        self.ecrire_audio("b.wav", 0.5)

        resultat = self.executer(self.demande(("b.wav", "a.wav")))

        self.assertIsNotNone(resultat)
        self.assertTerminee(resultat)
        self.assertTrue(resultat.factice)
        self.assertTrue(resultat.synthetique)
        self.assertEqual(resultat.moteur, "factice")
        self.assertEqual(resultat.threads_demandes, 2)
        self.assertEqual([audio.nom for audio in resultat.audios], ["b.wav", "a.wav"])
        self.assertEqual(resultat.audios_non_traites, ())
        self.assertEqual(resultat.audios_en_erreur, ())
        self.assertEqual(resultat.lignes_parasites, 0)
        self.assertEqual(resultat.journal_moteur, ())
        self.assertEqual(resultat.evenements[0]["type"], TYPE_CHARGEMENT)
        self.assertEqual(resultat.evenements[-1]["type"], TYPE_FIN)
        types = [evenement["type"] for evenement in resultat.evenements]
        self.assertEqual(types.count(TYPE_AUDIO), 2)
        for audio in resultat.audios:
            self.assertTrue(audio.factice)
            self.assertTrue(audio.synthetique)
            self.assertTrue(audio.evenement["factice"])
            self.assertTrue(audio.evenement["mesures_simulees"])
            self.assertIn("[FACTICE]", audio.evenement["texte"])
            self.assertIsNotNone(audio.prepare)
            self.assertEqual(len(audio.prepare.empreinte_sha256), 64)
            self.assertEqual(audio.prepare.format, "wav")
        # Le signal brut écrit est bien le signal décodé : la durée vue par le
        # moteur est la durée décodée, pas la durée indicative de l'en-tête.
        self.assertAlmostEqual(
            resultat.audios[0].evenement["duree_audio_s"], 0.5, places=2
        )
        self.assertAlmostEqual(resultat.audios[0].prepare.duree_decodee, 0.5, places=2)
        # Cache décodé supprimé et créneau libéré.
        self.assertCacheNettoye()
        self.assertNotEqual(self.creneau.instantane().etat, ETAT_EN_COURS)
        journal = "\n".join(self.creneau.instantane().journal)
        self.assertIn("Processus moteur lancé", journal)
        self.assertIn("Exécution terminée", journal)

    def test_constantes_du_job_alignees_sur_le_runner(self) -> None:
        self.assertEqual(VERSION_JOB, VERSION_JOB_RUNNER)
        self.assertEqual(FORMAT_AUDIO_BRUT, FORMAT_AUDIO)

    def test_ligne_stdout_parasite_journalisee_sans_echec(self) -> None:
        self.ecrire_audio("a.wav")
        service = self.creer_service(
            construire_commande=commande_enveloppee(CODE_LIGNES_PARASITES)
        )
        resultat = self.executer(self.demande(("a.wav",)), service=service)

        self.assertTerminee(resultat)
        self.assertGreaterEqual(resultat.lignes_parasites, 3)
        self.assertEqual(
            [evenement["type"] for evenement in resultat.evenements].count(
                TYPE_CHARGEMENT
            ),
            1,
        )
        self.assertIsNotNone(resultat.audios[0].evenement)
        journal = "\n".join(self.creneau.instantane().journal)
        self.assertIn("Sortie du moteur ignorée", journal)
        self.assertIn("provenance incohérente", journal)

    def test_exception_de_decodage_ne_bloque_pas_les_suivants(self) -> None:
        self.ecrire_audio("a.wav")
        self.ecrire_fichier_illisible("casse.wav")
        self.ecrire_audio("b.wav")

        resultat = self.executer(
            self.demande(("a.wav", "casse.wav", "b.wav"))
        )

        self.assertTerminee(resultat)
        self.assertIsNone(resultat.audios[0].erreur)
        self.assertIsNotNone(resultat.audios[0].evenement)
        self.assertIsNone(resultat.audios[1].prepare)
        self.assertIsNotNone(resultat.audios[1].erreur)
        self.assertIn("décodage impossible", resultat.audios[1].erreur)
        self.assertIsNotNone(resultat.audios[2].evenement)
        # L'index du job exclut l'audio en erreur : la position dans la demande
        # est rétablie par le service.
        self.assertEqual(resultat.audios[2].evenement["index"], 1)
        self.assertEqual(resultat.audios[2].evenement["nom"], "b.wav")
        self.assertEqual(resultat.audios_en_erreur, ("casse.wav",))
        self.assertEqual(resultat.audios_non_traites, ())
        journal = "\n".join(self.creneau.instantane().journal)
        self.assertIn("décodage impossible", journal)

    def test_exception_inattendue_de_decodage_devient_une_erreur_d_audio(self) -> None:
        self.ecrire_audio("a.wav")
        self.ecrire_audio("b.wav")

        def decoder(nom: str, donnees):
            if nom == "b.wav":
                raise RuntimeError("incident imprévu du décodeur")
            return decoder_audio(nom, donnees)

        service = self.creer_service(decoder=decoder)
        resultat = self.executer(self.demande(("a.wav", "b.wav")), service=service)

        self.assertTerminee(resultat)
        self.assertIsNotNone(resultat.audios[0].evenement)
        self.assertIn("incident imprévu du décodeur", resultat.audios[1].erreur)

    def test_aucun_audio_decodable_echoue_sans_processus(self) -> None:
        self.ecrire_fichier_illisible("casse.wav")
        self.ecrire_fichier_illisible("casse2.wav")

        resultat = self.executer(self.demande(("casse.wav", "casse2.wav")))

        self.assertEqual(resultat.etat, ETAT_ECHOUEE)
        self.assertIsNone(resultat.code_sortie)
        self.assertIsNone(resultat.pid)
        self.assertIn("aucun audio n'a pu être décodé", resultat.erreur)
        self.assertEqual(len(resultat.audios_en_erreur), 2)
        self.assertEqual(self.creneau.instantane().etat, ETAT_CRENEAU_ECHOUEE)
        self.assertCacheNettoye()

    def test_dossier_de_travail_cree_au_lancement_seulement(self) -> None:
        self.ecrire_audio("a.wav")
        # Construit sans E/S : `data/cache` n'existe pas avant le lancement.
        self.assertFalse(self.cache.exists())

        resultat = self.executer(self.demande(("a.wav",)))

        self.assertTerminee(resultat)
        self.assertTrue(self.cache.is_dir())
        self.assertCacheNettoye()

    def test_racine_de_travail_injectable(self) -> None:
        """Couture de test : les signaux vont dans la racine fournie, pas sous `data/`."""
        racine = self.racine / "travail"
        service = self.creer_service(racine_temporaire=racine)
        self.ecrire_audio("a.wav")

        resultat = self.executer(self.demande(("a.wav",)), service=service)

        self.assertTerminee(resultat)
        self.assertFalse(self.cache.exists())
        self.assertEqual(list(racine.iterdir()), [])

    def test_evenements_en_double_traites_comme_lignes_parasites(self) -> None:
        self.ecrire_audio("a.wav")
        self.ecrire_audio("b.wav")
        service = self.creer_service(
            construire_commande=commande_enveloppee(CODE_EVENEMENTS_DOUBLES)
        )

        resultat = self.executer(self.demande(("a.wav", "b.wav")), service=service)

        self.assertTerminee(resultat)
        types = [evenement["type"] for evenement in resultat.evenements]
        # Un `chargement`, un événement par audio, un `fin` : le premier gagne.
        self.assertEqual(types.count(TYPE_CHARGEMENT), 1)
        self.assertEqual(types.count(TYPE_AUDIO), 2)
        self.assertEqual(types.count(TYPE_FIN), 1)
        self.assertEqual(resultat.lignes_parasites, 4)
        for audio in resultat.audios:
            self.assertIsNotNone(audio.evenement)
            self.assertIsNone(audio.erreur)
        journal = "\n".join(self.creneau.instantane().journal)
        self.assertIn("événement en double", journal)


class ArretExecutionTest(SocleExecutionTest):
    def test_arret_apres_un_audio_conserve_les_resultats(self) -> None:
        for nom in ("a.wav", "b.wav", "c.wav"):
            self.ecrire_audio(nom)
        service, paliers = self.service_a_paliers()
        self.service = service
        self.liberer_paliers(paliers, 1)

        service.reserver()
        self.creneau.demarrer(
            TYPE_EXECUTION,
            lambda travailleur: service.lancer(
                self.demande(("a.wav", "b.wav", "c.wav")), travailleur
            ),
            cible="factice",
        )
        # Le moteur est bloqué avant l'audio 2 : l'audio 1 est déjà transcrit et
        # son événement déjà interprété (journal), donc plus sujets à la course.
        attendre_fichier(paliers / "palier-2")
        attendre_journal(self.creneau, "Audio « a.wav » transcrit")
        self.assertEqual(self.creneau.instantane().etat, ETAT_EN_COURS)
        self.assertIsNone(service.derniere_execution())
        pid = service.pid_actif()
        self.assertIsNotNone(pid)
        if os.name == "posix":
            # Groupe de processus propre : le moteur ne partage pas celui du
            # serveur, pour que Ctrl+C soit traité par la supervision.
            self.assertEqual(os.getpgid(pid), pid)

        self.assertEqual(service.arreter_execution(), ARRET_DEMANDE)
        fil = self.creneau.thread_travailleur
        fil.join(DELAI)
        self.assertFalse(fil.is_alive())
        resultat = service.derniere_execution()

        self.assertEqual(resultat.etat, ETAT_INTERROMPUE)
        self.assertTrue(resultat.arret_demande)
        # Fin réelle constatée par le service (code de sortie renseigné), sans
        # test sur un PID qui peut être recyclé.
        self.assertIsNotNone(resultat.code_sortie)
        self.assertIsNone(service.pid_actif())
        self.assertEqual(
            [audio.nom for audio in resultat.audios if audio.evenement is not None],
            ["a.wav"],
        )
        self.assertEqual(resultat.audios_non_traites, ("b.wav", "c.wav"))
        self.assertEqual(resultat.audios_en_erreur, ())
        self.assertEqual(self.creneau.instantane().etat, ETAT_CRENEAU_INTERROMPUE)
        self.assertCacheNettoye()
        journal = "\n".join(self.creneau.instantane().journal)
        self.assertIn("Arrêt de l'exécution demandé", journal)
        self.assertIn("Exécution interrompue", journal)

    def test_creneau_occupe_jusqu_a_la_fin_reelle_du_processus(self) -> None:
        self.ecrire_audio("a.wav")
        self.ecrire_audio("b.wav")
        service, paliers = self.service_a_paliers()
        self.service = service
        self.liberer_paliers(paliers, 1)

        service.reserver()
        self.creneau.demarrer(
            TYPE_EXECUTION,
            lambda travailleur: service.lancer(
                self.demande(("a.wav", "b.wav")), travailleur
            ),
            cible="factice",
        )
        try:
            # Marqueur du moteur : il est entré dans l'audio 2 et n'en sortira
            # qu'à la libération du palier.
            attendre_fichier(paliers / "palier-2")
            attendre_journal(self.creneau, "Audio « a.wav » transcrit")
            self.assertEqual(self.creneau.instantane().etat, ETAT_EN_COURS)
            self.assertIsNone(service.derniere_execution())
            with self.assertRaises(CreneauOccupe):
                self.creneau.demarrer(TYPE_VERIFICATION, lambda travailleur: None)
        finally:
            self.liberer_paliers(paliers, 2)
        fil = self.creneau.thread_travailleur
        fil.join(DELAI)
        self.assertFalse(fil.is_alive())
        self.assertNotEqual(self.creneau.instantane().etat, ETAT_EN_COURS)
        self.assertEqual(service.derniere_execution().etat, ETAT_TERMINEE)
        self.assertCacheNettoye()

    def test_plantage_du_moteur_echoue_proprement(self) -> None:
        for nom in ("a.wav", "b.wav", "c.wav"):
            self.ecrire_audio(nom)
        service, paliers = self.service_a_paliers()
        self.service = service
        self.liberer_paliers(paliers, 1)

        service.reserver()
        self.creneau.demarrer(
            TYPE_EXECUTION,
            lambda travailleur: service.lancer(
                self.demande(("a.wav", "b.wav", "c.wav")), travailleur
            ),
            cible="factice",
        )
        attendre_fichier(paliers / "palier-2")
        pid = service.pid_actif()
        self.assertIsNotNone(pid)
        # Plantage simulé pendant l'audio 2 : le moteur meurt sans se terminer.
        psutil.Process(pid).kill()
        fil = self.creneau.thread_travailleur
        fil.join(DELAI)
        self.assertFalse(fil.is_alive())
        resultat = service.derniere_execution()

        self.assertEqual(resultat.etat, ETAT_ECHOUEE)
        self.assertIsNotNone(resultat.code_sortie)
        self.assertNotEqual(resultat.code_sortie, 0)
        self.assertIsNotNone(resultat.erreur)
        self.assertIn("code", resultat.erreur)
        self.assertFalse(resultat.arret_demande)
        self.assertEqual(
            [audio.nom for audio in resultat.audios if audio.evenement is not None],
            ["a.wav"],
        )
        self.assertEqual(resultat.audios_non_traites, ("b.wav", "c.wav"))
        self.assertEqual(self.creneau.instantane().etat, ETAT_CRENEAU_ECHOUEE)
        self.assertCacheNettoye()
        journal = "\n".join(self.creneau.instantane().journal)
        self.assertIn("Exécution en échec", journal)

    def test_arret_pendant_la_preparation_ne_lance_aucun_processus(self) -> None:
        self.ecrire_audio("a.wav")
        self.ecrire_audio("b.wav")
        appels: list[str] = []

        def decoder(nom: str, donnees):
            appels.append(nom)
            self.service.arreter_execution()
            return decoder_audio(nom, donnees)

        service = self.creer_service(decoder=decoder)
        self.service = service
        resultat = self.executer(self.demande(("a.wav", "b.wav")), service=service)

        self.assertEqual(resultat.etat, ETAT_INTERROMPUE)
        self.assertTrue(resultat.arret_demande)
        self.assertIsNone(resultat.pid)
        self.assertIsNone(resultat.code_sortie)
        self.assertEqual(appels, ["a.wav"])
        # Aucun événement reçu : les deux audios restent non traités.
        self.assertEqual(resultat.audios_non_traites, ("a.wav", "b.wav"))
        self.assertEqual(self.creneau.instantane().etat, ETAT_CRENEAU_INTERROMPUE)
        journal = "\n".join(self.creneau.instantane().journal)
        self.assertIn("Arrêt demandé avant le lancement du moteur", journal)
        self.assertCacheNettoye()

    def test_annuler_reservation_conserve_le_dernier_resultat(self) -> None:
        self.ecrire_audio("a.wav")
        precedent = self.executer(self.demande(("a.wav",)))
        self.assertIsNotNone(precedent)

        self.service.reserver()
        self.service.annuler_reservation()

        self.assertIs(self.service.derniere_execution(), precedent)
        self.assertFalse(self.service.en_cours())

    def test_arret_entre_reservation_et_demarrage_est_conserve(self) -> None:
        self.ecrire_audio("a.wav")
        self.service.reserver()

        # Arrêt demandé avant tout démarrage effectif : il n'est pas perdu.
        self.assertEqual(self.service.arreter_execution(), ARRET_DEMANDE)
        self.creneau.demarrer(
            TYPE_EXECUTION,
            lambda travailleur: self.service.lancer(
                self.demande(("a.wav",)), travailleur
            ),
            cible="factice",
        )
        fil = self.creneau.thread_travailleur
        fil.join(DELAI)
        self.assertFalse(fil.is_alive())

        resultat = self.service.derniere_execution()
        self.assertEqual(resultat.etat, ETAT_INTERROMPUE)
        self.assertTrue(resultat.arret_demande)
        self.assertIsNone(resultat.pid)
        self.assertEqual(resultat.audios_non_traites, ("a.wav",))
        self.assertEqual(self.creneau.instantane().etat, ETAT_CRENEAU_INTERROMPUE)
        self.assertCacheNettoye()

    def test_echec_de_creation_du_dossier_de_travail(self) -> None:
        self.ecrire_audio("a.wav")
        obstacle = self.racine / "pas-un-dossier"
        obstacle.write_text("fichier", encoding="utf-8")
        service = self.creer_service(racine_temporaire=obstacle)
        self.service = service

        resultat = self.executer(self.demande(("a.wav",)), service=service)

        self.assertEqual(resultat.etat, ETAT_ECHOUEE)
        self.assertIn("dossier de travail impossible", resultat.erreur)
        self.assertIsNone(resultat.pid)
        self.assertIsNone(resultat.code_sortie)
        # La liste des audios est conservée, entièrement non traitée.
        self.assertEqual([audio.nom for audio in resultat.audios], ["a.wav"])
        self.assertEqual(resultat.audios_non_traites, ("a.wav",))
        # Aucun état actif ni arrêt « demandé » fantôme ne subsiste.
        self.assertFalse(service.en_cours())
        self.assertEqual(service.arreter_execution(), ARRET_AUCUN)
        self.assertEqual(self.creneau.instantane().etat, ETAT_CRENEAU_ECHOUEE)
        self.assertCacheNettoye()

    def test_exception_avec_processus_recalcitrant_garde_le_creneau(self) -> None:
        self.ecrire_audio("a.wav")
        with mock.patch.object(
            module_execution_moteur, "ProcessusMoteur", ProcessusQuiResiste
        ):
            self.service.reserver()
            processus = ProcessusQuiResiste.dernier
            self.assertIsNotNone(processus)
            self.creneau.demarrer(
                TYPE_EXECUTION,
                lambda travailleur: self.service.lancer(
                    self.demande(("a.wav",)), travailleur
                ),
                cible="factice",
            )
            self.assertTrue(
                processus.attente_demandee.wait(DELAI),
                "l'attente de la fin réelle n'a pas été demandée",
            )
            # L'arrêt a échoué : l'état, le dossier de travail et le créneau
            # restent occupés jusqu'à la fin réelle du processus.
            self.assertTrue(self.service.en_cours())
            self.assertEqual(self.creneau.instantane().etat, ETAT_EN_COURS)
            self.assertTrue(self.dossiers_de_travail())
            self.assertIsNone(self.service.derniere_execution())
            with self.assertRaises(CreneauOccupe):
                self.creneau.demarrer(TYPE_VERIFICATION, lambda travailleur: None)
            processus.fin_reelle.set()
            fil = self.creneau.thread_travailleur
            fil.join(DELAI)
            self.assertFalse(fil.is_alive())
        self.assertFalse(self.service.en_cours())
        self.assertTrue(processus.ferme)
        self.assertEqual(self.creneau.instantane().etat, ETAT_CRENEAU_ECHOUEE)
        self.assertCacheNettoye()
        journal = "\n".join(self.creneau.instantane().journal)
        self.assertIn("encore actif après kill", journal)

    def test_aucune_execution_ne_demarre_apres_passage_a_l_arret(self) -> None:
        self.ecrire_audio("a.wav")
        self.creneau.arreter(1.0)

        with self.assertRaises(ServiceArrete):
            self.creneau.demarrer(
                TYPE_EXECUTION,
                lambda travailleur: self.service.lancer(
                    self.demande(("a.wav",)), travailleur
                ),
            )
        self.assertIsNone(self.service.derniere_execution())
        self.assertCacheNettoye()


class ProcessusMoteurTest(unittest.TestCase):
    """Sous-processus : groupe propre, `terminate`, attente bornée puis `kill`."""

    def setUp(self) -> None:
        temporaire = tempfile.TemporaryDirectory()
        self.addCleanup(temporaire.cleanup)
        self.dossier = Path(temporaire.name)

    @unittest.skipUnless(os.name == "posix", "signaux et groupes POSIX")
    def test_arret_borne_termine_un_processus_recalcitrant(self) -> None:
        processus = ProcessusMoteur(delai_arret=0.5)
        enfant = processus.lancer(
            [sys.executable, "-c", CODE_PROCESSUS_RECALCITRANT],
            environ=environnement_moteur(),
            dossier=self.dossier,
        )
        try:
            self.assertEqual(os.getpgid(enfant.pid), enfant.pid)
            self.assertEqual(enfant.stdout.readline().strip(), "pret")

            self.assertTrue(processus.arreter())
            self.assertIsNotNone(enfant.poll())
            self.assertNotEqual(enfant.returncode, 0)
        finally:
            processus.arreter()
            processus.fermer()

    def test_arret_avant_lancement_empeche_le_demarrage(self) -> None:
        processus = ProcessusMoteur()
        self.assertTrue(processus.arreter())

        with self.assertRaises(ExecutionImpossible):
            processus.lancer(
                [sys.executable, "-c", "print('jamais lancé')"],
                environ=environnement_moteur(),
                dossier=self.dossier,
            )
        self.assertIsNone(processus.pid)


class EvaluerIssueTest(unittest.TestCase):
    """Règles d'issue : aucun succès n'est déduit d'une sortie incomplète."""

    def evenement(self, type_evenement: str, index: int | None = None) -> dict[str, Any]:
        contenu: dict[str, Any] = {
            "type": type_evenement,
            "factice": True,
            "mesures_simulees": True,
        }
        if index is not None:
            contenu["index"] = index
        return contenu

    def test_execution_nominale_est_terminee(self) -> None:
        etat, motif = evaluer_issue(
            code_sortie=0,
            arret_demande=False,
            evenements=[self.evenement(TYPE_AUDIO, 0), self.evenement(TYPE_FIN)],
            indices_job=(0,),
            nb_audios=1,
        )

        self.assertEqual(etat, ETAT_TERMINEE)
        self.assertIsNone(motif)

    def test_erreur_d_audio_signalee_par_le_moteur_reste_un_succes(self) -> None:
        etat, motif = evaluer_issue(
            code_sortie=0,
            arret_demande=False,
            evenements=[
                self.evenement(TYPE_AUDIO_ERREUR, 0),
                self.evenement(TYPE_AUDIO, 1),
                self.evenement(TYPE_FIN),
            ],
            indices_job=(0, 1),
            nb_audios=2,
        )

        self.assertEqual(etat, ETAT_TERMINEE)
        self.assertIsNone(motif)

    def test_fin_absente_est_un_echec(self) -> None:
        etat, motif = evaluer_issue(
            code_sortie=0,
            arret_demande=False,
            evenements=[self.evenement(TYPE_AUDIO, 0)],
            indices_job=(0,),
            nb_audios=1,
        )

        self.assertEqual(etat, ETAT_ECHOUEE)
        self.assertIn("fin", motif)

    def test_evenement_d_audio_manquant_est_un_echec(self) -> None:
        etat, motif = evaluer_issue(
            code_sortie=0,
            arret_demande=False,
            evenements=[self.evenement(TYPE_AUDIO, 0), self.evenement(TYPE_FIN)],
            indices_job=(0, 1),
            nb_audios=2,
        )

        self.assertEqual(etat, ETAT_ECHOUEE)
        self.assertIn("n° 2", motif)

    def test_code_de_sortie_non_nul_est_un_echec(self) -> None:
        etat, motif = evaluer_issue(
            code_sortie=3,
            arret_demande=False,
            evenements=[self.evenement(TYPE_FIN)],
            indices_job=(0,),
            nb_audios=1,
        )

        self.assertEqual(etat, ETAT_ECHOUEE)
        self.assertIn("code 3", motif)

    def test_arret_demande_prime_sur_le_code_de_sortie(self) -> None:
        etat, motif = evaluer_issue(
            code_sortie=-15,
            arret_demande=True,
            evenements=[],
            indices_job=(0,),
            nb_audios=1,
        )

        self.assertEqual(etat, ETAT_INTERROMPUE)
        self.assertIsNone(motif)


class RoutesExecutionTest(SocleExecutionTest):
    """Routes de lancement et d'arrêt : jeton, 303 vers /operation, refus 4xx."""

    def setUp(self) -> None:
        super().setUp()
        self.ecrire_audio("a.wav")
        self.audio_noms = tuple(audio.nom for audio in lister_audios(self.dossier_data))
        self.demandes = ConfigurationExecutions(
            self.dossier_data,
            self.registre,
            lambda: (),
            lister=lister_audios,
            compter_threads=lambda: 2,
        )
        self.app = create_app(
            ConfigApplication(port=8765, dossier_data=self.dossier_data),
            ServicesApplication(
                creneau=self.creneau,
                moteurs=self.moteurs,
                executions=self.demandes,
                execution=self.service,
            ),
        )
        self.client = self.app.test_client()

    def formulaire(self, **options: Any) -> dict[str, Any]:
        donnees = {
            "modele": f"factice/{CLE_MODELE_FACTICE}",
            "audios": list(self.audio_noms),
            "threads": "2",
        }
        donnees.update(options)
        return donnees

    def base_url(self) -> str:
        return "http://127.0.0.1:8765"

    def jeton(self) -> str:
        return self.app.extensions[NOM_CHAMP_JETON]

    def poster(self, chemin: str, **options: Any):
        donnees = self.formulaire() if chemin.endswith("/lancer") else {}
        donnees.update(options)
        donnees["jeton_csrf"] = self.jeton()
        return self.client.post(chemin, data=donnees, base_url=self.base_url())

    def recreer_client(self) -> None:
        """Recrée l'application avec le service courant, sans changer de créneau."""
        self.app = create_app(
            ConfigApplication(port=8765, dossier_data=self.dossier_data),
            ServicesApplication(
                creneau=self.creneau,
                moteurs=self.moteurs,
                executions=self.demandes,
                execution=self.service,
            ),
        )
        self.client = self.app.test_client()

    def test_lancement_par_post_redirige_vers_operation(self) -> None:
        page = self.client.get("/executions", base_url=self.base_url())
        corps = page.get_data(as_text=True)
        self.assertEqual(page.status_code, 200)
        self.assertIn('formaction="/executions/lancer"', corps)
        self.assertIn("Lancer l'exécution", corps)
        self.assertIn("dossier de travail de l'exécution", corps)

        reponse = self.poster("/executions/lancer")

        self.assertEqual(reponse.status_code, 303)
        self.assertTrue(reponse.headers["Location"].endswith("/operation"))
        self.assertNotIn("Set-Cookie", reponse.headers)
        fil = self.creneau.thread_travailleur
        self.assertIsNotNone(fil)
        fil.join(DELAI)
        self.assertFalse(fil.is_alive())
        resultat = self.service.derniere_execution()
        self.assertTerminee(resultat)
        self.assertEqual(resultat.audios[0].nom, "a.wav")
        page = self.client.get("/operation", base_url=self.base_url())
        self.assertEqual(page.status_code, 200)
        self.assertIn("Exécution terminée", page.get_data(as_text=True))
        self.assertCacheNettoye()

    def test_seconde_operation_refusee_pendant_l_execution(self) -> None:
        self.service, paliers = self.service_a_paliers()
        self.recreer_client()

        self.assertEqual(self.poster("/executions/lancer").status_code, 303)
        try:
            attendre_fichier(paliers / "palier-1")
            self.assertEqual(self.poster("/executions/lancer").status_code, 409)
            self.assertEqual(self.poster("/dossiers/verifier").status_code, 409)
        finally:
            self.liberer_paliers(paliers, 1)
        self.creneau.thread_travailleur.join(DELAI)
        self.assertEqual(self.service.derniere_execution().etat, ETAT_TERMINEE)
        self.assertCacheNettoye()

    def test_lancement_refuse_apres_passage_a_l_arret(self) -> None:
        self.creneau.arreter(1.0)

        reponse = self.poster("/executions/lancer")

        self.assertEqual(reponse.status_code, 503)
        self.assertIsNone(self.service.derniere_execution())
        # La réservation refusée n'a laissé aucun état actif.
        self.assertFalse(self.service.en_cours())

    def test_lancement_revalide_la_demande(self) -> None:
        reponse = self.poster(
            "/executions/lancer", modele=f"factice/{'f' * 64}"
        )

        self.assertEqual(reponse.status_code, 400)
        self.assertIsNone(self.creneau.thread_travailleur)
        self.assertIsNone(self.service.derniere_execution())
        self.assertFalse(self.service.en_cours())

    def test_lancement_refuse_moteur_non_pret(self) -> None:
        registre = creer_registre_fourni()
        registre.enregistrer(declaration_avec_reglages())
        moteurs = InstallationMoteurs(self.dossier_data, registre, self.creneau)
        demandes = ConfigurationExecutions(
            self.dossier_data,
            registre,
            lambda: (modele_prete(),),
            lister=lister_audios,
            compter_threads=lambda: 2,
        )
        service = ExecutionMoteur(
            self.dossier_data,
            registre,
            moteurs,
            interpreteur_serveur=sys.executable,
        )
        self.service = service
        self.moteurs = moteurs
        self.demandes = demandes
        self.recreer_client()

        reponse = self.client.post(
            "/executions/lancer",
            data={
                "modele": f"moteur-de-test/{'a' * 64}",
                "audios": list(self.audio_noms),
                "threads": "2",
                "jeton_csrf": self.jeton(),
            },
            base_url=self.base_url(),
        )

        self.assertEqual(reponse.status_code, 403)
        corps = html.unescape(reponse.get_data(as_text=True))
        # Message propre au moteur non prêt, pas la phrase du jeton ou de l'adresse.
        self.assertIn("moteur demandé n'est pas prêt", corps)
        self.assertNotIn("jeton", corps.lower())
        self.assertIsNone(self.creneau.thread_travailleur)
        self.assertIsNone(service.derniere_execution())
        self.assertFalse(service.en_cours())

    def test_arret_par_post_protege_termine_l_execution(self) -> None:
        self.service, paliers = self.service_a_paliers()
        self.recreer_client()

        self.assertEqual(self.poster("/executions/lancer").status_code, 303)
        try:
            attendre_fichier(paliers / "palier-1")
            page = self.client.get("/operation", base_url=self.base_url())
            corps_operation = page.get_data(as_text=True)
            self.assertIn('action="/executions/arreter"', corps_operation)
            self.assertIn("Arrêter l'exécution", corps_operation)
            sans_jeton = self.client.post(
                "/executions/arreter",
                data={"jeton_csrf": "jeton-invalide"},
                base_url=self.base_url(),
            )
            self.assertEqual(sans_jeton.status_code, 403)
            reponse = self.poster("/executions/arreter")
            self.assertEqual(reponse.status_code, 303)
            self.assertIn("action=arret-demande", reponse.headers["Location"])
        finally:
            self.liberer_paliers(paliers, 1)
        self.creneau.thread_travailleur.join(DELAI)
        resultat = self.service.derniere_execution()
        self.assertEqual(resultat.etat, ETAT_INTERROMPUE)
        self.assertEqual(self.creneau.instantane().etat, ETAT_CRENEAU_INTERROMPUE)
        page = self.client.get("/operation?action=arret-demande", base_url=self.base_url())
        corps = html.unescape(page.get_data(as_text=True))
        self.assertIn("Arrêt de l'exécution demandé", corps)
        self.assertNotIn("<script", corps)
        self.assertNotIn("<style", corps)
        self.assertCacheNettoye()

    def test_arret_non_abouti_signale_par_la_route(self) -> None:
        """Un processus qui survit à `kill` ne doit pas être annoncé comme arrêté."""
        with mock.patch.object(
            self.service, "arreter_execution", return_value=ARRET_SURVIVANT
        ):
            reponse = self.poster("/executions/arreter")

        self.assertEqual(reponse.status_code, 303)
        self.assertIn("action=arret-incomplet", reponse.headers["Location"])
        page = self.client.get("/operation?action=arret-incomplet", base_url=self.base_url())
        corps = html.unescape(page.get_data(as_text=True))
        self.assertIn("n'a pas pu être terminé", corps)

    def test_aucune_operation_a_arreter(self) -> None:
        reponse = self.poster("/executions/arreter")

        self.assertEqual(reponse.status_code, 303)
        self.assertEqual(self.creneau.instantane().etat, ETAT_LIBRE)
        page = self.client.get("/operation", base_url=self.base_url())
        corps = html.unescape(page.get_data(as_text=True))
        self.assertNotIn("Arrêt de l'exécution demandé", corps)


if __name__ == "__main__":
    unittest.main()
