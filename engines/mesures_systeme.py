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
lecture (`absent`, `invalide`, `version_inconnue`) :

- `lecture_impossible` : exception à l'amorçage, à la lecture ou de l'horloge ;
- `intervalle_trop_court` : intervalle monotone absent, non fini, négatif ou
  inférieur à 0,1 s ;
- `valeur_incoherente` : retour non numérique (booléen exclu), non fini ou hors
  0..100 pour le CPU, ou champs mémoire absents, non entiers ou hors bornes.

Les erreurs brutes d'OS ne sont jamais recopiées dans les objets produits : elles
ne deviennent que ces codes.

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
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any

import psutil

#: Version du contrat d'objet d'observation système (design D3).
VERSION_METHODE = 1
#: Identifiant de la méthode de relevé CPU employée, pas une promesse de mesure.
METHODE_CPU = "psutil-cpu-percent-nonbloquant-v1"
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
    """Nombre réel fini ; un booléen est exclu bien qu'il soit un `int`."""
    if isinstance(valeur, bool) or not isinstance(valeur, (int, float)):
        return False
    return math.isfinite(valeur)


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


def _resultat_memoire(
    releve_le: str,
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
        releve_le = self._horodatage()
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
