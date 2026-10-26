"""Runner du processus moteur : job, chargement unique, audios, mesures.

Le serveur lance ce script dans l'environnement du moteur (design D5) :

    python engines/runner.py job.json

Le runner lit le job, résout le moteur et la famille dans le registre, charge le
modèle une seule fois, traite les audios un par un et émet des événements
préfixés sur stdout (`engines.protocole`). Il n'écrit aucun résultat : le
serveur seul écrit `run.json` et les résultats d'audios (tâches 6.3 et 6.4).

Le runner n'importe ni Flask ni aucun module du serveur. Il importe `numpy`
et, sous Windows seulement, `psutil` à l'exécution : les environnements de
moteur devront donc fournir leurs propres dépendances, numpy compris (tâches
4.4 et 8.x), et ne pas s'appuyer sur celui du serveur.

Job (JSON UTF-8). Les chemins sont absolus ou relatifs au dossier du job :

    {
      "version": 1,
      "moteur": "faster-whisper",
      "famille": "whisper",
      "modele": {"identifiant": "org/nom", "revision": "abc", "chemin": "..."},
      "threads_demandes": 8,
      "reglages": {},
      "format_audio": "float32le-16000-mono",
      "audios": [{"nom": "consultation.wav", "chemin": "audio-0.f32"}]
    }

Chaque audio est un signal brut `float32` little-endian, 16 kHz, mono, déjà
décodé par le serveur (tâche 6.1) : le runner ne décode rien. Sans mécanisme
natif déclaré et vérifié, il découpe l'audio en fenêtres fixes de 30 s sans
recouvrement, concatène les textes et décale les horodatages.

Options de chargement forcées (tâche 5.5) : avant d'appeler `charger`, le runner
copie le dictionnaire `modele` et y impose `local_files_only=True` et
`trust_remote_code=False`. Un job qui fournit les valeurs contraires ne peut
donc pas les désactiver, et le dictionnaire du job n'est jamais modifié. Les
adaptateurs réels des tâches 8.x consommeront ces options aux API concernées ;
aucun adaptateur réel n'est écrit ni qualifié CPU ici. L'exécution est entourée
de `HF_HUB_OFFLINE=1` dans le processus du runner, avec restauration de la
valeur précédente à la sortie : l'environnement du serveur n'est jamais muté.

Contrat d'adaptateur, volontairement minimal (aucun framework) :

    charger(modele, threads_demandes, reglages) -> objet opaque
    transcrire(moteur, signal, taux_echantillonnage, reglages) -> dict

`signal` est un `numpy.ndarray` float32 en lecture seule (toute tentative de
modification lève) et `reglages` un dictionnaire en lecture seule. Le résultat
est un dict avec `texte` (obligatoire) et, en option, `segments` (liste de dicts
avec `debut_s`, `fin_s`, `texte`),
`reglages_effectifs` (dict), `langue_imposee` (texte ou `None`) et
`threads_appliques` (entier ou `None`, seulement si l'API du moteur permet de le
relire). Aucune clé inconnue n'est acceptée : le contrat est explicite. Ces
trois métadonnées doivent être **identiques pour toutes les fenêtres d'un même
audio** : la première valeur est conservée et toute divergence met l'audio en
erreur.

Mesures : durées en secondes, mémoire en octets. Le pic de mémoire est le pic
résident du processus depuis son démarrage (cumulatif), relevé après le
chargement puis après chaque audio : `resource.getrusage().ru_maxrss * 1024`
sous Linux (Kio vers octets) et `psutil.Process().memory_info().peak_wset` sous
Windows (octets, psutil 7.2.2). Si ce champ manque, la mesure est absente
(`None`) : aucun repli inventé.

Moteur factice (tâche 4.3) : seule une déclaration portant `factice=True`, fixée
par le code du dépôt et jamais par le job, est exécutée malgré des familles non
qualifiées. Ses mesures ne sont pas des mesures du runner : elles sont
remplacées par des valeurs simulées déterministes (`DUREE_CHARGEMENT_SIMULEE_S`,
`RTF_SIMULE`, `FACTEUR_TEMPS_CPU_SIMULE`, `PIC_MEMOIRE_SIMULE_OCTETS`), sans
aucune prétention de représentativité d'un PC. Ces constantes ne servent qu'à
exercer le protocole et la durée décodée de l'audio, elle, reste réelle. Chaque
événement porte `factice` et `mesures_simulees` à `True` ; un moteur réel émet
ces deux champs à `False`.

Codes de sortie : 0 exécution terminée (même avec des audios en erreur),
2 job invalide, 3 moteur refusé ou chargement du modèle impossible.
"""

