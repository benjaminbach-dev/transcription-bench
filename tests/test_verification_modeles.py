"""Tests de la vérification distante des modèles, sans réseau réel ni poids.

Les réponses Hugging Face sont simulées : soit par un petit client injecté,
soit par le vrai client ``HuggingFace`` branché sur un transport ``httpx2``
local. Aucun HTTP réel n'est émis, aucun poids n'est téléchargé et aucune
déclaration fournie ne change de qualification. Les chemins de succès utilisent
des déclarations synthétiques ``qualifiee=True``.
"""

from __future__ import annotations

import dataclasses
import io
import json
import re
import subprocess
import sys
import threading
import unittest
from contextlib import nullcontext
from types import SimpleNamespace
from unittest import mock

import httpx2
from huggingface_hub.utils import close_session, set_client_factory

from engines.declarations import (
    DECLARATION_FASTER_WHISPER,
    DECLARATION_TRANSCRIBE_CPP,
    DeclarationAdaptateur,
    Famille,
    declarations_fournies,
)
from engines.registre import MoteurInconnu, RegistreMoteurs
from transcription_bench.compatibilite_modeles import (
    RAISON_FAMILLE_NON_QUALIFIEE,
    RAISON_FICHIER_GGUF_NON_CHOISI,
    RAISON_NOM_FICHIER_REFUSE,
    REGLE_CTRANSLATE2_WHISPER,
    REGLE_TRANSFORMERS_SAFETENSORS,
    REGLE_TRANSCRIBE_CPP_GGUF,
)
from transcription_bench.gguf import TAILLE_BLOC
from transcription_bench.operations import (
    ETAT_EN_COURS,
    ETAT_LIBRE,
    ETAT_TERMINEE,
    TYPE_EXECUTION,
    TYPE_VERIFICATION,
    CreneauOccupe,
    CreneauOperations,
    ServiceArrete,
)
from transcription_bench.paths import RACINE_PROJET, ValeurRefusee
from transcription_bench.verification_modeles import (
    DELAI_MODELE_INFO,
    MESSAGES_ERREUR,
    OCTETS_MAX_JSON,
    RAISON_ACCES_REFUSE,
    RAISON_COMMIT_INVALIDE,
    RAISON_ERREUR_HUB,
    RAISON_ERREUR_INATTENDUE,
    RAISON_FICHIER_ILLISIBLE,
    RAISON_FICHIER_TROP_VOLUMINEUX,
    RAISON_RESEAU_INDISPONIBLE,
    RAISON_REVISION_INCONNUE,
    ClientHuggingFace,
    ErreurClientModeles,
    FichierDistant,
    InfosModele,
    ResultatVerification,
    VerificationModeles,
)
from tests.entetes_gguf_de_test import entete_gguf

DELAI = 5.0
COMMIT = "0123456789abcdef0123456789abcdef01234567"
SECRET_FACTICE = "hf_FAKE_SECRET"

CONTENUS_CTRANSLATE2 = {
    "config.json": json.dumps({"lang_ids": {"fr": 50265}}).encode(),
    "model.safetensors.index.json": b'{"weight_map": {"x": "x.safetensors"}}',
    "preprocessor_config.json": json.dumps(
        {"feature_extractor_type": "WhisperFeatureExtractor"}
    ).encode(),
    "tokenizer.json": b"poids-factice-tokenizer-a-ne-pas-lire",
    "model.bin": b"poids-ctranslate2-a-ne-pas-lire",
    "vocabulary.json": b"{}",
    "README.md": b"documentation non retenue",
}
CONTENUS_TRANSFORMERS = {
    "config.json": json.dumps(
        {"model_type": "whisper", "architectures": ["WhisperForConditionalGeneration"]}
    ).encode(),
    "generation_config.json": json.dumps({"max_length": 448}).encode(),
    "preprocessor_config.json": json.dumps(
        {"feature_extractor_type": "WhisperFeatureExtractor"}
    ).encode(),
    "tokenizer_config.json": json.dumps(
        {"tokenizer_class": "WhisperTokenizer"}
    ).encode(),
    "tokenizer.json": b"poids-factice-tokenizer-a-ne-pas-lire",
    "model.safetensors": b"poids-safetensors-a-ne-pas-lire",
    "pytorch_model.bin": b"pickle-a-ne-pas-lire",
    "pytorch_model.bin.index.json": b"{}",
    "modele.nemo": b"nemo-a-ne-pas-lire",
    "modele.gguf": b"gguf-a-ne-pas-lire",
    "modele.onnx": b"onnx-a-ne-pas-lire",
    "modele.h5": b"h5-a-ne-pas-lire",
}


def declaration_synthetique(
    *,
    identifiant: str = "moteur-de-test",
    regle: str = REGLE_CTRANSLATE2_WHISPER,
    familles: tuple[str, ...] = ("whisper",),
    qualifiee: bool = True,
) -> DeclarationAdaptateur:
    return DeclarationAdaptateur(
        identifiant=identifiant,
        nom="Moteur de test",
        fichier_requirements=None,
        regle_compatibilite=regle,
        familles=tuple(Famille(nom, nom, qualifiee=qualifiee) for nom in familles),
    )


def infos_de(
    contenus: dict[str, bytes],
    *,
    commit: str = COMMIT,
    tailles: dict[str, int | None] | None = None,
    noms_supplementaires: tuple[str, ...] = (),
) -> InfosModele:
    tailles = tailles or {}
    noms = tuple(contenus) + noms_supplementaires
    return InfosModele(
        commit=commit,
        fichiers=tuple(
            FichierDistant(
                nom,
                tailles[nom] if nom in tailles else len(contenus.get(nom, b"")),
            )
            for nom in noms
        ),
    )


