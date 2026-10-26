"""Téléchargement explicite des modèles et inventaire local, sans Flask.

Ce service reprend uniquement le dernier résultat de vérification accepté par la
tâche 5.3 (identifiant canonique, commit exact, variante GGUF et fichiers retenus
côté serveur), vérifie que le moteur est installé et prêt, puis admet un
téléchargement dans le créneau unique d'opération longue. Aucun champ de
formulaire ne fournit de commit, de liste de fichiers ni de verdict : seule une
empreinte du dernier résultat permet de refuser une page périmée ou modifiée,
sans session ni nouvelle authentification.

Disposition locale (design D10) ::

    data/models/<moteur>/<CLE>/model.json   inventaire atomique, jamais prêt sinon
    data/models/<moteur>/<CLE>/fichiers/    local_dir du client de téléchargement

`<CLE>` est le SHA-256 d'un JSON déterministe de `[id_resolu, commit,
fichier_gguf ou None]`. L'identifiant Hugging Face n'est jamais transformé en
`<org>__<nom>` ni utilisé comme nom de dossier : la collision relevée en 3.3
disparaît et chaque variante GGUF possède sa propre clé. À la lecture, la clé et
l'identité du manifeste sont recalculées ; un manifeste absent, illisible,
incohérent ou un dossier de clé invalide n'est jamais proposé comme prêt.

`snapshot_download` reçoit des motifs glob et non des noms littéraux : chaque nom
retenu est échappé avec `glob.escape` pour qu'un fichier comme
`model[abc].safetensors` ne sélectionne pas `modela.safetensors`. Le
téléchargement est à révision figée, sans jeton explicite, avec un seul
travailleur. Après succès, chaque fichier attendu doit exister comme fichier
ordinaire confiné et, lorsque sa taille distante est connue, avoir exactement
cette taille : une réponse de client qui ne matérialise rien ou partiellement
n'écrit jamais le marqueur prêt. Les tailles distantes inconnues restent
inconnues ; la taille sur disque est calculée à l'affichage.

Les E/S sont bornées à `data/` par les helpers de `paths` : la racine des modèles
doit rester sous les données et les liens symboliques sortants sont refusés avant
toute écriture du client, avant le marqueur atomique et avant une suppression.
Ces contrôles ne constituent pas une sandbox et ne prétendent pas couvrir une
course TOCTOU ni tous les cas d'un système de fichiers hostile.

Le réseau a lieu hors du verrou du créneau ; le marqueur n'est publié que par
`Travailleur.publier_pret`, donc jamais après le passage à l'arrêt. Le verrou du
créneau peut être tenu pendant l'écriture atomique du stockage, jamais
l'inverse. Le service ne s'exécute jamais dans un contexte Flask : la fabrique
web ne fait aucune E/S et ne crée aucun client réseau.
"""

from __future__ import annotations

import glob
import hashlib
import json
import os
import re
import shutil
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from hmac import compare_digest
from pathlib import Path
from typing import Any, Protocol

import httpx2
from huggingface_hub import snapshot_download
from huggingface_hub.errors import (
    GatedRepoError,
    HfHubHTTPError,
    OfflineModeIsEnabled,
    RepositoryNotFoundError,
    RevisionNotFoundError,
)

from engines.declarations import DeclarationAdaptateur
from engines.registre import MoteurInconnu, RegistreMoteurs
from transcription_bench.compatibilite_modeles import (
    est_fragment_gguf,
    nom_fichier_relatif_valide,
)
from transcription_bench.moteurs import ETAT_PRET, EtatMoteur
from transcription_bench.operations import (
    TYPE_TELECHARGEMENT,
    CreneauOperations,
    ServiceArrete,
    Travailleur,
    horodatage_iso,
)
from transcription_bench.paths import (
    NOM_DOSSIER_MODELES,
    ValeurRefusee,
    resoudre_dans_racine,
    valider_identifiant_modele,
)
from transcription_bench.stockage import (
    VERROU_STOCKAGE,
    JsonInvalide,
    ecrire_json_atomique,
    lire_json,
)
from transcription_bench.verification_modeles import (
    FichierVerifie,
    MOTIF_COMMIT,
    ResultatVerification,
    VerificationModeles,
)

