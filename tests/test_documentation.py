"""Cohérence de la documentation utilisateur avec l'interface : libellés, liens, jargon."""

from __future__ import annotations

import ast
import re
import tempfile
import unittest
from pathlib import Path

from tests.test_aide_resultats_web import texte_visible
from tests.test_web import ADRESSE_LOCALE, PORT_TEST
from transcription_bench.cli import COMMAND_SERVE
from transcription_bench.command_session import CommandGroup
from transcription_bench.commands import COMMANDS
from transcription_bench.operations import CreneauOperations
from transcription_bench.web import ConfigApplication, ServicesApplication, create_app

RACINE = Path(__file__).resolve().parent.parent
GUIDE = RACINE / "docs" / "guide-utilisateur.md"
TECHNIQUE = RACINE / "docs" / "technique.md"
README = RACINE / "README.md"
DOSSIER_WEB = RACINE / "transcription_bench" / "web"
#: Début de la note du guide sur le contexte de l'ordinateur (tâche 3.2).
NOTE_CONTEXTE = "*Contexte de l'ordinateur.*"

# Gras du guide qui n'est pas un libellé d'interface : aucune pour l'instant.
LIBELLES_HORS_INTERFACE: frozenset[str] = frozenset()

TERMES_INTERDITS = (
    "CSRF",
    "WSGI",
    "Flask",
    "Jinja",
    "venv",
    "namespace",
    "mmap",
    "RTF",
    "HF_HUB_OFFLINE",
)
MAX_LIGNES_README = 60
TITRE_GLOSSAIRE = "## Glossaire"
#: Début de la section d'usage en commande destinée aux agents (tâche 4.3
#: d'`ajouter-cli-agent`) : son contenu est confronté aux commandes réelles.
TITRE_SECTION_CLI = "## Utiliser le programme en commande (agents)"
#: Ancre Markdown de cette section, cible du renvoi du README.
ANCRE_SECTION_CLI = "utiliser-le-programme-en-commande-agents"
LIEN_RELATIF = re.compile(r"\]\((?!https?:|mailto:|#)([^)#\s]+)")


def lire(chemin: Path) -> str:
    return chemin.read_text(encoding="utf-8")


def section_cli() -> str:
    """Section « Utiliser le programme en commande (agents) » de la doc technique.

    Bornée au titre suivant : les contrôles ne portent que sur cette section,
    sans dépendre du reste du document.
    """
    texte = lire(TECHNIQUE)
    debut = texte.find(TITRE_SECTION_CLI)
    if debut < 0:
        raise AssertionError(
            f"section absente de {TECHNIQUE.relative_to(RACINE)} : {TITRE_SECTION_CLI!r}"
        )
    fin = texte.find("\n## ", debut + len(TITRE_SECTION_CLI))
    return texte[debut:fin if fin >= 0 else len(texte)]


def chaines_python(source: str) -> list[str]:
    """Constantes de chaîne d'un module, docstrings et commentaires exclus.

    Seuls les littéraux peuvent porter un libellé affiché ; une docstring ou un
    commentaire n'apparaît jamais dans l'interface.
    """
    arbre = ast.parse(source)
    docstrings = {
        id(noeud.body[0].value)
        for noeud in ast.walk(arbre)
        if isinstance(
            noeud, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
        )
        and noeud.body
        and isinstance(noeud.body[0], ast.Expr)
        and isinstance(noeud.body[0].value, ast.Constant)
        and isinstance(noeud.body[0].value.value, str)
    }
    return [
        noeud.value
        for noeud in ast.walk(arbre)
        if isinstance(noeud, ast.Constant)
        and isinstance(noeud.value, str)
        and id(noeud) not in docstrings
    ]


