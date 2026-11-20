"""Tests de la consultation des extractions (tâche 4.1, design D9).

Les extractions sont écrites par le vrai écrivain `ExtractionRecorder`, sans moteur
ni réseau ; les manipulations hostiles (liens sortants, JSON invalide, marqueurs
absents, valeurs non finies) sont appliquées ensuite aux fichiers réels. Toutes
les données sont synthétiques et sous un dossier temporaire.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import time
import unittest
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from unittest import mock

from transcription_bench.consignes_grilles import system_message
from transcription_bench.executions import ModelePropose
from transcription_bench.extraction_consultation import (
    ExtractionConsultation,
    group_key,
    sort_entries,
)
from transcription_bench.extractions import ExtractionGrid, ExtractionRequest, ExtractionSource
from transcription_bench.grilles import interpret_grid_copy
from transcription_bench.indicateurs_resultats import NON_MESURE
from transcription_bench.paths import ValeurRefusee
from transcription_bench.resultats_extraction import ExtractionRecorder
from transcription_bench.schema_grilles import grid_schema
from transcription_bench.consultation_resultats import (
    MARQUE_FACTICE,
    MARQUE_MESURES_SIMULEES,
    MARQUE_SYNTHETIQUE,
    ResultatIntrouvable,
    ResultatNonInterpretable,
)

GRILLE_A = """# Grille de test

## Motif ?

## Symptômes ?
Liste.

## Prescription ?
Liste.
### Médicament
### Posologie
"""

#: Grille B : même titre, une case de plus (schéma et empreinte différents).
GRILLE_B = GRILLE_A + "\n## Durée ?\n"

TEXTE_A = "Bonjour, je tousse depuis trois jours."
TEXTE_B = "Autre consultation, sans toux."

VALEUR_A = {
    "motif": "Toux",
    "symptomes": ["fièvre", ""],
    "prescription": [{"medicament": "Amoxicilline", "posologie": None}],
    "autres_informations": [{"intitule": "Allergie", "valeur": "non dite"}],
}
VALEUR_B = dict(VALEUR_A, duree=None)

MESURES_DEFAUT: dict[str, Any] = {
    "tokens_entree": 812,
    "tokens_sortie": 40,
    "delai_premier_token_s": 1.25,
    "duree_generation_s": 2.0,
    "duree_extraction_s": 3.0,
    "vitesse_generation_tps": 20.0,
    "vitesse_lecture_estimee_tps": 650.0,
    "temps_cpu_s": 6.0,
    "pic_memoire_octets": 2_000_000_000,
}
MACHINE: dict[str, Any] = {
    "os": "Linux",
    "version_os": "test",
    "architecture": "x86_64",
    "processeur": "processeur de test",
    "coeurs_physiques": 4,
    "coeurs_logiques": 8,
    "ram_totale_octets": 16_000_000_000,
}
PROGRAMME: dict[str, Any] = {"nom": "transcription-bench", "version": "test"}
ORIGINE = "20260228-120000-0badc0de"


@dataclass(frozen=True)
class Source:
    """Source synthétique d'une extraction, avec son résultat ou non."""

    nom: str = "consultation-a.wav"
    texte: str = TEXTE_A
    valeur: Any = field(default_factory=lambda: dict(VALEUR_A))
    conforme: bool = True
    mesures: Mapping[str, Any] = field(default_factory=dict)
    publier: bool = True
    origine: str = ORIGINE
    source_factice: bool = False


def sha(octets: bytes) -> str:
    return hashlib.sha256(octets).hexdigest()


