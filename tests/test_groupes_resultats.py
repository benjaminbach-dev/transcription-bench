"""Page Résultats groupée par audio (tâche 1.4), sans moteur ni réseau.

Services, mapping et pages sont testés sur des JSON synthétiques écrits dans un
dossier temporaire. Aucune donnée personnelle, aucun modèle réel, aucune écriture
autre que ces fixtures.
"""

from __future__ import annotations

import html
import unittest
from pathlib import Path

from tests.test_consultation_resultats import (
    SocleConsultationTest,
    ecrire_execution,
    result_json,
    run_json,
)
from tests.test_web import SocleWebTest
from transcription_bench.consultation_resultats import (
    EntreeEmpreinte,
    TRI_RAM,
    TRI_RECENT,
    TRI_TEMPS,
    analyser_tri,
)
from transcription_bench.paths import ValeurRefusee
from transcription_bench.resultats import (
    ETAT_ECHOUEE,
    ETAT_INTERROMPUE,
    ETAT_TERMINEE,
    STATUT_ERREUR,
    STATUT_OK,
)
from transcription_bench.web.vues_resultats import etats_ligne, vue_ligne

EMPREINTE_A = "a" * 64
EMPREINTE_B = "b" * 64
EMPREINTE_C = "c" * 64
ID_ANCIEN = "20240101-010101-00000001"
ID_MILIEU = "20240102-010101-00000002"
ID_RECENT = "20240103-010101-00000003"
ID_AUTRE = "20240104-010101-00000004"


def ecrire_essai(
    donnees: Path,
    identifiant: str,
    *,
    cree_le: str,
    empreinte: str = EMPREINTE_A,
    nom: str = "entretien.wav",
    duree: float | None = 2.0,
    temps: float = 1.0,
    pic: int = 2048,
    modele: str = "organisation/modele-a",
    gguf: str | None = None,
    etat: str = ETAT_TERMINEE,
    simule: bool = False,
    ram_totale: int | None = None,
    revision: str | None = None,
) -> None:
    """Écrit une exécution d'un audio, avec ses marques et son matériel explicites."""
    run = run_json(
        identifiant,
        audios=((nom, STATUT_OK),),
        etat=etat,
        cree_le=cree_le,
        factice=simule,
        synthetique=False,
        mesures_simulees=simule,
    )
    run["demande"]["modele"]["identifiant"] = modele
    run["demande"]["modele"]["fichier_gguf"] = gguf
    if ram_totale is not None:
        run["machine"]["ram_totale_octets"] = ram_totale
    resultats = []
    for plan in run["audios"]:
        resultat = result_json(
            plan,
            execution=identifiant,
            duree_decodee=duree,
            duree_transcription=temps,
            mesures_extra={"pic_memoire_octets": pic},
            factice=simule,
            synthetique=False,
            mesures_simulees=simule,
        )
        resultat["audio"]["empreinte_sha256"] = empreinte
        resultat["modele"] = {
            "identifiant": modele,
            "commit": revision,
            "fichier_gguf": gguf,
            "famille": "factice",
        }
        resultats.append(resultat)
    ecrire_execution(donnees, run, tuple(resultats))