from __future__ import annotations

import json
import os
import sys
import time
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType, ModuleType
from typing import Any

import numpy as np

if __name__ == "__main__" and not __package__:
    # `python engines/runner.py` : la racine du dépôt est calculée depuis
    # `__file__`, jamais depuis le job ni `PYTHONPATH`, pour importer `engines`.
    _RACINE_PROJET = Path(__file__).resolve().parent.parent
    if str(_RACINE_PROJET) not in sys.path:
        sys.path.insert(0, str(_RACINE_PROJET))

from engines.declarations import (
    DeclarationAdaptateur,
    Famille,
    motif_famille_non_executable,
)
from engines.hors_ligne import mode_hors_ligne, options_modele
from engines.protocole import (
    TYPE_AUDIO,
    TYPE_AUDIO_ERREUR,
    TYPE_CHARGEMENT,
    TYPE_FIN,
    emettre,
)
from engines.registre import (
    AdaptateurIndisponible,
    MoteurInconnu,
    RegistreMoteurs,
    creer_registre_fourni,
)

VERSION_JOB = 1
FORMAT_AUDIO = "float32le-16000-mono"
TAUX_ECHANTILLONNAGE = 16000
FENETRE_SECONDES = 30
ECHANTILLONS_PAR_FENETRE = FENETRE_SECONDES * TAUX_ECHANTILLONNAGE

CHAMPS_RESULTAT_OBLIGATOIRES = ("texte",)
CHAMPS_RESULTAT_FACULTATIFS = (
    "segments",
    "reglages_effectifs",
    "langue_imposee",
    "threads_appliques",
)

# Mesures simulées du moteur factice : valeurs arbitraires, constantes et
# cohérentes entre elles (rtf = transcription / durée réelle). Elles n'ont
# aucune valeur de mesure PC et ne sont jamais présentées comme telles.
DUREE_CHARGEMENT_SIMULEE_S = 1.2
RTF_SIMULE = 0.5
FACTEUR_TEMPS_CPU_SIMULE = 1.5
PIC_MEMOIRE_SIMULE_OCTETS = 314572800


class ErreurJob(ValueError):
    """Job absent, illisible ou invalide (code de sortie 2)."""


class ErreurMoteur(RuntimeError):
    """Moteur inconnu, famille non qualifiée ou chargement impossible (code 3)."""


class ErreurAudio(RuntimeError):
    """Échec d'un audio : il est signalé et le lot continue."""


@dataclass(frozen=True)
class AudioJob:
    """Audio brut à transcrire, dans l'ordre du lot."""

    nom: str
    chemin: Path


@dataclass(frozen=True)
class Job:
    """Requête d'exécution lue depuis `job.json`."""

    moteur: str
    famille: str
    modele: dict[str, Any]
    threads_demandes: int
    reglages: dict[str, Any]
    audios: tuple[AudioJob, ...]


def charger_job(chemin: str | Path) -> Job:
    """Lit et valide un job, en résolvant ses chemins depuis son dossier."""
    chemin_job = Path(chemin).resolve()
    try:
        contenu = json.loads(chemin_job.read_text(encoding="utf-8"))
    except OSError as exception:
        raise ErreurJob(f"job illisible ({chemin_job}) : {exception}") from exception
    except json.JSONDecodeError as exception:
        raise ErreurJob(f"job JSON invalide ({chemin_job}) : {exception}") from exception
    if not isinstance(contenu, dict):
        raise ErreurJob("le job doit être un objet JSON")
    if contenu.get("version") != VERSION_JOB:
        raise ErreurJob(f"version de job attendue : {VERSION_JOB}")
    if contenu.get("format_audio") != FORMAT_AUDIO:
        raise ErreurJob(f"format audio attendu : {FORMAT_AUDIO!r}")
    base = chemin_job.parent
    moteur = _texte(contenu, "moteur")
    famille = _texte(contenu, "famille")
    modele = _modele(contenu.get("modele"), base)
    threads_demandes = _entier_positif(contenu, "threads_demandes")
    reglages = contenu.get("reglages", {})
    if not isinstance(reglages, dict):
        raise ErreurJob("'reglages' doit être un objet JSON")
    audios = _audios(contenu.get("audios"), base)
    return Job(
        moteur=moteur,
        famille=famille,
        modele=modele,
        threads_demandes=threads_demandes,
        reglages=dict(reglages),
        audios=audios,
    )


