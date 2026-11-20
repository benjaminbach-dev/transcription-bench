"""Tests du runner et du protocole d'événements, sans moteur réel.

Le runner est exécuté dans ce processus avec un registre de test dont la
déclaration est qualifiée et pointe vers `tests/adaptateur_runner_de_test.py`.
Les audios sont des signaux synthétiques bruts, créés localement. Aucun moteur,
aucun poids, aucun accès réseau : les validations PC restent dues.
"""

from __future__ import annotations

import dataclasses
import io
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import numpy as np
import psutil

from engines.declarations import (
    TASK_EXTRACTION,
    DeclarationAdaptateur,
    Famille,
    declarations_fournies,
)
from engines.hors_ligne import environnement_moteur
from engines.mesures_systeme import (
    MOMENT_AUDIO,
    MOMENT_CHARGEMENT,
    PROVENANCE_REELLE,
    PROVENANCE_SIMULEE,
    SIMULATION_CPU_POURCENTAGE,
    SIMULATION_INTERVALLE_CPU_S,
    SIMULATION_MEMOIRE_DISPONIBLE_OCTETS,
    SIMULATION_RELEVE_LE,
    AmorcageCpu,
    ReleveurSysteme,
    valider_observation_systeme,
)
from engines.protocole import (
    CHAMPS_REQUIS,
    MARQUEUR_EVENEMENT,
    PREFIXE_EVENEMENT,
    TYPE_AUDIO,
    TYPE_AUDIO_ERREUR,
    TYPE_CHARGEMENT,
    TYPE_EXTRACTION,
    TYPE_EXTRACTION_ERREUR,
    TYPE_FIN,
    TYPES_EVENEMENTS,
    analyser_ligne,
    emettre,
    formater_ligne,
)
from engines.registre import RegistreMoteurs, creer_registre_fourni
from engines.runner import (
    DUREE_CHARGEMENT_SIMULEE_S,
    FORMAT_AUDIO,
    PIC_MEMOIRE_SIMULE_OCTETS,
    ErreurAudio,
    ErreurJob,
    ErreurMoteur,
    _pic_memoire_unix,
    _pic_memoire_windows,
    _valider_resultat,
    charger_job,
    executer,
    pic_memoire,
)
from engines.runner_extraction import (
    DUREE_EXTRACTION_SIMULEE_S,
    MOTIF_LIMITE,
    charger_job_extraction,
)
from engines.runner_extraction import executer as executer_extraction
from engines.runner_extraction import main as main_extraction
from tests import adaptateur_extraction_de_test as adaptateur_extraction
from tests import adaptateur_runner_de_test as adaptateur
from transcription_bench.consignes_grilles import (
    SOURCE_END_MARKER,
    system_message,
    user_message,
)
from transcription_bench.grilles import Field, Grid, read_grid
from transcription_bench.paths import RACINE_PROJET
from transcription_bench.schema_grilles import grid_schema

MODULE_ADAPTATEUR = "tests.adaptateur_runner_de_test"
MOTEUR_DE_TEST = "moteur-de-test"
FAMILLE_DE_TEST = "factice"

CODE_SANS_MODULE_SERVEUR = """
import sys

import engines.runner

interdits = ("flask", "waitress", "werkzeug", "jinja2", "transcription_bench")
charges = sorted(module for module in interdits if module in sys.modules)
print("|".join(charges) if charges else "ok")
"""

# Sonde synthétique : un vrai processus enfant exécute `runner.main` avec un
# registre de test, sans moteur réel. Elle n'imprime que de petites valeurs
# factices (HF_HUB_OFFLINE, options de modèle), jamais l'environnement complet.
CODE_SONDE_HORS_LIGNE = """
import json
import os
import sys

import engines.runner as runner
from engines.declarations import DeclarationAdaptateur, Famille
from engines.registre import RegistreMoteurs
from tests import adaptateur_runner_de_test as adaptateur

hf_initial = os.environ.get("HF_HUB_OFFLINE")
# Simule un environnement hérité hostile : le runner doit forcer le mode hors
# ligne avant d'importer puis de charger l'adaptateur de test.
os.environ["HF_HUB_OFFLINE"] = "0"

registre = RegistreMoteurs()
registre.enregistrer(DeclarationAdaptateur(
    identifiant="moteur-de-test",
    nom="Moteur de test",
    fichier_requirements=None,
    regle_compatibilite="aucune",
    familles=(Famille("factice", "Famille de test", qualifiee=True),),
    module_adaptateur="tests.adaptateur_runner_de_test",
))
adaptateur.reinitialiser()
runner.creer_registre_fourni = lambda: registre
code = runner.main([sys.argv[1]])
print("##SONDE## " + json.dumps({
    "code": code,
    "hf_initial": hf_initial,
    "consigne": adaptateur.derniere_consigne,
    "hf_apres": os.environ.get("HF_HUB_OFFLINE"),
}))
raise SystemExit(code)
"""


def registre_non_qualifie(identifiant: str) -> RegistreMoteurs:
    """Registre d'un seul moteur fourni, copié avec ses familles non qualifiées.

    Les adaptateurs réels sont qualifiés après validation Linux ; ce registre
    conserve l'éprouvette du refus d'une famille non qualifiée.
    """
    registre = RegistreMoteurs()
    for declaration in declarations_fournies():
        if declaration.identifiant != identifiant:
            continue
        registre.enregistrer(
            dataclasses.replace(
                declaration,
                familles=tuple(
                    dataclasses.replace(famille, qualifiee=False, duree_native=None)
                    for famille in declaration.familles
                ),
            )
        )
    return registre


def registre_de_test() -> RegistreMoteurs:
    registre = RegistreMoteurs()
    registre.enregistrer(
        DeclarationAdaptateur(
            identifiant=MOTEUR_DE_TEST,
            nom="Moteur de test",
            fichier_requirements=None,
            regle_compatibilite="aucune",
            familles=(
                Famille(FAMILLE_DE_TEST, "Famille de test", qualifiee=True),
            ),
            module_adaptateur=MODULE_ADAPTATEUR,
        )
    )
    return registre


def ecrire_signal(
    dossier: Path, nom: str, secondes: float, valeur: float
) -> str:
    """Écrit un signal brut float32 16 kHz mono et renvoie son chemin relatif."""
    echantillons = round(secondes * 16000)
    np.full(echantillons, valeur, dtype="<f4").tofile(dossier / nom)
    return nom


def ecrire_job(
    dossier: Path,
    audios: list[tuple[str, str]],
    *,
    moteur: str = MOTEUR_DE_TEST,
    famille: str = FAMILLE_DE_TEST,
    threads_demandes: int = 4,
    reglages: dict[str, object] | None = None,
    modele: dict[str, object] | None = None,
) -> Path:
    contenu = {
        "version": 1,
        "moteur": moteur,
        "famille": famille,
        "modele": modele
        if modele is not None
        else {
            "identifiant": "test/modele",
            "revision": "abc",
            "chemin": "modele",
        },
        "threads_demandes": threads_demandes,
        "reglages": {} if reglages is None else reglages,
        "format_audio": FORMAT_AUDIO,
        "audios": [
            {"nom": nom, "chemin": chemin} for nom, chemin in audios
        ],
    }
    chemin_job = dossier / "job.json"
    chemin_job.write_text(json.dumps(contenu), encoding="utf-8")
    return chemin_job


def executer_et_lire(
    chemin_job: Path, registre: RegistreMoteurs | None
) -> tuple[list[str], list[dict[str, object]]]:
    """Exécute un job en capturant stdout, comme le ferait le serveur."""
    sortie = io.StringIO()
    with redirect_stdout(sortie):
        executer(charger_job(chemin_job), registre)
    lignes = sortie.getvalue().splitlines()
    evenements = [
        evenement
        for evenement in (analyser_ligne(ligne) for ligne in lignes)
        if evenement is not None
    ]
    return lignes, evenements


class ProtocoleTest(unittest.TestCase):
    def test_evenements_prevus_analysables(self) -> None:
        evenements = [
            {
                "type": TYPE_CHARGEMENT,
                "duree_s": 1.5,
                "pic_memoire_octets": None,
                "factice": False,
                "mesures_simulees": False,
            },
            {
                "type": TYPE_AUDIO,
                "index": 0,
                "nom": "a.wav",
                "texte": "bonjour",
                "segments": [],
                "duree_audio_s": 10.0,
                "duree_transcription_s": 2.0,
                "temps_cpu_s": None,
                "rtf": 0.2,
                "fenetre_s": 30.0,
                "decoupage": "fenetres-fixes",
                "nb_fenetres": 1,
                "pic_memoire_octets": 1024,
                "reglages_effectifs": {},
                "timings_natifs": [
                    {
                        "unite": "ms",
                        "load_ms": 1.0,
                        "mel_ms": 2.0,
                        "encode_ms": 3.0,
                        "decode_ms": 4.0,
                    }
                ],
                "langue_imposee": "fr",
                "threads_demandes": 4,
                "threads_appliques": None,
                "factice": False,
                "mesures_simulees": False,
            },
            {
                "type": TYPE_AUDIO_ERREUR,
                "index": 1,
                "nom": "b.wav",
                "erreur": "échec",
                "factice": False,
                "mesures_simulees": False,
            },
            {
                "type": TYPE_FIN,
                "duree_chargement_s": 1.5,
                "pic_memoire_octets": 2048,
                "audios_ok": 1,
                "audios_erreur": 1,
                "factice": False,
                "mesures_simulees": False,
            },
        ]
        for evenement in evenements:
            with self.subTest(type_evenement=evenement["type"]):
                self.assertEqual(
                    analyser_ligne(formater_ligne(evenement)), evenement
                )

    def test_provenance_obligatoire_dans_chaque_evenement(self) -> None:
        evenement = {
            "type": TYPE_AUDIO_ERREUR,
            "index": 0,
            "nom": "a",
            "erreur": "x",
            "factice": True,
            "mesures_simulees": True,
        }
        self.assertEqual(analyser_ligne(formater_ligne(evenement)), evenement)
        for champ in ("factice", "mesures_simulees"):
            with self.subTest(champ=champ):
                sans_champ = dict(evenement)
                del sans_champ[champ]
                self.assertIsNone(analyser_ligne(formater_ligne(sans_champ)))
                for valeur in (None, 0, "true"):
                    with self.subTest(champ=champ, valeur=valeur):
                        invalide = dict(evenement)
                        invalide[champ] = valeur
                        self.assertIsNone(analyser_ligne(formater_ligne(invalide)))
                # Un booléen `False` reste valide : aucune égalité entre les
                # deux champs de provenance n'est exigée.
                desaccorde = dict(evenement)
                desaccorde[champ] = False
                self.assertEqual(
                    analyser_ligne(formater_ligne(desaccorde)), desaccorde
                )

    def test_lignes_parasites_ignorees(self) -> None:
        parasites = [
            "bavardage de bibliothèque",
            f"{PREFIXE_EVENEMENT}pas du JSON",
            f'{PREFIXE_EVENEMENT}{{"type": "inconnu"}}',
            f'{PREFIXE_EVENEMENT}{{"type": "audio"}}',
            f"{PREFIXE_EVENEMENT}[]",
            # Marqueur nu, sans l'espace de séparation : jamais un événement
            # analysable — mais une ligne d'événement pour les journaux du
            # serveur, qui la masquent sans jamais la recopier.
            f'{MARQUEUR_EVENEMENT}{{"nom": "SENTINELLE-FUITE"}}',
            "",
        ]
        for ligne in parasites:
            with self.subTest(ligne=ligne):
                self.assertIsNone(analyser_ligne(ligne))

    def test_lignes_hostiles_ignorees_sans_exception(self) -> None:
        # Contre-revue : un entier JSON de plus de 4300 chiffres fait lever
        # `ValueError` à `json.loads` (pas une `JSONDecodeError`) et un `type`
        # non hachable leverait `TypeError` : la ligne est rendue invalide,
        # jamais une exception.
        entier_geant = (
            PREFIXE_EVENEMENT
            + '{"type": "chargement", "duree_s": '
            + "9" * 5000
            + "}"
        )
        self.assertIsNone(analyser_ligne(entier_geant))
        self.assertIsNone(
            analyser_ligne(PREFIXE_EVENEMENT + '{"type": ["x"], "factice": true}')
        )
        self.assertIsNone(
            analyser_ligne(PREFIXE_EVENEMENT + '{"type": {"cle": 1}, "a": 2}')
        )

    def test_ligne_imbriquee_profonde_ignoree_sans_exception(self) -> None:
        # Contre-revue : un JSON imbriqué au-delà de la limite de récursion du
        # décodeur lève `RecursionError`, pas seulement `JSONDecodeError` : la
        # ligne est rendue invalide, jamais une exception.
        profonde = PREFIXE_EVENEMENT + "[" * 100_000 + "]" * 100_000
        self.assertIsNone(analyser_ligne(profonde))

    def test_non_ascii_conserve_et_ligne_unique(self) -> None:
        ligne = formater_ligne(
            {
                "type": TYPE_AUDIO_ERREUR,
                "index": 0,
                "nom": "é",
                "erreur": "échec",
                "factice": False,
                "mesures_simulees": False,
            }
        )
        self.assertTrue(ligne.startswith(PREFIXE_EVENEMENT))
        self.assertEqual(ligne.count("\n"), 1)
        self.assertNotIn("\\u00e9", ligne)
        self.assertEqual(analyser_ligne(ligne)["erreur"], "échec")

    def test_emettre_ecrit_et_vide_le_tampon(self) -> None:
        sortie = io.StringIO()
        emettre(
            {
                "type": TYPE_AUDIO_ERREUR,
                "index": 0,
                "nom": "a",
                "erreur": "x",
                "factice": False,
                "mesures_simulees": False,
            },
            sortie,
        )
        self.assertEqual(sortie.getvalue().count("\n"), 1)
        self.assertIsNone(analyser_ligne("parasite"))


