"""Tests du schéma des grilles : génération déterministe, décodage, validation.

Tâche 1.2 du change `ajouter-bench-extraction` : le module `schema_grilles`
est exercé sans réseau, sans écriture dans le dépôt et sans moteur. La
grille de test, écrite dans un dossier temporaire, couvre les quatre types
de cases du tableau D2 (texte, liste de textes, composée, liste composée)
avec une sous-case liste. Le schéma attendu est comparé littéralement au
tableau D2 ; la sérialisation est contrôlée octet pour octet ; chaque motif
de refus (case manquante, clé inconnue, mauvais type, null non admis,
liste vide, clé dupliquée, JSON indécodable) est nommé et distinct.
"""

from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

from transcription_bench.grilles import GRID_DIR_NAME, RESERVED_KEY, read_grid
from transcription_bench.schema_grilles import (
    DECODE_DUPLICATE_KEY,
    DECODE_JSON_INVALID,
    REASON_EMPTY_LIST,
    REASON_MISSING_KEY,
    REASON_NULL_NOT_ALLOWED,
    REASON_UNKNOWN_KEY,
    REASON_WRONG_TYPE,
    decode_output,
    grid_schema,
    schema_to_json,
    validate_output,
)

#: Grille de test : les quatre types de cases du tableau D2, avec une
#: sous-case liste (`posologie`) et une composée sans consigne propre.
GRILLE_CONSULTATION = """\
# Consultation de test

Consignes : n'extraire que ce qui est dit.

## Qui ?
Personnes présentes et leur rôle.

## Symptômes déclarés ?
Liste. Un symptôme par entrée.

## Constantes ?
### Tension
### Poids

## Prescription ?
Liste.
### Médicament
### Posologie
Liste. Une prise par entrée.

## Prise en charge ?
Orientation, conseils, suivi prévu.
"""

#: Clés de la grille dans l'ordre, `autres_informations` en dernier.
CLES_ATTENDUES = [
    "qui",
    "symptomes_declares",
    "constantes",
    "prescription",
    "prise_en_charge",
    RESERVED_KEY,
]

#: Schéma attendu, écrit littéralement selon le tableau D2 du design.
SCHEMA_ATTENDU = {
    "type": "object",
    "properties": {
        "qui": {"anyOf": [{"type": "string"}, {"type": "null"}]},
        "symptomes_declares": {
            "anyOf": [
                {"type": "array", "items": {"type": "string"}, "minItems": 1},
                {"type": "null"},
            ]
        },
        "constantes": {
            "anyOf": [
                {
                    "type": "object",
                    "properties": {
                        "tension": {"anyOf": [{"type": "string"}, {"type": "null"}]},
                        "poids": {"anyOf": [{"type": "string"}, {"type": "null"}]},
                    },
                    "required": ["tension", "poids"],
                    "additionalProperties": False,
                },
                {"type": "null"},
            ]
        },
        "prescription": {
            "anyOf": [
                {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "medicament": {
                                "anyOf": [{"type": "string"}, {"type": "null"}]
                            },
                            "posologie": {
                                "anyOf": [
                                    {
                                        "type": "array",
                                        "items": {"type": "string"},
                                        "minItems": 1,
                                    },
                                    {"type": "null"},
                                ]
                            },
                        },
                        "required": ["medicament", "posologie"],
                        "additionalProperties": False,
                    },
                    "minItems": 1,
                },
                {"type": "null"},
            ]
        },
        "prise_en_charge": {"anyOf": [{"type": "string"}, {"type": "null"}]},
        "autres_informations": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "intitule": {"type": "string"},
                    "valeur": {"type": "string"},
                },
                "required": ["intitule", "valeur"],
                "additionalProperties": False,
            },
        },
    },
    "required": CLES_ATTENDUES,
    "additionalProperties": False,
}

#: Sortie complète et conforme à la grille de test.
SORTIE_COMPLETE = {
    "qui": "Le patient, accompagné de son épouse.",
    "symptomes_declares": [
        "fatigue depuis trois jours",
        "douleur abdominale le matin",
    ],
    "constantes": {"tension": "12/8 dite par le patient", "poids": None},
    "prescription": [
        {"medicament": "paracétamol", "posologie": ["un le matin", "un le soir"]}
    ],
    "prise_en_charge": "Revenir dans une semaine si les symptômes persistent.",
    "autres_informations": [
        {"intitule": "vaccination", "valeur": "grippe faite en octobre"}
    ],
}

