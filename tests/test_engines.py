"""Tests des déclarations de moteurs et du registre, sans paquet moteur.

Le registre et les déclarations ne doivent dépendre que de la bibliothèque
standard : un processus neuf vérifie qu'aucun paquet moteur n'est chargé. Les
imports différés sont vérifiés avec un module d'adaptateur de test contrôlé
(`tests/adaptateur_de_test.py`) et un faux paquet moteur créé dans un dossier
temporaire. Aucun moteur réel, aucun poids et aucun accès réseau.
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from dataclasses import FrozenInstanceError
from pathlib import Path

from engines.declarations import (
    DECLARATIONS_FOURNIES,
    TYPE_BOOLEEN,
    TYPE_CHOIX,
    TYPE_ENTIER,
    TYPE_TEXTE,
    DeclarationAdaptateur,
    DureeNative,
    Famille,
    Reglage,
    declarations_fournies,
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
) -> DeclarationAdaptateur:
    return DeclarationAdaptateur(
        identifiant=identifiant,
        nom="Moteur de test",
        fichier_requirements=None,
        regle_compatibilite="aucune",
        familles=(Famille("factice", "Moteur de test"),),
        module_adaptateur=module_adaptateur,
    )


class ImportSansPaquetMoteurTest(unittest.TestCase):
    def test_import_du_registre_ne_charge_aucun_paquet_moteur(self) -> None:
        resultat = subprocess.run(
            [sys.executable, "-c", CODE_IMPORT_FRAIS.format(interdits=PAQUETS_INTERDITS)],
            cwd=RACINE_PROJET,
            capture_output=True,
            text=True,
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
            ("faster-whisper", "transcribe-cpp", "transformers", "factice"),
        )
        self.assertIs(declarations_fournies(), DECLARATIONS_FOURNIES)

    def test_aucune_famille_ni_duree_native_qualifiee(self) -> None:
        for declaration in declarations_fournies():
            with self.subTest(moteur=declaration.identifiant):
                self.assertTrue(declaration.familles)
                self.assertEqual(declaration.familles_qualifiees, ())
                for famille in declaration.familles:
                    self.assertFalse(famille.qualifiee)
                    self.assertIsNone(famille.duree_native)

    def test_requirements_declares_sans_creation_de_verrou(self) -> None:
        attendus = {
            "faster-whisper": "requirements/faster-whisper.txt",
            "transcribe-cpp": "requirements/transcribe-cpp.txt",
            "transformers": "requirements/transformers.txt",
            "factice": None,
        }
        for declaration in declarations_fournies():
            with self.subTest(moteur=declaration.identifiant):
                self.assertEqual(
                    declaration.fichier_requirements,
                    attendus[declaration.identifiant],
                )

    def test_references_d_adaptateur_locales(self) -> None:
        for declaration in declarations_fournies():
            with self.subTest(moteur=declaration.identifiant):
                self.assertEqual(
                    declaration.module_adaptateur,
                    f"engines.adaptateurs.{declaration.identifiant.replace('-', '_')}",
                )

    def test_aucun_reglage_reel_fourni(self) -> None:
        for declaration in declarations_fournies():
            with self.subTest(moteur=declaration.identifiant):
                for famille in declaration.familles:
                    self.assertEqual(famille.reglages, ())

    def test_declarations_immuables(self) -> None:
        declaration = declarations_fournies()[0]
        with self.assertRaises(FrozenInstanceError):
            declaration.nom = "autre"  # type: ignore[misc]


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
        self.assertEqual(len(creer_registre_fourni().lister()), 4)
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
