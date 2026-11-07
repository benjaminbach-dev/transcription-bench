"""Relevés système du runner : CPU global moyen et RAM disponible (tâche 1.1).

Couture injectable du change `mesurer-charge-systeme` (design D2 et D3). Ce
module vit dans `engines/` parce que son seul consommateur prévu est
`engines/runner.py`, exécuté dans l'environnement du moteur où seule la racine du
dépôt est ajoutée à `sys.path` : il n'importe ni module du serveur ni
bibliothèque de moteur, seulement la bibliothèque standard et `psutil`
(7.2.2, déjà verrouillé dans les environnements). Rien ici n'écrit de fichier,
n'émet d'événement ni ne lance d'inférence : l'intégration aux bornes du runner
est faite en 1.2, la persistance relève des tâches 2.x.

Méthode versionnée (version de méthode 1) : `psutil-cpu-percent-nonbloquant-v1`.
Un relevé CPU est une fenêtre de deux appels à
`psutil.cpu_percent(interval=None, percpu=False)` sur le **même thread** :

1. `amorcer_cpu()` : appel d'amorçage, valeur retournée ignorée ; l'instant
   monotone est lu juste après, parce que psutil enregistre sa référence de
   compteurs à la fin de cet appel ;
2. `lire_cpu()` : instant monotone lu juste avant l'appel de lecture, puis appel
   de lecture, parce que psutil relève les compteurs au début de cet appel.

Aucun appel intermédiaire n'est fait sur ce thread, aucune attente artificielle
n'est introduite pour atteindre le seuil. L'intervalle conservé (`intervalle_s`)
est la durée monotone propre de la fenêtre de relevé, pas celle de l'audio ni du
lot.

Limites assumées :

- l'état non bloquant de psutil est un cache **par identifiant de thread** ; deux
  fenêtres ne partagent rien ici, mais un appel `cpu_percent` fait par une autre
  bibliothèque sur le même thread pendant la fenêtre réinitialiserait le
  compteur. Cette limite est documentée sans garantie de détection : aucun
  contrôle ne permet de distinguer un tel appel d'une mesure normale ;
- seuil documentaire de 0,1 s entre les deux appels (recommandation de psutil) ;
  un intervalle plus court rend la mesure indisponible avec un motif, il n'est
  jamais complété par une attente ;
- 100 % représente tous les processeurs logiques visibles du système. Aucune
  attribution au moteur, aucune part « autres applications » par soustraction
  avec le CPU du moteur, aucune garantie de diagnostic des compteurs : psutil ne
  distingue pas un delta total nul d'une inactivité réelle et corrige certains
  deltas négatifs en interne. Un 0 % retourné après un amorçage valide et un
  intervalle suffisant est donc conservé tel quel ;
- la mémoire vient de `psutil.virtual_memory()` : `total` et `available`
  seulement, jamais `total - free` ni une somme de RSS. Un instantané n'est ni
  un minimum pendant l'audio, ni une consommation attribuable à la
  transcription, ni une prédiction de fluidité.

Décision de validité (D2) : un compteur inexploitable donne une valeur `None` et
un motif stable. Codes écrits par ce module, distincts des états calculés à la
lecture (`absent`, `invalide`, `version_inconnue`, jamais écrits) :

- `lecture_impossible` : exception à l'amorçage, à la lecture ou de l'horloge ;
- `intervalle_trop_court` : intervalle monotone absent, non fini, négatif ou
  inférieur à 0,1 s ;
- `valeur_incoherente` : retour non numérique (booléen exclu), non fini ou hors
  0..100 pour le CPU, ou champs mémoire absents, non entiers ou hors bornes.

Les erreurs brutes d'OS ne sont jamais recopiées dans les objets produits : elles
ne deviennent que ces codes.

Validation additive (tâche 2.1, design D3) : `valider_observation_systeme`
contrôle un objet reçu, quel qu'en soit l'émetteur, et renvoie une copie
normalisée ne portant que les champs du contrat, ou `None` avec un motif court
à journaliser. Elle est employée par le runner avant émission et par la
consignation avant écriture ; un objet invalide n'est jamais persisté et ne
fait jamais échouer l'audio. La provenance attendue est déduite de
`mesures_simulees` (`simulee` si vrai, `reelle` sinon) : toute contradiction
invalide l'objet. Un `intervalle_s` non nul à côté d'un motif est accepté, car
il décrit la fenêtre réellement observée ; la mémoire partielle l'est aussi
(total valide avec seule `available` invalide, motif portant sur
l'instantané). Seules les clés connues sont recopiées : un champ inconnu est
ignoré, jamais persisté.

Les objets produits suivent le contrat D3 (version 1) : `observation_chargement()`
donne l'instantané mémoire du chargement, `observation_audio()` ajoute le relevé
CPU de la fenêtre. La provenance vaut `reelle` par défaut. Le mode factice du
runner n'exécute aucune collecte réelle : `creer_releveur_simule()` fournit le
même parcours (amorçage, lecture, instantanés) avec des valeurs fixes marquées
`simulee`, documentées ci-dessous et reproductibles d'une exécution à l'autre.
"""

