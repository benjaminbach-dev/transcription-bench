"""Tests de l'habillage Sumi : squelette, navigation, classes et encarts.

Lot 2 : squelette et classes ; lot 5 : cartes (`article`), accordéons
(`details`/`summary`) et grilles, sans JavaScript.

Les gabarits sont contrôlés de deux façons : analyse statique des classes
littérales et des balises écrites dans `transcription_bench/web/templates/`, et
analyse des pages réellement rendues avec `tests/outils_html.py` (fondée sur
`html.parser`). Aucune installation, aucun poids, aucune inférence, aucun réseau.
"""

from __future__ import annotations

import re
import threading
import unittest
from html import unescape
from html.parser import HTMLParser
from pathlib import Path

from tests.outils_html import ELEMENTS_INTERDITS, assert_html_seul
from tests.test_comparaison_resultats import EMPREINTE_A, resultat_empreinte
from tests.test_feuilles import lire_feuille, regles
from tests.test_consultation_resultats import (
    IDENTIFIANT,
    IDENTIFIANT_ANCIEN,
    ecrire_execution,
    result_json,
    run_json,
)
from tests.test_web import SocleWebTest
from transcription_bench.web.app import NOM_FEUILLE_APP

DOSSIER_GABARITS = (
    Path(__file__).resolve().parents[1]
    / "transcription_bench"
    / "web"
    / "templates"
)

# Design D3 : seules ces classes Sumi, plus `danger` sur un bouton, sont employées.
CLASSES_AUTORISEES = frozenset(
    {
        "overflow-auto",
        "grid",
        "cols-2",
        "cols-3",
        "callout",
        "warning",
        "danger",
        "success",
        "secondary",
        "contrast",
        "outline",
        "muted",
        "small",
        "narrow",
        "prose",
    }
)

# Tâche 1.3 : classes du composant de résultat. Elles ne sont admises que dans
# `composants.html`, qui doit les employer toutes, et doivent avoir une règle
# dans `app.css` : aucune classe orpheline ni inventée dans un autre gabarit.
GABARIT_COMPOSANT = "composants.html"
CLASSES_COMPOSANT_RESULTAT = frozenset(
    {
        "resultat-compact",
        "resultat-titre",
        "resultat-entete",
        "resultat-tris",
        "resultat-groupe",
        "resultat-modele",
        "resultat-audio",
        "resultat-secondaire",
        "resultat-libelle",
        "resultat-mesures",
        "resultat-mesure",
        "resultat-mesure-temps",
        "resultat-mesure-ram",
        "resultat-mesure-cpu",
        "resultat-valeur",
        "resultat-valeur-absente",
        "resultat-etats",
        "resultat-etat",
        "resultat-section",
        "resultat-alerte",
        "resultat-mesure-moteur",
        "resultat-mesure-date",
        "resultat-distinction",
    }
)
MOTIF_SELECTEUR_CLASSE = re.compile(r"\.([A-Za-z][\w-]*)")

# Liens de la navigation commune, dans l'ordre exigé par le design D1 : six
# rubriques, sans Accueil ni Opération (redirigées depuis la tâche 3.1).
LIENS_NAVIGATION = (
    ("/resultats", "Résultats"),
    ("/resultats/comparaison", "Comparaisons"),
    ("/executions", "Exécutions"),
    ("/modeles", "Modèles"),
    ("/moteurs", "Moteurs"),
    ("/audios", "Audios"),
)
CHEMIN_NAVIGATION = ("html", "body", "header", "nav")
CHEMIN_HEADER = ("html", "body", "header")

# Boutons destructeurs : seuls ceux-là portent la classe `danger`.
BOUTONS_DESTRUCTEURS = {
    "modeles.html": "Supprimer ce modèle local",
    "executions.html": "Arrêter l'exécution",
}

# Design D7 : un seul `h1` (titre de la page dans `main`), sous-titres sans
# saut de niveau ; le nom du programme n'est pas un titre.
NIVEAUX_TITRES = ("h1", "h2", "h3", "h4", "h5", "h6")

# Design D7 : boutons de simple contrôle (classe `secondary`) et actions
# principales (style primaire de Sumi, jamais `secondary`).
BOUTONS_SECONDAIRES = {
    "executions.html": ("Vérifier la demande (aucun lancement)",),
    "modeles.html": (
        "Vérifier la compatibilité sans télécharger",
        "Vérifier avec {{ candidat }}",
    ),
}
BOUTONS_PRIMAIRES = {
    "executions.html": ("Lancer l'exécution",),
    "modeles.html": ("Télécharger ce modèle à la révision vérifiée",),
    "moteurs.html": ("Installer ce moteur",),
    "comparaisons.html": ("Comparer les transcriptions sélectionnées",),
}

