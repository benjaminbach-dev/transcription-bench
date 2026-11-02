"""Tests de l'inventaire et de l'installation explicite des moteurs.

Les installations réussies et le contrôle d'import en échec utilisent de
véritables commandes `uv` dans un dossier temporaire, avec réseau coupé
(`UV_OFFLINE=1`) et téléchargement de Python interdit
(`UV_PYTHON_DOWNLOADS=never`), sur des verrous vides. Aucun moteur réel, aucun
poids et aucun accès réseau externe ne sont utilisés ; les versions affichées
sont celles réellement lues ou restent absentes.
"""

from __future__ import annotations

import hashlib
import html
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

import psutil

from engines.declarations import DeclarationAdaptateur, Famille
from engines.registre import RegistreMoteurs, creer_registre_fourni
from transcription_bench.moteurs import (
    ETAT_ECHEC,
    ETAT_NON_INSTALLE,
    ETAT_PRET,
    ExecuteurCommandes,
    ExecuteurSubprocess,
    InstallationEchouee,
    InstallationIndisponible,
    InstallationMoteurs,
    ResultatCommande,
    empreinte_fichier,
)
from transcription_bench.operations import (
    ETAT_ECHOUEE,
    ETAT_INTERROMPUE,
    ETAT_TERMINEE,
    TYPE_INSTALLATION,
    CreneauOperations,
)
from transcription_bench.paths import ValeurRefusee
from transcription_bench.stockage import JsonInvalide, ecrire_json_atomique, lire_json
from transcription_bench.web import (
    NOM_CHAMP_JETON,
    ConfigApplication,
    ServicesApplication,
    create_app,
)

PORT_TEST = 8765
BASE_URL = f"http://127.0.0.1:{PORT_TEST}"
DELAI = 60.0
ENVIRON_UV = {
    **os.environ,
    "UV_OFFLINE": "1",
    "UV_PYTHON_DOWNLOADS": "never",
}
SECRET_FACTICE = "valeur-secrete-a-ne-pas-journaliser"

CODE_COMMANDE_AVEC_DESCENDANT = """
import subprocess
import sys
import time

enfant = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)"])
print(enfant.pid, flush=True)
time.sleep(120)
"""


def declaration_test(
    identifiant: str = "engine-test",
    modules: tuple[str, ...] = ("sys",),
) -> DeclarationAdaptateur:
    """Déclaration d'un moteur de test, sans adaptateur ni paquet moteur."""
    return DeclarationAdaptateur(
        identifiant=identifiant,
        nom=f"Moteur de test {identifiant}",
        fichier_requirements=f"requirements/{identifiant}.txt",
        regle_compatibilite="aucune",
        familles=(Famille("factice", "Moteur de test"),),
        modules_verification=modules,
    )


def chemin_interpreteur(dossier: Path) -> Path:
    if os.name == "nt":
        return dossier / "Scripts" / "python.exe"
    return dossier / "bin" / "python"


