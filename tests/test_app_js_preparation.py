"""Tests réels de la préparation améliorée dans `app.js` (tâche 4.2, design D4/D6).

Le fichier servi est exécuté dans un contexte `node:vm` avec un DOM factice
(`tests/harnais_preparation.js`) : sélecteurs, cases d'audios, soumission du
formulaire GET et minuteurs du suivi sont simulés, sans navigateur, sans
dépendance installée et sans réseau. Le test est ignoré si aucun binaire `node`
n'est disponible : il n'installe rien. Ces scénarios ne sont pas une observation
de navigateur : ils vérifient le contrat du script et de ses données rendues.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import unittest
from pathlib import Path

from transcription_bench.web.app import DOSSIER_FEUILLES, NOM_SCRIPT_APP

RACINE = Path(__file__).resolve().parents[1]
HARNAIS = RACINE / "tests" / "harnais_preparation.js"
SCRIPT = DOSSIER_FEUILLES / NOM_SCRIPT_APP
NODE = shutil.which("node")
DELAI_HARNAIS_S = 60
MODULE_B = "moteur-b/" + "b" * 64
MODULE_A = "moteur-a/" + "a" * 64


class SourceScriptPreparationTest(unittest.TestCase):
    """Contrat statique : DOM sûr, requête GET réutilisée, aucune mutation."""

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

    def test_preparation_reutilise_le_formulaire_get_sans_requete_propre(self) -> None:
        # Une seule lecture réseau dans tout le fichier : l'état du suivi. La
        # préparation soumet le formulaire GET rendu par Jinja et ne fabrique
        # aucune adresse, aucun jeton et aucune méthode.
        self.assertEqual(self.source.count("fetch("), 1)
        self.assertIn("formulaire.submit();", self.source)
        self.assertNotIn('setAttribute("method"', self.source)
        self.assertNotIn("jeton_csrf", self.source)

    def test_contrat_de_donnees_lu_sur_les_options(self) -> None:
        for attribut in (
            "data-choix-modele",
            "data-choix-moteur",
            "data-choix-audio",
            "data-copie-reglage",
            "data-valeur-reglage",
        ):
            with self.subTest(attribut=attribut):
                self.assertIn(attribut, self.source)
        self.assertIn('getAttribute("data-moteur")', self.source)
        self.assertIn('getAttribute("data-reference")', self.source)
        # Les copies de réglages ne sont activées qu'après recopie d'un contrôle
        # marqué : le jeton anti-CSRF n'est jamais copié ni transmis.
        self.assertIn("cible.disabled = false;", self.source)
        self.assertIn("cible.disabled = true;", self.source)


@unittest.skipUnless(NODE, "node indisponible : aucun test JS réel")
class HarnaisPreparationTest(unittest.TestCase):
    """Scénarios simulés du panneau unique : sélections, repli et absence de POST."""

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

    def verifier_lecture_seule(self, soumission: dict) -> None:
        """Aucune action : méthode GET du formulaire, aucun jeton transmis."""
        self.assertEqual(soumission["method"], "get")
        self.assertFalse(soumission["jeton"], "jeton anti-CSRF dans la requête")
        self.assertTrue(soumission["action"].startswith("/executions"))
        # Liste blanche des valeurs transmises : threads et réglages déclarés.
        for nom in soumission["noms"]:
            self.assertTrue(
                nom == "threads" or nom.startswith("reglage_"),
                f"paramètre transmis hors liste blanche : {nom}",
            )

    def test_changement_de_modele_soumet_le_formulaire_get_compatible(self) -> None:
        rapport = self.scenario("changement_modele")

        self.assertEqual(len(rapport["soumissions"]), 1)
        soumission = rapport["soumissions"][0]
        self.verifier_lecture_seule(soumission)
        self.assertEqual(soumission["modele"], MODULE_B)
        self.assertEqual(soumission["moteur"], "moteur-b")
        self.assertEqual(soumission["audios"], ["a.wav"])
        self.assertEqual(soumission["action"], "/executions#preparation")
        self.assertTrue(rapport["boutonMasque"], "bouton intermédiaire encore affiché")
        self.assertEqual(rapport["appelsReseau"], 0, "requête réseau inattendue")
        self.assertEqual(rapport["minuteurs"], 0, "action différée inattendue")

    def test_changement_d_audio_conserve_l_ordre_et_les_doublons_locaux(self) -> None:
        rapport = self.scenario("changement_audio")

        # Un seul audio ajouté, même déclenché deux fois : aucun doublon.
        for soumission in rapport["soumissions"]:
            self.verifier_lecture_seule(soumission)
            self.assertEqual(soumission["audios"], ["a.wav", "b.wav"])
            self.assertEqual(soumission["modele"], MODULE_A)
            self.assertEqual(soumission["moteur"], "moteur-a")
        self.assertTrue(rapport["boutonMasque"])
        self.assertEqual(rapport["appelsReseau"], 0)

    def test_audio_unitaire_change_sans_envoyer_le_lot(self) -> None:
        rapport = self.scenario("changement_audio_unitaire")

        self.assertEqual(len(rapport["soumissions"]), 1)
        soumission = rapport["soumissions"][0]
        self.verifier_lecture_seule(soumission)
        # Un seul contrôle simple : aucune case de lot n'est cochée et le
        # serveur reçoit le seul audio choisi, sans jeton ni doublon.
        self.assertEqual(soumission["audios"], [])
        self.assertEqual(soumission["audioUnique"], "b.wav")
        self.assertEqual(soumission["action"], "/executions#preparation")
        self.assertTrue(rapport["boutonMasque"])
        self.assertEqual(rapport["appelsReseau"], 0, "requête réseau inattendue")
        self.assertEqual(rapport["minuteurs"], 0, "action différée inattendue")

    def test_changement_de_moteur_prend_une_reference_compatible(self) -> None:
        rapport = self.scenario("changement_moteur")

        self.assertEqual(len(rapport["soumissions"]), 1)
        soumission = rapport["soumissions"][0]
        self.verifier_lecture_seule(soumission)
        self.assertEqual(soumission["moteur"], "moteur-b")
        self.assertEqual(soumission["modele"], MODULE_B)
        self.assertEqual(rapport["appelsReseau"], 0)

    def test_moteur_deja_coherent_ne_change_pas_le_modele(self) -> None:
        rapport = self.scenario("moteur_deja_coherent")

        self.assertEqual(rapport["soumissions"], [])
        self.assertTrue(rapport["modele"].startswith("moteur-a/" + "d"))

    def test_contrat_absent_laisse_le_repli_html(self) -> None:
        for nom, attendu in (
            ("contrat_absent_modele", False),
            ("contrat_absent_moteur", True),
        ):
            with self.subTest(scenario=nom):
                rapport = self.scenario(nom)
                self.assertEqual(rapport["soumissions"], [])
                if nom == "contrat_absent_modele":
                    self.assertEqual(rapport["boutonMasque"], attendu)

    def test_option_hors_liste_n_invente_aucune_combinaison(self) -> None:
        rapport = self.scenario("reference_hors_liste")

        self.assertEqual(rapport["soumissions"], [])
        self.assertEqual(rapport["moteur"], "moteur-z", "valeur forgée réécrite")

    def test_page_sans_preparation_ou_sans_hook_reste_utilisable(self) -> None:
        sans_formulaire = self.scenario("sans_formulaire")
        self.assertEqual(sans_formulaire["soumissions"], [])
        self.assertFalse(sans_formulaire["boutonMasque"])
        self.assertEqual(sans_formulaire["appelsReseau"], 0)

        sans_hook = self.scenario("sans_hook_de_bouton")
        self.assertEqual(len(sans_hook["soumissions"]), 1)
        self.verifier_lecture_seule(sans_hook["soumissions"][0])
        self.assertEqual(sans_hook["appelsReseau"], 0)

    def test_noms_d_audios_speciaux_transmis_tels_quels(self) -> None:
        rapport = self.scenario("noms_d_audios_speciaux")

        soumission = rapport["soumissions"][0]
        self.verifier_lecture_seule(soumission)
        self.assertEqual(
            soumission["audios"], ["séance #2 & fin.wav", "a+b=c.wav"]
        )

    def test_ancre_de_preparation_non_dupliquee(self) -> None:
        rapport = self.scenario("ancre_non_dupliquee")

        self.assertEqual(len(rapport["soumissions"]), 2)
        for soumission in rapport["soumissions"]:
            self.assertEqual(soumission["action"], "/executions#preparation")

    def test_audio_seul_conserve_reglages_et_threads(self) -> None:
        rapport = self.scenario("audio_seul_conserve_reglages")

        self.assertEqual(len(rapport["soumissions"]), 1)
        soumission = rapport["soumissions"][0]
        self.verifier_lecture_seule(soumission)
        self.assertEqual(soumission["modele"], MODULE_A)
        self.assertEqual(soumission["audios"], ["a.wav", "b.wav"])
        # Réglages non par défaut et threads repris tels quels, jamais le jeton.
        # Le texte libre (prompt) n'a pas de copie GET : il n'est pas transmis.
        self.assertEqual(
            soumission["reglages"],
            {
                "threads": "6",
                "reglage_compute_type": "int8",
                "reglage_beam_size": "8",
                "reglage_vad_filter": "non",
            },
        )
        self.assertEqual(rapport["copiesActives"], 4)
        self.assertEqual(rapport["appelsReseau"], 0, "requête réseau inattendue")

    def test_variante_transmet_les_valeurs_pour_validation_serveur(self) -> None:
        rapport = self.scenario("variante_conserve_reglages")

        soumission = rapport["soumissions"][0]
        self.verifier_lecture_seule(soumission)
        self.assertEqual(soumission["modele"], MODULE_B)
        self.assertEqual(
            soumission["reglages"],
            {"threads": "2", "reglage_compute_type": "int8"},
        )

    def test_radio_sans_selection_laisse_la_copie_inactive(self) -> None:
        rapport = self.scenario("radio_sans_selection")

        soumission = rapport["soumissions"][0]
        self.verifier_lecture_seule(soumission)
        # Aucune valeur pour le groupe sans case cochée : elle n'est pas transmise.
        self.assertEqual(soumission["reglages"], {"threads": "3"})
        self.assertTrue(rapport["copieDesactivee"])

    def test_jeton_toujours_absent_des_valeurs_transmises(self) -> None:
        rapport = self.scenario("jeton_jamais_transmis")

        soumission = rapport["soumissions"][0]
        self.verifier_lecture_seule(soumission)
        self.assertEqual(soumission["noms"], ["threads", "reglage_beam_size"])
        # Le jeton existe bien dans la préparation appliquée : il n'est pas copié.
        self.assertTrue(rapport["jetonDansLeFormulaireLancement"])

    def test_sans_preparation_appliquee_aucune_valeur_transmise(self) -> None:
        rapport = self.scenario("sans_preparation_appliquee")

        soumission = rapport["soumissions"][0]
        self.verifier_lecture_seule(soumission)
        self.assertEqual(soumission["reglages"], {})
        self.assertEqual(soumission["noms"], [])

    def test_suivi_d_operation_toujours_armer_avec_la_preparation(self) -> None:
        rapport = self.scenario("avec_suivi")

        self.assertTrue(rapport["suiviPresent"])
        self.assertEqual(rapport["minuteursAvant"], 1, "suivi non armé")
        self.assertEqual(rapport["appelsAvant"], 0, "requête avant le délai de 3 s")
        self.assertEqual(len(rapport["soumissions"]), 1)


if __name__ == "__main__":
    unittest.main()