class ExtractionConsultationBench(unittest.TestCase):
    """Dossier temporaire, extractions réelles et consultation en lecture seule."""

    def setUp(self) -> None:
        temporaire = tempfile.TemporaryDirectory()
        self.addCleanup(temporaire.cleanup)
        racine = Path(temporaire.name).resolve()
        self.donnees = racine / "data"
        self.donnees.mkdir()
        self.hors = racine / "hors"
        self.hors.mkdir()
        self.compteur = 0
        self.consultation = ExtractionConsultation(self.donnees)

    # -- outillage ---------------------------------------------------------

    def write_run(
        self,
        sources: list[Source],
        *,
        grille: str = GRILLE_A,
        factice: bool = False,
        version_consignes: int = 1,
        date: str | None = "2026-03-01T10:00:00+00:00",
        cree_le_fixe: bool = True,
    ) -> str:
        """Écrit une extraction réelle via le vrai écrivain ; renvoie son identifiant."""
        self.compteur += 1
        octets_grille = grille.encode("utf-8")
        objet_grille = interpret_grid_copy("grille-test", octets_grille)
        self.assertTrue(objet_grille.valid)
        message = system_message(objet_grille)
        demande = ExtractionRequest(
            modele=ModelePropose(
                moteur="factice" if factice else "llama-cpp",
                nom_moteur="moteur de test",
                cle="modele-test",
                identifiant="modele-test",
                id_resolu="modele-test",
                commit="0" * 40,
                famille="factice" if factice else "llm-gguf",
                libelle_famille="test",
                qualifiee=True,
                fichier_gguf=None,
                reglages=(),
                fenetre_fixe_secondes=None,
                synthetique=factice,
            ),
            grille=ExtractionGrid(
                nom="grille-test",
                sha256=sha(octets_grille),
                titre=objet_grille.title,
                copie=grille,
                schema=grid_schema(objet_grille),
                message_systeme=message.text,
                version_consignes=version_consignes,
                nombre_cases=len(objet_grille.fields),
            ),
            sources=tuple(
                ExtractionSource(
                    rang=rang,
                    identifiant=source.origine,
                    ordre=1,
                    nom=source.nom,
                    empreinte_audio=sha(source.nom.encode("utf-8")),
                    modele="transcription-test",
                    moteur="transcription-moteur",
                    factice=source.source_factice,
                    texte=source.texte,
                    empreinte_texte=sha(source.texte.encode("utf-8")),
                    caracteres=len(source.texte),
                )
                for rang, source in enumerate(sources, 1)
            ),
            threads=2,
            reglages=(),
        )
        moteur = {
            "identifiant": "factice" if factice else "llama-cpp",
            "nom": "moteur de test",
            "factice": factice,
        }
        self.compteur_court = f"{self.compteur:08x}"
        consignateur = ExtractionRecorder(
            self.donnees,
            demande,
            moteur,
            debut=time.perf_counter(),
            machine=MACHINE,
            programme=PROGRAMME,
            horloge=lambda: date,
            base="20260301-100000",
            court_id=self.compteur_court,
        )
        self.assertTrue(consignateur.ouvrir(), consignateur.erreur)
        self.assertTrue(
            consignateur.record_event(
                {
                    "type": "chargement",
                    "duree_s": 0.5,
                    "pic_memoire_octets": 1000,
                    "factice": factice,
                    "mesures_simulees": factice,
                    "meta_moteur": {
                        "threads_appliques": 2,
                        "mode_chargement_poids": "mmap",
                        "architecture": "llama",
                        "sha256_gabarit_embarque": "b" * 64,
                        "version_format": 1,
                        "decodage": "glouton",
                        "graine": "0",
                    },
                }
            )
        )
        for index, source in enumerate(sources):
            if source.publier:
                evenement = {
                    "type": "extraction",
                    "index": index,
                    "conforme": source.conforme,
                    "motif": None if source.conforme else "clé inconnue de la grille",
                    "valeur": source.valeur if source.conforme else None,
                    "sortie_brute": '{"motif": "Toux"}',
                    "fin": "arret",
                    "comptes_natifs": {"tokens_lecture": 812, "tokens_generation": 40},
                    "factice": factice,
                    "mesures_simulees": factice,
                    **MESURES_DEFAUT,
                    **dict(source.mesures),
                }
                self.assertTrue(consignateur.record_event(evenement))
        self.assertTrue(consignateur.clore(etat="terminee", erreur=None, code_sortie=0))
        consignateur.fermer()
        assert consignateur.identifiant is not None
        return consignateur.identifiant

    def run_dir(self, run_id: str) -> Path:
        return self.donnees / "extractions" / run_id

    def read_run(self, run_id: str) -> dict[str, Any]:
        return json.loads((self.run_dir(run_id) / "run.json").read_text(encoding="utf-8"))

    def source_dir(self, run_id: str, rang: int) -> Path:
        plan = next(p for p in self.read_run(run_id)["sources"] if p["rang"] == rang)
        return self.run_dir(run_id) / plan["dossier"]

    def rewrite_json(self, chemin: Path, mutation: Callable[[Any], None]) -> None:
        contenu = json.loads(chemin.read_text(encoding="utf-8"))
        mutation(contenu)
        chemin.write_text(json.dumps(contenu, ensure_ascii=False), encoding="utf-8")

    def link_outside(self, chemin: Path, contenu: str) -> None:
        """Remplace `chemin` par un lien symbolique vers un fichier hors du dossier."""
        cible = self.hors / f"cible-{chemin.name}"
        cible.write_text(contenu, encoding="utf-8")
        chemin.unlink()
        os.symlink(cible, chemin)

    def tree_snapshot(self) -> dict[str, bytes]:
        """Empreinte de tout l'arbre `data/` pour prouver l'absence d'écriture."""
        snapshot: dict[str, bytes] = {}
        for chemin in sorted(self.donnees.rglob("*")):
            if chemin.is_file():
                snapshot[str(chemin.relative_to(self.donnees))] = chemin.read_bytes()
        return snapshot


