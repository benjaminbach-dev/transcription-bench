"""Tests des grilles d'extraction : découverte, lecture bornée, interprétation.

Tâche 1.1 du change `ajouter-bench-extraction` : le module `grilles` est
exercé sans réseau, sans écriture dans le dépôt et sans moteur. Les grilles
sont écrites dans des dossiers temporaires (`tempfile`) sous une racine
passée en argument : le dossier `grilles/` du dépôt n'existe pas et n'est
jamais créé par ces tests. La règle « Liste », la normalisation des clés,
les blocs de code, les limites et le confinement des noms sont couverts case
par case sur les exemples du design D1.
"""

from __future__ import annotations

import hashlib
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from transcription_bench.grilles import (
    GRID_DIR_NAME,
    MAX_FIELDS,
    MAX_GRID_BYTES,
    NAME_REJECTED_ERROR,
    RESERVED_KEY,
    RULE_DUPLICATE_KEY,
    RULE_EMPTY_KEY,
    RULE_ENCODING,
    RULE_FIELD_LIMIT,
    RULE_HEADING_DEPTH,
    RULE_NO_FIELD,
    RULE_ORPHAN_SUBFIELD,
    RULE_RESERVED_KEY,
    RULE_SIZE_LIMIT,
    RULE_TITLE,
    RULE_UNCLOSED_BLOCK,
    GridUnreadable,
    discover_grids,
    grid_key,
    read_grid,
)
from transcription_bench.paths import ValeurRefusee

#: Grille d'exemple du design D1 (consultation de médecine générale).
GRILLE_EXEMPLE = """\
# Consultation de médecine générale

Consignes : n'extraire que ce qui est dit pendant la consultation.

## Qui ?
Personnes présentes et leur rôle (patient, accompagnant, soignant).

## Quand ?
Date, moment ou délai évoqués pour les faits rapportés.

## Motif de consultation ?

## Symptômes déclarés ?
Liste. Un symptôme par entrée, avec durée ou intensité si dites.

## Examens pratiqués ?
Liste. Examen clinique ou complémentaire réalisé ou demandé, avec résultat s'il est dit.

## Doute restant ?
Hypothèses non tranchées, points à vérifier.

## Prescription ?
Liste.
### Médicament
### Posologie
### Durée

## Prise en charge ?
Orientation, conseils, suivi prévu.
"""

#: Grille valides dont les consignes contiennent des blocs de code fermés,
#: avec des titres qui ne doivent pas être interprétés à l'intérieur.
GRILLE_BLOCS = """\
# Grille avec blocs

## Case avec exemple ?
Consigne précédant l'exemple :

```
## Exemple dans le bloc
### Et un autre
```
Suite de la consigne.

## Case en tildes ?
Un bloc en tildes :
~~~
#### Profondeur dans le bloc
### Un autre titre
~~~
Fin de la consigne.
"""


class SocleGrillesTest(unittest.TestCase):
    """Racine temporaire et helpers communs : aucune écriture dans le dépôt."""

    def setUp(self) -> None:
        temporaire = tempfile.TemporaryDirectory()
        self.addCleanup(temporaire.cleanup)
        self.racine = Path(temporaire.name)
        self.dossier = self.racine / GRID_DIR_NAME

    def ecrire(self, texte: str, nom: str = "exemple") -> Path:
        """Écrit une grille de test dans le dossier temporaire `grilles/`."""
        self.dossier.mkdir(exist_ok=True)
        chemin = self.dossier / f"{nom}.md"
        chemin.write_text(texte, encoding="utf-8")
        return chemin

    def write_grid_bytes(self, content: bytes) -> Path:
        """Écrit la grille sans conversion des fins de ligne."""
        self.dossier.mkdir(exist_ok=True)
        path = self.dossier / "exemple.md"
        path.write_bytes(content)
        return path

    def lire(self, nom: str = "exemple"):
        """Lit la grille écrite par `ecrire`, sous la racine temporaire."""
        return read_grid(nom, self.racine)


