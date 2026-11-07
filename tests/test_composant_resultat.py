"""Rendu du composant compact de résultat (tâche 1.3, design D2, D3 et D6).

Le composant `composants.html` n'est branché sur aucune page ici : il est rendu
dans le squelette commun (`base.html`) par un gabarit de test, afin que le
contrôle HTML existant (`assert_html_seul`) s'applique. Les valeurs passent par
les formateurs de premier niveau de `indicateurs_resultats`, jamais par une
réécriture locale. Aucun moteur, aucun réseau, aucune donnée réelle.
"""

from __future__ import annotations

import html
import re
import tempfile
import unittest
from pathlib import Path

from tests.outils_html import assert_html_seul
from transcription_bench.consultation_resultats import IndicateursAudio
from transcription_bench.operations import CreneauOperations
from transcription_bench.web import (
    ConfigApplication,
    ServicesApplication,
    create_app,
)

BASE = "http://127.0.0.1:8765"

# Gabarit de test : le composant est rendu dans le squelette commun, avec le
# titre de groupe qui le précède dans une vraie page.
GABARIT_DE_TEST = (
    '{% extends "base.html" %}'
    '{% import "composants.html" as composants %}'
    "{% block titre %}Composant — test{% endblock %}"
    "{% block contenu %}"
    "<h1>Composant</h1>"
    "{{ composants.entete_groupe_audio(groupe.nom, groupe.duree_audio_s) }}"
    "{{ composants.resultat_compact(resultat) }}"
    "{% endblock %}"
)

INDICATEURS_COURANTS = {
    "duree_transcription_s": 97,
    "pic_memoire_octets": 2_400_000_000,
    "ram_totale_octets": 16_000_000_000,
    "temps_cpu_s": 48.0,
    "part_ram": 15.0,
    "occupation_cpu": 50.0,
}
RESULTAT_COURANT = {
    "modele": "whisper-large-v3-turbo",
    "moteur": "faster-whisper",
    "date_essai": "2026-11-06T14:20:00",
    "variante": None,
    "indicateurs": INDICATEURS_COURANTS,
    "annotation_ram": None,
    "materiel_alerte": None,
    "etats": [],
}
GROUPE_COURANT = {"nom": "entretien.wav", "duree_audio_s": 180}


def textes(corps: str, classe: str) -> list[str]:
    """Textes des éléments portant exactement cette classe, dans l'ordre."""
    motif = rf'<(\w+) class="{re.escape(classe)}(?: [^"<>]*)?">([^<]*)</\1>'
    return [html.unescape(texte) for _, texte in re.findall(motif, corps)]


def bloc_mesure(corps: str, nom: str) -> str:
    """Corps du bloc d'une mesure (`temps`, `ram` ou `cpu`)."""
    trouve = re.search(
        rf'<div class="resultat-mesure resultat-mesure-{nom}">(.*?)</div>',
        corps,
        re.S,
    )
    if trouve is None:
        raise AssertionError(f"bloc de mesure absent : {nom}")
    return trouve.group(1)


def valeur_mesure(corps: str, nom: str) -> str:
    """Valeur affichée d'une mesure, sans autre texte du bloc."""
    valeurs = textes(bloc_mesure(corps, nom), "resultat-valeur")
    if len(valeurs) != 1:
        raise AssertionError(f"une seule valeur attendue pour {nom} : {valeurs}")
    return valeurs[0]


