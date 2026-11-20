"""Consultation web d'extractions : données synthétiques, sans moteur ni réseau."""

from __future__ import annotations

import html
import json
from pathlib import Path
from unittest import mock
from urllib.parse import urlencode

from tests.extraction_web_fixture import FIXTURE_SOURCE, build_extraction_web_fixture
from tests.outils_html import analyser, assert_html_seul
from tests.test_extraction_consultation import (
    ExtractionConsultationBench,
    GRILLE_A,
    ORIGINE,
    Source,
    TEXTE_A,
    TEXTE_B,
    VALEUR_A,
)
from tests.test_groupes_resultats import ecrire_essai
from transcription_bench.consultation_resultats import LectureResultatsImpossible
from transcription_bench.historique import combined_history
from transcription_bench.resultats import ETAT_ECHOUEE, ETAT_INTERROMPUE
from transcription_bench.web import ConfigApplication, ServicesApplication, create_app
from transcription_bench.web.app import POLITIQUE_CONTENU
from transcription_bench.web.extraction_help import EXTRACTION_HELP

BASE_URL = "http://127.0.0.1:8765"
NAVIGATION = [
    ("/resultats", "Résultats"),
    ("/resultats/comparaison", "Comparaisons"),
    ("/extractions", "Extractions"),
    ("/executions", "Historique"),
]