def _extraction(**modifications: object) -> dict[str, object]:
    """Événement `extraction` conforme et complet, modifié par les champs donnés."""
    evenement: dict[str, object] = {
        "type": TYPE_EXTRACTION,
        "index": 0,
        "nom": "consultation",
        "conforme": True,
        "motif": None,
        "valeur": {"motif_consultation": "toux", "autres_informations": []},
        "sortie_brute": '{"motif_consultation":"toux","autres_informations":[]}',
        "tokens_entree": 812,
        "tokens_sortie": 24,
        "delai_premier_token_s": 1.25,
        "duree_generation_s": 2.5,
        "duree_extraction_s": 2.7,
        "vitesse_generation_tps": 9.2,
        "vitesse_lecture_estimee_tps": 650.0,
        "temps_cpu_s": 2.6,
        "pic_memoire_octets": 4096,
        "fin": "arret",
        "factice": False,
        "mesures_simulees": False,
    }
    evenement.update(modifications)
    return evenement


def _extraction_erreur(**modifications: object) -> dict[str, object]:
    """Événement `extraction_erreur` complet, modifié par les champs donnés."""
    evenement: dict[str, object] = {
        "type": TYPE_EXTRACTION_ERREUR,
        "index": 1,
        "nom": "consultation",
        "motif": "contexte insuffisant",
        "factice": False,
        "mesures_simulees": False,
    }
    evenement.update(modifications)
    return evenement


class ValidationExtractionTest(unittest.TestCase):
    """Validation stricte des événements d'extraction (tâche 3.1, design D5 à D7)."""

    def test_evenements_complets_valides(self) -> None:
        non_conforme = _extraction(
            conforme=False,
            motif="JSON indécodable",
            valeur=None,
            sortie_brute="{\"motif\":",
            fin="limite",
        )
        for evenement in (
            _extraction(),
            non_conforme,
            _extraction_erreur(),
        ):
            with self.subTest(type_evenement=evenement["type"]):
                self.assertEqual(
                    analyser_ligne(formater_ligne(evenement)), evenement
                )

    def test_mesures_absentes_admises_sans_zero(self) -> None:
        absentes = _extraction(
            conforme=False,
            motif="limite de sortie atteinte",
            valeur=None,
            sortie_brute=None,
            tokens_entree=None,
            tokens_sortie=None,
            delai_premier_token_s=None,
            duree_generation_s=None,
            duree_extraction_s=None,
            vitesse_generation_tps=None,
            vitesse_lecture_estimee_tps=None,
            temps_cpu_s=None,
            pic_memoire_octets=None,
            fin="limite",
        )
        lu = analyser_ligne(formater_ligne(absentes))
        self.assertEqual(lu, absentes)
        for champ in ("vitesse_generation_tps", "temps_cpu_s", "pic_memoire_octets"):
            with self.subTest(champ=champ):
                self.assertIsNone(lu[champ])
        # Une seule sortie de token : la vitesse de génération est absente, pas nulle.
        un_token = _extraction(tokens_sortie=1, vitesse_generation_tps=None)
        self.assertEqual(analyser_ligne(formater_ligne(un_token)), un_token)

    def test_entier_geant_refuse_sans_exception(self) -> None:
        # Un entier de 400 chiffres ne tient pas dans un flottant : la ligne est
        # ignorée (`None`), sans lever `OverflowError`.
        geant = _extraction(duree_extraction_s=10**399)
        self.assertIsNone(analyser_ligne(formater_ligne(geant)))
        self.assertIsNone(
            analyser_ligne(formater_ligne(_extraction(temps_cpu_s=-(10**399))))
        )

    def test_champ_requis_manquant_refuse(self) -> None:
        for type_evenement, evenement in (
            (TYPE_EXTRACTION, _extraction()),
            (TYPE_EXTRACTION_ERREUR, _extraction_erreur()),
        ):
            for champ in CHAMPS_REQUIS[type_evenement]:
                with self.subTest(type_evenement=type_evenement, champ=champ):
                    sans_champ = dict(evenement)
                    del sans_champ[champ]
                    self.assertIsNone(analyser_ligne(formater_ligne(sans_champ)))

    def test_champ_inconnu_refuse(self) -> None:
        for evenement in (
            _extraction(),
            _extraction_erreur(),
        ):
            for champ in ("champ_inconnu", "timings_natifs", "texte"):
                with self.subTest(type_evenement=evenement["type"], champ=champ):
                    self.assertIsNone(
                        analyser_ligne(formater_ligne({**evenement, champ: 1}))
                    )

    def test_types_inattendus_refuses(self) -> None:
        invalides_extraction = [
            ("index", "0"),
            ("index", True),
            ("index", -1),
            ("index", 1.0),
            ("nom", 3),
            ("conforme", "oui"),
            ("conforme", 1),
            ("valeur", "texte"),
            ("valeur", ["x"]),
            ("sortie_brute", 12),
            ("tokens_entree", -1),
            ("tokens_entree", "812"),
            ("tokens_entree", True),
            ("tokens_sortie", 1.5),
            ("delai_premier_token_s", "1.2"),
            ("delai_premier_token_s", True),
            ("duree_generation_s", -0.1),
            ("duree_extraction_s", float("nan")),
            ("duree_extraction_s", float("inf")),
            ("vitesse_generation_tps", "9"),
            ("vitesse_lecture_estimee_tps", False),
            ("temps_cpu_s", [1]),
            ("pic_memoire_octets", 1.0),
            ("fin", "stop"),
            ("fin", None),
            ("factice", "true"),
            ("mesures_simulees", None),
        ]
        for champ, valeur in invalides_extraction:
            with self.subTest(
                type_evenement=TYPE_EXTRACTION, champ=champ, valeur=valeur
            ):
                self.assertIsNone(
                    analyser_ligne(formater_ligne(_extraction(**{champ: valeur})))
                )
        invalides_erreur = [
            ("index", "0"),
            ("index", True),
            ("nom", None),
            ("motif", 3),
            ("factice", "true"),
        ]
        for champ, valeur in invalides_erreur:
            with self.subTest(
                type_evenement=TYPE_EXTRACTION_ERREUR, champ=champ, valeur=valeur
            ):
                self.assertIsNone(
                    analyser_ligne(
                        formater_ligne(_extraction_erreur(**{champ: valeur}))
                    )
                )

    def test_motif_borne(self) -> None:
        longueur_max = "x" * 200
        trop_long = "x" * 201
        self.assertEqual(
            analyser_ligne(formater_ligne(_extraction_erreur(motif=longueur_max))),
            _extraction_erreur(motif=longueur_max),
        )
        for motif in (trop_long, "", None):
            with self.subTest(motif=motif[:10] if motif else motif):
                self.assertIsNone(
                    analyser_ligne(formater_ligne(_extraction_erreur(motif=motif)))
                )
                self.assertIsNone(
                    analyser_ligne(
                        formater_ligne(
                            _extraction(conforme=False, valeur=None, motif=motif)
                        )
                    )
                )

    def test_coherence_conforme_valeur_motif(self) -> None:
        incoherents = [
            _extraction(valeur=None),
            _extraction(motif="x"),
            _extraction(sortie_brute=None),
            _extraction(conforme=False, valeur=None, motif=None),
            _extraction(conforme=False, motif="x"),
        ]
        for evenement in incoherents:
            with self.subTest(
                conforme=evenement["conforme"],
                valeur=evenement["valeur"],
                motif=evenement["motif"],
            ):
                self.assertIsNone(analyser_ligne(formater_ligne(evenement)))

    def test_provenance_transportee_comme_pour_audio(self) -> None:
        evenements = (
            _extraction(factice=True, mesures_simulees=True),
            _extraction(factice=True, mesures_simulees=False),
            _extraction_erreur(factice=True, mesures_simulees=True),
        )
        for evenement in evenements:
            with self.subTest(
                type_evenement=evenement["type"], factice=evenement["factice"]
            ):
                lu = analyser_ligne(formater_ligne(evenement))
                self.assertEqual(lu, evenement)
                self.assertIs(lu["factice"], True)
                self.assertIs(lu["mesures_simulees"], evenement["mesures_simulees"])

    def test_transcription_inchangee(self) -> None:
        # Les événements de transcription ne sont pas validés strictement : un
        # champ supplémentaire reste admis, comme avant cette tâche.
        audio_erreur = {
            "type": TYPE_AUDIO_ERREUR,
            "index": 0,
            "nom": "a.wav",
            "erreur": "échec",
            "factice": False,
            "mesures_simulees": False,
            "champ_supplementaire": 1,
        }
        self.assertEqual(analyser_ligne(formater_ligne(audio_erreur)), audio_erreur)

    def test_types_evenements_inclut_extraction(self) -> None:
        self.assertIn(TYPE_EXTRACTION, TYPES_EVENEMENTS)
        self.assertIn(TYPE_EXTRACTION_ERREUR, TYPES_EVENEMENTS)


class ValidationTimingsNatifsTest(unittest.TestCase):
    def test_mesures_non_finies_deviennent_absentes(self) -> None:
        resultat = _valider_resultat(
            {
                "texte": "x",
                "timings_natifs": [
                    {
                        "unite": "ms",
                        "load_ms": float("nan"),
                        "mel_ms": float("inf"),
                        "encode_ms": 1.0,
                        "decode_ms": None,
                    }
                ],
            }
        )

        timing = resultat["timings_natifs"][0]
        self.assertIsNone(timing["load_ms"])
        self.assertIsNone(timing["mel_ms"])
        self.assertEqual(timing["encode_ms"], 1.0)
        self.assertIsNone(timing["decode_ms"])

    def test_cle_inconnue_dans_un_timing_refusee(self) -> None:
        with self.assertRaises(ErreurAudio):
            _valider_resultat(
                {
                    "texte": "x",
                    "timings_natifs": [
                        {"unite": "ms", "load_ms": 1.0, "inventee": 2.0}
                    ],
                }
            )


