"""Vérification distante d'un dépôt Hugging Face avant tout téléchargement.

Ce service lit les métadonnées d'un dépôt avec ``HfApi.model_info(...,
files_metadata=True)``, fige le commit exact, lit uniquement les petits JSON de
configuration (et, pour Transformers, l'index safetensors) puis délègue le
verdict aux règles de compatibilité des tâches 5.1 et 5.2. Il ne télécharge
aucun poids, ne conserve aucun verdict sur disque et n'exécute aucun code
distant. La tâche 5.4 utilisera le résultat approuvé pour un téléchargement
explicite à révision figée.

Choix de transport, vérifiés sur les sources installées de huggingface_hub
2.3.0 et fsspec : ``HfFileSystem.open(..., revision=<commit>,
block_size=64 Kio, cache_type='none')`` sélectionne ``HfFileSystemFile`` et non
le flux ``block_size=0``. Avec ``cache_type='none'``, ``BaseCache._fetch``
appelle exactement ``fetcher(start, stop)`` sans prélecture de bloc, et
``HfFileSystemFile._fetch_range`` émet un GET avec
``Range: bytes=start-stop-1`` puis retourne ``response.content``. Chaque lecture
applicative est donc bornée par l'appelant et correspond à une requête Range
bornée ; le lecteur GGUF ne demande jamais plus de 64 Kio. Contrepartie
explicite : un fichier lu par petits morceaux produit de nombreuses requêtes,
chaque morceau pouvant coûter un aller-retour ; ce choix évite un GET complet
implicite des poids mais ne prétend pas contraindre un serveur adverse à
respecter la longueur annoncée (une réponse incohérente est refusée comme
illisible).

Aucune URL, aucun corps de réponse et aucun message d'exception de la
bibliothèque n'est recopié dans un résultat ou un journal : les erreurs sont
traduites en catégories fixes. Le jeton Hugging Face est lu par les mécanismes
standards de la bibliothèque ; il n'est jamais demandé au formulaire, stocké,
journalisé ni affiché.

Le créneau unique d'opération longue est le point d'admission : la vérification
est admise avant toute E/S, s'exécute dans un thread démon et occupe le créneau,
ce qui interdit une exécution ou un téléchargement concurrent (design D3). Le
réseau a lieu hors du verrou du créneau, et le résultat n'est publié que par
``Travailleur.publier_pret`` : après le passage à l'arrêt, aucun résultat n'est
publié. Ce module n'importe pas Flask et ne crée aucun client réseau à la
construction du service : le client de production est instancié au début du
travail de fond, pas dans la fabrique web.
"""

from __future__ import annotations

import re
import threading
from collections.abc import Callable, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from typing import BinaryIO, ContextManager, Protocol

import httpx2
from huggingface_hub import HfApi, HfFileSystem
from huggingface_hub.errors import (
    GatedRepoError,
    HfHubHTTPError,
    OfflineModeIsEnabled,
    RepositoryNotFoundError,
    RevisionNotFoundError,
)

from engines.declarations import DeclarationAdaptateur
from engines.registre import RegistreMoteurs
from transcription_bench.compatibilite_modeles import (
    FICHIERS_CONFIGURATION_INSPECTES,
    INDEX_SAFETENSORS,
    RAISONS_REFUS,
    RAISON_NOM_FICHIER_REFUSE,
    REGLE_CTRANSLATE2_WHISPER,
    REGLE_TRANSFORMERS_SAFETENSORS,
    REGLE_TRANSCRIBE_CPP_GGUF,
    ResultatCompatibilite,
    verifier_compatibilite,
    fichiers_gguf,
    nom_fichier_relatif_valide,
)
from transcription_bench.gguf import (
    OCTETS_MAX_ENTETE,
    TAILLE_BLOC,
    EnteteGGUF,
    EnteteGGUFInvalide,
    lire_entete_gguf,
)
from transcription_bench.operations import (
    TYPE_VERIFICATION,
    CreneauOperations,
    ServiceArrete,
    Travailleur,
)
from transcription_bench.paths import ValeurRefusee, valider_identifiant_modele

# Bornes de lecture des petits JSON, contrôlées avant toute ouverture lorsque la
# taille est connue. `tokenizer_config.json` réel de Whisper peut approcher
# 283 Kio ; 2 Mio laisse une marge documentaire sans permettre de fichier
# arbitrairement gros.
OCTETS_MAX_JSON = 2 * 1024 * 1024
OCTETS_MAX_INDEX = 8 * 1024 * 1024
DELAI_MODELE_INFO = 30.0
LONGUEUR_MAX_REVISION = 200
MOTIF_COMMIT = re.compile(r"[0-9a-f]{40}", re.ASCII)

