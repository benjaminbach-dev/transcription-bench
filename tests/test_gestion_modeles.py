"""Tests du téléchargement explicite et de l'inventaire local des modèles.

Aucun réseau réel, aucun poids et aucun moteur installé : un client de
téléchargement simulé écrit des fichiers locaux temporaires, et une vérification
factice fournit un résultat déjà accepté. Les moteurs sont des doublures
déclarées dans le test ; aucune déclaration fournie ne change de qualification.
"""

from __future__ import annotations

import fnmatch
import json
import shutil
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

from engines.declarations import DECLARATION_FACTICE
from engines.registre import MoteurInconnu, RegistreMoteurs
from tests.test_verification_modeles import (
    COMMIT,
    declaration_synthetique,
)
from transcription_bench.gestion_modeles import (
    NOM_DOSSIER_FICHIERS,
    NOM_MARQUEUR,
    RAISON_ACCES_REFUSE,
    ClientHuggingFaceTelechargement,
    ErreurClientTelechargement,
    GestionModeles,
    cle_stockage,
    empreinte_verification,
)
from transcription_bench.moteurs import ETAT_ECHEC, ETAT_NON_INSTALLE, ETAT_PRET, EtatMoteur
from transcription_bench.operations import (
    ETAT_ECHOUEE,
    ETAT_EN_COURS,
    ETAT_TERMINEE,
    TYPE_EXECUTION,
    CreneauOccupe,
    CreneauOperations,
    ServiceArrete,
)
from transcription_bench.paths import ValeurRefusee
from transcription_bench.verification_modeles import (
    FichierVerifie,
    ResultatVerification,
)
from transcription_bench.stockage import VERROU_STOCKAGE, ecrire_json_atomique

DELAI = 5.0
MOTEUR = "moteur-de-test"
CONTENUS = {
    "config.json": b"{}",
    "model.bin": b"poids-ctranslate2-simule",
    "preprocessor_config.json": b"{}",
    "tokenizer.json": b"{}",
}
AUTRE_COMMIT = "fedcba9876543210fedcba9876543210fedcba98"


def instantane_arbre(racine: Path) -> dict[str, bytes]:
    """Contenu de tous les fichiers sous `racine`, pour prouver leur conservation."""
    return {
        str(chemin.relative_to(racine)): chemin.read_bytes()
        for chemin in sorted(racine.rglob("*"))
        if chemin.is_file()
    }


class _VerrouObserve:
    """Verrou qui signale l'entrée avant d'attendre le verrou réel."""

    def __init__(self, verrou) -> None:
        self.verrou = verrou
        self.avant = threading.Event()

    def __enter__(self):
        self.avant.set()
        self.verrou.acquire()
        return self

    def __exit__(self, exc_type, exc, traceback) -> bool:
        self.verrou.release()
        return False


class FauxMoteurs:
    """Inventaire d'états injecté, sans installation réelle."""

    def __init__(self, etats: tuple[EtatMoteur, ...]) -> None:
        self._etats = tuple(etats)

    def inventaire(self) -> tuple[EtatMoteur, ...]:
        return self._etats


class FausseVerification:
    """Vérification factice : résultat en mémoire et appels relevés."""

    def __init__(self, resultat: ResultatVerification | None) -> None:
        self.resultat = resultat
        self.lances: list[tuple[str, str, str | None, str | None]] = []

    def lancer(self, identifiant, moteur, *, revision=None, fichier_gguf=None) -> None:
        self.lances.append((identifiant, moteur, revision, fichier_gguf))

    def dernier_resultat(self) -> ResultatVerification | None:
        return self.resultat


class FauxClientTelechargement:
    """Client simulé : écrit des contenus locaux et relève les appels."""

    def __init__(
        self,
        contenus: dict[str, bytes] | None = None,
        *,
        erreur: BaseException | None = None,
        tronquer: bool = False,
    ) -> None:
        self.contenus = dict(CONTENUS if contenus is None else contenus)
        self.erreur = erreur
        self.tronquer = tronquer
        self.appels: list[tuple[str, str, tuple[str, ...], Path]] = []

    def telecharger(self, id_resolu, commit, fichiers, dossier) -> None:
        self.appels.append((id_resolu, commit, tuple(fichiers), Path(dossier)))
        if self.erreur is not None:
            raise self.erreur
        for nom in fichiers:
            contenu = self.contenus.get(nom)
            if contenu is None:
                # Certaines réponses de la bibliothèque ne matérialisent rien.
                continue
            chemin = Path(dossier) / nom
            chemin.parent.mkdir(parents=True, exist_ok=True)
            chemin.write_bytes(contenu[:-1] if self.tronquer else contenu)