from __future__ import annotations

import itertools
import math
import re
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any

import psutil

#: Version du contrat d'objet d'observation système (design D3).
VERSION_METHODE = 1
#: Identifiant de la méthode de relevé CPU employée, pas une promesse de mesure.
METHODE_CPU = "psutil-cpu-percent-nonbloquant-v1"
#: Numéro de version psutil acceptable (court, formaté), jamais un texte libre :
#: ces deux valeurs sont des identifiants de protocole, pas des messages.
_MOTIF_VERSION_PSUTIL = re.compile(r"\d{1,3}(\.\d{1,3}){1,3}[A-Za-z0-9.\-_+]{0,12}")
#: Intervalle monotone minimal, en secondes, entre amorçage et lecture.
INTERVALLE_MINIMUM_S = 0.1

MOTIF_LECTURE_IMPOSSIBLE = "lecture_impossible"
MOTIF_INTERVALLE_TROP_COURT = "intervalle_trop_court"
MOTIF_VALEUR_INCOHERENTE = "valeur_incoherente"
#: Motifs écrits par ce module, à distinguer des états calculés à la lecture.
MOTIFS_ECRITS = (
    MOTIF_LECTURE_IMPOSSIBLE,
    MOTIF_INTERVALLE_TROP_COURT,
    MOTIF_VALEUR_INCOHERENTE,
)

PROVENANCE_REELLE = "reelle"
PROVENANCE_SIMULEE = "simulee"
PROVENANCES = (PROVENANCE_REELLE, PROVENANCE_SIMULEE)

#: Emplacement d'un objet d'observation système : sur l'événement de chargement
#: ou sur celui d'un audio (design D3).
MOMENT_CHARGEMENT = "chargement"
MOMENT_AUDIO = "audio"
MOMENTS = (MOMENT_CHARGEMENT, MOMENT_AUDIO)

#: États calculés à la lecture (tâche 2.2), jamais écrits dans un résultat :
#: une observation absente ou écartée reste distinguable de ces états par
#: l'absence de l'objet, jamais par une valeur enregistrée.
ETATS_LECTURE = ("absent", "invalide", "version_inconnue")

#: Champs du contrat D3, par emplacement. Le relevé de chargement ne porte pas
#: de CPU moyen : un `cpu` qui y figure est hors contrat.
CHAMPS_ENVELOPPE = ("version", "methode_cpu", "version_psutil", "provenance")
CHAMPS_CPU = ("pourcentage_moyen", "intervalle_s", "motif")
CHAMPS_MEMOIRE = ("releve_le", "totale_octets", "disponible_octets", "motif")

