"""Tests du lecteur partiel d'en-tête GGUF, sans fichier réel ni réseau.

Les en-têtes sont assemblés localement par `tests.entetes_gguf_de_test` selon la
spécification ggml (versions 2 et 3, petit et grand boutisme). Aucun poids,
aucun tenseur et aucun accès distant : seules les métadonnées utiles à
`general.architecture` sont lues.
"""

from __future__ import annotations

import struct
import unittest

from tests.entetes_gguf_de_test import entete_gguf, source_de
from transcription_bench.gguf import (
    OCTETS_MAX_ENTETE,
    PROFONDEUR_MAX_TABLEAUX,
    TAILLE_BLOC,
    EnteteGGUF,
    EnteteGGUFInvalide,
    lire_entete_gguf,
)

ARCHITECTURE = ("general.architecture", "string", "whisper")


def metadonnee_brute(
    cle: bytes, type_valeur: int, valeur: bytes, ordre: str = "<"
) -> bytes:
    """Paire clé/valeur assemblée à la main, pour les cas volontairement malformés."""
    return (
        struct.pack(ordre + "Q", len(cle))
        + cle
        + struct.pack(ordre + "I", type_valeur)
        + valeur
    )


def entete_avec_metadonnee_brute(*metadonnees: bytes) -> bytes:
    return entete_gguf(nombre_metadonnees=len(metadonnees)) + b"".join(metadonnees)


