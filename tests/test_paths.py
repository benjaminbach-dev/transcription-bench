"""Tests des dossiers de données et de la résolution contrôlée des noms.

Les audios de test sont des octets factices : aucun décodage, aucun réseau et
aucune donnée réelle. Les liens symboliques sont ignorés sur les postes où leur
création n'est pas autorisée (Windows sans privilège, par exemple).
"""

from __future__ import annotations

import contextlib
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from transcription_bench import paths
from transcription_bench.paths import (
    DOSSIERS_DATA,
    NOM_DOSSIER_AUDIO,
    NOM_DOSSIER_RESULTATS,
    ValeurRefusee,
    preparer_dossiers_data,
    resoudre_audio,
    resoudre_dans_racine,
    resoudre_resultat,
    valider_identifiant_modele,
)

AUDIO_FACTICE = b"RIFF\x00\x00\x00\x00WAVEforme factice pour test local"


class DossiersDataTest(unittest.TestCase):
    def test_base_par_defaut_ancre_a_la_racine_du_projet(self) -> None:
        self.assertEqual(paths.DOSSIER_DATA, paths.RACINE_PROJET / "data")
        self.assertTrue((paths.RACINE_PROJET / "pyproject.toml").is_file())

    def test_cree_les_dossiers_manquants(self) -> None:
        with tempfile.TemporaryDirectory() as dossier:
            chemins = preparer_dossiers_data(Path(dossier) / "data")
            self.assertEqual(sorted(chemins), sorted(DOSSIERS_DATA))
            for nom, chemin in chemins.items():
                self.assertTrue(chemin.is_dir(), nom)
                self.assertEqual(chemin, Path(dossier) / "data" / nom)

    def test_idempotent_et_conserve_les_fichiers_existants(self) -> None:
        with tempfile.TemporaryDirectory() as dossier:
            base = Path(dossier) / "data"
            preparer_dossiers_data(base)
            temoin = base / "audio" / "exemple.wav"
            temoin.write_bytes(b"contenu existant")

            chemins = preparer_dossiers_data(base)

            self.assertTrue(temoin.is_file())
            self.assertEqual(temoin.read_bytes(), b"contenu existant")
            self.assertEqual(sorted(chemins), sorted(DOSSIERS_DATA))

    def test_base_par_defaut_independante_du_dossier_courant(self) -> None:
        with tempfile.TemporaryDirectory() as dossier, tempfile.TemporaryDirectory() as ailleurs:
            base = Path(dossier) / "data-projet"
            with mock.patch.object(paths, "DOSSIER_DATA", base):
                with contextlib.chdir(ailleurs):
                    chemins = preparer_dossiers_data()

            for nom, chemin in chemins.items():
                self.assertTrue(chemin.is_dir(), nom)
                self.assertEqual(chemin, base / nom)
            self.assertEqual(os.listdir(ailleurs), [])


class ResolutionSousRacineTest(unittest.TestCase):
    """Socle commun : racine temporaire, dossier extérieur et cibles factices."""

    def setUp(self) -> None:
        temporaire = tempfile.TemporaryDirectory()
        self.addCleanup(temporaire.cleanup)
        self.racine_temp = Path(temporaire.name)
        self.donnees = self.racine_temp / "data"
        self.audio = self.donnees / NOM_DOSSIER_AUDIO
        self.resultats = self.donnees / NOM_DOSSIER_RESULTATS
        self.exterieur = self.racine_temp / "exterieur"
        self.audio.mkdir(parents=True)
        self.resultats.mkdir(parents=True)
        self.exterieur.mkdir()
        self.secret = self.exterieur / "secret.wav"
        self.secret.write_bytes(AUDIO_FACTICE)
        self.temoin_exterieur = self.exterieur / "temoin.txt"
        self.temoin_exterieur.write_bytes(b"hors racine intact")

    def creer_lien(self, cible: Path, lien: Path) -> None:
        """Crée un lien symbolique ou ignore le test si le poste le refuse."""
        try:
            os.symlink(cible, lien, target_is_directory=cible.is_dir())
        except (OSError, NotImplementedError) as erreur:
            self.skipTest(f"liens symboliques indisponibles sur ce poste : {erreur}")

    def assert_refuse(self, fonction, valeur: str) -> None:
        with self.subTest(valeur=valeur):
            with self.assertRaises(ValeurRefusee):
                fonction(valeur)

    def verifier_exterieur_intact(self) -> None:
        self.assertEqual(self.secret.read_bytes(), AUDIO_FACTICE)
        self.assertEqual(self.temoin_exterieur.read_bytes(), b"hors racine intact")