class LectureJobTest(unittest.TestCase):
    def setUp(self) -> None:
        self._temporaire = tempfile.TemporaryDirectory()
        self.addCleanup(self._temporaire.cleanup)
        self.dossier = Path(self._temporaire.name)

    def test_job_valide_et_chemins_resolus(self) -> None:
        ecrire_signal(self.dossier, "a.f32", 1.0, 1.0)
        chemin = ecrire_job(
            self.dossier,
            [("a.wav", "a.f32")],
            threads_demandes=2,
            reglages={"bruit": "faible"},
        )
        job = charger_job(chemin)
        self.assertEqual(job.moteur, MOTEUR_DE_TEST)
        self.assertEqual(job.famille, FAMILLE_DE_TEST)
        self.assertEqual(job.threads_demandes, 2)
        self.assertEqual(job.reglages, {"bruit": "faible"})
        self.assertEqual(job.audios[0].nom, "a.wav")
        self.assertEqual(job.audios[0].chemin, (self.dossier / "a.f32").resolve())
        self.assertEqual(
            Path(job.modele["chemin"]), (self.dossier / "modele").resolve()
        )

    def test_job_invalide_refuse(self) -> None:
        contenu_valide = {
            "version": 1,
            "moteur": MOTEUR_DE_TEST,
            "famille": FAMILLE_DE_TEST,
            "modele": {"identifiant": "test/modele", "chemin": "modele"},
            "threads_demandes": 4,
            "reglages": {},
            "format_audio": FORMAT_AUDIO,
            "audios": [{"nom": "a.wav", "chemin": "a.f32"}],
        }
        mutations = {
            "version": {"version": 2},
            "format audio": {"format_audio": "wav"},
            "moteur vide": {"moteur": ""},
            "threads nuls": {"threads_demandes": 0},
            "threads booléens": {"threads_demandes": True},
            "audios vides": {"audios": []},
            "reglages non objet": {"reglages": []},
            "modele sans identifiant": {"modele": {"chemin": "modele"}},
            "audio sans nom": {"audios": [{"chemin": "a.f32"}]},
        }
        for libelle, changement in mutations.items():
            with self.subTest(cas=libelle):
                contenu = dict(contenu_valide)
                contenu.update(changement)
                chemin = self.dossier / "job.json"
                chemin.write_text(json.dumps(contenu), encoding="utf-8")
                with self.assertRaises(ErreurJob):
                    charger_job(chemin)

        chemin = self.dossier / "job.json"
        chemin.write_text("{", encoding="utf-8")
        with self.assertRaises(ErreurJob):
            charger_job(chemin)
        with self.assertRaises(ErreurJob):
            charger_job(self.dossier / "absent.json")


class ExecutionTest(unittest.TestCase):
    def setUp(self) -> None:
        self._temporaire = tempfile.TemporaryDirectory()
        self.addCleanup(self._temporaire.cleanup)
        self.dossier = Path(self._temporaire.name)
        adaptateur.reinitialiser()
        self.registre = registre_de_test()

    def test_chargement_unique_et_ordre_des_audios(self) -> None:
        audios = [
            ("un.wav", ecrire_signal(self.dossier, "un.f32", 1.0, 1.0)),
            ("deux.wav", ecrire_signal(self.dossier, "deux.f32", 1.0, 2.0)),
            ("trois.wav", ecrire_signal(self.dossier, "trois.f32", 1.0, 3.0)),
        ]
        chemin = ecrire_job(self.dossier, audios, reglages={"bruit": "faible"})
        _, evenements = executer_et_lire(chemin, self.registre)

        self.assertEqual(
            [evenement["type"] for evenement in evenements],
            [TYPE_CHARGEMENT, TYPE_AUDIO, TYPE_AUDIO, TYPE_AUDIO, TYPE_FIN],
        )
        self.assertEqual(adaptateur.compteur_chargements, 1)
        self.assertEqual(
            [appel["premier_echantillon"] for appel in adaptateur.appels],
            [1.0, 2.0, 3.0],
        )
        self.assertEqual(
            adaptateur.derniere_consigne["modele"]["identifiant"], "test/modele"
        )
        self.assertEqual(adaptateur.derniere_consigne["threads_demandes"], 4)
        for appel in adaptateur.appels:
            self.assertFalse(appel["modifiable"])
            self.assertEqual(appel["reglages"], {"bruit": "faible"})
            self.assertEqual(appel["taux_echantillonnage"], 16000)
        for position, evenement in enumerate(evenements[1:4]):
            with self.subTest(index=position):
                self.assertEqual(evenement["index"], position)
                self.assertEqual(evenement["nom"], audios[position][0])
                self.assertEqual(evenement["threads_demandes"], 4)
                self.assertIsNone(evenement["threads_appliques"])
                self.assertEqual(evenement["langue_imposee"], "fr")
                self.assertEqual(
                    evenement["reglages_effectifs"], {"modele": "test"}
                )
        self.assertEqual(evenements[-1]["audios_ok"], 3)
        self.assertEqual(evenements[-1]["audios_erreur"], 0)

    def test_fenetres_de_30_s_et_horodatages_decales(self) -> None:
        chemin = ecrire_job(
            self.dossier,
            [("long.wav", ecrire_signal(self.dossier, "long.f32", 31.0, 7.0))],
        )
        _, evenements = executer_et_lire(chemin, self.registre)
        audio = evenements[1]

        self.assertEqual(
            [appel["echantillons"] for appel in adaptateur.appels], [480000, 16000]
        )
        self.assertEqual(audio["nb_fenetres"], 2)
        self.assertEqual(audio["fenetre_s"], 30.0)
        self.assertEqual(audio["decoupage"], "fenetres-fixes")
        self.assertEqual(audio["duree_audio_s"], 31.0)
        self.assertEqual(audio["texte"], "héllo 480000 héllo 16000")
        self.assertEqual(len(audio["segments"]), 2)
        self.assertEqual(audio["segments"][0]["debut_s"], 0.0)
        self.assertEqual(audio["segments"][0]["fin_s"], 30.0)
        self.assertEqual(audio["segments"][1]["debut_s"], 30.0)
        self.assertEqual(audio["segments"][1]["fin_s"], 31.0)

    def test_timings_natifs_conserves_par_appel(self) -> None:
        adaptateur.reinitialiser(timings_natifs=True)
        chemin = ecrire_job(
            self.dossier,
            [("long.wav", ecrire_signal(self.dossier, "long.f32", 31.0, 7.0))],
        )
        _, evenements = executer_et_lire(chemin, self.registre)
        audio = evenements[1]

        # Une entrée par appel, dans l'ordre des fenêtres : aucune agrégation.
        self.assertEqual(len(audio["timings_natifs"]), 2)
        self.assertEqual(
            [timing["load_ms"] for timing in audio["timings_natifs"]], [1.0, 2.0]
        )
        for timing in audio["timings_natifs"]:
            self.assertEqual(
                set(timing),
                {"unite", "load_ms", "mel_ms", "encode_ms", "decode_ms"},
            )
            self.assertEqual(timing["unite"], "ms")

    def test_timings_natifs_absents_valent_none(self) -> None:
        chemin = ecrire_job(
            self.dossier,
            [("court.wav", ecrire_signal(self.dossier, "court.f32", 10.0, 4.0))],
        )
        _, evenements = executer_et_lire(chemin, self.registre)

        self.assertIsNone(evenements[1]["timings_natifs"])

    def test_timings_natifs_invalides_sont_une_erreur_audio(self) -> None:
        adaptateur.reinitialiser(timings_invalides=True)
        chemin = ecrire_job(
            self.dossier,
            [("un.wav", ecrire_signal(self.dossier, "un.f32", 1.0, 1.0))],
        )
        _, evenements = executer_et_lire(chemin, self.registre)

        erreur = evenements[1]
        self.assertEqual(erreur["type"], TYPE_AUDIO_ERREUR)
        self.assertIn("timing natif d'unité inconnue", erreur["erreur"])

    def test_audio_court_une_seule_fenetre(self) -> None:
        chemin = ecrire_job(
            self.dossier,
            [("court.wav", ecrire_signal(self.dossier, "court.f32", 10.0, 4.0))],
        )
        _, evenements = executer_et_lire(chemin, self.registre)
        audio = evenements[1]
        self.assertEqual(audio["nb_fenetres"], 1)
        self.assertEqual(audio["duree_audio_s"], 10.0)
        self.assertEqual(audio["segments"][0]["fin_s"], 10.0)

    def test_erreur_audio_puis_audios_suivants(self) -> None:
        adaptateur.reinitialiser(echec_appel=2)
        audios = [
            ("un.wav", ecrire_signal(self.dossier, "un.f32", 1.0, 1.0)),
            ("deux.wav", ecrire_signal(self.dossier, "deux.f32", 1.0, 2.0)),
            ("trois.wav", ecrire_signal(self.dossier, "trois.f32", 1.0, 3.0)),
        ]
        chemin = ecrire_job(self.dossier, audios)
        _, evenements = executer_et_lire(chemin, self.registre)

        self.assertEqual(
            [evenement["type"] for evenement in evenements],
            [TYPE_CHARGEMENT, TYPE_AUDIO, TYPE_AUDIO_ERREUR, TYPE_AUDIO, TYPE_FIN],
        )
        erreur = evenements[2]
        self.assertEqual(erreur["index"], 1)
        self.assertEqual(erreur["nom"], "deux.wav")
        self.assertIn("échec simulé", erreur["erreur"])
        self.assertNotIn("rtf", erreur)
        self.assertEqual(
            [appel["premier_echantillon"] for appel in adaptateur.appels],
            [1.0, 2.0, 3.0],
        )
        self.assertEqual(evenements[-1]["audios_ok"], 2)
        self.assertEqual(evenements[-1]["audios_erreur"], 1)

    def test_duree_nulle_est_une_erreur_sans_rtf(self) -> None:
        (self.dossier / "vide.f32").write_bytes(b"")
        chemin = ecrire_job(
            self.dossier,
            [
                ("vide.wav", "vide.f32"),
                ("ok.wav", ecrire_signal(self.dossier, "ok.f32", 1.0, 1.0)),
            ],
        )
        _, evenements = executer_et_lire(chemin, self.registre)

        erreur = evenements[1]
        self.assertEqual(erreur["type"], TYPE_AUDIO_ERREUR)
        self.assertIn("durée décodée nulle", erreur["erreur"])
        self.assertEqual(evenements[2]["type"], TYPE_AUDIO)
        self.assertEqual(len(adaptateur.appels), 1)

    def test_resultat_d_adaptateur_invalide_est_une_erreur_audio(self) -> None:
        adaptateur.reinitialiser(resultat_invalide=True)
        chemin = ecrire_job(
            self.dossier,
            [
                ("un.wav", ecrire_signal(self.dossier, "un.f32", 1.0, 1.0)),
                ("deux.wav", ecrire_signal(self.dossier, "deux.f32", 1.0, 2.0)),
            ],
        )
        _, evenements = executer_et_lire(chemin, self.registre)

        self.assertEqual(
            [evenement["type"] for evenement in evenements],
            [TYPE_CHARGEMENT, TYPE_AUDIO_ERREUR, TYPE_AUDIO, TYPE_FIN],
        )
        self.assertIn("dict", evenements[1]["erreur"])
        self.assertEqual(evenements[2]["nom"], "deux.wav")

    def test_taille_non_multiple_de_4_est_une_erreur_audio(self) -> None:
        (self.dossier / "tronque.f32").write_bytes(b"0123456789")
        chemin = ecrire_job(
            self.dossier,
            [
                ("tronque.wav", "tronque.f32"),
                ("ok.wav", ecrire_signal(self.dossier, "ok.f32", 1.0, 1.0)),
            ],
        )
        _, evenements = executer_et_lire(chemin, self.registre)

        erreur = evenements[1]
        self.assertEqual(erreur["type"], TYPE_AUDIO_ERREUR)
        self.assertIn("multiple de 4", erreur["erreur"])
        self.assertNotIn("rtf", erreur)
        self.assertEqual(evenements[2]["type"], TYPE_AUDIO)
        self.assertEqual(adaptateur.appels[0]["premier_echantillon"], 1.0)

    def test_metadonnees_divergentes_entre_fenetres(self) -> None:
        for divergence in ("effectifs", "langue", "threads"):
            with self.subTest(divergence=divergence):
                adaptateur.reinitialiser(divergence=divergence)
                chemin = ecrire_job(
                    self.dossier,
                    [
                        (
                            "long.wav",
                            ecrire_signal(self.dossier, "long.f32", 31.0, 7.0),
                        )
                    ],
                )
                _, evenements = executer_et_lire(chemin, self.registre)

                self.assertEqual(
                    [evenement["type"] for evenement in evenements],
                    [TYPE_CHARGEMENT, TYPE_AUDIO_ERREUR, TYPE_FIN],
                )
                self.assertIn("divergentes", evenements[1]["erreur"])
                self.assertNotIn("rtf", evenements[1])
                self.assertEqual(evenements[-1]["audios_erreur"], 1)

    def test_sortie_parasite_journalisee_sans_interruption(self) -> None:
        adaptateur.reinitialiser(parasite=True)
        chemin = ecrire_job(
            self.dossier,
            [
                ("un.wav", ecrire_signal(self.dossier, "un.f32", 1.0, 1.0)),
                ("deux.wav", ecrire_signal(self.dossier, "deux.f32", 1.0, 2.0)),
            ],
        )
        lignes, evenements = executer_et_lire(chemin, self.registre)

        parasites = [ligne for ligne in lignes if not ligne.startswith(PREFIXE_EVENEMENT)]
        self.assertEqual(parasites, ["bavardage de bibliothèque sans préfixe"])
        self.assertEqual(
            [evenement["type"] for evenement in evenements],
            [TYPE_CHARGEMENT, TYPE_AUDIO, TYPE_AUDIO, TYPE_FIN],
        )
        self.assertEqual(evenements[1]["texte"], "héllo 16000")

    def test_mesures_brutes_avec_unites(self) -> None:
        chemin = ecrire_job(
            self.dossier,
            [("un.wav", ecrire_signal(self.dossier, "un.f32", 1.0, 1.0))],
        )
        _, evenements = executer_et_lire(chemin, self.registre)
        audio = evenements[1]

        for cle in audio:
            self.assertNotIn("%", cle)
            self.assertNotIn("pourcent", cle)
            self.assertNotIn("swap", cle)
        self.assertGreaterEqual(audio["duree_transcription_s"], 0.0)
        self.assertGreaterEqual(audio["temps_cpu_s"], 0.0)
        self.assertGreater(audio["duree_audio_s"], 0.0)
        self.assertAlmostEqual(
            audio["rtf"], audio["duree_transcription_s"] / audio["duree_audio_s"]
        )
        self.assertIsInstance(audio["pic_memoire_octets"], int)
        self.assertGreater(audio["pic_memoire_octets"], 0)
        self.assertIsInstance(evenements[-1]["pic_memoire_octets"], int)
        for evenement in evenements:
            self.assertIs(evenement["factice"], False)
            self.assertIs(evenement["mesures_simulees"], False)