class CopyIntegrityTest(ExtractionConsultationBench):
    def test_comparison_rechecks_source_copy_and_original_group_hash(self) -> None:
        for alteration in ("missing", "changed", "changed_with_metadata"):
            with self.subTest(alteration=alteration):
                first = self.write_run([Source()])
                second = self.write_run([Source()])
                key = self.consultation.groups()[0].key
                read_run = self.consultation._read_run
                reads = 0
                source_dir = self.source_dir(first, 1)

                def read_and_alter(run_id: str):
                    nonlocal reads
                    if run_id == first:
                        reads += 1
                        # First read builds the group, second read serves shared text.
                        if reads == 2:
                            source_path = source_dir / "source.txt"
                            if alteration == "missing":
                                source_path.unlink()
                            else:
                                source_path.write_text(TEXTE_B, encoding="utf-8")
                            if alteration == "changed_with_metadata":
                                digest = sha(TEXTE_B.encode("utf-8"))
                                self.rewrite_json(
                                    self.run_dir(first) / "run.json",
                                    lambda value: value["sources"][0]["texte"].update(empreinte_sha256=digest),
                                )
                                self.rewrite_json(
                                    source_dir / "result.json",
                                    lambda value: value["texte"].update(empreinte_sha256=digest),
                                )
                    return read_run(run_id)

                with mock.patch.object(self.consultation, "_read_run", side_effect=read_and_alter):
                    comparison = self.consultation.compare(key, [f"{first}:1", f"{second}:1"])
                self.assertEqual(reads, 2)
                self.assertIsNone(comparison.source_text)

    def test_extracted_value_requires_matching_envelope(self) -> None:
        for field, invalid in (("schema", 99), ("schema", True),
                               ("type", "foreign"), ("rang", 2), ("rang", True)):
            with self.subTest(field=field, invalid=invalid):
                run_id = self.write_run([Source()])
                self.rewrite_json(
                    self.source_dir(run_id, 1) / "extraction.json",
                    lambda value: value.update({field: invalid}),
                )
                source = self.consultation.detail(run_id).sources[0]
                self.assertIsNone(source.rows)
                self.assertIsNone(source.entry.value)
                self.assertFalse(source.entry.groupable)

    def test_ram_sort_preserves_large_integer_without_float_overflow(self) -> None:
        run_id = self.write_run([Source(mesures={"pic_memoire_octets": 10 ** 400})])
        groups = self.consultation.groups("ram")
        self.assertEqual(groups[0].entries[0].run_id, run_id)
        self.assertEqual(groups[0].entries[0].indicators.peak_memory_bytes, 10 ** 400)
        self.assertIsNone(groups[0].entries[0].indicators.ram_ratio)

    def test_large_source_copy_remains_complete(self) -> None:
        text = "a" * (16 * 1024 * 1024 + 1)
        run_id = self.write_run([Source(texte=text)])
        source = self.consultation.detail(run_id).sources[0]
        self.assertEqual(source.source_text, text)
        self.assertTrue(source.source_copy_ok)
        self.assertTrue(source.entry.groupable)


class RegroupementTest(ExtractionConsultationBench):
    def test_groupe_par_triplet_avec_empreintes_des_copies(self) -> None:
        run = self.write_run([Source()])
        groupes = self.consultation.groups()
        self.assertEqual(len(groupes), 1)
        dossier = self.run_dir(run)
        attendu = group_key(
            sha(TEXTE_A.encode("utf-8")),
            sha((dossier / "grille.md").read_bytes()),
            sha((dossier / "schema.json").read_bytes()),
        )
        self.assertEqual(groupes[0].key, attendu)
        self.assertEqual(groupes[0].entries[0].selection, f"{run}:1")

    def test_meme_source_grilles_differentes_donnent_deux_groupes(self) -> None:
        self.write_run([Source(valeur=VALEUR_A)], grille=GRILLE_A)
        self.write_run([Source(valeur=VALEUR_B)], grille=GRILLE_B)
        groupes = self.consultation.groups()
        self.assertEqual(len(groupes), 2)
        self.assertNotEqual(groupes[0].key, groupes[1].key)
        self.assertEqual({len(g.entries) for g in groupes}, {1})

    def test_versions_de_consignes_differentes_sont_signalees_dans_le_groupe(self) -> None:
        self.write_run([Source()], version_consignes=1)
        self.write_run([Source()], version_consignes=2)
        groupes = self.consultation.groups()
        self.assertEqual(len(groupes), 1)
        self.assertEqual(groupes[0].consignes_versions, (1, 2))
        self.assertTrue(groupes[0].consignes_diverge)

    def test_groupes_ordonnes_par_extraction_la_plus_recente(self) -> None:
        self.write_run([Source(texte=TEXTE_A)], date="2026-03-01T10:00:00+00:00")
        self.write_run([Source(texte=TEXTE_B)], date="2026-03-05T10:00:00+00:00")
        groupes = self.consultation.groups()
        self.assertEqual(
            [g.text_sha256 for g in groupes],
            [sha(TEXTE_B.encode("utf-8")), sha(TEXTE_A.encode("utf-8"))],
        )

    def test_factices_separees_et_non_comparables_aux_reelles(self) -> None:
        reelle = self.write_run([Source()])
        factice = self.write_run([Source()], factice=True)
        groupes = self.consultation.groups()
        self.assertEqual(len(groupes), 1)
        groupe = groupes[0]
        self.assertEqual([e.run_id for e in groupe.real_entries], [reelle])
        self.assertEqual([e.run_id for e in groupe.simulated_entries], [factice])
        self.assertIn(MARQUE_FACTICE, groupe.simulated_entries[0].marks)
        self.assertIn(MARQUE_SYNTHETIQUE, groupe.simulated_entries[0].marks)
        self.assertEqual([e.run_id for e in groupe.entries], [reelle, factice])


