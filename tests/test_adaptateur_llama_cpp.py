"""Tests de l'adaptateur llama.cpp, sans importer la bibliothèque réelle.

Le module `llama_cpp` (et son sous-module `llama_grammar`) est remplacé par
une doublure injectée dans `sys.modules` : un vocabulaire fictif de 12 tokens,
un token de fin (id 8), un tokenizer déterministe (un token par caractère) et
des compteurs natifs qui ne s'engagent qu'à l'échantillonnage, comme mesuré à
l'essai minimal 0.1. Ces tests ne constituent donc aucune validation PC : la
bibliothèque réelle est couverte par la qualification (tâches 6.x).

La doublure refuse par ailleurs tout accès à la classe `Llama` : un appel
interdit fait échouer le test, pas seulement la génération.
"""

from __future__ import annotations

import ctypes
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest import mock

from engines.adaptateurs import llama_cpp
from engines.protocole import (
    TYPE_CHARGEMENT,
    TYPE_EXTRACTION_ERREUR,
    TYPE_FIN,
    ErreurContexteInsuffisant,
    analyser_ligne,
)
from transcription_bench.compatibilite_modeles import ARCHITECTURES_LLAMA_CPP
from transcription_bench.paths import RACINE_PROJET

#: Vocabulaire fictif : un token par caractère, plus un token de fin (id 8).
N_VOCAB = 12
ALPHABET = "abcdefghijkl"
JETON_EOG = 8


def _etat_defaut() -> dict[str, object]:
    """État pilotable de la doublure, remis à neuf par chaque test."""
    return {
        "architecture": "mistral3",
        "gabarit": "[INST] gabarit embarqué [/INST]",
        "mode_grammaire": "constraine",
        "erreur_conversion": None,
        "echantillons": [0, 1, JETON_EOG],
        "appels": [],
        "libere": [],
        "clear_appels": [],
        "reset_appels": 0,
        "log_set": [],
        "tokenisations": [],
        "conversions": [],
        "decodes": 0,
        "chaine_nulle": False,
        "greedy_nul": False,
        "echec_decode": False,
        "batches_crees": 0,
        "batches_liberes": 0,
        "params_modele": None,
        "params_contexte": None,
    }