class OptionsModeleEtHorsLigneTest(unittest.TestCase):
    """Options de chargement forcées et mode hors ligne du runner (tâche 5.5)."""

    def setUp(self) -> None:
        self._temporaire = tempfile.TemporaryDirectory()
        self.addCleanup(self._temporaire.cleanup)
        self.dossier = Path(self._temporaire.name)
        adaptateur.reinitialiser()
        self.registre = registre_de_test()

    def test_options_forcees_et_dict_du_job_non_modifie(self) -> None:
        chemin = ecrire_job(
            self.dossier,
            [("un.wav", ecrire_signal(self.dossier, "un.f32", 1.0, 1.0))],
            modele={
                "identifiant": "test/modele",
                "revision": "abc",
                "chemin": "modele",
                "local_files_only": False,
                "trust_remote_code": True,
            },
        )
        job = charger_job(chemin)
        self.assertIs(job.modele["local_files_only"], False)
        self.assertIs(job.modele["trust_remote_code"], True)

        sortie = io.StringIO()
        with mock.patch.dict(os.environ, {"HF_HUB_OFFLINE": "0"}):
            with redirect_stdout(sortie):
                executer(job, self.registre)
            self.assertEqual(os.environ["HF_HUB_OFFLINE"], "0")

        consigne = adaptateur.derniere_consigne
        self.assertIs(consigne["modele"]["local_files_only"], True)
        self.assertIs(consigne["modele"]["trust_remote_code"], False)
        self.assertEqual(consigne["modele"]["identifiant"], "test/modele")
        self.assertEqual(consigne["hf_hub_offline"], "1")
        self.assertIs(job.modele["local_files_only"], False)
        self.assertIs(job.modele["trust_remote_code"], True)
        evenements = [
            evenement
            for evenement in (
                analyser_ligne(ligne) for ligne in sortie.getvalue().splitlines()
            )
            if evenement is not None
        ]
        self.assertEqual(evenements[0]["type"], TYPE_CHARGEMENT)
        self.assertEqual(evenements[-1]["type"], TYPE_FIN)

    def test_child_runner_force_hf_offline_puis_restaure(self) -> None:
        chemin = ecrire_job(
            self.dossier,
            [("un.wav", ecrire_signal(self.dossier, "un.f32", 1.0, 1.0))],
            modele={
                "identifiant": "test/modele",
                "revision": "abc",
                "chemin": "modele",
                "local_files_only": False,
                "trust_remote_code": True,
            },
        )
        base = {"HF_HUB_OFFLINE": "0", "PATH": os.environ.get("PATH", "")}
        for cle in ("SystemRoot", "SYSTEMROOT", "TEMP", "TMP"):
            if cle in os.environ:
                base[cle] = os.environ[cle]

        with mock.patch.dict(os.environ, {"HF_HUB_OFFLINE": "0"}):
            resultat = subprocess.run(
                [sys.executable, "-c", CODE_SONDE_HORS_LIGNE, str(chemin)],
                cwd=RACINE_PROJET,
                env=environnement_moteur(base),
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=120,
                check=False,
            )
            self.assertEqual(os.environ["HF_HUB_OFFLINE"], "0")

        self.assertEqual(resultat.returncode, 0, resultat.stderr)
        lignes = [
            ligne
            for ligne in resultat.stdout.splitlines()
            if ligne.startswith("##SONDE## ")
        ]
        self.assertEqual(len(lignes), 1, resultat.stderr)
        sonde = json.loads(lignes[0][len("##SONDE## ") :])
        self.assertEqual(sonde["code"], 0)
        self.assertEqual(sonde["hf_initial"], "1")
        self.assertEqual(sonde["consigne"]["hf_hub_offline"], "1")
        self.assertIs(sonde["consigne"]["modele"]["local_files_only"], True)
        self.assertIs(sonde["consigne"]["modele"]["trust_remote_code"], False)
        self.assertEqual(sonde["hf_apres"], "0")


class MoteurRefuseTest(unittest.TestCase):
    def setUp(self) -> None:
        self._temporaire = tempfile.TemporaryDirectory()
        self.addCleanup(self._temporaire.cleanup)
        self.dossier = Path(self._temporaire.name)

    def test_moteur_reel_non_qualifie_refuse(self) -> None:
        chemin = ecrire_job(
            self.dossier,
            [("a.wav", "a.f32")],
            moteur="faster-whisper",
            famille="whisper",
        )
        with self.assertRaises(ErreurMoteur) as contexte:
            executer(
                charger_job(chemin), registre_non_qualifie("faster-whisper")
            )
        self.assertIn("non qualifiée", str(contexte.exception))

    def test_moteur_ou_famille_inconnus(self) -> None:
        chemin = ecrire_job(
            self.dossier, [("a.wav", "a.f32")], moteur="inconnu"
        )
        with self.assertRaises(ErreurMoteur):
            executer(charger_job(chemin), creer_registre_fourni())
        chemin = ecrire_job(
            self.dossier, [("a.wav", "a.f32")], famille="autre"
        )
        with self.assertRaises(ErreurMoteur):
            executer(charger_job(chemin), registre_de_test())


class MesureMemoireTest(unittest.TestCase):
    @unittest.skipIf(sys.platform != "linux", "module resource et sémantique ru_maxrss propres à Linux")
    def test_pic_linux_en_octets(self) -> None:
        import resource

        attendu = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss) * 1024
        self.assertEqual(_pic_memoire_unix(), attendu)
        self.assertIsInstance(pic_memoire(), int)
        self.assertGreater(pic_memoire(), 0)

    def test_pic_windows_via_faux_psutil(self) -> None:
        class FauxProcessus:
            def __init__(self, memoire: object) -> None:
                self._memoire = memoire

            def memory_info(self) -> object:
                return self._memoire

        def faux_psutil(memoire: object) -> SimpleNamespace:
            return SimpleNamespace(Process=lambda: FauxProcessus(memoire))

        cas = {
            "peak_wset": (SimpleNamespace(peak_wset=123456), 123456),
            "aucun pic": (SimpleNamespace(rss=10), None),
        }
        for libelle, (memoire, attendu) in cas.items():
            with self.subTest(cas=libelle):
                with mock.patch.dict(sys.modules, {"psutil": faux_psutil(memoire)}):
                    self.assertEqual(_pic_memoire_windows(), attendu)

        with mock.patch.dict(sys.modules, {"psutil": None}):
            self.assertIsNone(_pic_memoire_windows())


class IsolementTest(unittest.TestCase):
    def setUp(self) -> None:
        self._temporaire = tempfile.TemporaryDirectory()
        self.addCleanup(self._temporaire.cleanup)
        self.dossier = Path(self._temporaire.name)

    def test_runner_n_importe_aucun_module_serveur(self) -> None:
        resultat = subprocess.run(
            [sys.executable, "-c", CODE_SANS_MODULE_SERVEUR],
            cwd=RACINE_PROJET,
            env={**os.environ, "PYTHONIOENCODING": "utf-8"},
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=60,
            check=False,
        )
        self.assertEqual(
            resultat.returncode,
            0,
            f"modules serveur chargés : {resultat.stdout.strip()} {resultat.stderr}",
        )
        self.assertEqual(resultat.stdout.strip(), "ok")

    def test_lancement_depuis_un_dossier_courant_quelconque(self) -> None:
        chemin = ecrire_job(
            self.dossier,
            [("a.wav", "a.f32")],
            moteur="faster-whisper",
            famille="whisper",
        )
        environ = {
            cle: valeur
            for cle, valeur in os.environ.items()
            if cle != "PYTHONPATH"
        }
        # L'enfant écrit en UTF-8 même sans variable héritée.
        environ["PYTHONIOENCODING"] = "utf-8"
        resultat = subprocess.run(
            [
                sys.executable,
                str(RACINE_PROJET / "engines" / "runner.py"),
                str(chemin),
            ],
            cwd=self.dossier,
            env=environ,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=60,
            check=False,
        )
        self.assertEqual(resultat.returncode, 3, resultat.stderr)
        self.assertEqual(resultat.stdout, "")
        # La famille réelle est qualifiée : depuis un dossier courant
        # quelconque, le runner importe son adaptateur puis échoue proprement
        # faute de modèle local, sans importer de module serveur.
        self.assertIn("chargement du modèle impossible", resultat.stderr)