# Raisons propres à la vérification distante, distinctes des refus de format de
# la tâche 5.1. Les messages associés sont fixes et ne recopient jamais une
# exception, une URL ou un éventuel jeton.
RAISON_ACCES_REFUSE = "acces-refuse"
RAISON_REVISION_INCONNUE = "revision-inconnue"
RAISON_RESEAU_INDISPONIBLE = "reseau-indisponible"
RAISON_ERREUR_HUB = "erreur-hub"
RAISON_METADONNEES_INVALIDES = "metadonnees-invalides"
RAISON_COMMIT_INVALIDE = "commit-invalide"
RAISON_FICHIER_TROP_VOLUMINEUX = "fichier-trop-volumineux"
RAISON_FICHIER_ILLISIBLE = "fichier-illisible"
RAISON_ERREUR_INATTENDUE = "erreur-inattendue"

RAISONS_CLIENT = (
    RAISON_ACCES_REFUSE,
    RAISON_REVISION_INCONNUE,
    RAISON_RESEAU_INDISPONIBLE,
    RAISON_ERREUR_HUB,
    RAISON_METADONNEES_INVALIDES,
    RAISON_COMMIT_INVALIDE,
    RAISON_FICHIER_TROP_VOLUMINEUX,
    RAISON_FICHIER_ILLISIBLE,
)

REGLES_VERIFIABLES = (
    REGLE_CTRANSLATE2_WHISPER,
    REGLE_TRANSFORMERS_SAFETENSORS,
    REGLE_TRANSCRIBE_CPP_GGUF,
)

RAISONS_VERIFICATION = RAISONS_REFUS + (
    RAISON_ACCES_REFUSE,
    RAISON_REVISION_INCONNUE,
    RAISON_RESEAU_INDISPONIBLE,
    RAISON_ERREUR_HUB,
    RAISON_METADONNEES_INVALIDES,
    RAISON_COMMIT_INVALIDE,
    RAISON_FICHIER_TROP_VOLUMINEUX,
    RAISON_FICHIER_ILLISIBLE,
    RAISON_ERREUR_INATTENDUE,
)

MESSAGES_ERREUR = {
    RAISON_ACCES_REFUSE: (
        "accès refusé par le dépôt distant : il peut être privé, inexistant ou "
        "soumis à l'acceptation de conditions. Le programme ne peut pas "
        "déterminer lequel ; configurez un jeton Hugging Face par les moyens "
        "standards si un accès authentifié est nécessaire."
    ),
    RAISON_REVISION_INCONNUE: (
        "révision demandée introuvable : choisissez une révision existante ou "
        "laissez la valeur par défaut."
    ),
    RAISON_RESEAU_INDISPONIBLE: (
        "dépôt distant inaccessible : réseau indisponible ou connexion "
        "interrompue ; aucune vérification n'a été enregistrée."
    ),
    RAISON_ERREUR_HUB: (
        "le dépôt distant n'a pas pu être interrogé ; aucune vérification n'a "
        "été enregistrée."
    ),
    RAISON_METADONNEES_INVALIDES: (
        "métadonnées du dépôt invalides : identifiant canonique avec "
        "organisation absent ou inutilisable ; aucun fichier n'a été lu."
    ),
    RAISON_COMMIT_INVALIDE: (
        "révision résolue invalide : un commit hexadécimal de 40 caractères est "
        "requis pour figer les fichiers d'une vérification."
    ),
    RAISON_FICHIER_TROP_VOLUMINEUX: (
        "fichier de configuration ou index trop volumineux pour être lu pendant "
        "la vérification."
    ),
    RAISON_FICHIER_ILLISIBLE: (
        "fichier distant illisible pendant la vérification ; aucun poids n'est "
        "lu ni téléchargé à cette étape."
    ),
    RAISON_ERREUR_INATTENDUE: (
        "la vérification a échoué sans verdict ; réessayez."
    ),
}

MESSAGE_NOM_FICHIER_REFUSE = (
    "nom de fichier distant refusé : la liste du dépôt contient un chemin non "
    "confiné ; aucun fichier n'a été ouvert."
)