NOM_MARQUEUR = "model.json"
NOM_DOSSIER_FICHIERS = "fichiers"
MOTIF_CLE = re.compile(r"[0-9a-f]{64}", re.ASCII)

RAISON_ACCES_REFUSE = "acces-refuse"
RAISON_REVISION_INCONNUE = "revision-inconnue"
RAISON_RESEAU_INDISPONIBLE = "reseau-indisponible"
RAISON_ERREUR_HUB = "erreur-hub"
RAISON_TELECHARGEMENT_ECHOUE = "telechargement-echoue"
RAISON_ERREUR_INATTENDUE = "erreur-inattendue"

RAISONS_TELECHARGEMENT = (
    RAISON_ACCES_REFUSE,
    RAISON_REVISION_INCONNUE,
    RAISON_RESEAU_INDISPONIBLE,
    RAISON_ERREUR_HUB,
    RAISON_TELECHARGEMENT_ECHOUE,
    RAISON_ERREUR_INATTENDUE,
)

MESSAGES_TELECHARGEMENT = {
    RAISON_ACCES_REFUSE: (
        "accès refusé par le dépôt distant pendant le téléchargement : le jeton "
        "standard éventuel n'a pas permis l'accès, ou les conditions d'utilisation "
        "n'ont pas été acceptées. Aucun modèle n'a été marqué prêt."
    ),
    RAISON_REVISION_INCONNUE: (
        "révision figée introuvable au téléchargement ; aucun modèle n'a été "
        "marqué prêt."
    ),
    RAISON_RESEAU_INDISPONIBLE: (
        "réseau indisponible ou connexion interrompue pendant le téléchargement ; "
        "aucun modèle n'a été marqué prêt."
    ),
    RAISON_ERREUR_HUB: (
        "le dépôt distant n'a pas pu être téléchargé ; aucun modèle n'a été "
        "marqué prêt."
    ),
    RAISON_TELECHARGEMENT_ECHOUE: (
        "le téléchargement a échoué ou les fichiers écrits sont incomplets ou de "
        "taille inattendue ; aucun modèle n'a été marqué prêt. Un dossier partiel "
        "peut être complété par une nouvelle demande explicite."
    ),
    RAISON_ERREUR_INATTENDUE: (
        "le téléchargement a échoué sans verdict ; aucun modèle n'a été marqué "
        "prêt."
    ),
}


class ErreurClientTelechargement(Exception):
    """Erreur de transport traduite en catégorie fixe, sans texte d'exception."""

    def __init__(self, raison: str) -> None:
        if raison not in RAISONS_TELECHARGEMENT:
            raise ValueError(f"catégorie d'erreur de téléchargement inconnue : {raison!r}")
        self.raison = raison
        super().__init__(raison)


class TelechargementEchoue(RuntimeError):
    """Échec de téléchargement à message fixe, publié dans l'état d'opération."""

    def __init__(self, raison: str) -> None:
        if raison not in RAISONS_TELECHARGEMENT:
            raise ValueError(f"catégorie d'échec de téléchargement inconnue : {raison!r}")
        self.raison = raison
        super().__init__(MESSAGES_TELECHARGEMENT[raison])


@dataclass(frozen=True)
class ModeleLocal:
    """Modèle prêt, tel que relu depuis un manifeste cohérent.

    `fichiers` garde les noms et tailles distantes connues ; `taille_disque` est
    la somme réellement présente sous le dossier du modèle, ou `None` si elle
    n'a pas pu être calculée. Aucune taille inconnue n'est remplacée par zéro.
    """

    moteur: str
    cle: str
    identifiant: str
    id_resolu: str
    commit: str
    famille: str
    fichier_gguf: str | None
    fichiers: tuple[FichierVerifie, ...]
    taille_disque: int | None
    date: str

    @property
    def taille_distante(self) -> int | None:
        """Somme des tailles distantes connues, ou `None` si une taille manque."""
        tailles = [fichier.taille for fichier in self.fichiers]
        if not tailles or any(taille is None for taille in tailles):
            return None
        return sum(tailles)


