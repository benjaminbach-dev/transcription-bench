"""Tests du regroupement par empreinte et de la comparaison (tâche 7.2).

Les fichiers de résultats restent des données synthétiques écrites dans le
dossier temporaire des fixtures de `tests.test_consultation_resultats` : aucun
test n'écrit sous le `data/` du dépôt. Le test d'intégration final exécute le
vrai `engines/runner.py` avec le moteur factice sur un WAV synthétique, sans
poids ni réseau ; ses mesures de moteur sont simulées et marquées comme telles.
"""

from __future__ import annotations

import json
import unittest
from typing import Any

from tests.test_consultation_resultats import (
    IDENTIFIANT,
    IDENTIFIANT_ANCIEN,
    SocleConsultationTest,
    ecrire_execution,
    result_json,
    run_json,
)
from tests.test_execution_moteur import SocleExecutionTest
from transcription_bench.consultation_resultats import (
    ConsultationResultats,
    ResultatIntrouvable,
    analyser_selection,
)
from transcription_bench.paths import ValeurRefusee
from transcription_bench.resultats import (
    ETAT_ABANDONNEE,
    ETAT_INTERROMPUE,
    ETAT_TERMINEE,
    STATUT_ERREUR,
    STATUT_NON_TRAITE,
    STATUT_OK,
)

EMPREINTE_A = "a" * 64
EMPREINTE_B = "b" * 64


def resultat_empreinte(
    run: dict[str, Any],
    plan: dict[str, Any],
    empreinte: Any = EMPREINTE_A,
    **options: Any,
) -> dict[str, Any]:
    """`result.json` dont l'empreinte du fichier audio source est imposée."""
    resultat = result_json(plan, execution=run["identifiant"], **options)
    resultat["audio"]["empreinte_sha256"] = empreinte
    return resultat


def options_resultat(
    demandes: dict[str, Any] | None,
    effectifs: dict[str, Any] | None,
    texte: str | None,
    mesures: dict[str, Any] | None,
) -> dict[str, Any]:
    """Options de `result_json` : `None` laisse les réglages demandés par défaut."""
    options: dict[str, Any] = {"texte": texte, "mesures_extra": mesures}
    if demandes is not None:
        options["reglages"] = demandes
    options["reglages_effectifs"] = effectifs
    return options


def ligne(vue, libelle: str):
    """Ligne de comparaison par libellé, ou échec explicite."""
    for candidate in vue.lignes:
        if candidate.libelle == libelle:
            return candidate
    raise AssertionError(f"ligne absente : {libelle!r}")


