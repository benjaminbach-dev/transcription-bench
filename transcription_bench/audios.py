"""Liste des audios d'entrée et décodage commun en `float32` 16 kHz mono.

Ce service, indépendant de Flask, couvre la tâche 6.1 du lot « Audios et
exécutions » et le décodage commun du design D7 :

- la **liste** parcourt le dossier d'entrée `data/audio` et ne retient que les
  formats acceptés (wav, mp3, m4a, ogg, opus, flac). La durée affichée est lue
  dans l'en-tête du conteneur : elle reste **indicative**, car un en-tête absent
  ou incohérent avec le flux réel ne prouve rien sur le signal décodé. Un
  fichier illisible est signalé par un message d'erreur propre, sans interrompre
  la liste des autres fichiers ;
- le **décodage** produit un signal `float32` mono à 16 000 Hz identique pour
  tous les moteurs, l'empreinte SHA-256 du fichier source, la durée décodée
  (`échantillons / 16 000`, référence du RTF) et le temps de décodage. Une durée
  décodée nulle est une erreur explicite : aucun RTF ne peut être calculé. La
  durée indicative et la durée décodée sont lues sur le même conteneur ouvert,
  pour que la paire consignée soit cohérente ; les deux valeurs restent
  distinctes.

Accès au système de fichiers : les noms passent par les contrôles de `paths`
(tâche 3.3). Un nom est refusé s'il n'a pas un format accepté, s'il contient
`/`, `:` ou `\\`, s'il sort du dossier autorisé, s'il désigne un périphérique
réservé Windows (`CON`, `NUL`, `COM1`… `COM³` : sous Windows, l'ouverture vise
le périphérique et non un fichier), ou si la cible n'est pas un fichier
ordinaire (répertoire, lien symbolique sortant). Un fichier au bon format mais
refusé reste listé avec l'erreur « nom refusé », afin qu'il soit visible sans
être proposé à une exécution ; un format non accepté n'est pas listé du tout.
Un fichier dont la description échoue de façon inattendue reste également listé,
avec une erreur générique, pour qu'aucun fichier ne fasse échouer la liste.

Limites assumées : ces contrôles ne constituent pas une sandbox et ne couvrent
pas une course TOCTOU ; le fichier peut changer entre la liste, l'empreinte et
le décodage. Le temps de décodage ne comprend pas le calcul de l'empreinte,
couvert par la durée totale de l'opération (D8). Le signal complet est conservé
en mémoire : un audio long occupe environ 64 Kio par seconde (16 000 × 4 octets)
pendant son décodage, sans écriture temporaire ici. Ce module n'ouvre aucune
connexion et n'appelle aucun service distant ; pour autant, l'ouverture d'un
fichier local par PyAV confie son contenu à FFmpeg, qui sait suivre les
références d'un conteneur (liste HLS, par exemple). Aucune liste blanche de
protocoles n'est imposée ici : ce durcissement n'a pas été vérifié et reste à
traiter séparément. Aucun moteur ni aucune bibliothèque de moteur n'est utilisé :
seul PyAV (FFmpeg embarqué dans ses roues) décode, et seul le processus serveur
y accède.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass
from pathlib import Path

import av
import numpy as np

from transcription_bench.paths import (
    DOSSIER_DATA,
    NOM_DOSSIER_AUDIO,
    ValeurRefusee,
    resoudre_audio,
)

FORMATS_AUDIO = ("wav", "mp3", "m4a", "ogg", "opus", "flac")
FREQUENCE_DECODAGE = 16_000
FORMAT_ECHANTILLONS_DECODAGE = "flt"
DISPOSITION_DECODAGE = "mono"
TAILLE_BLOC_EMPREINTE = 1024 * 1024
#: Erreur affichée pour un fichier au bon format mais dont le nom ou la cible
#: est refusé : il reste listé, jamais proposé à une exécution.
ERREUR_NOM_REFUSE = "nom refusé"

#: Noms de périphériques réservés de Windows : un fichier `CON.wav` y ouvre le
#: périphérique et non un fichier du dossier. Comparaison sur la partie du nom
#: avant le premier point, insensible à la casse et aux espaces/points finaux.
#: Windows réserve aussi `COM¹`, `COM²`, `COM³`, `LPT¹`, `LPT²` et `LPT³`
#: (chiffres en exposant), en plus des chiffres ASCII.
_INDICES_PERIPHERIQUES = tuple("123456789") + ("¹", "²", "³")
PERIPHERIQUES_WINDOWS = frozenset(
    {"CON", "PRN", "AUX", "NUL", "CONIN$", "CONOUT$"}
    | {f"COM{indice}" for indice in _INDICES_PERIPHERIQUES}
    | {f"LPT{indice}" for indice in _INDICES_PERIPHERIQUES}
)


class AudioEnErreur(Exception):
    """Erreur de lecture ou de décodage propre à un fichier audio.

    Une erreur ne concerne qu'un fichier : la liste et les lots d'exécution
    continuent avec les suivants. Les messages ne contiennent que le nom du
    fichier, jamais son chemin absolu ni de trace d'exception.
    """


class AudioIllisible(AudioEnErreur):
    """Fichier impossible à ouvrir, à lire ou à décoder."""


class DureeDecodeeNulle(AudioEnErreur):
    """Fichier décodé sans aucun échantillon : aucun RTF n'est calculable."""


