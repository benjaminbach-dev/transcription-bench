"""Tests des règles de compatibilité des modèles, sans moteur, réseau ni poids.

Les dépôts sont simulés par des listes de noms de fichiers et de petits JSON
repris des arborescences publiques documentées (faster-whisper v1.2.1,
`openai/whisper-large-v3-turbo`, `nvidia/parakeet-tdt-0.6b-v3`, source
`transformers` v5.20.2). Les chemins de succès utilisent des déclarations
synthétiques `qualifiee=True` : aucune déclaration fournie ne change de
qualification, et les familles de production restent refusées à l'ajout.
Aucun paquet moteur, aucun fichier de modèle et aucun appel réseau.
"""

from __future__ import annotations

import json
import subprocess
import sys
import unittest

from engines.declarations import (
    DECLARATION_FACTICE,
    DECLARATION_FASTER_WHISPER,
    DECLARATION_TRANSCRIBE_CPP,
    DECLARATION_TRANSFORMERS,
    DeclarationAdaptateur,
    Famille,
    declarations_fournies,
)
from transcription_bench.compatibilite_modeles import (
    RAISON_ARCHITECTURE_GGUF_ABSENTE,
    RAISON_CODE_DISTANT,
    RAISON_CONFIGURATION_ILLISIBLE,
    RAISON_CONFIGURATION_NON_INSPECTEE,
    RAISON_EN_TETE_GGUF_ILLISIBLE,
    RAISON_EN_TETE_GGUF_NON_LU,
    RAISON_FAMILLE_HORS_PERIMETRE,
    RAISON_FAMILLE_NON_QUALIFIEE,
    RAISON_FICHIER_GGUF_ABSENT,
    RAISON_FICHIER_GGUF_NON_CHOISI,
    RAISON_FICHIERS_MANQUANTS,
    RAISON_INDEX_INVALIDE,
    RAISON_NOM_FICHIER_REFUSE,
    RAISON_POIDS_SAFETENSORS_ABSENTS,
    RAISON_WHISPER_NON_CONVERTI,
    PROFONDEUR_MAX_INSPECTION,
    RAISONS_REFUS,
    REGLE_CTRANSLATE2_WHISPER,
    REGLE_TRANSCRIBE_CPP_GGUF,
    REGLE_TRANSFORMERS_SAFETENSORS,
    RegleCompatibiliteInconnue,
    ResultatCompatibilite,
    ResultatCompatibiliteInvalide,
    fichiers_gguf,
    verifier_compatibilite,
)
from transcription_bench.gguf import lire_entete_gguf
from transcription_bench.paths import RACINE_PROJET
from tests.entetes_gguf_de_test import entete_gguf, source_de

PAQUETS_INTERDITS = (
    "av",
    "ctranslate2",
    "faster_whisper",
    "huggingface_hub",
    "numpy",
    "torch",
    "transformers",
    "transcribe_cpp",
)

CODE_IMPORT_FRAIS = """
import sys

import transcription_bench.compatibilite_modeles

interdits = {interdits!r}
charges = sorted(module for module in interdits if module in sys.modules)
if charges:
    print("|".join(charges))
    raise SystemExit(1)
print("ok")
"""

# Dépôt CTranslate2 simulé, sur le modèle de
# mobiuslabsgmbh/faster-whisper-large-v3-turbo.
FICHIERS_CTRANSLATE2 = (
    ".gitattributes",
    "README.md",
    "config.json",
    "model.bin",
    "preprocessor_config.json",
    "tokenizer.json",
    "vocabulary.json",
)
CONTENUS_CTRANSLATE2 = {
    # config.json CTranslate2 : ni model_type ni architectures Hugging Face.
    "config.json": json.dumps(
        {
            "alignment_heads": [[1, 2]],
            "lang_ids": {"fr": 50265},
            "suppress_ids": [50257],
        }
    ),
    "preprocessor_config.json": json.dumps(
        {"feature_extractor_type": "WhisperFeatureExtractor", "sampling_rate": 16000}
    ),
}

# Dépôt Transformers Whisper simulé, sur le modèle de openai/whisper-large-v3-turbo.
FICHIERS_WHISPER_TRANSFORMERS = (
    ".gitattributes",
    "README.md",
    "added_tokens.json",
    "config.json",
    "generation_config.json",
    "merges.txt",
    "model.safetensors",
    "normalizer.json",
    "preprocessor_config.json",
    "special_tokens_map.json",
    "tokenizer.json",
    "tokenizer_config.json",
    "vocab.json",
)
CONTENUS_WHISPER_TRANSFORMERS = {
    "config.json": json.dumps(
        {
            "model_type": "whisper",
            "architectures": ["WhisperForConditionalGeneration"],
        }
    ),
    "generation_config.json": json.dumps({"max_length": 448}),
    "preprocessor_config.json": json.dumps(
        {"feature_extractor_type": "WhisperFeatureExtractor", "sampling_rate": 16000}
    ),
    "tokenizer_config.json": json.dumps({"tokenizer_class": "WhisperTokenizer"}),
}

# Dépôt Transformers Parakeet TDT simulé, sur le modèle de nvidia/parakeet-tdt-0.6b-v3.
FICHIERS_PARAKET = (
    ".gitattributes",
    "README.md",
    "config.json",
    "generation_config.json",
    "model.safetensors",
    "parakeet-tdt-0.6b-v3.nemo",
    "parakeet-tdt-0.6b-v3.q8_0.gguf",
    "processor_config.json",
    "tokenizer.json",
    "tokenizer_config.json",
)
CONTENUS_PARAKET = {
    "config.json": json.dumps(
        {"model_type": "parakeet_tdt", "architectures": ["ParakeetForTDT"]}
    ),
    "generation_config.json": json.dumps({"max_new_tokens": 512}),
    "processor_config.json": json.dumps(
        {
            "feature_extractor": {
                "feature_extractor_type": "ParakeetFeatureExtractor",
                "sampling_rate": 16000,
            },
            "tokenizer_class": "ParakeetTokenizer",
        }
    ),
    "tokenizer_config.json": json.dumps(
        {"tokenizer_class": "ParakeetTokenizer", "tokenizer_file": "tokenizer.json"}
    ),
}