class GroupesServiceTest(SocleConsultationTest):
    """Groupes par empreinte, tri commun, durées et mentions de matériel."""

    def test_meme_nom_empreintes_differentes_forment_deux_groupes(self) -> None:
        ecrire_essai(self.donnees, ID_ANCIEN, cree_le="2024-01-01T01:01:01+00:00", empreinte=EMPREINTE_A)
        ecrire_essai(self.donnees, ID_RECENT, cree_le="2024-01-03T01:01:01+00:00", empreinte=EMPREINTE_B)

        groupes = self.service.groupes_par_empreinte()

        self.assertEqual([g.empreinte for g in groupes], [EMPREINTE_B, EMPREINTE_A])
        self.assertEqual([g.noms for g in groupes], [("entretien.wav",), ("entretien.wav",)])

    def test_essais_du_meme_audio_conserves_sans_dedoublonnage(self) -> None:
        for identifiant, cree_le in (
            (ID_ANCIEN, "2024-01-01T01:01:01+00:00"),
            (ID_MILIEU, "2024-01-02T01:01:01+00:00"),
            (ID_RECENT, "2024-01-03T01:01:01+00:00"),
        ):
            ecrire_essai(self.donnees, identifiant, cree_le=cree_le)

        (groupe,) = self.service.groupes_par_empreinte()

        self.assertEqual(len(groupe.entrees), 3)
        self.assertEqual(
            [entree.execution for entree in groupe.entrees],
            [ID_RECENT, ID_MILIEU, ID_ANCIEN],
        )

    def test_groupes_ordonnes_par_essai_recent_quel_que_soit_le_tri(self) -> None:
        # Le groupe A a le temps le plus court mais l'essai le plus ancien.
        ecrire_essai(self.donnees, ID_ANCIEN, cree_le="2024-01-01T01:01:01+00:00", empreinte=EMPREINTE_A, temps=0.5)
        ecrire_essai(self.donnees, ID_RECENT, cree_le="2024-01-03T01:01:01+00:00", empreinte=EMPREINTE_B, temps=9.0)

        for tri in (TRI_TEMPS, TRI_RAM, TRI_RECENT):
            with self.subTest(tri=tri):
                groupes = self.service.groupes_par_empreinte(tri)
                self.assertEqual(
                    [g.empreinte for g in groupes], [EMPREINTE_B, EMPREINTE_A]
                )

    def test_tri_interne_recent_par_defaut_et_egalites_stables(self) -> None:
        ecrire_essai(self.donnees, ID_ANCIEN, cree_le="2024-01-01T01:01:01+00:00", temps=5.0)
        ecrire_essai(self.donnees, ID_MILIEU, cree_le="2024-01-02T01:01:01+00:00", temps=1.0)
        ecrire_essai(self.donnees, ID_RECENT, cree_le="2024-01-03T01:01:01+00:00", temps=1.0)

        recent = self.service.groupes_par_empreinte(TRI_RECENT)[0].entrees
        temps = self.service.groupes_par_empreinte(TRI_TEMPS)[0].entrees

        self.assertEqual(
            [e.execution for e in recent], [ID_RECENT, ID_MILIEU, ID_ANCIEN]
        )
        # Égalité de temps (1,0 s) : date décroissante ; puis le plus lent.
        self.assertEqual(
            [e.execution for e in temps], [ID_RECENT, ID_MILIEU, ID_ANCIEN]
        )

    def test_factices_separes_apres_les_resultats_observes(self) -> None:
        ecrire_essai(self.donnees, ID_ANCIEN, cree_le="2024-01-01T01:01:01+00:00", simule=True, temps=0.1)
        ecrire_essai(self.donnees, ID_RECENT, cree_le="2024-01-03T01:01:01+00:00", simule=False, temps=9.0)

        (groupe,) = self.service.groupes_par_empreinte()

        self.assertEqual([e.execution for e in groupe.entrees_reelles], [ID_RECENT])
        self.assertEqual([e.execution for e in groupe.entrees_simulees], [ID_ANCIEN])
        self.assertEqual([e.execution for e in groupe.entrees], [ID_RECENT, ID_ANCIEN])

    def test_durees_divergentes_sans_duree_commune(self) -> None:
        ecrire_essai(self.donnees, ID_ANCIEN, cree_le="2024-01-01T01:01:01+00:00", duree=2.0)
        ecrire_essai(self.donnees, ID_RECENT, cree_le="2024-01-03T01:01:01+00:00", duree=3.0)

        (groupe,) = self.service.groupes_par_empreinte()

        self.assertTrue(groupe.durees_divergentes)
        self.assertIsNone(groupe.duree_decodee_commune_s)
        self.assertEqual(
            {e.execution: e.duree_decodee_s for e in groupe.entrees},
            {ID_ANCIEN: 2.0, ID_RECENT: 3.0},
        )

    def test_duree_commune_seulement_si_identique(self) -> None:
        ecrire_essai(self.donnees, ID_ANCIEN, cree_le="2024-01-01T01:01:01+00:00", duree=2.0)
        ecrire_essai(self.donnees, ID_RECENT, cree_le="2024-01-03T01:01:01+00:00", duree=2.0)

        (groupe,) = self.service.groupes_par_empreinte()

        self.assertFalse(groupe.durees_divergentes)
        self.assertEqual(groupe.duree_decodee_commune_s, 2.0)

    def test_variante_et_materiel_compares_entre_essais_du_meme_audio(self) -> None:
        ecrire_essai(self.donnees, ID_ANCIEN, cree_le="2024-01-01T01:01:01+00:00", gguf="modele-q4.gguf", ram_totale=8 * 1024**3)
        ecrire_essai(self.donnees, ID_RECENT, cree_le="2024-01-03T01:01:01+00:00", gguf="modele-q8.gguf", ram_totale=16 * 1024**3)

        (groupe,) = self.service.groupes_par_empreinte()
        par_essai = {e.execution: e for e in groupe.entrees}

        self.assertEqual(par_essai[ID_ANCIEN].variante, "modele-q4.gguf")
        self.assertEqual(par_essai[ID_RECENT].variante, "modele-q8.gguf")
        self.assertIn("RAM totale", par_essai[ID_ANCIEN].materiel_alerte or "")

    def test_annotation_ram_pour_un_audio_suivant_seulement(self) -> None:
        ecrire_essai(self.donnees, ID_ANCIEN, cree_le="2024-01-01T01:01:01+00:00")
        (groupe,) = self.service.groupes_par_empreinte()
        entree = groupe.entrees[0]

        self.assertIsNone(entree.annotation_ram)  # premier audio de la demande
        self.assertIsNotNone(entree.indicateurs)

    def test_modele_supprime_reste_lisible_sans_inventaire(self) -> None:
        # Aucun modèle n'est installé dans ce dossier : l'essai reste lisible.
        ecrire_essai(self.donnees, ID_ANCIEN, cree_le="2024-01-01T01:01:01+00:00", modele="organisation/modele-supprime", etat=ETAT_INTERROMPUE)

        (groupe,) = self.service.groupes_par_empreinte()
        ligne = vue_ligne(groupe.entrees[0], lambda identifiant: f"/r/{identifiant}", False)

        self.assertEqual(ligne["modele"], "modele-supprime")
        self.assertEqual(ligne["etats"], ["interrompue"])

    def test_analyser_tri_defaut_explicite_et_refus(self) -> None:
        self.assertEqual(analyser_tri((), defaut=TRI_RECENT), TRI_RECENT)
        self.assertEqual(analyser_tri(()), TRI_TEMPS)
        with self.assertRaises(ValeurRefusee):
            analyser_tri((TRI_TEMPS, TRI_RAM))