class SocleMoteurs(unittest.TestCase):
    """Projet temporaire, registre contrôlé et créneau partagé."""

    def setUp(self) -> None:
        temporaire = tempfile.TemporaryDirectory()
        self.addCleanup(temporaire.cleanup)
        # Chemin résolu : sous Windows, le dossier temporaire peut être rendu
        # en chemin court (8.3) alors que le produit résout les siens.
        self.base = Path(temporaire.name).resolve()
        self.racine = self.base / "projet"
        self.donnees = self.racine / "data"
        (self.racine / "requirements").mkdir(parents=True)
        self.creneau = CreneauOperations()
        self.registre = self.registre_avec(declaration_test())

    def registre_avec(
        self, *declarations: DeclarationAdaptateur, contenu: str = ""
    ) -> RegistreMoteurs:
        registre = RegistreMoteurs()
        for declaration in declarations:
            chemin = self.racine / declaration.fichier_requirements
            chemin.parent.mkdir(parents=True, exist_ok=True)
            chemin.write_text(contenu, encoding="utf-8")
            registre.enregistrer(declaration)
        return registre

    def service(self, **options) -> InstallationMoteurs:
        options.setdefault("racine_projet", self.racine)
        options.setdefault("environ", ENVIRON_UV)
        return InstallationMoteurs(self.donnees, self.registre, self.creneau, **options)

    def lancer_installation(
        self, service: InstallationMoteurs, identifiant: str = "engine-test"
    ) -> object:
        self.creneau.demarrer(
            TYPE_INSTALLATION,
            lambda travailleur: service.installer(identifiant, travailleur),
            cible=identifiant,
        )
        thread = self.creneau.thread_travailleur
        self.assertIsNotNone(thread)
        thread.join(DELAI)
        self.assertFalse(thread.is_alive(), "l'installation de test ne s'est pas terminée")
        return self.creneau.instantane()

    def etat(self, service: InstallationMoteurs, identifiant: str = "engine-test"):
        return {
            moteur.identifiant: moteur for moteur in service.inventaire()
        }[identifiant]

    def dossier_moteur(self, identifiant: str = "engine-test") -> Path:
        return self.donnees / "engines" / identifiant

    def marqueur(self, identifiant: str = "engine-test") -> Path:
        return self.dossier_moteur(identifiant) / "installation.json"

    def journal(self, identifiant: str = "engine-test") -> Path:
        return self.donnees / "engines" / f"{identifiant}.installation.log"

    def creer_interpreteur(self, identifiant: str = "engine-test") -> Path:
        dossier = self.dossier_moteur(identifiant)
        interpreteur = chemin_interpreteur(dossier)
        interpreteur.parent.mkdir(parents=True, exist_ok=True)
        interpreteur.write_text("", encoding="utf-8")
        return interpreteur

    def ecrire_marqueur(
        self,
        identifiant: str = "engine-test",
        modules: tuple[str, ...] = ("sys",),
        versions: dict[str, str | None] | None = None,
    ) -> Path:
        """Marqueur valide pour un état prêt simulé, sans lancer d'installation."""
        self.creer_interpreteur(identifiant)
        verrou = self.racine / "requirements" / f"{identifiant}.txt"
        marqueur = self.marqueur(identifiant)
        ecrire_json_atomique(
            marqueur,
            {
                "moteur": identifiant,
                "empreinte_verrou": hashlib.sha256(verrou.read_bytes()).hexdigest(),
                "date": "2026-10-25T12:00:00+02:00",
                "versions": versions if versions is not None else {m: None for m in modules},
            },
        )
        return marqueur


class StockageJsonTest(unittest.TestCase):
    """Lecture JSON commune : un contenu non UTF-8 est refusé proprement."""

    def test_octets_non_utf8_refuses_comme_json_invalide(self) -> None:
        temporaire = tempfile.TemporaryDirectory()
        self.addCleanup(temporaire.cleanup)
        chemin = Path(temporaire.name) / "marqueur-corrompu.json"
        chemin.write_bytes(b"\xff\xfe{")

        with self.assertRaises(JsonInvalide):
            lire_json(chemin)