class ReleveurTrace(ReleveurSysteme):
    """Relevé système réel (doubles injectés) dont chaque étape est journalisée.

    Le journal sert à vérifier le périmètre temporel et les instants des
    relevés, jamais une durée mesurée : aucune valeur réelle n'est comparée.
    """

    def __init__(self, journal: list[str], **injections: object) -> None:
        super().__init__(**injections)
        self.journal = journal

    def amorcer_cpu(self) -> AmorcageCpu:
        self.journal.append("amorcage_systeme")
        return super().amorcer_cpu()

    def lire_cpu(self, amorcage: AmorcageCpu) -> dict[str, object]:
        self.journal.append("lecture_cpu")
        return super().lire_cpu(amorcage)

    def relever_memoire(self) -> dict[str, object]:
        self.journal.append("memoire")
        return super().relever_memoire()

    def observation_chargement(self) -> dict[str, object]:
        self.journal.append("observation_chargement")
        return super().observation_chargement()

    def observation_audio(self, amorcage: AmorcageCpu) -> dict[str, object]:
        self.journal.append("observation_audio")
        return super().observation_audio(amorcage)


class CompteurCpuFixe:
    """Compteur CPU factice : valeurs programmées, appels comptés."""

    def __init__(self, valeurs: list[float]) -> None:
        self.valeurs = list(valeurs)
        self.appels = 0

    def __call__(self, **options: object) -> float:
        self.appels += 1
        return self.valeurs.pop(0)


class HorlogeFixe:
    """Horloge monotone factice : instants programmés, dans l'ordre."""

    def __init__(self, instants: list[float]) -> None:
        self.instants = list(instants)

    def __call__(self) -> float:
        return self.instants.pop(0)


#: RAM totale des instantanés de test : valeur distincte de celle du scénario
#: simulé, pour que les deux modes ne puissent pas se confondre.
TOTAL_MEMOIRE_DE_TEST = 16 * 1024**3


class MemoireFixe:
    """Instantanés mémoire programmés : RAM disponible variable, total fixe."""

    def __init__(
        self, disponibles: list[int], total: int = TOTAL_MEMOIRE_DE_TEST
    ) -> None:
        self.disponibles = list(disponibles)
        self.total = total
        self.appels = 0

    def __call__(self) -> SimpleNamespace:
        self.appels += 1
        return SimpleNamespace(
            total=self.total, available=self.disponibles.pop(0), free=1
        )


class HorlogeTracee:
    """Proxy de `time` pour le runner : journalise les bornes, délègue la mesure."""

    def __init__(self, journal: list[str]) -> None:
        self.journal = journal

    def perf_counter(self) -> float:
        self.journal.append("borne_moteur")
        return time.perf_counter()

    def process_time(self) -> float:
        self.journal.append("borne_moteur")
        return time.process_time()


class RelevesSystemeTest(unittest.TestCase):
    """Relevés CPU/RAM aux frontières du runner (tâche 1.2), sans timing réel."""

    def setUp(self) -> None:
        self._temporaire = tempfile.TemporaryDirectory()
        self.addCleanup(self._temporaire.cleanup)
        self.dossier = Path(self._temporaire.name)
        adaptateur.reinitialiser()
        self.registre = registre_de_test()

    def _releveur(
        self,
        journal: list[str],
        *,
        cpu: list[float],
        horloge: list[float],
        disponibles: list[int],
    ) -> ReleveurTrace:
        return ReleveurTrace(
            journal,
            cpu_percent=CompteurCpuFixe(cpu),
            memoire=MemoireFixe(disponibles),
            horloge=HorlogeFixe(horloge),
        )

    def _run(
        self, chemin: Path, releveur: ReleveurSysteme, journal: list[str]
    ) -> tuple[list[str], list[dict[str, object]]]:
        """Exécute un job en traçant décodage, bornes et sérialisation."""
        vrai_fromfile = np.fromfile
        vrai_transcrire = adaptateur.transcrire

        def fromfile(*arguments: object, **options: object) -> object:
            journal.append("decodage")
            return vrai_fromfile(*arguments, **options)

        def transcrire(*arguments: object, **options: object) -> object:
            journal.append("moteur")
            return vrai_transcrire(*arguments, **options)

        def emettre_trace(evenement: dict[str, object], flux: object = None) -> None:
            journal.append(f"serialisation:{evenement['type']}")
            emettre(evenement, flux)

        with (
            mock.patch(
                "engines.runner.creer_releveur_systeme",
                lambda *, factice: releveur,
            ),
            mock.patch(
                "engines.runner.np", SimpleNamespace(fromfile=fromfile)
            ),
            mock.patch("engines.runner.time", HorlogeTracee(journal)),
            mock.patch.object(adaptateur, "transcrire", transcrire),
            mock.patch("engines.runner.emettre", emettre_trace),
        ):
            return executer_et_lire(chemin, self.registre)

    def test_fenetre_systeme_entoure_les_bornes_de_l_inference(self) -> None:
        journal: list[str] = []
        releveur = self._releveur(
            journal, cpu=[99.0, 12.5], horloge=[0.0, 2.5], disponibles=[1234]
        )
        chemin = ecrire_job(
            self.dossier,
            [("un.wav", ecrire_signal(self.dossier, "un.f32", 1.0, 1.0))],
        )
        _, evenements = self._run(chemin, releveur, journal)

        self.assertEqual(
            [evenement["type"] for evenement in evenements],
            [TYPE_CHARGEMENT, TYPE_AUDIO, TYPE_FIN],
        )
        # Ordre attendu : le chargement relève sa RAM après sa borne ; l'audio
        # décode, amorce la fenêtre système, exécute les bornes du moteur, lit
        # le CPU système, relève la RAM, puis seulement sérialise l'événement.
        self.assertEqual(
            journal,
            [
                "borne_moteur",
                "borne_moteur",
                "observation_chargement",
                "memoire",
                f"serialisation:{TYPE_CHARGEMENT}",
                "decodage",
                "amorcage_systeme",
                "borne_moteur",
                "borne_moteur",
                "moteur",
                "borne_moteur",
                "borne_moteur",
                "observation_audio",
                "lecture_cpu",
                "memoire",
                f"serialisation:{TYPE_AUDIO}",
                f"serialisation:{TYPE_FIN}",
            ],
        )
        self.assertIsNone(evenements[1]["observation_systeme"]["cpu"]["motif"])
        self.assertEqual(
            evenements[1]["observation_systeme"]["cpu"]["pourcentage_moyen"],
            12.5,
        )
        self.assertNotIn("cpu", evenements[0]["observation_systeme"])

    def test_un_instantane_ram_apres_le_chargement_et_apres_chaque_audio(self) -> None:
        journal: list[str] = []
        releveur = self._releveur(
            journal,
            cpu=[99.0, 0.0, 99.0, 0.0],
            horloge=[0.0, 1.0, 2.0, 3.0],
            disponibles=[7000, 6000, 5000],
        )
        chemin = ecrire_job(
            self.dossier,
            [
                ("un.wav", ecrire_signal(self.dossier, "un.f32", 1.0, 1.0)),
                ("deux.wav", ecrire_signal(self.dossier, "deux.f32", 1.0, 2.0)),
            ],
        )
        _, evenements = self._run(chemin, releveur, journal)

        # Une RAM disponible différente à chaque frontière : les instantanés ne
        # sont ni mémoïsés ni recopiés d'une frontière à l'autre.
        self.assertEqual(
            [
                evenement["observation_systeme"]["memoire_apres"][
                    "disponible_octets"
                ]
                for evenement in evenements[:3]
            ],
            [7000, 6000, 5000],
        )
        for evenement in evenements[:3]:
            with self.subTest(type_evenement=evenement["type"]):
                memoire = evenement["observation_systeme"]["memoire_apres"]
                self.assertEqual(memoire["totale_octets"], TOTAL_MEMOIRE_DE_TEST)
                self.assertIsNone(memoire["motif"])
                self.assertIsInstance(memoire["releve_le"], str)
        self.assertEqual(journal.count("observation_chargement"), 1)
        self.assertEqual(journal.count("memoire"), 3)

    def test_releves_reels_et_simules_ne_se_melangent_jamais(self) -> None:
        journal: list[str] = []
        releveur = self._releveur(
            journal, cpu=[99.0, 7.5], horloge=[0.0, 2.5], disponibles=[5000, 4321]
        )
        chemin = ecrire_job(
            self.dossier,
            [("un.wav", ecrire_signal(self.dossier, "un.f32", 1.0, 1.0))],
        )
        _, evenements = self._run(chemin, releveur, journal)

        for evenement in evenements[:2]:
            observation = evenement["observation_systeme"]
            self.assertEqual(observation["provenance"], PROVENANCE_REELLE)
            self.assertEqual(
                observation["provenance"],
                PROVENANCE_SIMULEE
                if evenement["mesures_simulees"]
                else PROVENANCE_REELLE,
            )
        observation = evenements[1]["observation_systeme"]
        self.assertEqual(observation["cpu"]["pourcentage_moyen"], 7.5)
        self.assertEqual(observation["cpu"]["intervalle_s"], 2.5)
        self.assertEqual(observation["memoire_apres"]["disponible_octets"], 4321)
        self.assertNotEqual(
            observation["cpu"]["pourcentage_moyen"], SIMULATION_CPU_POURCENTAGE
        )

        # Sens inverse : le moteur factice n'injecte aucune valeur réelle et
        # n'appelle aucune fonction de mesure de psutil (doubles qui lèvent).
        def interdire(*arguments: object, **options: object) -> None:
            raise AssertionError("aucune mesure psutil réelle en mode factice")

        chemin_factice = ecrire_job(
            self.dossier,
            [("un.wav", ecrire_signal(self.dossier, "un.f32", 1.0, 1.0))],
            moteur="factice",
            famille="factice",
        )
        with (
            mock.patch.object(psutil, "cpu_percent", interdire),
            mock.patch.object(psutil, "virtual_memory", interdire),
        ):
            _, evenements_factices = executer_et_lire(
                chemin_factice, creer_registre_fourni()
            )

        self.assertEqual(
            [evenement["type"] for evenement in evenements_factices],
            [TYPE_CHARGEMENT, TYPE_AUDIO, TYPE_FIN],
        )
        for evenement in evenements_factices[:2]:
            with self.subTest(type_evenement=evenement["type"]):
                observation = evenement["observation_systeme"]
                self.assertIs(evenement["mesures_simulees"], True)
                self.assertEqual(observation["provenance"], PROVENANCE_SIMULEE)
                self.assertEqual(
                    observation["memoire_apres"]["disponible_octets"],
                    SIMULATION_MEMOIRE_DISPONIBLE_OCTETS,
                )
                self.assertEqual(
                    observation["memoire_apres"]["releve_le"], SIMULATION_RELEVE_LE
                )
        cpu_factice = evenements_factices[1]["observation_systeme"]["cpu"]
        self.assertEqual(cpu_factice["pourcentage_moyen"], SIMULATION_CPU_POURCENTAGE)
        self.assertEqual(cpu_factice["intervalle_s"], SIMULATION_INTERVALLE_CPU_S)
        self.assertNotEqual(cpu_factice["pourcentage_moyen"], 7.5)
        self.assertNotEqual(
            evenements_factices[1]["observation_systeme"]["memoire_apres"][
                "disponible_octets"
            ],
            4321,
        )

    def test_observation_hors_contrat_ecartee_sans_casser_l_evenement(self) -> None:
        """Objet système invalide : clé absente, événement et texte intacts (2.1)."""
        journal: list[str] = []
        releveur = self._releveur(
            journal, cpu=[99.0, 12.5], horloge=[0.0, 2.5], disponibles=[1234]
        )
        chemin = ecrire_job(
            self.dossier,
            [("un.wav", ecrire_signal(self.dossier, "un.f32", 1.0, 1.0))],
        )
        erreurs = io.StringIO()
        with (
            mock.patch.object(
                releveur,
                "observation_chargement",
                lambda: {"version": 2, "memoire_apres": {}},
            ),
            mock.patch.object(
                releveur,
                "observation_audio",
                lambda _amorcage: {
                    "version": 1,
                    "methode_cpu": "psutil-cpu-percent-nonbloquant-v1",
                    "version_psutil": "7.2.2",
                    # Provenance contradictoire avec `mesures_simulees`.
                    "provenance": "simulee",
                    "cpu": {
                        "pourcentage_moyen": 12.5,
                        "intervalle_s": 2.5,
                        "motif": None,
                    },
                    "memoire_apres": {
                        "releve_le": "2026-11-07T10:00:00+00:00",
                        "totale_octets": 4096,
                        "disponible_octets": 2048,
                        "motif": None,
                    },
                },
            ),
            redirect_stderr(erreurs),
        ):
            _, evenements = self._run(chemin, releveur, journal)

        self.assertEqual(
            [evenement["type"] for evenement in evenements],
            [TYPE_CHARGEMENT, TYPE_AUDIO, TYPE_FIN],
        )
        self.assertNotIn("observation_systeme", evenements[0])
        self.assertNotIn("observation_systeme", evenements[1])
        # L'événement et sa transcription restent valides.
        self.assertEqual(evenements[1]["texte"], "héllo 16000")
        self.assertIsNotNone(evenements[1]["rtf"])
        messages = erreurs.getvalue()
        self.assertIn("Relevé système ignoré (chargement)", messages)
        self.assertIn("Relevé système ignoré (audio)", messages)
        self.assertIn("provenance contradictoire", messages)

    def test_observation_conforme_emise_sans_cle_supplementaire(self) -> None:
        """Un objet conforme est émis tel quel sous la clé facultative."""
        journal: list[str] = []
        releveur = self._releveur(
            journal, cpu=[99.0, 12.5], horloge=[0.0, 2.5], disponibles=[1234, 1200]
        )
        chemin = ecrire_job(
            self.dossier,
            [("un.wav", ecrire_signal(self.dossier, "un.f32", 1.0, 1.0))],
        )
        erreurs = io.StringIO()
        with redirect_stderr(erreurs):
            _, evenements = self._run(chemin, releveur, journal)

        self.assertEqual(erreurs.getvalue(), "")
        for evenement in evenements[:2]:
            with self.subTest(type_evenement=evenement["type"]):
                observation = evenement["observation_systeme"]
                self.assertEqual(observation["provenance"], PROVENANCE_REELLE)
                self.assertEqual(observation["memoire_apres"]["motif"], None)
        self.assertEqual(
            set(evenements[0]["observation_systeme"]),
            {"version", "methode_cpu", "version_psutil", "provenance", "memoire_apres"},
        )
        self.assertIn("cpu", evenements[1]["observation_systeme"])
        # Aucun champ nouveau n'est exigé : les événements restent analysables.
        for evenement in evenements:
            self.assertIn("mesures_simulees", evenement)

    def test_audio_en_echec_ne_fabrique_aucune_observation(self) -> None:
        adaptateur.reinitialiser(echec_appel=2)
        journal: list[str] = []
        releveur = self._releveur(
            journal, cpu=[99.0, 12.5, 99.0],
            horloge=[0.0, 2.5], disponibles=[1234, 1200],
        )
        chemin = ecrire_job(
            self.dossier,
            [
                ("un.wav", ecrire_signal(self.dossier, "un.f32", 1.0, 1.0)),
                ("deux.wav", ecrire_signal(self.dossier, "deux.f32", 1.0, 2.0)),
            ],
        )
        _, evenements = self._run(chemin, releveur, journal)

        self.assertEqual(
            [evenement["type"] for evenement in evenements],
            [TYPE_CHARGEMENT, TYPE_AUDIO, TYPE_AUDIO_ERREUR, TYPE_FIN],
        )
        # Aucune observation finale n'est inventée pour l'audio en échec, ni
        # depuis l'état courant : la fenêtre amorcée n'est jamais lue.
        self.assertNotIn("observation_systeme", evenements[2])
        self.assertNotIn("observation_systeme", evenements[3])
        self.assertEqual(journal.count("amorcage_systeme"), 2)
        self.assertEqual(journal.count("lecture_cpu"), 1)
        self.assertEqual(journal.count("memoire"), 2)
        # Les relevés déjà produits restent intacts.
        observation = evenements[1]["observation_systeme"]
        self.assertEqual(observation["cpu"]["pourcentage_moyen"], 12.5)
        self.assertEqual(observation["memoire_apres"]["disponible_octets"], 1200)
        self.assertEqual(
            evenements[0]["observation_systeme"]["memoire_apres"][
                "disponible_octets"
            ],
            1234,
        )


