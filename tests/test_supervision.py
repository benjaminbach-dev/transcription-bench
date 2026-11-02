"""Tests de la supervision d'arrêt de la CLI (tâche 6.6).

Aucun moteur réel, aucun poids, aucun réseau : le moteur factice et ses
enveloppes de test suffisent. Les tests couvrent, dans l'ordre du design D5 :

- le gestionnaire de signaux (premier signal → `SIG_IGN` puis exception,
  signaux suivants ignorés) ;
- l'ordre du nettoyage idempotent et la libération du verrou d'instance en
  dernier, jamais avant la fin réelle du thread d'opération ;
- un vrai sous-processus moteur (enveloppe du runner factice qui lance en plus
  un descendant) arrêté sans survivant, avec un `run.json` clos en
  `interrupted` ;
- un téléchargement factice bloqué : aucun marqueur prêt, verrou non libéré
  prématurément ;
- une installation interrompue : jamais prête ;
- un vrai processus serveur (Waitress, port éphémère, dossier de données
  temporaire) auquel on envoie `SIGINT` puis `SIGTERM` sous Linux, en vérifiant
  le code de sortie, l'absence de survivant et la libération du verrou.

Les tests du serveur de développement ne valent **pas** validation Linux ou
Windows : la sonde 1.7 sur PC (Ctrl+C via `uv run`, double Ctrl+C, SIGTERM,
port occupé) et le rejeu Windows restent dus. Les scénarios en processus réel
lancent l'interpréteur du serveur avec le même `cli.main` que `uv run
transcription-bench`, sur un port éphémère et un dossier de données temporaire
(`paths.DOSSIER_DATA`) : aucun fichier n'est écrit sous le `data/` du dépôt.
`uv run transcription-bench` lui-même n'est pas lancé ici pour deux raisons :
`paths.DOSSIER_DATA` est une constante de module sans surcharge par variable
d'environnement, et `uv run` interpose un processus superviseur dont la
transmission de Ctrl+C/SIGTERM relève justement de la sonde 1.7 et non d'un test
automatisé du serveur de développement.
"""

from __future__ import annotations

import contextlib
import http.client
import io
import json
import os
import re
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import urllib.parse
from pathlib import Path

import psutil

from engines.hors_ligne import commande_runner
from engines.registre import RegistreMoteurs, creer_registre_fourni
from tests.test_audios import ecrire_wav
from tests.test_gestion_modeles import (
    CONTENUS,
    MOTEUR,
    FauxClientTelechargement,
    FausseVerification,
    FauxMoteurs,
)
from tests.test_moteurs import (
    ENVIRON_UV,
    ExecuteurBloqueSynchronisation,
    declaration_test,
)
from tests.test_verification_modeles import COMMIT, declaration_synthetique
from transcription_bench import paths
from transcription_bench.execution_moteur import (
    ARRET_DEMANDE,
    ETAT_INTERROMPUE,
    ExecutionMoteur,
)
from transcription_bench.executions import (
    CLE_MODELE_FACTICE,
    FENETRE_FIXE_SECONDES,
    LIBELLE_MODELE_FACTICE,
    DemandeExecution,
)
from transcription_bench.gestion_modeles import (
    NOM_MARQUEUR,
    GestionModeles,
    cle_stockage,
    empreinte_verification,
)
from transcription_bench.instance import InstanceDejaActive, VerrouInstance
from transcription_bench.moteurs import (
    ETAT_PRET,
    EtatMoteur,
    InstallationEchouee,
    InstallationMoteurs,
)
from transcription_bench.operations import (
    ETAT_INTERROMPUE as ETAT_CRENEAU_INTERROMPUE,
    TYPE_EXECUTION,
    TYPE_INSTALLATION,
    CreneauOperations,
    OperationEchouee,
)
from transcription_bench.supervision import (
    CODE_ARRET_SIGTERM,
    GestionnaireSignaux,
    NettoyageArret,
    signaux_arret_normal,
    signaux_supervises,
)
from transcription_bench.verification_modeles import (
    FichierVerifie,
    ResultatVerification,
)

DELAI = 30.0
PAS = 0.01

#: Descendant de longue durée du moteur, coopératif : `SIGTERM` le termine. Il
#: annonce sur sa sortie d'erreur que son gestionnaire de signaux est installé.
CODE_DESCENDANT = """
import sys
import time

print("pret", file=sys.stderr, flush=True)
time.sleep(120)
"""

#: Descendant qui **ignore** `SIGTERM` et garde le stdout du moteur ouvert :
#: seul le relevé psutil suivi d'un `kill` peut le terminer.
CODE_DESCENDANT_INSENSIBLE = """
import signal
import sys
import time

signal.signal(signal.SIGTERM, signal.SIG_IGN)
print("pret", file=sys.stderr, flush=True)
time.sleep(120)
"""