class ClientBloqueTelechargement(FauxClientTelechargement):
    """Client qui bloque au milieu du téléchargement jusqu'à libération."""

    def __init__(self) -> None:
        super().__init__()
        self.debut = threading.Event()
        self.fin = threading.Event()

    def telecharger(self, id_resolu, commit, fichiers, dossier) -> None:
        self.debut.set()
        if not self.fin.wait(DELAI):
            raise AssertionError("client bloqué non libéré")
        super().telecharger(id_resolu, commit, fichiers, dossier)


class BaseGestionTest(unittest.TestCase):
    def setUp(self) -> None:
        temporaire = tempfile.TemporaryDirectory()
        self.addCleanup(temporaire.cleanup)
        # Chemin résolu : le produit résout les siens ; sous Windows, le
        # dossier temporaire peut être rendu en chemin court (8.3).
        self.donnees = Path(temporaire.name).resolve() / "data"
        self.creneau = CreneauOperations()
        self.addCleanup(self._nettoyer_creneau)
        self.registre = RegistreMoteurs()
        self.registre.enregistrer(declaration_synthetique(identifiant=MOTEUR))
        self.moteurs = FauxMoteurs(
            (EtatMoteur(identifiant=MOTEUR, nom="Moteur de test", etat=ETAT_PRET),)
        )
        self.verification = FausseVerification(self.resultat())
        self.client = FauxClientTelechargement()

    def _nettoyer_creneau(self) -> None:
        self.creneau.arreter(0.1)

    def resultat(
        self,
        *,
        commit: str = COMMIT,
        id_resolu: str = "org/modele",
        identifiant: str = "org/modele",
        fichiers: tuple[FichierVerifie, ...] | None = None,
        gguf: str | None = None,
    ) -> ResultatVerification:
        if fichiers is None:
            fichiers = tuple(
                FichierVerifie(nom, len(octets)) for nom, octets in CONTENUS.items()
            )
        total = (
            sum(fichier.taille for fichier in fichiers)
            if fichiers and all(fichier.taille is not None for fichier in fichiers)
            else None
        )
        return ResultatVerification(
            accepte=True,
            identifiant=identifiant,
            moteur=MOTEUR,
            famille="whisper",
            commit=commit,
            id_resolu=id_resolu,
            fichiers=fichiers,
            taille_totale=total,
            fichier_gguf=gguf,
            message="dépôt compatible (simulé)",
        )

    def service(
        self,
        *,
        client=None,
        verification=None,
        moteurs=None,
    ) -> GestionModeles:
        return GestionModeles(
            self.donnees,
            self.registre,
            self.creneau,
            moteurs or self.moteurs,
            verification=verification or self.verification,
            client=client if client is not None else self.client,
        )

    def attendre(self) -> None:
        thread = self.creneau.thread_travailleur
        self.assertIsNotNone(thread)
        thread.join(DELAI)
        self.assertFalse(thread.is_alive(), "thread de téléchargement non terminé")

    def dossier(self, resultat: ResultatVerification) -> Path:
        cle = cle_stockage(resultat.id_resolu, resultat.commit, resultat.fichier_gguf)
        return self.donnees / "models" / MOTEUR / cle

    def telecharger(self, service: GestionModeles, resultat: ResultatVerification) -> None:
        self.assertTrue(service.lancer_telechargement(empreinte_verification(resultat)))
        self.attendre()