@dataclass(frozen=True)
class AudioListe:
    """Entrée de la liste des audios d'entrée.

    `duree_indicative` vaut `None` si l'en-tête du conteneur ne l'annonce pas :
    elle n'est jamais déduite du décodage ni remplacée par zéro. `erreur` est
    renseignée pour un fichier présent mais illisible, ou au bon format mais
    dont le nom est refusé, avec une durée indicative absente ; une entrée avec
    erreur n'est jamais proposée à une exécution.
    """

    nom: str
    format: str
    taille_octets: int | None
    duree_indicative: float | None
    erreur: str | None = None


@dataclass(frozen=True, eq=False)
class AudioDecode:
    """Audio décodé, prêt pour tous les moteurs.

    `signal` est un vecteur `float32` mono à `frequence` Hz, en lecture seule
    pour qu'aucun adaptateur ne modifie le tampon partagé. `duree_decodee`
    (`echantillons / frequence`) est la seule référence du RTF ;
    `duree_indicative` ne sert qu'à l'affichage et à la comparaison. `eq=False` :
    l'égalité porte sur l'identité de l'objet, un tableau numpy n'ayant pas de
    valeur de vérité utilisable.
    """

    nom: str
    format: str
    taille_octets: int
    empreinte_sha256: str
    duree_indicative: float | None
    duree_decodee: float
    echantillons: int
    frequence: int
    temps_decodage: float
    signal: np.ndarray


def lister_audios(donnees: Path | str | None = None) -> tuple[AudioListe, ...]:
    """Liste les audios du dossier d'entrée, erreurs de lecture comprises.

    Les entrées sont triées par nom. Seules les entrées dont le nom a un format
    accepté sont examinées : celles dont la cible est un fichier ordinaire
    confiné au dossier autorisé sont décrites, les autres (séparateur, `:`,
    périphérique réservé Windows, lien symbolique sortant) restent listées avec
    l'erreur `ERREUR_NOM_REFUSE` et ne sont donc jamais proposées à une
    exécution. Un répertoire, même nommé comme un audio, n'est pas listé : ce
    n'est pas un audio. Une erreur inattendue sur un fichier ne fait pas échouer
    la liste : elle donne une erreur de lecture générique pour ce seul fichier.
    Un dossier d'entrée absent donne une liste vide sans être créé ; une erreur
    d'accès au dossier (`PermissionError`, par exemple) est propagée à
    l'appelant, qui l'affiche. Aucun signal n'est décodé : seule la durée
    indicative annoncée par l'en-tête est relevée.
    """
    dossier = _dossier_entree(donnees)
    try:
        entrees = sorted(dossier.iterdir(), key=lambda entree: entree.name)
    except (FileNotFoundError, NotADirectoryError):
        return ()

    audios: list[AudioListe] = []
    for entree in entrees:
        format_audio = _format_accepte(entree.name)
        if format_audio is None:
            continue
        try:
            est_repertoire = entree.is_dir()
        except OSError:
            est_repertoire = False  # lien illisible : traité plus bas, listé en erreur
        if est_repertoire:
            # Un répertoire n'est pas un audio à lister.
            continue
        try:
            chemin, format_audio = _chemin_audio(entree.name, donnees)
        except ValeurRefusee:
            audios.append(_entree_refusee(entree.name, format_audio, ERREUR_NOM_REFUSE))
            continue
        except Exception:
            # Un fichier ne doit jamais interrompre la liste des autres :
            # l'erreur reste locale et son message ne cite que le nom.
            audios.append(
                _entree_refusee(
                    entree.name, format_audio, f"lecture impossible : {entree.name}"
                )
            )
            continue
        audios.append(_decrire_audio(entree.name, format_audio, chemin))
    return tuple(audios)