#: Enveloppe de test du runner : bloque dans l'adaptateur factice au premier
#: audio et lance en plus un descendant de longue durée, dans le même groupe de
#: processus. L'arrêt doit atteindre les deux.
CODE_MOTEUR_PALIER_DESCENDANT = """
import os
import runpy
import subprocess
import sys
import time

import engines.adaptateurs.factice as factice

_original = factice.transcrire
dossier = {dossier!r}
descendant_code = {descendant!r}
appels = [0]
LIMITE_PALIER = 30.0


def transcrire(*arguments, **options):
    appels[0] += 1
    marque = os.path.join(dossier, "palier-%d" % appels[0])
    with open(marque, "w", encoding="utf-8") as fichier:
        fichier.write("ok")
    if appels[0] == 1:
        descendant = subprocess.Popen(
            [sys.executable, "-c", descendant_code],
            stderr=subprocess.PIPE,
            text=True,
        )
        # Le descendant annonce qu'il a installé son gestionnaire de signaux :
        # le signal du groupe ne peut donc pas le tuer par avance.
        if descendant.stderr is not None:
            descendant.stderr.readline()
        with open(os.path.join(dossier, "moteur.pid"), "w", encoding="utf-8") as f:
            f.write(str(os.getpid()))
        with open(os.path.join(dossier, "descendant.pid"), "w", encoding="utf-8") as f:
            f.write(str(descendant.pid))
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

#: Processus serveur réel : même code que `uv run transcription-bench`, avec un
#: dossier de données temporaire et le moteur factice enveloppé par les paliers.
CODE_SERVEUR_SUPERVISE = """
import sys
from pathlib import Path

from engines.hors_ligne import commande_runner
from transcription_bench import cli, paths
from transcription_bench.execution_moteur import ExecutionMoteur

CODE = {code!r}


def construire_commande(interpreteur, chemin_job):
    commande = commande_runner(interpreteur, chemin_job)
    return [commande[0], "-c", CODE, commande[2], commande[1]]


class ServiceEnveloppe(ExecutionMoteur):
    def __init__(self, *arguments, **options):
        options["construire_commande"] = construire_commande
        options.setdefault("delai_arret", 2.0)
        super().__init__(*arguments, **options)


cli.ExecutionMoteur = ServiceEnveloppe
paths.DOSSIER_DATA = Path(sys.argv[1])
raise SystemExit(cli.main(["--port", sys.argv[2]]))
"""


# -- petits utilitaires -------------------------------------------------------


def attendre_condition(condition, description: str, delai: float = DELAI) -> None:
    """Attend qu'une condition devienne vraie, sans supposer de durée."""
    echeance = time.monotonic() + delai
    while time.monotonic() < echeance:
        if condition():
            return
        time.sleep(PAS)
    raise AssertionError(description)


def attendre_fichier(chemin: Path, delai: float = DELAI) -> None:
    attendre_condition(chemin.exists, f"fichier jamais créé : {chemin.name}", delai)


def lire_pid(chemin: Path) -> int:
    attendre_fichier(chemin)
    return int(chemin.read_text(encoding="utf-8").strip())


def identite(pid: int) -> float | None:
    """Heure de création d'un processus vivant, ou `None` s'il a disparu."""
    try:
        return psutil.Process(pid).create_time()
    except psutil.Error:
        return None


def attendre_disparition(pid: int, heure_creation: float | None, delai: float = DELAI) -> None:
    """Attend la disparition réelle d'un processus, identité vérifiée.

    Un processus zombie n'exécute plus rien : il est considéré comme arrêté. Le
    contrôle de l'heure de création évite de confondre sa disparition avec la
    réutilisation du PID par un autre programme.
    """

    def disparu() -> bool:
        try:
            processus = psutil.Process(pid)
            if heure_creation is not None:
                try:
                    if abs(processus.create_time() - heure_creation) > 1.0:
                        return True  # PID réutilisé : ce n'est plus notre processus
                except psutil.Error:
                    return True
            return processus.status() == psutil.STATUS_ZOMBIE
        except psutil.Error:
            return True

    attendre_condition(disparu, f"le processus {pid} est encore vivant", delai)


def port_libre() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as prise:
        prise.bind(("127.0.0.1", 0))
        return prise.getsockname()[1]


def requete_get(port: int, chemin: str) -> tuple[int, str]:
    connexion = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    try:
        connexion.request("GET", chemin)
        reponse = connexion.getresponse()
        return reponse.status, reponse.read().decode("utf-8", "replace")
    finally:
        connexion.close()


def requete_post(port: int, chemin: str, champs: dict[str, object]) -> int:
    corps = urllib.parse.urlencode(champs, doseq=True).encode("utf-8")
    connexion = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    try:
        connexion.request(
            "POST",
            chemin,
            body=corps,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        reponse = connexion.getresponse()
        reponse.read()
        return reponse.status
    finally:
        connexion.close()


def attendre_serveur(port: int, processus: subprocess.Popen[str]) -> None:
    def joignable() -> bool:
        if processus.poll() is not None:
            raise AssertionError(
                f"serveur arrêté prématurément (code {processus.returncode})"
            )
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=1):
                return True
        except OSError:
            return False

    attendre_condition(joignable, "serveur Waitress indisponible")