class TriTest(ExtractionConsultationBench):
    def test_tri_temps_ram_cpu_absents_en_dernier(self) -> None:
        rapide = self.write_run([Source(mesures={"duree_extraction_s": 1.0, "pic_memoire_octets": 3_000_000_000, "temps_cpu_s": 2.0})])
        lente = self.write_run([Source(mesures={"duree_extraction_s": 9.0, "pic_memoire_octets": 1_000_000_000, "temps_cpu_s": 40.0})])
        absente = self.write_run([Source(mesures={"duree_extraction_s": NON_MESURE, "pic_memoire_octets": None, "temps_cpu_s": True})])
        groupe = self.consultation.groups("temps")[0]
        self.assertEqual([e.run_id for e in groupe.entries], [rapide, lente, absente])
        self.assertEqual([e.run_id for e in self.consultation.groups("ram")[0].entries], [lente, rapide, absente])
        self.assertEqual([e.run_id for e in self.consultation.groups("cpu")[0].entries], [rapide, lente, absente])

    def test_tri_recent_par_date_inconnue_en_fin(self) -> None:
        ancienne = self.write_run([Source()], date="2026-03-01T10:00:00+00:00")
        recente = self.write_run([Source()], date="2026-03-03T10:00:00+00:00")
        sans_date = self.write_run([Source()], date=None)
        groupe = self.consultation.groups("recent")[0]
        self.assertEqual([e.run_id for e in groupe.entries], [recente, ancienne, sans_date])

    def test_tri_inconnu_refuse(self) -> None:
        self.write_run([Source()])
        with self.assertRaises(ValeurRefusee):
            self.consultation.groups("score")
        with self.assertRaises(ValeurRefusee):
            sort_entries([], "score")

    def test_ratios_sur_le_materiel_consigne(self) -> None:
        self.write_run([Source(mesures={"duree_extraction_s": 2.0, "temps_cpu_s": 8.0, "pic_memoire_octets": 4_000_000_000})])
        indicateurs = self.consultation.groups()[0].entries[0].indicators
        self.assertAlmostEqual(indicateurs.ram_ratio or 0.0, 25.0)
        # 100 × 8 / (2 × 8 processeurs logiques) = 50 %
        self.assertAlmostEqual(indicateurs.cpu_occupancy or 0.0, 50.0)


class ValeursDouteusesTest(ExtractionConsultationBench):
    def test_valeurs_non_finies_booleennes_absentes_ne_deviennent_jamais_zero(self) -> None:
        run = self.write_run(
            [
                Source(
                    mesures={
                        "duree_extraction_s": float("nan"),
                        "temps_cpu_s": True,
                        "pic_memoire_octets": None,
                        "tokens_sortie": -3,
                        "vitesse_generation_tps": float("inf"),
                    }
                )
            ]
        )
        indicateurs = self.consultation.groups("temps")[0].entries[0].indicators
        self.assertIsNone(indicateurs.duration_extraction_s)
        self.assertIsNone(indicateurs.cpu_time_s)
        self.assertIsNone(indicateurs.peak_memory_bytes)
        self.assertIsNone(indicateurs.tokens_out)
        self.assertIsNone(indicateurs.generation_speed_tps)
        self.assertIsNone(indicateurs.cpu_occupancy)
        self.assertEqual(self.read_run(run)["sources"][0]["etat"], "conforme")

    def test_ram_totale_absente_donne_ratio_absent(self) -> None:
        self.write_run([Source()])
        dossier_run = self.run_dir(self.consultation.groups()[0].entries[0].run_id)
        self.rewrite_json(dossier_run / "run.json", lambda c: c["machine"].pop("ram_totale_octets"))
        indicateurs = self.consultation.groups()[0].entries[0].indicators
        self.assertIsNone(indicateurs.ram_total_bytes)
        self.assertIsNone(indicateurs.ram_ratio)
        self.assertIsNotNone(indicateurs.peak_memory_bytes)