def sources_interface() -> str:
    """Gabarits `.html` et chaînes littérales Python de la couche web.

    Ce sont les seuls endroits où vivent les libellés affichés ; les docstrings
    et les commentaires Python en sont exclus.
    """
    morceaux = [
        lire(chemin)
        for chemin in sorted(DOSSIER_WEB.rglob("*.html"))
        if chemin.is_file()
    ]
    for chemin in sorted(DOSSIER_WEB.rglob("*.py")):
        if chemin.is_file():
            morceaux.extend(chaines_python(lire(chemin)))
    return "\n".join(morceaux)


def sans_glossaire(texte: str) -> str:
    debut = texte.find(TITRE_GLOSSAIRE)
    if debut < 0:
        return texte
    fin = texte.find("\n## ", debut + len(TITRE_GLOSSAIRE))
    return texte[:debut] + (texte[fin:] if fin >= 0 else "")


def sans_libelles(texte: str) -> str:
    return re.sub(r"\*\*[^*]+\*\*", "", texte)


def note_contexte(texte: str) -> str:
    """Paragraphe du guide consacré au contexte de l'ordinateur."""
    debut = texte.index(NOTE_CONTEXTE)
    fin = texte.find("\n", debut)
    return texte[debut : fin if fin >= 0 else len(texte)]

def help_text() -> str:
    """Texte visible de la page « Comprendre les indicateurs », rendue par l'application.

    La route `/resultats/aide` rend le gabarit à partir de la source unique
    (`web/results_help.py`) : le contrôle porte sur le texte réellement affiché,
    sans balisage, et non sur la mise en page du module source.
    """
    with tempfile.TemporaryDirectory() as temporary:
        application = create_app(
            ConfigApplication(port=PORT_TEST, dossier_data=Path(temporary) / "data"),
            ServicesApplication(creneau=CreneauOperations()),
        )
        response = application.test_client().get(
            "/resultats/aide", base_url=f"http://{ADRESSE_LOCALE}:{PORT_TEST}"
        )
    if response.status_code != 200:
        raise AssertionError(f"page d'aide non servie : {response.status_code}")
    return texte_visible(response.get_data(as_text=True))

class DocumentationTest(unittest.TestCase):
    def test_libelles_en_gras_existent_dans_l_interface(self) -> None:
        interface = sources_interface()
        for libelle in re.findall(r"\*\*([^*]+)\*\*", lire(GUIDE)):
            if libelle in LIBELLES_HORS_INTERFACE:
                continue
            self.assertTrue(
                libelle in interface,
                f"libellé « {libelle} » du guide absent de l'interface (docs/guide-utilisateur.md)",
            )

    def test_liens_relatifs_pointent_vers_des_fichiers(self) -> None:
        documents = [README, *sorted((RACINE / "docs").glob("*.md"))]
        for document in documents:
            for cible in LIEN_RELATIF.findall(lire(document)):
                self.assertTrue(
                    (document.parent / cible).exists(),
                    f"lien cassé dans {document.relative_to(RACINE)} : {cible}",
                )

    def test_termes_interdits_absents_du_guide_et_du_readme(self) -> None:
        for document in (GUIDE, README):
            texte = sans_libelles(sans_glossaire(lire(document))).casefold()
            for terme in TERMES_INTERDITS:
                self.assertNotIn(
                    terme.casefold(),
                    texte,
                    f"terme interdit « {terme} » dans {document.relative_to(RACINE)}",
                )

    def test_readme_court_avec_lien_vers_le_guide(self) -> None:
        texte = lire(README)
        self.assertLess(len(texte.splitlines()), MAX_LIGNES_README)
        self.assertIn("docs/guide-utilisateur.md", texte)
        self.assertIn("docs/technique.md", texte)
        self.assertIn("pas un produit clinique validé", texte.replace("\n", " "))

    def test_guide_a_un_glossaire(self) -> None:
        self.assertIn(TITRE_GLOSSAIRE, lire(GUIDE))