class ResultatsTemporairesTest(unittest.TestCase):
    """Base commune : dossier de données temporaire et nettoyage systématique."""

    def setUp(self) -> None:
        temporaire = tempfile.TemporaryDirectory()
        self.addCleanup(temporaire.cleanup)
        self.racine = Path(temporaire.name)
        self.donnees = self.racine / "data"
        self.donnees.mkdir(parents=True)

    def creer_creneau(self) -> CreneauOperations:
        creneau = CreneauOperations()
        self.addCleanup(creneau.arreter, 1.0)
        return creneau

    def verrou(self) -> VerrouInstance:
        verrou = VerrouInstance(self.donnees).acquerir()
        self.addCleanup(verrou.liberer)
        return verrou

    def assertVerrouTenant(self, donnees: Path | None = None) -> None:
        with self.assertRaises(InstanceDejaActive):
            VerrouInstance(donnees or self.donnees).acquerir()

    def assertVerrouLibre(self, donnees: Path | None = None) -> None:
        VerrouInstance(donnees or self.donnees).acquerir().liberer()


# -- 1. signaux ---------------------------------------------------------------


class GestionnaireSignauxTest(unittest.TestCase):
    """Premier signal → SIG_IGN puis exception ; les suivants sont ignorés."""

    def setUp(self) -> None:
        self.gestionnaires: list[GestionnaireSignaux] = []
        self.addCleanup(self._restaurer)

    def _restaurer(self) -> None:
        for gestionnaire in self.gestionnaires:
            gestionnaire.restaurer(force=True)

    def creer(self) -> GestionnaireSignaux:
        gestionnaire = GestionnaireSignaux()
        self.gestionnaires.append(gestionnaire)
        return gestionnaire

    def test_signaux_par_defaut_selon_l_os(self) -> None:
        attendus = (
            (signal.SIGINT,)
            if os.name == "nt"
            else (signal.SIGINT, signal.SIGTERM)
        )
        self.assertEqual(signaux_arret_normal(), attendus)
        self.assertEqual(self.creer().signaux, attendus)

    def test_sigint_reel_ignore_les_signaux_puis_leve(self) -> None:
        gestionnaire = self.creer()
        gestionnaire.installer()
        self.assertTrue(gestionnaire.installe)

        with self.assertRaises(KeyboardInterrupt):
            signal.raise_signal(signal.SIGINT)

        self.assertTrue(gestionnaire.recu)
        for numero in gestionnaire.signaux:
            self.assertIs(signal.getsignal(numero), signal.SIG_IGN)
        # Second signal : consommé sans exception ni nouvel effet.
        gestionnaire.traiter(signal.SIGINT, None)
        self.assertTrue(gestionnaire.recu)

    @unittest.skipIf(os.name == "nt", "SIGTERM n'est pas un signal d'arrêt Windows")
    def test_sigterm_reel_leve_systemexit(self) -> None:
        gestionnaire = self.creer()
        gestionnaire.installer()

        with self.assertRaises(SystemExit) as sortie:
            os.kill(os.getpid(), signal.SIGTERM)

        self.assertEqual(sortie.exception.code, CODE_ARRET_SIGTERM)
        for numero in gestionnaire.signaux:
            self.assertIs(signal.getsignal(numero), signal.SIG_IGN)

    def test_restaurer_apres_signal_conserve_sig_ign_sauf_force(self) -> None:
        gestionnaire = self.creer()
        gestionnaire.installer()
        with self.assertRaises(KeyboardInterrupt):
            gestionnaire.traiter(signal.SIGINT, None)

        gestionnaire.restaurer()
        self.assertIs(signal.getsignal(signal.SIGINT), signal.SIG_IGN)

        gestionnaire.restaurer(force=True)
        self.assertIsNot(signal.getsignal(signal.SIGINT), signal.SIG_IGN)

    def test_contexte_restaure_les_gestionnaires_sans_signal(self) -> None:
        avant = signal.getsignal(signal.SIGINT)

        with signaux_supervises() as gestionnaire:
            self.assertTrue(gestionnaire.installe)
            self.assertIsNot(signal.getsignal(signal.SIGINT), avant)

        self.assertIs(signal.getsignal(signal.SIGINT), avant)


# -- 2. ordre et idempotence --------------------------------------------------


class _CreneauFactice:
    def __init__(self, ordre: list[str], clos: bool = True) -> None:
        self.ordre = ordre
        self.clos = clos

    def passer_a_l_arret(self) -> None:
        self.ordre.append("creneau")

    def attendre_thread(self, delai: float) -> bool:
        self.ordre.append("attente_thread")
        return self.clos


