"""Tests des feuilles de style servies localement : routes, provenance et palette.

Aucun accès réseau : les feuilles sont lues dans le paquet et comparées à la
copie figée décrite par `transcription_bench/web/ressources/PROVENANCE.md`.
"""

from __future__ import annotations

import hashlib
import re
import tempfile
import unittest
from pathlib import Path

from tests.outils_html import assert_html_seul
from transcription_bench.operations import CreneauOperations
from transcription_bench.web import (
    ConfigApplication,
    ServicesApplication,
    create_app,
)
from transcription_bench.web.app import (
    DOSSIER_FEUILLES,
    NOM_FEUILLE_APP,
    NOM_FEUILLE_SUMI,
    TYPE_FEUILLE,
)

ADRESSE_LOCALE = "127.0.0.1"
PORT_TEST = 8765
RACINE_DEPOT = Path(__file__).resolve().parents[1]

# SHA-256 de la copie figée de `sumi.min.css`, consigné dans PROVENANCE.md.
SHA256_SUMI = "3535cf90e19150a2805dd57ad442d8f6e4a04ed4f50aa53b34b8306d10297116"

JETONS_COULEUR = (
    "--s-bg",
    "--s-surface",
    "--s-card",
    "--s-card-section",
    "--s-text",
    "--s-muted",
    "--s-border",
    "--s-border-strong",
    "--s-primary",
    "--s-on-primary",
    "--s-secondary",
    "--s-on-secondary",
    "--s-contrast",
    "--s-on-contrast",
    "--s-success",
    "--s-warning",
    "--s-danger",
    "--s-code-bg",
)

PROPRIETES_AUTORISEES = frozenset(
    {"white-space", "overflow-wrap", "min-width", "--s-btn", "--s-btn-on", *JETONS_COULEUR}
)

# `min-width` n'est admis que pour les `pre` des cellules (voir
# `test_largeur_minimale_des_transcriptions_dans_les_cellules`) : ailleurs, il
# imposerait une largeur minimale au-delà du besoin de coupure de D4-1.
SELECTEURS_LARGEUR_MINIMALE = ("td pre", "th pre")

# Sélecteurs de coupure d'`app.css` (design D4-1) : `anywhere` hors tableaux,
# `break-word` dans les cellules (où `anywhere` rétrécirait les colonnes et
# empêcherait le conteneur défilant de faire son office). `overflow-wrap`
# étant hérité, les éléments coupés sont répétés dans les cellules.
SELECTEURS_COUPURE_ANYWHERE = ("p", "li", "strong", "dd", "h1", "h2", "h3", "h4", "dt", "code")
SELECTEURS_COUPURE_TABLEAU = (
    "td",
    "th",
    "td p",
    "th p",
    "td li",
    "th li",
    "td strong",
    "th strong",
    "td dd",
    "th dd",
    "td h1",
    "th h1",
    "td h2",
    "th h2",
    "td h3",
    "th h3",
    "td h4",
    "th h4",
    "td dt",
    "th dt",
    "td code",
    "th code",
    "td pre",
    "th pre",
)

# Niveaux de titre réellement employés par les gabarits : une empreinte
# SHA-256 peut se trouver dans un titre depuis la renumérotation du design D7
# (`h2` sur la page de comparaison), donc chaque niveau doit couper.
NIVEAUX_TITRE = ("h1", "h2", "h3", "h4")

# Paires texte/fond contrôlées par le design D6, en clair comme en sombre.
PAIRES_CONTRASTE = (
    ("--s-text", "--s-bg"),
    ("--s-muted", "--s-bg"),
    ("--s-on-primary", "--s-primary"),
    ("--s-on-secondary", "--s-secondary"),
    ("--s-on-contrast", "--s-contrast"),
    ("--s-on-primary", "--s-danger"),
    ("--s-on-primary", "--s-success"),
    ("--s-primary", "--s-bg"),
    ("--s-primary", "--s-surface"),
    ("--s-primary", "--s-card"),
)
CONTRASTE_MINIMAL = 4.5