#: Cases de la grille, sans la section réservée.
CASES_GRILLE = [cle for cle in CLES_ATTENDUES if cle != RESERVED_KEY]

#: Schéma D2 de la grille d'exemple `consultation-generale`, octet pour octet
#: (`indent=2`) : texte, liste, composée, liste composée, puis autres informations.
SCHEMA_CONSULTATION_GENERALE = """{
  "type": "object",
  "properties": {
    "qui": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ]
    },
    "quand": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ]
    },
    "motif_de_consultation": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ]
    },
    "symptomes_declares": {
      "anyOf": [
        {
          "type": "array",
          "items": {
            "type": "string"
          },
          "minItems": 1
        },
        {
          "type": "null"
        }
      ]
    },
    "examens_pratiques": {
      "anyOf": [
        {
          "type": "array",
          "items": {
            "type": "string"
          },
          "minItems": 1
        },
        {
          "type": "null"
        }
      ]
    },
    "doute_restant": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ]
    },
    "prescription": {
      "anyOf": [
        {
          "type": "array",
          "items": {
            "type": "object",
            "properties": {
              "medicament": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ]
              },
              "posologie": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ]
              },
              "duree": {
                "anyOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ]
              }
            },
            "required": [
              "medicament",
              "posologie",
              "duree"
            ],
            "additionalProperties": false
          },
          "minItems": 1
        },
        {
          "type": "null"
        }
      ]
    },
    "prise_en_charge": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ]
    },
    "autres_informations": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "intitule": {
            "type": "string"
          },
          "valeur": {
            "type": "string"
          }
        },
        "required": [
          "intitule",
          "valeur"
        ],
        "additionalProperties": false
      }
    }
  },
  "required": [
    "qui",
    "quand",
    "motif_de_consultation",
    "symptomes_declares",
    "examens_pratiques",
    "doute_restant",
    "prescription",
    "prise_en_charge",
    "autres_informations"
  ],
  "additionalProperties": false
}"""


def sortie_complete() -> dict:
    """Copie fraîche de la sortie complète, librement mutable par le test."""
    return copy.deepcopy(SORTIE_COMPLETE)


class SocleSchemaGrilles(unittest.TestCase):
    """Racine temporaire et helpers : aucune écriture dans le dépôt."""

    def setUp(self) -> None:
        temporaire = tempfile.TemporaryDirectory()
        self.addCleanup(temporaire.cleanup)
        self.racine = Path(temporaire.name)
        self.dossier = self.racine / GRID_DIR_NAME

    def ecrire(self, texte: str, nom: str = "exemple") -> Path:
        """Écrit une grille de test dans le dossier temporaire `grilles/`."""
        self.dossier.mkdir(exist_ok=True)
        chemin = self.dossier / f"{nom}.md"
        chemin.write_text(texte, encoding="utf-8")
        return chemin

    def lire(self, nom: str = "exemple"):
        """Lit la grille écrite par `ecrire`, sous la racine temporaire."""
        return read_grid(nom, self.racine)

    def ecrire_consultation(self):
        """Écrit la grille de consultation et la rend interprétée."""
        self.ecrire(GRILLE_CONSULTATION, "consultation")
        return self.lire("consultation")