#: Scénario simulé du moteur factice (design D2) : valeurs arbitraires fixes,
#: sans aucune valeur de mesure et sans description d'un ordinateur. Elles
#: servent uniquement à exercer le même parcours que le relevé réel.
SIMULATION_CPU_POURCENTAGE = 42.0
SIMULATION_INTERVALLE_CPU_S = 1.0
SIMULATION_MEMOIRE_TOTALE_OCTETS = 8 * 1024**3
SIMULATION_MEMOIRE_DISPONIBLE_OCTETS = 6 * 1024**3
#: Date du scénario : constante reproductible, jamais une lecture d'horloge.
SIMULATION_RELEVE_LE = "1970-01-01T00:00:00+00:00"

#: Sentinelle interne : distingue un champ mémoire absent d'une valeur `None`.
_CHAMP_ABSENT = object()


def horodatage_utc() -> str:
    """Instant ISO 8601 UTC, à la seconde, pour `releve_le` (design D3)."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _est_nombre_fini(valeur: Any) -> bool:
    """Nombre réel fini ; un booléen est exclu bien qu'il soit un `int`.

    Un entier gigantesque n'est pas convertible en flottant : `math.isfinite`
    lève alors `OverflowError`, intercepté ici comme une valeur hors contrat
    (jamais une exception de validation).
    """
    if isinstance(valeur, bool) or not isinstance(valeur, (int, float)):
        return False
    try:
        return math.isfinite(valeur)
    except OverflowError:
        return False


def _est_entier_positif(valeur: Any) -> bool:
    """Entier strictement positif ; booléen exclu."""
    return not isinstance(valeur, bool) and isinstance(valeur, int) and valeur > 0


def _est_entier_naturel(valeur: Any) -> bool:
    """Entier positif ou nul ; booléen exclu."""
    return not isinstance(valeur, bool) and isinstance(valeur, int) and valeur >= 0


def _pourcentage_valide(valeur: Any) -> bool:
    """Retour CPU exploitable : nombre fini dans 0..100, booléen exclu."""
    return _est_nombre_fini(valeur) and 0.0 <= valeur <= 100.0


def _intervalle_releve(debut: Any, fin: Any) -> tuple[float | None, str | None]:
    """Durée monotone de la fenêtre et motif éventuel.

    L'intervalle n'est conservé que s'il est un nombre fini positif ou nul
    (contrat D3) ; un intervalle court mais valide reste consigné, car il décrit
    la fenêtre réellement observée, tandis que le motif dit que le CPU est
    indisponible.
    """
    if not (_est_nombre_fini(debut) and _est_nombre_fini(fin)):
        return None, MOTIF_INTERVALLE_TROP_COURT
    intervalle = float(fin) - float(debut)
    if not math.isfinite(intervalle) or intervalle < 0.0:
        return None, MOTIF_INTERVALLE_TROP_COURT
    if intervalle < INTERVALLE_MINIMUM_S:
        return intervalle, MOTIF_INTERVALLE_TROP_COURT
    return intervalle, None


def _resultat_cpu(
    pourcentage: float | None, intervalle: float | None, motif: str | None
) -> dict[str, Any]:
    """Sous-objet `cpu` du contrat D3."""
    return {
        "pourcentage_moyen": pourcentage,
        "intervalle_s": intervalle,
        "motif": motif,
    }


def provenance_attendue(mesures_simulees: Any) -> str:
    """Provenance exigée par un événement ou un résultat (design D3).

    `simulee` si `mesures_simulees` vaut explicitement vrai, `reelle` sinon :
    une valeur d'un autre type est traitée comme non simulée, jamais comme une
    provenance implicite.
    """
    return PROVENANCE_SIMULEE if mesures_simulees is True else PROVENANCE_REELLE


def _horodatage_valide(valeur: Any) -> bool:
    """Texte ISO 8601 interprétable : jamais un message d'erreur d'OS recopié."""
    if not isinstance(valeur, str) or not valeur.strip():
        return False
    try:
        instant = datetime.fromisoformat(valeur)
    except ValueError:
        return False
    # D3 : un instant ISO UTC ; une date seule ou sans décalage nul est refusée.
    return instant.tzinfo is not None and instant.utcoffset() == timedelta(0)


def _champs_manquants(objet: Mapping[str, Any], champs: tuple[str, ...]) -> list[str]:
    """Champs du contrat absents de l'objet reçu."""
    return [champ for champ in champs if champ not in objet]


