"""Installation explicite des moteurs : environnements isolés, marqueur et états.

Ce service ne touche jamais au réseau pour les modèles et n'installe aucun
moteur au démarrage : seule une demande explicite de l'utilisateur, exécutée
dans le créneau unique d'opération longue, lance `uv venv` puis `uv pip sync`.
Les déclarations des trois moteurs réels n'ont pas de verrou validé sur PC à ce
stade : leur installation reste indisponible et la page l'explique. Le moteur
factice est, lui, prêt sans installation puisqu'il utilise l'interpréteur du
serveur.

Contrat d'installation (design D4) :

1. `uv venv --python 3.12 --clear data/engines/<moteur>` (sans `--force` :
   l'environnement du moteur est le seul dossier que l'installation peut vider) ;
2. `uv pip sync --python <interpréteur-du-venv> requirements/<moteur>.txt` ;
3. contrôle d'import dans le venv avec ses propres modules déclarés, par un
   interpréteur isolé (`-I` : ni `PYTHONPATH`, ni site utilisateur, ni dossier
   courant) comme pour la sonde de préfixe ;
4. publication atomique du marqueur `installation.json` (empreinte SHA-256 du
   verrou, date, versions réellement lues) sous `Travailleur.publier_pret`.

Un marqueur valide seul rend le moteur prêt. Sans marqueur, avec une empreinte
de verrou différente, un marqueur incohérent, illisible (octets non UTF-8 ou
JSON invalide) ou un interpréteur absent, l'état est `echec` : jamais `pret`.
Avant toute tentative de resynchronisation, le marqueur existant est supprimé,
et un échec, une interruption ou un arrêt du serveur laisse le moteur non prêt.

L'environnement est créé dans `data/engines/<moteur>` ; le journal d'installation
est écrit à côté (`data/engines/<moteur>.installation.log`) pour survivre à un
`uv venv --clear`. Ni le journal ni le marqueur ne recopient l'environnement du
processus : seules les lignes de sortie d'uv et du contrôle sont conservées.

La protection commune des JSON vit dans `transcription_bench.stockage`. Ordre
des verrous : le verrou du créneau peut être tenu pendant l'écriture du marqueur,
jamais l'inverse. L'arrêt du sous-processus d'installation, y compris de son
groupe (`transcription_bench.processus`), est fourni ici ; la supervision des
signaux du serveur et l'enchaînement du nettoyage vivent dans
`transcription_bench.supervision` (tâche 6.6).
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import threading
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path

from engines.declarations import DeclarationAdaptateur
from engines.registre import RegistreMoteurs
from transcription_bench.operations import (
    ETAT_EN_COURS,
    TYPE_INSTALLATION,
    CreneauOperations,
    OperationEchouee,
    ServiceArrete,
    Travailleur,
    horodatage_iso,
)
from transcription_bench.paths import (
    NOM_DOSSIER_MOTEURS,
    RACINE_PROJET,
    ValeurRefusee,
    resoudre_dans_racine,
)
from transcription_bench.processus import (
    arreter_descendants,
    arreter_groupe,
    descendants,
    options_groupe,
)
from transcription_bench.stockage import (
    VERROU_STOCKAGE,
    JsonInvalide,
    ecrire_json_atomique,
    lire_json,
)

ETAT_NON_INSTALLE = "non-installe"
ETAT_EN_INSTALLATION = "en-installation"
ETAT_PRET = "pret"
ETAT_ECHEC = "echec"

LIBELLES_ETATS_MOTEUR = {
    ETAT_NON_INSTALLE: "non installé",
    ETAT_EN_INSTALLATION: "installation en cours",
    ETAT_PRET: "prêt",
    ETAT_ECHEC: "échec",
}

NOM_MARQUEUR = "installation.json"
SUFFIXE_JOURNAL = ".installation.log"

DELAI_CONTROLE_IMPORT = 120.0
DELAI_SONDAGE_INTERPRETEUR = 30.0

CODE_PREFIXE_INTERPRETEUR = "import sys\nprint(sys.prefix)"
DELAI_ARRET_PROCESSUS = 5.0

CODE_CONTROLE_IMPORT = """
import importlib
import importlib.metadata
import json
import sys

modules = json.loads(sys.argv[1])
versions = {}
for nom in modules:
    importlib.import_module(nom)
    try:
        versions[nom] = importlib.metadata.version(nom)
    except importlib.metadata.PackageNotFoundError:
        versions[nom] = None
