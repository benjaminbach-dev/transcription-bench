"""Bloc secondaire « Contexte de l'ordinateur » (tâche 3.1, design D4).

Les pages de détail et de comparaison sont rendues à partir de fichiers de
résultats synthétiques écrits dans le dossier temporaire de `SocleWebTest` :
aucune inférence, aucun réseau, aucune mesure de l'ordinateur qui exécute les
tests. Les observations système sont relues par la consultation ; le bloc ne
calcule aucune marge ni aucune part « autres applications », ne classe rien et
fonctionne sans JavaScript (`details`/`summary` natifs).
"""

from __future__ import annotations

import html
import re
from typing import Any

from engines.mesures_systeme import (
    PROVENANCE_REELLE,
    SIMULATION_RELEVE_LE,
)
from tests.outils_html import assert_html_seul
from tests.test_consultation_observations_systeme import (
    cpu_systeme,
    memoire_systeme,
    observation,
)
from tests.test_consultation_resultats import (
    IDENTIFIANT,
    IDENTIFIANT_ANCIEN,
    ecrire_execution,
    result_json,
    run_json,
)
from tests.test_web import SocleWebTest
from transcription_bench.consultation_resultats import (
    CLE_OBSERVATION_AUDIO,
    CLE_OBSERVATION_CHARGEMENT,
    LIBELLES_TRI,
)

TOTAL_OCTETS = 16_000_000_000
DISPONIBLE_AUDIO = 5_200_000_000
DISPONIBLE_CHARGEMENT = 7_000_000_000
PIC_MOTEUR = 2_400_000_000
RELEVE_AUDIO = "2024-01-02T03:04:30+00:00"
RELEVE_CHARGEMENT = "2024-01-02T03:04:10+00:00"
EMPREINTE = "c" * 64

RESUME_BLOC = "<summary>Contexte de l'ordinateur</summary>"
#: Fin du bloc dans la page de détail : la section suivante de l'exécution.
FIN_BLOC_DETAIL = "<h2>Informations sur l'exécution</h2>"
RESUME_BRUT = "<summary>Valeurs brutes et méthode</summary>"
AIDE = "inclut les autres programmes"
VALEUR_ABSENTE = (
    '<span class="resultat-valeur resultat-valeur-absente">non mesuré</span>'
)

#: Valeur d'un argument d'écriture qui laisse la clé absente du fichier :
#: distincte de `None`, qui écrit une clé présente et nulle (objet écarté).
ABSENT = object()


def observation_reelle_audio() -> dict[str, Any]:
    """Observation réelle de fin d'audio : 90 %, 5,2 Go disponibles sur 16 Go."""
    return observation(
        provenance=PROVENANCE_REELLE,
        cpu=cpu_systeme(pourcentage=90.0, intervalle=1.2),
        memoire=memoire_systeme(
            releve_le=RELEVE_AUDIO,
            totale=TOTAL_OCTETS,
            disponible=DISPONIBLE_AUDIO,
        ),
    )


def observation_reelle_chargement() -> dict[str, Any]:
    """Observation réelle après chargement : 7 Go disponibles sur 16 Go."""
    return observation(
        provenance=PROVENANCE_REELLE,
        memoire=memoire_systeme(
            releve_le=RELEVE_CHARGEMENT,
            totale=TOTAL_OCTETS,
            disponible=DISPONIBLE_CHARGEMENT,
        ),
    )