class IdentiteEtAdmissionTest(BaseGestionTest):
    def test_cle_distincte_par_identifiant_et_variante(self) -> None:
        self.assertNotEqual(
            cle_stockage("a__b/c", COMMIT), cle_stockage("a/b__c", COMMIT)
        )
        self.assertNotEqual(
            cle_stockage("org/modele", COMMIT, "modele-a.gguf"),
            cle_stockage("org/modele", COMMIT, "modele-b.gguf"),
        )
        for identifiant in ("modele", "CON", "org/modele"):
            with self.subTest(identifiant=identifiant):
                self.assertEqual(len(cle_stockage(identifiant, COMMIT)), 64)
        self.assertNotEqual(cle_stockage("CON", COMMIT), cle_stockage("modele", COMMIT))

    def test_constructeur_sans_es_ni_client_reseau(self) -> None:
        appels: list[str] = []
        service = GestionModeles(
            self.donnees,
            self.registre,
            self.creneau,
            self.moteurs,
            verification=self.verification,
            fabrique_client=lambda: appels.append("client"),
        )
        self.assertEqual(appels, [])
        self.assertEqual(service.inventaire(), ())
        self.assertFalse(self.donnees.exists())

    def test_verification_refusee_si_moteur_non_pret_sans_delegation(self) -> None:
        service = self.service(
            moteurs=FauxMoteurs(
                (
                    EtatMoteur(
                        identifiant=MOTEUR,
                        nom="Moteur de test",
                        etat=ETAT_NON_INSTALLE,
                    ),
                )
            )
        )
        with self.assertRaises(ValeurRefusee):
            service.lancer_verification("org/modele", MOTEUR)
        self.assertEqual(self.verification.lances, [])
        self.assertFalse(self.donnees.exists())

    def test_verification_refusee_pour_identifiant_invalide_avant_lecture(self) -> None:
        with self.assertRaises(ValeurRefusee):
            self.service().lancer_verification("../secret", MOTEUR)
        self.assertEqual(self.verification.lances, [])
        self.assertFalse(self.donnees.exists())

    def test_verification_refusee_pour_moteur_inconnu_ou_factice(self) -> None:
        self.registre.enregistrer(DECLARATION_FACTICE)
        service = self.service(
            moteurs=FauxMoteurs(
                (
                    EtatMoteur(
                        identifiant=MOTEUR,
                        nom="Moteur de test",
                        etat=ETAT_PRET,
                    ),
                    EtatMoteur(
                        identifiant="factice",
                        nom="Moteur factice",
                        etat=ETAT_PRET,
                        factice=True,
                    ),
                )
            )
        )
        with self.assertRaises(MoteurInconnu):
            service.lancer_verification("org/modele", "moteur-absent")
        with self.assertRaises(ValeurRefusee):
            service.lancer_verification("org/modele", "factice")
        self.assertEqual(self.verification.lances, [])

    def test_verification_delegue_quand_moteur_pret(self) -> None:
        self.service().lancer_verification(
            "org/modele", MOTEUR, revision="main", fichier_gguf=None
        )
        self.assertEqual(
            self.verification.lances, [("org/modele", MOTEUR, "main", None)]
        )

    def test_moteurs_disponibles_filtre_non_prets_et_factice(self) -> None:
        service = self.service(
            moteurs=FauxMoteurs(
                (
                    EtatMoteur(identifiant=MOTEUR, nom="Prêt", etat=ETAT_PRET),
                    EtatMoteur(identifiant="autre", nom="Échec", etat=ETAT_ECHEC),
                    EtatMoteur(
                        identifiant="factice",
                        nom="Factice",
                        etat=ETAT_PRET,
                        factice=True,
                    ),
                )
            )
        )
        self.assertEqual(
            [moteur.identifiant for moteur in service.moteurs_disponibles()],
            [MOTEUR],
        )