class CheminsHostilesTest(ExtractionConsultationBench):
    def test_identifiants_hostiles_refuses_sans_lecture(self) -> None:
        self.write_run([Source()])
        for hostile in ("../extractions", "/etc", "..", "20260101-000000-zzzzzzzz", ""):
            with self.subTest(hostile=hostile):
                with self.assertRaises(ValeurRefusee):
                    self.consultation.detail(hostile)

    def test_dossier_d_extraction_lien_sortant_ignore_puis_refuse(self) -> None:
        run = self.write_run([Source()])
        dossier = self.run_dir(run)
        cible = self.hors / "extraction-externe"
        cible.mkdir()
        (cible / "run.json").write_text(json.dumps(self.read_run(run)), encoding="utf-8")
        renomme = self.donnees / "extractions" / "20260301-100000-ffffffff"
        os.symlink(cible, renomme)
        self.assertNotIn("20260301-100000-ffffffff", [r.run_id for r in self.consultation.list_runs()])
        with self.assertRaises((ValeurRefusee, ResultatIntrouvable)):
            self.consultation.detail("20260301-100000-ffffffff")
        self.assertTrue(dossier.is_dir())

    def test_run_json_lien_sortant_non_interprete(self) -> None:
        run = self.write_run([Source()])
        self.link_outside(self.run_dir(run) / "run.json", json.dumps(self.read_run(run)))
        resumes = {r.run_id: r for r in self.consultation.list_runs()}
        self.assertFalse(resumes[run].usable)
        with self.assertRaises(ResultatNonInterpretable):
            self.consultation.detail(run)
        self.assertEqual(self.consultation.groups(), ())

    def test_grille_copiee_lien_sortant_jamais_lue(self) -> None:
        run = self.write_run([Source()])
        chemin = self.run_dir(run) / "grille.md"
        self.link_outside(chemin, chemin.read_text(encoding="utf-8"))
        self.assertEqual(self.consultation.groups(), ())
        detail = self.consultation.detail(run)
        self.assertIsNone(detail.grid_copy)
        self.assertFalse(detail.grid_copy_ok)
        self.assertIsNone(detail.sources[0].rows)
        entry = detail.sources[0].entry
        assert entry is not None
        self.assertFalse(entry.groupable)

    def test_schema_copie_lien_sortant_jamais_lu(self) -> None:
        run = self.write_run([Source()])
        chemin = self.run_dir(run) / "schema.json"
        self.link_outside(chemin, GRILLE_A)
        self.assertEqual(self.consultation.groups(), ())
        entry = self.consultation.detail(run).sources[0].entry
        assert entry is not None
        self.assertIn("schéma", entry.copy_issue or "")

    def test_source_txt_lien_sortant_exclut_du_groupe(self) -> None:
        run = self.write_run([Source()])
        chemin = self.source_dir(run, 1) / "source.txt"
        self.link_outside(chemin, TEXTE_A)
        self.assertEqual(self.consultation.groups(), ())
        detail = self.consultation.detail(run).sources[0]
        self.assertIsNone(detail.source_text)
        self.assertFalse(detail.source_copy_ok)

    def test_sortie_brute_lien_sortant_non_lue(self) -> None:
        run = self.write_run([Source(conforme=False, valeur=None)])
        chemin = self.source_dir(run, 1) / "sortie_brute.txt"
        self.link_outside(chemin, '{"motif": "Toux"}')
        detail = self.consultation.detail(run).sources[0]
        self.assertEqual(detail.state, "non_conforme")
        self.assertIsNone(detail.raw_output)
        self.assertIsNone(detail.rows)

    def test_extraction_json_lien_sortant_sans_valeur_inventee(self) -> None:
        run = self.write_run([Source()])
        chemin = self.source_dir(run, 1) / "extraction.json"
        self.link_outside(chemin, json.dumps({"schema": 1, "valeur": VALEUR_A}))
        self.assertEqual(self.consultation.groups(), ())
        entry = self.consultation.detail(run).sources[0].entry
        assert entry is not None
        self.assertIsNone(entry.value)
        self.assertIn("incohérente", entry.copy_issue or "")

    def test_result_json_lien_sortant_source_non_traitee(self) -> None:
        run = self.write_run([Source()])
        chemin = self.source_dir(run, 1) / "result.json"
        self.link_outside(chemin, "{}")
        detail = self.consultation.detail(run).sources[0]
        self.assertEqual(detail.state, "non_traitee")
        self.assertIsNone(detail.entry)

    def test_dossier_de_source_lien_sortant_refuse(self) -> None:
        run = self.write_run([Source()])
        dossier_source = self.source_dir(run, 1)
        cible = self.hors / "dossier-source"
        cible.mkdir()
        (cible / "result.json").write_text("{}", encoding="utf-8")
        dossier_source.rename(self.donnees / "extractions" / run / "deplace")
        os.symlink(cible, dossier_source)
        detail = self.consultation.detail(run).sources[0]
        self.assertEqual(detail.state, "non_traitee")
        self.assertIn("refusé", detail.reason or "")


