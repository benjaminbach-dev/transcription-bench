"""Runner du processus moteur d'extraction : job, chargement unique, sources, mesures.

Le serveur lance ce script dans l'environnement du moteur d'extraction (design D5) :

    python engines/runner_extraction.py job.json

Le runner lit le job, résout le moteur et la famille dans le registre, charge le
modèle une seule fois avec le schéma de sortie, traite les sources une par une et
émet des événements préfixés sur stdout (`engines.protocole`). Il n'écrit aucun
résultat : le service (tâche 3.4) écrit `run.json`, `result.json` et les copies
des sources. Sur stderr, il n'écrit que des étapes, des états, des motifs et des
compteurs : jamais le texte source ni la sortie du modèle.

Job (JSON UTF-8) :

    {
      "version": 1,
      "tache": "extraction",
      "moteur": "llama-cpp",
      "famille": "llm-gguf",
      "modele": {"identifiant": "org/nom", "revision": "abc", "chemin": "..."},
      "threads_demandes": 8,
      "reglages": {"contexte": 16384, "sortie_max": 4096},
      "schema": {"type": "object", "properties": {...}, "required": [...]},
      "message_systeme": "...",
      "sources": [{"texte": "...", "ordre": 0, "nom": "consultation.wav"}]
    }

Les sources sont traitées dans l'ordre de la liste (`index` dans les événements).
`ordre` est la position de la source dans son exécution de transcription (D8) et
`nom` son libellé. `texte` est la transcription source : elle ne vit que dans le
fichier de travail nettoyé par le service (D7). Le message utilisateur est
construit par `transcription_bench.consignes_grilles.user_message` ; le schéma
et la validation de sortie viennent de `transcription_bench.schema_grilles`.
Ces modules purs n'importent que la bibliothèque standard ; seuls les paquets
serveur (Flask, Jinja, Werkzeug, Waitress) restent interdits ici.

Contrat d'adaptateur (volontairement minimal, aucun framework) :

    charger(modele, threads_demandes, reglages, schema) -> objet opaque
        Charge le modèle et compile la contrainte de sortie issue de `schema`.
        Une erreur ici (grammaire refusée comprise) met l'exécution entière en
        échec, sans aucune génération.
    reinitialiser(moteur) -> None
        Vide le contexte (cache KV) et réinitialise l'échantillonneur. Le runner
        l'appelle avant **chaque** `extraire` : la lecture d'une source ne bénéficie
        jamais du cache de la précédente (D4).
    extraire(moteur, messages, reglages) -> dict
        `messages` : liste de `{"role": "system" | "user", "content": texte}`.
        Rend exactement les clés suivantes :
          `sortie_brute` (texte détokenisé, `""` si aucun token généré),
          `tokens_entree` (tokens du prompt soumis, tokens spéciaux compris),
          `tokens_sortie` (tokens générés, token de fin exclu),
          `fin` (`"arret"` sur token de fin, `"limite"` si `sortie_max` atteint),
          `delai_premier_token_s` (début de la génération jusqu'au premier token,
          lecture du prompt comprise, ou `None`),
          `duree_generation_s` (du premier au dernier token, ou `None`),
          `temps_cpu_s` (ou `None`).
        Si `tokens_entree` plus `sortie_max` dépasse `contexte`, lève
        `ErreurContexteInsuffisant` **avant** toute génération : aucune troncature.
        Une clé inconnue ou manquante est refusée par le runner.

Mesures par source (D6) : `duree_extraction_s` est mesurée par le runner, de
l'appel à `extraire` jusqu'à la validation (génération, détokenisation et
validation comprises ; la réinitialisation est exclue). `vitesse_generation_tps`
= (tokens_sortie − 1) / `duree_generation_s`, absente sous deux tokens.
`vitesse_lecture_estimee_tps` = `tokens_entree` / `delai_premier_token_s` : c'est
une estimation, son étiquette relève de l'affichage. Aucune valeur n'est inventée :
une mesure illisible est `None`.

Validation de sortie : `fin` valant `"limite"` rend la source non conforme sans
décodage. Sinon la sortie est décodée (clés dupliquées refusées) puis validée
contre `schema`. Une source conforme porte sa valeur décodée ; sinon le motif
est un libellé fixe, sans contenu du modèle (la clé inconnue n'est pas recopiée).

Événements : `chargement` (avec son `observation_systeme` facultatif), un
`extraction` par source extraite (conforme ou non), un `extraction_erreur` par
source en erreur (contexte insuffisant, erreur de l'adaptateur, résultat
d'adaptateur invalide), puis `fin` avec le compte des `extraction` dans
`audios_ok` et des `extraction_erreur` dans `audios_erreur` (noms du protocole
réutilisé, sources ici), l'observation système de la fenêtre du lot étant
portée par `observation_systeme`. Une source sans événement n'a pas été traitée.

Codes de sortie : 0 exécution terminée (même avec des sources non conformes ou en
erreur), 2 job invalide, 3 moteur refusé ou chargement impossible. Un échec de
chargement n'émet aucun événement : il est signalé sur stderr, comme dans le
runner de transcription, dont le protocole n'a pas de champ d'échec pour `fin`.

Ce runner n'installe aucun gestionnaire de signal, comme le runner de
transcription : l'arrêt, le marquage de la source en cours et l'état
d'interruption relèvent du service (tâche 3.4).

Les helpers privés `_texte`, `_modele`, `_entier_positif`, `_configurer_stdout` et
`_observation_systeme_emise` sont réutilisés depuis `engines.runner`, sans
modification de ce dernier.
"""

