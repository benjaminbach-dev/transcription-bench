"""Parité web/CLI (design D3) : la table couvre exactement les routes réelles.

Le sens est inversé : chaque page de consultation a une commande de lecture ; une
commande sans page est admise. Seuls l'accueil et les ressources fixes peuvent
être exclus.
"""

from __future__ import annotations

import contextlib
import io
import tempfile
import unittest
from pathlib import Path

from transcription_bench import cli
from transcription_bench.commands import COMMANDS
from transcription_bench.parity import ROUTES_EXCLUES_AUTORISEES, WEB_CLI_PARITY
from transcription_bench.web import ConfigApplication, ServicesApplication, create_app

PORT_TEST = 8765


class PariteWebCliTest(unittest.TestCase):
    """Confronte la table de parité aux routes réelles et à l'analyseur CLI."""

    def setUp(self) -> None:
        temporaire = tempfile.TemporaryDirectory()
        self.addCleanup(temporaire.cleanup)
        self.dossier_data = Path(temporaire.name) / "data"
        self.app = create_app(
            ConfigApplication(port=PORT_TEST, dossier_data=self.dossier_data),
            ServicesApplication(),
        )
        self.analyseur = cli.construire_analyseur(COMMANDS)

    def routes_reelles(self) -> set[tuple[str, str]]:
        """Paires (règle, méthode) déclarées par l'application, hors automatismes."""
        return {
            (regle.rule, methode)
            for regle in self.app.url_map.iter_rules()
            for methode in regle.methods - {"HEAD", "OPTIONS"}
        }

    def test_chaque_route_reelle_a_une_entree_et_vice_versa(self) -> None:
        reelles = self.routes_reelles()
        declarees: set[tuple[str, str]] = set()
        for entree in WEB_CLI_PARITY:
            cle = (entree.rule, entree.method)
            self.assertNotIn(
                cle,
                declarees,
                f"entrée de parité dupliquée : {entree.method} {entree.rule}",
            )
            declarees.add(cle)
        sans_entree = reelles - declarees
        self.assertEqual(
            sans_entree,
            set(),
            "routes réelles sans entrée de parité : " + repr(sorted(sans_entree)),
        )
        sans_route = declarees - reelles
        self.assertEqual(
            sans_route,
            set(),
            "entrées de parité sans route réelle : " + repr(sorted(sans_route)),
        )

    def test_les_commandes_de_la_table_existent_dans_l_analyseur(self) -> None:
        for entree in WEB_CLI_PARITY:
            for chemin in entree.commands:
                with self.subTest(
                    route=f"{entree.method} {entree.rule}",
                    commande=" ".join(chemin),
                ):
                    with contextlib.redirect_stdout(io.StringIO()):
                        with self.assertRaises(SystemExit) as sortie:
                            self.analyseur.parse_args([*chemin, "--help"])
                    self.assertEqual(
                        sortie.exception.code,
                        0,
                        f"commande inexistante dans l'analyseur CLI : {' '.join(chemin)}",
                    )

    def test_chaque_entree_est_une_commande_ou_une_exclusion_documentee(self) -> None:
        for entree in WEB_CLI_PARITY:
            with self.subTest(route=f"{entree.method} {entree.rule}"):
                self.assertTrue(
                    bool(entree.commands) != bool(entree.exclusion),
                    "une entrée doit porter des commandes ou une exclusion, pas les deux",
                )
                if not entree.commands:
                    self.assertTrue(
                        entree.exclusion.strip(),
                        "une exclusion doit documenter sa raison",
                    )

    def test_seuls_l_accueil_et_les_ressources_sont_exclus(self) -> None:
        """Une nouvelle page sans commande de lecture fait échouer la suite."""
        for entree in WEB_CLI_PARITY:
            if entree.commands:
                continue
            with self.subTest(route=f"{entree.method} {entree.rule}"):
                self.assertIn(
                    entree.rule,
                    ROUTES_EXCLUES_AUTORISEES,
                    "une page de consultation doit avoir une commande de lecture",
                )


if __name__ == "__main__":
    unittest.main()
