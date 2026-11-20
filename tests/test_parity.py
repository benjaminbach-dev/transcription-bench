"""Parité web/CLI (design D3) : la table couvre exactement les routes réelles.

Le sens est inversé : chaque page de consultation a une commande de lecture ; une
commande sans page est admise. Seuls l'accueil et les ressources fixes peuvent
être exclus. Les listes admises (exclusions, commandes de lecture) sont fixées
ici, hors du module de production : élargir la table exige aussi de modifier ce
test.
"""

from __future__ import annotations

import contextlib
import io
import tempfile
import unittest
from pathlib import Path

from transcription_bench import cli
from transcription_bench.commands import COMMANDS
from transcription_bench.parity import WEB_CLI_PARITY
from transcription_bench.web import ConfigApplication, ServicesApplication, create_app

PORT_TEST = 8765

#: Seules ces routes peuvent être exclues de la table : l'accueil et les
#: ressources fixes.
ROUTES_EXCLUES_AUTORISEES: frozenset[str] = frozenset({"/", "/sumi.css", "/app.css"})

#: Seules ces commandes peuvent être associées à une page de consultation.
COMMANDES_DE_LECTURE: frozenset[tuple[str, ...]] = frozenset(
    {
        ("results", "list"),
        ("results", "show"),
        ("results", "explain"),
        ("results", "history"),
        ("compare",),
        ("extract", "list"),
        ("extract", "show"),
        ("extract", "compare"),
        ("extract", "explain"),
    }
)


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

    def test_exclusions_de_la_table_egales_a_la_liste_blanche(self) -> None:
        """Une exclusion non listée ici, ou une entrée listée sans exclusion, échoue."""
        exclues = {entree.rule for entree in WEB_CLI_PARITY if not entree.commands}
        self.assertEqual(
            exclues,
            ROUTES_EXCLUES_AUTORISEES,
            "exclusions de la table différentes de la liste blanche de ce test",
        )

    def test_commandes_associees_aux_pages_sont_de_lecture(self) -> None:
        """Une page de consultation ne mène qu'à une commande de lecture."""
        for entree in WEB_CLI_PARITY:
            for chemin in entree.commands:
                with self.subTest(
                    route=f"{entree.method} {entree.rule}",
                    commande=" ".join(chemin),
                ):
                    self.assertIn(
                        chemin,
                        COMMANDES_DE_LECTURE,
                        "commande d'action associée à une page de consultation",
                    )


if __name__ == "__main__":
    unittest.main()