from __future__ import annotations

import json
import math
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType, ModuleType
from typing import Any

if __name__ == "__main__" and not __package__:
    # `python engines/runner_extraction.py` : la racine du dépôt est calculée
    # depuis `__file__`, jamais depuis le job ni `PYTHONPATH`.
    _RACINE_PROJET = Path(__file__).resolve().parent.parent
    if str(_RACINE_PROJET) not in sys.path:
        sys.path.insert(0, str(_RACINE_PROJET))

from engines.declarations import (
    TASK_EXTRACTION,
    DeclarationAdaptateur,
    motif_famille_non_executable,
)
from engines.hors_ligne import mode_hors_ligne, options_modele
from engines.mesures_systeme import (
    MOMENT_AUDIO,
    MOMENT_CHARGEMENT,
    ReleveurSysteme,
    creer_releveur_systeme,
)
from engines.protocole import (
    FINS_GENERATION,
    LONGUEUR_MAX_MOTIF,
    TYPE_CHARGEMENT,
    TYPE_EXTRACTION,
    TYPE_EXTRACTION_ERREUR,
    TYPE_FIN,
    emettre,
)
from engines.registre import (
    AdaptateurIndisponible,
    MoteurInconnu,
    RegistreMoteurs,
    creer_registre_fourni,
)
from engines.runner import (
    DUREE_CHARGEMENT_SIMULEE_S,
    PIC_MEMOIRE_SIMULE_OCTETS,
    VERSION_JOB,
    ErreurJob,
    ErreurMoteur,
    _configurer_stdout,
    _entier_positif,
    _modele,
    _observation_systeme_emise,
    _texte,
    pic_memoire,
)
from transcription_bench.consignes_grilles import user_message
from transcription_bench.schema_grilles import (
    DECODE_DUPLICATE_KEY,
    REASON_EMPTY_LIST,
    REASON_MISSING_KEY,
    REASON_NULL_NOT_ALLOWED,
    REASON_UNKNOWN_KEY,
    REASON_WRONG_TYPE,
    DecodeResult,
    SchemaIssue,
    decode_output,
    validate_output,
)