class _Fabrique:
    """Construit la doublure de `llama_cpp` liée à un état pilotable."""

    def __init__(self, etat: dict[str, object]) -> None:
        self.etat = etat

    def module(self) -> tuple[ModuleType, ModuleType]:
        etat = self.etat
        module = ModuleType("llama_cpp")

        class llama_token_data(ctypes.Structure):
            _fields_ = [
                ("id", ctypes.c_int32),
                ("logit", ctypes.c_float),
                ("p", ctypes.c_float),
            ]

        llama_token_data_p = ctypes.POINTER(llama_token_data)

        class llama_token_data_array(ctypes.Structure):
            _fields_ = [
                ("data", llama_token_data_p),
                ("size", ctypes.c_size_t),
                ("selected", ctypes.c_int64),
                ("sorted", ctypes.c_bool),
            ]

        module.llama_token = ctypes.c_int32  # type: ignore[attr-defined]
        module.llama_token_data = llama_token_data  # type: ignore[attr-defined]
        module.llama_token_data_p = llama_token_data_p  # type: ignore[attr-defined]
        module.llama_token_data_array = llama_token_data_array  # type: ignore[attr-defined]
        module.llama_log_callback = lambda fonction: fonction  # type: ignore[attr-defined]

        def _journal(nom, **extra):
            entree = {"nom": nom}
            entree.update(extra)
            etat["appels"].append(entree)

        def llama_backend_init():
            _journal("llama_backend_init")

        def llama_log_set(rappel, donnee):
            etat["log_set"].append(rappel)

        def llama_model_default_params():
            params = SimpleNamespace(n_gpu_layers=-1)
            etat["params_modele"] = params
            return params

        def llama_model_load_from_file(chemin, params):
            _journal("llama_model_load_from_file", chemin=chemin.decode())
            # La bibliothèque réelle émet des journaux natifs pendant le
            # chargement : la doublure les reproduit via le rappel installé.
            if etat["log_set"]:
                etat["log_set"][-1](4, b"load_tensors: contenu natif qui ne doit jamais fuiter\n", None)
            return SimpleNamespace(
                meta={
                    "general.architecture": etat["architecture"],
                    "tokenizer.chat_template": etat["gabarit"],
                }
            )

        def llama_model_free(modele):
            etat["libere"].append("model")

        def llama_model_meta_val_str(modele, cle, tampon, taille):
            valeur = modele.meta.get(cle.decode())
            if valeur is None:
                return -1
            brut = valeur.encode("utf-8")
            if not tampon:
                return len(brut)
            tampon[: len(brut)] = brut
            return len(brut)

        def llama_model_get_vocab(modele):
            return SimpleNamespace(modele=modele)

        def llama_vocab_n_tokens(vocabulaire):
            return N_VOCAB

        def llama_vocab_is_eog(vocabulaire, jeton):
            return jeton == JETON_EOG

        def llama_context_default_params():
            params = SimpleNamespace(n_ctx=512, n_threads=1, n_threads_batch=1)
            etat["params_contexte"] = params
            return params

        def llama_init_from_model(modele, params):
            return SimpleNamespace(
                n_ctx=params.n_ctx,
                committed_p=0,
                committed_e=0,
                pending_p=0,
                pending_e=0,
                decodes=0,
            )

        def llama_n_ctx(contexte):
            return contexte.n_ctx

        def llama_free(contexte):
            etat["libere"].append("ctx")

        def llama_get_memory(contexte):
            return SimpleNamespace(contexte=contexte)

        def llama_memory_clear(memoire, donnees):
            etat["clear_appels"].append(bool(donnees))

        def llama_batch_init(nombre, embd, sequences):
            etat["batches_crees"] += 1
            return SimpleNamespace(
                n_tokens=0,
                token=[0] * nombre,
                pos=[0] * nombre,
                seq_id=[[0] for _ in range(nombre)],
                n_seq_id=[1] * nombre,
                logits=[0] * nombre,
            )

        def llama_batch_free(lot):
            etat["batches_liberes"] += 1

        def llama_decode(contexte, lot):
            contexte.decodes += 1
            etat["decodes"] += 1
            if etat["echec_decode"]:
                return -1
            jetons = list(lot.token[: lot.n_tokens])
            if len(jetons) > 1:
                contexte.pending_p += len(jetons)
            else:
                contexte.pending_e += 1
            return 0

        def llama_sampler_chain_default_params():
            return SimpleNamespace()

        def llama_sampler_chain_init(params):
            if etat["chaine_nulle"]:
                return None
            return SimpleNamespace(samplers=[])

        def llama_sampler_chain_add(chaine, echantillonneur):
            chaine.samplers.append(echantillonneur)

        def llama_sampler_init_greedy():
            if etat["greedy_nul"]:
                return None
            return SimpleNamespace(mode="greedy")

        def llama_sampler_init_grammar(vocabulaire, gbnf, racine):
            _journal(
                "llama_sampler_init_grammar",
                gbnf=gbnf.decode(),
                racine=racine.decode(),
            )
            mode = etat["mode_grammaire"]
            if mode == "nul":
                return None
            return SimpleNamespace(mode=mode)

        def llama_sampler_apply(echantillonneur, pointeur):
            _journal("llama_sampler_apply", mode=echantillonneur.mode)
            tableau = getattr(pointeur, "_obj", None) or pointeur.contents
            admis = {
                "constraine": {0},
                "repli": set(range(N_VOCAB)),
                "bloque_tout": set(),
            }[echantillonneur.mode]
            for indice in range(tableau.size):
                if indice not in admis:
                    tableau.data[indice].logit = float("-inf")

        def llama_sampler_reset(chaine):
            etat["reset_appels"] += 1

        def llama_sampler_free(echantillonneur):
            etat["libere"].append(
                "chaine" if hasattr(echantillonneur, "samplers") else "sampler"
            )

        def llama_sampler_sample(chaine, contexte, index):
            # Engagement différé mesuré à l'essai : les compteurs d'un décodage
            # ne s'engagent qu'à l'accès aux sorties, ici l'échantillonnage.
            contexte.committed_p += contexte.pending_p
            contexte.pending_p = 0
            contexte.committed_e += contexte.pending_e
            contexte.pending_e = 0
            echantillons = etat["echantillons"]
            if echantillons:
                return echantillons.pop(0)
            return JETON_EOG

        def llama_perf_context(contexte):
            return SimpleNamespace(
                n_p_eval=contexte.committed_p,
                n_eval=contexte.committed_e,
                t_p_eval_ms=0.0,
                t_eval_ms=0.0,
                n_reused=0,
            )

        def llama_tokenize(vocabulaire, brut, taille, tampon, maximum, special, analyse):
            etat["tokenisations"].append(
                (brut.decode("utf-8"), bool(special), bool(analyse))
            )
            jetons = [
                ALPHABET.index(caractere) if caractere in ALPHABET else 0
                for caractere in brut.decode("utf-8")
            ]
            if maximum == 0:
                return -len(jetons)
            for position, jeton in enumerate(jetons):
                tampon[position] = jeton
            return len(jetons)

        def llama_token_to_piece(vocabulaire, jeton, tampon, taille, gauche, special):
            jeton = jeton.value if hasattr(jeton, "value") else jeton
            piece = ALPHABET[jeton] if 0 <= jeton < N_VOCAB else ""
            tampon[: len(piece)] = piece.encode("utf-8")
            return len(piece)

        for nom, fonction in (
            ("llama_backend_init", llama_backend_init),
            ("llama_log_set", llama_log_set),
            ("llama_model_default_params", llama_model_default_params),
            ("llama_model_load_from_file", llama_model_load_from_file),
            ("llama_model_free", llama_model_free),
            ("llama_model_meta_val_str", llama_model_meta_val_str),
            ("llama_model_get_vocab", llama_model_get_vocab),
            ("llama_vocab_n_tokens", llama_vocab_n_tokens),
            ("llama_vocab_is_eog", llama_vocab_is_eog),
            ("llama_context_default_params", llama_context_default_params),
            ("llama_init_from_model", llama_init_from_model),
            ("llama_n_ctx", llama_n_ctx),
            ("llama_free", llama_free),
            ("llama_get_memory", llama_get_memory),
            ("llama_memory_clear", llama_memory_clear),
            ("llama_batch_init", llama_batch_init),
            ("llama_batch_free", llama_batch_free),
            ("llama_decode", llama_decode),
            ("llama_sampler_chain_default_params", llama_sampler_chain_default_params),
            ("llama_sampler_chain_init", llama_sampler_chain_init),
            ("llama_sampler_chain_add", llama_sampler_chain_add),
            ("llama_sampler_init_greedy", llama_sampler_init_greedy),
            ("llama_sampler_init_grammar", llama_sampler_init_grammar),
            ("llama_sampler_apply", llama_sampler_apply),
            ("llama_sampler_reset", llama_sampler_reset),
            ("llama_sampler_free", llama_sampler_free),
            ("llama_sampler_sample", llama_sampler_sample),
            ("llama_perf_context", llama_perf_context),
            ("llama_tokenize", llama_tokenize),
            ("llama_token_to_piece", llama_token_to_piece),
        ):
            setattr(module, nom, fonction)

        def _interdit(nom):
            raise AssertionError(f"liaison de haut niveau interdite : {nom}")

        def __getattr__(nom):
            if nom in ("Llama", "LlamaGrammar", "LlamaChatFormatter", "LlamaServer"):
                _interdit(nom)
            raise AttributeError(nom)

        module.__getattr__ = __getattr__  # type: ignore[attr-defined]

        grammaire = ModuleType("llama_cpp.llama_grammar")

        def json_schema_to_gbnf(schema):
            erreur = etat["erreur_conversion"]
            if erreur is not None:
                raise erreur
            etat["conversions"].append(schema)
            return 'root ::= "json"'

        grammaire.json_schema_to_gbnf = json_schema_to_gbnf  # type: ignore[attr-defined]
        return module, grammaire