class ClientTelechargement(Protocol):
    """Petit client injectable de téléchargement, sans dépendance Flask."""

    def telecharger(
        self,
        id_resolu: str,
        commit: str,
        fichiers: Sequence[str],
        dossier: Path,
    ) -> None: ...


class ClientHuggingFaceTelechargement:
    """Client de production, créé dans le thread de fond et non à la construction.

    Le jeton Hugging Face reste lu par les mécanismes standards de la
    bibliothèque : il n'est jamais passé explicitement, stocké ni journalisé.
    """

    def telecharger(
        self,
        id_resolu: str,
        commit: str,
        fichiers: Sequence[str],
        dossier: Path,
    ) -> None:
        motifs = [glob.escape(nom) for nom in fichiers]
        try:
            snapshot_download(
                repo_id=id_resolu,
                revision=commit,
                allow_patterns=motifs,
                local_dir=dossier,
                max_workers=1,
            )
        except OfflineModeIsEnabled:
            raise ErreurClientTelechargement(RAISON_RESEAU_INDISPONIBLE) from None
        except (GatedRepoError, RepositoryNotFoundError):
            raise ErreurClientTelechargement(RAISON_ACCES_REFUSE) from None
        except RevisionNotFoundError:
            raise ErreurClientTelechargement(RAISON_REVISION_INCONNUE) from None
        except HfHubHTTPError:
            raise ErreurClientTelechargement(RAISON_ERREUR_HUB) from None
        except httpx2.RequestError:
            raise ErreurClientTelechargement(RAISON_RESEAU_INDISPONIBLE) from None
        except OSError:
            raise ErreurClientTelechargement(RAISON_TELECHARGEMENT_ECHOUE) from None
        except (httpx2.HTTPError, ValueError, TypeError):
            raise ErreurClientTelechargement(RAISON_ERREUR_HUB) from None
        except Exception:  # aucun texte d'exception ne doit remonter
            raise ErreurClientTelechargement(RAISON_ERREUR_INATTENDUE) from None