#: Durée d'extraction simulée du moteur factice : constante, sans valeur de PC.
DUREE_EXTRACTION_SIMULEE_S = 2.0
#: Clés exactes du résultat rendu par `extraire` (contrat ci-dessus).
CLES_RESULTAT_EXTRACTION = (
    "sortie_brute",
    "tokens_entree",
    "tokens_sortie",
    "fin",
    "delai_premier_token_s",
    "duree_generation_s",
    "temps_cpu_s",
)
MOTIF_LIMITE = "limite de sortie atteinte"
MOTIF_DECODAGE_DUPLIQUE = "clé JSON dupliquée"
MOTIF_ERREUR_INATTENDUE = "sortie non conforme"
#: Libellés fixes des motifs de conformité : ils ne recopient jamais une clé
#: produite par le modèle, seule source de contenu libre d'un motif.
MOTIFS_CONFORMITE = {
    REASON_MISSING_KEY: "clé de la grille absente",
    REASON_UNKNOWN_KEY: "clé inconnue de la grille",
    REASON_WRONG_TYPE: "type de valeur non conforme",
    REASON_NULL_NOT_ALLOWED: "null non admis à cet endroit",
    REASON_EMPTY_LIST: "liste vide non admise",
}


class ErreurSource(RuntimeError):
    """Résultat d'adaptateur inexploitable : source en erreur, lot poursuivi."""


class ErreurContexteInsuffisant(RuntimeError):
    """Prompt plus sortie maximale au-delà du contexte : refus sans génération (D4).

    Levée par `extraire` de l'adaptateur, qui seul tokenise le prompt. Le runner la
    traduit en `extraction_erreur` avec les nombres ci-dessous dans le motif.
    """

    def __init__(self, tokens_entree: int, sortie_max: int, contexte: int) -> None:
        self.tokens_entree = tokens_entree
        self.sortie_max = sortie_max
        self.contexte = contexte
        super().__init__(
            "contexte insuffisant : "
            f"{tokens_entree + sortie_max} tokens requis "
            f"({tokens_entree} de prompt + {sortie_max} de sortie) "
            f"pour un contexte de {contexte}"
        )


@dataclass(frozen=True)
class SourceJob:
    """Source à extraire ; son texte est exclu de `repr` et jamais journalisé."""

    texte: str = field(repr=False)
    ordre: int
    nom: str


@dataclass(frozen=True)
class JobExtraction:
    """Requête d'extraction lue depuis `job.json`."""

    moteur: str
    famille: str
    modele: dict[str, Any]
    threads_demandes: int
    reglages: dict[str, Any]
    schema: dict[str, Any] = field(repr=False)
    message_systeme: str = field(repr=False)
    sources: tuple[SourceJob, ...] = field(repr=False)


def charger_job_extraction(chemin: str | Path) -> JobExtraction:
    """Lit et valide un job d'extraction ; chemins résolus depuis son dossier."""
    chemin_job = Path(chemin).resolve()
    try:
        contenu = json.loads(chemin_job.read_text(encoding="utf-8"))
    except OSError as exception:
        raise ErreurJob(f"job illisible ({chemin_job}) : {exception}") from exception
    except json.JSONDecodeError as exception:
        raise ErreurJob(
            f"job JSON invalide ({chemin_job}) : {exception}"
        ) from exception
    if not isinstance(contenu, dict):
        raise ErreurJob("le job doit être un objet JSON")
    if contenu.get("version") != VERSION_JOB:
        raise ErreurJob(f"version de job attendue : {VERSION_JOB}")
    if contenu.get("tache") != TASK_EXTRACTION:
        raise ErreurJob(f"tâche de job attendue : {TASK_EXTRACTION!r}")
    base = chemin_job.parent
    reglages = contenu.get("reglages", {})
    if not isinstance(reglages, dict):
        raise ErreurJob("'reglages' doit être un objet JSON")
    return JobExtraction(
        moteur=_texte(contenu, "moteur"),
        famille=_texte(contenu, "famille"),
        modele=_modele(contenu.get("modele"), base),
        threads_demandes=_entier_positif(contenu, "threads_demandes"),
        reglages=dict(reglages),
        schema=_schema(contenu.get("schema")),
        message_systeme=_texte(contenu, "message_systeme"),
        sources=_sources(contenu.get("sources")),
    )


def executer(
    job: JobExtraction,
    registre: RegistreMoteurs | None = None,
) -> None:
    """Exécute un job d'extraction et émet ses événements sur stdout.

    Lève `ErreurMoteur` avant tout événement si le moteur, la famille ou
    l'adaptateur ne convient pas, ou si le chargement échoue (grammaire comprise).
    Une source en erreur est émise en `extraction_erreur` et le lot continue.
    """
    registre = creer_registre_fourni() if registre is None else registre
    with mode_hors_ligne():
        _executer_job(job, registre)