# Runner d'extraction (tâche 3.2, design D4 à D7) : adaptateur de test local.

MOTEUR_EXTRACTION_DE_TEST = "moteur-extraction-de-test"
FAMILLE_EXTRACTION_DE_TEST = "extraction-de-test"
MODULE_ADAPTATEUR_EXTRACTION = "tests.adaptateur_extraction_de_test"
GRILLE_DE_TEST = read_grid("consultation-generale")
SCHEMA_DE_TEST = grid_schema(GRILLE_DE_TEST)
MESSAGE_SYSTEME_DE_TEST = system_message(GRILLE_DE_TEST).text
SORTIE_CONFORME = adaptateur_extraction.sortie_conforme(SCHEMA_DE_TEST)
RESULTAT_VALIDE = {
    "sortie_brute": SORTIE_CONFORME,
    "tokens_entree": 812,
    "tokens_sortie": 24,
    "fin": "arret",
    "delai_premier_token_s": 1.25,
    "duree_generation_s": 2.5,
    "temps_cpu_s": 2.6,
}


def registre_extraction_de_test(factice: bool = False) -> RegistreMoteurs:
    """Registre d'un moteur d'extraction de test, pointant vers l'adaptateur de test."""
    registre = RegistreMoteurs()
    registre.enregistrer(
        DeclarationAdaptateur(
            identifiant=MOTEUR_EXTRACTION_DE_TEST,
            nom="Moteur d'extraction de test",
            fichier_requirements=None,
            regle_compatibilite="aucune",
            familles=(
                Famille(
                    FAMILLE_EXTRACTION_DE_TEST,
                    "Famille d'extraction de test",
                    qualifiee=True,
                    task=TASK_EXTRACTION,
                ),
            ),
            module_adaptateur=MODULE_ADAPTATEUR_EXTRACTION,
            factice=factice,
        )
    )
    return registre


def ecrire_job_extraction(
    dossier: Path,
    sources: list[tuple[str, str]],
    *,
    moteur: str = MOTEUR_EXTRACTION_DE_TEST,
    famille: str = FAMILLE_EXTRACTION_DE_TEST,
    reglages: dict[str, object] | None = None,
    schema: dict[str, object] | None = None,
    message_systeme: str = MESSAGE_SYSTEME_DE_TEST,
) -> Path:
    """Écrit un job d'extraction ; `sources` donne (nom, texte) dans l'ordre."""
    contenu = {
        "version": 1,
        "tache": "extraction",
        "moteur": moteur,
        "famille": famille,
        "modele": {
            "identifiant": "test/extraction",
            "revision": "abc",
            "chemin": "modele",
        },
        "threads_demandes": 4,
        "reglages": {} if reglages is None else reglages,
        "schema": SCHEMA_DE_TEST if schema is None else schema,
        "message_systeme": message_systeme,
        "sources": [
            {"texte": texte, "ordre": position, "nom": nom}
            for position, (nom, texte) in enumerate(sources)
        ],
    }
    chemin_job = dossier / "job.json"
    chemin_job.write_text(json.dumps(contenu), encoding="utf-8")
    return chemin_job


def executer_extraction_et_lire(
    chemin_job: Path, registre: RegistreMoteurs
) -> tuple[str, str, list[str], list[dict[str, object]]]:
    """Exécute un job d'extraction ; rend stdout, stderr, lignes et événements valides."""
    sortie = io.StringIO()
    erreurs = io.StringIO()
    with redirect_stdout(sortie), redirect_stderr(erreurs):
        executer_extraction(charger_job_extraction(chemin_job), registre)
    lignes = [
        ligne
        for ligne in sortie.getvalue().splitlines()
        if ligne.startswith(PREFIXE_EVENEMENT)
    ]
    evenements = [
        evenement
        for evenement in (analyser_ligne(ligne) for ligne in lignes)
        if evenement is not None
    ]
    return sortie.getvalue(), erreurs.getvalue(), lignes, evenements


class ExtractionLectureJobTest(unittest.TestCase):
    def setUp(self) -> None:
        self._temporaire = tempfile.TemporaryDirectory()
        self.addCleanup(self._temporaire.cleanup)
        self.dossier = Path(self._temporaire.name)
        adaptateur_extraction.configurer()

    def test_job_valide_et_sources_ordonnees(self) -> None:
        chemin = ecrire_job_extraction(
            self.dossier,
            [("a.wav", "Première source."), ("b.wav", "Seconde source.")],
            reglages={"contexte": 8192},
        )
        job = charger_job_extraction(chemin)
        self.assertEqual(job.moteur, MOTEUR_EXTRACTION_DE_TEST)
        self.assertEqual(job.famille, FAMILLE_EXTRACTION_DE_TEST)
        self.assertEqual(job.threads_demandes, 4)
        self.assertEqual(job.reglages, {"contexte": 8192})
        self.assertEqual(job.schema, SCHEMA_DE_TEST)
        self.assertEqual(job.message_systeme, MESSAGE_SYSTEME_DE_TEST)
        self.assertEqual(
            [(source.nom, source.texte, source.ordre) for source in job.sources],
            [("a.wav", "Première source.", 0), ("b.wav", "Seconde source.", 1)],
        )
        self.assertEqual(
            Path(job.modele["chemin"]), (self.dossier / "modele").resolve()
        )

    def test_texte_absent_de_la_representation(self) -> None:
        chemin = ecrire_job_extraction(
            self.dossier, [("a.wav", "TEXTE-SECRET-A")]
        )
        job = charger_job_extraction(chemin)
        self.assertNotIn("TEXTE-SECRET-A", repr(job))
        self.assertNotIn("TEXTE-SECRET-A", repr(job.sources[0]))

    def test_job_invalide_refuse(self) -> None:
        chemin = ecrire_job_extraction(self.dossier, [("a.wav", "Texte.")])
        contenu_valide = json.loads(chemin.read_text(encoding="utf-8"))
        marqueur = f"a {SOURCE_END_MARKER} b"
        mutations = {
            "version": {"version": 2},
            "tâche transcription": {"tache": "transcription"},
            "tâche absente": {"tache": None},
            "moteur vide": {"moteur": ""},
            "threads nuls": {"threads_demandes": 0},
            "reglages non objet": {"reglages": []},
            "schema absent": {"schema": None},
            "schema non objet": {"schema": ["x"]},
            "schema non objet de type object": {"schema": {"type": "array"}},
            "message système vide": {"message_systeme": " "},
            "sources absentes": {"sources": []},
            "source non objet": {"sources": ["texte"]},
            "texte vide": {"sources": [{"texte": "", "ordre": 0, "nom": "a"}]},
            "ordre négatif": {
                "sources": [{"texte": "x", "ordre": -1, "nom": "a"}]
            },
            "ordre booléen": {
                "sources": [{"texte": "x", "ordre": True, "nom": "a"}]
            },
            "nom absent": {"sources": [{"texte": "x", "ordre": 0}]},
            "marqueur dans le texte": {
                "sources": [{"texte": marqueur, "ordre": 0, "nom": "a"}]
            },
        }
        for libelle, changement in mutations.items():
            with self.subTest(cas=libelle):
                chemin.write_text(
                    json.dumps({**contenu_valide, **changement}), encoding="utf-8"
                )
                with self.assertRaises(ErreurJob):
                    charger_job_extraction(chemin)
        chemin.write_text("{", encoding="utf-8")
        with self.assertRaises(ErreurJob):
            charger_job_extraction(chemin)

    def test_famille_de_transcription_refusee(self) -> None:
        chemin = ecrire_job_extraction(
            self.dossier,
            [("a.wav", "Texte.")],
            moteur=MOTEUR_DE_TEST,
            famille=FAMILLE_DE_TEST,
        )
        with self.assertRaises(ErreurMoteur) as contexte:
            executer_extraction(charger_job_extraction(chemin), registre_de_test())
        self.assertIn("destinée à la tâche 'transcription'", str(contexte.exception))

        chemin = ecrire_job_extraction(
            self.dossier, [("a.wav", "Texte.")], famille="absente"
        )
        with self.assertRaises(ErreurMoteur):
            executer_extraction(
                charger_job_extraction(chemin), registre_extraction_de_test()
            )