class MarqueurPublicationTest(ExtractionConsultationBench):
    def test_sans_result_json_la_source_est_non_traitee_meme_avec_autres_fichiers(self) -> None:
        run = self.write_run([Source(publier=False)])
        dossier_source = self.source_dir(run, 1)
        (dossier_source / "extraction.json").write_text(json.dumps({"valeur": VALEUR_A}), encoding="utf-8")
        (dossier_source / "sortie_brute.txt").write_text('{"motif": "Toux"}', encoding="utf-8")
        detail = self.consultation.detail(run).sources[0]
        self.assertEqual(detail.state, "non_traitee")
        self.assertIsNone(detail.entry)
        self.assertIsNone(detail.rows)
        self.assertIsNone(detail.raw_output)
        self.assertEqual(self.consultation.groups(), ())

    def test_texte_et_provenance_lisibles_pour_une_source_non_traitee(self) -> None:
        run = self.write_run([Source(publier=False)])
        detail = self.consultation.detail(run).sources[0]
        self.assertEqual(detail.source_text, TEXTE_A)
        self.assertTrue(detail.source_copy_ok)
        self.assertEqual(detail.origin["execution"], ORIGINE)
        self.assertFalse(detail.origin_present)

    def test_result_json_d_une_autre_extraction_refuse(self) -> None:
        run = self.write_run([Source()])
        autre = self.write_run([Source()])
        chemin = self.source_dir(run, 1) / "result.json"
        copie = (self.source_dir(autre, 1) / "result.json").read_text(encoding="utf-8")
        chemin.write_text(copie, encoding="utf-8")
        detail = self.consultation.detail(run).sources[0]
        self.assertEqual(detail.state, "non_traitee")
        self.assertIn("non interprétable", detail.reason or "")
        self.assertEqual(len(self.consultation.groups()), 1)

    def test_result_json_rang_booleen_refuse(self) -> None:
        run = self.write_run([Source()])
        self.rewrite_json(self.source_dir(run, 1) / "result.json", lambda c: c.update(rang=True))
        self.assertEqual(self.consultation.detail(run).sources[0].state, "non_traitee")

    def test_result_json_dossier_ou_texte_incoherent_refuse(self) -> None:
        run = self.write_run([Source()])
        self.rewrite_json(self.source_dir(run, 1) / "result.json", lambda c: c["texte"].update(empreinte_sha256="0" * 64))
        self.assertEqual(self.consultation.detail(run).sources[0].state, "non_traitee")

    def test_facteur_factice_du_resultat_seul_classe_la_source_a_part(self) -> None:
        run = self.write_run([Source()])
        self.rewrite_json(self.source_dir(run, 1) / "result.json", lambda c: c.update(mesures_simulees=True))
        groupe = self.consultation.groups()[0]
        self.assertEqual(groupe.simulated_entries[0].run_id, run)
        self.assertIn(MARQUE_MESURES_SIMULEES, groupe.simulated_entries[0].marks)
        self.assertEqual(groupe.real_entries, ())


class FichiersInvalidesTest(ExtractionConsultationBench):
    def test_schema_inconnu_ou_json_invalide_refuse_sans_crash(self) -> None:
        schema_inconnu = self.write_run([Source()])
        self.rewrite_json(self.run_dir(schema_inconnu) / "run.json", lambda c: c.update(schema=2))
        invalide = self.write_run([Source(texte=TEXTE_B)])
        (self.run_dir(invalide) / "run.json").write_text("{ pas du json", encoding="utf-8")
        resumes = {r.run_id: r for r in self.consultation.list_runs()}
        self.assertFalse(resumes[schema_inconnu].usable)
        self.assertFalse(resumes[invalide].usable)
        for run in (schema_inconnu, invalide):
            with self.subTest(run=run):
                with self.assertRaises(ResultatNonInterpretable):
                    self.consultation.detail(run)
        self.assertEqual(self.consultation.groups(), ())

    def test_types_inattendus_dans_run_json_refuses(self) -> None:
        cas: list[Callable[[Any], None]] = [
            lambda c: c.update(etat={"x": 1}),
            lambda c: c.update(etat=["completed"]),
            lambda c: c.update(sources="pas une liste"),
            lambda c: c["sources"][0].update(etat=["non_traitee"]),
            lambda c: c["sources"][0].update(rang=True),
            lambda c: c.update(grille=None),
        ]
        for index, mutation in enumerate(cas):
            with self.subTest(cas=index):
                run = self.write_run([Source()])
                self.rewrite_json(self.run_dir(run) / "run.json", mutation)
                with self.assertRaises(ResultatNonInterpretable):
                    self.consultation.detail(run)
                self.assertFalse(
                    {r.run_id: r for r in self.consultation.list_runs()}[run].usable
                )

    def test_rangs_dupliques_refuses(self) -> None:
        run = self.write_run([Source(), Source(nom="consultation-b.wav", texte=TEXTE_B)])
        self.rewrite_json(self.run_dir(run) / "run.json", lambda c: c["sources"][1].update(rang=1))
        with self.assertRaises(ResultatNonInterpretable):
            self.consultation.detail(run)

    def test_result_json_invalide_ou_schema_inconnu_non_traite(self) -> None:
        invalide = self.write_run([Source()])
        (self.source_dir(invalide, 1) / "result.json").write_text("{ invalide", encoding="utf-8")
        inconnu = self.write_run([Source(texte=TEXTE_B)])
        self.rewrite_json(self.source_dir(inconnu, 1) / "result.json", lambda c: c.update(schema=9))
        self.assertEqual(self.consultation.detail(invalide).sources[0].state, "non_traitee")
        self.assertEqual(self.consultation.detail(inconnu).sources[0].state, "non_traitee")

    def test_schema_copie_invalide_ou_valeur_incoherente_exclue(self) -> None:
        schema_bris = self.write_run([Source()])
        (self.run_dir(schema_bris) / "schema.json").write_text("{ pas du json", encoding="utf-8")
        valeur_mauvaise = self.write_run([Source(texte=TEXTE_B, valeur=dict(VALEUR_A, symptomes="fièvre"))])
        self.assertEqual(self.consultation.groups(), ())
        entry_schema = self.consultation.detail(schema_bris).sources[0].entry
        entry_valeur = self.consultation.detail(valeur_mauvaise).sources[0].entry
        assert entry_schema is not None and entry_valeur is not None
        self.assertIsNone(entry_schema.value)
        self.assertIsNone(self.consultation.detail(valeur_mauvaise).sources[0].rows)
        self.assertIn("schéma", entry_schema.copy_issue or "")
        self.assertIn("incohérente", entry_valeur.copy_issue or "")

    def test_grille_copiee_modifiee_pas_de_remplissage_trompeur(self) -> None:
        run = self.write_run([Source()])
        chemin = self.run_dir(run) / "grille.md"
        chemin.write_text(GRILLE_A + "\n## Ajout ?\n", encoding="utf-8")
        detail = self.consultation.detail(run)
        self.assertFalse(detail.grid_copy_ok)
        self.assertIsNone(detail.sources[0].rows)
        self.assertEqual(self.consultation.groups(), ())