def _executer_job(job: JobExtraction, registre: RegistreMoteurs) -> None:
    """Corps de l'exécution, sous le mode hors ligne forcé par `executer`."""
    adaptateur, declaration = _charger_adaptateur(job, registre)
    factice = declaration.factice
    provenance = {"factice": factice, "mesures_simulees": factice}
    # Relevé réel, ou scénario simulé déterministe du moteur factice.
    releveur = creer_releveur_systeme(factice=factice)
    reglages = MappingProxyType(job.reglages)

    _journaliser(f"chargement du modèle ({len(job.sources)} source(s))")
    debut_chargement = time.perf_counter()
    try:
        moteur = adaptateur.charger(
            options_modele(job.modele),
            job.threads_demandes,
            reglages,
            job.schema,
        )
    except Exception as exception:  # l'erreur exacte du moteur reste visible
        raise ErreurMoteur(
            f"chargement du modèle impossible : {exception}"
        ) from exception
    duree_chargement = time.perf_counter() - debut_chargement
    pic_chargement = pic_memoire()
    if factice:
        duree_chargement = DUREE_CHARGEMENT_SIMULEE_S
        pic_chargement = PIC_MEMOIRE_SIMULE_OCTETS
    evenement_chargement: dict[str, Any] = {
        "type": TYPE_CHARGEMENT,
        "duree_s": duree_chargement,
        "pic_memoire_octets": pic_chargement,
        **provenance,
    }
    observation_chargement = _observation_chargement(releveur, factice)
    if observation_chargement is not None:
        evenement_chargement["observation_systeme"] = observation_chargement
    emettre(evenement_chargement)

    # Fenêtre CPU du lot : amorcée après le chargement, lue après la dernière source.
    amorcage = releveur.amorcer_cpu()
    nb_extractions = 0
    nb_erreurs = 0
    total = len(job.sources)
    for index, source in enumerate(job.sources):
        evenement = _traiter_source(
            index,
            source,
            adaptateur,
            moteur,
            reglages,
            job,
            provenance,
            factice,
        )
        if evenement["type"] == TYPE_EXTRACTION:
            nb_extractions += 1
        else:
            nb_erreurs += 1
        _journaliser(_resume_source(index, total, evenement))
        emettre(evenement)

    evenement_fin: dict[str, Any] = {
        "type": TYPE_FIN,
        "duree_chargement_s": duree_chargement,
        "pic_memoire_octets": PIC_MEMOIRE_SIMULE_OCTETS if factice else pic_memoire(),
        "audios_ok": nb_extractions,
        "audios_erreur": nb_erreurs,
        **provenance,
    }
    observation_lot = _observation_lot(releveur, amorcage, factice)
    if observation_lot is not None:
        evenement_fin["observation_systeme"] = observation_lot
    emettre(evenement_fin)
    _journaliser(f"terminé : {nb_extractions} extraite(s), {nb_erreurs} en erreur")