class InstallationReelleTest(SocleMoteurs):
    """Installations réelles avec uv hors ligne et verrou vide."""

    def test_installation_reussie_publie_le_marqueur_et_l_etat_pret(self) -> None:
        service = self.service(environ={**ENVIRON_UV, "TB_SECRET_TEST": SECRET_FACTICE})
        instantane = self.lancer_installation(service)

        self.assertEqual(instantane.etat, ETAT_TERMINEE, instantane.erreur)
        marqueur = self.marqueur()
        self.assertTrue(marqueur.is_file())
        donnees = json.loads(marqueur.read_text(encoding="utf-8"))
        self.assertEqual(donnees["moteur"], "engine-test")
        self.assertEqual(
            donnees["empreinte_verrou"], hashlib.sha256(b"").hexdigest()
        )
        self.assertEqual(donnees["versions"], {"sys": None})
        self.assertTrue(donnees["date"])
        self.assertTrue(chemin_interpreteur(self.dossier_moteur()).is_file())
        self.assertEqual(
            list(self.dossier_moteur().glob(".installation.json.*")), []
        )

        etat = self.etat(service)
        self.assertEqual(etat.etat, ETAT_PRET)
        self.assertFalse(etat.factice)
        self.assertTrue(etat.installable)
        self.assertEqual(dict(etat.versions), {"sys": None})
        self.assertEqual(etat.date_installation, donnees["date"])
        self.assertEqual(etat.note, None)

        lignes = service.lire_journal("engine-test")
        self.assertTrue(any("Moteur prêt" in ligne for ligne in lignes))
        self.assertFalse(any(SECRET_FACTICE in ligne for ligne in lignes))

    def test_import_inconnu_donne_echec_sans_marqueur(self) -> None:
        self.registre = self.registre_avec(
            declaration_test(modules=("module_absent_du_venv_de_test",))
        )
        service = self.service()
        instantane = self.lancer_installation(service)

        self.assertEqual(instantane.etat, ETAT_ECHOUEE, instantane.erreur)
        self.assertFalse(self.marqueur().exists())
        etat = self.etat(service)
        self.assertEqual(etat.etat, ETAT_ECHEC)
        self.assertNotEqual(etat.etat, ETAT_PRET)
        self.assertTrue(etat.installable)
        self.assertTrue(
            any("contrôle d'import échoué" in ligne for ligne in service.lire_journal("engine-test"))
        )

    def test_echec_de_uv_venv_donne_echec_meme_sans_environnement(self) -> None:
        service = self.service(executeur=ExecuteurVenvEchouee())
        instantane = self.lancer_installation(service)

        self.assertEqual(instantane.etat, ETAT_ECHOUEE)
        self.assertFalse(self.dossier_moteur().exists())
        self.assertFalse(self.marqueur().exists())
        etat = self.etat(service)
        self.assertEqual(etat.etat, ETAT_ECHEC)
        self.assertTrue(etat.installable)
        self.assertTrue(
            any("uv venv a échoué" in ligne for ligne in service.lire_journal("engine-test"))
        )

    def test_echec_de_synchronisation_donne_echec_sans_marqueur(self) -> None:
        service = self.service(executeur=ExecuteurSynchronisationEchouee())
        instantane = self.lancer_installation(service)

        self.assertEqual(instantane.etat, ETAT_ECHOUEE, instantane.erreur)
        self.assertFalse(self.marqueur().exists())
        self.assertEqual(self.etat(service).etat, ETAT_ECHEC)
        self.assertTrue(
            any("uv pip sync a échoué" in ligne for ligne in service.lire_journal("engine-test"))
        )

    def test_marqueur_absent_apres_redemarrage_donne_echec_puis_reinstallation(self) -> None:
        service = self.service()
        self.lancer_installation(service)
        self.marqueur().unlink()

        redemarrage = self.service()
        etat = self.etat(redemarrage)
        self.assertEqual(etat.etat, ETAT_ECHEC)
        self.assertTrue(etat.installable)
        self.assertNotEqual(etat.etat, ETAT_PRET)

        self.lancer_installation(redemarrage)
        self.assertEqual(self.etat(redemarrage).etat, ETAT_PRET)

    def test_empreinte_du_verrou_modifiee_invalide_le_marqueur(self) -> None:
        service = self.service()
        self.lancer_installation(service)
        verrou = self.racine / "requirements" / "engine-test.txt"
        verrou.write_text("# verrou modifié après installation\n", encoding="utf-8")

        redemarrage = self.service()
        etat = self.etat(redemarrage)
        self.assertEqual(etat.etat, ETAT_ECHEC)
        self.assertIn("incohérent", etat.note or "")
        self.assertNotEqual(etat.etat, ETAT_PRET)


    def test_module_trouve_seulement_par_pythonpath_refuse(self) -> None:
        faux = self.base / "faux-module"
        faux.mkdir()
        (faux / "module_par_pythonpath.py").write_text("VALEUR = 1\n", encoding="utf-8")
        self.registre = self.registre_avec(
            declaration_test(modules=("module_par_pythonpath",))
        )
        service = self.service(environ={**ENVIRON_UV, "PYTHONPATH": str(faux)})

        instantane = self.lancer_installation(service)

        self.assertEqual(instantane.etat, ETAT_ECHOUEE, instantane.erreur)
        self.assertFalse(self.marqueur().exists())
        self.assertEqual(self.etat(service).etat, ETAT_ECHEC)
        self.assertTrue(
            any(
                "contrôle d'import échoué" in ligne
                for ligne in service.lire_journal("engine-test")
            ),
            "un module trouvé par PYTHONPATH ne doit pas faire réussir le contrôle",
        )


class ExecuteurVenvEchouee(ExecuteurCommandes):
    """Exécuteur contrôlé : `uv venv` échoue avant de créer le dossier."""

    def executer(self, arguments, *, env, journaliser, delai=None):
        journaliser("échec de création simulé")
        return ResultatCommande(code=1, sortie="échec de création simulé")


class ExecuteurSynchronisationEchouee(ExecuteurSubprocess):
    """Exécuteur réel qui simule un code de sortie 1 pour `uv pip sync`."""

    def executer(self, arguments, *, env, journaliser, delai=None):
        if "sync" in arguments:
            journaliser("échec de synchronisation simulé")
            return ResultatCommande(code=1, sortie="échec simulé")
        return super().executer(
            arguments, env=env, journaliser=journaliser, delai=delai
        )


