"""Tests du stockage des résultats d'une exécution (tâche 6.4).

Deux niveaux : les helpers de format (noms de dossiers, RTF, métadonnées,
création sans écrasement) puis la consignation elle-même, exercée sans lancer
aucun moteur. Aucun test n'écrit sous le `data/` du dépôt : le dossier de
données est temporaire. Les cas qui demandent un vrai moteur factice vivent dans
`tests/test_execution_moteur.py`.
"""

from __future__ import annotations

import json
import os
import platform
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from typing import Any
from unittest import mock

from engines.mesures_systeme import (
    ETATS_LECTURE,
    METHODE_CPU,
    MOTIF_INTERVALLE_TROP_COURT,
    MOTIF_LECTURE_IMPOSSIBLE,
    MOTIFS_ECRITS,
    PROVENANCE_REELLE,
    PROVENANCE_SIMULEE,
    VERSION_METHODE,
)
from transcription_bench.execution_moteur import (
    ETAT_ECHOUEE as ETAT_EXECUTION_ECHOUEE,
    ETAT_INTERROMPUE as ETAT_EXECUTION_INTERROMPUE,
    ETAT_TERMINEE as ETAT_EXECUTION_TERMINEE,
    AudioPrepare,
    ResultatAudio,
    ResultatExecution,
)
from transcription_bench.executions import DemandeExecution
from transcription_bench.paths import ValeurRefusee, resoudre_dans_racine
from transcription_bench.resultats import (
    ETAT_ECHOUEE,
    ETAT_EN_COURS,
    ETAT_INTERROMPUE,
    ETAT_TERMINEE,
    ETATS_EXECUTION_VERS_RESULTAT,
    SCHEMA,
    STATUT_ERREUR,
    STATUT_NON_TRAITE,
    STATUT_OK,
    ConsignateurExecution,
    ConsignationImpossible,
    ResultatImmuable,
    abandonner_execution,
    calculer_rtf,
    creer_dossier_resultat,
    etat_resultat,
    metadonnees_machine,
    metadonnees_moteur,
    metadonnees_programme,
    nom_dossier_audio,
)

MACHINE = {"os": "Linux", "coeurs_physiques": 4, "ram_totale_octets": 1024}
PROGRAMME = {"nom": "transcription-bench", "version": "0.1.0", "python": "3.12.0"}
MOTEUR = metadonnees_moteur("factice", "Moteur factice", factice=True)


def demande(
    audios: tuple[str, ...] = ("a.wav", "b.wav"), *, threads: int = 2
) -> DemandeExecution:
    """Demande d'exécution minimale, sans aucun effet de bord."""
    return DemandeExecution(
        moteur="factice",
        cle="0" * 64,
        identifiant="modèle de test",
        id_resolu="modèle de test",
        commit="aucun",
        famille="factice",
        fichier_gguf=None,
        audios=audios,
        threads=threads,
        reglages=(),
        fenetre_fixe_secondes=30.0,
        synthetique=True,
    )


def audio_transcrit(
    index: int = 0,
    nom: str = "a.wav",
    *,
    duree_decodee: float = 2.0,
    duree_transcription: float = 1.0,
    pic: int = 1024,
) -> ResultatAudio:
    """Audio décodé et transcrit, avec des mesures d'événement explicites."""
    prepare = AudioPrepare(
        index=index,
        nom=nom,
        fichier_brut=f"audio-{index}.f32",
        format="wav",
        taille_octets=100,
        empreinte_sha256="a" * 64,
        duree_indicative=duree_decodee,
        duree_decodee=duree_decodee,
        echantillons=int(duree_decodee * 16000),
        temps_decodage=0.25,
    )
    return ResultatAudio(
        index=index,
        nom=nom,
        prepare=prepare,
        evenement={
            "type": "audio",
            "index": index,
            "nom": nom,
            "texte": "texte simulé",
            "segments": [{"debut_s": 0.0, "fin_s": 1.0, "texte": "texte simulé"}],
            "duree_audio_s": duree_decodee,
            "duree_transcription_s": duree_transcription,
            "temps_cpu_s": 1.5,
            "rtf": duree_transcription / duree_decodee,
            "fenetre_s": 30.0,
            "decoupage": "fenetres-fixes",
            "nb_fenetres": 1,
            "pic_memoire_octets": pic,
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
            "threads_demandes": 2,
            "threads_appliques": None,
            "factice": True,
            "mesures_simulees": True,
        },
        erreur=None,
        factice=True,
        synthetique=True,
    )


def audio_en_erreur(index: int = 1, nom: str = "b.wav") -> ResultatAudio:
    """Audio dont le décodage a échoué : ni signal, ni mesure."""
    return ResultatAudio(
        index=index,
        nom=nom,
        prepare=None,
        evenement=None,
        erreur="décodage impossible : fichier illisible",
        factice=True,
        synthetique=True,
    )


def audio_non_traite(index: int = 1, nom: str = "b.wav") -> ResultatAudio:
    """Audio jamais traité (arrêt ou plantage avant son tour)."""
    return ResultatAudio(
        index=index,
        nom=nom,
        prepare=None,
        evenement=None,
        erreur=None,
        factice=True,
        synthetique=True,
    )


def memoire_apres(**remplacements: Any) -> dict[str, Any]:
    """Sous-objet `memoire_apres` du contrat D3, conforme par défaut."""
    base: dict[str, Any] = {
        "releve_le": "2026-11-07T10:00:00+00:00",
        "totale_octets": 16 * 1024**3,
        "disponible_octets": 8 * 1024**3,
        "motif": None,
    }
    base.update(remplacements)
    return base


def observation_chargement(**remplacements: Any) -> dict[str, Any]:
    """Objet d'observation système du chargement, conforme au contrat D3."""
    base: dict[str, Any] = {
        "version": VERSION_METHODE,
        "methode_cpu": METHODE_CPU,
        "version_psutil": "7.2.2",
        "provenance": PROVENANCE_SIMULEE,
        "memoire_apres": memoire_apres(),
    }
    base.update(remplacements)
    return base


def observation_audio(**remplacements: Any) -> dict[str, Any]:
    """Objet d'observation système d'un audio, conforme au contrat D3."""
    base = observation_chargement()
    base["cpu"] = {
        "pourcentage_moyen": 42.0,
        "intervalle_s": 1.0,
        "motif": None,
    }
    base.update(remplacements)
    return base


def resultat_execution(
    *,
    etat: str,
    audios: tuple[ResultatAudio, ...],
    evenements: tuple[dict[str, Any], ...] = (),
    erreur: str | None = None,
    code_sortie: int | None = 0,
) -> ResultatExecution:
    """Résultat d'exécution minimal, tel que la consignation le reçoit."""
    return ResultatExecution(
        etat=etat,
        factice=True,
        synthetique=True,
        moteur="factice",
        famille="factice",
        modele_identifiant="modèle de test",
        threads_demandes=2,
        audios=audios,
        evenements=evenements,
        lignes_parasites=0,
        journal_moteur=(),
        erreur=erreur,
        code_sortie=code_sortie,
        pid=1234,
        arret_demande=etat == ETAT_EXECUTION_INTERROMPUE,
    )


