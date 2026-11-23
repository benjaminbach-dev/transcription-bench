"""Tests des déclarations de moteurs et du registre, sans paquet moteur.

Le registre et les déclarations ne doivent dépendre que de la bibliothèque
standard : un processus neuf vérifie qu'aucun paquet moteur n'est chargé. Les
imports différés sont vérifiés avec un module d'adaptateur de test contrôlé
(`tests/adaptateur_de_test.py`) et un faux paquet moteur créé dans un dossier
temporaire. Aucun moteur réel, aucun poids et aucun accès réseau.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from dataclasses import FrozenInstanceError, replace
from pathlib import Path

from engines.declarations import (
    DECLARATIONS_FOURNIES,
    TASK_EXTRACTION,
    TASK_TRANSCRIPTION,
    TYPE_BOOLEEN,
    TYPE_CHOIX,
    TYPE_ENTIER,
    TYPE_TEXTE,
    DeclarationAdaptateur,
    DureeNative,
    Famille,
    Reglage,
    declarations_fournies,
    motif_famille_non_executable,
)
from engines.registre import (
    AdaptateurIndisponible,
    DeclarationRefusee,
    MoteurInconnu,
    RegistreMoteurs,
    creer_registre_fourni,
)
from transcription_bench.paths import RACINE_PROJET

MODULE_ADAPTATEUR_DE_TEST = "tests.adaptateur_de_test"
MODULE_MOTEUR_FACTICE = "moteur_factice_stub"

PAQUETS_INTERDITS = (
    "av",
    "ctranslate2",
    "faster_whisper",
    "flask",
    "huggingface_hub",
    "jinja2",
    "llama_cpp",
    "numpy",
    "psutil",
    "torch",
    "transformers",
    "transcribe_cpp",
    "transcribe_cpp_native",
    "waitress",
    "werkzeug",
)

CODE_IMPORT_FRAIS = """
import sys

import engines.declarations
import engines.registre

interdits = {interdits!r}
charges = sorted(module for module in interdits if module in sys.modules)
if charges:
    print("|".join(charges))
    raise SystemExit(1)
