"""Parité web/CLI : la table du code couvre exactement les routes réelles."""

from __future__ import annotations

import contextlib
import io
import tempfile
import unittest
from pathlib import Path

from transcription_bench import cli
from transcription_bench.command_session import CommandGroup
from transcription_bench.commands import COMMANDS
from transcription_bench.operations import CreneauOperations
from transcription_bench.parity import WEB_CLI_PARITY
from transcription_bench.web import ConfigApplication, ServicesApplication, create_app

PORT_TEST = 8765

#: Commandes enregistrées sans équivalent web, admises uniquement par cette
#: exclusion documentée. Vide : `serve` n'est pas concerné, `cli` l'ajoute
#: hors de `COMMANDS` et la table décrit les routes du serveur, pas son
#: lancement ; une future commande sans équivalent devra s'y ajouter avec sa
#: raison.
COMMAND_EXCLUSIONS: frozenset[tuple[str, ...]] = frozenset()


class PariteWebCliTest(unittest.TestCase):
    """Confronte la table de parité aux routes réelles et à l'analyseur CLI."""

    def setUp(self) -> None:
        temporaire = tempfile.TemporaryDirectory()
        self.addCleanup(temporaire.cleanup)
        self.dossier_data = Path(temporaire.name) / "data"
        self.creneau = CreneauOperations()
        self.app = create_app(
            ConfigApplication(port=PORT_TEST, dossier_data=self.dossier_data),
            ServicesApplication(creneau=self.creneau),
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

    def test_every_registered_leaf_is_covered_or_excluded(self) -> None:
        """Sens inverse : chaque commande feuille est couverte par la table.

        Sans ce sens, une commande enregistrée sans aucune entrée de parité
        passerait inaperçue : elle existerait dans l'analyseur sans équivalent
        web documenté.
        """
        couvertes: set[tuple[str, ...]] = set()
        for entree in WEB_CLI_PARITY:
            couvertes.update(entree.commands)
        enregistrees: set[tuple[str, ...]] = set()
        for command in COMMANDS:
            if isinstance(command, CommandGroup):
                for leaf in command.commands:
                    enregistrees.add((command.name, leaf.name))
            else:
                enregistrees.add((command.name,))
        sans_couverture = enregistrees - couvertes - COMMAND_EXCLUSIONS
        self.assertEqual(
            sans_couverture,
            set(),
            "commandes enregistrées sans entrée de parité ni exclusion documentée : "
            + repr(sorted(" ".join(chemin) for chemin in sans_couverture)),
        )
