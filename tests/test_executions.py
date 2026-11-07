"""Tests du formulaire d'exécution et de la demande validée (tâche 6.2).

Le service est exercé avec une déclaration synthétique qui expose des réglages
des quatre types, un inventaire de modèles factice et une liste d'audios
factice : aucun moteur, aucun poids, aucun audio réel et aucun réseau. Les tests
de page réutilisent le socle de `tests/test_web.py` et vérifient qu'aucune
exécution n'est lancée et qu'aucun dossier de données n'est créé.
"""

from __future__ import annotations

import html
import re
import unittest
from dataclasses import replace
from pathlib import Path
from urllib.parse import urlencode

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
    MESSAGE_AUDIO_INCOHERENT,
    MESSAGE_MODELE_REINITIALISE,
    MESSAGE_MOTEUR_INCOHERENT,
    MESSAGE_MOTEUR_ADAPTE,
    MESSAGE_REGLAGES_AUTRE_FAMILLE,
    MESSAGE_REGLAGES_INVALIDES,
    MESSAGE_REGLAGES_REINITIALISES,
    MESSAGE_THREADS_REINITIALISES,
    MESSAGE_TEXTE_NON_CONSERVE,
    MESSAGE_REGLAGES_SANS_SOURCE,
    MESSAGE_REGLAGE_INCONNU,
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
from transcription_bench.web import NOM_CHAMP_JETON
from transcription_bench.web.app import MESSAGE_PREPARATION_REFUSEE

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

