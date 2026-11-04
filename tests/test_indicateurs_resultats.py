"""Tests des ratios et formats de premier niveau (tâche 1.2).

Les mesures sont synthétiques : aucun test ne mesure le poste courant, ne lance
de moteur ni n'accède au réseau. Les fixtures de `test_consultation_resultats`
écrivent leurs `run.json` et `result.json` dans un dossier temporaire ; les tests
de rendu de l'aide vivent dans `tests/test_aide_resultats_web.py`.
"""

from __future__ import annotations

import math
import unittest

from tests.test_consultation_resultats import (
    IDENTIFIANT,
    IDENTIFIANT_ANCIEN,
    SocleConsultationTest,
    ecrire_execution,
    result_json,
    run_json,
)
from transcription_bench.indicateurs_resultats import (
    INDISPONIBLE,
    NON_MESURE,
    formater_duree_premier_niveau,
    formater_memoire_premier_niveau,
    formater_pourcentage_premier_niveau,
    ratio_cpu,
    ratio_ram,
)

MACHINE_16_LOGICAL = {
    "os": "Linux",
    "version_os": "6.1",
    "architecture": "x86_64",
    "processeur": None,
    "coeurs_physiques": 8,
    "coeurs_logiques": 16,
    "ram_totale_octets": 32_000_000_000,
}
MACHINE_8_LOGICAL = {
    **MACHINE_16_LOGICAL,
    "coeurs_physiques": 4,
    "coeurs_logiques": 8,
    "ram_totale_octets": 8_000_000_000,
}


class RatioCpuTest(unittest.TestCase):
    def test_cas_de_reference_50_pourcent(self) -> None:
        # 8 s CPU pour 2 s de transcription sur 8 processeurs logiques.
        self.assertEqual(ratio_cpu(8.0, 2.0, 8), 50.0)

    def test_zero_reel_conserve(self) -> None:
        self.assertEqual(ratio_cpu(0, 2.0, 8), 0.0)

    def test_entrees_invalides_indisponibles(self) -> None:
        cas = (
            (True, 2.0, 8),
            (0, True, 8),
            (0, 2.0, True),
            (False, 2.0, 8),
            (math.nan, 2.0, 8),
            (math.inf, 2.0, 8),
            (-math.inf, 2.0, 8),
            (0, math.nan, 8),
            (0, math.inf, 8),
            (-1.0, 2.0, 8),
            (0, -2.0, 8),
            (0, 0, 8),
            (0, 2.0, 0),
            (0, 2.0, -1),
            (0, 2.0, None),
            (0, 2.0, 8.0),
            (0, 2.0, "8"),
            (None, 2.0, 8),
            (0, None, 8),
            ("1", 2.0, 8),
        )
        for temps_cpu, duree, coeurs in cas:
            with self.subTest(temps_cpu=temps_cpu, duree=duree, coeurs=coeurs):
                self.assertIsNone(ratio_cpu(temps_cpu, duree, coeurs))

    def test_grandes_valeurs_finies_sans_debordement_intermediaire(self) -> None:
        self.assertEqual(ratio_cpu(1e308, 1e308, 1), 100.0)
        self.assertIsNone(ratio_cpu(1.0, 1.0, 10**400))

    def test_ratio_au_dessus_de_100_indisponible_sans_ecretage(self) -> None:
        self.assertIsNone(ratio_cpu(10.0, 2.0, 4))  # 125 %
        self.assertEqual(ratio_cpu(8.0, 2.0, 4), 100.0)  # borne exacte acceptée