def executer(
    job: Job,
    registre: RegistreMoteurs | None = None,
) -> None:
    """Exécute un job et émet ses événements sur stdout.

    Lève `ErreurMoteur` avant tout événement si le moteur, la famille ou
    l'adaptateur ne convient pas, ou si le chargement du modèle échoue. Un échec
    d'audio est émis en `audio_erreur` et le lot continue.

    L'import de l'adaptateur et toute l'exécution ont lieu sous
    `HF_HUB_OFFLINE=1` ; la valeur précédente est restaurée à la sortie, même
    pour un appelant de test partageant le processus.
    """
    registre = creer_registre_fourni() if registre is None else registre
    with mode_hors_ligne():
        _executer_job(job, registre)


def _executer_job(job: Job, registre: RegistreMoteurs) -> None:
    """Corps de l'exécution, sous le mode hors ligne forcé par `executer`."""
    adaptateur, declaration = _charger_adaptateur(job, registre)
    factice = declaration.factice
    provenance = {"factice": factice, "mesures_simulees": factice}
    reglages = MappingProxyType(job.reglages)

    debut_chargement = time.perf_counter()
    try:
        moteur = adaptateur.charger(
            options_modele(job.modele), job.threads_demandes, reglages
        )
    except Exception as exception:  # l'erreur exacte du moteur reste visible
        raise ErreurMoteur(
            f"chargement du modèle impossible : {exception}"
        ) from exception
    duree_chargement = time.perf_counter() - debut_chargement
    pic_chargement = pic_memoire()
    if factice:
        # Les compteurs réels ne sont jamais émis pour le factice.
        duree_chargement = DUREE_CHARGEMENT_SIMULEE_S
        pic_chargement = PIC_MEMOIRE_SIMULE_OCTETS
    emettre(
        {
            "type": TYPE_CHARGEMENT,
            "duree_s": duree_chargement,
            "pic_memoire_octets": pic_chargement,
            **provenance,
        }
    )

    audios_ok = 0
    audios_erreur = 0
    for index, audio in enumerate(job.audios):
        try:
            evenement = _traiter_audio(
                index,
                audio,
                adaptateur,
                moteur,
                job.threads_demandes,
                reglages,
                factice,
            )
        except Exception as exception:  # un audio en erreur ne bloque pas le lot
            audios_erreur += 1
            emettre(
                {
                    "type": TYPE_AUDIO_ERREUR,
                    "index": index,
                    "nom": audio.nom,
                    "erreur": str(exception) or type(exception).__name__,
                    **provenance,
                }
            )
            continue
        audios_ok += 1
        emettre(evenement)

    emettre(
        {
            "type": TYPE_FIN,
            "duree_chargement_s": duree_chargement,
            "pic_memoire_octets": (
                PIC_MEMOIRE_SIMULE_OCTETS if factice else pic_memoire()
            ),
            "audios_ok": audios_ok,
            "audios_erreur": audios_erreur,
            **provenance,
        }
    )


def pic_memoire() -> int | None:
    """Pic de mémoire résidente du processus depuis son démarrage, en octets."""
    if os.name == "nt":
        return _pic_memoire_windows()
    return _pic_memoire_unix()


def _pic_memoire_unix() -> int | None:
    """`ru_maxrss` est en Kio sous Linux (macOS hors périmètre : octets)."""
    try:
        import resource

        return int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss) * 1024
    except (ImportError, OSError, ValueError, AttributeError):
        return None


def _pic_memoire_windows() -> int | None:
    """`peak_wset` en octets sous Windows (psutil 7.2.2) ; sinon mesure absente."""
    try:
        import psutil

        memoire = psutil.Process().memory_info()
    except Exception:  # une mesure absente ne doit jamais faire échouer le lot
        return None
    pic = getattr(memoire, "peak_wset", None)
    return None if pic is None else int(pic)