class ResoudreAudioTest(ResolutionSousRacineTest):
    def test_nom_legitime_resolu_sous_le_dossier_audio(self) -> None:
        cible = self.audio / "enregistrement 01.wav"
        cible.write_bytes(AUDIO_FACTICE)

        chemin = resoudre_audio("enregistrement 01.wav", self.donnees)

        self.assertTrue(chemin.is_absolute())
        self.assertEqual(chemin, cible.resolve())
        self.assertEqual(chemin.read_bytes(), AUDIO_FACTICE)

    def test_nom_inexistant_reste_sous_le_dossier_audio(self) -> None:
        chemin = resoudre_audio("depot-futur.wav", self.donnees)

        self.assertEqual(chemin, (self.audio / "depot-futur.wav").resolve())
        self.assertFalse(chemin.exists())

    def test_noms_dangereux_refuses_meme_si_la_cible_existe(self) -> None:
        noms = (
            "../exterieur/secret.wav",
            "../../secret.wav",
            "sous/../../exterieur/secret.wav",
            "sous/../depot-futur.wav",
            "./depot-futur.wav",
            "../",
            "..",
            ".",
            "",
            "/etc/passwd",
            "C:/Windows/win.ini",
            "C:secret.wav",
            "\\\\serveur\\partage\\secret.wav",
            "..\\..\\secret.wav",
            "sous/secret.wav\\..\\..\\secret.wav",
            "sous//secret.wav",
            "sous/",
            "secret.wav\x00.txt",
        )
        for nom in noms:
            self.assert_refuse(lambda valeur: resoudre_audio(valeur, self.donnees), nom)
        self.verifier_exterieur_intact()

    def test_lien_symbolique_sortant_refuse(self) -> None:
        self.creer_lien(self.secret, self.audio / "secret.wav")
        self.creer_lien(self.exterieur, self.audio / "dossier-sortant")

        self.assert_refuse(lambda nom: resoudre_audio(nom, self.donnees), "secret.wav")
        self.assert_refuse(
            lambda nom: resoudre_audio(nom, self.donnees), "dossier-sortant/secret.wav"
        )
        self.verifier_exterieur_intact()

    def test_lien_symbolique_interne_accepte(self) -> None:
        dossier_interne = self.audio / "archives"
        dossier_interne.mkdir()
        cible = dossier_interne / "exemple.wav"
        cible.write_bytes(AUDIO_FACTICE)
        self.creer_lien(dossier_interne, self.audio / "lien-interne")

        chemin = resoudre_audio("lien-interne/exemple.wav", self.donnees)

        self.assertEqual(chemin, cible.resolve())
        self.assertEqual(chemin.read_bytes(), AUDIO_FACTICE)

    def test_boucle_de_liens_refusee_sans_erreur_interne(self) -> None:
        boucle = self.audio / "boucle.wav"
        self.creer_lien(boucle, boucle)
        racine_boucle = self.racine_temp / "racine-boucle"
        self.creer_lien(racine_boucle, racine_boucle)

        self.assert_refuse(lambda nom: resoudre_audio(nom, self.donnees), "boucle.wav")
        self.assert_refuse(
            lambda nom: resoudre_dans_racine(racine_boucle, nom), "exemple.wav"
        )
        self.verifier_exterieur_intact()

    def test_racine_elle_meme_lien_symbolique_reste_couverte(self) -> None:
        lieu = self.racine_temp / "donnees-liees"
        self.creer_lien(self.donnees, lieu)

        chemin = resoudre_audio("depot-futur.wav", lieu)

        self.assertEqual(chemin, (self.audio / "depot-futur.wav").resolve())


