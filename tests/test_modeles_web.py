"""Tests de la page des modèles et des actions POST associées.

Les services sont injectés : une vérification simulée et un téléchargement
simulé écrivent uniquement dans un dossier temporaire. Aucun moteur réel n'est
installé, aucun poids n'est téléchargé et aucune requête réseau n'est émise.
"""

from __future__ import annotations

import re
import threading
from pathlib import Path

from engines.registre import RegistreMoteurs
from tests.test_gestion_modeles import FauxClientTelechargement, FauxMoteurs
from tests.test_verification_modeles import (
    COMMIT,
    CONTENUS_CTRANSLATE2,
    FauxClient,
    declaration_synthetique,
    infos_de,
)
from tests.test_web import SocleWebTest
from transcription_bench.compatibilite_modeles import (
    RAISON_FICHIER_GGUF_NON_CHOISI,
)
from transcription_bench.gestion_modeles import (
    NOM_MARQUEUR,
    GestionModeles,
    ModeleLocal,
)
from transcription_bench.moteurs import ETAT_PRET, EtatMoteur
from transcription_bench.operations import TYPE_EXECUTION, TYPE_TELECHARGEMENT
from transcription_bench.verification_modeles import (
    FichierVerifie,
    ResultatVerification,
    VerificationModeles,
)

DELAI = 5.0
MOTEUR = "moteur-de-test"


class FausseGestion:
    """Service factice pour exercer le rendu, sans aucune E/S."""

    def __init__(
        self,
        resultat: ResultatVerification | None = None,
        inventaire: tuple[ModeleLocal, ...] = (),
        moteurs: tuple[EtatMoteur, ...] = (),
    ) -> None:
        self.resultat = resultat
        self._inventaire = inventaire
        self._moteurs = moteurs

    def dernier_resultat(self):
        return self.resultat

    def inventaire(self):
        return self._inventaire

    def moteurs_disponibles(self):
        return self._moteurs

    def lancer_verification(self, *args, **kwargs):
        raise AssertionError("vérification inattendue sur un service de rendu")

    def lancer_telechargement(self, *args, **kwargs):
        raise AssertionError("téléchargement inattendu sur un service de rendu")

    def supprimer(self, *args, **kwargs):
        raise AssertionError("suppression inattendue sur un service de rendu")