SCHEMA_TEST = {
    "type": "object",
    "properties": {"qui": {"type": "string"}},
    "required": ["qui"],
}


class LlamaCppAdaptateurTest(unittest.TestCase):
    def setUp(self) -> None:
        self.etat = _etat_defaut()
        self.fabrique = _Fabrique(self.etat)
        self.dossier = tempfile.TemporaryDirectory()
        self.fichier = Path(self.dossier.name) / "modele.gguf"
        self.fichier.write_bytes(b"GGUF factice")

    def tearDown(self) -> None:
        self.dossier.cleanup()

    def _modele(self, **options) -> dict[str, object]:
        modele = {
            "identifiant": "org/modele",
            "revision": "abc",
            "chemin": str(self.fichier),
            "local_files_only": True,
            "trust_remote_code": False,
        }
        modele.update(options)
        return modele

    def _charger(self, **reglages):
        module, grammaire = self.fabrique.module()
        with mock.patch.dict(
            sys.modules, {"llama_cpp": module, "llama_cpp.llama_grammar": grammaire}
        ):
            moteur = llama_cpp.charger(
                self._modele(), 4, reglages, SCHEMA_TEST
            )
        return moteur

    def _extraire(self, moteur, messages=None, **reglages):
        messages = messages or [
            {"role": "system", "content": "consignes"},
            {"role": "user", "content": "transcription"},
        ]
        reglages_complets = {"contexte": 512, "sortie_max": 64}
        reglages_complets.update(reglages)
        return llama_cpp.extraire(moteur, messages, reglages_complets)

    # -- Chargement et sonde -------------------------------------------------

    def test_chargement_bas_niveau_et_meta(self) -> None:
        moteur = self._charger(contexte=1024)

        self.assertEqual(self.etat["params_modele"].n_gpu_layers, 0)
        self.assertEqual(self.etat["params_contexte"].n_ctx, 1024)
        self.assertEqual(self.etat["params_contexte"].n_threads, 4)
        self.assertEqual(self.etat["params_contexte"].n_threads_batch, 4)
        self.assertEqual(moteur["contexte"], 1024)
        self.assertEqual(len(moteur["chaine"].samplers), 2)
        self.assertGreater(moteur["gbnf_octets"], 0)
        # Le schéma est passé au convertisseur du paquet, racine "root".
        conversion = json.loads(self.etat["conversions"][0])
        self.assertEqual(conversion, SCHEMA_TEST)
        grammaire = next(
            appel
            for appel in self.etat["appels"]
            if appel["nom"] == "llama_sampler_init_grammar"
        )
        self.assertEqual(grammaire["racine"], "root")
        self.assertIn("root", grammaire["gbnf"])
        # Le gabarit embarqué est lu comme texte et empreinté, jamais exécuté.
        meta = moteur["meta_chargement"]
        self.assertEqual(
            meta,
            {
                "threads_appliques": 4,
                "mode_chargement_poids": "mmap",
                "architecture": "mistral3",
                "sha256_gabarit_embarque": meta["sha256_gabarit_embarque"],
                "version_format": 1,
                "decodage": "glouton",
                "graine": None,
            },
        )
        self.assertRegex(meta["sha256_gabarit_embarque"], r"^[0-9a-f]{64}$")

    def test_sha256_gabarit_embarque_calcule(self) -> None:
        import hashlib

        moteur = self._charger()

        attendu = hashlib.sha256(
            str(self.etat["gabarit"]).encode("utf-8")
        ).hexdigest()
        self.assertEqual(
            moteur["meta_chargement"]["sha256_gabarit_embarque"], attendu
        )

    def test_log_set_installe_un_rappel_neutralise(self) -> None:
        self._charger()

        self.assertEqual(len(self.etat["log_set"]), 1)
        self.assertTrue(callable(self.etat["log_set"][0]))

    def test_rappel_journal_conserve_au_niveau_module(self) -> None:
        # Le C peut appeler le rappel bien après le retour de `charger` : une
        # référence locale seule serait libérée et ferait tomber le processus.
        # La doublure ne doit plus masquer le défaut en gardant le rappel
        # elle-même : la preuve est la liste de niveau module de l'adaptateur.
        moteur = self._charger()

        rappel = self.etat["log_set"][0]
        self.assertEqual(len(llama_cpp._RAPPEL_JOURNAL_ACTIF), 1)
        self.assertIs(llama_cpp._RAPPEL_JOURNAL_ACTIF[0], rappel)
        del moteur

        # Une seconde installation remplace la précédente, sans en garder deux.
        self._charger()
        self.assertEqual(len(llama_cpp._RAPPEL_JOURNAL_ACTIF), 1)
        self.assertIs(llama_cpp._RAPPEL_JOURNAL_ACTIF[0], self.etat["log_set"][-1])

    def test_journaux_natifs_neutralises_run_log_sans_texte(self) -> None:
        # La doublure émet un message natif pendant le chargement : le rappel
        # installé ne doit rien écrire — run.log ne reçoit jamais de contenu
        # natif (design D7), pas même un fragment court de texte recopié.
        erreurs = io.StringIO()
        module, grammaire = self.fabrique.module()
        with mock.patch.dict(
            sys.modules, {"llama_cpp": module, "llama_cpp.llama_grammar": grammaire}
        ), redirect_stderr(erreurs):
            llama_cpp.charger(self._modele(), 4, {"contexte": 512}, SCHEMA_TEST)

        self.assertEqual(erreurs.getvalue(), "")
        # Le rappel reste silencieux même appelé directement après installation.
        llama_cpp._RAPPEL_JOURNAL_ACTIF[0](4, b"avertissement natif\n", None)
        self.assertEqual(erreurs.getvalue(), "")

    def test_chaine_nulle_refusee_sans_fuite(self) -> None:
        self.etat["chaine_nulle"] = True

        with self.assertRaises(RuntimeError) as capture:
            self._charger()

        self.assertIn("llama_sampler_chain_init", str(capture.exception))
        # L'échantillonneur de grammaire n'a pas encore été adopté par la
        # chaîne : sa libération reste à la charge de l'adaptateur.
        self.assertIn("sampler", self.etat["libere"])
        self.assertIn("ctx", self.etat["libere"])
        self.assertIn("model", self.etat["libere"])
        self.assertNotIn("chaine", self.etat["libere"])

    def test_glouton_nul_refuse_sans_fuite(self) -> None:
        self.etat["greedy_nul"] = True

        with self.assertRaises(RuntimeError) as capture:
            self._charger()

        self.assertIn("llama_sampler_init_greedy", str(capture.exception))
        # La grammaire a été adoptée par la chaîne : libérer la chaîne libère
        # l'échantillonneur avec elle, jamais deux fois à la main.
        self.assertIn("chaine", self.etat["libere"])
        self.assertNotIn("sampler", self.etat["libere"])
        self.assertIn("ctx", self.etat["libere"])
        self.assertIn("model", self.etat["libere"])

    def test_lot_libere_sur_echec_de_decodage(self) -> None:
        moteur = self._charger(contexte=512)
        self.etat["echec_decode"] = True

        with self.assertRaises(RuntimeError):
            self._extraire(moteur)

        # Chaque lot créé est libéré, même quand llama_decode échoue.
        self.assertEqual(self.etat["batches_crees"], self.etat["batches_liberes"])
        self.assertGreater(self.etat["batches_liberes"], 0)

    def test_comptes_omis_apres_echec_partiel(self) -> None:
        # Une source qui échoue en plein décodage laisse des compteurs différés
        # non engagés : les comptes de la source suivante seraient faussés
        # au-delà du ±1 documenté, donc omis — jamais rendus faux.
        moteur = self._charger(contexte=512)
        self.etat["echec_decode"] = True
        with self.assertRaises(RuntimeError):
            self._extraire(moteur)

        self.etat["echec_decode"] = False
        self.etat["echantillons"] = [0, 1, JETON_EOG]
        premiere = self._extraire(moteur)

        self.assertEqual(
            set(premiere),
            {
                "sortie_brute",
                "tokens_entree",
                "tokens_sortie",
                "fin",
                "delai_premier_token_s",
                "duree_generation_s",
                "temps_cpu_s",
            },
        )
        self.assertNotIn("comptes_natifs", premiere)

        # La marque est levée après une source entièrement décodée : la
        # suivante retrouve des comptes natifs cohérents.
        self.etat["echantillons"] = [0, 1, JETON_EOG]
        deuxieme = self._extraire(moteur)
        self.assertIn("comptes_natifs", deuxieme)
        self.assertLessEqual(
            abs(deuxieme["comptes_natifs"]["tokens_lecture"] - deuxieme["tokens_entree"]),
            1,
        )

    def test_repli_silencieux_refuse_avec_motif(self) -> None:
        self.etat["mode_grammaire"] = "repli"

        with self.assertRaises(RuntimeError) as capture:
            self._charger()

        self.assertIn("non contraignante", str(capture.exception))
        # Échec sans génération possible : tout est libéré, aucune chaîne.
        self.assertIn("sampler", self.etat["libere"])
        self.assertIn("ctx", self.etat["libere"])
        self.assertIn("model", self.etat["libere"])
        self.assertFalse(
            [appel for appel in self.etat["appels"] if "chain" in appel["nom"]]
        )

    def test_echantillonneur_nul_refuse(self) -> None:
        self.etat["mode_grammaire"] = "nul"

        with self.assertRaises(RuntimeError) as capture:
            self._charger()

        self.assertIn("NULL", str(capture.exception))
        self.assertIn("model", self.etat["libere"])

    def test_grammaire_bloquant_tout_refusee(self) -> None:
        self.etat["mode_grammaire"] = "bloque_tout"

        with self.assertRaises(RuntimeError) as capture:
            self._charger()

        self.assertIn("bloque tout le vocabulaire", str(capture.exception))

    def test_schema_inconvertible_refuse(self) -> None:
        self.etat["erreur_conversion"] = ValueError("schéma hors sous-ensemble")

        with self.assertRaises(RuntimeError) as capture:
            self._charger()

        self.assertIn("non convertible", str(capture.exception))
        self.assertIn("model", self.etat["libere"])

    def test_fichier_gguf_absent_refuse(self) -> None:
        self.fichier.unlink()

        with self.assertRaises(RuntimeError):
            self._charger()

    def test_chargement_local_impose(self) -> None:
        module, grammaire = self.fabrique.module()
        with mock.patch.dict(
            sys.modules, {"llama_cpp": module, "llama_cpp.llama_grammar": grammaire}
        ):
            with self.assertRaises(RuntimeError):
                llama_cpp.charger(
                    self._modele(local_files_only=False), 4, {}, SCHEMA_TEST
                )

    # -- Formats de conversation --------------------------------------------

    def test_formats_pour_chaque_architecture_admise(self) -> None:
        self.assertEqual(
            set(llama_cpp.FORMATS_CONVERSATION), set(ARCHITECTURES_LLAMA_CPP)
        )

    def test_rendus_exact_des_formats(self) -> None:
        rendus = {
            nom: fonction(" S ", " U ")
            for nom, fonction in llama_cpp.FORMATS_CONVERSATION.items()
        }

        self.assertEqual(
            rendus["mistral3"],
            "<s>[SYSTEM_PROMPT] S [/SYSTEM_PROMPT][INST] U [/INST]",
        )
        self.assertEqual(
            rendus["qwen35"],
            "<|im_start|>system\nS<|im_end|>\n"
            "<|im_start|>user\nU<|im_end|>\n"
            "<|im_start|>assistant\n",
        )
        self.assertEqual(
            rendus["granite"],
            "<|im_start|>system\n S <|im_end|>\n"
            "<|im_start|>user\n U <|im_end|>\n"
            "<|im_start|>assistant\n",
        )
        self.assertEqual(
            rendus["gemma4"],
            "<bos><|turn>system\nS<turn|>\n"
            "<|turn>user\nU<turn|>\n"
            "<|turn>model\n",
        )

    def test_architecture_sans_format_refusee(self) -> None:
        self.etat["architecture"] = "llama"

        with self.assertRaises(RuntimeError) as capture:
            self._charger()

        self.assertIn("sans format local", str(capture.exception))
        self.assertIn("model", self.etat["libere"])

    # -- Extraction -----------------------------------------------------------

    def test_contexte_insuffisant_avant_toute_generation(self) -> None:
        moteur = self._charger(contexte=64)
        messages = [
            {"role": "system", "content": "a" * 30},
            {"role": "user", "content": "b" * 30},
        ]
        attendu = len(
            llama_cpp.FORMATS_CONVERSATION["mistral3"]("a" * 30, "b" * 30)
        )

        with self.assertRaises(ErreurContexteInsuffisant) as capture:
            self._extraire(moteur, messages, contexte=64, sortie_max=16)

        erreur = capture.exception
        self.assertEqual(erreur.tokens_entree, attendu)
        self.assertEqual(erreur.sortie_max, 16)
        self.assertEqual(erreur.contexte, 64)
        # Refus avant toute génération : aucun décodage simulé appelé.
        self.assertEqual(self.etat["decodes"], 0)
        self.assertFalse(
            [appel for appel in self.etat["appels"] if appel["nom"] == "llama_sampler_sample"]
        )

    def test_cles_exactes_arret_eog_exclu_et_comptes(self) -> None:
        moteur = self._charger(contexte=512)
        self.etat["echantillons"] = [0, 1, JETON_EOG]

        resultat = self._extraire(moteur)

        self.assertEqual(
            set(resultat),
            {
                "sortie_brute",
                "tokens_entree",
                "tokens_sortie",
                "fin",
                "delai_premier_token_s",
                "duree_generation_s",
                "temps_cpu_s",
                "comptes_natifs",
            },
        )
        self.assertEqual(resultat["fin"], "arret")
        # Le token de fin (id 8) est exclu du compte et de la sortie.
        self.assertEqual(resultat["tokens_sortie"], 2)
        self.assertEqual(resultat["sortie_brute"], "ab")
        self.assertGreaterEqual(resultat["delai_premier_token_s"], 0.0)
        self.assertGreaterEqual(resultat["duree_generation_s"], 0.0)
        self.assertGreaterEqual(resultat["temps_cpu_s"], 0.0)
        comptes = resultat["comptes_natifs"]
        self.assertEqual(comptes["tokens_lecture"], resultat["tokens_entree"])
        self.assertEqual(comptes["tokens_generation"], resultat["tokens_sortie"])

    def test_limite_atteinte_avec_comptes(self) -> None:
        moteur = self._charger(contexte=512)
        self.etat["echantillons"] = [0, 1, 0]

        resultat = self._extraire(moteur, sortie_max=3)

        self.assertEqual(resultat["fin"], "limite")
        self.assertEqual(resultat["tokens_sortie"], 3)
        # Comptes natifs en cumul, cohérents à ±1 token près (engagement
        # différé du dernier décodage, mesuré à l'essai minimal).
        comptes = resultat["comptes_natifs"]
        self.assertEqual(comptes["tokens_lecture"], resultat["tokens_entree"])
        self.assertLessEqual(
            abs(comptes["tokens_generation"] - resultat["tokens_sortie"]), 1
        )

    def test_tokenisation_sans_tokens_speciaux_ajoutes(self) -> None:
        moteur = self._charger(contexte=512)

        self._extraire(moteur)

        self.assertGreater(len(self.etat["tokenisations"]), 0)
        for _texte, special, analyse in self.etat["tokenisations"]:
            self.assertIs(special, False)
            self.assertIs(analyse, True)

    def test_messages_incomplets_refuses(self) -> None:
        moteur = self._charger(contexte=512)

        with self.assertRaises(ValueError):
            self._extraire(moteur, messages=[{"role": "user", "content": "u"}])

    def test_reinitialiser_vide_memoire_et_chaine(self) -> None:
        moteur = self._charger(contexte=512)
        self.etat["echantillons"] = [0, 1, JETON_EOG]

        for _ in range(2):
            llama_cpp.reinitialiser(moteur)
            self._extraire(moteur)

        self.assertEqual(self.etat["clear_appels"], [True, True])
        self.assertEqual(self.etat["reset_appels"], 2)

    def test_aucune_liaison_de_haut_niveau_utilisee(self) -> None:
        # La doublure lève AssertionError sur tout accès à la classe de haut
        # niveau : un parcours complet sans exception suffit à prouver que
        # l'adaptateur ne l'utilise pas, ni aucun format de réponse magique.
        moteur = self._charger(contexte=512)
        self.etat["echantillons"] = [0, JETON_EOG]

        resultat = self._extraire(moteur)

        self.assertEqual(resultat["fin"], "arret")
        noms = {appel["nom"] for appel in self.etat["appels"]}
        self.assertNotIn("Llama", noms)
        self.assertNotIn("create_completion", noms)
        self.assertNotIn("response_format", noms)


