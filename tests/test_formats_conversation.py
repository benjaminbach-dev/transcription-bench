"""Tests des formats de conversation locaux `qwen35` et `granite`, sans moteur.

Ces tests verrouillent le rendu du seul domaine du parcours d'extraction : deux
messages, système puis utilisateur, sans outils, sans historique et sans
raisonnement. Les littéraux attendus sont ceux du code
(`engines/adaptateurs/llama_cpp.py`) ; aucun gabarit GGUF n'est lu ni affiché.
"""

from __future__ import annotations

import unittest

from engines.adaptateurs import llama_cpp
from transcription_bench.consignes_grilles import (
    SOURCE_END_MARKER,
    SOURCE_START_MARKER,
    user_message,
)

#: Texte contenant accents, guillemets, barres, syntaxe Jinja et émoji, sans
#: espace en bordure (le rendu doit le reproduire octet pour octet).
SPECIAL_TEXT = (
    'Accents é à ç, "guillemets", \\ barre, {{ jinja }} {% if x %} %}, '
    "émoji 🩺, tab\tfin"
)

#: Texte très long (environ 500 000 caractères), sans espace en bordure.
LONG_TEXT = ("segment de transcription " * 20_000).strip()


class ChatMLContractMixin:
    """Contrat commun aux deux formats ChatML ; la sous-classe fournit le format."""

    format_text = None  # défini par la sous-classe (staticmethod)
    suffixe_sans_raisonnement = ""

    def expected(self, system_text: str, user_text: str) -> str:
        raise NotImplementedError

    def test_roles_in_order_and_count(self) -> None:
        rendu = self.format_text("SYS", "USR")

        self.assertEqual(rendu.count("<|im_start|>system"), 1)
        self.assertEqual(rendu.count("<|im_start|>user"), 1)
        self.assertEqual(rendu.count("<|im_start|>assistant"), 1)
        self.assertEqual(rendu.count("<|im_start|>"), 3)
        self.assertLess(
            rendu.index("<|im_start|>system"), rendu.index("<|im_start|>user")
        )
        self.assertLess(
            rendu.index("<|im_start|>user"), rendu.index("<|im_start|>assistant")
        )

    def test_full_rendering_matches_literal(self) -> None:
        self.assertEqual(self.format_text("SYS", "USR"), self.expected("SYS", "USR"))

    def test_special_text_preserved_verbatim(self) -> None:
        rendu = self.format_text("SYS", SPECIAL_TEXT)

        self.assertIn(SPECIAL_TEXT, rendu)
        self.assertEqual(rendu, self.expected("SYS", SPECIAL_TEXT))

    def test_very_long_text_not_truncated(self) -> None:
        rendu = self.format_text("SYS", LONG_TEXT)

        self.assertEqual(rendu, self.expected("SYS", LONG_TEXT))

    def test_empty_system_content_renders_without_error(self) -> None:
        self.assertEqual(self.format_text("", "USR"), self.expected("", "USR"))

    def test_empty_user_content_renders_without_error(self) -> None:
        # Le formateur accepte un contenu vide ; l'appelant n'en envoie jamais
        # (voir ParcoursContratTest.test_user_message_never_empty).
        self.assertEqual(self.format_text("SYS", ""), self.expected("SYS", ""))

    def test_reasoning_parameter_is_not_accepted(self) -> None:
        # Pas de paramètre de raisonnement : les valeurs « absente » et « False »
        # produisent donc le même rendu, celui de la branche sans raisonnement.
        with self.assertRaises(TypeError):
            self.format_text("SYS", "USR", enable_thinking=False)

    def test_single_empty_reasoning_block_at_generation_prompt(self) -> None:
        rendu = self.format_text("SYS", "USR")

        self.assertEqual(rendu.count("<think>"), 1)
        self.assertEqual(rendu.count("</think>"), 1)
        self.assertTrue(rendu.endswith(self.suffixe_sans_raisonnement))