print(json.dumps({"modules": versions}, ensure_ascii=False))
"""


class InstallationIndisponible(RuntimeError):
    """Moteur non installable : factice, identifiant inconnu ou verrou absent."""


class InstallationEchouee(OperationEchouee):
    """Étape d'installation en échec : le moteur ne doit pas devenir prêt.

    Hérite d'`OperationEchouee` : un échec prévu est consigné par le créneau
    avec son message seul, sans pile d'appels complète (comme
    `ExecutionEchouee`). La pile n'apporterait rien pour un code de sortie uv
    non nul ou un import manquant, et elle noierait le journal.
    """


@dataclass(frozen=True)
class EtatMoteur:
    """État affichable d'un moteur, sans action ni accès réseau.

    `versions` contient des couples (module, version ou `None`) : aucune version
    n'est inventée, et l'absence de métadonnée de distribution reste affichée
    comme telle. `installable` indique seulement qu'une installation explicite
    peut être demandée depuis l'interface.
    """

    identifiant: str
    nom: str
    etat: str
    factice: bool = False
    installable: bool = False
    note: str | None = None
    date_installation: str | None = None
    versions: tuple[tuple[str, str | None], ...] = ()


@dataclass(frozen=True)
class ResultatCommande:
    """Code de sortie et sortie complète (stdout et stderr fusionnés)."""

    code: int
    sortie: str


class ExecuteurCommandes:
    """Exécuteur minimal, remplaçable par les tests sans effet de bord.

    `arreter` doit terminer le sous-processus éventuellement en cours, y compris
    son groupe ou son arborescence, et rester idempotent : la supervision d'arrêt
    du serveur (tâche 6.6) l'appelle au moment du nettoyage.
    """

    def executer(
        self,
        arguments: list[str],
        *,
        env: Mapping[str, str],
        journaliser: Callable[[str], None],
        delai: float | None = None,
    ) -> ResultatCommande:
        raise NotImplementedError

    def arreter(self) -> None:
        """Termine le sous-processus en cours, sans lever d'erreur."""


class ExecuteurSubprocess(ExecuteurCommandes):
    """Exécuteur réel avec nettoyage borné du sous-processus et de son groupe.

    Le contrôle d'arrêt, `Popen` et l'enregistrement du processus se font sous
    le même verrou court : `arreter` voit donc toujours un processus déjà admis,
    jamais un démarrage encore en cours qu'il laisserait ensuite s'exécuter. La
    commande est lancée dans son propre groupe (`options_groupe`) et `arreter`
    signale ce groupe : `uv` et les processus qu'il aurait lancés ne survivent
    pas à l'arrêt du serveur (tâche 6.6). Les tuyaux sont toujours fermés et le
    processus est toujours attendu, y compris après une erreur ou un délai
    dépassé, afin de ne pas laisser de processus orphelin ni de descripteur
    ouvert.
    """

    def __init__(self) -> None:
        self._verrou = threading.Lock()
        self._processus: subprocess.Popen[str] | None = None
        self._arrete = False

    @property
    def en_cours(self) -> bool:
        """Vrai si une commande est actuellement suivie."""
        with self._verrou:
            return self._processus is not None

    def executer(
        self,
        arguments: list[str],
        *,
        env: Mapping[str, str],
        journaliser: Callable[[str], None],
        delai: float | None = None,
    ) -> ResultatCommande:
        environ = dict(env)
        with self._verrou:
            if self._arrete:
                raise InstallationEchouee("installation arrêtée : commande non lancée")
            processus = subprocess.Popen(
                arguments,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                env=environ,
                bufsize=1,
                **options_groupe(),
            )
            self._processus = processus
        morceaux: list[str] = []
        try:
            if delai is None:
                if processus.stdout is not None:
                    for ligne in processus.stdout:
                        ligne = ligne.rstrip("\r\n")
                        morceaux.append(ligne)
                        journaliser(ligne)
                code = processus.wait()
            else:
                sortie, _ = processus.communicate(timeout=delai)
                for ligne in sortie.splitlines():
                    morceaux.append(ligne)
                    journaliser(ligne)
                code = processus.returncode
        except subprocess.TimeoutExpired:
            arreter_groupe(processus, force=True)
            processus.wait()
            journaliser("Délai dépassé : commande arrêtée.")
            code = -1
        finally:
            with self._verrou:
                self._processus = None
            if processus.poll() is None:
                arreter_groupe(processus, force=True)
                processus.wait()
            if processus.stdout is not None:
                processus.stdout.close()
        return ResultatCommande(code=code, sortie="\n".join(morceaux))

    def arreter(self) -> None:
        """Termine le groupe du sous-processus en cours, avec des délais bornés.

        La descendance est relevée avant le signal, puis attendue et tuée si
        elle survit à `SIGTERM` : un `uv` qui aurait lancé un sous-traitant ne
        doit pas en laisser un orphelin, et le groupe n'est plus signalable dès
        que le processus principal a disparu.
        """
        with self._verrou:
            self._arrete = True
            processus = self._processus
        if processus is None or processus.poll() is not None:
            return
        arbre = descendants(processus.pid)
        arreter_groupe(processus)
        try:
            processus.wait(DELAI_ARRET_PROCESSUS)
        except subprocess.TimeoutExpired:
            arreter_groupe(processus, force=True)
            try:
                processus.wait(DELAI_ARRET_PROCESSUS)
            except subprocess.TimeoutExpired:
                # Un processus insensible au forçage reste signalé par son
                # absence de sortie ; l'appelant garde le créneau occupé.
                arreter_descendants(arbre, DELAI_ARRET_PROCESSUS)
                return
        arreter_descendants(arbre, DELAI_ARRET_PROCESSUS)


