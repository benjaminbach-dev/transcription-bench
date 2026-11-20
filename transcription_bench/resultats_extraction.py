"""Stockage des extractions : dossier, copies, résultats par source (tâche 3.4, D7).

Ce module ne lance aucun processus et n'interprète aucun événement : le service
d'exécution (`transcription_bench.execution_extraction`) lui remet les valeurs
déjà validées, au fil de l'exécution. Il réutilise le format, les mesures serveur
et l'écriture atomique de `transcription_bench.resultats`.

Arborescence écrite, sans base de données et hors Git (sous `data/`) :

    data/extractions/<AAAAMMJJ-HHMMSS>-<court-id>/
      run.json          suivi de l'extraction (mutable pendant, immuable ensuite)
      run.log           états, motifs et mesures seulement : ni texte source ni sortie du modèle
      grille.md         copie exacte de la grille validée
      schema.json       schéma de sortie généré (D2)
      consignes.json    message système exact et version des consignes (D3) ;
                        `version_format` ajouté au chargement, si le moteur le fournit
      <n>-<libellé>/    une par source, dans l'ordre de la demande :
        source.txt        copie du texte source, écrite dès l'admission
        sortie_brute.txt  sortie du modèle, si au moins un token a été généré
        extraction.json   valeur décodée, uniquement si la source est conforme
        result.json       publication de la source : écrit EN DERNIER

**Publication** : `result.json` est le marqueur de publication d'une source. Une
source sans `result.json` est non traitée, même si d'autres fichiers existent
(interruption entre deux écritures). Un `result.json` publié n'est jamais
réécrit : une seconde publication est refusée.

**Immuabilité** : `run.json` passe en état final une seule fois (`clore` ou
`abandon_extraction`). Toute modification ultérieure lève `ResultatImmuable`.
Chaque extraction reçoit un dossier neuf : aucune extraction précédente n'est
modifiée.

**Atomicité** : chaque JSON et chaque texte passe par `transcription_bench.stockage`
(fichier temporaire du même dossier, `fsync`, puis `os.replace`). Une erreur
d'écriture est retenue (`erreur`), l'extraction est close en échec, et l'état
final est malgré tout tenté.

**Mesures** : `None` signifie « mesure indisponible », jamais zéro. Le pic
mémoire d'une source vient de son propre événement ; le pic de l'exécution est le
dernier relevé transmis, marqué partiel tant que l'extraction n'est pas finie
normalement (événement `fin`).

**Secrets** : rien de l'environnement n'est recopié. Le journal ne reçoit que des
états, des motifs et des compteurs ; le texte source et la sortie du modèle ne
sont écrits que dans leurs fichiers dédiés.
"""

from __future__ import annotations

import math
import threading
import time
from collections.abc import Mapping
from pathlib import Path
from typing import IO, TYPE_CHECKING, Any

from engines.mesures_systeme import (
    MOMENT_AUDIO,
    MOMENT_CHARGEMENT,
    valider_observation_systeme,
)
from engines.protocole import (
    TYPE_CHARGEMENT,
    TYPE_EXTRACTION,
    TYPE_EXTRACTION_ERREUR,
    TYPE_FIN,
    valider_meta_moteur,
)
from transcription_bench.operations import ETAT_ECHOUEE as ETAT_EXECUTION_ECHOUEE
from transcription_bench.operations import horodatage_iso
from transcription_bench.paths import (
    NOM_DOSSIER_EXTRACTIONS,
    ValeurRefusee,
    resoudre_dans_racine,
)
from transcription_bench.resultats import (
    ETAT_ABANDONNEE,
    ETAT_ECHOUEE,
    ETAT_EN_COURS,
    ETAT_TERMINEE,
    NOM_FICHIER_EXECUTION,
    NOM_FICHIER_JOURNAL,
    ConsignationImpossible,
    MesuresExecution,
    ResultatImmuable,
    create_timestamped_dir,
    etat_resultat,
    metadonnees_machine,
    metadonnees_programme,
    nom_dossier_audio,
)
from transcription_bench.schema_grilles import schema_to_json
from transcription_bench.stockage import (
    JsonInvalide,
    ecrire_json_atomique,
    ecrire_texte_atomique,
    lire_json,
)

if TYPE_CHECKING:  # pragma: no cover - uniquement pour les annotations
    from transcription_bench.extractions import ExtractionRequest

#: Version du format des extractions, écrite dans `schema`. Même valeur initiale
#: que celle des transcriptions, mais versionnée séparément.
SCHEMA_EXTRACTION = 1
#: Valeur de `type` de `run.json` et de chaque `result.json` source.
RUN_TYPE_EXTRACTION = "extraction"
SOURCE_RESULT_TYPE = "source_extraction"
EXTRACTION_FILE_TYPE = "extraction_source"