class ExecuteurBloqueSynchronisation(ExecuteurCommandes):
    """Exécuteur contrôlé : crée un faux venv et bloque la synchronisation."""

    def __init__(self) -> None:
        self.debut_synchronisation = threading.Event()
        self.liberer_synchronisation = threading.Event()

    def executer(self, arguments, *, env, journaliser, delai=None):
        if "venv" in arguments:
            dossier = Path(arguments[-1])
            (dossier / "bin").mkdir(parents=True, exist_ok=True)
            (dossier / "bin" / "python").write_text("", encoding="utf-8")
            dossier.joinpath("Scripts").mkdir(parents=True, exist_ok=True)
            (dossier / "Scripts" / "python.exe").write_text("", encoding="utf-8")
            journaliser("environnement simulé créé")
            return ResultatCommande(code=0, sortie="")
        if "sync" in arguments:
            self.debut_synchronisation.set()
            self.liberer_synchronisation.wait(DELAI)
            journaliser("synchronisation simulée terminée")
            return ResultatCommande(code=0, sortie="")
        if "-c" in arguments:
            if "sys.prefix" in arguments[-1]:
                return ResultatCommande(
                    code=0, sortie=str(Path(arguments[0]).parent.parent)
                )
            journaliser("contrôle d'import simulé")
            return ResultatCommande(code=0, sortie='{"modules": {"sys": null}}')
        return ResultatCommande(code=1, sortie="commande inattendue")

    def arreter(self) -> None:
        self.liberer_synchronisation.set()


class ExecuteurEnregistreur(ExecuteurCommandes):
    """Exécuteur contrôlé : installation simulée réussie, commandes enregistrées."""

    def __init__(self) -> None:
        self.commandes: list[list[str]] = []

    def executer(self, arguments, *, env, journaliser, delai=None):
        self.commandes.append(list(arguments))
        if "venv" in arguments:
            dossier = Path(arguments[-1])
            interpreteur = chemin_interpreteur(dossier)
            interpreteur.parent.mkdir(parents=True, exist_ok=True)
            interpreteur.write_text("", encoding="utf-8")
            journaliser("environnement simulé créé")
            return ResultatCommande(code=0, sortie="")
        if "-c" in arguments:
            if "sys.prefix" in arguments[-1]:
                return ResultatCommande(
                    code=0, sortie=str(Path(arguments[0]).parent.parent)
                )
            journaliser("contrôle d'import simulé")
            return ResultatCommande(code=0, sortie='{"modules": {"sys": null}}')
        return ResultatCommande(code=0, sortie="")


class ExecuteurCibleServeur(ExecuteurCommandes):
    """Exécuteur contrôlé : venv simulé dont la sonde renvoie le préfixe serveur."""

    def __init__(self) -> None:
        self.commandes: list[list[str]] = []

    def executer(self, arguments, *, env, journaliser, delai=None):
        self.commandes.append(list(arguments))
        if "venv" in arguments:
            dossier = Path(arguments[-1])
            interpreteur = chemin_interpreteur(dossier)
            interpreteur.parent.mkdir(parents=True, exist_ok=True)
            interpreteur.write_text("", encoding="utf-8")
            return ResultatCommande(code=0, sortie="")
        if "-c" in arguments:
            return ResultatCommande(code=0, sortie=str(sys.prefix))
        return ResultatCommande(code=0, sortie="")


