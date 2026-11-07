"""Tests de la liste des audios et du décodage PyAV commun (tâche 6.1).

Les WAV de test sont générés localement avec la bibliothèque standard et numpy :
aucune donnée réelle, aucun moteur, aucun poids et aucun réseau. Les liens
symboliques sont ignorés là où leur création est refusée (Windows sans
privilège, par exemple), et un nom de périphérique réservé Windows n'est créé
que si le système de fichiers l'accepte.
"""

from __future__ import annotations

import hashlib
import html
import os
import tempfile
import unittest
import wave
from pathlib import Path
from unittest import mock

import numpy as np

import transcription_bench.audios as audios_module
from tests.outils_html import assert_html_seul
from transcription_bench.audios import (
    AudioEnErreur,
    AudioIllisible,
    AudioListe,
    DureeDecodeeNulle,
    ERREUR_NOM_REFUSE,
    decoder_audio,
    lister_audios,
)
from transcription_bench.operations import CreneauOperations
from transcription_bench.paths import ValeurRefusee
from transcription_bench.web import (
    ConfigApplication,
    ServicesApplication,
    create_app,
)

FREQUENCE_TEST = 44100
CANAUX_TEST = 2
DUREE_TEST = 0.5
PORT_TEST = 8765
BASE_URL = f"http://127.0.0.1:{PORT_TEST}"


def ecrire_wav(
    chemin: Path,
    duree: float = DUREE_TEST,
    frequence: int = FREQUENCE_TEST,
    canaux: int = CANAUX_TEST,
) -> None:
    """Écrit un WAV PCM 16 bits de sinus à 440 Hz, entièrement synthétique."""
    total = int(round(frequence * duree))
    temps = np.arange(total) / frequence
    signal = (20000 * np.sin(2 * np.pi * 440 * temps)).astype("<i2")
    if canaux > 1:
        signal = np.repeat(signal[:, None], canaux, axis=1)
    with wave.open(str(chemin), "wb") as fichier:
        fichier.setnchannels(canaux)
        fichier.setsampwidth(2)
        fichier.setframerate(frequence)
        fichier.writeframes(signal.tobytes())


def ecrire_wav_sans_echantillon(chemin: Path) -> None:
    """Écrit un WAV valide dont le flux ne contient aucun échantillon."""
    with wave.open(str(chemin), "wb") as fichier:
        fichier.setnchannels(1)
        fichier.setsampwidth(2)
        fichier.setframerate(16000)
        fichier.writeframes(b"")


class SocleAudiosTest(unittest.TestCase):
    """Dossier de données temporaire et helpers communs."""

    def setUp(self) -> None:
        temporaire = tempfile.TemporaryDirectory()
        self.addCleanup(temporaire.cleanup)
        self.racine = Path(temporaire.name)
        self.donnees = self.racine / "data"
        self.dossier = self.donnees / "audio"
        self.dossier.mkdir(parents=True)

    def chemin(self, nom: str) -> Path:
        return self.dossier / nom


