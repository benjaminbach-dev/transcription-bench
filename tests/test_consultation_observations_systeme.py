"""Tests de la lecture du contexte système par la consultation (tâche 2.2).

Les fichiers de résultats sont des données synthétiques écrites dans un dossier
temporaire : aucun test n'écrit sous le `data/` du dépôt, ne lit le matériel du
poste, ne lance d'inférence ni n'émet de requête réseau. Les observations
système sont relues en version 1 seulement ; les états de lecture sont calculés
et ne sont jamais écrits dans un résultat.
"""

from __future__ import annotations

import shutil
import unittest
from pathlib import Path
from typing import Any
from unittest import mock

import psutil

from engines.mesures_systeme import (
    ETATS_LECTURE,
    METHODE_CPU,
    MOTIF_INTERVALLE_TROP_COURT,
    MOTIF_VALEUR_INCOHERENTE,
    MOTIFS_ECRITS,
    PROVENANCE_REELLE,
    PROVENANCE_SIMULEE,
    SIMULATION_RELEVE_LE,
    VERSION_METHODE,
)
from tests.test_consultation_resultats import (
    IDENTIFIANT,
    IDENTIFIANT_ANCIEN,
    SocleConsultationTest,
    ecrire_execution,
    result_json,
    run_json,
)
from transcription_bench.consultation_resultats import (
    CLE_OBSERVATION_AUDIO,
    CLE_OBSERVATION_CHARGEMENT,
    MOTIF_VERSION_OBSERVATION_INCONNUE,
    ObservationSystemeVue,
)
from transcription_bench.indicateurs_resultats import ratio_cpu
from transcription_bench.resultats import (
    ETAT_ABANDONNEE,
    STATUT_NON_TRAITE,
    STATUT_OK,
)

GIO = 1024**3
RELEVE_SIMULE = "2024-01-02T03:04:20+00:00"


def memoire_systeme(
    *,
    releve_le: str = RELEVE_SIMULE,
    totale: int | None = 8 * GIO,
    disponible: int | None = 6 * GIO,
    motif: str | None = None,
) -> dict[str, Any]:
    """Sous-objet `memoire_apres` conforme au contrat D3."""
    return {
        "releve_le": releve_le,
        "totale_octets": totale,
        "disponible_octets": disponible,
        "motif": motif,
    }


def cpu_systeme(
    *,
    pourcentage: float | None = 90.0,
    intervalle: float | None = 1.2,
    motif: str | None = None,
) -> dict[str, Any]:
    """Sous-objet `cpu` conforme au contrat D3."""
    return {
        "pourcentage_moyen": pourcentage,
        "intervalle_s": intervalle,
        "motif": motif,
    }