class GrilleRemplieTest(ExtractionConsultationBench):
    def test_grille_remplie_dans_l_ordre_avec_null_vide_et_listes(self) -> None:
        run = self.write_run([Source()])
        rows = self.consultation.detail(run).sources[0].rows
        assert rows is not None
        affichage = [(r.label, r.depth, r.display, r.absent) for r in rows]
        self.assertEqual(
            affichage,
            [
                ("Motif ?", 0, "Toux", False),
                ("Symptômes ? (1)", 0, "fièvre", False),
                ("Symptômes ? (2)", 0, "(vide)", False),
                ("Prescription ? (1)", 0, "", False),
                ("Médicament", 1, "Amoxicilline", False),
                ("Posologie", 1, "non mentionné", True),
            ],
        )

    def test_valeur_null_distincte_de_chaine_vide(self) -> None:
        run = self.write_run([Source(valeur=dict(VALEUR_A, motif=None))])
        rows = self.consultation.detail(run).sources[0].rows
        assert rows is not None
        self.assertEqual((rows[0].display, rows[0].absent), ("non mentionné", True))

    def test_autres_informations_et_message_systeme_disponibles(self) -> None:
        run = self.write_run([Source()])
        detail = self.consultation.detail(run)
        self.assertIsNotNone(detail.system_message)
        self.assertEqual(detail.consignes_version, 1)
        self.assertEqual(self.consultation.groups()[0].entries[0].other_info, (("Allergie", "non dite"),))


class ComparaisonTest(ExtractionConsultationBench):
    def setUp(self) -> None:
        super().setUp()
        self.a = self.write_run([Source(mesures={"duree_extraction_s": 2.0})])
        self.b = self.write_run([Source(valeur=dict(VALEUR_A, motif="Fièvre"))])
        self.c = self.write_run([Source(valeur=dict(VALEUR_A, motif=None))])
        self.cle = self.consultation.groups()[0].key

    def test_comparaison_dans_l_ordre_recu_avec_cases(self) -> None:
        comparaison = self.consultation.compare(self.cle, [f"{self.b}:1", f"{self.a}:1"])
        self.assertEqual([e.run_id for e in comparaison.entries], [self.b, self.a])
        motif = comparaison.cases[0]
        self.assertEqual(motif.label, "Motif ?")
        self.assertEqual(motif.values, ("Fièvre", "Toux"))
        self.assertTrue(motif.differs)
        self.assertIn("Médicament : Amoxicilline", comparaison.cases[2].values[0] or "")

    def test_null_affiche_explicitement_dans_la_comparaison(self) -> None:
        comparaison = self.consultation.compare(self.cle, [f"{self.a}:1", f"{self.c}:1"])
        self.assertEqual(comparaison.cases[0].values, ("Toux", "non mentionné"))

    def test_bornes_de_selection(self) -> None:
        self.assertEqual(len(self.consultation.compare(self.cle, [f"{self.a}:1", f"{self.a}:1", f"{self.b}:1"]).entries), 2)
        with self.assertRaises(ValeurRefusee):
            self.consultation.compare(self.cle, [f"{self.a}:1"])
        with self.assertRaises(ValeurRefusee):
            self.consultation.compare(self.cle, [f"{self.a}:1"] * 7)

    def test_selections_mal_formees_ou_hors_groupe_refusees(self) -> None:
        for mauvaise in ("../x:1", f"{self.a}:0", f"{self.a}", f"{self.a}:1:2"):
            with self.subTest(selection=mauvaise):
                with self.assertRaises(ValeurRefusee):
                    self.consultation.compare(self.cle, [f"{self.a}:1", mauvaise])
        autre_groupe = self.write_run([Source(texte=TEXTE_B)])
        with self.assertRaises(ValeurRefusee):
            self.consultation.compare(self.cle, [f"{self.a}:1", f"{autre_groupe}:1"])
        with self.assertRaises(ResultatIntrouvable):
            self.consultation.compare(self.cle, [f"{self.a}:1", "20260101-000000-aaaaaaaa:1"])
        with self.assertRaises(ValeurRefusee):
            self.consultation.compare("0" * 10, [f"{self.a}:1", f"{self.b}:1"])

    def test_factices_et_reelles_non_melangees(self) -> None:
        factice = self.write_run([Source()], factice=True)
        with self.assertRaises(ValeurRefusee):
            self.consultation.compare(self.cle, [f"{self.a}:1", f"{factice}:1"])
        self.assertEqual(len(self.consultation.compare(self.cle, [f"{self.a}:1", f"{self.b}:1"]).entries), 2)

    def test_extraction_non_conforme_dans_la_selection(self) -> None:
        non_conforme = self.write_run([Source(conforme=False, valeur=None)])
        comparaison = self.consultation.compare(self.cle, [f"{self.a}:1", f"{non_conforme}:1"])
        self.assertIsNone(comparaison.cases[0].values[1])
        self.assertIsNone(comparaison.other_info[1])