class ListeAudiosTest(SocleAudiosTest):
    """Liste du dossier d'entrée : formats, durée indicative, erreurs par fichier."""

    def test_formats_acceptes_tries_avec_duree_indicative(self) -> None:
        ecrire_wav(self.chemin("b.wav"), duree=DUREE_TEST)
        ecrire_wav(self.chemin("A.WAV"), duree=0.25)
        self.chemin("note.txt").write_text("pas un audio", encoding="utf-8")
        self.chemin("photo.jpeg").write_bytes(b"pas un audio non plus")
        self.chemin("sous.wav").mkdir()

        audios = lister_audios(self.donnees)

        self.assertEqual([audio.nom for audio in audios], ["A.WAV", "b.wav"])
        self.assertEqual([audio.format for audio in audios], ["wav", "wav"])
        self.assertAlmostEqual(audios[0].duree_indicative, 0.25, places=2)
        self.assertAlmostEqual(audios[1].duree_indicative, DUREE_TEST, places=2)
        for audio, nom in zip(audios, ("A.WAV", "b.wav")):
            self.assertIsNone(audio.erreur, nom)
            self.assertEqual(audio.taille_octets, self.chemin(nom).stat().st_size)

    def test_fichier_illisible_signale_sans_interrompre_la_liste(self) -> None:
        ecrire_wav(self.chemin("ok.wav"))
        self.chemin("illisible.wav").write_bytes(b"pas de l'audio du tout" * 8)

        audios = lister_audios(self.donnees)

        self.assertEqual([audio.nom for audio in audios], ["illisible.wav", "ok.wav"])
        illisible, lisible = audios
        self.assertIsNotNone(illisible.erreur)
        self.assertIn("lecture impossible", illisible.erreur or "")
        self.assertIn("illisible.wav", illisible.erreur or "")
        self.assertIsNone(illisible.duree_indicative)
        self.assertEqual(
            illisible.taille_octets, self.chemin("illisible.wav").stat().st_size
        )
        self.assertIsNone(lisible.erreur)
        self.assertAlmostEqual(lisible.duree_indicative or 0.0, DUREE_TEST, places=2)

    def test_fichier_sans_duree_indicative_reste_lisible(self) -> None:
        ecrire_wav_sans_echantillon(self.chemin("zero.wav"))

        audios = lister_audios(self.donnees)

        self.assertEqual(len(audios), 1)
        self.assertIsNone(audios[0].duree_indicative)
        self.assertIsNone(audios[0].erreur)
        self.assertIsNotNone(audios[0].taille_octets)

    def test_dossier_absent_liste_vide_sans_creation(self) -> None:
        dossier_absent = self.racine / "absent" / "audio"

        self.assertEqual(lister_audios(self.racine / "absent"), ())
        self.assertFalse(dossier_absent.exists())

    def test_lien_symbolique_sortant_liste_avec_nom_refuse(self) -> None:
        exterieur = self.racine / "exterieur.wav"
        ecrire_wav(exterieur)
        try:
            os.symlink(exterieur, self.chemin("sortant.wav"))
        except (OSError, NotImplementedError):
            self.skipTest("création de lien symbolique non autorisée sur ce poste")
        ecrire_wav(self.chemin("interne.wav"))

        audios = lister_audios(self.donnees)

        self.assertEqual([audio.nom for audio in audios], ["interne.wav", "sortant.wav"])
        interne, sortant = audios
        self.assertIsNone(interne.erreur)
        self.assertEqual(sortant.erreur, ERREUR_NOM_REFUSE)
        self.assertIsNone(sortant.taille_octets)
        self.assertIsNone(sortant.duree_indicative)

    def test_peripherique_reserve_windows_liste_avec_nom_refuse(self) -> None:
        con = self.chemin("CON.wav")
        try:
            if os.name == "nt":
                con_etendu = Path(f"\\\\?\\{con}")
                con_etendu.write_bytes(b"contenu factice")
                # La suppression d'un nom réservé exige aussi le préfixe.
                self.addCleanup(lambda: con_etendu.unlink(missing_ok=True))
            else:
                con.write_bytes(b"contenu factice")
        except OSError:
            self.skipTest("ce système de fichiers refuse un nom de périphérique Windows")
        ecrire_wav(self.chemin("reel.wav"))

        audios = lister_audios(self.donnees)

        self.assertEqual([audio.nom for audio in audios], ["CON.wav", "reel.wav"])
        self.assertEqual(audios[0].erreur, ERREUR_NOM_REFUSE)
        self.assertIsNone(audios[1].erreur)

    def test_noms_au_bon_format_refuses_listes_sans_selection(self) -> None:
        # `:` et `\` sont des caractères de nom valides sous Linux ; sous
        # Windows leur création échoue et le test est ignoré.
        for nom in ("a:b.wav", "a\\b.wav"):
            try:
                self.chemin(nom).write_bytes(b"contenu factice")
            except OSError:
                self.skipTest(
                    f"ce système de fichiers refuse le nom {nom!r}"
                )
        ecrire_wav(self.chemin("reel.wav"))

        audios = lister_audios(self.donnees)

        self.assertEqual(
            [audio.nom for audio in audios], ["a:b.wav", "a\\b.wav", "reel.wav"]
        )
        for refuse in audios[:2]:
            self.assertEqual(refuse.erreur, ERREUR_NOM_REFUSE, refuse.nom)
            self.assertEqual(refuse.format, "wav", refuse.nom)
        self.assertIsNone(audios[2].erreur)

    def test_erreur_inattendue_sur_un_fichier_n_interrompt_pas_la_liste(self) -> None:
        ecrire_wav(self.chemin("casse.wav"))
        ecrire_wav(self.chemin("ok.wav"))
        origine = audios_module._chemin_audio

        def echouer_sur_casse(nom, donnees):
            if nom == "casse.wav":
                raise RuntimeError("incident imprévu")
            return origine(nom, donnees)

        with mock.patch.object(audios_module, "_chemin_audio", echouer_sur_casse):
            audios = lister_audios(self.donnees)

        self.assertEqual([audio.nom for audio in audios], ["casse.wav", "ok.wav"])
        casse, ok = audios
        self.assertIn("lecture impossible", casse.erreur or "")
        self.assertIn("casse.wav", casse.erreur or "")
        self.assertNotIn("incident", casse.erreur or "")
        self.assertIsNone(ok.erreur)