class GenerationSchemaTest(SocleSchemaGrilles):
    """Génération déterministe du schéma D2 pour la grille de consultation."""

    def test_schema_attendu_litteral(self) -> None:
        grille = self.ecrire_consultation()

        self.assertEqual(grid_schema(grille), SCHEMA_ATTENDU)

    def test_schema_de_la_grille_d_exemple_octet_pour_octet(self) -> None:
        grille = read_grid("consultation-generale")

        self.assertTrue(grille.valid)
        self.assertEqual(
            schema_to_json(grid_schema(grille)), SCHEMA_CONSULTATION_GENERALE
        )

    def test_ordre_des_cles_suivant_la_grille(self) -> None:
        schema = grid_schema(self.ecrire_consultation())

        self.assertEqual(list(schema["properties"]), CLES_ATTENDUES)
        self.assertEqual(schema["required"], CLES_ATTENDUES)
        constantes = schema["properties"]["constantes"]["anyOf"][0]
        self.assertEqual(list(constantes["properties"]), ["tension", "poids"])
        self.assertEqual(constantes["required"], ["tension", "poids"])
        entree = schema["properties"]["prescription"]["anyOf"][0]["items"]
        self.assertEqual(list(entree["properties"]), ["medicament", "posologie"])
        self.assertEqual(entree["required"], ["medicament", "posologie"])

    def test_autres_informations_derniere_et_non_nullable(self) -> None:
        schema = grid_schema(self.ecrire_consultation())
        autres = schema["properties"][RESERVED_KEY]

        self.assertEqual(list(schema["properties"])[-1], RESERVED_KEY)
        self.assertEqual(schema["required"][-1], RESERVED_KEY)
        # Tableau non « null-able », liste vide admise (aucun `minItems`).
        self.assertNotIn("anyOf", autres)
        self.assertNotIn("minItems", autres)
        # Les entrées non plus : deux chaînes requises, directes.
        entree = autres["items"]
        self.assertNotIn("anyOf", entree)
        self.assertEqual(
            entree["properties"],
            {"intitule": {"type": "string"}, "valeur": {"type": "string"}},
        )

    def test_deux_generations_identiques_octet_pour_octet(self) -> None:
        grille = self.ecrire_consultation()

        premiere = schema_to_json(grid_schema(grille))
        seconde = schema_to_json(grid_schema(grille))
        self.assertEqual(premiere, seconde)
        # Une relecture du fichier produit le même schéma, même sérialisation.
        relue = self.lire("consultation")
        self.assertEqual(schema_to_json(grid_schema(relue)), premiere)
        # La sérialisation reste du JSON valide relisant le schéma exact.
        self.assertEqual(json.loads(premiere), grid_schema(grille))

    def test_grille_invalide_sans_schema(self) -> None:
        self.ecrire("# Titre\n\n## ???\n", "invalide")
        grille = self.lire("invalide")

        self.assertFalse(grille.valid)
        with self.assertRaises(ValueError):
            grid_schema(grille)


class SortiesConformesTest(SocleSchemaGrilles):
    """Sorties conformes : complète, nul partout, vides, autres informations."""

    def setUp(self) -> None:
        super().setUp()
        self.schema = grid_schema(self.ecrire_consultation())

    def test_sortie_complete(self) -> None:
        verdict = validate_output(sortie_complete(), self.schema)

        self.assertTrue(verdict.valid)
        self.assertIsNone(verdict.issue)

    def test_null_partout_avec_section_vide(self) -> None:
        sortie = {cle: None for cle in CASES_GRILLE}
        sortie[RESERVED_KEY] = []

        self.assertTrue(validate_output(sortie, self.schema).valid)

    def test_section_autres_informations_vide(self) -> None:
        sortie = sortie_complete()
        sortie[RESERVED_KEY] = []

        self.assertTrue(validate_output(sortie, self.schema).valid)

    def test_chaines_vides_conformes(self) -> None:
        # Une chaîne vide est conforme : elle est distincte de « non mentionné ».
        sortie = sortie_complete()
        sortie["qui"] = ""
        sortie[RESERVED_KEY] = [{"intitule": "", "valeur": ""}]

        self.assertTrue(validate_output(sortie, self.schema).valid)

    def test_entree_autres_informations_seule(self) -> None:
        sortie = {cle: None for cle in CASES_GRILLE}
        sortie[RESERVED_KEY] = [
            {"intitule": "tabagisme", "valeur": "arrêté il y a deux ans"}
        ]

        self.assertTrue(validate_output(sortie, self.schema).valid)