FILE_GRID = "grille.md"
FILE_SCHEMA = "schema.json"
FILE_INSTRUCTIONS = "consignes.json"
FILE_SOURCE = "source.txt"
FILE_RAW_OUTPUT = "sortie_brute.txt"
FILE_EXTRACTION = "extraction.json"
FILE_SOURCE_RESULT = "result.json"

#: États d'une source. `non_traitee` est le seul état sans `result.json`.
SOURCE_COMPLIANT = "conforme"
SOURCE_NON_COMPLIANT = "non_conforme"
SOURCE_ERROR = "erreur"
SOURCE_NOT_PROCESSED = "non_traitee"
SOURCE_PUBLISHED_STATES = (SOURCE_COMPLIANT, SOURCE_NON_COMPLIANT, SOURCE_ERROR)
SOURCE_STATES = (*SOURCE_PUBLISHED_STATES, SOURCE_NOT_PROCESSED)

#: Mesures d'une source transmises par son événement `extraction` (D6).
SOURCE_MEASURE_FIELDS = (
    "tokens_entree",
    "tokens_sortie",
    "delai_premier_token_s",
    "duree_generation_s",
    "duree_extraction_s",
    "vitesse_generation_tps",
    "vitesse_lecture_estimee_tps",
    "temps_cpu_s",
    "pic_memoire_octets",
)