class ErreurClientModeles(Exception):
    """Erreur de transport ou de lecture traduite en catégorie fixe.

    Le constructeur n'accepte pas de message libre : aucun texte d'exception,
    d'URL ou de secret ne peut ainsi être recopié dans un résultat ou un
    journal. Un client de test peut lever cette erreur avec une catégorie
    connue ; toute autre exception est traitée par le service comme une erreur
    inattendue et reçoit aussi un message fixe.
    """

    def __init__(self, raison: str) -> None:
        if raison not in RAISONS_CLIENT:
            raise ValueError(f"catégorie d'erreur client inconnue : {raison!r}")
        self.raison = raison
        super().__init__(raison)


@dataclass(frozen=True)
class FichierDistant:
    """Fichier lu dans les métadonnées du dépôt.

    `taille` vaut `None` quand la métadonnée est absente ou invalide : aucune
    taille zéro n'est inventée.
    """

    nom: str
    taille: int | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.nom, str) or not self.nom:
            raise ValueError("nom de fichier distant attendu non vide")
        if self.taille is not None and (
            not isinstance(self.taille, int)
            or isinstance(self.taille, bool)
            or self.taille < 0
        ):
            raise ValueError("taille de fichier distant attendue entière ou None")


@dataclass(frozen=True)
class FichierVerifie:
    """Fichier retenu par la vérification, avec sa taille si elle est connue."""

    nom: str
    taille: int | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.nom, str) or not self.nom:
            raise ValueError("nom de fichier vérifié attendu non vide")
        if self.taille is not None and (
            not isinstance(self.taille, int)
            or isinstance(self.taille, bool)
            or self.taille < 0
        ):
            raise ValueError("taille de fichier vérifié attendue entière ou None")


@dataclass(frozen=True)
class InfosModele:
    """Métadonnées minimales d'un dépôt, telles que renvoyées par le client.

    `id_resolu` est l'identifiant canonique renvoyé par l'API (`ModelInfo.id`),
    utilisé pour les lectures HfFileSystem lorsqu'il possède une organisation.
    L'identifiant demandé reste la référence affichée par le résultat. Le commit
    n'est pas validé ici : le service exige un hexadécimal de 40 caractères et
    refuse sinon, afin qu'une référence mobile ne soit jamais réutilisée pour
    une lecture ou un futur téléchargement.
    """

    commit: str
    fichiers: tuple[FichierDistant, ...] = ()
    id_resolu: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.commit, str):
            raise ValueError("commit attendu sous forme de texte")
        if self.id_resolu is not None and (
            not isinstance(self.id_resolu, str) or not self.id_resolu
        ):
            raise ValueError("identifiant résolu attendu non vide ou None")
        object.__setattr__(self, "fichiers", tuple(self.fichiers))
        for fichier in self.fichiers:
            if not isinstance(fichier, FichierDistant):
                raise ValueError("fichier distant attendu")


