"""Cohérence de la documentation utilisateur avec l'interface : libellés, liens, jargon."""

from __future__ import annotations

import ast
import re
import unittest
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
GUIDE = RACINE / "docs" / "guide-utilisateur.md"
README = RACINE / "README.md"
DOSSIER_WEB = RACINE / "transcription_bench" / "web"

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
LIEN_RELATIF = re.compile(r"\]\((?!https?:|mailto:|#)([^)#\s]+)")


def lire(chemin: Path) -> str:
    return chemin.read_text(encoding="utf-8")


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


if __name__ == "__main__":
    unittest.main()
