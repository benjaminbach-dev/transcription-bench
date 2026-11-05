"""Tests des pages de comparaison (tâche 7.2), sans moteur ni réseau.

Les fixtures viennent de `tests.test_consultation_resultats` et de
`tests.test_comparaison_resultats` : elles écrivent des `run.json` et
`result.json` synthétiques dans le dossier temporaire du `SocleWebTest`. Les
pages sont en lecture seule : aucune requête GET ne doit créer ni modifier un
fichier.
"""

from __future__ import annotations

import html
import re

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
from transcription_bench.consultation_resultats import LIBELLES_TRI, TRI_CPU
from transcription_bench.resultats import (
    ETAT_INTERROMPUE,
    ETAT_TERMINEE,
    STATUT_ERREUR,
    STATUT_OK,
)
from transcription_bench.web.app import (
    CHAMP_SELECTION_COMPARAISON,
    CHAMP_TRI_CLASSEMENT,
)


IDENTIFIANT_TIERS = "20240103-040506-55667788"
IDENTIFIANT_QUATRIEME = "20240104-050607-8899aabb"
DATE_ANCIENNE = "2024-01-01T00:00:00+00:00"
DATE_RECENTE = "2024-01-02T00:00:00+00:00"
MOTIF_SELECTION = re.compile(r'name="transcription" value="([^"]+)"')


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
        # Chaque carte affiche son texte intégral dans un bloc préformaté, hors
        # de tout accordéon fermé.
        self.assertEqual(corps.count("<pre>"), 2)
        self.assertIn(
            "<pre>Première ligne du texte A.\nDeuxième ligne du texte A.</pre>",
            corps,
        )
        self.assertIn("<pre>Texte B, autre contenu.</pre>", corps)
        self.assertLess(corps.index("<pre>"), corps.index("<details"))
        # Le texte n'est jamais comparé : aucune carte ne porte « différent ».
        for texte in ("Première ligne du texte A.", "Texte B, autre contenu."):
            fin = corps.index("</article>", corps.index(texte))
            debut = corps.rindex("<article>", 0, corps.index(texte))
            with self.subTest(texte=texte):
                self.assertNotIn("différent", corps[debut:fin])

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
        self.assertIn("transcrit", corps)
        # L'explication du repère est regroupée dans l'aide locale.
        self.assertNotIn("n'exclut aucune transcription", corps)
        aide = self.client.get("/resultats/aide", base_url=self.base_url())
        self.assertEqual(aide.status_code, 200)
        self.assertIn(
            "n'exclut aucune transcription",
            html.unescape(aide.get_data(as_text=True)),
        )

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