@dataclass(frozen=True)
class ResultatVerification:
    """Résultat immuable d'une vérification distante, réutilisable par 5.4.

    Un résultat accepté porte un commit hexadécimal exact, au moins un fichier
    retenu et, pour transcribe.cpp, la variante GGUF choisie. `taille_totale`
    ne totalise que les fichiers retenus et vaut `None` dès qu'une taille
    manque : aucune taille n'est inventée. Un refus conserve la famille, le
    commit déjà résolu et les variantes GGUF candidates lorsqu'ils sont connus,
    pour que l'interface puisse proposer un choix sans relancer de requête.

    Ce type est construit uniquement par le service à partir des métadonnées
    distantes et des règles de compatibilité ; il n'est jamais dérivé d'un
    champ de formulaire qui déclarerait le dépôt prêt.
    """

    accepte: bool
    identifiant: str
    moteur: str
    famille: str | None
    commit: str | None
    id_resolu: str | None = None
    fichiers: tuple[FichierVerifie, ...] = ()
    taille_totale: int | None = None
    gguf_candidats: tuple[str, ...] = ()
    fichier_gguf: str | None = None
    raison: str | None = None
    message: str = ""
    fichiers_manquants: tuple[str, ...] = ()
    moteur_suggere: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.accepte, bool):
            raise ValueError("accepte doit être un booléen")
        if not isinstance(self.identifiant, str) or not self.identifiant:
            raise ValueError("identifiant de modèle attendu non vide")
        if not isinstance(self.moteur, str) or not self.moteur:
            raise ValueError("moteur attendu non vide")
        object.__setattr__(self, "fichiers", tuple(self.fichiers))
        object.__setattr__(self, "gguf_candidats", tuple(self.gguf_candidats))
        object.__setattr__(self, "fichiers_manquants", tuple(self.fichiers_manquants))
        for fichier in self.fichiers:
            if not isinstance(fichier, FichierVerifie):
                raise ValueError("fichier vérifié attendu")
        if self.commit is not None and (
            not isinstance(self.commit, str)
            or not MOTIF_COMMIT.fullmatch(self.commit)
        ):
            raise ValueError("commit vérifié attendu en hexadécimal de 40 caractères")
        if not isinstance(self.message, str) or not self.message.strip():
            raise ValueError("message de vérification attendu non vide")
        if not isinstance(self.raison, (str, type(None))):
            raise ValueError("raison de vérification attendue textuelle ou None")
        if not isinstance(self.famille, (str, type(None))):
            raise ValueError("famille attendue textuelle ou None")
        if self.id_resolu is not None:
            try:
                if not isinstance(self.id_resolu, str) or self.id_resolu.count("/") != 1:
                    raise ValeurRefusee("identifiant canonique sans organisation")
                object.__setattr__(
                    self, "id_resolu", valider_identifiant_modele(self.id_resolu)
                )
            except ValeurRefusee:
                raise ValueError("id_resolu canonique avec organisation attendu") from None
        if not isinstance(self.moteur_suggere, (str, type(None))):
            raise ValueError("moteur suggéré attendu textuel ou None")
        if not isinstance(self.fichier_gguf, (str, type(None))):
            raise ValueError("fichier GGUF attendu textuel ou None")
        if self.accepte:
            if self.raison is not None:
                raise ValueError("une acceptation n'a pas de raison de refus")
            if not self.fichiers:
                raise ValueError("une acceptation retient au moins un fichier")
            if self.commit is None:
                raise ValueError("une acceptation exige un commit figé")
            if not self.famille:
                raise ValueError("une acceptation exige une famille")
            if self.taille_totale is not None:
                if not isinstance(self.taille_totale, int) or isinstance(
                    self.taille_totale, bool
                ):
                    raise ValueError("taille totale attendue entière ou None")
                tailles = [fichier.taille for fichier in self.fichiers]
                if any(taille is None for taille in tailles):
                    raise ValueError(
                        "une taille totale ne peut pas être calculée avec une "
                        "taille de fichier inconnue"
                    )
                if self.taille_totale != sum(tailles):
                    raise ValueError("taille totale incohérente avec les fichiers")
            if self.fichier_gguf is not None and self.fichier_gguf not in {
                fichier.nom for fichier in self.fichiers
            }:
                raise ValueError("fichier GGUF choisi absent des fichiers retenus")
        else:
            if self.raison not in RAISONS_VERIFICATION:
                raise ValueError(f"raison de vérification inconnue : {self.raison!r}")
            if self.fichiers:
                raise ValueError("un refus ne retient aucun fichier")
            if self.taille_totale is not None:
                raise ValueError("un refus n'annonce pas de taille totale")
            if self.fichiers_manquants and not all(
                isinstance(nom, str) and nom for nom in self.fichiers_manquants
            ):
                raise ValueError("fichiers manquants attendus sous forme de noms")


@dataclass(frozen=True)
class DemandeVerification:
    """Demande validée avant admission : aucune E/S n'a encore eu lieu."""

    declaration: DeclarationAdaptateur
    identifiant: str
    revision: str | None
    fichier_gguf: str | None


class FichierLecture(Protocol):
    """Flux binaire minimal d'un fichier distant, fourni par le client."""

    def read(self, taille: int) -> bytes: ...

    def __enter__(self) -> FichierLecture: ...

    def __exit__(self, exc_type, exc, traceback) -> bool | None: ...


class ClientModeles(Protocol):
    """Petit client injectable, sans dépendance à Flask ni au créneau."""

    def informations(
        self, identifiant: str, revision: str | None
    ) -> InfosModele: ...

    def ouvrir_fichier(
        self, identifiant: str, commit: str, nom: str
    ) -> ContextManager[BinaryIO]: ...