class DecodageAudioTest(SocleAudiosTest):
    """Décodage commun : signal, empreinte, durées et refus explicites."""

    def test_wav_local_decode_en_float32_mono_16_khz(self) -> None:
        chemin = self.chemin("ok.wav")
        ecrire_wav(chemin)

        audio = decoder_audio("ok.wav", self.donnees)

        self.assertEqual(audio.nom, "ok.wav")
        self.assertEqual(audio.format, "wav")
        self.assertEqual(audio.frequence, 16000)
        self.assertEqual(audio.echantillons, 8000)
        self.assertAlmostEqual(audio.duree_decodee, DUREE_TEST, places=3)
        self.assertAlmostEqual(audio.duree_indicative or 0.0, DUREE_TEST, places=2)
        self.assertEqual(audio.signal.dtype, np.float32)
        self.assertEqual(audio.signal.ndim, 1)
        self.assertEqual(audio.signal.size, audio.echantillons)
        self.assertFalse(audio.signal.flags.writeable)
        self.assertLessEqual(float(np.abs(audio.signal).max()), 1.0)
        self.assertEqual(audio.taille_octets, chemin.stat().st_size)
        self.assertEqual(
            audio.empreinte_sha256, hashlib.sha256(chemin.read_bytes()).hexdigest()
        )
        self.assertGreaterEqual(audio.temps_decodage, 0.0)
        self.assertLess(audio.temps_decodage, 60.0)

    def test_decodage_deterministe_pour_les_moteurs(self) -> None:
        ecrire_wav(self.chemin("ok.wav"))

        premier = decoder_audio("ok.wav", self.donnees)
        second = decoder_audio("ok.wav", self.donnees)

        self.assertEqual(premier.echantillons, second.echantillons)
        self.assertEqual(premier.empreinte_sha256, second.empreinte_sha256)
        self.assertTrue(np.array_equal(premier.signal, second.signal))

    def test_fichier_illisible_leve_une_erreur_explicite(self) -> None:
        self.chemin("illisible.wav").write_bytes(b"pas de l'audio du tout" * 8)

        with self.assertRaises(AudioIllisible) as contexte:
            decoder_audio("illisible.wav", self.donnees)

        message = str(contexte.exception)
        self.assertIsInstance(contexte.exception, AudioEnErreur)
        self.assertIn("lecture impossible", message)
        self.assertIn("illisible.wav", message)
        self.assertNotIn(str(self.dossier), message)
        self.assertNotIn("Traceback", message)

    def test_duree_decodee_nulle_leve_une_erreur_explicite(self) -> None:
        ecrire_wav_sans_echantillon(self.chemin("zero.wav"))

        with self.assertRaises(DureeDecodeeNulle) as contexte:
            decoder_audio("zero.wav", self.donnees)

        message = str(contexte.exception)
        self.assertIsInstance(contexte.exception, AudioEnErreur)
        self.assertIn("durée décodée nulle", message)
        self.assertIn("zero.wav", message)
        self.assertIn("RTF", message)

    def test_noms_hors_liste_ou_hors_dossier_refuses(self) -> None:
        ecrire_wav(self.chemin("ok.wav"))
        self.chemin("note.txt").write_text("pas un audio", encoding="utf-8")
        self.chemin("sous.wav").mkdir()
        absolu = str(self.chemin("ok.wav"))
        noms = (
            "note.txt",
            "sans_extension",
            "",
            "../ok.wav",
            "sous/ok.wav",
            "..",
            absolu,
            "ok.wav/../ok.wav",
            "ok.wav\\ok.wav",
            "C:ok.wav",
            "CON.wav",
            "nul.wav",
            "COM1.wav",
            "COM¹.wav",
            "COM².wav",
            "com³.wav",
            "LPT1.wav",
            "lpt9.wav",
            "LPT².wav",
            "LPT³.wav",
            "sous.wav",
            "absent.wav",
        )
        for nom in noms:
            with self.subTest(nom=nom):
                with self.assertRaises(ValeurRefusee):
                    decoder_audio(nom, self.donnees)

    def test_sous_dossier_existant_refuse(self) -> None:
        sous_dossier = self.dossier / "sous"
        sous_dossier.mkdir()
        ecrire_wav(sous_dossier / "ok.wav")

        with self.assertRaises(ValeurRefusee) as contexte:
            decoder_audio("sous/ok.wav", self.donnees)

        self.assertIn("sans sous-dossier", str(contexte.exception))
        self.assertEqual([audio.nom for audio in lister_audios(self.donnees)], [])

    def test_lien_symbolique_sortant_refuse(self) -> None:
        exterieur = self.racine / "exterieur.wav"
        ecrire_wav(exterieur)
        try:
            os.symlink(exterieur, self.chemin("sortant.wav"))
        except (OSError, NotImplementedError):
            self.skipTest("création de lien symbolique non autorisée sur ce poste")

        with self.assertRaises(ValeurRefusee):
            decoder_audio("sortant.wav", self.donnees)