class TelechargementTest(BaseGestionTest):
    def test_refus_sans_resultat_ou_avec_empreinte_invalide_sans_io(self) -> None:
        service = self.service(verification=FausseVerification(None))
        with self.assertRaises(ValeurRefusee):
            service.lancer_telechargement("a" * 64)
        with self.assertRaises(ValeurRefusee):
            self.service().lancer_telechargement("a" * 64)
        self.assertEqual(self.client.appels, [])
        self.assertFalse(self.donnees.exists())

    def test_empreinte_perimee_refusee_apres_nouvelle_verification(self) -> None:
        ancien = self.resultat()
        self.verification.resultat = ancien
        empreinte = empreinte_verification(ancien)
        self.verification.resultat = self.resultat(commit=AUTRE_COMMIT)
        with self.assertRaises(ValeurRefusee):
            self.service().lancer_telechargement(empreinte)
        self.assertEqual(self.client.appels, [])
        self.assertFalse(self.donnees.exists())

    def test_refus_si_moteur_non_pret_avant_admission(self) -> None:
        service = self.service(
            moteurs=FauxMoteurs(
                (
                    EtatMoteur(
                        identifiant=MOTEUR,
                        nom="Moteur de test",
                        etat=ETAT_NON_INSTALLE,
                    ),
                )
            )
        )
        with self.assertRaises(ValeurRefusee):
            service.lancer_telechargement(empreinte_verification(self.resultat()))
        self.assertEqual(self.client.appels, [])
        self.assertFalse(self.donnees.exists())

    def test_telechargement_reussi_identite_commit_et_marqueur(self) -> None:
        resultat = self.resultat()
        service = self.service()
        self.telecharger(service, resultat)

        self.assertEqual(len(self.client.appels), 1)
        id_resolu, commit, fichiers, dossier_fichiers = self.client.appels[0]
        self.assertEqual(id_resolu, "org/modele")
        self.assertEqual(commit, COMMIT)
        self.assertEqual(fichiers, tuple(CONTENUS))
        self.assertEqual(dossier_fichiers, self.dossier(resultat) / NOM_DOSSIER_FICHIERS)
        self.assertEqual(self.creneau.instantane().etat, ETAT_TERMINEE)

        manifeste = json.loads((self.dossier(resultat) / NOM_MARQUEUR).read_text())
        self.assertEqual(manifeste["moteur"], MOTEUR)
        self.assertEqual(manifeste["identifiant"], "org/modele")
        self.assertEqual(manifeste["id_resolu"], "org/modele")
        self.assertEqual(manifeste["commit"], COMMIT)
        self.assertEqual(manifeste["famille"], "whisper")
        self.assertIsNone(manifeste["fichier_gguf"])

        modeles = service.inventaire()
        self.assertEqual(len(modeles), 1)
        modele = modeles[0]
        self.assertEqual(modele.cle, cle_stockage("org/modele", COMMIT))
        attendu_disque = sum(
            chemin.stat().st_size
            for chemin in self.dossier(resultat).rglob("*")
            if chemin.is_file() and not chemin.is_symlink()
        )
        self.assertEqual(modele.taille_disque, attendu_disque)
        self.assertEqual(modele.taille_distante, sum(len(o) for o in CONTENUS.values()))

    def test_motifs_glob_echappes_et_client_sans_jeton(self) -> None:
        with mock.patch(
            "transcription_bench.gestion_modeles.snapshot_download"
        ) as telecharger:
            ClientHuggingFaceTelechargement().telecharger(
                "org/modele",
                COMMIT,
                ("model[abc].safetensors", "dossier/poids.gguf"),
                Path("/tmp/modeles-factices"),
            )
        options = telecharger.call_args.kwargs
        self.assertEqual(
            options["allow_patterns"],
            ["model[[]abc].safetensors", "dossier/poids.gguf"],
        )
        self.assertEqual(options["max_workers"], 1)
        self.assertEqual(options["revision"], COMMIT)
        self.assertEqual(options["repo_id"], "org/modele")
        self.assertNotIn("token", options)
        self.assertFalse(
            fnmatch.fnmatch("modela.safetensors", options["allow_patterns"][0])
        )

    def test_cache_huggingface_alias_vers_resultats_refuse_avant_client(self) -> None:
        resultat = self.resultat()
        dossier = self.dossier(resultat)
        fichiers = dossier / NOM_DOSSIER_FICHIERS
        fichiers.mkdir(parents=True)
        resultats = self.donnees / "results" / "run-sentinelle"
        resultats.mkdir(parents=True)
        sentinelle = resultats / "run.json"
        sentinelle.write_text("résultat intact", encoding="utf-8")
        (fichiers / ".cache").symlink_to(resultats, target_is_directory=True)

        service = self.service()
        self.telecharger(service, resultat)

        self.assertEqual(self.client.appels, [])
        self.assertEqual(service.inventaire(), ())
        self.assertEqual(sentinelle.read_text(encoding="utf-8"), "résultat intact")
        self.assertEqual(self.creneau.instantane().etat, ETAT_ECHOUEE)

    def test_fichiers_manquants_ou_taille_changee_non_pret_puis_reparation(self) -> None:
        service = self.service()
        resultat = self.resultat()
        self.telecharger(service, resultat)
        self.assertEqual(len(service.inventaire()), 1)
        chemin = self.dossier(resultat) / NOM_DOSSIER_FICHIERS / "model.bin"
        original = chemin.read_bytes()

        chemin.write_bytes(original[:-1])
        self.assertEqual(service.inventaire(), ())
        self.assertEqual(self.service().inventaire(), ())

        self.verification.resultat = resultat
        self.assertTrue(
            service.lancer_telechargement(empreinte_verification(resultat))
        )
        self.attendre()
        self.assertEqual(len(service.inventaire()), 1)
        self.assertEqual(chemin.read_bytes(), original)

        chemin.unlink()
        self.assertEqual(service.inventaire(), ())
        self.assertTrue(
            service.lancer_telechargement(empreinte_verification(resultat))
        )
        self.attendre()
        self.assertEqual(len(service.inventaire()), 1)

    def test_lien_interne_vers_un_fichier_reel_non_pret(self) -> None:
        service = self.service()
        resultat = self.resultat()
        self.telecharger(service, resultat)
        self.assertEqual(len(service.inventaire()), 1)

        fichiers = self.dossier(resultat) / NOM_DOSSIER_FICHIERS
        original = fichiers / "model.bin"
        alias = fichiers / "alias.bin"
        alias.write_bytes(original.read_bytes())
        original.unlink()
        original.symlink_to(alias.name)

        self.assertEqual(service.inventaire(), ())

    def test_marqueur_symlink_sortant_jamais_lu(self) -> None:
        cle = "a" * 64
        dossier = self.donnees / "models" / MOTEUR / cle
        dossier.mkdir(parents=True)
        exterieur = Path(self.donnees.parent) / "manifeste-exterieur.json"
        exterieur.write_text('{"moteur": "moteur-de-test"}', encoding="utf-8")
        (dossier / NOM_MARQUEUR).symlink_to(exterieur)

        with mock.patch(
            "transcription_bench.gestion_modeles.lire_json"
        ) as lire:
            self.assertEqual(self.service().inventaire(), ())
            lire.assert_not_called()

    def test_deja_pret_ne_relance_pas_de_telechargement(self) -> None:
        resultat = self.resultat()
        service = self.service()
        self.telecharger(service, resultat)
        self.assertFalse(service.lancer_telechargement(empreinte_verification(resultat)))
        self.assertEqual(len(self.client.appels), 1)
        self.assertEqual(self.creneau.instantane().etat, ETAT_TERMINEE)

    def test_partiel_sans_marqueur_repris_par_demande_explicite(self) -> None:
        resultat = self.resultat()
        dossier = self.dossier(resultat)
        partiel = dossier / NOM_DOSSIER_FICHIERS
        partiel.mkdir(parents=True)
        (partiel / "ancien.bin").write_bytes(b"reliquat")
        service = self.service()
        self.telecharger(service, resultat)
        self.assertEqual(len(service.inventaire()), 1)

    def test_interruption_pendant_telechargement_ne_marque_jamais_pret(self) -> None:
        client = ClientBloqueTelechargement()
        service = self.service(client=client)
        resultat = self.resultat()
        self.assertTrue(
            service.lancer_telechargement(empreinte_verification(resultat))
        )
        self.assertTrue(client.debut.wait(DELAI), "téléchargement non démarré")
        self.assertFalse(self.creneau.arreter(0.1))
        client.fin.set()
        thread = self.creneau.thread_travailleur
        self.assertIsNotNone(thread)
        thread.join(DELAI)
        self.assertFalse(thread.is_alive())
        self.assertEqual(self.creneau.instantane().etat, "interrompue")
        self.assertEqual(service.inventaire(), ())
        self.assertFalse((self.dossier(resultat) / NOM_MARQUEUR).exists())

    def test_fichier_distant_model_json_ne_remplace_pas_l_inventaire(self) -> None:
        contenus = dict(CONTENUS)
        contenus["model.json"] = b'{"faux": true}'
        fichiers = tuple(
            FichierVerifie(nom, len(octets)) for nom, octets in contenus.items()
        )
        resultat = self.resultat(fichiers=fichiers)
        self.verification.resultat = resultat
        service = self.service(client=FauxClientTelechargement(contenus))
        self.telecharger(service, resultat)

        manifeste = json.loads(
            (self.dossier(resultat) / NOM_MARQUEUR).read_text(encoding="utf-8")
        )
        self.assertEqual(manifeste["moteur"], MOTEUR)
        self.assertEqual(manifeste["commit"], COMMIT)
        self.assertEqual(
            (self.dossier(resultat) / NOM_DOSSIER_FICHIERS / "model.json").read_bytes(),
            b'{"faux": true}',
        )

    def test_identifiants_ancienne_collision_et_variantes_independants(self) -> None:
        service = self.service()
        identifiants = ("a__b/c", "a/b__c")
        for identifiant in identifiants:
            resultat = self.resultat(
                id_resolu=identifiant,
                identifiant=identifiant,
                fichiers=(FichierVerifie("config.json", 2),),
            )
            self.verification.resultat = resultat
            self.telecharger(service, resultat)
        variante = self.resultat(
            fichiers=(FichierVerifie("modele-q8_0.gguf", 3),),
            gguf="modele-q8_0.gguf",
        )
        self.verification.resultat = variante
        self.client.contenus["modele-q8_0.gguf"] = b"ggg"
        self.telecharger(service, variante)

        cles = [modele.cle for modele in service.inventaire()]
        self.assertEqual(len(cles), 3)
        self.assertEqual(len(set(cles)), 3)
        self.assertIn(cle_stockage("a__b/c", COMMIT), cles)
        self.assertIn(cle_stockage("a/b__c", COMMIT), cles)

    def test_gguf_decoupe_refuse_avant_admission_et_sans_travail(self) -> None:
        nom = "modele-00001-of-00002.gguf"
        resultat = self.resultat(
            fichiers=(FichierVerifie(nom, 10),), gguf=nom
        )
        service = self.service(verification=FausseVerification(resultat))
        with self.assertRaises(ValeurRefusee):
            service.lancer_telechargement(empreinte_verification(resultat))
        self.assertEqual(self.client.appels, [])
        self.assertFalse(self.donnees.exists())