class FauxFichier:
    """Flux binaire local, avec relevé des lectures et refus des demandes géantes."""

    def __init__(self, octets: bytes, journal: list[tuple[str, int]], nom: str) -> None:
        self._octets = octets
        self._journal = journal
        self._nom = nom
        self.position = 0

    def read(self, taille: int) -> bytes:
        if not isinstance(taille, int) or taille <= 0:
            raise AssertionError(f"lecture non bornée demandée : {taille!r}")
        self._journal.append((self._nom, taille))
        if taille > TAILLE_BLOC:
            raise AssertionError(
                f"lecture de {taille} octets au-delà du bloc de {TAILLE_BLOC}"
            )
        bloc = self._octets[self.position : self.position + taille]
        self.position += len(bloc)
        return bloc

    def __enter__(self) -> FauxFichier:
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        return None


class FauxClient:
    def __init__(
        self,
        infos: InfosModele | None = None,
        contenus: dict[str, bytes] | None = None,
        *,
        erreur_infos: BaseException | None = None,
    ) -> None:
        self.infos = infos or InfosModele(commit=COMMIT, fichiers=())
        self.contenus = dict(contenus or {})
        self.erreur_infos = erreur_infos
        self.appels_infos: list[tuple[str, str | None]] = []
        self.ouvertures: list[tuple[str, str, str]] = []
        self.lectures: list[tuple[str, int]] = []

    def informations(self, identifiant: str, revision: str | None) -> InfosModele:
        self.appels_infos.append((identifiant, revision))
        if self.erreur_infos is not None:
            raise self.erreur_infos
        return self.infos

    def ouvrir_fichier(self, identifiant: str, commit: str, nom: str):
        self.ouvertures.append((identifiant, commit, nom))
        if nom not in self.contenus:
            raise FileNotFoundError(nom)
        return FauxFichier(self.contenus[nom], self.lectures, nom)


class ClientBloque(FauxClient):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.debut = threading.Event()
        self.debloque = threading.Event()

    def informations(self, identifiant: str, revision: str | None) -> InfosModele:
        self.debut.set()
        if not self.debloque.wait(DELAI):
            raise AssertionError("client bloqué non libéré")
        return super().informations(identifiant, revision)


class BaseVerificationTest(unittest.TestCase):
    def setUp(self) -> None:
        self.creneau = CreneauOperations()
        self.registre = RegistreMoteurs()
        self.addCleanup(self._nettoyer_creneau)

    def _nettoyer_creneau(self) -> None:
        self.creneau.arreter(0.1)

    def enregistrer(self, declaration: DeclarationAdaptateur) -> None:
        self.registre.enregistrer(declaration)

    def service(self, client: FauxClient | None = None) -> VerificationModeles:
        return VerificationModeles(
            self.registre, self.creneau, client=client
        )

    def attendre(self) -> None:
        thread = self.creneau.thread_travailleur
        self.assertIsNotNone(thread)
        thread.join(DELAI)
        self.assertFalse(thread.is_alive(), "thread de vérification non terminé")

    def lancer_et_attendre(self, service: VerificationModeles, **kwargs) -> None:
        service.lancer(**kwargs)
        self.attendre()

    def assert_refus(self, resultat: ResultatVerification, raison: str) -> None:
        self.assertIsNotNone(resultat)
        self.assertFalse(resultat.accepte, resultat.message)
        self.assertEqual(resultat.raison, raison)
        self.assertTrue(resultat.message.strip())
        self.assertEqual(resultat.fichiers, ())