class _ExecutionFactice:
    def __init__(self, ordre: list[str], issue: str = ARRET_DEMANDE) -> None:
        self.ordre = ordre
        self.issue = issue
        self.arret_serveur: bool | None = None

    def arreter_execution(self, *, arret_serveur: bool = False) -> str:
        self.ordre.append("moteur")
        self.arret_serveur = arret_serveur
        return self.issue


class _InstallationFactice:
    def __init__(self, ordre: list[str]) -> None:
        self.ordre = ordre

    def arreter(self) -> None:
        self.ordre.append("installation")


class _VerrouFactice:
    def __init__(self, ordre: list[str]) -> None:
        self.ordre = ordre
        self.liberations = 0

    def liberer(self) -> None:
        self.liberations += 1
        self.ordre.append("verrou")


class OrdreNettoyageTest(unittest.TestCase):
    """Ordre fixe et idempotence du nettoyage, sans processus ni fichier."""

    def test_ordre_des_etapes_et_appel_double(self) -> None:
        ordre: list[str] = []
        verrou = _VerrouFactice(ordre)
        lignes: list[str] = []
        execution = _ExecutionFactice(ordre)
        nettoyage = NettoyageArret(
            verrou=verrou,
            creneau=_CreneauFactice(ordre),
            execution=execution,
            installation=_InstallationFactice(ordre),
            journal=lignes.append,
        )

        self.assertIsNone(nettoyage.issue)
        self.assertTrue(nettoyage.executer())

        self.assertEqual(
            ordre, ["creneau", "moteur", "installation", "attente_thread", "verrou"]
        )
        self.assertEqual(lignes, [])
        # L'arrêt du moteur est déclaré comme un arrêt du serveur, pas comme une
        # demande de l'utilisateur.
        self.assertIs(execution.arret_serveur, True)
        self.assertTrue(nettoyage.issue)

        self.assertTrue(nettoyage.executer())
        self.assertEqual(
            ordre, ["creneau", "moteur", "installation", "attente_thread", "verrou"]
        )
        self.assertEqual(verrou.liberations, 1, "double clôture du verrou")

    def test_thread_encore_actif_conserve_le_verrou_et_le_signale(self) -> None:
        ordre: list[str] = []
        lignes: list[str] = []
        verrou = _VerrouFactice(ordre)
        nettoyage = NettoyageArret(
            verrou=verrou,
            creneau=_CreneauFactice(ordre, clos=False),
            journal=lignes.append,
        )

        self.assertFalse(nettoyage.executer())

        self.assertEqual(ordre, ["creneau", "attente_thread"])
        self.assertEqual(verrou.liberations, 0)
        self.assertTrue(any("opération non close" in ligne for ligne in lignes))
        self.assertFalse(nettoyage.executer())
        self.assertEqual(verrou.liberations, 0)

    def test_echec_d_une_etape_n_empeche_pas_les_suivantes(self) -> None:
        ordre: list[str] = []
        lignes: list[str] = []
        verrou = _VerrouFactice(ordre)

        class ExecutionEnPanne(_ExecutionFactice):
            def arreter_execution(self, *, arret_serveur: bool = False) -> str:
                self.ordre.append("moteur")
                raise RuntimeError("panne simulée de l'arrêt du moteur")

        nettoyage = NettoyageArret(
            verrou=verrou,
            creneau=_CreneauFactice(ordre),
            execution=ExecutionEnPanne(ordre),
            installation=_InstallationFactice(ordre),
            journal=lignes.append,
        )

        self.assertTrue(nettoyage.executer())

        self.assertEqual(
            ordre, ["creneau", "moteur", "installation", "attente_thread", "verrou"]
        )
        self.assertEqual(verrou.liberations, 1)
        self.assertTrue(
            any(ligne.startswith("arrêt du moteur impossible : RuntimeError") for ligne in lignes)
        )

    def test_moteur_survivant_signale_sans_trace(self) -> None:
        ordre: list[str] = []
        lignes: list[str] = []
        nettoyage = NettoyageArret(
            verrou=_VerrouFactice(ordre),
            creneau=_CreneauFactice(ordre),
            execution=_ExecutionFactice(ordre, issue="survivant"),
            journal=lignes.append,
        )

        self.assertTrue(nettoyage.executer())
        self.assertTrue(any("survit au signal de forçage" in ligne for ligne in lignes))
        self.assertFalse(any("Traceback" in ligne for ligne in lignes))

    def test_refus_de_recovery_libere_seulement_le_verrou(self) -> None:
        ordre: list[str] = []
        nettoyage = NettoyageArret(verrou=_VerrouFactice(ordre))

        self.assertTrue(nettoyage.executer())

        self.assertEqual(ordre, ["verrou"])


# -- 3. verrou, créneau et opérations réelles --------------------------------