class RatioRamTest(unittest.TestCase):
    def test_part_de_ram_en_pourcentage(self) -> None:
        self.assertEqual(ratio_ram(2_400_000_000, 16_000_000_000), 15.0)
        self.assertEqual(ratio_ram(0, 16_000_000_000), 0.0)

    def test_entrees_invalides_indisponibles(self) -> None:
        cas = (
            (True, 100),
            (0, True),
            (math.nan, 100),
            (math.inf, 100),
            (-1, 100),
            (0, 0),
            (0, -100),
            (0, None),
            (None, 100),
            ("1", 100),
        )
        for pic, totale in cas:
            with self.subTest(pic=pic, totale=totale):
                self.assertIsNone(ratio_ram(pic, totale))

    def test_grandes_valeurs_finies_sans_debordement_intermediaire(self) -> None:
        self.assertEqual(ratio_ram(1e308, 1e308), 100.0)

    def test_ratio_au_dessus_de_100_indisponible_sans_ecretage(self) -> None:
        self.assertIsNone(ratio_ram(200, 100))
        self.assertEqual(ratio_ram(100, 100), 100.0)


class FormatDureePremierNiveauTest(unittest.TestCase):
    def test_durees_lisibles_et_bornes(self) -> None:
        cas = (
            (None, NON_MESURE),
            (True, INDISPONIBLE),
            (math.nan, INDISPONIBLE),
            (math.inf, INDISPONIBLE),
            (-1, INDISPONIBLE),
            (0, "0 s"),
            (0.001, "< 0,1 s"),
            (0.04, "< 0,1 s"),
            (0.1, "0,1 s"),
            (0.4, "0,4 s"),
            (0.99, "0,9 s"),
            (1, "1 s"),
            (42, "42 s"),
            (42.9, "42 s"),
            (59.9, "59 s"),
            (60, "1 min"),
            (97, "1 min 37 s"),
            (3599, "59 min 59 s"),
            (3600, "1 h"),
            (3660, "1 h 1 min"),
            (7325, "2 h 2 min"),
        )
        for valeur, attendu in cas:
            with self.subTest(valeur=valeur):
                self.assertEqual(formater_duree_premier_niveau(valeur), attendu)


class FormatMemoirePremierNiveauTest(unittest.TestCase):
    def test_mo_et_go_decimaux(self) -> None:
        cas = (
            (None, NON_MESURE),
            (True, INDISPONIBLE),
            (math.nan, INDISPONIBLE),
            (math.inf, INDISPONIBLE),
            (-1, INDISPONIBLE),
            (0, "0 Mo"),
            (50_000, "< 0,1 Mo"),
            (99_999, "< 0,1 Mo"),
            (100_000, "0,1 Mo"),
            (240_000, "0,2 Mo"),
            (999_999, "0,9 Mo"),
            (1_000_000, "1 Mo"),
            (999_999_999, "999,9 Mo"),
            (1_000_000_000, "1 Go"),
            (1_090_000_000, "1 Go"),
            (1_500_000_000, "1,5 Go"),
            (2_400_000_000, "2,4 Go"),
            (16_000_000_000, "16 Go"),
        )
        for valeur, attendu in cas:
            with self.subTest(valeur=valeur):
                self.assertEqual(formater_memoire_premier_niveau(valeur), attendu)

    def test_grande_valeur_finie_ne_leve_pas(self) -> None:
        self.assertTrue(formater_memoire_premier_niveau(1e308).endswith(" Go"))


class FormatPourcentagePremierNiveauTest(unittest.TestCase):
    def test_ratios_entiers_ne_perdent_pas_un_point_avec_les_flottants(self) -> None:
        self.assertEqual(
            formater_pourcentage_premier_niveau(ratio_ram(4_640_000_000, 16_000_000_000)),
            "29 %",
        )
        self.assertEqual(formater_pourcentage_premier_niveau(ratio_cpu(2.9, 10, 1)), "29 %")

    def test_pourcentages_entiers_et_petites_valeurs(self) -> None:
        cas = (
            (None, NON_MESURE),
            (True, INDISPONIBLE),
            (math.nan, INDISPONIBLE),
            (math.inf, INDISPONIBLE),
            (-0.5, INDISPONIBLE),
            (0, "0 %"),
            (0.4, "< 1 %"),
            (0.999, "< 1 %"),
            (1, "1 %"),
            (15, "15 %"),
            (50, "50 %"),
            (99.9, "99 %"),
            (100, "100 %"),
            (100.1, INDISPONIBLE),
            (101, INDISPONIBLE),
        )
        for valeur, attendu in cas:
            with self.subTest(valeur=valeur):
                self.assertEqual(
                    formater_pourcentage_premier_niveau(valeur), attendu
                )