MOTIF_CLASSE = re.compile(r'class="([^"]*)"')
MOTIF_PARAGRAPHE = re.compile(r"<p\b[^>]*>")
MOTIF_LISTE = re.compile(r"<(?:ul|ol|dl)\b[^>]*>")
MOTIF_GESTIONNAIRE = re.compile(r"<[^>]*\son[a-z]+\s*=")
# Classes d'encart de Sumi : elles ne prennent effet que sur un `callout`.
CLASSES_D_ENCART = ("danger", "warning", "success")
MOTIF_BLOC_TITRE = re.compile(r"{%-?\s*block titre\s*-?%}")
MOTIF_BLOC_COURANTE = re.compile(
    r"{%-?\s*block page_courante\s*-?%}\s*([^{}%]*?)\s*{%-?\s*endblock"
)

DELAI = 5.0
IDENTIFIANT_DETAIL = "20240103-000000-0000dead"

# Design D8 : contenus qui restent visibles sans ouvrir d'accordéon.
CONTENU_TOUJOURS_VISIBLE = frozenset({"pre", "button"})
CLASSES_TOUJOURS_VISIBLES = frozenset({"danger", "warning"})


def gabarits() -> dict[str, str]:
    """Contenu des gabarits de l'interface, par nom de fichier."""
    return {
        chemin.name: chemin.read_text(encoding="utf-8")
        for chemin in sorted(DOSSIER_GABARITS.glob("*.html"))
    }


def classes_litterales(source: str) -> set[str]:
    """Classes écrites en dur dans un gabarit (les valeurs Jinja sont ignorées)."""
    classes: set[str] = set()
    for valeur in MOTIF_CLASSE.findall(source):
        if "{{" in valeur or "{%" in valeur:
            continue
        classes.update(valeur.split())
    return classes


def classes_de_balise(balise: str) -> set[str]:
    """Classes lues dans l'attribut `class` d'une balise d'une ligne."""
    return set(" ".join(MOTIF_CLASSE.findall(balise)).split())


class BlocDetails:
    """Un `details` d'une page rendue : état d'ouverture, résumé et contenu."""

    def __init__(self, ouvert: bool) -> None:
        self.ouvert = ouvert
        self.resume = ""
        self.balises: list[tuple[str, dict[str, str | None]]] = []


class AnalyseDetails(HTMLParser):
    """Blocs `details` d'une page rendue, dans l'ordre du document.

    `blocs` conserve, pour chaque `details`, s'il est ouvert (attribut `open`
    posé par le serveur), le texte de son `summary` et les balises qu'il
    contient. Sert à vérifier qu'aucun contenu à garder visible (erreur, marque,
    texte transcrit, bouton d'action) n'est enfermé dans un accordéon fermé.
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.blocs: list[BlocDetails] = []
        self._ouverts: list[BlocDetails] = []
        self._capture: list[str] | None = None

    def handle_starttag(self, tag, attrs) -> None:
        attributs = dict(attrs)
        if tag == "details":
            bloc = BlocDetails("open" in attributs)
            self.blocs.append(bloc)
            self._ouverts.append(bloc)
            return
        if tag == "summary":
            self._capture = []
            return
        for bloc in self._ouverts:
            bloc.balises.append((tag, attributs))

    def handle_startendtag(self, tag, attrs) -> None:
        if tag == "details":
            return
        self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag) -> None:
        if tag == "summary" and self._capture is not None:
            if self._ouverts:
                self._ouverts[-1].resume = " ".join(
                    "".join(self._capture).split()
                )
            self._capture = None
        elif tag == "details" and self._ouverts:
            self._ouverts.pop()

    def handle_data(self, data) -> None:
        if self._capture is not None:
            self._capture.append(data)


def analyser_details(corps: str) -> AnalyseDetails:
    """Analyse les `details` d'un corps de page rendue."""
    analyse = AnalyseDetails()
    analyse.feed(corps)
    analyse.close()
    return analyse


