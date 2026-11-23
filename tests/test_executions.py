"""Tests des services d'exécution et de la demande validée (tâche 6.2).

Le service est exercé avec une déclaration synthétique qui expose des réglages
des quatre types, un inventaire de modèles factice et une liste d'audios
factice : aucun moteur, aucun poids, aucun audio réel et aucun réseau. La
préparation et le lancement ne sont plus des pages : la CLI les porte, et seule
une vérification de non-régression du web reste ici (routes supprimées).
"""

from __future__ import annotations

import unittest
from pathlib import Path

from engines.declarations import (
    TYPE_BOOLEEN,
    TYPE_CHOIX,
    TYPE_ENTIER,
    TYPE_TEXTE,
    TASK_EXTRACTION,
    DECLARATION_FACTICE,
    DECLARATION_LLAMA_CPP,
    DeclarationAdaptateur,
    DureeNative,
    Famille,
    Reglage,
)
from engines.registre import RegistreMoteurs
from engines.runner import FENETRE_SECONDES
from tests.test_web import SocleWebTest
from transcription_bench.audios import AudioListe
from transcription_bench.executions import (
    CLE_MODELE_FACTICE,
    CLE_MODELE_FACTICE_EXTRACTION,
    FENETRE_FIXE_SECONDES,
    LIBELLE_MODELE_FACTICE,
    MESSAGE_AUDIO_INCOHERENT,
    MESSAGE_MODELE_REINITIALISE,
    MESSAGE_MOTEUR_INCOHERENT,
    NOMBRE_THREADS_MINIMUM,
    PREFIXE_CHAMP_REGLAGE,
    ConfigurationExecutions,
    ReglageValide,
    proposer_modele,
    refuser_champs_repetes,
    reglages_depuis_champs,
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

    def test_extraction_family_has_no_fixed_window(self) -> None:
        # Extraction : chaque source fait un seul appel (engines/runner_extraction.py),
        # donc aucune fenêtre de 30 s. Modèle prêt simulé : seule la déclaration
        # réelle sert, aucun moteur n'est chargé.
        famille = DECLARATION_LLAMA_CPP.familles[0]
        self.assertEqual(famille.task, TASK_EXTRACTION)

        propose = proposer_modele(
            DECLARATION_LLAMA_CPP,
            famille,
            cle=CLE,
            identifiant="org/modele",
            id_resolu="org/modele",
            commit=COMMIT,
            fichier_gguf="modele.gguf",
            tache=TASK_EXTRACTION,
        )

        self.assertIsNone(propose.fenetre_fixe_secondes)
        self.assertTrue(propose.executable)
        self.assertIsNone(propose.motif_non_executable)

    def test_transcription_family_keeps_fixed_window(self) -> None:
        famille = declaration_avec_reglages().familles[0]

        propose = proposer_modele(
            declaration_avec_reglages(),
            famille,
            cle=CLE,
            identifiant="org/modele",
            id_resolu="org/modele",
            commit=COMMIT,
            fichier_gguf=None,
        )

        self.assertEqual(propose.fenetre_fixe_secondes, FENETRE_FIXE_SECONDES)

    def test_mecanisme_natif_declare_sans_fenetre_fixe_et_executable(self) -> None:
        registre = RegistreMoteurs()
        registre.enregistrer(
            declaration_avec_reglages(
                duree_native=DureeNative(60.0, "encodage en un seul appel")
            )
        )
        service = self.construire(registre=registre)

        propose = service.modeles_proposables()[0]

        # Le runner applique la durée native jusqu'à sa borne, puis découpe en
        # fenêtres fixes : ce n'est plus un motif de non-exécutabilité.
        self.assertIsNone(propose.fenetre_fixe_secondes)
        self.assertTrue(propose.executable)
        self.assertIsNone(propose.motif_non_executable)

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

        # Un modèle synthétique par famille : transcription, puis extraction.
        self.assertEqual(len(proposes), 2)
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
        extraction = proposes[1]
        self.assertEqual(extraction.famille, "factice-extraction")
        self.assertEqual(extraction.cle, CLE_MODELE_FACTICE_EXTRACTION)
        self.assertTrue(extraction.synthetique)
        self.assertIsNone(extraction.fenetre_fixe_secondes)
        # Famille d'extraction proposée à une exécution de transcription : refusée.
        self.assertFalse(extraction.executable)
        self.assertIn("extraction", extraction.motif_non_executable or "")

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

        self.assertEqual([propose.synthetique for propose in proposes], [True, True])
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

    def test_modele_d_extraction_refuse_en_transcription(self) -> None:
        registre = RegistreMoteurs()
        registre.enregistrer(DECLARATION_FACTICE)
        service = self.construire(registre=registre)
        reference = f"factice/{CLE_MODELE_FACTICE_EXTRACTION}"

        with self.assertRaises(ValeurRefusee) as contexte:
            service.valider(
                modele=reference,
                audios=["a.wav"],
                threads="4",
                reglages={},
            )
        self.assertIn("extraction", str(contexte.exception))
        self.assertIn("transcription", str(contexte.exception))
        # La préparation n'applique jamais ce modèle : repli sur le modèle de transcription.
        preparation = service.preparer(modele=reference)
        self.assertEqual(preparation.reference, f"factice/{CLE_MODELE_FACTICE}")
        self.assertIsNotNone(preparation.notice)

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
            reglages_depuis_champs(champs),
            {"beam_size": "7", "vad_filter": "oui"},
        )

    def test_prefixe_seul_devient_un_nom_vide_donc_inconnu(self) -> None:
        self.assertEqual(reglages_depuis_champs({PREFIXE_CHAMP_REGLAGE: "x"}), {"": "x"})

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

    def test_champs_repetes_autorises_pour_les_audios(self) -> None:
        refuser_champs_repetes(
            [
                ("audios", "a.wav"),
                ("audios", "b.wav"),
                ("modele", f"{MOTEUR}/{CLE}"),
                ("threads", "4"),
            ]
        )