class VueLigneTest(unittest.TestCase):
    def test_etats_ne_listent_que_les_ecarts_et_marques(self) -> None:
        entree = EntreeEmpreinte(
            execution=ID_RECENT,
            ordre=1,
            nom="a.wav",
            empreinte=EMPREINTE_A,
            statut=STATUT_OK,
            libelle_statut="transcrit",
            libelle_etat="terminée",
            partiel=False,
            marques=(),
            modele="m",
            moteur="moteur",
            etat=ETAT_TERMINEE,
        )
        self.assertEqual(etats_ligne(entree), [])

    def test_le_statut_porte_son_sujet_avant_l_etat(self) -> None:
        # « audio : erreur » suivi de « en échec » se lit sans ambiguïté ; les
        # deux badges nus (« erreur en échec ») formaient une fausse phrase.
        entree = EntreeEmpreinte(
            execution=ID_RECENT,
            ordre=1,
            nom="a.wav",
            empreinte=EMPREINTE_A,
            statut=STATUT_ERREUR,
            libelle_statut="erreur",
            libelle_etat="en échec",
            partiel=True,
            marques=("FACTICE",),
            modele="m",
            moteur="moteur",
            etat=ETAT_ECHOUEE,
        )

        self.assertEqual(
            etats_ligne(entree), ["audio : erreur", "en échec", "FACTICE"]
        )