class ExtractionRecorder:
    """Consignation d'une extraction : `run.json`, `run.log`, copies, sources.

    Construit sans E/S ; `ouvrir` crée le dossier et tous les fichiers de
    l'admission (copies, `source.txt` de chaque source, `run.json` en cours). Les
    méthodes `enregistrer_*` ne lèvent pas pour une erreur d'E/S : la première est
    retenue dans `erreur`, les écritures suivantes sont ignorées et l'appelant
    close l'extraction en échec. `clore` rend `run.json` immuable.
    """

    def __init__(
        self,
        dossier_data: Path | str,
        demande: ExtractionRequest,
        moteur: Mapping[str, Any],
        *,
        debut: float,
        machine: Mapping[str, Any] | None = None,
        programme: Mapping[str, Any] | None = None,
        horloge: Any = horodatage_iso,
        base: str | None = None,
        court_id: str | None = None,
    ) -> None:
        self._donnees = Path(dossier_data)
        self._request = demande
        self._moteur = dict(moteur)
        self._factice = bool(self._moteur.get("factice"))
        self._machine = dict(machine) if machine is not None else metadonnees_machine()
        self._programme = (
            dict(programme) if programme is not None else metadonnees_programme()
        )
        self._horloge = horloge
        self._base = base
        self._short_id = court_id
        self._verrou = threading.RLock()
        self._erreur: str | None = None
        self._erreur_journal: str | None = None
        self._etat_final: str | None = None
        self._identifiant: str | None = None
        self._dossier: Path | None = None
        self._date: str | None = None
        self._journal: IO[str] | None = None
        self._peak_from_end = False
        #: Observation système du lot, relevée par l'événement `fin` (D3). Gardée
        #: ici : elle n'a pas de place dans `MesuresExecution`, partagée avec les
        #: transcriptions.
        self._lot_observation: dict[str, Any] | None = None
        #: Métadonnées du chargement, validées (`meta_moteur`) : `None` tant qu'il
        #: n'y en a pas, ce qui reste vrai pour le moteur factice.
        self._architecture: str | None = None
        self._sha256_gabarit: str | None = None
        self._version_format: int | None = None
        self._process: dict[str, Any] = {
            "pid": None,
            "heure_creation": None,
            "heure_creation_source": None,
            "lance_a": None,
            "code_sortie": None,
        }
        self._sources: list[dict[str, Any]] = [
            {
                "rang": source.rang,
                "nom": source.nom,
                "dossier": nom_dossier_audio(source.rang, source.nom),
                "etat": SOURCE_NOT_PROCESSED,
                "motif": None,
                "source": {
                    "execution": source.identifiant,
                    "ordre": source.ordre,
                    "audio": {
                        "nom": source.nom,
                        "empreinte_sha256": source.empreinte_audio,
                    },
                    "modele": source.modele,
                    "moteur": source.moteur,
                    "factice": source.factice,
                },
                "texte": {
                    "empreinte_sha256": source.empreinte_texte,
                    "caracteres": source.caracteres,
                },
                "mesures": None,
                "fin": None,
            }
            for source in demande.sources
        ]
        self._effective: dict[str, Any] = {
            "threads_appliques": None,
            "reglages_effectifs": {
                reglage.nom: reglage.valeur for reglage in demande.reglages
            },
            "mode_chargement_poids": None,
        }
        self.measures = MesuresExecution(debut=debut)

    # -- état observable -----------------------------------------------------

    @property
    def identifiant(self) -> str | None:
        """Identifiant du dossier d'extraction, ou `None` avant `ouvrir`."""
        return self._identifiant

    @property
    def dossier(self) -> Path | None:
        """Dossier de l'extraction créé, ou `None`."""
        return self._dossier

    @property
    def erreur(self) -> str | None:
        """Première erreur d'écriture rencontrée, ou `None`."""
        with self._verrou:
            return self._erreur

    @property
    def erreur_journal(self) -> str | None:
        """Première erreur d'écriture de `run.log`, distincte de `erreur`."""
        with self._verrou:
            return self._erreur_journal

    @property
    def etat_final(self) -> str | None:
        """État final écrit par `clore`, ou `None` tant que l'extraction dure."""
        with self._verrou:
            return self._etat_final

    def summary(self) -> dict[str, int]:
        """Compte des sources par état, pour le journal de l'opération."""
        compte = {etat: 0 for etat in SOURCE_STATES}
        for plan in self._sources:
            compte[plan["etat"]] += 1
        return {
            "sources_total": len(self._sources),
            "conformes": compte[SOURCE_COMPLIANT],
            "non_conformes": compte[SOURCE_NON_COMPLIANT],
            "erreurs": compte[SOURCE_ERROR],
            "non_traitees": compte[SOURCE_NOT_PROCESSED],
        }

    def resume_sources(self) -> tuple[dict[str, Any], ...]:
        """État et motif de chaque source, dans l'ordre de la demande (résumé de commande)."""
        with self._verrou:
            return tuple(
                {
                    "rang": plan["rang"],
                    "nom": plan["nom"],
                    "etat": plan["etat"],
                    "motif": plan["motif"],
                }
                for plan in self._sources
            )

    # -- cycle de vie --------------------------------------------------------

    def ouvrir(self) -> bool:
        """Admission : dossier, `run.json` en cours, puis fichiers et copies des sources.

        `run.json` est écrit juste après la création du dossier : une admission
        interrompue ne laisse jamais un dossier orphelin, sans état. Si une écriture
        échoue, l'extraction est close en échec avec le motif (`run.json` porte cet
        état). Renvoie `False` dans ce cas : l'appelant ne lance aucun moteur.
        """
        try:
            self._identifiant, dossier = create_timestamped_dir(
                self._donnees / NOM_DOSSIER_EXTRACTIONS,
                base=self._base,
                court_id=self._short_id,
            )
        except (ConsignationImpossible, ValeurRefusee) as erreur:
            self._set_error(str(erreur))
            return False
        self._dossier = dossier
        self._date = self._horloge()
        if self._write_run(etat=ETAT_EN_COURS):
            self._ecrire_admission(dossier)
        if self.erreur is not None:
            # Clôture en échec : l'état final est tenté même si l'écriture a échoué.
            self.clore(etat=ETAT_EXECUTION_ECHOUEE, erreur=None, code_sortie=None)
            return False
        return True

    def _ecrire_admission(self, dossier: Path) -> None:
        """Journal, grille, schéma, consignes puis copie de chaque source."""
        try:
            self._journal = (dossier / NOM_FICHIER_JOURNAL).open(
                "w", encoding="utf-8", newline="\n"
            )
            grille = self._request.grille
            ecrire_texte_atomique(dossier / FILE_GRID, grille.copie)
            ecrire_texte_atomique(
                dossier / FILE_SCHEMA, schema_to_json(dict(grille.schema)) + "\n"
            )
            self._ecrire_consignes(dossier)
            for plan, source in zip(self._sources, self._request.sources, strict=True):
                dossier_source = dossier / plan["dossier"]
                dossier_source.mkdir(parents=True, exist_ok=False)
                ecrire_texte_atomique(dossier_source / FILE_SOURCE, source.texte)
        except (OSError, ValueError) as erreur:
            self._set_error(
                f"écriture de l'admission de l'extraction impossible : {_message(erreur)}"
            )

    def _ecrire_consignes(self, dossier: Path, version_format: int | None = None) -> None:
        """`consignes.json` : message système et version des consignes, puis format.

        L'admission écrit les deux premières clés ; le chargement réécrit le fichier
        avec `version_format` quand le moteur le fournit (écriture atomique).
        """
        grille = self._request.grille
        contenu: dict[str, Any] = {
            "version_consignes": grille.version_consignes,
            "message_systeme": grille.message_systeme,
        }
        if version_format is not None:
            contenu["version_format"] = version_format
        ecrire_json_atomique(dossier / FILE_INSTRUCTIONS, contenu)

    def enregistrer_processus(
        self,
        *,
        pid: int,
        heure_creation: float | None,
        source: str,
        lance_a: str,
    ) -> bool:
        """Consigne le PID et l'heure de création du moteur dès son lancement.

        Même règle que pour une transcription : sans PID persisté, la récupération
        ne retrouve pas le processus. Renvoie `False` si l'écriture échoue.
        """
        self._refuse_if_finalized()
        if self.erreur is not None or self._dossier is None:
            return False
        self._process.update(
            {
                "pid": pid,
                "heure_creation": heure_creation,
                "heure_creation_source": source,
                "lance_a": lance_a,
            }
        )
        return self._write_run(etat=ETAT_EN_COURS)

    def record_event(self, evenement: Mapping[str, Any]) -> bool:
        """Consigne un événement accepté : chargement, source ou fin.

        Les événements sont ceux du protocole déjà filtrés par le service ; un type
        inattendu est refusé ici aussi, sans écriture.
        """
        type_evenement = evenement.get("type")
        if type_evenement == TYPE_CHARGEMENT:
            return self._record_loading(evenement)
        if type_evenement in (TYPE_EXTRACTION, TYPE_EXTRACTION_ERREUR):
            return self._record_source(evenement)
        if type_evenement == TYPE_FIN:
            return self._record_end(evenement)
        return False

    def ecrire_journal(self, ligne: str) -> None:
        """Ajoute une ligne à `run.log` : état, motif ou mesure, jamais de contenu.

        Appelée depuis le fil de lecture du moteur : ne lève jamais. La première
        erreur d'écriture est retenue dans `erreur_journal`.
        """
        with self._verrou:
            fichier = self._journal
            if fichier is None or self._etat_final is not None:
                return
            if self._erreur_journal is not None:
                return
            try:
                fichier.write(f"{ligne}\n")
                fichier.flush()
            except (OSError, ValueError) as erreur:
                self._erreur_journal = (
                    f"écriture du journal de l'extraction impossible : {_message(erreur)}"
                )

    def ecrire_notice(self, ligne: str) -> bool:
        """Ajoute une ligne de service à `run.log` après la fermeture du journal.

        Un constat fait après la fin du moteur (par exemple un dossier de travail
        non supprimé) survient après `fermer` : la ligne est ajoutée au fichier
        lui-même, tant que l'extraction n'est pas finalisée. Ne lève jamais ;
        renvoie `False`, sans effet, si la consignation n'a pas eu lieu, si
        l'extraction est déjà close ou si l'écriture échoue.
        """
        with self._verrou:
            if self._etat_final is not None or self._dossier is None:
                return False
            try:
                with (self._dossier / NOM_FICHIER_JOURNAL).open(
                    "a", encoding="utf-8", newline="\n"
                ) as fichier:
                    fichier.write(f"{ligne}\n")
            except (OSError, ValueError):
                return False
            return True

    def fermer(self) -> None:
        """Ferme `run.log` ; idempotent, ne lève pas."""
        with self._verrou:
            fichier, self._journal = self._journal, None
        if fichier is None:
            return
        try:
            fichier.close()
        except OSError:
            pass

    def clore(self, *, etat: str, erreur: str | None, code_sortie: int | None) -> bool:
        """Écrit l'état final de `run.json` ; le fichier devient immuable.

        `etat` est l'état interne du service (`terminee`, `interrompue`,
        `echouee`). L'état final est tenté même après une erreur d'écriture : il
        vaut alors `failed` avec le motif retenu. Une source déjà publiée n'est
        jamais rétrogradée ; une source sans publication reste `non_traitee`.
        """
        self._refuse_if_finalized()
        etat_persiste = etat_resultat(etat)
        if self.measures.duree_operation_s is None:
            # Issue imprévue avant la fin mesurée : la durée va jusqu'à la clôture.
            self.measures.duree_operation_s = time.perf_counter() - self.measures.debut
        self._process["code_sortie"] = code_sortie
        pic = self.measures.pic_memoire_octets
        self.measures.pic_memoire_partiel = (
            None if pic is None else etat_persiste != ETAT_TERMINEE or not self._peak_from_end
        )
        if self._erreur is None:
            etat_final, erreur_finale = etat_persiste, erreur
        else:
            etat_final, erreur_finale = ETAT_ECHOUEE, self._erreur
        self._etat_final = etat_final
        ecrit = self._write_run(
            etat=etat_final, erreur=erreur_finale, fin=self._horloge(), forcer=True
        )
        # Plus aucune ligne n'est attendue après l'état final : le journal se ferme.
        self.fermer()
        return ecrit

    # -- événements ----------------------------------------------------------

    def _record_loading(self, evenement: Mapping[str, Any]) -> bool:
        """Mesures du chargement, observation et métadonnées validées, puis `run.json`."""
        self._refuse_if_finalized()
        duree = evenement.get("duree_s")
        if self.measures.duree_chargement_s is None and _is_finite_number(duree):
            self.measures.duree_chargement_s = float(duree)
        self._retain_peak(evenement, de_fin=False)
        self.measures.observation_systeme_chargement = self._observation_of(
            evenement, MOMENT_CHARGEMENT
        )
        if self.erreur is not None or self._dossier is None:
            return False
        if not self._enregistrer_meta(evenement):
            return False
        return self._write_run(etat=ETAT_EN_COURS)

    def _enregistrer_meta(self, evenement: Mapping[str, Any]) -> bool:
        """Retient les métadonnées du chargement conformes et réécrit `consignes.json`.

        Sans `meta_moteur`, ou avec un objet non conforme (écarté, ligne de journal
        sans contenu), rien ne change : le run reste valide. Renvoie `False` seulement
        si la réécriture de `consignes.json` échoue.
        """
        if "meta_moteur" not in evenement:
            return True
        meta, motif = valider_meta_moteur(evenement["meta_moteur"])
        if meta is None:
            self.ecrire_journal(f"Métadonnées du chargement ignorées : {motif}.")
            return True
        self._effective["threads_appliques"] = meta["threads_appliques"]
        self._effective["mode_chargement_poids"] = meta["mode_chargement_poids"]
        self._effective["reglages_effectifs"].update(
            {"decodage": meta["decodage"], "graine": meta["graine"]}
        )
        self._architecture = meta["architecture"]
        self._sha256_gabarit = meta["sha256_gabarit_embarque"]
        self._version_format = meta["version_format"]
        try:
            self._ecrire_consignes(self._dossier, self._version_format)
        except (OSError, ValueError) as erreur:
            self._set_error(
                f"écriture des consignes de l'extraction impossible : {_message(erreur)}"
            )
            return False
        self.ecrire_journal("métadonnées du chargement enregistrées.")
        return True

    def _record_end(self, evenement: Mapping[str, Any]) -> bool:
        """Pic de fin et observation du lot ; l'état final reste à `clore`."""
        self._refuse_if_finalized()
        self._retain_peak(evenement, de_fin=True)
        self._lot_observation = self._observation_of(evenement, MOMENT_AUDIO)
        if self.erreur is not None or self._dossier is None:
            return False
        return self._write_run(etat=ETAT_EN_COURS)

    def _record_source(self, evenement: Mapping[str, Any]) -> bool:
        """Publie une source : sortie brute, valeur, puis `result.json` en dernier.

        Ordre fixe (D7) : `sortie_brute.txt` si au moins un token, `extraction.json`
        si la source est conforme, `result.json` ensuite. Une source déjà publiée
        n'est jamais réécrite.
        """
        self._refuse_if_finalized()
        rang = evenement.get("index", -1) + 1
        plan = self._source_plan(rang)
        if plan is None or plan["etat"] != SOURCE_NOT_PROCESSED:
            return False
        if self.erreur is not None or self._dossier is None:
            return False
        dossier_source = resoudre_dans_racine(self._dossier, plan["dossier"])
        if (dossier_source / FILE_SOURCE_RESULT).exists():
            self._set_error(f"résultat de la source {rang} déjà publié")
            return False
        sortie: str | None = None
        valeur_conforme: Mapping[str, Any] | None = None
        try:
            if evenement["type"] == TYPE_EXTRACTION:
                etat = SOURCE_COMPLIANT if evenement["conforme"] else SOURCE_NON_COMPLIANT
                motif = evenement["motif"]
                measures = _source_measures(evenement)
                comptes = evenement.get("comptes_natifs")
                if comptes is not None:
                    # Sous leur nom, à part des mesures D6 (design D6).
                    measures["comptes_natifs"] = dict(comptes)
                fin = evenement["fin"]
                if evenement["sortie_brute"] is not None:
                    ecrire_texte_atomique(
                        dossier_source / FILE_RAW_OUTPUT, evenement["sortie_brute"]
                    )
                    sortie = FILE_RAW_OUTPUT
                if evenement["conforme"]:
                    valeur_conforme = evenement["valeur"]
                    ecrire_json_atomique(
                        dossier_source / FILE_EXTRACTION,
                        {
                            "schema": SCHEMA_EXTRACTION,
                            "type": EXTRACTION_FILE_TYPE,
                            "rang": rang,
                            "valeur": valeur_conforme,
                        },
                    )
            else:
                etat = SOURCE_ERROR
                motif = evenement["motif"]
                measures = _source_measures(None)
                fin = None
            ecrire_json_atomique(
                dossier_source / FILE_SOURCE_RESULT,
                {
                    "schema": SCHEMA_EXTRACTION,
                    "type": SOURCE_RESULT_TYPE,
                    "identifiant": self._identifiant,
                    "rang": rang,
                    "nom": plan["nom"],
                    "dossier": plan["dossier"],
                    "etat": etat,
                    "motif": motif,
                    "ecrit_le": self._horloge(),
                    "factice": evenement["factice"],
                    "mesures_simulees": evenement["mesures_simulees"],
                    "source": plan["source"],
                    "texte": plan["texte"],
                    "sortie_brute": sortie,
                    "fin": fin,
                    "mesures": measures,
                },
            )
        except (OSError, ValueError) as erreur:
            self._set_error(
                f"écriture du résultat de la source {rang} impossible : {_message(erreur)}"
            )
            return False
        plan.update({"etat": etat, "motif": motif, "mesures": measures, "fin": fin})
        self._retain_peak(evenement, de_fin=False)
        if evenement.get("comptes_natifs") is not None:
            self.ecrire_journal(f"compteurs natifs source {rang} enregistrés.")
        return self._write_run(etat=ETAT_EN_COURS)

    def _observation_of(self, evenement: Mapping[str, Any], moment: str) -> dict[str, Any] | None:
        """Observation système validée et de provenance cohérente, ou `None`."""
        if "observation_systeme" not in evenement:
            return None
        if evenement.get("mesures_simulees") is not self._factice:
            self.ecrire_journal(
                f"Relevé système ignoré ({moment}) : provenance contradictoire "
                "avec l'extraction."
            )
            return None
        objet, motif = valider_observation_systeme(
            evenement["observation_systeme"],
            moment=moment,
            mesures_simulees=self._factice,
        )
        if objet is None:
            self.ecrire_journal(f"Relevé système ignoré ({moment}) : {motif}")
        return objet

    def _retain_peak(self, evenement: Mapping[str, Any], *, de_fin: bool) -> None:
        """Dernier pic mémoire cumulatif transmis ; partiel tant que ce n'est pas `fin`."""
        pic = evenement.get("pic_memoire_octets")
        if isinstance(pic, int) and not isinstance(pic, bool):
            self.measures.pic_memoire_octets = pic
            self._peak_from_end = de_fin

    # -- écriture ------------------------------------------------------------

    def _write_run(
        self,
        *,
        etat: str,
        erreur: str | None = None,
        fin: str | None = None,
        forcer: bool = False,
    ) -> bool:
        """Écrit `run.json` de façon atomique ; `forcer` pour l'état final seulement."""
        dossier = self._dossier
        if dossier is None:
            return False
        if self.erreur is not None and not forcer:
            return False
        demande = self._request
        grille = demande.grille
        contenu = {
            "schema": SCHEMA_EXTRACTION,
            "type": RUN_TYPE_EXTRACTION,
            "identifiant": self._identifiant,
            "etat": etat,
            "cree_le": self._date,
            "fin": fin,
            "erreur": erreur,
            "factice": self._factice,
            "synthetique": demande.synthetique,
            "mesures_simulees": self._factice,
            "grille": {
                "nom": grille.nom,
                "sha256": grille.sha256,
                "titre": grille.titre,
                "fichier": FILE_GRID,
            },
            "schema_sortie": {"fichier": FILE_SCHEMA},
            "consignes": {
                "version_consignes": grille.version_consignes,
                "version_format": self._version_format,
                "fichier": FILE_INSTRUCTIONS,
            },
            "modele": {
                "identifiant": demande.modele.identifiant,
                "id_resolu": demande.modele.id_resolu,
                "commit": demande.modele.commit,
                "cle": demande.modele.cle,
                "famille": demande.modele.famille,
                "fichier_gguf": demande.modele.fichier_gguf,
                # Lues au chargement (`meta_moteur`), jamais inventées : None sans elles.
                "architecture": self._architecture,
                "sha256_gabarit_embarque": self._sha256_gabarit,
            },
            "moteur": dict(self._moteur),
            "machine": dict(self._machine),
            "programme": dict(self._programme),
            "demande": {
                "moteur": demande.moteur,
                "famille": demande.modele.famille,
                "threads_demandes": demande.threads,
                "reglages": {reglage.nom: reglage.valeur for reglage in demande.reglages},
                "sources": [source.reference for source in demande.sources],
            },
            "effectifs": dict(self._effective),
            "processus_moteur": dict(self._process),
            "mesures": {
                "duree_chargement_s": self.measures.duree_chargement_s,
                "duree_processus_s": self.measures.duree_processus_s,
                "duree_operation_s": self.measures.duree_operation_s,
                "pic_memoire_octets": self.measures.pic_memoire_octets,
                "pic_memoire_partiel": self.measures.pic_memoire_partiel,
                "observation_systeme_chargement": (
                    self.measures.observation_systeme_chargement
                ),
                "observation_systeme_lot": self._lot_observation,
            },
            "progression": {
                "sources_traitees": sum(
                    1 for plan in self._sources if plan["etat"] != SOURCE_NOT_PROCESSED
                ),
                "sources_total": len(self._sources),
            },
            "sources": [dict(plan) for plan in self._sources],
        }
        try:
            ecrire_json_atomique(dossier / NOM_FICHIER_EXECUTION, contenu)
        except (OSError, ValueError) as erreur:
            self._set_error(
                f"écriture de l'état de l'extraction impossible : {_message(erreur)}"
            )
            return False
        return True

    # -- helpers -------------------------------------------------------------

    def _source_plan(self, rang: int) -> dict[str, Any] | None:
        """Plan de consignation d'une source, par son rang (1-based)."""
        if not 1 <= rang <= len(self._sources):
            return None
        return self._sources[rang - 1]

    def _set_error(self, message: str) -> None:
        """Retient la première erreur d'écriture rencontrée."""
        with self._verrou:
            if self._erreur is None:
                self._erreur = message

    def _refuse_if_finalized(self) -> None:
        """Refuse toute modification d'une extraction déjà finalisée."""
        if self._etat_final is not None:
            raise ResultatImmuable(
                f"extraction déjà finalisée ({self._etat_final}) : "
                f"{self._identifiant or 'identifiant inconnu'} n'est plus modifiable"
            )