class ClesGrillesTest(unittest.TestCase):
    """Normalisation D1 des clés, sur les exemples du design et leurs bords."""

    def test_exemples_du_design(self) -> None:
        self.assertEqual(grid_key("Examens pratiqués ?"), "examens_pratiques")
        self.assertEqual(grid_key("Œdème / douleur !!"), "oedeme_douleur")

    def test_accents_casse_et_chiffres(self) -> None:
        self.assertEqual(grid_key("Àçîôû Élève"), "aciou_eleve")
        self.assertEqual(grid_key("SYMPTÔMES DÉCLARÉS"), "symptomes_declares")
        self.assertEqual(grid_key("Posologie 2 fois/jour"), "posologie_2_fois_jour")

    def test_ligatures_oe_ae_ss(self) -> None:
        self.assertEqual(grid_key("Œdème"), "oedeme")
        self.assertEqual(grid_key("œuvres"), "oeuvres")
        self.assertEqual(grid_key("Cæsar"), "caesar")
        self.assertEqual(grid_key("Straße"), "strasse")

    def test_majuscule_allemande_donne_ss(self) -> None:
        self.assertEqual(grid_key("\u1e9e"), "ss")
        self.assertEqual(grid_key("STRA\u1e9eE"), "strasse")

    def test_ponctuation_repetee_reduite_a_un_seul_separateur(self) -> None:
        self.assertEqual(grid_key("Doute ?!.. vraiment ??"), "doute_vraiment")
        self.assertEqual(grid_key("Titre — avec  tiré"), "titre_avec_tire")

    def test_libelles_sans_alphanumeriques_donnent_cle_vide(self) -> None:
        self.assertEqual(grid_key("???"), "")
        self.assertEqual(grid_key("—"), "")
        self.assertEqual(grid_key(""), "")

    def test_libelle_reserve_retrouve_par_normalisation(self) -> None:
        self.assertEqual(grid_key("Autres informations ?"), "autres_informations")
        self.assertEqual(RESERVED_KEY, "autres_informations")