def empreinte_fichier(chemin: Path) -> str:
    """Empreinte SHA-256 d'un fichier de verrou, en hexadécimal."""
    return hashlib.sha256(Path(chemin).read_bytes()).hexdigest()


def _resume_sortie(sortie: str) -> str:
    """Dernière ligne non vide d'une sortie, pour un message d'erreur court."""
    for ligne in reversed(sortie.splitlines()):
        if ligne.strip():
            return ligne.strip()
    return "aucune sortie"


def _extraire_versions(sortie: str) -> dict[str, str | None]:
    """Extrait l'objet JSON du contrôle d'import, sans dépendre de sa position."""
    for ligne in reversed(sortie.splitlines()):
        if not ligne.strip().startswith("{"):
            continue
        try:
            donnees = json.loads(ligne)
        except json.JSONDecodeError:
            continue
        if isinstance(donnees, dict) and isinstance(donnees.get("modules"), dict):
            return donnees["modules"]
    raise InstallationEchouee("contrôle d'import : réponse JSON absente ou invalide")


class InstallationMoteurs:
    """Service d'inventaire et d'installation des moteurs déclarés.

    Le service est construit au démarrage sans aucune E/S ; chaque lecture
    d'état consulte les fichiers sous `data/`. Les identifiants viennent toujours
    du registre et les chemins sont résolus avec les helpers contrôlés du projet.
    """

    def __init__(
        self,
        dossier_data: Path | str,
        registre: RegistreMoteurs,
        creneau: CreneauOperations,
        *,
        racine_projet: Path | str = RACINE_PROJET,
        executeur: ExecuteurCommandes | None = None,
        environ: Mapping[str, str] | None = None,
    ) -> None:
        self._donnees = Path(dossier_data)
        self._registre = registre
        self._creneau = creneau
        self._racine = Path(racine_projet)
        self._executeur = executeur or ExecuteurSubprocess()
        self._environ = dict(environ or {})

    def inventaire(self) -> tuple[EtatMoteur, ...]:
        """États de tous les moteurs du registre, dans leur ordre d'enregistrement."""
        instantane = self._creneau.instantane()
        cible_installation = (
            instantane.cible
            if instantane.etat == ETAT_EN_COURS
            and instantane.type_operation == TYPE_INSTALLATION
            else None
        )
        return tuple(
            self._etat_moteur(declaration, cible_installation)
            for declaration in self._registre.lister()
        )

    def declaration(self, identifiant: str) -> DeclarationAdaptateur:
        """Déclaration d'un moteur connu, ou `MoteurInconnu`."""
        return self._registre.obtenir(identifiant)

    def verifier_installable(self, identifiant: str) -> DeclarationAdaptateur:
        """Contrôle sans effet de bord qu'une installation peut être demandée.

        Lève `MoteurInconnu` pour un identifiant absent, `InstallationIndisponible`
        pour le moteur factice ou un verrou non validé, et `ValeurRefusee` pour un
        chemin d'environnement dangereux, avant toute création de fichier.
        """
        declaration = self._registre.obtenir(identifiant)
        if declaration.factice or declaration.fichier_requirements is None:
            raise InstallationIndisponible(
                "moteur factice : aucune installation n'est nécessaire ni possible"
            )
        verrou = self.chemin_verrou(declaration)
        if not verrou.is_file():
            raise InstallationIndisponible(
                "verrou de dépendances non validé sur PC (jalon 0) : "
                "installation indisponible"
            )
        self.dossier_moteur(identifiant)
        return declaration

    def chemin_verrou(self, declaration: DeclarationAdaptateur) -> Path:
        """Chemin contrôlé du verrou de dépendances déclaré."""
        if declaration.fichier_requirements is None:
            raise InstallationIndisponible(
                f"aucun verrou de dépendances pour {declaration.identifiant!r}"
            )
        return resoudre_dans_racine(self._racine, declaration.fichier_requirements)

    def dossier_moteur(self, identifiant: str) -> Path:
        """Environnement du moteur sous `data/engines`, hors de tout lien sortant."""
        self._registre.obtenir(identifiant)
        dossier = resoudre_dans_racine(self._dossier_engines(), identifiant)
        if dossier.is_symlink():
            raise ValeurRefusee(
                f"environnement moteur symbolique refusé : {identifiant!r}"
            )
        return dossier

    def interpreteur(self, identifiant: str) -> Path:
        """Interpréteur du venv d'un moteur réel, pour lancer une exécution.

        Le chemin renvoyé est celui du venv (jamais sa cible résolue, qui
        perdrait l'environnement). Le moteur factice n'a pas de venv : son
        lancement utilise l'interpréteur du serveur et `InstallationIndisponible`
        est levée ici. Un état d'installation n'est pas vérifié : l'appelant
        contrôle d'abord `inventaire()` (tâche 6.3).
        """
        declaration = self._registre.obtenir(identifiant)
        if declaration.factice:
            raise InstallationIndisponible(
                "moteur factice : aucun environnement propre, interpréteur du "
                "serveur attendu"
            )
        return self._chemin_interpreteur(identifiant, self.dossier_moteur(identifiant))

    def chemin_journal(self, identifiant: str) -> Path:
        """Journal d'installation, à côté de l'environnement du moteur."""
        self._registre.obtenir(identifiant)
        return resoudre_dans_racine(
            self._dossier_engines(), f"{identifiant}{SUFFIXE_JOURNAL}"
        )

    def lire_journal(self, identifiant: str, limite: int = 2000) -> tuple[str, ...]:
        """Dernières lignes du journal d'installation, ou vide s'il n'existe pas."""
        declaration = self._registre.obtenir(identifiant)
        if declaration.factice:
            return ()
        try:
            texte = self.chemin_journal(identifiant).read_text(
                encoding="utf-8", errors="replace"
            )
        except FileNotFoundError:
            return ()
        except OSError as erreur:
            return (f"Journal illisible : {type(erreur).__name__}.",)
        return tuple(texte.splitlines()[-limite:])

    def installer(self, identifiant: str, travailleur: Travailleur) -> None:
        """Installe un moteur dans le créneau, journalise et publie le marqueur.

        Cette méthode s'exécute dans le thread de fond du créneau. Elle ne publie
        le marqueur prêt que par `Travailleur.publier_pret`, donc jamais après le
        passage à l'arrêt, même si une commande uv se termine ensuite.
        """
        declaration = self.verifier_installable(identifiant)
        verrou = self.chemin_verrou(declaration)
        dossier = self.dossier_moteur(identifiant)

        def journaliser(message: str) -> None:
            self._ajouter_journal(identifiant, message)
            travailleur.journaliser(message)

        try:
            empreinte = empreinte_fichier(verrou)
            self._supprimer_marqueur(dossier / NOM_MARQUEUR)
            journaliser(f"Installation de {declaration.nom} depuis {verrou.name}.")
            environ = self._environ_effectif()

            journaliser("Création de l'environnement Python 3.12.")
            resultat = self._executeur.executer(
                [
                    "uv",
                    "venv",
                    "--no-project",
                    "--python",
                    "3.12",
                    "--clear",
                    str(dossier),
                ],
                env=environ,
                journaliser=journaliser,
            )
            if resultat.code != 0:
                raise InstallationEchouee(
                    f"uv venv a échoué (code {resultat.code}) : "
                    f"{_resume_sortie(resultat.sortie)}"
                )

            interpreteur = self._interpreteur_verifie(
                identifiant, dossier, environ, journaliser
            )
            journaliser("Synchronisation des dépendances depuis le verrou.")
            resultat = self._executeur.executer(
                [
                    "uv",
                    "pip",
                    "sync",
                    "--python",
                    str(interpreteur),
                    "--allow-empty-requirements",
                    str(verrou),
                ],
                env=environ,
                journaliser=journaliser,
            )
            if resultat.code != 0:
                raise InstallationEchouee(
                    f"uv pip sync a échoué (code {resultat.code}) : "
                    f"{_resume_sortie(resultat.sortie)}"
                )

            journaliser("Contrôle d'import dans l'environnement du moteur.")
            versions = self._controler_imports(
                interpreteur, declaration.modules_verification, environ, journaliser
            )
            marqueur = {
                "moteur": identifiant,
                "empreinte_verrou": empreinte,
                "date": horodatage_iso(),
                "versions": versions,
            }
            try:
                travailleur.publier_pret(
                    lambda: ecrire_json_atomique(dossier / NOM_MARQUEUR, marqueur)
                )
            except ServiceArrete:
                journaliser("Marqueur prêt non publié : arrêt du serveur demandé.")
                return
            journaliser("Moteur prêt : marqueur d'installation publié.")
        except (InstallationEchouee, InstallationIndisponible, ValeurRefusee, OSError) as erreur:
            journaliser(f"Échec : {erreur}")
            raise

    def arreter(self) -> None:
        """Demande l'arrêt du sous-processus d'installation éventuellement en cours."""
        self._executeur.arreter()

    def _etat_moteur(
        self, declaration: DeclarationAdaptateur, cible_installation: str | None
    ) -> EtatMoteur:
        identifiant = declaration.identifiant
        if declaration.factice:
            return EtatMoteur(
                identifiant=identifiant,
                nom=declaration.nom,
                etat=ETAT_PRET,
                factice=True,
                installable=False,
                note=(
                    "Moteur factice : aucune installation, aucun modèle et aucune "
                    "inférence réelle. Textes et mesures sont simulés et ne "
                    "représentent aucun PC."
                ),
            )
        try:
            verrou = self.chemin_verrou(declaration)
        except (InstallationIndisponible, ValeurRefusee, OSError) as erreur:
            return self._etat_simple(declaration, ETAT_ECHEC, str(erreur), False)
        if not verrou.is_file():
            return EtatMoteur(
                identifiant=identifiant,
                nom=declaration.nom,
                etat=ETAT_NON_INSTALLE,
                installable=False,
                note=(
                    "Verrou de dépendances non validé sur PC (jalon 0) : "
                    "installation indisponible depuis le serveur de développement."
                ),
            )
        try:
            dossier = self.dossier_moteur(identifiant)
        except (ValeurRefusee, OSError) as erreur:
            return self._etat_simple(declaration, ETAT_ECHEC, str(erreur), False)

        if cible_installation == identifiant:
            return EtatMoteur(
                identifiant=identifiant,
                nom=declaration.nom,
                etat=ETAT_EN_INSTALLATION,
                installable=False,
                note="Installation en cours dans le créneau d'opération.",
            )
        if not dossier.exists():
            if self._journal_existe(identifiant):
                return EtatMoteur(
                    identifiant=identifiant,
                    nom=declaration.nom,
                    etat=ETAT_ECHEC,
                    installable=True,
                    note=(
                        "Environnement absent après une tentative d'installation : "
                        "réinstallation explicite nécessaire."
                    ),
                )
            return EtatMoteur(
                identifiant=identifiant,
                nom=declaration.nom,
                etat=ETAT_NON_INSTALLE,
                installable=True,
            )

        marqueur = dossier / NOM_MARQUEUR
        if not marqueur.exists():
            return EtatMoteur(
                identifiant=identifiant,
                nom=declaration.nom,
                etat=ETAT_ECHEC,
                installable=True,
                note=(
                    "Environnement sans marqueur d'installation valide : "
                    "réinstallation explicite nécessaire."
                ),
            )
        try:
            empreinte = empreinte_fichier(verrou)
            donnees = lire_json(marqueur)
        except (OSError, JsonInvalide) as erreur:
            return self._etat_simple(
                declaration, ETAT_ECHEC, f"Marqueur illisible : {erreur}", True
            )
        if not self._marqueur_valide(donnees, declaration, empreinte):
            return EtatMoteur(
                identifiant=identifiant,
                nom=declaration.nom,
                etat=ETAT_ECHEC,
                installable=True,
                note=(
                    "Marqueur d'installation incohérent avec le verrou ou la "
                    "déclaration : réinstallation explicite nécessaire."
                ),
            )
        try:
            self._chemin_interpreteur(identifiant, dossier)
        except (InstallationEchouee, ValeurRefusee, OSError) as erreur:
            return self._etat_simple(declaration, ETAT_ECHEC, str(erreur), True)
        return EtatMoteur(
            identifiant=identifiant,
            nom=declaration.nom,
            etat=ETAT_PRET,
            installable=True,
            date_installation=donnees["date"],
            versions=tuple(sorted(donnees["versions"].items())),
        )

    def _etat_simple(
        self,
        declaration: DeclarationAdaptateur,
        etat: str,
        note: str,
        installable: bool,
    ) -> EtatMoteur:
        return EtatMoteur(
            identifiant=declaration.identifiant,
            nom=declaration.nom,
            etat=etat,
            installable=installable,
            note=note,
        )

    def _marqueur_valide(
        self,
        donnees: object,
        declaration: DeclarationAdaptateur,
        empreinte: str,
    ) -> bool:
        if not isinstance(donnees, dict):
            return False
        if donnees.get("moteur") != declaration.identifiant:
            return False
        if donnees.get("empreinte_verrou") != empreinte:
            return False
        date = donnees.get("date")
        if not isinstance(date, str) or not date:
            return False
        versions = donnees.get("versions")
        if not isinstance(versions, dict):
            return False
        if set(versions) != set(declaration.modules_verification):
            return False
        return all(
            isinstance(nom, str) and (version is None or isinstance(version, str))
            for nom, version in versions.items()
        )

    def _chemin_interpreteur(self, identifiant: str, dossier: Path) -> Path:
        """Chemin de l'interpréteur du venv, sans résoudre son lien final.

        Un venv POSIX expose normalement `bin/python` comme lien vers
        l'interpréteur de base de Python : la cible finale n'est pas le venv et
        ne permet donc pas de vérifier le confinement. Le chemin renvoyé est
        celui du venv, utilisé par `uv pip sync --python`.
        """
        dossier = self.dossier_moteur(identifiant)
        if dossier.is_symlink():
            raise InstallationEchouee("environnement moteur symbolique refusé")
        if os.name == "nt":
            candidat = dossier / "Scripts" / "python.exe"
        else:
            candidat = dossier / "bin" / "python"
        if not candidat.is_file():
            raise InstallationEchouee(
                "interpréteur absent de l'environnement créé : synchronisation refusée"
            )
        return candidat.absolute()

    def _interpreteur_verifie(
        self,
        identifiant: str,
        dossier: Path,
        environ: Mapping[str, str],
        journaliser: Callable[[str], None],
    ) -> Path:
        """Vérifie avant `uv pip sync` que l'interpréteur cible bien ce venv.

        La sonde exécute l'interpréteur du venv avec `-I` : `PYTHONPATH`,
        `PYTHONHOME`, le site utilisateur et le dossier courant sont ignorés,
        alors que `pyvenv.cfg` continue de définir `sys.prefix`. Elle compare
        ensuite ce préfixe au dossier de l'environnement : une cible qui
        pointerait vers le venv du serveur, le Python système ou un autre venv
        est ainsi refusée avant la synchronisation, sans analyse des liens.
        """
        candidat = self._chemin_interpreteur(identifiant, dossier)
        resultat = self._executeur.executer(
            [str(candidat), "-I", "-c", CODE_PREFIXE_INTERPRETEUR],
            env=environ,
            journaliser=journaliser,
            delai=DELAI_SONDAGE_INTERPRETEUR,
        )
        prefixe = _resume_sortie(resultat.sortie) if resultat.code == 0 else ""
        if not prefixe:
            raise InstallationEchouee(
                "sonde de l'interpréteur en échec : synchronisation refusée"
            )
        try:
            cible = Path(prefixe).resolve()
            attendu = dossier.resolve()
        except (OSError, RuntimeError) as erreur:
            raise InstallationEchouee(
                f"préfixe de l'interpréteur non résoluble : {type(erreur).__name__}"
            ) from None
        if os.path.normcase(str(cible)) != os.path.normcase(str(attendu)):
            raise InstallationEchouee(
                "cible de l'interpréteur différente de l'environnement du "
                "moteur : synchronisation refusée"
            )
        return candidat

    def _controler_imports(
        self,
        interpreteur: Path,
        modules: tuple[str, ...],
        environ: Mapping[str, str],
        journaliser: Callable[[str], None],
    ) -> dict[str, str | None]:
        """Contrôle les imports déclarés dans le venv, avec un interpréteur isolé.

        `-I` élimine `PYTHONPATH`, `PYTHONHOME`, le site utilisateur et le
        dossier courant : un module trouvé hors des dépendances synchronisées ne
        peut pas faire réussir le contrôle.
        """
        if not modules:
            raise InstallationEchouee(
                "aucun module de vérification déclaré : contrôle impossible"
            )
        resultat = self._executeur.executer(
            [
                str(interpreteur),
                "-I",
                "-c",
                CODE_CONTROLE_IMPORT,
                json.dumps(list(modules)),
            ],
            env=environ,
            journaliser=journaliser,
            delai=DELAI_CONTROLE_IMPORT,
        )
        if resultat.code != 0:
            raise InstallationEchouee(
                "contrôle d'import échoué dans l'environnement du moteur "
                f"(code {resultat.code}) : {_resume_sortie(resultat.sortie)}"
            )
        versions = _extraire_versions(resultat.sortie)
        if set(versions) != set(modules):
            raise InstallationEchouee(
                "contrôle d'import incohérent : modules vérifiés différents de la "
                "déclaration"
            )
        return versions

    def _dossier_engines(self) -> Path:
        return self._donnees / NOM_DOSSIER_MOTEURS

    def _environ_effectif(self) -> dict[str, str]:
        """Environnement du sous-processus, sans environnement virtuel courant.

        `VIRTUAL_ENV` et le dossier `bin`/`Scripts` du serveur sont retirés, et
        `uv venv` reçoit `--no-project` : l'environnement du moteur ne doit pas
        être dérivé de celui du serveur, ni découvrir le projet uv courant. Le
        dossier du serveur n'est retiré du `PATH` que si le serveur tourne
        lui-même dans un venv (`sys.prefix` différent de `sys.base_prefix`) :
        hors venv, aucun chemin système ne doit disparaître. Les surcharges du
        service (par exemple les options hors ligne des tests) sont appliquées
        avant ce nettoyage.
        """
        environ = dict(os.environ)
        environ.update(self._environ)
        environ.pop("VIRTUAL_ENV", None)
        environ.pop("VIRTUAL_ENV_PROMPT", None)
        prefixe_serveur = Path(sys.prefix).resolve()
        filtrer_prefixe = Path(sys.prefix) != Path(sys.base_prefix)
        entrees: list[str] = []
        for entree in environ.get("PATH", "").split(os.pathsep):
            if not entree:
                continue
            try:
                resolu = Path(entree).resolve()
            except (OSError, RuntimeError):
                entrees.append(entree)
                continue
            if filtrer_prefixe and resolu.is_relative_to(prefixe_serveur):
                continue
            entrees.append(entree)
        environ["PATH"] = os.pathsep.join(entrees)
        return environ

    def _journal_existe(self, identifiant: str) -> bool:
        try:
            return self.chemin_journal(identifiant).is_file()
        except (OSError, ValeurRefusee):
            return False

    def _supprimer_marqueur(self, marqueur: Path) -> None:
        with VERROU_STOCKAGE:
            try:
                marqueur.unlink()
            except FileNotFoundError:
                pass

    def _ajouter_journal(self, identifiant: str, message: str) -> None:
        """Ajoute une ligne au journal local du moteur, sans échouer l'installation."""
        try:
            chemin = self.chemin_journal(identifiant)
            chemin.parent.mkdir(parents=True, exist_ok=True)
            with chemin.open("a", encoding="utf-8") as fichier:
                fichier.write(f"{horodatage_iso()} {message}\n")
        except (OSError, ValeurRefusee):
            pass