class VerrouEnDernierTest(ResultatsTemporairesTest):
    """Le verrou d'instance n'est libéré qu'après la fin réelle du thread."""

    def test_verrou_libere_apres_la_cloture_du_thread(self) -> None:
        verrou = self.verrou()
        creneau = self.creer_creneau()
        creneau.demarrer(TYPE_EXECUTION, lambda travailleur: None)
        fil = creneau.thread_travailleur
        self.assertIsNotNone(fil)
        observations: list[tuple[bool, bool]] = []
        vrai_liberer = verrou.liberer

        def liberer() -> None:
            observations.append((fil.is_alive(), creneau.instantane().arrete))
            vrai_liberer()

        verrou.liberer = liberer  # type: ignore[method-assign]

        self.assertTrue(NettoyageArret(verrou=verrou, creneau=creneau).executer())

        self.assertEqual(observations, [(False, True)])
        self.assertFalse(verrou.detenu)
        self.assertVerrouLibre()

    def test_operation_non_close_conserve_le_verrou_puis_reste_idempotent(self) -> None:
        verrou = self.verrou()
        creneau = self.creer_creneau()
        liberation = threading.Event()
        self.addCleanup(liberation.set)
        creneau.demarrer(
            TYPE_EXECUTION, lambda travailleur: liberation.wait(DELAI)
        )
        fil = creneau.thread_travailleur
        self.assertIsNotNone(fil)
        erreur = io.StringIO()
        nettoyage = NettoyageArret(verrou=verrou, creneau=creneau, delai_operation=0.05)

        with contextlib.redirect_stderr(erreur):
            self.assertFalse(nettoyage.executer())

        self.assertTrue(verrou.detenu)
        self.assertVerrouTenant()
        self.assertIn("opération non close", erreur.getvalue())
        self.assertIn("Opération non close", " ".join(creneau.instantane().journal))

        liberation.set()
        fil.join(DELAI)
        self.assertFalse(fil.is_alive())
        self.assertFalse(nettoyage.executer())
        self.assertTrue(verrou.detenu, "le nettoyage idempotent ne doit pas relibérer")
        self.assertVerrouTenant()


class TelechargementBloqueTest(ResultatsTemporairesTest):
    """Téléchargement factice bloqué : aucun marqueur prêt, verrou conservé."""

    def setUp(self) -> None:
        super().setUp()
        self.creneau = self.creer_creneau()
        self.registre = RegistreMoteurs()
        self.registre.enregistrer(declaration_synthetique(identifiant=MOTEUR))
        self.moteurs = FauxMoteurs(
            (EtatMoteur(identifiant=MOTEUR, nom="Moteur de test", etat=ETAT_PRET),)
        )
        fichiers = tuple(
            FichierVerifie(nom, len(octets)) for nom, octets in CONTENUS.items()
        )
        self.resultat = ResultatVerification(
            accepte=True,
            identifiant="org/modele",
            moteur=MOTEUR,
            famille="whisper",
            commit=COMMIT,
            id_resolu="org/modele",
            fichiers=fichiers,
            taille_totale=sum(fichier.taille or 0 for fichier in fichiers),
            fichier_gguf=None,
            message="dépôt compatible (simulé)",
        )
        self.client = _ClientBloque()
        self.service = GestionModeles(
            self.donnees,
            self.registre,
            self.creneau,
            self.moteurs,
            verification=FausseVerification(self.resultat),
            client=self.client,
        )

    def dossier_modele(self) -> Path:
        cle = cle_stockage(self.resultat.id_resolu, self.resultat.commit, None)
        return self.donnees / "models" / MOTEUR / cle

    def test_aucun_marqueur_pret_et_verrou_non_libere(self) -> None:
        verrou = self.verrou()
        self.assertTrue(
            self.service.lancer_telechargement(
                empreinte_verification(self.resultat)
            )
        )
        self.assertTrue(
            self.client.debut.wait(DELAI), "téléchargement factice non démarré"
        )
        nettoyage = NettoyageArret(
            verrou=verrou, creneau=self.creneau, delai_operation=0.2
        )

        with contextlib.redirect_stderr(io.StringIO()):
            self.assertFalse(nettoyage.executer())

        self.assertTrue(verrou.detenu)
        self.assertVerrouTenant()
        self.assertFalse((self.dossier_modele() / NOM_MARQUEUR).exists())

        self.client.fin.set()
        fil = self.creneau.thread_travailleur
        self.assertIsNotNone(fil)
        fil.join(DELAI)
        self.assertFalse(fil.is_alive())

        self.assertFalse(
            (self.dossier_modele() / NOM_MARQUEUR).exists(),
            "un marqueur prêt a été publié après le passage à l'arrêt",
        )
        self.assertEqual(self.service.inventaire(), ())
        self.assertEqual(
            self.creneau.instantane().etat, ETAT_CRENEAU_INTERROMPUE
        )
        self.assertTrue(
            any(
                "Modèle non marqué prêt" in ligne
                for ligne in self.creneau.instantane().journal
            )
        )