def observation(
    *,
    provenance: str = PROVENANCE_SIMULEE,
    version: Any = VERSION_METHODE,
    cpu: dict[str, Any] | None = None,
    memoire: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Objet d'observation système conforme, de chargement ou d'audio selon `cpu`."""
    objet: dict[str, Any] = {
        "version": version,
        "methode_cpu": METHODE_CPU,
        "version_psutil": "7.2.2",
        "provenance": provenance,
        "memoire_apres": memoire_systeme() if memoire is None else memoire,
    }
    if cpu is not None:
        objet["cpu"] = cpu
    return objet


def mesures_execution(**ajouts: Any) -> dict[str, Any]:
    """Mesures de `run.json` avec leurs anciens champs et les ajouts demandés."""
    mesures: dict[str, Any] = {
        "duree_operation_s": 12.5,
        "duree_processus_s": 11.0,
        "duree_chargement_s": 2.0,
        "pic_memoire_octets": 123456789,
        "pic_memoire_partiel": False,
    }
    mesures.update(ajouts)
    return mesures


def ecrire_essai(
    donnees: Path,
    identifiant: str,
    *,
    observation_chargement: Any,
    observation_audio: Any,
    mesures_simulees: bool = True,
) -> None:
    """Écrit un essai d'un audio, avec les observations fournies telles quelles."""
    run = run_json(
        identifiant,
        mesures=mesures_execution(
            **{CLE_OBSERVATION_CHARGEMENT: observation_chargement}
        ),
        factice=mesures_simulees,
        mesures_simulees=mesures_simulees,
    )
    resultat = result_json(
        run["audios"][0],
        execution=identifiant,
        mesures_extra={CLE_OBSERVATION_AUDIO: observation_audio},
        factice=mesures_simulees,
        mesures_simulees=mesures_simulees,
    )
    ecrire_execution(donnees, run, (resultat,))


class AnciensFichiersTest(SocleConsultationTest):
    def test_ancien_fichier_sans_cles_observation_reste_non_mesure(self) -> None:
        run = run_json()
        resultat = result_json(run["audios"][0])
        ecrire_execution(self.donnees, run, (resultat,))

        detail = self.service.detail(IDENTIFIANT)

        chargement = detail.mesures.observation_chargement
        audio = detail.audios[0].observation_systeme
        for vue in (chargement, audio):
            self.assertEqual(vue.etat, "absent")
            self.assertFalse(vue.lisible)
            self.assertFalse(vue.cle_presente)
            self.assertFalse(vue.ecarte_a_l_ecriture)
            self.assertIsNone(vue.motif)
            self.assertIsNone(vue.provenance)
            self.assertIsNone(vue.version)
            self.assertIsNone(vue.methode_cpu)
            self.assertIsNone(vue.version_psutil)
            self.assertIsNone(vue.cpu)
            self.assertIsNone(vue.memoire_apres)

        # Transcriptions, marques et anciennes mesures restent lisibles.
        transcription = detail.audios[0].transcription
        assert transcription is not None
        self.assertEqual(transcription.texte, "transcription simulée de test")
        self.assertEqual(transcription.mesures.duree_transcription_s, 1.0)
        self.assertEqual(transcription.mesures.pic_memoire_octets, 2048)
        self.assertEqual(transcription.mesures.temps_cpu_s, 1.5)
        self.assertEqual(detail.mesures.duree_operation_s, 12.5)
        self.assertIn("MESURES SIMULÉES", detail.execution.marques or ())

    def test_audio_sans_resultat_n_a_aucune_observation(self) -> None:
        run = run_json(audios=(("a.wav", STATUT_OK), ("b.wav", STATUT_NON_TRAITE)))
        ecrire_execution(self.donnees, run, (result_json(run["audios"][0]),))

        detail = self.service.detail(IDENTIFIANT)

        self.assertEqual(detail.audios[0].observation_systeme.etat, "absent")
        second = detail.audios[1].observation_systeme
        self.assertEqual(second.etat, "absent")
        self.assertFalse(second.cle_presente)


class EtatsDeLectureTest(SocleConsultationTest):
    def test_objet_ecarte_a_l_ecriture_distinct_d_un_objet_invalide(self) -> None:
        # Premier essai : le serveur a écarté l'objet avant écriture, la clé
        # existe et vaut `null`.
        ecrire_essai(
            self.donnees,
            IDENTIFIANT,
            observation_chargement=None,
            observation_audio=None,
        )
        # Second essai : un objet est présent mais hors contrat.
        ecrire_essai(
            self.donnees,
            IDENTIFIANT_ANCIEN,
            observation_chargement={
                "version": VERSION_METHODE,
                "methode_cpu": "methode-inconnue",
                "version_psutil": "7.2.2",
                "provenance": PROVENANCE_SIMULEE,
                "memoire_apres": memoire_systeme(),
            },
            observation_audio={"version": VERSION_METHODE, "provenance": "simulee"},
        )

        ecarte = self.service.detail(IDENTIFIANT)
        invalide = self.service.detail(IDENTIFIANT_ANCIEN)

        for vue in (
            ecarte.mesures.observation_chargement,
            ecarte.audios[0].observation_systeme,
        ):
            self.assertEqual(vue.etat, "absent")
            self.assertTrue(vue.cle_presente)
            self.assertTrue(vue.ecarte_a_l_ecriture)
            self.assertIsNone(vue.motif)
            self.assertFalse(vue.lisible)

        for vue in (
            invalide.mesures.observation_chargement,
            invalide.audios[0].observation_systeme,
        ):
            self.assertEqual(vue.etat, "invalide")
            self.assertTrue(vue.cle_presente)
            self.assertFalse(vue.ecarte_a_l_ecriture)
            self.assertFalse(vue.lisible)
            self.assertTrue(vue.motif)
            # Aucune valeur reçue n'est recopiée dans le motif de lecture.
            self.assertNotIn("methode-inconnue", vue.motif or "")
            self.assertIsNone(vue.provenance)
            self.assertIsNone(vue.cpu)
            self.assertIsNone(vue.memoire_apres)

        # Un objet invalide n'empêche jamais la transcription ni les mesures.
        transcription = invalide.audios[0].transcription
        assert transcription is not None
        self.assertEqual(transcription.texte, "transcription simulée de test")
        self.assertEqual(transcription.mesures.duree_transcription_s, 1.0)

    def test_observations_non_objet_ne_levent_jamais(self) -> None:
        # Chaîne, liste, nombre ou booléen à la place d'un objet : la lecture
        # expose l'état `invalide` sans exception et ne substitue rien.
        for valeur in ("Traceback: OSError recopié", [1, 2], 42, True):
            with self.subTest(valeur=type(valeur).__name__):
                ecrire_essai(
                    self.donnees,
                    IDENTIFIANT,
                    observation_chargement=valeur,
                    observation_audio=valeur,
                )

                vue = self.service.detail(IDENTIFIANT)

                self.assertEqual(vue.mesures.observation_chargement.etat, "invalide")
                self.assertEqual(vue.audios[0].observation_systeme.etat, "invalide")
                self.assertIsNone(vue.mesures.observation_chargement.cpu)
                self.assertIsNone(vue.audios[0].observation_systeme.memoire_apres)

    def test_version_inconnue_n_est_jamais_interpretee(self) -> None:
        ecrire_essai(
            self.donnees,
            IDENTIFIANT,
            observation_chargement=observation(version=2),
            observation_audio=observation(version=2, cpu=cpu_systeme()),
        )

        detail = self.service.detail(IDENTIFIANT)

        for vue in (
            detail.mesures.observation_chargement,
            detail.audios[0].observation_systeme,
        ):
            self.assertEqual(vue.etat, "version_inconnue")
            self.assertIn(vue.etat, ETATS_LECTURE)
            self.assertNotIn(vue.etat, MOTIFS_ECRITS)
            self.assertEqual(vue.motif, MOTIF_VERSION_OBSERVATION_INCONNUE)
            self.assertEqual(vue.version, 2)
            self.assertFalse(vue.lisible)
            self.assertTrue(vue.cle_presente)
            self.assertIsNone(vue.provenance)
            self.assertIsNone(vue.methode_cpu)
            self.assertIsNone(vue.cpu)
            self.assertIsNone(vue.memoire_apres)

        transcription = detail.audios[0].transcription
        assert transcription is not None
        self.assertEqual(transcription.texte, "transcription simulée de test")

    def test_version_non_entiere_reste_un_objet_invalide(self) -> None:
        ecrire_essai(
            self.donnees,
            IDENTIFIANT,
            observation_chargement=observation(version="2"),
            observation_audio=observation(version=None, cpu=cpu_systeme()),
        )

        detail = self.service.detail(IDENTIFIANT)

        self.assertEqual(detail.mesures.observation_chargement.etat, "invalide")
        self.assertEqual(detail.audios[0].observation_systeme.etat, "invalide")
        self.assertIsNone(detail.mesures.observation_chargement.version)

    def test_objet_hors_contrat_par_emplacement_est_invalide(self) -> None:
        # Un relevé de chargement ne porte pas de CPU moyen ; un relevé d'audio
        # en exige un.
        ecrire_essai(
            self.donnees,
            IDENTIFIANT,
            observation_chargement=observation(cpu=cpu_systeme()),
            observation_audio={
                "version": VERSION_METHODE,
                "methode_cpu": METHODE_CPU,
                "version_psutil": "7.2.2",
                "provenance": PROVENANCE_SIMULEE,
                "memoire_apres": memoire_systeme(),
            },
        )

        detail = self.service.detail(IDENTIFIANT)

        self.assertEqual(detail.mesures.observation_chargement.etat, "invalide")
        self.assertEqual(detail.audios[0].observation_systeme.etat, "invalide")

    def test_provenance_contradictoire_ecartee_a_la_lecture(self) -> None:
        ecrire_essai(
            self.donnees,
            IDENTIFIANT,
            observation_chargement=observation(provenance=PROVENANCE_REELLE),
            observation_audio=observation(
                provenance=PROVENANCE_REELLE, cpu=cpu_systeme()
            ),
        )

        detail = self.service.detail(IDENTIFIANT)

        for vue in (
            detail.mesures.observation_chargement,
            detail.audios[0].observation_systeme,
        ):
            self.assertEqual(vue.etat, "invalide")
            self.assertTrue(vue.motif)
            self.assertIsNone(vue.provenance)


class ObservationValideTest(SocleConsultationTest):
    def test_objet_valide_expose_valeurs_motifs_et_provenance(self) -> None:
        ecrire_essai(
            self.donnees,
            IDENTIFIANT,
            observation_chargement=observation(
                memoire=memoire_systeme(totale=16 * GIO, disponible=5 * GIO)
            ),
            observation_audio=observation(
                cpu=cpu_systeme(
                    pourcentage=None,
                    intervalle=0.05,
                    motif=MOTIF_INTERVALLE_TROP_COURT,
                ),
                memoire=memoire_systeme(
                    totale=16 * GIO,
                    disponible=None,
                    motif=MOTIF_VALEUR_INCOHERENTE,
                ),
            ),
        )

        detail = self.service.detail(IDENTIFIANT)
        chargement = detail.mesures.observation_chargement
        audio = detail.audios[0].observation_systeme

        self.assertTrue(chargement.lisible)
        self.assertIsNone(chargement.etat)
        self.assertEqual(chargement.version, VERSION_METHODE)
        self.assertEqual(chargement.methode_cpu, METHODE_CPU)
        self.assertEqual(chargement.version_psutil, "7.2.2")
        self.assertEqual(chargement.provenance, PROVENANCE_SIMULEE)
        self.assertTrue(chargement.simulee)
        self.assertIsNone(chargement.cpu)
        assert chargement.memoire_apres is not None
        self.assertEqual(chargement.memoire_apres.releve_le, RELEVE_SIMULE)
        self.assertEqual(chargement.memoire_apres.totale_octets, 16 * GIO)
        self.assertEqual(chargement.memoire_apres.disponible_octets, 5 * GIO)
        self.assertIsNone(chargement.memoire_apres.motif)

        self.assertTrue(audio.lisible)
        assert audio.cpu is not None
        self.assertIsNone(audio.cpu.pourcentage_moyen)
        self.assertEqual(audio.cpu.intervalle_s, 0.05)
        self.assertEqual(audio.cpu.motif, MOTIF_INTERVALLE_TROP_COURT)
        assert audio.memoire_apres is not None
        self.assertEqual(audio.memoire_apres.totale_octets, 16 * GIO)
        self.assertIsNone(audio.memoire_apres.disponible_octets)
        self.assertEqual(audio.memoire_apres.motif, MOTIF_VALEUR_INCOHERENTE)

    def test_vues_n_exposent_aucune_marge_ni_part_inventee(self) -> None:
        # Le contexte système et les indicateurs moteur restent deux objets
        # distincts : aucune marge (total - pic) ni part « autres applications ».
        champs = set(ObservationSystemeVue.__dataclass_fields__)
        self.assertEqual(
            champs,
            {
                "etat",
                "cle_presente",
                "motif",
                "provenance",
                "version",
                "methode_cpu",
                "version_psutil",
                "cpu",
                "memoire_apres",
            },
        )
        for interdit in ("marge", "part_autres", "part_ram", "occupation_cpu"):
            self.assertNotIn(interdit, champs)

    def test_provenance_simulee_exposee_et_date_de_scenario(self) -> None:
        ecrire_essai(
            self.donnees,
            IDENTIFIANT,
            observation_chargement=observation(
                memoire=memoire_systeme(releve_le=SIMULATION_RELEVE_LE)
            ),
            observation_audio=observation(
                cpu=cpu_systeme(),
                memoire=memoire_systeme(releve_le=SIMULATION_RELEVE_LE),
            ),
        )

        detail = self.service.detail(IDENTIFIANT)
        audio = detail.audios[0].observation_systeme

        # La date du scénario est exposée telle quelle : seule la provenance
        # permet de la distinguer d'une vraie date de relevé.
        self.assertEqual(audio.provenance, PROVENANCE_SIMULEE)
        self.assertTrue(audio.simulee)
        assert audio.memoire_apres is not None
        self.assertEqual(audio.memoire_apres.releve_le, SIMULATION_RELEVE_LE)

    def test_provenance_reelle_distincte_de_la_simulation(self) -> None:
        ecrire_essai(
            self.donnees,
            IDENTIFIANT,
            observation_chargement=observation(provenance=PROVENANCE_REELLE),
            observation_audio=observation(
                provenance=PROVENANCE_REELLE, cpu=cpu_systeme()
            ),
            mesures_simulees=False,
        )

        detail = self.service.detail(IDENTIFIANT)
        audio = detail.audios[0].observation_systeme

        self.assertTrue(audio.lisible)
        self.assertEqual(audio.provenance, PROVENANCE_REELLE)
        self.assertFalse(audio.simulee)


class RelectureTest(SocleConsultationTest):
    def test_lecture_ne_reecrit_aucun_fichier(self) -> None:
        for identifiant in (IDENTIFIANT, IDENTIFIANT_ANCIEN):
            ecrire_essai(
                self.donnees,
                identifiant,
                observation_chargement=observation(),
                observation_audio=observation(cpu=cpu_systeme()),
            )
        dossier = self.donnees / "results" / IDENTIFIANT
        resultat = dossier / "1-a.wav" / "result.json"
        self.assertTrue(resultat.is_file())
        fichiers = (dossier / "run.json", resultat)
        etats = {
            chemin: (chemin.read_bytes(), chemin.stat().st_mtime_ns)
            for chemin in fichiers
        }

        detail = self.service.detail(IDENTIFIANT)
        self.service.groupes_par_empreinte()
        transcription = detail.audios[0].transcription
        assert transcription is not None
        self.service.comparer(
            transcription.empreinte_sha256 or "",
            ((IDENTIFIANT, 1), (IDENTIFIANT_ANCIEN, 1)),
        )

        for chemin, (contenu, mtime) in etats.items():
            self.assertEqual(chemin.read_bytes(), contenu)
            self.assertEqual(chemin.stat().st_mtime_ns, mtime)

    def test_mesures_lisibles_apres_suppression_du_modele_local(self) -> None:
        ecrire_essai(
            self.donnees,
            IDENTIFIANT,
            observation_chargement=observation(),
            observation_audio=observation(cpu=cpu_systeme()),
        )
        modele = self.donnees / "models" / "factice" / ("0" * 64)
        modele.mkdir(parents=True)
        (modele / "modele.bin").write_bytes(b"poids simules")

        avant = self.service.detail(IDENTIFIANT)
        shutil.rmtree(self.donnees / "models")
        self.assertFalse((self.donnees / "models").exists())
        apres = self.service.detail(IDENTIFIANT)

        self.assertEqual(apres.mesures, avant.mesures)
        self.assertEqual(
            apres.audios[0].observation_systeme,
            avant.audios[0].observation_systeme,
        )
        avant_transcription = avant.audios[0].transcription
        apres_transcription = apres.audios[0].transcription
        assert avant_transcription is not None and apres_transcription is not None
        self.assertEqual(apres_transcription.mesures, avant_transcription.mesures)
        self.assertEqual(apres_transcription.texte, "transcription simulée de test")


class ComparaisonTest(SocleConsultationTest):
    def test_entrees_exposent_les_deux_observations_sans_ratio_invente(self) -> None:
        for identifiant in (IDENTIFIANT, IDENTIFIANT_ANCIEN):
            ecrire_essai(
                self.donnees,
                identifiant,
                observation_chargement=observation(),
                observation_audio=observation(cpu=cpu_systeme(pourcentage=90.0)),
            )

        groupe = self.service.groupes_par_empreinte()[0]

        self.assertEqual(len(groupe.entrees), 2)
        for entree in groupe.entrees:
            self.assertTrue(entree.observation_systeme.lisible)
            self.assertTrue(entree.observation_chargement.lisible)
            assert entree.observation_systeme.cpu is not None
            self.assertEqual(entree.observation_systeme.cpu.pourcentage_moyen, 90.0)
            # L'indicateur moteur reste calculé sur les valeurs du moteur et du
            # matériel consignés, jamais sur le CPU système.
            self.assertEqual(
                entree.indicateurs.occupation_cpu, ratio_cpu(1.5, 1.0, 8)
            )
            self.assertNotEqual(entree.indicateurs.occupation_cpu, 90.0)

        comparaison = self.service.comparer(
            groupe.empreinte, ((IDENTIFIANT, 1), (IDENTIFIANT_ANCIEN, 1))
        )
        for carte in comparaison.cartes:
            self.assertTrue(carte.entree.observation_systeme.lisible)
            self.assertTrue(carte.entree.observation_chargement.lisible)

    def test_entree_sans_observation_reste_non_mesuree(self) -> None:
        for identifiant in (IDENTIFIANT, IDENTIFIANT_ANCIEN):
            run = run_json(identifiant)
            ecrire_execution(
                self.donnees,
                run,
                (result_json(run["audios"][0], execution=identifiant),),
            )

        groupe = self.service.groupes_par_empreinte()[0]

        self.assertEqual(len(groupe.entrees), 2)
        for entree in groupe.entrees:
            self.assertEqual(entree.observation_systeme.etat, "absent")
            self.assertEqual(entree.observation_chargement.etat, "absent")


class AucuneValeurLocaleTest(SocleConsultationTest):
    def test_lecture_n_interroge_pas_l_ordinateur_courant(self) -> None:
        ecrire_essai(
            self.donnees,
            IDENTIFIANT,
            observation_chargement=observation(
                memoire=memoire_systeme(totale=16 * GIO, disponible=5 * GIO)
            ),
            observation_audio=observation(
                cpu=cpu_systeme(),
                memoire=memoire_systeme(totale=16 * GIO, disponible=5 * GIO),
            ),
        )
        run_ancien = run_json(IDENTIFIANT_ANCIEN)
        ecrire_execution(
            self.donnees, run_ancien, (result_json(run_ancien["audios"][0]),)
        )

        with mock.patch.object(
            psutil, "cpu_percent", side_effect=AssertionError("mesure locale")
        ) as cpu_percent, mock.patch.object(
            psutil, "virtual_memory", side_effect=AssertionError("mesure locale")
        ) as memoire:
            detail = self.service.detail(IDENTIFIANT)
            ancien = self.service.detail(IDENTIFIANT_ANCIEN)
            self.service.groupes_par_empreinte()

        cpu_percent.assert_not_called()
        memoire.assert_not_called()

        # Les valeurs exposées sont celles du fichier, pas celles du poste.
        audio = detail.audios[0].observation_systeme
        assert audio.cpu is not None and audio.memoire_apres is not None
        self.assertEqual(audio.cpu.pourcentage_moyen, 90.0)
        self.assertEqual(audio.memoire_apres.totale_octets, 16 * GIO)
        self.assertEqual(audio.memoire_apres.disponible_octets, 5 * GIO)
        # Un ancien fichier reste explicitement non mesuré, sans valeur locale.
        self.assertEqual(ancien.mesures.observation_chargement.etat, "absent")
        self.assertEqual(ancien.audios[0].observation_systeme.etat, "absent")

    def test_lecture_d_un_essai_abandonne_ne_complete_aucun_releve(self) -> None:
        """Essai abandonné après l'audio 1 : absence explicite pour l'audio 2."""
        run = run_json(
            etat=ETAT_ABANDONNEE,
            audios=(("a.wav", STATUT_OK), ("b.wav", STATUT_NON_TRAITE)),
            mesures=mesures_execution(**{CLE_OBSERVATION_CHARGEMENT: observation()}),
        )
        premier = result_json(
            run["audios"][0],
            mesures_extra={CLE_OBSERVATION_AUDIO: observation(cpu=cpu_systeme())},
        )
        ecrire_execution(self.donnees, run, (premier,))

        with mock.patch.object(
            psutil, "cpu_percent", side_effect=AssertionError("mesure locale")
        ) as cpu_percent, mock.patch.object(
            psutil, "virtual_memory", side_effect=AssertionError("mesure locale")
        ) as memoire:
            detail = self.service.detail(IDENTIFIANT)

        cpu_percent.assert_not_called()
        memoire.assert_not_called()

        # L'essai abandonné garde son instantané de chargement et le relevé déjà
        # écrit de l'audio terminé, tels quels.
        chargement = detail.mesures.observation_chargement
        self.assertTrue(chargement.lisible)
        self.assertEqual(chargement.provenance, PROVENANCE_SIMULEE)
        audio = detail.audios[0].observation_systeme
        self.assertTrue(audio.lisible)
        assert audio.cpu is not None and audio.memoire_apres is not None
        self.assertEqual(audio.cpu.pourcentage_moyen, 90.0)
        self.assertEqual(audio.memoire_apres.totale_octets, 8 * GIO)

        # L'audio non terminé reste explicitement non mesuré : ni observation
        # simulée, ni valeur du poste courant, ni clé écartée.
        second = detail.audios[1].observation_systeme
        self.assertEqual(second.etat, "absent")
        self.assertFalse(second.cle_presente)
        self.assertFalse(second.lisible)
        self.assertIsNone(second.cpu)
        self.assertIsNone(second.memoire_apres)
        self.assertIsNone(second.provenance)


if __name__ == "__main__":
    unittest.main()
