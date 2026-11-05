"""Tests du regroupement par empreinte et de la comparaison (tâche 7.2).

Les fichiers de résultats restent des données synthétiques écrites dans le
dossier temporaire des fixtures de `tests.test_consultation_resultats` : aucun
test n'écrit sous le `data/` du dépôt. Le test d'intégration final exécute le
vrai `engines/runner.py` avec le moteur factice sur un WAV synthétique, sans
poids ni réseau ; ses mesures de moteur sont simulées et marquées comme telles.
"""

from __future__ import annotations

import json
import shutil
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
    MARQUE_FACTICE,
    MARQUE_MESURES_SIMULEES,
    MARQUE_SYNTHETIQUE,
    TRI_CPU,
    TRI_DEFAUT,
    TRI_RAM,
    TRI_RECENT,
    TRI_TEMPS,
    ConsultationResultats,
    EntreeEmpreinte,
    GroupeEmpreinte,
    ResultatIntrouvable,
    analyser_selection,
    analyser_tri,
    valeur_distinction,
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


IDENTIFIANT_TIERS = "20240103-040506-55667788"
IDENTIFIANT_QUATRIEME = "20240104-050607-8899aabb"


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
        self.assertEqual(entree.etat, ETAT_INTERROMPUE)
        self.assertEqual(entree.date_essai, run["cree_le"])
        self.assertTrue(entree.partiel)
        self.assertEqual(entree.libelle_statut, "transcrit")
        self.assertIn("FACTICE", entree.marques)
        self.assertIn("SYNTHÉTIQUE", entree.marques)
        self.assertIn("MESURES SIMULÉES", entree.marques)
        self.assertEqual(entree.modele, "aucun modèle, textes et mesures simulés")
        self.assertEqual(entree.moteur, "Moteur factice")
        self.assertEqual(entree.mesures.duree_transcription_s, 1.0)
        self.assertEqual(entree.mesures.temps_cpu_s, 1.5)
        self.assertEqual(entree.mesures.pic_memoire_octets, 2048)
        self.assertEqual(entree.materiel.coeurs_logiques, 8)
        self.assertEqual(entree.materiel.ram_totale_octets, 8 * 1024**3)

    def test_entree_mesures_par_audio_et_materiel_consigne(self) -> None:
        machine = {
            "os": "Windows",
            "version_os": "10.0.19045",
            "architecture": "ARM64",
            "processeur": "Processeur fictif de test",
            "coeurs_physiques": 2,
            "coeurs_logiques": 3,
            "ram_totale_octets": 4_000_000_000,
        }
        run = run_json(
            audios=(("a.wav", STATUT_OK), ("b.wav", STATUT_OK)),
            machine=machine,
            cree_le="2024-05-06T07:08:09+00:00",
        )
        premier, second = run["audios"]
        ecrire_execution(
            self.donnees,
            run,
            (
                resultat_empreinte(
                    run,
                    premier,
                    mesures_extra={
                        "duree_transcription_s": 1.0,
                        "temps_cpu_s": 2.5,
                        "pic_memoire_octets": 1000,
                    },
                ),
                resultat_empreinte(
                    run,
                    second,
                    mesures_extra={
                        "duree_transcription_s": 7.5,
                        "temps_cpu_s": 12.0,
                        "pic_memoire_octets": 9000,
                    },
                ),
            ),
        )

        entree_a, entree_b = self.service.groupes_par_empreinte()[0].entrees

        # Les mesures sont celles de chaque audio, jamais celles de l'exécution.
        self.assertEqual((entree_a.ordre, entree_b.ordre), (1, 2))
        self.assertEqual(entree_a.mesures.duree_transcription_s, 1.0)
        self.assertEqual(entree_a.mesures.temps_cpu_s, 2.5)
        self.assertEqual(entree_a.mesures.pic_memoire_octets, 1000)
        self.assertEqual(entree_b.mesures.duree_transcription_s, 7.5)
        self.assertEqual(entree_b.mesures.temps_cpu_s, 12.0)
        self.assertEqual(entree_b.mesures.pic_memoire_octets, 9000)
        # Le matériel est celui consigné dans l'essai, pas celui du poste qui
        # consulte : rien n'est remplacé par une capacité locale.
        self.assertEqual(entree_a.materiel, entree_b.materiel)
        self.assertEqual(entree_a.materiel.os, "Windows")
        self.assertEqual(entree_a.materiel.version_os, "10.0.19045")
        self.assertEqual(entree_a.materiel.architecture, "ARM64")
        self.assertEqual(entree_a.materiel.processeur, "Processeur fictif de test")
        self.assertEqual(entree_a.materiel.coeurs_physiques, 2)
        self.assertEqual(entree_a.materiel.coeurs_logiques, 3)
        self.assertEqual(entree_a.materiel.ram_totale_octets, 4_000_000_000)
        self.assertEqual(entree_a.date_essai, "2024-05-06T07:08:09+00:00")
        self.assertEqual(entree_a.date_essai, entree_b.date_essai)
        self.assertEqual(entree_a.etat, ETAT_TERMINEE)

    def test_entree_disponible_apres_suppression_du_modele_local(self) -> None:
        run = run_json()
        modele = self.donnees / "models" / "factice" / ("0" * 64)
        modele.mkdir(parents=True)
        (modele / "modele.bin").write_bytes(b"poids simules")
        ecrire_execution(
            self.donnees, run, (resultat_empreinte(run, run["audios"][0]),)
        )

        avant = self.service.groupes_par_empreinte()[0].entrees[0]
        shutil.rmtree(self.donnees / "models")
        self.assertFalse((self.donnees / "models").exists())
        apres = self.service.groupes_par_empreinte()[0].entrees[0]

        # Les données consignées ne dépendent pas des poids locaux : le modèle
        # supprimé ne retire ni mesure, ni matériel, ni date de l'entrée.
        self.assertEqual(apres, avant)
        self.assertEqual(apres.mesures.duree_transcription_s, 1.0)
        self.assertEqual(apres.materiel.coeurs_logiques, 8)
        self.assertEqual(apres.date_essai, run["cree_le"])

    def test_entree_champs_manquants_ou_invalides_indisponibles(self) -> None:
        ancien = run_json(IDENTIFIANT_ANCIEN, machine=None, cree_le=None)
        ancien_resultat = resultat_empreinte(ancien, ancien["audios"][0])
        del ancien_resultat["mesures"]
        ecrire_execution(self.donnees, ancien, (ancien_resultat,))

        invalide = run_json(
            IDENTIFIANT,
            machine={
                "os": 123,
                "version_os": "  ",
                "architecture": None,
                "processeur": False,
                "coeurs_physiques": "2",
                "coeurs_logiques": 3.0,
                "ram_totale_octets": True,
            },
            cree_le=42,
        )
        ecrire_execution(
            self.donnees,
            invalide,
            (
                resultat_empreinte(
                    invalide,
                    invalide["audios"][0],
                    mesures_extra={
                        "duree_transcription_s": "1.0",
                        "temps_cpu_s": True,
                        "pic_memoire_octets": float("nan"),
                    },
                ),
            ),
        )

        entree_invalide, entree_ancienne = self.service.groupes_par_empreinte()[
            0
        ].entrees

        # Un champ illisible reste indisponible : il n'est ni repris ni remplacé
        # par zéro, et l'exécution reste groupée.
        self.assertIsNone(entree_invalide.date_essai)
        self.assertEqual(entree_invalide.etat, ETAT_TERMINEE)
        self.assertIsNone(entree_invalide.mesures.duree_transcription_s)
        self.assertIsNone(entree_invalide.mesures.temps_cpu_s)
        self.assertIsNone(entree_invalide.mesures.pic_memoire_octets)
        self.assertEqual(
            (
                entree_invalide.materiel.os,
                entree_invalide.materiel.version_os,
                entree_invalide.materiel.architecture,
                entree_invalide.materiel.processeur,
                entree_invalide.materiel.coeurs_physiques,
                entree_invalide.materiel.coeurs_logiques,
                entree_invalide.materiel.ram_totale_octets,
            ),
            (None, None, None, None, None, None, None),
        )
        # Résultat antérieur aux champs : toutes les mesures sont indisponibles,
        # mais le matériel manquant ne rend pas l'entrée inutilisable.
        self.assertIsNone(entree_ancienne.date_essai)
        self.assertIsNone(entree_ancienne.mesures.duree_transcription_s)
        self.assertIsNone(entree_ancienne.mesures.temps_cpu_s)
        self.assertEqual(
            (
                entree_ancienne.materiel.os,
                entree_ancienne.materiel.architecture,
                entree_ancienne.materiel.coeurs_logiques,
                entree_ancienne.materiel.ram_totale_octets,
            ),
            (None, None, None, None),
        )

    def test_execution_non_interpretable_ignoree_sans_exception(self) -> None:
        valide = run_json()
        ecrire_execution(
            self.donnees, valide, (resultat_empreinte(valide, valide["audios"][0]),)
        )
        ecrire_execution(self.donnees, run_json("20240103-000000-00000003", schema=2))

        groupes = self.service.groupes_par_empreinte()

        self.assertEqual(len(groupes), 1)
        self.assertEqual(groupes[0].entrees[0].execution, IDENTIFIANT)