class IdentiteRunnerScriptTest(unittest.TestCase):
    """Preuve d'identité de l'exception à travers le lancement réel en script.

    Le service lance le runner comme **script** (`extraction_runner_command` →
    `interprete engines/runner_extraction.py job.json`) : le code s'exécute
    alors sous le nom `__main__`, et une exception définie dans son fichier
    aurait une seconde identité (`engines.runner_extraction`) du côté de
    l'adaptateur. Le test reproduit exactement ce lancement (runpy avec
    `run_name="__main__"`, seul moyen d'y injecter le registre de test) et
    vérifie que le refus de contexte garde son motif exact et ses nombres.
    """

    MOTEUR = "test-extraction-script"

    def test_refus_contexte_precis_a_travers_la_frontiere(self) -> None:
        with tempfile.TemporaryDirectory() as temporaire:
            dossier = Path(temporaire)
            job = dossier / "job.json"
            job.write_text(
                json.dumps(
                    {
                        "version": 1,
                        "tache": "extraction",
                        "moteur": self.MOTEUR,
                        "famille": self.MOTEUR,
                        "modele": {
                            "identifiant": "test/extraction",
                            "revision": "abc",
                            "chemin": "modele",
                        },
                        "threads_demandes": 4,
                        "reglages": {"contexte": 1024, "sortie_max": 200},
                        "schema": {"type": "object", "properties": {}, "required": []},
                        "message_systeme": "consignes",
                        "sources": [
                            {"texte": "Texte.", "ordre": 0, "nom": "a.wav"}
                        ],
                    }
                ),
                encoding="utf-8",
            )
            prelude = f"""\
import runpy
import sys
from pathlib import Path

RACINE = Path({str(RACINE_PROJET)!r})
sys.path.insert(0, str(RACINE))

import engines.registre as module_registre
from engines.declarations import (
    DeclarationAdaptateur, Famille, TASK_EXTRACTION,
)
from engines.registre import RegistreMoteurs


def registre_de_test():
    registre = RegistreMoteurs()
    registre.enregistrer(
        DeclarationAdaptateur(
            identifiant={self.MOTEUR!r},
            nom="Moteur d'extraction de test (script)",
            fichier_requirements=None,
            regle_compatibilite="aucune",
            familles=(
                Famille(
                    {self.MOTEUR!r},
                    "Famille d'extraction de test (script)",
                    qualifiee=True,
                    task=TASK_EXTRACTION,
                ),
            ),
            module_adaptateur="tests.adaptateur_extraction_de_test",
        )
    )
    return registre


module_registre.creer_registre_fourni = registre_de_test

import tests.adaptateur_extraction_de_test as adaptateur
adaptateur.configurer(tokens_entree=900)

sys.argv = ["runner_extraction.py", {str(job)!r}]
runpy.run_path(
    str(RACINE / "engines" / "runner_extraction.py"), run_name="__main__"
)
"""
            resultat = subprocess.run(
                [sys.executable, "-c", prelude],
                cwd=RACINE_PROJET,
                env={**os.environ, "PYTHONIOENCODING": "utf-8"},
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=120,
                check=False,
            )

        self.assertEqual(resultat.returncode, 0, resultat.stderr)
        evenements = [
            evenement
            for evenement in (
                analyser_ligne(ligne)
                for ligne in resultat.stdout.splitlines()
            )
            if evenement is not None
        ]
        self.assertEqual(
            [evenement["type"] for evenement in evenements],
            [TYPE_CHARGEMENT, TYPE_EXTRACTION_ERREUR, TYPE_FIN],
        )
        erreur = evenements[1]
        # Motif exact avec ses nombres : une seconde identité de l'exception
        # produirait « erreur du moteur (ErreurContexteInsuffisant) ».
        self.assertEqual(
            erreur["motif"],
            "contexte insuffisant : 1100 tokens requis "
            "(900 de prompt + 200 de sortie) pour un contexte de 1024",
        )


if __name__ == "__main__":
    unittest.main()
