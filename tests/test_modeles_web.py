"""Tests de la page des modèles et des actions POST associées.

Les services sont injectés : une vérification simulée et un téléchargement
simulé écrivent uniquement dans un dossier temporaire. Aucun moteur réel n'est
installé, aucun poids n'est téléchargé et aucune requête réseau n'est émise.
"""

from __future__ import annotations

import html
import re
import threading
import unittest
from pathlib import Path

from engines.registre import RegistreMoteurs
from tests.test_gestion_modeles import FauxClientTelechargement, FauxMoteurs
from tests.test_audios import ecrire_wav
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
from transcription_bench.executions import (
    MESSAGE_AUDIO_AUCUN,
    ConfigurationExecutions,
)
from transcription_bench.gestion_modeles import (
    NOM_MARQUEUR,
    GestionModeles,
    ModeleLocal,
)
from transcription_bench.moteurs import ETAT_PRET, EtatMoteur
from transcription_bench.operations import (
    ETAT_EN_COURS,
    ETAT_LIBRE,
    TYPE_EXECUTION,
    TYPE_TELECHARGEMENT,
    InstantaneCreneau,
)
from transcription_bench.verification_modeles import (
    FichierVerifie,
    ResultatVerification,
    VerificationModeles,
)
from transcription_bench.web.vues_modeles import (
    formater_taille_modele,
    vues_modeles_locaux,
)