# Deux familles déclarent un réglage du même nom avec des valeurs disjointes :
# aucune valeur de l'une ne doit être reportée sur l'autre.
REGLAGES_A = (
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
REGLAGES_B = (
    Reglage(
        "compute_type",
        "Type de calcul",
        TYPE_CHOIX,
        "int8_float16",
        "Précision de calcul demandée au moteur.",
        valeurs=("int8_float16", "bfloat16"),
    ),
)
CLE_VARIANTE = "d" * 64


def declaration_homonyme(
    identifiant: str,
    famille: str,
    libelle: str,
    reglages: tuple[Reglage, ...],
    *,
    nom: str = "Moteur de test",
) -> DeclarationAdaptateur:
    """Déclaration synthétique d'une famille aux réglages nommés librement."""
    return DeclarationAdaptateur(
        identifiant=identifiant,
        nom=nom,
        fichier_requirements=None,
        regle_compatibilite="transformers-safetensors",
        familles=(
            Famille(famille, libelle, qualifiee=True, reglages=reglages),
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

    def test_page_sans_modele_proposable_n_affiche_aucun_lancement(self) -> None:
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
        self.assertIn("Aucun modèle proposable", corps)
        self.assertNotIn("Lancer l'exécution", corps)
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

    def test_page_et_validation_modele_natif_sans_formatage_none(self) -> None:
        registre = RegistreMoteurs()
        registre.enregistrer(declaration_avec_reglages(
            duree_native=DureeNative(300.0, "mécanisme natif de test")))
        service = ConfigurationExecutions(
            self.dossier_data, registre, lambda: self.modeles,
            lister=lambda dossier: AUDIOS,
        )
        app = self.construire_app(self.services(executions=service))
        reponse = app.test_client().get("/executions", base_url=self.base_url())
        self.assertEqual(reponse.status_code, 200)
        corps = reponse.get_data(as_text=True)
        self.assertIn("Mécanisme natif d'audio long", corps)
        self.assertIn("repli en fenêtres fixes de 30 s", corps)
        self.assertNotIn("Seul le moteur factice est exécutable", corps)
        self.verifier_html_seul(corps)
        validation = self.post_autorise(
            "/executions/verifier", app=app,
            donnees={"modele": service.modeles_proposables()[0].reference,
                     "audios": ["a.wav"], "threads": "2"},
        )
        self.assertEqual(validation.status_code, 200)
        self.assertIn("Demande validée", validation.get_data(as_text=True))
        self.assertEqual(self.creneau.instantane().etat, "libre")

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

        corps = self.verifier_refus_preparation(reponse)
        self.assertNotIn('action="/executions/lancer"', corps)
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
                corps = self.verifier_refus_preparation(reponse)
                # Le premier choix du champ répété n'est pas arbitré : la page
                # reprend les valeurs de la préparation, sans lancer.
                self.assertIn("Lancer l'exécution", corps)
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
        self.assertIn('value="non" data-valeur-reglage checked', corps)
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

        corps = self.verifier_refus_preparation(reponse)
        self.assertIn(MESSAGE_REGLAGE_INCONNU, corps)
        self.assertEqual(self.creneau.instantane().etat, "libre")

    def test_post_refuse_audio_hors_liste_et_modele_non_pret(self) -> None:
        cas = (
            ("z.wav", self.reference(), MESSAGE_AUDIO_INCOHERENT),
            ("illisible.wav", self.reference(), MESSAGE_AUDIO_INCOHERENT),
            ("a.wav", f"{MOTEUR}/{AUTRE_CLE}", MESSAGE_MODELE_REINITIALISE),
        )
        for audio, modele, attendu in cas:
            with self.subTest(audio=audio, modele=modele):
                reponse = self.post_autorise(
                    "/executions/verifier",
                    donnees={"modele": modele, "audios": [audio], "threads": "4"},
                )
                corps = self.verifier_refus_preparation(reponse)
                self.assertIn(attendu, corps)

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


AUTRE_MOTEUR = "autre-moteur"
INSTANCE_AUTRE_MOTEUR = "Moteur alternatif de test"


class PreparationUniqueTest(SocleWebTest):
    """Panneau de préparation unique Modèle/Audio/Moteur (tâche 4.1, D4).

    Deux moteurs proposent un modèle de même identifiant : les libellés courts
    restent distincts, le moteur n'est jamais un second choix indépendant et
    toute sélection GET est revalidée côté serveur sans jeton dans l'URL.
    """

    def setUp(self) -> None:
        super().setUp()
        self.registre = RegistreMoteurs()
        self.registre.enregistrer(declaration_avec_reglages())
        self.registre.enregistrer(
            replace(
                declaration_avec_reglages(
                    identifiant=AUTRE_MOTEUR, famille="autre"
                ),
                nom=INSTANCE_AUTRE_MOTEUR,
            )
        )
        self.modeles = (
            modele_prete(),
            modele_prete(moteur=AUTRE_MOTEUR, cle=AUTRE_CLE, famille="autre"),
        )
        self.service = self.creer_service()
        self.app = self.construire_app(self.services(executions=self.service))
        self.client = self.app.test_client()

    def creer_service(self, **options) -> ConfigurationExecutions:
        parametres = {
            "lister": lambda dossier: AUDIOS,
            "compter_threads": lambda: THREADS_DEFAUT,
        }
        parametres.update(options)
        return ConfigurationExecutions(
            self.dossier_data,
            self.registre,
            lambda: self.modeles,
            **parametres,
        )

    def get(self, chemin: str = "/executions"):
        return self.client.get(chemin, base_url=self.base_url())

    def reference(self, position: int = 0) -> str:
        return self.service.modeles_proposables()[position].reference

    def scenario(self, parametres: dict[str, object]) -> str:
        return "/executions?" + urlencode(parametres, doseq=True)

    def test_un_seul_panneau_avec_une_seule_serie_de_selecteurs(self) -> None:
        reponse = self.get()

        self.assertEqual(reponse.status_code, 200)
        corps = reponse.get_data(as_text=True)
        self.verifier_html_seul(corps)
        self.assertEqual(
            corps.count('<select id="champ-modele" name="modele" data-choix-modele>'), 1
        )
        self.assertEqual(
            corps.count('<select id="champ-moteur" name="moteur" data-choix-moteur>'), 1
        )
        # Tâche 4.3 : un audio unitaire par défaut et un lot facultatif, jamais
        # envoyés dans le même champ.
        self.assertEqual(
            corps.count('<select id="champ-audio" name="audios" data-choix-audio>'), 1
        )
        self.assertNotIn('type="checkbox" name="audios"', corps)
        self.assertNotIn("formulaire est répété", corps)
        # Un seul formulaire de lancement, pas un par modèle proposé.
        self.assertEqual(corps.count('action="/executions/lancer"'), 1)
        # Les audios lisibles sont proposés une fois chacun, pas un par modèle.
        for audio in AUDIOS[:2]:
            self.assertEqual(
                corps.count(f'<option value="{audio.nom}"'),
                1,
                audio.nom,
            )
            self.assertEqual(
                corps.count(
                    f'<input type="checkbox" name="audios_lot" value="{audio.nom}"'
                ),
                1,
                audio.nom,
            )

    def test_defauts_appliques_sans_clic_supplementaire(self) -> None:
        corps = self.get().get_data(as_text=True)
        corps_html = html.unescape(corps)

        self.assertIn("Préparation appliquée", corps)
        self.assertIn(f'name="modele" value="{self.reference()}"', corps)
        self.assertIn('name="moteur" value="moteur-de-test"', corps)
        self.assertIn('name="audios" value="a.wav"', corps)
        self.assertIn('<option value="a.wav" selected>', corps)
        self.assertIn(
            f'<option value="moteur-de-test" data-reference="{self.reference()}" selected>',
            corps,
        )
        self.assertIn("Lancer l'exécution", corps_html)
        # Ni identifiant canonique ni commit avant les contrôles (D4).
        self.assertNotIn(COMMIT, corps)

    def test_libelles_courts_et_moteurs_distincts(self) -> None:
        corps = html.unescape(self.get().get_data(as_text=True))
        options = re.findall(r"<option value=\"[^\"]*\"[^>]*>([^<]*)</option>", corps)

        self.assertIn("org/modele — Moteur de test", options)
        self.assertIn(f"org/modele — {INSTANCE_AUTRE_MOTEUR}", options)

    def test_preparation_get_sans_jeton_ni_action(self) -> None:
        corps = self.get().get_data(as_text=True)
        formulaire = corps.split('data-preparation-choix>', 1)[1].split("</form>", 1)[0]
        noms = set(re.findall(r'name="([^"]+)"', formulaire))

        self.assertIn('method="get"', corps)
        self.assertNotIn(NOM_CHAMP_JETON, formulaire)
        # Liste blanche stricte des paramètres GET : références locales, noms
        # d'audios (unitaire et lot facultatif) et copies non sensibles des
        # réglages déjà affichés.
        for nom in noms:
            self.assertTrue(
                nom
                in ("modele", "moteur", "audios", "audios_lot", "source", "threads")
                or nom.startswith(PREFIXE_CHAMP_REGLAGE),
                f"paramètre GET hors liste blanche : {nom}",
            )
        # Sans script, ces copies restent désactivées : aucune valeur saisie ne
        # voyage, et le remplacement par les défauts est annoncé.
        copies = re.findall(
            r'<input type="hidden" name="[^"]+" value="[^"]*"'
            r' data-copie-reglage( disabled)?>',
            formulaire,
        )
        self.assertTrue(copies)
        self.assertTrue(all(disabled for disabled in copies), formulaire)
        self.assertEqual(self.creneau.instantane().etat, "libre")
        self.assertFalse(self.dossier_data.exists())

    def test_jeton_fourni_en_get_ignore_et_non_recopie(self) -> None:
        reponse = self.get(
            self.scenario(
                {
                    NOM_CHAMP_JETON: "jeton-en-url",
                    "modele": self.reference(),
                    "audios": ["a.wav"],
                }
            )
        )

        self.assertEqual(reponse.status_code, 200)
        self.assertNotIn("jeton-en-url", reponse.get_data(as_text=True))

    def test_choix_appliques_par_get_conserves(self) -> None:
        seconde = self.reference(1)
        corps = self.get(
            self.scenario(
                {
                    "modele": seconde,
                    "moteur": AUTRE_MOTEUR,
                    "audios": ["b.wav"],
                    "source": seconde,
                }
            )
        ).get_data(as_text=True)

        self.assertIn(f'name="modele" value="{seconde}"', corps)
        self.assertIn(f'name="moteur" value="{AUTRE_MOTEUR}"', corps)
        self.assertIn('name="audios" value="b.wav"', corps)
        # La préparation d'origine accompagne la sélection, mais aucune valeur de
        # réglage (repli HTML) : le remplacement par les défauts est annoncé.
        self.assertIn(f'name="source" value="{seconde}"', corps)
        self.assertIn(MESSAGE_REGLAGES_REINITIALISES, html.unescape(corps))

    def test_reference_perimee_refusee_sans_500(self) -> None:
        perimee = f"MOTEUR_INCONNU/{'f' * 64}"
        reponse = self.get(self.scenario({"modele": perimee, "audios": ["a.wav"]}))
        corps = reponse.get_data(as_text=True)

        self.assertEqual(reponse.status_code, 400)
        self.verifier_html_seul(corps)
        # La page Exécutions reste rendue : l'opération et l'historique restent
        # accessibles, seuls les choix sont réinitialisés.
        self.assertIn("<h1>Exécutions</h1>", corps)
        self.assertIn(MESSAGE_MODELE_REINITIALISE, corps)
        self.assertIn(f'name="modele" value="{self.reference()}"', corps)
        self.assertNotIn("Erreur 400", corps)
        self.assertEqual(self.creneau.instantane().etat, "libre")

    def test_reference_non_executable_refusee_et_defaut_repris(self) -> None:
        registre = RegistreMoteurs()
        registre.enregistrer(declaration_avec_reglages(qualifiee=False))
        service = ConfigurationExecutions(
            self.dossier_data,
            registre,
            lambda: (modele_prete(),),
            lister=lambda dossier: AUDIOS,
        )
        reference = service.modeles_proposables()[0].reference
        app = self.construire_app(self.services(executions=service))

        reponse = app.test_client().get(
            f"/executions?modele={reference}",
            base_url=self.base_url(),
        )
        corps = reponse.get_data(as_text=True)

        self.assertEqual(reponse.status_code, 400)
        self.assertIn("Aucun modèle exécutable", corps)
        self.assertIn("Non exécutable", corps)
        self.assertNotIn('name="modele"', corps)

    def test_audio_invalide_refuse_et_modele_conserve(self) -> None:
        reponse = self.get(
            self.scenario(
                {
                    "modele": self.reference(),
                    "moteur": "moteur-de-test",
                    "audios": ["z.wav", "illisible.wav"],
                }
            )
        )
        corps = reponse.get_data(as_text=True)

        self.assertEqual(reponse.status_code, 400)
        self.assertIn(MESSAGE_AUDIO_INCOHERENT, corps)
        self.assertIn(f'name="modele" value="{self.reference()}"', corps)
        self.assertIn('name="audios" value="a.wav"', corps)
        self.assertNotIn('name="audios" value="z.wav"', corps)

    def test_audio_absent_annonce_le_defaut(self) -> None:
        reponse = self.get(
            self.scenario({"modele": self.reference(), "moteur": "moteur-de-test"})
        )

        self.assertEqual(reponse.status_code, 400)
        self.assertIn(
            "Aucun audio sélectionné", reponse.get_data(as_text=True)
        )

    def test_moteur_incoherent_refuse_et_moteur_de_la_reference_retenu(self) -> None:
        reponse = self.get(
            self.scenario(
                {
                    "modele": self.reference(),
                    "moteur": AUTRE_MOTEUR,
                    "audios": ["a.wav"],
                }
            )
        )
        corps = reponse.get_data(as_text=True)

        self.assertEqual(reponse.status_code, 400)
        self.assertIn(MESSAGE_MOTEUR_INCOHERENT, corps)
        self.assertIn('name="moteur" value="moteur-de-test"', corps)
        self.assertNotIn(f'name="moteur" value="{AUTRE_MOTEUR}"', corps)

    def test_champ_get_repete_refuse_sans_500(self) -> None:
        chemin = "/executions?" + urlencode(
            [("modele", self.reference()), ("modele", self.reference(1))]
        )
        reponse = self.get(chemin)
        corps = reponse.get_data(as_text=True)

        self.assertEqual(reponse.status_code, 400)
        self.verifier_html_seul(corps)
        self.assertIn(MESSAGE_PREPARATION_REFUSEE, corps)
        self.assertIn("<h1>Exécutions</h1>", corps)

    def test_valeur_get_hostile_echappee_sans_script(self) -> None:
        reponse = self.get(
            self.scenario(
                {
                    "modele": "<script>alert(1)</script>",
                    "moteur": "<img src=x onerror=alert(1)>",
                    "audios": ["<script>alert(2)</script>"],
                }
            )
        )
        corps = reponse.get_data(as_text=True)

        self.assertEqual(reponse.status_code, 400)
        self.verifier_html_seul(corps)
        self.assertNotIn("<script>alert", corps)
        self.assertNotIn("<img", corps)
        self.assertIn(MESSAGE_MODELE_REINITIALISE, corps)

    def test_inventaire_vide_et_non_executable_sans_lancement(self) -> None:
        for modeles, attendu in (
            ((), "Aucun modèle proposable"),
            ((modele_prete(),), "Aucun modèle exécutable"),
        ):
            with self.subTest(attendu=attendu):
                registre = self.registre
                if not modeles:
                    registre = RegistreMoteurs()
                else:
                    registre = RegistreMoteurs()
                    registre.enregistrer(
                        declaration_avec_reglages(qualifiee=False)
                    )
                service = ConfigurationExecutions(
                    self.dossier_data,
                    registre,
                    lambda modeles=modeles: modeles,
                    lister=lambda dossier: AUDIOS,
                )
                app = self.construire_app(self.services(executions=service))
                corps = (
                    app.test_client()
                    .get("/executions", base_url=self.base_url())
                    .get_data(as_text=True)
                )

                self.assertIn(attendu, corps)
                self.assertNotIn('name="modele"', corps)
                self.assertNotIn("Lancer l'exécution", corps)
                self.verifier_html_seul(corps)

    def test_post_moteur_incoherent_refuse_sans_lancer(self) -> None:
        reponse = self.post_autorise(
            "/executions/verifier",
            donnees={
                "modele": self.reference(),
                "moteur": AUTRE_MOTEUR,
                "audios": ["a.wav"],
                "threads": "4",
            },
        )

        corps = self.verifier_refus_preparation(reponse)
        self.assertIn(MESSAGE_MOTEUR_INCOHERENT, corps)
        self.assertEqual(self.creneau.instantane().etat, "libre")

    def test_post_moteur_repete_refuse(self) -> None:
        reponse = self.post_autorise(
            "/executions/verifier",
            donnees={
                "modele": self.reference(),
                "moteur": ["moteur-de-test", AUTRE_MOTEUR],
                "audios": ["a.wav"],
                "threads": "4",
            },
        )

        self.verifier_refus_preparation(reponse)
        self.assertEqual(self.creneau.instantane().etat, "libre")

    def test_post_coherent_verifie_sans_lancer_ni_creer_de_dossier(self) -> None:
        reponse = self.post_autorise(
            "/executions/verifier",
            donnees={
                "modele": self.reference(1),
                "moteur": AUTRE_MOTEUR,
                "audios": ["b.wav", "a.wav"],
                "threads": "3",
            },
        )

        self.assertEqual(reponse.status_code, 200)
        corps = reponse.get_data(as_text=True)
        self.verifier_html_seul(corps)
        self.assertIn("Demande validée", corps)
        self.assertIn(f'name="moteur" value="{AUTRE_MOTEUR}"', corps)
        self.assertIn("<li>b.wav</li>", corps)
        self.assertEqual(self.creneau.instantane().etat, "libre")
        self.assertFalse(self.dossier_data.exists())


class PreparationLotTest(SocleWebTest):
    """Audio unitaire par défaut et lot facultatif ordonné (tâche 4.3, D4).

    Le cas courant est un contrôle simple qui sélectionne un seul audio ; le
    lot reste replié au second plan, sous un autre nom de champ, et son ordre
    de traitement est celui de la liste rendue, rappelé dans la préparation
    appliquée. Aucun essai n'est lancé : ces lectures ne sollicitent pas le
    créneau et ne transmettent aucun jeton dans l'URL.
    """

    def setUp(self) -> None:
        super().setUp()
        registre = RegistreMoteurs()
        registre.enregistrer(declaration_avec_reglages())
        self.service = ConfigurationExecutions(
            self.dossier_data,
            registre,
            lambda: (modele_prete(),),
            lister=lambda dossier: AUDIOS,
            compter_threads=lambda: THREADS_DEFAUT,
        )
        self.app = self.construire_app(self.services(executions=self.service))
        self.client = self.app.test_client()

    def reference(self) -> str:
        return self.service.modeles_proposables()[0].reference

    def get(self, parametres: dict[str, object] | None = None):
        chemin = "/executions"
        if parametres:
            chemin += "?" + urlencode(parametres, doseq=True)
        return self.client.get(chemin, base_url=self.base_url())

    def formulaire_lancement(self, corps: str) -> str:
        return corps.split("data-preparation-lancement>", 1)[1].split("</form>", 1)[0]

    def test_audio_unitaire_par_defaut_et_lot_replie(self) -> None:
        reponse = self.get()
        corps = reponse.get_data(as_text=True)

        self.assertEqual(reponse.status_code, 200)
        self.verifier_html_seul(corps)
        # Contrôle simple : un seul audio sélectionné par défaut, une option
        # choisie, et aucune case de lot active sans geste explicite.
        self.assertIn(
            '<select id="champ-audio" name="audios" data-choix-audio>', corps
        )
        self.assertIn('<option value="a.wav" selected>', corps)
        self.assertNotIn(
            'name="audios_lot" value="a.wav" data-choix-audio checked', corps
        )
        self.assertIn(
            '<details>\n<summary>Plusieurs audios, dans cet ordre (facultatif)</summary>',
            corps,
        )
        self.assertNotIn('<details open>\n<summary>Plusieurs audios', corps)
        # L'audio retenu n'est envoyé qu'une fois : le lot porte un autre nom.
        self.assertEqual(corps.count('name="audios" value="a.wav"'), 1)
        lancement = self.formulaire_lancement(corps)
        self.assertNotIn('name="audios_lot"', lancement)
        self.assertEqual(lancement.count('name="audios"'), 1)
        self.assertEqual(self.creneau.instantane().etat, "libre")

    def test_premiere_case_du_lot_reste_cochee_pour_en_ajouter_une_autre(self) -> None:
        # Le JS applique un GET après chaque case : la première sélection ne
        # doit ni refermer le lot ni disparaître avant la deuxième.
        reponse = self.get({"modele": self.reference(), "audios_lot": ["b.wav"]})
        corps = reponse.get_data(as_text=True)
        self.assertEqual(reponse.status_code, 200)
        self.assertIn('<details open>\n<summary>Plusieurs audios', corps)
        self.assertIn('name="audios_lot" value="b.wav" data-choix-audio checked', corps)
        lancement = self.formulaire_lancement(corps)
        self.assertEqual(lancement.count('name="audios"'), 1)
        self.assertIn('name="audios" value="b.wav"', lancement)

    def test_lot_ordonne_avant_lancement(self) -> None:
        reponse = self.get(
            {"modele": self.reference(), "audios_lot": ["b.wav", "a.wav"]}
        )
        corps = reponse.get_data(as_text=True)

        self.assertEqual(reponse.status_code, 200)
        self.verifier_html_seul(corps)
        self.assertIn("dans cet ordre de traitement", corps)
        applique = corps.split('id="preparation-appliquee"', 1)[1].split("</p>", 1)[0]
        self.assertLess(applique.index("b.wav"), applique.index("a.wav"))
        liste = corps.split("<summary>Plusieurs audios", 1)[1].split("</ol>", 1)[0]
        self.assertLess(liste.index('value="b.wav"'), liste.index('value="a.wav"'))
        # Le lot est déplié et ses cases cochées : l'ordre est lisible avant
        # tout lancement, sans promettre un ordre de clic différent du DOM.
        self.assertIn(
            '<details open>\n<summary>Plusieurs audios, dans cet ordre (facultatif)</summary>',
            corps,
        )
        self.assertIn('name="audios_lot" value="a.wav" data-choix-audio checked', corps)
        self.assertIn('name="audios_lot" value="b.wav" data-choix-audio checked', corps)
        lancement = self.formulaire_lancement(corps)
        self.assertLess(
            lancement.index('name="audios" value="b.wav"'),
            lancement.index('name="audios" value="a.wav"'),
        )
        self.assertEqual(lancement.count('name="audios"'), 2)
        self.assertIn('name="threads" value="4"', lancement)
        self.assertEqual(self.creneau.instantane().etat, "libre")

    def test_lot_prime_et_annonce_l_audio_unique_ecarte(self) -> None:
        reponse = self.get(
            {
                "modele": self.reference(),
                "audios": "a.wav",
                "audios_lot": ["b.wav"],
            }
        )
        corps = reponse.get_data(as_text=True)

        self.assertEqual(reponse.status_code, 200)
        self.verifier_html_seul(corps)
        self.assertIn("Mode lot appliqué", corps)
        self.assertIn("« a.wav »", corps)
        lancement = self.formulaire_lancement(corps)
        self.assertEqual(lancement.count('name="audios" value="b.wav"'), 1)
        self.assertNotIn('name="audios" value="a.wav"', lancement)
        self.assertEqual(self.creneau.instantane().etat, "libre")

    def test_audio_unitaire_forge_n_est_pas_reafiche(self) -> None:
        reponse = self.get(
            {
                "modele": self.reference(),
                "audios": "<script>alert(1)</script>",
                "audios_lot": ["b.wav"],
            }
        )
        corps = reponse.get_data(as_text=True)

        self.assertEqual(reponse.status_code, 200)
        self.verifier_html_seul(corps)
        self.assertNotIn("<script>alert(1)</script>", corps)
        # Ce nom n'est pas un audio de l'inventaire : il n'est pas nommé dans
        # l'annonce, même échappé.
        self.assertNotIn("Mode lot appliqué", corps)
        self.assertIn('name="audios" value="b.wav"', corps)
        self.assertEqual(self.creneau.instantane().etat, "libre")

    def test_lot_avec_audio_inconnu_refuse_et_conserve_les_choix_valides(self) -> None:
        reponse = self.get(
            {"modele": self.reference(), "audios_lot": ["z.wav", "b.wav"]}
        )
        corps = reponse.get_data(as_text=True)

        self.assertEqual(reponse.status_code, 400)
        self.verifier_html_seul(corps)
        self.assertIn(MESSAGE_AUDIO_INCOHERENT, corps)
        self.assertIn("<h1>Exécutions</h1>", corps)
        self.assertIn(f'name="modele" value="{self.reference()}"', corps)
        self.assertIn('name="audios" value="b.wav"', corps)
        self.assertNotIn('name="audios" value="z.wav"', corps)
        self.assertEqual(self.creneau.instantane().etat, "libre")

    def test_lot_en_double_signale_sans_500(self) -> None:
        reponse = self.get(
            {"modele": self.reference(), "audios_lot": ["b.wav", "b.wav"]}
        )
        corps = reponse.get_data(as_text=True)

        self.assertEqual(reponse.status_code, 400)
        self.verifier_html_seul(corps)
        self.assertIn(MESSAGE_AUDIO_INCOHERENT, corps)
        self.assertEqual(corps.count('name="audios" value="b.wav"'), 1)
        self.assertEqual(self.creneau.instantane().etat, "libre")

    def test_defauts_et_reglages_avances_fermes_et_actions_uniques(self) -> None:
        corps = self.get().get_data(as_text=True)

        self.verifier_html_seul(corps)
        # Les réglages avancés restent fermés, avec leurs défauts déjà utilisables
        # dans le formulaire de lancement.
        self.assertIn(
            '<details>\n<summary>Réglages avancés (facultatif)</summary>', corps
        )
        self.assertNotIn('<details open>\n<summary>Réglages avancés', corps)
        lancement = self.formulaire_lancement(corps)
        self.assertIn('name="threads" value="4"', lancement)
        self.assertIn('<option value="float32" selected>', lancement)
        # Actions uniques : Lancer puis la vérification secondaire, une fois.
        self.assertEqual(corps.count('action="/executions/lancer"'), 1)
        self.assertEqual(corps.count("Lancer l'exécution"), 1)
        self.assertEqual(corps.count("Vérifier la demande (aucun lancement)"), 1)
        # Aucun lancement ni dossier de travail n'est créé par la lecture GET.
        self.assertEqual(self.creneau.instantane().etat, "libre")
        self.assertFalse(self.dossier_data.exists())

    def test_verification_reprend_les_defauts_sans_repetter_les_actions(self) -> None:
        validation = self.post_autorise(
            "/executions/verifier",
            donnees={
                "modele": self.reference(),
                "audios": ["b.wav", "a.wav"],
                "threads": str(THREADS_DEFAUT),
            },
        )
        corps = validation.get_data(as_text=True)

        self.assertEqual(validation.status_code, 200)
        self.verifier_html_seul(corps)
        self.assertIn("Demande validée", corps)
        self.assertLess(corps.index("<li>b.wav</li>"), corps.index("<li>a.wav</li>"))
        # Le résumé ne répète pas les actions du panneau : une seule série.
        self.assertEqual(corps.count('action="/executions/lancer"'), 1)
        self.assertEqual(corps.count("Lancer l'exécution"), 1)
        self.assertEqual(corps.count("Vérifier la demande (aucun lancement)"), 1)
        self.assertIn(
            '<details open>\n<summary>Plusieurs audios, dans cet ordre (facultatif)</summary>',
            corps,
        )
        self.assertEqual(self.creneau.instantane().etat, "libre")
        self.assertFalse(self.dossier_data.exists())


class PreparationCompatibiliteTest(SocleWebTest):
    """Sélections compatibles : variante, familles homonymes et doublons (4.2).

    Deux familles déclarent un réglage du **même nom** avec des valeurs
    disjointes : la page d'une famille ne doit jamais porter les contrôles ni
    les valeurs de l'autre, et un POST mêlant les deux est refusé. Une variante
    GGUF de la même référence est une ressource locale distincte, choisie par
    sa propre référence. Le contrat de données (`data-moteur`,
    `data-reference`) reste la seule information lue par le script local ; il
    ne contient ni jeton ni valeur sensible.
    """

    def setUp(self) -> None:
        super().setUp()
        self.registre = RegistreMoteurs()
        self.registre.enregistrer(
            declaration_homonyme(MOTEUR, "whisper", "Whisper", REGLAGES_A)
        )
        self.registre.enregistrer(
            declaration_homonyme(
                AUTRE_MOTEUR,
                "autre",
                "Autre famille",
                REGLAGES_B,
                nom=INSTANCE_AUTRE_MOTEUR,
            )
        )
        self.modeles = (
            modele_prete(),
            replace(
                modele_prete(),
                cle=CLE_VARIANTE,
                fichier_gguf="modele-Q8_0.gguf",
            ),
            modele_prete(
                moteur=AUTRE_MOTEUR,
                cle=AUTRE_CLE,
                famille="autre",
                identifiant="org/modele-autre",
            ),
        )
        self.service = ConfigurationExecutions(
            self.dossier_data,
            self.registre,
            lambda: self.modeles,
            lister=lambda dossier: AUDIOS,
            compter_threads=lambda: THREADS_DEFAUT,
        )
        self.app = self.construire_app(self.services(executions=self.service))
        self.client = self.app.test_client()

    def reference(self, position: int) -> str:
        return self.service.modeles_proposables()[position].reference

    def preparation(self, parametres: dict[str, object]):
        return self.client.get(
            "/executions?" + urlencode(parametres, doseq=True),
            base_url=self.base_url(),
        )

    def verifier(self, modele: str, moteur: str, **champs: object):
        donnees = {
            "modele": modele,
            "moteur": moteur,
            "audios": ["a.wav"],
            "threads": "4",
        }
        donnees.update(champs)
        return self.post_autorise("/executions/verifier", donnees=donnees)

    def test_changement_de_variante_applique_la_reference_choisie(self) -> None:
        variante = self.reference(1)
        reponse = self.preparation({"modele": variante, "audios": ["a.wav"]})
        corps = reponse.get_data(as_text=True)

        self.assertEqual(reponse.status_code, 200)
        self.verifier_html_seul(corps)
        self.assertIn(f'name="modele" value="{variante}"', corps)
        self.assertIn(f'value="{variante}" data-moteur="{MOTEUR}" selected', corps)
        self.assertIn("variante GGUF modele-Q8_0.gguf", corps)
        # La variante n'est pas confondue avec le modèle sans fichier GGUF.
        self.assertNotIn(f'name="modele" value="{self.reference(0)}"', corps)

        verification = self.verifier(variante, MOTEUR)
        self.assertEqual(verification.status_code, 200)
        self.assertIn("Demande validée", verification.get_data(as_text=True))
        self.assertEqual(self.creneau.instantane().etat, "libre")

    def test_famille_retenue_seule_rend_les_reglages_homonymes(self) -> None:
        corps = self.preparation(
            {"modele": self.reference(2), "audios": ["a.wav"]}
        ).get_data(as_text=True)

        self.assertIn("Réglages de la famille Autre famille", corps)
        self.assertIn('name="reglage_compute_type"', corps)
        self.assertIn('<option value="int8_float16" selected>', corps)
        # Ni les valeurs de l'autre famille ni son réglage propre ne suivent.
        self.assertNotIn('value="float32"', corps)
        self.assertNotIn('name="reglage_beam_size"', corps)
        self.assertIn('<option value="int8_float16" selected>', corps)

    def test_post_valeur_de_l_autre_famille_refusee(self) -> None:
        for modele, moteur, valeur in (
            (self.reference(2), AUTRE_MOTEUR, "float32"),
            (self.reference(0), MOTEUR, "int8_float16"),
        ):
            with self.subTest(valeur=valeur):
                reponse = self.verifier(
                    modele, moteur, **{f"{PREFIXE_CHAMP_REGLAGE}compute_type": valeur}
                )

                self.verifier_refus_preparation(reponse)
                self.assertEqual(self.creneau.instantane().etat, "libre")
                self.assertFalse(self.dossier_data.exists())

    def test_post_reglage_etranger_ou_repete_refuse_sans_lancer(self) -> None:
        etranger = self.verifier(
            self.reference(2),
            AUTRE_MOTEUR,
            **{f"{PREFIXE_CHAMP_REGLAGE}beam_size": "3"},
        )
        self.verifier_refus_preparation(etranger)

        repete = self.verifier(
            self.reference(0),
            MOTEUR,
            **{f"{PREFIXE_CHAMP_REGLAGE}compute_type": ["float32", "int8"]},
        )
        self.verifier_refus_preparation(repete)
        self.assertEqual(self.creneau.instantane().etat, "libre")

    def test_post_valeur_propre_a_la_famille_retenue_accepte(self) -> None:
        reponse = self.verifier(
            self.reference(2),
            AUTRE_MOTEUR,
            **{f"{PREFIXE_CHAMP_REGLAGE}compute_type": "bfloat16"},
        )
        corps = reponse.get_data(as_text=True)

        self.assertEqual(reponse.status_code, 200)
        self.verifier_html_seul(corps)
        self.assertIn("<li>compute_type : bfloat16</li>", corps)
        self.assertNotIn("compute_type : float32", corps)
        self.assertEqual(self.creneau.instantane().etat, "libre")

    def test_get_audio_repete_signale_et_choix_valides_conserves(self) -> None:
        reponse = self.preparation(
            {"modele": self.reference(1), "audios": ["b.wav", "b.wav"]}
        )
        corps = reponse.get_data(as_text=True)

        self.assertEqual(reponse.status_code, 400)
        self.assertIn(MESSAGE_AUDIO_INCOHERENT, corps)
        self.assertIn(f'name="modele" value="{self.reference(1)}"', corps)
        self.assertIn('<option value="b.wav" selected>', corps)

    def test_sans_js_changement_de_moteur_seul_selectionne_un_modele_compatible(self) -> None:
        # Repli HTML : seul le moteur a changé depuis la préparation affichée,
        # `source` désigne toujours le modèle rendu : la première référence
        # exécutable de ce moteur est sélectionnée et annoncée, sans refus.
        reponse = self.preparation(
            {
                "modele": self.reference(0),
                "moteur": AUTRE_MOTEUR,
                "audios": ["a.wav"],
                "source": self.reference(0),
            }
        )
        corps = reponse.get_data(as_text=True)

        self.assertEqual(reponse.status_code, 200)
        self.verifier_html_seul(corps)
        self.assertIn(f'name="modele" value="{self.reference(2)}"', corps)
        self.assertIn(
            f'<option value="{AUTRE_MOTEUR}" '
            f'data-reference="{self.reference(2)}" selected>',
            corps,
        )
        self.assertIn(MESSAGE_MOTEUR_ADAPTE, html.unescape(corps))
        self.assertEqual(self.creneau.instantane().etat, "libre")

    def test_get_moteur_incoherent_sans_origine_refuse(self) -> None:
        # Sans `source`, un moteur qui contredit la référence est une requête
        # forgée : refus 400, la référence fait foi.
        reponse = self.preparation(
            {"modele": self.reference(0), "moteur": AUTRE_MOTEUR, "audios": ["a.wav"]}
        )
        corps = reponse.get_data(as_text=True)

        self.assertEqual(reponse.status_code, 400)
        self.assertIn(MESSAGE_MOTEUR_INCOHERENT, html.unescape(corps))

    def test_contrat_de_donnees_pour_la_mise_a_jour_automatique(self) -> None:
        corps = self.client.get(
            "/executions", base_url=self.base_url()
        ).get_data(as_text=True)

        self.verifier_html_seul(corps)
        self.assertIn(
            '<select id="champ-modele" name="modele" data-choix-modele>', corps
        )
        self.assertIn(
            '<select id="champ-moteur" name="moteur" data-choix-moteur>', corps
        )
        self.assertIn(f'data-moteur="{MOTEUR}"', corps)
        self.assertIn(f'data-moteur="{AUTRE_MOTEUR}"', corps)
        for attendue in (self.reference(0), self.reference(2)):
            with self.subTest(reference=attendue):
                self.assertIn(
                    f'data-reference="{attendue}"',
                    corps,
                    "chaque moteur propose une référence réellement compatible",
                )
        # Le contrat du moteur reste sa première référence, pas une variante.
        self.assertNotIn(f'data-reference="{self.reference(1)}"', corps)
        self.assertIn("data-choix-audio", corps)
        self.assertIn("data-action-appliquer", corps)
        # Formulaire GET : ni jeton, ni champ hors de la liste blanche.
        formulaire = corps.split("data-preparation-choix>", 1)[1].split("</form>", 1)[0]
        self.assertNotIn(NOM_CHAMP_JETON, formulaire)
        noms = set(re.findall(r'name="([^"]+)"', formulaire))
        for nom in noms:
            self.assertTrue(
                nom
                in ("modele", "moteur", "audios", "audios_lot", "source", "threads")
                or nom.startswith(PREFIXE_CHAMP_REGLAGE),
                f"paramètre GET hors liste blanche : {nom}",
            )
        # Les copies restent désactivées sans script, pour le repli HTML.
        for nom in noms - {"modele", "moteur", "audios", "audios_lot"}:
            with self.subTest(nom=nom):
                self.assertIn(
                    f'<input type="hidden" name="{nom}" value="', formulaire
                )
        self.assertEqual(
            formulaire.count("data-copie-reglage disabled"),
            1 + sum(
                1 for reglage in REGLAGES_A if reglage.type_valeur != TYPE_TEXTE
            ),
        )
        # Aucun texte libre n'a de copie GET : il ne partirait jamais en URL.
        # La référence d'origine accompagne la sélection, jamais le jeton.
        self.assertIn(f'name="source" value="{self.reference(0)}"', corps)

    def formulaire_lancement(self, corps: str) -> str:
        return corps.split("data-preparation-lancement>", 1)[1].split("</form>", 1)[0]

    def test_get_conserve_audio_et_reglages_non_defaut(self) -> None:
        origine = self.reference(0)
        reponse = self.preparation(
            {
                "modele": origine,
                "moteur": MOTEUR,
                "audios": ["b.wav"],
                "source": origine,
                "threads": "6",
                f"{PREFIXE_CHAMP_REGLAGE}compute_type": "int8",
                f"{PREFIXE_CHAMP_REGLAGE}beam_size": "8",
                f"{PREFIXE_CHAMP_REGLAGE}vad_filter": "oui",
            }
        )
        corps = reponse.get_data(as_text=True)
        lancement = self.formulaire_lancement(corps)

        self.assertEqual(reponse.status_code, 200)
        self.verifier_html_seul(corps)
        self.assertNotIn(MESSAGE_REGLAGES_AUTRE_FAMILLE, corps)
        self.assertNotIn(MESSAGE_REGLAGES_INVALIDES, corps)
        self.assertNotIn(MESSAGE_REGLAGES_REINITIALISES, corps)
        # Audio conservé et réglages non par défaut repris tels quels.
        self.assertIn('<option value="b.wav" selected>', corps)
        self.assertIn('name="threads" value="6"', lancement)
        self.assertIn('<option value="int8" selected>', lancement)
        self.assertIn('name="reglage_beam_size" value="8"', lancement)
        self.assertIn('value="oui" data-valeur-reglage checked', lancement)
        # Les copies GET portent les mêmes valeurs, prêtes pour le script.
        self.assertIn(
            '<input type="hidden" name="reglage_compute_type" value="int8"', corps
        )

    def test_get_variante_conserve_les_valeurs_valides(self) -> None:
        origine, variante = self.reference(0), self.reference(1)
        reponse = self.preparation(
            {
                "modele": variante,
                "moteur": MOTEUR,
                "audios": ["a.wav"],
                "source": origine,
                "threads": "2",
                f"{PREFIXE_CHAMP_REGLAGE}beam_size": "3",
            }
        )
        corps = reponse.get_data(as_text=True)

        self.assertEqual(reponse.status_code, 200)
        self.assertIn(f'name="modele" value="{variante}"', corps)
        self.assertNotIn(MESSAGE_REGLAGES_AUTRE_FAMILLE, corps)
        self.assertIn('name="reglage_beam_size" value="3"', corps)
        self.assertIn('name="threads" value="2"', corps)

    def test_get_autre_famille_reinitialise_et_annonce(self) -> None:
        reponse = self.preparation(
            {
                "modele": self.reference(2),
                "moteur": AUTRE_MOTEUR,
                "audios": ["a.wav"],
                "source": self.reference(0),
                "threads": "6",
                f"{PREFIXE_CHAMP_REGLAGE}compute_type": "float32",
            }
        )
        corps = reponse.get_data(as_text=True)
        lancement = self.formulaire_lancement(corps)

        self.assertEqual(reponse.status_code, 200)
        self.assertIn(MESSAGE_REGLAGES_AUTRE_FAMILLE, html.unescape(corps))
        # Aucune valeur homonyme de l'autre famille n'est reportée.
        self.assertNotIn('value="float32"', corps)
        self.assertIn('<option value="int8_float16" selected>', lancement)
        # Les threads, indépendants de la famille, restent conservés.
        self.assertIn('name="threads" value="6"', lancement)

    def test_get_valeur_invalide_reinitialisee_et_signalee(self) -> None:
        origine = self.reference(0)
        reponse = self.preparation(
            {
                "modele": origine,
                "audios": ["a.wav"],
                "source": origine,
                "threads": "trois",
                f"{PREFIXE_CHAMP_REGLAGE}compute_type": "int8",
                f"{PREFIXE_CHAMP_REGLAGE}beam_size": "abc",
            }
        )
        corps = reponse.get_data(as_text=True)
        lancement = self.formulaire_lancement(corps)

        self.assertEqual(reponse.status_code, 200)
        self.assertIn(MESSAGE_REGLAGES_INVALIDES, html.unescape(corps))
        # Les valeurs valides restent, les invalides reviennent aux défauts.
        self.assertIn('<option value="int8" selected>', lancement)
        self.assertIn('name="reglage_beam_size" value="5"', lancement)
        self.assertIn('name="threads" value="4"', lancement)

    def test_get_valeur_inconnue_refusee(self) -> None:
        origine = self.reference(0)
        reponse = self.preparation(
            {
                "modele": origine,
                "audios": ["a.wav"],
                "source": origine,
                f"{PREFIXE_CHAMP_REGLAGE}nom_forge_non_affichable": "1",
            }
        )
        corps = reponse.get_data(as_text=True)

        self.assertEqual(reponse.status_code, 400)
        self.verifier_html_seul(corps)
        self.assertIn(MESSAGE_REGLAGE_INCONNU, html.unescape(corps))
        self.assertNotIn("nom_forge_non_affichable", corps)

    def test_get_valeurs_sans_source_refusees(self) -> None:
        for source in (None, f"{MOTEUR}/{'f' * 64}"):
            with self.subTest(source=source):
                parametres = {
                    "modele": self.reference(0),
                    "audios": ["a.wav"],
                    f"{PREFIXE_CHAMP_REGLAGE}beam_size": "8",
                }
                if source is not None:
                    parametres["source"] = source
                reponse = self.preparation(parametres)
                corps = reponse.get_data(as_text=True)

                self.assertEqual(reponse.status_code, 400)
                self.assertIn(
                    MESSAGE_REGLAGES_SANS_SOURCE, html.unescape(corps)
                )
                self.assertIn('name="reglage_beam_size" value="5"', corps)

    def test_post_verifie_conserve_les_valeurs_effectives(self) -> None:
        reponse = self.verifier(
            self.reference(0),
            MOTEUR,
            threads="6",
            **{
                f"{PREFIXE_CHAMP_REGLAGE}compute_type": "int8",
                f"{PREFIXE_CHAMP_REGLAGE}beam_size": "8",
                f"{PREFIXE_CHAMP_REGLAGE}vad_filter": "oui",
            },
        )
        corps = html.unescape(reponse.get_data(as_text=True))
        lancement = self.formulaire_lancement(corps)

        self.assertEqual(reponse.status_code, 200)
        self.assertIn("Demande validée", corps)
        # Vérifier ne remet pas à zéro les valeurs affichées de la préparation.
        self.assertIn('name="threads" value="6"', lancement)
        self.assertIn('<option value="int8" selected>', lancement)
        self.assertIn('name="reglage_beam_size" value="8"', lancement)
        self.assertIn('value="oui" data-valeur-reglage checked', lancement)

    def test_get_valeur_hostile_textuelle_jamais_conservee_ni_repetee(self) -> None:
        origine = self.reference(0)
        hostile = "<script>alert(1)</script>"
        reponse = self.preparation(
            {
                "modele": origine,
                "audios": ["a.wav"],
                "source": origine,
                f"{PREFIXE_CHAMP_REGLAGE}prompt": hostile,
            }
        )
        corps = reponse.get_data(as_text=True)

        self.assertEqual(reponse.status_code, 200)
        self.verifier_html_seul(corps)
        # Un texte libre ne voyage jamais dans une URL de GET : la valeur
        # hostile est écartée et annoncée, jamais réaffichée.
        self.assertNotIn(hostile, corps)
        self.assertNotIn(html.escape(hostile), corps)
        self.assertIn(MESSAGE_TEXTE_NON_CONSERVE, html.unescape(corps))
        self.assertNotIn(f'value="{hostile}"', corps)

    def test_post_valeur_textuelle_hostile_echappee_dans_les_controles(self) -> None:
        origine = self.reference(0)
        hostile = '<script>alert(1)</script> & suite'
        verification = self.verifier(
            origine, MOTEUR, **{f"{PREFIXE_CHAMP_REGLAGE}prompt": hostile}
        )

        self.assertEqual(verification.status_code, 200)
        corps = verification.get_data(as_text=True)
        self.verifier_html_seul(corps)
        # Au POST, la valeur textuelle vérifiée est rendue échappée dans le
        # contrôle de la préparation restituée.
        self.assertNotIn("<script>alert", corps)
        self.assertIn(html.escape(hostile), corps)

    def test_get_champs_de_reglage_repetes_refuses(self) -> None:
        origine = self.reference(0)
        for champ in ("threads", "source", f"{PREFIXE_CHAMP_REGLAGE}beam_size"):
            with self.subTest(champ=champ):
                chemin = "/executions?" + urlencode(
                    [
                        ("modele", origine),
                        ("audios", "a.wav"),
                        ("source", origine),
                        (champ, "1"),
                        (champ, "2"),
                    ]
                )
                reponse = self.client.get(chemin, base_url=self.base_url())

                self.assertEqual(reponse.status_code, 400)
                self.assertIn(
                    MESSAGE_PREPARATION_REFUSEE, reponse.get_data(as_text=True)
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