class QwenFormatTest(ChatMLContractMixin, unittest.TestCase):
    """Format `qwen35` : contenu trimé par le gabarit, préfixe sans raisonnement."""

    format_text = staticmethod(llama_cpp._format_qwen35)
    suffixe_sans_raisonnement = "<|im_start|>assistant\n<think>\n\n</think>\n\n"

    def expected(self, system_text: str, user_text: str) -> str:
        return (
            f"<|im_start|>system\n{system_text.strip()}<|im_end|>\n"
            f"<|im_start|>user\n{user_text.strip()}<|im_end|>\n"
            "<|im_start|>assistant\n<think>\n\n</think>\n\n"
        )

    def test_surrounding_whitespace_trimmed_inner_kept(self) -> None:
        rendu = self.format_text("  \nSYS avec\nligne\n", " USR \n\n")

        self.assertEqual(
            rendu,
            "<|im_start|>system\nSYS avec\nligne<|im_end|>\n"
            "<|im_start|>user\nUSR<|im_end|>\n"
            "<|im_start|>assistant\n<think>\n\n</think>\n\n",
        )

    def test_system_whitespace_only_becomes_empty(self) -> None:
        rendu = self.format_text(" \n\t ", "USR")

        self.assertTrue(rendu.startswith("<|im_start|>system\n<|im_end|>\n"))


class GraniteFormatTest(ChatMLContractMixin, unittest.TestCase):
    """Format `granite` : contenu non trimé, préfixe `<think></think>`."""

    format_text = staticmethod(llama_cpp._format_granite)
    suffixe_sans_raisonnement = "<|im_start|>assistant\n<think></think>"

    def expected(self, system_text: str, user_text: str) -> str:
        return (
            f"<|im_start|>system\n{system_text}<|im_end|>\n"
            f"<|im_start|>user\n{user_text}<|im_end|>\n"
            "<|im_start|>assistant\n<think></think>"
        )

    def test_surrounding_whitespace_kept(self) -> None:
        rendu = self.format_text("  \nSYS\n", " USR \n\n")

        self.assertEqual(
            rendu,
            "<|im_start|>system\n  \nSYS\n<|im_end|>\n"
            "<|im_start|>user\n USR \n\n<|im_end|>\n"
            "<|im_start|>assistant\n<think></think>",
        )


class ParcoursContratTest(unittest.TestCase):
    """Contrat d'entrée du chemin d'appel (runner -> adaptateur -> formateur)."""

    def test_messages_system_then_user(self) -> None:
        systeme, utilisateur = llama_cpp._messages(
            [{"role": "system", "content": "S"}, {"role": "user", "content": "U"}]
        )

        self.assertEqual((systeme, utilisateur), ("S", "U"))

    def test_history_is_dropped_silently(self) -> None:
        # Contrat actuel : l'historique n'est jamais rendu. Le runner n'en envoie
        # pas (tests/test_runner.py, test_messages_systeme_et_utilisateur_recus).
        messages = [
            {"role": "system", "content": "S"},
            {"role": "user", "content": "U1"},
            {"role": "assistant", "content": "A"},
            {"role": "user", "content": "U2"},
        ]

        self.assertEqual(llama_cpp._messages(messages), ("S", "U1"))

    def test_role_order_is_not_enforced_by_adapter(self) -> None:
        # L'ordre est garanti par l'appelant, pas par l'adaptateur : le rendu
        # fixe toujours système puis utilisateur.
        systeme, utilisateur = llama_cpp._messages(
            [{"role": "user", "content": "U"}, {"role": "system", "content": "S"}]
        )

        self.assertEqual((systeme, utilisateur), ("S", "U"))

    def test_missing_system_refused(self) -> None:
        with self.assertRaises(ValueError):
            llama_cpp._messages([{"role": "user", "content": "U"}])

    def test_non_string_content_refused(self) -> None:
        with self.assertRaises(ValueError):
            llama_cpp._messages(
                [{"role": "system", "content": None}, {"role": "user", "content": "U"}]
            )

    def test_user_message_never_empty(self) -> None:
        # Même une transcription vide donne un contenu utilisateur non vide.
        self.assertEqual(
            user_message(""), f"{SOURCE_START_MARKER}\n\n{SOURCE_END_MARKER}"
        )


if __name__ == "__main__":
    unittest.main()