def validate_running_extraction(contenu: Mapping[str, Any]) -> str | None:
    """Motif d'incohérence d'un `run.json` d'extraction en cours, ou `None`.

    Vérifie ce que la récupération interprète : le type, le schéma et les plans
    de sources. Le processus consigné est contrôlé par la récupération elle-même.
    Un contenu qui n'a jamais été interprété n'est pas réécrit.
    """
    if contenu.get("type") != RUN_TYPE_EXTRACTION:
        return "type d'exécution attendu : extraction"
    schema = contenu.get("schema")
    if type(schema) is not int or schema != SCHEMA_EXTRACTION:
        return f"schéma d'extraction non pris en charge ({schema!r})"
    sources = contenu.get("sources")
    if not isinstance(sources, list):
        return "clé 'sources' absente ou invalide"
    for plan in sources:
        if not isinstance(plan, Mapping):
            return "plan de source invalide"
        dossier = plan.get("dossier")
        if not isinstance(dossier, str) or not dossier:
            return "plan de source sans dossier"
        if plan.get("etat") not in SOURCE_STATES:
            return "plan de source à l'état inconnu"
    return None


def abandon_extraction(
    dossier: Path | str,
    contenu: Mapping[str, Any],
    *,
    fin: str | None = None,
    horloge: Any = horodatage_iso,
) -> dict[str, Any]:
    """Finalise en `abandoned` une extraction restée en cours, sans reprise.

    Appelée par la récupération du démarrage, avec le contenu de `run.json` déjà
    lu et validé. Règles de `resultats.abandonner_execution` : les durées totale
    et du processus deviennent inconnues, le dernier pic est conservé et marqué
    partiel, et aucune inférence n'est reprise. Une source déjà publiée n'est
    jamais rétrogradée ; une source dont le `result.json` existe, même si
    `run.json` ne le reflète pas encore, prend l'état de ce fichier ; les autres
    restent `non_traitee`. Aucun résultat existant n'est réécrit.
    """
    if contenu.get("etat") != ETAT_EN_COURS:
        raise ValueError(
            f"clôture en abandonné refusée : état {contenu.get('etat')!r} au lieu de "
            f"{ETAT_EN_COURS!r}"
        )
    dossier_extraction = Path(dossier)
    final = dict(contenu)
    final["etat"] = ETAT_ABANDONNEE
    final["fin"] = horloge() if fin is None else fin
    measures = dict(_mapping(contenu.get("mesures")))
    measures["duree_operation_s"] = None
    measures["duree_processus_s"] = None
    pic = measures.get("pic_memoire_octets")
    measures["pic_memoire_partiel"] = None if pic is None else True
    final["mesures"] = measures
    sources = [
        _abandon_plan(dossier_extraction, plan) for plan in contenu.get("sources") or ()
    ]
    final["sources"] = sources
    final["progression"] = {
        "sources_traitees": sum(1 for plan in sources if plan["etat"] != SOURCE_NOT_PROCESSED),
        "sources_total": len(sources),
    }
    ecrire_json_atomique(dossier_extraction / NOM_FICHIER_EXECUTION, final)
    return final