class EchecsEtInventaireTest(BaseGestionTest):
    def test_reponse_sans_fichier_ou_taille_incorrecte_non_pret(self) -> None:
        service = self.service(client=FauxClientTelechargement({}))
        self.telecharger(service, self.resultat())
        self.assertEqual(service.inventaire(), ())
        self.assertEqual(self.creneau.instantane().etat, ETAT_ECHOUEE)
        self.assertFalse(
            (self.dossier(self.resultat()) / NOM_MARQUEUR).exists()
        )

        self.creneau2 = CreneauOperations()
        self.addCleanup(self.creneau2.arreter, 0.1)
        self.creneau = self.creneau2
        service = self.service(client=FauxClientTelechargement(tronquer=True))
        self.telecharger(service, self.resultat())
        self.assertEqual(service.inventaire(), ())
        self.assertEqual(self.creneau.instantane().etat, ETAT_ECHOUEE)

    def test_ecriture_du_marqueur_en_echec_laisse_non_pret(self) -> None:
        service = self.service()
        with mock.patch(
            "transcription_bench.gestion_modeles.ecrire_json_atomique",
            side_effect=OSError("disque plein"),
        ):
            self.telecharger(service, self.resultat())
        self.assertEqual(service.inventaire(), ())
        self.assertEqual(self.creneau.instantane().etat, ETAT_ECHOUEE)

    def test_marqueur_absent_illisible_ou_incoherent_jamais_pret(self) -> None:
        resultat = self.resultat()
        service = self.service()
        self.telecharger(service, resultat)
        self.assertEqual(len(service.inventaire()), 1)
        marqueur = self.dossier(resultat) / NOM_MARQUEUR

        marqueur.unlink()
        self.assertEqual(self.service().inventaire(), ())

        marqueur.write_text("{pas du json", encoding="utf-8")
        self.assertEqual(self.service().inventaire(), ())

        manifeste = {
            "moteur": MOTEUR,
            "cle": cle_stockage("org/autre", COMMIT),
            "identifiant": "org/modele",
            "id_resolu": "org/autre",
            "commit": COMMIT,
            "famille": "whisper",
            "fichier_gguf": None,
            "fichiers": [{"nom": nom, "taille": len(octets)} for nom, octets in CONTENUS.items()],
            "date": "2026-10-25T00:00:00+00:00",
        }
        ecrire_json_atomique(marqueur, manifeste)
        # La clé du dossier ne correspond pas à l'identité du manifeste.
        self.assertEqual(self.service().inventaire(), ())

        manifeste["cle"] = self.dossier(resultat).name
        manifeste["id_resolu"] = "org/modele"
        manifeste["identifiant"] = "org/modele"
        ecrire_json_atomique(marqueur, manifeste)
        self.assertEqual(len(self.service().inventaire()), 1)

    def test_lien_sortant_refuse_avant_ecriture_et_avant_suppression(self) -> None:
        resultat = self.resultat()
        exterieur = Path(self.donnees.parent) / "exterieur"
        exterieur.mkdir()
        for nom in (NOM_DOSSIER_FICHIERS, ".cache"):
            with self.subTest(nom=nom):
                dossier = self.dossier(resultat)
                dossier.mkdir(parents=True, exist_ok=True)
                (dossier / nom).symlink_to(exterieur, target_is_directory=True)
                service = self.service()
                self.telecharger(service, resultat)
                self.assertEqual(self.client.appels, [])
                self.assertEqual(list(exterieur.iterdir()), [])
                self.assertEqual(service.inventaire(), ())
                self.assertEqual(self.creneau.instantane().etat, ETAT_ECHOUEE)
                shutil.rmtree(dossier, ignore_errors=True)
                shutil.rmtree(self.donnees / "models", ignore_errors=True)

        service = self.service()
        self.verification.resultat = resultat
        self.telecharger(service, resultat)
        dossier = self.dossier(resultat)
        lien = dossier / NOM_DOSSIER_FICHIERS / "lien-sortant"
        lien.symlink_to(exterieur, target_is_directory=True)
        with self.assertRaises(ValeurRefusee):
            service.supprimer(
                MOTEUR, cle_stockage(resultat.id_resolu, resultat.commit)
            )
        self.assertTrue((dossier / NOM_MARQUEUR).is_file())
        self.assertEqual(list(exterieur.iterdir()), [])

    def test_erreur_client_ne_divulgue_pas_de_secret(self) -> None:
        secret = "hf_FAKE_SECRET"
        service = self.service(
            client=FauxClientTelechargement(erreur=RuntimeError(secret))
        )
        self.telecharger(service, self.resultat())
        instantane = self.creneau.instantane()
        self.assertEqual(instantane.etat, ETAT_ECHOUEE)
        self.assertNotIn(secret, " ".join(instantane.journal))
        self.assertNotIn(secret, instantane.erreur or "")
        self.assertEqual(service.inventaire(), ())

    def test_erreur_client_categorisee_sans_secret(self) -> None:
        service = self.service(
            client=FauxClientTelechargement(
                erreur=ErreurClientTelechargement(RAISON_ACCES_REFUSE)
            )
        )
        self.telecharger(service, self.resultat())
        instantane = self.creneau.instantane()
        self.assertEqual(instantane.etat, ETAT_ECHOUEE)
        self.assertIn(RAISON_ACCES_REFUSE, " ".join(instantane.journal))
        self.assertNotIn("Traceback", " ".join(instantane.journal))