class GroupesParEmpreinteTest(SocleConsultationTest):
    def test_groupes_vides_sans_creation_de_dossier(self) -> None:
        self.assertEqual(self.service.groupes_par_empreinte(), ())
        self.assertFalse(self.service.dossier_resultats.exists())

    def test_meme_nom_et_empreintes_differentes_forment_deux_groupes(self) -> None:
        ancien = run_json(IDENTIFIANT_ANCIEN)
        recent = run_json(IDENTIFIANT)
        ecrire_execution(
            self.donnees,
            ancien,
            (resultat_empreinte(ancien, ancien["audios"][0], EMPREINTE_A),),
        )
        ecrire_execution(
            self.donnees,
            recent,
            (resultat_empreinte(recent, recent["audios"][0], EMPREINTE_B),),
        )

        groupes = self.service.groupes_par_empreinte()

        # Le plus récent d'abord, comme la liste des exécutions.
        self.assertEqual(
            [groupe.empreinte for groupe in groupes], [EMPREINTE_B, EMPREINTE_A]
        )
        self.assertEqual([groupe.noms for groupe in groupes], [("a.wav",), ("a.wav",)])
        self.assertEqual([len(groupe.entrees) for groupe in groupes], [1, 1])
        self.assertEqual(
            [groupe.entrees[0].execution for groupe in groupes],
            [IDENTIFIANT, IDENTIFIANT_ANCIEN],
        )

    def test_meme_empreinte_et_noms_differents_reunis_dans_un_groupe(self) -> None:
        premier = run_json(IDENTIFIANT, audios=(("prise.wav", STATUT_OK),))
        second = run_json(IDENTIFIANT_ANCIEN, audios=(("copie.wav", STATUT_OK),))
        ecrire_execution(
            self.donnees,
            premier,
            (resultat_empreinte(premier, premier["audios"][0]),),
        )
        ecrire_execution(
            self.donnees,
            second,
            (resultat_empreinte(second, second["audios"][0]),),
        )

        groupes = self.service.groupes_par_empreinte()

        self.assertEqual(len(groupes), 1)
        groupe = groupes[0]
        self.assertEqual(groupe.empreinte, EMPREINTE_A)
        self.assertEqual(groupe.noms, ("copie.wav", "prise.wav"))
        self.assertEqual(
            [(entree.execution, entree.nom) for entree in groupe.entrees],
            [(IDENTIFIANT, "prise.wav"), (IDENTIFIANT_ANCIEN, "copie.wav")],
        )

    def test_empreinte_absente_ou_invalide_jamais_groupee(self) -> None:
        sans_empreinte = run_json(IDENTIFIANT, audios=(("a.wav", STATUT_OK),))
        invalide = run_json(
            "20240103-000000-00000003", audios=(("b.wav", STATUT_OK),)
        )
        sans_resultat = run_json(
            "20240104-000000-00000004", audios=(("c.wav", STATUT_OK),)
        )
        non_traite = run_json(
            "20240105-000000-00000005", audios=(("d.wav", STATUT_NON_TRAITE),)
        )
        ecrire_execution(
            self.donnees,
            sans_empreinte,
            (resultat_empreinte(sans_empreinte, sans_empreinte["audios"][0], None),),
        )
        ecrire_execution(
            self.donnees,
            invalide,
            (
                resultat_empreinte(
                    invalide, invalide["audios"][0], "pas-une-empreinte"
                ),
            ),
        )
        ecrire_execution(self.donnees, sans_resultat)
        ecrire_execution(self.donnees, non_traite)

        self.assertEqual(self.service.groupes_par_empreinte(), ())

    def test_empreinte_en_majuscules_normalisee(self) -> None:
        run = run_json()
        ecrire_execution(
            self.donnees,
            run,
            (resultat_empreinte(run, run["audios"][0], EMPREINTE_A.upper()),),
        )

        groupes = self.service.groupes_par_empreinte()

        self.assertEqual([groupe.empreinte for groupe in groupes], [EMPREINTE_A])

    def test_entree_reprend_etat_partiel_et_marques(self) -> None:
        run = run_json(etat=ETAT_INTERROMPUE)
        ecrire_execution(
            self.donnees, run, (resultat_empreinte(run, run["audios"][0]),)
        )

        entree = self.service.groupes_par_empreinte()[0].entrees[0]

        self.assertEqual(entree.libelle_etat, "interrompue")
        self.assertTrue(entree.partiel)
        self.assertEqual(entree.libelle_statut, "transcrit")
        self.assertIn("FACTICE", entree.marques)
        self.assertIn("SYNTHÉTIQUE", entree.marques)
        self.assertIn("MESURES SIMULÉES", entree.marques)
        self.assertEqual(entree.modele, "aucun modèle, textes et mesures simulés")
        self.assertEqual(entree.moteur, "Moteur factice")

    def test_execution_non_interpretable_ignoree_sans_exception(self) -> None:
        valide = run_json()
        ecrire_execution(
            self.donnees, valide, (resultat_empreinte(valide, valide["audios"][0]),)
        )
        ecrire_execution(self.donnees, run_json("20240103-000000-00000003", schema=2))

        groupes = self.service.groupes_par_empreinte()

        self.assertEqual(len(groupes), 1)
        self.assertEqual(groupes[0].entrees[0].execution, IDENTIFIANT)