# Dépôt GGUF transcribe.cpp simulé : deux quantifications, un README et un
# config.json sans rapport, ignorés. Aucune architecture n'est déduite du nom.
FICHIERS_GGUF = (
    ".gitattributes",
    "README.md",
    "config.json",
    "modele-f16.gguf",
    "modele-q8_0.gguf",
)


def octets_gguf(architecture: str = "whisper", *, version: int = 3) -> bytes:
    """En-tête GGUF minimal portant `general.architecture`, généré localement."""
    return entete_gguf(
        ("general.name", "string", "modèle de test"),
        ("general.architecture", "string", architecture),
        version=version,
    )


def lecteur_gguf_de(octets: bytes, journal: list[str] | None = None):
    """Lecteur d'en-tête injecté : lit les octets fournis et note les appels."""

    def lire(nom: str):
        if journal is not None:
            journal.append(nom)
        return lire_entete_gguf(source_de(octets))

    return lire


def declaration_synthetique(
    *,
    identifiant: str = "moteur-de-test",
    regle: str = REGLE_CTRANSLATE2_WHISPER,
    familles: tuple[str, ...] = ("whisper",),
) -> DeclarationAdaptateur:
    """Déclaration qualifiée synthétique : couvre les chemins de succès en test."""
    return DeclarationAdaptateur(
        identifiant=identifiant,
        nom="Moteur de test",
        fichier_requirements=f"requirements/{identifiant}.txt",
        regle_compatibilite=regle,
        familles=tuple(Famille(nom, nom, qualifiee=True) for nom in familles),
        module_adaptateur="tests.adaptateur_de_test",
        modules_verification=("tests",),
    )


def retire(fichiers: tuple[str, ...], *noms: str) -> tuple[str, ...]:
    return tuple(nom for nom in fichiers if nom not in noms)


def remplace(fichiers: tuple[str, ...], ancien: str, nouveau: str) -> tuple[str, ...]:
    return tuple(nouveau if nom == ancien else nom for nom in fichiers)


class AssertionsCompatibilite(unittest.TestCase):
    def assertAccepte(self, resultat: ResultatCompatibilite, famille: str) -> None:
        self.assertTrue(resultat.accepte, resultat.message)
        self.assertIsNone(resultat.raison)
        self.assertEqual(resultat.famille, famille)
        self.assertTrue(resultat.fichiers)
        self.assertEqual(resultat.fichiers_manquants, ())

    def assertRefus(
        self, resultat: ResultatCompatibilite, raison: str
    ) -> ResultatCompatibilite:
        self.assertFalse(resultat.accepte, resultat.message)
        self.assertEqual(resultat.raison, raison)
        self.assertIn(resultat.raison, RAISONS_REFUS)
        self.assertIsInstance(resultat.message, str)
        self.assertTrue(resultat.message.strip())
        self.assertEqual(resultat.fichiers, ())
        return resultat