def main(argv: list[str] | None = None) -> int:
    """Point d'entrée du processus moteur : un seul argument, le job."""
    arguments = list(sys.argv[1:] if argv is None else argv)
    if len(arguments) != 1:
        print("usage : python engines/runner.py job.json", file=sys.stderr)
        return 2
    _configurer_stdout()
    try:
        executer(charger_job(arguments[0]))
    except ErreurJob as exception:
        print(f"job invalide : {exception}", file=sys.stderr)
        return 2
    except ErreurMoteur as exception:
        print(f"moteur indisponible : {exception}", file=sys.stderr)
        return 3
    return 0


def _configurer_stdout() -> None:
    """Sortie standard en UTF-8 : les textes non ASCII ne dépendent pas de la
    page de codes de la console Windows ; les caractères imprévus sont échappés."""
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    except (AttributeError, ValueError):
        pass


def _charger_adaptateur(
    job: Job, registre: RegistreMoteurs
) -> tuple[ModuleType, DeclarationAdaptateur]:
    """Résout la déclaration, vérifie la qualification, puis importe l'adaptateur."""
    try:
        declaration = registre.obtenir(job.moteur)
    except MoteurInconnu:
        raise ErreurMoteur(f"moteur inconnu : {job.moteur!r}") from None
    famille = next(
        (
            candidate
            for candidate in declaration.familles
            if candidate.identifiant == job.famille
        ),
        None,
    )
    if famille is None:
        raise ErreurMoteur(
            f"famille {job.famille!r} non déclarée pour le moteur {job.moteur!r}"
        )
    _verifier_famille(job, famille, declaration)
    try:
        adaptateur = registre.charger_adaptateur(job.moteur)
    except AdaptateurIndisponible as exception:
        raise ErreurMoteur(str(exception)) from exception
    for nom in ("charger", "transcrire"):
        if not callable(getattr(adaptateur, nom, None)):
            raise ErreurMoteur(
                f"adaptateur incomplet pour {job.moteur!r} : {nom}() manquant"
            )
    return adaptateur, declaration


def _verifier_famille(
    job: Job, famille: Famille, declaration: DeclarationAdaptateur
) -> None:
    """Refuse une famille non qualifiée et un mécanisme natif non pris en charge.

    La règle elle-même vit dans `motif_famille_non_executable`, seule source
    partagée avec le service des demandes d'exécution : l'interface n'annonce
    donc jamais comme exécutable une famille que ce runner refuse. Aucune
    famille fournie n'est qualifiée sur PC : les trois moteurs réels sont donc
    refusés tant que le jalon PC et les tâches 8.x ne l'ont pas prouvé. Seul le
    moteur factice, marqué `factice=True` dans sa déclaration, est exécuté sans
    qualification PC : il ne charge aucun modèle et n'effectue aucune inférence,
    ce qui n'est pas une qualification PC. Ce contrôle ne remplace jamais une
    validation sur un PC de test.
    """
    motif = motif_famille_non_executable(declaration, famille)
    if motif is not None:
        raise ErreurMoteur(f"{motif} : exécution refusée")


