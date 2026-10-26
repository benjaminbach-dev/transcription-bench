"""Tests du formulaire d'exécution et de la demande validée (tâche 6.2).

Le service est exercé avec une déclaration synthétique qui expose des réglages
des quatre types, un inventaire de modèles factice et une liste d'audios
factice : aucun moteur, aucun poids, aucun audio réel et aucun réseau. Les tests
de page réutilisent le socle de `tests/test_web.py` et vérifient qu'aucune
exécution n'est lancée et qu'aucun dossier de données n'est créé.
"""

from __future__ import annotations

import unittest
from pathlib import Path

from engines.declarations import (
    TYPE_BOOLEEN,
    TYPE_CHOIX,
    TYPE_ENTIER,
    TYPE_TEXTE,
    DECLARATION_FACTICE,
    DeclarationAdaptateur,
    DureeNative,
    Famille,
    Reglage,
)
from engines.registre import RegistreMoteurs, creer_registre_fourni
from engines.runner import FENETRE_SECONDES
from tests.test_web import SocleWebTest
from transcription_bench.audios import AudioListe
from transcription_bench.executions import (
    CLE_MODELE_FACTICE,
    FENETRE_FIXE_SECONDES,
    LIBELLE_MODELE_FACTICE,
    NOMBRE_THREADS_MINIMUM,
    PREFIXE_CHAMP_REGLAGE,
    ConfigurationExecutions,
    ReglageValide,
    refuser_champs_repetes,
    reglages_depuis_formulaire,
    threads_par_defaut,
)
from transcription_bench.gestion_modeles import ModeleLocal
from transcription_bench.paths import ValeurRefusee

MOTEUR = "moteur-de-test"
CLE = "a" * 64
AUTRE_CLE = "c" * 64
COMMIT = "b" * 40
THREADS_DEFAUT = 4

REGLAGES = (
    Reglage(
        "compute_type",
        "Type de calcul",
        TYPE_CHOIX,
        "float32",
        "Précision de calcul demandée au moteur.",
        valeurs=("float32", "int8"),
    ),
    Reglage(
        "beam_size",
        "Largeur du faisceau",
        TYPE_ENTIER,
        5,
        "Nombre d'hypothèses conservées pendant le décodage.",
    ),
    Reglage(
        "vad_filter",
        "Filtre de silence",
        TYPE_BOOLEEN,
        False,
        "Active le filtre de détection d'activité vocale.",
    ),
    Reglage(
        "prompt",
        "Amorce",
        TYPE_TEXTE,
        "",
        "Texte d'amorce facultatif.",
    ),
)

AUDIOS = (
    AudioListe("a.wav", "wav", 1_000, 1.0),
    AudioListe("b.wav", "wav", 2_000, 2.5),
    AudioListe(
        "illisible.wav",
        "wav",
        500,
        None,
        "lecture impossible : illisible.wav (fichier invalide)",
    ),
)


def declaration_avec_reglages(
    *,
    identifiant: str = MOTEUR,
    famille: str = "whisper",
    reglages: tuple[Reglage, ...] = REGLAGES,
    duree_native: DureeNative | None = None,
    qualifiee: bool = True,
) -> DeclarationAdaptateur:
    """Déclaration synthétique : mêmes formes que les vraies, sans dépendance.

    `qualifiee=True` par défaut : les tests de la voie valide décrivent une
    famille que le runner accepterait, sans quoi elle serait non exécutable.
    """
    return DeclarationAdaptateur(
        identifiant=identifiant,
        nom="Moteur de test",
        fichier_requirements=None,
        regle_compatibilite="transformers-safetensors",
        familles=(
            Famille(
                famille,
                "Whisper",
                qualifiee=qualifiee,
                duree_native=duree_native,
                reglages=reglages,
            ),
        ),
    )


def modele_prete(
    *,
    moteur: str = MOTEUR,
    cle: str = CLE,
    famille: str = "whisper",
    identifiant: str = "org/modele",
) -> ModeleLocal:
    """Modèle prêt factice, tel qu'un inventaire 5.4 le relirait."""
    return ModeleLocal(
        moteur=moteur,
        cle=cle,
        identifiant=identifiant,
        id_resolu="org/modele",
        commit=COMMIT,
        famille=famille,
        fichier_gguf=None,
        fichiers=(),
        taille_disque=0,
        date="2026-10-25T00:00:00+00:00",
    )