def _traiter_source(
    index: int,
    source: SourceJob,
    adaptateur: ModuleType,
    moteur: Any,
    reglages: Any,
    job: JobExtraction,
    provenance: dict[str, bool],
    factice: bool,
) -> dict[str, Any]:
    """Extrait une source et rend son événement : `extraction` ou `extraction_erreur`.

    La réinitialisation précède chaque génération. Une exception de l'adaptateur,
    un refus de contexte ou un résultat invalide ne lève jamais hors de la
    fonction : la source devient une erreur, avec un motif borné qui ne recopie
    ni le texte source ni la sortie du modèle.
    """
    messages = [
        {"role": "system", "content": job.message_systeme},
        {"role": "user", "content": user_message(source.texte)},
    ]
    try:
        adaptateur.reinitialiser(moteur)
        debut = time.perf_counter()
        brut = adaptateur.extraire(moteur, messages, reglages)
        resultat = _valider_resultat_extraction(brut)
        conforme, motif, valeur = _verdict(resultat, job.schema)
        duree_extraction = time.perf_counter() - debut
    except (ErreurContexteInsuffisant, ErreurSource) as exception:
        return _evenement_erreur(index, source, str(exception), provenance)
    except Exception as exception:
        # Seul le type d'exception est recopié : son message peut contenir un
        # fragment d'entrée, que le journal et les événements ne doivent pas garder.
        return _evenement_erreur(
            index,
            source,
            f"erreur du moteur ({type(exception).__name__})",
            provenance,
        )
    tokens_sortie = resultat["tokens_sortie"]
    return {
        "type": TYPE_EXTRACTION,
        "index": index,
        "nom": source.nom,
        "conforme": conforme,
        # Le chemin d'une case absente porte la clé de la grille : le motif est borné
        # comme celui d'une erreur, sans quoi le protocole refuserait l'événement.
        "motif": None if motif is None else motif[:LONGUEUR_MAX_MOTIF],
        "valeur": valeur,
        "sortie_brute": resultat["sortie_brute"] if tokens_sortie > 0 else None,
        "tokens_entree": resultat["tokens_entree"],
        "tokens_sortie": tokens_sortie,
        "delai_premier_token_s": resultat["delai_premier_token_s"],
        "duree_generation_s": resultat["duree_generation_s"],
        "duree_extraction_s": (
            DUREE_EXTRACTION_SIMULEE_S if factice else duree_extraction
        ),
        "vitesse_generation_tps": _vitesse_generation(
            tokens_sortie, resultat["duree_generation_s"]
        ),
        "vitesse_lecture_estimee_tps": _vitesse_lecture(
            resultat["tokens_entree"], resultat["delai_premier_token_s"]
        ),
        "temps_cpu_s": resultat["temps_cpu_s"],
        "pic_memoire_octets": PIC_MEMOIRE_SIMULE_OCTETS if factice else pic_memoire(),
        "fin": resultat["fin"],
        **provenance,
    }


def _evenement_erreur(
    index: int,
    source: SourceJob,
    motif: str,
    provenance: dict[str, bool],
) -> dict[str, Any]:
    """Événement `extraction_erreur` avec un motif borné à sa longueur maximale."""
    return {
        "type": TYPE_EXTRACTION_ERREUR,
        "index": index,
        "nom": source.nom,
        "motif": motif[:LONGUEUR_MAX_MOTIF],
        **provenance,
    }


def _verdict(
    resultat: dict[str, Any], schema: dict[str, Any]
) -> tuple[bool, str | None, dict[str, Any] | None]:
    """Conformité d'une sortie : `(conforme, motif, valeur décodée)`.

    Une génération arrêtée à `sortie_max` n'est jamais décodée : elle est non
    conforme par définition (D7).
    """
    if resultat["fin"] == "limite":
        return False, MOTIF_LIMITE, None
    decodage = decode_output(resultat["sortie_brute"])
    if not decodage.ok:
        return False, _motif_decodage(decodage), None
    verdict = validate_output(decodage.value, schema)
    if verdict.issue is not None:
        return False, _motif_conformite(verdict.issue), None
    return True, None, decodage.value


def _motif_decodage(decodage: DecodeResult) -> str:
    """Motif d'un refus de décodage : la clé dupliquée n'est pas recopiée."""
    if decodage.reason == DECODE_DUPLICATE_KEY:
        return MOTIF_DECODAGE_DUPLIQUE
    return decodage.message or MOTIF_ERREUR_INATTENDUE


def _motif_conformite(issue: SchemaIssue) -> str:
    """Motif d'une non-conformité ; le chemin est omis pour une clé inconnue.

    Une clé inconnue vient du modèle : son chemin la contient, il ne doit donc
    pas entrer dans un motif. Les autres chemins ne suivent que les clés du schéma.
    """
    libelle = MOTIFS_CONFORMITE.get(issue.reason, MOTIF_ERREUR_INATTENDUE)
    if issue.reason == REASON_UNKNOWN_KEY:
        return libelle
    return f"{libelle} ({issue.path})"