class ResoudreResultatTest(ResolutionSousRacineTest):
    def test_identifiant_d_execution_legitime(self) -> None:
        execution = self.resultats / "20261025-120000-abc123"
        execution.mkdir()

        chemin = resoudre_resultat("20261025-120000-abc123", self.donnees)

        self.assertEqual(chemin, execution.resolve())

    def test_fichiers_internes_predictibles_acceptes(self) -> None:
        execution = self.resultats / "20261025-120000-abc123" / "1-exemple"
        execution.mkdir(parents=True)
        cible = execution / "result.json"
        cible.write_text("{}", encoding="utf-8")

        chemin = resoudre_resultat(
            "20261025-120000-abc123/1-exemple/result.json", self.donnees
        )

        self.assertEqual(chemin, cible.resolve())

    def test_identifiants_dangereux_refuses_meme_si_la_cible_existe(self) -> None:
        noms = (
            "../exterieur/secret.wav",
            "20261025-120000-abc123/../../exterieur/secret.wav",
            "20261025-120000-abc123/../autre-execution",
            "./20261025-120000-abc123",
            "..",
            ".",
            "",
            "/etc/passwd",
            "C:/Windows/win.ini",
            "\\\\serveur\\partage\\secret.wav",
            "..\\..\\secret.wav",
            "20261025-120000-abc123//run.json",
            "20261025-120000-abc123/",
            "run.json\x00.txt",
        )
        for nom in noms:
            self.assert_refuse(lambda valeur: resoudre_resultat(valeur, self.donnees), nom)
        self.verifier_exterieur_intact()

    def test_lien_symbolique_sortant_refuse(self) -> None:
        self.creer_lien(self.exterieur, self.resultats / "20261025-120000-abc123")

        self.assert_refuse(
            lambda nom: resoudre_resultat(nom, self.donnees),
            "20261025-120000-abc123/secret.wav",
        )
        self.verifier_exterieur_intact()


class ResoudreDansRacineTest(ResolutionSousRacineTest):
    def test_chemin_imbrique_legitime(self) -> None:
        cible = self.audio / "sous" / "exemple.wav"
        cible.parent.mkdir()
        cible.write_bytes(AUDIO_FACTICE)

        chemin = resoudre_dans_racine(self.audio, "sous/exemple.wav")

        self.assertEqual(chemin, cible.resolve())

    def test_racine_non_existante_reste_autorisee_pour_ecriture_future(self) -> None:
        racine = self.racine_temp / "nouvelle-racine"
        chemin = resoudre_dans_racine(racine, "exemple.wav")

        self.assertEqual(chemin, (racine / "exemple.wav").resolve())
        self.assertFalse(racine.exists())

    def test_refus_d_un_prefixe_de_racine_voisin(self) -> None:
        voisine = self.racine_temp / "audio-voisin"
        voisine.mkdir()
        self.creer_lien(voisine, self.audio / "voisine")

        self.assert_refuse(
            lambda nom: resoudre_dans_racine(self.audio, nom), "voisine/exemple.wav"
        )


class IdentifiantModeleTest(unittest.TestCase):
    def test_identifiants_valides_rendus_inchanges(self) -> None:
        identifiants = (
            "Systran/faster-whisper-large-v3-turbo",
            "openai/whisper-large-v3-turbo",
            "nvidia/parakeet-tdt-0.6b-v3",
            "gpt2",
            "whisper-large-v3-turbo",
            "_org/name_with.dot-dash",
            "123/456",
            f"{'a' * 96}/{'b' * 96}",
            "a" * 96,
        )
        for identifiant in identifiants:
            with self.subTest(identifiant=identifiant):
                self.assertEqual(valider_identifiant_modele(identifiant), identifiant)

    def test_identifiants_dangereux_ou_non_conformes_refuses(self) -> None:
        identifiants = (
            "",
            "org/name/extra",
            "org//name",
            "org/",
            "/org/name",
            "../models/org/name",
            "org/../name",
            "org/name/../../x",
            "org/..name",
            "org/na..me",
            "org/na--me",
            "org/name.git",
            "C:/org/name",
            "C:\\org\\name",
            "\\\\serveur\\partage\\org\\name",
            "org\\name",
            " org/name",
            "org/name ",
            ".org/name",
            "org/.name",
            "org/name.",
            "café/name",
            f"{'a' * 97}/name",
            "a" * 97,
            "org/name\x00",
        )
        for identifiant in identifiants:
            with self.subTest(identifiant=identifiant):
                with self.assertRaises(ValeurRefusee):
                    valider_identifiant_modele(identifiant)
        with self.assertRaises(ValeurRefusee):
            valider_identifiant_modele(Path("org/name"))

    def test_valeur_refusee_reste_une_erreur_de_valeur(self) -> None:
        self.assertTrue(issubclass(ValeurRefusee, ValueError))


if __name__ == "__main__":
    unittest.main()