class LecteurEnteteGGUFTest(unittest.TestCase):
    def test_entete_minimal_extrait_l_architecture(self) -> None:
        octets = entete_gguf(ARCHITECTURE)
        # Octets officiels : magie `GGUF` puis version 3 en petit boutisme.
        self.assertEqual(octets[:8], b"GGUF\x03\x00\x00\x00")
        entete = lire_entete_gguf(source_de(octets))
        self.assertEqual(entete.architecture, "whisper")
        self.assertEqual(entete.version, 3)
        self.assertEqual(entete.boutisme, "petit")
        self.assertEqual(entete.octets_lus, len(octets))

    def test_lecteur_s_arrete_a_l_architecture(self) -> None:
        # Les octets qui suivent les métadonnées ne sont jamais lus : ils
        # représentent les tenseurs, que ce lecteur ne valide pas.
        debut = entete_gguf(ARCHITECTURE)
        octets = debut + b"\x00" * 4096
        demandes: list[int] = []
        entete = lire_entete_gguf(source_de(octets, demandes=demandes))
        self.assertEqual(entete.architecture, "whisper")
        self.assertEqual(entete.octets_lus, len(debut))
        self.assertLess(entete.octets_lus, len(octets))
        self.assertTrue(all(0 < demande <= TAILLE_BLOC for demande in demandes))
        self.assertEqual(demandes[0], 4)

    def test_metadonnees_variees_avant_l_architecture(self) -> None:
        octets = entete_gguf(
            ("general.name", "string", "Whisper de test"),
            ("general.file_type", "u32", 2),
            ("whisper.n_vocab", "i32", 51866),
            ("whisper.n_text_layer", "u8", 32),
            ("whisper.flag", "bool", True),
            ("whisper.score", "f32", 0.25),
            ("whisper.offset", "i64", -3),
            ("whisper.compteur", "u64", 2**40),
            ("whisper.marge", "f64", 1.5),
            ("whisper.petit", "i8", -1),
            ("whisper.moyen", "u16", 65535),
            ("whisper.moyen_signe", "i16", -32768),
            ("whisper.tokens", "array", ("string", ["<|debut|>", "<|fin|>", ""])),
            ("whisper.identifiants", "array", ("u32", [1, 2, 3])),
            (
                "whisper.tableaux",
                "array",
                ("array", [("u32", [1, 2]), ("u32", [])]),
            ),
            ARCHITECTURE,
        )
        entete = lire_entete_gguf(source_de(octets))
        self.assertEqual(entete.architecture, "whisper")
        self.assertEqual(entete.octets_lus, len(octets))

    def test_tableau_volumineux_accepte_sans_plafond_invente(self) -> None:
        # Un vocabulaire réel dépasse largement les petites bornes de nœuds :
        # 20 000 jetons doivent passer sans refus.
        jetons = [f"<|jeton-{index}|>" for index in range(20_000)]
        octets = entete_gguf(
            ("tokenizer.ggml.tokens", "array", ("string", jetons)),
            ARCHITECTURE,
        )
        self.assertGreater(len(octets), 200_000)
        self.assertLess(len(octets), OCTETS_MAX_ENTETE)
        entete = lire_entete_gguf(source_de(octets))
        self.assertEqual(entete.architecture, "whisper")

    def test_boutismes_et_versions_acceptes(self) -> None:
        cas = (
            ("v2 petit boutisme", dict(version=2, boutisme="petit"), "petit"),
            ("v2 grand boutisme", dict(version=2, boutisme="grand"), "grand"),
            ("v3 petit boutisme", dict(version=3, boutisme="petit"), "petit"),
            ("v3 grand boutisme", dict(version=3, boutisme="grand"), "grand"),
        )
        for etiquette, options, boutisme in cas:
            with self.subTest(cas=etiquette):
                octets = entete_gguf(ARCHITECTURE, **options)
                # La magie reste `GGUF` dans tous les cas ; c'est la version qui
                # porte le boutisme.
                self.assertEqual(octets[:4], b"GGUF")
                entete = lire_entete_gguf(source_de(octets))
                self.assertEqual(entete.architecture, "whisper")
                self.assertEqual(entete.boutisme, boutisme)
                self.assertEqual(entete.version, options["version"])

    def test_entete_standard_big_endian_accepte(self) -> None:
        # Reproduction des octets officiels, écrits à la main : magie `GGUF`,
        # version 3 en grand boutisme (0x03000000 relu en petit boutisme), puis
        # une paire clé/valeur big-endian portant l'architecture.
        cle = b"general.architecture"
        valeur = b"whisper"
        octets = (
            b"GGUF"
            + struct.pack(">IQQ", 3, 0, 1)
            + struct.pack(">Q", len(cle))
            + cle
            + struct.pack(">I", 8)
            + struct.pack(">Q", len(valeur))
            + valeur
        )
        entete = lire_entete_gguf(source_de(octets))
        self.assertEqual(entete.version, 3)
        self.assertEqual(entete.boutisme, "grand")
        self.assertEqual(entete.architecture, "whisper")
        self.assertEqual(entete.octets_lus, len(octets))

    def test_magie_ou_version_invalide_refusee(self) -> None:
        cas_versions = (
            (0, "petit"),
            (1, "petit"),
            (1, "grand"),
            (4, "petit"),
            (4, "grand"),
            (0xFFFFFFFF, "petit"),
        )
        for version, boutisme in cas_versions:
            with self.subTest(version=version, boutisme=boutisme):
                octets = entete_gguf(
                    ARCHITECTURE, version=version, boutisme=boutisme
                )
                with self.assertRaises(EnteteGGUFInvalide):
                    lire_entete_gguf(source_de(octets))
        for magie in (b"GGML", b"FUGG", b"FOO!", b"\x00\x00\x00\x00"):
            with self.subTest(magie=magie):
                octets = entete_gguf(ARCHITECTURE, magie=magie)
                with self.assertRaises(EnteteGGUFInvalide):
                    lire_entete_gguf(source_de(octets))

    def test_flux_tronque_refuse(self) -> None:
        octets = entete_gguf(
            ("general.name", "string", "nom"), ARCHITECTURE
        )
        for coupe in (0, 2, 4, 9, 12, 20, len(octets) // 2, len(octets) - 1):
            with self.subTest(coupe=coupe):
                with self.assertRaises(EnteteGGUFInvalide):
                    lire_entete_gguf(source_de(octets[:coupe]))

    def test_architecture_absente_ou_invalide(self) -> None:
        sans_architecture = entete_gguf(("general.name", "string", "sans architecture"))
        entete = lire_entete_gguf(source_de(sans_architecture))
        self.assertIsNone(entete.architecture)
        self.assertEqual(entete.octets_lus, len(sans_architecture))

        cas = {
            "type entier": metadonnee_brute(
                b"general.architecture", 4, struct.pack("<I", 1)
            ),
            "chaîne vide": metadonnee_brute(
                b"general.architecture", 8, struct.pack("<Q", 0)
            ),
            "chaîne non UTF-8": metadonnee_brute(
                b"general.architecture",
                8,
                struct.pack("<Q", 2) + b"\xff\xfe",
            ),
        }
        for etiquette, metadonnee in cas.items():
            with self.subTest(cas=etiquette):
                with self.assertRaises(EnteteGGUFInvalide):
                    lire_entete_gguf(
                        source_de(entete_avec_metadonnee_brute(metadonnee))
                    )

    def test_cle_non_utf8_refusee(self) -> None:
        octets = entete_avec_metadonnee_brute(
            metadonnee_brute(b"\xff\xfe", 4, struct.pack("<I", 1))
        )
        with self.assertRaises(EnteteGGUFInvalide):
            lire_entete_gguf(source_de(octets))

    def test_lecture_episodique_acceptee(self) -> None:
        octets = entete_gguf(
            ("general.name", "string", "nom"), ARCHITECTURE
        )
        for pas_max in (1, 3, 7):
            with self.subTest(pas_max=pas_max):
                demandes: list[int] = []
                entete = lire_entete_gguf(
                    source_de(octets, demandes=demandes, pas_max=pas_max)
                )
                self.assertEqual(entete.architecture, "whisper")
                self.assertEqual(entete.octets_lus, len(octets))
                self.assertTrue(all(demande > 0 for demande in demandes))

    def test_budget_depasse_refuse(self) -> None:
        jetons = [f"<|jeton-{index}|>" for index in range(1000)]
        octets = entete_gguf(
            ("tokenizer.ggml.tokens", "array", ("string", jetons)),
            ARCHITECTURE,
        )
        demandes: list[int] = []
        with self.assertRaises(EnteteGGUFInvalide):
            lire_entete_gguf(
                source_de(octets, demandes=demandes), octets_max=256
            )
        self.assertTrue(all(0 < demande <= 256 for demande in demandes))

    def test_longueurs_gigantesques_refusees_sans_allocation(self) -> None:
        cas = {
            "chaîne de 1 Tio": metadonnee_brute(
                b"general.name", 8, struct.pack("<Q", 2**40)
            ),
            "tableau de scalaires gigantesque": metadonnee_brute(
                b"whisper.identifiants",
                9,
                struct.pack("<I", 4) + struct.pack("<Q", 2**40),
            ),
            "tableau de chaînes gigantesque": metadonnee_brute(
                b"whisper.tokens",
                9,
                struct.pack("<I", 8) + struct.pack("<Q", 2**40),
            ),
        }
        for etiquette, metadonnee in cas.items():
            with self.subTest(cas=etiquette):
                demandes: list[int] = []
                octets = entete_avec_metadonnee_brute(metadonnee)
                with self.assertRaises(EnteteGGUFInvalide):
                    lire_entete_gguf(source_de(octets, demandes=demandes))
                self.assertTrue(all(0 < demande <= TAILLE_BLOC for demande in demandes))

        # Un compteur de métadonnées impossible est refusé avant toute lecture.
        with self.subTest(cas="nombre de métadonnées impossible"):
            octets = entete_gguf(nombre_metadonnees=2**40)
            with self.assertRaises(EnteteGGUFInvalide):
                lire_entete_gguf(source_de(octets))

    def test_entrees_malformees_refusees(self) -> None:
        architecture_normale = metadonnee_brute(
            b"general.architecture", 8, struct.pack("<Q", 7) + b"whisper"
        )
        type_inconnu = metadonnee_brute(b"general.name", 13, b"")
        with self.subTest(cas="type inconnu"):
            octets = entete_avec_metadonnee_brute(type_inconnu, architecture_normale)
            with self.assertRaises(EnteteGGUFInvalide):
                lire_entete_gguf(source_de(octets))

        imbrique = ("string", ["a"])
        for _ in range(PROFONDEUR_MAX_TABLEAUX + 2):
            imbrique = ("array", [imbrique])
        with self.subTest(cas="tableaux trop imbriqués"):
            octets = entete_gguf(("whisper.tableaux", "array", imbrique), ARCHITECTURE)
            with self.assertRaises(EnteteGGUFInvalide):
                lire_entete_gguf(source_de(octets))

        with self.subTest(cas="lecteur non appelable"):
            with self.assertRaises(TypeError):
                lire_entete_gguf(None)  # type: ignore[arg-type]

        with self.subTest(cas="lecteur renvoyant du texte"):
            with self.assertRaises(EnteteGGUFInvalide):
                lire_entete_gguf(lambda nombre: "GGUF")

        with self.subTest(cas="lecteur renvoyant trop d'octets"):
            octets = entete_gguf(ARCHITECTURE)

            def trop(nombre: int) -> bytes:
                return octets[: nombre + 1]

            with self.assertRaises(EnteteGGUFInvalide):
                lire_entete_gguf(trop)

        with self.subTest(cas="bornes invalides"):
            with self.assertRaises(ValueError):
                lire_entete_gguf(source_de(entete_gguf(ARCHITECTURE)), octets_max=0)
            with self.assertRaises(ValueError):
                lire_entete_gguf(
                    source_de(entete_gguf(ARCHITECTURE)), taille_bloc=0
                )


class EnteteGGUFTest(unittest.TestCase):
    def test_entete_incoherent_refuse(self) -> None:
        with self.assertRaises(ValueError):
            EnteteGGUF(version=1, boutisme="petit", architecture=None, octets_lus=0)
        with self.assertRaises(ValueError):
            EnteteGGUF(version=3, boutisme="moyen", architecture=None, octets_lus=0)
        with self.assertRaises(ValueError):
            EnteteGGUF(version=3, boutisme="petit", architecture="", octets_lus=0)


if __name__ == "__main__":
    unittest.main()