class ClientHuggingFace:
    """Client de production, créé au début d'une vérification et non à l'import.

    Une instance vit le temps d'une opération et n'est pas partagée entre
    threads : son cache HfFileSystem réduit les requêtes répétées pendant la
    lecture des JSON d'un même dépôt. Aucun jeton n'est passé explicitement :
    la bibliothèque applique ses mécanismes standards de configuration.
    """

    def __init__(self) -> None:
        self._api = HfApi()
        self._systeme = HfFileSystem()

    def informations(
        self, identifiant: str, revision: str | None
    ) -> InfosModele:
        try:
            info = self._api.model_info(
                identifiant,
                revision=revision,
                files_metadata=True,
                timeout=DELAI_MODELE_INFO,
            )
        except OfflineModeIsEnabled:
            raise ErreurClientModeles(RAISON_RESEAU_INDISPONIBLE) from None
        except (GatedRepoError, RepositoryNotFoundError):
            raise ErreurClientModeles(RAISON_ACCES_REFUSE) from None
        except RevisionNotFoundError:
            raise ErreurClientModeles(RAISON_REVISION_INCONNUE) from None
        except HfHubHTTPError:
            raise ErreurClientModeles(RAISON_ERREUR_HUB) from None
        except httpx2.RequestError:
            raise ErreurClientModeles(RAISON_RESEAU_INDISPONIBLE) from None
        except (httpx2.HTTPError, OSError, ValueError, TypeError):
            raise ErreurClientModeles(RAISON_ERREUR_HUB) from None
        except Exception:  # aucun texte d'exception ne doit remonter
            raise ErreurClientModeles(RAISON_ERREUR_HUB) from None

        id_resolu = getattr(info, "id", None)
        try:
            if not isinstance(id_resolu, str) or id_resolu.count("/") != 1:
                raise ValeurRefusee("identifiant canonique sans organisation")
            id_resolu = valider_identifiant_modele(id_resolu)
        except ValeurRefusee:
            raise ErreurClientModeles(RAISON_METADONNEES_INVALIDES) from None

        commit = getattr(info, "sha", None)
        fichiers: list[FichierDistant] = []
        for frere in getattr(info, "siblings", None) or ():
            nom = getattr(frere, "rfilename", None)
            if not isinstance(nom, str):
                continue
            taille = getattr(frere, "size", None)
            if (
                not isinstance(taille, int)
                or isinstance(taille, bool)
                or taille < 0
            ):
                taille = None
            fichiers.append(FichierDistant(nom=nom, taille=taille))
        return InfosModele(
            commit=commit if isinstance(commit, str) else "",
            fichiers=tuple(fichiers),
            id_resolu=id_resolu,
        )

    def ouvrir_fichier(
        self, identifiant: str, commit: str, nom: str
    ) -> ContextManager[BinaryIO]:
        try:
            return self._systeme.open(
                f"{identifiant}/{nom}",
                "rb",
                revision=commit,
                block_size=TAILLE_BLOC,
                cache_type="none",
            )
        except OfflineModeIsEnabled:
            raise ErreurClientModeles(RAISON_RESEAU_INDISPONIBLE) from None
        except (GatedRepoError, RepositoryNotFoundError):
            raise ErreurClientModeles(RAISON_ACCES_REFUSE) from None
        except RevisionNotFoundError:
            raise ErreurClientModeles(RAISON_REVISION_INCONNUE) from None
        except HfHubHTTPError:
            raise ErreurClientModeles(RAISON_ERREUR_HUB) from None
        except httpx2.RequestError:
            raise ErreurClientModeles(RAISON_RESEAU_INDISPONIBLE) from None
        except (httpx2.HTTPError, OSError, ValueError, TypeError):
            raise ErreurClientModeles(RAISON_FICHIER_ILLISIBLE) from None
        except Exception:  # aucun texte d'exception ne doit remonter
            raise ErreurClientModeles(RAISON_FICHIER_ILLISIBLE) from None