class PreparationServiceTest(SocleExecutionsTest):
    """Résolution d'une préparation sans page : valeurs par défaut et notices."""

    def test_preparer_par_defaut_applique_le_premier_audio_lisible(self) -> None:
        preparation = self.service.preparer()

        self.assertEqual(preparation.audios, ("a.wav",))
        self.assertIsNone(preparation.notice)

    def test_preparer_defauts_et_audios_dans_l_ordre(self) -> None:
        preparation = self.service.preparer(audios=["b.wav", "a.wav"])

        self.assertEqual(preparation.modele.reference, self.reference())
        self.assertEqual(preparation.moteur, MOTEUR)
        self.assertEqual(preparation.audios, ("b.wav", "a.wav"))
        self.assertIsNone(preparation.notice)

    def test_preparer_audio_par_defaut_et_doublon_signale(self) -> None:
        preparation = self.service.preparer(audios=["a.wav", "a.wav"])

        self.assertEqual(preparation.audios, ("a.wav",))
        self.assertEqual(preparation.notice, MESSAGE_AUDIO_INCOHERENT)

    def test_preparer_reference_inconnue_reinitialisee(self) -> None:
        preparation = self.service.preparer(
            modele=f"{MOTEUR}/{'f' * 64}", audios=["a.wav"]
        )

        self.assertEqual(preparation.modele.reference, self.reference())
        self.assertEqual(preparation.notice, MESSAGE_MODELE_REINITIALISE)

    def test_preparer_moteur_incoherent_signale(self) -> None:
        preparation = self.service.preparer(
            modele=self.reference(), moteur="autre-moteur", audios=["a.wav"]
        )

        self.assertEqual(preparation.moteur, MOTEUR)
        self.assertEqual(preparation.notice, MESSAGE_MOTEUR_INCOHERENT)

    def test_preparer_sans_audio_lisible_ni_modele_executable(self) -> None:
        service = ConfigurationExecutions(
            "/donnees", self.registre, lambda: (), lister=lambda dossier: AUDIOS
        )

        preparation = service.preparer(modele=f"{MOTEUR}/{CLE}", audios=["a.wav"])

        self.assertFalse(preparation.applicable)
        self.assertIsNone(preparation.modele)
        self.assertIsNone(preparation.reference)
        self.assertEqual(preparation.notice, MESSAGE_MODELE_REINITIALISE)

    def test_preparer_sans_audio_lisible(self) -> None:
        service = ConfigurationExecutions(
            "/donnees",
            self.registre,
            lambda: self.modeles,
            lister=lambda dossier: (AUDIOS[2],),
        )

        preparation = service.preparer(audios=["illisible.wav"])

        self.assertFalse(preparation.applicable)
        self.assertEqual(preparation.audios, ())
        self.assertEqual(preparation.notice, MESSAGE_AUDIO_INCOHERENT)

    def test_valider_refuse_un_moteur_incoherent(self) -> None:
        with self.assertRaises(ValeurRefusee):
            self.service.valider(
                modele=self.reference(),
                moteur="autre-moteur",
                audios=["a.wav"],
                threads="4",
                reglages={},
            )

    def test_valider_accepte_le_moteur_de_la_reference_et_son_absence(self) -> None:
        for moteur in (None, MOTEUR):
            with self.subTest(moteur=moteur):
                demande = self.service.valider(
                    modele=self.reference(),
                    moteur=moteur,
                    audios=["a.wav"],
                    threads="4",
                    reglages={},
                )

                self.assertEqual(demande.moteur, MOTEUR)


class PageExecutionsRetireeTest(SocleWebTest):
    """Exécutions : l'historique reste, la préparation et le lancement ne sont plus routés."""

    def setUp(self) -> None:
        super().setUp()
        self.app = self.construire_app()
        self.client = self.app.test_client()

    def test_historique_sans_formulaire(self) -> None:
        reponse = self.client.get("/executions", base_url=self.base_url())
        corps = reponse.get_data(as_text=True)

        self.assertEqual(reponse.status_code, 200)
        self.assertNotIn("<form", corps)
        self.assertNotIn('name="modele"', corps)
        self.assertNotIn("Lancer l'exécution", corps)
        self.verifier_html_seul(corps)

    def test_preparation_et_lancement_repondent_404(self) -> None:
        for chemin in (
            "/executions/verifier",
            "/executions/lancer",
            "/executions/arreter",
        ):
            with self.subTest(chemin=chemin):
                reponse = self.client.post(
                    chemin, data={}, base_url=self.base_url()
                )

                self.verifier_page_erreur(reponse, 404)
        etat = self.client.get("/executions/etat", base_url=self.base_url())
        self.verifier_page_erreur(etat, 404)