def decoder_audio(nom: str, donnees: Path | str | None = None) -> AudioDecode:
    """Décode `nom` en `float32` 16 kHz mono, avec empreinte et mesures.

    Lève `ValeurRefusee` si le nom sort du dossier autorisé, n'a pas un format
    accepté, désigne un périphérique réservé Windows ou n'est pas un fichier
    ordinaire ; `AudioIllisible` si le fichier ne peut pas être lu ou décodé ;
    `DureeDecodeeNulle` si aucun échantillon n'est produit.

    Le SHA-256 porte sur les octets du fichier source et son calcul est exclu du
    temps de décodage, qui couvre l'ouverture, le décodage et le
    rééchantillonnage. Les erreurs PyAV et système sont converties en
    `AudioIllisible` dont le message ne cite que le nom du fichier.
    """
    chemin, format_audio = _chemin_audio(nom, donnees)
    taille_octets = _taille(chemin, nom)
    empreinte = _empreinte_sha256(chemin, nom)

    debut = time.perf_counter()
    try:
        with av.open(str(chemin)) as conteneur:
            duree_indicative = _duree_indicative(conteneur)
            signal, echantillons = _decoder_signal(conteneur, nom)
    except (av.FFmpegError, OSError) as erreur:
        raise AudioIllisible(
            f"lecture impossible : {nom} ({_explication(erreur)})"
        ) from None
    temps_decodage = time.perf_counter() - debut

    if echantillons == 0:
        raise DureeDecodeeNulle(
            f"durée décodée nulle : {nom} "
            "(aucun échantillon décodé, aucun RTF calculable)"
        )
    signal.flags.writeable = False
    return AudioDecode(
        nom=nom,
        format=format_audio,
        taille_octets=taille_octets,
        empreinte_sha256=empreinte,
        duree_indicative=duree_indicative,
        duree_decodee=echantillons / FREQUENCE_DECODAGE,
        echantillons=echantillons,
        frequence=FREQUENCE_DECODAGE,
        temps_decodage=temps_decodage,
        signal=signal,
    )


def _decoder_signal(
    conteneur: av.container.InputContainer, nom: str
) -> tuple[np.ndarray, int]:
    """Décode le premier flux audio en vecteur `float32` mono rééchantillonné."""
    if not conteneur.streams.audio:
        raise AudioIllisible(f"lecture impossible : {nom} (aucun flux audio)")
    resampler = av.AudioResampler(
        format=FORMAT_ECHANTILLONS_DECODAGE,
        layout=DISPOSITION_DECODAGE,
        rate=FREQUENCE_DECODAGE,
    )
    blocs: list[np.ndarray] = []
    echantillons = 0
    for trame in conteneur.decode(audio=0):
        for sortie in resampler.resample(trame):
            blocs.append(_bloc_vers_vecteur(sortie))
            echantillons += sortie.samples
    for sortie in resampler.resample(None):
        blocs.append(_bloc_vers_vecteur(sortie))
        echantillons += sortie.samples
    if not blocs:
        return np.zeros(0, dtype=np.float32), 0
    return np.concatenate(blocs).astype(np.float32, copy=False), echantillons


def _bloc_vers_vecteur(trame: av.AudioFrame) -> np.ndarray:
    """Convertit une trame mono en vecteur 1-D `float32`."""
    return trame.to_ndarray().reshape(-1).astype(np.float32, copy=False)


def _duree_indicative(conteneur: av.container.InputContainer) -> float | None:
    """Lit la durée annoncée par l'en-tête, en secondes, ou `None`.

    Le conteneur est prioritaire ; à défaut, la durée du flux audio est
    convertie par sa base de temps. Une valeur absente ou négative reste
    inconnue : elle n'est jamais remplacée par zéro.
    """
    if conteneur.duration is not None and conteneur.duration > 0:
        return conteneur.duration / av.time_base
    for flux in conteneur.streams.audio:
        if flux.duration is not None and flux.time_base is not None:
            if flux.duration > 0:
                return float(flux.duration * flux.time_base)
    return None


def _entree_refusee(nom: str, format_audio: str, erreur: str) -> AudioListe:
    """Entrée de liste au nom refusé : ni taille ni durée, seulement l'erreur."""
    return AudioListe(
        nom=nom,
        format=format_audio,
        taille_octets=None,
        duree_indicative=None,
        erreur=erreur,
    )


def _entree_illisible(
    nom: str, format_audio: str, taille_octets: int, erreur: str
) -> AudioListe:
    """Entrée de liste illisible : la taille connue reste affichée."""
    return AudioListe(
        nom=nom,
        format=format_audio,
        taille_octets=taille_octets,
        duree_indicative=None,
        erreur=erreur,
    )