class PageResultatsTest(SocleWebTest):
    """Rendu de la page : groupes, tri, durées, factices et historique secondaire."""

    def page(self, chemin: str = "/resultats") -> str:
        reponse = self.client.get(chemin, base_url=self.base_url())
        self.assertEqual(reponse.status_code, 200)
        corps = reponse.get_data(as_text=True)
        self.verifier_html_seul(corps)
        return html.unescape(corps)

    def historique(self) -> str:
        """Historique technique complet, désormais tenu par Exécutions (3.1)."""
        return self.page("/executions")

    def test_groupes_recents_d_abord_et_tri_par_defaut_recent(self) -> None:
        ecrire_essai(self.dossier_data, ID_ANCIEN, cree_le="2024-01-01T01:01:01+00:00", empreinte=EMPREINTE_A, nom="ancien.wav", temps=0.5)
        ecrire_essai(self.dossier_data, ID_RECENT, cree_le="2024-01-03T01:01:01+00:00", empreinte=EMPREINTE_B, nom="recent.wav", temps=9.0)

        corps = self.page()

        self.assertLess(corps.index("recent.wav"), corps.index("ancien.wav"))
        self.assertIn('href="/resultats?tri=ram"', corps)
        self.assertIn("<strong>Plus récents</strong>", corps)

    def test_tri_explicite_ordonne_dans_chaque_groupe_et_refus_invalide(self) -> None:
        ecrire_essai(self.dossier_data, ID_ANCIEN, cree_le="2024-01-01T01:01:01+00:00", temps=9.0)
        ecrire_essai(self.dossier_data, ID_RECENT, cree_le="2024-01-03T01:01:01+00:00", temps=1.0)

        corps = self.page("/resultats?tri=temps")
        self.assertLess(corps.index(ID_RECENT), corps.index(ID_ANCIEN))
        self.assertIn("<strong>Plus rapides</strong>", corps)

        for chemin in ("/resultats?tri=inconnu", "/resultats?tri=temps&tri=ram"):
            with self.subTest(chemin=chemin):
                reponse = self.client.get(chemin, base_url=self.base_url())
                self.assertEqual(reponse.status_code, 400)

    def test_meme_nom_empreintes_differentes_desambiguisees(self) -> None:
        ecrire_essai(self.dossier_data, ID_ANCIEN, cree_le="2024-01-01T01:01:01+00:00", empreinte=EMPREINTE_A)
        ecrire_essai(self.dossier_data, ID_RECENT, cree_le="2024-01-03T01:01:01+00:00", empreinte=EMPREINTE_B)

        corps = self.page()

        self.assertEqual(corps.count('<h2 class="resultat-audio">entretien.wav</h2>'), 2)
        self.assertIn("Empreinte aaaaaaaa", corps)
        self.assertIn("Empreinte bbbbbbbb", corps)

    def test_durees_divergentes_affichees_par_essai(self) -> None:
        ecrire_essai(self.dossier_data, ID_ANCIEN, cree_le="2024-01-01T01:01:01+00:00", duree=2.0)
        ecrire_essai(self.dossier_data, ID_RECENT, cree_le="2024-01-03T01:01:01+00:00", duree=3.0)

        corps = self.page()

        self.assertIn("Durée non commune aux essais", corps)
        self.assertIn("Audio : 2 s", corps)
        self.assertIn("Audio : 3 s", corps)

    def test_identite_complete_apres_les_valeurs_et_historique_accessible(self) -> None:
        ecrire_essai(self.dossier_data, ID_RECENT, cree_le="2024-01-03T01:01:01+00:00")
        corps = self.page()
        self.assertLess(corps.index("Transcription</span>"), corps.index("Empreinte SHA-256 complète"))
        # L'historique complet a quitté la page : un lien secondaire y mène.
        self.assertIn('href="/executions#historique"', corps)
        self.assertNotIn("Historique complet des exécutions", corps)
        self.assertIn(
            'tabindex="0" role="region" aria-label="Historique des exécutions"',
            self.historique(),
        )

    def test_variantes_proches_et_etats_visibles_dans_la_ligne(self) -> None:
        ecrire_essai(self.dossier_data, ID_ANCIEN, cree_le="2024-01-01T01:01:01+00:00", gguf="modele-q4.gguf", etat=ETAT_INTERROMPUE)
        ecrire_essai(self.dossier_data, ID_RECENT, cree_le="2024-01-03T01:01:01+00:00", gguf="modele-q8.gguf")

        corps = self.page()

        self.assertIn("Variante : modele-q4.gguf", corps)
        self.assertIn("Variante : modele-q8.gguf", corps)
        self.assertIn('<span class="resultat-etat">interrompue</span>', corps)

    def test_factices_dans_une_sous_partie_separee(self) -> None:
        ecrire_essai(self.dossier_data, ID_ANCIEN, cree_le="2024-01-01T01:01:01+00:00", simule=True)
        ecrire_essai(self.dossier_data, ID_RECENT, cree_le="2024-01-03T01:01:01+00:00", simule=False)

        corps = self.page()

        self.assertIn("Mesures simulées de cet audio", corps)
        self.assertLess(corps.index(ID_RECENT), corps.index("Mesures simulées de cet audio"))
        self.assertIn("FACTICE", corps)

    def test_revisions_distinctes_affichees_entre_essais_indiscernables(self) -> None:
        ecrire_essai(self.dossier_data, ID_ANCIEN, cree_le="2024-01-01T01:01:01+00:00", revision="abcdef1234567")
        ecrire_essai(self.dossier_data, ID_RECENT, cree_le="2024-01-03T01:01:01+00:00", revision="9876543210fed")

        corps = self.page()

        self.assertIn("Révision : abcdef1", corps)
        self.assertIn("Révision : 9876543", corps)

    def test_revision_absente_gardee_sans_valeur_inventee(self) -> None:
        ecrire_essai(self.dossier_data, ID_ANCIEN, cree_le="2024-01-01T01:01:01+00:00", revision=None)
        ecrire_essai(self.dossier_data, ID_RECENT, cree_le="2024-01-03T01:01:01+00:00", revision="abcdef1234567")

        corps = self.page()

        self.assertIn("Révision : non consignée", corps)
        self.assertIn("Révision : abcdef1", corps)
        self.assertNotIn("None", corps)

    def test_revisions_au_meme_prefixe_restent_distinctes(self) -> None:
        for identifiant, revision in (
            (ID_ANCIEN, "abcdef10"), (ID_RECENT, "abcdef11")
        ):
            ecrire_essai(
                self.dossier_data, identifiant,
                cree_le="2024-01-03T01:01:01+00:00", revision=revision,
            )
        corps = self.client.get("/resultats", base_url=self.base_url()).get_data(as_text=True)
        self.assertIn("Révision : abcdef10", corps)
        self.assertIn("Révision : abcdef11", corps)

    def test_revision_identique_non_repetee_dans_les_lignes(self) -> None:
        for identifiant in (ID_ANCIEN, ID_RECENT):
            ecrire_essai(
                self.dossier_data, identifiant,
                cree_le="2024-01-03T01:01:01+00:00", revision="abcdef1234567",
            )
        corps = self.client.get("/resultats", base_url=self.base_url()).get_data(as_text=True)
        self.assertNotIn("Révision :", corps)

    def test_revision_non_affichee_sans_collision(self) -> None:
        ecrire_essai(self.dossier_data, ID_RECENT, cree_le="2024-01-03T01:01:01+00:00", revision="abcdef1234567")

        corps = self.page()

        self.assertNotIn("Révision :", corps)

    def test_nom_court_et_homonymes_gardent_leur_identifiant(self) -> None:
        ecrire_essai(self.dossier_data, ID_ANCIEN, cree_le="2024-01-01T01:01:01+00:00", modele="organisation/modele-a")
        ecrire_essai(self.dossier_data, ID_RECENT, cree_le="2024-01-03T01:01:01+00:00", modele="autre/modele-a", empreinte=EMPREINTE_A)

        corps = self.page()
        groupes = corps

        self.assertIn("organisation/modele-a", groupes)
        self.assertIn("autre/modele-a", groupes)

    def test_nom_court_sans_organisation_si_pas_d_homonyme(self) -> None:
        ecrire_essai(self.dossier_data, ID_RECENT, cree_le="2024-01-03T01:01:01+00:00", modele="organisation/modele-a")

        corps = self.page()
        groupes = corps

        self.assertIn('class="resultat-modele" href=', groupes)
        self.assertIn(">modele-a</a>", groupes)
        self.assertNotIn("organisation/", groupes)

    def test_prefixe_empreinte_s_allonge_si_huit_caracteres_se_repetent(self) -> None:
        ecrire_essai(self.dossier_data, ID_ANCIEN, cree_le="2024-01-01T01:01:01+00:00", empreinte="a" * 8 + "0" * 56)
        ecrire_essai(self.dossier_data, ID_RECENT, cree_le="2024-01-03T01:01:01+00:00", empreinte="a" * 8 + "1" * 56)

        corps = self.page()

        self.assertIn("Empreinte " + "a" * 8 + "0<", corps)
        self.assertIn("Empreinte " + "a" * 8 + "1<", corps)

    def test_dossier_des_resultats_dans_l_historique_secondaire(self) -> None:
        corps = self.page()
        historique = self.historique()

        self.assertIn("Dossier des résultats", historique)
        self.assertLess(
            historique.index("Historique complet"),
            historique.index("Dossier des résultats"),
        )
        self.assertNotIn("Dossier des résultats", corps)

    def test_modele_supprime_et_historique_complet_dans_un_detail(self) -> None:
        ecrire_essai(self.dossier_data, ID_ANCIEN, cree_le="2024-01-01T01:01:01+00:00", modele="organisation/modele-supprime", etat=ETAT_INTERROMPUE)
        ecrire_essai(self.dossier_data, ID_RECENT, cree_le="2024-01-03T01:01:01+00:00")
        ancien_non_interpretable = self.dossier_data / "results" / ID_AUTRE
        ancien_non_interpretable.mkdir(parents=True)
        (ancien_non_interpretable / "run.json").write_text("{ pas du json", encoding="utf-8")

        corps = self.page()

        # Le nom court reste lisible dans la liste, même sans modèle local.
        self.assertIn("modele-supprime", corps)
        self.assertIn(f'href="/resultats/{ID_ANCIEN}#audio-1"', corps)
        self.assertNotIn("<table", corps)
        self.assertNotIn(ID_AUTRE, corps, "pas d'entrée illisible dans Résultats")
        # L'historique complet, y compris l'entrée illisible et l'identité
        # complète d'un modèle supprimé, reste tenu par Exécutions sans perte.
        historique = self.historique()
        historique = historique[historique.index("Historique complet des exécutions") :]
        self.assertIn("organisation/modele-supprime", historique)
        self.assertIn(ID_AUTRE, historique)
        self.assertIn("non interprétable", historique)
        self.assertIn(ID_ANCIEN, historique)


if __name__ == "__main__":
    unittest.main()