# Paires de composants d'interface (WCAG 1.4.11) : la bordure d'un champ doit
# se distinguer du fond, avec un seuil de 3.
PAIRES_CONTRASTE_COMPOSANT = (("--s-border-strong", "--s-bg"),)
CONTRASTE_MINIMAL_COMPOSANT = 3.0

MOTIF_COMMENTAIRE = re.compile(r"/\*.*?\*/", re.S)
MOTIF_REGLE = re.compile(r"([^{}]+)\{([^{}]*)\}", re.S)
MOTIF_DECLARATION = re.compile(r"([-A-Za-z_][\w-]*)\s*:\s*([^;{}]+)")
MOTIF_JETON = re.compile(r"(--s-[a-z0-9-]+)\s*:\s*(#[0-9A-Fa-f]{6})")
MOTIF_HEXA = re.compile(r"#[0-9A-Fa-f]{6}")
PRELUDE_SOMBRE = "@media (prefers-color-scheme: dark)"
SELECTEUR_CLAIR = ":root"
SELECTEUR_SOMBRE = ':root:not([data-theme="light"])'


def sans_commentaires(css: str) -> str:
    """Feuille privée de ses commentaires, longueur conservée pour les indices."""
    return MOTIF_COMMENTAIRE.sub(lambda trouve: " " * len(trouve.group(0)), css)


def blocs(css: str) -> list[tuple[str, int, int, int]]:
    """Blocs : (préambule, début du préambule, début et fin du contenu)."""
    resultat: list[tuple[str, int, int, int]] = []
    pile: list[tuple[str, int, int]] = []
    debut = 0
    for position, caractere in enumerate(css):
        if caractere == "{":
            pile.append((css[debut:position].strip(), debut, position + 1))
            debut = position + 1
        elif caractere == "}":
            if not pile:
                raise AssertionError(
                    f"accolade fermante sans bloc dans {NOM_FEUILLE_APP}"
                )
            preambule, debut_preambule, ouverture = pile.pop()
            resultat.append((preambule, debut_preambule, ouverture, position))
            debut = position + 1
        elif caractere == ";":
            debut = position + 1
    if pile:
        raise AssertionError(f"bloc non fermé dans {NOM_FEUILLE_APP}")
    return resultat


def declarations_positionnees(css: str) -> list[tuple[str, str, int]]:
    """(propriété, valeur, position) déclarés, à toute profondeur de blocs.

    Les préambules de règles et d'at-rules sont ignorés : une déclaration du
    parent n'est plus masquée par un bloc imbriqué
    (`button{font-size:3em;&.x{color:red}}`).
    """
    texte = sans_commentaires(css)
    trouvees: list[tuple[str, str, int]] = []
    debut = 0
    for position, caractere in enumerate(texte):
        if caractere not in "{};":
            continue
        segment = texte[debut:position]
        if caractere != "{":
            declaration = MOTIF_DECLARATION.fullmatch(segment.strip())
            if declaration:
                decalage = len(segment) - len(segment.lstrip())
                trouvees.append(
                    (
                        declaration.group(1).lower(),
                        declaration.group(2).strip(),
                        debut + decalage,
                    )
                )
        debut = position + 1
    return trouvees


def declarations(css: str) -> list[tuple[str, str]]:
    """Couples (propriété, valeur) déclarés, préambules d'at-rules exclus."""
    return [
        (propriete, valeur)
        for propriete, valeur, _ in declarations_positionnees(css)
    ]


def regles(css: str) -> dict[str, dict[str, str]]:
    """Déclarations de chaque sélecteur, at-rule englobante non comptée."""
    sans_commentaires_css = sans_commentaires(css)
    feuille: dict[str, dict[str, str]] = {}
    for regle in MOTIF_REGLE.finditer(sans_commentaires_css):
        declarations_regle = {
            declaration.group(1).lower(): declaration.group(2).strip()
            for declaration in MOTIF_DECLARATION.finditer(regle.group(2))
        }
        for selecteur in regle.group(1).split(","):
            selecteur = selecteur.strip()
            if selecteur:
                feuille.setdefault(selecteur, {}).update(declarations_regle)
    return feuille