def _valider_resultat_extraction(valeur: Any) -> dict[str, Any]:
    """Vérifie le résultat de `extraire` : clés exactes, types et cause de fin."""
    if not isinstance(valeur, dict):
        raise ErreurSource("résultat d'adaptateur attendu sous forme de dict")
    inconnues = set(valeur) - set(CLES_RESULTAT_EXTRACTION)
    manquantes = [cle for cle in CLES_RESULTAT_EXTRACTION if cle not in valeur]
    if inconnues or manquantes:
        raise ErreurSource(
            "résultat d'adaptateur avec des clés inconnues ou manquantes"
        )
    sortie = valeur["sortie_brute"]
    if not isinstance(sortie, str):
        raise ErreurSource("'sortie_brute' doit être un texte")
    tokens_entree = _entier_naturel_adaptateur(valeur, "tokens_entree")
    tokens_sortie = _entier_naturel_adaptateur(valeur, "tokens_sortie")
    if tokens_sortie == 0 and sortie != "":
        raise ErreurSource("sortie non vide sans aucun token généré")
    fin = valeur["fin"]
    if fin not in FINS_GENERATION:
        raise ErreurSource(f"cause de fin inconnue : {fin!r}")
    return {
        "sortie_brute": sortie,
        "tokens_entree": tokens_entree,
        "tokens_sortie": tokens_sortie,
        "fin": fin,
        "delai_premier_token_s": _duree_adaptateur(valeur, "delai_premier_token_s"),
        "duree_generation_s": _duree_adaptateur(valeur, "duree_generation_s"),
        "temps_cpu_s": _duree_adaptateur(valeur, "temps_cpu_s"),
    }


def _entier_naturel_adaptateur(valeur: dict[str, Any], champ: str) -> int:
    """Compteur de tokens : entier positif ou nul, booléen exclu."""
    compte = valeur[champ]
    if isinstance(compte, bool) or not isinstance(compte, int) or compte < 0:
        raise ErreurSource(f"{champ!r} doit être un entier positif ou nul")
    return compte


def _duree_adaptateur(valeur: dict[str, Any], champ: str) -> float | None:
    """Chronométrage du résultat : `None` si indisponible, jamais zéro inventé.

    Une valeur non finie est traitée comme indisponible ; une valeur négative ou
    non numérique rend la source en erreur.
    """
    duree = valeur[champ]
    if duree is None:
        return None
    if isinstance(duree, bool) or not isinstance(duree, (int, float)):
        raise ErreurSource(f"{champ!r} doit être un nombre ou null")
    try:
        fini = math.isfinite(duree)
    except OverflowError:
        fini = False
    if not fini:
        return None
    if duree < 0:
        raise ErreurSource(f"{champ!r} ne peut pas être négatif")
    return float(duree)


def _vitesse_generation(
    tokens_sortie: int, duree_generation: float | None
) -> float | None:
    """(tokens_sortie − 1) / durée de génération ; absente sous deux tokens (D6)."""
    if tokens_sortie < 2 or duree_generation is None or duree_generation <= 0:
        return None
    return (tokens_sortie - 1) / duree_generation


def _vitesse_lecture(
    tokens_entree: int, delai_premier_token: float | None
) -> float | None:
    """tokens_entree / délai avant le premier token : estimation (D6)."""
    if delai_premier_token is None or delai_premier_token <= 0:
        return None
    return tokens_entree / delai_premier_token


def _observation_chargement(
    releveur: ReleveurSysteme, factice: bool
) -> dict[str, Any] | None:
    """Instantané RAM du chargement ; une erreur imprévue est écartée sans arrêt."""
    try:
        return _observation_systeme_emise(
            releveur.observation_chargement(),
            moment=MOMENT_CHARGEMENT,
            mesures_simulees=factice,
        )
    except Exception:
        print("Relevé système ignoré (chargement) : erreur imprévue", file=sys.stderr)
        return None


def _observation_lot(
    releveur: ReleveurSysteme, amorcage: Any, factice: bool
) -> dict[str, Any] | None:
    """CPU de la fenêtre du lot puis RAM disponible ; écarté sans arrêt si erreur."""
    try:
        return _observation_systeme_emise(
            releveur.observation_audio(amorcage),
            moment=MOMENT_AUDIO,
            mesures_simulees=factice,
        )
    except Exception:
        print("Relevé système ignoré (lot) : erreur imprévue", file=sys.stderr)
        return None