class InstallationEchoueeTest(unittest.TestCase):
    """Échec d'installation prévu : message seul, sans pile complète."""

    def test_installation_echouee_est_un_echec_prevu_du_creneau(self) -> None:
        self.assertTrue(issubclass(InstallationEchouee, OperationEchouee))


class InstallationInterrompueTest(ResultatsTemporairesTest):
    """Installation bloquée : le nettoyage arrête uv et ne publie jamais prêt."""

    def test_installation_interrompue_non_prete(self) -> None:
        racine_projet = self.racine / "projet"
        (racine_projet / "requirements").mkdir(parents=True)
        declaration = declaration_test()
        (racine_projet / declaration.fichier_requirements).write_text(
            "", encoding="utf-8"
        )
        registre = RegistreMoteurs()
        registre.enregistrer(declaration)
        creneau = self.creer_creneau()
        executeur = ExecuteurBloqueSynchronisation()
        self.addCleanup(executeur.liberer_synchronisation.set)
        service = InstallationMoteurs(
            self.donnees,
            registre,
            creneau,
            racine_projet=racine_projet,
            executeur=executeur,
            environ=ENVIRON_UV,
        )
        verrou = self.verrou()

        creneau.demarrer(
            TYPE_INSTALLATION,
            lambda travailleur: service.installer(declaration.identifiant, travailleur),
            cible=declaration.identifiant,
        )
        self.assertTrue(
            executeur.debut_synchronisation.wait(DELAI),
            "synchronisation factice non démarrée",
        )

        with contextlib.redirect_stderr(io.StringIO()):
            self.assertTrue(
                NettoyageArret(
                    verrou=verrou,
                    creneau=creneau,
                    installation=service,
                    delai_operation=DELAI,
                ).executer()
            )

        marqueur = (
            self.donnees / "engines" / declaration.identifiant / "installation.json"
        )
        self.assertFalse(marqueur.exists())
        etat = service.inventaire()[0]
        self.assertNotEqual(etat.etat, ETAT_PRET)
        self.assertEqual(creneau.instantane().etat, ETAT_CRENEAU_INTERROMPUE)
        self.assertFalse(verrou.detenu)
        self.assertVerrouLibre()


class _ClientBloque(FauxClientTelechargement):
    """Client de téléchargement qui bloque jusqu'à libération."""

    def __init__(self) -> None:
        super().__init__()
        self.debut = threading.Event()
        self.fin = threading.Event()

    def telecharger(self, id_resolu, commit, fichiers, dossier) -> None:
        self.debut.set()
        if not self.fin.wait(DELAI):
            raise AssertionError("client bloqué non libéré")
        super().telecharger(id_resolu, commit, fichiers, dossier)


