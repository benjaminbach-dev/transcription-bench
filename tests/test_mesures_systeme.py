"""Tests du helper injectable de relevés système (tâche 1.1).

Tout est déterministe : les deux retours CPU, l'horloge monotone et les retours
mémoire sont des doubles programmés. Aucune mesure réelle ne sert d'attente et
aucune valeur de performance n'est comparée. La seule sonde réelle est
`test_sonde_de_fonctionnement_psutil`, limitée à deux appels non bloquants sur le
même thread autour d'un court intervalle : elle vérifie que le logiciel
fonctionne, pas la qualité ni la vitesse de la machine.

Les tests couvrent l'amorçage dont la valeur est ignorée, le second appel non
bloquant, l'isolation entre deux audios (y compris après erreur), l'intervalle
court sans attente, le zéro retourné conservé, les exceptions et les retours
invalides, les instantanés mémoire et la forme des objets D3.
"""

from __future__ import annotations

import math
import time
import unittest
from datetime import datetime, timezone
from types import SimpleNamespace

import psutil

from engines.mesures_systeme import (
    INTERVALLE_MINIMUM_S,
    METHODE_CPU,
    MOTIF_INTERVALLE_TROP_COURT,
    MOTIF_LECTURE_IMPOSSIBLE,
    MOTIF_VALEUR_INCOHERENTE,
    PROVENANCE_REELLE,
    PROVENANCE_SIMULEE,
    VERSION_METHODE,
    ReleveurSysteme,
)


class FauxCpu:
    """Compteur CPU factice : valeurs programmées, appels consignés."""

    def __init__(self, valeurs: list[object]) -> None:
        self.valeurs = list(valeurs)
        self.appels: list[dict[str, object]] = []

    def __call__(self, **options: object) -> object:
        self.appels.append(dict(options))
        valeur = self.valeurs.pop(0)
        if isinstance(valeur, BaseException):
            raise valeur
        return valeur


class FausseHorloge:
    """Horloge monotone factice : instants programmés, dans l'ordre."""

    def __init__(self, instants: list[object]) -> None:
        self.instants = list(instants)
        self.appels = 0

    def __call__(self) -> object:
        self.appels += 1
        valeur = self.instants.pop(0)
        if isinstance(valeur, BaseException):
            raise valeur
        return valeur


class FausseMemoire:
    """Retour mémoire factice ; `free` est présent pour prouver qu'il est ignoré."""

    def __init__(
        self,
        total: object = 16 * 1024**3,
        available: object = 5 * 1024**3,
        free: object = 1024**3,
        exception: BaseException | None = None,
    ) -> None:
        self.total = total
        self.available = available
        self.free = free
        self.exception = exception
        self.appels = 0

    def __call__(self) -> object:
        self.appels += 1
        if self.exception is not None:
            raise self.exception
        return SimpleNamespace(
            total=self.total, available=self.available, free=self.free
        )


def _releveur(
    cpu: FauxCpu,
    horloge: FausseHorloge,
    memoire: FausseMemoire | None = None,
    provenance: str = PROVENANCE_REELLE,
) -> ReleveurSysteme:
    return ReleveurSysteme(
        cpu_percent=cpu,
        memoire=FausseMemoire() if memoire is None else memoire,
        horloge=horloge,
        provenance=provenance,
    )