class NomDossierAudioTest(unittest.TestCase):
    """Noms de dossiers d'audios : portables, uniques et confinés."""

    def test_nom_portable_prefixe_par_l_ordre(self) -> None:
        self.assertEqual(nom_dossier_audio(1, "consultation été.wav"), "1-consultation été.wav")
        self.assertEqual(nom_dossier_audio(12, "a.wav"), "12-a.wav")

    def test_caracteres_dangereux_remplaces(self) -> None:
        nom = nom_dossier_audio(1, 'a/b\\c:d*e?f"g<h>i|j.wav')
        self.assertEqual(nom, "1-a_b_c_d_e_f_g_h_i_j.wav")
        self.assertNotRegex(nom, r'[/\\<>:"|?*]')

    def test_caracteres_de_controle_et_points_finaux_retires(self) -> None:
        nom = nom_dossier_audio(2, "audio\x00\x1f.wav. ")
        self.assertEqual(nom, "2-audio__.wav")

    def test_noms_reserves_windows_ne_sont_pas_des_peripheriques(self) -> None:
        for reserve in ("CON", "NUL", "COM1", "LPT1", "CONIN$"):
            with self.subTest(reserve=reserve):
                nom = nom_dossier_audio(1, reserve)
                self.assertEqual(nom, f"1-{reserve}")
                self.assertNotEqual(nom.split(".")[0].upper(), reserve)

    def test_nom_vide_ou_traversant_redevient_sur(self) -> None:
        self.assertEqual(nom_dossier_audio(1, ""), "1-audio")
        self.assertEqual(nom_dossier_audio(1, "..."), "1-audio")
        self.assertNotIn("/", nom_dossier_audio(1, "../../evil.wav"))
        self.assertNotIn("\\", nom_dossier_audio(1, "..\\..\\evil.wav"))

    def test_longueur_bornee(self) -> None:
        nom = nom_dossier_audio(1, "x" * 500 + ".wav")
        self.assertLessEqual(len(nom), 2 + 80)

    def test_deux_noms_reduits_au_meme_texte_restent_distincts(self) -> None:
        premier = nom_dossier_audio(1, "a|b.wav")
        second = nom_dossier_audio(2, "a*b.wav")
        self.assertEqual(premier, "1-a_b.wav")
        self.assertEqual(second, "2-a_b.wav")
        self.assertNotEqual(premier, second)

    def test_dossiers_crees_restent_confines(self) -> None:
        with tempfile.TemporaryDirectory() as temporaire:
            racine = Path(temporaire) / "resultat"
            racine.mkdir()
            for index, nom in enumerate(
                ("../evil.wav", "..\\evil.wav", "CON", "NUL.txt", "a|b.wav", "..."),
                start=1,
            ):
                with self.subTest(nom=nom):
                    dossier = resoudre_dans_racine(racine, nom_dossier_audio(index, nom))
                    dossier.mkdir()
                    self.assertTrue(dossier.is_relative_to(racine.resolve()))
                    self.assertEqual(dossier.parent, racine.resolve())

    def test_ordre_invalide_refuse(self) -> None:
        for ordre in (0, -1, True, "1", None):
            with self.subTest(ordre=ordre):
                with self.assertRaises(ValeurRefusee):
                    nom_dossier_audio(ordre, "a.wav")  # type: ignore[arg-type]


class CreerDossierResultatTest(unittest.TestCase):
    """Chaque exécution reçoit un dossier neuf, jamais un dossier existant."""

    def setUp(self) -> None:
        temporaire = tempfile.TemporaryDirectory()
        self.addCleanup(temporaire.cleanup)
        # Chemin résolu : le produit résout les siens ; sous Windows, le
        # dossier temporaire peut être rendu en chemin court (8.3).
        self.donnees = Path(temporaire.name).resolve() / "data"

    def test_identifiant_horodate_et_dossier_cree(self) -> None:
        identifiant, chemin = creer_dossier_resultat(self.donnees)
        self.assertRegex(identifiant, r"^\d{8}-\d{6}-[0-9a-f]{8}$")
        self.assertEqual(chemin.name, identifiant)
        self.assertEqual(chemin.parent, self.donnees / "results")
        self.assertTrue(chemin.is_dir())

    def test_deux_creations_ne_partagent_jamais_un_dossier(self) -> None:
        premier, chemin_premier = creer_dossier_resultat(
            self.donnees, base="20260101-120000"
        )
        (chemin_premier / "run.json").write_text("{}", encoding="utf-8")
        second, chemin_second = creer_dossier_resultat(
            self.donnees, base="20260101-120000"
        )

        self.assertNotEqual(premier, second)
        self.assertNotEqual(chemin_premier, chemin_second)
        self.assertEqual(
            (chemin_premier / "run.json").read_text(encoding="utf-8"), "{}"
        )

    def test_identifiant_deja_pris_remplace_par_un_autre_tirage(self) -> None:
        base = "20260101-120000"
        occupe, _ = creer_dossier_resultat(self.donnees, base=base, court_id="deadbeef")

        libre, chemin = creer_dossier_resultat(
            self.donnees, base=base, court_id="deadbeef"
        )

        self.assertEqual(occupe, f"{base}-deadbeef")
        self.assertNotEqual(libre, occupe)
        self.assertRegex(libre, r"^20260101-120000-[0-9a-f]{8}$")
        self.assertTrue(chemin.is_dir())

    def test_formes_invalides_refusees(self) -> None:
        with self.assertRaises(ValeurRefusee):
            creer_dossier_resultat(self.donnees, base="2026-01-01")
        with self.assertRaises(ValeurRefusee):
            creer_dossier_resultat(self.donnees, court_id="../evil")

    def test_stockage_indisponible_signale(self) -> None:
        racine = self.donnees / "results"
        racine.parent.mkdir(parents=True, exist_ok=True)
        racine.write_text("pas un dossier", encoding="utf-8")

        with self.assertRaises(ConsignationImpossible) as capture:
            creer_dossier_resultat(self.donnees)

        self.assertIn("results", str(capture.exception))


class CalculerRtfTest(unittest.TestCase):
    """Le RTF se calcule sur la durée décodée, jamais sur l'indicative."""

    def test_rtf_sur_duree_decodee(self) -> None:
        self.assertAlmostEqual(calculer_rtf(1.0, 2.0), 0.5)
        self.assertAlmostEqual(calculer_rtf(3.0, 1.0), 3.0)

    def test_duree_decodee_nulle_ou_absente_donne_mesure_absente(self) -> None:
        self.assertIsNone(calculer_rtf(1.0, 0.0))
        self.assertIsNone(calculer_rtf(1.0, 0))
        self.assertIsNone(calculer_rtf(None, 1.0))
        self.assertIsNone(calculer_rtf(1.0, None))
        self.assertIsNone(calculer_rtf("1", 1.0))
        self.assertIsNone(calculer_rtf(True, 1.0))
        self.assertIsNone(calculer_rtf(-1.0, 1.0))


class MetadonneesTest(unittest.TestCase):
    """Métadonnées machine et programme : complètes, sans invention."""

    def test_machine(self) -> None:
        machine = metadonnees_machine()
        self.assertEqual(
            set(machine),
            {
                "os",
                "version_os",
                "architecture",
                "processeur",
                "coeurs_physiques",
                "coeurs_logiques",
                "ram_totale_octets",
            },
        )
        self.assertTrue(isinstance(machine["os"], str))

    def test_programme(self) -> None:
        programme = metadonnees_programme()
        self.assertEqual(programme["nom"], "transcription-bench")
        self.assertEqual(programme["python"], platform.python_version())
        self.assertRegex(programme["empreinte_verrou"], r"^[0-9a-f]{64}$")
        self.assertIsNotNone(programme["pyav"])
        self.assertIn("bibliotheques", programme["ffmpeg"])
        # Aucun commit n'est inventé : le champ n'est pas écrit du tout.
        self.assertNotIn("commit", programme)

    def test_moteur(self) -> None:
        moteur = metadonnees_moteur(
            "faster-whisper", "faster-whisper", factice=False, versions={"ctranslate2": "4.8.3"}
        )
        self.assertEqual(moteur["identifiant"], "faster-whisper")
        self.assertFalse(moteur["factice"])
        self.assertEqual(moteur["versions"], {"ctranslate2": "4.8.3"})
        self.assertIsNone(moteur["empreinte_verrou"])