class LectureGrillesTest(SocleGrillesTest):
    """Lecture interprétée d'une grille : structure, règles D1 et refus."""

    def test_grille_d_exemple_entierement_interpretee(self) -> None:
        self.ecrire(GRILLE_EXEMPLE, "consultation-generale")

        grille = self.lire("consultation-generale")

        self.assertIsNone(grille.error)
        self.assertTrue(grille.valid)
        self.assertEqual(grille.name, "consultation-generale")
        self.assertEqual(grille.title, "Consultation de médecine générale")
        self.assertEqual(
            grille.general_instructions,
            "Consignes : n'extraire que ce qui est dit pendant la consultation.",
        )
        self.assertEqual(
            [case.key for case in grille.fields],
            [
                "qui",
                "quand",
                "motif_de_consultation",
                "symptomes_declares",
                "examens_pratiques",
                "doute_restant",
                "prescription",
                "prise_en_charge",
            ],
        )
        qui, quand, motif, symptomes, examens, doute, prescription, prise = (
            grille.fields
        )
        # Case texte simple : consigne conservée, ni liste ni sous-case.
        self.assertEqual(
            qui.instructions,
            "Personnes présentes et leur rôle (patient, accompagnant, soignant).",
        )
        self.assertFalse(qui.is_list)
        self.assertFalse(qui.composed)
        self.assertEqual(qui.line, 5)
        self.assertEqual(quand.subfields, ())
        # Case sans consigne : facultative, reste une case texte.
        self.assertIsNone(motif.instructions)
        self.assertFalse(motif.is_list)
        self.assertFalse(motif.composed)
        self.assertEqual(motif.key, "motif_de_consultation")
        # Cases listes de textes : « Liste. » en tête de consigne.
        self.assertTrue(symptomes.is_list)
        self.assertFalse(symptomes.composed)
        self.assertTrue(examens.is_list)
        self.assertEqual(examens.key, "examens_pratiques")
        self.assertEqual(doute.key, "doute_restant")
        # Case liste composée : consigne propre conservée, trois sous-cases.
        self.assertTrue(prescription.is_list)
        self.assertTrue(prescription.composed)
        self.assertEqual(prescription.instructions, "Liste.")
        self.assertEqual(prescription.line, 22)
        self.assertEqual(
            [sous.key for sous in prescription.subfields],
            ["medicament", "posologie", "duree"],
        )
        self.assertEqual(prescription.subfields[2].line, 26)
        self.assertIsNone(prescription.subfields[2].instructions)
        self.assertFalse(prescription.subfields[0].is_list)
        self.assertEqual(prise.instructions, "Orientation, conseils, suivi prévu.")
        # L'empreinte est celle des octets du fichier.
        self.assertEqual(
            grille.sha256,
            hashlib.sha256(
                (self.dossier / "consultation-generale.md").read_bytes()
            ).hexdigest(),
        )

    def test_case_texte_sans_consigne(self) -> None:
        self.ecrire("# Titre\n\n## Case vide ?\n")

        grille = self.lire()

        self.assertIsNone(grille.error)
        self.assertEqual(len(grille.fields), 1)
        case = grille.fields[0]
        self.assertEqual(case.key, "case_vide")
        self.assertIsNone(case.instructions)
        self.assertFalse(case.is_list)
        self.assertFalse(case.composed)

    def test_case_composee_sans_liste(self) -> None:
        self.ecrire("# T\n\n## Fiche ?\nDescription.\n### Nom\n### Âge\n")

        grille = self.lire()

        self.assertIsNone(grille.error)
        case = grille.fields[0]
        self.assertFalse(case.is_list)
        self.assertTrue(case.composed)
        self.assertEqual(case.instructions, "Description.")
        self.assertEqual([sous.key for sous in case.subfields], ["nom", "age"])

    def test_regle_liste_selon_premiere_ligne_non_vide(self) -> None:
        variantes = (
            ("Liste. Un par ligne", True),
            ("Liste:", True),
            ("Liste :", True),
            ("LISTE.", True),
            ("   Liste. avec des blancs de tête", True),
            ("Consigne d'abord.\nListe.", False),
            ("Listes des antécédents", False),
            ("Liste des antécédents", False),
            ("Liste", False),
        )
        for index, (consigne, attendu) in enumerate(variantes):
            with self.subTest(consigne=consigne):
                self.ecrire(f"# T\n\n## Case {index} ?\n{consigne}\n")

                grille = self.lire()

                self.assertIsNone(grille.error)
                self.assertEqual(grille.fields[0].is_list, attendu)

    def test_liste_espaces_unicode_admis_mot_ascii_seulement(self) -> None:
        variantes = (
            ("Liste\u00a0: insécable", True),
            ("Liste\u202f. espace fine", True),
            ("li\u017fte. long s", False),
        )
        for index, (consigne, attendu) in enumerate(variantes):
            with self.subTest(consigne=consigne):
                self.ecrire(f"# T\n\n## Case {index} ?\n{consigne}\n")

                grille = self.lire()

                self.assertIsNone(grille.error)
                self.assertEqual(grille.fields[0].is_list, attendu)

    def test_consignes_generales_absentes(self) -> None:
        self.ecrire("# T\n\n## Case ?\ntexte\n")

        grille = self.lire()

        self.assertIsNone(grille.error)
        self.assertIsNone(grille.general_instructions)

    def test_consignes_generales_multilignes(self) -> None:
        self.ecrire("# T\n\nLigne une.\nLigne deux.\n\n## Case ?\ntexte\n")

        grille = self.lire()

        self.assertIsNone(grille.error)
        self.assertEqual(grille.general_instructions, "Ligne une.\nLigne deux.")

    def test_consigne_bords_retires_contenu_fidele(self) -> None:
        self.ecrire("# T\n\n## Case ?\n\n   Première ligne indentée.\n\nMilieu.\n\n")

        grille = self.lire()

        self.assertIsNone(grille.error)
        self.assertEqual(
            grille.fields[0].instructions,
            "Première ligne indentée.\n\nMilieu.",
        )

    def test_lignes_vides_en_tete_ignorees(self) -> None:
        self.ecrire("\n\n# T\n\n## Case ?\ntexte\n")

        grille = self.lire()

        self.assertIsNone(grille.error)
        self.assertEqual(grille.title, "T")
        self.assertEqual(grille.fields[0].line, 5)

    def test_titres_dans_blocs_de_code_non_interpretes(self) -> None:
        self.ecrire(GRILLE_BLOCS)

        grille = self.lire()

        self.assertIsNone(grille.error)
        self.assertEqual([case.key for case in grille.fields], [
            "case_avec_exemple",
            "case_en_tildes",
        ])
        premiere, seconde = grille.fields
        self.assertFalse(premiere.composed)
        self.assertFalse(seconde.composed)
        self.assertIn("## Exemple dans le bloc", premiere.instructions or "")
        self.assertIn("### Et un autre", premiere.instructions or "")
        self.assertIn("Suite de la consigne.", premiere.instructions or "")
        self.assertIn("#### Profondeur dans le bloc", seconde.instructions or "")
        self.assertIn("### Un autre titre", seconde.instructions or "")
        self.assertIn("Fin de la consigne.", seconde.instructions or "")

    def test_bloc_non_ferme_refuse(self) -> None:
        variantes = (
            (f"# T\n\n## Case ?\nConsigne.\n{cloture}\nx\n", 5)
            for cloture in ("```", "~~~")
        )
        for texte, ligne in variantes:
            with self.subTest(ligne=ligne):
                self.ecrire(texte)

                grille = self.lire()

                self.assertIsNotNone(grille.error)
                self.assertEqual(grille.error.rule, RULE_UNCLOSED_BLOCK)
                self.assertEqual(grille.error.line, ligne)

    def test_profondeur_excessive_refusee(self) -> None:
        for profondeur in ("####", "#####"):
            with self.subTest(profondeur=profondeur):
                self.ecrire(f"# T\n\n## Case ?\ntexte\n{profondeur} Trop ?\n")

                grille = self.lire()

                self.assertIsNotNone(grille.error)
                self.assertEqual(grille.error.rule, RULE_HEADING_DEPTH)
                self.assertEqual(grille.error.line, 5)

    def test_sous_case_orpheline_refusee(self) -> None:
        self.ecrire("# T\n\nConsigne générale.\n### Orphelin ?\n")

        grille = self.lire()

        self.assertIsNotNone(grille.error)
        self.assertEqual(grille.error.rule, RULE_ORPHAN_SUBFIELD)
        self.assertEqual(grille.error.line, 4)

    def test_aucune_case_refusee(self) -> None:
        for texte in ("# T\n\nConsignes seulement.\n", "# T\n"):
            with self.subTest(texte=texte):
                self.ecrire(texte)

                grille = self.lire()

                self.assertIsNotNone(grille.error)
                self.assertEqual(grille.error.rule, RULE_NO_FIELD)
                self.assertIsNone(grille.error.line)

    def test_second_titre_refuse(self) -> None:
        self.ecrire("# T\n\n## Case ?\ntexte\n# Second titre\n")

        grille = self.lire()

        self.assertIsNotNone(grille.error)
        self.assertEqual(grille.error.rule, RULE_TITLE)
        self.assertEqual(grille.error.line, 5)
        self.assertIn("ligne 1", grille.error.message)

    def test_premier_contenu_non_titre_refuse(self) -> None:
        variantes = (
            "Bonjour\n## Case ?\n",
            "## Case ?\ntexte\n",
            "#\n",
            "#   \n## Case ?\n",
        )
        for texte in variantes:
            with self.subTest(texte=texte):
                self.ecrire(texte)

                grille = self.lire()

                self.assertIsNotNone(grille.error)
                self.assertEqual(grille.error.rule, RULE_TITLE)
                self.assertEqual(grille.error.line, 1)

    def test_grille_vide_refusee(self) -> None:
        for texte in ("", "\n\n\n"):
            with self.subTest(texte=texte):
                self.ecrire(texte)

                grille = self.lire()

                self.assertIsNotNone(grille.error)
                self.assertEqual(grille.error.rule, RULE_TITLE)
                self.assertIsNone(grille.error.line)
                self.assertIn("vide", grille.error.message)

    def test_doublon_de_cles_refuse_en_citant_les_deux_lignes(self) -> None:
        self.ecrire("# T\n\n## Qui ?\ntexte\n## Qui\nautre\n")

        grille = self.lire()

        self.assertIsNotNone(grille.error)
        self.assertEqual(grille.error.rule, RULE_DUPLICATE_KEY)
        self.assertEqual(grille.error.line, 5)
        self.assertIn("ligne 3", grille.error.message)

    def test_doublon_de_sous_cases_refuse(self) -> None:
        self.ecrire("# T\n\n## Prescription ?\n### Posologie\n### Posologie\n")

        grille = self.lire()

        self.assertIsNotNone(grille.error)
        self.assertEqual(grille.error.rule, RULE_DUPLICATE_KEY)
        self.assertEqual(grille.error.line, 5)
        self.assertIn("ligne 4", grille.error.message)

    def test_cles_identiques_a_niveaux_differents_admises(self) -> None:
        self.ecrire("# T\n\n## Durée ?\ntexte\n## Médicament ?\nListe.\n### Durée\n")

        grille = self.lire()

        self.assertIsNone(grille.error)
        self.assertEqual(grille.fields[0].key, "duree")
        self.assertEqual(grille.fields[1].subfields[0].key, "duree")

    def test_cle_reservee_refusee_meme_en_sous_case(self) -> None:
        for texte, ligne in (
            ("# T\n\n## Autres informations ?\ntexte\n", 3),
            ("# T\n\n## Case ?\n### Autres informations\n", 4),
        ):
            with self.subTest(ligne=ligne):
                self.ecrire(texte)

                grille = self.lire()

                self.assertIsNotNone(grille.error)
                self.assertEqual(grille.error.rule, RULE_RESERVED_KEY)
                self.assertEqual(grille.error.line, ligne)

    def test_cle_vide_refusee(self) -> None:
        self.ecrire("# T\n\n## ???\n")

        grille = self.lire()

        self.assertIsNotNone(grille.error)
        self.assertEqual(grille.error.rule, RULE_EMPTY_KEY)
        self.assertEqual(grille.error.line, 3)

    def test_limite_de_cases_depassee(self) -> None:
        # 61 cases : le refus nomme la ligne de la 61e.
        texte = "# T\n\n" + "\n".join(
            f"## Case {index} ?" for index in range(1, 62)
        )
        self.ecrire(texte)

        grille = self.lire()

        self.assertIsNotNone(grille.error)
        self.assertEqual(grille.error.rule, RULE_FIELD_LIMIT)
        self.assertEqual(grille.error.line, 63)

    def test_sous_cases_comptees_dans_la_limite(self) -> None:
        # 59 cases, une 60e case, puis une sous-case : 61 au total.
        texte = (
            "# T\n\n"
            + "\n".join(f"## Case {index} ?" for index in range(1, 60))
            + "\n## Case 60 ?\n### Sous ?\n"
        )
        self.ecrire(texte)

        grille = self.lire()

        self.assertIsNotNone(grille.error)
        self.assertEqual(grille.error.rule, RULE_FIELD_LIMIT)
        self.assertEqual(grille.error.line, 63)

    def test_limite_de_cases_exacte_admise(self) -> None:
        texte = "# T\n\n" + "\n".join(
            f"## Case {index} ?" for index in range(1, MAX_FIELDS + 1)
        )
        self.ecrire(texte)

        grille = self.lire()

        self.assertIsNone(grille.error)
        self.assertEqual(len(grille.fields), MAX_FIELDS)

    def test_taille_maximale_exacte_admise(self) -> None:
        structure = b"# T\n\n## Case ?\n"
        path = self.write_grid_bytes(structure + b"x" * (MAX_GRID_BYTES - len(structure)))

        grille = self.lire()

        self.assertIsNone(grille.error)
        self.assertEqual(path.stat().st_size, MAX_GRID_BYTES)

    def test_taille_maximale_depassee_refusee(self) -> None:
        structure = b"# T\n\n## Case ?\n"
        path = self.write_grid_bytes(
            structure + b"x" * (MAX_GRID_BYTES - len(structure) + 1)
        )

        grille = self.lire()

        self.assertEqual(path.stat().st_size, MAX_GRID_BYTES + 1)
        self.assertIsNotNone(grille.error)
        self.assertEqual(grille.error.rule, RULE_SIZE_LIMIT)
        self.assertIsNone(grille.error.line)
        self.assertIn("volumineux", grille.error.message)
        # Refus avant lecture complète : aucune empreinte pour un fichier
        # dépassant la limite, la lecture reste bornée.
        self.assertIsNone(grille.sha256)

    def test_contenu_non_utf8_refuse(self) -> None:
        self.dossier.mkdir(exist_ok=True)
        chemin = self.dossier / "exemple.md"
        chemin.write_bytes(b"# T\n\n## Case ?\n\xfft texte\n")

        grille = self.lire()

        self.assertIsNotNone(grille.error)
        self.assertEqual(grille.error.rule, RULE_ENCODING)
        self.assertEqual(grille.error.line, 4)

    def test_bom_utf8_tolere(self) -> None:
        self.dossier.mkdir(exist_ok=True)
        chemin = self.dossier / "exemple.md"
        chemin.write_bytes(b"\xef\xbb\xbf# T\n\n## Case ?\ntexte\n")

        grille = self.lire()

        self.assertIsNone(grille.error)
        self.assertEqual(grille.title, "T")

    def test_noms_refuses_avant_lecture(self) -> None:
        self.ecrire("# T\n\n## Case ?\n")
        for nom in (
            "../ailleurs",
            "a/b",
            "..",
            "./exemple",
            "A",
            "a_b",
            "a" * 65,
            "exemple.md",
            "a\\b",
            "a:b",
            "",
            None,
        ):
            with self.subTest(nom=nom):
                with self.assertRaises(ValeurRefusee):
                    read_grid(nom, self.racine)

    def test_grille_inconnue_refusee_sans_creation(self) -> None:
        with self.assertRaises(ValeurRefusee) as contexte:
            read_grid("absente", self.racine)
        self.assertIn("absente", str(contexte.exception))

        # Une racine sans dossier `grilles/` n'est jamais créée par la lecture.
        ailleurs = self.racine / "ailleurs"
        with self.assertRaises(ValeurRefusee):
            read_grid("exemple", ailleurs)
        self.assertFalse((ailleurs / GRID_DIR_NAME).exists())

    def test_cible_repertoire_refusee(self) -> None:
        self.dossier.mkdir(exist_ok=True)
        (self.dossier / "repertoire.md").mkdir()

        with self.assertRaises(ValeurRefusee):
            self.lire("repertoire")

    def test_lien_symbolique_sortant_refuse(self) -> None:
        self.ecrire("# T\n\n## Case ?\n", "cible")
        exterieur = self.racine / "hors-grilles.md"
        exterieur.write_text("# Hors du dossier\n", encoding="utf-8")
        self.dossier.mkdir(exist_ok=True)
        try:
            os.symlink(exterieur, self.dossier / "sortant.md")
        except (OSError, NotImplementedError):
            self.skipTest("création de lien symbolique non autorisée sur ce poste")

        with self.assertRaises(ValeurRefusee):
            self.lire("sortant")

    def test_lien_symbolique_interne_admis(self) -> None:
        chemin = self.ecrire(GRILLE_EXEMPLE, "cible")
        try:
            os.symlink(chemin, self.dossier / "lien.md")
        except (OSError, NotImplementedError):
            self.skipTest("création de lien symbolique non autorisée sur ce poste")

        grille = self.lire("lien")

        self.assertIsNone(grille.error)
        self.assertEqual(grille.name, "lien")
        self.assertEqual(grille.sha256, hashlib.sha256(chemin.read_bytes()).hexdigest())

    def test_fins_de_ligne_crlf_interpretees_comme_lf(self) -> None:
        for nom, texte in (("exemple", GRILLE_EXEMPLE), ("blocs", GRILLE_BLOCS)):
            with self.subTest(grille=nom):
                self.dossier.mkdir(exist_ok=True)
                (self.dossier / f"{nom}-lf.md").write_bytes(texte.encode("utf-8"))
                (self.dossier / f"{nom}-crlf.md").write_bytes(
                    texte.replace("\n", "\r\n").encode("utf-8")
                )

                lf = self.lire(f"{nom}-lf")
                crlf = self.lire(f"{nom}-crlf")

                self.assertIsNone(crlf.error)
                self.assertEqual(crlf.title, lf.title)
                self.assertEqual(crlf.general_instructions, lf.general_instructions)
                self.assertEqual(crlf.fields, lf.fields)
                # L'empreinte porte sur les octets bruts : elle diffère, par nature.
                self.assertNotEqual(crlf.sha256, lf.sha256)

    def test_separateurs_unicode_ne_coupent_pas_les_lignes(self) -> None:
        # U+2028 et U+0085 au milieu d'une ligne : ni titre caché, ni décalage.
        self.ecrire(
            "# Titre\n\n## Case ?\nAvant\u2028## Caché ?\u0085suite\n\n"
            "## Autre ?\n## Case ?\n"
        )

        grille = self.lire()

        self.assertIsNotNone(grille.error)
        self.assertEqual(grille.error.rule, RULE_DUPLICATE_KEY)
        # Le numéro suit le découpage par LF : le doublon est à la ligne 7.
        self.assertEqual(grille.error.line, 7)
        # Les cases déjà fermées avant le doublon restent : « autre » aussi.
        self.assertEqual([case.key for case in grille.fields], ["case", "autre"])
        self.assertEqual(
            grille.fields[0].instructions, "Avant\u2028## Caché ?\u0085suite"
        )

    def test_fichier_illisible_leve_grid_unreadable_et_liste_avec_erreur(self) -> None:
        self.ecrire("# T\n\n## Case ?\n")
        avec_lecture_refusee = mock.patch.object(
            Path, "open", side_effect=PermissionError("refus")
        )
        with avec_lecture_refusee:
            with self.assertRaises(GridUnreadable) as contexte:
                self.lire()
            self.assertIn("lecture impossible", str(contexte.exception))

            resumes = discover_grids(self.racine)

        self.assertEqual(len(resumes), 1)
        self.assertIn("lecture impossible", resumes[0].error or "")