def abandon_extraction_inachevee(
    dossier: Path | str, *, horloge: Any = horodatage_iso
) -> dict[str, Any]:
    """Clôture en `abandoned` un dossier d'extraction resté sans `run.json`.

    Cas défensif de la récupération : les copies `source.txt` sont écrites dès
    l'admission, après `run.json`, donc un dossier avec des copies mais sans
    état ne devrait plus exister. Il est clôturé plutôt que purgé : il contient
    des textes sources, qui restent en place et seuls. Le `run.json` écrit est
    minimal — état final, identifiant, sources inconnues, sans mesures — mais
    il donne au dossier un état lisible au lieu d'un dossier ignoré.
    """
    return abandon_extraction(
        dossier,
        {
            "schema": SCHEMA_EXTRACTION,
            "type": RUN_TYPE_EXTRACTION,
            "identifiant": Path(dossier).name,
            "etat": ETAT_EN_COURS,
            "mesures": {
                "duree_chargement_s": None,
                "duree_processus_s": None,
                "duree_operation_s": None,
                "pic_memoire_octets": None,
                "pic_memoire_partiel": None,
                "observation_systeme_chargement": None,
                "observation_systeme_lot": None,
            },
            "sources": [],
        },
        horloge=horloge,
    )


def _abandon_plan(dossier: Path, plan: Mapping[str, Any]) -> dict[str, Any]:
    """Plan de source finalisé : état publié conservé, sinon relu, sinon non traité."""
    final = dict(plan)
    if final.get("etat") in SOURCE_PUBLISHED_STATES:
        return final
    publie = _published_state(dossier, final.get("dossier"))
    if publie is None:
        final.update({"etat": SOURCE_NOT_PROCESSED, "motif": None})
        return final
    final.update(publie)
    return final