DELAI = 5.0
MOTEUR = "moteur-de-test"
#: Phrase de l'explication générale unique de la page (tâche 5.1).
EXPLICATION_GENERALE = (
    "les transcriptions et mesures déjà consignées ne sont pas modifiées"
)


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

    def inventaire_rendu(self, corps: str) -> str:
        """Partie du HTML propre à l'inventaire, avant l'espace d'ajout."""
        debut = corps.index("<h2>Modèles locaux prêts</h2>")
        fin = corps.index('id="ajouter-un-modele"')
        return corps[debut:fin]

    def test_inventaire_avant_le_formulaire_d_ajout(self) -> None:
        # Spec « Inventaire des modèles locaux » : la liste des modèles prêts
        # est le premier contenu fonctionnel ; l'ajout ne la précède jamais.
        self.preparer_modele_pret()
        corps = self.page()

        titre = corps.index("<h1>Modèles</h1>")
        inventaire = corps.index("<h2>Modèles locaux prêts</h2>")
        ajout = corps.index('id="ajouter-un-modele"')
        formulaire = corps.index('action="/modeles/verifier"')
        self.assertLess(titre, inventaire)
        self.assertLess(inventaire, ajout)
        self.assertLess(ajout, formulaire)
        # Le modèle prêt est atteignable sans traverser le formulaire d'ajout.
        self.assertLess(corps.index(">Utiliser</a>"), ajout)

    def test_etat_vide_court_avant_l_ajout(self) -> None:
        corps = self.page()

        vide = corps.index("Aucun modèle local prêt")
        ajout = corps.index('id="ajouter-un-modele"')
        self.assertLess(vide, ajout)
        self.assertIn('href="#ajouter-un-modele"', corps)
        self.assertNotIn('class="grid cols-2"', corps)

    def test_etat_vide_sans_moteur_oriente_vers_l_installation(self) -> None:
        app = self.construire_app(self.services(modeles=FausseGestion(moteurs=())))
        corps = (
            app.test_client()
            .get("/modeles", base_url=self.base_url())
            .get_data(as_text=True)
        )

        vide = corps.index("Aucun modèle local prêt")
        self.assertLess(vide, corps.index('id="ajouter-un-modele"'))
        self.assertIn('href="/moteurs"', corps[: corps.index('id="ajouter-un-modele"')])
        self.assertNotIn('href="#ajouter-un-modele"', corps)

    def test_ajout_replie_par_defaut_sans_solliciter_de_depot(self) -> None:
        # Tâche 5.2 : l'espace d'ajout est un accordéon fermé par défaut ;
        # l'afficher ne vérifie aucun dépôt et ne télécharge rien, et son
        # ouverture reste un choix local du navigateur, sans script.
        corps = self.page()

        self.assertIn('<details id="ajouter-un-modele">', corps)
        self.assertIn("<summary>Ajouter un modèle</summary>", corps)
        self.assertIn('action="/modeles/verifier"', corps)
        self.assertNotIn('action="/modeles/telecharger"', corps)
        self.assertEqual(self.verification_client.appels_infos, [])
        self.assertEqual(self.telechargement.appels, [])
        self.assertFalse(self.dossier_data.exists())

    def test_get_sans_verification_ni_telechargement_meme_repete(self) -> None:
        # Le service factice lève une erreur à toute action : rendre la page
        # plusieurs fois ne sollicite ni dépôt ni téléchargement et ne pose
        # aucun script ni contrôle d'ouverture automatique.
        app = self.construire_app(
            self.services(
                modeles=FausseGestion(
                    moteurs=(EtatMoteur(MOTEUR, "Moteur de test", ETAT_PRET),)
                )
            )
        )
        client = app.test_client()
        for _ in range(2):
            reponse = client.get("/modeles", base_url=self.base_url())
            self.assertEqual(reponse.status_code, 200)
            corps = reponse.get_data(as_text=True)
            self.verifier_html_seul(corps)

        self.assertNotIn("autofocus", corps)
        self.assertNotIn("onload", corps)
        self.assertIn('<details id="ajouter-un-modele">', corps)

    def test_retour_de_verification_ouvre_l_ajout(self) -> None:
        # Tâche 5.2 : le retour POST 303 d'une vérification rouvre l'accordéon
        # pour que son résultat reste visible sans geste supplémentaire.
        corps = self.verifier_depuis_la_page()

        self.assertIn('<details id="ajouter-un-modele" open>', corps)
        self.assertIn("Taille à télécharger :", corps)

    def resultat_accepte_avec_tailles(self) -> ResultatVerification:
        """Résultat accepté aux tailles connues, sans aucun dépôt réel."""
        return ResultatVerification(
            accepte=True,
            identifiant="org/modele",
            moteur=MOTEUR,
            famille="whisper",
            commit=COMMIT,
            id_resolu="org/modele",
            fichiers=(
                FichierVerifie("model.bin", 300_000_000),
                FichierVerifie("config.json", 1024),
            ),
            taille_totale=300_001_024,
            message="famille whisper reconnue",
        )

    def test_taille_previsionnelle_lisible_brute_en_detail(self) -> None:
        # Tâche 5.2 : les tailles annoncées par la vérification sont lisibles
        # près du bouton de téléchargement ; les octets bruts restent dans le
        # seul détail technique (tâche 5.3).
        app = self.construire_app(
            self.services(
                modeles=FausseGestion(
                    resultat=self.resultat_accepte_avec_tailles(),
                    moteurs=(EtatMoteur(MOTEUR, "Moteur de test", ETAT_PRET),),
                )
            )
        )
        corps = (
            app.test_client()
            .get("/modeles", base_url=self.base_url())
            .get_data(as_text=True)
        )

        self.assertIn('<details id="ajouter-un-modele" open>', corps)
        rendu = html.unescape(corps)
        self.assertIn("Taille à télécharger : 286,1 Mio, fichiers retenus :", rendu)
        self.assertIn("model.bin : 286,1 Mio", rendu)
        self.assertIn("config.json : < 0,1 Mio", rendu)
        self.assertIn("Télécharger ce modèle à la révision vérifiée", rendu)

        technique = corps.index(
            "<summary>Fichiers du modèle et identifiants</summary>"
        )
        premier_niveau = corps[
            corps.index("Dépôt compatible") : technique
        ]
        self.assertIsNone(
            re.search(r"\d+ octets", premier_niveau),
            "taille en octets bruts au premier niveau du résultat",
        )
        self.assertIn("300001024 octets", corps[technique:])
        self.assertIn("300000000 octets", corps[technique:])

    def test_choix_gguf_au_meme_endroit_que_le_refus(self) -> None:
        # Spec « Ajout secondaire explicite » : le motif du refus et les choix
        # de fichier GGUF restent visibles ensemble, jamais répétés dans
        # l'inventaire des modèles prêts.
        refus = ResultatVerification(
            accepte=False,
            identifiant="org/modele",
            moteur=MOTEUR,
            famille=None,
            commit=COMMIT,
            raison=RAISON_FICHIER_GGUF_NON_CHOISI,
            message="plusieurs fichiers GGUF autonomes",
            gguf_candidats=("modele-a.gguf", "modele-b.gguf"),
        )
        modele = ModeleLocal(
            moteur=MOTEUR,
            cle="d" * 64,
            identifiant="org/modele",
            id_resolu="org/modele",
            commit=COMMIT,
            famille="whisper",
            fichier_gguf=None,
            fichiers=(FichierVerifie("model.bin", 3),),
            taille_disque=3,
            date="2026-10-25",
        )
        app = self.construire_app(
            self.services(
                modeles=FausseGestion(
                    resultat=refus,
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

        self.assertIn('<details id="ajouter-un-modele" open>', corps)
        self.assertIn("Dépôt refusé", corps)
        self.assertLess(
            corps.index("Dépôt refusé"), corps.index("Variantes GGUF proposées")
        )
        for candidat in ("modele-a.gguf", "modele-b.gguf"):
            with self.subTest(candidat=candidat):
                self.assertEqual(corps.count(f"Vérifier avec {candidat}"), 1)

        inventaire = self.inventaire_rendu(corps)
        self.assertNotIn("Variantes GGUF proposées", inventaire)
        self.assertNotIn("Vérifier avec", inventaire)

    def test_verification_sans_telechargement_puis_confirmation_dediee(self) -> None:
        # Tâche 5.2 : vérifier et télécharger restent deux actions séparées.
        corps = self.verifier_depuis_la_page()

        self.assertEqual(self.telechargement.appels, [])
        self.assertFalse((self.dossier_data / "models").exists())
        self.assertIn('action="/modeles/verifier"', corps)
        self.assertIn('action="/modeles/telecharger"', corps)

        reponse = self.post_autorise(
            "/modeles/telecharger", donnees={"empreinte": self.empreinte(corps)}
        )
        self.assertEqual(reponse.status_code, 303)
        self.attendre()
        self.assertEqual(len(self.telechargement.appels), 1)
        self.assertEqual(len(self.verification_client.appels_infos), 1)

    def test_explication_generale_unique(self) -> None:
        cle = self.preparer_modele_pret()
        corps = self.page()

        self.assertEqual(corps.count(EXPLICATION_GENERALE), 1)
        self.assertGreater(
            corps.index(EXPLICATION_GENERALE), corps.index("Modèles locaux prêts")
        )
        self.assertLess(
            corps.index(EXPLICATION_GENERALE), corps.index('id="ajouter-un-modele"')
        )

        reponse = self.post_autorise(
            "/modeles/supprimer", donnees={"moteur": MOTEUR, "cle": cle}
        )
        self.assertEqual(reponse.status_code, 303)
        corps = self.client.get(
            reponse.headers["Location"], base_url=self.base_url()
        ).get_data(as_text=True)
        self.assertIn("Modèle local supprimé.", corps)
        # Le message d'action ne répète pas l'explication de conservation.
        self.assertEqual(corps.count(EXPLICATION_GENERALE), 1)

    def test_taille_lisible_sans_octets_bruts(self) -> None:
        self.preparer_modele_pret()
        corps = self.inventaire_rendu(self.page())

        self.assertIn("0,1 Mio", corps)
        self.assertIsNone(
            re.search(r"\d+ octets", corps),
            "taille en octets bruts au premier niveau de l'inventaire",
        )
        self.assertIn("Taille sur disque", corps)

    def modeles_pour_executions(self, cle: str) -> FausseGestion:
        """Inventaire dont le moteur est l'une des quatre déclarations fournies.

        `/executions` construit son service avec le registre fourni de
        l'application ; un modèle local dont le moteur n'y est pas déclaré n'y
        est pas proposable. Le moteur `faster-whisper` et la famille `whisper`
        de cette déclaration rendent la sélection réellement testable.
        """
        modele = ModeleLocal(
            moteur="faster-whisper",
            cle=cle,
            identifiant="org/modele",
            id_resolu="org/modele",
            commit=COMMIT,
            famille="whisper",
            fichier_gguf=None,
            fichiers=(FichierVerifie("model.bin", 3),),
            taille_disque=3,
            date="2026-10-25",
        )
        return FausseGestion(
            inventaire=(modele,),
            moteurs=(EtatMoteur(MOTEUR, "Moteur de test", ETAT_PRET),),
        )

    def test_utiliser_preselectionne_le_modele_dans_executions(self) -> None:
        cle = "c" * 64
        app = self.construire_app(
            self.services(modeles=self.modeles_pour_executions(cle))
        )
        client = app.test_client()
        # Un audio synthétique rend la préparation applicable : sans audio
        # lisible, la page Exécutions remplace les contrôles. Il est écrit dans
        # le dossier temporaire du test, sans aucun contenu personnel.
        dossier_audio = self.dossier_data / "audio"
        dossier_audio.mkdir(parents=True, exist_ok=True)
        ecrire_wav(dossier_audio / "prise.wav", duree=0.1)

        corps = client.get("/modeles", base_url=self.base_url()).get_data(as_text=True)
        reference = f"faster-whisper/{cle}"

        trouve = re.search(r'href="(/executions\?modele=[^"]+)"', corps)
        self.assertIsNotNone(trouve, "action Utiliser absente")
        self.assertEqual(
            html.unescape(trouve.group(1)), f"/executions?modele={reference}"
        )

        page = client.get(html.unescape(trouve.group(1)), base_url=self.base_url())
        rendu = html.unescape(page.get_data(as_text=True))
        # Le lien ne choisit aucun audio : omission, pas valeur périmée. La page
        # retient le modèle demandé, annonce le repli sur le premier audio
        # lisible dans le bandeau neutre et rend en 200 : un parcours normal
        # depuis Modèles n'est jamais présenté comme une demande refusée.
        self.assertEqual(page.status_code, 200)
        self.assertIn(MESSAGE_AUDIO_AUCUN, rendu)
        self.assertNotIn(
            f'<p class="callout warning prose" role="alert">{MESSAGE_AUDIO_AUCUN}',
            rendu,
        )
        self.assertIn(
            f'<option value="{reference}" data-moteur="faster-whisper" selected>',
            rendu,
        )
        self.assertIn("Modèle : <strong>org/modele</strong>", rendu)
        self.verifier_html_seul(rendu)

    def test_utiliser_porte_la_reference_acceptee_par_le_service(self) -> None:
        # La référence du lien est celle que `ConfigurationExecutions` accepte :
        # aucune nouvelle API n'est introduite pour la sélection.
        cle = self.preparer_modele_pret()
        corps = self.page()
        trouve = re.search(r'href="(/executions\?modele=[^"]+)"', corps)
        self.assertIsNotNone(trouve)
        reference = html.unescape(trouve.group(1)).partition("modele=")[2]
        self.assertEqual(reference, f"{MOTEUR}/{cle}")

        service = ConfigurationExecutions(
            self.dossier_data, self.registre, self.gestion.inventaire
        )
        preparation = service.preparer(modele=reference)
        self.assertIsNotNone(preparation.modele)
        self.assertEqual(preparation.modele.reference, reference)
        self.assertIsNone(preparation.notice)

    def test_modele_actif_non_supprimable_et_refus_serveur(self) -> None:
        cle = self.preparer_modele_pret()
        dossier = self.dossier_data / "models" / MOTEUR / cle
        avant = self.instantane_fichiers(dossier)

        liberation = threading.Event()
        self.addCleanup(liberation.set)
        self.creneau.demarrer(
            TYPE_EXECUTION,
            lambda travailleur: liberation.wait(DELAI),
            cible="org/modele",
        )

        corps = self.page()
        self.assertIn('aria-disabled="true"', corps)
        self.assertIn("Supprimer ce modèle local", corps)
        self.assertIn("opération en cours", corps)
        self.assertNotIn('action="/modeles/supprimer"', corps)

        # Une requête forgée est refusée côté serveur, fichiers intactes.
        reponse = self.post_autorise(
            "/modeles/supprimer", donnees={"moteur": MOTEUR, "cle": cle}
        )
        corps_erreur = self.verifier_page_erreur(reponse, 409)
        self.assertIn("exécution en cours", corps_erreur)
        self.assertEqual(self.instantane_fichiers(dossier), avant)

        liberation.set()
        self.attendre()
        corps = self.page()
        self.assertIn('action="/modeles/supprimer"', corps)
        self.assertNotIn('aria-disabled="true"', corps)

    def test_modele_non_vise_reste_supprimable_apres_operation(self) -> None:
        cle = self.preparer_modele_pret()
        liberation = threading.Event()
        self.addCleanup(liberation.set)
        self.creneau.demarrer(
            TYPE_EXECUTION,
            lambda travailleur: liberation.wait(DELAI),
            cible="org/autre-modele",
        )

        corps = self.page()
        self.assertNotIn('aria-disabled="true"', corps)
        self.assertIn('action="/modeles/supprimer"', corps)
        liberation.set()
        self.attendre()
        reponse = self.post_autorise(
            "/modeles/supprimer", donnees={"moteur": MOTEUR, "cle": cle}
        )
        self.assertEqual(reponse.status_code, 303)

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


class TailleModeleTest(unittest.TestCase):
    """Format lisible des tailles de modèles et vues de l'inventaire (5.1)."""

    def test_format_binaire_sans_octets_bruts(self) -> None:
        cas = {
            None: "taille inconnue",
            0: "0 Mio",
            10: "< 0,1 Mio",
            104_857: "< 0,1 Mio",
            104_858: "0,1 Mio",
            1_048_576: "1 Mio",
            3 * 1_048_576 // 2: "1,5 Mio",
            2 * 1024**3 + 1024**3 // 2: "2,5 Gio",
            -1: "indisponible",
            True: "indisponible",
            "1024": "indisponible",
            1.5: "indisponible",
        }
        for valeur, attendu in cas.items():
            with self.subTest(valeur=valeur):
                self.assertEqual(formater_taille_modele(valeur), attendu)

    def modele(self, identifiant: str = "org/modele") -> ModeleLocal:
        return ModeleLocal(
            moteur=MOTEUR,
            cle="a" * 64,
            identifiant=identifiant,
            id_resolu="org/modele",
            commit=COMMIT,
            famille="whisper",
            fichier_gguf=None,
            fichiers=(FichierVerifie("model.bin", 3),),
            taille_disque=3,
            date="2026-10-25",
        )

    def instantane(self, etat: str, cible: str | None) -> InstantaneCreneau:
        return InstantaneCreneau(
            etat=etat,
            arrete=False,
            type_operation=TYPE_EXECUTION if cible else None,
            cible=cible,
            debut=None,
            fin=None,
            erreur=None,
            journal=(),
            generation=1,
        )

    def test_vue_porte_reference_et_etat_actif(self) -> None:
        (vue,) = vues_modeles_locaux(
            (self.modele(),), self.instantane(ETAT_LIBRE, None)
        )

        self.assertEqual(vue["reference"], f"{MOTEUR}/{'a' * 64}")
        self.assertEqual(vue["taille_disque"], 3)
        self.assertFalse(vue["actif"])

        (actif,) = vues_modeles_locaux(
            (self.modele(),), self.instantane(ETAT_EN_COURS, "org/modele")
        )
        self.assertTrue(actif["actif"])

        (autre,) = vues_modeles_locaux(
            (self.modele(),), self.instantane(ETAT_EN_COURS, "org/autre")
        )
        self.assertFalse(autre["actif"])


if __name__ == "__main__":
    unittest.main()