class MoteurReelArreteTest(ResultatsTemporairesTest):
    """Vrai sous-processus moteur en cours : arrêt sans survivant, état interrompu."""

    def setUp(self) -> None:
        super().setUp()
        self.dossier_audio = self.donnees / "audio"
        self.dossier_audio.mkdir(parents=True)
        self.paliers = self.racine / "paliers"
        self.paliers.mkdir()
        ecrire_wav(self.dossier_audio / "a.wav", duree=0.2)
        self.registre = creer_registre_fourni()
        self.creneau = self.creer_creneau()
        self.moteurs = InstallationMoteurs(
            self.donnees, self.registre, self.creneau
        )
        self.service = ExecutionMoteur(
            self.donnees,
            self.registre,
            self.moteurs,
            interpreteur_serveur=sys.executable,
            construire_commande=self._commande_enveloppee(CODE_DESCENDANT),
            delai_arret=1.0,
        )
        self.addCleanup(self._arreter)

    def _arreter(self) -> None:
        self.service.arreter_execution()
        fil = self.creneau.thread_travailleur
        if fil is not None:
            fil.join(DELAI)
        self.creneau.arreter(1.0)

    def _commande_enveloppee(self, descendant: str):
        code = CODE_MOTEUR_PALIER_DESCENDANT.format(
            dossier=str(self.paliers), descendant=descendant
        )

        def construire(interpreteur, chemin_job):
            commande = commande_runner(interpreteur, chemin_job)
            return [commande[0], "-c", code, commande[2], commande[1]]

        return construire

    def _demande(self) -> DemandeExecution:
        return DemandeExecution(
            moteur="factice",
            cle=CLE_MODELE_FACTICE,
            identifiant=LIBELLE_MODELE_FACTICE,
            id_resolu=LIBELLE_MODELE_FACTICE,
            commit="aucun",
            famille="factice",
            fichier_gguf=None,
            audios=("a.wav",),
            threads=2,
            reglages=(),
            fenetre_fixe_secondes=FENETRE_FIXE_SECONDES,
            synthetique=True,
        )

    def test_arret_termine_le_moteur_et_son_descendant(self) -> None:
        self._scenario_arret()

    def test_descendant_insensible_au_sigterm_ne_bloque_pas_l_arret(self) -> None:
        """Un descendant qui ignore SIGTERM et garde stdout ouvert est tué.

        Sans ce forçage, la lecture du stdout du moteur ne se terminerait jamais
        (le descendant en détient une extrémité) et le créneau resterait occupé.
        """
        self.service = ExecutionMoteur(
            self.donnees,
            self.registre,
            self.moteurs,
            interpreteur_serveur=sys.executable,
            construire_commande=self._commande_enveloppee(CODE_DESCENDANT_INSENSIBLE),
            delai_arret=0.2,
        )
        self._scenario_arret()

    def _scenario_arret(self) -> None:
        verrou = self.verrou()
        self.service.reserver()
        self.creneau.demarrer(
            TYPE_EXECUTION,
            lambda travailleur: self.service.lancer(self._demande(), travailleur),
            cible="factice",
        )
        attendre_fichier(self.paliers / "palier-1")
        pid_moteur = lire_pid(self.paliers / "moteur.pid")
        pid_descendant = lire_pid(self.paliers / "descendant.pid")
        supervise = self.service.pid_actif()
        if os.name == "nt":
            # Sous Windows, le python du venv uv est un trampoline : le PID
            # supervisé (Popen) est le parent de l'interpréteur réel, qui
            # s'auto-déclare dans moteur.pid ; le trampoline place l'enfant
            # dans un Job Object, le tuer termine bien l'interpréteur.
            self.assertEqual(psutil.Process(pid_moteur).ppid(), supervise)
        else:
            self.assertEqual(supervise, pid_moteur)
        heure_moteur, heure_descendant = identite(pid_moteur), identite(pid_descendant)
        self.assertIsNotNone(heure_moteur)
        self.assertIsNotNone(heure_descendant)
        self.assertNotEqual(pid_moteur, pid_descendant)
        self.assertEqual(
            psutil.Process(pid_descendant).ppid(), pid_moteur
        )

        with contextlib.redirect_stderr(io.StringIO()):
            self.assertTrue(
                NettoyageArret(
                    verrou=verrou,
                    creneau=self.creneau,
                    execution=self.service,
                    delai_operation=DELAI,
                ).executer()
            )

        fil = self.creneau.thread_travailleur
        self.assertIsNotNone(fil)
        self.assertFalse(fil.is_alive())
        resultat = self.service.derniere_execution()
        self.assertIsNotNone(resultat)
        self.assertEqual(resultat.etat, ETAT_INTERROMPUE)
        # L'audio était en cours de transcription : aucun événement reçu, il est
        # signalé non traité et les résultats déjà écrits restent valides.
        self.assertEqual(resultat.audios_non_traites, ("a.wav",))
        codes_arret = (-signal.SIGTERM, -signal.SIGKILL)
        if os.name == "nt":
            # Un arrêt forcé Windows (TerminateProcess) se lit comme 1.
            codes_arret = (*codes_arret, 1)
        self.assertIn(resultat.code_sortie, codes_arret)
        run_json = (
            self.donnees / "results" / resultat.identifiant_resultat / "run.json"
        )
        self.assertEqual(
            json.loads(run_json.read_text(encoding="utf-8"))["etat"], "interrupted"
        )
        attendre_disparition(pid_moteur, heure_moteur)
        attendre_disparition(pid_descendant, heure_descendant)
        self.assertFalse(verrou.detenu)
        self.assertVerrouLibre()
        instantane = self.creneau.instantane()
        self.assertEqual(instantane.etat, ETAT_CRENEAU_INTERROMPUE)
        # L'arrêt normal du serveur n'est pas une demande de l'utilisateur.
        journal = "\n".join(instantane.journal)
        self.assertIn("Opération interrompue par l'arrêt du serveur.", journal)
        self.assertNotIn("à la demande de l'utilisateur", journal)


# -- 4. processus serveur réel ------------------------------------------------