class ListeParResultatTest(SocleConsultationTest):
    """Lignes de résultats, sous-listes simulées et distinctions (tâche 2.2)."""

    def ecrire_essai(
        self,
        identifiant: str = IDENTIFIANT,
        *,
        empreinte: Any = EMPREINTE_A,
        simule: bool = False,
        synthetique: bool = False,
        etat: str = ETAT_TERMINEE,
        mesures: dict[str, Any] | None = None,
        **options: Any,
    ) -> None:
        """Exécution synthétique, marquée ou non comme simulée.

        `simule=False` écrit des marques de mesures observées ; `synthetique`
        reste indépendant, car un audio synthétique peut être transcrit avec des
        mesures réelles.
        """
        marques = {
            "factice": False,
            "synthetique": synthetique,
            "mesures_simulees": False,
        }
        if simule:
            marques = {
                "factice": True,
                "synthetique": True,
                "mesures_simulees": True,
            }
        run = run_json(identifiant, etat=etat, **marques)
        options_resultat: dict[str, Any] = dict(marques)
        if mesures is not None:
            options_resultat["mesures_extra"] = mesures
        options_resultat.update(options)
        ecrire_execution(
            self.donnees,
            run,
            (
                resultat_empreinte(
                    run, run["audios"][0], empreinte, **options_resultat
                ),
            ),
        )

    def groupe(self, tri: str = TRI_DEFAUT) -> GroupeEmpreinte:
        groupes = self.service.groupes_par_empreinte(tri)
        self.assertEqual(len(groupes), 1)
        return groupes[0]

    def entree(self, identifiant: str, tri: str = TRI_DEFAUT) -> EntreeEmpreinte:
        for candidat in self.groupe(tri).entrees:
            if candidat.execution == identifiant:
                return candidat
        raise AssertionError(f"entrée absente : {identifiant!r}")

    def test_simulations_separees_avec_tri_conserve_dans_chaque_sous_liste(
        self,
    ) -> None:
        self.ecrire_essai(
            IDENTIFIANT_ANCIEN,
            mesures={"duree_transcription_s": 2.0, "pic_memoire_octets": 400},
        )
        self.ecrire_essai(
            IDENTIFIANT,
            mesures={"duree_transcription_s": 1.0, "pic_memoire_octets": 300},
        )
        self.ecrire_essai(
            IDENTIFIANT_TIERS,
            simule=True,
            mesures={"duree_transcription_s": 0.5, "pic_memoire_octets": 500},
        )
        self.ecrire_essai(
            IDENTIFIANT_QUATRIEME,
            simule=True,
            mesures={"duree_transcription_s": 3.0, "pic_memoire_octets": 100},
        )

        groupe = self.groupe()

        # Les mesures simulées sont dans une sous-liste distincte, chacune
        # classée par le critère demandé et jamais fusionnée avec les réelles.
        self.assertEqual(
            [entree.execution for entree in groupe.entrees_reelles],
            [IDENTIFIANT, IDENTIFIANT_ANCIEN],
        )
        self.assertEqual(
            [entree.execution for entree in groupe.entrees_simulees],
            [IDENTIFIANT_TIERS, IDENTIFIANT_QUATRIEME],
        )
        self.assertEqual(
            groupe.entrees, groupe.entrees_reelles + groupe.entrees_simulees
        )
        self.assertTrue(all(not e.simule for e in groupe.entrees_reelles))
        self.assertTrue(all(e.simule for e in groupe.entrees_simulees))
        self.assertIn(MARQUE_FACTICE, self.entree(IDENTIFIANT_TIERS).marques)
        self.assertIn(MARQUE_MESURES_SIMULEES, self.entree(IDENTIFIANT_TIERS).marques)
        self.assertEqual(self.entree(IDENTIFIANT).marques, ())

        # Le tri par mémoire s'applique aussi dans chaque sous-liste :
        # l'ordre des simulations change, celui des résultats observés reste.
        ram = self.groupe(TRI_RAM)
        self.assertEqual(
            [entree.execution for entree in ram.entrees_reelles],
            [IDENTIFIANT, IDENTIFIANT_ANCIEN],
        )
        self.assertEqual(
            [entree.execution for entree in ram.entrees_simulees],
            [IDENTIFIANT_QUATRIEME, IDENTIFIANT_TIERS],
        )

    def test_synthetique_seul_n_est_pas_une_mesure_simulee(self) -> None:
        self.ecrire_essai(IDENTIFIANT, synthetique=True)

        groupe = self.groupe()
        entree = groupe.entrees[0]

        self.assertIn(MARQUE_SYNTHETIQUE, entree.marques)
        self.assertNotIn(MARQUE_FACTICE, entree.marques)
        self.assertFalse(entree.simule)
        self.assertEqual(groupe.entrees_simulees, ())
        self.assertEqual([e.execution for e in groupe.entrees_reelles], [IDENTIFIANT])

    def test_reglages_distinctifs_par_valeurs_brutes(self) -> None:
        # Les deux valeurs s'affichent « [0] » : seule la valeur brute, une
        # liste contre la chaîne qui la représente, révèle la différence.
        self.ecrire_essai(
            IDENTIFIANT_ANCIEN, reglages={"langue": "fr", "temperature": [0]}
        )
        self.ecrire_essai(
            IDENTIFIANT, reglages={"langue": "fr", "temperature": "[0]"}
        )

        groupe = self.groupe()

        for entree in groupe.entrees_reelles:
            libelles = [libelle for libelle, _valeur in entree.reglages_distinctifs]
            # Le réglage commun n'est pas répété ; la valeur brute différente
            # reste distinctive malgré un affichage identique.
            self.assertEqual(libelles, ["Réglage demandé : temperature"])
            self.assertEqual(
                dict(entree.reglages_distinctifs)["Réglage demandé : temperature"],
                "[0]",
            )

    def test_reglage_nul_ou_non_fini_reste_distinctif(self) -> None:
        for gauche, droite in (
            ({"temperature": None}, {}),
            ({"temperature": float("nan")}, {"temperature": float("inf")}),
        ):
            with self.subTest(gauche=gauche, droite=droite):
                self.ecrire_essai(IDENTIFIANT_ANCIEN, reglages=gauche)
                self.ecrire_essai(IDENTIFIANT, reglages=droite)
                ancien = self.entree(IDENTIFIANT_ANCIEN)
                self.assertIn(
                    "Réglage demandé : temperature",
                    dict(ancien.reglages_distinctifs),
                )
                if droite:
                    self.assertIn(
                        "Réglage demandé : temperature",
                        dict(self.entree(IDENTIFIANT).reglages_distinctifs),
                    )
                else:
                    self.assertEqual(self.entree(IDENTIFIANT).reglages_distinctifs, ())

    def test_reglages_distinctifs_calcules_dans_chaque_sous_liste(self) -> None:
        threads_reels = {"demandes": 4, "appliques": None}
        threads_simules = {"demandes": 8, "appliques": None}
        self.ecrire_essai(IDENTIFIANT_ANCIEN, threads=threads_reels)
        self.ecrire_essai(IDENTIFIANT, threads=threads_reels)
        self.ecrire_essai(IDENTIFIANT_TIERS, simule=True, threads=threads_simules)
        self.ecrire_essai(IDENTIFIANT_QUATRIEME, simule=True, threads=threads_simules)

        groupe = self.groupe()

        # Les threads sont communs dans chaque sous-liste : ils ne sont pas
        # déclarés distinctifs à cause de l'autre sous-liste.
        for entree in groupe.entrees:
            libelles = [libelle for libelle, _valeur in entree.reglages_distinctifs]
            self.assertNotIn("Threads demandés", libelles)
            self.assertEqual(libelles, [])

    def test_entree_seule_montre_tous_ses_reglages_consignes(self) -> None:
        self.ecrire_essai(IDENTIFIANT)

        entree = self.groupe().entrees[0]

        self.assertEqual(entree.reglages_distinctifs, entree.reglages)
        libelles = [libelle for libelle, _valeur in entree.reglages_distinctifs]
        self.assertIn("Famille", libelles)
        self.assertIn("Threads demandés", libelles)
        self.assertIn("Langue imposée", libelles)
        self.assertIn("Réglage demandé : langue", libelles)

    def test_aucun_dedoublonnage_des_essais_identiques(self) -> None:
        self.ecrire_essai(IDENTIFIANT_ANCIEN)
        self.ecrire_essai(IDENTIFIANT)

        groupe = self.groupe()

        # Deux essais identiques restent deux lignes : aucun représentant
        # n'est choisi silencieusement, et tout leur est commun.
        self.assertEqual(len(groupe.entrees_reelles), 2)
        self.assertEqual(
            {entree.execution for entree in groupe.entrees_reelles},
            {IDENTIFIANT, IDENTIFIANT_ANCIEN},
        )
        for entree in groupe.entrees_reelles:
            self.assertEqual(entree.reglages_distinctifs, ())

    def test_valeur_distinction_exclut_mesures_simulees_et_partielles(self) -> None:
        mesures = {
            "duree_transcription_s": 2.0,
            "temps_cpu_s": 1.0,
            "pic_memoire_octets": 500,
        }
        self.ecrire_essai(IDENTIFIANT, mesures=mesures)
        self.ecrire_essai(IDENTIFIANT_ANCIEN, simule=True, mesures=mesures)
        self.ecrire_essai(
            IDENTIFIANT_TIERS, etat=ETAT_INTERROMPUE, mesures=mesures
        )

        reel = self.entree(IDENTIFIANT)
        simulation = self.entree(IDENTIFIANT_ANCIEN)
        partiel = self.entree(IDENTIFIANT_TIERS)

        self.assertFalse(reel.simule)
        self.assertFalse(reel.partiel)
        self.assertEqual(valeur_distinction(reel, TRI_TEMPS), 2.0)
        self.assertEqual(valeur_distinction(reel, TRI_RAM), 500.0)
        # 100 × 1 s CPU / (2 s × 8 processeurs logiques) = 6,25 %.
        self.assertEqual(valeur_distinction(reel, TRI_CPU), 6.25)

        for exclue in (simulation, partiel):
            with self.subTest(entree=exclue.execution):
                self.assertIsNone(valeur_distinction(exclue, TRI_TEMPS))
                self.assertIsNone(valeur_distinction(exclue, TRI_RAM))
                self.assertIsNone(valeur_distinction(exclue, TRI_CPU))

        with self.assertRaises(ValeurRefusee):
            valeur_distinction(reel, TRI_RECENT)
        with self.assertRaises(ValeurRefusee):
            valeur_distinction(reel, "inconnu")