def _valider_memoire(objet: Any) -> tuple[dict[str, Any] | None, str | None]:
    """Sous-objet `memoire_apres` conforme (D3), ou `(None, motif)`.

    Une mémoire partielle est acceptée : un champ valide reste conservé même si
    l'autre manque. En revanche, un motif accompagne toujours une valeur
    manquante, et une valeur complète n'a jamais de motif.
    """
    if not isinstance(objet, Mapping):
        return None, "mémoire après mesure non conforme"
    manquants = _champs_manquants(objet, CHAMPS_MEMOIRE)
    if manquants:
        return None, "mémoire après mesure incomplète"
    releve_le = objet["releve_le"]
    totale = objet["totale_octets"]
    disponible = objet["disponible_octets"]
    motif = objet["motif"]
    if not _horodatage_valide(releve_le):
        return None, "instant de la mémoire après mesure non conforme"
    if totale is not None and not _est_entier_positif(totale):
        return None, "mémoire totale hors contrat"
    if disponible is not None and not _est_entier_naturel(disponible):
        return None, "mémoire disponible hors contrat"
    if totale is not None and disponible is not None and disponible > totale:
        return None, "mémoire disponible supérieure à la mémoire totale"
    if totale is None and disponible is not None:
        return None, "mémoire disponible sans mémoire totale"
    if motif is not None and motif not in MOTIFS_ECRITS:
        return None, "motif de mémoire hors contrat"
    if motif is None and (totale is None or disponible is None):
        return None, "mémoire après mesure incomplète sans motif"
    if motif is not None and totale is not None and disponible is not None:
        return None, "motif de mémoire alors que la mesure est complète"
    return (
        {
            "releve_le": releve_le,
            "totale_octets": totale,
            "disponible_octets": disponible,
            "motif": motif,
        },
        None,
    )


def _valider_cpu(objet: Any) -> tuple[dict[str, Any] | None, str | None]:
    """Sous-objet `cpu` conforme (D3), ou `(None, motif)`.

    `intervalle_s` reste consigné à côté d'un motif lorsqu'il décrit la fenêtre
    réellement observée (fenêtre trop courte) : c'est le CPU qui est
    indisponible, pas la durée observée.
    """
    if not isinstance(objet, Mapping):
        return None, "relevé CPU non conforme"
    manquants = _champs_manquants(objet, CHAMPS_CPU)
    if manquants:
        return None, "relevé CPU incomplet"
    pourcentage = objet["pourcentage_moyen"]
    intervalle = objet["intervalle_s"]
    motif = objet["motif"]
    if pourcentage is not None and not _pourcentage_valide(pourcentage):
        return None, "pourcentage CPU hors de 0 à 100"
    if intervalle is not None and not (
        _est_nombre_fini(intervalle) and intervalle >= 0.0
    ):
        return None, "intervalle CPU hors contrat"
    if motif is not None and motif not in MOTIFS_ECRITS:
        return None, "motif CPU hors contrat"
    if motif is None and (pourcentage is None or intervalle is None):
        return None, "relevé CPU incomplet sans motif"
    if motif is not None and pourcentage is not None:
        return None, "motif CPU alors qu'un pourcentage est présent"
    # D2 recroisé à la validation : sans motif, la fenêtre doit atteindre le
    # seuil ; le motif d'intervalle trop court doit décrire une fenêtre
    # réellement sous le seuil (absente ou courte).
    if motif is None and intervalle < INTERVALLE_MINIMUM_S:
        return None, "intervalle CPU sous le seuil minimal sans motif"
    if (
        motif == MOTIF_INTERVALLE_TROP_COURT
        and intervalle is not None
        and intervalle >= INTERVALLE_MINIMUM_S
    ):
        return None, "motif d'intervalle trop court pour une fenêtre suffisante"
    return (
        {
            "pourcentage_moyen": (
                float(pourcentage) if pourcentage is not None else None
            ),
            "intervalle_s": float(intervalle) if intervalle is not None else None,
            "motif": motif,
        },
        None,
    )