class AmorcageEtLectureCpuTest(unittest.TestCase):
    def test_amorcage_ignore_la_valeur_et_lecture_non_bloquante(self) -> None:
        cpu = FauxCpu([99.0, 42.5])
        horloge = FausseHorloge([10.0, 10.5])
        releveur = _releveur(cpu, horloge)

        amorcage = releveur.amorcer_cpu()
        resultat = releveur.lire_cpu(amorcage)

        # La valeur d'amorçage (99,0) n'est jamais exposée : seul le second
        # appel de la fenêtre compte.
        self.assertEqual(
            resultat,
            {"pourcentage_moyen": 42.5, "intervalle_s": 0.5, "motif": None},
        )
        self.assertEqual(
            cpu.appels,
            [
                {"interval": None, "percpu": False},
                {"interval": None, "percpu": False},
            ],
        )
        self.assertEqual(horloge.appels, 2)

    def test_intervalle_exactement_au_seuil_est_accepte(self) -> None:
        releveur = _releveur(
            FauxCpu([1.0, 12.0]), FausseHorloge([0.0, INTERVALLE_MINIMUM_S])
        )

        resultat = releveur.lire_cpu(releveur.amorcer_cpu())

        self.assertEqual(resultat["intervalle_s"], INTERVALLE_MINIMUM_S)
        self.assertEqual(resultat["pourcentage_moyen"], 12.0)
        self.assertIsNone(resultat["motif"])

    def test_intervalle_trop_court_sans_aucune_attente(self) -> None:
        cpu = FauxCpu([50.0])
        horloge = FausseHorloge([0.0, 0.099])
        releveur = _releveur(cpu, horloge)

        resultat = releveur.lire_cpu(releveur.amorcer_cpu())

        self.assertEqual(resultat["motif"], MOTIF_INTERVALLE_TROP_COURT)
        self.assertIsNone(resultat["pourcentage_moyen"])
        self.assertEqual(resultat["intervalle_s"], 0.099)
        # Aucun appel de lecture et aucun instant supplémentaire : rien n'a été
        # attendu pour atteindre le seuil.
        self.assertEqual(len(cpu.appels), 1)
        self.assertEqual(horloge.appels, 2)

    def test_intervalle_absent_non_fini_ou_negatif(self) -> None:
        cas = {
            "amorçage absent": ([None, 1.0], None),
            "lecture absente": ([0.0, None], None),
            "lecture non finie": ([0.0, math.inf], None),
            "lecture nan": ([0.0, math.nan], None),
            "horloge inversée": ([1.0, 0.5], None),
            "texte": (["0.0", 1.0], None),
        }
        for nom, (instants, intervalle) in cas.items():
            with self.subTest(nom):
                cpu = FauxCpu([50.0])
                releveur = _releveur(cpu, FausseHorloge(instants))

                resultat = releveur.lire_cpu(releveur.amorcer_cpu())

                self.assertEqual(resultat["motif"], MOTIF_INTERVALLE_TROP_COURT)
                self.assertIsNone(resultat["pourcentage_moyen"])
                self.assertEqual(resultat["intervalle_s"], intervalle)
                self.assertEqual(len(cpu.appels), 1)

    def test_zero_retourne_apres_amorcage_valide_est_conserve(self) -> None:
        cpu = FauxCpu([0.0, 0.0])
        releveur = _releveur(cpu, FausseHorloge([0.0, 0.25]))

        resultat = releveur.lire_cpu(releveur.amorcer_cpu())

        self.assertEqual(resultat["pourcentage_moyen"], 0.0)
        self.assertIsNone(resultat["motif"])
        self.assertEqual(resultat["intervalle_s"], 0.25)

    def test_exception_a_l_amorcage_ne_lit_pas_et_donne_un_motif(self) -> None:
        cpu = FauxCpu([OSError("compteur indisponible")])
        horloge = FausseHorloge([])
        releveur = _releveur(cpu, horloge)

        amorcage = releveur.amorcer_cpu()
        resultat = releveur.lire_cpu(amorcage)

        self.assertEqual(amorcage.motif, MOTIF_LECTURE_IMPOSSIBLE)
        self.assertIsNone(amorcage.instant)
        self.assertEqual(
            resultat,
            {
                "pourcentage_moyen": None,
                "intervalle_s": None,
                "motif": MOTIF_LECTURE_IMPOSSIBLE,
            },
        )
        self.assertEqual(len(cpu.appels), 1)

    def test_exception_a_la_lecture_donne_un_motif_sans_texte_d_os(self) -> None:
        cpu = FauxCpu([50.0, OSError("chemin interne /proc/stat")])
        releveur = _releveur(cpu, FausseHorloge([0.0, 0.4]))

        resultat = releveur.lire_cpu(releveur.amorcer_cpu())

        self.assertEqual(resultat["motif"], MOTIF_LECTURE_IMPOSSIBLE)
        self.assertIsNone(resultat["pourcentage_moyen"])
        self.assertEqual(resultat["intervalle_s"], 0.4)
        self.assertNotIn("proc", repr(resultat))

    def test_exception_de_l_horloge_donne_lecture_impossible(self) -> None:
        for nom, instants in {
            "à l'amorçage": [OSError("horloge")],
            "à la lecture": [0.0, OSError("horloge")],
        }.items():
            with self.subTest(nom):
                cpu = FauxCpu([50.0])
                releveur = _releveur(cpu, FausseHorloge(instants))

                resultat = releveur.lire_cpu(releveur.amorcer_cpu())

                self.assertEqual(resultat["motif"], MOTIF_LECTURE_IMPOSSIBLE)
                self.assertIsNone(resultat["pourcentage_moyen"])

    def test_retours_cpu_invalides_donnent_valeur_incoherente(self) -> None:
        valeurs = (True, False, math.inf, -math.inf, math.nan, -0.1, 100.1, "12", None)
        for valeur in valeurs:
            with self.subTest(valeur=repr(valeur)):
                cpu = FauxCpu([50.0, valeur])
                releveur = _releveur(cpu, FausseHorloge([0.0, 0.5]))

                resultat = releveur.lire_cpu(releveur.amorcer_cpu())

                self.assertEqual(resultat["motif"], MOTIF_VALEUR_INCOHERENTE)
                self.assertIsNone(resultat["pourcentage_moyen"])
                self.assertEqual(resultat["intervalle_s"], 0.5)

    def test_lecture_refuse_un_amorcage_etranger(self) -> None:
        releveur = _releveur(FauxCpu([]), FausseHorloge([]))

        with self.assertRaises(TypeError):
            releveur.lire_cpu(object())  # type: ignore[arg-type]

    def test_amorcage_sans_etat_partage_entre_deux_audios(self) -> None:
        cpu = FauxCpu([11.0, 22.0, 33.0, 44.0])
        horloge = FausseHorloge([0.0, 1.0, 2.0, 3.0])
        releveur = _releveur(cpu, horloge)

        premier = releveur.lire_cpu(releveur.amorcer_cpu())
        second = releveur.lire_cpu(releveur.amorcer_cpu())

        self.assertEqual(premier["pourcentage_moyen"], 22.0)
        self.assertEqual(second["pourcentage_moyen"], 44.0)
        self.assertEqual(premier["intervalle_s"], 1.0)
        self.assertEqual(second["intervalle_s"], 1.0)
        # Chaque fenêtre a bien refait un amorçage : aucune réutilisation de la
        # référence précédente.
        self.assertEqual(len(cpu.appels), 4)
        self.assertEqual(horloge.appels, 4)

    def test_apres_une_erreur_l_enchainement_suivant_repart_neuf(self) -> None:
        cpu = FauxCpu([OSError("échec"), 5.0, 33.0])
        horloge = FausseHorloge([2.0, 2.5])
        releveur = _releveur(cpu, horloge)

        premier = releveur.lire_cpu(releveur.amorcer_cpu())
        second = releveur.lire_cpu(releveur.amorcer_cpu())

        self.assertEqual(premier["motif"], MOTIF_LECTURE_IMPOSSIBLE)
        self.assertEqual(second["pourcentage_moyen"], 33.0)
        self.assertEqual(second["intervalle_s"], 0.5)
        self.assertIsNone(second["motif"])