def _resume_source(index: int, total: int, evenement: dict[str, Any]) -> str:
    """Ligne de progression sans aucun texte source ni sortie du modèle."""
    position = f"source {index + 1}/{total}"
    if evenement["type"] == TYPE_EXTRACTION_ERREUR:
        return f"{position} : erreur ({evenement['motif']})"
    if evenement["conforme"]:
        return f"{position} : conforme"
    return f"{position} : non conforme ({evenement['motif']})"


def _journaliser(message: str) -> None:
    """Étape de progression sur stderr, recopiée par le serveur dans le journal."""
    print(message, file=sys.stderr)


def _charger_adaptateur(
    job: JobExtraction, registre: RegistreMoteurs
) -> tuple[ModuleType, DeclarationAdaptateur]:
    """Résout la déclaration, contrôle tâche et qualification, importe l'adaptateur."""
    try:
        declaration = registre.obtenir(job.moteur)
    except MoteurInconnu:
        raise ErreurMoteur(f"moteur inconnu : {job.moteur!r}") from None
    famille = next(
        (
            candidate
            for candidate in declaration.familles
            if candidate.identifiant == job.famille
        ),
        None,
    )
    if famille is None:
        raise ErreurMoteur(
            f"famille {job.famille!r} non déclarée pour le moteur {job.moteur!r}"
        )
    motif = motif_famille_non_executable(declaration, famille, TASK_EXTRACTION)
    if motif is not None:
        raise ErreurMoteur(f"{motif} : exécution refusée")
    try:
        adaptateur = registre.charger_adaptateur(job.moteur)
    except AdaptateurIndisponible as exception:
        raise ErreurMoteur(str(exception)) from exception
    for nom in ("charger", "reinitialiser", "extraire"):
        if not callable(getattr(adaptateur, nom, None)):
            raise ErreurMoteur(
                f"adaptateur incomplet pour {job.moteur!r} : {nom}() manquant"
            )
    return adaptateur, declaration


def main(argv: list[str] | None = None) -> int:
    """Point d'entrée du processus moteur d'extraction : un seul argument, le job."""
    arguments = list(sys.argv[1:] if argv is None else argv)
    if len(arguments) != 1:
        print("usage : python engines/runner_extraction.py job.json", file=sys.stderr)
        return 2
    _configurer_stdout()
    try:
        executer(charger_job_extraction(arguments[0]))
    except ErreurJob as exception:
        print(f"job invalide : {exception}", file=sys.stderr)
        return 2
    except ErreurMoteur as exception:
        print(f"moteur indisponible : {exception}", file=sys.stderr)
        return 3
    return 0


def _schema(valeur: Any) -> dict[str, Any]:
    """Schéma de sortie : objet JSON de type `object`, validé à la lecture du job."""
    if not isinstance(valeur, dict) or valeur.get("type") != "object":
        raise ErreurJob("'schema' doit être un objet de schéma JSON de type object")
    return valeur


def _sources(valeur: Any) -> tuple[SourceJob, ...]:
    """Sources ordonnées ; un texte contenant un marqueur de délimitation est refusé."""
    if not isinstance(valeur, list) or not valeur:
        raise ErreurJob("'sources' doit être une liste non vide")
    sources = []
    for position, entree in enumerate(valeur):
        if not isinstance(entree, dict):
            raise ErreurJob(f"source {position} : objet JSON attendu")
        texte = _texte(entree, "texte")
        ordre = entree.get("ordre")
        if isinstance(ordre, bool) or not isinstance(ordre, int) or ordre < 0:
            raise ErreurJob(
                f"source {position} : 'ordre' doit être un entier positif ou nul"
            )
        nom = _texte(entree, "nom")
        try:
            user_message(texte)
        except ValueError as exception:
            raise ErreurJob(f"source {position} : {exception}") from exception
        sources.append(SourceJob(texte=texte, ordre=ordre, nom=nom))
    return tuple(sources)


if __name__ == "__main__":
    sys.exit(main())