def lire_feuille(nom_fichier: str) -> str:
    """Contenu d'une feuille figée, lu en UTF-8 explicite."""
    return (DOSSIER_FEUILLES / nom_fichier).read_text(encoding="utf-8")


def feuilles_par_theme(css: str) -> tuple[str, str]:
    """Partie claire (tous les blocs `:root` hors media) et contenu du bloc sombre.

    Les jetons de couleur ne peuvent être déclarés que dans `:root` hors du
    bloc sombre, ou dans `:root:not([data-theme="light"])` à l'intérieur de
    celui-ci ; toute autre structure échoue clairement.
    """
    texte = sans_commentaires(css)
    decoupage = blocs(texte)
    sombres = [bloc for bloc in decoupage if bloc[0] == PRELUDE_SOMBRE]
    if len(sombres) != 1:
        raise AssertionError(
            f"{NOM_FEUILLE_APP} : un seul bloc « {PRELUDE_SOMBRE} » attendu, "
            f"{len(sombres)} trouvé(s)"
        )
    _, debut_sombre, ouverture, fermeture = sombres[0]
    clair = texte[:debut_sombre] + texte[fermeture + 1 :]
    sombre = texte[ouverture:fermeture]

    controles: dict[str, set[str]] = {"clair": set(), "sombre": set()}
    for propriete, valeur, position in declarations_positionnees(css):
        if not propriete.startswith("--s-") or not MOTIF_HEXA.fullmatch(valeur):
            continue
        englobants = [
            bloc for bloc in decoupage if bloc[2] <= position <= bloc[3]
        ]
        if not englobants:
            raise AssertionError(
                f"{NOM_FEUILLE_APP} : jeton {propriete} déclaré hors de tout bloc"
            )
        preambule = min(englobants, key=lambda bloc: bloc[3] - bloc[2])[0]
        if ouverture <= position <= fermeture:
            theme, attendu = "sombre", SELECTEUR_SOMBRE
        else:
            theme, attendu = "clair", SELECTEUR_CLAIR
        if preambule != attendu:
            raise AssertionError(
                f"{NOM_FEUILLE_APP} : jeton {propriete} déclaré dans "
                f"« {preambule} » au lieu de « {attendu} »"
            )
        if propriete in controles[theme]:
            raise AssertionError(
                f"{NOM_FEUILLE_APP} : jeton {propriete} redéclaré dans le thème {theme}"
            )
        controles[theme].add(propriete)
    return clair, sombre


def jetons_couleur(css_theme: str) -> dict[str, str]:
    """Jetons de couleur hexadécimaux d'une partie de feuille, commentaires exclus."""
    return {
        jeton: valeur
        for jeton, valeur in MOTIF_JETON.findall(sans_commentaires(css_theme))
    }


def luminance(hexa: str) -> float:
    """Luminance relative WCAG d'une couleur `#rrggbb`."""
    composantes = [
        int(hexa.lstrip("#")[decalage : decalage + 2], 16) / 255
        for decalage in (0, 2, 4)
    ]

    def lineariser(canal: float) -> float:
        return canal / 12.92 if canal <= 0.03928 else ((canal + 0.055) / 1.055) ** 2.4

    rouge, vert, bleu = (lineariser(canal) for canal in composantes)
    return 0.2126 * rouge + 0.7152 * vert + 0.0722 * bleu


def contraste(premier: str, second: str) -> float:
    """Rapport de contraste WCAG entre deux couleurs opaques."""
    plus_clair, plus_sombre = sorted(
        (luminance(premier), luminance(second)), reverse=True
    )
    return (plus_clair + 0.05) / (plus_sombre + 0.05)


class SocleFeuillesTest(unittest.TestCase):
    """Application locale et client de test, sans aucune donnée réelle."""

    def setUp(self) -> None:
        temporaire = tempfile.TemporaryDirectory()
        self.addCleanup(temporaire.cleanup)
        self.dossier_data = Path(temporaire.name) / "data"
        self.app = create_app(
            ConfigApplication(port=PORT_TEST, dossier_data=self.dossier_data),
            ServicesApplication(creneau=CreneauOperations()),
        )
        self.client = self.app.test_client()

    def base_url(self, port: int = PORT_TEST) -> str:
        return f"http://{ADRESSE_LOCALE}:{port}"