class SortiesNonConformesTest(SocleSchemaGrilles):
    """Sorties non conformes : la première erreur, son chemin et son motif."""

    def setUp(self) -> None:
        super().setUp()
        self.schema = grid_schema(self.ecrire_consultation())

    def assert_issue(self, sortie: object, chemin: str, motif: str):
        """La sortie doit être refusée avec exactement ce chemin et ce motif."""
        verdict = validate_output(sortie, self.schema)
        self.assertFalse(verdict.valid)
        self.assertIsNotNone(verdict.issue)
        assert verdict.issue is not None
        self.assertEqual(verdict.issue.path, chemin)
        self.assertEqual(verdict.issue.reason, motif)
        return verdict.issue

    def test_case_manquante(self) -> None:
        sortie = sortie_complete()
        del sortie["qui"]

        issue = self.assert_issue(sortie, "$.qui", REASON_MISSING_KEY)
        self.assertIn("'qui'", issue.message)

    def test_cle_inconnue(self) -> None:
        sortie = sortie_complete()
        sortie["fumeur"] = "oui"

        issue = self.assert_issue(sortie, "$.fumeur", REASON_UNKNOWN_KEY)
        self.assertIn("'fumeur'", issue.message)

    def test_mauvais_type_sur_chaque_type_de_case(self) -> None:
        cas = (
            ("qui", 5, "$.qui"),
            ("qui", True, "$.qui"),
            ("qui", ["a"], "$.qui"),
            ("qui", {"a": 1}, "$.qui"),
            ("symptomes_declares", "fatigue", "$.symptomes_declares"),
            ("constantes", "12/8", "$.constantes"),
            ("prescription", {"medicament": "x", "posologie": None}, "$.prescription"),
        )
        for cle, valeur, chemin in cas:
            with self.subTest(cle=cle, valeur=valeur):
                sortie = sortie_complete()
                sortie[cle] = valeur

                issue = self.assert_issue(sortie, chemin, REASON_WRONG_TYPE)
                self.assertIn("attendu", issue.message)

    def test_null_dans_autres_informations(self) -> None:
        sortie = sortie_complete()
        sortie[RESERVED_KEY] = None

        issue = self.assert_issue(
            sortie, "$.autres_informations", REASON_NULL_NOT_ALLOWED
        )
        self.assertIn("liste attendu", issue.message)

    def test_null_dans_une_entree_d_autres_informations(self) -> None:
        sortie = sortie_complete()
        sortie[RESERVED_KEY] = [None]

        issue = self.assert_issue(
            sortie, "$.autres_informations[0]", REASON_NULL_NOT_ALLOWED
        )
        self.assertIn("objet attendu", issue.message)

        sortie = sortie_complete()
        sortie[RESERVED_KEY] = [{"intitule": None, "valeur": "x"}]

        issue = self.assert_issue(
            sortie, "$.autres_informations[0].intitule", REASON_NULL_NOT_ALLOWED
        )
        self.assertIn("texte attendu", issue.message)

    def test_liste_vide_d_une_case_liste(self) -> None:
        premiere = sortie_complete()
        premiere["symptomes_declares"] = []
        seconde = sortie_complete()
        seconde["prescription"] = []
        troisieme = sortie_complete()
        troisieme["prescription"][0]["posologie"] = []
        cas = (
            (premiere, "$.symptomes_declares"),
            (seconde, "$.prescription"),
            (troisieme, "$.prescription[0].posologie"),
        )
        for sortie, chemin in cas:
            with self.subTest(chemin=chemin):
                issue = self.assert_issue(sortie, chemin, REASON_EMPTY_LIST)
                self.assertIn("liste vide", issue.message)

    def test_composee_sous_case_manquante(self) -> None:
        sortie = sortie_complete()
        del sortie["constantes"]["poids"]

        issue = self.assert_issue(sortie, "$.constantes.poids", REASON_MISSING_KEY)
        self.assertIn("'poids'", issue.message)

    def test_composee_cle_inconnue(self) -> None:
        sortie = sortie_complete()
        sortie["constantes"]["douleur"] = "oui"

        issue = self.assert_issue(sortie, "$.constantes.douleur", REASON_UNKNOWN_KEY)
        self.assertIn("'douleur'", issue.message)

    def test_composee_mauvais_type_de_sous_case(self) -> None:
        sortie = sortie_complete()
        sortie["constantes"]["tension"] = 12

        issue = self.assert_issue(sortie, "$.constantes.tension", REASON_WRONG_TYPE)
        self.assertIn("texte ou null", issue.message)

    def test_profondeur_objet_inattendu(self) -> None:
        # Un objet imbriqué là où un texte est attendu : refus nommé, même
        # profond (le sous-ensemble est récursif borné).
        sortie = sortie_complete()
        sortie["prescription"] = [
            {"medicament": {"profond": {"encore": 1}}, "posologie": None}
        ]

        issue = self.assert_issue(
            sortie, "$.prescription[0].medicament", REASON_WRONG_TYPE
        )
        self.assertIn("reçu objet", issue.message)

    def test_entree_autres_informations_incomplete(self) -> None:
        sortie = sortie_complete()
        sortie[RESERVED_KEY] = [{"valeur": "sans intitulé"}]

        issue = self.assert_issue(
            sortie, "$.autres_informations[0].intitule", REASON_MISSING_KEY
        )

        sortie = sortie_complete()
        sortie[RESERVED_KEY] = [
            {"intitule": "a", "valeur": "b", "extra": "c"}
        ]

        issue = self.assert_issue(
            sortie, "$.autres_informations[0].extra", REASON_UNKNOWN_KEY
        )

    def test_racine_non_objet(self) -> None:
        for valeur in (["x"], "texte", None):
            with self.subTest(valeur=valeur):
                verdict = validate_output(valeur, self.schema)
                self.assertFalse(verdict.valid)
                self.assertIsNotNone(verdict.issue)
                assert verdict.issue is not None
                self.assertEqual(verdict.issue.path, "$")
                self.assertIn(
                    verdict.issue.reason,
                    (REASON_WRONG_TYPE, REASON_NULL_NOT_ALLOWED),
                )


