"""Tests de la consultation des résultats (tâche 7.1), sans moteur ni réseau.

Les fichiers de résultats sont des données synthétiques écrites par les helpers
de ce module dans un dossier temporaire : aucun test n'écrit sous le `data/` du
dépôt, ne lance d'inférence ou n'émet de requête réseau. Les tests de page qui
réutilisent ces fixtures vivent dans `tests/test_resultats_web.py`.
"""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from typing import Any

from tests.test_execution_moteur import SocleExecutionTest
from transcription_bench.consultation_resultats import (
    MOTIF_DOSSIER_REFUSE,
    MOTIF_FICHIER_REFUSE,
    MOTIF_NON_TRAITE,
    MOTIF_RESULTAT_ABSENT,
    MOTIF_RESULTAT_ILLISIBLE,
    REPERE_RTF,
    ConsultationResultats,
    LectureResultatsImpossible,
    ResultatIntrouvable,
    ResultatNonInterpretable,
)
from transcription_bench.paths import ValeurRefusee
from transcription_bench.resultats import (
    ETAT_ABANDONNEE,
    ETAT_ECHOUEE,
    ETAT_EN_COURS,
    ETAT_INTERROMPUE,
    ETAT_TERMINEE,
    SCHEMA,
    STATUT_ERREUR,
    STATUT_NON_TRAITE,
    STATUT_OK,
    nom_dossier_audio,
)
from transcription_bench.stockage import ecrire_json_atomique

IDENTIFIANT = "20240102-030405-0a0b0c0d"
IDENTIFIANT_ANCIEN = "20240101-010101-11223344"


def plan_audio(ordre: int, nom: str, statut: str = STATUT_OK) -> dict[str, Any]:
    """Plan d'audio tel que `run.json` le consigne."""
    return {
        "ordre": ordre,
        "nom": nom,
        "dossier": nom_dossier_audio(ordre, nom),
        "statut": statut,
        "erreur": None,
        "fenetre_s": 30.0 if statut != STATUT_NON_TRAITE else None,
        "decoupage": "fenetres-fixes" if statut != STATUT_NON_TRAITE else None,
    }


def run_json(
    identifiant: str = IDENTIFIANT,
    *,
    etat: str = ETAT_TERMINEE,
    schema: Any = SCHEMA,
    audios: tuple[tuple[str, str], ...] = (("a.wav", STATUT_OK),),
    mesures: dict[str, Any] | None = None,
    erreur: str | None = None,
    **remplacements: Any,
) -> dict[str, Any]:
    """`run.json` synthétique complet, conforme au format décrit en D11."""
    plans = [
        plan_audio(position + 1, nom, statut)
        for position, (nom, statut) in enumerate(audios)
    ]
    if mesures is None:
        mesures = {
            "duree_operation_s": 12.5,
            "duree_processus_s": 11.0,
            "duree_chargement_s": 2.0,
            "pic_memoire_octets": 123456789,
            "pic_memoire_partiel": False,
        }
    contenu: dict[str, Any] = {
        "schema": schema,
        "identifiant": identifiant,
        "etat": etat,
        "cree_le": "2024-01-02T03:04:05+00:00",
        "fin": "2024-01-02T03:05:00+00:00",
        "erreur": erreur,
        "factice": True,
        "synthetique": True,
        "mesures_simulees": True,
        "demande": {
            "moteur": "factice",
            "famille": "factice",
            "modele": {
                "identifiant": "aucun modèle, textes et mesures simulés",
                "id_resolu": "aucun modèle, textes et mesures simulés",
                "commit": "aucun",
                "cle": "0" * 64,
                "fichier_gguf": None,
            },
            "audios": [nom for nom, _statut in audios],
            "threads_demandes": 2,
            "reglages": {"langue": "fr"},
            "fenetre_fixe_secondes": 30.0,
        },
        "moteur": {
            "identifiant": "factice",
            "nom": "Moteur factice",
            "factice": True,
            "empreinte_verrou": None,
            "versions": None,
        },
        "machine": {
            "os": "Linux",
            "version_os": "6.1",
            "architecture": "x86_64",
            "processeur": None,
            "coeurs_physiques": 4,
            "coeurs_logiques": 8,
            "ram_totale_octets": 8 * 1024**3,
        },
        "programme": {
            "nom": "transcription-bench",
            "version": "0.1.0",
            "python": "3.12.0",
            "empreinte_verrou": "b" * 64,
            "pyav": "19.0.2",
            "ffmpeg": {"version": "7.1", "bibliotheques": {}},
        },
        "processus_moteur": {
            "pid": 4242,
            "heure_creation": None,
            "heure_creation_source": "serveur",
            "lance_a": "2024-01-02T03:04:06+00:00",
            "code_sortie": 0,
        },
        "effectifs": {
            "threads_demandes": 2,
            "threads_appliques": None,
            "reglages_effectifs": {},
        },
        "mesures": mesures,
        "progression": {"audios_traites": 0, "audios_total": len(plans)},
        "audios": plans,
    }
    contenu.update(remplacements)
    return contenu