class SocleExecutionsTest(unittest.TestCase):
    """Service construit avec un registre, un inventaire et des audios factices."""

    def setUp(self) -> None:
        self.registre = RegistreMoteurs()
        self.registre.enregistrer(declaration_avec_reglages())
        self.modeles: tuple[ModeleLocal, ...] = (modele_prete(),)
        self.dossiers_lus: list[object] = []
        self.service = self.construire()

    def construire(
        self,
        *,
        registre: RegistreMoteurs | None = None,
        modeles=None,
        compter_threads=None,
    ) -> ConfigurationExecutions:
        return ConfigurationExecutions(
            "/donnees",
            registre or self.registre,
            lambda: self.modeles if modeles is None else modeles,
            lister=self.lister_audios,
            compter_threads=compter_threads or (lambda: THREADS_DEFAUT),
        )

    def lister_audios(self, dossier) -> tuple[AudioListe, ...]:
        self.dossiers_lus.append(dossier)
        return AUDIOS

    def reference(self) -> str:
        return self.service.modeles_proposables()[0].reference


class ThreadsParDefautTest(unittest.TestCase):
    """Défaut des threads : cœurs physiques, repli logiques, repli 1 (D6)."""

    def test_coeurs_physiques_prioritaires(self) -> None:
        self.assertEqual(
            threads_par_defaut(lambda logical: 16 if logical else 8),
            8,
        )

    def test_repli_sur_les_coeurs_logiques(self) -> None:
        self.assertEqual(
            threads_par_defaut(lambda logical: 16 if logical else None),
            16,
        )

    def test_repli_minimal_si_aucun_comptage(self) -> None:
        self.assertEqual(threads_par_defaut(lambda logical: None), 1)
        self.assertEqual(threads_par_defaut(lambda logical: 0), 1)

    def test_service_jamais_sous_le_minimum(self) -> None:
        service = ConfigurationExecutions(
            "/donnees", RegistreMoteurs(), lambda: (), compter_threads=lambda: 0
        )
        self.assertEqual(service.threads_par_defaut(), NOMBRE_THREADS_MINIMUM)