class EtatResultatTest(unittest.TestCase):
    """Les états persistés sont ceux attendus par la récupération (6.5)."""

    def test_correspondance_avec_les_etats_du_service(self) -> None:
        self.assertEqual(
            ETATS_EXECUTION_VERS_RESULTAT,
            {
                ETAT_EXECUTION_TERMINEE: ETAT_TERMINEE,
                ETAT_EXECUTION_INTERROMPUE: ETAT_INTERROMPUE,
                ETAT_EXECUTION_ECHOUEE: ETAT_ECHOUEE,
            },
        )
        self.assertEqual(etat_resultat(ETAT_EXECUTION_TERMINEE), "completed")
        with self.assertRaises(ValueError):
            etat_resultat("abandonnee")


class ConsignateurExecutionTest(unittest.TestCase):
    """Consignation d'une exécution : format, atomicité, immuabilité."""

    def setUp(self) -> None:
        temporaire = tempfile.TemporaryDirectory()
        self.addCleanup(temporaire.cleanup)
        self.donnees = Path(temporaire.name) / "data"
        self.consignateur = self.creer_consignateur()
        self.addCleanup(self.consignateur.fermer)

    def creer_consignateur(self, **options: Any) -> ConsignateurExecution:
        options.setdefault("machine", MACHINE)
        options.setdefault("programme", PROGRAMME)
        return ConsignateurExecution(
            self.donnees, demande(), MOTEUR, debut=0.0, **options
        )

    def ouvrir(self) -> ConsignateurExecution:
        self.assertTrue(self.consignateur.ouvrir(), self.consignateur.erreur)
        return self.consignateur

    def lire(self, nom: str, *parties: str) -> Any:
        chemin = Path(self.consignateur.dossier or "")
        for partie in parties:
            chemin = chemin / partie
        return json.loads((chemin / nom).read_text(encoding="utf-8"))

    def test_ouverture_cree_run_json_running_et_run_log(self) -> None:
        consignateur = self.ouvrir()
        dossier = consignateur.dossier

        self.assertIsNotNone(dossier)
        self.assertTrue((dossier / "run.json").is_file())
        run = self.lire("run.json")
        self.assertEqual(run["schema"], SCHEMA)
        self.assertEqual(run["identifiant"], dossier.name)
        self.assertEqual(run["etat"], ETAT_EN_COURS)
        self.assertIsNone(run["fin"])
        self.assertIsNone(run["erreur"])
        self.assertTrue(run["factice"])
        self.assertTrue(run["synthetique"])
        self.assertTrue(run["mesures_simulees"])
        self.assertEqual(run["demande"]["audios"], ["a.wav", "b.wav"])
        self.assertEqual(run["demande"]["threads_demandes"], 2)
        self.assertEqual(run["demande"]["reglages"], {})
        self.assertEqual(run["demande"]["fenetre_fixe_secondes"], 30.0)
        self.assertEqual(
            run["effectifs"],
            {
                "threads_demandes": 2,
                "threads_appliques": None,
                "reglages_effectifs": None,
            },
        )
        self.assertEqual(run["machine"], MACHINE)
        self.assertEqual(run["programme"], PROGRAMME)
        self.assertEqual(run["progression"], {"audios_traites": 0, "audios_total": 2})
        self.assertEqual(
            [(plan["ordre"], plan["nom"], plan["statut"]) for plan in run["audios"]],
            [(1, "a.wav", STATUT_NON_TRAITE), (2, "b.wav", STATUT_NON_TRAITE)],
        )
        self.assertEqual(
            [plan["dossier"] for plan in run["audios"]], ["1-a.wav", "2-b.wav"]
        )
        # Mesures indisponibles : absentes, jamais zéro.
        for valeur in run["mesures"].values():
            self.assertIsNone(valeur)
        self.assertIsNone(run["processus_moteur"]["pid"])
        self.assertTrue((dossier / "run.log").is_file())
        self.assertEqual((dossier / "run.log").read_text(encoding="utf-8"), "")

    def test_resultat_d_audio_ecrit_avec_transcription_et_mesures(self) -> None:
        consignateur = self.ouvrir()

        self.assertTrue(consignateur.enregistrer_audio(audio_transcrit()))

        resultat = self.lire("result.json", "1-a.wav")
        self.assertEqual(resultat["schema"], SCHEMA)
        self.assertEqual(resultat["execution"], consignateur.identifiant)
        self.assertEqual(resultat["ordre"], 1)
        self.assertEqual(resultat["statut"], STATUT_OK)
        # Le modèle d'un résultat porte aussi la famille, sans relire run.json.
        self.assertEqual(resultat["modele"]["famille"], "factice")
        self.assertEqual(resultat["modele"]["identifiant"], "modèle de test")
        self.assertEqual(resultat["audio"]["empreinte_sha256"], "a" * 64)
        self.assertEqual(resultat["audio"]["duree_decodee_s"], 2.0)
        self.assertEqual(resultat["audio"]["duree_indicative_s"], 2.0)
        self.assertEqual(resultat["mesures"]["temps_decodage_s"], 0.25)
        self.assertAlmostEqual(resultat["mesures"]["rtf"], 0.5)
        self.assertEqual(resultat["threads"], {"demandes": 2, "appliques": None})
        self.assertEqual(resultat["fenetre"]["duree_s"], 30.0)
        self.assertEqual(resultat["fenetre"]["decoupage"], "fenetres-fixes")
        self.assertEqual(resultat["reglages_effectifs"], {"langue": "fr"})
        # Timings natifs recopiés par appel, sans agrégation.
        self.assertEqual(
            resultat["timings_natifs"],
            [
                {
                    "unite": "ms",
                    "load_ms": 12.5,
                    "mel_ms": 3.25,
                    "encode_ms": 40.0,
                    "decode_ms": 60.5,
                }
            ],
        )
        self.assertEqual(resultat["transcription"]["texte"], "texte simulé")
        self.assertTrue(resultat["mesures_simulees"])
        self.assertEqual(
            (consignateur.dossier / "1-a.wav" / "transcription.txt").read_text(
                encoding="utf-8"
            ),
            "texte simulé\n",
        )
        run = self.lire("run.json")
        self.assertEqual(run["etat"], ETAT_EN_COURS)
        self.assertEqual(run["progression"], {"audios_traites": 1, "audios_total": 2})
        self.assertEqual(run["audios"][0]["statut"], STATUT_OK)
        self.assertEqual(run["audios"][0]["decoupage"], "fenetres-fixes")
        self.assertEqual(run["audios"][1]["statut"], STATUT_NON_TRAITE)
        # Réglages effectifs relus du moteur : le thread appliqué reste absent
        # (le moteur ne le rapporte pas), la valeur demandée n'est pas recopiée.
        self.assertEqual(run["effectifs"]["reglages_effectifs"], {"langue": "fr"})
        self.assertIsNone(run["effectifs"]["threads_appliques"])

    def test_audio_en_erreur_sans_transcription(self) -> None:
        consignateur = self.ouvrir()

        self.assertTrue(consignateur.enregistrer_audio(audio_en_erreur()))

        resultat = self.lire("result.json", "2-b.wav")
        self.assertEqual(resultat["statut"], STATUT_ERREUR)
        self.assertIn("décodage impossible", resultat["erreur"])
        self.assertIsNone(resultat["transcription"])
        self.assertIsNone(resultat["fenetre"])
        self.assertIsNone(resultat["timings_natifs"])
        self.assertIsNone(resultat["audio"]["empreinte_sha256"])
        for valeur in resultat["mesures"].values():
            self.assertIsNone(valeur)
        self.assertFalse((consignateur.dossier / "2-b.wav" / "transcription.txt").exists())
        run = self.lire("run.json")
        self.assertEqual(run["audios"][1]["statut"], STATUT_ERREUR)
        self.assertIn("décodage impossible", run["audios"][1]["erreur"])

    def test_audio_non_traite_n_invente_aucune_mesure(self) -> None:
        consignateur = self.ouvrir()

        self.assertTrue(consignateur.enregistrer_audio(audio_non_traite()))

        resultat = self.lire("result.json", "2-b.wav")
        self.assertEqual(resultat["statut"], STATUT_NON_TRAITE)
        self.assertIsNone(resultat["erreur"])
        self.assertIsNone(resultat["mesures"]["rtf"])
        self.assertIsNone(resultat["mesures"]["temps_decodage_s"])
        self.assertFalse((consignateur.dossier / "2-b.wav" / "transcription.txt").exists())

    def test_processus_consigne_des_son_lancement(self) -> None:
        consignateur = self.ouvrir()

        self.assertTrue(
            consignateur.enregistrer_processus(
                pid=4321,
                heure_creation=1767261600.123456,
                source="psutil",
                lance_a="2026-01-01T10:00:01+01:00",
            )
        )

        processus = self.lire("run.json")["processus_moteur"]
        self.assertEqual(processus["pid"], 4321)
        # L'horodatage système est conservé brut : aucune troncature à la seconde.
        self.assertEqual(processus["heure_creation"], 1767261600.123456)
        self.assertEqual(processus["heure_creation_source"], "psutil")
        self.assertEqual(processus["lance_a"], "2026-01-01T10:00:01+01:00")
        self.assertIsNone(processus["code_sortie"])

    def test_mesures_du_chargement_consignees_des_reception(self) -> None:
        consignateur = self.ouvrir()

        self.assertTrue(
            consignateur.enregistrer_mesures(
                {"type": "chargement", "duree_s": 1.2, "pic_memoire_octets": 1024}
            )
        )

        run = self.lire("run.json")
        self.assertEqual(run["etat"], ETAT_EN_COURS)
        self.assertEqual(run["mesures"]["duree_chargement_s"], 1.2)
        self.assertEqual(run["mesures"]["pic_memoire_octets"], 1024)
        self.assertIs(run["mesures"]["pic_memoire_partiel"], True)
        self.assertIsNone(run["mesures"]["duree_operation_s"])
        self.assertIsNone(run["mesures"]["duree_processus_s"])

    def test_mesures_d_audio_persistees_avec_le_resultat(self) -> None:
        consignateur = self.ouvrir()
        audio = audio_transcrit(pic=4096)

        self.assertTrue(consignateur.enregistrer_mesures(audio.evenement))
        # Aucune écriture séparée pour un audio : c'est `enregistrer_audio`
        # qui réécrit `run.json`, juste après, avec le pic à jour.
        self.assertIsNone(self.lire("run.json")["mesures"]["pic_memoire_octets"])

        self.assertTrue(consignateur.enregistrer_audio(audio))

        run = self.lire("run.json")
        self.assertEqual(run["mesures"]["pic_memoire_octets"], 4096)
        self.assertIs(run["mesures"]["pic_memoire_partiel"], True)
        self.assertIsNone(run["mesures"]["duree_chargement_s"])
        self.assertEqual(run["progression"], {"audios_traites": 1, "audios_total": 2})

    # -- observations système (tâche 2.1, design D3) -------------------------

    def _lire_audio(self, consignateur: ConsignateurExecution, dossier: str) -> Any:
        return json.loads(
            (Path(consignateur.dossier or "") / dossier / "result.json").read_text(
                encoding="utf-8"
            )
        )

    def _consigner_chargement(
        self, observation: Any, *, mesures_simulees: bool = True
    ) -> dict[str, Any]:
        """Consigne un événement de chargement portant une observation système."""
        consignateur = self.ouvrir()
        evenement: dict[str, Any] = {
            "type": "chargement",
            "duree_s": 1.2,
            "pic_memoire_octets": 1024,
            "factice": mesures_simulees,
            "mesures_simulees": mesures_simulees,
        }
        if observation is not None:
            evenement["observation_systeme"] = observation
        self.assertTrue(consignateur.enregistrer_mesures(evenement))
        return self.lire("run.json")

    def _consigner_audio(
        self, observation: Any, *, mesures_simulees: bool = True
    ) -> tuple[ConsignateurExecution, Any]:
        """Consigne l'audio `a.wav` avec, ou sans, observation système."""
        consignateur = self.ouvrir()
        audio = audio_transcrit()
        evenement = dict(audio.evenement or {})
        evenement["factice"] = mesures_simulees
        evenement["mesures_simulees"] = mesures_simulees
        if observation is not None:
            evenement["observation_systeme"] = observation
        audio = replace(audio, evenement=evenement, factice=mesures_simulees)
        self.assertTrue(consignateur.enregistrer_mesures(evenement))
        self.assertTrue(consignateur.enregistrer_audio(audio))
        return consignateur, self._lire_audio(consignateur, "1-a.wav")

    def test_observation_systeme_du_chargement_persistee(self) -> None:
        objet = observation_chargement()

        run = self._consigner_chargement(objet)

        self.assertEqual(run["mesures"]["observation_systeme_chargement"], objet)
        # Version, méthode, unités et provenance restent explicites.
        observation = run["mesures"]["observation_systeme_chargement"]
        self.assertEqual(observation["version"], VERSION_METHODE)
        self.assertEqual(observation["methode_cpu"], METHODE_CPU)
        self.assertEqual(observation["provenance"], PROVENANCE_SIMULEE)
        self.assertEqual(observation["memoire_apres"]["totale_octets"], 16 * 1024**3)
        self.assertEqual(
            observation["memoire_apres"]["disponible_octets"], 8 * 1024**3
        )
        self.assertNotIn("cpu", observation)
        # Aucune compatibilité rompue : schéma global et machine inchangés.
        self.assertEqual(run["schema"], SCHEMA)
        self.assertEqual(run["machine"], MACHINE)
        self.assertEqual(
            set(run["mesures"]),
            {
                "duree_operation_s",
                "duree_processus_s",
                "duree_chargement_s",
                "pic_memoire_octets",
                "pic_memoire_partiel",
                "observation_systeme_chargement",
            },
        )
        # Le relevé du chargement est persisté dès sa réception, sans résultat
        # d'audio inventé pour autant.
        dossier = Path(self.consignateur.dossier or "")
        self.assertEqual(
            sorted(chemin.name for chemin in dossier.iterdir()),
            ["run.json", "run.log"],
        )

    def test_observation_systeme_d_un_audio_persistee_avec_lui(self) -> None:
        objet = observation_audio()

        consignateur, resultat = self._consigner_audio(objet)

        self.assertEqual(resultat["mesures"]["observation_systeme"], objet)
        observation = resultat["mesures"]["observation_systeme"]
        self.assertEqual(observation["version"], VERSION_METHODE)
        self.assertEqual(observation["provenance"], PROVENANCE_SIMULEE)
        self.assertEqual(observation["cpu"]["pourcentage_moyen"], 42.0)
        self.assertEqual(observation["cpu"]["intervalle_s"], 1.0)
        self.assertIsNone(observation["cpu"]["motif"])
        self.assertEqual(
            observation["memoire_apres"]["disponible_octets"], 8 * 1024**3
        )
        # L'addition ne touche ni les anciennes mesures ni le schéma.
        self.assertEqual(resultat["mesures"]["temps_decodage_s"], 0.25)
        self.assertAlmostEqual(resultat["mesures"]["rtf"], 0.5)
        self.assertEqual(resultat["transcription"]["texte"], "texte simulé")
        self.assertEqual(resultat["statut"], STATUT_OK)
        self.assertEqual(resultat["schema"], SCHEMA)
        self.assertEqual(resultat["machine"], MACHINE)
        run = self.lire("run.json")
        self.assertEqual(run["schema"], SCHEMA)
        self.assertEqual(run["machine"], MACHINE)
        # Le relevé du chargement n'est pas inventé à partir de celui de l'audio.
        self.assertIsNone(run["mesures"]["observation_systeme_chargement"])
        self.assertEqual(
            (consignateur.dossier / "1-a.wav" / "transcription.txt").read_text(
                encoding="utf-8"
            ),
            "texte simulé\n",
        )

    def test_chargement_simule_sur_un_resultat_reel_ignore(self) -> None:
        """La provenance doit aussi concorder avec `mesures_simulees` du run."""
        consignateur = ConsignateurExecution(
            self.donnees,
            demande(),
            metadonnees_moteur("reel", "Moteur réel", factice=False),
            debut=0.0,
            machine=MACHINE,
            programme=PROGRAMME,
        )
        self.addCleanup(consignateur.fermer)
        self.assertTrue(consignateur.ouvrir(), consignateur.erreur)

        self.assertTrue(
            consignateur.enregistrer_mesures(
                {
                    "type": "chargement",
                    "duree_s": 1.2,
                    "pic_memoire_octets": 1024,
                    "factice": True,
                    "mesures_simulees": True,
                    "observation_systeme": observation_chargement(),
                }
            )
        )

        dossier = Path(consignateur.dossier or "")
        run = json.loads((dossier / "run.json").read_text(encoding="utf-8"))
        self.assertIsNone(run["mesures"]["observation_systeme_chargement"])
        self.assertFalse(run["mesures_simulees"])
        # La mesure du chargement, elle, reste consignée.
        self.assertEqual(run["mesures"]["duree_chargement_s"], 1.2)
        self.assertIn(
            "provenance contradictoire",
            (dossier / "run.log").read_text(encoding="utf-8"),
        )

    def test_observation_systeme_absente_reste_explicitement_indisponible(
        self,
    ) -> None:
        consignateur = self.ouvrir()
        self.assertTrue(
            consignateur.enregistrer_mesures(
                {
                    "type": "chargement",
                    "duree_s": 1.2,
                    "pic_memoire_octets": 1024,
                    "factice": True,
                    "mesures_simulees": True,
                }
            )
        )
        audio = audio_transcrit()
        self.assertTrue(consignateur.enregistrer_mesures(audio.evenement))
        self.assertTrue(consignateur.enregistrer_audio(audio))
        run = self.lire("run.json")
        resultat = self._lire_audio(consignateur, "1-a.wav")

        self.assertIsNone(run["mesures"]["observation_systeme_chargement"])
        self.assertIsNone(resultat["mesures"]["observation_systeme"])
        self.assertEqual(resultat["statut"], STATUT_OK)
        self.assertEqual(resultat["transcription"]["texte"], "texte simulé")
        self.assertEqual(
            (Path(consignateur.dossier or "") / "run.log").read_text(
                encoding="utf-8"
            ),
            "",
        )

    def test_observation_invalide_ignoree_sans_persistance_ni_perte(self) -> None:
        """Seul l'objet système est écarté : transcription et mesures intactes."""
        cas: dict[str, Any] = {
            "version inconnue": observation_audio(version=2),
            "pourcentage hors contrat": observation_audio(
                cpu={
                    "pourcentage_moyen": 101.0,
                    "intervalle_s": 1.0,
                    "motif": None,
                }
            ),
            "mémoire disponible supérieure": observation_audio(
                memoire_apres=memoire_apres(disponible_octets=20 * 1024**3)
            ),
            "provenance inconnue": observation_audio(provenance="estimee"),
            "état de lecture comme motif": observation_audio(
                cpu={
                    "pourcentage_moyen": None,
                    "intervalle_s": 0.05,
                    "motif": "invalide",
                }
            ),
            "structure non conforme": "relevé système",
        }
        for etiquette, observation in cas.items():
            with self.subTest(cas=etiquette):
                consignateur = self.creer_consignateur()
                self.addCleanup(consignateur.fermer)
                self.assertTrue(consignateur.ouvrir(), consignateur.erreur)
                audio = audio_transcrit()
                evenement = dict(audio.evenement or {})
                evenement["observation_systeme"] = observation
                audio = replace(audio, evenement=evenement)
                self.assertTrue(consignateur.enregistrer_mesures(evenement))
                self.assertTrue(consignateur.enregistrer_audio(audio))
                resultat = self._lire_audio(consignateur, "1-a.wav")

                self.assertIsNone(resultat["mesures"]["observation_systeme"])
                self.assertEqual(resultat["statut"], STATUT_OK)
                self.assertEqual(resultat["transcription"]["texte"], "texte simulé")
                self.assertAlmostEqual(resultat["mesures"]["rtf"], 0.5)
                self.assertEqual(
                    (
                        consignateur.dossier / "1-a.wav" / "transcription.txt"
                    ).read_text(encoding="utf-8"),
                    "texte simulé\n",
                )
                # Signalé au journal seulement, jamais persisté.
                journal = (consignateur.dossier / "run.log").read_text(
                    encoding="utf-8"
                )
                self.assertIn("Relevé système ignoré", journal)
                contenu = (
                    consignateur.dossier / "1-a.wav" / "result.json"
                ).read_text(encoding="utf-8")
                for etat in ETATS_LECTURE:
                    self.assertNotIn(f'"{etat}"', contenu)

    def test_provenance_contradictoire_ignoree_sans_persistance(self) -> None:
        # Objet simulé sur un événement réel : contradiction objet/événement.
        consignateur = self.creer_consignateur()
        self.addCleanup(consignateur.fermer)
        self.assertTrue(consignateur.ouvrir(), consignateur.erreur)
        audio = audio_transcrit()
        evenement = dict(audio.evenement or {})
        evenement["factice"] = False
        evenement["mesures_simulees"] = False
        evenement["observation_systeme"] = observation_audio(
            provenance=PROVENANCE_SIMULEE
        )
        audio = replace(audio, evenement=evenement, factice=False)
        self.assertTrue(consignateur.enregistrer_mesures(evenement))
        self.assertTrue(consignateur.enregistrer_audio(audio))

        resultat = self._lire_audio(consignateur, "1-a.wav")
        self.assertIsNone(resultat["mesures"]["observation_systeme"])
        self.assertEqual(resultat["statut"], STATUT_OK)
        self.assertEqual(resultat["transcription"]["texte"], "texte simulé")
        self.assertIn(
            "Relevé système ignoré",
            (consignateur.dossier / "run.log").read_text(encoding="utf-8"),
        )

    def test_provenance_contradictoire_avec_le_resultat_ignoree(self) -> None:
        """Un résultat réel et un événement simulé ne se réconcilient pas."""
        consignateur = self.ouvrir()
        audio = audio_transcrit()
        evenement = dict(audio.evenement or {})
        evenement["observation_systeme"] = observation_audio()
        # L'événement reste marqué simulé alors que le résultat est réel.
        audio = replace(audio, evenement=evenement, factice=False)

        self.assertTrue(consignateur.enregistrer_mesures(evenement))
        self.assertTrue(consignateur.enregistrer_audio(audio))

        resultat = self._lire_audio(consignateur, "1-a.wav")
        self.assertIsNone(resultat["mesures"]["observation_systeme"])
        self.assertFalse(resultat["mesures_simulees"])
        self.assertEqual(resultat["transcription"]["texte"], "texte simulé")
        self.assertIn(
            "provenance contradictoire",
            (consignateur.dossier / "run.log").read_text(encoding="utf-8"),
        )

    def test_codes_stockes_distincts_des_etats_de_lecture(self) -> None:
        objet = observation_audio(
            cpu={
                "pourcentage_moyen": None,
                "intervalle_s": 0.05,
                "motif": MOTIF_INTERVALLE_TROP_COURT,
            },
            memoire_apres=memoire_apres(
                disponible_octets=None, motif=MOTIF_LECTURE_IMPOSSIBLE
            ),
        )

        consignateur, resultat = self._consigner_audio(objet)

        observation = resultat["mesures"]["observation_systeme"]
        # La fenêtre réellement observée reste consignée à côté du motif.
        self.assertEqual(observation["cpu"]["motif"], MOTIF_INTERVALLE_TROP_COURT)
        self.assertEqual(observation["cpu"]["intervalle_s"], 0.05)
        self.assertIsNone(observation["cpu"]["pourcentage_moyen"])
        self.assertEqual(
            observation["memoire_apres"]["motif"], MOTIF_LECTURE_IMPOSSIBLE
        )
        for motif in (
            observation["cpu"]["motif"],
            observation["memoire_apres"]["motif"],
        ):
            self.assertIn(motif, MOTIFS_ECRITS)
        contenu = (
            consignateur.dossier / "1-a.wav" / "result.json"
        ).read_text(encoding="utf-8")
        for etat in ETATS_LECTURE:
            self.assertNotIn(f'"{etat}"', contenu)

    def test_abandon_n_ajoute_aucune_observation_aux_anciens_fichiers(self) -> None:
        """Aucun remplissage rétroactif : un ancien `run.json` reste sans clé."""
        consignateur = self.ouvrir()
        contenu = self.lire("run.json")
        del contenu["mesures"]["observation_systeme_chargement"]
        run_json = Path(consignateur.dossier or "") / "run.json"
        run_json.write_text(json.dumps(contenu), encoding="utf-8")

        final = abandonner_execution(consignateur.dossier, contenu)

        self.assertNotIn("observation_systeme_chargement", final["mesures"])
        self.assertEqual(final["schema"], SCHEMA)
        self.assertEqual(final["machine"], MACHINE)
        relu = json.loads(run_json.read_text(encoding="utf-8"))
        self.assertNotIn("observation_systeme_chargement", relu["mesures"])

    def test_ancien_resultat_d_audio_jamais_reecrit(self) -> None:
        consignateur = self.ouvrir()
        ancien = Path(consignateur.dossier or "") / "1-a.wav"
        ancien.mkdir()
        resultat_ancien = {
            "schema": SCHEMA,
            "statut": STATUT_OK,
            "mesures": {"rtf": 0.5, "duree_transcription_s": 1.0},
        }
        chemin = ancien / "result.json"
        chemin.write_text(json.dumps(resultat_ancien), encoding="utf-8")
        avant = chemin.read_bytes()

        audio = audio_transcrit(index=1, nom="b.wav")
        self.assertTrue(consignateur.enregistrer_audio(audio))
        self.assertTrue(
            consignateur.clore(
                resultat_execution(etat=ETAT_EXECUTION_TERMINEE, audios=(audio,))
            )
        )

        self.assertEqual(chemin.read_bytes(), avant)
        self.assertNotIn("observation_systeme", json.loads(avant)["mesures"])

    def test_mesures_non_finies_ou_invalides_jamais_retenues(self) -> None:
        consignateur = self.ouvrir()

        consignateur.enregistrer_mesures(
            {"type": "chargement", "duree_s": float("nan"), "pic_memoire_octets": True}
        )
        run = self.lire("run.json")
        self.assertIsNone(run["mesures"]["duree_chargement_s"])
        self.assertIsNone(run["mesures"]["pic_memoire_octets"])
        self.assertIsNone(run["mesures"]["pic_memoire_partiel"])

        consignateur.enregistrer_mesures(
            {"type": "chargement", "duree_s": 1.2, "pic_memoire_octets": 1.5}
        )
        consignateur.enregistrer_mesures(
            {"type": "audio", "index": 0, "pic_memoire_octets": float("inf")}
        )
        run = self.lire("run.json")
        self.assertEqual(run["mesures"]["duree_chargement_s"], 1.2)
        self.assertIsNone(run["mesures"]["pic_memoire_octets"])
        self.assertIsNone(run["mesures"]["pic_memoire_partiel"])

        consignateur.enregistrer_mesures(
            {"type": "audio", "index": 0, "pic_memoire_octets": 4096}
        )
        self.assertTrue(consignateur.enregistrer_audio(audio_transcrit(pic=4096)))
        run = self.lire("run.json")
        self.assertEqual(run["mesures"]["pic_memoire_octets"], 4096)
        self.assertIs(run["mesures"]["pic_memoire_partiel"], True)

    def test_duree_de_chargement_retenue_une_seule_fois(self) -> None:
        consignateur = self.ouvrir()

        consignateur.enregistrer_mesures({"type": "chargement", "duree_s": 1.2})
        consignateur.enregistrer_mesures({"type": "chargement", "duree_s": 9.9})

        self.assertEqual(
            self.lire("run.json")["mesures"]["duree_chargement_s"], 1.2
        )

    def test_mesures_ne_sont_plus_ecrites_apres_cloture(self) -> None:
        consignateur = self.ouvrir()
        resultat = resultat_execution(
            etat=ETAT_EXECUTION_TERMINEE,
            audios=(audio_non_traite(index=0, nom="a.wav"), audio_non_traite()),
        )
        self.assertTrue(consignateur.clore(resultat))
        chemin = Path(consignateur.dossier) / "run.json"
        avant = chemin.read_bytes()

        with self.assertRaises(ResultatImmuable):
            consignateur.enregistrer_mesures(
                {"type": "chargement", "duree_s": 1.2, "pic_memoire_octets": 1024}
            )

        self.assertEqual(chemin.read_bytes(), avant)

    def test_echec_d_ecriture_des_mesures_du_chargement_est_retenu(self) -> None:
        consignateur = self.ouvrir()
        chemin = Path(consignateur.dossier) / "run.json"
        avant = chemin.read_text(encoding="utf-8")

        def remplacer(origine: Any, cible: Any) -> None:
            raise OSError(28, "espace insuffisant sur le périphérique")

        with mock.patch("transcription_bench.stockage.os.replace", remplacer):
            self.assertFalse(
                consignateur.enregistrer_mesures(
                    {"type": "chargement", "duree_s": 1.2, "pic_memoire_octets": 1024}
                )
            )

        # L'erreur est retenue, jamais avalée ; aucune mesure n'est publiée et
        # l'état précédent reste lisible, sans troncature.
        self.assertIsNotNone(consignateur.erreur)
        self.assertIn("impossible", consignateur.erreur or "")
        run = self.lire("run.json")
        self.assertIsNone(run["mesures"]["duree_chargement_s"])
        self.assertIsNone(run["mesures"]["pic_memoire_octets"])
        self.assertEqual(chemin.read_text(encoding="utf-8"), avant)

    def test_cloture_ecrit_etat_final_et_rend_immuable(self) -> None:
        consignateur = self.ouvrir()
        consignateur.enregistrer_audio(audio_transcrit())
        resultat = resultat_execution(
            etat=ETAT_EXECUTION_TERMINEE,
            audios=(audio_transcrit(), audio_non_traite()),
            evenements=(
                {"type": "chargement", "duree_s": 1.2, "pic_memoire_octets": 1024},
                {"type": "fin", "pic_memoire_octets": 2048},
            ),
        )
        consignateur.mesures.duree_operation_s = 3.5
        consignateur.mesures.duree_processus_s = 2.0

        self.assertTrue(consignateur.clore(resultat))

        run = self.lire("run.json")
        self.assertEqual(run["etat"], ETAT_TERMINEE)
        self.assertIsNotNone(run["fin"])
        self.assertEqual(run["progression"], {"audios_traites": 1, "audios_total": 2})
        self.assertEqual(
            [plan["statut"] for plan in run["audios"]], [STATUT_OK, STATUT_NON_TRAITE]
        )
        self.assertEqual(run["processus_moteur"]["code_sortie"], 0)
        self.assertEqual(run["mesures"]["duree_operation_s"], 3.5)
        self.assertEqual(run["mesures"]["duree_processus_s"], 2.0)
        self.assertEqual(run["mesures"]["duree_chargement_s"], 1.2)
        self.assertEqual(run["mesures"]["pic_memoire_octets"], 2048)
        self.assertFalse(run["mesures"]["pic_memoire_partiel"])
        avant = (consignateur.dossier / "run.json").read_bytes()
        self.assertEqual(consignateur.etat_final, ETAT_TERMINEE)

        with self.assertRaises(ResultatImmuable):
            consignateur.enregistrer_audio(audio_non_traite())
        with self.assertRaises(ResultatImmuable):
            consignateur.enregistrer_processus(
                pid=1, heure_creation=1.0, source="serveur", lance_a="y"
            )
        with self.assertRaises(ResultatImmuable):
            consignateur.clore(resultat)
        self.assertEqual((consignateur.dossier / "run.json").read_bytes(), avant)

    def test_pic_memoire_partiel_si_interrompue(self) -> None:
        consignateur = self.ouvrir()
        resultat = resultat_execution(
            etat=ETAT_EXECUTION_INTERROMPUE,
            audios=(audio_transcrit(), audio_non_traite()),
            evenements=(
                {"type": "chargement", "duree_s": 1.2, "pic_memoire_octets": 1024},
                {"type": "audio", "pic_memoire_octets": 4096},
            ),
        )

        self.assertTrue(consignateur.clore(resultat))

        run = self.lire("run.json")
        self.assertEqual(run["etat"], ETAT_INTERROMPUE)
        self.assertEqual(run["mesures"]["pic_memoire_octets"], 4096)
        self.assertTrue(run["mesures"]["pic_memoire_partiel"])

    def test_pic_memoire_absent_si_aucun_releve(self) -> None:
        consignateur = self.ouvrir()
        resultat = resultat_execution(
            etat=ETAT_EXECUTION_ECHOUEE,
            audios=(audio_non_traite(), audio_non_traite(1, "b.wav")),
            erreur="moteur inconnu",
        )

        self.assertTrue(consignateur.clore(resultat))

        run = self.lire("run.json")
        self.assertEqual(run["etat"], ETAT_ECHOUEE)
        self.assertIsNone(run["mesures"]["pic_memoire_octets"])
        self.assertIsNone(run["mesures"]["pic_memoire_partiel"])
        self.assertIsNone(run["mesures"]["duree_chargement_s"])

    def test_pic_memoire_partiel_si_terminee_sans_pic_dans_fin(self) -> None:
        consignateur = self.ouvrir()
        resultat = resultat_execution(
            etat=ETAT_EXECUTION_TERMINEE,
            audios=(audio_transcrit(), audio_non_traite()),
            evenements=(
                {"type": "chargement", "duree_s": 1.2, "pic_memoire_octets": 1024},
                {"type": "audio", "pic_memoire_octets": 4096},
            ),
        )

        self.assertTrue(consignateur.clore(resultat))

        # Terminée mais dernier pic venu d'un audio : pas de pic final affirmé.
        run = self.lire("run.json")
        self.assertEqual(run["etat"], ETAT_TERMINEE)
        self.assertEqual(run["mesures"]["pic_memoire_octets"], 4096)
        self.assertTrue(run["mesures"]["pic_memoire_partiel"])

    def test_mesures_non_finies_traitees_comme_absentes(self) -> None:
        consignateur = self.ouvrir()
        audio = audio_transcrit()
        assert audio.evenement is not None
        evenement = dict(audio.evenement)
        evenement.update(
            {
                "duree_transcription_s": float("nan"),
                "temps_cpu_s": float("inf"),
                "pic_memoire_octets": float("nan"),
            }
        )
        audio = replace(audio, evenement=evenement)

        self.assertTrue(consignateur.enregistrer_audio(audio))
        self.assertTrue(
            consignateur.clore(
                resultat_execution(
                    etat=ETAT_EXECUTION_TERMINEE,
                    audios=(audio, audio_non_traite()),
                    evenements=(
                        {"type": "fin", "pic_memoire_octets": float("nan")},
                    ),
                )
            )
        )

        mesures = self.lire("result.json", "1-a.wav")["mesures"]
        # NaN et infinis ne sont pas des mesures : absents, jamais recopiés.
        self.assertIsNone(mesures["duree_transcription_s"])
        self.assertIsNone(mesures["temps_cpu_s"])
        self.assertIsNone(mesures["pic_memoire_octets"])
        self.assertIsNone(mesures["rtf"])
        run = self.lire("run.json")
        self.assertIsNone(run["mesures"]["pic_memoire_octets"])
        self.assertIsNone(run["mesures"]["pic_memoire_partiel"])

    def test_journal_moteur_complet_puis_ferme(self) -> None:
        consignateur = self.ouvrir()

        for numero in range(2500):
            consignateur.ecrire_journal(f"ligne {numero}")
        consignateur.fermer()
        consignateur.fermer()  # idempotent
        consignateur.ecrire_journal("après fermeture, ignorée")

        lignes = (consignateur.dossier / "run.log").read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(lignes), 2500)
        self.assertEqual(lignes[0], "ligne 0")
        self.assertEqual(lignes[-1], "ligne 2499")

    def test_echec_result_json_puis_etat_final_en_echec(self) -> None:
        consignateur = self.ouvrir()
        vrai_remplacer = os.replace
        remplacements: list[str] = []

        def remplacer(origine: Any, cible: Any) -> None:
            remplacements.append(Path(cible).name)
            if Path(cible).name == "result.json":
                raise OSError(28, "espace insuffisant sur le périphérique")
            vrai_remplacer(origine, cible)

        with mock.patch("transcription_bench.stockage.os.replace", remplacer):
            self.assertFalse(consignateur.enregistrer_audio(audio_transcrit()))
            self.assertTrue(
                consignateur.clore(
                    resultat_execution(
                        etat=ETAT_EXECUTION_TERMINEE,
                        audios=(audio_transcrit(), audio_non_traite()),
                        evenements=(
                            {"type": "fin", "pic_memoire_octets": 2048},
                        ),
                    )
                )
            )

        self.assertIsNotNone(consignateur.erreur)
        self.assertIn("espace insuffisant", consignateur.erreur or "")
        # L'état final est écrit malgré l'erreur : jamais d'exécution `running`
        # laissée derrière soi, et le motif retenu y figure.
        self.assertEqual(remplacements[-1], "run.json")
        run = self.lire("run.json")
        self.assertEqual(run["etat"], ETAT_ECHOUEE)
        self.assertIn("espace insuffisant", run["erreur"])
        self.assertIsNotNone(run["fin"])
        self.assertEqual(consignateur.etat_final, ETAT_ECHOUEE)
        for chemin in consignateur.dossier.rglob("*"):
            self.assertFalse(chemin.name.endswith(".tmp"), chemin)
        with self.assertRaises(FileNotFoundError):
            (consignateur.dossier / "1-a.wav" / "result.json").read_text(
                encoding="utf-8"
            )
        self.assertTrue(vrai_remplacer)  # le remplacement réel est restauré

    def test_echec_total_d_ecriture_laisse_run_json_en_cours_et_lisible(self) -> None:
        consignateur = self.ouvrir()
        avant = (consignateur.dossier / "run.json").read_text(encoding="utf-8")

        def remplacer(origine: Any, cible: Any) -> None:
            raise OSError(28, "espace insuffisant sur le périphérique")

        with mock.patch("transcription_bench.stockage.os.replace", remplacer):
            self.assertFalse(consignateur.enregistrer_audio(audio_transcrit()))
            self.assertFalse(
                consignateur.clore(
                    resultat_execution(
                        etat=ETAT_EXECUTION_ECHOUEE,
                        audios=(audio_en_erreur(0, "a.wav"),),
                        erreur="disque plein",
                    )
                )
            )

        # Même l'ultime écriture échoue : l'état précédent reste lisible, sans
        # troncature ; la clôture des exécutions `running` relève de 6.5.
        self.assertEqual(
            (consignateur.dossier / "run.json").read_text(encoding="utf-8"), avant
        )
        run = self.lire("run.json")
        self.assertEqual(run["etat"], ETAT_EN_COURS)
        for chemin in consignateur.dossier.rglob("*"):
            self.assertFalse(chemin.name.endswith(".tmp"), chemin)

    def test_echec_du_journal_ne_bloque_ni_les_resultats_ni_l_etat_final(self) -> None:
        consignateur = self.ouvrir()

        class JournalQuiEchoue:
            def write(self, ligne: str) -> None:
                raise OSError(28, "espace insuffisant sur le périphérique")

            def flush(self) -> None:
                return None

        with mock.patch.object(consignateur, "_journal", JournalQuiEchoue()):
            consignateur.ecrire_journal("ligne du moteur")
            self.assertTrue(consignateur.enregistrer_audio(audio_transcrit()))
            self.assertTrue(
                consignateur.clore(
                    resultat_execution(
                        etat=ETAT_EXECUTION_TERMINEE,
                        audios=(audio_transcrit(), audio_non_traite()),
                    )
                )
            )

        # L'erreur du journal est retenue à part : elle ne masque pas les
        # résultats, qui restent écrits et exploitables.
        self.assertIsNone(consignateur.erreur)
        self.assertIn("journal", consignateur.erreur_journal or "")
        self.assertIn("espace insuffisant", consignateur.erreur_journal or "")
        run = self.lire("run.json")
        self.assertEqual(run["etat"], ETAT_TERMINEE)
        self.assertIsNone(run["erreur"])
        self.assertEqual(self.lire("result.json", "1-a.wav")["statut"], STATUT_OK)

    def test_statut_d_audio_deja_consigne_jamais_retrograde(self) -> None:
        consignateur = self.ouvrir()
        consignateur.enregistrer_audio(audio_transcrit())
        consignateur.enregistrer_audio(audio_en_erreur())

        # Clôture avec un résultat qui ne connaît plus ces audios (issue
        # imprévue) : les statuts déjà écrits font foi.
        self.assertTrue(
            consignateur.clore(
                resultat_execution(
                    etat=ETAT_EXECUTION_ECHOUEE,
                    audios=(audio_non_traite(0, "a.wav"), audio_non_traite()),
                    erreur="erreur interne",
                )
            )
        )

        run = self.lire("run.json")
        self.assertEqual(run["etat"], ETAT_ECHOUEE)
        self.assertEqual(
            [plan["statut"] for plan in run["audios"]], [STATUT_OK, STATUT_ERREUR]
        )
        self.assertIn("décodage impossible", run["audios"][1]["erreur"])
        self.assertEqual(run["progression"], {"audios_traites": 2, "audios_total": 2})

    def test_stockage_indisponible_a_l_ouverture(self) -> None:
        racine = self.donnees / "results"
        racine.parent.mkdir(parents=True, exist_ok=True)
        racine.write_text("pas un dossier", encoding="utf-8")

        self.assertFalse(self.consignateur.ouvrir())

        self.assertIsNone(self.consignateur.dossier)
        self.assertIsNotNone(self.consignateur.erreur)
        self.assertFalse(self.consignateur.enregistrer_audio(audio_transcrit()))

    def test_aucune_donnee_d_environnement_persistee(self) -> None:
        with mock.patch.dict(
            os.environ, {"HF_TOKEN": "marqueur-secret-de-test-1234"}
        ):
            consignateur = self.ouvrir()
            consignateur.enregistrer_audio(audio_transcrit())
            consignateur.clore(
                resultat_execution(
                    etat=ETAT_EXECUTION_TERMINEE, audios=(audio_transcrit(),)
                )
            )

        for chemin in consignateur.dossier.rglob("*"):
            if chemin.is_file():
                self.assertNotIn(
                    "marqueur-secret-de-test-1234",
                    chemin.read_text(encoding="utf-8", errors="replace"),
                    chemin,
                )