class DocumentationCLITest(unittest.TestCase):
    """Section « agents » alignée sur la CLI réelle (tâche 4.3 d'`ajouter-cli-agent`).

    Les contrôles existants (liens, termes interdits, README court) restent
    intacts ; ceux-ci ajoutent : section présente, renvoi du README, chaque
    commande enregistrée documentée, et les points du contrat que la spec
    exige de la documentation (`--json`, `schema: 1`, codes, signaux).
    """

    def test_section_presente_avec_renvoi_readme(self) -> None:
        self.assertIn(TITRE_SECTION_CLI, lire(TECHNIQUE))
        self.assertTrue(section_cli().strip())
        readme = lire(README)
        self.assertIn("Utiliser le programme en commande", readme)
        # Le renvoi pointe vers la section de la documentation technique, ancre
        # comprise : la cible du lien est contrôlée par
        # test_liens_relatifs_pointent_vers_des_fichiers.
        self.assertIn(f"docs/technique.md#{ANCRE_SECTION_CLI}", readme)

    def test_commandes_enregistrees_sont_documentees(self) -> None:
        """Chaque commande enregistrée dans le code figure dans la section.

        Le sens documenté -> enregistré n'est pas contrôlé : extraire les
        commandes du tableau coûterait un analyseur dédié pour peu de gain.
        """
        section = section_cli()
        self.assertIn(f"`{COMMAND_SERVE}", section)
        for commande in COMMANDS:
            if isinstance(commande, CommandGroup):
                for leaf in commande.commands:
                    self.assertIn(
                        f"`{commande.name} {leaf.name}",
                        section,
                        f"commande enregistrée non documentée : "
                        f"{commande.name} {leaf.name}",
                    )
            else:
                self.assertIn(
                    f"`{commande.name}",
                    section,
                    f"commande enregistrée non documentée : {commande.name}",
                )

    def test_contrat_de_sortie_et_de_signaux_documente(self) -> None:
        section = section_cli()
        for attendu in (
            "--json",
            "schema: 1",
            "SIGTERM",
            "SIGKILL",
            "`0`",
            "`1`",
            "`2`",
            "`3`",
        ):
            with self.subTest(attendu=attendu):
                self.assertIn(attendu, section)


class GuideContexteOrdinateurTest(unittest.TestCase):
    """Note du guide alignée sur l'aide locale (tâche 3.2, design D4).

    L'aide locale porte le texte complet des limites du contexte système ; le
    guide en donne une note courte, sans promesse de confort ni marge inventée,
    et sans contredire les sections qui l'entourent.
    """

    def test_note_situee_dans_la_lecture_d_un_resultat(self) -> None:
        texte = lire(GUIDE)
        debut = texte.index("## 10. Lire un résultat")
        fin = texte.index("## 11. Comparer deux résultats")
        self.assertIn(NOTE_CONTEXTE, texte[debut:fin])

    def test_note_dit_les_limites_du_contexte_systeme(self) -> None:
        note = note_contexte(lire(GUIDE))
        for attendu in (
            "**Contexte de l'ordinateur**",
            "Le CPU total inclut les autres programmes",
            "estimation du système à un instant donné",
            "le minimum resté pendant la transcription",
            "ressources visibles par le système",
            "capacité matérielle garantie",
            "ni fluidité ni confort",
            "cet essai",
            "un autre ordinateur",
            "non mesuré",
        ):
            with self.subTest(attendu=attendu):
                self.assertIn(attendu, note)
        # Aucune présentation positive d'une garantie, d'une marge ou d'une
        # propriété du modèle.
        for interdit in (
            "marge restante",
            "ordinateur fluide",
            "garantie de performance",
            "propre au modèle",
        ):
            with self.subTest(interdit=interdit):
                self.assertNotIn(interdit, note)

    def test_note_et_aide_locale_disent_les_memes_limites(self) -> None:
        note = note_contexte(lire(GUIDE))
        aide = help_text()
        for terme in (
            "autres programmes",
            "un instant donné",
            "ressources visibles par le système",
            "capacité matérielle garantie",
            "un autre ordinateur",
        ):
            with self.subTest(terme=terme):
                self.assertIn(terme, note)
                self.assertIn(terme, aide)


if __name__ == "__main__":
    unittest.main()