def cle_stockage(
    id_resolu: str, commit: str, fichier_gguf: str | None = None
) -> str:
    """Clé SHA-256 du dossier d'un modèle, sans collision d'identifiant.

    L'encodage JSON est déterministe et porte l'identité exacte : deux dépôts
    comme `a__b/c` et `a/b__c` produisent des clés distinctes, et chaque variante
    GGUF d'un même dépôt a sa propre clé.
    """
    if not isinstance(id_resolu, str) or not id_resolu:
        raise ValeurRefusee("identifiant canonique attendu pour la clé de stockage")
    if not isinstance(commit, str) or not MOTIF_COMMIT.fullmatch(commit):
        raise ValeurRefusee("commit figé attendu pour la clé de stockage")
    if fichier_gguf is not None and (
        not isinstance(fichier_gguf, str) or not nom_fichier_relatif_valide(fichier_gguf)
    ):
        raise ValeurRefusee("variante GGUF invalide pour la clé de stockage")
    contenu = json.dumps(
        [id_resolu, commit, fichier_gguf],
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(contenu.encode("utf-8")).hexdigest()


def empreinte_verification(resultat: ResultatVerification) -> str:
    """Empreinte du dernier résultat, pour refuser une page périmée ou modifiée.

    Elle ne remplace ni session ni authentification : le formulaire ne transporte
    que cette empreinte, et le service reprend l'identité complète de son propre
    dernier résultat accepté.
    """
    if not isinstance(resultat, ResultatVerification):
        raise ValueError("résultat de vérification attendu")
    contenu = json.dumps(
        [
            resultat.moteur,
            resultat.id_resolu,
            resultat.commit,
            resultat.fichier_gguf,
        ],
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(contenu.encode("utf-8")).hexdigest()


class GestionModeles:
    """Vérification préalable, téléchargement explicite, inventaire et suppression.

    Le constructeur ne fait aucune E/S et ne crée aucun client réseau. Les
    lectures d'inventaire ont lieu à l'affichage ; le client de production est
    instancié dans le thread de fond après admission dans le créneau.
    """

    def __init__(
        self,
        dossier_data: Path | str,
        registre: RegistreMoteurs,
        creneau: CreneauOperations,
        installations: Any,
        *,
        verification: VerificationModeles | None = None,
        client: ClientTelechargement | None = None,
        fabrique_client: Callable[[], ClientTelechargement] = ClientHuggingFaceTelechargement,
        horloge: Callable[[], str] = horodatage_iso,
    ) -> None:
        self._donnees = Path(dossier_data)
        self._registre = registre
        self._creneau = creneau
        self._installations = installations
        self._verification = verification or VerificationModeles(registre, creneau)
        self._client = client
        self._fabrique_client = fabrique_client
        self._horloge = horloge

    def dernier_resultat(self) -> ResultatVerification | None:
        """Dernier résultat de vérification publié, en mémoire seulement."""
        return self._verification.dernier_resultat()

    def moteurs_disponibles(self) -> tuple[EtatMoteur, ...]:
        """Moteurs réels prêts, seuls proposés pour vérifier un dépôt."""
        return tuple(
            etat
            for etat in self._installations.inventaire()
            if etat.etat == ETAT_PRET and not etat.factice
        )

    def lancer_verification(
        self,
        identifiant: str,
        moteur: str,
        *,
        revision: str | None = None,
        fichier_gguf: str | None = None,
    ) -> None:
        """Vérifie le moteur installé puis délègue à la vérification distante 5.3.

        L'identifiant est validé avant toute lecture ; le moteur doit être connu
        et prêt avant l'admission et donc avant tout appel réseau. Les refus
        (`ValeurRefusee`, `MoteurInconnu`) n'effectuent aucune E/S de modèle.
        """
        identifiant_valide = valider_identifiant_modele(identifiant)
        self._moteur_pret(moteur)
        self._verification.lancer(
            identifiant_valide,
            moteur,
            revision=revision,
            fichier_gguf=fichier_gguf,
        )

    def lancer_telechargement(self, empreinte: str) -> bool:
        """Admet le téléchargement du dernier résultat accepté.

        Renvoie `True` si un téléchargement démarre et `False` si ce modèle est
        déjà prêt. Une empreinte absente, périmée ou modifiée est refusée avant
        toute lecture du dossier des modèles. Le moteur est recontrôlé côté
        serveur, puis le travail est admis dans le créneau avant toute E/S.
        """
        resultat = self._verification.dernier_resultat()
        if resultat is None or not resultat.accepte:
            raise ValeurRefusee(
                "aucune vérification acceptée à télécharger : lancez d'abord une "
                "vérification compatible"
            )
        if resultat.id_resolu is None or resultat.commit is None:
            raise ValeurRefusee(
                "résultat de vérification incomplet : identifiant canonique et "
                "commit figé sont requis pour télécharger"
            )
        attendue = empreinte_verification(resultat).encode("ascii")
        if not isinstance(empreinte, str) or not compare_digest(
            empreinte.encode("utf-8", "replace"), attendue
        ):
            raise ValeurRefusee(
                "empreinte de vérification périmée ou inconnue : relancez la "
                "vérification avant de télécharger"
            )
        self._moteur_pret(resultat.moteur)
        if resultat.fichier_gguf is not None and est_fragment_gguf(resultat.fichier_gguf):
            raise ValeurRefusee(
                "le fichier GGUF retenu est un fragment découpé : aucun "
                "téléchargement de fragment n'est lancé"
            )
        if self._modele_pret(resultat):
            return False
        self._creneau.demarrer(
            TYPE_TELECHARGEMENT,
            lambda travailleur: self._telecharger(travailleur, resultat),
            cible=resultat.identifiant,
        )
        return True

    def inventaire(self) -> tuple[ModeleLocal, ...]:
        """Modèles prêts, relus depuis des manifestes cohérents uniquement."""
        racine = self._racine_modeles()
        if not racine.is_dir():
            return ()
        modeles: list[ModeleLocal] = []
        try:
            dossiers_moteurs = sorted(racine.iterdir())
        except OSError:
            return ()
        for dossier_moteur in dossiers_moteurs:
            if dossier_moteur.is_symlink() or not dossier_moteur.is_dir():
                continue
            try:
                self._registre.obtenir(dossier_moteur.name)
                dossiers_cles = sorted(dossier_moteur.iterdir())
            except (MoteurInconnu, OSError):
                continue
            for dossier_cle in dossiers_cles:
                modele = self._lire_modele(dossier_moteur.name, dossier_cle)
                if modele is not None:
                    modeles.append(modele)
        return tuple(modeles)

    def supprimer(self, moteur: str, cle: str) -> None:
        """Supprime un dossier de modèle visé par une clé valide.

        La suppression est admise comme mutation courte du créneau : elle est
        refusée pendant une opération ou après le passage à l'arrêt. Seuls le
        dossier du modèle et ses fichiers sont retirés ; les résultats déjà
        écrits et les autres modèles ne sont jamais touchés.
        """
        self._registre.obtenir(moteur)
        if not isinstance(cle, str) or not MOTIF_CLE.fullmatch(cle):
            raise ValeurRefusee("clé de modèle invalide : SHA-256 hexadécimal attendu")
        dossier = self._dossier_modele(moteur, cle)
        if dossier.is_symlink() or not dossier.is_dir():
            raise ValeurRefusee("modèle local introuvable ou non conforme")
        self._refuser_liens_sortants(dossier)
        self._creneau.executer_mutation(lambda: self._supprimer_dossier(dossier))

    def _moteur_pret(self, moteur: str) -> DeclarationAdaptateur:
        """Contrôle côté serveur que le moteur est installé et prêt."""
        declaration = self._registre.obtenir(moteur)
        if declaration.factice:
            raise ValeurRefusee(
                "le moteur factice ne charge ni ne télécharge aucun modèle : "
                "choisissez un moteur réel installé"
            )
        for etat in self._installations.inventaire():
            if etat.identifiant == moteur:
                if etat.etat != ETAT_PRET:
                    raise ValeurRefusee(
                        f"le moteur {moteur!r} n'est pas installé et prêt : "
                        "installez-le avant de vérifier ou de télécharger un modèle"
                    )
                return declaration
        raise ValeurRefusee(
            f"le moteur {moteur!r} n'est pas installé et prêt : "
            "installez-le avant de vérifier ou de télécharger un modèle"
        )

    def _modele_pret(self, resultat: ResultatVerification) -> bool:
        """Vrai si la même identité est déjà présente avec un manifeste cohérent."""
        return any(
            modele.moteur == resultat.moteur
            and modele.id_resolu == resultat.id_resolu
            and modele.commit == resultat.commit
            and modele.fichier_gguf == resultat.fichier_gguf
            for modele in self.inventaire()
        )

    def _telecharger(
        self, travailleur: Travailleur, resultat: ResultatVerification
    ) -> None:
        """Travail de fond : télécharge, contrôle, puis publie le marqueur prêt."""
        if resultat.id_resolu is None or resultat.commit is None:
            raise ValeurRefusee(
                "résultat de vérification incomplet : téléchargement impossible"
            )
        cle = cle_stockage(resultat.id_resolu, resultat.commit, resultat.fichier_gguf)
        travailleur.journaliser(
            f"Téléchargement de « {resultat.identifiant} » pour le moteur "
            f"« {resultat.moteur} », commit {resultat.commit}."
        )
        try:
            dossier = self._dossier_modele(resultat.moteur, cle)
            fichiers = self._sous_dossier(dossier, NOM_DOSSIER_FICHIERS)
            marqueur = self._sous_dossier(dossier, NOM_MARQUEUR)
            self._preparer_dossiers(dossier, fichiers)
            self._supprimer_marqueur(marqueur)
            client = self._client if self._client is not None else self._fabrique_client()
            client.telecharger(
                resultat.id_resolu,
                resultat.commit,
                tuple(fichier.nom for fichier in resultat.fichiers),
                fichiers,
            )
            self._refuser_liens_sortants(dossier)
            self._verifier_fichiers(fichiers, resultat.fichiers)
            manifeste = self._manifeste(resultat, cle)
            try:
                travailleur.publier_pret(
                    lambda: ecrire_json_atomique(marqueur, manifeste)
                )
            except ServiceArrete:
                travailleur.journaliser(
                    "Modèle non marqué prêt : arrêt du serveur demandé."
                )
                return
            travailleur.journaliser("Téléchargement terminé : modèle prêt.")
        except TelechargementEchoue:
            travailleur.journaliser(
                "Échec du téléchargement : aucun modèle marqué prêt."
            )
            raise
        except ErreurClientTelechargement as erreur:
            travailleur.journaliser(
                f"Échec du téléchargement ({erreur.raison}) : aucun modèle marqué prêt."
            )
            raise TelechargementEchoue(erreur.raison) from None
        except (ValeurRefusee, OSError):
            travailleur.journaliser(
                f"Échec du téléchargement ({RAISON_TELECHARGEMENT_ECHOUE}) : "
                "aucun modèle marqué prêt."
            )
            raise TelechargementEchoue(RAISON_TELECHARGEMENT_ECHOUE) from None
        except Exception:
            # Aucun message d'exception, chemin ou secret ne doit être recopié.
            travailleur.journaliser(
                f"Échec du téléchargement ({RAISON_ERREUR_INATTENDUE}) : "
                "aucun modèle marqué prêt."
            )
            raise TelechargementEchoue(RAISON_ERREUR_INATTENDUE) from None

    def _manifeste(
        self, resultat: ResultatVerification, cle: str
    ) -> dict[str, object]:
        """Contenu déterministe du manifeste, relu et revérifié à l'affichage."""
        return {
            "moteur": resultat.moteur,
            "cle": cle,
            "identifiant": resultat.identifiant,
            "id_resolu": resultat.id_resolu,
            "commit": resultat.commit,
            "famille": resultat.famille,
            "fichier_gguf": resultat.fichier_gguf,
            "fichiers": [
                {"nom": fichier.nom, "taille": fichier.taille}
                for fichier in resultat.fichiers
            ],
            "date": self._horloge(),
        }

    def _preparer_dossiers(self, dossier: Path, fichiers: Path) -> None:
        """Crée les dossiers après avoir refusé tout lien sortant existant."""
        self._refuser_liens_sortants(dossier)
        dossier.mkdir(parents=True, exist_ok=True)
        self._refuser_liens_sortants(dossier)
        fichiers.mkdir(parents=True, exist_ok=True)
        self._refuser_liens_sortants(dossier)

    def _verifier_fichiers(
        self, fichiers: Path, attendus: Sequence[FichierVerifie]
    ) -> None:
        """Chaque fichier attendu doit être ordinaire, confiné et de bonne taille.

        `resoudre_dans_racine` renvoie un chemin déjà résolu : `is_symlink` y est
        donc faux pour un lien interne au modèle pointant vers un vrai fichier du
        modèle. Le chemin résolu est comparé au chemin attendu, composant par
        composant, pour refuser un tel alias avant toute lecture ou `stat`.
        """
        for attendu in attendus:
            chemin = self._sous_dossier(fichiers, attendu.nom)
            if chemin != fichiers.joinpath(*attendu.nom.split("/")):
                raise TelechargementEchoue(RAISON_TELECHARGEMENT_ECHOUE)
            if chemin.is_symlink() or not chemin.is_file():
                raise TelechargementEchoue(RAISON_TELECHARGEMENT_ECHOUE)
            if attendu.taille is not None:
                try:
                    taille = chemin.stat().st_size
                except OSError:
                    raise TelechargementEchoue(RAISON_TELECHARGEMENT_ECHOUE) from None
                if taille != attendu.taille:
                    raise TelechargementEchoue(RAISON_TELECHARGEMENT_ECHOUE)

    def _lire_modele(
        self, moteur: str, dossier_cle: Path
    ) -> ModeleLocal | None:
        """Relit un manifeste confiné et vérifie fichiers et identité.

        Le dossier du moteur et celui de la clé doivent désigner leur propre
        dossier physique : un lien symbolique, même interne à `data/`, n'est
        jamais suivi. Le marqueur doit être un fichier ordinaire, contrôlé sous
        le dossier du modèle avant lecture. Enfin les fichiers attendus doivent
        être présents et de taille connue : un manifeste valide seul ne suffit
        pas à déclarer un modèle prêt après suppression ou altération locale.
        """
        if dossier_cle.is_symlink() or not dossier_cle.is_dir():
            return None
        cle = dossier_cle.name
        if not MOTIF_CLE.fullmatch(cle):
            return None
        try:
            dossier = self._dossier_modele(moteur, cle)
        except (ValeurRefusee, OSError):
            return None
        marqueur_brut = dossier / NOM_MARQUEUR
        if marqueur_brut.is_symlink():
            return None
        try:
            marqueur = self._sous_dossier(dossier, NOM_MARQUEUR)
        except (ValeurRefusee, OSError):
            return None
        try:
            manifeste = lire_json(marqueur)
        except (JsonInvalide, OSError):
            return None
        if not isinstance(manifeste, Mapping):
            return None
        try:
            return self._modele_depuis_manifeste(
                moteur, cle, dossier, manifeste
            )
        except (
            TelechargementEchoue,
            ValeurRefusee,
            OSError,
            TypeError,
            ValueError,
        ):
            return None

    def _modele_depuis_manifeste(
        self,
        moteur: str,
        cle: str,
        dossier_cle: Path,
        manifeste: Mapping[str, Any],
    ) -> ModeleLocal | None:
        identifiant = manifeste.get("identifiant")
        id_resolu = manifeste.get("id_resolu")
        commit = manifeste.get("commit")
        famille = manifeste.get("famille")
        fichier_gguf = manifeste.get("fichier_gguf")
        date = manifeste.get("date")
        fichiers_bruts = manifeste.get("fichiers")
        if manifeste.get("moteur") != moteur or manifeste.get("cle") != cle:
            return None
        if not all(
            isinstance(valeur, str) and valeur
            for valeur in (identifiant, id_resolu, famille, date)
        ):
            return None
        if not isinstance(commit, str) or not MOTIF_COMMIT.fullmatch(commit):
            return None
        valider_identifiant_modele(identifiant)
        valider_identifiant_modele(id_resolu)
        if id_resolu.count("/") != 1:
            return None
        if cle_stockage(id_resolu, commit, fichier_gguf) != cle:
            return None
        if fichier_gguf is not None and est_fragment_gguf(fichier_gguf):
            return None
        if isinstance(fichiers_bruts, (str, bytes)) or not isinstance(
            fichiers_bruts, Sequence
        ):
            return None
        fichiers: list[FichierVerifie] = []
        for brut in fichiers_bruts:
            if not isinstance(brut, Mapping):
                return None
            nom = brut.get("nom")
            taille = brut.get("taille")
            if not isinstance(nom, str) or not nom_fichier_relatif_valide(nom):
                return None
            if taille is not None and (
                not isinstance(taille, int)
                or isinstance(taille, bool)
                or taille < 0
            ):
                return None
            fichiers.append(FichierVerifie(nom, taille))
        if not fichiers:
            return None
        if fichier_gguf is not None and fichier_gguf not in {
            fichier.nom for fichier in fichiers
        }:
            return None
        dossier_fichiers = self._sous_dossier(dossier_cle, NOM_DOSSIER_FICHIERS)
        self._refuser_liens_sortants(dossier_cle)
        self._verifier_fichiers(dossier_fichiers, fichiers)
        return ModeleLocal(
            moteur=moteur,
            cle=cle,
            identifiant=identifiant,
            id_resolu=id_resolu,
            commit=commit,
            famille=famille,
            fichier_gguf=fichier_gguf,
            fichiers=tuple(fichiers),
            taille_disque=self._taille_dossier(dossier_cle),
            date=date,
        )

    def _racine_modeles(self) -> Path:
        """Racine des modèles, confinée à `data/` même en cas de lien existant."""
        donnees = self._donnees.resolve()
        racine = (self._donnees / NOM_DOSSIER_MODELES).resolve()
        if not racine.is_relative_to(donnees):
            raise ValeurRefusee(
                "dossier des modèles hors des données : lien symbolique refusé"
            )
        return racine

    def _dossier_modele(self, moteur: str, cle: str) -> Path:
        """Dossier physique propre du modèle, sans alias symbolique."""
        self._registre.obtenir(moteur)
        if not MOTIF_CLE.fullmatch(cle):
            raise ValeurRefusee("clé de modèle invalide : SHA-256 hexadécimal attendu")
        racine = self._racine_modeles()
        dossier_moteur = racine / moteur
        dossier = dossier_moteur / cle
        if dossier_moteur.is_symlink() or dossier.is_symlink():
            raise ValeurRefusee(
                "lien symbolique refusé dans le dossier des modèles : la clé doit "
                "désigner son propre dossier"
            )
        return resoudre_dans_racine(racine, f"{moteur}/{cle}")

    def _sous_dossier(self, racine: Path, nom: str) -> Path:
        """Chemin relatif contrôlé sous un dossier déjà confiné."""
        return resoudre_dans_racine(racine, nom)

    def _refuser_liens_sortants(self, dossier: Path) -> None:
        """Refuse tout lien symbolique dont la cible sort du dossier fourni.

        `dossier` est la racine contrôlée, en pratique le dossier physique d'un
        modèle : une cible interne au modèle reste autorisée, tandis qu'une cible
        vers `data/results`, un autre modèle ou l'extérieur est refusée. Le cache
        Hugging Face écrit sous `fichiers/.cache/huggingface` ; il est donc
        contrôlé comme le reste de l'arborescence du modèle, avant l'appel au
        client de téléchargement.
        """
        if not dossier.exists():
            return
        racine = dossier.resolve()
        for courant, sous_dossiers, noms in os.walk(dossier, followlinks=False):
            for nom in list(sous_dossiers) + list(noms):
                chemin = Path(courant) / nom
                if not chemin.is_symlink():
                    continue
                try:
                    cible = chemin.resolve()
                except (OSError, RuntimeError):
                    raise ValeurRefusee(
                        f"lien symbolique non résoluble refusé : {nom!r}"
                    ) from None
                if not cible.is_relative_to(racine):
                    raise ValeurRefusee(
                        f"lien symbolique sortant refusé dans le dossier du modèle : {nom!r}"
                    )

    def _taille_dossier(self, dossier: Path) -> int | None:
        """Somme des fichiers ordinaires présents, ou `None` si illisible."""
        total = 0
        try:
            for courant, _sous_dossiers, noms in os.walk(dossier):
                for nom in noms:
                    chemin = Path(courant) / nom
                    if chemin.is_symlink() or not chemin.is_file():
                        continue
                    total += chemin.stat().st_size
        except OSError:
            return None
        return total

    def _supprimer_marqueur(self, marqueur: Path) -> None:
        """Supprime un ancien marqueur sous le verrou commun du stockage.

        Le verrou évite qu'une lecture JSON tienne le fichier ouvert pendant sa
        suppression, cas où Windows refuse le retrait. Aucun appel au créneau
        n'est fait en tenant ce verrou.
        """
        with VERROU_STOCKAGE:
            try:
                marqueur.unlink()
            except FileNotFoundError:
                pass

    def _supprimer_dossier(self, dossier: Path) -> None:
        """Supprime le seul dossier du modèle sous le verrou du stockage."""
        with VERROU_STOCKAGE:
            shutil.rmtree(dossier)