class MetadonneesDetailTest(ExtractionConsultationBench):
    def test_metadonnees_completes_et_reglages_effectifs_accessibles(self) -> None:
        run = self.write_run([Source()])
        detail = self.consultation.detail(run)
        self.assertEqual(detail.threads_requested, 2)
        self.assertEqual(detail.threads_applied, 2)
        self.assertEqual(detail.weight_loading_mode, "mmap")
        self.assertIn(("Architecture GGUF", "llama"), detail.model)
        self.assertIn(("SHA-256 du gabarit embarqué", "b" * 64), detail.model)
        self.assertEqual(detail.effective_settings["decodage"], "glouton")
        self.assertEqual(detail.effective_settings["graine"], "0")
        self.assertIn(("Programme", "transcription-bench"), detail.program)
        self.assertEqual(detail.raw_metadata["effectifs"]["mode_chargement_poids"], "mmap")
        self.assertEqual(detail.raw_metadata["machine"]["ram_totale_octets"], 16_000_000_000)

    def test_source_brute_et_comptes_natifs_accessibles_et_serialisables(self) -> None:
        run = self.write_run([Source()])
        source = self.consultation.detail(run).sources[0]
        assert source.raw_result is not None
        self.assertEqual(source.raw_result["mesures"]["comptes_natifs"], {"tokens_lecture": 812, "tokens_generation": 40})
        self.assertEqual(source.raw_result["sortie_brute"], "sortie_brute.txt")
        self.assertEqual(source.raw_output, '{"motif": "Toux"}')
        json.dumps(source.raw_result)
        json.dumps(self.consultation.detail(run).raw_metadata)

    def test_source_non_publiee_sans_resultat_brut(self) -> None:
        run = self.write_run([Source(publier=False)])
        source = self.consultation.detail(run).sources[0]
        self.assertIsNone(source.raw_result)
        self.assertIsNone(source.raw_output)


class LectureSeuleTest(ExtractionConsultationBench):
    def test_aucune_ecriture_dans_data(self) -> None:
        self.write_run([Source(), Source(nom="consultation-b.wav", texte=TEXTE_B, publier=False)])
        self.write_run([Source()], version_consignes=2)
        avant = self.tree_snapshot()
        groupes = self.consultation.groups("temps")
        self.consultation.list_runs()
        self.consultation.detail(groupes[0].entries[0].run_id)
        self.consultation.compare(groupes[0].key, [f"{e.run_id}:1" for e in groupes[0].entries])
        self.assertEqual(self.tree_snapshot(), avant)

    def test_lecture_apres_disparition_de_la_transcription_source(self) -> None:
        run = self.write_run([Source()])
        dossier_origine = self.donnees / "results" / ORIGINE
        dossier_origine.mkdir(parents=True)
        (dossier_origine / "run.json").write_text("{}", encoding="utf-8")
        self.assertTrue(self.consultation.detail(run).sources[0].origin_present)
        for fichier in dossier_origine.iterdir():
            fichier.unlink()
        dossier_origine.rmdir()
        self.assertFalse(self.consultation.detail(run).sources[0].origin_present)
        self.assertEqual(len(self.consultation.groups()), 1)
        self.assertEqual(self.consultation.detail(run).sources[0].source_text, TEXTE_A)

    def test_donnees_sans_dossier_extractions(self) -> None:
        self.assertEqual(self.consultation.list_runs(), ())
        self.assertEqual(self.consultation.groups(), ())
        with self.assertRaises(ResultatIntrouvable):
            self.consultation.detail("20260101-000000-aaaaaaaa")


if __name__ == "__main__":
    unittest.main()