def valider_observation_systeme(
    objet: Any, *, moment: str, mesures_simulees: Any
) -> tuple[dict[str, Any] | None, str | None]:
    """Objet d'observation système conforme (D3), ou `(None, motif)`.

    `moment` vaut `MOMENT_CHARGEMENT` ou `MOMENT_AUDIO` ; la provenance attendue
    est déduite de `mesures_simulees`. La copie renvoyée ne contient que les
    champs du contrat, dans leur ordre de définition : un objet valide reçu d'un
    émetteur tiers ne peut donc pas faire entrer de champ inconnu dans un
    résultat persisté. Aucun motif renvoyé ne recopie de valeur reçue ni de
    message d'erreur d'OS : il est destiné au journal, jamais au fichier.
    """
    if moment not in MOMENTS:
        raise ValueError(f"emplacement inconnu : {moment!r}")
    if not isinstance(objet, Mapping):
        return None, "relevé système non conforme"
    manquants = _champs_manquants(objet, CHAMPS_ENVELOPPE)
    if manquants:
        return None, "relevé système incomplet"
    version = objet["version"]
    if isinstance(version, bool) or not isinstance(version, int):
        return None, "version de relevé système non entière"
    if version != VERSION_METHODE:
        return None, "version de relevé système non prise en charge"
    # Version 1 : l'identifiant de méthode est fixe et la version de psutil est
    # un court numéro formaté — jamais de texte libre ni de message d'OS (D3).
    methode = objet["methode_cpu"]
    if methode != METHODE_CPU:
        return None, "méthode CPU hors contrat"
    version_psutil = objet["version_psutil"]
    if not isinstance(version_psutil, str) or not _MOTIF_VERSION_PSUTIL.fullmatch(
        version_psutil
    ):
        return None, "version de psutil hors contrat"
    provenance = objet["provenance"]
    if provenance not in PROVENANCES:
        return None, "provenance de relevé système inconnue"
    if provenance != provenance_attendue(mesures_simulees):
        return None, "provenance contradictoire avec la simulation"
    normalise: dict[str, Any] = {
        "version": VERSION_METHODE,
        "methode_cpu": methode,
        "version_psutil": version_psutil,
        "provenance": provenance,
    }
    if moment == MOMENT_AUDIO:
        if "cpu" not in objet:
            return None, "relevé CPU absent d'un relevé d'audio"
        cpu, motif_cpu = _valider_cpu(objet["cpu"])
        if cpu is None:
            return None, motif_cpu
        normalise["cpu"] = cpu
    elif "cpu" in objet:
        return None, "relevé CPU présent sur un relevé de chargement"
    if "memoire_apres" not in objet:
        return None, "mémoire après mesure absente"
    memoire, motif_memoire = _valider_memoire(objet["memoire_apres"])
    if memoire is None:
        return None, motif_memoire
    normalise["memoire_apres"] = memoire
    return normalise, None


def _resultat_memoire(
    releve_le: str | None,
    totale: int | None,
    disponible: int | None,
    motif: str | None,
) -> dict[str, Any]:
    """Sous-objet `memoire_apres` du contrat D3."""
    return {
        "releve_le": releve_le,
        "totale_octets": totale,
        "disponible_octets": disponible,
        "motif": motif,
    }


@dataclass(frozen=True)
class AmorcageCpu:
    """Trace d'un amorçage CPU, sans la valeur retournée (ignorée par contrat).

    `instant` est la lecture monotone prise juste après l'appel d'amorçage ;
    `motif` vaut `None` si l'amorçage a réussi, sinon le code stable expliquant
    son échec. Un amorçage n'est lu que par la fenêtre qui l'a créé : aucune
    valeur n'est conservée dans l'instance du releveur, donc deux enchaînements
    successifs ne partagent rien, même après une erreur.
    """

    instant: Any
    motif: str | None