class MemoireTest(unittest.TestCase):
    def test_utilise_available_jamais_total_moins_free(self) -> None:
        memoire = FausseMemoire(
            total=16 * 1024**3, available=5 * 1024**3, free=1024**3
        )
        releveur = _releveur(FauxCpu([]), FausseHorloge([]), memoire)

        resultat = releveur.relever_memoire()

        self.assertEqual(resultat["totale_octets"], 16 * 1024**3)
        self.assertEqual(resultat["disponible_octets"], 5 * 1024**3)
        self.assertNotEqual(resultat["disponible_octets"], 16 * 1024**3 - 1024**3)
        self.assertIsNone(resultat["motif"])

    def test_releve_le_est_un_instant_iso_utc(self) -> None:
        releveur = _releveur(FauxCpu([]), FausseHorloge([]))

        date = datetime.fromisoformat(releveur.relever_memoire()["releve_le"])

        self.assertEqual(date.tzinfo, timezone.utc)

    def test_valeurs_memoire_hors_bornes_donnent_un_motif(self) -> None:
        cas = {
            "disponible supérieure au total": dict(
                total=8 * 1024**3, available=9 * 1024**3
            ),
            "total nul": dict(total=0, available=0),
            "total négatif": dict(total=-1, available=0),
            "disponible négatif": dict(total=8 * 1024**3, available=-1),
            "disponible flottant": dict(total=8 * 1024**3, available=1.0),
            "disponible booléen": dict(total=8 * 1024**3, available=True),
        }
        for nom, champs in cas.items():
            with self.subTest(nom):
                memoire = FausseMemoire(**champs)
                resultat = _releveur(
                    FauxCpu([]), FausseHorloge([]), memoire
                ).relever_memoire()

                self.assertEqual(resultat["motif"], MOTIF_VALEUR_INCOHERENTE)
                self.assertIsNone(resultat["disponible_octets"])

        # Un total valide reste consigné quand seul le disponible est invalide.
        total = 8 * 1024**3
        resultat = _releveur(
            FauxCpu([]),
            FausseHorloge([]),
            FausseMemoire(total=total, available=total + 1),
        ).relever_memoire()
        self.assertEqual(resultat["totale_octets"], total)

    def test_champ_memoire_absent_donne_valeur_incoherente(self) -> None:
        releveur = ReleveurSysteme(
            cpu_percent=FauxCpu([]),
            memoire=lambda: SimpleNamespace(total=8 * 1024**3),
            horloge=FausseHorloge([]),
        )

        resultat = releveur.relever_memoire()

        self.assertEqual(resultat["motif"], MOTIF_VALEUR_INCOHERENTE)
        self.assertIsNone(resultat["disponible_octets"])
        self.assertEqual(resultat["totale_octets"], 8 * 1024**3)

    def test_exception_memoire_donne_lecture_impossible(self) -> None:
        memoire = FausseMemoire(exception=OSError("mémoire indisponible"))
        resultat = _releveur(
            FauxCpu([]), FausseHorloge([]), memoire
        ).relever_memoire()

        self.assertEqual(resultat["motif"], MOTIF_LECTURE_IMPOSSIBLE)
        self.assertIsNone(resultat["totale_octets"])
        self.assertIsNone(resultat["disponible_octets"])
        self.assertNotIn("mémoire indisponible", repr(resultat))
        self.assertTrue(resultat["releve_le"])