class ContexteOrdinateurTest(SocleWebTest):
    """Rendu du bloc, absences, faux calculs, listes et scénario simulé."""

    def ecrire_essai(
        self,
        identifiant: str = IDENTIFIANT,
        *,
        audio: Any = ABSENT,
        chargement: Any = ABSENT,
        simule: bool = False,
        modele: str | None = None,
    ) -> None:
        """Écrit un essai d'un audio avec les observations demandées.

        `ABSENT` laisse la clé hors du fichier (résultat antérieur), `None`
        l'écrit nulle (objet écarté à l'écriture). `simule` règle les marques
        de l'essai et la provenance attendue à la lecture.
        """
        mesures: dict[str, Any] = {
            "duree_operation_s": 12.5,
            "duree_processus_s": 11.0,
            "duree_chargement_s": 2.0,
            "pic_memoire_octets": PIC_MOTEUR,
            "pic_memoire_partiel": False,
        }
        if chargement is not ABSENT:
            mesures[CLE_OBSERVATION_CHARGEMENT] = chargement
        run = run_json(
            identifiant,
            mesures=mesures,
            factice=simule,
            mesures_simulees=simule,
            synthetique=simule,
        )
        if modele is not None:
            run["demande"]["modele"]["identifiant"] = modele
        mesures_audio: dict[str, Any] = {"pic_memoire_octets": PIC_MOTEUR}
        if audio is not ABSENT:
            mesures_audio[CLE_OBSERVATION_AUDIO] = audio
        resultat = result_json(
            run["audios"][0],
            execution=identifiant,
            mesures_extra=mesures_audio,
            factice=simule,
            mesures_simulees=simule,
            synthetique=simule,
        )
        ecrire_execution(self.dossier_data, run, (resultat,))

    def corps(self, chemin: str) -> str:
        """Corps brut d'une page rendue, après contrôle HTML local."""
        reponse = self.client.get(chemin, base_url=self.base_url())
        self.assertEqual(reponse.status_code, 200, chemin)
        corps = reponse.get_data(as_text=True)
        assert_html_seul(self, corps)
        return corps

    def page_detail(self, identifiant: str = IDENTIFIANT) -> str:
        return self.corps(f"/resultats/{identifiant}")

    def chemin_comparaison(self) -> str:
        return (
            f"/resultats/comparaison/{EMPREINTE}"
            f"?transcription={IDENTIFIANT}:1"
            f"&transcription={IDENTIFIANT_ANCIEN}:1"
        )

    def bloc(self, corps: str, fin: str = FIN_BLOC_DETAIL) -> str:
        """Bloc « Contexte de l'ordinateur », sans le reste de la page."""
        debut = corps.index(RESUME_BLOC)
        return corps[debut : corps.index(fin, debut)]

    def valeurs_premier_niveau(self, corps: str) -> str:
        """Valeurs lisibles de la première entrée, avant ses valeurs brutes."""
        bloc = self.bloc(corps)
        return bloc[: bloc.index(RESUME_BRUT)]

    def ecrire_observation_complete(self) -> None:
        self.ecrire_essai(
            audio=observation_reelle_audio(),
            chargement=observation_reelle_chargement(),
        )

    def test_libelles_et_valeurs_du_bloc_dans_le_detail(self) -> None:
        self.ecrire_observation_complete()

        corps = self.page_detail()
        bloc = self.bloc(corps)
        premier_niveau = self.valeurs_premier_niveau(corps)
        brutes = bloc[bloc.index(RESUME_BRUT) :]

        # Bloc secondaire repliable, fermé par défaut et sans JavaScript :
        # la balise `details` ne porte aucun attribut, donc aucun `open`.
        self.assertIn("<details>\n" + RESUME_BLOC, corps)
        # Une seule phrase d'aide, explicite sur les autres programmes.
        self.assertEqual(bloc.count(AIDE), 1)
        self.assertIn("instantané relevé après l'audio", premier_niveau)

        # CPU global moyen, explicité comme incluant les autres programmes.
        self.assertIn("<h3>Audio 1 — a.wav</h3>", bloc)
        self.assertIn("CPU total moyen pendant la transcription", premier_niveau)
        self.assertIn("90 %", premier_niveau)
        # RAM disponible après l'audio, avec la capacité du même instant.
        self.assertIn("RAM disponible après l'audio", premier_niveau)
        self.assertIn("5,2 Go sur 16 Go", premier_niveau)
        # Relevé après chargement, dans le même niveau secondaire.
        self.assertIn("<h3>Après chargement du modèle</h3>", bloc)
        apres_chargement = bloc[bloc.index("<h3>Après chargement du modèle</h3>") :]
        self.assertIn("RAM disponible après chargement", apres_chargement)
        self.assertIn("7 Go sur 16 Go", apres_chargement)

        # Les valeurs brutes restent au second niveau, avec la méthode.
        self.assertEqual(bloc.count(RESUME_BRUT), 2)
        for valeur in (
            "90.000 % sur 0 à 100",
            "1.200 s",
            f"{DISPONIBLE_AUDIO} octets",
            f"{TOTAL_OCTETS} octets",
            f"{DISPONIBLE_CHARGEMENT} octets",
            "psutil-cpu-percent-nonbloquant-v1",
            "7.2.2",
            RELEVE_AUDIO,
            RELEVE_CHARGEMENT,
        ):
            self.assertIn(valeur, brutes)
        # Aucune valeur brute (trois décimales, octets) au premier niveau.
        for valeur in ("90.000", str(DISPONIBLE_AUDIO), "1.200", "octets"):
            self.assertNotIn(valeur, premier_niveau)

        # Les indicateurs moteur gardent leur place, distincts du contexte :
        # aucune valeur système avant le bloc, qui reste après les audios.
        avant_bloc = corps[: corps.index(RESUME_BLOC)]
        self.assertIn('<span class="resultat-libelle">CPU moteur</span>', avant_bloc)
        self.assertIn('<span class="resultat-libelle">RAM moteur</span>', avant_bloc)
        self.assertNotIn("CPU total", avant_bloc)
        self.assertNotIn("90 %", avant_bloc)
        self.assertLess(corps.rindex("</article>"), corps.index(RESUME_BLOC))
        self.assertEqual(avant_bloc.count('<div class="resultat-compact">'), 1)

    def test_non_mesure_pour_chaque_etat_de_lecture(self) -> None:
        cas: tuple[tuple[str, dict[str, Any]], ...] = (
            # Fichier antérieur aux observations : clés absentes.
            ("absent", {}),
            # Objet écarté avant écriture : clé présente et nulle.
            ("ecarte", {"audio": None, "chargement": None}),
            (
                "invalide",
                {
                    "audio": {
                        "version": 1,
                        "methode_cpu": "methode-inconnue",
                        "version_psutil": "7.2.2",
                        "provenance": "simulee",
                        "cpu": cpu_systeme(),
                        "memoire_apres": memoire_systeme(),
                    },
                    "chargement": {"version": 1, "provenance": "simulee"},
                },
            ),
            (
                "version_inconnue",
                {
                    "audio": observation(version=2, cpu=cpu_systeme()),
                    "chargement": observation(version=2),
                },
            ),
        )
        for nom, options in cas:
            with self.subTest(etat=nom):
                # Le même identifiant est réécrit : chaque cas part de son
                # propre fichier, sans relire l'état du cas précédent.
                self.ecrire_essai(
                    simule=nom in ("invalide", "version_inconnue"), **options
                )

                corps = self.page_detail()
                bloc = self.bloc(corps)
                premier_niveau = self.valeurs_premier_niveau(corps)

                # Un seul rendu « non mesuré » par valeur, jamais zéro ni ratio :
                # CPU total, RAM après l'audio et RAM après chargement.
                self.assertEqual(bloc.count(VALEUR_ABSENTE), 3, bloc)
                self.assertNotIn("Go sur", premier_niveau)
                self.assertNotIn("octets", premier_niveau)

                # Le motif court reste au second niveau, jamais une valeur inventée.
                self.assertIn("Motif du relevé après l'audio", bloc)
                self.assertIn("Motif du relevé après chargement", bloc)
                attendus = {
                    "absent": "aucun relevé consigné",
                    "ecarte": "relevé écarté avant écriture",
                    "invalide": "relevé hors contrat",
                    "version_inconnue": "version de relevé non prise en charge",
                }
                self.assertIn(attendus[nom], bloc)

    def test_aucun_faux_calcul_de_marge_ni_de_part_autres(self) -> None:
        self.ecrire_observation_complete()

        corps = html.unescape(self.page_detail())

        # Ni total moins pic (13,6 Go), ni total moins disponible (10,8 Go),
        # ni disponible moins pic (2,8 Go), ni total moins RSS.
        for faux in ("13,6", "10,8 Go", "2,8 Go", "15,9 Go", "13.6", "10800000000"):
            self.assertNotIn(faux, corps)
        for interdit in (
            "marge",
            "part autres applications",
            "autres applications",
            "RAM restante",
            "minimum disponible",
            "RSS",
        ):
            self.assertNotIn(interdit.lower(), corps.lower())

        # Le pic du moteur et la RAM disponible restent deux informations.
        self.assertIn("2,4 Go", corps)
        self.assertIn("5,2 Go sur 16 Go", corps)

    def test_listes_sans_colonne_systeme_ni_classement(self) -> None:
        self.ecrire_observation_complete()

        for chemin in ("/resultats", "/resultats/comparaison"):
            with self.subTest(chemin=chemin):
                corps = self.corps(chemin)
                self.assertNotIn(RESUME_BLOC, corps)
                self.assertNotIn("CPU total", corps)
                self.assertNotIn("RAM disponible après", corps)
                self.assertNotIn("Contexte de l'ordinateur", corps)
                # Aucun critère de tri supplémentaire sur ces valeurs.
                for libelle in LIBELLES_TRI.values():
                    self.assertIn(libelle, corps)
                criteres = set(re.findall(r"[?&]tri=([a-z]+)", corps))
                self.assertLessEqual(criteres, set(LIBELLES_TRI), corps)

        # Les liens et ancres existants restent intacts.
        liste = self.corps("/resultats")
        self.assertIn(f'href="/resultats/{IDENTIFIANT}#audio-1"', liste)
        detail = self.page_detail()
        self.assertIn('id="audio-1"', detail)

    def test_comparaison_bloc_par_audio_sans_colonne_systeme(self) -> None:
        self.ecrire_essai(
            audio=observation_reelle_audio(),
            chargement=observation_reelle_chargement(),
            modele="organisation/modele-a",
        )
        self.ecrire_essai(IDENTIFIANT_ANCIEN, modele="organisation/modele-b")

        corps = self.corps(self.chemin_comparaison())

        # Un seul bloc secondaire, une entrée par transcription comparée.
        self.assertEqual(corps.count(RESUME_BLOC), 1)
        bloc = self.bloc(corps, fin="</main>")
        self.assertIn("<h3>modele-a</h3>", bloc)
        self.assertIn("<h3>modele-b</h3>", bloc)
        premiere = bloc[: bloc.index("<h3>modele-b</h3>")]
        self.assertIn("90 %", premiere)
        self.assertIn("5,2 Go sur 16 Go", premiere)
        self.assertIn("7 Go sur 16 Go", premiere)
        seconde = bloc[bloc.index("<h3>modele-b</h3>") :]
        self.assertEqual(seconde.count(VALEUR_ABSENTE), 3, seconde)

        # Aucune colonne système dans le tableau des mesures comparées.
        tableau = corps[corps.index("<table>") : corps.index("</table>")]
        self.assertNotIn("CPU total", tableau)
        self.assertNotIn("RAM disponible après", tableau)

        # Les ancres vers le détail et le texte comparé restent en place.
        self.assertIn(f'href="/resultats/{IDENTIFIANT}#audio-1"', corps)
        self.assertEqual(corps.count("Texte transcrit"), 2)

    def test_observation_simulee_jamais_presentee_comme_reelle(self) -> None:
        self.ecrire_essai(
            audio=observation(cpu=cpu_systeme(pourcentage=42.0, intervalle=1.0)),
            chargement=observation(),
            simule=True,
        )

        corps = self.page_detail()
        bloc = self.bloc(corps)

        # Marquage explicite du scénario, cohérent avec les marques de l'essai.
        self.assertIn("Scénario simulé", bloc)
        self.assertIn("FACTICE", corps)
        # La date constante de scénario n'est jamais affichée comme un relevé.
        self.assertNotIn("1970", corps)
        self.assertNotIn(SIMULATION_RELEVE_LE, corps)
        self.assertIn("date de scénario simulé, non réelle", bloc)
        # Les valeurs du scénario restent lisibles, marquées comme telles.
        self.assertIn("42 %", bloc)

    def test_bloc_repliable_sans_javascript(self) -> None:
        self.ecrire_observation_complete()

        corps = self.page_detail()
        bloc = self.bloc(corps)

        self.assertNotIn("<script", bloc)
        self.assertIsNone(re.search(r"\son[a-z]+\s*=", bloc))
        self.assertNotIn("style=", bloc)
        self.assertIn(RESUME_BLOC, bloc)
        self.assertIn("<details>\n" + RESUME_BRUT, bloc)
        # Contenu de texte courant : prose sur les paragraphes et la liste.
        self.assertIn('<p class="prose small">', bloc)
        self.assertIn('<dl class="prose">', bloc)

    def test_motif_cpu_au_second_niveau_premier_non_mesure(self) -> None:
        # CPU indisponible (fenêtre trop courte) : « non mesuré » au premier
        # niveau, le motif écrit et la fenêtre observée restent au second.
        self.ecrire_essai(
            audio=observation(
                provenance=PROVENANCE_REELLE,
                cpu=cpu_systeme(
                    pourcentage=None,
                    intervalle=0.05,
                    motif="intervalle_trop_court",
                ),
                memoire=memoire_systeme(
                    releve_le=RELEVE_AUDIO,
                    totale=TOTAL_OCTETS,
                    disponible=DISPONIBLE_AUDIO,
                ),
            ),
        )

        corps = self.page_detail()
        premier = self.valeurs_premier_niveau(corps)
        bloc = self.bloc(corps)

        self.assertIn(VALEUR_ABSENTE, premier)
        self.assertIn("intervalle de mesure trop court", bloc)
        self.assertIn("0.050 s", bloc)

    def test_memoire_partielle_affiche_non_mesure_et_motif(self) -> None:
        # Seul le total est valide : jamais « X sur indisponible » ni une
        # valeur partielle ; le motif reste au second niveau.
        self.ecrire_essai(
            audio=observation_reelle_audio(),
            chargement=observation(
                provenance=PROVENANCE_REELLE,
                memoire=memoire_systeme(
                    releve_le=RELEVE_CHARGEMENT,
                    totale=TOTAL_OCTETS,
                    disponible=None,
                    motif="valeur_incoherente",
                ),
            ),
        )

        corps = self.page_detail()
        bloc = self.bloc(corps)
        section = bloc[bloc.index("Après chargement du modèle") :]

        self.assertIn(VALEUR_ABSENTE, section)
        # Jamais « X sur Y » quand une des deux valeurs manque.
        self.assertNotIn(" sur ", section)
        self.assertIn("valeur du compteur incohérente", section)

    def test_valeur_hors_bornes_ne_montre_jamais_sur_indisponible(self) -> None:
        # Totale hors bornes d'affichage (fichier hostile) : « non mesuré » et
        # jamais « … sur indisponible ».
        self.ecrire_essai(
            audio=observation_reelle_audio(),
            chargement=observation(
                provenance=PROVENANCE_REELLE,
                memoire=memoire_systeme(
                    releve_le=RELEVE_CHARGEMENT,
                    totale=10**400,
                    disponible=DISPONIBLE_CHARGEMENT,
                ),
            ),
        )

        corps = self.page_detail()
        bloc = self.bloc(corps)
        section = bloc[bloc.index("Après chargement du modèle") :]

        self.assertNotIn("sur indisponible", section)
        self.assertIn(VALEUR_ABSENTE, section)

    def test_motif_inconnu_ne_fuit_jamais(self) -> None:
        # Un motif hors des codes écrits rend l'objet hors contrat à la lecture :
        # le code reçu ne s'affiche nulle part, un libellé fixe le remplace.
        self.ecrire_essai(
            audio=observation(
                provenance=PROVENANCE_REELLE,
                cpu=cpu_systeme(
                    pourcentage=None, intervalle=1.2, motif="code-sauvage"
                ),
                memoire=memoire_systeme(
                    releve_le=RELEVE_AUDIO,
                    totale=TOTAL_OCTETS,
                    disponible=DISPONIBLE_AUDIO,
                ),
            ),
        )

        corps = self.page_detail()

        self.assertNotIn("code-sauvage", corps)
        self.assertIn("relevé hors contrat", self.bloc(corps))