class ClassementTest(SocleConsultationTest):
    """Critère de tri borné des listes de résultats (tâche 2.1)."""

    def test_analyser_tri_defaut_et_criteres_connus(self) -> None:
        self.assertEqual(TRI_DEFAUT, TRI_TEMPS)
        self.assertEqual(analyser_tri(()), TRI_DEFAUT)
        for critere in (TRI_TEMPS, TRI_RAM, TRI_CPU, TRI_RECENT):
            with self.subTest(critere=critere):
                self.assertEqual(analyser_tri([critere]), critere)
                self.assertEqual(analyser_tri(critere), critere)

    def test_analyser_tri_refuse_duplique_vide_ou_inconnu(self) -> None:
        for valeurs in (
            [TRI_CPU, TRI_RAM],
            [TRI_CPU, TRI_CPU],
            ["inconnu"],
            [""],
            ["Temps"],
        ):
            with self.subTest(valeurs=valeurs):
                with self.assertRaises(ValeurRefusee):
                    analyser_tri(valeurs)

    def test_groupes_refusent_un_critere_inconnu(self) -> None:
        with self.assertRaises(ValeurRefusee):
            self.service.groupes_par_empreinte("inconnu")


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

    def test_colonnes_portent_mesures_et_materiel_consignes(self) -> None:
        self.deux_executions(
            mesures_audio_a={"duree_transcription_s": 3.0},
            mesures_audio_b={"duree_transcription_s": 9.0},
        )

        vue = self.comparer()

        self.assertEqual(vue.colonnes[0].mesures.duree_transcription_s, 3.0)
        self.assertEqual(vue.colonnes[1].mesures.duree_transcription_s, 9.0)
        self.assertEqual(vue.colonnes[0].date_essai, "2024-01-02T03:04:05+00:00")
        self.assertEqual(vue.colonnes[0].materiel.coeurs_logiques, 8)
        self.assertEqual(vue.colonnes[0].etat, ETAT_TERMINEE)

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