class CartesComparaisonWebTest(SocleWebTest):
    """Cartes à trois indicateurs et détails progressifs (tâche 3.1).

    Les données sont synthétiques et écrites dans le dossier temporaire du
    socle : aucune inférence, aucun réseau, aucune écriture dans les fichiers
    lus. Les essais observés ne portent aucune marque de mesures simulées.
    """

    MACHINE = {
        "os": "Linux",
        "version_os": "6.1",
        "architecture": "x86_64",
        "processeur": None,
        "coeurs_physiques": 4,
        "coeurs_logiques": 8,
        "ram_totale_octets": 16_000_000_000,
    }

    def page(self, selections) -> str:
        """Page de comparaison rendue, HTML seul et entités décodées."""
        reponse = self.client.get(
            f"/resultats/comparaison/{EMPREINTE_A}",
            query_string=[
                (CHAMP_SELECTION_COMPARAISON, selection) for selection in selections
            ],
            base_url=self.base_url(),
        )
        self.assertEqual(reponse.status_code, 200, selections)
        corps = reponse.get_data(as_text=True)
        self.verifier_html_seul(corps)
        return html.unescape(corps)

    def ecrire_essai(
        self,
        identifiant: str = IDENTIFIANT,
        *,
        modele: str = "Modèle",
        mesures: dict | None = None,
        reglages: dict | None = None,
        simule: bool = False,
        etat: str = ETAT_TERMINEE,
        audios: int = 1,
        machine: dict | None = None,
    ) -> None:
        """Exécution terminée d'un audio transcrit, observée ou simulée."""
        marques = {
            "factice": simule,
            "synthetique": True,
            "mesures_simulees": simule,
        }
        plans = tuple(
            (f"prise{position}.wav", STATUT_OK) for position in range(1, audios + 1)
        )
        run = run_json(
            identifiant,
            audios=plans,
            machine=self.MACHINE if machine is None else machine,
            etat=etat,
            **marques,
        )
        run["demande"]["modele"]["identifiant"] = modele
        resultats = []
        for plan in run["audios"]:
            options: dict = dict(marques)
            if mesures is not None:
                options["mesures_extra"] = mesures
            if reglages is not None:
                options["reglages"] = reglages
            resultats.append(resultat_empreinte(run, plan, **options))
        ecrire_execution(self.dossier_data, run, tuple(resultats))

    def ecrire_deux_modeles(self) -> None:
        """Deux essais observés du scénario de la spec : 1 min 37 s et 42 s."""
        self.ecrire_essai(
            IDENTIFIANT,
            modele="Modèle A",
            mesures={
                "duree_transcription_s": 97.0,
                "temps_cpu_s": 3.104,
                "pic_memoire_octets": 2_400_000_000,
            },
        )
        self.ecrire_essai(
            IDENTIFIANT_ANCIEN,
            modele="Modèle B",
            mesures={
                "duree_transcription_s": 42.0,
                "temps_cpu_s": 12.6,
                "pic_memoire_octets": 3_200_000_000,
            },
        )

    def test_erreur_comparee_visible_hors_details_et_echappee(self) -> None:
        self.ecrire_essai(IDENTIFIANT, modele="Modèle A")
        run = run_json(IDENTIFIANT_ANCIEN, audios=(("erreur.wav", STATUT_ERREUR),))
        resultat = resultat_empreinte(run, run["audios"][0], statut=STATUT_ERREUR,
                                     texte=None, erreur="Échec <test> & conservé")
        ecrire_execution(self.dossier_data, run, (resultat,))

        corps = self.page([f"{IDENTIFIANT}:1", f"{IDENTIFIANT_ANCIEN}:1"])

        self.assertIn("Erreur consignée pour cet audio : Échec <test> & conservé",
                      corps[:corps.index("<details")])
        brut = self.client.get(
            f"/resultats/comparaison/{EMPREINTE_A}",
            query_string=[("transcription", f"{IDENTIFIANT}:1"),
                          ("transcription", f"{IDENTIFIANT_ANCIEN}:1")],
            base_url=self.base_url(),
        ).get_data(as_text=True)
        self.assertIn("Échec &lt;test&gt; &amp; conservé", brut)

    def test_provenance_complete_consultable_dans_la_comparaison(self) -> None:
        for identifiant, cpu, version in (
            (IDENTIFIANT, "CPU-A", "1.2"),
            (IDENTIFIANT_ANCIEN, "CPU-B", "1.3"),
        ):
            run = run_json(identifiant, machine={**self.MACHINE, "processeur": cpu})
            run["moteur"]["versions"] = {"moteur-test": version}
            run["programme"]["version"] = version
            ecrire_execution(self.dossier_data, run,
                              (resultat_empreinte(run, run["audios"][0]),))

        corps = self.page([f"{IDENTIFIANT}:1", f"{IDENTIFIANT_ANCIEN}:1"])

        details = corps[corps.index("<summary>Toutes les mesures et informations</summary>"):]
        for valeur in ("CPU-A", "CPU-B", "Architecture", "x86_64", "Cœurs logiques",
                       "Versions du moteur", "moteur-test", "1.2", "1.3", "Python",
                       "FFmpeg", "Fichier audio : Empreinte SHA-256", "Segments horodatés",
                       "Timings natifs"):
            self.assertIn(valeur, details)
        differences = corps[corps.index("<summary>Ce qui diffère</summary>"):
                            corps.index("<summary>Toutes les mesures et informations</summary>")]
        self.assertIn("Processeur", differences)
        self.assertIn("CPU-A", differences)
        for libelle in ("PID du moteur", "Lancé à", "Timings natifs", "Segments horodatés"):
            self.assertNotIn(libelle, differences)
        self.assertNotIn("Matériel différent", corps[:corps.index("<details")])

    def test_cartes_trois_indicateurs_avant_le_texte(self) -> None:
        self.ecrire_deux_modeles()

        corps = self.page([f"{IDENTIFIANT}:1", f"{IDENTIFIANT_ANCIEN}:1"])

        self.assertIn('class="grid cols-2"', corps)
        self.assertEqual(corps.count("<article>"), 2)
        self.assertIn("Modèle A · Moteur factice", corps)
        self.assertIn("Modèle B · Moteur factice", corps)
        # Trois indicateurs de premier niveau, formatés en unités lisibles.
        self.assertIn("1 min 37 s", corps)
        self.assertIn("2,4 Go sur 16 Go — 15 %", corps)
        self.assertIn("< 1 % en moyenne", corps)
        self.assertIn("42 s", corps)
        self.assertIn("3,2 Go sur 16 Go — 20 %", corps)
        self.assertIn("3 % en moyenne", corps)
        # Ordre de lecture : titre, trois indicateurs, puis texte complet.
        premiere = corps[corps.index("<article>") : corps.index("</article>")]
        positions = [
            premiere.index(libelle)
            for libelle in (
                "Transcription",
                "Mémoire max",
                "CPU du moteur",
                "Texte transcrit",
                "<pre>",
            )
        ]
        self.assertEqual(positions, sorted(positions))
        # Aucune valeur brute d'octets ne remonte au premier niveau.
        self.assertNotIn("octets", premiere)
        self.assertIn("transcription simulée de test", premiere)

    def test_synthese_descriptive_temps_et_ram(self) -> None:
        self.ecrire_deux_modeles()

        corps = self.page([f"{IDENTIFIANT}:1", f"{IDENTIFIANT_ANCIEN}:1"])

        self.assertIn(
            "Mesures observées · Plus rapide : Modèle B · Moins de RAM : Modèle A",
            corps,
        )
        self.assertNotIn("Sans distinction", corps)
        # Le CPU est affiché mais ne désigne aucun vainqueur.
        self.assertNotIn("CPU le moins", corps)

    def test_synthese_egalite_et_exclusion_des_mesures_simulees(self) -> None:
        mesures = {"duree_transcription_s": 2.0, "pic_memoire_octets": 900}
        self.ecrire_essai(IDENTIFIANT, modele="Modèle A", mesures=mesures)
        self.ecrire_essai(IDENTIFIANT_ANCIEN, modele="Modèle B", mesures=mesures)

        egalite = self.page([f"{IDENTIFIANT}:1", f"{IDENTIFIANT_ANCIEN}:1"])

        self.assertIn("Plus rapide : Modèle A et Modèle B (égalité)", egalite)
        self.assertIn("Moins de RAM : Modèle A et Modèle B (égalité)", egalite)

        self.ecrire_essai(IDENTIFIANT_TIERS, modele="Modèle C", simule=True)
        exclues = self.page(
            [
                f"{IDENTIFIANT}:1",
                f"{IDENTIFIANT_ANCIEN}:1",
                f"{IDENTIFIANT_TIERS}:1",
            ]
        )

        # Une mesure simulée ne reçoit aucune distinction de performance réelle.
        self.assertIn(
            "Sans distinction : Modèle C (mesures simulées ou résultat partiel)",
            exclues,
        )
        self.assertNotIn("Plus rapide : Modèle C", exclues)

    def test_details_progressifs_differences_puis_toutes_les_mesures(self) -> None:
        self.ecrire_essai(
            IDENTIFIANT,
            modele="Modèle A",
            reglages={"langue": "fr", "beam_size": 5},
        )
        self.ecrire_essai(
            IDENTIFIANT_ANCIEN,
            modele="Modèle B",
            reglages={"langue": "fr", "beam_size": 3},
        )

        corps = self.page([f"{IDENTIFIANT}:1", f"{IDENTIFIANT_ANCIEN}:1"])

        grille = corps.index('class="grid cols-2"')
        differences = corps.index("Ce qui diffère")
        mesures = corps.index("Toutes les mesures et informations")
        self.assertLess(grille, differences)
        self.assertLess(differences, mesures)

        # « Ce qui diffère » ne montre que les valeurs distinctes.
        section = corps[differences:mesures]
        self.assertIn("Réglage demandé : beam_size", section)
        self.assertNotIn("Réglage demandé : langue", section)
        self.assertIn(
            "Les autres mesures et informations comparées sont communes", section
        )

        # « Toutes les mesures et informations » garde tout, RTF et son repère.
        details = corps[mesures:]
        self.assertIn("Réglage demandé : langue", details)
        self.assertIn("Durée totale de l'opération", details)
        self.assertIn("RTF (durée de transcription / durée décodée)", details)
        self.assertIn("repère d'objectif 2, non bloquant", details)
        self.assertIn("<table>", details)

    def test_toutes_les_selections_deviennent_des_cartes(self) -> None:
        self.ecrire_essai(IDENTIFIANT, modele="Modèle A")
        self.ecrire_essai(IDENTIFIANT_ANCIEN, modele="Modèle B")
        self.ecrire_essai(IDENTIFIANT_TIERS, modele="Modèle C")

        corps = self.page(
            [
                f"{IDENTIFIANT_ANCIEN}:1",
                f"{IDENTIFIANT_TIERS}:1",
                f"{IDENTIFIANT}:1",
            ]
        )

        self.assertEqual(corps.count("<article>"), 3)
        grille = corps.index('class="grid cols-2"')
        positions = [
            corps.index(f"<h2>Modèle {lettre} · ", grille) for lettre in ("B", "C", "A")
        ]
        self.assertEqual(positions, sorted(positions))

    def test_alertes_materiel_visibles_hors_details(self) -> None:
        self.ecrire_essai(IDENTIFIANT, modele="Modèle A")
        self.ecrire_essai(
            IDENTIFIANT_ANCIEN,
            modele="Modèle B",
            machine={**self.MACHINE, "ram_totale_octets": 32_000_000_000},
        )

        corps = self.page([f"{IDENTIFIANT}:1", f"{IDENTIFIANT_ANCIEN}:1"])
        premier_details = corps.index("<details")

        # Les deux cartes signalent la différence connue, sans ouvrir de détail.
        self.assertEqual(corps[:premier_details].count("Matériel différent"), 2)
        self.assertIn("Matériel différent sur RAM totale", corps[:premier_details])
        self.assertIn(
            "sans preuve d'identité des machines", corps[:premier_details]
        )

    def test_materiel_inconnu_et_difference_connue_sur_les_cartes(self) -> None:
        self.ecrire_essai(IDENTIFIANT, modele="Modèle A")
        self.ecrire_essai(
            IDENTIFIANT_ANCIEN,
            modele="Modèle B",
            machine={
                **self.MACHINE,
                "architecture": None,
                "ram_totale_octets": 32_000_000_000,
            },
        )

        corps = self.page([f"{IDENTIFIANT}:1", f"{IDENTIFIANT_ANCIEN}:1"])
        visible = corps[: corps.index("<details")]

        # La différence connue n'est pas masquée par le champ inconnu.
        self.assertIn("Matériel différent sur RAM totale", visible)
        self.assertIn("matériel non vérifié pour architecture", visible)

    def test_processeur_absent_seul_sans_alerte_materiel(self) -> None:
        self.ecrire_essai(IDENTIFIANT, modele="Modèle A")
        self.ecrire_essai(
            IDENTIFIANT_ANCIEN,
            modele="Modèle B",
            machine={**self.MACHINE, "processeur": "Autre processeur fictif"},
        )

        corps = self.page([f"{IDENTIFIANT}:1", f"{IDENTIFIANT_ANCIEN}:1"])

        self.assertNotIn("Matériel différent", corps)
        self.assertNotIn("matériel non vérifié", corps)

    def test_annotation_ram_cumulative_pour_audio_non_premier(self) -> None:
        self.ecrire_essai(IDENTIFIANT, modele="Modèle A", audios=2)
        self.ecrire_essai(IDENTIFIANT_ANCIEN, modele="Modèle B")

        corps = self.page([f"{IDENTIFIANT}:2", f"{IDENTIFIANT_ANCIEN}:1"])

        self.assertEqual(corps.count("Pic mémoire cumulatif du lot"), 1)
        self.assertIn("il peut provenir d'un audio précédent", corps)