class ModelesProposesTest(SocleExecutionsTest):
    """Seuls les modèles prêts des familles déclarées sont proposés."""

    def test_reglages_exactement_ceux_de_la_declaration(self) -> None:
        propose = self.service.modeles_proposables()[0]

        self.assertEqual(propose.moteur, MOTEUR)
        self.assertEqual(propose.cle, CLE)
        self.assertEqual(propose.famille, "whisper")
        self.assertEqual([reglage.nom for reglage in propose.reglages], [
            "compute_type",
            "beam_size",
            "vad_filter",
            "prompt",
        ])
        self.assertEqual(propose.reference, f"{MOTEUR}/{CLE}")

    def test_fenetre_fixe_annoncee_sans_mecanisme_natif(self) -> None:
        propose = self.service.modeles_proposables()[0]

        self.assertEqual(propose.fenetre_fixe_secondes, FENETRE_FIXE_SECONDES)
        self.assertEqual(FENETRE_FIXE_SECONDES, FENETRE_SECONDES)

    def test_mecanisme_natif_declare_sans_fenetre_fixe(self) -> None:
        registre = RegistreMoteurs()
        registre.enregistrer(
            declaration_avec_reglages(
                duree_native=DureeNative(60.0, "encodage en un seul appel")
            )
        )
        service = self.construire(registre=registre)

        propose = service.modeles_proposables()[0]

        self.assertIsNone(propose.fenetre_fixe_secondes)
        self.assertFalse(propose.executable)
        self.assertIn("mécanisme natif", propose.motif_non_executable or "")

    def test_famille_non_qualifiee_proposee_non_executable_et_refusee(self) -> None:
        registre = RegistreMoteurs()
        registre.enregistrer(declaration_avec_reglages(qualifiee=False))
        service = self.construire(registre=registre)

        propose = service.modeles_proposables()[0]

        self.assertFalse(propose.executable)
        self.assertIn("non qualifiée", propose.motif_non_executable or "")
        with self.assertRaises(ValeurRefusee) as contexte:
            service.valider(
                modele=propose.reference,
                audios=["a.wav"],
                threads="4",
                reglages={},
            )
        self.assertIn("non exécutable", str(contexte.exception))

    def test_modele_synthetique_factice_propose_sans_inventaire(self) -> None:
        registre = RegistreMoteurs()
        registre.enregistrer(DECLARATION_FACTICE)
        service = ConfigurationExecutions(
            "/donnees",
            registre,
            lambda: (),
            lister=self.lister_audios,
            compter_threads=lambda: THREADS_DEFAUT,
        )

        proposes = service.modeles_proposables()

        self.assertEqual(len(proposes), 1)
        propose = proposes[0]
        self.assertEqual(propose.moteur, "factice")
        self.assertEqual(propose.cle, CLE_MODELE_FACTICE)
        self.assertEqual(len(propose.cle), 64)
        self.assertEqual(
            propose.reference, f"factice/{CLE_MODELE_FACTICE}"
        )
        self.assertEqual(propose.identifiant, LIBELLE_MODELE_FACTICE)
        self.assertTrue(propose.executable)
        self.assertTrue(propose.synthetique)
        self.assertIsNone(propose.motif_non_executable)
        self.assertIsNone(propose.fichier_gguf)
        self.assertEqual(propose.reglages, ())
        self.assertEqual(propose.fenetre_fixe_secondes, FENETRE_FIXE_SECONDES)

        demande = service.valider(
            modele=propose.reference,
            audios=["a.wav"],
            threads="2",
            reglages={},
        )
        self.assertEqual(demande.moteur, "factice")
        self.assertEqual(demande.famille, "factice")
        self.assertEqual(demande.identifiant, LIBELLE_MODELE_FACTICE)
        self.assertTrue(demande.synthetique)

    def test_pas_de_modele_synthetique_sans_declaration_factice(self) -> None:
        proposes = self.service.modeles_proposables()

        self.assertEqual([propose.moteur for propose in proposes], [MOTEUR])
        self.assertFalse(any(propose.synthetique for propose in proposes))

    def test_moteur_non_declare_ignore(self) -> None:
        self.modeles = (modele_prete(moteur="moteur-absent"),)

        self.assertEqual(self.service.modeles_proposables(), ())

    def test_famille_non_declaree_ignoree(self) -> None:
        self.modeles = (modele_prete(famille="parakeet-tdt"),)

        self.assertEqual(self.service.modeles_proposables(), ())

    def test_inventaire_refuse_donne_une_liste_vide(self) -> None:
        def inventaire_refuse():
            raise ValeurRefusee("inventaire illisible")

        service = ConfigurationExecutions(
            "/donnees", self.registre, inventaire_refuse, lister=self.lister_audios
        )

        self.assertEqual(service.modeles_proposables(), ())

    def test_inventaire_refuse_conserve_le_modele_synthetique_factice(self) -> None:
        def inventaire_refuse():
            raise OSError("inventaire illisible")

        registre = RegistreMoteurs()
        registre.enregistrer(DECLARATION_FACTICE)
        service = ConfigurationExecutions(
            "/donnees",
            registre,
            inventaire_refuse,
            lister=self.lister_audios,
            compter_threads=lambda: THREADS_DEFAUT,
        )

        proposes = service.modeles_proposables()

        self.assertEqual([propose.synthetique for propose in proposes], [True])
        self.assertTrue(proposes[0].executable)

    def test_audios_proposables_excluent_les_illisibles(self) -> None:
        audios = self.service.audios_proposables()

        self.assertEqual([audio.nom for audio in audios], ["a.wav", "b.wav"])
        self.assertEqual(self.dossiers_lus, [Path("/donnees")])