class SuppressionTest(BaseGestionTest):
    def _deux_modeles(self) -> tuple[GestionModeles, ResultatVerification, ResultatVerification]:
        service = self.service()
        premier = self.resultat()
        self.telecharger(service, premier)
        second = self.resultat(commit=AUTRE_COMMIT)
        self.verification.resultat = second
        self.telecharger(service, second)
        return service, premier, second

    def test_suppression_preserve_resultats_et_autre_modele(self) -> None:
        service, premier, second = self._deux_modeles()
        resultats = self.donnees / "results" / "20261025-000000-test"
        resultats.mkdir(parents=True)
        (resultats / "run.json").write_text('{"etat": "completed"}', encoding="utf-8")

        service.supprimer(
            MOTEUR,
            cle_stockage(second.id_resolu, second.commit, second.fichier_gguf),
        )

        self.assertFalse(self.dossier(second).exists())
        self.assertTrue((self.dossier(premier) / NOM_MARQUEUR).is_file())
        self.assertTrue((resultats / "run.json").is_file())
        self.assertEqual(
            [modele.commit for modele in service.inventaire()], [COMMIT]
        )

    def test_suppression_refusee_pendant_execution_fichiers_intacts_puis_autorisee(
        self,
    ) -> None:
        service, premier, second = self._deux_modeles()
        cle_premier = cle_stockage(
            premier.id_resolu, premier.commit, premier.fichier_gguf
        )
        cle_second = cle_stockage(second.id_resolu, second.commit, second.fichier_gguf)
        dossier_premier = self.dossier(premier)
        dossier_second = self.dossier(second)
        self.assertTrue((dossier_premier / NOM_MARQUEUR).is_file())
        self.assertTrue((dossier_second / NOM_MARQUEUR).is_file())
        avant = instantane_arbre(dossier_premier)

        resultats = self.donnees / "results" / "20261026-000000-test"
        resultats.mkdir(parents=True)
        run_json = resultats / "run.json"
        run_json.write_text('{"etat": "completed"}', encoding="utf-8")

        liberation = threading.Event()
        self.addCleanup(liberation.set)
        self.creneau.demarrer(
            TYPE_EXECUTION,
            lambda travailleur: liberation.wait(DELAI),
            cible="org/modele",
        )

        with self.assertRaises(CreneauOccupe) as contexte:
            service.supprimer(MOTEUR, cle_premier)
        self.assertEqual(contexte.exception.type_operation, TYPE_EXECUTION)
        self.assertEqual(instantane_arbre(dossier_premier), avant)
        self.assertTrue((dossier_premier / NOM_MARQUEUR).is_file())
        self.assertEqual(
            run_json.read_text(encoding="utf-8"), '{"etat": "completed"}'
        )
        instantane = self.creneau.instantane()
        self.assertEqual(instantane.etat, ETAT_EN_COURS)
        self.assertEqual(instantane.type_operation, TYPE_EXECUTION)

        liberation.set()
        self.attendre()
        service.supprimer(MOTEUR, cle_premier)
        self.assertFalse(dossier_premier.exists())
        self.assertTrue((dossier_second / NOM_MARQUEUR).is_file())
        self.assertEqual(
            run_json.read_text(encoding="utf-8"), '{"etat": "completed"}'
        )

        self.creneau.arreter(0.5)
        with self.assertRaises(ServiceArrete):
            service.supprimer(MOTEUR, cle_second)
        self.assertTrue((dossier_second / NOM_MARQUEUR).is_file())

    def test_cle_symlink_interne_refusee_sans_toucher_autre_modele(self) -> None:
        service = self.service()
        resultat_b = self.resultat()
        self.telecharger(service, resultat_b)
        cle_b = cle_stockage(
            resultat_b.id_resolu, resultat_b.commit, resultat_b.fichier_gguf
        )
        dossier_b = self.dossier(resultat_b)
        marqueur_avant = (dossier_b / NOM_MARQUEUR).read_bytes()
        poids_avant = (
            dossier_b / NOM_DOSSIER_FICHIERS / "model.bin"
        ).read_bytes()

        resultat_a = self.resultat(
            commit=AUTRE_COMMIT, id_resolu="org/autre", identifiant="org/autre"
        )
        cle_a = cle_stockage(
            resultat_a.id_resolu, resultat_a.commit, resultat_a.fichier_gguf
        )
        lien = self.donnees / "models" / MOTEUR / cle_a
        lien.symlink_to(dossier_b, target_is_directory=True)
        self.verification.resultat = resultat_a

        with self.assertRaises(ValeurRefusee):
            service.supprimer(MOTEUR, cle_a)
        self.assertTrue(lien.is_symlink())
        self.assertEqual((dossier_b / NOM_MARQUEUR).read_bytes(), marqueur_avant)

        appels_avant = len(self.client.appels)
        self.assertTrue(
            service.lancer_telechargement(empreinte_verification(resultat_a))
        )
        self.attendre()
        self.assertEqual(self.creneau.instantane().etat, ETAT_ECHOUEE)
        self.assertEqual(len(self.client.appels), appels_avant)
        self.assertEqual(
            (dossier_b / NOM_DOSSIER_FICHIERS / "model.bin").read_bytes(),
            poids_avant,
        )
        self.assertTrue((dossier_b / NOM_MARQUEUR).is_file())

    def test_suppression_attend_le_verrou_json_du_stockage(self) -> None:
        service = self.service()
        resultat = self.resultat()
        self.telecharger(service, resultat)
        cle = cle_stockage(
            resultat.id_resolu, resultat.commit, resultat.fichier_gguf
        )
        dossier = self.dossier(resultat)
        observe = _VerrouObserve(VERROU_STOCKAGE)
        erreurs: list[BaseException] = []

        def supprimer() -> None:
            try:
                service.supprimer(MOTEUR, cle)
            except BaseException as erreur:  # relevé pour l'assertion du test
                erreurs.append(erreur)

        thread = threading.Thread(target=supprimer)
        VERROU_STOCKAGE.acquire()
        try:
            with mock.patch(
                "transcription_bench.gestion_modeles.VERROU_STOCKAGE", observe
            ):
                thread.start()
                self.assertTrue(observe.avant.wait(DELAI))
                self.assertTrue(thread.is_alive())
                self.assertTrue(dossier.exists())
        finally:
            VERROU_STOCKAGE.release()
        thread.join(DELAI)
        self.assertFalse(thread.is_alive())
        self.assertEqual(erreurs, [])
        self.assertFalse(dossier.exists())

    def test_suppression_cle_invalide_ou_moteur_inconnu_refusee(self) -> None:
        service, premier, _second = self._deux_modeles()
        with self.assertRaises(ValeurRefusee):
            service.supprimer(MOTEUR, "../modele")
        with self.assertRaises(MoteurInconnu):
            service.supprimer(
                "moteur-absent",
                cle_stockage(premier.id_resolu, premier.commit),
            )
        self.assertTrue(self.dossier(premier).exists())
