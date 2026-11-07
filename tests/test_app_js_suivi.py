"""Tests réels du suivi d'opération dans `app.js` (tâche 3.3, design D5/D6).

Le fichier servi est exécuté dans un contexte `node:vm` avec un DOM factice
(`tests/harnais_suivi_operation.js`) : requêtes simulées, visibilité d'onglet,
focus et URL forgées, sans navigateur, sans dépendance installée et sans réseau.
Le test est ignoré si aucun binaire `node` n'est disponible : il n'installe rien.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import threading
import unittest
from pathlib import Path

from tests.test_web import SocleWebTest
from transcription_bench.operations import ETAT_EN_COURS
from transcription_bench.web.app import DOSSIER_FEUILLES, NOM_SCRIPT_APP

RACINE = Path(__file__).resolve().parents[1]
HARNAIS = RACINE / "tests" / "harnais_suivi_operation.js"
SCRIPT = DOSSIER_FEUILLES / NOM_SCRIPT_APP
NODE = shutil.which("node")
DELAI_HARNAIS_S = 60
MESSAGE_ECHEC = (
    "Suivi automatique interrompu : le lien Actualiser recharge l'état."
)


class SourceScriptSuiviTest(unittest.TestCase):
    """Contrat statique du fichier : DOM sûr, pas de contrôle recréé, pas de focus."""

    def setUp(self) -> None:
        self.source = SCRIPT.read_text(encoding="utf-8")

    def test_aucune_ecriture_html_ni_controle_recree(self) -> None:
        for interdit in (
            "innerHTML",
            "outerHTML",
            "insertAdjacentHTML",
            "document.write",
            "createElement",
            "replaceChildren",
            "insertBefore",
        ):
            with self.subTest(interdit=interdit):
                self.assertNotIn(interdit, self.source)

    def test_aucun_deplacement_de_focus(self) -> None:
        for interdit in (".focus(", "scrollIntoView", "activeElement"):
            with self.subTest(interdit=interdit):
                self.assertNotIn(interdit, self.source)

    def test_adresse_et_delai_fixes(self) -> None:
        self.assertIn('var CHEMIN_ETAT = "/executions/etat";', self.source)
        self.assertIn("var DELAI_SUIVI_MS = 3000;", self.source)


@unittest.skipUnless(NODE, "node indisponible : aucun test JS réel")
class HarnaisSuiviTest(unittest.TestCase):
    """Scénarios simulés : requêtes, visibilité, terminal, échec et URL forgées."""

    @classmethod
    def setUpClass(cls) -> None:
        resultat = subprocess.run(
            [NODE, str(HARNAIS), str(SCRIPT)],
            cwd=RACINE,
            capture_output=True,
            text=True,
            encoding="utf-8",  # stdout de Node, indépendant de la locale Windows
            timeout=DELAI_HARNAIS_S,
            check=False,
        )
        if resultat.returncode != 0:
            raise AssertionError(f"harnais JS en échec :\n{resultat.stderr}")
        cls.rapport = json.loads(resultat.stdout)["scenarios"]

    def scenario(self, nom: str) -> dict:
        return self.rapport[nom]

    def test_polling_toutes_les_trois_secondes_tant_que_actif(self) -> None:
        rapport = self.scenario("actif_puis_second_tour")

        self.assertTrue(rapport["premier"])
        self.assertTrue(rapport["second"])
        self.assertEqual(rapport["appels"], 2)
        self.assertEqual(rapport["delais"], [3000, 3000, 3000])
        self.assertEqual(rapport["adresseDemandee"], "/executions/etat")
        self.assertEqual(rapport["texteEtat"], "État : en cours")
        self.assertEqual(rapport["texteCible"], "Cible : modele.wav")
        self.assertTrue(rapport["cibleVisible"])

    def test_etat_terminal_arrete_le_polling(self) -> None:
        rapport = self.scenario("terminal")

        self.assertEqual(rapport["appelsApres"], 1)
        self.assertEqual(rapport["minuteursApres"], 0)
        self.assertEqual(rapport["appelsFinal"], 1, "relance après un état terminal")
        self.assertEqual(rapport["texteEtat"], "État : terminée")

    def test_une_seule_requete_a_la_fois(self) -> None:
        rapport = self.scenario("une_requete_a_la_fois")

        self.assertEqual(rapport["pendant"], 1, "deuxième requête concurrente")
        self.assertEqual(rapport["apres"], 1)
        self.assertEqual(rapport["minuteurs"], 0)

    def test_onglet_masque_suspend_puis_reprend(self) -> None:
        rapport = self.scenario("onglet_masque")

        self.assertEqual(rapport["masque"], 0, "requête alors que l'onglet est masqué")
        self.assertEqual(rapport["masqueApres"], 0)
        self.assertEqual(rapport["visible"], 1, "aucune reprise à la visibilité")
        self.assertEqual(rapport["minuteurs"], 1)

    def test_echec_signale_sans_relance_agressive(self) -> None:
        for nom in ("echec_requete", "reponse_non_ok"):
            with self.subTest(scenario=nom):
                rapport = self.scenario(nom)
                self.assertEqual(rapport["appels"], 1)
                self.assertEqual(rapport["minuteurs"], 0)
                self.assertEqual(rapport["message"], MESSAGE_ECHEC)
        self.assertTrue(self.scenario("echec_requete")["echecVisible"])

    def test_lien_de_resultat_valide_avant_creation(self) -> None:
        urls = {entree["candidate"]: entree for entree in self.scenario("urls")}

        valide = urls["/resultats/20240103-000000-0000dead"]
        self.assertEqual(valide["href"], "/resultats/20240103-000000-0000dead")
        self.assertFalse(valide["ligneMasquee"])
        # Même origine explicite : acceptée, ramenée au chemin local normalisé.
        self.assertEqual(
            urls["http://127.0.0.1:8765/resultats/20240103-000000-0000dead"]["href"],
            "/resultats/20240103-000000-0000dead",
        )
        # Préfixe naïf, remontée, autre origine, chemin profond : aucun lien.
        for candidate in (
            "/resultats/../../evil",
            "//127.0.0.1:8765/resultats/20240103-000000-0000dead",
            "/resultats/x",
            "/resultats/20240103-000000-0000dead%2f..",
            "/resultats/20240103-000000-0000dead%5c..",
            "//evil.example/resultats/x",
            "https://evil.example/resultats/x",
            "/resultats/",
            "/resultats/a/b",
            "/resultats/x?suite=1",
            "/resultats/x#ancre",
            "/modeles",
            "",
            None,
        ):
            with self.subTest(candidate=candidate):
                self.assertIsNone(urls[candidate]["href"])
                self.assertTrue(urls[candidate]["ligneMasquee"])

    def test_changement_operation_arrete_le_suivi_sans_melanger_les_etats(self) -> None:
        rapport = self.scenario("operation_changee")
        self.assertEqual(rapport["etat"], "")
        self.assertIn("Opération changée", rapport["message"])
        self.assertEqual(rapport["desactive"], "true")
        self.assertTrue(rapport["focusInchange"])
        self.assertEqual(rapport["minuteurs"], 0)

    def test_arret_terminal_sans_perte_de_focus_ni_soumission(self) -> None:
        rapport = self.scenario("arret_terminal")
        self.assertEqual(rapport["desactive"], "true")
        self.assertIn("arrêt sans objet", rapport["libelle"])
        self.assertEqual(rapport["classe"], "secondary")
        self.assertTrue(rapport["focusInchange"])
        self.assertTrue(rapport["submitEmpeche"])
        self.assertEqual(rapport["appels"], 1)
        self.assertEqual(rapport["minuteurs"], 0)

    def test_contenu_affiche_comme_texte_et_focus_inchange(self) -> None:
        rapport = self.scenario("texte_et_focus")

        self.assertEqual(rapport["cible"], "Cible : <img src=x onerror=alert(1)>")
        self.assertEqual(
            rapport["erreur"], "Erreur : ligne <script>alert(2)</script>"
        )
        self.assertEqual(rapport["innerHTML"], "", "écriture HTML détectée")
        self.assertTrue(rapport["focusInchange"])
        self.assertTrue(rapport["ligneCibleVisible"])
        self.assertTrue(rapport["ligneErreurVisible"])

    def test_aucune_requete_hors_operation_active(self) -> None:
        for nom in ("inactif_au_chargement", "adresse_inattendue", "sans_conteneur"):
            with self.subTest(scenario=nom):
                rapport = self.scenario(nom)
                self.assertEqual(rapport["appels"], 0)
                self.assertEqual(rapport["minuteurs"], 0)


class GabaritSuiviTest(SocleWebTest):
    """Page Exécutions : abri du suivi, attributs échappés, aucun JSON à suivre."""

    def page_executions(self) -> str:
        reponse = self.client.get("/executions", base_url=self.base_url())
        self.assertEqual(reponse.status_code, 200)
        corps = reponse.get_data(as_text=True)
        self.verifier_html_seul(corps)
        return corps

    def demarrer(self, fin: threading.Event) -> None:
        demarre = threading.Event()

        def travail(travailleur) -> None:
            demarre.set()
            fin.wait(5.0)

        self.creneau.demarrer("execution", travail, cible="modele.wav")

        def liberer() -> None:
            fin.set()
            thread = self.creneau.thread_travailleur
            if thread is not None:
                thread.join(5.0)

        self.addCleanup(liberer)
        self.assertTrue(demarre.wait(5.0))

    def test_abri_de_suivi_actif_sans_json_inline(self) -> None:
        fin = threading.Event()
        self.demarrer(fin)

        corps = self.page_executions()

        self.assertEqual(self.creneau.instantane().etat, ETAT_EN_COURS)
        self.assertIn(
            '<div data-suivi-operation data-generation="1" '
            'data-etat-url="/executions/etat" data-actif="oui">',
            corps,
        )
        self.assertIn(
            '<p class="prose" data-champ="etat" role="status">État : en cours</p>', corps
        )
        self.assertIn('data-champ="lien-resultat"', corps)
        # L'adresse de l'état n'apparaît que dans l'attribut : aucun JSON inline,
        # aucun second script, aucune donnée de suivi sérialisée dans la page.
        self.assertEqual(corps.count("/executions/etat"), 1)
        self.assertNotIn("application/json", corps)

    def test_abri_de_suivi_inactif_apres_une_issue(self) -> None:
        corps = self.page_executions()

        # Aucune opération enregistrée : pas de panneau technique vide (D5).
        self.assertNotIn("data-suivi-operation", corps)
        self.assertEqual(self.creneau.instantane().etat, "libre")


if __name__ == "__main__":
    unittest.main()