class PageAudiosTest(SocleAudiosTest):
    """Page HTML minimale : liste lue, erreurs affichées, échappement, hors ligne."""

    def setUp(self) -> None:
        super().setUp()
        _, self.client = self.construire_client()

    def construire_client(self, **options):
        """Application de test et client pointant sur le dossier temporaire."""
        application = create_app(
            ConfigApplication(port=PORT_TEST, dossier_data=self.donnees),
            ServicesApplication(creneau=CreneauOperations(), **options),
        )
        return application, application.test_client()

    def verifier_html_seul(self, corps: str) -> None:
        assert_html_seul(self, corps)

    def texte(self, chemin: str, client=None) -> str:
        reponse = (client or self.client).get(chemin, base_url=BASE_URL)
        self.assertEqual(reponse.status_code, 200, chemin)
        return html.unescape(reponse.get_data(as_text=True))

    def test_page_reelle_liste_les_audios_et_signale_les_erreurs(self) -> None:
        ecrire_wav(self.chemin("ok.wav"))
        ecrire_wav_sans_echantillon(self.chemin("zero.wav"))
        self.chemin("illisible.wav").write_bytes(b"pas de l'audio du tout" * 8)

        corps = self.texte("/audios")

        self.assertNotIn("Fonctionnalité non disponible", corps)
        self.assertIn("ok.wav", corps)
        # Durée avec le formateur commun de premier niveau : virgule décimale
        # française, jamais trois décimales (tâche 5.3).
        self.assertIn("0,5 s", corps)
        self.assertNotIn("0.50 s", corps)
        self.assertIn("zero.wav", corps)
        self.assertIn("illisible.wav", corps)
        self.assertIn("lecture impossible", corps)
        self.assertIn("durée réellement décodée", corps)
        self.verifier_html_seul(corps)

    def test_page_vide_sans_audio(self) -> None:
        corps = self.texte("/audios")

        self.assertIn("Aucun fichier audio", corps)
        self.assertIn('href="/resultats"', corps, "navigation commune présente")
        self.verifier_html_seul(corps)

    def test_page_signale_un_nom_refuse_sans_le_proposer(self) -> None:
        try:
            self.chemin("a:b.wav").write_bytes(b"contenu factice")
        except OSError:
            self.skipTest("ce système de fichiers refuse le nom 'a:b.wav'")

        corps = self.texte("/audios")

        self.assertIn("a:b.wav", corps)
        self.assertIn(ERREUR_NOM_REFUSE, corps)
        self.verifier_html_seul(corps)

    def test_page_dossier_inaccessible_message_fixe(self) -> None:
        def lister_inaccessible(donnees) -> tuple[AudioListe, ...]:
            raise PermissionError("accès refusé")

        _, client = self.construire_client(lister_audios=lister_inaccessible)

        corps = self.texte("/audios", client=client)

        self.assertIn("n'a pas pu être lu", corps)
        self.assertNotIn("Aucun fichier audio", corps)
        self.assertNotIn("accès refusé", corps)
        self.verifier_html_seul(corps)

    def test_contenus_externes_echappes(self) -> None:
        nom = '<script>alert("x")</script>.wav'
        liste = (
            AudioListe(nom=nom, format="wav", taille_octets=1, duree_indicative=None),
        )
        _, client = self.construire_client(lister_audios=lambda donnees: liste)

        corps = self.texte("/audios", client=client)
        brut = client.get("/audios", base_url=BASE_URL).get_data(as_text=True)

        self.assertIn(nom, corps)
        # Le nom brut n'apparaît jamais : il est échappé. Le squelette charge
        # par ailleurs son unique script local, d'où le contrôle sur le nom.
        self.assertNotIn(nom, brut)
        self.assertIn("&lt;script&gt;", brut)
        self.verifier_html_seul(brut)

    def test_page_audios_sans_effet_de_bord(self) -> None:
        self.texte("/audios")

        self.assertTrue(self.dossier.is_dir())
        for nom in ("results", "models", "engines"):
            self.assertFalse((self.donnees / nom).exists(), nom)
        self.assertEqual(list(self.dossier.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