class ArretEtCheminsTest(SocleMoteurs):
    def test_arret_empeche_la_publication_du_marqueur_pret(self) -> None:
        executeur = ExecuteurBloqueSynchronisation()
        self.addCleanup(executeur.liberer_synchronisation.set)
        service = self.service(executeur=executeur)
        self.creneau.demarrer(
            TYPE_INSTALLATION,
            lambda travailleur: service.installer("engine-test", travailleur),
            cible="engine-test",
        )
        thread = self.creneau.thread_travailleur
        self.assertIsNotNone(thread)
        self.assertTrue(executeur.debut_synchronisation.wait(DELAI))

        self.assertFalse(self.creneau.arreter(0.05))
        executeur.liberer_synchronisation.set()
        thread.join(DELAI)
        self.assertFalse(thread.is_alive())

        self.assertEqual(self.creneau.instantane().etat, ETAT_INTERROMPUE)
        self.assertFalse(self.marqueur().exists())
        self.assertEqual(self.etat(service).etat, ETAT_ECHEC)
        self.assertTrue(
            any("non publié" in ligne for ligne in service.lire_journal("engine-test"))
        )

    @unittest.skipIf(os.name == "nt", "groupes de processus POSIX")
    def test_arret_de_la_commande_termine_aussi_ses_descendants(self) -> None:
        """`uv` et ce qu'il a lancé ne survivent pas à l'arrêt du serveur."""
        executeur = ExecuteurSubprocess()
        pids: list[int] = []
        pret = threading.Event()
        resultat: dict[str, ResultatCommande] = {}

        def journaliser(ligne: str) -> None:
            if ligne.strip().isdigit():
                pids.append(int(ligne.strip()))
                pret.set()

        def travail() -> None:
            resultat["commande"] = executeur.executer(
                [sys.executable, "-u", "-c", CODE_COMMANDE_AVEC_DESCENDANT],
                env=os.environ,
                journaliser=journaliser,
            )

        fil = threading.Thread(target=travail, daemon=True)
        try:
            fil.start()
            self.assertTrue(pret.wait(DELAI), "commande de test non démarrée")
            executeur.arreter()
            fil.join(DELAI)
            self.assertFalse(fil.is_alive())
            self.assertNotEqual(resultat["commande"].code, 0)
            self.assertFalse(executeur.en_cours)
        finally:
            executeur.arreter()
            fil.join(DELAI)

        echeance = time.monotonic() + DELAI
        while time.monotonic() < echeance:
            try:
                if psutil.Process(pids[0]).status() == psutil.STATUS_ZOMBIE:
                    break
            except psutil.Error:
                break
            time.sleep(0.01)
        else:
            self.fail("le descendant de la commande survit à l'arrêt")

    @unittest.skipIf(os.name == "nt", "liens symboliques non qualifiés sous Windows")
    def test_environnement_symbolique_sortant_refuse_sans_io(self) -> None:
        (self.donnees / "engines").mkdir(parents=True)
        serveur = self.base / "serveur-venv"
        (serveur / "bin").mkdir(parents=True)
        (serveur / "bin" / "python").write_text("", encoding="utf-8")
        os.symlink(serveur, self.donnees / "engines" / "engine-test")

        service = self.service()
        with self.assertRaises(ValeurRefusee):
            service.verifier_installable("engine-test")
        etat = self.etat(service)
        self.assertEqual(etat.etat, ETAT_ECHEC)
        self.assertFalse(etat.installable)

    def test_cible_interpreteur_serveur_refusee_avant_sync(self) -> None:
        executeur = ExecuteurCibleServeur()
        service = self.service(executeur=executeur)

        instantane = self.lancer_installation(service)

        self.assertEqual(instantane.etat, ETAT_ECHOUEE)
        self.assertFalse(any("sync" in commande for commande in executeur.commandes))
        self.assertFalse(self.marqueur().exists())
        self.assertEqual(self.etat(service).etat, ETAT_ECHEC)
        self.assertTrue(
            any(
                "cible de l'interpréteur différente" in ligne
                for ligne in service.lire_journal("engine-test")
            )
        )

    def test_echec_d_un_moteur_ne_touche_pas_le_marqueur_d_un_autre(self) -> None:
        self.registre = self.registre_avec(
            declaration_test("engine-a"), declaration_test("engine-b")
        )
        service = self.service()
        self.ecrire_marqueur("engine-a")
        avant = self.marqueur("engine-a").read_bytes()
        self.assertEqual(self.etat(service, "engine-a").etat, ETAT_PRET)

        echec = self.service(executeur=ExecuteurSynchronisationEchouee())
        self.lancer_installation(echec, "engine-b")

        self.assertEqual(self.etat(service, "engine-b").etat, ETAT_ECHEC)
        self.assertEqual(self.marqueur("engine-a").read_bytes(), avant)
        self.assertEqual(self.etat(service, "engine-a").etat, ETAT_PRET)

    def test_factice_pret_sans_installation_ni_fichier(self) -> None:
        service = InstallationMoteurs(
            self.donnees, creer_registre_fourni(), self.creneau, racine_projet=self.racine
        )
        etats = {etat.identifiant: etat for etat in service.inventaire()}

        factice = etats["factice"]
        self.assertEqual(factice.etat, ETAT_PRET)
        self.assertTrue(factice.factice)
        self.assertFalse(factice.installable)
        self.assertEqual(factice.versions, ())
        self.assertIn("aucune installation", factice.note or "")
        self.assertEqual(etats["faster-whisper"].etat, ETAT_NON_INSTALLE)
        self.assertFalse(etats["faster-whisper"].installable)
        with self.assertRaises(InstallationIndisponible):
            service.verifier_installable("factice")
        self.assertFalse(self.donnees.exists())

    def test_processus_d_installation_termine_sans_orphelin(self) -> None:
        executeur = ExecuteurSubprocess()
        lignes: list[str] = []
        resultat: dict[str, ResultatCommande] = {}

        def travail() -> None:
            resultat["commande"] = executeur.executer(
                [
                    sys.executable,
                    "-u",
                    "-c",
                    "print('démarré', flush=True)\nimport time\ntime.sleep(30)",
                ],
                env=os.environ,
                journaliser=lignes.append,
            )

        thread = threading.Thread(target=travail, daemon=True)
        thread.start()
        echeance = time.monotonic() + 10
        while time.monotonic() < echeance and "démarré" not in lignes:
            time.sleep(0.02)
        self.assertIn("démarré", lignes)

        executeur.arreter()
        thread.join(15)

        self.assertFalse(thread.is_alive())
        self.assertFalse(executeur.en_cours)
        self.assertNotEqual(resultat["commande"].code, 0)


    def test_arret_pendant_le_demarrage_ne_laisse_pas_de_processus(self) -> None:
        executeur = ExecuteurSubprocess()
        demarrage_tente = threading.Event()
        processus_crees: list[subprocess.Popen] = []
        vrai_popen = subprocess.Popen

        class PopenRetarde(vrai_popen):
            """Popen réel avec une fenêtre déterministe avant le vrai démarrage."""

            def __init__(self, *arguments, **options):
                demarrage_tente.set()
                time.sleep(0.1)
                super().__init__(*arguments, **options)
                processus_crees.append(self)

        resultat: dict[str, ResultatCommande] = {}

        def travail() -> None:
            resultat["commande"] = executeur.executer(
                [sys.executable, "-u", "-c", "import time\ntime.sleep(30)"],
                env=os.environ,
                journaliser=lambda ligne: None,
            )

        def arreter_pendant_le_demarrage() -> None:
            self.assertTrue(demarrage_tente.wait(DELAI))
            executeur.arreter()

        thread_arret = threading.Thread(
            target=arreter_pendant_le_demarrage, daemon=True
        )
        thread = threading.Thread(target=travail, daemon=True)
        try:
            with mock.patch.object(subprocess, "Popen", PopenRetarde):
                thread_arret.start()
                thread.start()
                thread.join(10)
                thread_arret.join(DELAI)

            self.assertFalse(
                thread.is_alive(),
                "l'arrêt demandé pendant le démarrage n'a pas interrompu l'exécution",
            )
            self.assertFalse(thread_arret.is_alive())
            self.assertFalse(executeur.en_cours)
            self.assertNotEqual(resultat["commande"].code, 0)
            self.assertEqual(len(processus_crees), 1)
            self.assertIsNotNone(
                processus_crees[0].poll(), "processus encore vivant après l'arrêt"
            )
        finally:
            for processus in processus_crees:
                if processus.poll() is None:
                    processus.kill()
                    processus.wait()
            thread.join(DELAI)
            thread_arret.join(DELAI)

    def test_commandes_uv_et_sondes_isolees(self) -> None:
        executeur = ExecuteurCibleServeur()
        service = self.service(executeur=executeur)

        self.lancer_installation(service)

        commande_venv, commande_sonde = executeur.commandes[0], executeur.commandes[1]
        self.assertIn("--clear", commande_venv)
        self.assertNotIn(
            "--force",
            commande_venv,
            "`--force` permettrait d'effacer un dossier qui n'est pas un venv",
        )
        self.assertEqual(commande_sonde[1:3], ["-I", "-c"])

    def test_commande_sync_refuse_toute_compilation(self) -> None:
        executeur = ExecuteurEnregistreur()
        service = self.service(executeur=executeur)

        instantane = self.lancer_installation(service)

        self.assertEqual(instantane.etat, ETAT_TERMINEE, instantane.erreur)
        synchronisations = [
            commande
            for commande in executeur.commandes
            if commande[:3] == ["uv", "pip", "sync"]
        ]
        self.assertEqual(len(synchronisations), 1)
        commande = synchronisations[0]
        self.assertIn(
            "--no-build",
            commande,
            "sans `--no-build`, uv pourrait compiler une sdist à l'installation",
        )
        self.assertIn("--python", commande)
        self.assertEqual(
            commande[commande.index("--python") + 1],
            str(chemin_interpreteur(self.dossier_moteur()).absolute()),
        )
        self.assertEqual(
            commande[-1],
            str((self.racine / "requirements" / "engine-test.txt").resolve()),
        )