class ExtractionExecutionTest(unittest.TestCase):
    """Exécution du runner d'extraction avec l'adaptateur de test (tâche 3.2)."""

    def setUp(self) -> None:
        self._temporaire = tempfile.TemporaryDirectory()
        self.addCleanup(self._temporaire.cleanup)
        self.dossier = Path(self._temporaire.name)
        adaptateur_extraction.configurer()
        self.registre = registre_extraction_de_test()

    def _executer(
        self,
        sources: list[tuple[str, str]],
        *,
        registre: RegistreMoteurs | None = None,
        reglages: dict[str, object] | None = None,
    ) -> tuple[str, str, list[str], list[dict[str, object]]]:
        chemin = ecrire_job_extraction(self.dossier, sources, reglages=reglages)
        resultat = executer_extraction_et_lire(
            chemin, self.registre if registre is None else registre
        )
        # Aucun événement ne doit être écarté par la validation du protocole.
        self.assertEqual(len(resultat[2]), len(resultat[3]))
        return resultat

    def test_chargement_unique_et_sources_dans_l_ordre(self) -> None:
        _, _, _, evenements = self._executer(
            [("a.wav", "Première."), ("b.wav", "Seconde."), ("c.wav", "Troisième.")],
            reglages={"contexte": 16384},
        )

        self.assertEqual(
            [evenement["type"] for evenement in evenements],
            [
                TYPE_CHARGEMENT,
                TYPE_EXTRACTION,
                TYPE_EXTRACTION,
                TYPE_EXTRACTION,
                TYPE_FIN,
            ],
        )
        self.assertEqual(adaptateur_extraction.compteur_chargements, 1)
        consigne = adaptateur_extraction.derniere_consigne
        self.assertEqual(consigne["schema"], SCHEMA_DE_TEST)
        self.assertEqual(consigne["reglages"], {"contexte": 16384})
        self.assertEqual(consigne["threads_demandes"], 4)
        self.assertEqual(consigne["modele"]["identifiant"], "test/extraction")
        self.assertIs(consigne["modele"]["local_files_only"], True)
        self.assertIs(consigne["modele"]["trust_remote_code"], False)
        self.assertEqual(consigne["hf_hub_offline"], "1")
        extractions = evenements[1:4]
        self.assertEqual([e["index"] for e in extractions], [0, 1, 2])
        self.assertEqual([e["nom"] for e in extractions], ["a.wav", "b.wav", "c.wav"])
        self.assertEqual(evenements[-1]["audios_ok"], 3)
        self.assertEqual(evenements[-1]["audios_erreur"], 0)

    def test_reinitialisation_avant_chaque_source(self) -> None:
        self._executer([("a.wav", "Un."), ("b.wav", "Deux."), ("c.wav", "Trois.")])

        self.assertEqual(
            adaptateur_extraction.journal,
            [
                "charger",
                "reinitialiser",
                "generer",
                "reinitialiser",
                "generer",
                "reinitialiser",
                "generer",
            ],
        )

    def test_messages_systeme_et_utilisateur_recus(self) -> None:
        self._executer([("a.wav", "Toux depuis trois jours.")])

        messages = adaptateur_extraction.appels_generation[0]["messages"]
        self.assertEqual(
            messages,
            [
                {"role": "system", "content": MESSAGE_SYSTEME_DE_TEST},
                {"role": "user", "content": user_message("Toux depuis trois jours.")},
            ],
        )

    def test_comptage_du_prompt_soumis_transmis_a_l_evenement(self) -> None:
        adaptateur_extraction.configurer(scenario=[{"tokens_entree": 1234}])

        _, _, _, evenements = self._executer([("a.wav", "Texte.")])

        extraction = evenements[1]
        self.assertEqual(extraction["tokens_entree"], 1234)
        self.assertAlmostEqual(extraction["vitesse_lecture_estimee_tps"], 1234 / 1.25)

    def test_contexte_insuffisant_refuse_sans_generation_puis_suite(self) -> None:
        adaptateur_extraction.configurer(scenario=[{"tokens_entree": 16000}, {}])

        _, _, _, evenements = self._executer(
            [("long.wav", "Très long."), ("court.wav", "Court.")]
        )

        self.assertEqual(
            [evenement["type"] for evenement in evenements],
            [TYPE_CHARGEMENT, TYPE_EXTRACTION_ERREUR, TYPE_EXTRACTION, TYPE_FIN],
        )
        erreur = evenements[1]
        self.assertEqual(erreur["index"], 0)
        self.assertEqual(erreur["nom"], "long.wav")
        self.assertEqual(
            erreur["motif"],
            "contexte insuffisant : 20096 tokens requis "
            "(16000 de prompt + 4096 de sortie) pour un contexte de 16384",
        )
        # La source refusée n'a jamais été générée ; la suivante l'a été.
        self.assertEqual(
            adaptateur_extraction.journal,
            ["charger", "reinitialiser", "reinitialiser", "generer"],
        )
        self.assertEqual(len(adaptateur_extraction.appels_generation), 1)
        self.assertEqual(
            adaptateur_extraction.appels_generation[0]["messages"][1]["content"],
            user_message("Court."),
        )
        self.assertIs(evenements[2]["conforme"], True)
        self.assertEqual(evenements[-1]["audios_ok"], 1)
        self.assertEqual(evenements[-1]["audios_erreur"], 1)

    def test_sortie_conforme_decodee(self) -> None:
        _, _, _, evenements = self._executer([("a.wav", "Texte.")])

        extraction = evenements[1]
        self.assertIs(extraction["conforme"], True)
        self.assertIsNone(extraction["motif"])
        self.assertEqual(extraction["valeur"], json.loads(SORTIE_CONFORME))
        self.assertEqual(extraction["sortie_brute"], SORTIE_CONFORME)
        self.assertEqual(extraction["fin"], "arret")

    def test_sorties_non_conformes_gardent_la_sortie_brute(self) -> None:
        objet = json.loads(SORTIE_CONFORME)
        cas = {
            "JSON invalide": ('{"qui": "Marie"', "JSON indécodable"),
            "clé dupliquée": (
                SORTIE_CONFORME.replace('"qui": null', '"qui": null, "qui": null', 1),
                "clé JSON dupliquée",
            ),
            "clé de la grille absente": (
                '{"qui": null}',
                "clé de la grille absente",
            ),
            "clé inconnue": (
                json.dumps({**objet, "inventee_secrete_42": None}),
                "clé inconnue de la grille",
            ),
            "mauvais type": (
                json.dumps({**objet, "qui": 3}),
                "type de valeur non conforme ($.qui)",
            ),
            "liste vide": (
                json.dumps({**objet, "symptomes_declares": []}),
                "liste vide non admise ($.symptomes_declares)",
            ),
            "null hors cas admis": (
                json.dumps({**objet, "autres_informations": None}),
                "null non admis à cet endroit ($.autres_informations)",
            ),
        }
        for libelle, (brute, motif_attendu) in cas.items():
            with self.subTest(cas=libelle):
                adaptateur_extraction.configurer(
                    scenario=[{"sortie_brute": brute}]
                )
                _, _, _, evenements = self._executer([("a.wav", "Texte.")])
                extraction = evenements[1]
                self.assertEqual(extraction["type"], TYPE_EXTRACTION)
                self.assertIs(extraction["conforme"], False)
                self.assertIsNone(extraction["valeur"])
                self.assertTrue(extraction["motif"].startswith(motif_attendu))
                self.assertLessEqual(len(extraction["motif"]), 200)
                self.assertEqual(extraction["sortie_brute"], brute)

        # Le motif d'une clé inconnue ne recopie pas la clé produite par le modèle.
        adaptateur_extraction.configurer(
            scenario=[
                {"sortie_brute": json.dumps({**objet, "inventee_secrete_42": None})}
            ]
        )
        _, _, _, evenements = self._executer([("a.wav", "Texte.")])
        self.assertNotIn("inventee", evenements[1]["motif"])

    def test_motif_de_case_absente_borne_a_la_longueur_du_protocole(self) -> None:
        # Grille temporaire dont la case a une clé très longue : le chemin de la case
        # absente la reprend, et le motif dépasserait 200 caractères sans troncature.
        cle_longue = "case_" + "a" * 175
        grille = Grid(
            name="grille-temporaire",
            sha256=None,
            title="Grille temporaire",
            general_instructions=None,
            fields=(
                Field(
                    key=cle_longue,
                    label=cle_longue,
                    instructions=None,
                    line=1,
                ),
            ),
            error=None,
        )
        brute = json.dumps({"autres_informations": []})
        adaptateur_extraction.configurer(scenario=[{"sortie_brute": brute}])
        chemin = ecrire_job_extraction(
            self.dossier,
            [("a.wav", "Texte.")],
            schema=grid_schema(grille),
            message_systeme=system_message(grille).text,
        )

        _, _, lignes, evenements = executer_extraction_et_lire(chemin, self.registre)

        # Aucune ligne d'événement n'est écartée par le protocole.
        self.assertEqual(len(lignes), len(evenements))
        extraction = evenements[1]
        self.assertEqual(extraction["type"], TYPE_EXTRACTION)
        self.assertIs(extraction["conforme"], False)
        self.assertIsNone(extraction["valeur"])
        self.assertTrue(extraction["motif"].startswith("clé de la grille absente"))
        self.assertLessEqual(len(extraction["motif"]), 200)
        self.assertEqual(extraction["sortie_brute"], brute)
        self.assertEqual(evenements[-1]["audios_ok"], 1)

    def test_limite_de_sortie_non_conforme_sans_decodage(self) -> None:
        # Sortie valide dans sa forme, mais arrêtée à `sortie_max` : non conforme.
        adaptateur_extraction.configurer(
            scenario=[
                {
                    "fin": "limite",
                    "sortie_brute": SORTIE_CONFORME,
                    "tokens_sortie": 4096,
                }
            ]
        )

        _, _, _, evenements = self._executer([("a.wav", "Texte.")])

        extraction = evenements[1]
        self.assertIs(extraction["conforme"], False)
        self.assertEqual(extraction["motif"], MOTIF_LIMITE)
        self.assertIsNone(extraction["valeur"])
        self.assertEqual(extraction["sortie_brute"], SORTIE_CONFORME)
        self.assertEqual(extraction["fin"], "limite")
        self.assertEqual(extraction["tokens_sortie"], 4096)

    def test_erreur_de_l_adaptateur_bornee_sans_texte(self) -> None:
        adaptateur_extraction.configurer(
            scenario=[RuntimeError("fuite TEXTE-SENTINELLE-XYZ"), {}]
        )

        sortie, erreurs, _, evenements = self._executer(
            [("a.wav", "Texte."), ("b.wav", "Autre.")]
        )

        self.assertEqual(evenements[1]["type"], TYPE_EXTRACTION_ERREUR)
        self.assertEqual(evenements[1]["index"], 0)
        self.assertEqual(evenements[1]["motif"], "erreur du moteur (RuntimeError)")
        self.assertNotIn("TEXTE-SENTINELLE", sortie + erreurs)
        self.assertEqual(evenements[2]["type"], TYPE_EXTRACTION)
        self.assertEqual(evenements[-1]["audios_erreur"], 1)

    def test_resultat_d_adaptateur_invalide_source_en_erreur(self) -> None:
        sans_temps_cpu = {
            k: v for k, v in RESULTAT_VALIDE.items() if k != "temps_cpu_s"
        }
        cas = {
            "pas un dict": (
                ["pas un dict"],
                "résultat d'adaptateur attendu sous forme de dict",
            ),
            "clé inconnue": (
                {**RESULTAT_VALIDE, "champ": 1},
                "résultat d'adaptateur avec des clés inconnues ou manquantes",
            ),
            "clé manquante": (
                sans_temps_cpu,
                "résultat d'adaptateur avec des clés inconnues ou manquantes",
            ),
            "cause de fin inconnue": (
                {**RESULTAT_VALIDE, "fin": "stop"},
                "cause de fin inconnue : 'stop'",
            ),
            "compte négatif": (
                {**RESULTAT_VALIDE, "tokens_entree": -1},
                "'tokens_entree' doit être un entier positif ou nul",
            ),
            "sortie sans token": (
                {**RESULTAT_VALIDE, "tokens_sortie": 0},
                "sortie non vide sans aucun token généré",
            ),
            "durée négative": (
                {**RESULTAT_VALIDE, "duree_generation_s": -1.0},
                "'duree_generation_s' ne peut pas être négatif",
            ),
        }
        for libelle, (brut, motif_attendu) in cas.items():
            with self.subTest(cas=libelle):
                adaptateur_extraction.configurer(scenario=[{"brut": brut}, {}])
                _, _, _, evenements = self._executer(
                    [("a.wav", "Texte."), ("b.wav", "Autre.")]
                )
                self.assertEqual(
                    [evenement["type"] for evenement in evenements],
                    [
                        TYPE_CHARGEMENT,
                        TYPE_EXTRACTION_ERREUR,
                        TYPE_EXTRACTION,
                        TYPE_FIN,
                    ],
                )
                self.assertEqual(evenements[1]["motif"], motif_attendu)

    def test_mesures_absentes_valent_null(self) -> None:
        adaptateur_extraction.configurer(
            scenario=[
                {
                    "tokens_sortie": 1,
                    "delai_premier_token_s": None,
                    "duree_generation_s": None,
                    "temps_cpu_s": None,
                }
            ]
        )

        _, _, _, evenements = self._executer([("a.wav", "Texte.")])

        extraction = evenements[1]
        self.assertIsNone(extraction["delai_premier_token_s"])
        self.assertIsNone(extraction["duree_generation_s"])
        self.assertIsNone(extraction["temps_cpu_s"])
        self.assertIsNone(extraction["vitesse_generation_tps"])
        self.assertIsNone(extraction["vitesse_lecture_estimee_tps"])
        self.assertIsInstance(extraction["duree_extraction_s"], float)
        self.assertGreaterEqual(extraction["duree_extraction_s"], 0.0)
        self.assertIsInstance(extraction["pic_memoire_octets"], int)

    def test_vitesses_calculees_selon_d6(self) -> None:
        adaptateur_extraction.configurer(
            scenario=[
                {
                    "tokens_entree": 100,
                    "tokens_sortie": 5,
                    "delai_premier_token_s": 0.5,
                    "duree_generation_s": 2.0,
                }
            ]
        )

        _, _, _, evenements = self._executer([("a.wav", "Texte.")])

        extraction = evenements[1]
        # (tokens_sortie − 1) / durée de génération ; tokens_entree / délai.
        self.assertAlmostEqual(extraction["vitesse_generation_tps"], 4 / 2.0)
        self.assertAlmostEqual(extraction["vitesse_lecture_estimee_tps"], 100 / 0.5)

    def test_vitesse_generation_absente_sous_deux_tokens_et_aucun_token(self) -> None:
        adaptateur_extraction.configurer(
            scenario=[
                {
                    "tokens_sortie": 1,
                    "duree_generation_s": 2.0,
                },
                {
                    "sortie_brute": "",
                    "tokens_sortie": 0,
                    "duree_generation_s": None,
                    "delai_premier_token_s": 0.4,
                },
            ]
        )

        _, _, _, evenements = self._executer(
            [("a.wav", "Un."), ("b.wav", "Deux.")]
        )

        un_token, aucun_token = evenements[1], evenements[2]
        self.assertIsNone(un_token["vitesse_generation_tps"])
        self.assertIs(aucun_token["conforme"], False)
        self.assertIsNone(aucun_token["sortie_brute"])
        self.assertIsNone(aucun_token["vitesse_generation_tps"])
        self.assertAlmostEqual(aucun_token["vitesse_lecture_estimee_tps"], 812 / 0.4)

    def test_observations_systeme_du_chargement_et_du_lot(self) -> None:
        _, _, _, evenements = self._executer([("a.wav", "Texte.")])

        chargement, extraction, fin = evenements[0], evenements[1], evenements[-1]
        self.assertIsNotNone(
            valider_observation_systeme(
                chargement["observation_systeme"],
                moment=MOMENT_CHARGEMENT,
                mesures_simulees=False,
            )[0]
        )
        self.assertIsNotNone(
            valider_observation_systeme(
                fin["observation_systeme"],
                moment=MOMENT_AUDIO,
                mesures_simulees=False,
            )[0]
        )
        self.assertNotIn("observation_systeme", extraction)
        self.assertIs(chargement["factice"], False)
        self.assertIs(fin["mesures_simulees"], False)

    def test_provenance_factice_mesures_simulees(self) -> None:
        _, _, _, evenements = self._executer(
            [("a.wav", "Texte.")], registre=registre_extraction_de_test(factice=True)
        )

        chargement, extraction, fin = evenements[0], evenements[1], evenements[-1]
        for evenement in (chargement, extraction, fin):
            with self.subTest(type_evenement=evenement["type"]):
                self.assertIs(evenement["factice"], True)
                self.assertIs(evenement["mesures_simulees"], True)
        self.assertEqual(chargement["duree_s"], DUREE_CHARGEMENT_SIMULEE_S)
        self.assertEqual(extraction["duree_extraction_s"], DUREE_EXTRACTION_SIMULEE_S)
        self.assertEqual(extraction["pic_memoire_octets"], PIC_MEMOIRE_SIMULE_OCTETS)
        self.assertEqual(
            chargement["observation_systeme"]["provenance"], PROVENANCE_SIMULEE
        )

    def test_journal_sans_texte_source_ni_sortie_du_modele(self) -> None:
        adaptateur_extraction.configurer(
            scenario=[
                {
                    "sortie_brute": '{"qui": "SORTIE-SENTINELLE-9"',
                }
            ]
        )

        sortie, erreurs, _, evenements = self._executer(
            [("a.wav", "TEXTE-SOURCE-SENTINELLE-7 et suite.")]
        )

        # La sortie brute n'apparaît que dans l'événement, jamais dans le journal.
        self.assertIn("SORTIE-SENTINELLE-9", sortie)
        self.assertNotIn("SORTIE-SENTINELLE", erreurs)
        self.assertNotIn("TEXTE-SOURCE-SENTINELLE", erreurs)
        self.assertNotIn("SORTIE-SENTINELLE", evenements[1]["motif"])
        self.assertIn("source 1/1", erreurs)
        self.assertIn("terminé", erreurs)