class AbandonnerExecutionTest(unittest.TestCase):
    """La clôture en abandonné (6.5) ne s'applique qu'à une exécution `running`."""

    def setUp(self) -> None:
        temporaire = tempfile.TemporaryDirectory()
        self.addCleanup(temporaire.cleanup)
        self.dossier = Path(temporaire.name) / "results" / "20260101-120000-aaaaaaaa"
        self.dossier.mkdir(parents=True)
        self.run_json = self.dossier / "run.json"

    def test_refus_si_etat_deja_final(self) -> None:
        for etat in ("completed", "interrupted", "failed", "abandoned"):
            with self.subTest(etat):
                with self.assertRaises(ValueError) as capture:
                    abandonner_execution(
                        self.dossier, {"schema": SCHEMA, "etat": etat, "audios": []}
                    )

                self.assertIn(etat, str(capture.exception))
                self.assertFalse(self.run_json.exists(), "un état final a été réécrit")

    def test_execution_en_cours_close_en_abandonnee(self) -> None:
        contenu = abandonner_execution(
            self.dossier,
            {"schema": SCHEMA, "etat": ETAT_EN_COURS, "audios": []},
            fin="2026-01-01T12:00:00+00:00",
        )

        self.assertEqual(contenu["etat"], "abandoned")
        self.assertEqual(
            json.loads(self.run_json.read_text(encoding="utf-8"))["etat"], "abandoned"
        )


if __name__ == "__main__":
    unittest.main()