class ComposantResultatTest(unittest.TestCase):
    """Rendu du composant : unités, absences, invalides, variantes et états."""

    def setUp(self) -> None:
        temporaire = tempfile.TemporaryDirectory()
        self.addCleanup(temporaire.cleanup)
        self.app = create_app(
            ConfigApplication(port=8765, dossier_data=Path(temporaire.name) / "data"),
            ServicesApplication(creneau=CreneauOperations()),
        )

    def rendre(self, resultat: object, groupe: dict | None = None) -> str:
        """Page de test rendue dans le squelette commun, contrôle HTML compris."""
        with self.app.test_request_context("/", base_url=BASE):
            modele = self.app.jinja_env.from_string(GABARIT_DE_TEST)
            corps = modele.render(resultat=resultat, groupe=groupe or GROUPE_COURANT)
        assert_html_seul(self, corps)
        return corps

    def resultat(self, **surcharges: object) -> dict:
        """Copie du résultat courant ; `indicateurs` remplace le bloc entier."""
        return {**RESULTAT_COURANT, **surcharges}

    def test_valeurs_courantes_du_premier_niveau(self) -> None:
        corps = self.rendre(self.resultat())

        self.assertEqual(textes(corps, "resultat-modele"), ["whisper-large-v3-turbo"])
        self.assertEqual(valeur_mesure(corps, "temps"), "1 min 37 s")
        self.assertEqual(valeur_mesure(corps, "ram"), "2,4 Go")
        self.assertEqual(valeur_mesure(corps, "cpu"), "50 %")
        secondaires = textes(corps, "resultat-secondaire")
        # Moteur et date ont chacun leur bloc étiqueté sur la ligne bureau.
        self.assertIn("faster-whisper", secondaires)
        self.assertIn("06/11/2026 14:20", secondaires)
        self.assertIn("Audio : 3 min", textes(corps, "resultat-secondaire"))

    def test_unites_des_durees_memoires_et_cpu(self) -> None:
        cas = (
            ({"duree_transcription_s": 0}, "temps", "0 s"),
            ({"duree_transcription_s": 0.4}, "temps", "0,4 s"),
            ({"duree_transcription_s": 0.05}, "temps", "< 0,1 s"),
            ({"duree_transcription_s": 59.9}, "temps", "59 s"),
            ({"duree_transcription_s": 60}, "temps", "1 min"),
            ({"duree_transcription_s": 3600}, "temps", "1 h"),
            ({"duree_transcription_s": 3725}, "temps", "1 h 2 min"),
            ({"pic_memoire_octets": 0}, "ram", "0 Mo"),
            ({"pic_memoire_octets": 50_000}, "ram", "< 0,1 Mo"),
            ({"pic_memoire_octets": 150_000_000}, "ram", "150 Mo"),
            ({"pic_memoire_octets": 1_500_000_000}, "ram", "1,5 Go"),
            ({"occupation_cpu": 0}, "cpu", "0 %"),
            ({"occupation_cpu": 0.4}, "cpu", "< 1 %"),
            ({"occupation_cpu": 50.7}, "cpu", "50 %"),
        )
        for indicateurs, mesure, attendu in cas:
            with self.subTest(indicateurs=indicateurs):
                corps = self.rendre(self.resultat(indicateurs=indicateurs))
                self.assertEqual(valeur_mesure(corps, mesure), attendu)

    def test_valeurs_non_mesurees_et_champs_non_consignes(self) -> None:
        corps = self.rendre(
            self.resultat(
                modele=None,
                moteur=None,
                date_essai=None,
                indicateurs={
                    "duree_transcription_s": None,
                    "pic_memoire_octets": None,
                    "occupation_cpu": None,
                    "temps_cpu_s": None,
                },
            ),
            groupe={"nom": None, "duree_audio_s": None},
        )

        self.assertEqual(valeur_mesure(corps, "temps"), "non mesuré")
        self.assertEqual(valeur_mesure(corps, "ram"), "non mesuré")
        self.assertEqual(valeur_mesure(corps, "cpu"), "non mesuré")
        self.assertEqual(textes(corps, "resultat-modele"), ["modèle non consigné"])
        secondaire = " ".join(textes(corps, "resultat-secondaire"))
        self.assertIn("moteur non consigné", secondaire)
        self.assertIn("date non consignée", secondaire)
        self.assertEqual(textes(corps, "resultat-audio"), ["fichier non consigné"])
        self.assertIn("Audio : non mesuré", secondaire)

    def test_bloc_indicateurs_absent_ou_null_reste_lisible(self) -> None:
        for resultat in ({}, self.resultat(indicateurs=None)):
            with self.subTest(resultat=resultat):
                corps = self.rendre(resultat)
                for mesure in ("temps", "ram", "cpu"):
                    self.assertEqual(valeur_mesure(corps, mesure), "non mesuré")

    def test_valeurs_invalides_donnent_indisponible_sans_zero(self) -> None:
        corps = self.rendre(
            self.resultat(
                indicateurs={
                    "duree_transcription_s": "abc",
                    "pic_memoire_octets": -5,
                    "occupation_cpu": True,
                }
            )
        )

        self.assertEqual(valeur_mesure(corps, "temps"), "indisponible")
        self.assertEqual(valeur_mesure(corps, "ram"), "indisponible")
        self.assertEqual(valeur_mesure(corps, "cpu"), "indisponible")
        self.assertNotIn(">0 s<", corps)
        self.assertNotIn(">0 Mo<", corps)

    def test_absences_distinguees_des_valeurs_mesurees(self) -> None:
        corps = self.rendre(self.resultat(indicateurs={}))
        self.assertEqual(len(textes(corps, "resultat-valeur resultat-valeur-absente")), 3)
        mesure = self.rendre(self.resultat())
        self.assertNotIn("resultat-valeur-absente", mesure)

    def test_cpu_non_interpretable_quand_seul_le_temps_cpu_est_consigne(self) -> None:
        corps = self.rendre(
            self.resultat(indicateurs={"occupation_cpu": None, "temps_cpu_s": 12.0})
        )

        self.assertEqual(valeur_mesure(corps, "cpu"), "non interprétable")

    def test_objets_indicateurs_du_service_acceptes(self) -> None:
        # Le contrat du service (`IndicateursAudio`, dataclass) donne le même rendu
        # qu'un mapping de mêmes clés.
        indicateurs = IndicateursAudio(
            duree_transcription_s=97,
            pic_memoire_octets=2_400_000_000,
            ram_totale_octets=16_000_000_000,
            temps_cpu_s=48.0,
            part_ram=15.0,
            occupation_cpu=50.0,
        )
        objet = self.rendre(self.resultat(indicateurs=indicateurs))
        mapping = self.rendre(self.resultat())

        self.assertEqual(objet, mapping)

    def test_valeurs_longues_gardees_en_entier(self) -> None:
        modele = "-".join(["modele-tres-long-variante"] * 6)
        variante = "variante-" * 12
        corps = self.rendre(
            self.resultat(
                modele=modele,
                variante=variante.strip("-"),
                moteur="moteur-" * 10,
            )
        )

        self.assertEqual(textes(corps, "resultat-modele"), [modele])
        self.assertIn(variante.strip("-"), html.unescape(corps))
        self.assertNotIn("<table", corps)
        self.assertNotIn("overflow-auto", corps)

    def test_ram_cumulative_signalee_brievement(self) -> None:
        annotation = (
            "Pic mémoire cumulatif du lot : il peut provenir d'un audio précédent "
            "et inclut le chargement du modèle."
        )
        corps = self.rendre(self.resultat(annotation_ram=annotation))

        self.assertIn("pic cumulatif", bloc_mesure(corps, "ram"))
        # La phrase longue reste dans le détail : jamais répétée par carte.
        self.assertNotIn("peut provenir d'un audio précédent", html.unescape(corps))

    def test_ram_cumulative_absente_sans_annotation_ou_sans_pic(self) -> None:
        sans_annotation = self.rendre(self.resultat())
        self.assertNotIn("pic cumulatif", sans_annotation)

        sans_pic = self.rendre(
            self.resultat(
                annotation_ram="Pic mémoire non isolé par audio.",
                indicateurs={"pic_memoire_octets": None},
            )
        )
        self.assertNotIn("pic cumulatif", bloc_mesure(sans_pic, "ram"))
        self.assertEqual(valeur_mesure(sans_pic, "ram"), "non mesuré")

    def test_etats_et_alerte_materiel_restent_visibles(self) -> None:
        corps = self.rendre(
            self.resultat(
                etats=["partiel", "factice", "erreur"],
                materiel_alerte="matériel différent",
            )
        )

        self.assertEqual(
            textes(corps, "resultat-etat"), ["partiel", "factice", "erreur"]
        )
        self.assertIn("matériel différent", textes(corps, "resultat-alerte"))

    def test_modele_lie_au_detail_et_variante_distincte(self) -> None:
        corps = self.rendre(
            self.resultat(
                lien="/resultats/20240102-030405-0a0b0c0d",
                variante="modele-q4.gguf",
                duree_audio="Audio : 2 s",
            )
        )

        self.assertIn(
            '<a class="resultat-modele" href="/resultats/20240102-030405-0a0b0c0d">'
            "whisper-large-v3-turbo</a>",
            corps,
        )
        self.assertIn("Variante : modele-q4.gguf", corps)
        self.assertIn("Audio : 2 s", corps)

    def test_bloc_moteur_et_date_sans_valeur(self) -> None:
        corps = self.rendre(self.resultat(moteur=None, date_essai=None))

        self.assertIn("moteur non consigné", corps)
        self.assertIn("date non consignée", corps)

    def test_sans_etat_ni_alerte_aucun_bloc_vide(self) -> None:
        corps = self.rendre(self.resultat())

        self.assertNotIn("resultat-etats", corps)
        self.assertNotIn("resultat-etat", corps)
        self.assertNotIn("matériel", corps)

    def test_valeurs_echappees_sans_balise_active(self) -> None:
        corps = self.rendre(
            self.resultat(modele="<script>alert(1)</script>", moteur="<b>x</b>")
        )

        self.assertNotIn("<script>alert", corps)
        self.assertNotIn("<b>x</b>", corps)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", corps)

    def test_composant_sans_table_ni_style_ni_paragraphe(self) -> None:
        corps = self.rendre(self.resultat(etats=["partiel"]))

        bloc = corps[corps.index('class="resultat-compact"') :]
        self.assertNotIn("<table", bloc)
        self.assertNotIn("<p", bloc)
        self.assertNotIn("style=", corps)
        self.assertNotIn("role=\"status\"", bloc)

    def test_en_tete_de_groupe_audio(self) -> None:
        corps = self.rendre(self.resultat(), groupe=GROUPE_COURANT)

        self.assertEqual(textes(corps, "resultat-audio"), ["entretien.wav"])
        self.assertIn("Audio : 3 min", textes(corps, "resultat-secondaire"))

    def test_case_de_selection_facultative_dans_la_cellule_modele(self) -> None:
        case = {
            "nom": "transcription",
            "valeur": "20240102-030405-0a0b0c0d:1",
            "libelle": "Sélectionner whisper-large-v3-turbo, audio 1",
            "coche": True,
        }

        corps = self.rendre(self.resultat(case=case))

        self.assertIn(
            '<input type="checkbox" name="transcription" '
            'value="20240102-030405-0a0b0c0d:1" '
            'aria-label="Sélectionner whisper-large-v3-turbo, audio 1" checked>',
            corps,
        )
        # La case précède le modèle dans la même ligne, sans colonne technique.
        self.assertLess(
            corps.index('<div class="resultat-entete">'),
            corps.index('<input type="checkbox"'),
        )
        self.assertLess(
            corps.index('<input type="checkbox"'),
            corps.index('<span class="resultat-modele">'),
        )
        self.assertNotIn("<table", corps)

        decochee = self.rendre(self.resultat(case={**case, "coche": False}))
        self.assertNotIn(" checked>", decochee)

    def test_sans_case_aucune_case_rendue(self) -> None:
        corps = self.rendre(self.resultat())

        self.assertNotIn("checkbox", corps)

    def test_distinctions_courtes_pres_des_valeurs(self) -> None:
        corps = self.rendre(
            self.resultat(
                distinction_temps="meilleur temps",
                distinction_ram="meilleure RAM (égalité)",
            )
        )

        self.assertEqual(
            textes(corps, "resultat-distinction"),
            ["meilleur temps", "meilleure RAM (égalité)"],
        )
        # Chaque libellé reste dans le bloc de sa mesure ; le CPU n'en reçoit pas.
        self.assertIn("meilleur temps", bloc_mesure(corps, "temps"))
        self.assertIn("meilleure RAM (égalité)", bloc_mesure(corps, "ram"))
        self.assertNotIn("distinction", bloc_mesure(corps, "cpu"))

    def test_sans_distinction_aucun_libelle(self) -> None:
        corps = self.rendre(self.resultat())

        self.assertNotIn("resultat-distinction", corps)

    def test_distinction_echappee_sans_balise_active(self) -> None:
        corps = self.rendre(
            self.resultat(distinction_temps="<script>alert(1)</script>")
        )

        self.assertNotIn("<script>alert", corps)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", corps)


if __name__ == "__main__":
    unittest.main()