class ModelesWebTest(SocleWebTest):
    def setUp(self) -> None:
        super().setUp()
        self.registre = RegistreMoteurs()
        self.registre.enregistrer(declaration_synthetique(identifiant=MOTEUR))
        self.moteurs = FauxMoteurs(
            (EtatMoteur(identifiant=MOTEUR, nom="Moteur de test", etat=ETAT_PRET),)
        )
        self.verification_client = FauxClient(
            infos_de(CONTENUS_CTRANSLATE2), CONTENUS_CTRANSLATE2
        )
        self.verification = VerificationModeles(
            self.registre, self.creneau, client=self.verification_client
        )
        self.telechargement = FauxClientTelechargement(
            contenus=CONTENUS_CTRANSLATE2
        )
        self.gestion = GestionModeles(
            self.dossier_data,
            self.registre,
            self.creneau,
            self.moteurs,
            verification=self.verification,
            client=self.telechargement,
        )
        self.app = self.construire_app(self.services(modeles=self.gestion))
        self.client = self.app.test_client()

    def attendre(self) -> None:
        thread = self.creneau.thread_travailleur
        self.assertIsNotNone(thread)
        thread.join(DELAI)
        self.assertFalse(thread.is_alive(), "thread d'opération non terminé")

    def page(self) -> str:
        reponse = self.client.get("/modeles", base_url=self.base_url())
        self.assertEqual(reponse.status_code, 200)
        corps = reponse.get_data(as_text=True)
        self.verifier_html_seul(corps)
        return corps

    def empreinte(self, corps: str) -> str:
        trouve = re.search(
            r'<input type="hidden" name="empreinte" value="([0-9a-f]{64})">',
            corps,
        )
        self.assertIsNotNone(trouve, "empreinte de téléchargement absente")
        return trouve.group(1)

    def cle_affichee(self, corps: str) -> str:
        trouve = re.search(
            r'<input type="hidden" name="cle" value="([0-9a-f]{64})">',
            corps,
        )
        self.assertIsNotNone(trouve, "clé de suppression absente")
        return trouve.group(1)

    def verifier_depuis_la_page(self, *, identifiant: str = "org/modele") -> str:
        reponse = self.post_autorise(
            "/modeles/verifier",
            donnees={"identifiant": identifiant, "moteur": MOTEUR},
        )
        self.assertEqual(reponse.status_code, 303)
        self.assertIn("action=verification-lancee", reponse.headers["Location"])
        self.attendre()
        return self.page()

    def preparer_modele_pret(self) -> str:
        """Télécharge un modèle simulé et renvoie la clé de suppression affichée."""
        corps = self.verifier_depuis_la_page()
        reponse = self.post_autorise(
            "/modeles/telecharger", donnees={"empreinte": self.empreinte(corps)}
        )
        self.assertEqual(reponse.status_code, 303)
        self.attendre()
        return self.cle_affichee(self.page())

    def instantane_fichiers(self, dossier: Path) -> dict[str, bytes]:
        return {
            str(chemin.relative_to(dossier)): chemin.read_bytes()
            for chemin in sorted(dossier.rglob("*"))
            if chemin.is_file()
        }

    def test_page_reelle_sans_effet_de_bord(self) -> None:
        corps = self.page()

        self.assertIn("Vérifier un dépôt", corps)
        self.assertIn("Vérifier la compatibilité sans télécharger", corps)
        self.assertIn("Aucun modèle local prêt", corps)
        self.assertFalse(self.dossier_data.exists())
        self.assertEqual(self.creneau.instantane().etat, "libre")

    def test_verification_telechargement_et_suppression(self) -> None:
        corps = self.verifier_depuis_la_page()
        self.assertIn(COMMIT, corps)
        self.assertIn("Télécharger ce modèle à la révision vérifiée", corps)
        empreinte = self.empreinte(corps)

        reponse = self.post_autorise(
            "/modeles/telecharger", donnees={"empreinte": empreinte}
        )
        self.assertEqual(reponse.status_code, 303)
        self.assertIn("action=telechargement-lance", reponse.headers["Location"])
        self.attendre()

        corps = self.page()
        self.assertIn("org/modele", corps)
        self.assertIn("Supprimer ce modèle local", corps)
        self.assertIn("Taille sur disque", corps)
        cle = self.cle_affichee(corps)
        self.assertEqual(len(self.verification_client.appels_infos), 1)
        self.assertEqual(len(self.telechargement.appels), 1)

        resultats = self.dossier_data / "results" / "20261025-000000-test"
        resultats.mkdir(parents=True)
        (resultats / "run.json").write_text('{"etat": "completed"}', encoding="utf-8")

        reponse = self.post_autorise(
            "/modeles/supprimer", donnees={"moteur": MOTEUR, "cle": cle}
        )
        self.assertEqual(reponse.status_code, 303)
        self.assertIn("action=modele-supprime", reponse.headers["Location"])
        corps = self.page()
        self.assertIn("Aucun modèle local prêt", corps)
        self.assertTrue((resultats / "run.json").is_file())

    def test_post_sans_jeton_refuse_sans_io(self) -> None:
        reponse = self.client.post(
            "/modeles/verifier",
            data={"identifiant": "org/modele", "moteur": MOTEUR},
            base_url=self.base_url(),
        )
        self.verifier_page_erreur(reponse, 403)
        self.assertEqual(self.verification_client.appels_infos, [])
        self.assertFalse(self.dossier_data.exists())

    def test_refus_identifiant_invalide_sans_io(self) -> None:
        reponse = self.post_autorise(
            "/modeles/verifier",
            donnees={"identifiant": "../secret", "moteur": MOTEUR},
        )
        self.verifier_page_erreur(reponse, 400)
        self.assertEqual(self.verification_client.appels_infos, [])
        self.assertFalse(self.dossier_data.exists())

    def test_operation_en_cours_refusee_en_409_sans_io(self) -> None:
        liberation = threading.Event()
        self.addCleanup(liberation.set)
        self.creneau.demarrer(
            TYPE_EXECUTION, lambda travailleur: liberation.wait(DELAI), cible="audio"
        )
        reponse = self.post_autorise(
            "/modeles/verifier",
            donnees={"identifiant": "org/modele", "moteur": MOTEUR},
        )
        self.verifier_page_erreur(reponse, 409)
        self.assertEqual(self.verification_client.appels_infos, [])
        liberation.set()
        self.attendre()

    def test_suppression_pendant_execution_409_execution_en_cours(self) -> None:
        cle = self.preparer_modele_pret()
        dossier = self.dossier_data / "models" / MOTEUR / cle
        avant = self.instantane_fichiers(dossier)
        resultats = self.dossier_data / "results" / "20261026-000000-test"
        resultats.mkdir(parents=True)
        run_json = resultats / "run.json"
        run_json.write_text('{"etat": "completed"}', encoding="utf-8")

        liberation = threading.Event()
        self.addCleanup(liberation.set)
        self.creneau.demarrer(
            TYPE_EXECUTION,
            lambda travailleur: liberation.wait(DELAI),
            cible="org/modele",
        )

        reponse = self.post_autorise(
            "/modeles/supprimer", donnees={"moteur": MOTEUR, "cle": cle}
        )
        corps = self.verifier_page_erreur(reponse, 409)
        self.assertIn("exécution en cours", corps)
        self.assertNotIn("opération longue", corps)
        self.assertEqual(self.instantane_fichiers(dossier), avant)
        self.assertTrue((dossier / NOM_MARQUEUR).is_file())
        self.assertEqual(
            run_json.read_text(encoding="utf-8"), '{"etat": "completed"}'
        )
        self.assertEqual(self.creneau.instantane().etat, "en_cours")

        liberation.set()
        self.attendre()
        reponse = self.post_autorise(
            "/modeles/supprimer", donnees={"moteur": MOTEUR, "cle": cle}
        )
        self.assertEqual(reponse.status_code, 303)
        self.assertIn("action=modele-supprime", reponse.headers["Location"])
        self.assertFalse(dossier.exists())
        self.assertEqual(
            run_json.read_text(encoding="utf-8"), '{"etat": "completed"}'
        )

    def test_suppression_pendant_autre_operation_reste_generique(self) -> None:
        cle = self.preparer_modele_pret()
        dossier = self.dossier_data / "models" / MOTEUR / cle
        avant = self.instantane_fichiers(dossier)
        liberation = threading.Event()
        self.addCleanup(liberation.set)
        self.creneau.demarrer(
            TYPE_TELECHARGEMENT,
            lambda travailleur: liberation.wait(DELAI),
            cible="org/autre",
        )

        reponse = self.post_autorise(
            "/modeles/supprimer", donnees={"moteur": MOTEUR, "cle": cle}
        )
        corps = self.verifier_page_erreur(reponse, 409)
        self.assertIn("opération longue", corps)
        self.assertNotIn("exécution en cours", corps)
        self.assertEqual(self.instantane_fichiers(dossier), avant)

        liberation.set()
        self.attendre()

    def test_suppression_apres_arret_refusee_en_503_fichiers_intacts(self) -> None:
        cle = self.preparer_modele_pret()
        dossier = self.dossier_data / "models" / MOTEUR / cle
        avant = self.instantane_fichiers(dossier)
        self.creneau.arreter(0.5)

        reponse = self.post_autorise(
            "/modeles/supprimer", donnees={"moteur": MOTEUR, "cle": cle}
        )
        corps = self.verifier_page_erreur(reponse, 503)
        self.assertIn("arrêt", corps)
        self.assertEqual(self.instantane_fichiers(dossier), avant)

    def test_apres_arret_refuse_en_503_sans_io(self) -> None:
        self.creneau.arreter(0.5)
        reponse = self.post_autorise(
            "/modeles/verifier",
            donnees={"identifiant": "org/modele", "moteur": MOTEUR},
        )
        self.verifier_page_erreur(reponse, 503)
        self.assertEqual(self.verification_client.appels_infos, [])
        self.assertFalse(self.dossier_data.exists())

    def test_empreinte_absente_ou_perimee_refusee_sans_telechargement(self) -> None:
        corps = self.verifier_depuis_la_page()
        self.assertIn("Télécharger", corps)

        for empreinte in ("", "a" * 64):
            with self.subTest(empreinte=empreinte):
                reponse = self.post_autorise(
                    "/modeles/telecharger", donnees={"empreinte": empreinte}
                )
                self.verifier_page_erreur(reponse, 400)
        self.assertEqual(self.telechargement.appels, [])
        self.assertFalse(self.dossier_data.joinpath("models").exists())

    def test_page_echappe_resultat_et_modele_locaux(self) -> None:
        modele = ModeleLocal(
            moteur=MOTEUR,
            cle="b" * 64,
            identifiant="<script>alert(1)</script>",
            id_resolu="org/modele",
            commit=COMMIT,
            famille="<img src=x>",
            fichier_gguf=None,
            fichiers=(FichierVerifie("<b>poids.bin</b>", 3),),
            taille_disque=3,
            date="<i>2026-10-25</i>",
        )
        resultat = ResultatVerification(
            accepte=False,
            identifiant="org/modele",
            moteur=MOTEUR,
            famille="whisper",
            commit=COMMIT,
            raison=RAISON_FICHIER_GGUF_NON_CHOISI,
            message="<script>refus</script>",
            gguf_candidats=("modele-a.gguf", "modele-00001-of-00002.gguf"),
        )
        app = self.construire_app(
            self.services(
                modeles=FausseGestion(
                    resultat=resultat,
                    inventaire=(modele,),
                    moteurs=(EtatMoteur(MOTEUR, "Moteur de test", ETAT_PRET),),
                )
            )
        )
        corps = (
            app.test_client()
            .get("/modeles", base_url=self.base_url())
            .get_data(as_text=True)
        )
        self.assertNotIn("<script>", corps)
        self.assertNotIn("<img src=x>", corps)
        self.assertNotIn("<b>poids.bin</b>", corps)
        self.assertIn("&lt;script&gt;", corps)
        self.assertIn("&lt;img src=x&gt;", corps)
        self.assertIn("&lt;b&gt;poids.bin&lt;/b&gt;", corps)
        self.assertIn("Vérifier avec modele-a.gguf", corps)
        self.assertIn("Vérifier avec modele-00001-of-00002.gguf", corps)
        self.assertIn("fragment", corps)
        self.verifier_html_seul(corps)

        revisions = re.findall(
            r'<input type="hidden" name="revision" value="([0-9a-f]{40})">', corps
        )
        self.assertEqual(revisions, [COMMIT, COMMIT])
        for bloc in corps.split("<form")[1:]:
            if "fichier_gguf" in bloc:
                self.assertIn(f'name="revision" value="{COMMIT}"', bloc)

    def test_sans_moteur_installation_indisponible_expliquee(self) -> None:
        app = self.construire_app(
            self.services(modeles=FausseGestion(moteurs=()))
        )
        corps = (
            app.test_client()
            .get("/modeles", base_url=self.base_url())
            .get_data(as_text=True)
        )
        self.assertIn("Aucun moteur réel n'est installé", corps)
        self.assertIn("moteur factice", corps)
        self.assertIn("ne télécharge aucun poids", corps)


if __name__ == "__main__":
    unittest.main()