class GabaritsTest(unittest.TestCase):
    """Analyse statique des gabarits : classes, balises écrites, encarts."""

    def setUp(self) -> None:
        self.sources = gabarits()

    def test_tous_les_gabarits_de_page_sont_analyses(self) -> None:
        attendus = {
            "base.html",
            "audios.html",
            "comparaison.html",
            "comparaisons.html",
            "erreur.html",
            "executions.html",
            "journal.html",
            "modeles.html",
            "moteurs.html",
            "resultat.html",
            "resultats.html",
        }

        self.assertLessEqual(attendus, set(self.sources))

    def test_classes_litterales_sumi_ou_definies_dans_app_css(self) -> None:
        # Les composants applicatifs sont partagés entre pages : leur contrat
        # vient de la feuille locale, pas d'une ancienne liste fermée Sumi.
        definies = set(MOTIF_SELECTEUR_CLASSE.findall(lire_feuille(NOM_FEUILLE_APP)))
        for nom, source in self.sources.items():
            with self.subTest(gabarit=nom):
                self.assertLessEqual(
                    classes_litterales(source),
                    CLASSES_AUTORISEES | definies,
                    f"classe sans définition locale dans {nom}",
                )

    def test_classes_du_composant_utilisees_dans_les_gabarits(self) -> None:
        sources = "\n".join(self.sources.values())
        for classe in CLASSES_COMPOSANT_RESULTAT:
            self.assertIn(classe, sources)

    def test_classes_du_composant_definies_dans_app_css(self) -> None:
        feuille = regles(lire_feuille(NOM_FEUILLE_APP))
        definies: set[str] = set()
        for selecteur in feuille:
            definies.update(MOTIF_SELECTEUR_CLASSE.findall(selecteur))
        self.assertLessEqual(CLASSES_COMPOSANT_RESULTAT, definies)

    def test_aucun_element_ni_attribut_interdit(self) -> None:
        # `<script` n'est plus interdit en bloc : le squelette commun charge
        # l'unique script local `/app.js` en `defer` (design D6). Tout autre
        # script, incorporé ou non, reste refusé par le contrôle ci-dessous.
        interdits = ("<style", "<iframe", "<object", "<img", "<dialog")
        for nom, source in self.sources.items():
            with self.subTest(gabarit=nom):
                for interdit in interdits:
                    self.assertNotIn(interdit, source)
                self.assertNotIn("style=", source)
                self.assertNotIn("data-theme", source)
                self.assertNotIn("aria-busy", source)
                self.assertNotIn("aria-invalid", source)
                self.assertNotIn('role="button"', source)
                for ligne in source.splitlines():
                    self.assertIsNone(
                        MOTIF_GESTIONNAIRE.search(ligne),
                        f"attribut de gestionnaire d'événement dans {nom} : {ligne}",
                    )

        # Un seul gabarit écrit un script, une seule fois, avec le fichier local
        # en `defer` : ni script incorporé, ni fichier arbitraire ou distant.
        self.assertEqual(
            {
                nom: source.count("<script")
                for nom, source in self.sources.items()
                if "<script" in source
            },
            {"base.html": 1},
        )
        self.assertIn(
            '<script src="/app.js" defer></script>', self.sources["base.html"]
        )

    def test_deux_feuilles_locales_dans_l_ordre(self) -> None:
        base = self.sources["base.html"]

        self.assertEqual(base.count('href="/sumi.css"'), 1)
        self.assertEqual(base.count('href="/app.css"'), 1)
        self.assertLess(base.index("/sumi.css"), base.index("/app.css"))
        for nom, source in self.sources.items():
            if nom != "base.html":
                self.assertNotIn("<link", source, f"{nom} ne déclare pas de feuille")

    def test_chaque_tableau_dans_un_conteneur_defilant(self) -> None:
        for nom, source in self.sources.items():
            with self.subTest(gabarit=nom):
                lignes = [
                    ligne.strip() for ligne in source.splitlines() if ligne.strip()
                ]
                for position, ligne in enumerate(lignes):
                    if ligne == "<table>":
                        self.assertGreater(position, 0, nom)
                        self.assertRegex(
                            lignes[position - 1],
                            r'^<div class="overflow-auto"(?: [^<>]*)?>$',
                            f"tableau sans conteneur défilant dans {nom}",
                        )
                    if ligne == "</table>":
                        self.assertLess(position, len(lignes) - 1, nom)
                        self.assertEqual(lignes[position + 1], "</div>", nom)

    def test_prose_jamais_sur_main_ni_sur_un_tableau(self) -> None:
        for nom, source in self.sources.items():
            with self.subTest(gabarit=nom):
                self.assertNotRegex(source, r"<main[^>]*class=")
                self.assertNotRegex(source, r"<table[^>]*class=")
                for ligne in source.splitlines():
                    if 'class="prose"' in ligne or 'class="narrow"' in ligne:
                        self.assertNotIn("<main", ligne)
                        self.assertNotIn("<table", ligne)

    def test_role_status_conserve_dans_un_encart(self) -> None:
        # Aucun message d'état existant n'est retiré : chacun reste dans un encart.
        trouves = 0
        for nom, source in self.sources.items():
            for ligne in source.splitlines():
                if 'role="status"' in ligne:
                    trouves += 1
                    with self.subTest(gabarit=nom, ligne=ligne.strip()):
                        if 'data-champ="etat"' in ligne:
                            self.assertEqual(nom, "executions.html")
                        else:
                            self.assertIn("callout", ligne)
        self.assertEqual(trouves, 10)

    def test_classes_d_encart_seulement_sur_des_callouts(self) -> None:
        # D3 : `danger`, `warning` et `success` ne prennent effet que sur un
        # élément `callout` ; seul `danger` reste admis sur un bouton.
        for nom, source in self.sources.items():
            for ligne in source.splitlines():
                classes = set(" ".join(MOTIF_CLASSE.findall(ligne)).split())
                intrus = classes & set(CLASSES_D_ENCART)
                if not intrus:
                    continue
                with self.subTest(gabarit=nom, ligne=ligne.strip()):
                    if "callout" not in classes:
                        self.assertIn(
                            "<button", ligne, "classe d'encart hors d'un callout"
                        )
                        self.assertEqual(
                            intrus,
                            {"danger"},
                            "seule la classe danger est admise sur un bouton",
                        )

    def test_danger_seulement_sur_les_boutons_destructeurs(self) -> None:
        occurrences: dict[str, list[str]] = {}
        total = 0
        for nom, source in self.sources.items():
            for ligne in source.splitlines():
                if 'class="danger"' in ligne:
                    total += 1
                    occurrences.setdefault(nom, []).append(ligne.strip())

        self.assertEqual(total, len(BOUTONS_DESTRUCTEURS), occurrences)
        self.assertEqual(set(occurrences), set(BOUTONS_DESTRUCTEURS))
        for nom, libelle in BOUTONS_DESTRUCTEURS.items():
            (ligne,) = occurrences[nom]
            self.assertIn("<button", ligne, nom)
            self.assertIn(libelle, ligne, nom)
            self.assertEqual(ligne.count('class="danger"'), 1, nom)

    def test_bloc_page_courante_des_pages_de_premier_niveau(self) -> None:
        attendus = {
            "audios.html": "audios",
            "moteurs.html": "moteurs",
            "modeles.html": "modeles",
            "executions.html": "executions",
            "resultats.html": "resultats",
            "comparaisons.html": "comparaisons",
        }
        for nom, cle in attendus.items():
            with self.subTest(gabarit=nom):
                self.assertEqual(
                    MOTIF_BLOC_COURANTE.findall(self.sources[nom]), [cle], nom
                )

    def test_bloc_page_courante_des_sous_pages(self) -> None:
        attendus = {
            "resultat.html": "parent:resultats",
            "comparaison.html": "parent:comparaisons",
            "journal.html": "parent:moteurs",
        }
        for nom, cle in attendus.items():
            with self.subTest(gabarit=nom):
                self.assertEqual(
                    MOTIF_BLOC_COURANTE.findall(self.sources[nom]), [cle], nom
                )

    def test_page_erreur_sans_page_courante(self) -> None:
        self.assertEqual(MOTIF_BLOC_COURANTE.findall(self.sources["erreur.html"]), [])

    def test_chaque_page_a_son_titre(self) -> None:
        for nom, source in self.sources.items():
            if nom in ("base.html", "formats.html", GABARIT_COMPOSANT):
                # `base.html` porte le titre par défaut, `formats.html` et
                # `composants.html` sont des fichiers de macros sans page propre.
                continue
            with self.subTest(gabarit=nom):
                self.assertIsNotNone(MOTIF_BLOC_TITRE.search(source), nom)

    def test_base_sans_pied_de_page(self) -> None:
        self.assertNotIn("<footer", self.sources["base.html"])

    def test_tous_les_paragraphes_portent_prose(self) -> None:
        # Design D7 : largeur de lecture homogène, sur tous les paragraphes.
        for nom, source in self.sources.items():
            for balise in MOTIF_PARAGRAPHE.findall(source):
                with self.subTest(gabarit=nom, balise=balise.strip()):
                    self.assertIn("prose", classes_de_balise(balise), nom)

    def test_toutes_les_listes_de_texte_portent_prose(self) -> None:
        # Design D7 : listes et listes de définitions de texte courant. Les deux
        # `ul` de `base.html` sont ceux de la navigation : elles n'en portent pas.
        for nom, source in self.sources.items():
            if nom == "base.html":
                continue
            for balise in MOTIF_LISTE.findall(source):
                with self.subTest(gabarit=nom, balise=balise.strip()):
                    self.assertIn("prose", classes_de_balise(balise), nom)

    def lignes_de_bouton(self, nom: str, libelle: str) -> list[str]:
        """Lignes de gabarit qui déclarent le bouton d'un libellé donné."""
        return [
            ligne.strip()
            for ligne in self.sources[nom].splitlines()
            if "<button" in ligne and libelle in ligne
        ]

    def test_boutons_de_controle_secondaires(self) -> None:
        trouves = 0
        for nom, libelles in BOUTONS_SECONDAIRES.items():
            for libelle in libelles:
                with self.subTest(gabarit=nom, libelle=libelle):
                    lignes = self.lignes_de_bouton(nom, libelle)
                    self.assertEqual(len(lignes), 1, lignes)
                    self.assertIn("secondary", classes_de_balise(lignes[0]))
                    trouves += 1
        self.assertEqual(trouves, 3, "trois boutons de contrôle")

    def test_actions_principales_sans_secondary(self) -> None:
        for nom, libelles in BOUTONS_PRIMAIRES.items():
            for libelle in libelles:
                with self.subTest(gabarit=nom, libelle=libelle):
                    lignes = self.lignes_de_bouton(nom, libelle)
                    self.assertEqual(len(lignes), 1, lignes)
                    self.assertNotIn("secondary", classes_de_balise(lignes[0]))
                    self.assertNotIn("danger", classes_de_balise(lignes[0]))

    def test_details_avec_summary_sans_titre_ni_lien(self) -> None:
        # Design D8 : le `summary` ne porte ni titre ni lien (Sumi le style
        # comme un contrôle, et un titre dans un accordéon brouille la
        # hiérarchie des titres de la page).
        for nom, source in self.sources.items():
            with self.subTest(gabarit=nom):
                self.assertEqual(
                    source.count("<details"),
                    source.count("<summary"),
                    "un `details` a exactement un `summary`",
                )
                for ligne in source.splitlines():
                    if "<summary" not in ligne:
                        continue
                    for interdit in ("<h1", "<h2", "<h3", "<h4", "<h5", "<h6"):
                        self.assertNotIn(interdit, ligne, nom)
                    self.assertNotIn("<a ", ligne, nom)
                    self.assertNotIn("<button", ligne, nom)

    def test_grille_utilisee_hors_de_main_et_des_tableaux(self) -> None:
        # Design D8 : les cartes se répartissent avec `.grid` et `.cols-N`.
        attendus = {
            "moteurs.html": "grid cols-2",
            "modeles.html": "grid cols-2",
        }
        for nom, classes in attendus.items():
            with self.subTest(gabarit=nom):
                self.assertIn(f'class="{classes}"', self.sources[nom])
        for nom, source in self.sources.items():
            for ligne in source.splitlines():
                if "class=\"grid" not in ligne:
                    continue
                self.assertNotIn("<main", ligne)
                self.assertNotIn("<table", ligne)