class RoutesFeuillesTest(SocleFeuillesTest):
    """Routes fixes `/sumi.css` et `/app.css`, hors ligne et sans dossier statique."""

    def test_feuilles_servies_avec_entetes_fixes(self) -> None:
        for chemin in ("/sumi.css", "/app.css"):
            with self.subTest(chemin=chemin):
                reponse = self.client.get(chemin, base_url=self.base_url())

                self.assertEqual(reponse.status_code, 200)
                self.assertEqual(reponse.headers["Content-Type"], TYPE_FEUILLE)
                self.assertEqual(
                    reponse.headers["X-Content-Type-Options"], "nosniff"
                )
                self.assertEqual(reponse.headers["Cache-Control"], "no-cache")
                self.assertNotIn("Set-Cookie", reponse.headers)
                self.assertTrue(reponse.get_data())

    def test_feuilles_servies_sont_les_copies_du_paquet(self) -> None:
        for chemin, nom_fichier in (
            ("/sumi.css", NOM_FEUILLE_SUMI),
            ("/app.css", NOM_FEUILLE_APP),
        ):
            with self.subTest(chemin=chemin):
                corps = self.client.get(chemin, base_url=self.base_url()).get_data()

                self.assertEqual(corps, (DOSSIER_FEUILLES / nom_fichier).read_bytes())

    def test_feuilles_decodees_en_utf8(self) -> None:
        for chemin in ("/sumi.css", "/app.css"):
            with self.subTest(chemin=chemin):
                corps = self.client.get(chemin, base_url=self.base_url()).get_data()

                self.assertTrue(corps.decode("utf-8"))

    def test_accueil_relie_les_deux_feuilles_servies(self) -> None:
        # Lot 2 : les gabarits se relient aux deux feuilles servies, dans
        # l'ordre `/sumi.css` puis `/app.css`. Le contrôle précis des `link`
        # est dans `tests/test_habillage.py` ; ici, on vérifie que les deux
        # chemins liés sont bien ceux que l'application sert.
        corps = self.client.get("/", base_url=self.base_url()).get_data(as_text=True)
        page = assert_html_seul(self, corps)

        for _, chemin in page.feuilles:
            reponse = self.client.get(chemin, base_url=self.base_url())
            self.assertEqual(reponse.status_code, 200, chemin)

    def test_host_non_local_refuse_pour_les_feuilles(self) -> None:
        for chemin in ("/sumi.css", "/app.css"):
            for hote in ("evil.example:8765", "127.0.0.1:8766", "127.0.0.1"):
                with self.subTest(chemin=chemin, hote=hote):
                    reponse = self.client.get(
                        chemin,
                        base_url=self.base_url(),
                        headers={"Host": hote},
                    )

                    self.assertEqual(reponse.status_code, 403)
                    self.assertIn("text/html", reponse.headers["Content-Type"])
                    self.assertNotEqual(reponse.headers["Content-Type"], TYPE_FEUILLE)

    def test_adresse_locale_et_localhost_acceptes(self) -> None:
        for base in (self.base_url(), f"http://localhost:{PORT_TEST}"):
            with self.subTest(base=base):
                for chemin in ("/sumi.css", "/app.css"):
                    reponse = self.client.get(chemin, base_url=base)
                    self.assertEqual(reponse.status_code, 200, chemin)

    def test_aucun_service_de_fichiers_arbitraires(self) -> None:
        chemins = (
            "/static/base.css",
            "/sumi.min.css",
            "/ressources/sumi.min.css",
            "/static/../transcription_bench/web/ressources/sumi.min.css",
            "/%2e%2e/pyproject.toml",
            "/sumi.css/../pyproject.toml",
        )
        for chemin in chemins:
            with self.subTest(chemin=chemin):
                reponse = self.client.get(chemin, base_url=self.base_url())

                self.assertEqual(reponse.status_code, 404)
                self.assertNotIn("--s-bg", reponse.get_data(as_text=True))

    def test_methodes_non_autorisees_sur_les_feuilles(self) -> None:
        for chemin in ("/sumi.css", "/app.css"):
            with self.subTest(chemin=chemin):
                reponse = self.client.post(
                    chemin,
                    data={},
                    base_url=self.base_url(),
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                )

                # Le contrôle Host puis jeton s'applique avant la méthode : le
                # refus est toujours 403, jamais une réponse 405 ni une feuille.
                self.assertEqual(reponse.status_code, 403)
                self.assertIn("text/html", reponse.headers["Content-Type"])
                self.assertNotEqual(reponse.headers["Content-Type"], TYPE_FEUILLE)