def result_json(
    plan: dict[str, Any],
    *,
    execution: str = IDENTIFIANT,
    schema: Any = SCHEMA,
    statut: str = STATUT_OK,
    duree_decodee: float | None = 2.0,
    duree_transcription: float | None = 1.0,
    texte: str | None = "transcription simulée de test",
    segments: list[dict[str, Any]] | None = None,
    mesures_extra: dict[str, Any] | None = None,
    **remplacements: Any,
) -> dict[str, Any]:
    """`result.json` synthétique complet, avec des mesures explicites."""
    if segments is None:
        segments = [{"debut_s": 0.0, "fin_s": 1.0, "texte": texte or ""}]
    mesures: dict[str, Any] = {
        "temps_decodage_s": 0.25,
        "duree_transcription_s": duree_transcription,
        "temps_cpu_s": 1.5,
        "rtf": None,
        "pic_memoire_octets": 2048,
    }
    if mesures_extra is not None:
        mesures.update(mesures_extra)
    contenu: dict[str, Any] = {
        "schema": schema,
        "execution": execution,
        "ordre": plan["ordre"],
        "nom": plan["nom"],
        "dossier": plan["dossier"],
        "statut": statut,
        "ecrit_le": "2024-01-02T03:04:30+00:00",
        "factice": True,
        "synthetique": True,
        "mesures_simulees": True,
        "audio": {
            "nom": plan["nom"],
            "format": "wav",
            "taille_octets": 64044,
            "empreinte_sha256": "c" * 64,
            "duree_indicative_s": duree_decodee,
            "duree_decodee_s": duree_decodee,
            "echantillons": (
                None if duree_decodee is None else int(duree_decodee * 16000)
            ),
        },
        "modele": {"famille": "factice"},
        "moteur": {"identifiant": "factice", "nom": "Moteur factice"},
        "machine": {"os": "Linux"},
        "programme": {"nom": "transcription-bench"},
        "reglages": {"langue": "fr"},
        "reglages_effectifs": {"langue": "fr"},
        "timings_natifs": [
            {
                "unite": "ms",
                "load_ms": 12.5,
                "mel_ms": 3.25,
                "encode_ms": 40.0,
                "decode_ms": 60.5,
            }
        ],
        "langue_imposee": "fr",
        "threads": {"demandes": 2, "appliques": None},
        "fenetre": {"duree_s": 30.0, "decoupage": "fenetres-fixes", "nb_fenetres": 1},
        "mesures": mesures,
        "transcription": (
            None if texte is None else {"texte": texte, "segments": segments}
        ),
        "erreur": None,
    }
    contenu.update(remplacements)
    return contenu


def ecrire_execution(
    donnees: Path | str,
    run: dict[str, Any],
    resultats: tuple[dict[str, Any], ...] = (),
) -> Path:
    """Écrit `run.json` et les `result.json` fournis sous `donnees/results`."""
    dossier = Path(donnees) / "results" / run["identifiant"]
    ecrire_json_atomique(dossier / "run.json", run)
    for resultat in resultats:
        ecrire_json_atomique(
            dossier / str(resultat["dossier"]) / "result.json", resultat
        )
    return dossier