class ReleveurSysteme:
    """Relevés système injectables : CPU global par fenêtre et instantanés mémoire.

    Les fonctions `cpu_percent`, `memoire`, `horloge` et `horodatage` sont
    injectables pour les tests et le scénario simulé ; par défaut ce sont les
    fonctions psutil réelles, `time.monotonic` et l'instant UTC. Le releveur ne
    conserve aucun état entre deux fenêtres.
    """

    def __init__(
        self,
        *,
        cpu_percent: Callable[..., Any] = psutil.cpu_percent,
        memoire: Callable[[], Any] = psutil.virtual_memory,
        horloge: Callable[[], Any] = time.monotonic,
        horodatage: Callable[[], str] = horodatage_utc,
        provenance: str = PROVENANCE_REELLE,
    ) -> None:
        if provenance not in PROVENANCES:
            raise ValueError(f"provenance inconnue : {provenance!r}")
        self._cpu_percent = cpu_percent
        self._memoire = memoire
        self._horloge = horloge
        self._horodatage = horodatage
        self._provenance = provenance
        self._version_psutil = psutil.__version__

    def amorcer_cpu(self) -> AmorcageCpu:
        """Amorce le compteur CPU global sur ce thread et ignore sa valeur.

        La valeur retournée par psutil au premier appel n'est pas interprétable :
        elle n'est ni conservée ni exposée. Une exception est convertie en motif
        stable, sans être recopiée.
        """
        try:
            self._cpu_percent(interval=None, percpu=False)
        except Exception:
            return AmorcageCpu(instant=None, motif=MOTIF_LECTURE_IMPOSSIBLE)
        try:
            instant = self._horloge()
        except Exception:
            return AmorcageCpu(instant=None, motif=MOTIF_LECTURE_IMPOSSIBLE)
        return AmorcageCpu(instant=instant, motif=None)

    def lire_cpu(self, amorcage: AmorcageCpu) -> dict[str, Any]:
        """Lit le CPU global de la fenêtre ouverte par `amorcage` (D2, D3).

        Aucun appel intermédiaire n'est fait : un amorçage en échec donne
        directement `lecture_impossible`, et un intervalle invalide donne
        `intervalle_trop_court` sans même interroger psutil.
        """
        if not isinstance(amorcage, AmorcageCpu):
            raise TypeError("amorçage CPU attendu sous forme d'AmorcageCpu")
        if amorcage.motif is not None:
            return _resultat_cpu(None, None, amorcage.motif)
        try:
            fin = self._horloge()
        except Exception:
            return _resultat_cpu(None, None, MOTIF_LECTURE_IMPOSSIBLE)
        intervalle, motif = _intervalle_releve(amorcage.instant, fin)
        if motif is not None:
            return _resultat_cpu(None, intervalle, motif)
        try:
            valeur = self._cpu_percent(interval=None, percpu=False)
        except Exception:
            return _resultat_cpu(None, intervalle, MOTIF_LECTURE_IMPOSSIBLE)
        if not _pourcentage_valide(valeur):
            return _resultat_cpu(None, intervalle, MOTIF_VALEUR_INCOHERENTE)
        return _resultat_cpu(float(valeur), intervalle, None)

    def relever_memoire(self) -> dict[str, Any]:
        """Instantané de RAM totale et disponible, avec son instant (D3).

        Seuls `total` et `available` sont lus : jamais `total - free`, jamais une
        somme de RSS. Chaque champ individuellement valide est conservé ; la
        contrainte `available <= total` n'invalide que `disponible_octets`. Le
        motif porte sur l'instantané entier.
        """
        try:
            releve_le = self._horodatage()
        except Exception:  # jamais fatal : l'objet sera écarté, l'audio intact
            return _resultat_memoire(None, None, None, MOTIF_LECTURE_IMPOSSIBLE)
        try:
            valeur = self._memoire()
        except Exception:
            return _resultat_memoire(
                releve_le, None, None, MOTIF_LECTURE_IMPOSSIBLE
            )
        totale = getattr(valeur, "total", _CHAMP_ABSENT)
        disponible = getattr(valeur, "available", _CHAMP_ABSENT)
        total_valide = _est_entier_positif(totale)
        disponible_valide = (
            total_valide
            and _est_entier_naturel(disponible)
            and disponible <= totale
        )
        if total_valide and disponible_valide:
            return _resultat_memoire(releve_le, int(totale), int(disponible), None)
        return _resultat_memoire(
            releve_le,
            int(totale) if total_valide else None,
            int(disponible) if disponible_valide else None,
            MOTIF_VALEUR_INCOHERENTE,
        )

    def observation_chargement(self) -> dict[str, Any]:
        """Objet `observation_systeme` du chargement : instantané RAM seul (D3)."""
        return self._enveloppe({"memoire_apres": self.relever_memoire()})

    def observation_audio(self, amorcage: AmorcageCpu) -> dict[str, Any]:
        """Objet `observation_systeme` d'un audio : CPU de la fenêtre puis RAM.

        L'ordre suit le design D1 : la valeur CPU est lue après l'arrêt des
        bornes d'inférence, puis la mémoire disponible est relevée.
        """
        return self._enveloppe(
            {
                "cpu": self.lire_cpu(amorcage),
                "memoire_apres": self.relever_memoire(),
            }
        )

    def _enveloppe(self, contenu: dict[str, Any]) -> dict[str, Any]:
        """En-tête versionné commun aux objets d'observation système."""
        return {
            "version": VERSION_METHODE,
            "methode_cpu": METHODE_CPU,
            "version_psutil": self._version_psutil,
            "provenance": self._provenance,
            **contenu,
        }