@unittest.skipIf(os.name == "nt", "SIGINT/SIGTERM réels non vérifiés sous Windows")
class ServeurReelArreteTest(ResultatsTemporairesTest):
    """Serveur Waitress réel : SIGINT puis SIGTERM, sans survivant, verrou libre.

    Le processus lancé exécute le même `cli.main` que `uv run transcription-bench`
    avec l'interpréteur du serveur et un dossier de données temporaire ; aucun
    moteur réel, aucun poids, aucun réseau. Ce test ne remplace ni la sonde 1.7
    (Ctrl+C via `uv run`, double Ctrl+C, port occupé) ni le rejeu Windows.
    """

    def setUp(self) -> None:
        super().setUp()
        self.port = port_libre()
        self.dossier_audio = self.donnees / "audio"
        self.dossier_audio.mkdir(parents=True)
        ecrire_wav(self.dossier_audio / "a.wav", duree=0.2)
        self.paliers = self.racine / "paliers"
        self.paliers.mkdir()

    def _lancer(self) -> subprocess.Popen[str]:
        code = CODE_SERVEUR_SUPERVISE.format(
            code=CODE_MOTEUR_PALIER_DESCENDANT.format(
                dossier=str(self.paliers), descendant=CODE_DESCENDANT
            )
        )
        processus = subprocess.Popen(
            [sys.executable, "-c", code, str(self.donnees), str(self.port)],
            cwd=paths.RACINE_PROJET,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
        )
        self.addCleanup(self._arreter, processus)
        attendre_serveur(self.port, processus)
        return processus

    def _arreter(self, processus: subprocess.Popen[str]) -> None:
        """Nettoyage de secours : serveur, moteur et descendant, même en échec.

        Les PID sont relus dans les fichiers de palier : le test peut échouer
        avant de les avoir consommés, et un moteur ou un descendant survivant
        resterait sinon actif jusqu'à sa limite interne.
        """
        if processus.poll() is None:
            processus.kill()
            processus.wait(timeout=DELAI)
        for nom in ("moteur.pid", "descendant.pid"):
            try:
                pid = int((self.paliers / nom).read_text(encoding="utf-8").strip())
            except (OSError, ValueError):
                continue
            try:
                psutil.Process(pid).kill()
            except psutil.Error:
                continue
        for flux in (processus.stdout, processus.stderr):
            if flux is not None:
                flux.close()

    def _lancer_execution(self) -> tuple[int, int]:
        """Lance une exécution par HTTP et renvoie (pid moteur, pid descendant)."""
        statut, page = requete_get(self.port, "/executions")
        self.assertEqual(statut, 200, page)
        jeton = re.search(r'name="jeton_csrf" value="([^"]+)"', page)
        self.assertIsNotNone(jeton, "jeton anti-CSRF absent de la page")
        statut = requete_post(
            self.port,
            "/executions/lancer",
            {
                "modele": f"factice/{CLE_MODELE_FACTICE}",
                "audios": "a.wav",
                "threads": "2",
                "jeton_csrf": jeton.group(1),
            },
        )
        self.assertEqual(statut, 303)
        attendre_fichier(self.paliers / "palier-1")
        pid_moteur = lire_pid(self.paliers / "moteur.pid")
        pid_descendant = lire_pid(self.paliers / "descendant.pid")
        return pid_moteur, pid_descendant

    def _scenario_arret(self, numero: int, sortie_attendue: int) -> None:
        processus = self._lancer()
        pid_moteur, pid_descendant = self._lancer_execution()
        heure_moteur, heure_descendant = identite(pid_moteur), identite(pid_descendant)
        self.assertIsNotNone(heure_moteur)
        self.assertIsNotNone(heure_descendant)

        os.kill(processus.pid, numero)
        sortie, erreur = processus.communicate(timeout=DELAI)

        self.assertEqual(processus.returncode, sortie_attendue, erreur)
        self.assertNotIn("Traceback", erreur)
        self.assertIn("Interface disponible", sortie)
        self.assertIn("Arrêt du serveur.", sortie)
        attendre_disparition(pid_moteur, heure_moteur)
        attendre_disparition(pid_descendant, heure_descendant)
        self.assertVerrouLibre()

        runs = sorted((self.donnees / "results").glob("*/run.json"))
        self.assertEqual(len(runs), 1)
        contenu = json.loads(runs[0].read_text(encoding="utf-8"))
        self.assertEqual(contenu["etat"], "interrupted")
        self.assertIsNotNone(contenu["fin"])

    def test_sigint_arrete_le_serveur_le_moteur_et_son_descendant(self) -> None:
        self._scenario_arret(signal.SIGINT, 0)

    def test_sigterm_arrete_le_serveur_le_moteur_et_son_descendant(self) -> None:
        self._scenario_arret(signal.SIGTERM, 0)

    def test_second_signal_pendant_le_nettoyage_est_ignore(self) -> None:
        """SIGINT puis SIGTERM : le second signal n'interrompt pas la clôture."""
        processus = self._lancer()
        pid_moteur, pid_descendant = self._lancer_execution()
        heure_moteur, heure_descendant = identite(pid_moteur), identite(pid_descendant)
        self.assertIsNotNone(heure_moteur)
        self.assertIsNotNone(heure_descendant)

        os.kill(processus.pid, signal.SIGINT)
        # Le moteur est terminé par le nettoyage : le second signal arrive donc
        # pendant la clôture. S'il venait après la sortie, il n'aurait plus de
        # destinataire et le test resterait valable.
        attendre_disparition(pid_moteur, heure_moteur, delai=10.0)
        try:
            os.kill(processus.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass

        sortie, erreur = processus.communicate(timeout=DELAI)
        self.assertEqual(processus.returncode, 0, erreur)
        self.assertNotIn("Traceback", erreur)
        self.assertIn("Arrêt du serveur.", sortie)
        attendre_disparition(pid_descendant, heure_descendant)
        self.assertVerrouLibre()


if __name__ == "__main__":
    unittest.main()