print("ok")
"""


def declaration_de_test(
    *,
    identifiant: str = "moteur-de-test",
    module_adaptateur: str | None = MODULE_ADAPTATEUR_DE_TEST,
    modules_verification: tuple[str, ...] = (),
) -> DeclarationAdaptateur:
    return DeclarationAdaptateur(
        identifiant=identifiant,
        nom="Moteur de test",
        fichier_requirements=None,
        regle_compatibilite="aucune",
        familles=(Famille("factice", "Moteur de test"),),
        module_adaptateur=module_adaptateur,
        modules_verification=modules_verification,
    )


class ImportSansPaquetMoteurTest(unittest.TestCase):
    def test_import_du_registre_ne_charge_aucun_paquet_moteur(self) -> None:
        resultat = subprocess.run(
            [sys.executable, "-c", CODE_IMPORT_FRAIS.format(interdits=PAQUETS_INTERDITS)],
            cwd=RACINE_PROJET,
            env={**os.environ, "PYTHONIOENCODING": "utf-8"},
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=60,
            check=False,
        )
        self.assertEqual(
            resultat.returncode,
            0,
            f"paquets moteur chargés : {resultat.stdout.strip()} {resultat.stderr}",
        )
        self.assertEqual(resultat.stdout.strip(), "ok")


class DeclarationsFourniesTest(unittest.TestCase):
    def test_identifiants_stables_et_ordre(self) -> None:
        self.assertEqual(
            tuple(declaration.identifiant for declaration in declarations_fournies()),
            (
                "faster-whisper",
                "transcribe-cpp",
                "transformers",
                "llama-cpp",
                "factice",
            ),
        )
        self.assertIs(declarations_fournies(), DECLARATIONS_FOURNIES)

    def test_familles_reelles_qualifiees_sur_linux_et_factice_non(self) -> None:
        for declaration in declarations_fournies():
            with self.subTest(moteur=declaration.identifiant):
                self.assertTrue(declaration.familles)
                if declaration.factice:
                    self.assertEqual(declaration.familles_qualifiees, ())
                    for famille in declaration.familles:
                        self.assertFalse(famille.qualifiee)
                        self.assertIsNone(famille.duree_native)
                    continue
                # Validation Linux consignée (jalon 0 et tâches 8.1 à 8.3) :
                # les familles réelles sont qualifiées et déclarent la durée
                # native prouvée. La qualification Windows reste due à la CI.
                self.assertEqual(
                    declaration.familles_qualifiees, declaration.familles
                )
                for famille in declaration.familles:
                    self.assertTrue(famille.qualifiee)
                    if (declaration.identifiant, famille.identifiant) in (
                        ("transcribe-cpp", "qwen3-asr"),
                        ("llama-cpp", "llm-gguf"),
                    ):
                        # Aucune durée native prouvée (tâche 8.2 ; llama.cpp : temps
                        # natifs non consignés, tâche 6.3).
                        self.assertIsNone(famille.duree_native)
                    else:
                        self.assertIsNotNone(famille.duree_native)

    def test_seule_la_declaration_factice_porte_le_drapeau(self) -> None:
        drapeaux = {
            declaration.identifiant: declaration.factice
            for declaration in declarations_fournies()
        }
        self.assertEqual(
            drapeaux,
            {
                "faster-whisper": False,
                "transcribe-cpp": False,
                "transformers": False,
                "llama-cpp": False,
                "factice": True,
            },
        )
        # Le drapeau ne vaut pas qualification PC : la famille reste non qualifiée.
        factice = creer_registre_fourni().obtenir("factice")
        self.assertEqual(factice.familles_qualifiees, ())
        self.assertIsNone(factice.fichier_requirements)

    def test_requirements_declares_sans_creation_de_verrou(self) -> None:
        attendus = {
            "faster-whisper": "requirements/faster-whisper.txt",
            "transcribe-cpp": "requirements/transcribe-cpp.txt",
            "transformers": "requirements/transformers.txt",
            "llama-cpp": "requirements/llama-cpp.txt",
            "factice": None,
        }
        for declaration in declarations_fournies():
            with self.subTest(moteur=declaration.identifiant):
                self.assertEqual(
                    declaration.fichier_requirements,
                    attendus[declaration.identifiant],
                )

    def test_tous_les_verrous_sont_valides_apres_essai_minimal(self) -> None:
        # Le verrou llama-cpp, non résolu jusqu'à l'essai minimal 0.1 (PC de
        # test, 2026-11-20), est désormais résolu et vérifié : toutes les
        # déclarations livrées autorisent l'installation. Le refus drapeau
        # baissé reste couvert par test_moteurs.InstallationLlamaCppTest.
        valides = {
            declaration.identifiant: declaration.verrou_valide
            for declaration in declarations_fournies()
        }
        self.assertEqual(
            valides,
            {
                "faster-whisper": True,
                "transcribe-cpp": True,
                "transformers": True,
                "llama-cpp": True,
                "factice": True,
            },
        )

    def test_references_d_adaptateur_locales(self) -> None:
        for declaration in declarations_fournies():
            with self.subTest(moteur=declaration.identifiant):
                self.assertEqual(
                    declaration.module_adaptateur,
                    f"engines.adaptateurs.{declaration.identifiant.replace('-', '_')}",
                )

    def test_modules_de_verification_declares_sans_version(self) -> None:
        attendus = {
            "faster-whisper": ("faster_whisper", "numpy"),
            "transcribe-cpp": ("transcribe_cpp", "numpy"),
            "transformers": ("transformers", "numpy"),
            "llama-cpp": ("llama_cpp",),
            "factice": (),
        }
        for declaration in declarations_fournies():
            with self.subTest(moteur=declaration.identifiant):
                self.assertEqual(
                    declaration.modules_verification,
                    attendus[declaration.identifiant],
                )

    def test_declaration_installable_sans_module_de_verification_refusee(self) -> None:
        with self.assertRaises(ValueError):
            DeclarationAdaptateur(
                identifiant="moteur-de-test",
                nom="Moteur de test",
                fichier_requirements="requirements/test.txt",
                regle_compatibilite="aucune",
                familles=(Famille("factice", "Moteur de test"),),
            )

    def test_module_de_verification_invalide_refuse(self) -> None:
        for module in ("../moteur", "/tmp/moteur.py", "module version==1", ""):
            with self.subTest(module=module):
                with self.assertRaises(ValueError):
                    declaration_de_test(modules_verification=(module,))

    def test_reglages_reels_exposes_par_famille(self) -> None:
        factice = creer_registre_fourni().obtenir("factice")
        self.assertEqual(factice.familles[0].reglages, ())
        noms = {
            (declaration.identifiant, famille.identifiant): tuple(
                reglage.nom for reglage in famille.reglages
            )
            for declaration in declarations_fournies()
            for famille in declaration.familles
        }
        self.assertEqual(
            noms[("faster-whisper", "whisper")],
            ("compute_type", "beam_size"),
        )
        self.assertEqual(
            noms[("transcribe-cpp", "whisper")],
            ("no_mmap", "condition_on_prev_tokens"),
        )
        self.assertEqual(noms[("transformers", "whisper")], ("do_normalize",))
        self.assertEqual(noms[("transformers", "parakeet-tdt")], ())
        self.assertEqual(noms[("llama-cpp", "llm-gguf")], ("contexte", "sortie_max"))
        self.assertEqual(noms[("factice", "factice-extraction")], ())

    def test_declarations_immuables(self) -> None:
        declaration = declarations_fournies()[0]
        with self.assertRaises(FrozenInstanceError):
            declaration.nom = "autre"  # type: ignore[misc]


class TachesTest(unittest.TestCase):
    """Tâche de chaque moteur et de chaque famille, refus croisés de tâche."""

    def test_taches_des_moteurs_fournis(self) -> None:
        obtenues = {
            declaration.identifiant: declaration.tasks
            for declaration in declarations_fournies()
        }
        self.assertEqual(
            obtenues,
            {
                "faster-whisper": ("transcription",),
                "transcribe-cpp": ("transcription",),
                "transformers": ("transcription",),
                "llama-cpp": ("extraction",),
                "factice": ("transcription", "extraction"),
            },
        )

    def test_famille_llama_cpp_d_extraction_avec_reglages_documentes(self) -> None:
        famille = creer_registre_fourni().obtenir("llama-cpp").familles[0]

        self.assertEqual(famille.identifiant, "llm-gguf")
        self.assertEqual(famille.task, TASK_EXTRACTION)
        self.assertIsNone(famille.duree_native)
        self.assertEqual(
            {reglage.nom: (reglage.type_valeur, reglage.defaut) for reglage in famille.reglages},
            {"contexte": (TYPE_ENTIER, 16384), "sortie_max": (TYPE_ENTIER, 4096)},
        )

    def test_factice_expose_une_famille_par_tache(self) -> None:
        factice = creer_registre_fourni().obtenir("factice")

        self.assertEqual(
            {famille.identifiant: famille.task for famille in factice.familles},
            {"factice": TASK_TRANSCRIPTION, "factice-extraction": TASK_EXTRACTION},
        )

    def test_moteur_reel_porte_une_seule_tache(self) -> None:
        with self.assertRaises(ValueError) as contexte:
            DeclarationAdaptateur(
                identifiant="moteur-de-test",
                nom="Moteur de test",
                fichier_requirements=None,
                regle_compatibilite="aucune",
                familles=(
                    Famille("transcription-de-test", "Transcription"),
                    Famille(
                        "extraction-de-test",
                        "Extraction",
                        task=TASK_EXTRACTION,
                    ),
                ),
            )
        self.assertIn("une seule tâche", str(contexte.exception))

    def test_factice_peut_porter_deux_taches(self) -> None:
        declaration = DeclarationAdaptateur(
            identifiant="factice-de-test",
            nom="Factice de test",
            fichier_requirements=None,
            regle_compatibilite="aucune",
            familles=(
                Famille("transcription-de-test", "Transcription"),
                Famille("extraction-de-test", "Extraction", task=TASK_EXTRACTION),
            ),
            factice=True,
        )

        self.assertEqual(declaration.tasks, ("transcription", "extraction"))

    def test_tache_de_famille_inconnue_refusee(self) -> None:
        with self.assertRaises(ValueError):
            Famille("classification-de-test", "Classification", task="classification")

    def test_refus_croise_nomme_les_deux_taches(self) -> None:
        factice = creer_registre_fourni().obtenir("factice")
        famille_transcription, famille_extraction = factice.familles

        motif = motif_famille_non_executable(factice, famille_extraction)
        self.assertIsNotNone(motif)
        self.assertIn("extraction", motif)
        self.assertIn("transcription", motif)
        self.assertIsNone(
            motif_famille_non_executable(factice, famille_extraction, TASK_EXTRACTION)
        )
        motif_inverse = motif_famille_non_executable(
            factice, famille_transcription, TASK_EXTRACTION
        )
        self.assertIsNotNone(motif_inverse)
        self.assertIn("transcription", motif_inverse)

    def test_famille_llama_cpp_refusee_en_transcription_puis_qualifiee_en_extraction(
        self,
    ) -> None:
        llama = creer_registre_fourni().obtenir("llama-cpp")
        famille = llama.familles[0]

        motif_transcription = motif_famille_non_executable(llama, famille)
        self.assertIn("extraction", motif_transcription)
        # Famille qualifiée sur PC (tâche 6.2) : aucun motif en extraction.
        self.assertIsNone(motif_famille_non_executable(llama, famille, TASK_EXTRACTION))
        # Garde-fou conservé : une copie non qualifiée refuse en extraction.
        non_qualifiee = replace(famille, qualifiee=False, duree_native=None)
        motif_non_qualifiee = motif_famille_non_executable(
            llama, non_qualifiee, TASK_EXTRACTION
        )
        self.assertIn("non qualifiée", motif_non_qualifiee)


class ValidationDeclarationTest(unittest.TestCase):
    def test_duree_native_invalide(self) -> None:
        for valeur in (0, -1, float("nan"), float("inf"), float("-inf")):
            with self.subTest(secondes_max=valeur):
                with self.assertRaises(ValueError):
                    DureeNative(valeur, "generate")
        self.assertEqual(DureeNative(30, "generate").secondes_max, 30)
        self.assertEqual(DureeNative(12.5, "generate").methode, "generate")

    def test_identifiant_de_famille_invalide(self) -> None:
        with self.assertRaises(ValueError):
            Famille("Whisper", "Whisper")

    def test_noms_de_reglage_uniques_par_famille(self) -> None:
        reglage = Reglage("langue", "Langue", TYPE_TEXTE, "fr", "Description")
        with self.assertRaises(ValueError):
            Famille("whisper", "Whisper", reglages=(reglage, reglage))

    def test_type_de_reglage_inconnu(self) -> None:
        with self.assertRaises(ValueError):
            Reglage("langue", "Langue", "date", "fr", "Description")

    def test_choix_sans_valeur(self) -> None:
        with self.assertRaises(ValueError):
            Reglage("tache", "Tâche", TYPE_CHOIX, "transcribe", "Description")

    def test_entier_booleen_refuse(self) -> None:
        with self.assertRaises(ValueError):
            Reglage("essais", "Essais", TYPE_ENTIER, True, "Description")
        with self.assertRaises(ValueError):
            Reglage("actif", "Actif", TYPE_BOOLEEN, 1, "Description")

    def test_reference_module_non_locale_refusee(self) -> None:
        for reference in ("../adaptateur", "/tmp/adaptateur.py", "https://exemple.tld/a.py"):
            with self.subTest(reference=reference):
                with self.assertRaises(ValueError):
                    declaration_de_test(module_adaptateur=reference)

    def test_requirements_hors_convention_refuses(self) -> None:
        with self.assertRaises(ValueError):
            DeclarationAdaptateur(
                identifiant="moteur-de-test",
                nom="Moteur de test",
                fichier_requirements="requirements/test.pip",
                regle_compatibilite="aucune",
                familles=(Famille("factice", "Moteur de test"),),
            )

    def test_familles_vides_refusees(self) -> None:
        with self.assertRaises(ValueError):
            DeclarationAdaptateur(
                identifiant="moteur-de-test",
                nom="Moteur de test",
                fichier_requirements=None,
                regle_compatibilite="aucune",
                familles=(),
            )

    def test_drapeau_factice_non_booleen_refuse(self) -> None:
        for valeur in ("oui", 1, None):
            with self.subTest(valeur=valeur):
                with self.assertRaises(ValueError):
                    DeclarationAdaptateur(
                        identifiant="moteur-de-test",
                        nom="Moteur de test",
                        fichier_requirements=None,
                        regle_compatibilite="aucune",
                        familles=(Famille("factice", "Moteur de test"),),
                        factice=valeur,  # type: ignore[arg-type]
                    )
        self.assertFalse(declaration_de_test().factice)


class RegistreMoteursTest(unittest.TestCase):
    def test_registres_independants_et_liste_sans_chargement(self) -> None:
        registre = RegistreMoteurs()
        autre = RegistreMoteurs()
        registre.enregistrer(declaration_de_test())
        self.assertEqual(
            [declaration.identifiant for declaration in registre.lister()],
            ["moteur-de-test"],
        )
        self.assertEqual(autre.lister(), ())
        self.assertEqual(len(creer_registre_fourni().lister()), 5)
        self.assertNotIn(MODULE_ADAPTATEUR_DE_TEST, sys.modules)

    def test_doublon_refuse_sans_remplacement(self) -> None:
        registre = RegistreMoteurs()
        registre.enregistrer(declaration_de_test())
        with self.assertRaises(DeclarationRefusee):
            registre.enregistrer(declaration_de_test())
        self.assertEqual(len(registre.lister()), 1)

    def test_moteur_inconnu(self) -> None:
        registre = RegistreMoteurs()
        with self.assertRaises(MoteurInconnu):
            registre.obtenir("absent")
        with self.assertRaises(MoteurInconnu):
            registre.charger_adaptateur("absent")

    def test_adaptateur_sans_reference_ou_absent(self) -> None:
        registre = RegistreMoteurs()
        registre.enregistrer(
            declaration_de_test(identifiant="sans-module", module_adaptateur=None)
        )
        registre.enregistrer(
            declaration_de_test(
                identifiant="module-absent",
                module_adaptateur="engines.adaptateurs.moteur_inexistant_de_test",
            )
        )
        with self.assertRaises(AdaptateurIndisponible):
            registre.charger_adaptateur("sans-module")
        with self.assertRaises(AdaptateurIndisponible):
            registre.charger_adaptateur("module-absent")

    def test_charger_adaptateur_importe_a_la_demande_et_differe_le_moteur(self) -> None:
        self.addCleanup(sys.modules.pop, MODULE_ADAPTATEUR_DE_TEST, None)
        self.addCleanup(sys.modules.pop, MODULE_MOTEUR_FACTICE, None)
        with tempfile.TemporaryDirectory() as temporaire:
            dossier = Path(temporaire)
            (dossier / f"{MODULE_MOTEUR_FACTICE}.py").write_text(
                "VALEUR = 42\n", encoding="utf-8"
            )
            sys.path.insert(0, temporaire)
            self.addCleanup(sys.path.remove, temporaire)

            self.assertNotIn(MODULE_ADAPTATEUR_DE_TEST, sys.modules)
            registre = RegistreMoteurs()
            registre.enregistrer(declaration_de_test())
            # Enregistrer et lister ne charge ni l'adaptateur ni son paquet moteur.
            self.assertEqual(registre.lister()[0].module_adaptateur, MODULE_ADAPTATEUR_DE_TEST)
            self.assertNotIn(MODULE_ADAPTATEUR_DE_TEST, sys.modules)
            self.assertNotIn(MODULE_MOTEUR_FACTICE, sys.modules)

            module = registre.charger_adaptateur("moteur-de-test")
            # L'import de l'adaptateur n'exécute pas encore son import moteur.
            self.assertIn(MODULE_ADAPTATEUR_DE_TEST, sys.modules)
            self.assertNotIn(MODULE_MOTEUR_FACTICE, sys.modules)
            self.assertEqual(module.creer_moteur().VALEUR, 42)
            self.assertIn(MODULE_MOTEUR_FACTICE, sys.modules)


if __name__ == "__main__":
    unittest.main()