class ObjetsDObservationTest(unittest.TestCase):
    def test_observation_chargement_sans_cpu(self) -> None:
        releveur = _releveur(FauxCpu([]), FausseHorloge([]))

        observation = releveur.observation_chargement()

        self.assertEqual(
            set(observation),
            {"version", "methode_cpu", "version_psutil", "provenance", "memoire_apres"},
        )
        self.assertEqual(observation["version"], VERSION_METHODE)
        self.assertEqual(observation["methode_cpu"], METHODE_CPU)
        self.assertEqual(observation["version_psutil"], psutil.__version__)
        self.assertEqual(observation["provenance"], PROVENANCE_REELLE)
        self.assertEqual(
            set(observation["memoire_apres"]),
            {"releve_le", "totale_octets", "disponible_octets", "motif"},
        )

    def test_observation_audio_porte_le_cpu_de_la_fenetre(self) -> None:
        cpu = FauxCpu([80.0, 25.0])
        releveur = _releveur(cpu, FausseHorloge([0.0, 0.6]))

        observation = releveur.observation_audio(releveur.amorcer_cpu())

        self.assertEqual(observation["version"], VERSION_METHODE)
        self.assertEqual(observation["methode_cpu"], METHODE_CPU)
        self.assertEqual(observation["provenance"], PROVENANCE_REELLE)
        self.assertEqual(
            observation["cpu"],
            {"pourcentage_moyen": 25.0, "intervalle_s": 0.6, "motif": None},
        )
        self.assertEqual(observation["memoire_apres"]["motif"], None)
        self.assertEqual(observation["memoire_apres"]["totale_octets"], 16 * 1024**3)

    def test_provenance_simulee_acceptee_et_inconnue_refusee(self) -> None:
        observation = _releveur(
            FauxCpu([]), FausseHorloge([]), provenance=PROVENANCE_SIMULEE
        ).observation_chargement()
        self.assertEqual(observation["provenance"], PROVENANCE_SIMULEE)

        with self.assertRaises(ValueError):
            ReleveurSysteme(provenance="estimee")


class SondeDeFonctionnementPsutilTest(unittest.TestCase):
    """Sonde de fonctionnement réelle, pas une mesure de performance.

    Deux appels non bloquants de `psutil.cpu_percent` sur le même thread autour
    d'un court intervalle d'au moins 0,1 s : on vérifie seulement que le
    logiciel fonctionne et rend un pourcentage plausible. Aucun seuil de
    performance, aucune représentativité d'un PC, aucun moteur lancé.
    """

    def test_deux_appels_non_bloquants_sur_le_meme_thread(self) -> None:
        releveur = ReleveurSysteme()

        amorcage = releveur.amorcer_cpu()
        time.sleep(INTERVALLE_MINIMUM_S + 0.05)
        resultat = releveur.lire_cpu(amorcage)

        self.assertIsNone(resultat["motif"])
        self.assertIsInstance(resultat["pourcentage_moyen"], float)
        self.assertGreaterEqual(resultat["pourcentage_moyen"], 0.0)
        self.assertLessEqual(resultat["pourcentage_moyen"], 100.0)
        self.assertGreaterEqual(resultat["intervalle_s"], INTERVALLE_MINIMUM_S)

        memoire = releveur.relever_memoire()
        self.assertIsNone(memoire["motif"])
        self.assertIsInstance(memoire["totale_octets"], int)
        self.assertIsInstance(memoire["disponible_octets"], int)
        self.assertLessEqual(memoire["disponible_octets"], memoire["totale_octets"])


if __name__ == "__main__":
    unittest.main()