class ValidationDemandeTest(SocleExecutionsTest):
    """La demande validée consigne threads et réglages effectifs, refus compris."""

    def test_defauts_complets_et_ordre_des_audios(self) -> None:
        demande = self.service.valider(
            modele=self.reference(),
            audios=["b.wav", "a.wav"],
            threads=str(THREADS_DEFAUT),
            reglages={},
        )

        self.assertEqual(demande.audios, ("b.wav", "a.wav"))
        self.assertEqual(demande.threads, THREADS_DEFAUT)
        self.assertEqual(
            demande.reglages,
            (
                ReglageValide("compute_type", "float32"),
                ReglageValide("beam_size", 5),
                ReglageValide("vad_filter", False),
                ReglageValide("prompt", ""),
            ),
        )
        self.assertEqual(demande.fenetre_fixe_secondes, FENETRE_FIXE_SECONDES)
        self.assertEqual(demande.commit, COMMIT)
        self.assertEqual(demande.identifiant, "org/modele")
        self.assertEqual(demande.reglage("beam_size"), 5)
        self.assertIsNone(demande.reglage("temperature"))

    def test_valeurs_saisies_interpretees_selon_leur_type(self) -> None:
        demande = self.service.valider(
            modele=self.reference(),
            audios=["a.wav"],
            threads=" 3 ",
            reglages={
                "compute_type": "int8",
                "beam_size": "7",
                "vad_filter": "oui",
                "prompt": " consultation ",
            },
        )

        self.assertEqual(demande.threads, 3)
        self.assertEqual(demande.reglage("compute_type"), "int8")
        self.assertEqual(demande.reglage("beam_size"), 7)
        self.assertIs(demande.reglage("vad_filter"), True)
        self.assertEqual(demande.reglage("prompt"), "consultation")

    def test_reglage_non_declare_refuse(self) -> None:
        with self.assertRaises(ValeurRefusee) as contexte:
            self.service.valider(
                modele=self.reference(),
                audios=["a.wav"],
                threads="4",
                reglages={"temperature": "0.0", "fast": "oui"},
            )
        self.assertIn("temperature", str(contexte.exception))
        self.assertIn("fast", str(contexte.exception))

    def test_audio_hors_liste_ou_illisible_refuse(self) -> None:
        for nom in ("z.wav", "illisible.wav"):
            with self.subTest(nom=nom):
                with self.assertRaises(ValeurRefusee):
                    self.service.valider(
                        modele=self.reference(),
                        audios=[nom],
                        threads="4",
                        reglages={},
                    )

    def test_audio_en_double_ou_selection_vide_refusee(self) -> None:
        for audios in ([], ["a.wav", "a.wav"]):
            with self.subTest(audios=audios):
                with self.assertRaises(ValeurRefusee):
                    self.service.valider(
                        modele=self.reference(),
                        audios=audios,
                        threads="4",
                        reglages={},
                    )

    def test_modele_non_pret_ou_reference_invalide_refuse(self) -> None:
        references = (
            f"{MOTEUR}/{AUTRE_CLE}",
            "moteur-absent/" + CLE,
            CLE,
            f"{MOTEUR}/{CLE}extra",
            "",
        )
        for reference in references:
            with self.subTest(reference=reference):
                with self.assertRaises(ValeurRefusee):
                    self.service.valider(
                        modele=reference,
                        audios=["a.wav"],
                        threads="4",
                        reglages={},
                    )

    def test_threads_invalides_refuses(self) -> None:
        for threads in ("0", "-2", "4.0", "1.5", "", "  ", "quatre", True, None):
            with self.subTest(threads=threads):
                with self.assertRaises(ValeurRefusee):
                    self.service.valider(
                        modele=self.reference(),
                        audios=["a.wav"],
                        threads=threads,
                        reglages={},
                    )

    def test_threads_minimum_accepte(self) -> None:
        demande = self.service.valider(
            modele=self.reference(), audios=["a.wav"], threads="1", reglages={}
        )

        self.assertEqual(demande.threads, 1)

    def test_valeurs_de_reglage_invalides_refusees(self) -> None:
        cas = (
            {"compute_type": "float16"},
            {"beam_size": "5.5"},
            {"beam_size": ""},
            {"vad_filter": "peut-être"},
            {"vad_filter": "True"},
        )
        for reglages in cas:
            with self.subTest(reglages=reglages):
                with self.assertRaises(ValeurRefusee):
                    self.service.valider(
                        modele=self.reference(),
                        audios=["a.wav"],
                        threads="4",
                        reglages=reglages,
                    )


