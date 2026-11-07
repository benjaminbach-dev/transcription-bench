"""Tests des pages de résultats (tâche 7.1), sans moteur ni réseau.

Les fixtures viennent de `tests.test_consultation_resultats` : elles écrivent
des `run.json` et `result.json` synthétiques dans le dossier temporaire du
`SocleWebTest`, jamais sous le `data/` du dépôt. Les pages sont en lecture seule :
aucun test ne doit voir de fichier créé ou modifié par une requête GET.
"""

from __future__ import annotations

import html

from tests.test_consultation_resultats import (
    IDENTIFIANT,
    IDENTIFIANT_ANCIEN,
    ecrire_execution,
    execution_complete,
    plan_audio,
    result_json,
    run_json,
)
from tests.test_web import SocleWebTest
from transcription_bench.resultats import (
    ETAT_ABANDONNEE,
    ETAT_ECHOUEE,
    ETAT_EN_COURS,
    ETAT_INTERROMPUE,
    ETAT_TERMINEE,
    STATUT_NON_TRAITE,
    STATUT_OK,
)


class DetailProgressifWebTest(SocleWebTest):
    """Tête de lecture et alertes du détail individuel (tâche 3.2).

    Les fichiers sont synthétiques et écrits dans le dossier temporaire du
    socle : aucune inférence, aucun réseau, aucune écriture dans les fichiers
    lus.
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

    def page(self, identifiant: str = IDENTIFIANT) -> str:
        reponse = self.client.get(
            f"/resultats/{identifiant}", base_url=self.base_url()
        )
        self.assertEqual(reponse.status_code, 200, identifiant)
        corps = reponse.get_data(as_text=True)
        self.verifier_html_seul(corps)
        return html.unescape(corps)

    def ecrire_essai(
        self,
        identifiant: str = IDENTIFIANT,
        *,
        machine: dict | None = None,
        audios: int = 1,
        mesures: dict | None = None,
        mesures_execution: dict | None = None,
        etat: str = ETAT_INTERROMPUE,
        modele: str | None = None,
    ) -> None:
        plans = tuple(
            (f"prise{position}.wav", STATUT_OK) for position in range(1, audios + 1)
        )
        options: dict = {"audios": plans, "etat": etat}
        if machine is not None:
            options["machine"] = machine
        if mesures_execution is not None:
            options["mesures"] = mesures_execution
        run = run_json(identifiant, **options)
        if modele is not None:
            run["demande"]["modele"]["identifiant"] = modele
        resultats = tuple(
            result_json(
                plan,
                execution=identifiant,
                **({} if mesures is None else {"mesures_extra": mesures}),
            )
            for plan in run["audios"]
        )
        ecrire_execution(self.dossier_data, run, resultats)

    def ecrire_audio_synthetique(self) -> None:
        """Scénario de la spec : 1 min 37 s, 2,4 Go sur 16 Go, CPU < 1 %."""
        self.ecrire_essai(
            machine=self.MACHINE,
            mesures={
                "duree_transcription_s": 97.0,
                "temps_cpu_s": 3.104,
                "pic_memoire_octets": 2_400_000_000,
            },
            modele="organisation/modele-a",
        )

    def cartes_principales(self, corps: str) -> list[str]:
        """Partie principale de chaque carte : avant son premier accordéon."""
        cartes: list[str] = []
        position = 0
        while True:
            debut = corps.find("<article>", position)
            if debut == -1:
                return cartes
            fin = corps.find("<details", debut)
            if fin == -1:
                fin = corps.find("</article>", debut)
            cartes.append(corps[debut:fin])
            position = debut + 1

    def test_erreur_execution_visible_sans_ouvrir_les_details(self) -> None:
        run = run_json(etat=ETAT_ECHOUEE, erreur="Erreur globale de démonstration")
        ecrire_execution(self.dossier_data, run, (result_json(run["audios"][0]),))

        corps = self.page()

        self.assertIn("Erreur globale de démonstration", corps[:corps.index("<details")])
        self.assertIn('class="callout danger prose"', corps)

    def test_trois_indicateurs_avant_le_texte(self) -> None:
        self.ecrire_audio_synthetique()

        corps = self.page()

        self.assertIn("modele-a · Moteur factice", corps)
        self.assertIn("1 min 37 s", corps)
        self.assertIn("2,4 Go sur 16 Go — 15 %", corps)
        self.assertIn("< 1 % en moyenne", corps)
        # La date courte précède les textes, l'horodatage complet reste en détail.
        self.assertIn("02/01/2024 03:04", corps)
        self.assertLess(corps.index("02/01/2024 03:04"), corps.index("<pre>"))
        self.assertIn("2024-01-02T03:04:05+00:00", corps)
        positions = [
            corps.index(libelle)
            for libelle in (
                "Transcription",
                "Mémoire max",
                "CPU du moteur",
                "Texte transcrit",
                "<pre>",
            )
        ]
        self.assertEqual(positions, sorted(positions))
        # Texte et indicateurs précèdent le premier accordéon.
        self.assertLess(corps.index("<pre>"), corps.index("<details"))

    def test_duree_du_lot_jamais_presentee_comme_duree_de_l_audio(self) -> None:
        self.ecrire_essai(
            machine=self.MACHINE,
            mesures={"duree_transcription_s": 1.0},
            mesures_execution={
                "duree_operation_s": 12.5,
                "duree_processus_s": 11.0,
                "duree_chargement_s": 2.0,
                "pic_memoire_octets": 4096,
                "pic_memoire_partiel": False,
            },
        )

        corps = self.page()
        carte = corps[corps.index("<article>") : corps.index("<details")]

        # La carte ne porte que la durée de l'audio ; le lot reste en détail.
        self.assertIn("<strong>Transcription</strong> : 1 s<br>", carte)
        self.assertNotIn("12.500", carte)
        self.assertIn("Durée totale de l'opération", corps)
        self.assertIn("12.500 s", corps)
        self.assertGreater(
            corps.index("12.500 s"), corps.index("Durée totale de l'opération")
        )
        self.assertIn("ce n'est jamais la durée d'un audio", corps)

    def test_annotation_ram_et_materiel_different_hors_details(self) -> None:
        self.ecrire_essai(machine=self.MACHINE, audios=2)
        self.ecrire_essai(
            IDENTIFIANT_ANCIEN,
            machine={**self.MACHINE, "ram_totale_octets": 32_000_000_000},
        )

        corps = self.page()
        premiere, deuxieme = self.cartes_principales(corps)

        # Annotation cumulative du seul deuxième audio, visible d'emblée.
        self.assertNotIn("Pic mémoire cumulatif", premiere)
        self.assertIn("Pic mémoire cumulatif du lot", deuxieme)
        self.assertIn("il peut provenir d'un audio précédent", deuxieme)
        self.assertEqual(corps.count("Pic mémoire cumulatif du lot"), 1)
        # Matériel différent signalé pour chacun des deux audios du même fichier.
        self.assertIn("Matériel différent", premiere)
        self.assertIn("Matériel différent", deuxieme)
        self.assertIn("RAM totale", deuxieme)

    def test_materiel_non_verifie_visible_sans_details(self) -> None:
        self.ecrire_essai(
            machine={**self.MACHINE, "architecture": None},
        )

        corps = self.page()

        self.assertIn("Matériel non vérifié", corps[: corps.index("<details")])
        self.assertIn("non vérifié pour architecture", corps)

    def test_marques_et_mesure_partielle_hors_details(self) -> None:
        self.ecrire_essai(
            audios=2,
            machine=self.MACHINE,
            mesures_execution={
                "duree_operation_s": None,
                "duree_processus_s": None,
                "duree_chargement_s": 2.5,
                "pic_memoire_octets": 4096,
                "pic_memoire_partiel": True,
            },
        )

        corps = self.page()
        premier_details = corps.index("<details")

        visible = corps[:premier_details]
        self.assertIn("Exécution non terminée", visible)
        self.assertIn("résultats partiels", visible)
        self.assertIn("résultat partiel", visible)
        self.assertIn("Mesure partielle", visible)
        self.assertIn("Marques de cette transcription", visible)
        self.assertIn("<pre>", visible)

    def test_marque_synthetique_seule_ne_declare_pas_le_factice(self) -> None:
        run = run_json(
            IDENTIFIANT,
            factice=False,
            synthetique=True,
            mesures_simulees=False,
        )
        resultat = result_json(
            run["audios"][0], factice=False, synthetique=True, mesures_simulees=False
        )
        ecrire_execution(self.dossier_data, run, (resultat,))

        corps = self.page()

        self.assertIn("SYNTHÉTIQUE", corps)
        # Une marque SYNTHÉTIQUE seule ne dit rien du moteur ni des mesures.
        self.assertNotIn("Le moteur factice ne charge aucun modèle", corps)
        self.assertNotIn("Texte et mesures simulés", corps)
        self.assertIn("elle ne dit rien du moteur ni des mesures", corps)

    def test_marque_factice_affirme_les_mesures_simulees(self) -> None:
        self.ecrire_essai(etat=ETAT_TERMINEE, mesures={"duree_transcription_s": 1.0})

        corps = self.page()

        self.assertIn("Le moteur factice ne charge aucun modèle", corps)
        self.assertIn("Texte et mesures simulés", corps)

    def test_materiel_identique_aucune_alerte_rendue(self) -> None:
        self.ecrire_essai(machine=self.MACHINE)
        self.ecrire_essai(IDENTIFIANT_ANCIEN, machine=dict(self.MACHINE))

        corps = self.page()

        self.assertNotIn("Matériel différent", corps)
        self.assertNotIn("Matériel non vérifié", corps)


class ResultatsWebTest(SocleWebTest):
    """Liste des exécutions et détail d'une transcription."""

    def page(self, chemin: str) -> str:
        reponse = self.client.get(chemin, base_url=self.base_url())
        self.assertEqual(reponse.status_code, 200, chemin)
        corps = reponse.get_data(as_text=True)
        self.verifier_html_seul(corps)
        return html.unescape(corps)

    def test_page_resultats_vide_sans_creation_de_dossier(self) -> None:
        corps = self.page("/resultats")

        self.assertIn("Aucune exécution enregistrée", corps)
        self.assertIn(str(self.dossier_data / "results"), corps)
        # Le lien vers les groupes et le classement est mis en avant.
        self.assertIn('href="/resultats/comparaison"', corps)
        self.assertIn(">Comparer</a>", corps)
        self.assertIn('href="/resultats/aide"', corps)
        self.assertIn('href="/"', corps)
        self.assertFalse(self.dossier_data.exists())

    def test_liste_des_executions_ordre_etats_et_marques(self) -> None:
        recent = run_json(
            IDENTIFIANT,
            audios=(("a.wav", STATUT_OK), ("b.wav", STATUT_NON_TRAITE)),
        )
        ecrire_execution(self.dossier_data, recent, (result_json(recent["audios"][0]),))
        ecrire_execution(
            self.dossier_data,
            run_json("20240101-010101-11223344", etat=ETAT_ECHOUEE),
        )

        corps = self.page("/resultats")

        self.assertIn(f'href="/resultats/{IDENTIFIANT}"', corps)
        self.assertLess(
            corps.index(IDENTIFIANT), corps.index("20240101-010101-11223344")
        )
        self.assertIn("terminée", corps)
        self.assertIn("en échec", corps)
        self.assertIn("1 sur 2", corps)
        self.assertIn("FACTICE", corps)
        self.assertIn("SYNTHÉTIQUE", corps)
        self.assertIn("MESURES SIMULÉES", corps)

    def test_detail_transcription_metadonnees_mesures_et_repere_rtf(self) -> None:
        run = run_json(audios=(("a.wav", STATUT_OK),))
        resultat = result_json(
            run["audios"][0],
            duree_decodee=4.0,
            duree_transcription=6.0,
            texte="Transcription synthétique de contrôle",
        )
        ecrire_execution(self.dossier_data, run, (resultat,))

        corps = self.page(f"/resultats/{IDENTIFIANT}")

        self.assertIn("Transcription synthétique de contrôle", corps)
        self.assertIn("Segments horodatés", corps)
        self.assertIn("Moteur factice", corps)
        self.assertIn("Linux", corps)
        self.assertIn("Processeur", corps)
        self.assertIn("FFmpeg", corps)
        self.assertIn("7.1", corps)
        self.assertIn("Durée totale de l'opération", corps)
        self.assertIn("Durée du processus moteur", corps)
        self.assertIn("12.500 s", corps)
        self.assertIn("11.000 s", corps)
        # RTF = 6 / 4 = 1.5, repère 2 affiché sans blocage.
        self.assertIn("1.500, repère d'objectif 2 (non bloquant)", corps)
        self.assertNotIn("au-dessus du repère", corps)
        self.assertIn("FACTICE", corps)
        self.assertIn("indisponible", corps)  # threads appliqués non affirmés

    def test_detail_timings_natifs_affiches_par_appel(self) -> None:
        run = run_json(audios=(("a.wav", STATUT_OK),))
        resultat = result_json(
            run["audios"][0],
            timings_natifs=[
                {
                    "unite": "ms",
                    "load_ms": 12.5,
                    "mel_ms": 3.25,
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
        ecrire_execution(self.dossier_data, run, (resultat,))

        corps = self.page(f"/resultats/{IDENTIFIANT}")

        self.assertIn("Timings natifs transmis par le moteur", corps)
        self.assertEqual(corps.count("<td>ms</td>"), 2)
        self.assertIn("12.500", corps)
        self.assertIn("60.500", corps)
        # Une étape absente reste « indisponible », jamais zéro.
        self.assertIn("indisponible", corps)

    def test_detail_sans_timings_natifs_signale_l_absence(self) -> None:
        run = run_json(audios=(("a.wav", STATUT_OK),))
        resultat = result_json(run["audios"][0])
        del resultat["timings_natifs"]
        ecrire_execution(self.dossier_data, run, (resultat,))

        corps = self.page(f"/resultats/{IDENTIFIANT}")

        self.assertIn("Aucun timing natif n'a été transmis", corps)

    def test_detail_rtf_au_dessus_du_repere_reste_non_bloquant(self) -> None:
        run = run_json(audios=(("a.wav", STATUT_OK),))
        resultat = result_json(
            run["audios"][0], duree_decodee=1.0, duree_transcription=3.0
        )
        ecrire_execution(self.dossier_data, run, (resultat,))

        corps = self.page(f"/resultats/{IDENTIFIANT}")

        self.assertIn("au-dessus du repère", corps)
        self.assertIn("enregistrée normalement", corps)
        self.assertIn("transcrit", corps)

    def test_detail_rtf_absent_sur_duree_decodee_nulle(self) -> None:
        run = run_json(audios=(("a.wav", STATUT_OK),))
        resultat = result_json(
            run["audios"][0], duree_decodee=0.0, duree_transcription=1.0
        )
        ecrire_execution(self.dossier_data, run, (resultat,))

        corps = self.page(f"/resultats/{IDENTIFIANT}")

        self.assertIn("aucun RTF n'est calculé", corps)
        self.assertNotIn("repère d'objectif 2 (non bloquant)", corps)

    def test_detail_partiel_accessibles_et_etats_affiches(self) -> None:
        attendus = {
            ETAT_EN_COURS: "en cours",
            ETAT_INTERROMPUE: "interrompue",
            ETAT_ABANDONNEE: "abandonnée",
            ETAT_ECHOUEE: "en échec",
        }
        for position, (etat, libelle) in enumerate(attendus.items()):
            identifiant = f"2024010{position + 1}-000000-0000000{position}"
            run = run_json(
                identifiant,
                etat=etat,
                audios=(("a.wav", STATUT_OK), ("b.wav", STATUT_NON_TRAITE)),
            )
            ecrire_execution(
                self.dossier_data,
                run,
                (result_json(run["audios"][0], execution=identifiant),),
            )

            with self.subTest(etat=etat):
                corps = self.page(f"/resultats/{identifiant}")
                self.assertIn(libelle, corps)
                self.assertIn("résultats partiels", corps)
                self.assertIn("résultat partiel", corps)
                self.assertIn("Audio non traité", corps)

    def test_detail_termine_signale_les_audios_non_traites(self) -> None:
        run = run_json(
            audios=(("a.wav", STATUT_OK), ("b.wav", STATUT_NON_TRAITE)),
        )
        ecrire_execution(self.dossier_data, run, (result_json(run["audios"][0]),))

        corps = self.page(f"/resultats/{IDENTIFIANT}")

        self.assertNotIn("résultats partiels", corps)
        self.assertIn("Audio non traité", corps)

    def test_detail_echappe_le_contenu_des_fichiers(self) -> None:
        texte = "<script>alert('x')</script> & <b>gras</b>"
        execution_complete(self.dossier_data, texte=texte)

        reponse = self.client.get(
            f"/resultats/{IDENTIFIANT}", base_url=self.base_url()
        )
        corps_brut = reponse.get_data(as_text=True)

        self.assertEqual(reponse.status_code, 200)
        self.verifier_html_seul(corps_brut)
        self.assertIn("&lt;script&gt;", corps_brut)
        self.assertIn("&amp;", corps_brut)
        self.assertIn("&lt;b&gt;gras&lt;/b&gt;", corps_brut)
        self.assertNotIn("<b>gras</b>", corps_brut)

    def test_detail_segments_non_finis_et_reglages_json_echappes(self) -> None:
        run = run_json()
        run["demande"]["reglages"] = {
            "temperature": [0.0, 0.2],
            "options": {"a": "<valeur>"},
        }
        resultat = result_json(
            run["audios"][0],
            segments=[
                {"debut_s": float("nan"), "fin_s": 1.0, "texte": "segment conservé"}
            ],
        )
        ecrire_execution(self.dossier_data, run, (resultat,))

        reponse = self.client.get(
            f"/resultats/{IDENTIFIANT}", base_url=self.base_url()
        )
        corps_brut = reponse.get_data(as_text=True)

        self.assertEqual(reponse.status_code, 200)
        self.verifier_html_seul(corps_brut)
        self.assertIn("segment conservé", corps_brut)
        self.assertIn("indisponible", corps_brut)
        self.assertIn("[0.0,0.2]", corps_brut)
        self.assertIn("&lt;valeur&gt;", corps_brut)
        self.assertNotIn("<valeur>", corps_brut)

    def test_detail_absent_refuse_sans_trace(self) -> None:
        reponse = self.client.get(
            "/resultats/20240101-010101-11223344", base_url=self.base_url()
        )
        self.verifier_page_erreur(reponse, 404)

        reponse = self.client.get("/resultats/pas-un-identifiant", base_url=self.base_url())
        self.verifier_page_erreur(reponse, 404)

    def test_detail_identifiant_hostile_refuse(self) -> None:
        reponse = self.client.get("/resultats/C:%5Csecret", base_url=self.base_url())

        self.verifier_page_erreur(reponse, 400)

    def test_detail_schema_inconnu_refuse_sans_ecriture_ni_500(self) -> None:
        run = run_json(schema=2)
        dossier = ecrire_execution(self.dossier_data, run)
        avant = (dossier / "run.json").read_bytes()

        reponse = self.client.get(
            f"/resultats/{IDENTIFIANT}", base_url=self.base_url()
        )

        corps = self.verifier_page_erreur(reponse, 422)
        self.assertIn("non interprétable", corps)
        self.assertEqual((dossier / "run.json").read_bytes(), avant)

    def test_liste_entree_illisible_affichee_sans_500(self) -> None:
        racine = self.dossier_data / "results"
        racine.mkdir(parents=True)
        dossier = racine / IDENTIFIANT
        dossier.mkdir()
        (dossier / "run.json").write_text("{ pas du json", encoding="utf-8")

        corps = self.page("/resultats")

        self.assertIn("non interprétable", corps)
        self.assertIn(IDENTIFIANT, corps)
        self.assertNotIn(f'href="/resultats/{IDENTIFIANT}"', corps)
        # Marques inconnues : « indisponible », jamais « aucune ».
        debut = corps.index(IDENTIFIANT)
        ligne = corps[corps.rfind("<tr>", 0, debut) : corps.index("</tr>", debut)]
        self.assertNotIn("aucune", ligne)
        self.assertIn("<td>indisponible</td>", ligne)

    def test_liste_runtime_json_incoherent_affiche_sans_500(self) -> None:
        audios_invalides = run_json("20240101-000000-00000001")
        audios_invalides["audios"] = "pas une liste"
        statut_invalide = run_json("20240102-000000-00000002")
        statut_invalide["audios"][0]["statut"] = []
        for run in (audios_invalides, statut_invalide):
            ecrire_execution(self.dossier_data, run)

        corps = self.page("/resultats")

        self.assertIn("non interprétable", corps)
        self.assertIn("20240101-000000-00000001", corps)
        self.assertIn("20240102-000000-00000002", corps)

    def test_pages_resultats_sans_effet_de_bord_en_lecture(self) -> None:
        execution_complete(self.dossier_data)
        dossier = self.dossier_data / "results" / IDENTIFIANT
        avant = {
            chemin: chemin.read_bytes()
            for chemin in sorted(dossier.rglob("*"))
            if chemin.is_file()
        }

        self.page("/resultats")
        self.page(f"/resultats/{IDENTIFIANT}")

        apres = {
            chemin: chemin.read_bytes()
            for chemin in sorted(dossier.rglob("*"))
            if chemin.is_file()
        }
        self.assertEqual(avant, apres)

    def test_liste_dossier_resultats_illisible_message_fixe(self) -> None:
        # Un fichier à la place du dossier des résultats rend la liste illisible.
        self.dossier_data.mkdir(parents=True)
        (self.dossier_data / "results").write_text("pas un dossier", encoding="utf-8")

        corps = self.page("/resultats")

        self.assertIn("n'a pas pu être lu", corps)
        self.assertNotIn("Traceback", corps)