class ImportEtAdmissionTest(BaseVerificationTest):
    def test_import_sans_flask(self) -> None:
        code = (
            "import sys\n"
            "import transcription_bench.verification_modeles\n"
            "assert 'flask' not in sys.modules, 'Flask chargé par la vérification'\n"
            "print('ok')\n"
        )
        resultat = subprocess.run(
            [sys.executable, "-B", "-c", code],
            cwd=RACINE_PROJET,
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        self.assertEqual(resultat.returncode, 0, resultat.stderr)
        self.assertEqual(resultat.stdout.strip(), "ok")

    def test_aucun_client_cree_a_la_construction(self) -> None:
        appels: list[str] = []

        def fabrique() -> FauxClient:
            appels.append("appel")
            return FauxClient()

        service = VerificationModeles(
            self.registre, self.creneau, fabrique_client=fabrique
        )
        self.assertEqual(appels, [])
        self.assertIsNone(service.dernier_resultat())

    def test_entrees_invalides_refusees_avant_admission_et_sans_io(self) -> None:
        self.enregistrer(declaration_synthetique())
        faux = FauxClient()
        service = self.service(faux)
        cas = (
            ("identifiant", {"identifiant": "../secret", "moteur": "moteur-de-test"}),
            ("revision_vide", {"identifiant": "org/modele", "moteur": "moteur-de-test", "revision": " "}),
            ("revision_controle", {"identifiant": "org/modele", "moteur": "moteur-de-test", "revision": "a\nb"}),
            ("gguf_pour_ct2", {"identifiant": "org/modele", "moteur": "moteur-de-test", "fichier_gguf": "x.gguf"}),
            ("gguf_absolu", {"identifiant": "org/modele", "moteur": "moteur-de-test", "fichier_gguf": "/x.gguf"}),
        )
        for nom, arguments in cas:
            with self.subTest(cas=nom):
                with self.assertRaises(ValeurRefusee):
                    service.lancer(**arguments)
                self.assertEqual(faux.appels_infos, [])
                self.assertEqual(faux.ouvertures, [])
                self.assertEqual(self.creneau.instantane().etat, ETAT_LIBRE)

    def test_moteur_inconnu_refuse_avant_io(self) -> None:
        faux = FauxClient()
        service = self.service(faux)
        with self.assertRaises(MoteurInconnu):
            service.lancer("org/modele", "moteur-absent")
        self.assertEqual(faux.appels_infos, [])
        self.assertEqual(self.creneau.instantane().etat, ETAT_LIBRE)

    def test_moteur_sans_regle_de_verification_refuse_avant_io(self) -> None:
        self.enregistrer(
            declaration_synthetique(identifiant="sans-regle", regle="aucune")
        )
        faux = FauxClient()
        service = self.service(faux)
        with self.assertRaises(ValeurRefusee):
            service.lancer("org/modele", "sans-regle")
        self.assertEqual(faux.appels_infos, [])
        self.assertEqual(self.creneau.instantane().etat, ETAT_LIBRE)

    def test_creneau_occupe_par_execution_refuse_sans_io(self) -> None:
        self.enregistrer(declaration_synthetique())
        faux = FauxClient()
        service = self.service(faux)
        liberation = threading.Event()
        self.creneau.demarrer(
            TYPE_EXECUTION, lambda travailleur: liberation.wait(DELAI), cible="audio"
        )
        self.addCleanup(liberation.set)
        with self.assertRaises(CreneauOccupe):
            service.lancer("org/modele", "moteur-de-test")
        self.assertEqual(faux.appels_infos, [])
        liberation.set()
        thread = self.creneau.thread_travailleur
        thread.join(DELAI)
        self.assertFalse(thread.is_alive())

    def test_verification_occupe_le_creneau_et_refuse_une_execution(self) -> None:
        self.enregistrer(declaration_synthetique())
        bloque = ClientBloque(infos_de(CONTENUS_CTRANSLATE2), CONTENUS_CTRANSLATE2)
        service = self.service(bloque)
        service.lancer("org/modele", "moteur-de-test")
        self.assertTrue(bloque.debut.wait(DELAI), "vérification non démarrée")
        instantane = self.creneau.instantane()
        self.assertEqual(instantane.etat, ETAT_EN_COURS)
        self.assertEqual(instantane.type_operation, TYPE_VERIFICATION)
        with self.assertRaises(CreneauOccupe):
            self.creneau.demarrer(TYPE_EXECUTION, lambda travailleur: None)
        bloque.debloque.set()
        self.attendre()

    def test_service_arrete_refuse_sans_io(self) -> None:
        self.enregistrer(declaration_synthetique())
        faux = FauxClient()
        service = self.service(faux)
        self.creneau.arreter(0)
        with self.assertRaises(ServiceArrete):
            service.lancer("org/modele", "moteur-de-test")
        self.assertEqual(faux.appels_infos, [])
        self.assertEqual(faux.ouvertures, [])


class SuccesEtSelectionTest(BaseVerificationTest):
    def test_succes_ctranslate2_commit_tailles_et_fichiers_selectionnes(self) -> None:
        self.enregistrer(declaration_synthetique())
        faux = FauxClient(infos_de(CONTENUS_CTRANSLATE2), CONTENUS_CTRANSLATE2)
        service = self.service(faux)
        self.lancer_et_attendre(
            service,
            identifiant="org/modele",
            moteur="moteur-de-test",
            revision="main",
        )
        resultat = service.dernier_resultat()
        self.assertIsNotNone(resultat)
        assert resultat is not None
        self.assertTrue(resultat.accepte, resultat.message)
        self.assertEqual(resultat.famille, "whisper")
        self.assertEqual(resultat.commit, COMMIT)
        self.assertEqual(faux.appels_infos, [("org/modele", "main")])
        self.assertEqual(
            set(faux.ouvertures),
            {
                ("org/modele", COMMIT, "config.json"),
                ("org/modele", COMMIT, "preprocessor_config.json"),
            },
        )
        noms = {fichier.nom for fichier in resultat.fichiers}
        self.assertEqual(
            noms,
            {
                "config.json",
                "model.bin",
                "preprocessor_config.json",
                "tokenizer.json",
                "vocabulary.json",
            },
        )
        self.assertEqual(
            resultat.taille_totale,
            sum(len(CONTENUS_CTRANSLATE2[nom]) for nom in noms),
        )
        self.assertNotIn("model.safetensors.index.json", noms)
        self.assertNotIn("poids-ctranslate2-a-ne-pas-lire", str(faux.ouvertures))
        with self.assertRaises(dataclasses.FrozenInstanceError):
            resultat.accepte = False  # type: ignore[misc]

    def test_tailles_manquantes_ne_sont_pas_inventees(self) -> None:
        self.enregistrer(declaration_synthetique())
        infos = infos_de(
            CONTENUS_CTRANSLATE2, tailles={"model.bin": None}
        )
        faux = FauxClient(infos, CONTENUS_CTRANSLATE2)
        service = self.service(faux)
        self.lancer_et_attendre(
            service, identifiant="org/modele", moteur="moteur-de-test"
        )
        resultat = service.dernier_resultat()
        self.assertIsNotNone(resultat)
        assert resultat is not None
        self.assertTrue(resultat.accepte, resultat.message)
        self.assertIsNone(resultat.taille_totale)
        tailles = {fichier.nom: fichier.taille for fichier in resultat.fichiers}
        self.assertIsNone(tailles["model.bin"])
        self.assertNotIn(0, [taille for taille in tailles.values() if taille is not None])

    def test_grande_configuration_sous_la_borne_est_acceptee(self) -> None:
        self.enregistrer(
            declaration_synthetique(
                identifiant="transformers-test",
                regle=REGLE_TRANSFORMERS_SAFETENSORS,
            )
        )
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
        contenus = dict(CONTENUS_TRANSFORMERS)
        contenus["tokenizer_config.json"] = json.dumps(
            {"tokenizer_class": "WhisperTokenizer", "added_tokens_decoder": jetons}
        ).encode()
        self.assertGreater(len(contenus["tokenizer_config.json"]), 100_000)
        faux = FauxClient(infos_de(contenus), contenus)
        service = self.service(faux)
        self.lancer_et_attendre(
            service, identifiant="org/modele", moteur="transformers-test"
        )
        resultat = service.dernier_resultat()
        self.assertIsNotNone(resultat)
        assert resultat is not None
        self.assertTrue(resultat.accepte, resultat.message)
        self.assertIn(
            ("org/modele", COMMIT, "tokenizer_config.json"), faux.ouvertures
        )

    def test_depot_transformers_mixte_ne_lit_aucun_poids(self) -> None:
        self.enregistrer(
            declaration_synthetique(
                identifiant="transformers-test",
                regle=REGLE_TRANSFORMERS_SAFETENSORS,
            )
        )
        faux = FauxClient(infos_de(CONTENUS_TRANSFORMERS), CONTENUS_TRANSFORMERS)
        service = self.service(faux)
        self.lancer_et_attendre(
            service, identifiant="org/modele", moteur="transformers-test"
        )
        resultat = service.dernier_resultat()
        self.assertIsNotNone(resultat)
        assert resultat is not None
        self.assertTrue(resultat.accepte, resultat.message)
        noms = {fichier.nom for fichier in resultat.fichiers}
        self.assertIn("model.safetensors", noms)
        self.assertNotIn("pytorch_model.bin", noms)
        self.assertNotIn("modele.nemo", noms)
        self.assertNotIn("modele.gguf", noms)
        self.assertNotIn("modele.onnx", noms)
        self.assertNotIn("modele.h5", noms)
        self.assertEqual(
            {nom for _, _, nom in faux.ouvertures},
            {
                "config.json",
                "generation_config.json",
                "preprocessor_config.json",
                "tokenizer_config.json",
            },
        )
        self.assertEqual(
            resultat.taille_totale,
            sum(len(CONTENUS_TRANSFORMERS[nom]) for nom in noms),
        )


class RefusEtErreursTest(BaseVerificationTest):
    def test_json_trop_volumineux_refuse_sans_lecture(self) -> None:
        self.enregistrer(
            declaration_synthetique(
                identifiant="transformers-test",
                regle=REGLE_TRANSFORMERS_SAFETENSORS,
            )
        )
        infos = infos_de(
            CONTENUS_TRANSFORMERS,
            tailles={"config.json": OCTETS_MAX_JSON + 1},
        )
        faux = FauxClient(infos, CONTENUS_TRANSFORMERS)
        service = self.service(faux)
        self.lancer_et_attendre(
            service, identifiant="org/modele", moteur="transformers-test"
        )
        resultat = service.dernier_resultat()
        self.assert_refus(resultat, RAISON_FICHIER_TROP_VOLUMINEUX)
        self.assertEqual(faux.ouvertures, [])

    def test_commit_non_hexadecimal_refuse_sans_ouverture(self) -> None:
        self.enregistrer(declaration_synthetique())
        for commit in ("main", "z" * 40, COMMIT[:-1]):
            with self.subTest(commit=commit):
                faux = FauxClient(
                    infos_de(CONTENUS_CTRANSLATE2, commit=commit),
                    CONTENUS_CTRANSLATE2,
                )
                service = self.service(faux)
                self.lancer_et_attendre(
                    service, identifiant="org/modele", moteur="moteur-de-test"
                )
                resultat = service.dernier_resultat()
                self.assert_refus(resultat, RAISON_COMMIT_INVALIDE)
                self.assertEqual(faux.ouvertures, [])

    def test_erreur_client_et_erreur_inattendue_ne_divulguent_aucun_secret(self) -> None:
        self.enregistrer(declaration_synthetique())
        cas = (
            (
                "acces",
                ErreurClientModeles(RAISON_ACCES_REFUSE),
                RAISON_ACCES_REFUSE,
            ),
            (
                "inattendue",
                RuntimeError(f"{SECRET_FACTICE} https://exemple/?token={SECRET_FACTICE}"),
                RAISON_ERREUR_INATTENDUE,
            ),
        )
        for nom, erreur, raison in cas:
            with self.subTest(cas=nom):
                faux = FauxClient(erreur_infos=erreur)
                service = self.service(faux)
                self.lancer_et_attendre(
                    service, identifiant="org/modele", moteur="moteur-de-test"
                )
                resultat = service.dernier_resultat()
                self.assert_refus(resultat, raison)
                assert resultat is not None
                instantane = self.creneau.instantane()
                textes = [
                    resultat.message,
                    *instantane.journal,
                    instantane.erreur or "",
                ]
                for texte in textes:
                    self.assertNotIn(SECRET_FACTICE, texte)
                self.assertEqual(instantane.etat, ETAT_TERMINEE)

    def test_nom_fichier_hostile_refuse_avant_toute_ouverture(self) -> None:
        self.enregistrer(declaration_synthetique())
        infos = InfosModele(
            commit=COMMIT,
            fichiers=(
                FichierDistant("config.json", 2),
                FichierDistant("../evil.json", 2),
            ),
        )
        faux = FauxClient(infos, {"config.json": b"{}"})
        service = self.service(faux)
        self.lancer_et_attendre(
            service, identifiant="org/modele", moteur="moteur-de-test"
        )
        resultat = service.dernier_resultat()
        self.assert_refus(resultat, RAISON_NOM_FICHIER_REFUSE)
        assert resultat is not None
        self.assertEqual(resultat.commit, COMMIT)
        self.assertEqual(faux.ouvertures, [])

    def test_declaration_reelle_non_qualifiee_reste_refusee(self) -> None:
        self.enregistrer(DECLARATION_FASTER_WHISPER)
        faux = FauxClient(infos_de(CONTENUS_CTRANSLATE2), CONTENUS_CTRANSLATE2)
        service = self.service(faux)
        self.lancer_et_attendre(
            service, identifiant="org/modele", moteur="faster-whisper"
        )
        resultat = service.dernier_resultat()
        self.assert_refus(resultat, RAISON_FAMILLE_NON_QUALIFIEE)
        assert resultat is not None
        self.assertEqual(resultat.famille, "whisper")
        self.assertEqual(resultat.commit, COMMIT)
        for declaration in declarations_fournies():
            if declaration.factice:
                continue
            self.assertTrue(
                all(not famille.qualifiee for famille in declaration.familles)
            )


class GgufTest(BaseVerificationTest):
    def test_plusieurs_gguf_sans_choix_refuses_et_candidats_proposes(self) -> None:
        self.enregistrer(
            declaration_synthetique(
                identifiant="transcribe-test", regle=REGLE_TRANSCRIBE_CPP_GGUF
            )
        )
        infos = InfosModele(
            commit=COMMIT,
            fichiers=(
                FichierDistant("modele-f16.gguf", 10),
                FichierDistant("modele-q8_0.gguf", 20),
                FichierDistant("README.md", 5),
            ),
        )
        faux = FauxClient(infos)
        service = self.service(faux)
        self.lancer_et_attendre(
            service, identifiant="org/modele", moteur="transcribe-test"
        )
        resultat = service.dernier_resultat()
        self.assert_refus(resultat, RAISON_FICHIER_GGUF_NON_CHOISI)
        assert resultat is not None
        self.assertEqual(
            resultat.gguf_candidats, ("modele-f16.gguf", "modele-q8_0.gguf")
        )
        self.assertEqual(resultat.commit, COMMIT)
        self.assertEqual(faux.ouvertures, [])

    def test_gguf_choisi_inconnu_refuse_avant_toute_ouverture(self) -> None:
        self.enregistrer(
            declaration_synthetique(
                identifiant="transcribe-test", regle=REGLE_TRANSCRIBE_CPP_GGUF
            )
        )
        infos = InfosModele(
            commit=COMMIT,
            fichiers=(
                FichierDistant("modele-f16.gguf", 10),
                FichierDistant("modele-q8_0.gguf", 20),
            ),
        )
        faux = FauxClient(infos)
        service = self.service(faux)
        self.lancer_et_attendre(
            service,
            identifiant="org/modele",
            moteur="transcribe-test",
            fichier_gguf="modele-q4_0.gguf",
        )
        self.assert_refus(service.dernier_resultat(), RAISON_FICHIER_GGUF_NON_CHOISI)
        self.assertEqual(faux.ouvertures, [])

    def test_gguf_lit_seulement_l_entete_et_ignore_les_poids_sentinelle(self) -> None:
        self.enregistrer(
            declaration_synthetique(
                identifiant="transcribe-test", regle=REGLE_TRANSCRIBE_CPP_GGUF
            )
        )
        entete = entete_gguf(("general.architecture", "string", "whisper"))
        sentinelle = b"SENTINELLE-POIDS-" * 200_000
        contenu = entete + sentinelle
        infos = InfosModele(
            commit=COMMIT,
            fichiers=(
                FichierDistant("modele-f16.gguf", 100),
                FichierDistant("modele-q8_0.gguf", len(contenu)),
                FichierDistant("config.json", OCTETS_MAX_JSON + 1),
                FichierDistant("model.safetensors.index.json", 1024),
            ),
        )
        faux = FauxClient(
            infos,
            {
                "modele-q8_0.gguf": contenu,
                "config.json": b"{}",
                "model.safetensors.index.json": b"{}",
            },
        )
        service = self.service(faux)
        self.lancer_et_attendre(
            service,
            identifiant="org/modele",
            moteur="transcribe-test",
            fichier_gguf="modele-q8_0.gguf",
        )
        resultat = service.dernier_resultat()
        self.assertIsNotNone(resultat)
        assert resultat is not None
        self.assertTrue(resultat.accepte, resultat.message)
        self.assertEqual(resultat.fichier_gguf, "modele-q8_0.gguf")
        self.assertEqual(resultat.famille, "whisper")
        self.assertEqual(
            resultat.gguf_candidats, ("modele-f16.gguf", "modele-q8_0.gguf")
        )
        self.assertEqual(
            [nom for _, _, nom in faux.ouvertures], ["modele-q8_0.gguf"]
        )
        octets_lus = sum(taille for _, taille in faux.lectures)
        self.assertEqual(octets_lus, len(entete))
        self.assertLess(octets_lus, len(contenu))

    def test_gguf_architecture_reconnue_mais_famille_non_qualifiee(self) -> None:
        self.enregistrer(DECLARATION_TRANSCRIBE_CPP)
        entete = entete_gguf(("general.architecture", "string", "whisper"))
        infos = InfosModele(
            commit=COMMIT, fichiers=(FichierDistant("modele-q8_0.gguf", len(entete)),)
        )
        faux = FauxClient(infos, {"modele-q8_0.gguf": entete})
        service = self.service(faux)
        self.lancer_et_attendre(
            service, identifiant="org/modele", moteur="transcribe-cpp"
        )
        resultat = service.dernier_resultat()
        self.assert_refus(resultat, RAISON_FAMILLE_NON_QUALIFIEE)
        assert resultat is not None
        self.assertEqual(resultat.famille, "whisper")
        self.assertEqual(resultat.gguf_candidats, ("modele-q8_0.gguf",))


class ArretEtPublicationTest(BaseVerificationTest):
    def test_resultat_non_publie_apres_arret(self) -> None:
        self.enregistrer(declaration_synthetique())
        bloque = ClientBloque(infos_de(CONTENUS_CTRANSLATE2), CONTENUS_CTRANSLATE2)
        service = self.service(bloque)
        service.lancer("org/modele", "moteur-de-test")
        self.assertTrue(bloque.debut.wait(DELAI), "vérification non démarrée")
        fini = self.creneau.arreter(0.1)
        self.assertFalse(fini, "le thread bloqué ne devrait pas être terminé")
        bloque.debloque.set()
        self.attendre()
        self.assertIsNone(service.dernier_resultat())
        journal = "\n".join(self.creneau.instantane().journal)
        self.assertIn("Résultat non publié", journal)


def intervalle_range(request: httpx2.Request) -> tuple[int, int] | None:
    """Intervalle demandé par un GET Range, ou None si le GET est complet."""
    valeur = request.headers.get("range")
    if valeur is None:
        return None
    correspondance = re.fullmatch(r"bytes=(\d+)-(\d+)", valeur)
    if correspondance is None:
        return None
    debut, fin = int(correspondance.group(1)), int(correspondance.group(2))
    if debut < 0 or fin < debut:
        return None
    return debut, fin


def reponse_range(request: httpx2.Request, contenu: bytes) -> httpx2.Response:
    """Réponse 206 exacte ; un GET sans Range est refusé pour prouver l'absence de flux entier."""
    intervalle = intervalle_range(request)
    if intervalle is None:
        return httpx2.Response(400, text="GET sans Range refusé")
    debut, fin = intervalle
    if debut >= len(contenu):
        return httpx2.Response(416)
    fin = min(fin, len(contenu) - 1)
    return httpx2.Response(
        206,
        content=contenu[debut : fin + 1],
        headers={"Content-Range": f"bytes {debut}-{fin}/{len(contenu)}"},
    )


class ContexteEspion:
    """Enveloppe un vrai contexte HfFileSystem et relève les lectures applicatives."""

    def __init__(self, contexte, journal: list[int]) -> None:
        self._contexte = contexte
        self._journal = journal
        self._flux = None

    def __enter__(self):
        self._flux = self._contexte.__enter__()
        return self

    def read(self, taille: int) -> bytes:
        self._journal.append(taille)
        return self._flux.read(taille)

    def __exit__(self, exc_type, exc, traceback):
        return self._contexte.__exit__(exc_type, exc, traceback)


class ClientEspion(ClientHuggingFace):
    """Client réel dont seules les lectures sont relevées, sans remplacer le transport."""

    def __init__(self, journal: list[int]) -> None:
        super().__init__()
        self._journal = journal

    def ouvrir_fichier(self, identifiant: str, commit: str, nom: str):
        return ContexteEspion(
            super().ouvrir_fichier(identifiant, commit, nom), self._journal
        )


class ClientHuggingFaceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.addCleanup(self._restaurer_client)

    def _restaurer_client(self) -> None:
        set_client_factory(httpx2.Client)
        close_session()

    def _installer_transport(self, handler) -> None:
        set_client_factory(
            lambda: httpx2.Client(
                transport=httpx2.MockTransport(handler), follow_redirects=True
            )
        )
        close_session()

    def test_api_publique_appelee_avec_les_parametres_attendus(self) -> None:
        api = mock.Mock()
        api.model_info.return_value = SimpleNamespace(
            id="org/modele",
            sha=COMMIT,
            siblings=[SimpleNamespace(rfilename="config.json", size=2)],
        )
        systeme = mock.Mock()
        flux = io.BytesIO(b"ok")
        systeme.open.return_value = nullcontext(flux)
        with mock.patch(
            "transcription_bench.verification_modeles.HfApi", return_value=api
        ), mock.patch(
            "transcription_bench.verification_modeles.HfFileSystem",
            return_value=systeme,
        ):
            client = ClientHuggingFace()
            infos = client.informations("org/modele", "main")
            with client.ouvrir_fichier("org/modele", COMMIT, "config.json") as lecture:
                self.assertEqual(lecture.read(), b"ok")
        api.model_info.assert_called_once_with(
            "org/modele",
            revision="main",
            files_metadata=True,
            timeout=DELAI_MODELE_INFO,
        )
        self.assertNotIn("token", api.model_info.call_args.kwargs)
        systeme.open.assert_called_once_with(
            "org/modele/config.json",
            "rb",
            revision=COMMIT,
            block_size=TAILLE_BLOC,
            cache_type="none",
        )
        self.assertEqual(infos.commit, COMMIT)
        self.assertEqual(infos.id_resolu, "org/modele")
        self.assertEqual(infos.fichiers, (FichierDistant("config.json", 2),))

    def test_erreurs_reelles_traduites_en_categories_fixes_sans_secret(self) -> None:
        def handler_repo(request):
            if request.url.path.startswith("/api/models/"):
                return httpx2.Response(
                    404, headers={"X-Error-Code": "RepoNotFound"}, text=SECRET_FACTICE
                )
            return httpx2.Response(404)

        def handler_gated(request):
            if request.url.path.startswith("/api/models/"):
                return httpx2.Response(
                    403, headers={"X-Error-Code": "GatedRepo"}, text=SECRET_FACTICE
                )
            return httpx2.Response(404)

        def handler_revision(request):
            if request.url.path.startswith("/api/models/"):
                return httpx2.Response(
                    404,
                    headers={"X-Error-Code": "RevisionNotFound"},
                    text=SECRET_FACTICE,
                )
            return httpx2.Response(404)

        def handler_reseau(request):
            raise httpx2.ConnectError(f"{SECRET_FACTICE} https://exemple/?token=x")

        cas = (
            ("repo", handler_repo, RAISON_ACCES_REFUSE),
            ("gated", handler_gated, RAISON_ACCES_REFUSE),
            ("revision", handler_revision, RAISON_REVISION_INCONNUE),
            ("reseau", handler_reseau, RAISON_RESEAU_INDISPONIBLE),
        )
        for nom, handler, raison in cas:
            with self.subTest(cas=nom):
                self._installer_transport(handler)
                with self.assertRaises(ErreurClientModeles) as contexte:
                    ClientHuggingFace().informations("org/modele", "main")
                self.assertEqual(contexte.exception.raison, raison)
                self.assertNotIn(SECRET_FACTICE, str(contexte.exception))

    def test_erreur_hub_generique_traduite_sans_secret(self) -> None:
        def handler(request):
            if request.url.path.startswith("/api/models/"):
                return httpx2.Response(500, text=SECRET_FACTICE)
            return httpx2.Response(404)

        self._installer_transport(handler)
        with self.assertRaises(ErreurClientModeles) as contexte:
            ClientHuggingFace().informations("org/modele", "main")
        self.assertEqual(contexte.exception.raison, RAISON_ERREUR_HUB)
        self.assertNotIn(SECRET_FACTICE, str(contexte.exception))
        self.assertIn(RAISON_ERREUR_HUB, MESSAGES_ERREUR)
        self.assertIn(RAISON_FICHIER_ILLISIBLE, MESSAGES_ERREUR)

    def test_client_reel_avec_transport_simule_bout_en_bout(self) -> None:
        contenus = {
            nom: contenu
            for nom, contenu in CONTENUS_TRANSFORMERS.items()
            if nom
            in {
                "config.json",
                "generation_config.json",
                "preprocessor_config.json",
                "tokenizer_config.json",
                "tokenizer.json",
                "model.safetensors",
            }
        }
        requetes: list[httpx2.Request] = []
        siblings = [
            {"rfilename": nom, "size": len(contenu)}
            for nom, contenu in contenus.items()
        ]

        def handler(request: httpx2.Request) -> httpx2.Response:
            requetes.append(request)
            chemin = request.url.path
            if chemin.startswith("/api/models/org/modele/tree/"):
                return httpx2.Response(
                    200,
                    json=[
                        {
                            "type": "file",
                            "path": nom,
                            "size": len(contenu),
                            "oid": "b" * 40,
                        }
                        for nom, contenu in contenus.items()
                    ],
                )
            if chemin.startswith("/api/models/org/modele"):
                return httpx2.Response(
                    200, json={"id": "org/modele", "sha": COMMIT, "siblings": siblings}
                )
            if chemin.startswith("/org/modele/resolve/"):
                nom = chemin.rsplit("/", 1)[-1]
                if nom in contenus:
                    return reponse_range(request, contenus[nom])
            return httpx2.Response(404, headers={"X-Error-Code": "EntryNotFound"})

        self._installer_transport(handler)
        creneau = CreneauOperations()
        registre = RegistreMoteurs()
        registre.enregistrer(
            DeclarationAdaptateur(
                identifiant="transformers-test",
                nom="Transformers de test",
                fichier_requirements=None,
                regle_compatibilite=REGLE_TRANSFORMERS_SAFETENSORS,
                familles=(Famille("whisper", "Whisper", qualifiee=True),),
            )
        )
        service = VerificationModeles(registre, creneau)
        service.lancer(
            "org/modele", "transformers-test", revision="main"
        )
        thread = creneau.thread_travailleur
        self.assertIsNotNone(thread)
        thread.join(DELAI)
        self.assertFalse(thread.is_alive())
        resultat = service.dernier_resultat()
        self.assertIsNotNone(resultat)
        assert resultat is not None
        self.assertTrue(resultat.accepte, resultat.message)
        self.assertEqual(resultat.commit, COMMIT)
        urls = [str(requete.url) for requete in requetes]
        self.assertTrue(
            any("blobs=true" in url or "blobs=True" in url for url in urls), urls
        )
        fichiers_lus = [
            url
            for url in urls
            if "/resolve/" in url
        ]
        self.assertTrue(fichiers_lus, urls)
        self.assertTrue(
            all(f"/resolve/{COMMIT}/" in url for url in fichiers_lus), fichiers_lus
        )
        self.assertFalse(any("model.safetensors" in url for url in urls), urls)
        self.assertFalse(any(url.endswith("/tokenizer.json") for url in urls), urls)
        self.assertFalse(any(SECRET_FACTICE in url for url in urls), urls)
        intervalles = [
            intervalle_range(requete)
            for requete in requetes
            if "/resolve/" in str(requete.url)
        ]
        self.assertTrue(intervalles)
        self.assertTrue(all(intervalle is not None for intervalle in intervalles))
        self.assertTrue(
            all(
                fin - debut + 1 <= TAILLE_BLOC
                for debut, fin in (
                    intervalle for intervalle in intervalles if intervalle is not None
                )
            )
        )

    def test_gguf_reel_avec_transport_simule_ne_lit_pas_les_poids(self) -> None:
        entete = entete_gguf(("general.architecture", "string", "whisper"))
        sentinelle = b"SENTINELLE-POIDS-" * 200_000
        contenu = entete + sentinelle
        requetes: list[httpx2.Request] = []
        lectures: list[int] = []
        servis: list[int] = []

        def handler(request: httpx2.Request) -> httpx2.Response:
            requetes.append(request)
            chemin = request.url.path
            if chemin.startswith("/api/models/org/modele/tree/"):
                return httpx2.Response(
                    200,
                    json=[
                        {
                            "type": "file",
                            "path": "modele-q8_0.gguf",
                            "size": len(contenu),
                            "oid": "c" * 40,
                        }
                    ],
                )
            if chemin.startswith("/api/models/org/modele"):
                return httpx2.Response(
                    200,
                    json={
                        "id": "org/modele",
                        "sha": COMMIT,
                        "siblings": [
                            {"rfilename": "modele-q8_0.gguf", "size": len(contenu)}
                        ],
                    },
                )
            if chemin == f"/org/modele/resolve/{COMMIT}/modele-q8_0.gguf":
                intervalle = intervalle_range(request)
                if intervalle is None or intervalle[1] >= len(entete):
                    return httpx2.Response(400, text="lecture au-delà de l'en-tête")
                servis.append(intervalle[1] - intervalle[0] + 1)
                return reponse_range(request, contenu)
            return httpx2.Response(404, headers={"X-Error-Code": "EntryNotFound"})

        self._installer_transport(handler)
        creneau = CreneauOperations()
        registre = RegistreMoteurs()
        registre.enregistrer(
            DeclarationAdaptateur(
                identifiant="transcribe-test",
                nom="Transcribe de test",
                fichier_requirements=None,
                regle_compatibilite=REGLE_TRANSCRIBE_CPP_GGUF,
                familles=(Famille("whisper", "Whisper", qualifiee=True),),
            )
        )
        service = VerificationModeles(registre, creneau, client=ClientEspion(lectures))
        service.lancer(
            "org/modele",
            "transcribe-test",
            fichier_gguf="modele-q8_0.gguf",
        )
        thread = creneau.thread_travailleur
        self.assertIsNotNone(thread)
        thread.join(DELAI)
        self.assertFalse(thread.is_alive())
        resultat = service.dernier_resultat()
        self.assertIsNotNone(resultat)
        assert resultat is not None
        self.assertTrue(resultat.accepte, resultat.message)
        self.assertEqual(resultat.commit, COMMIT)
        self.assertEqual(resultat.fichier_gguf, "modele-q8_0.gguf")
        self.assertEqual(resultat.taille_totale, len(contenu))
        self.assertEqual(sum(lectures), len(entete))
        self.assertEqual(sum(servis), len(entete))
        self.assertTrue(all(taille <= TAILLE_BLOC for taille in servis))
        self.assertLess(sum(lectures), len(contenu))
        urls = [str(requete.url) for requete in requetes]
        self.assertIn(
            f"https://huggingface.co/org/modele/resolve/{COMMIT}/modele-q8_0.gguf",
            urls,
        )

    def test_identifiant_bare_utilise_l_id_canonique_renvoye_par_l_api(self) -> None:
        entete = entete_gguf(("general.architecture", "string", "whisper"))
        requetes: list[httpx2.Request] = []

        def handler(request: httpx2.Request) -> httpx2.Response:
            requetes.append(request)
            chemin = request.url.path
            if chemin.startswith("/api/models/openai-community/gpt2/tree/"):
                return httpx2.Response(
                    200,
                    json=[
                        {
                            "type": "file",
                            "path": "modele.gguf",
                            "size": len(entete),
                            "oid": "d" * 40,
                        }
                    ],
                )
            if chemin.startswith("/api/models/"):
                return httpx2.Response(
                    200,
                    json={
                        "id": "openai-community/gpt2",
                        "sha": COMMIT,
                        "siblings": [{"rfilename": "modele.gguf", "size": len(entete)}],
                    },
                )
            if chemin == (
                f"/openai-community/gpt2/resolve/{COMMIT}/modele.gguf"
            ):
                return reponse_range(request, entete)
            return httpx2.Response(404, headers={"X-Error-Code": "EntryNotFound"})

        self._installer_transport(handler)
        creneau = CreneauOperations()
        registre = RegistreMoteurs()
        registre.enregistrer(
            DeclarationAdaptateur(
                identifiant="transcribe-test",
                nom="Transcribe de test",
                fichier_requirements=None,
                regle_compatibilite=REGLE_TRANSCRIBE_CPP_GGUF,
                familles=(Famille("whisper", "Whisper", qualifiee=True),),
            )
        )
        service = VerificationModeles(registre, creneau)
        service.lancer("gpt2", "transcribe-test", fichier_gguf="modele.gguf")
        thread = creneau.thread_travailleur
        self.assertIsNotNone(thread)
        thread.join(DELAI)
        self.assertFalse(thread.is_alive())
        resultat = service.dernier_resultat()
        self.assertIsNotNone(resultat)
        assert resultat is not None
        self.assertTrue(resultat.accepte, resultat.message)
        self.assertEqual(resultat.identifiant, "gpt2")
        self.assertEqual(resultat.id_resolu, "openai-community/gpt2")
        self.assertEqual(resultat.commit, COMMIT)
        urls = [str(requete.url) for requete in requetes]
        self.assertIn(
            f"https://huggingface.co/openai-community/gpt2/resolve/{COMMIT}/modele.gguf",
            urls,
        )
        self.assertFalse(
            any(url.startswith("https://huggingface.co/gpt2/resolve/") for url in urls),
            urls,
        )
        for requete in requetes:
            if "/resolve/" in str(requete.url):
                self.assertIsNotNone(intervalle_range(requete))