class ReglagesFormulaireTest(unittest.TestCase):
    """Extraction des champs `reglage_<nom>` d'un formulaire."""

    def test_seuls_les_champs_prefixes_sont_extraits(self) -> None:
        champs = {
            "jeton_csrf": "secret",
            "modele": f"{MOTEUR}/{CLE}",
            "audios": "a.wav",
            "threads": "4",
            PREFIXE_CHAMP_REGLAGE + "beam_size": "7",
            PREFIXE_CHAMP_REGLAGE + "vad_filter": "oui",
        }

        self.assertEqual(
            reglages_depuis_formulaire(champs),
            {"beam_size": "7", "vad_filter": "oui"},
        )

    def test_prefixe_seul_devient_un_nom_vide_donc_inconnu(self) -> None:
        self.assertEqual(reglages_depuis_formulaire({PREFIXE_CHAMP_REGLAGE: "x"}), {"": "x"})

    def test_champs_repetes_refuses(self) -> None:
        cas = (
            [("modele", f"{MOTEUR}/{CLE}"), ("modele", f"{MOTEUR}/{AUTRE_CLE}")],
            [("threads", "4"), ("threads", "8")],
            [
                (PREFIXE_CHAMP_REGLAGE + "beam_size", "5"),
                (PREFIXE_CHAMP_REGLAGE + "beam_size", "7"),
            ],
        )
        for champs in cas:
            with self.subTest(champs=champs):
                with self.assertRaises(ValeurRefusee) as contexte:
                    refuser_champs_repetes(champs)
                self.assertIn(champs[0][0], str(contexte.exception))

    def test_champs_repetes_autorises_pour_les_audios_et_le_jeton(self) -> None:
        refuser_champs_repetes(
            [
                ("audios", "a.wav"),
                ("audios", "b.wav"),
                ("jeton_csrf", "x"),
                ("jeton_csrf", "y"),
                ("modele", f"{MOTEUR}/{CLE}"),
                ("threads", "4"),
            ]
        )