class DecodageSortieTest(SocleSchemaGrilles):
    """Décodage strict : doublons refusés, syntaxe et doublons distingués."""

    def setUp(self) -> None:
        super().setUp()
        self.schema = grid_schema(self.ecrire_consultation())

    def test_sortie_valide_decodee_puis_validee(self) -> None:
        brut = json.dumps(sortie_complete(), ensure_ascii=False)

        decodage = decode_output(brut)
        self.assertTrue(decodage.ok)
        self.assertEqual(decodage.value, sortie_complete())

        verdict = validate_output(decodage.value, self.schema)
        self.assertTrue(verdict.valid)

    def test_cle_dupliquee_premier_niveau_refusee(self) -> None:
        brut = (
            '{"qui": "a", "qui": "b", "symptomes_declares": null, '
            '"constantes": null, "prescription": null, "prise_en_charge": null, '
            '"autres_informations": []}'
        )

        resultat = decode_output(brut)

        self.assertFalse(resultat.ok)
        self.assertIsNone(resultat.value)
        self.assertEqual(resultat.reason, DECODE_DUPLICATE_KEY)
        self.assertIn("'qui'", resultat.message)

    def test_cle_dupliquee_imbriquee_refusee(self) -> None:
        cas = (
            (
                '{"constantes": {"tension": "12", "tension": "8"}}',
                "tension",
            ),
            (
                '{"autres_informations": '
                '[{"intitule": "a", "valeur": "b", "intitule": "c"}]}',
                "intitule",
            ),
        )
        for brut, cle in cas:
            with self.subTest(cle=cle):
                resultat = decode_output(brut)

                self.assertFalse(resultat.ok)
                self.assertEqual(resultat.reason, DECODE_DUPLICATE_KEY)
                self.assertIn(repr(cle), resultat.message)

    def test_json_indecodable_refuse(self) -> None:
        for brut in ('{"qui": ', "", "pas du tout", "[1, 2,"):
            with self.subTest(brut=brut):
                resultat = decode_output(brut)

                self.assertFalse(resultat.ok)
                self.assertIsNone(resultat.value)
                self.assertEqual(resultat.reason, DECODE_JSON_INVALID)
                self.assertIn("JSON indécodable", resultat.message)
                self.assertIn("ligne", resultat.message)

    def test_motifs_de_decodage_distincts_et_nommes(self) -> None:
        # Les deux refus du décodage ont chacun leur identifiant stable et
        # leur vocabulaire propre, distincts l'un de l'autre.
        self.assertNotEqual(DECODE_JSON_INVALID, DECODE_DUPLICATE_KEY)

        doublon = decode_output('{"a": 1, "a": 2}')
        syntaxe = decode_output("{")
        self.assertEqual(doublon.reason, DECODE_DUPLICATE_KEY)
        self.assertEqual(syntaxe.reason, DECODE_JSON_INVALID)
        self.assertIn("clé dupliquée", doublon.message)
        self.assertIn("JSON indécodable", syntaxe.message)

    def test_recursion_trop_profonde_refusee_sans_exception(self) -> None:
        brut = "[" * 100_000 + "]" * 100_000

        resultat = decode_output(brut)

        self.assertFalse(resultat.ok)
        self.assertIsNone(resultat.value)
        self.assertEqual(resultat.reason, DECODE_JSON_INVALID)
        self.assertIn("imbriquée", resultat.message)

    def test_constantes_hors_json_strict_refusees(self) -> None:
        cas = (
            ('{"a": NaN}', "NaN"),
            ("Infinity", "Infinity"),
            ("-Infinity", "-Infinity"),
            ('{"a": [1, -Infinity]}', "-Infinity"),
        )
        for brut, constante in cas:
            with self.subTest(brut=brut):
                resultat = decode_output(brut)

                self.assertFalse(resultat.ok)
                self.assertIsNone(resultat.value)
                self.assertEqual(resultat.reason, DECODE_JSON_INVALID)
                self.assertIn(f"constante {constante} non admise", resultat.message)

    def test_entier_hors_limites_refuse_sans_exception(self) -> None:
        # Python refuse les entiers de plusieurs milliers de chiffres : le
        # décodage reste total et rend un verdict, jamais une exception.
        brut = '{"a": ' + "9" * 5000 + "}"

        resultat = decode_output(brut)

        self.assertFalse(resultat.ok)
        self.assertIsNone(resultat.value)
        self.assertEqual(resultat.reason, DECODE_JSON_INVALID)
        self.assertIn("limites", resultat.message)