class ImportSansPaquetMoteurTest(unittest.TestCase):
    def test_import_des_regles_ne_charge_aucun_paquet_moteur(self) -> None:
        resultat = subprocess.run(
            [
                sys.executable,
                "-c",
                CODE_IMPORT_FRAIS.format(interdits=PAQUETS_INTERDITS),
            ],
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


class FasterWhisperCompatibiliteTest(AssertionsCompatibilite):
    def setUp(self) -> None:
        self.declaration = declaration_synthetique()

    def test_depot_ctranslate2_accepte(self) -> None:
        resultat = verifier_compatibilite(
            self.declaration,
            FICHIERS_CTRANSLATE2,
            configurations=CONTENUS_CTRANSLATE2,
        )
        self.assertAccepte(resultat, "whisper")
        self.assertEqual(
            resultat.fichiers,
            (
                "config.json",
                "model.bin",
                "preprocessor_config.json",
                "tokenizer.json",
                "vocabulary.json",
            ),
        )

    def test_fichiers_hors_liste_blanche_ignores(self) -> None:
        fichiers = (
            *FICHIERS_CTRANSLATE2,
            "model.safetensors",
            "model.pt",
            "onnx/model.onnx",
        )
        resultat = verifier_compatibilite(self.declaration, fichiers)
        self.assertAccepte(resultat, "whisper")
        self.assertNotIn("model.safetensors", resultat.fichiers)
        self.assertNotIn("model.pt", resultat.fichiers)
        self.assertNotIn("onnx/model.onnx", resultat.fichiers)

    def test_vocabulary_facultatif_json_ou_txt(self) -> None:
        cas = {
            "vocabulary.json": FICHIERS_CTRANSLATE2,
            "vocabulary.txt": remplace(
                FICHIERS_CTRANSLATE2, "vocabulary.json", "vocabulary.txt"
            ),
            "sans vocabulaire": retire(FICHIERS_CTRANSLATE2, "vocabulary.json"),
        }
        for etiquette, fichiers in cas.items():
            with self.subTest(cas=etiquette):
                resultat = verifier_compatibilite(self.declaration, fichiers)
                self.assertAccepte(resultat, "whisper")
                if etiquette == "sans vocabulaire":
                    self.assertNotIn("vocabulary.json", resultat.fichiers)
                    self.assertNotIn("vocabulary.txt", resultat.fichiers)
                else:
                    self.assertIn(etiquette, resultat.fichiers)

    def test_whisper_transformers_refuse_pour_faster_whisper(self) -> None:
        resultat = verifier_compatibilite(
            DECLARATION_FASTER_WHISPER,
            FICHIERS_WHISPER_TRANSFORMERS,
            configurations=CONTENUS_WHISPER_TRANSFORMERS,
        )
        refus = self.assertRefus(resultat, RAISON_WHISPER_NON_CONVERTI)
        self.assertEqual(refus.famille, "whisper")
        self.assertEqual(refus.moteur_suggere, "transformers")
        self.assertIn("model.bin", refus.fichiers_manquants)

    def test_depot_incomplet_indique_les_fichiers_manquants(self) -> None:
        fichiers = retire(
            FICHIERS_CTRANSLATE2, "tokenizer.json", "preprocessor_config.json"
        )
        resultat = verifier_compatibilite(self.declaration, fichiers)
        refus = self.assertRefus(resultat, RAISON_FICHIERS_MANQUANTS)
        self.assertEqual(
            refus.fichiers_manquants, ("preprocessor_config.json", "tokenizer.json")
        )

    def test_preprocesseur_seul_manquant_refuse_sans_valeurs_par_defaut(self) -> None:
        # Règle stricte du prototype : même un petit CTranslate2 comme
        # Systran/faster-whisper-small est refusé, sans valeurs par défaut.
        fichiers = retire(FICHIERS_CTRANSLATE2, "preprocessor_config.json")
        resultat = verifier_compatibilite(self.declaration, fichiers)
        refus = self.assertRefus(resultat, RAISON_FICHIERS_MANQUANTS)
        self.assertEqual(refus.fichiers_manquants, ("preprocessor_config.json",))

    def test_production_refuse_la_famille_non_qualifiee(self) -> None:
        resultat = verifier_compatibilite(
            DECLARATION_FASTER_WHISPER,
            FICHIERS_CTRANSLATE2,
            configurations=CONTENUS_CTRANSLATE2,
        )
        refus = self.assertRefus(resultat, RAISON_FAMILLE_NON_QUALIFIEE)
        self.assertEqual(refus.famille, "whisper")
        self.assertEqual(refus.fichiers_manquants, ())

    def test_auto_map_dans_config_json_ctranslate2_refuse(self) -> None:
        contenus = dict(CONTENUS_CTRANSLATE2)
        contenus["config.json"] = json.dumps(
            {"auto_map": {"AutoModel": "modele.Configuration"}}
        )
        resultat = verifier_compatibilite(
            self.declaration, FICHIERS_CTRANSLATE2, configurations=contenus
        )
        self.assertRefus(resultat, RAISON_CODE_DISTANT)


class TransformersCompatibiliteTest(AssertionsCompatibilite):
    def setUp(self) -> None:
        self.declaration = declaration_synthetique(
            identifiant="transformers",
            regle=REGLE_TRANSFORMERS_SAFETENSORS,
            familles=("whisper", "parakeet-tdt"),
        )

    def test_whisper_accepte_avec_sa_liste_blanche_complete(self) -> None:
        resultat = verifier_compatibilite(
            self.declaration,
            FICHIERS_WHISPER_TRANSFORMERS,
            configurations=CONTENUS_WHISPER_TRANSFORMERS,
        )
        self.assertAccepte(resultat, "whisper")
        self.assertEqual(
            resultat.fichiers,
            (
                "added_tokens.json",
                "config.json",
                "generation_config.json",
                "merges.txt",
                "model.safetensors",
                "normalizer.json",
                "preprocessor_config.json",
                "special_tokens_map.json",
                "tokenizer.json",
                "tokenizer_config.json",
                "vocab.json",
            ),
        )

    def test_parakeet_accepte_avec_processor_config_seul(self) -> None:
        resultat = verifier_compatibilite(
            self.declaration,
            FICHIERS_PARAKET,
            configurations=CONTENUS_PARAKET,
        )
        self.assertAccepte(resultat, "parakeet-tdt")
        self.assertEqual(
            resultat.fichiers,
            (
                "config.json",
                "generation_config.json",
                "model.safetensors",
                "processor_config.json",
                "tokenizer.json",
                "tokenizer_config.json",
            ),
        )
        self.assertNotIn("parakeet-tdt-0.6b-v3.nemo", resultat.fichiers)
        self.assertNotIn("parakeet-tdt-0.6b-v3.q8_0.gguf", resultat.fichiers)

    def test_depot_sans_processor_ni_preprocessor_refuse(self) -> None:
        fichiers = retire(
            FICHIERS_PARAKET, "processor_config.json", "parakeet-tdt-0.6b-v3.nemo"
        )
        resultat = verifier_compatibilite(
            self.declaration, fichiers, configurations=CONTENUS_PARAKET
        )
        refus = self.assertRefus(resultat, RAISON_FICHIERS_MANQUANTS)
        self.assertEqual(refus.fichiers_manquants, ("preprocessor_config.json",))

    def test_processor_config_sans_feature_extractor_refuse(self) -> None:
        contenus = dict(CONTENUS_PARAKET)
        contenus["processor_config.json"] = json.dumps(
            {"tokenizer_class": "ParakeetTokenizer"}
        )
        resultat = verifier_compatibilite(
            self.declaration, FICHIERS_PARAKET, configurations=contenus
        )
        refus = self.assertRefus(resultat, RAISON_FICHIERS_MANQUANTS)
        self.assertEqual(refus.fichiers_manquants, ("preprocessor_config.json",))
        self.assertIn("feature_extractor", refus.message)

    def test_whisper_sans_generation_config_refuse(self) -> None:
        fichiers = retire(FICHIERS_WHISPER_TRANSFORMERS, "generation_config.json")
        contenus = dict(CONTENUS_WHISPER_TRANSFORMERS)
        contenus.pop("generation_config.json")
        resultat = verifier_compatibilite(
            self.declaration, fichiers, configurations=contenus
        )
        refus = self.assertRefus(resultat, RAISON_FICHIERS_MANQUANTS)
        self.assertEqual(refus.fichiers_manquants, ("generation_config.json",))
        self.assertIn("generation_config.json", refus.message)

    def test_parakeet_ignore_les_auxiliaires_de_vocabulaire_whisper(self) -> None:
        fichiers = (
            *FICHIERS_PARAKET,
            "vocab.json",
            "merges.txt",
            "normalizer.json",
        )
        resultat = verifier_compatibilite(
            self.declaration, fichiers, configurations=CONTENUS_PARAKET
        )
        self.assertAccepte(resultat, "parakeet-tdt")
        self.assertIn("generation_config.json", resultat.fichiers)
        for nom in ("vocab.json", "merges.txt", "normalizer.json"):
            self.assertNotIn(nom, resultat.fichiers)

    def test_tokenizer_manquant_refuse(self) -> None:
        for nom in ("tokenizer.json", "tokenizer_config.json"):
            with self.subTest(fichier=nom):
                fichiers = retire(FICHIERS_WHISPER_TRANSFORMERS, nom)
                contenus = dict(CONTENUS_WHISPER_TRANSFORMERS)
                contenus.pop(nom, None)
                resultat = verifier_compatibilite(
                    self.declaration, fichiers, configurations=contenus
                )
                refus = self.assertRefus(resultat, RAISON_FICHIERS_MANQUANTS)
                self.assertEqual(refus.fichiers_manquants, (nom,))

    def test_famille_hors_perimetre_refusee(self) -> None:
        contenus = dict(CONTENUS_WHISPER_TRANSFORMERS)
        contenus["config.json"] = json.dumps({"model_type": "wav2vec2"})
        resultat = verifier_compatibilite(
            self.declaration,
            FICHIERS_WHISPER_TRANSFORMERS,
            configurations=contenus,
        )
        refus = self.assertRefus(resultat, RAISON_FAMILLE_HORS_PERIMETRE)
        self.assertIn("extension future", refus.message)
        self.assertIsNone(refus.famille)

    def test_model_type_absent_refuse(self) -> None:
        contenus = dict(CONTENUS_WHISPER_TRANSFORMERS)
        contenus["config.json"] = json.dumps(
            {"architectures": ["WhisperForConditionalGeneration"]}
        )
        resultat = verifier_compatibilite(
            self.declaration,
            FICHIERS_WHISPER_TRANSFORMERS,
            configurations=contenus,
        )
        self.assertRefus(resultat, RAISON_FAMILLE_HORS_PERIMETRE)

    def test_famille_non_declaree_suggere_un_autre_moteur(self) -> None:
        declaration = declaration_synthetique(
            identifiant="transformers-parakeet",
            regle=REGLE_TRANSFORMERS_SAFETENSORS,
            familles=("parakeet-tdt",),
        )
        resultat = verifier_compatibilite(
            declaration,
            FICHIERS_WHISPER_TRANSFORMERS,
            configurations=CONTENUS_WHISPER_TRANSFORMERS,
            declarations_connues=(DECLARATION_TRANSFORMERS,),
        )
        refus = self.assertRefus(resultat, RAISON_FAMILLE_HORS_PERIMETRE)
        self.assertEqual(refus.famille, "whisper")
        self.assertEqual(refus.moteur_suggere, "transformers")

    def test_production_refuse_la_famille_non_qualifiee(self) -> None:
        resultat = verifier_compatibilite(
            DECLARATION_TRANSFORMERS,
            FICHIERS_WHISPER_TRANSFORMERS,
            configurations=CONTENUS_WHISPER_TRANSFORMERS,
        )
        refus = self.assertRefus(resultat, RAISON_FAMILLE_NON_QUALIFIEE)
        self.assertEqual(refus.famille, "whisper")

        resultat = verifier_compatibilite(
            DECLARATION_TRANSFORMERS,
            FICHIERS_PARAKET,
            configurations=CONTENUS_PARAKET,
        )
        refus = self.assertRefus(resultat, RAISON_FAMILLE_NON_QUALIFIEE)
        self.assertEqual(refus.famille, "parakeet-tdt")

    def test_auto_map_dans_processor_config_refuse(self) -> None:
        contenus = dict(CONTENUS_PARAKET)
        contenus["processor_config.json"] = json.dumps(
            {
                "feature_extractor": {"sampling_rate": 16000},
                "auto_map": {"AutoProcessor": "modele.Processor"},
            }
        )
        resultat = verifier_compatibilite(
            self.declaration, FICHIERS_PARAKET, configurations=contenus
        )
        refus = self.assertRefus(resultat, RAISON_CODE_DISTANT)
        self.assertIn("processor_config.json", refus.message)

    def test_auto_map_dans_tokenizer_config_refuse(self) -> None:
        contenus = dict(CONTENUS_WHISPER_TRANSFORMERS)
        contenus["tokenizer_config.json"] = json.dumps(
            {"auto_map": {"AutoTokenizer": "modele.Tokenizer"}}
        )
        resultat = verifier_compatibilite(
            self.declaration,
            FICHIERS_WHISPER_TRANSFORMERS,
            configurations=contenus,
        )
        refus = self.assertRefus(resultat, RAISON_CODE_DISTANT)
        self.assertIn("tokenizer_config.json", refus.message)

    def test_auto_map_imbrique_refuse(self) -> None:
        contenus = dict(CONTENUS_PARAKET)
        contenus["processor_config.json"] = json.dumps(
            {"feature_extractor": {"sous_config": {"auto_map": {"X": "y.Z"}}}}
        )
        resultat = verifier_compatibilite(
            self.declaration, FICHIERS_PARAKET, configurations=contenus
        )
        self.assertRefus(resultat, RAISON_CODE_DISTANT)

    def test_configuration_illisible_refusee(self) -> None:
        for contenu in ("{ pas du json", "[]", '"texte"', "\xff".encode("latin-1")):
            with self.subTest(contenu=contenu):
                contenus = dict(CONTENUS_WHISPER_TRANSFORMERS)
                contenus["config.json"] = contenu
                resultat = verifier_compatibilite(
                    self.declaration,
                    FICHIERS_WHISPER_TRANSFORMERS,
                    configurations=contenus,
                )
                self.assertRefus(resultat, RAISON_CONFIGURATION_ILLISIBLE)

    def test_configuration_non_fournie_refusee(self) -> None:
        contenus = dict(CONTENUS_WHISPER_TRANSFORMERS)
        contenus.pop("config.json")
        resultat = verifier_compatibilite(
            self.declaration, FICHIERS_WHISPER_TRANSFORMERS, configurations=contenus
        )
        refus = self.assertRefus(resultat, RAISON_CONFIGURATION_NON_INSPECTEE)
        self.assertIn("config.json", refus.message)

    def test_configuration_trop_profonde_refusee(self) -> None:
        profond: dict[str, object] = {"model_type": "whisper"}
        for _ in range(PROFONDEUR_MAX_INSPECTION + 4):
            profond = {"sous_config": profond}
        contenus = dict(CONTENUS_WHISPER_TRANSFORMERS)
        contenus["config.json"] = json.dumps(profond)
        resultat = verifier_compatibilite(
            self.declaration, FICHIERS_WHISPER_TRANSFORMERS, configurations=contenus
        )
        self.assertRefus(resultat, RAISON_CONFIGURATION_ILLISIBLE)

    def test_json_trop_profond_pour_etre_decode_refuse(self) -> None:
        contenus = dict(CONTENUS_WHISPER_TRANSFORMERS)
        contenus["config.json"] = "[" * 200_000
        resultat = verifier_compatibilite(
            self.declaration, FICHIERS_WHISPER_TRANSFORMERS, configurations=contenus
        )
        self.assertRefus(resultat, RAISON_CONFIGURATION_ILLISIBLE)

    def test_tokenizer_config_reel_depasse_les_anciennes_bornes_de_noeuds(self) -> None:
        jetons = {
            str(i): {
                "id": i,
                "content": f"<|jeton-{i}|>",
                "single_word": False,
                "lstrip": False,
                "rstrip": False,
                "normalized": False,
            }
            for i in range(1700)
        }
        contenus = dict(CONTENUS_WHISPER_TRANSFORMERS)
        contenus["tokenizer_config.json"] = json.dumps(
            {
                "tokenizer_class": "WhisperTokenizer",
                "added_tokens_decoder": jetons,
                "additional_special_tokens": ["<|debut|>", "<|fin|>"],
            }
        )
        resultat = verifier_compatibilite(
            self.declaration, FICHIERS_WHISPER_TRANSFORMERS, configurations=contenus
        )
        self.assertAccepte(resultat, "whisper")
        self.assertIn("tokenizer_config.json", resultat.fichiers)

    def test_depot_mixte_selectionne_uniquement_safetensors(self) -> None:
        fichiers = (
            *FICHIERS_WHISPER_TRANSFORMERS,
            "pytorch_model.bin",
            "pytorch_model.bin.index.json",
            "model.pt",
            "model.pth",
            "model.nemo",
            "model.q8_0.gguf",
            "onnx/model.onnx",
            "model.h5",
        )
        resultat = verifier_compatibilite(
            self.declaration, fichiers, configurations=CONTENUS_WHISPER_TRANSFORMERS
        )
        self.assertAccepte(resultat, "whisper")
        for nom in (
            "pytorch_model.bin",
            "pytorch_model.bin.index.json",
            "model.pt",
            "model.pth",
            "model.nemo",
            "model.q8_0.gguf",
            "onnx/model.onnx",
            "model.h5",
        ):
            self.assertNotIn(nom, resultat.fichiers)

    def test_poids_pickle_seul_refuse(self) -> None:
        fichiers = retire(
            FICHIERS_WHISPER_TRANSFORMERS, "model.safetensors"
        ) + ("pytorch_model.bin", "model.pt")
        resultat = verifier_compatibilite(
            self.declaration, fichiers, configurations=CONTENUS_WHISPER_TRANSFORMERS
        )
        self.assertRefus(resultat, RAISON_POIDS_SAFETENSORS_ABSENTS)

    def test_shards_complets_acceptes_sans_shard_inutilise(self) -> None:
        fichiers = (
            *retire(FICHIERS_WHISPER_TRANSFORMERS, "model.safetensors"),
            "model.safetensors.index.json",
            "model-00001-of-00002.safetensors",
            "model-00002-of-00002.safetensors",
            "model-00003-of-00003.safetensors",
        )
        contenus = dict(CONTENUS_WHISPER_TRANSFORMERS)
        contenus["model.safetensors.index.json"] = json.dumps(
            {
                "metadata": {"total_size": 1234},
                "weight_map": {
                    "model.encoder.conv1.weight": "model-00001-of-00002.safetensors",
                    "model.decoder.layers.0.weight": "model-00002-of-00002.safetensors",
                },
            }
        )
        resultat = verifier_compatibilite(
            self.declaration, fichiers, configurations=contenus
        )
        self.assertAccepte(resultat, "whisper")
        self.assertIn("model.safetensors.index.json", resultat.fichiers)
        self.assertIn("model-00001-of-00002.safetensors", resultat.fichiers)
        self.assertIn("model-00002-of-00002.safetensors", resultat.fichiers)
        self.assertNotIn("model-00003-of-00003.safetensors", resultat.fichiers)

    def test_index_avec_nom_de_shard_refuse(self) -> None:
        fichiers = (
            *retire(FICHIERS_WHISPER_TRANSFORMERS, "model.safetensors"),
            "model.safetensors.index.json",
            "model-00001-of-00002.safetensors",
        )
        contenus = dict(CONTENUS_WHISPER_TRANSFORMERS)
        contenus["model.safetensors.index.json"] = json.dumps(
            {
                "weight_map": {
                    "a": "model-00001-of-00002.safetensors",
                    "b": "../model-00002-of-00002.safetensors",
                }
            }
        )
        resultat = verifier_compatibilite(
            self.declaration, fichiers, configurations=contenus
        )
        self.assertRefus(resultat, RAISON_INDEX_INVALIDE)

    def test_index_complet_prime_sur_le_fichier_unique(self) -> None:
        fichiers = (
            *FICHIERS_WHISPER_TRANSFORMERS,
            "model.safetensors.index.json",
            "model-00001-of-00002.safetensors",
            "model-00002-of-00002.safetensors",
        )
        contenus = dict(CONTENUS_WHISPER_TRANSFORMERS)
        contenus["model.safetensors.index.json"] = json.dumps(
            {
                "weight_map": {
                    "a": "model-00001-of-00002.safetensors",
                    "b": "model-00002-of-00002.safetensors",
                }
            }
        )
        resultat = verifier_compatibilite(
            self.declaration, fichiers, configurations=contenus
        )
        self.assertAccepte(resultat, "whisper")
        self.assertIn("model.safetensors.index.json", resultat.fichiers)
        self.assertIn("model-00001-of-00002.safetensors", resultat.fichiers)
        self.assertIn("model-00002-of-00002.safetensors", resultat.fichiers)
        self.assertNotIn("model.safetensors", resultat.fichiers)

    def test_shard_manquant_refuse(self) -> None:
        fichiers = (
            *retire(FICHIERS_WHISPER_TRANSFORMERS, "model.safetensors"),
            "model.safetensors.index.json",
            "model-00001-of-00002.safetensors",
        )
        contenus = dict(CONTENUS_WHISPER_TRANSFORMERS)
        contenus["model.safetensors.index.json"] = json.dumps(
            {
                "weight_map": {
                    "a": "model-00001-of-00002.safetensors",
                    "b": "model-00002-of-00002.safetensors",
                }
            }
        )
        resultat = verifier_compatibilite(
            self.declaration, fichiers, configurations=contenus
        )
        refus = self.assertRefus(resultat, RAISON_INDEX_INVALIDE)
        self.assertEqual(
            refus.fichiers_manquants, ("model-00002-of-00002.safetensors",)
        )

    def test_index_invalide_refuse(self) -> None:
        fichiers = (
            *retire(FICHIERS_WHISPER_TRANSFORMERS, "model.safetensors"),
            "model.safetensors.index.json",
            "model-00001-of-00002.safetensors.bin",
        )
        index = "model.safetensors.index.json"
        for contenu in (
            "{ pas du json",
            json.dumps({}),
            json.dumps({"weight_map": []}),
            json.dumps({"weight_map": {"a": 1}}),
            json.dumps({"weight_map": {"a": "model-00001-of-00002.safetensors.bin"}}),
            json.dumps({"weight_map": {"a": "/abs/model-00001.safetensors"}}),
        ):
            with self.subTest(contenu=contenu):
                contenus = dict(CONTENUS_WHISPER_TRANSFORMERS)
                contenus[index] = contenu
                resultat = verifier_compatibilite(
                    self.declaration, fichiers, configurations=contenus
                )
                self.assertIn(
                    resultat.raison,
                    (RAISON_INDEX_INVALIDE, RAISON_CONFIGURATION_ILLISIBLE),
                )
                self.assertRefus(resultat, resultat.raison)

    def test_index_non_fourni_refuse(self) -> None:
        fichiers = (
            *retire(FICHIERS_WHISPER_TRANSFORMERS, "model.safetensors"),
            "model.safetensors.index.json",
            "model-00001-of-00002.safetensors",
        )
        resultat = verifier_compatibilite(
            self.declaration, fichiers, configurations=CONTENUS_WHISPER_TRANSFORMERS
        )
        self.assertRefus(resultat, RAISON_CONFIGURATION_NON_INSPECTEE)

    def test_index_pickle_ignore_et_poids_safetensors_absents(self) -> None:
        fichiers = (
            *retire(FICHIERS_WHISPER_TRANSFORMERS, "model.safetensors"),
            "pytorch_model.bin.index.json",
            "pytorch_model-00001-of-00002.bin",
            "pytorch_model-00002-of-00002.bin",
        )
        resultat = verifier_compatibilite(
            self.declaration, fichiers, configurations=CONTENUS_WHISPER_TRANSFORMERS
        )
        self.assertRefus(resultat, RAISON_POIDS_SAFETENSORS_ABSENTS)

    def test_shards_sans_index_ne_suffisent_pas(self) -> None:
        fichiers = (
            *retire(FICHIERS_WHISPER_TRANSFORMERS, "model.safetensors"),
            "model-00001-of-00002.safetensors",
            "model-00002-of-00002.safetensors",
        )
        resultat = verifier_compatibilite(
            self.declaration, fichiers, configurations=CONTENUS_WHISPER_TRANSFORMERS
        )
        self.assertRefus(resultat, RAISON_POIDS_SAFETENSORS_ABSENTS)


class TranscribeCppCompatibiliteTest(AssertionsCompatibilite):
    def setUp(self) -> None:
        self.declaration = declaration_synthetique(
            identifiant="transcribe-cpp",
            regle=REGLE_TRANSCRIBE_CPP_GGUF,
            familles=("whisper",),
        )

    def test_gguf_whisper_accepte_et_seule_variante_choisie_listee(self) -> None:
        journal: list[str] = []
        resultat = verifier_compatibilite(
            self.declaration,
            (*FICHIERS_GGUF, "notes.txt"),
            fichier_gguf="modele-q8_0.gguf",
            lecteur_entete_gguf=lecteur_gguf_de(octets_gguf(), journal),
        )
        self.assertAccepte(resultat, "whisper")
        # Le nom déclaré porte la variante, sans qu'aucune quantification ne soit
        # affirmée : seule cette variante est retenue.
        self.assertEqual(resultat.fichiers, ("modele-q8_0.gguf",))
        self.assertEqual(journal, ["modele-q8_0.gguf"])

    def test_unique_gguf_accepte_sans_choix_explicite(self) -> None:
        fichiers = retire(FICHIERS_GGUF, "modele-f16.gguf")
        resultat = verifier_compatibilite(
            self.declaration,
            fichiers,
            lecteur_entete_gguf=lecteur_gguf_de(octets_gguf(version=2)),
        )
        self.assertAccepte(resultat, "whisper")
        self.assertEqual(resultat.fichiers, ("modele-q8_0.gguf",))

    def test_plusieurs_gguf_sans_choix_refuses(self) -> None:
        self.assertEqual(
            fichiers_gguf((*FICHIERS_GGUF, "dossier/autre.gguf", "notes.txt")),
            ("dossier/autre.gguf", "modele-f16.gguf", "modele-q8_0.gguf"),
        )
        journal: list[str] = []
        resultat = verifier_compatibilite(
            self.declaration,
            FICHIERS_GGUF,
            lecteur_entete_gguf=lecteur_gguf_de(octets_gguf(), journal),
        )
        refus = self.assertRefus(resultat, RAISON_FICHIER_GGUF_NON_CHOISI)
        self.assertIn("modele-f16.gguf", refus.message)
        self.assertIn("modele-q8_0.gguf", refus.message)
        self.assertEqual(journal, [])

    def test_choix_hors_liste_ou_nom_dangereux_refuse_sans_lecture(self) -> None:
        journal: list[str] = []
        lecteur = lecteur_gguf_de(octets_gguf(), journal)
        cas = {
            "notes.txt": RAISON_FICHIER_GGUF_NON_CHOISI,
            "modele-q4.gguf": RAISON_FICHIER_GGUF_NON_CHOISI,
            "../modele-q8_0.gguf": RAISON_NOM_FICHIER_REFUSE,
            "/tmp/modele-q8_0.gguf": RAISON_NOM_FICHIER_REFUSE,
            "dossier\\modele-q8_0.gguf": RAISON_NOM_FICHIER_REFUSE,
        }
        for choix, raison in cas.items():
            with self.subTest(choix=choix):
                resultat = verifier_compatibilite(
                    self.declaration,
                    FICHIERS_GGUF,
                    fichier_gguf=choix,
                    lecteur_entete_gguf=lecteur,
                )
                self.assertRefus(resultat, raison)
        self.assertEqual(journal, [])
        with self.assertRaises(TypeError):
            verifier_compatibilite(
                self.declaration,
                FICHIERS_GGUF,
                fichier_gguf=42,  # type: ignore[arg-type]
                lecteur_entete_gguf=lecteur,
            )

    def test_depot_sans_gguf_refuse(self) -> None:
        fichiers = retire(FICHIERS_GGUF, "modele-f16.gguf", "modele-q8_0.gguf") + (
            "model.safetensors",
        )
        resultat = verifier_compatibilite(
            self.declaration,
            fichiers,
            lecteur_entete_gguf=lecteur_gguf_de(octets_gguf()),
        )
        self.assertRefus(resultat, RAISON_FICHIER_GGUF_ABSENT)

    def test_architecture_vient_de_l_entete_pas_du_nom(self) -> None:
        resultat = verifier_compatibilite(
            self.declaration,
            ("whisper-large-v3.q8_0.gguf",),
            lecteur_entete_gguf=lecteur_gguf_de(octets_gguf("qwen3-asr")),
        )
        refus = self.assertRefus(resultat, RAISON_FAMILLE_HORS_PERIMETRE)
        self.assertEqual(refus.famille, "qwen3-asr")

        resultat = verifier_compatibilite(
            self.declaration,
            ("qwen3-asr.q8_0.gguf",),
            lecteur_entete_gguf=lecteur_gguf_de(octets_gguf("whisper")),
        )
        self.assertAccepte(resultat, "whisper")
        self.assertEqual(resultat.fichiers, ("qwen3-asr.q8_0.gguf",))

    def test_architectures_non_verifiees_refusees(self) -> None:
        for architecture in ("qwen3-asr", "parakeet-tdt", "llama"):
            with self.subTest(architecture=architecture):
                resultat = verifier_compatibilite(
                    self.declaration,
                    ("modele.gguf",),
                    lecteur_entete_gguf=lecteur_gguf_de(octets_gguf(architecture)),
                )
                refus = self.assertRefus(resultat, RAISON_FAMILLE_HORS_PERIMETRE)
                self.assertEqual(refus.famille, architecture)
                self.assertIn("non vérifiées", refus.message)

    def test_production_transcribe_whisper_reste_refusee(self) -> None:
        resultat = verifier_compatibilite(
            DECLARATION_TRANSCRIBE_CPP,
            FICHIERS_GGUF,
            fichier_gguf="modele-q8_0.gguf",
            lecteur_entete_gguf=lecteur_gguf_de(octets_gguf()),
        )
        refus = self.assertRefus(resultat, RAISON_FAMILLE_NON_QUALIFIEE)
        self.assertEqual(refus.famille, "whisper")
        self.assertEqual(refus.fichiers_manquants, ())

    def test_entete_absent_non_lu_ou_illisible_refuse(self) -> None:
        sans_architecture = entete_gguf(("general.name", "string", "test"))
        resultat = verifier_compatibilite(
            self.declaration,
            ("modele.gguf",),
            lecteur_entete_gguf=lecteur_gguf_de(sans_architecture),
        )
        self.assertRefus(resultat, RAISON_ARCHITECTURE_GGUF_ABSENTE)

        resultat = verifier_compatibilite(self.declaration, ("modele.gguf",))
        self.assertRefus(resultat, RAISON_EN_TETE_GGUF_NON_LU)

        resultat = verifier_compatibilite(
            self.declaration,
            ("modele.gguf",),
            lecteur_entete_gguf=lecteur_gguf_de(b"GGML" + b"\x00" * 32),
        )
        self.assertRefus(resultat, RAISON_EN_TETE_GGUF_ILLISIBLE)

        with self.assertRaises(TypeError):
            verifier_compatibilite(
                self.declaration,
                ("modele.gguf",),
                lecteur_entete_gguf=lambda nom: "whisper",
            )

    def test_noms_refuses_avant_tout_appel_au_lecteur(self) -> None:
        journal: list[str] = []
        resultat = verifier_compatibilite(
            self.declaration,
            (*FICHIERS_GGUF, "../evil.gguf"),
            fichier_gguf="modele-q8_0.gguf",
            lecteur_entete_gguf=lecteur_gguf_de(octets_gguf(), journal),
        )
        self.assertRefus(resultat, RAISON_NOM_FICHIER_REFUSE)
        self.assertEqual(journal, [])

    def test_parametres_gguf_refuses_pour_une_autre_regle(self) -> None:
        with self.assertRaises(TypeError):
            verifier_compatibilite(
                DECLARATION_FASTER_WHISPER,
                FICHIERS_CTRANSLATE2,
                fichier_gguf="modele.gguf",
                lecteur_entete_gguf=lecteur_gguf_de(octets_gguf()),
            )
        with self.assertRaises(TypeError):
            verifier_compatibilite(
                DECLARATION_FASTER_WHISPER,
                FICHIERS_CTRANSLATE2,
                configurations=CONTENUS_CTRANSLATE2,
                lecteur_entete_gguf=lecteur_gguf_de(octets_gguf()),
            )


class EntreesRefuseesTest(AssertionsCompatibilite):
    def setUp(self) -> None:
        self.declaration = declaration_synthetique()

    def test_noms_de_fichiers_dangereux_refuses(self) -> None:
        for nom in ("../evil.bin", "/etc/passwd", "a\\b.bin", "a/../b.bin", "", "a//b"):
            with self.subTest(nom=nom):
                fichiers = (*FICHIERS_CTRANSLATE2, nom)
                resultat = verifier_compatibilite(self.declaration, fichiers)
                self.assertRefus(resultat, RAISON_NOM_FICHIER_REFUSE)

    def test_entrees_non_textuelles_refusees(self) -> None:
        resultat = verifier_compatibilite(
            self.declaration,
            (1, 2),  # type: ignore[arg-type]
        )
        self.assertRefus(resultat, RAISON_NOM_FICHIER_REFUSE)
        with self.assertRaises(TypeError):
            verifier_compatibilite(
                self.declaration,
                "model.bin",  # type: ignore[arg-type]
            )
        with self.assertRaises(TypeError):
            verifier_compatibilite(
                self.declaration,
                ("model.bin",),
                configurations=[],  # type: ignore[arg-type]
            )
        with self.assertRaises(TypeError):
            verifier_compatibilite(
                "faster-whisper",  # type: ignore[arg-type]
                ("model.bin",),
            )

    def test_regle_non_implementee(self) -> None:
        with self.assertRaises(RegleCompatibiliteInconnue):
            verifier_compatibilite(DECLARATION_FACTICE, ("modele.gguf",))


class QualificationProductionTest(AssertionsCompatibilite):
    def test_familles_de_production_restent_non_qualifiees(self) -> None:
        for declaration in declarations_fournies():
            for famille in declaration.familles:
                with self.subTest(
                    moteur=declaration.identifiant, famille=famille.identifiant
                ):
                    self.assertFalse(famille.qualifiee)
                    self.assertIsNone(famille.duree_native)


class ResultatCompatibiliteTest(unittest.TestCase):
    def test_resultat_incoherent_refuse(self) -> None:
        with self.assertRaises(ResultatCompatibiliteInvalide):
            ResultatCompatibilite(
                accepte=True,
                famille="whisper",
                fichiers=("config.json",),
                raison=RAISON_FICHIERS_MANQUANTS,
                message="incohérent",
            )
        with self.assertRaises(ResultatCompatibiliteInvalide):
            ResultatCompatibilite(
                accepte=True,
                famille="whisper",
                fichiers=(),
                raison=None,
                message="sans fichier",
            )
        with self.assertRaises(ResultatCompatibiliteInvalide):
            ResultatCompatibilite(
                accepte=False,
                famille=None,
                fichiers=("config.json",),
                raison=RAISON_FICHIERS_MANQUANTS,
                message="refus avec fichier",
            )
        with self.assertRaises(ResultatCompatibiliteInvalide):
            ResultatCompatibilite(
                accepte=False,
                famille=None,
                fichiers=(),
                raison="raison-inventee",
                message="raison inconnue",
            )
        with self.assertRaises(ResultatCompatibiliteInvalide):
            ResultatCompatibilite(
                accepte=False,
                famille=None,
                fichiers=(),
                raison=RAISON_FICHIERS_MANQUANTS,
                message="   ",
            )

    def test_raisons_de_refus_uniques(self) -> None:
        self.assertEqual(len(RAISONS_REFUS), len(set(RAISONS_REFUS)))


if __name__ == "__main__":
    unittest.main()