def _decrire_audio(nom: str, format_audio: str, chemin: Path) -> AudioListe:
    """Décrit un fichier pour la liste, sans propager ses erreurs de lecture."""
    try:
        taille = chemin.stat().st_size
    except OSError as erreur:
        return _entree_refusee(
            nom,
            format_audio,
            f"lecture impossible : {nom} ({_explication(erreur)})",
        )
    try:
        with av.open(str(chemin)) as conteneur:
            if not conteneur.streams.audio:
                raise AudioIllisible(f"lecture impossible : {nom} (aucun flux audio)")
            duree = _duree_indicative(conteneur)
    except AudioIllisible as erreur:
        return _entree_illisible(nom, format_audio, taille, str(erreur))
    except (av.FFmpegError, OSError) as erreur:
        return _entree_illisible(
            nom,
            format_audio,
            taille,
            f"lecture impossible : {nom} ({_explication(erreur)})",
        )
    except Exception:
        # Signalé sans détail : un incident imprévu de PyAV ne doit ni
        # interrompre la liste ni exposer de trace dans la page.
        return _entree_illisible(
            nom, format_audio, taille, f"lecture impossible : {nom}"
        )
    return AudioListe(
        nom=nom,
        format=format_audio,
        taille_octets=taille,
        duree_indicative=duree,
    )


def _chemin_audio(nom: str, donnees: Path | str | None) -> tuple[Path, str]:
    """Résout un nom d'audio admis et renvoie son chemin et son format.

    Le format doit être accepté, le nom ne doit contenir aucun séparateur `/`
    (un audio est un fichier du dossier d'entrée, jamais un sous-dossier) ni
    désigner un périphérique réservé Windows ; le chemin est ensuite résolu par
    les contrôles de `paths` (`ValeurRefusee` pour un chemin absolu, `..`, un
    séparateur `\\` ou `:`, ou un lien symbolique sortant) puis vérifié comme
    fichier ordinaire.
    """
    format_audio = _format_accepte(nom)
    if format_audio is None:
        raise ValeurRefusee(
            f"audio refusé : format non accepté ({nom!r}) ; formats acceptés : "
            f"{', '.join(FORMATS_AUDIO)}"
        )
    if "/" in nom:
        raise ValeurRefusee(
            f"audio refusé : nom de fichier du dossier d'entrée attendu, sans "
            f"sous-dossier ({nom!r})"
        )
    if _est_peripherique_windows(nom):
        raise ValeurRefusee(
            f"audio refusé : nom de périphérique réservé Windows ({nom!r})"
        )
    chemin = resoudre_audio(nom, donnees)
    if not chemin.is_file():
        raise ValeurRefusee(
            f"audio refusé : fichier ordinaire attendu sous le dossier "
            f"d'entrée ({nom!r})"
        )
    return chemin, format_audio


def _format_accepte(nom: str) -> str | None:
    """Renvoie l'extension acceptée en minuscules, ou `None`."""
    if not isinstance(nom, str):
        return None
    base, separateur, extension = nom.rpartition(".")
    if not separateur or not base:
        return None
    extension = extension.lower()
    return extension if extension in FORMATS_AUDIO else None


def _est_peripherique_windows(nom: str) -> bool:
    """Vrai si le nom vise un périphérique réservé Windows, extension comprise."""
    if not isinstance(nom, str):
        return False
    base = nom.split(".", 1)[0].strip().rstrip(" ").upper()
    return base in PERIPHERIQUES_WINDOWS


def _empreinte_sha256(chemin: Path, nom: str) -> str:
    """SHA-256 des octets du fichier source, lu par blocs."""
    empreinte = hashlib.sha256()
    try:
        with chemin.open("rb") as fichier:
            while bloc := fichier.read(TAILLE_BLOC_EMPREINTE):
                empreinte.update(bloc)
    except OSError as erreur:
        raise AudioIllisible(
            f"lecture impossible : {nom} ({_explication(erreur)})"
        ) from None
    return empreinte.hexdigest()


def _taille(chemin: Path, nom: str) -> int:
    """Taille du fichier en octets, ou erreur de lecture explicite."""
    try:
        return chemin.stat().st_size
    except OSError as erreur:
        raise AudioIllisible(
            f"lecture impossible : {nom} ({_explication(erreur)})"
        ) from None


def _explication(erreur: BaseException) -> str:
    """Texte court de l'erreur, sans chemin absolu ni trace d'exception."""
    texte = getattr(erreur, "strerror", None)
    return texte if texte else type(erreur).__name__


def _dossier_entree(donnees: Path | str | None) -> Path:
    """Dossier d'entrée `data/audio` (ou `donnees/audio` pour les tests)."""
    racine = DOSSIER_DATA if donnees is None else Path(donnees)
    return racine / NOM_DOSSIER_AUDIO