class ClassementGroupesWebTest(SocleWebTest):
    """Tri GET borné des listes de `/resultats/comparaison` (tâche 2.1).

    Les données sont synthétiques et écrites dans le dossier temporaire du socle :
    aucune inférence, aucun réseau, aucune écriture dans les fichiers lus.
    """

    def page(self, chemin: str = "/resultats/comparaison", **options) -> str:
        """Page rendue avec succès, HTML seul et entités décodées."""
        options.setdefault("base_url", self.base_url())
        reponse = self.client.get(chemin, **options)
        self.assertEqual(reponse.status_code, 200, chemin)
        corps = reponse.get_data(as_text=True)
        self.verifier_html_seul(corps)
        return html.unescape(corps)

    def ecrire_essai(
        self,
        identifiant: str,
        *,
        cree_le: str | None = DATE_RECENTE,
        mesures: dict | None = None,
        machine: dict | None = None,
        empreinte: str = EMPREINTE_A,
        audios: int = 1,
    ) -> None:
        """Exécution terminée d'un audio de l'empreinte demandée.

        `mesures` remplace les mesures de l'audio (`None` = mesures par défaut) ;
        `audios` crée plusieurs audios de même contenu pour observer le départage
        par ordre audio.
        """
        plans = tuple(
            (f"prise{position}.wav", STATUT_OK) for position in range(1, audios + 1)
        )
        remplacements: dict = {"cree_le": cree_le}
        if machine is not None:
            remplacements["machine"] = machine
        run = run_json(identifiant, audios=plans, **remplacements)
        resultats = tuple(
            resultat_empreinte(
                run,
                plan,
                empreinte,
                **({} if mesures is None else {"mesures_extra": mesures}),
            )
            for plan in run["audios"]
        )
        ecrire_execution(self.dossier_data, run, resultats)

    def selections(self, corps: str) -> list[str]:
        """Sélections de comparaison, dans l'ordre où la page les affiche."""
        return MOTIF_SELECTION.findall(corps)

    def selections_du_groupe(self, corps: str, empreinte: str) -> list[str]:
        """Sélections d'un groupe, de son ancre à l'ancre suivante."""
        debut = corps.index(f'id="groupe-{empreinte}"')
        fin = corps.find('id="groupe-', debut + 1)
        section = corps[debut:] if fin == -1 else corps[debut:fin]
        return self.selections(section)

    def test_tri_par_defaut_temps_croissant_avant_arrondi(self) -> None:
        # 1,03 s et 1,04 s s'affichent toutes deux « 1 s » : l'ordre prouve que
        # le tri porte sur la valeur non arrondie.
        self.ecrire_essai(IDENTIFIANT_ANCIEN, mesures={"duree_transcription_s": 1.04})
        self.ecrire_essai(IDENTIFIANT, mesures={"duree_transcription_s": 1.03})
        self.ecrire_essai(IDENTIFIANT_TIERS, mesures={"duree_transcription_s": 2.0})

        sans_parametre = self.page()
        self.assertEqual(
            self.selections(sans_parametre),
            [f"{IDENTIFIANT}:1", f"{IDENTIFIANT_ANCIEN}:1", f"{IDENTIFIANT_TIERS}:1"],
        )
        explicite = self.page(query_string=[(CHAMP_TRI_CLASSEMENT, "temps")])

        self.assertEqual(self.selections(explicite), self.selections(sans_parametre))

    def test_tri_ram_cpu_et_recent(self) -> None:
        self.ecrire_essai(
            IDENTIFIANT_ANCIEN,
            mesures={"duree_transcription_s": 2.0, "pic_memoire_octets": 1000},
        )
        self.ecrire_essai(
            IDENTIFIANT,
            mesures={
                "duree_transcription_s": 1.0,
                "temps_cpu_s": 1.0,
                "pic_memoire_octets": 500,
            },
        )
        self.ecrire_essai(
            IDENTIFIANT_TIERS,
            mesures={"duree_transcription_s": 3.0, "pic_memoire_octets": None},
            cree_le=None,
        )

        ram = self.page(query_string=[(CHAMP_TRI_CLASSEMENT, "ram")])
        self.assertEqual(
            self.selections(ram),
            [f"{IDENTIFIANT}:1", f"{IDENTIFIANT_ANCIEN}:1", f"{IDENTIFIANT_TIERS}:1"],
        )

        # CPU = 100 × temps CPU / (durée × 8 processeurs logiques) : 6,25 %
        # (TIERS), 9,375 % (ANCIEN), 12,5 % (IDENTIFIANT) ; une capacité
        # absente rend le ratio indisponible, donc classé en fin.
        self.ecrire_essai(
            IDENTIFIANT_QUATRIEME,
            mesures={"duree_transcription_s": 2.0, "temps_cpu_s": 8.0},
            machine={"os": "Linux", "coeurs_logiques": None},
        )
        cpu = self.page(query_string=[(CHAMP_TRI_CLASSEMENT, "cpu")])

        self.assertEqual(
            self.selections_du_groupe(cpu, EMPREINTE_A),
            [
                f"{IDENTIFIANT_TIERS}:1",
                f"{IDENTIFIANT_ANCIEN}:1",
                f"{IDENTIFIANT}:1",
                f"{IDENTIFIANT_QUATRIEME}:1",
            ],
        )

        # Date inconnue de TIERS en fin, les trois autres dates égales étant
        # départagées par identifiant décroissant.
        recent = self.page(query_string=[(CHAMP_TRI_CLASSEMENT, "recent")])
        self.assertEqual(
            self.selections_du_groupe(recent, EMPREINTE_A)[-1],
            f"{IDENTIFIANT_TIERS}:1",
        )

    def test_duree_nulle_mesuree_reste_triable(self) -> None:
        self.ecrire_essai(IDENTIFIANT, mesures={"duree_transcription_s": 0.0})
        self.ecrire_essai(IDENTIFIANT_ANCIEN, mesures={"duree_transcription_s": 1.0})
        corps = self.page()
        self.assertEqual(
            self.selections_du_groupe(corps, EMPREINTE_A),
            [f"{IDENTIFIANT}:1", f"{IDENTIFIANT_ANCIEN}:1"],
        )

    def test_tri_absents_en_fin_et_dates_inconnues_en_fin(self) -> None:
        self.ecrire_essai(IDENTIFIANT, mesures={"duree_transcription_s": 5.0})
        self.ecrire_essai(
            IDENTIFIANT_ANCIEN,
            mesures={"duree_transcription_s": None},
            cree_le=None,
        )
        self.ecrire_essai(
            IDENTIFIANT_TIERS,
            mesures={"duree_transcription_s": "1.0"},
            cree_le="pas une date",
        )

        temps = self.page(query_string=[(CHAMP_TRI_CLASSEMENT, "temps")])
        # Valeur valide d'abord ; les deux indisponibles ensuite, départagées par
        # identifiant décroissant (date inconnue pour les deux).
        self.assertEqual(
            self.selections_du_groupe(temps, EMPREINTE_A),
            [f"{IDENTIFIANT}:1", f"{IDENTIFIANT_TIERS}:1", f"{IDENTIFIANT_ANCIEN}:1"],
        )

        recent = self.page(query_string=[(CHAMP_TRI_CLASSEMENT, "recent")])
        self.assertEqual(
            self.selections_du_groupe(recent, EMPREINTE_A),
            [f"{IDENTIFIANT}:1", f"{IDENTIFIANT_TIERS}:1", f"{IDENTIFIANT_ANCIEN}:1"],
        )

    def test_egalites_departagees_par_date_identifiant_et_ordre_audio(self) -> None:
        self.ecrire_essai(
            IDENTIFIANT_ANCIEN,
            cree_le=DATE_ANCIENNE,
            mesures={"duree_transcription_s": 1.0},
            audios=2,
        )
        self.ecrire_essai(
            IDENTIFIANT, cree_le=DATE_RECENTE, mesures={"duree_transcription_s": 1.0}
        )
        self.ecrire_essai(
            IDENTIFIANT_TIERS,
            cree_le=DATE_RECENTE,
            mesures={"duree_transcription_s": 1.0},
        )

        corps = self.page(query_string=[(CHAMP_TRI_CLASSEMENT, "temps")])

        # Date décroissante, puis identifiant décroissant, puis ordre audio.
        self.assertEqual(
            self.selections_du_groupe(corps, EMPREINTE_A),
            [
                f"{IDENTIFIANT_TIERS}:1",
                f"{IDENTIFIANT}:1",
                f"{IDENTIFIANT_ANCIEN}:1",
                f"{IDENTIFIANT_ANCIEN}:2",
            ],
        )

    def test_tri_applique_a_toutes_les_listes_de_groupes(self) -> None:
        self.ecrire_essai(IDENTIFIANT, mesures={"pic_memoire_octets": 900})
        self.ecrire_essai(IDENTIFIANT_ANCIEN, mesures={"pic_memoire_octets": 100})
        self.ecrire_essai(
            IDENTIFIANT_TIERS, mesures={"pic_memoire_octets": 500}, empreinte=EMPREINTE_B
        )
        self.ecrire_essai(
            IDENTIFIANT_QUATRIEME, mesures={"pic_memoire_octets": 200}, empreinte=EMPREINTE_B
        )

        corps = self.page(query_string=[(CHAMP_TRI_CLASSEMENT, "ram")])

        self.assertEqual(
            self.selections_du_groupe(corps, EMPREINTE_A),
            [f"{IDENTIFIANT_ANCIEN}:1", f"{IDENTIFIANT}:1"],
        )
        self.assertEqual(
            self.selections_du_groupe(corps, EMPREINTE_B),
            [f"{IDENTIFIANT_QUATRIEME}:1", f"{IDENTIFIANT_TIERS}:1"],
        )

    def test_tri_duplique_ou_inconnu_refuse_sans_operation(self) -> None:
        self.ecrire_essai(IDENTIFIANT, mesures={"duree_transcription_s": 2.0})
        self.ecrire_essai(IDENTIFIANT_ANCIEN, mesures={"duree_transcription_s": 1.0})
        racine = self.dossier_data / "results"
        avant = {
            chemin: chemin.read_bytes()
            for chemin in sorted(racine.rglob("*"))
            if chemin.is_file()
        }

        for parametres in (
            [(CHAMP_TRI_CLASSEMENT, "cpu"), (CHAMP_TRI_CLASSEMENT, "ram")],
            [(CHAMP_TRI_CLASSEMENT, "cpu"), (CHAMP_TRI_CLASSEMENT, "cpu")],
            [(CHAMP_TRI_CLASSEMENT, "inconnu")],
            [(CHAMP_TRI_CLASSEMENT, "")],
        ):
            with self.subTest(parametres=parametres):
                reponse = self.client.get(
                    "/resultats/comparaison",
                    query_string=parametres,
                    base_url=self.base_url(),
                )
                corps = self.verifier_page_erreur(reponse, 400)
                self.assertIn("Classement refusé", corps)

        self.assertEqual(
            {
                chemin: chemin.read_bytes()
                for chemin in sorted(racine.rglob("*"))
                if chemin.is_file()
            },
            avant,
        )
        instantane = self.creneau.instantane()
        self.assertIsNone(instantane.type_operation)
        self.assertEqual(instantane.journal, ())

    def test_liens_de_tri_avec_ancre_de_retour_et_limite_des_cases(self) -> None:
        self.ecrire_essai(IDENTIFIANT, mesures={"duree_transcription_s": 2.0})
        self.ecrire_essai(IDENTIFIANT_ANCIEN, mesures={"duree_transcription_s": 1.0})

        corps = self.page()

        # Chaque groupe est une cible d'ancre ; le critère courant n'est pas un lien.
        self.assertIn(f'id="groupe-{EMPREINTE_A}"', corps)
        for critere in ("ram", "cpu", "recent"):
            self.assertIn(
                f'href="/resultats/comparaison?{CHAMP_TRI_CLASSEMENT}={critere}'
                f'#groupe-{EMPREINTE_A}"',
                corps,
            )
        self.assertIn("<strong>Temps de transcription</strong>", corps)
        self.assertNotIn(
            f'href="/resultats/comparaison?{CHAMP_TRI_CLASSEMENT}=temps#groupe-', corps
        )

        # Le critère demandé devient le critère courant, et le temps redevient
        # un lien : la page ne propose jamais de recharger le critère affiché.
        ram = self.page(query_string=[(CHAMP_TRI_CLASSEMENT, "ram")])
        self.assertIn("<strong>Moins de RAM</strong>", ram)
        self.assertIn(
            f'href="/resultats/comparaison?{CHAMP_TRI_CLASSEMENT}=temps'
            f'#groupe-{EMPREINTE_A}"',
            ram,
        )
        # Limite explicite du HTML sans JavaScript : les cases non soumises
        # ne sont pas conservées lors d'un changement de tri.
        self.assertIn("cases cochées mais non soumises ne sont pas conservées", corps)

    def test_comparaison_selectionnee_garde_l_ordre_recu(self) -> None:
        self.ecrire_essai(IDENTIFIANT, mesures={"duree_transcription_s": 2.0})
        self.ecrire_essai(IDENTIFIANT_ANCIEN, mesures={"duree_transcription_s": 1.0})
        premier = f"{IDENTIFIANT}:1"
        second = f"{IDENTIFIANT_ANCIEN}:1"

        for ordre, parametres in (
            ((premier, second), [(CHAMP_TRI_CLASSEMENT, "temps")]),
            ((second, premier), [(CHAMP_TRI_CLASSEMENT, "ram")]),
        ):
            with self.subTest(ordre=ordre):
                corps = self.page(
                    f"/resultats/comparaison/{EMPREINTE_A}",
                    query_string=[
                        (CHAMP_SELECTION_COMPARAISON, ordre[0]),
                        (CHAMP_SELECTION_COMPARAISON, ordre[1]),
                        *parametres,
                    ],
                )
                positions = [
                    corps.index(f'href="/resultats/{selection.split(":")[0]}"')
                    for selection in ordre
                ]
                self.assertEqual(positions, sorted(positions))