class ExtractionChargementTest(unittest.TestCase):
    def setUp(self) -> None:
        self._temporaire = tempfile.TemporaryDirectory()
        self.addCleanup(self._temporaire.cleanup)
        self.dossier = Path(self._temporaire.name)
        adaptateur_extraction.configurer()

    def test_echec_de_grammaire_sans_generation(self) -> None:
        adaptateur_extraction.configurer(
            echec_charger="grammaire refusée : propriété inconnue"
        )
        chemin = ecrire_job_extraction(self.dossier, [("a.wav", "Texte.")])

        sortie = io.StringIO()
        with redirect_stdout(sortie), redirect_stderr(io.StringIO()), self.assertRaises(
            ErreurMoteur
        ) as contexte:
            executer_extraction(
                charger_job_extraction(chemin), registre_extraction_de_test()
            )

        self.assertIn("chargement du modèle impossible", str(contexte.exception))
        self.assertIn("grammaire refusée", str(contexte.exception))
        self.assertEqual(sortie.getvalue(), "")
        self.assertEqual(adaptateur_extraction.journal, ["charger"])

    def test_codes_de_sortie_du_point_d_entree(self) -> None:
        chemin = ecrire_job_extraction(self.dossier, [("a.wav", "Texte.")])
        registre_test = mock.patch(
            "engines.runner_extraction.creer_registre_fourni",
            registre_extraction_de_test,
        )

        adaptateur_extraction.configurer(echec_charger="grammaire refusée")
        with registre_test, redirect_stdout(io.StringIO()) as sortie, redirect_stderr(
            io.StringIO()
        ) as erreurs:
            code_echec = main_extraction([str(chemin)])
        self.assertEqual(code_echec, 3)
        self.assertIn("moteur indisponible", erreurs.getvalue())
        self.assertEqual(sortie.getvalue(), "")

        adaptateur_extraction.configurer()
        with registre_test, redirect_stdout(io.StringIO()), redirect_stderr(
            io.StringIO()
        ):
            self.assertEqual(main_extraction([str(chemin)]), 0)

        with redirect_stderr(io.StringIO()):
            self.assertEqual(main_extraction([str(self.dossier / "absent.json")]), 2)
            self.assertEqual(main_extraction([]), 2)


class ExtractionIsolementTest(unittest.TestCase):
    def setUp(self) -> None:
        self._temporaire = tempfile.TemporaryDirectory()
        self.addCleanup(self._temporaire.cleanup)
        self.dossier = Path(self._temporaire.name)

    def test_runner_extraction_sans_paquet_serveur_web(self) -> None:
        code = (
            "import sys\n"
            "import engines.runner_extraction\n"
            "interdits = ('flask', 'waitress', 'werkzeug', 'jinja2')\n"
            "charges = [m for m in interdits if m in sys.modules]\n"
            "print('|'.join(charges) if charges else 'ok')\n"
        )
        resultat = subprocess.run(
            [sys.executable, "-c", code],
            cwd=RACINE_PROJET,
            env={**os.environ, "PYTHONIOENCODING": "utf-8"},
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=60,
            check=False,
        )
        self.assertEqual(resultat.returncode, 0, resultat.stderr)
        self.assertEqual(resultat.stdout.strip(), "ok")

    def test_lancement_avec_registre_fourni_refuse_famille_non_qualifiee(self) -> None:
        # Le vrai registre est utilisé : llm-gguf n'est pas qualifiée, donc refusée
        # avant tout import d'adaptateur (aucune bibliothèque de moteur chargée).
        chemin = ecrire_job_extraction(
            self.dossier,
            [("a.wav", "Texte.")],
            moteur="llama-cpp",
            famille="llm-gguf",
        )
        resultat = subprocess.run(
            [
                sys.executable,
                str(RACINE_PROJET / "engines" / "runner_extraction.py"),
                str(chemin),
            ],
            cwd=self.dossier,
            env={**os.environ, "PYTHONIOENCODING": "utf-8"},
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=60,
            check=False,
        )
        self.assertEqual(resultat.returncode, 3, resultat.stderr)
        self.assertEqual(resultat.stdout, "")
        self.assertIn("non qualifiée", resultat.stderr)


if __name__ == "__main__":
    unittest.main()