class ComparerTest(SocleConsultationTest):
    def deux_executions(
        self,
        *,
        effectifs_a: dict[str, Any] | None = None,
        effectifs_b: dict[str, Any] | None = None,
        demandes_a: dict[str, Any] | None = None,
        demandes_b: dict[str, Any] | None = None,
        etat_b: str = ETAT_TERMINEE,
        statut_b: str = STATUT_OK,
        mesures_b: dict[str, Any] | None = None,
        empreinte_b: Any = EMPREINTE_A,
        avec_resultat_b: bool = True,
        texte_a: str | None = "transcription simulée de test",
        texte_b: str | None = "transcription simulée de test",
        mesures_audio_a: dict[str, Any] | None = None,
        mesures_audio_b: dict[str, Any] | None = None,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        """Écrit deux exécutions d'un même audio et renvoie leurs `run.json`.

        `demandes_*` laisse la valeur par défaut de la fixture quand il vaut
        `None` ; `effectifs_*` vaut alors « aucun réglage effectif consigné »,
        comme pour un audio en erreur.
        """
        premier = run_json(IDENTIFIANT)
        second = run_json(IDENTIFIANT_ANCIEN, etat=etat_b, mesures=mesures_b)
        ecrire_execution(
            self.donnees,
            premier,
            (
                resultat_empreinte(
                    premier,
                    premier["audios"][0],
                    **options_resultat(
                        demandes_a, effectifs_a, texte_a, mesures_audio_a
                    ),
                ),
            ),
        )
        resultats = (
            (
                resultat_empreinte(
                    second,
                    second["audios"][0],
                    empreinte_b,
                    statut=statut_b,
                    **options_resultat(
                        demandes_b, effectifs_b, texte_b, mesures_audio_b
                    ),
                ),
            )
            if avec_resultat_b
            else ()
        )
        ecrire_execution(self.donnees, second, resultats)
        return premier, second

    def comparer(self, empreinte: str = EMPREINTE_A):
        return self.service.comparer(
            empreinte, [(IDENTIFIANT, 1), (IDENTIFIANT_ANCIEN, 1)]
        )

    def test_comparaison_deux_executions_du_meme_audio(self) -> None:
        self.deux_executions()

        vue = self.comparer()

        self.assertEqual(vue.empreinte, EMPREINTE_A)
        self.assertEqual(vue.noms, ("a.wav",))
        self.assertEqual(
            [colonne.execution for colonne in vue.colonnes],
            [IDENTIFIANT, IDENTIFIANT_ANCIEN],
        )
        self.assertFalse(vue.partiel)
        # Les fixtures sont factices : la marque reste visible dans les cellules.
        self.assertTrue(vue.factice)
        marques = ligne(vue, "Marques")
        self.assertFalse(marques.differents)
        self.assertIn("FACTICE", marques.cellules[0].valeur)
        self.assertEqual(
            ligne(vue, "Résultats partiels").cellules[0].valeur,
            False,
        )
        duree = ligne(vue, "Durée totale de l'opération")
        self.assertEqual([cellule.valeur for cellule in duree.cellules], [12.5, 12.5])
        self.assertFalse(duree.differents)
        self.assertEqual(duree.nature, "duree")

    def test_ligne_texte_transcrit_sans_diff_textuel(self) -> None:
        self.deux_executions(
            texte_a="Premier texte transcrit.\nDeuxième ligne du premier texte.",
            texte_b="Autre texte transcrit, différent.",
        )

        vue = self.comparer()

        textes = ligne(vue, "Texte transcrit")
        self.assertEqual(textes.nature, "transcription")
        # Aucun diff textuel : la ligne n'est jamais marquée « différent ».
        self.assertFalse(textes.differents)
        self.assertEqual(
            [cellule.valeur for cellule in textes.cellules],
            [
                "Premier texte transcrit.\nDeuxième ligne du premier texte.",
                "Autre texte transcrit, différent.",
            ],
        )
        self.assertTrue(all(cellule.presente for cellule in textes.cellules))

    def test_ligne_texte_transcrit_absente_quand_aucun_texte(self) -> None:
        self.deux_executions(texte_a=None, texte_b="Autre texte transcrit.")

        textes = ligne(self.comparer(), "Texte transcrit")

        self.assertEqual(
            [cellule.valeur for cellule in textes.cellules],
            [None, "Autre texte transcrit."],
        )

    def test_rtf_conserve_sa_nature_pour_le_repere_non_bloquant(self) -> None:
        self.deux_executions(
            mesures_audio_a={"duree_transcription_s": 3.0},
            mesures_audio_b={"duree_transcription_s": 1.0},
        )

        vue = self.comparer()

        rtf = ligne(vue, "RTF (durée de transcription / durée décodée)")
        self.assertEqual(rtf.nature, "rtf")
        # RTF de 1.5 et 0.5 sur une durée décodée de 2 s : repère jamais bloquant.
        self.assertEqual([cellule.valeur for cellule in rtf.cellules], [1.5, 0.5])

    def test_reglages_identiques_composes_non_signales(self) -> None:
        reglages = {
            "langue": "fr",
            "temperature": [0.0, 0.2],
            "options": {"a": {"b": 1}},
        }
        self.deux_executions(effectifs_a=reglages, effectifs_b=dict(reglages))

        vue = self.comparer()

        for nom in ("langue", "temperature", "options"):
            with self.subTest(reglage=nom):
                ligne_reglage = ligne(vue, f"Réglage effectif : {nom}")
                self.assertFalse(ligne_reglage.differents)
                self.assertTrue(ligne_reglage.cellules[0].presente)
        # La valeur brute d'une liste et d'un objet reste affichable.
        self.assertEqual(
            ligne(vue, "Réglage effectif : temperature").cellules[0].valeur,
            "[0.0,0.2]",
        )
        self.assertEqual(
            ligne(vue, "Réglage effectif : options").cellules[0].valeur,
            '{"a":{"b":1}}',
        )

    def test_reglages_differents_listes_et_objets_signales(self) -> None:
        self.deux_executions(
            effectifs_a={
                "langue": "fr",
                "temperature": [0.0, 0.2],
                "options": {"a": {"b": 1}},
            },
            effectifs_b={
                "langue": "fr",
                "temperature": [0.0, 0.4],
                "options": {"a": {"b": 2}},
            },
        )

        vue = self.comparer()

        self.assertTrue(ligne(vue, "Réglage effectif : temperature").differents)
        self.assertTrue(ligne(vue, "Réglage effectif : options").differents)
        self.assertFalse(ligne(vue, "Réglage effectif : langue").differents)

    def test_cle_absente_distincte_d_une_valeur_explicite(self) -> None:
        self.deux_executions(
            effectifs_a={"langue": "fr", "beam_size": 5},
            effectifs_b={"langue": None},
        )

        vue = self.comparer()

        langue = ligne(vue, "Réglage effectif : langue")
        self.assertTrue(langue.differents)
        self.assertEqual(
            [(cellule.presente, cellule.valeur) for cellule in langue.cellules],
            [(True, "fr"), (True, None)],
        )
        beam = ligne(vue, "Réglage effectif : beam_size")
        self.assertTrue(beam.differents)
        self.assertEqual(
            [(cellule.presente, cellule.valeur) for cellule in beam.cellules],
            [(True, 5), (False, None)],
        )

    def test_reglage_absent_des_deux_cotes_absent_de_la_table(self) -> None:
        self.deux_executions(effectifs_a={}, effectifs_b={})

        vue = self.comparer()

        self.assertEqual(
            [
                candidate.libelle
                for candidate in vue.lignes
                if candidate.libelle.startswith("Réglage effectif")
            ],
            [],
        )

    def test_etats_partiels_et_mesures_absentes(self) -> None:
        self.deux_executions(
            etat_b=ETAT_ABANDONNEE,
            mesures_b={
                "duree_operation_s": None,
                "duree_processus_s": None,
                "duree_chargement_s": 2.5,
                "pic_memoire_octets": 4096,
                "pic_memoire_partiel": True,
            },
            empreinte_b=EMPREINTE_A,
        )

        vue = self.comparer()

        self.assertTrue(vue.partiel)
        self.assertEqual(vue.colonnes[1].libelle_etat, "abandonnée")
        partiels = ligne(vue, "Résultats partiels")
        self.assertTrue(partiels.differents)
        self.assertEqual(
            [cellule.valeur for cellule in partiels.cellules], [False, True]
        )
        duree = ligne(vue, "Durée totale de l'opération")
        self.assertTrue(duree.differents)
        self.assertEqual([cellule.valeur for cellule in duree.cellules], [12.5, None])
        memoire = ligne(vue, "Pic de mémoire de l'exécution partiel")
        self.assertEqual(
            [cellule.valeur for cellule in memoire.cellules], [False, True]
        )

    def test_valeurs_brutes_distinctes_jamais_confondues_par_l_affichage(self) -> None:
        cas = (
            ("liste et chaîne", "temperature", [0.0, 0.2], "[0,0.2]"),
            ("objet et chaîne", "options", {"a": 1}, '{"a":1}'),
            (
                "NaN imbriqué et null imbriqué",
                "temperature",
                [float("nan")],
                [None],
            ),
            ("NaN et null", "temperature", float("nan"), None),
            ("infini et moins infini", "temperature", float("inf"), float("-inf")),
            ("entier et flottant", "beam_size", 1, 1.0),
            ("booléen et entier", "condition", True, 1),
        )
        for nom, cle, gauche, droite in cas:
            with self.subTest(cas=nom):
                # Les écritures remplacent les fichiers précédents du même audio.
                self.deux_executions(
                    effectifs_a={cle: gauche},
                    effectifs_b={cle: droite},
                )

                reglage = ligne(self.comparer(), f"Réglage effectif : {cle}")

                self.assertTrue(reglage.differents)
                # NaN n'étant pas égal à lui-même, les valeurs brutes sont
                # comparées sur leur JSON, comme le fait le service.
                self.assertEqual(
                    json.dumps(reglage.cellules[0].brut), json.dumps(gauche)
                )
                self.assertEqual(
                    json.dumps(reglage.cellules[1].brut), json.dumps(droite)
                )

    def test_affichage_peut_masquer_une_difference_brute(self) -> None:
        # NaN et null s'affichent tous deux « indisponible », infini et moins
        # infini aussi : la différence n'est visible que sur les valeurs brutes.
        self.deux_executions(
            effectifs_a={"temperature": float("nan")},
            effectifs_b={"temperature": None},
        )

        reglage = ligne(self.comparer(), "Réglage effectif : temperature")

        self.assertTrue(reglage.differents)
        self.assertIsNone(reglage.cellules[0].valeur)
        self.assertIsNone(reglage.cellules[1].valeur)
        self.assertNotEqual(
            reglage.cellules[0].brut, reglage.cellules[1].brut
        )

    def test_liste_et_chaine_de_meme_texte_restent_differentes(self) -> None:
        self.deux_executions(
            effectifs_a={"temperature": [0.0, 0.2]},
            effectifs_b={"temperature": "[0.0,0.2]"},
        )

        reglage = ligne(self.comparer(), "Réglage effectif : temperature")

        # Même texte affiché, types bruts différents : la ligne est marquée.
        self.assertTrue(reglage.differents)
        self.assertEqual(reglage.cellules[0].valeur, "[0.0,0.2]")
        self.assertEqual(reglage.cellules[1].valeur, "[0.0,0.2]")
        self.assertEqual(reglage.cellules[0].brut, [0.0, 0.2])
        self.assertEqual(reglage.cellules[1].brut, "[0.0,0.2]")

    def test_colonne_en_erreur_compare_les_reglages_demandes(self) -> None:
        self.deux_executions(
            statut_b=STATUT_ERREUR,
            demandes_a={"temperature": 0.0, "beam_size": 5},
            demandes_b={"temperature": 0.4, "beam_size": 5},
        )

        vue = self.comparer()

        self.assertEqual(vue.colonnes[1].libelle_statut, "erreur")
        temperature = ligne(vue, "Réglage demandé : temperature")
        self.assertTrue(temperature.differents)
        self.assertEqual(
            [cellule.valeur for cellule in temperature.cellules], [0.0, 0.4]
        )
        self.assertEqual([cellule.brut for cellule in temperature.cellules], [0.0, 0.4])
        self.assertFalse(ligne(vue, "Réglage demandé : beam_size").differents)
        # Aucun réglage effectif n'est consigné : aucune ligne effective inventée.
        self.assertEqual(
            [
                candidate.libelle
                for candidate in vue.lignes
                if candidate.libelle.startswith("Réglage effectif")
            ],
            [],
        )

    def test_melange_d_empreintes_refuse(self) -> None:
        self.deux_executions(empreinte_b=EMPREINTE_B)

        with self.assertRaises(ValeurRefusee):
            self.comparer()

    def test_empreinte_demandee_invalide_refusee(self) -> None:
        self.deux_executions()

        for empreinte in ("", "abc", EMPREINTE_A.upper() + "z", "\x00" * 64):
            with self.subTest(empreinte=empreinte):
                with self.assertRaises(ValeurRefusee):
                    self.service.comparer(
                        empreinte, [(IDENTIFIANT, 1), (IDENTIFIANT_ANCIEN, 1)]
                    )

    def test_selection_insuffisante_refusee(self) -> None:
        self.deux_executions()

        for selections in (
            (),
            ((IDENTIFIANT, 1),),
            ((IDENTIFIANT, 1), (IDENTIFIANT, 1)),
        ):
            with self.subTest(selections=selections):
                with self.assertRaises(ValeurRefusee):
                    self.service.comparer(EMPREINTE_A, list(selections))

    def test_doublon_de_selection_retire(self) -> None:
        self.deux_executions()

        vue = self.service.comparer(
            EMPREINTE_A,
            [(IDENTIFIANT, 1), (IDENTIFIANT, 1), (IDENTIFIANT_ANCIEN, 1)],
        )

        self.assertEqual(len(vue.colonnes), 2)

    def test_empreinte_absente_dans_un_resultat_refusee(self) -> None:
        premier = run_json(IDENTIFIANT)
        second = run_json(IDENTIFIANT_ANCIEN)
        ecrire_execution(
            self.donnees,
            premier,
            (resultat_empreinte(premier, premier["audios"][0], None),),
        )
        ecrire_execution(
            self.donnees,
            second,
            (resultat_empreinte(second, second["audios"][0], None),),
        )

        with self.assertRaises(ValeurRefusee):
            self.comparer()

    def test_selection_inconnue_hostile_ou_sans_resultat(self) -> None:
        self.deux_executions(avec_resultat_b=False)

        with self.assertRaises(ResultatIntrouvable):
            self.service.comparer(
                EMPREINTE_A, [(IDENTIFIANT, 1), (IDENTIFIANT_ANCIEN, 1)]
            )
        with self.assertRaises(ResultatIntrouvable):
            self.service.comparer(
                EMPREINTE_A, [(IDENTIFIANT, 1), (IDENTIFIANT_ANCIEN, 9)]
            )
        with self.assertRaises(ResultatIntrouvable):
            self.service.comparer(
                EMPREINTE_A,
                [(IDENTIFIANT, 1), ("20240101-000000-00000000", 1)],
            )
        with self.assertRaises(ValeurRefusee):
            self.service.comparer(
                EMPREINTE_A, [(IDENTIFIANT, 1), ("../secret", 1)]
            )

    def test_lecture_seule_sur_les_fichiers_compares(self) -> None:
        self.deux_executions(
            effectifs_a={"temperature": [0.0, 0.2]},
            effectifs_b={"temperature": [0.0, 0.4]},
        )
        racine = self.donnees / "results"
        avant = {
            chemin: chemin.read_bytes()
            for chemin in sorted(racine.rglob("*"))
            if chemin.is_file()
        }

        self.service.groupes_par_empreinte()
        self.comparer()

        apres = {
            chemin: chemin.read_bytes()
            for chemin in sorted(racine.rglob("*"))
            if chemin.is_file()
        }
        self.assertEqual(avant, apres)


class AnalyserSelectionTest(unittest.TestCase):
    def test_selection_valide(self) -> None:
        self.assertEqual(analyser_selection(f"{IDENTIFIANT}:2"), (IDENTIFIANT, 2))

    def test_formes_hostiles_refusees(self) -> None:
        hostiles = (
            "",
            IDENTIFIANT,
            f"{IDENTIFIANT}:",
            f"{IDENTIFIANT}:0",
            f"{IDENTIFIANT}:-1",
            f"{IDENTIFIANT}:1:2",
            f"{IDENTIFIANT}:1a",
            f"{IDENTIFIANT}:١",
            f"{IDENTIFIANT}/../secret:1",
            f"..\\secret:1",
            f"C:\\secret:1",
            f"/etc/passwd:1",
            "pas-un-identifiant:1",
            "20240102-030405-0A0B0C0D:1",
            f"{IDENTIFIANT}:1234567",
        )
        for texte in hostiles:
            with self.subTest(selection=texte):
                with self.assertRaises(ValeurRefusee):
                    analyser_selection(texte)


class IntegrationComparaisonFacticeTest(SocleExecutionTest):
    """Deux exécutions réelles du moteur factice comparées par empreinte.

    Le vrai `engines/runner.py` est exécuté sur le même WAV synthétique, sans
    poids, sans inférence réelle et sans réseau ; les mesures du moteur sont
    simulées et marquées comme telles.
    """

    def test_deux_executions_factices_du_meme_audio_comparees(self) -> None:
        self.ecrire_audio("prise.wav", 0.4)
        premier = self.executer(self.demande(("prise.wav",)))
        self.assertTerminee(premier)
        second = self.executer(self.demande(("prise.wav",)))
        self.assertTerminee(second)
        self.assertNotEqual(premier.identifiant_resultat, second.identifiant_resultat)

        service = ConsultationResultats(self.dossier_data)
        groupes = service.groupes_par_empreinte()
        self.assertEqual(len(groupes), 1)
        groupe = groupes[0]
        self.assertEqual(len(groupe.empreinte), 64)
        self.assertEqual(groupe.noms, ("prise.wav",))
        self.assertEqual(
            {entree.execution for entree in groupe.entrees},
            {premier.identifiant_resultat, second.identifiant_resultat},
        )

        vue = service.comparer(
            groupe.empreinte,
            [(entree.execution, entree.ordre) for entree in groupe.entrees],
        )

        self.assertEqual(len(vue.colonnes), 2)
        self.assertFalse(vue.partiel)
        self.assertTrue(vue.factice)
        marques = ligne(vue, "Marques")
        self.assertIn("FACTICE", marques.cellules[0].valeur)
        self.assertIn("FACTICE", marques.cellules[1].valeur)
        duree = ligne(vue, "Durée totale de l'opération")
        for cellule in duree.cellules:
            self.assertIsInstance(cellule.valeur, float)
            self.assertGreater(cellule.valeur, 0)
        rtf = ligne(vue, "RTF (durée de transcription / durée décodée)")
        for cellule in rtf.cellules:
            self.assertIsNotNone(cellule.valeur)
        decodee = ligne(vue, "Durée décodée (référence du RTF)")
        for cellule in decodee.cellules:
            self.assertAlmostEqual(cellule.valeur, 0.4, places=2)


if __name__ == "__main__":
    unittest.main()