class NullPartoutSaufAutresTest(SocleSchemaGrilles):
    """« null accepté partout sauf autres_informations », type par type."""

    def setUp(self) -> None:
        super().setUp()
        self.schema = grid_schema(self.ecrire_consultation())

    def motif_de_refus(self, sortie: object) -> str:
        """Motif de la non-conformité, pour un refus attendu."""
        verdict = validate_output(sortie, self.schema)
        self.assertFalse(verdict.valid)
        self.assertIsNotNone(verdict.issue)
        assert verdict.issue is not None
        return verdict.issue.reason

    def test_null_admis_sur_chaque_type_de_case(self) -> None:
        # texte, liste de textes, composée, liste composée, texte encore.
        for cle in CASES_GRILLE:
            with self.subTest(cle=cle):
                sortie = sortie_complete()
                sortie[cle] = None

                self.assertTrue(validate_output(sortie, self.schema).valid)

    def test_null_admis_sur_les_sous_cases(self) -> None:
        sortie = sortie_complete()
        sortie["constantes"] = {"tension": None, "poids": None}
        with self.subTest(cle="sous-cases d'une composée"):
            self.assertTrue(validate_output(sortie, self.schema).valid)

        sortie = sortie_complete()
        sortie["prescription"][0]["posologie"] = None
        with self.subTest(cle="sous-case liste d'une liste composée"):
            self.assertTrue(validate_output(sortie, self.schema).valid)

        sortie = sortie_complete()
        sortie["prescription"] = [{"medicament": None, "posologie": None}]
        with self.subTest(cle="toutes les sous-cases d'une entrée"):
            self.assertTrue(validate_output(sortie, self.schema).valid)

    def test_null_partout_a_la_fois(self) -> None:
        sortie = {cle: None for cle in CASES_GRILLE}
        sortie[RESERVED_KEY] = []

        self.assertTrue(validate_output(sortie, self.schema).valid)

    def test_null_refuse_sur_autres_informations(self) -> None:
        sortie = sortie_complete()
        sortie[RESERVED_KEY] = None
        with self.subTest(cle="la section elle-même"):
            self.assertEqual(self.motif_de_refus(sortie), REASON_NULL_NOT_ALLOWED)

        sortie = sortie_complete()
        sortie[RESERVED_KEY] = [None]
        with self.subTest(cle="une entrée"):
            self.assertEqual(self.motif_de_refus(sortie), REASON_NULL_NOT_ALLOWED)

        sortie = sortie_complete()
        sortie[RESERVED_KEY] = [{"intitule": "a", "valeur": None}]
        with self.subTest(cle="un champ d'une entrée"):
            self.assertEqual(self.motif_de_refus(sortie), REASON_NULL_NOT_ALLOWED)


if __name__ == "__main__":
    unittest.main()