class PageExecutionsTest(SocleWebTest):
    """Page GET et prévisualisation POST : aucune exécution n'est lancée."""

    def setUp(self) -> None:
        super().setUp()
        self.registre = RegistreMoteurs()
        self.registre.enregistrer(declaration_avec_reglages())
        self.modeles: tuple[ModeleLocal, ...] = (modele_prete(),)
        self.service = ConfigurationExecutions(
            self.dossier_data,
            self.registre,
            lambda: self.modeles,
            lister=lambda dossier: AUDIOS,
            compter_threads=lambda: THREADS_DEFAUT,
        )
        self.app = self.construire_app(self.services(executions=self.service))
        self.client = self.app.test_client()

    def page(self, chemin: str = "/executions") -> str:
        reponse = self.client.get(chemin, base_url=self.base_url())
        self.assertEqual(reponse.status_code, 200, chemin)
        corps = reponse.get_data(as_text=True)
        self.verifier_html_seul(corps)
        return corps

    def reference(self) -> str:
        return self.service.modeles_proposables()[0].reference

    def test_page_sans_modele_proposable_annonce_le_lancement_indisponible(self) -> None:
        service = ConfigurationExecutions(
            self.dossier_data,
            RegistreMoteurs(),
            lambda: (),
            lister=lambda dossier: AUDIOS,
            compter_threads=lambda: THREADS_DEFAUT,
        )
        app = self.construire_app(self.services(executions=service))
        reponse = app.test_client().get("/executions", base_url=self.base_url())

        self.assertEqual(reponse.status_code, 200)
        corps = reponse.get_data(as_text=True)
        self.assertIn("Lancement non disponible", corps)
        self.assertIn("Aucun modèle proposable", corps)
        self.verifier_html_seul(corps)
        self.assertFalse(self.dossier_data.exists())

    def test_page_propose_le_modele_synthetique_factice(self) -> None:
        service = ConfigurationExecutions(
            self.dossier_data,
            creer_registre_fourni(),
            lambda: (),
            lister=lambda dossier: AUDIOS,
            compter_threads=lambda: THREADS_DEFAUT,
        )
        app = self.construire_app(self.services(executions=service))
        client = app.test_client()
        reponse = client.get("/executions", base_url=self.base_url())

        self.assertEqual(reponse.status_code, 200)
        corps = reponse.get_data(as_text=True)
        self.verifier_html_seul(corps)
        self.assertNotIn("Aucun modèle proposable", corps)
        self.assertIn(LIBELLE_MODELE_FACTICE, corps)
        self.assertIn(
            f'value="factice/{CLE_MODELE_FACTICE}"', corps
        )
        self.assertIn("textes et mesures simulés", corps)
        self.assertNotIn("Non exécutable", corps)

        validation = self.post_autorise(
            "/executions/verifier",
            donnees={
                "modele": f"factice/{CLE_MODELE_FACTICE}",
                "audios": ["a.wav"],
                "threads": "2",
            },
            app=app,
        )
        self.assertEqual(validation.status_code, 200)
        corps_valide = validation.get_data(as_text=True)
        self.assertIn("Demande validée", corps_valide)
        self.assertIn("modèle synthétique : aucun fichier", corps_valide)
        self.assertIn("<dd>factice</dd>", corps_valide)
        self.assertEqual(self.creneau.instantane().etat, "libre")
        self.assertFalse(self.dossier_data.exists())

    def test_page_affiche_non_executable_sans_formulaire(self) -> None:
        registre = RegistreMoteurs()
        registre.enregistrer(declaration_avec_reglages(qualifiee=False))
        service = ConfigurationExecutions(
            self.dossier_data,
            registre,
            lambda: self.modeles,
            lister=lambda dossier: AUDIOS,
            compter_threads=lambda: THREADS_DEFAUT,
        )
        app = self.construire_app(self.services(executions=service))

        corps = (
            app.test_client()
            .get("/executions", base_url=self.base_url())
            .get_data(as_text=True)
        )
        self.verifier_html_seul(corps)
        self.assertIn("Non exécutable", corps)
        self.assertIn("non qualifiée", corps)
        self.assertNotIn('name="modele"', corps)
        self.assertNotIn("fenêtres fixes de 30 s", corps)

    def test_post_refuse_un_modele_non_executable(self) -> None:
        registre = RegistreMoteurs()
        registre.enregistrer(declaration_avec_reglages(qualifiee=False))
        service = ConfigurationExecutions(
            self.dossier_data,
            registre,
            lambda: self.modeles,
            lister=lambda dossier: AUDIOS,
            compter_threads=lambda: THREADS_DEFAUT,
        )
        reference = service.modeles_proposables()[0].reference
        app = self.construire_app(self.services(executions=service))

        reponse = self.post_autorise(
            "/executions/verifier",
            donnees={"modele": reference, "audios": ["a.wav"], "threads": "4"},
            app=app,
        )

        self.verifier_page_erreur(reponse, 400)
        self.assertEqual(self.creneau.instantane().etat, "libre")

    def test_post_refuse_un_champ_repete(self) -> None:
        reference = self.reference()
        cas = (
            {"modele": [reference, reference], "audios": ["a.wav"], "threads": "4"},
            {"modele": reference, "audios": ["a.wav"], "threads": ["4", "8"]},
            {
                "modele": reference,
                "audios": ["a.wav"],
                "threads": "4",
                PREFIXE_CHAMP_REGLAGE + "beam_size": ["5", "7"],
            },
        )
        for donnees in cas:
            with self.subTest(donnees=donnees):
                reponse = self.post_autorise("/executions/verifier", donnees=donnees)
                self.verifier_page_erreur(reponse, 400)
                self.assertEqual(self.creneau.instantane().etat, "libre")

    def test_formulaire_propose_seulement_les_reglages_declares(self) -> None:
        corps = self.page()

        for nom in ("compute_type", "beam_size", "vad_filter", "prompt"):
            self.assertIn(f'name="{PREFIXE_CHAMP_REGLAGE}{nom}"', corps, nom)
        for nom in ("temperature", "language", "no_speech_threshold"):
            self.assertNotIn(f'name="{PREFIXE_CHAMP_REGLAGE}{nom}"', corps, nom)

        # Valeurs par défaut de la déclaration, sans valeur inventée.
        self.assertIn('value="5"', corps)
        self.assertIn('<option value="float32" selected>', corps)
        self.assertIn('value="non" checked', corps)
        self.assertIn('name="threads" value="4"', corps)

        # Audios lisibles seulement, et fenêtres fixes annoncées.
        self.assertIn("a.wav", corps)
        self.assertIn("b.wav", corps)
        self.assertNotIn("illisible.wav", corps)
        self.assertIn("fenêtres fixes de 30 s", corps)
        self.assertIn("Famille sans mécanisme natif", corps)
        self.assertNotIn("Non exécutable", corps)

    def test_post_valide_consigne_threads_et_ne_lance_rien(self) -> None:
        reponse = self.post_autorise(
            "/executions/verifier",
            donnees={
                "modele": self.reference(),
                "audios": ["b.wav", "a.wav"],
                "threads": "3",
                PREFIXE_CHAMP_REGLAGE + "beam_size": "7",
            },
        )

        self.assertEqual(reponse.status_code, 200)
        corps = reponse.get_data(as_text=True)
        self.verifier_html_seul(corps)
        self.assertIn("Demande validée", corps)
        self.assertIn("<dt>Threads demandés</dt>", corps)
        self.assertIn("<dd>3 (nombre demandé", corps)
        self.assertIn("beam_size : 7", corps)
        self.assertIn("compute_type : float32", corps)
        self.assertIn("vad_filter : non", corps)
        self.assertIn("prompt : (vide)", corps)
        self.assertIn("aucune exécution n'a été lancée", corps)
        self.assertIn("<li>b.wav</li>", corps)
        self.assertIn("<li>a.wav</li>", corps)
        self.assertLess(corps.index("<li>b.wav</li>"), corps.index("<li>a.wav</li>"))
        self.assertEqual(self.creneau.instantane().etat, "libre")
        self.assertFalse(self.dossier_data.exists())

    def test_post_refuse_reglage_inconnu(self) -> None:
        reponse = self.post_autorise(
            "/executions/verifier",
            donnees={
                "modele": self.reference(),
                "audios": ["a.wav"],
                "threads": "4",
                PREFIXE_CHAMP_REGLAGE + "temperature": "0.0",
            },
        )

        self.verifier_page_erreur(reponse, 400)
        self.assertEqual(self.creneau.instantane().etat, "libre")

    def test_post_refuse_audio_hors_liste_et_modele_non_pret(self) -> None:
        cas = (
            ("z.wav", self.reference()),
            ("illisible.wav", self.reference()),
            ("a.wav", f"{MOTEUR}/{AUTRE_CLE}"),
        )
        for audio, modele in cas:
            with self.subTest(audio=audio, modele=modele):
                reponse = self.post_autorise(
                    "/executions/verifier",
                    donnees={"modele": modele, "audios": [audio], "threads": "4"},
                )
                self.verifier_page_erreur(reponse, 400)

    def test_post_sans_jeton_refuse_sans_lancer(self) -> None:
        reponse = self.post_autorise(
            "/executions/verifier",
            donnees={
                "modele": self.reference(),
                "audios": ["a.wav"],
                "threads": "4",
            },
            jeton="jeton-invalide",
        )

        self.assertEqual(reponse.status_code, 403)
        self.assertEqual(self.creneau.instantane().etat, "libre")

    def test_page_echappe_les_valeurs_des_services(self) -> None:
        self.modeles = (
            modele_prete(identifiant="<script>alert(1)</script>"),
        )

        corps = self.page()

        self.assertNotIn("<script>", corps)
        self.assertIn("&lt;script&gt;", corps)

    def test_page_sans_audio_lisible(self) -> None:
        service = ConfigurationExecutions(
            self.dossier_data,
            self.registre,
            lambda: self.modeles,
            lister=lambda dossier: (AUDIOS[2],),
        )
        app = self.construire_app(self.services(executions=service))

        corps = (
            app.test_client()
            .get("/executions", base_url=self.base_url())
            .get_data(as_text=True)
        )

        self.assertIn("Aucun audio lisible", corps)
        self.assertNotIn("illisible.wav", corps)
        self.verifier_html_seul(corps)