class CopieFigeeTest(SocleFeuillesTest):
    """Condensat, provenance et fins de ligne de la copie de Sumi.css."""

    def test_sha256_de_la_copie(self) -> None:
        contenu = (DOSSIER_FEUILLES / NOM_FEUILLE_SUMI).read_bytes()

        self.assertEqual(len(contenu), 28245)
        self.assertEqual(hashlib.sha256(contenu).hexdigest(), SHA256_SUMI)

    def test_note_de_provenance_et_condensat_concordent(self) -> None:
        note = (DOSSIER_FEUILLES / "PROVENANCE.md").read_text(encoding="utf-8")

        self.assertIn(SHA256_SUMI, note)
        self.assertIn("cee85b75efb2f129b82bc014439381b57ede7c22", note)
        self.assertIn("v1.0.0", note)
        self.assertIn("2026-11-03", note)
        self.assertIn("LICENSE-Sumi.css", note)

    def test_copie_sans_fin_de_ligne_convertie(self) -> None:
        contenu = (DOSSIER_FEUILLES / NOM_FEUILLE_SUMI).read_bytes()

        self.assertNotIn(b"\r\n", contenu)

    def test_gitattributes_declare_la_copie_sans_conversion(self) -> None:
        regles = (RACINE_DEPOT / ".gitattributes").read_text(encoding="utf-8")

        ligne = "transcription_bench/web/ressources/sumi.min.css -text"
        self.assertIn(ligne, regles)

    def test_licence_sumi_jointe(self) -> None:
        licence = (DOSSIER_FEUILLES / "LICENSE-Sumi.css").read_text(encoding="utf-8")

        self.assertIn("MIT License", licence)
        self.assertIn("Vladimir Carrer", licence)
        en_tete = lire_feuille(NOM_FEUILLE_SUMI)[:200]
        self.assertIn("MIT License", en_tete)