def _traiter_audio(
    index: int,
    audio: AudioJob,
    adaptateur: ModuleType,
    moteur: Any,
    threads_demandes: int,
    reglages: Mapping[str, Any],
    factice: bool,
) -> dict[str, Any]:
    """Transcrit un audio en fenêtres fixes et renvoie son événement `audio`."""
    # Un fichier brut float32 doit contenir un nombre entier d'échantillons :
    # on refuse avant lecture plutôt que de laisser numpy interpréter un
    # reliquat d'octets.
    taille = audio.chemin.stat().st_size
    if taille % 4 != 0:
        raise ErreurAudio(
            f"taille de fichier non multiple de 4 octets (float32) : {taille} octets"
        )
    # `fromfile` charge tout le signal en mémoire sans mmap : aucun fichier ne
    # reste ouvert, donc aucun retrait de fichier temporaire bloqué sous Windows.
    signal = np.fromfile(audio.chemin, dtype="<f4")
    try:
        if signal.size == 0:
            raise ErreurAudio("durée décodée nulle : aucun échantillon")
        duree_audio = signal.size / TAUX_ECHANTILLONNAGE
        textes: list[str] = []
        segments: list[dict[str, Any]] = []
        reglages_effectifs: dict[str, Any] = {}
        langue_imposee: str | None = None
        threads_appliques: int | None = None
        premiere_fenetre = True
        nb_fenetres = 0
        debut = time.perf_counter()
        cpu_debut = time.process_time()
        for position in range(0, signal.size, ECHANTILLONS_PAR_FENETRE):
            fenetre = signal[position : position + ECHANTILLONS_PAR_FENETRE]
            # Le signal est en lecture seule : l'adaptateur ne peut pas le modifier.
            fenetre.setflags(write=False)
            resultat = _valider_resultat(
                adaptateur.transcrire(
                    moteur, fenetre, TAUX_ECHANTILLONNAGE, reglages
                )
            )
            decalage = position / TAUX_ECHANTILLONNAGE
            textes.append(resultat["texte"].strip())
            segments.extend(_decaller_segments(resultat["segments"], decalage))
            if premiere_fenetre:
                reglages_effectifs = resultat["reglages_effectifs"]
                langue_imposee = resultat["langue_imposee"]
                threads_appliques = resultat["threads_appliques"]
                premiere_fenetre = False
            else:
                _verifier_metadonnees_identiques(
                    resultat, reglages_effectifs, langue_imposee, threads_appliques
                )
            nb_fenetres += 1
            del fenetre
        if factice:
            # Mesures simulées déterministes : les compteurs réels mesurés
            # ci-dessus ne sont ni conservés ni émis.
            duree_transcription = duree_audio * RTF_SIMULE
            temps_cpu = duree_transcription * FACTEUR_TEMPS_CPU_SIMULE
            pic_audio = PIC_MEMOIRE_SIMULE_OCTETS
        else:
            duree_transcription = time.perf_counter() - debut
            temps_cpu = time.process_time() - cpu_debut
            pic_audio = pic_memoire()
        return {
            "type": TYPE_AUDIO,
            "index": index,
            "nom": audio.nom,
            "texte": " ".join(texte for texte in textes if texte),
            "segments": segments,
            "duree_audio_s": duree_audio,
            "duree_transcription_s": duree_transcription,
            "temps_cpu_s": temps_cpu,
            "rtf": duree_transcription / duree_audio,
            "fenetre_s": float(FENETRE_SECONDES),
            "decoupage": "fenetres-fixes",
            "nb_fenetres": nb_fenetres,
            "pic_memoire_octets": pic_audio,
            "reglages_effectifs": reglages_effectifs,
            "langue_imposee": langue_imposee,
            "threads_demandes": threads_demandes,
            "threads_appliques": threads_appliques,
            "factice": factice,
            "mesures_simulees": factice,
        }
    finally:
        # Libère le signal avant l'audio suivant (hygiène mémoire Windows).
        del signal


def _verifier_metadonnees_identiques(
    resultat: dict[str, Any],
    reglages_effectifs: dict[str, Any],
    langue_imposee: str | None,
    threads_appliques: int | None,
) -> None:
    """Un même audio doit rapporter les mêmes métadonnées à chaque fenêtre."""
    divergences = []
    if resultat["reglages_effectifs"] != reglages_effectifs:
        divergences.append("reglages_effectifs")
    if resultat["langue_imposee"] != langue_imposee:
        divergences.append("langue_imposee")
    if resultat["threads_appliques"] != threads_appliques:
        divergences.append("threads_appliques")
    if divergences:
        raise ErreurAudio(
            "métadonnées d'adaptateur divergentes entre les fenêtres du même "
            "audio : " + ", ".join(divergences)
        )


