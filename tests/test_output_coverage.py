"""Garde les évolutions des vues explicites dans le contrat JSON."""

from __future__ import annotations

import ast
import dataclasses
import inspect
import typing
import unittest

from transcription_bench import output


# Chaque exclusion explique pourquoi la valeur n'est pas lue séparément.
EXCLUDED_MEMBERS = {
    "serialize_hash_group": {"entrees"},  # Déjà séparées en réelles/simulées.
    "serialize_comparison_card": {  # Regroupés sous la propriété indicateurs.
        "duree_transcription_s", "pic_memoire_octets", "ram_totale_octets",
        "temps_cpu_s", "part_ram", "occupation_cpu",
    },
    "serialize_audio_prepare": {"fichier_brut"},  # Chemin de travail interne.
    "serialize_run_result": {"evenements"},  # Événements bruts internes.
}


class OutputCoverageTest(unittest.TestCase):
    def test_every_view_member_is_used_or_explicitly_excluded(self) -> None:
        checked = set()
        for name, serializer in vars(output).items():
            if not name.startswith("serialize_") or not inspect.isfunction(serializer):
                continue
            view_type = typing.get_type_hints(serializer).get("view")
            if typing.get_origin(view_type):
                view_type = next((
                    candidate for candidate in typing.get_args(view_type)
                    if dataclasses.is_dataclass(candidate)
                ), None)
            if not dataclasses.is_dataclass(view_type):
                continue
            checked.add(name)
            members = {field.name for field in dataclasses.fields(view_type)} | {
                key for key, value in vars(view_type).items()
                if isinstance(value, property)
            }
            tree = ast.parse(inspect.getsource(serializer))
            used = {
                node.attr for node in ast.walk(tree)
                if isinstance(node, ast.Attribute)
                and isinstance(node.value, ast.Name) and node.value.id == "view"
            }
            excluded = EXCLUDED_MEMBERS.get(name, set())
            with self.subTest(serializer=name):
                self.assertEqual(members - used, excluded,
                                 "Champ ajouté ou exclusion obsolète : décider du contrat JSON")
        self.assertGreaterEqual(len(checked), 30)
        self.assertLessEqual(set(EXCLUDED_MEMBERS), checked)


if __name__ == "__main__":
    unittest.main()