class PageMoteursWebTest(SocleMoteurs):
    """Page des moteurs, journal et demandes d'installation via Flask."""

    def application(self, service: InstallationMoteurs | None = None):
        app = create_app(
            ConfigApplication(port=PORT_TEST, dossier_data=self.donnees),
            ServicesApplication(
                creneau=self.creneau, moteurs=service or self.service()
            ),
        )
        client = app.test_client()
        jeton = app.extensions[NOM_CHAMP_JETON]

        def get(chemin: str):
            return client.get(chemin, base_url=BASE_URL)

        def post(chemin: str, jeton_envoye: str | None = None):
            return client.post(
                chemin,
                data={NOM_CHAMP_JETON: jeton if jeton_envoye is None else jeton_envoye},
                base_url=BASE_URL,
            )

        return get, post

    def test_page_moteurs_affiche_les_quatre_etats_et_le_formulaire(self) -> None:
        factice = creer_registre_fourni().obtenir("factice")
        self.registre = self.registre_avec(
            declaration_test("engine-pret"),
            declaration_test("engine-echec"),
            declaration_test("engine-non-installe"),
            declaration_test("engine-en-installation"),
        )
        self.registre.enregistrer(factice)
        self.ecrire_marqueur("engine-pret")
        self.dossier_moteur("engine-echec").mkdir(parents=True)

        liberation = threading.Event()
        self.addCleanup(liberation.set)
        self.creneau.demarrer(
            TYPE_INSTALLATION, lambda travailleur: liberation.wait(DELAI),
            cible="engine-en-installation",
        )

        get, _ = self.application()
        reponse = get("/moteurs")
        corps = html.unescape(reponse.get_data(as_text=True))

        self.assertEqual(reponse.status_code, 200)
        for libelle in ("non installé", "installation en cours", "prêt", "échec"):
            self.assertIn(libelle, corps)
        self.assertIn("FACTICE", corps)
        self.assertIn("sys (version non disponible)", corps)
        self.assertIn(
            f'name="{NOM_CHAMP_JETON}"', get("/moteurs").get_data(as_text=True)
        )
        self.assertIn('action="/moteurs/engine-non-installe/installer"', corps)
        self.assertIn('action="/moteurs/engine-echec/installer"', corps)
        self.assertNotIn('action="/moteurs/factice/installer"', corps)
        self.assertIn('href="/moteurs/engine-pret/journal"', corps)
        self.assertNotIn("<script", corps)

        self.creneau.arreter(0.05)
        thread = self.creneau.thread_travailleur
        liberation.set()
        if thread is not None:
            thread.join(DELAI)

    def test_page_moteurs_sans_effet_de_bord(self) -> None:
        get, _ = self.application()
        reponse = get("/moteurs")

        self.assertEqual(reponse.status_code, 200)
        self.assertFalse(self.donnees.exists())

    def test_marqueur_corrompu_donne_echec_et_page_200(self) -> None:
        self.dossier_moteur().mkdir(parents=True)
        self.marqueur().write_bytes(b"\xff\xfe{")
        get, _ = self.application()

        etat = self.etat(self.service())
        self.assertEqual(etat.etat, ETAT_ECHEC)
        self.assertIn("Marqueur illisible", etat.note or "")

        reponse = get("/moteurs")
        corps = html.unescape(reponse.get_data(as_text=True))

        self.assertEqual(reponse.status_code, 200)
        self.assertIn("Moteur de test engine-test", corps)
        self.assertIn("échec", corps)

    def test_journal_est_echappe(self) -> None:
        self.journal().parent.mkdir(parents=True, exist_ok=True)
        self.journal().write_text(
            "2026-10-25 <script>alert(1)</script> & suite\n", encoding="utf-8"
        )
        get, _ = self.application()
        reponse = get("/moteurs/engine-test/journal")
        corps = reponse.get_data(as_text=True)

        self.assertEqual(reponse.status_code, 200)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt; &amp; suite", corps)
        self.assertNotIn("<script", corps)
        self.assertNotIn("style=", corps)

    def test_post_installation_sans_jeton_refuse_sans_io(self) -> None:
        app = create_app(
            ConfigApplication(port=PORT_TEST, dossier_data=self.donnees),
            ServicesApplication(creneau=self.creneau, moteurs=self.service()),
        )
        reponse = app.test_client().post(
            "/moteurs/engine-test/installer", data={"x": "1"}, base_url=BASE_URL
        )

        self.assertEqual(reponse.status_code, 403)
        self.assertEqual(self.creneau.instantane().etat, "libre")
        self.assertFalse(self.donnees.exists())

    def test_post_identifiant_inconnu_404_sans_io(self) -> None:
        get, post = self.application()

        reponse = post("/moteurs/inconnu/installer")

        self.assertEqual(reponse.status_code, 404)
        self.assertEqual(self.creneau.instantane().etat, "libre")
        self.assertFalse(self.donnees.exists())

    def test_post_factice_ou_verrou_absent_refuse_en_403(self) -> None:
        self.registre = RegistreMoteurs()
        self.registre.enregistrer(declaration_test("engine-sans-verrou"))
        self.registre.enregistrer(creer_registre_fourni().obtenir("factice"))
        get, post = self.application()

        for identifiant in ("factice", "engine-sans-verrou"):
            with self.subTest(identifiant=identifiant):
                reponse = post(f"/moteurs/{identifiant}/installer")
                self.assertEqual(reponse.status_code, 403)
        self.assertEqual(self.creneau.instantane().etat, "libre")
        self.assertFalse(self.donnees.exists())

    def test_post_pendant_une_operation_refuse_en_409(self) -> None:
        liberation = threading.Event()
        self.addCleanup(liberation.set)
        self.creneau.demarrer(
            TYPE_INSTALLATION, lambda travailleur: liberation.wait(DELAI),
            cible="engine-test",
        )
        get, post = self.application()

        reponse = post("/moteurs/engine-test/installer")

        self.assertEqual(reponse.status_code, 409)
        self.assertFalse(self.marqueur().exists())
        liberation.set()
        thread = self.creneau.thread_travailleur
        if thread is not None:
            thread.join(DELAI)

    def test_post_apres_arret_refuse_en_503(self) -> None:
        self.creneau.arreter(0.05)
        get, post = self.application()

        reponse = post("/moteurs/engine-test/installer")

        self.assertEqual(reponse.status_code, 503)
        self.assertFalse(self.donnees.exists())

    def test_installation_autorisee_redirige_et_devient_prete(self) -> None:
        get, post = self.application()
        page = get("/moteurs").get_data(as_text=True)
        jeton = page.split(f'name="{NOM_CHAMP_JETON}" value="', 1)[1].split('"', 1)[0]

        reponse = post("/moteurs/engine-test/installer", jeton_envoye=jeton)

        self.assertEqual(reponse.status_code, 303)
        self.assertEqual(reponse.headers["Location"], "/operation")
        thread = self.creneau.thread_travailleur
        self.assertIsNotNone(thread)
        thread.join(DELAI)
        self.assertFalse(thread.is_alive())
        self.assertTrue(self.marqueur().is_file())

        corps = get("/moteurs").get_data(as_text=True)
        self.assertIn("prêt", corps)
        self.assertIn("Moteur de test engine-test", corps)
        self.assertNotIn("installation en cours", corps)


class InterpreteurMoteurTest(SocleMoteurs):
    """Interpréteur du venv exposé pour le lancement d'une exécution (tâche 6.3)."""

    def test_interpreteur_du_venv_est_rendu_quand_il_existe(self) -> None:
        service = self.service()
        attendu = chemin_interpreteur(self.dossier_moteur())
        attendu.parent.mkdir(parents=True, exist_ok=True)
        attendu.write_text("", encoding="utf-8")

        self.assertEqual(service.interpreteur("engine-test"), attendu.absolute())

    def test_interpreteur_absent_est_refuse(self) -> None:
        service = self.service()
        self.dossier_moteur().mkdir(parents=True, exist_ok=True)

        with self.assertRaises(InstallationEchouee):
            service.interpreteur("engine-test")

    def test_interpreteur_du_moteur_factice_est_indisponible(self) -> None:
        service = InstallationMoteurs(
            self.donnees,
            creer_registre_fourni(),
            self.creneau,
            racine_projet=self.racine,
            environ=ENVIRON_UV,
        )

        with self.assertRaises(InstallationIndisponible):
            service.interpreteur("factice")


if __name__ == "__main__":
    unittest.main()