class VerificationModeles:
    """Vérification distante dans le créneau global, sans Flask.

    Le service valide la demande avant admission (identifiant, moteur, révision,
    nom GGUF), puis appelle `CreneauOperations.demarrer` : le créneau est donc
    occupé avant toute E/S et une exécution ou un téléchargement concurrent est
    refusé. Le client de production est construit dans le thread de fond ; la
    construction du service ne fait aucune E/S.
    """

    def __init__(
        self,
        registre: RegistreMoteurs,
        creneau: CreneauOperations,
        *,
        client: ClientModeles | None = None,
        fabrique_client: Callable[[], ClientModeles] = ClientHuggingFace,
    ) -> None:
        self._registre = registre
        self._creneau = creneau
        self._client = client
        self._fabrique_client = fabrique_client
        self._verrou_resultat = threading.Lock()
        self._dernier: ResultatVerification | None = None

    def lancer(
        self,
        identifiant: str,
        moteur: str,
        *,
        revision: str | None = None,
        fichier_gguf: str | None = None,
    ) -> None:
        """Valide la demande puis l'admet dans le créneau, avant toute E/S.

        Lève `ValeurRefusee` pour une entrée invalide, `MoteurInconnu` pour un
        moteur absent du registre, `CreneauOccupe` si une opération est déjà en
        cours et `ServiceArrete` après le passage à l'arrêt. Ces refus
        n'effectuent aucune requête réseau.
        """
        demande = self._preparer(identifiant, moteur, revision, fichier_gguf)
        self._creneau.demarrer(
            TYPE_VERIFICATION,
            lambda travailleur: self._executer(travailleur, demande),
            cible=demande.identifiant,
        )

    def dernier_resultat(self) -> ResultatVerification | None:
        """Dernier résultat réellement publié, ou `None` après un refus d'arrêt."""
        with self._verrou_resultat:
            return self._dernier

    def _preparer(
        self,
        identifiant: str,
        moteur: str,
        revision: str | None,
        fichier_gguf: str | None,
    ) -> DemandeVerification:
        declaration = self._registre.obtenir(moteur)
        if declaration.factice:
            raise ValeurRefusee(
                "le moteur factice ne vérifie aucun dépôt distant : choisissez "
                "un moteur réel"
            )
        if declaration.regle_compatibilite not in REGLES_VERIFIABLES:
            raise ValeurRefusee(
                f"le moteur {declaration.identifiant!r} n'a pas de règle de "
                "vérification distante"
            )
        identifiant_valide = valider_identifiant_modele(identifiant)
        revision_valide = _valider_revision(revision)
        if fichier_gguf is not None:
            if declaration.regle_compatibilite != REGLE_TRANSCRIBE_CPP_GGUF:
                raise ValeurRefusee(
                    "un fichier GGUF ne peut être choisi que pour transcribe.cpp"
                )
            if not isinstance(fichier_gguf, str) or not nom_fichier_relatif_valide(
                fichier_gguf
            ):
                raise ValeurRefusee(
                    f"nom de fichier GGUF refusé : {fichier_gguf!r} (chemin relatif "
                    "confiné attendu)"
                )
        return DemandeVerification(
            declaration=declaration,
            identifiant=identifiant_valide,
            revision=revision_valide,
            fichier_gguf=fichier_gguf,
        )

    def _executer(
        self, travailleur: Travailleur, demande: DemandeVerification
    ) -> None:
        self._effacer_dernier()
        travailleur.journaliser(
            f"Vérification distante de « {demande.identifiant} » pour le moteur "
            f"« {demande.declaration.identifiant} »."
        )
        try:
            resultat = self._verifier(demande)
        except ErreurClientModeles as erreur:
            resultat = self._resultat_echec(demande, erreur.raison)
        except Exception:
            # Aucun message d'exception, aucune URL et aucun secret ne remontent.
            resultat = self._resultat_echec(demande, RAISON_ERREUR_INATTENDUE)
        try:
            travailleur.publier_pret(lambda: self._publier(resultat))
        except ServiceArrete:
            travailleur.journaliser(
                "Résultat non publié : arrêt du serveur demandé."
            )
            return
        travailleur.journaliser(_resume(resultat))

    def _verifier(self, demande: DemandeVerification) -> ResultatVerification:
        client = self._client if self._client is not None else self._fabrique_client()
        infos = client.informations(demande.identifiant, demande.revision)
        commit = infos.commit
        if not isinstance(commit, str) or not MOTIF_COMMIT.fullmatch(commit):
            raise ErreurClientModeles(RAISON_COMMIT_INVALIDE)

        tailles = {fichier.nom: fichier.taille for fichier in infos.fichiers}
        noms = tuple(tailles)
        identifiant_lecture = self._identifiant_lecture(demande, infos)
        if any(not nom_fichier_relatif_valide(nom) for nom in noms):
            return self._resultat_preflight(
                demande,
                infos,
                identifiant_lecture,
                RAISON_NOM_FICHIER_REFUSE,
                MESSAGE_NOM_FICHIER_REFUSE,
            )
        regle = demande.declaration.regle_compatibilite
        est_gguf = regle == REGLE_TRANSCRIBE_CPP_GGUF
        contenus: dict[str, bytes] = {}
        if regle == REGLE_CTRANSLATE2_WHISPER:
            noms_json = ("config.json", "preprocessor_config.json")
        elif regle == REGLE_TRANSFORMERS_SAFETENSORS:
            noms_json = FICHIERS_CONFIGURATION_INSPECTES
        else:
            noms_json = ()
        for nom in noms_json:
            if nom in tailles:
                contenus[nom] = self._lire_json(
                    client,
                    identifiant_lecture,
                    commit,
                    nom,
                    tailles[nom],
                    OCTETS_MAX_JSON,
                )
        if regle == REGLE_TRANSFORMERS_SAFETENSORS and INDEX_SAFETENSORS in tailles:
            contenus[INDEX_SAFETENSORS] = self._lire_json(
                client,
                identifiant_lecture,
                commit,
                INDEX_SAFETENSORS,
                tailles[INDEX_SAFETENSORS],
                OCTETS_MAX_INDEX,
            )

        lecteur = (
            (lambda nom: self._lire_entete(client, identifiant_lecture, commit, nom))
            if est_gguf
            else None
        )
        compatibilite = verifier_compatibilite(
            demande.declaration,
            noms,
            configurations=contenus,
            fichier_gguf=demande.fichier_gguf if est_gguf else None,
            lecteur_entete_gguf=lecteur,
        )
        return self._resultat_compatibilite(
            demande,
            infos,
            identifiant_lecture,
            tailles,
            compatibilite,
            est_gguf,
            noms,
        )

    def _resultat_compatibilite(
        self,
        demande: DemandeVerification,
        infos: InfosModele,
        identifiant_lecture: str,
        tailles: Mapping[str, int | None],
        compatibilite: ResultatCompatibilite,
        est_gguf: bool,
        noms: Sequence[str],
    ) -> ResultatVerification:
        if compatibilite.accepte:
            fichiers = tuple(
                FichierVerifie(nom, tailles.get(nom))
                for nom in compatibilite.fichiers
            )
            total = (
                sum(fichier.taille for fichier in fichiers)
                if fichiers and all(fichier.taille is not None for fichier in fichiers)
                else None
            )
        else:
            fichiers = ()
            total = None
        choisi = demande.fichier_gguf
        if est_gguf and compatibilite.accepte and choisi is None:
            choisi = compatibilite.fichiers[0]
        return ResultatVerification(
            accepte=compatibilite.accepte,
            identifiant=demande.identifiant,
            moteur=demande.declaration.identifiant,
            famille=compatibilite.famille,
            commit=infos.commit,
            id_resolu=identifiant_lecture,
            fichiers=fichiers,
            taille_totale=total,
            gguf_candidats=tuple(fichiers_gguf(noms)) if est_gguf else (),
            fichier_gguf=choisi,
            raison=compatibilite.raison,
            message=compatibilite.message,
            fichiers_manquants=compatibilite.fichiers_manquants,
            moteur_suggere=compatibilite.moteur_suggere,
        )

    def _identifiant_lecture(
        self, demande: DemandeVerification, infos: InfosModele
    ) -> str:
        """Identifiant canonique pour HfFileSystem, sans deviner d'organisation.

        L'identifiant demandé reste la référence du résultat ; seul l'identifiant
        retourné par l'API (`ModelInfo.id`) sert aux lectures, car HfFileSystem 2.3
        exige un identifiant avec organisation. Sans identifiant résolu, le
        client de test peut encore ouvrir l'identifiant demandé déjà qualifié.
        """
        if infos.id_resolu is None:
            try:
                if demande.identifiant.count("/") != 1:
                    raise ValeurRefusee("identifiant canonique sans organisation")
                return valider_identifiant_modele(demande.identifiant)
            except ValeurRefusee:
                raise ErreurClientModeles(RAISON_METADONNEES_INVALIDES) from None
        try:
            if infos.id_resolu.count("/") != 1:
                raise ValeurRefusee("identifiant canonique sans organisation")
            return valider_identifiant_modele(infos.id_resolu)
        except ValeurRefusee:
            raise ErreurClientModeles(RAISON_METADONNEES_INVALIDES) from None

    def _resultat_preflight(
        self,
        demande: DemandeVerification,
        infos: InfosModele,
        identifiant_lecture: str,
        raison: str,
        message: str,
    ) -> ResultatVerification:
        return ResultatVerification(
            accepte=False,
            identifiant=demande.identifiant,
            moteur=demande.declaration.identifiant,
            famille=None,
            commit=infos.commit,
            id_resolu=identifiant_lecture,
            fichiers=(),
            taille_totale=None,
            gguf_candidats=(),
            fichier_gguf=demande.fichier_gguf,
            raison=raison,
            message=message,
        )

    def _resultat_echec(
        self, demande: DemandeVerification, raison: str
    ) -> ResultatVerification:
        return ResultatVerification(
            accepte=False,
            identifiant=demande.identifiant,
            moteur=demande.declaration.identifiant,
            famille=None,
            commit=None,
            fichiers=(),
            taille_totale=None,
            gguf_candidats=(),
            fichier_gguf=demande.fichier_gguf,
            raison=raison,
            message=MESSAGES_ERREUR[raison],
        )

    def _lire_json(
        self,
        client: ClientModeles,
        identifiant: str,
        commit: str,
        nom: str,
        taille: int | None,
        maximum: int,
    ) -> bytes:
        if taille is not None and taille > maximum:
            raise ErreurClientModeles(RAISON_FICHIER_TROP_VOLUMINEUX)
        octets = self._lire_borne(client, identifiant, commit, nom, maximum)
        if taille is not None and len(octets) != taille:
            raise ErreurClientModeles(RAISON_FICHIER_ILLISIBLE)
        return octets

    def _lire_borne(
        self,
        client: ClientModeles,
        identifiant: str,
        commit: str,
        nom: str,
        maximum: int,
    ) -> bytes:
        morceaux: list[bytes] = []
        total = 0
        with self._ouvrir(client, identifiant, commit, nom) as flux:
            while total <= maximum:
                demande = min(TAILLE_BLOC, maximum + 1 - total)
                bloc = flux.read(demande)
                if not isinstance(bloc, (bytes, bytearray, memoryview)):
                    raise ErreurClientModeles(RAISON_FICHIER_ILLISIBLE)
                octets = bytes(bloc)
                if not octets:
                    break
                if len(octets) > demande:
                    raise ErreurClientModeles(RAISON_FICHIER_ILLISIBLE)
                total += len(octets)
                if total > maximum:
                    raise ErreurClientModeles(RAISON_FICHIER_TROP_VOLUMINEUX)
                morceaux.append(octets)
        return b"".join(morceaux)

    def _lire_entete(
        self, client: ClientModeles, identifiant: str, commit: str, nom: str
    ) -> EnteteGGUF:
        with self._ouvrir(client, identifiant, commit, nom) as flux:
            return lire_entete_gguf(
                lambda demande: _lire_source(flux, demande),
                octets_max=OCTETS_MAX_ENTETE,
                taille_bloc=TAILLE_BLOC,
            )

    @contextmanager
    def _ouvrir(
        self, client: ClientModeles, identifiant: str, commit: str, nom: str
    ):
        try:
            with client.ouvrir_fichier(identifiant, commit, nom) as flux:
                yield flux
        except EnteteGGUFInvalide:
            raise
        except ErreurClientModeles:
            raise
        except Exception:
            raise ErreurClientModeles(RAISON_FICHIER_ILLISIBLE) from None

    def _publier(self, resultat: ResultatVerification) -> None:
        with self._verrou_resultat:
            self._dernier = resultat

    def _effacer_dernier(self) -> None:
        with self._verrou_resultat:
            self._dernier = None