def _published_state(dossier: Path, nom_dossier: Any) -> dict[str, Any] | None:
    """État, motif, mesures et fin d'un `result.json` publié, ou `None`.

    Le dossier de la source puis le fichier sont résolus confinés (même règle
    que la sélection des sources d'extraction) : un `result.json` qui
    sortirait par un lien symbolique n'est jamais lu, la source reste non
    traitée.
    """
    if not isinstance(nom_dossier, str) or not nom_dossier:
        return None
    try:
        dossier_source = resoudre_dans_racine(dossier, nom_dossier)
        chemin = resoudre_dans_racine(dossier_source, FILE_SOURCE_RESULT)
        contenu = lire_json(chemin)
    except (ValeurRefusee, JsonInvalide, OSError):
        return None
    if not isinstance(contenu, Mapping):
        return None
    if contenu.get("schema") != SCHEMA_EXTRACTION:
        return None
    if contenu.get("etat") not in SOURCE_PUBLISHED_STATES:
        return None
    return {
        "etat": contenu["etat"],
        "motif": contenu.get("motif"),
        "mesures": contenu.get("mesures"),
        "fin": contenu.get("fin"),
    }


def _source_measures(evenement: Mapping[str, Any] | None) -> dict[str, Any]:
    """Mesures d'une source ; chacune absente d'un événement vaut `None`, jamais zéro."""
    if evenement is None:
        return {champ: None for champ in SOURCE_MEASURE_FIELDS}
    return {champ: evenement.get(champ) for champ in SOURCE_MEASURE_FIELDS}


def _mapping(valeur: Any) -> Mapping[str, Any]:
    """Sous-objet d'un fichier JSON, vide s'il n'est pas un objet."""
    return valeur if isinstance(valeur, Mapping) else {}


def _is_finite_number(valeur: Any) -> bool:
    """Vrai pour un nombre fini, booléen exclu : une mesure absurde n'est pas retenue."""
    if not isinstance(valeur, (int, float)) or isinstance(valeur, bool):
        return False
    try:
        return math.isfinite(valeur)
    except OverflowError:
        return False


def _message(erreur: BaseException) -> str:
    """Texte court d'une erreur, sans message vide."""
    texte = str(erreur).strip()
    return texte if texte else type(erreur).__name__