def execution_complete(
    donnees: Path | str,
    identifiant: str = IDENTIFIANT,
    *,
    texte: str = "transcription simulée de test",
    **options: Any,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Écrit une exécution terminée d'un audio transcrit et renvoie ses JSON."""
    run = run_json(identifiant, **options)
    resultat = result_json(run["audios"][0], execution=identifiant, texte=texte)
    ecrire_execution(donnees, run, (resultat,))
    return run, resultat


class SocleConsultationTest(unittest.TestCase):
    """Dossier de données temporaire et service de consultation."""

    def setUp(self) -> None:
        temporaire = tempfile.TemporaryDirectory()
        self.addCleanup(temporaire.cleanup)
        self.donnees = Path(temporaire.name)
        self.service = ConsultationResultats(self.donnees)

    def creer_lien(self, cible: Path, lien: Path) -> None:
        """Crée un lien symbolique ou ignore le test si le poste le refuse."""
        try:
            os.symlink(cible, lien, target_is_directory=cible.is_dir())
        except (OSError, NotImplementedError) as erreur:
            self.skipTest(f"liens symboliques indisponibles sur ce poste : {erreur}")


class ListerExecutionsTest(SocleConsultationTest):
    def test_liste_vide_sans_dossier_ni_creation(self) -> None:
        self.assertEqual(self.service.lister(), ())
        self.assertFalse(self.service.dossier_resultats.exists())

    def test_ordre_du_plus_recent_au_plus_ancien_avec_etats_et_marques(self) -> None:
        recent = run_json(
            IDENTIFIANT,
            audios=(("a.wav", STATUT_OK), ("b.wav", STATUT_NON_TRAITE)),
        )
        ancien = run_json(
            IDENTIFIANT_ANCIEN,
            etat=ETAT_ABANDONNEE,
            mesures={
                "duree_operation_s": None,
                "duree_processus_s": None,
                "duree_chargement_s": 2.5,
                "pic_memoire_octets": 4096,
                "pic_memoire_partiel": True,
            },
        )
        ecrire_execution(self.donnees, recent, (result_json(recent["audios"][0]),))
        ecrire_execution(self.donnees, ancien)

        executions = self.service.lister()

        self.assertEqual(
            [execution.identifiant for execution in executions],
            [IDENTIFIANT, IDENTIFIANT_ANCIEN],
        )
        premier = executions[0]
        self.assertEqual(premier.libelle_etat, "terminée")
        self.assertFalse(premier.partiel)
        self.assertEqual(premier.modele, "aucun modèle, textes et mesures simulés")
        self.assertEqual(premier.moteur, "Moteur factice")
        self.assertEqual((premier.audios_traites, premier.audios_total), (1, 2))
        self.assertEqual(premier.duree_operation_s, 12.5)
        self.assertIn("FACTICE", premier.marques)
        self.assertIn("SYNTHÉTIQUE", premier.marques)
        self.assertIn("MESURES SIMULÉES", premier.marques)
        self.assertTrue(premier.exploitable)
        second = executions[1]
        self.assertEqual(second.libelle_etat, "abandonnée")
        self.assertTrue(second.partiel)
        self.assertIsNone(second.duree_operation_s)

    def test_dossier_sans_run_json_noms_non_conformes_et_liens_ignores(self) -> None:
        racine = self.donnees / "results"
        racine.mkdir(parents=True)
        (racine / "20240103-000000-deadbeef").mkdir()  # création interrompue
        (racine / "pas-un-identifiant").mkdir()
        exterieur = self.donnees / "ailleurs"
        exterieur.mkdir()
        ecrire_json_atomique(
            exterieur / "run.json", run_json("20240105-000000-aaaaaaaa")
        )
        try:
            os.symlink(exterieur, racine / "20240105-000000-aaaaaaaa")
        except (OSError, NotImplementedError):
            self.skipTest("création de lien symbolique non autorisée sur ce poste")
        ecrire_execution(self.donnees, run_json())

        executions = self.service.lister()

        self.assertEqual([execution.identifiant for execution in executions], [IDENTIFIANT])

    def test_entree_illisible_schema_inconnu_ou_incoherente_listee_sans_exception(
        self,
    ) -> None:
        racine = self.donnees / "results"
        racine.mkdir(parents=True)
        (racine / "20240102-000000-00000001").mkdir()
        (racine / "20240102-000000-00000001" / "run.json").write_text(
            "{ pas du json", encoding="utf-8"
        )
        ecrire_execution(self.donnees, run_json("20240102-000000-00000002", schema=2))
        incoherent = run_json("20240102-000000-00000003")
        ecrire_execution(self.donnees, incoherent)
        # Identifiant du fichier différent du nom du dossier : refusé.
        ecrire_json_atomique(
            self.donnees / "results" / "20240102-000000-00000003" / "run.json",
            {**incoherent, "identifiant": "20240102-000000-00000004"},
        )

        executions = self.service.lister()

        self.assertEqual(len(executions), 3)
        for execution in executions:
            with self.subTest(identifiant=execution.identifiant):
                self.assertFalse(execution.exploitable)
                self.assertEqual(execution.libelle_etat, "non interprétable")
                self.assertIsNone(execution.etat)
                self.assertIsNone(execution.duree_operation_s)
                self.assertIsNone(execution.audios_traites)
                self.assertIsNone(execution.marques)
                self.assertTrue(execution.motif)

    def test_dossier_resultats_qui_est_un_fichier_refuse(self) -> None:
        self.donnees.mkdir(parents=True, exist_ok=True)
        (self.donnees / "results").write_text("pas un dossier", encoding="utf-8")

        with self.assertRaises(LectureResultatsImpossible):
            self.service.lister()


class DetailExecutionTest(SocleConsultationTest):
    def test_detail_transcription_metadonnees_et_mesures(self) -> None:
        run = run_json(audios=(("a.wav", STATUT_OK),))
        resultat = result_json(
            run["audios"][0],
            duree_decodee=4.0,
            duree_transcription=2.0,
            texte="Texte <simulé> & factice",
            mesures_extra={"rtf": 9.0},
        )
        ecrire_execution(self.donnees, run, (resultat,))

        detail = self.service.detail(IDENTIFIANT)

        self.assertFalse(detail.partiel)
        self.assertEqual(detail.execution.libelle_etat, "terminée")
        self.assertEqual(detail.execution.audios_traites, 1)
        self.assertEqual(detail.mesures.duree_operation_s, 12.5)
        self.assertEqual(detail.mesures.duree_processus_s, 11.0)
        self.assertEqual(detail.mesures.duree_chargement_s, 2.0)
        self.assertEqual(detail.famille, "factice")
        self.assertEqual(detail.threads_demandes, 2)
        self.assertIsNone(detail.threads_appliques)
        self.assertEqual(detail.fenetre_fixe_s, 30.0)
        self.assertEqual(detail.reglages, (("langue", "fr"),))
        self.assertIn(
            ("Identifiant demandé", "aucun modèle, textes et mesures simulés"),
            detail.modele,
        )
        self.assertIn(("Nom du moteur", "Moteur factice"), detail.moteur)
        self.assertIn(("Système d'exploitation", "Linux"), detail.machine)
        self.assertIn(("Python", "3.12.0"), detail.programme)
        self.assertEqual(detail.processus[0], ("PID du moteur", 4242))

        audio = detail.audios[0]
        self.assertEqual(audio.statut, STATUT_OK)
        self.assertFalse(audio.partiel)
        self.assertIsNone(audio.motif_indisponible)
        transcription = audio.transcription
        self.assertIsNotNone(transcription)
        self.assertEqual(transcription.texte, "Texte <simulé> & factice")
        self.assertEqual(len(transcription.segments), 1)
        self.assertEqual(transcription.segments[0].debut_s, 0.0)
        self.assertEqual(transcription.mesures.temps_decodage_s, 0.25)
        self.assertEqual(transcription.mesures.duree_transcription_s, 2.0)
        self.assertEqual(transcription.mesures.temps_cpu_s, 1.5)
        # RTF recalculé sur la durée décodée, jamais repris du fichier.
        self.assertAlmostEqual(transcription.mesures.rtf, 0.5)
        self.assertIn(("Durée décodée (s)", 4.0), transcription.audio)
        self.assertEqual(transcription.langue_imposee, "fr")
        self.assertEqual(len(transcription.timings_natifs), 1)
        self.assertEqual(transcription.timings_natifs[0].unite, "ms")
        self.assertEqual(transcription.timings_natifs[0].chargement, 12.5)
        self.assertEqual(transcription.timings_natifs[0].decodage, 60.5)
        self.assertIn(("Threads demandés", 2), transcription.threads)
        self.assertIn(("Nombre de fenêtres", 1), transcription.fenetre)
        self.assertIn("FACTICE", transcription.marques)

    def test_timings_natifs_par_appel_sans_valeur_inventee(self) -> None:
        run = run_json(audios=(("a.wav", STATUT_OK),))
        resultat = result_json(
            run["audios"][0],
            timings_natifs=[
                {
                    "unite": "ms",
                    "load_ms": 12.5,
                    "mel_ms": None,
                    "encode_ms": 40.0,
                    "decode_ms": 60.5,
                },
                {
                    "unite": "ms",
                    "load_ms": 1.0,
                    "mel_ms": 2.0,
                    "encode_ms": 3.0,
                    "decode_ms": None,
                },
            ],
        )
        ecrire_execution(self.donnees, run, (resultat,))

        detail = self.service.detail(IDENTIFIANT)

        timings = detail.audios[0].transcription.timings_natifs
        self.assertEqual([timing.chargement for timing in timings], [12.5, 1.0])
        self.assertIsNone(timings[0].mel)
        self.assertIsNone(timings[1].decodage)

    def test_resultat_anterieur_sans_timings_natifs_reste_lisible(self) -> None:
        run = run_json(audios=(("a.wav", STATUT_OK),))
        resultat = result_json(run["audios"][0])
        # Résultat antérieur au champ, et entrées illisibles écartées.
        resultat["timings_natifs"] = ["pas un objet", {"load_ms": 1.0}]
        ecrire_execution(self.donnees, run, (resultat,))

        detail = self.service.detail(IDENTIFIANT)

        self.assertEqual(detail.audios[0].transcription.timings_natifs, ())
        del resultat["timings_natifs"]
        ecrire_execution(self.donnees, run, (resultat,))
        self.assertEqual(
            self.service.detail(IDENTIFIANT)
            .audios[0]
            .transcription.timings_natifs,
            (),
        )

    def test_rtf_absent_sur_duree_nulle_et_conserve_au_dessus_du_repere(
        self,
    ) -> None:
        run = run_json(
            audios=(("nul.wav", STATUT_OK), ("lent.wav", STATUT_OK)),
        )
        nul = result_json(run["audios"][0], duree_decodee=0.0, duree_transcription=1.0)
        lent = result_json(
            run["audios"][1],
            duree_decodee=1.0,
            duree_transcription=3.0,
            mesures_extra={"rtf": 3.0},
        )
        ecrire_execution(self.donnees, run, (nul, lent))

        audios = self.service.detail(IDENTIFIANT).audios

        self.assertIsNone(audios[0].transcription.mesures.rtf)
        self.assertAlmostEqual(audios[1].transcription.mesures.rtf, 3.0)
        self.assertGreater(audios[1].transcription.mesures.rtf, REPERE_RTF)
        self.assertEqual(audios[1].statut, STATUT_OK)

    def test_mesures_globales_absentes_restees_absentes(self) -> None:
        run = run_json(
            etat=ETAT_ABANDONNEE,
            audios=(("a.wav", STATUT_NON_TRAITE),),
            mesures={
                "duree_operation_s": None,
                "duree_processus_s": None,
                "duree_chargement_s": 2.5,
                "pic_memoire_octets": 4096,
                "pic_memoire_partiel": True,
            },
        )
        ecrire_execution(self.donnees, run)

        detail = self.service.detail(IDENTIFIANT)

        self.assertTrue(detail.partiel)
        self.assertEqual(detail.execution.libelle_etat, "abandonnée")
        self.assertIsNone(detail.mesures.duree_operation_s)
        self.assertIsNone(detail.mesures.duree_processus_s)
        self.assertEqual(detail.mesures.duree_chargement_s, 2.5)
        self.assertEqual(detail.mesures.pic_memoire_octets, 4096)
        self.assertTrue(detail.mesures.pic_memoire_partiel)
        self.assertIsNone(detail.execution.duree_operation_s)
        self.assertEqual(
            detail.audios[0].motif_indisponible,
            MOTIF_NON_TRAITE,
        )

    def test_resultats_partiels_d_une_execution_en_cours(self) -> None:
        run = run_json(
            etat=ETAT_EN_COURS,
            audios=(("a.wav", STATUT_OK), ("b.wav", STATUT_NON_TRAITE)),
        )
        ecrire_execution(self.donnees, run, (result_json(run["audios"][0]),))

        detail = self.service.detail(IDENTIFIANT)

        self.assertTrue(detail.partiel)
        self.assertEqual(detail.execution.libelle_etat, "en cours")
        self.assertEqual(detail.execution.audios_traites, 1)
        premier, second = detail.audios
        self.assertTrue(premier.partiel)
        self.assertIsNotNone(premier.transcription)
        self.assertIsNone(second.transcription)
        self.assertFalse(second.partiel)
        self.assertEqual(second.statut, STATUT_NON_TRAITE)
        self.assertEqual(second.motif_indisponible, MOTIF_NON_TRAITE)

    def test_resultat_ecrit_avant_le_suivi_fait_foi(self) -> None:
        run = run_json(
            etat=ETAT_EN_COURS, audios=(("a.wav", STATUT_NON_TRAITE),)
        )
        ecrire_execution(self.donnees, run, (result_json(run["audios"][0]),))

        audio = self.service.detail(IDENTIFIANT).audios[0]

        self.assertIsNotNone(audio.transcription)
        self.assertEqual(audio.statut, STATUT_OK)
        self.assertEqual(audio.libelle_statut, "transcrit")
        self.assertIsNone(audio.motif_indisponible)
        self.assertTrue(audio.partiel)

    def test_resultat_manquant_illisible_ou_schema_inconnu_signale(self) -> None:
        run = run_json(
            audios=(
                ("absente.wav", STATUT_OK),
                ("illisible.wav", STATUT_ERREUR),
                ("schema.wav", STATUT_OK),
            ),
        )
        ecrire_execution(self.donnees, run)
        dossier = self.service.dossier_resultats / IDENTIFIANT
        illisible = dossier / run["audios"][1]["dossier"]
        illisible.mkdir(parents=True)
        (illisible / "result.json").write_text("{ pas du json", encoding="utf-8")
        ecrire_json_atomique(
            dossier / run["audios"][2]["dossier"] / "result.json",
            result_json(run["audios"][2], schema=99),
        )

        audios = self.service.detail(IDENTIFIANT).audios

        self.assertIsNone(audios[0].transcription)
        self.assertEqual(audios[0].motif_indisponible, MOTIF_RESULTAT_ABSENT)
        self.assertIsNone(audios[1].transcription)
        self.assertEqual(audios[1].motif_indisponible, MOTIF_RESULTAT_ILLISIBLE)
        self.assertIsNone(audios[2].transcription)
        self.assertIn("non interprétable", audios[2].motif_indisponible)
        self.assertIn("schéma non pris en charge", audios[2].motif_indisponible)

    def test_dossier_d_audio_hors_execution_refuse_sans_lecture(self) -> None:
        run = run_json(audios=(("a.wav", STATUT_OK),))
        plan = run["audios"][0]
        plan["dossier"] = "../evasion"
        ecrire_execution(self.donnees, run)
        evasion = self.service.dossier_resultats / "evasion"
        ecrire_json_atomique(
            evasion / "result.json", result_json(plan_audio(1, "a.wav"))
        )

        audio = self.service.detail(IDENTIFIANT).audios[0]

        self.assertIsNone(audio.transcription)
        self.assertEqual(audio.motif_indisponible, MOTIF_DOSSIER_REFUSE)


    def test_reglages_listes_et_objets_affiches_en_json_compact(self) -> None:
        run = run_json()
        run["demande"]["reglages"] = {
            "temperature": [0.0, 0.2, float("nan")],
            "options": {"b": 1, "a": "<valeur>"},
            "vide": None,
            "infinie": float("inf"),
        }
        resultat = result_json(run["audios"][0])
        resultat["reglages_effectifs"] = {"temperature": [0.0, float("inf")]}
        ecrire_execution(self.donnees, run, (resultat,))

        detail = self.service.detail(IDENTIFIANT)

        reglages = dict(detail.reglages)
        self.assertEqual(reglages["temperature"], "[0.0,0.2,null]")
        self.assertEqual(reglages["options"], '{"a":"<valeur>","b":1}')
        self.assertIsNone(reglages["vide"])
        self.assertIsNone(reglages["infinie"])
        self.assertEqual(
            dict(detail.audios[0].transcription.reglages_effectifs)["temperature"],
            "[0.0,null]",
        )

    def test_segments_avec_bornes_non_finies_gardent_texte_et_mesures(self) -> None:
        run = run_json()
        resultat = result_json(
            run["audios"][0],
            segments=[
                {
                    "debut_s": float("nan"),
                    "fin_s": float("inf"),
                    "texte": "segment conservé",
                }
            ],
        )
        ecrire_execution(self.donnees, run, (resultat,))

        transcription = self.service.detail(IDENTIFIANT).audios[0].transcription

        self.assertIsNotNone(transcription)
        segment = transcription.segments[0]
        self.assertIsNone(segment.debut_s)
        self.assertIsNone(segment.fin_s)
        self.assertEqual(segment.texte, "segment conservé")
        self.assertEqual(transcription.texte, "transcription simulée de test")
        self.assertAlmostEqual(transcription.mesures.rtf, 0.5)

    def test_segment_de_forme_invalide_refuse_sans_masquer_le_reste(self) -> None:
        run = run_json()
        resultat = result_json(
            run["audios"][0],
            segments=[{"debut_s": "0", "fin_s": 1.0, "texte": "borne textuelle"}],
        )
        ecrire_execution(self.donnees, run, (resultat,))

        audio = self.service.detail(IDENTIFIANT).audios[0]

        self.assertIsNone(audio.transcription)
        self.assertIn("non interprétable", audio.motif_indisponible)

    def test_metadonnees_processeur_et_versions_ffmpeg_affichees(self) -> None:
        run = run_json()
        run["machine"]["processeur"] = "Processeur de test"
        ecrire_execution(self.donnees, run, (result_json(run["audios"][0]),))

        detail = self.service.detail(IDENTIFIANT)

        self.assertIn(("Processeur", "Processeur de test"), detail.machine)
        self.assertIn(("FFmpeg", "7.1"), detail.programme)
        self.assertIn(("PyAV", "19.0.2"), detail.programme)

    def test_run_json_lien_sortant_jamais_lu(self) -> None:
        exterieur = self.donnees / "ailleurs"
        exterieur.mkdir()
        ecrire_json_atomique(exterieur / "run.json", run_json())
        dossier = self.service.dossier_resultats / IDENTIFIANT
        dossier.mkdir(parents=True)
        self.creer_lien(exterieur / "run.json", dossier / "run.json")

        with self.assertRaises(ResultatNonInterpretable):
            self.service.detail(IDENTIFIANT)
        (execution,) = self.service.lister()
        self.assertFalse(execution.exploitable)

    def test_result_json_lien_sortant_jamais_lu(self) -> None:
        run = run_json()
        ecrire_execution(self.donnees, run)
        dossier_audio = (
            self.service.dossier_resultats / IDENTIFIANT / run["audios"][0]["dossier"]
        )
        dossier_audio.mkdir(parents=True)
        secret = self.donnees / "secret"
        secret.mkdir()
        ecrire_json_atomique(
            secret / "result.json",
            result_json(run["audios"][0], texte="ne doit jamais apparaître"),
        )
        self.creer_lien(secret / "result.json", dossier_audio / "result.json")

        audio = self.service.detail(IDENTIFIANT).audios[0]

        self.assertIsNone(audio.transcription)
        self.assertEqual(audio.motif_indisponible, MOTIF_FICHIER_REFUSE)

    def test_resultat_d_un_autre_audio_n_est_jamais_attribue(self) -> None:
        run = run_json(audios=(("a.wav", STATUT_OK), ("b.wav", STATUT_OK)))
        ecrire_execution(self.donnees, run)
        dossier_a = (
            self.service.dossier_resultats / IDENTIFIANT / run["audios"][0]["dossier"]
        )
        reference = result_json(run["audios"][0], texte="texte de a")
        ecrire_json_atomique(dossier_a / "result.json", reference)
        self.assertIsNotNone(self.service.detail(IDENTIFIANT).audios[0].transcription)

        faux = {
            "execution": "20240101-010101-11223344",
            "ordre": 2,
            "nom": "b.wav",
            "dossier": "2-b.wav",
        }
        for champ, valeur in faux.items():
            with self.subTest(champ=champ):
                ecrire_json_atomique(
                    dossier_a / "result.json", {**reference, champ: valeur}
                )
                audio = self.service.detail(IDENTIFIANT).audios[0]
                self.assertIsNone(audio.transcription)
                self.assertIn("non interprétable", audio.motif_indisponible)

    def test_statut_de_type_inattendu_refuse_sans_type_error(self) -> None:
        run = run_json()
        run["audios"][0]["statut"] = []
        ecrire_execution(self.donnees, run)

        (execution,) = self.service.lister()

        self.assertFalse(execution.exploitable)
        with self.assertRaises(ResultatNonInterpretable):
            self.service.detail(IDENTIFIANT)

    def test_statut_de_resultat_de_type_inattendu_signale(self) -> None:
        run = run_json()
        resultat = result_json(run["audios"][0])
        resultat["statut"] = {}
        ecrire_execution(self.donnees, run, (resultat,))

        audio = self.service.detail(IDENTIFIANT).audios[0]

        self.assertIsNone(audio.transcription)
        self.assertIn("non interprétable", audio.motif_indisponible)

    def test_lecture_ne_modifie_aucun_fichier(self) -> None:
        run, resultat = execution_complete(self.donnees)
        dossier = self.service.dossier_resultats / IDENTIFIANT
        (dossier / "run.log").write_text("journal simulé\n", encoding="utf-8")
        avant = {
            chemin: chemin.read_bytes()
            for chemin in sorted(dossier.rglob("*"))
            if chemin.is_file()
        }

        self.service.lister()
        self.service.detail(IDENTIFIANT)

        apres = {
            chemin: chemin.read_bytes()
            for chemin in sorted(dossier.rglob("*"))
            if chemin.is_file()
        }
        self.assertEqual(avant, apres)

    def test_refus_explicites_introuvable_ou_non_interpretable(self) -> None:
        with self.assertRaises(ValeurRefusee):
            self.service.detail("../secret")
        with self.assertRaises(ValeurRefusee):
            self.service.detail("C:\\secret")
        with self.assertRaises(ResultatIntrouvable):
            self.service.detail("pas-un-identifiant")
        with self.assertRaises(ResultatIntrouvable):
            self.service.detail(IDENTIFIANT)
        ecrire_execution(self.donnees, run_json(schema=2))
        with self.assertRaises(ResultatNonInterpretable):
            self.service.detail(IDENTIFIANT)


class DetailIndicateursEtAlertesTest(SocleConsultationTest):
    """Indicateurs et alertes visibles du détail individuel (tâche 3.2).

    Les fichiers sont synthétiques et écrits dans le dossier temporaire du
    socle : aucune inférence, aucun réseau, aucune écriture dans les fichiers
    lus. Les deux essais d'un même audio partagent la même empreinte.
    """

    MACHINE = {
        "os": "Linux",
        "version_os": "6.1",
        "architecture": "x86_64",
        "processeur": "Processeur fictif de test",
        "coeurs_physiques": 4,
        "coeurs_logiques": 8,
        "ram_totale_octets": 16_000_000_000,
    }

    def ecrire_essai(
        self,
        identifiant: str = IDENTIFIANT,
        *,
        machine: dict[str, Any] | None = None,
        audios: int = 1,
        mesures: dict[str, Any] | None = None,
        etat: str = ETAT_TERMINEE,
        modele: str | None = None,
        empreinte: Any = None,
    ) -> None:
        """Exécution synthétique d'un ou plusieurs audios transcrits."""
        plans = tuple(
            (f"prise{position}.wav", STATUT_OK) for position in range(1, audios + 1)
        )
        options: dict[str, Any] = {"audios": plans, "etat": etat}
        if machine is not None:
            options["machine"] = machine
        run = run_json(identifiant, **options)
        if modele is not None:
            run["demande"]["modele"]["identifiant"] = modele
        resultats = []
        for plan in run["audios"]:
            resultat = result_json(
                plan,
                execution=identifiant,
                **({} if mesures is None else {"mesures_extra": mesures}),
            )
            if empreinte is not None:
                resultat["audio"]["empreinte_sha256"] = empreinte
            resultats.append(resultat)
        ecrire_execution(self.donnees, run, tuple(resultats))

    def test_indicateurs_trois_valeurs_et_ratios_du_materiel_consigne(self) -> None:
        self.ecrire_essai(
            machine=self.MACHINE,
            mesures={
                "duree_transcription_s": 2.0,
                "temps_cpu_s": 1.6,
                "pic_memoire_octets": 2_400_000_000,
            },
        )

        audio = self.service.detail(IDENTIFIANT).audios[0]

        self.assertEqual(audio.indicateurs.duree_transcription_s, 2.0)
        self.assertEqual(audio.indicateurs.pic_memoire_octets, 2_400_000_000)
        self.assertEqual(audio.indicateurs.ram_totale_octets, 16_000_000_000)
        self.assertAlmostEqual(audio.indicateurs.part_ram, 15.0)
        # 100 × 1,6 s CPU / (2 s × 8 processeurs logiques) = 10 %.
        self.assertAlmostEqual(audio.indicateurs.occupation_cpu, 10.0)
        # Premier audio de la demande, aucun autre essai : aucune alerte.
        self.assertIsNone(audio.annotation_ram)
        self.assertIsNone(audio.materiel_alerte)

    def test_indicateurs_absents_et_materiel_non_verifie(self) -> None:
        run = run_json(IDENTIFIANT, machine=None)
        resultat = result_json(run["audios"][0])
        del resultat["mesures"]
        ecrire_execution(self.donnees, run, (resultat,))

        detail = self.service.detail(IDENTIFIANT)
        audio = detail.audios[0]

        # Aucune mesure n'est remplacée par zéro, et aucun ratio n'est inventé.
        self.assertIsNone(audio.indicateurs.duree_transcription_s)
        self.assertIsNone(audio.indicateurs.pic_memoire_octets)
        self.assertIsNone(audio.indicateurs.part_ram)
        self.assertIsNone(audio.indicateurs.occupation_cpu)
        self.assertIn("Matériel non vérifié", audio.materiel_alerte)
        self.assertEqual(
            detail.libelle_modele, "aucun modèle, textes et mesures simulés"
        )

    def test_annotation_ram_du_deuxieme_audio_seulement(self) -> None:
        self.ecrire_essai(machine=self.MACHINE, audios=2)

        premier, deuxieme = self.service.detail(IDENTIFIANT).audios

        self.assertIsNone(premier.annotation_ram)
        self.assertIn("cumulatif", deuxieme.annotation_ram)
        self.assertIn("audio précédent", deuxieme.annotation_ram)

    def test_materiel_different_entre_deux_essais_du_meme_audio(self) -> None:
        self.ecrire_essai(IDENTIFIANT, machine=self.MACHINE)
        self.ecrire_essai(
            IDENTIFIANT_ANCIEN,
            machine={**self.MACHINE, "ram_totale_octets": 32_000_000_000},
        )

        audio = self.service.detail(IDENTIFIANT).audios[0]

        self.assertIn("Matériel différent sur RAM totale", audio.materiel_alerte)
        self.assertNotIn("non vérifié", audio.materiel_alerte)

    def test_difference_connue_signalee_malgre_un_champ_inconnu(self) -> None:
        self.ecrire_essai(IDENTIFIANT, machine=self.MACHINE)
        self.ecrire_essai(
            IDENTIFIANT_ANCIEN,
            machine={
                **self.MACHINE,
                "architecture": None,
                "ram_totale_octets": 32_000_000_000,
            },
        )

        alerte = self.service.detail(IDENTIFIANT).audios[0].materiel_alerte

        # Une différence connue reste signalée même si un autre champ manque,
        # et l'inconnu du champ concerné reste mentionné.
        self.assertIn("Matériel différent sur RAM totale", alerte)
        self.assertIn("matériel non vérifié pour architecture", alerte)

    def test_difference_connue_non_masquee_par_un_autre_essai_inconnu(self) -> None:
        self.ecrire_essai(IDENTIFIANT, machine=self.MACHINE)
        self.ecrire_essai(
            IDENTIFIANT_ANCIEN,
            machine={**self.MACHINE, "ram_totale_octets": 32_000_000_000},
        )
        self.ecrire_essai(
            "20240103-000000-00000003",
            machine={**self.MACHINE, "ram_totale_octets": None},
        )

        alerte = self.service.detail(IDENTIFIANT).audios[0].materiel_alerte

        # La RAM est connue et différente chez un essai, inconnue chez l'autre :
        # la différence connue prime et reste signalée.
        self.assertIn("Matériel différent sur RAM totale", alerte)
        self.assertNotIn("non vérifié", alerte)

    def test_materiel_identique_ne_declenche_aucune_alerte(self) -> None:
        self.ecrire_essai(IDENTIFIANT, machine=self.MACHINE)
        self.ecrire_essai(IDENTIFIANT_ANCIEN, machine=dict(self.MACHINE))

        self.assertIsNone(self.service.detail(IDENTIFIANT).audios[0].materiel_alerte)

    def test_nom_du_processeur_informatif_sans_alerte(self) -> None:
        self.ecrire_essai(
            IDENTIFIANT, machine={**self.MACHINE, "processeur": None}
        )
        self.ecrire_essai(
            IDENTIFIANT_ANCIEN,
            machine={**self.MACHINE, "processeur": "Autre processeur fictif"},
        )

        detail = self.service.detail(IDENTIFIANT)

        # Le nom du processeur est facultatif : son absence seule n'alerte pas,
        # même quand un autre essai en consigne un différent.
        self.assertIsNone(detail.audios[0].materiel_alerte)
        self.assertIn(("Processeur", None), detail.machine)

    def test_champ_requis_absent_rend_le_materiel_non_verifie(self) -> None:
        self.ecrire_essai(IDENTIFIANT, machine=self.MACHINE)
        self.ecrire_essai(
            IDENTIFIANT_ANCIEN,
            machine={**self.MACHINE, "architecture": None},
        )

        self.assertIn(
            "Matériel non vérifié",
            self.service.detail(IDENTIFIANT).audios[0].materiel_alerte,
        )
        # L'essai incomplet est aussi signalé pour lui-même.
        self.assertIn(
            "Matériel non vérifié",
            self.service.detail(IDENTIFIANT_ANCIEN).audios[0].materiel_alerte,
        )

    def test_audio_different_n_est_pas_compare(self) -> None:
        self.ecrire_essai(IDENTIFIANT, machine=self.MACHINE)
        self.ecrire_essai(
            IDENTIFIANT_ANCIEN,
            machine={**self.MACHINE, "ram_totale_octets": 32_000_000_000},
            empreinte="d" * 64,
        )

        # Deux fichiers audio différents ne se comparent pas : aucune alerte.
        self.assertIsNone(self.service.detail(IDENTIFIANT).audios[0].materiel_alerte)

    def test_libelle_modele_dernier_segment(self) -> None:
        self.ecrire_essai(modele="organisation/modele-a")

        self.assertEqual(self.service.detail(IDENTIFIANT).libelle_modele, "modele-a")

    def test_marque_synthetique_seule_ne_simule_ni_moteur_ni_mesures(self) -> None:
        run = run_json(
            IDENTIFIANT,
            factice=False,
            synthetique=True,
            mesures_simulees=False,
        )
        resultat = result_json(
            run["audios"][0], factice=False, synthetique=True, mesures_simulees=False
        )
        ecrire_execution(self.donnees, run, (resultat,))

        detail = self.service.detail(IDENTIFIANT)

        self.assertIn("SYNTHÉTIQUE", detail.execution.marques)
        self.assertFalse(detail.simule_mesures)
        transcription = detail.audios[0].transcription
        self.assertIn("SYNTHÉTIQUE", transcription.marques)
        self.assertFalse(transcription.simule_mesures)

        simule = run_json(IDENTIFIANT_ANCIEN, factice=True, mesures_simulees=True)
        ecrire_execution(
            self.donnees,
            simule,
            (
                result_json(
                    simule["audios"][0],
                    execution=IDENTIFIANT_ANCIEN,
                    factice=True,
                    mesures_simulees=True,
                ),
            ),
        )
        self.assertTrue(self.service.detail(IDENTIFIANT_ANCIEN).simule_mesures)

    def test_lecture_sans_ecriture_avec_alertes(self) -> None:
        self.ecrire_essai(IDENTIFIANT, machine=self.MACHINE, audios=2)
        self.ecrire_essai(
            IDENTIFIANT_ANCIEN,
            machine={**self.MACHINE, "os": "Windows"},
        )
        racine = self.donnees / "results"
        avant = {
            chemin: chemin.read_bytes()
            for chemin in sorted(racine.rglob("*"))
            if chemin.is_file()
        }

        self.service.detail(IDENTIFIANT)

        apres = {
            chemin: chemin.read_bytes()
            for chemin in sorted(racine.rglob("*"))
            if chemin.is_file()
        }
        self.assertEqual(avant, apres)


class ConversionsTest(unittest.TestCase):
    def test_mesures_non_finies_ne_sont_jamais_des_mesures(self) -> None:
        temporaire = tempfile.TemporaryDirectory()
        self.addCleanup(temporaire.cleanup)
        donnees = Path(temporaire.name)
        run = run_json(
            mesures={
                "duree_operation_s": float("nan"),
                "duree_processus_s": float("inf"),
                "duree_chargement_s": "2.0",
                "pic_memoire_octets": True,
                "pic_memoire_partiel": "oui",
            },
            machine={"os": None, "coeurs_physiques": "4", "ram_totale_octets": None},
        )
        resultat = result_json(
            run["audios"][0],
            duree_decodee=None,
            duree_transcription=1.0,
            mesures_extra={"temps_cpu_s": float("nan")},
        )
        ecrire_execution(donnees, run, (resultat,))

        detail = ConsultationResultats(donnees).detail(IDENTIFIANT)

        self.assertIsNone(detail.mesures.duree_operation_s)
        self.assertIsNone(detail.mesures.duree_processus_s)
        self.assertIsNone(detail.mesures.duree_chargement_s)
        self.assertIsNone(detail.mesures.pic_memoire_octets)
        self.assertIsNone(detail.mesures.pic_memoire_partiel)
        # Une valeur de type inattendu est affichée telle quelle : aucune
        # conversion n'est inventée, et l'absence reste représentée par `None`.
        self.assertIn(("Cœurs physiques", "4"), detail.machine)
        self.assertIn(("RAM totale (octets)", None), detail.machine)
        transcription = detail.audios[0].transcription
        self.assertIsNone(transcription.mesures.temps_cpu_s)
        self.assertIsNone(transcription.mesures.rtf)
        self.assertIn(("Durée décodée (s)", None), transcription.audio)

    def test_etats_affiches_distincts(self) -> None:
        attendus = {
            ETAT_EN_COURS: "en cours",
            ETAT_TERMINEE: "terminée",
            ETAT_INTERROMPUE: "interrompue",
            ETAT_ABANDONNEE: "abandonnée",
            ETAT_ECHOUEE: "en échec",
        }
        temporaire = tempfile.TemporaryDirectory()
        self.addCleanup(temporaire.cleanup)
        donnees = Path(temporaire.name)
        for position, etat in enumerate(attendus):
            identifiant = f"2024010{position + 1}-000000-0000000{position}"
            ecrire_execution(donnees, run_json(identifiant, etat=etat))

        executions = ConsultationResultats(donnees).lister()

        self.assertEqual(len(executions), len(attendus))
        for execution in executions:
            with self.subTest(etat=execution.etat):
                self.assertEqual(execution.libelle_etat, attendus[execution.etat])


class IntegrationExecutionFacticeTest(SocleExecutionTest):
    """Compatibilité réelle du format : exécution factice 6.4 relue par 7.1.

    Le vrai `engines/runner.py` est exécuté avec le moteur factice sur un WAV
    synthétique ; aucune inférence réelle, aucun poids et aucun réseau. Les
    mesures du moteur sont simulées, les mesures serveur sont réelles.
    """

    def test_detail_relit_une_execution_factice_reelle(self) -> None:
        self.ecrire_audio("a.wav", 0.4)

        resultat = self.executer(self.demande(("a.wav",)))

        self.assertTerminee(resultat)
        detail = ConsultationResultats(self.dossier_data).detail(
            resultat.identifiant_resultat
        )
        self.assertFalse(detail.partiel)
        self.assertEqual(detail.execution.etat, ETAT_TERMINEE)
        self.assertEqual(detail.execution.libelle_etat, "terminée")
        self.assertEqual(detail.execution.audios_traites, 1)
        self.assertIn("FACTICE", detail.execution.marques)
        self.assertIn("SYNTHÉTIQUE", detail.execution.marques)
        self.assertIn("MESURES SIMULÉES", detail.execution.marques)
        programme = dict(detail.programme)
        self.assertTrue(programme["FFmpeg"])
        self.assertTrue(programme["PyAV"])
        audio = detail.audios[0]
        self.assertEqual(audio.statut, STATUT_OK)
        self.assertIsNone(audio.motif_indisponible)
        transcription = audio.transcription
        self.assertIsNotNone(transcription)
        self.assertTrue(transcription.texte.startswith("[FACTICE]"))
        self.assertEqual(len(transcription.segments), 1)
        self.assertEqual(len(dict(transcription.audio)["Empreinte SHA-256"]), 64)
        self.assertAlmostEqual(
            dict(transcription.audio)["Durée décodée (s)"], 0.4, places=2
        )
        # RTF recalculé : 0.5 pour le moteur factice, sans blocage au repère 2.
        self.assertAlmostEqual(transcription.mesures.rtf, 0.5, places=3)
        self.assertIn("FACTICE", transcription.marques)
        self.assertIn("MESURES SIMULÉES", transcription.marques)


if __name__ == "__main__":
    unittest.main()