class ExtractionWebTest(ExtractionConsultationBench):
    def setUp(self) -> None:
        super().setUp()
        self.app = create_app(
            ConfigApplication(8765, self.donnees),
            ServicesApplication(extraction_results=self.consultation),
        )
        self.client = self.app.test_client()

    def page(self, path: str, status: int = 200):
        response = self.client.get(path, base_url=BASE_URL)
        self.assertEqual(response.status_code, status, path)
        self.assertEqual(response.headers["Content-Security-Policy"], POLITIQUE_CONTENU)
        self.assertNotIn("Set-Cookie", response.headers)
        body = response.get_data(as_text=True)
        assert_html_seul(self, body)
        page = analyser(body)
        self.assertEqual(page.feuilles, [("stylesheet", "/sumi.css"), ("stylesheet", "/app.css")])
        self.assertEqual(
            [(link["href"], link["texte"]) for link in page.ancres_sous("html", "body", "header", "nav")],
            NAVIGATION,
        )
        if status >= 400:
            self.assertFalse(page.courants())
            self.assertNotIn("Traceback", body)
        return page

    def compare_path(self, key: str, selections: list[str]) -> str:
        return f"/extractions/comparaison/{key}?" + urlencode(
            [("extraction", selection) for selection in selections]
        )

    def fixture(self):
        fixture = build_extraction_web_fixture(self.donnees)
        self.compteur = 6
        return fixture

    def test_empty_pages_no_actions_and_current_navigation(self) -> None:
        for path in ("/extractions", "/extractions/comparaison", "/extractions/aide"):
            with self.subTest(path=path):
                page = self.page(path)
                self.assertEqual(len(page.courants()), 1)
                self.assertEqual(page.courants()[0]["href"], "/extractions")
                self.assertEqual(page.courants()[0]["aria-current"], "page" if path == "/extractions" else "true")
                self.assertFalse({"form", "button", "input"} & set(page.elements))
        self.assertEqual(self.tree_snapshot(), {})

    def test_list_sort_delegates_same_service_and_shows_groups_indicators_marks(self) -> None:
        first = self.write_run([Source(mesures={"duree_extraction_s": 9.0})])
        second = self.write_run([Source(mesures={"duree_extraction_s": 1.0})])
        simulated = self.write_run([Source(source_factice=True)], factice=True, version_consignes=2)
        with mock.patch.object(self.consultation, "groups", wraps=self.consultation.groups) as groups:
            page = self.page("/extractions?tri=temps")
            groups.assert_called_once_with("temps")
        body = page.corps
        self.assertLess(body.index(second), body.index(first))
        self.assertLess(body.index(first), body.index("<h3>Mesures simulées</h3>"))
        self.assertGreater(body.index(simulated), body.index("<h3>Mesures simulées</h3>"))
        for label in ("consultation-a.wav", "transcription-test", "Grille de test", "Extraction", "Premier token", "tokens/s", "RAM moteur", "CPU moteur", "conforme", "FACTICE", "SOURCE FACTICE", "MESURES SIMULÉES", "Versions de consignes différentes"):
            self.assertIn(label, body)
        self.assertNotIn("<form", body)
        for sort in ("recent", "temps", "cpu", "ram"):
            self.page(f"/extractions?tri={sort}")

    def test_bad_or_repeated_sorts_refused_before_reading(self) -> None:
        with mock.patch.object(self.consultation, "groups", side_effect=AssertionError("lecture")):
            for route in ("/extractions", "/extractions/comparaison"):
                for query in ("tri=inconnu", "tri=temps&tri=ram", "tri=", "tri=recent&tri=recent"):
                    with self.subTest(route=route, query=query):
                        self.page(f"{route}?{query}", 400)

    def test_ram_share_uses_recorded_capacity_and_absence_remains_explicit(self) -> None:
        run_id = self.write_run([Source()])
        page = self.page(f"/extractions/{run_id}")
        self.assertIn("sur 16 Go · 12 %", page.corps)
        self.rewrite_json(self.run_dir(run_id) / "run.json", lambda run: run["machine"].pop("ram_totale_octets"))
        page = self.page(f"/extractions/{run_id}")
        self.assertIn("RAM totale non consignée · part non interprétable", page.corps)
        self.assertNotIn("sur 16 Go", page.corps)
        # Le modèle et la capacité ne viennent jamais de la machine du serveur.
        with mock.patch("transcription_bench.resultats.metadonnees_machine", side_effect=AssertionError("matériel courant")):
            self.page("/extractions")

    def test_selection_forms_separate_simulated_and_real_and_keep_checked_on_sort(self) -> None:
        real = self.write_run([Source()])
        fake = self.write_run([Source()], factice=True)
        group = self.consultation.groups()[0]
        query = urlencode({"groupe": group.key, "tri": "ram", "extraction": f"{fake}:1"})
        page = self.page("/extractions/comparaison?" + query)
        forms = page.balises_de("form")
        self.assertEqual(len(forms), 2)
        for _, _, attrs in forms:
            self.assertEqual(attrs["method"], "get")
            self.assertEqual(attrs["action"], f"/extractions/comparaison/{group.key}")
        checks = [attrs for _, _, attrs in page.balises_de("input") if attrs.get("type") == "checkbox"]
        self.assertEqual([attrs["value"] for attrs in checks], [f"{real}:1", f"{fake}:1"])
        self.assertNotIn("checked", checks[0])
        self.assertIn("checked", checks[1])
        self.assertTrue(all(attrs.get("aria-label") for attrs in checks))
        self.assertIn('formaction="/extractions/comparaison#', page.corps)

    def test_selection_list_rejects_forged_group_and_selections(self) -> None:
        first = self.write_run([Source()])
        other = self.write_run([Source(texte=TEXTE_B)])
        fake = self.write_run([Source()], factice=True)
        key = next(group.key for group in self.consultation.groups() if any(entry.run_id == first for entry in group.entries))
        queries = [
            [("groupe", "a" * 64)],
            [("groupe", key), ("groupe", key)],
            [("extraction", f"{first}:1")],
            [("groupe", key), ("extraction", f"{other}:1")],
            [("groupe", key), ("extraction", "../secret:1")],
            [("groupe", key), ("extraction", f"{first}:1"), ("extraction", f"{fake}:1")],
            [("groupe", key)] + [("extraction", f"{first}:1")] * 7,
        ]
        for query in queries:
            with self.subTest(query=query):
                self.page("/extractions/comparaison?" + urlencode(query), 400)

    def test_detail_primary_grid_source_visible_and_secondary_information_accessible(self) -> None:
        run_id = self.write_run([Source(valeur=dict(VALEUR_A, motif=None)), Source(valeur=dict(VALEUR_A, motif=""))])
        page = self.page(f"/extractions/{run_id}")
        self.assertEqual(page.courants()[0]["aria-current"], "true")
        body = html.unescape(page.corps)
        for label in ("Grille remplie", "non mentionné", "(vide)", "Symptômes ? (1)", "Prescription ? (1)", "Médicament", "Posologie", "Autres informations utiles", "Allergie", TEXTE_A, "Tokens entrée / sortie", "Vitesse de lecture estimée", "Threads demandés / appliqués", "Réglages effectifs", "Métadonnées complètes", "Message système", "Grille copiée", "Sortie brute du modèle", "comptes_natifs", "mmap"):
            self.assertIn(label, body)
        self.assertEqual(len(page.avec_classe("extraction-reading")), 2)
        for ancestors, _, attrs in page.avec_classe("extraction-reading"):
            self.assertNotIn("details", ancestors)
        primary_pres = [ancestors for ancestors, _, _ in page.balises_de("pre") if "details" not in ancestors]
        self.assertEqual(len(primary_pres), 2, "source intégrale visible pour chaque source")
        self.assertNotIn("Transcription d'origine</a>", body)
        ecrire_essai(self.donnees, ORIGINE, cree_le="2026-02-28T12:00:00+00:00")
        page = self.page(f"/extractions/{run_id}")
        self.assertIn(f'href="/resultats/{ORIGINE}#audio-1"', page.corps)

    def test_noncompliant_error_unprocessed_and_partial_states_not_hidden(self) -> None:
        run_id = self.write_run([Source(conforme=False), Source(publier=False), Source()])
        self.rewrite_json(self.run_dir(run_id) / "run.json", lambda run: run.update(etat=ETAT_INTERROMPUE, erreur="arrêt synthétique"))
        result_path = self.source_dir(run_id, 3) / "result.json"
        self.rewrite_json(result_path, lambda result: result.update(etat="erreur", motif="contexte insuffisant"))
        page = self.page(f"/extractions/{run_id}")
        for label in ("non conforme", "non traitée", "en erreur", "Résultats partiels", "interrompue", "clé inconnue", "contexte insuffisant", "arrêt synthétique", "Sortie brute"):
            self.assertIn(label, html.unescape(page.corps))
        self.assertNotIn("Grille remplie", page.corps)
        self.assertNotIn("non mentionné", page.corps.split("<details>", 1)[0])
        raw = [attrs for ancestors, _, attrs in page.balises_de("h3") if attrs.get("id", "").startswith("raw-") and "details" not in ancestors]
        self.assertEqual(len(raw), 3)

    def test_six_column_comparison_in_received_order_one_source_and_noncompliant_links(self) -> None:
        fixture = self.fixture()
        selections = list(reversed(fixture["selections"]))
        page = self.page(self.compare_path(fixture["key"], selections))
        self.assertEqual(page.courants()[0]["aria-current"], "true")
        headers = [attrs for _, _, attrs in page.balises_de("th") if attrs.get("scope") == "col"]
        self.assertEqual(len(headers), 7)
        body = page.corps
        model_links = [link["href"] for link in page.ancres if str(link["href"]).endswith("#source-1")]
        self.assertEqual(model_links, [f"/extractions/{selection.split(':')[0]}#source-1" for selection in selections])
        self.assertEqual(html.unescape(body).count(FIXTURE_SOURCE), 1)
        self.assertEqual(len(page.avec_classe("extraction-indicators")), 6)
        self.assertEqual(len(page.avec_classe("extraction-mobile-label")), 24)
        self.assertEqual(len(page.balises_de("td")), 24, "trois cases plus autres informations, six valeurs chacune")
        self.assertIn(f'/extractions/{fixture["run_ids"][-1]}#raw-1', body)
        cells = body.split("<tbody>")[1].split("</tbody>")[0].split("<td ")
        for cell in (cells[1], cells[7], cells[13], cells[19]):
            self.assertIn("non conforme", cell)
            self.assertIn("Voir la sortie brute", cell)
            self.assertNotIn("non mentionné", cell)
        self.assertIn("Versions de consignes différentes", body)
        self.assertIn("(vide)", body)
        self.assertIn("non mentionné", body)
        self.assertNotIn("<form", body)
        for count in range(2, 7):
            self.page(self.compare_path(fixture["key"], fixture["selections"][:count]))

    def test_comparison_uses_shared_service_without_reordering(self) -> None:
        fixture = self.fixture()
        selections = list(reversed(fixture["selections"][:3]))
        with mock.patch.object(self.consultation, "compare", wraps=self.consultation.compare) as compare:
            self.page(self.compare_path(fixture["key"], selections))
            compare.assert_called_once_with(fixture["key"], selections)

    def test_comparison_rejects_bounds_paths_wrong_group_and_mixed_simulation(self) -> None:
        first = self.write_run([Source()])
        second = self.write_run([Source()])
        other = self.write_run([Source(texte=TEXTE_B)])
        fake = self.write_run([Source()], factice=True)
        key = next(group.key for group in self.consultation.groups() if any(entry.run_id == first for entry in group.entries))
        for selections in ([], [f"{first}:1"], [f"{first}:1"] * 2, [f"{first}:1"] * 7, [f"{first}:1", "../secret:1"], [f"{first}:1", "/secret:1"], [f"{first}:0", f"{second}:1"], [f"{first}:1", f"{other}:1"], [f"{first}:1", f"{fake}:1"]):
            with self.subTest(selections=selections):
                self.page(self.compare_path(key, selections), 400)
        self.page(self.compare_path(key, [f"{first}:99", f"{second}:1"]), 404)
        self.page(self.compare_path("a" * 64, [f"{first}:1", f"{second}:1"]), 404)
        self.page(self.compare_path("..", [f"{first}:1", f"{second}:1"]), 400)
        self.page(self.compare_path(key, [f"{first}:1", f"{second}:1"]) + "&groupe=autre", 400)

    def test_identifier_confinement_symlinks_and_fixed_errors(self) -> None:
        run_id = self.write_run([Source()])
        self.page("/extractions/..", 400)
        self.page("/extractions/nom-invalide", 400)
        self.page("/extractions/20260101-100000-00000000", 404)
        self.link_outside(self.run_dir(run_id) / "run.json", json.dumps(self.read_run(run_id)))
        self.page(f"/extractions/{run_id}", 422)
        self.assertNotIn("run.json", self.page(f"/extractions/{run_id}", 422).corps)

    def test_escaping_in_source_grid_values_raw_and_metadata(self) -> None:
        hostile = '<script>alert("test")</script><img src=x onerror=alert(1)>'
        # Changer le titre d'une case changerait sa clé : le contenu hostile
        # de la case est plutôt exercé dans sa consigne sans changer le schéma.
        grid = GRILLE_A.replace("Grille de test", hostile) + "\n" + hostile
        value = dict(VALEUR_A, motif=hostile, autres_informations=[{"intitule": hostile, "valeur": hostile}])
        run_id = self.write_run([Source(texte=hostile, valeur=value)], grille=grid)
        second = self.write_run([Source(texte=hostile, conforme=False)], grille=grid)
        (self.source_dir(second, 1) / "sortie_brute.txt").write_text(hostile, encoding="utf-8")
        self.rewrite_json(self.run_dir(run_id) / "run.json", lambda run: run.update(erreur=hostile))
        key = self.consultation.groups()[0].key
        for route in ("/extractions", "/extractions/comparaison", f"/extractions/{run_id}", f"/extractions/{second}", self.compare_path(key, [f"{run_id}:1", f"{second}:1"]), "/executions"):
            with self.subTest(route=route):
                page = self.page(route)
                self.assertNotIn("<script>", page.corps)
                self.assertNotIn("<img", page.corps)
                if route != "/executions":
                    self.assertIn("&lt;script&gt;", page.corps)

    def test_help_renders_unique_source_with_escaping(self) -> None:
        page = self.page("/extractions/aide")
        self.assertIn(EXTRACTION_HELP["title"], html.unescape(page.corps))
        for section in EXTRACTION_HELP["sections"]:
            self.assertIn(section["title"], html.unescape(page.corps))
        self.assertIn("exactitude médicale", page.corps)
        hostile_help = {"title": "<script>title</script>", "intro": ({"kind": "strong", "text": "<img src=x>"},), "sections": ()}
        with mock.patch.dict(self.app.jinja_env.globals, {"extraction_help": hostile_help}):
            page = self.page("/extractions/aide")
        self.assertIn("&lt;script&gt;title&lt;/script&gt;", page.corps)
        self.assertIn("&lt;img src=x&gt;", page.corps)

    def test_history_combines_both_types_same_id_failures_uninterpretable_and_typed_links(self) -> None:
        first = self.write_run([Source()])
        failed = self.write_run([Source(publier=False)])
        unreadable = self.write_run([Source()])
        self.rewrite_json(self.run_dir(failed) / "run.json", lambda run: run.update(etat=ETAT_ECHOUEE, erreur="échec de test"))
        (self.run_dir(unreadable) / "run.json").write_text("{invalide", encoding="utf-8")
        ecrire_essai(self.donnees, first, cree_le="2026-01-01T10:00:00+00:00", etat=ETAT_ECHOUEE)
        bad_id = "20260102-100000-00000000"
        bad_dir = self.donnees / "results" / bad_id
        bad_dir.mkdir()
        (bad_dir / "run.json").write_text("{invalide", encoding="utf-8")
        with mock.patch("transcription_bench.web.app.combined_history", wraps=combined_history) as history:
            page = self.page("/executions")
            history.assert_called_once()
        links = [link["href"] for link in page.ancres if str(link["href"]).startswith(("/extractions/20", "/resultats/20"))]
        self.assertEqual(len(links), 5)
        self.assertIn(f"/extractions/{first}", links)
        self.assertIn(f"/resultats/{first}", links)
        self.assertIn(f"/extractions/{unreadable}", links)
        self.assertIn(f"/resultats/{bad_id}", links)
        for label in ("transcription", "extraction", "non interprétable", "en échec", "Moteur", "Entrées traitées", "Durée totale"):
            self.assertIn(label, page.corps)
        self.assertNotIn("<form", page.corps)
        self.assertLess(page.corps.index(failed), page.corps.index(f'href="/resultats/{first}"'))

    def test_get_head_host_methods_csp_and_no_writes_or_network(self) -> None:
        fixture = self.fixture()
        routes = ["/extractions", "/extractions/aide", "/extractions/comparaison", fixture["detail"], fixture["comparison"], "/executions"]
        before = self.tree_snapshot()
        with mock.patch("socket.socket", side_effect=AssertionError("réseau")):
            for route in routes:
                with self.subTest(route=route):
                    self.page(route)
                    head = self.client.head(route, base_url=BASE_URL)
                    self.assertEqual(head.status_code, 200)
                    self.assertFalse(head.data)
                    self.assertEqual(head.headers["Content-Security-Policy"], POLITIQUE_CONTENU)
        self.assertEqual(before, self.tree_snapshot())
        with mock.patch.object(self.consultation, "groups", side_effect=AssertionError("lecture")), mock.patch.object(self.consultation, "detail", side_effect=AssertionError("lecture")), mock.patch.object(self.consultation, "compare", side_effect=AssertionError("lecture")):
            for route in routes[:-1]:
                for method in ("POST", "PUT", "PATCH", "DELETE", "OPTIONS"):
                    response = self.client.open(route, method=method, base_url=BASE_URL)
                    self.assertEqual(response.status_code, 405)
                    self.assertEqual(set(response.headers["Allow"].replace(" ", "").split(",")), {"GET", "HEAD"})
                for method in ("GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"):
                    response = self.client.open(route, method=method, base_url=BASE_URL, headers={"Host": "evil.example:8765"})
                    self.assertEqual(response.status_code, 403)
                    self.assertEqual(response.headers["Content-Security-Policy"], POLITIQUE_CONTENU)

    def test_errors_422_500_no_exception_text_or_current_navigation(self) -> None:
        run_id = self.write_run([Source()])
        (self.run_dir(run_id) / "run.json").write_text("{secret:invalide", encoding="utf-8")
        page = self.page(f"/extractions/{run_id}", 422)
        self.assertNotIn("secret", page.corps)
        with mock.patch.object(self.consultation, "groups", side_effect=LectureResultatsImpossible("chemin privé")):
            self.assertNotIn("chemin privé", self.page("/extractions", 500).corps)
        with mock.patch.object(self.consultation, "detail", side_effect=RuntimeError("détail privé")), self.assertLogs(self.app.logger, level="ERROR"):
            self.assertNotIn("détail privé", self.page(f"/extractions/{run_id}", 500).corps)

    def test_responsive_structure_css_and_no_alternative_styles(self) -> None:
        fixture = self.fixture()
        detail = self.page(fixture["detail"])
        comparison = self.page(fixture["comparison"])
        self.assertTrue(detail.avec_classe("extraction-reading"))
        self.assertTrue(comparison.avec_classe("extraction-comparison"))
        css = (Path(__file__).parents[1] / "transcription_bench/web/ressources/app.css").read_text(encoding="utf-8")
        self.assertIn("grid-template-columns: repeat(2, minmax(0, 1fr))", css)
        self.assertIn("@media (min-width: 64rem)", css)
        self.assertIn("@media (max-width: 63.999rem)", css)
        self.assertIn("table-layout: fixed", css)
        self.assertIn(".extraction-comparison .extraction-mobile-label", css)
        for page in (detail, comparison):
            self.assertEqual(len(page.textes["h1"]), 1)
            self.assertFalse(page.balises_de("style"))
            self.assertFalse(any(name == "style" for _, name, _ in page.attributs))