class FeuilleComplementaireTest(SocleFeuillesTest):
    """Bornes d'`app.css` : propriétés, jetons, thème et contraste."""

    def setUp(self) -> None:
        super().setUp()
        self.css = lire_feuille(NOM_FEUILLE_APP)
        self.clair, self.sombre = feuilles_par_theme(self.css)

    def test_aucune_ressource_externe(self) -> None:
        self.assertNotIn("@import", self.css)
        self.assertNotIn("url(", self.css)

    def test_proprietes_declarees_autorisees(self) -> None:
        declarees = {propriete for propriete, _ in declarations(self.css)}

        self.assertLessEqual(declarees, PROPRIETES_AUTORISEES)
        self.assertIn("white-space", declarees)
        self.assertIn("overflow-wrap", declarees)
        self.assertIn("--s-btn", declarees)
        self.assertIn("--s-btn-on", declarees)

    def test_jetons_de_couleur_declares_dans_les_deux_themes(self) -> None:
        for nom, partie in (("clair", self.clair), ("sombre", self.sombre)):
            with self.subTest(theme=nom):
                jetons = jetons_couleur(partie)

                self.assertLessEqual(set(JETONS_COULEUR), set(jetons))

    def test_commentaires_et_theme_clair_apres_le_bloc_sombre(self) -> None:
        # Un jeton écrit dans un commentaire n'est pas une déclaration ; un
        # second bloc `:root` clair, placé après le bloc sombre, compte aussi.
        css = (
            self.css.replace(
                "--s-bg: #fffcf0; /* papier */",
                "--s-bg: #fffcf0; /* --s-bg: #000000; */",
            )
            + "\n:root {\n  --s-apres: #123456;\n}\n"
        )

        clair, _ = feuilles_par_theme(css)
        jetons = jetons_couleur(clair)
        self.assertEqual(jetons["--s-bg"], "#fffcf0")
        self.assertEqual(jetons["--s-apres"], "#123456")

    def test_jeton_hors_structure_echoue_clairement(self) -> None:
        css = self.css + "\n.encart {\n  --s-bg: #000000;\n}\n"

        with self.assertRaisesRegex(AssertionError, "déclaré dans « .encart »"):
            feuilles_par_theme(css)

    def test_declarations_detectees_dans_les_blocs_imbriques(self) -> None:
        # Une règle imbriquée ne doit pas masquer la déclaration du parent.
        couples = declarations("button { font-size: 3em; &.x { color: red; } }")

        self.assertEqual(couples, [("font-size", "3em"), ("color", "red")])

    def test_jetons_surchargent_ceux_de_sumi(self) -> None:
        # Sumi déclare le clair sur `:root` et le sombre sur
        # `:root:not([data-theme="light"])` : app.css doit employer les mêmes
        # sélecteurs pour l'emporter à spécificité égale.
        self.assertRegex(self.clair, r":root\s*\{")
        self.assertIn(':root:not([data-theme="light"])', self.sombre)

    def test_licence_flexoki_jointe_et_citee(self) -> None:
        licence = (DOSSIER_FEUILLES / "LICENSE-Flexoki").read_text(encoding="utf-8")
        note = (DOSSIER_FEUILLES / "PROVENANCE.md").read_text(encoding="utf-8")

        self.assertIn("MIT License", licence)
        self.assertIn("Steph Ango", licence)
        self.assertIn("LICENSE-Flexoki", note)

    def test_bouton_destructeur_en_couleur_de_danger(self) -> None:
        couples = declarations(self.css)
        regles = {
            propriete: valeur
            for propriete, valeur in couples
            if propriete in ("--s-btn", "--s-btn-on")
        }

        self.assertIn("button.danger", self.css)
        self.assertEqual(regles, {"--s-btn": "var(--s-danger)", "--s-btn-on": "var(--s-on-primary)"})

    def test_retours_a_la_ligne_des_contenus_longs(self) -> None:
        couples = declarations(self.css)
        valeurs: dict[str, set[str]] = {}
        for propriete, valeur in couples:
            valeurs.setdefault(propriete, set()).add(valeur)

        self.assertIn("pre-wrap", valeurs["white-space"])
        self.assertIn("anywhere", valeurs["overflow-wrap"])
        self.assertIn("break-word", valeurs["overflow-wrap"])
        self.assertIn("pre", self.css)
        self.assertIn("td", self.css)
        self.assertIn("th", self.css)

        # Coupure des valeurs sans espace (chemins, empreintes SHA-256) :
        # `anywhere` sur le texte courant, `break-word` dans les tableaux.
        feuille = regles(self.css)
        self.assertEqual(feuille["pre"]["white-space"], "pre-wrap")
        self.assertEqual(feuille["pre"]["overflow-wrap"], "anywhere")
        for selecteur in SELECTEURS_COUPURE_ANYWHERE:
            with self.subTest(selecteur=selecteur):
                self.assertIn(selecteur, feuille)
                self.assertEqual(feuille[selecteur]["overflow-wrap"], "anywhere")
        for selecteur in SELECTEURS_COUPURE_TABLEAU:
            with self.subTest(selecteur=selecteur):
                self.assertIn(selecteur, feuille)
                self.assertEqual(feuille[selecteur]["overflow-wrap"], "break-word")

    def test_tous_les_niveaux_de_titre_coupent_les_valeurs_longues(self) -> None:
        # Intention de D4-1 : les titres portent parfois une empreinte SHA-256
        # (page de comparaison) ; tout niveau de titre employé doit donc couper,
        # hors tableaux en `anywhere` et dans les cellules en `break-word`.
        feuille = regles(self.css)
        for niveau in NIVEAUX_TITRE:
            with self.subTest(niveau=niveau):
                self.assertIn(niveau, SELECTEURS_COUPURE_ANYWHERE)
                self.assertEqual(feuille[niveau]["overflow-wrap"], "anywhere")
                for cellule in ("td", "th"):
                    selecteur = f"{cellule} {niveau}"
                    self.assertIn(selecteur, SELECTEURS_COUPURE_TABLEAU)
                    self.assertEqual(feuille[selecteur]["overflow-wrap"], "break-word")

    def test_cellules_repetent_tous_les_elements_coupes(self) -> None:
        # Intention de D4-1 : `overflow-wrap` étant hérité, tout élément coupé
        # hors tableau doit être répété dans les cellules pour y garder
        # `break-word`. Sans `td pre`/`th pre`, un `pre` garde `anywhere` dans
        # une cellule et rétrécit les colonnes à ~9 caractères par ligne à
        # 360 px. La liste des cellules reste le miroir du texte courant.
        feuille = regles(self.css)
        for selecteur in ("pre", *SELECTEURS_COUPURE_ANYWHERE):
            with self.subTest(selecteur=selecteur):
                for cellule in ("td", "th"):
                    dans_cellule = f"{cellule} {selecteur}"
                    self.assertIn(dans_cellule, SELECTEURS_COUPURE_TABLEAU)
                    self.assertEqual(
                        feuille[dans_cellule]["overflow-wrap"], "break-word"
                    )

    def test_largeur_minimale_des_transcriptions_dans_les_cellules(self) -> None:
        # Intention du lot 6, constat navigateur en 360 px : sans largeur
        # minimale, la colonne de la vue de comparaison se réduit au plus petit
        # mot et la transcription n'affiche plus qu'une dizaine de caractères
        # par ligne. 14rem ≈ 25 caractères monospace ; la cellule s'élargit et
        # le conteneur `overflow-auto` défile alors horizontalement.
        # `min-width` ne vaut que pour ces sélecteurs, et `min-width` plutôt que
        # `width` pour ne jamais brider un texte plus large.
        feuille = regles(self.css)
        for selecteur in SELECTEURS_LARGEUR_MINIMALE:
            with self.subTest(selecteur=selecteur):
                self.assertEqual(feuille[selecteur]["min-width"], "14rem")

        porteurs: set[str] = set()
        for regle in MOTIF_REGLE.finditer(sans_commentaires(self.css)):
            proprietes = {
                declaration.group(1).lower()
                for declaration in MOTIF_DECLARATION.finditer(regle.group(2))
            }
            if "min-width" in proprietes:
                porteurs.update(
                    selecteur.strip()
                    for selecteur in regle.group(1).split(",")
                    if selecteur.strip()
                )
        self.assertEqual(porteurs, set(SELECTEURS_LARGEUR_MINIMALE))

    def test_contraste_des_paires_de_jetons(self) -> None:
        for nom, partie in (("clair", self.clair), ("sombre", self.sombre)):
            jetons = jetons_couleur(partie)
            for premier, second in PAIRES_CONTRASTE:
                with self.subTest(theme=nom, paire=f"{premier}/{second}"):
                    mesure = contraste(jetons[premier], jetons[second])
                    self.assertGreaterEqual(
                        mesure,
                        CONTRASTE_MINIMAL,
                        f"{nom} : {premier} {jetons[premier]} sur {second} "
                        f"{jetons[second]} ne donne que {mesure:.2f}",
                    )

    def test_contraste_des_bordures_de_composants(self) -> None:
        # WCAG 1.4.11 : une bordure de champ est un composant d'interface, son
        # contraste avec le fond vaut au moins 3 (et non 4,5 comme du texte).
        for nom, partie in (("clair", self.clair), ("sombre", self.sombre)):
            jetons = jetons_couleur(partie)
            for premier, second in PAIRES_CONTRASTE_COMPOSANT:
                with self.subTest(theme=nom, paire=f"{premier}/{second}"):
                    mesure = contraste(jetons[premier], jetons[second])
                    self.assertGreaterEqual(
                        mesure,
                        CONTRASTE_MINIMAL_COMPOSANT,
                        f"{nom} : {premier} {jetons[premier]} sur {second} "
                        f"{jetons[second]} ne donne que {mesure:.2f}",
                    )


if __name__ == "__main__":
    unittest.main()