class HabillagePageTest(SocleWebTest):
    """Pages rendues : squelette, navigation, cartes, accordéons et classes."""

    def page(self, chemin: str, **options):
        options.setdefault("base_url", self.base_url())
        reponse = self.client.get(chemin, **options)
        self.assertEqual(reponse.status_code, 200, chemin)
        return assert_html_seul(self, reponse.get_data(as_text=True))

    def pages_de_premier_niveau(self) -> dict[str, object]:
        return {chemin: self.page(chemin) for chemin, _ in LIENS_NAVIGATION}

    def page_erreur(self):
        reponse = self.client.get("/route-inexistante", base_url=self.base_url())
        self.assertEqual(reponse.status_code, 404)
        return assert_html_seul(self, reponse.get_data(as_text=True))

    def ecrire_resultats_comparables(self) -> None:
        """Deux exécutions terminées de même empreinte audio, pour les tableaux."""
        premier = run_json(IDENTIFIANT)
        second = run_json(IDENTIFIANT_ANCIEN)
        ecrire_execution(
            self.dossier_data,
            premier,
            (resultat_empreinte(premier, premier["audios"][0]),),
        )
        ecrire_execution(
            self.dossier_data,
            second,
            (resultat_empreinte(second, second["audios"][0]),),
        )
        # Détail d'une exécution distincte : segments, timings et audio source.
        detail = run_json(IDENTIFIANT_DETAIL)
        ecrire_execution(
            self.dossier_data,
            detail,
            (result_json(detail["audios"][0], execution=IDENTIFIANT_DETAIL),),
        )

    def chemin_comparaison(self) -> str:
        return (
            f"/resultats/comparaison/{EMPREINTE_A}"
            f"?transcription={IDENTIFIANT}:1&transcription={IDENTIFIANT_ANCIEN}:1"
        )

    def pages_a_controler(self) -> dict[str, object]:
        """Pages de premier niveau, page d'erreur et sous-pages rendues."""
        self.ecrire_resultats_comparables()
        pages = self.pages_de_premier_niveau()
        pages["/route-inexistante"] = self.page_erreur()
        pages[f"/resultats/{IDENTIFIANT_DETAIL}"] = self.page(
            f"/resultats/{IDENTIFIANT_DETAIL}"
        )
        pages[self.chemin_comparaison()] = self.page(self.chemin_comparaison())
        pages["/moteurs/faster-whisper/journal"] = self.page(
            "/moteurs/faster-whisper/journal"
        )
        return pages

    def test_squelette_commun_des_pages(self) -> None:
        for chemin, page in self.pages_a_controler().items():
            with self.subTest(chemin=chemin):
                (document,) = page.balises_de("html")
                self.assertEqual(document[2].get("lang"), "fr")

                vues = [
                    attributs.get("content") or ""
                    for ancetres, tag, attributs in page.balises_de("meta")
                    if attributs.get("name") == "viewport"
                ]
                self.assertEqual(len(vues), 1, "une seule meta viewport")
                self.assertIn("width=device-width", vues[0])

                entetes = [ancetres for ancetres, _, _ in page.balises_de("header")]
                self.assertEqual(entetes[0], ("html", "body"), "<header> de la page")
                self.assertEqual(
                    entetes.count(("html", "body")),
                    1,
                    "un seul en-tête de page",
                )
                # Les autres `header` sont ceux des cartes (`article`).
                for ancetres in entetes[1:]:
                    self.assertIn("article", ancetres, "<header> hors d'une carte")

                # Aucun pied de page de page : les `footer` sont ceux des cartes.
                pieds = [ancetres for ancetres, _, _ in page.balises_de("footer")]
                self.assertNotIn(("html", "body"), pieds)
                for ancetres in pieds:
                    self.assertIn("article", ancetres, "<footer> hors d'une carte")
                self.assertEqual(
                    [ancetres for ancetres, _, _ in page.balises_de("main")],
                    [("html", "body")],
                    "<main> enfant direct de body",
                )
                self.assertTrue(page.texte_titre)
                self.assertTrue(page.texte_titre.endswith("transcription-bench"))

    def test_navigation_commune(self) -> None:
        for chemin, page in self.pages_de_premier_niveau().items():
            with self.subTest(chemin=chemin):
                self.assertEqual(
                    [ancetres for ancetres, _, _ in page.balises_de("nav")],
                    [CHEMIN_HEADER],
                    "un seul nav, dans le header",
                )
                (_, _, attributs_nav) = page.balises_de("nav")[0]
                etiquette = attributs_nav.get("aria-label") or ""
                self.assertTrue(etiquette)
                self.assertNotEqual(etiquette, "breadcrumb")

                listes = [
                    attributs
                    for ancetres, tag, attributs in page.balises_de("ul")
                    if ancetres == CHEMIN_NAVIGATION
                ]
                self.assertEqual(len(listes), 2, "deux listes dans le nav")

                # Design D5/D7 : le nom du programme est un `strong` du
                # premier `li`, jamais un titre ni un lien.
                self.assertEqual(
                    [
                        balise
                        for balise in page.balises
                        if balise[1] in NIVEAUX_TITRES
                        and balise[0][: len(CHEMIN_NAVIGATION)] == CHEMIN_NAVIGATION
                    ],
                    [],
                    "le nom du programme n'est pas un titre",
                )
                (nom,) = [
                    balise
                    for balise in page.balises_de("strong")
                    if balise[0] == CHEMIN_NAVIGATION + ("ul", "li")
                ]
                self.assertEqual(nom[2], {}, "aucun attribut sur le strong")
                self.assertEqual(page.textes["strong"][0], "transcription-bench")

                ancres_nav = page.ancres_sous(*CHEMIN_NAVIGATION)
                self.assertEqual(
                    [(ancre["href"], ancre["texte"]) for ancre in ancres_nav],
                    list(LIENS_NAVIGATION),
                )

    def test_titres_distincts(self) -> None:
        titres = [page.texte_titre for page in self.pages_de_premier_niveau().values()]
        titres.append(self.page_erreur().texte_titre)

        self.assertEqual(len(titres), len(set(titres)), titres)

    def test_aucun_bandeau_d_avertissement_clinique(self) -> None:
        # D5 amendée : ce pré-projet de banc de modèles n'affiche plus de
        # bandeau « non validé cliniquement » (aucune diffusion clinique).
        for chemin, page in self.pages_a_controler().items():
            with self.subTest(chemin=chemin):
                self.assertNotIn("non validé cliniquement", page.corps)

    def test_classes_d_encart_reservees_aux_callouts(self) -> None:
        # D3 : `danger`, `warning` et `success` ne prennent effet que sur un
        # élément `callout` ; ailleurs, elles ne stylent rien et signalent un
        # encart manquant. Seul `danger` reste admis sur un bouton.
        for chemin, page in self.pages_a_controler().items():
            for _, tag, attributs in page.balises:
                classes = set((attributs.get("class") or "").split())
                intrus = classes & set(CLASSES_D_ENCART)
                if not intrus:
                    continue
                with self.subTest(chemin=chemin, balise=tag, classes=sorted(classes)):
                    if "callout" not in classes:
                        self.assertEqual(
                            tag, "button", "classe d'encart hors d'un callout"
                        )
                        self.assertEqual(
                            intrus,
                            {"danger"},
                            "seule la classe danger est admise sur un bouton",
                        )

    def test_un_seul_h1_sans_saut_de_niveau(self) -> None:
        # Design D7 : chaque page a exactement un `h1` (son titre) et ses
        # sous-titres se suivent sans sauter plus d'un niveau.
        for chemin, page in self.pages_a_controler().items():
            with self.subTest(chemin=chemin):
                niveaux = [
                    int(tag[1])
                    for _, tag, _ in page.balises
                    if tag in NIVEAUX_TITRES
                ]
                self.assertEqual(niveaux.count(1), 1, niveaux)
                precedent = 0
                for niveau in niveaux:
                    self.assertLessEqual(
                        niveau,
                        precedent + 1,
                        f"saut de niveau dans {chemin} : {niveaux}",
                    )
                    precedent = niveau

    def test_prose_sur_tous_les_paragraphes_et_listes_de_texte(self) -> None:
        # Design D7 : `prose` sur tous les paragraphes, listes et listes de
        # définitions de texte courant (les deux listes du `nav` exceptées),
        # jamais sur `main`, un tableau ou un conteneur défilant.
        for chemin, page in self.pages_a_controler().items():
            with self.subTest(chemin=chemin):
                for ancetres, tag, attributs in page.balises:
                    if tag not in ("p", "ul", "ol", "dl"):
                        continue
                    if ancetres[: len(CHEMIN_NAVIGATION)] == CHEMIN_NAVIGATION:
                        continue
                    self.assertIn(
                        "prose",
                        (attributs.get("class") or "").split(),
                        f"<{tag}> sans prose dans {chemin}",
                    )

                for ancetres, tag, attributs in page.avec_classe("prose"):
                    self.assertNotIn(tag, ("main", "table"), chemin)
                    self.assertNotIn("table", ancetres, chemin)
                    self.assertNotIn(
                        "overflow-auto",
                        (attributs.get("class") or "").split(),
                        chemin,
                    )

    def test_aria_current_sur_les_six_pages(self) -> None:
        for chemin, libelle in LIENS_NAVIGATION:
            with self.subTest(chemin=chemin):
                courants = self.page(chemin).courants()

                self.assertEqual(len(courants), 1, courants)
                self.assertEqual(courants[0]["href"], chemin)
                self.assertEqual(courants[0]["texte"], libelle)
                self.assertEqual(courants[0]["aria-current"], "page")

    def test_aria_current_sur_les_sous_pages(self) -> None:
        self.ecrire_resultats_comparables()
        sous_pages = {
            f"/resultats/{IDENTIFIANT}": "/resultats",
            self.chemin_comparaison(): "/resultats/comparaison",
            "/moteurs/faster-whisper/journal": "/moteurs",
        }
        for chemin, parent in sous_pages.items():
            with self.subTest(chemin=chemin):
                courants = self.page(chemin).courants()

                self.assertEqual(len(courants), 1, courants)
                self.assertEqual(courants[0]["href"], parent)
                self.assertEqual(courants[0]["texte"], dict(
                    (cible, libelle) for cible, libelle in LIENS_NAVIGATION
                )[parent])
                self.assertEqual(courants[0]["aria-current"], "true")

    def test_aria_current_absent_sur_la_page_erreur(self) -> None:
        page = self.page_erreur()

        self.assertEqual(page.courants(), [])
        self.assertEqual(len(page.balises_de("nav")), 1, "navigation présente")

    def test_classes_rendues_autorisees(self) -> None:
        # Les classes du composant de résultat sont admises dans les pages qui
        # le rendent (tâche 1.4) ; aucune autre classe hors liste n'est tolérée.
        autorisees = CLASSES_AUTORISEES | CLASSES_COMPOSANT_RESULTAT
        for chemin, page in self.pages_a_controler().items():
            with self.subTest(chemin=chemin):
                self.assertLessEqual(page.classes, autorisees, page.classes)

    def test_aucun_attribut_interdit_dans_les_pages(self) -> None:
        for chemin, page in self.pages_a_controler().items():
            with self.subTest(chemin=chemin):
                self.assertFalse(set(page.elements) & ELEMENTS_INTERDITS)
                self.assertNotIn("dialog", page.elements)
                for element, nom, valeur in page.attributs:
                    self.assertNotIn(
                        nom, ("style", "data-theme", "aria-busy", "aria-invalid")
                    )
                    self.assertFalse(nom.startswith("on"), f"{nom} sur <{element}>")
                    if nom == "role":
                        self.assertNotEqual(valeur, "button")

    def test_tableaux_dans_un_conteneur_defilant_rendus(self) -> None:
        self.ecrire_resultats_comparables()
        pages = {
            # L'historique technique a quitté Résultats pour Exécutions (3.1).
            "/executions": self.page("/executions"),
            f"/resultats/{IDENTIFIANT_DETAIL}": self.page(
                f"/resultats/{IDENTIFIANT_DETAIL}"
            ),
            self.chemin_comparaison(): self.page(self.chemin_comparaison()),
        }

        for chemin, page in pages.items():
            with self.subTest(chemin=chemin):
                tableaux = page.balises_de("table")
                self.assertTrue(tableaux, "page sans tableau à contrôler")
                conteneurs = {
                    ancetres + ("div",)
                    for ancetres, tag, attributs in page.balises
                    if tag == "div"
                    and "overflow-auto" in (attributs.get("class") or "").split()
                }
                for ancetres, _, _ in tableaux:
                    self.assertIn(
                        ancetres, conteneurs, "tableau hors d'un conteneur overflow-auto"
                    )

    def test_aucun_contenu_a_garder_visible_dans_un_details_ferme(self) -> None:
        # Design D8 : erreurs, marques, résultats partiels, texte transcrit et
        # boutons d'action ne sont jamais enfermés dans un accordéon fermé (un
        # `details` qui contient une erreur porte `open`).
        for chemin, page in self.pages_a_controler().items():
            for bloc in analyser_details(page.corps).blocs:
                if bloc.ouvert:
                    continue
                for tag, attributs in bloc.balises:
                    with self.subTest(chemin=chemin, resume=bloc.resume, balise=tag):
                        # Diagnostic volontairement secondaire (D1), pas une
                        # action de lancement ou d'arrêt à garder au premier plan.
                        if (chemin == "/executions" and
                                bloc.resume == "Emplacement des dossiers" and
                                tag == "button"):
                            continue
                        self.assertNotIn(tag, CONTENU_TOUJOURS_VISIBLE, bloc.resume)
                        classes = set((attributs.get("class") or "").split())
                        self.assertFalse(
                            classes & CLASSES_TOUJOURS_VISIBLES, bloc.resume
                        )
                        self.assertNotEqual(attributs.get("role"), "status")

    def test_diagnostics_secondaires_fermes_avec_verification_accessible(self) -> None:
        page = self.pages_a_controler()["/executions"]
        bloc = next(
            bloc for bloc in analyser_details(page.corps).blocs
            if bloc.resume == "Emplacement des dossiers"
        )
        self.assertFalse(bloc.ouvert)
        self.assertIn("button", [tag for tag, _ in bloc.balises])
        self.assertIn('action="/dossiers/verifier"', page.corps)

    def test_journal_replie_pendant_une_operation(self) -> None:
        # Design D5 : le résumé et l'arrêt restent visibles, le journal
        # technique peut rester replié même pendant une opération en cours.
        fin = threading.Event()
        self.addCleanup(fin.set)
        self.creneau.demarrer(
            "execution", lambda travailleur: fin.wait(DELAI), cible="a.wav"
        )

        page = self.page("/executions")
        blocs = analyser_details(page.corps).blocs
        journaux = [bloc for bloc in blocs if bloc.resume.startswith("Journal")]

        self.assertEqual(len(journaux), 1, [bloc.resume for bloc in blocs])
        self.assertFalse(
            journaux[0].ouvert, "journal ouvert alors qu'il doit rester replié"
        )
        self.assertIn("État : en cours", page.corps)
        self.assertIn("Cible : a.wav", page.corps)
        self.assertIn("Arrêter l'exécution", page.corps)

    def test_arret_execution_en_danger(self) -> None:
        fin = threading.Event()
        self.addCleanup(fin.set)
        self.creneau.demarrer(
            "execution", lambda travailleur: fin.wait(DELAI), cible="a.wav"
        )

        page = self.page("/executions")
        boutons = [balise for balise in page.avec_classe("danger")]

        self.assertEqual(len(boutons), 1, boutons)
        self.assertEqual(boutons[0][1], "button")
        self.assertEqual(boutons[0][2].get("class"), "danger")
        self.assertIn(
            "Arrêter l'exécution",
            re.sub(r"\s+", " ", unescape(page.corps)),
        )

    def test_page_modeles_sans_danger_sans_modele_local(self) -> None:
        page = self.page("/modeles")

        self.assertEqual(page.avec_classe("danger"), [])


if __name__ == "__main__":
    unittest.main()