def _valider_resultat(valeur: Any) -> dict[str, Any]:
    """Vérifie le dict renvoyé par l'adaptateur et normalise ses champs."""
    if not isinstance(valeur, dict):
        raise ErreurAudio("résultat d'adaptateur attendu sous forme de dict")
    inconnus = set(valeur) - set(CHAMPS_RESULTAT_OBLIGATOIRES) - set(
        CHAMPS_RESULTAT_FACULTATIFS
    )
    if inconnus:
        raise ErreurAudio(
            f"résultat d'adaptateur avec des clés inconnues : {sorted(inconnus)}"
        )
    if "texte" not in valeur or not isinstance(valeur["texte"], str):
        raise ErreurAudio("résultat d'adaptateur sans 'texte' textuel")
    segments = valeur.get("segments", [])
    if not isinstance(segments, (list, tuple)):
        raise ErreurAudio("'segments' doit être une liste")
    reglages = valeur.get("reglages_effectifs", {})
    if not isinstance(reglages, dict):
        raise ErreurAudio("'reglages_effectifs' doit être un dict")
    langue = valeur.get("langue_imposee")
    if langue is not None and not isinstance(langue, str):
        raise ErreurAudio("'langue_imposee' doit être un texte ou null")
    threads = valeur.get("threads_appliques")
    if threads is not None and (
        not isinstance(threads, int) or isinstance(threads, bool)
    ):
        raise ErreurAudio("'threads_appliques' doit être un entier ou null")
    return {
        "texte": valeur["texte"],
        "segments": _valider_segments(segments),
        "reglages_effectifs": dict(reglages),
        "langue_imposee": langue,
        "threads_appliques": threads,
    }


def _valider_segments(segments: list[Any] | tuple[Any, ...]) -> list[dict[str, Any]]:
    """Copie les segments en exigeant des bornes numériques et un texte."""
    resultat: list[dict[str, Any]] = []
    for segment in segments:
        if not isinstance(segment, dict):
            raise ErreurAudio("segment attendu sous forme de dict")
        if not _est_nombre(segment.get("debut_s")) or not _est_nombre(
            segment.get("fin_s")
        ):
            raise ErreurAudio("segment sans bornes 'debut_s'/'fin_s' numériques")
        if not isinstance(segment.get("texte"), str):
            raise ErreurAudio("segment sans 'texte' textuel")
        resultat.append(dict(segment))
    return resultat


def _decaller_segments(
    segments: list[dict[str, Any]], decalage: float
) -> list[dict[str, Any]]:
    """Décale les horodatages d'une fenêtre vers le temps de l'audio complet."""
    decales = []
    for segment in segments:
        decale = dict(segment)
        decale["debut_s"] = float(segment["debut_s"]) + decalage
        decale["fin_s"] = float(segment["fin_s"]) + decalage
        decales.append(decale)
    return decales


def _est_nombre(valeur: Any) -> bool:
    return isinstance(valeur, (int, float)) and not isinstance(valeur, bool)


def _texte(contenu: dict[str, Any], champ: str) -> str:
    valeur = contenu.get(champ)
    if not isinstance(valeur, str) or not valeur.strip():
        raise ErreurJob(f"'{champ}' doit être un texte non vide")
    return valeur


def _entier_positif(contenu: dict[str, Any], champ: str) -> int:
    valeur = contenu.get(champ)
    if not isinstance(valeur, int) or isinstance(valeur, bool) or valeur < 1:
        raise ErreurJob(f"'{champ}' doit être un entier strictement positif")
    return valeur


def _modele(valeur: Any, base: Path) -> dict[str, Any]:
    if not isinstance(valeur, dict):
        raise ErreurJob("'modele' doit être un objet JSON")
    modele = dict(valeur)
    modele["identifiant"] = _texte(modele, "identifiant")
    modele["chemin"] = str(_chemin(modele.get("chemin"), base, "modele.chemin"))
    return modele


def _audios(valeur: Any, base: Path) -> tuple[AudioJob, ...]:
    if not isinstance(valeur, list) or not valeur:
        raise ErreurJob("'audios' doit être une liste non vide")
    audios = []
    for position, entree in enumerate(valeur):
        if not isinstance(entree, dict):
            raise ErreurJob(f"audio {position} : objet JSON attendu")
        nom = _texte(entree, "nom")
        chemin = _chemin(entree.get("chemin"), base, f"audios[{position}].chemin")
        audios.append(AudioJob(nom=nom, chemin=chemin))
    return tuple(audios)


def _chemin(valeur: Any, base: Path, champ: str) -> Path:
    if not isinstance(valeur, str) or not valeur.strip() or "\x00" in valeur:
        raise ErreurJob(f"'{champ}' doit être un chemin non vide")
    chemin = Path(valeur)
    if not chemin.is_absolute():
        chemin = base / chemin
    return chemin.resolve()


if __name__ == "__main__":
    sys.exit(main())
