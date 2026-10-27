"""Tests des pages de comparaison (tâche 7.2), sans moteur ni réseau.

Les fixtures viennent de `tests.test_consultation_resultats` et de
`tests.test_comparaison_resultats` : elles écrivent des `run.json` et
`result.json` synthétiques dans le dossier temporaire du `SocleWebTest`. Les
pages sont en lecture seule : aucune requête GET ne doit créer ni modifier un
fichier.
"""

from __future__ import annotations

import html

from tests.test_comparaison_resultats import (
    EMPREINTE_A,
    EMPREINTE_B,
    resultat_empreinte,
)
from tests.test_consultation_resultats import (
    IDENTIFIANT,
    IDENTIFIANT_ANCIEN,
    ecrire_execution,
    result_json,
    run_json,
)
from tests.test_web import SocleWebTest
from transcription_bench.resultats import (
    ETAT_INTERROMPUE,
    STATUT_ERREUR,
    STATUT_OK,
)
from transcription_bench.web.app import CHAMP_SELECTION_COMPARAISON


class ComparaisonWebTest(SocleWebTest):
    """Groupes par empreinte et comparaison côte à côte."""

    def page(self, chemin: str, **options) -> str:
        options.setdefault("base_url", self.base_url())
        reponse = self.client.get(chemin, **options)
        self.assertEqual(reponse.status_code, 200, chemin)
        corps = reponse.get_data(as_text=True)
        self.verifier_html_seul(corps)
        return html.unescape(corps)

    def ecrire_deux_empreintes(self) -> None:
        """Deux exécutions d'un audio de même nom, mais de contenus différents."""
        ancien = run_json(IDENTIFIANT_ANCIEN)
        recent = run_json(IDENTIFIANT)
        ecrire_execution(
            self.dossier_data,
            ancien,
            (resultat_empreinte(ancien, ancien["audios"][0], EMPREINTE_A),),
        )
        ecrire_execution(
            self.dossier_data,
            recent,
            (resultat_empreinte(recent, recent["audios"][0], EMPREINTE_B),),
        )

    def ecrire_comparables(
        self,
        *,
        effectifs_a=None,
        effectifs_b=None,
        demandes_a=None,
        demandes_b=None,
        etat_b: str = "completed",
        statut_b: str = STATUT_OK,
        nom_b: str = "a.wav",
        texte_a: str | None = "transcription simulée de test",
        texte_b: str | None = "transcription simulée de test",
        mesures_audio_a: dict | None = None,
        mesures_audio_b: dict | None = None,
    ) -> None:
        premier = run_json(IDENTIFIANT)
        second = run_json(IDENTIFIANT_ANCIEN, etat=etat_b, audios=((nom_b, STATUT_OK),))
        options_a: dict = {
            "reglages_effectifs": effectifs_a,
            "texte": texte_a,
            "mesures_extra": mesures_audio_a,
        }
        options_b: dict = {
            "reglages_effectifs": effectifs_b,
            "texte": texte_b,
            "mesures_extra": mesures_audio_b,
        }
        if demandes_a is not None:
            options_a["reglages"] = demandes_a
        if demandes_b is not None:
            options_b["reglages"] = demandes_b
        ecrire_execution(
            self.dossier_data,
            premier,
            (
                resultat_empreinte(
                    premier,
                    premier["audios"][0],
                    **options_a,
                ),
            ),
        )
        ecrire_execution(
            self.dossier_data,
            second,
            (
                resultat_empreinte(
                    second,
                    second["audios"][0],
                    statut=statut_b,
                    **options_b,
                ),
            ),
        )

    def test_groupes_vide_sans_creation_de_dossier(self) -> None:
        corps = self.page("/resultats/comparaison")

        self.assertIn("Aucune transcription comparable", corps)
        self.assertIn('href="/resultats"', corps)
        self.assertFalse(self.dossier_data.exists())

    def test_page_resultats_renvoie_vers_la_comparaison(self) -> None:
        corps = self.page("/resultats")

        self.assertIn('href="/resultats/comparaison"', corps)
        self.assertNotIn("n'est pas encore disponible", corps)

    def test_meme_nom_empreintes_differentes_presentes_dans_deux_groupes(self) -> None:
        self.ecrire_deux_empreintes()

        corps = self.page("/resultats/comparaison")

        self.assertEqual(corps.count("Empreinte SHA-256"), 2)
        self.assertIn(EMPREINTE_A, corps)
        self.assertIn(EMPREINTE_B, corps)
        # Chaque groupe a son propre formulaire, lié à son empreinte.
        self.assertIn(f'action="/resultats/comparaison/{EMPREINTE_A}"', corps)
        self.assertIn(f'action="/resultats/comparaison/{EMPREINTE_B}"', corps)
        self.assertIn("a.wav", corps)
        self.assertEqual(
            corps.count(f'name="{CHAMP_SELECTION_COMPARAISON}"'),
            2,
        )

    def test_meme_empreinte_noms_differents_reunis_dans_un_groupe(self) -> None:
        self.ecrire_comparables(nom_b="copie.wav")

        corps = self.page("/resultats/comparaison")

        self.assertEqual(corps.count("Empreinte SHA-256"), 1)
        self.assertIn("a.wav, copie.wav", corps)
        self.assertIn(f'value="{IDENTIFIANT}:1"', corps)
        self.assertIn(f'value="{IDENTIFIANT_ANCIEN}:1"', corps)

    def test_comparaison_affiche_differences_reglages_et_mesures(self) -> None:
        self.ecrire_comparables(
            effectifs_a={"langue": "fr", "temperature": [0.0, 0.2]},
            effectifs_b={"langue": "fr", "temperature": [0.0, 0.4]},
        )

        corps = self.page(
            f"/resultats/comparaison/{EMPREINTE_A}",
            query_string=[
                ("transcription", f"{IDENTIFIANT}:1"),
                ("transcription", f"{IDENTIFIANT_ANCIEN}:1"),
            ],
        )

        self.assertIn("<table>", corps)
        self.assertIn("Réglage demandé : langue", corps)
        self.assertIn("Réglage effectif : langue", corps)
        self.assertIn("Réglage effectif : temperature — différent", corps)
        self.assertIn("[0.0,0.2]", corps)
        self.assertIn("[0.0,0.4]", corps)
        self.assertIn("Durée totale de l'opération", corps)
        self.assertIn("12.500 s", corps)
        self.assertIn("RTF (durée de transcription / durée décodée)", corps)
        self.assertIn("FACTICE", corps)
        self.assertIn("État de l'exécution", corps)
        self.assertIn("terminée", corps)
        self.assertIn(f'href="/resultats/{IDENTIFIANT}"', corps)
        self.assertIn(f'href="/resultats/{IDENTIFIANT_ANCIEN}"', corps)
        # Aucun diff de texte ni score de qualité.
        self.assertIn("sans diff textuel", corps)

    def test_comparaison_affiche_les_deux_textes_cote_a_cote(self) -> None:
        self.ecrire_comparables(
            texte_a="Première ligne du texte A.\nDeuxième ligne du texte A.",
            texte_b="Texte B, autre contenu.",
        )

        corps = self.page(
            f"/resultats/comparaison/{EMPREINTE_A}",
            query_string=[
                ("transcription", f"{IDENTIFIANT}:1"),
                ("transcription", f"{IDENTIFIANT_ANCIEN}:1"),
            ],
        )

        self.assertIn("Texte transcrit", corps)
        # Chaque colonne affiche son texte dans un bloc préformaté.
        self.assertEqual(corps.count("<pre>"), 2)
        self.assertIn(
            "<pre>Première ligne du texte A.\nDeuxième ligne du texte A.</pre>",
            corps,
        )
        self.assertIn("<pre>Texte B, autre contenu.</pre>", corps)
        # La ligne de texte n'est jamais marquée « différent » : aucun diff.
        debut = corps.index("Texte transcrit")
        ligne_texte = corps[corps.rfind("<tr>", 0, debut) : corps.index("</tr>", debut)]
        self.assertNotIn("différent", ligne_texte)

    def test_comparaison_echappe_le_texte_transcrit(self) -> None:
        texte_piege = "<script>alert('x')</script> & <b>gras</b>\nseconde ligne"
        self.ecrire_comparables(texte_a=texte_piege, texte_b="texte de contrôle")

        reponse = self.client.get(
            f"/resultats/comparaison/{EMPREINTE_A}",
            query_string=[
                ("transcription", f"{IDENTIFIANT}:1"),
                ("transcription", f"{IDENTIFIANT_ANCIEN}:1"),
            ],
            base_url=self.base_url(),
        )
        corps_brut = reponse.get_data(as_text=True)

        self.assertEqual(reponse.status_code, 200)
        self.verifier_html_seul(corps_brut)
        self.assertIn(
            "<pre>&lt;script&gt;alert(&#39;x&#39;)&lt;/script&gt;", corps_brut
        )
        self.assertIn("&amp; &lt;b&gt;gras&lt;/b&gt;\nseconde ligne</pre>", corps_brut)
        self.assertNotIn("<script>alert", corps_brut)
        self.assertNotIn("<b>gras</b>", corps_brut)

    def test_comparaison_rtf_affiche_repere_non_bloquant(self) -> None:
        # RTF de 1.5 et 0.5 sur 2 s décodées ; repère 2 affiché sans blocage.
        self.ecrire_comparables(
            mesures_audio_a={"duree_transcription_s": 3.0},
            mesures_audio_b={"duree_transcription_s": 1.0},
        )

        corps = self.page(
            f"/resultats/comparaison/{EMPREINTE_A}",
            query_string=[
                ("transcription", f"{IDENTIFIANT}:1"),
                ("transcription", f"{IDENTIFIANT_ANCIEN}:1"),
            ],
        )

        self.assertIn("1.500 (repère d'objectif 2, non bloquant)", corps)
        self.assertIn("0.500 (repère d'objectif 2, non bloquant)", corps)
        self.assertIn("n'exclut aucune transcription", corps)
        self.assertIn("transcrit", corps)

    def test_comparaison_signale_partiel_et_marques_absentes(self) -> None:
        premier = run_json(IDENTIFIANT)
        second = run_json(IDENTIFIANT_ANCIEN, etat=ETAT_INTERROMPUE)
        second["factice"] = False
        second["synthetique"] = False
        second["mesures_simulees"] = False
        resultat_sans_marque = resultat_empreinte(
            second, second["audios"][0]
        )
        resultat_sans_marque["factice"] = False
        resultat_sans_marque["synthetique"] = False
        resultat_sans_marque["mesures_simulees"] = False
        ecrire_execution(
            self.dossier_data,
            premier,
            (resultat_empreinte(premier, premier["audios"][0]),),
        )
        ecrire_execution(self.dossier_data, second, (resultat_sans_marque,))

        corps = self.page(
            f"/resultats/comparaison/{EMPREINTE_A}",
            query_string=[
                ("transcription", f"{IDENTIFIANT}:1"),
                ("transcription", f"{IDENTIFIANT_ANCIEN}:1"),
            ],
        )

        self.assertIn("Résultats partiels", corps)
        self.assertIn("Marques", corps)
        self.assertIn("aucune", corps)
        self.assertIn("au moins une transcription vient du moteur factice", corps)

    def test_comparaison_affiche_reglages_demandes_pour_audio_en_erreur(self) -> None:
        self.ecrire_comparables(
            statut_b=STATUT_ERREUR,
            demandes_a={"temperature": 0.0, "beam_size": 5},
            demandes_b={"temperature": 0.4, "beam_size": 5},
        )

        corps = self.page(
            f"/resultats/comparaison/{EMPREINTE_A}",
            query_string=[
                ("transcription", f"{IDENTIFIANT}:1"),
                ("transcription", f"{IDENTIFIANT_ANCIEN}:1"),
            ],
        )

        self.assertIn("Réglage demandé : temperature — différent", corps)
        self.assertIn("Réglage demandé : beam_size", corps)
        self.assertIn("erreur", corps)
        self.assertNotIn("Réglage effectif :", corps)

    def test_comparaison_refuse_melange_d_empreintes(self) -> None:
        self.ecrire_deux_empreintes()

        reponse = self.client.get(
            f"/resultats/comparaison/{EMPREINTE_A}",
            query_string=[
                ("transcription", f"{IDENTIFIANT}:1"),
                ("transcription", f"{IDENTIFIANT_ANCIEN}:1"),
            ],
            base_url=self.base_url(),
        )

        corps = self.verifier_page_erreur(reponse, 400)
        self.assertIn("Comparaison refusée", corps)

    def test_comparaison_refuse_selection_insuffisante(self) -> None:
        self.ecrire_comparables()

        for selections in ([], [("transcription", f"{IDENTIFIANT}:1")]):
            with self.subTest(selections=selections):
                reponse = self.client.get(
                    f"/resultats/comparaison/{EMPREINTE_A}",
                    query_string=selections,
                    base_url=self.base_url(),
                )
                self.verifier_page_erreur(reponse, 400)

    def test_comparaison_refuse_empreinte_invalide(self) -> None:
        self.ecrire_comparables()

        reponse = self.client.get(
            "/resultats/comparaison/pas-une-empreinte",
            query_string=[
                ("transcription", f"{IDENTIFIANT}:1"),
                ("transcription", f"{IDENTIFIANT_ANCIEN}:1"),
            ],
            base_url=self.base_url(),
        )

        self.verifier_page_erreur(reponse, 400)

    def test_comparaison_refuse_selections_hostiles(self) -> None:
        self.ecrire_comparables()

        for hostile in (
            "../../etc/passwd:1",
            "..\\secret:1",
            "C:\\secret:1",
            f"{IDENTIFIANT}:0",
            f"{IDENTIFIANT}:1:2",
            f"{IDENTIFIANT}/../x:1",
        ):
            with self.subTest(selection=hostile):
                reponse = self.client.get(
                    f"/resultats/comparaison/{EMPREINTE_A}",
                    query_string=[
                        ("transcription", hostile),
                        ("transcription", f"{IDENTIFIANT_ANCIEN}:1"),
                    ],
                    base_url=self.base_url(),
                )
                self.verifier_page_erreur(reponse, 400)

    def test_comparaison_transcription_absente_repond_404(self) -> None:
        self.ecrire_comparables()

        reponse = self.client.get(
            f"/resultats/comparaison/{EMPREINTE_A}",
            query_string=[
                ("transcription", f"{IDENTIFIANT}:1"),
                ("transcription", f"{IDENTIFIANT_ANCIEN}:9"),
            ],
            base_url=self.base_url(),
        )

        self.verifier_page_erreur(reponse, 404)

    def test_comparaison_echappe_les_contenus_des_fichiers(self) -> None:
        premier = run_json(IDENTIFIANT, audios=(("<b>prise</b>.wav", STATUT_OK),))
        second = run_json(
            IDENTIFIANT_ANCIEN, audios=(("<b>prise</b>.wav", STATUT_OK),)
        )
        valeur_piege = "<script>alert('x')</script> & <i>italique</i>"
        reglages = {"prompt": valeur_piege, "options": {"a": "<valeur>"}}
        resultat_a = resultat_empreinte(
            premier, premier["audios"][0], reglages_effectifs=reglages
        )
        resultat_a["modele"] = {"famille": "factice", "identifiant": valeur_piege}
        resultat_b = resultat_empreinte(
            second, second["audios"][0], reglages_effectifs={"prompt": "autre"}
        )
        ecrire_execution(self.dossier_data, premier, (resultat_a,))
        ecrire_execution(self.dossier_data, second, (resultat_b,))

        reponse = self.client.get(
            f"/resultats/comparaison/{EMPREINTE_A}",
            query_string=[
                ("transcription", f"{IDENTIFIANT}:1"),
                ("transcription", f"{IDENTIFIANT_ANCIEN}:1"),
            ],
            base_url=self.base_url(),
        )
        corps_brut = reponse.get_data(as_text=True)

        self.assertEqual(reponse.status_code, 200)
        self.verifier_html_seul(corps_brut)
        self.assertIn("&lt;script&gt;", corps_brut)
        self.assertIn("&lt;b&gt;prise&lt;/b&gt;.wav", corps_brut)
        self.assertIn("&lt;i&gt;italique&lt;/i&gt;", corps_brut)
        self.assertIn("{&#34;a&#34;:&#34;&lt;valeur&gt;&#34;}", corps_brut)
        self.assertNotIn("<script>alert", corps_brut)
        self.assertNotIn("<b>prise</b>", corps_brut)

    def test_pages_comparaison_sans_effet_de_bord_en_lecture(self) -> None:
        self.ecrire_comparables(effectifs_a={"a": 1}, effectifs_b={"a": 2})
        racine = self.dossier_data / "results"
        avant = {
            chemin: chemin.read_bytes()
            for chemin in sorted(racine.rglob("*"))
            if chemin.is_file()
        }

        self.page("/resultats/comparaison")
        self.page(
            f"/resultats/comparaison/{EMPREINTE_A}",
            query_string=[
                ("transcription", f"{IDENTIFIANT}:1"),
                ("transcription", f"{IDENTIFIANT_ANCIEN}:1"),
            ],
        )

        apres = {
            chemin: chemin.read_bytes()
            for chemin in sorted(racine.rglob("*"))
            if chemin.is_file()
        }
        self.assertEqual(avant, apres)

    def test_liste_dossier_resultats_illisible_message_fixe(self) -> None:
        self.dossier_data.mkdir(parents=True)
        (self.dossier_data / "results").write_text("pas un dossier", encoding="utf-8")

        corps = self.page("/resultats/comparaison")

        self.assertIn("n'a pas pu être lu", corps)
        self.assertNotIn("Traceback", corps)

    def test_resultat_non_interpretable_refuse_sans_500(self) -> None:
        run = run_json(schema=2)
        ecrire_execution(
            self.dossier_data,
            run,
            (result_json(run["audios"][0]),),
        )
        valide = run_json(IDENTIFIANT_ANCIEN)
        ecrire_execution(
            self.dossier_data,
            valide,
            (resultat_empreinte(valide, valide["audios"][0]),),
        )

        reponse = self.client.get(
            f"/resultats/comparaison/{EMPREINTE_A}",
            query_string=[
                ("transcription", f"{IDENTIFIANT}:1"),
                ("transcription", f"{IDENTIFIANT_ANCIEN}:1"),
            ],
            base_url=self.base_url(),
        )

        self.verifier_page_erreur(reponse, 422)


if __name__ == "__main__":
    unittest.main()
