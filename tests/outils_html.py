"""Contrôles HTML partagés par les tests de l'interface web.

Une seule implémentation, fondée sur `html.parser` de la bibliothèque standard :
les pages sont réellement analysées (balises, attributs, `link`, ancres) au lieu
d'être fouillées par recherche de sous-chaînes, qui confondrait un texte affiché
avec du balisage. Les pages ne portent aucun script, aucun style et aucun autre
`link` que les deux feuilles locales servies par l'application.
"""

from __future__ import annotations

from html.parser import HTMLParser

ELEMENTS_INTERDITS = frozenset({"script", "style", "iframe", "object", "img"})
FEUILLES_ATTENDUES = ("/sumi.css", "/app.css")
ATTRIBUTS_DE_LIEN = frozenset({"href", "src", "action", "formaction"})
# Éléments sans contenu ni balise de fermeture : ils ne sont jamais empilés.
ELEMENTS_VIDES = frozenset(
    {
        "area",
        "base",
        "br",
        "col",
        "embed",
        "hr",
        "input",
        "link",
        "meta",
        "param",
        "source",
        "track",
        "wbr",
    }
)
ELEMENTS_A_TEXTE = ("title", "h1", "strong", "a")


class PageHtml(HTMLParser):
    """Balises, attributs, feuilles, ancres, classes, titres et h1 d'une page.

    `textes` conserve le texte de `title`, des `h1`, des `strong` et des
    ancres, dans l'ordre du document (`strong` porte le nom du programme dans
    la navigation).
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.elements: list[str] = []
        self.attributs: list[tuple[str, str, str | None]] = []
        # (ancêtres, balise, attributs) dans l'ordre du document.
        self.balises: list[tuple[tuple[str, ...], str, dict[str, str | None]]] = []
        self.feuilles: list[tuple[str | None, str | None]] = []
        self.liens: list[str] = []
        # Une entrée par `<a href>` : ancêtres, cible, `aria-current`, texte.
        self.ancres: list[dict[str, object]] = []
        self.classes: set[str] = set()
        self.textes: dict[str, list[str]] = {tag: [] for tag in ELEMENTS_A_TEXTE}
        # Corps brut de la page, renseigné par `analyser`.
        self.corps = ""
        self._pile: list[str] = []
        self._captures: list[tuple[str, list[str]]] = []

    def handle_starttag(self, tag, attrs) -> None:
        self._enregistrer(tag, attrs)
        if tag in ELEMENTS_A_TEXTE:
            self._captures.append((tag, []))
        if tag not in ELEMENTS_VIDES:
            self._pile.append(tag)

    def handle_startendtag(self, tag, attrs) -> None:
        self._enregistrer(tag, attrs)

    def handle_endtag(self, tag) -> None:
        if tag in ELEMENTS_A_TEXTE:
            self._terminer_capture(tag)
        if tag in self._pile:
            while self._pile and self._pile.pop() != tag:
                pass

    def handle_data(self, data) -> None:
        for _, contenu in self._captures:
            contenu.append(data)

    def _terminer_capture(self, tag: str) -> None:
        for position in range(len(self._captures) - 1, -1, -1):
            nom, contenu = self._captures[position]
            if nom != tag:
                continue
            del self._captures[position:]
            texte = "".join(contenu).strip()
            self.textes[tag].append(texte)
            if tag == "a" and self.ancres:
                self.ancres[-1]["texte"] = texte
            return

    def _enregistrer(self, tag: str, attrs) -> None:
        self.elements.append(tag)
        attributs: dict[str, str | None] = {}
        for nom, valeur in attrs:
            self.attributs.append((tag, nom, valeur))
            attributs.setdefault(nom, valeur)
        self.balises.append((tuple(self._pile), tag, attributs))
        self.classes.update((attributs.get("class") or "").split())
        if tag == "link":
            self.feuilles.append((attributs.get("rel"), attributs.get("href")))
        if tag == "a" and attributs.get("href"):
            self.liens.append(attributs["href"])
            self.ancres.append(
                {
                    "ancetres": tuple(self._pile),
                    "href": attributs["href"],
                    "aria-current": attributs.get("aria-current"),
                    "texte": None,
                }
            )

    def balises_de(self, tag: str) -> list[tuple[tuple[str, ...], str, dict]]:
        """Balises d'un nom donné, dans l'ordre du document."""
        return [balise for balise in self.balises if balise[1] == tag]

    def avec_classe(self, classe: str) -> list[tuple[tuple[str, ...], str, dict]]:
        """Balises portant la classe donnée, dans l'ordre du document."""
        return [
            balise
            for balise in self.balises
            if classe in (balise[2].get("class") or "").split()
        ]

    def ancres_sous(self, *ancetres: str) -> list[dict[str, object]]:
        """Ancres dont les ancêtres commencent par le chemin donné."""
        return [
            ancre
            for ancre in self.ancres
            if tuple(ancre["ancetres"])[: len(ancetres)] == ancetres
        ]

    def courants(self) -> list[dict[str, object]]:
        """Ancres portant `aria-current`, quelle qu'en soit la valeur."""
        return [ancre for ancre in self.ancres if ancre["aria-current"] is not None]

    @property
    def texte_titre(self) -> str:
        return self.textes["title"][0] if self.textes["title"] else ""


def analyser(corps: str) -> PageHtml:
    """Analyse une page rendue, sans rien exiger : les vérifications sont aux tests."""
    page = PageHtml()
    page.corps = corps
    page.feed(corps)
    page.close()
    return page


def assert_sans_script_ni_style(cas, corps: str) -> PageHtml:
    """Vérifie qu'un corps HTML ne porte ni script, ni style, ni lien actif.

    Interdits : `script`, `style`, `iframe`, `object`, `img`, tout attribut
    `style`, tout attribut de gestionnaire d'événement (`on…`) et tout lien
    `javascript:`. Utile aussi aux corps des redirections, qui ne sont pas des
    pages de l'interface et ne portent donc pas les deux feuilles.
    """
    page = analyser(corps)

    interdits = sorted(set(page.elements) & ELEMENTS_INTERDITS)
    cas.assertEqual(interdits, [], f"éléments interdits dans la page : {interdits}")
    for element, nom, valeur in page.attributs:
        cas.assertNotEqual(nom, "style", f"attribut style sur <{element}>")
        cas.assertFalse(
            nom.startswith("on"), f"attribut de gestionnaire {nom} sur <{element}>"
        )
        if nom in ATTRIBUTS_DE_LIEN:
            cas.assertFalse(
                (valeur or "").strip().lower().startswith("javascript:"),
                f"lien javascript: dans {nom} de <{element}>",
            )

    cas.assertNotIn("Traceback", corps)
    return page


def assert_html_seul(cas, corps: str) -> PageHtml:
    """Vérifie qu'une page est du HTML sans script, sans style et hors ligne.

    Autorisés : les deux feuilles locales `/sumi.css` puis `/app.css`, dans cet
    ordre, et aucune autre ressource.
    """
    page = assert_sans_script_ni_style(cas, corps)

    cas.assertEqual(
        page.feuilles,
        [("stylesheet", FEUILLES_ATTENDUES[0]), ("stylesheet", FEUILLES_ATTENDUES[1])],
        "les seuls éléments link doivent être /sumi.css puis /app.css",
    )
    return page