def _lire_source(flux: FichierLecture, demande: int) -> bytes:
    """Source bornée pour le lecteur GGUF : jamais de lecture sans limite."""
    if (
        not isinstance(demande, int)
        or isinstance(demande, bool)
        or demande <= 0
        or demande > TAILLE_BLOC
    ):
        raise EnteteGGUFInvalide("lecture distante hors bornes")
    bloc = flux.read(demande)
    if not isinstance(bloc, (bytes, bytearray, memoryview)):
        raise EnteteGGUFInvalide("flux distant non binaire")
    octets = bytes(bloc)
    if len(octets) > demande:
        raise EnteteGGUFInvalide("flux distant plus long que demandé")
    return octets


def _valider_revision(revision: str | None) -> str | None:
    """Valide une révision facultative, sans l'interpréter comme un chemin.

    La bibliothèque cite la révision dans l'URL ; ce contrôle refuse seulement
    les formes vides, trop longues ou porteuses de caractères de contrôle. Le
    résultat d'une vérification ne conserve jamais cette valeur : seul le
    commit hexadécimal résolu sera réutilisé.
    """
    if revision is None:
        return None
    if not isinstance(revision, str):
        raise ValeurRefusee("révision attendue sous forme de texte")
    texte = revision.strip()
    if not texte:
        raise ValeurRefusee("révision vide refusée")
    if len(texte) > LONGUEUR_MAX_REVISION:
        raise ValeurRefusee(
            f"révision refusée : {LONGUEUR_MAX_REVISION} caractères au maximum"
        )
    if any(ord(caractere) < 32 or ord(caractere) == 127 for caractere in texte):
        raise ValeurRefusee("révision refusée : caractère de contrôle")
    return texte


def _resume(resultat: ResultatVerification) -> str:
    """Ligne de journal fixe, sans URL ni message d'exception."""
    if resultat.accepte:
        return (
            "Vérification terminée : dépôt compatible, commit "
            f"{resultat.commit}."
        )
    return f"Vérification terminée : refus ({resultat.raison})."