class ListeParResultatWebTest(SocleWebTest):
    """Lignes de résultats et sous-listes simulées par audio (tâche 2.2).

    Les données sont synthétiques et écrites dans le dossier temporaire du
    socle : aucune inférence, aucun réseau, aucune écriture dans les fichiers
    lus.
    """

    def page(self, chemin: str = "/resultats/comparaison", **options) -> str:
        """Page rendue avec succès, HTML seul et entités décodées."""
        options.setdefault("base_url", self.base_url())
        reponse = self.client.get(chemin, **options)
        self.assertEqual(reponse.status_code, 200, chemin)
        corps = reponse.get_data(as_text=True)
        self.verifier_html_seul(corps)
        return html.unescape(corps)

    def ecrire_essai(
        self,
        identifiant: str = IDENTIFIANT,
        *,
        empreinte: object = EMPREINTE_A,
        simule: bool = False,
        cree_le: str | None = DATE_RECENTE,
        mesures: dict | None = None,
        **options: object,
    ) -> None:
        """Exécution synthétique, avec ou sans mesures simulées."""
        marques = {
            "factice": False,
            "synthetique": True,
            "mesures_simulees": False,
        }
        if simule:
            marques = {
                "factice": True,
                "synthetique": True,
                "mesures_simulees": True,
            }
        run = run_json(identifiant, cree_le=cree_le, **marques)
        options_resultat: dict = dict(marques)
        if mesures is not None:
            options_resultat["mesures_extra"] = mesures
        options_resultat.update(options)
        ecrire_execution(
            self.dossier_data,
            run,
            (
                resultat_empreinte(
                    run, run["audios"][0], empreinte, **options_resultat
                ),
            ),
        )

    def test_lignes_avec_etat_marques_date_et_reglages_distinctifs(self) -> None:
        self.ecrire_essai(
            IDENTIFIANT,
            cree_le=DATE_RECENTE,
            threads={"demandes": 4, "appliques": None},
        )
        self.ecrire_essai(IDENTIFIANT_ANCIEN, simule=True, cree_le=DATE_ANCIENNE)

        corps = self.page()

        # Deux sous-listes distinctes : les mesures simulées ne sont pas
        # mélangées aux résultats observés.
        self.assertIn("Résultats observés", corps)
        self.assertIn("Mesures simulées de cet audio", corps)
        self.assertLess(
            corps.index("Résultats observés"),
            corps.index("Mesures simulées de cet audio"),
        )
        self.assertLess(
            corps.index(f'href="/resultats/{IDENTIFIANT}"'),
            corps.index("Mesures simulées de cet audio"),
        )
        self.assertLess(
            corps.index("Mesures simulées de cet audio"),
            corps.index(f'href="/resultats/{IDENTIFIANT_ANCIEN}"'),
        )
        # État, date et réglages distinctifs restent visibles pour chaque ligne.
        self.assertIn("terminée", corps)
        self.assertIn(DATE_RECENTE, corps)
        self.assertIn(DATE_ANCIENNE, corps)
        self.assertIn("Threads demandés : 4", corps)
        self.assertIn("Marques", corps)
        self.assertIn("FACTICE", corps)
        self.assertIn("classées à part", corps)

    def test_aucun_dedoublonnage_dans_la_liste(self) -> None:
        # Deux essais identiques du même audio restent deux lignes.
        self.ecrire_essai(IDENTIFIANT_ANCIEN)
        self.ecrire_essai(IDENTIFIANT)

        corps = self.page()

        self.assertEqual(len(MOTIF_SELECTION.findall(corps)), 2)
        self.assertEqual(corps.count(f'value="{IDENTIFIANT}:1"'), 1)
        self.assertEqual(corps.count(f'value="{IDENTIFIANT_ANCIEN}:1"'), 1)
        self.assertEqual(corps.count(f'href="/resultats/{IDENTIFIANT}"'), 1)
        self.assertEqual(
            corps.count(f'href="/resultats/{IDENTIFIANT_ANCIEN}"'), 1
        )
        self.assertEqual(corps.count("Résultats observés"), 1)

    def test_classement_cpu_non_qualifie_d_efficacite(self) -> None:
        self.ecrire_essai(IDENTIFIANT)

        corps = self.page()

        self.assertIn(
            f'href="/resultats/comparaison?tri=cpu#groupe-{EMPREINTE_A}"', corps
        )
        for libelle in LIBELLES_TRI.values():
            self.assertIn(libelle, corps)
        self.assertEqual(LIBELLES_TRI[TRI_CPU], "CPU le moins occupé")
        # Un CPU peu occupé n'est ni une efficacité ni un vainqueur annoncé.
        minuscule = corps.lower()
        for terme in ("efficac", "effort", "difficulté", "meilleur"):
            self.assertNotIn(terme, minuscule)

    def test_historique_global_complet_sans_empreinte_valide(self) -> None:
        self.ecrire_essai(IDENTIFIANT, cree_le=DATE_RECENTE)
        self.ecrire_essai(
            IDENTIFIANT_TIERS, empreinte=None, cree_le=DATE_ANCIENNE
        )
        self.ecrire_essai(
            IDENTIFIANT_QUATRIEME,
            empreinte="pas-une-empreinte",
            cree_le="2024-01-03T00:00:00+00:00",
        )

        comparaisons = self.page()

        # Sans empreinte valide, aucune transcription comparable : le résultat
        # n'apparaît dans aucun groupe et n'est jamais regroupé de force.
        self.assertIn(f'href="/resultats/{IDENTIFIANT}"', comparaisons)
        self.assertNotIn(IDENTIFIANT_TIERS, comparaisons)
        self.assertNotIn(IDENTIFIANT_QUATRIEME, comparaisons)

        # L'historique global reste complet, avec lien de détail et ordre
        # décroissant, y compris pour ces exécutions.
        historique = self.page("/resultats")
        for identifiant in (
            IDENTIFIANT,
            IDENTIFIANT_TIERS,
            IDENTIFIANT_QUATRIEME,
        ):
            self.assertIn(f'href="/resultats/{identifiant}"', historique)
        self.assertLess(
            historique.index(IDENTIFIANT_QUATRIEME), historique.index(IDENTIFIANT_TIERS)
        )
        self.assertLess(
            historique.index(IDENTIFIANT_TIERS), historique.index(IDENTIFIANT)
        )


if __name__ == "__main__":
    unittest.main()