class DecouverteGrillesTest(SocleGrillesTest):
    """Découverte confinée de `grilles/` : états, empreinte, noms refusés."""

    def test_dossier_absent_liste_vide_sans_creation(self) -> None:
        absent = self.racine / "absent"

        self.assertEqual(discover_grids(absent), ())
        self.assertFalse(absent.exists())

    def test_liste_triee_avec_etats_et_empreinte(self) -> None:
        self.ecrire(GRILLE_EXEMPLE, "consultation-generale")
        self.ecrire("# T\n\n## Qui ?\ntexte\n## Qui\nautre\n", "doublon")
        (self.dossier / "Majus.md").write_text("# T\n\n## A ?\n", encoding="utf-8")
        (self.dossier / "notes.txt").write_text("pas une grille", encoding="utf-8")
        (self.dossier / "sous-dossier").mkdir()

        resumes = discover_grids(self.racine)

        self.assertEqual(
            [resume.name for resume in resumes],
            ["Majus.md", "consultation-generale", "doublon"],
        )
        refuse, valide, invalide = resumes
        # Nom non conforme : listé, jamais lu ni proposé à l'exécution.
        self.assertEqual(refuse.error, NAME_REJECTED_ERROR)
        self.assertIsNone(refuse.sha256)
        self.assertIsNone(refuse.field_count)
        # Grille valide : titre, cases de premier niveau, empreinte exacte.
        self.assertIsNone(valide.error)
        self.assertEqual(valide.title, "Consultation de médecine générale")
        self.assertEqual(valide.field_count, 8)
        self.assertEqual(
            valide.sha256,
            hashlib.sha256(
                (self.dossier / "consultation-generale.md").read_bytes()
            ).hexdigest(),
        )
        # Grille invalide : motif complet, cases non annoncées.
        self.assertIsNone(invalide.field_count)
        self.assertIn("ligne 5", invalide.error or "")

    def test_extension_exacte_md_exigee(self) -> None:
        self.ecrire(GRILLE_EXEMPLE, "consultation-generale")
        (self.dossier / "note.MD").write_text("# T\n\n## A ?\n", encoding="utf-8")
        (self.dossier / "double.md.md").write_text("# T\n\n## A ?\n", encoding="utf-8")

        resumes = discover_grids(self.racine)

        self.assertEqual(
            [resume.name for resume in resumes],
            ["consultation-generale", "double.md.md"],
        )
        self.assertIsNone(resumes[0].error)
        self.assertEqual(resumes[1].error, NAME_REJECTED_ERROR)

    def test_lien_symbolique_sortant_liste_nom_refuse(self) -> None:
        chemin = self.ecrire(GRILLE_EXEMPLE, "cible")
        exterieur = self.racine / "hors-grilles.md"
        exterieur.write_text("# Hors du dossier\n", encoding="utf-8")
        try:
            os.symlink(exterieur, self.dossier / "sortant.md")
        except (OSError, NotImplementedError):
            self.skipTest("création de lien symbolique non autorisée sur ce poste")

        resumes = discover_grids(self.racine)

        self.assertEqual([resume.name for resume in resumes], ["cible", "sortant.md"])
        self.assertIsNone(resumes[0].error)
        self.assertEqual(resumes[0].sha256, hashlib.sha256(chemin.read_bytes()).hexdigest())
        self.assertEqual(resumes[1].error, NAME_REJECTED_ERROR)
        self.assertIsNone(resumes[1].sha256)

    def test_grille_trop_volumineuse_listee_sans_empreinte(self) -> None:
        self.dossier.mkdir(exist_ok=True)
        (self.dossier / "grosse.md").write_bytes(b"x" * (MAX_GRID_BYTES + 10))

        with mock.patch("transcription_bench.grilles._read_file") as lecture:
            resumes = discover_grids(self.racine)

        # Découverte : le fichier n'est ni lu en entier ni haché.
        lecture.assert_not_called()
        self.assertEqual(len(resumes), 1)
        self.assertIsNone(resumes[0].sha256)
        self.assertIsNone(resumes[0].title)
        self.assertIn("volumineux", resumes[0].error or "")

    def test_erreur_de_stat_ne_fait_pas_echouer_la_liste(self) -> None:
        self.dossier.mkdir(exist_ok=True)
        (self.dossier / "grille.md").write_text(
            "# T\n\n## Case ?\n", encoding="utf-8"
        )

        with mock.patch(
            "transcription_bench.grilles.Path.stat", side_effect=OSError("disparu")
        ):
            resumes = discover_grids(self.racine)

        self.assertEqual(len(resumes), 1)
        self.assertEqual(resumes[0].name, "grille")
        self.assertIsNone(resumes[0].sha256)
        self.assertIn("illisible", resumes[0].error or "")


if __name__ == "__main__":
    unittest.main()