class RatiosDepuisCapacitesConsigneesTest(SocleConsultationTest):
    def test_chaque_essai_utilise_son_propre_materiel_consigne(self) -> None:
        # Deux essais du même audio, avec des machines consignées différentes.
        run_a = run_json(IDENTIFIANT, machine=MACHINE_16_LOGICAL)
        resultat_a = result_json(
            run_a["audios"][0],
            execution=IDENTIFIANT,
            duree_transcription=2.0,
            mesures_extra={
                "temps_cpu_s": 8.0,
                "pic_memoire_octets": 4_800_000_000,
            },
        )
        run_b = run_json(IDENTIFIANT_ANCIEN, machine=MACHINE_8_LOGICAL)
        resultat_b = result_json(
            run_b["audios"][0],
            execution=IDENTIFIANT_ANCIEN,
            duree_transcription=2.0,
            mesures_extra={
                "temps_cpu_s": 8.0,
                "pic_memoire_octets": 4_800_000_000,
            },
        )
        ecrire_execution(self.donnees, run_a, (resultat_a,))
        ecrire_execution(self.donnees, run_b, (resultat_b,))

        entrees = {
            entree.execution: entree
            for groupe in self.service.groupes_par_empreinte()
            for entree in groupe.entrees
        }

        self.assertEqual(set(entrees), {IDENTIFIANT, IDENTIFIANT_ANCIEN})
        entree_a = entrees[IDENTIFIANT]
        self.assertEqual(entree_a.materiel.coeurs_logiques, 16)
        self.assertEqual(entree_a.materiel.ram_totale_octets, 32_000_000_000)
        self.assertEqual(
            ratio_cpu(
                entree_a.mesures.temps_cpu_s,
                entree_a.mesures.duree_transcription_s,
                entree_a.materiel.coeurs_logiques,
            ),
            25.0,
        )
        self.assertEqual(
            ratio_ram(
                entree_a.mesures.pic_memoire_octets,
                entree_a.materiel.ram_totale_octets,
            ),
            15.0,
        )
        entree_b = entrees[IDENTIFIANT_ANCIEN]
        self.assertEqual(
            ratio_cpu(
                entree_b.mesures.temps_cpu_s,
                entree_b.mesures.duree_transcription_s,
                entree_b.materiel.coeurs_logiques,
            ),
            50.0,
        )
        self.assertEqual(
            ratio_ram(
                entree_b.mesures.pic_memoire_octets,
                entree_b.materiel.ram_totale_octets,
            ),
            60.0,
        )

    def test_aucune_reecriture_des_json_par_les_ratios_et_formats(self) -> None:
        run = run_json(machine=MACHINE_16_LOGICAL)
        resultat = result_json(run["audios"][0], execution=IDENTIFIANT)
        dossier = ecrire_execution(self.donnees, run, (resultat,))
        fichiers = sorted(chemin for chemin in dossier.rglob("*") if chemin.is_file())
        avant = {chemin: chemin.read_bytes() for chemin in fichiers}

        groupe = self.service.groupes_par_empreinte()[0]
        entree = groupe.entrees[0]
        ratio_cpu(
            entree.mesures.temps_cpu_s,
            entree.mesures.duree_transcription_s,
            entree.materiel.coeurs_logiques,
        )
        ratio_ram(
            entree.mesures.pic_memoire_octets,
            entree.materiel.ram_totale_octets,
        )
        formater_duree_premier_niveau(entree.mesures.duree_transcription_s)
        formater_memoire_premier_niveau(entree.mesures.pic_memoire_octets)
        formater_pourcentage_premier_niveau(15)

        self.assertEqual(
            sorted(chemin for chemin in dossier.rglob("*") if chemin.is_file()),
            fichiers,
        )
        for chemin, contenu in avant.items():
            self.assertEqual(chemin.read_bytes(), contenu, chemin)


if __name__ == "__main__":
    unittest.main()