def _cpu_simule(**_options: Any) -> float:
    """Retour CPU du scénario simulé : constante fixe, jamais psutil."""
    return SIMULATION_CPU_POURCENTAGE


def _memoire_simulee() -> SimpleNamespace:
    """Retour mémoire du scénario simulé : constantes fixes, jamais psutil."""
    return SimpleNamespace(
        total=SIMULATION_MEMOIRE_TOTALE_OCTETS,
        available=SIMULATION_MEMOIRE_DISPONIBLE_OCTETS,
    )


def _horloge_simulee() -> Callable[[], float]:
    """Horloge du scénario : 0,0 puis 1,0 puis 2,0… → intervalle de 1,0 s.

    Le compteur est propre à l'instance créée : deux exécutions rejouent la même
    suite, une fenêtre par audio consommant deux instants (amorçage puis
    lecture), comme le relevé réel.
    """
    compteur = itertools.count()
    return lambda: float(next(compteur)) * SIMULATION_INTERVALLE_CPU_S


def creer_releveur_simule() -> ReleveurSysteme:
    """Scénario simulé déterministe du moteur factice (design D2).

    Le parcours est celui du relevé réel (mêmes objets, même enveloppe D3),
    avec des entrées fixes et une provenance `simulee`. Aucune fonction de
    mesure de psutil n'est appelée : seul `psutil.__version__` est lu comme
    attribut du module, pour nommer la bibliothèque dont le protocole est
    employé ; ce n'est jamais une mesure de l'ordinateur.
    """
    return ReleveurSysteme(
        cpu_percent=_cpu_simule,
        memoire=_memoire_simulee,
        horloge=_horloge_simulee(),
        horodatage=lambda: SIMULATION_RELEVE_LE,
        provenance=PROVENANCE_SIMULEE,
    )


def creer_releveur_systeme(*, factice: bool) -> ReleveurSysteme:
    """Relevé réel, ou scénario simulé déterministe pour le moteur factice.

    Seul point de choix employé par le runner : aucun mélange n'est possible,
    puisque les deux modes ne partagent aucune entrée de mesure.
    """
    return creer_releveur_simule() if factice else ReleveurSysteme()
