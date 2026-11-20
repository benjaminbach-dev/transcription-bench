"""Validation d'une demande d'extraction : modèle, grille, sources (tâche 3.4).

Ce module formule et valide une **demande d'extraction**, sans rien lancer ni
rien écrire, sur le modèle de `executions.py` : un modèle d'extraction prêt
(mêmes règles d'exécutabilité que la transcription, pour la tâche d'extraction),
un moteur cohérent avec la référence, une grille valide (`grilles`,
`schema_grilles`), des sources `identifiant:ordre` (D8), les threads et les
réglages de la famille.

Une source désigne un audio **terminé**, avec un texte **non vide**, d'une
exécution de transcription enregistrée sous `data/results` (D8). Elle est lue
brute depuis `run.json` et `result.json` : les vues de consultation ne donnent
pas les provenances brutes (moteur, modèle, empreinte de l'audio). Une
transcription factice est admise et marquée ; l'empreinte de la source est le
SHA-256 du texte en UTF-8, et c'est elle qui définit la comparabilité.

Refus (`ValeurRefusee`, nommant la source ou la règle en cause) : modèle non
prêt ou modèle de transcription, moteur incohérent, grille illisible ou invalide
(avec son motif), source inexistante, en erreur, non traitée, vide, en double,
au format erroné, ou dont le texte contient un marqueur de délimitation. Aucun
message ne recopie le texte source.

Ce module ne fait aucune écriture. Les lectures se limitent aux résultats et à
la grille, par les chemins confinés des modules existants.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from engines.declarations import TASK_EXTRACTION
from engines.registre import MoteurInconnu, RegistreMoteurs
from transcription_bench.consignes_grilles import system_message, user_message
from transcription_bench.consultation_resultats import (
    EntreeEmpreinte,
    analyser_selection,
)
from transcription_bench.executions import (
    CLES_MODELE_FACTICE,
    LIBELLE_MODELE_FACTICE,
    ConfigurationExecutions,
    ModelePropose,
    ReglageValide,
    decouper_reference,
    famille_declaree,
    proposer_modele,
    threads_par_defaut,
    valider_reglages,
    valider_threads,
)
from transcription_bench.gestion_modeles import ModeleLocal
from transcription_bench.grilles import (
    GridUnreadable,
    grid_path,
    read_grid,
)
from transcription_bench.paths import ValeurRefusee, resoudre_dans_racine, resoudre_resultat
from transcription_bench.resultats import (
    NOM_FICHIER_EXECUTION,
    NOM_FICHIER_RESULTAT,
    SCHEMA,
    STATUT_ERREUR,
    STATUT_NON_TRAITE,
    STATUT_OK,
)
from transcription_bench.schema_grilles import grid_schema
from transcription_bench.stockage import JsonInvalide, lire_json

#: Libellés des statuts d'audio refusés, en français, sans contenu du fichier.
_REFUSED_STATUS_LABELS = {
    STATUT_ERREUR: "en erreur",
    STATUT_NON_TRAITE: "non traité",
}


@dataclass(frozen=True)
class ExtractionSource:
    """Source validée d'une extraction : provenance complète et texte copié.

    `rang` est la position dans l'extraction (1-based) ; `identifiant` et `ordre`
    désignent l'audio dans son exécution de transcription (D8). `texte` est la
    transcription source : il n'est jamais affiché par `repr` ni journalisé, il
    n'est écrit que dans la copie `source.txt` et dans le fichier de travail.
    `empreinte_texte` est le SHA-256 du texte UTF-8, `empreinte_audio` celle de
    l'audio, `None` si la transcription ne la porte pas.
    """

    rang: int
    identifiant: str
    ordre: int
    nom: str
    empreinte_audio: str | None
    modele: str | None
    moteur: str | None
    factice: bool
    texte: str = field(repr=False)
    empreinte_texte: str
    caracteres: int

    @property
    def reference(self) -> str:
        """Référence de la source, sous la forme `identifiant:ordre`."""
        return f"{self.identifiant}:{self.ordre}"


@dataclass(frozen=True)
class ExtractionGrid:
    """Grille validée : copie exacte, empreinte, schéma et message système.

    `copie` est le texte exact du fichier `grilles/<nom>.md` au moment de la
    validation, vérifié par son empreinte : elle est recopiée telle quelle dans
    le dossier de l'extraction (D7). `schema` et `message_systeme` sont ceux
    de la grille, et `version_consignes` la version du gabarit (D3).
    """

    nom: str
    sha256: str
    titre: str | None
    copie: str = field(repr=False)
    schema: Mapping[str, Any] = field(repr=False)
    message_systeme: str = field(repr=False)
    version_consignes: int
    nombre_cases: int


@dataclass(frozen=True)
class ExtractionRequest:
    """Demande d'extraction validée, consommée par le lancement (tâche 3.4).

    `sources` garde l'ordre de la demande, qui fixe le traitement et le rang de
    chaque source. `threads` est le nombre demandé, jamais un nombre appliqué.
    `reglages` contient toutes les valeurs effectives, défauts compris.
    """

    modele: ModelePropose
    grille: ExtractionGrid
    sources: tuple[ExtractionSource, ...]
    threads: int
    reglages: tuple[ReglageValide, ...]

    @property
    def moteur(self) -> str:
        """Identifiant du moteur d'extraction de la demande."""
        return self.modele.moteur

    @property
    def synthetique(self) -> bool:
        """Vrai pour le modèle synthétique du moteur factice."""
        return self.modele.synthetique

    def reglage(self, nom: str) -> int | bool | str | None:
        """Valeur effective d'un réglage par son nom, ou `None` s'il est absent."""
        for reglage in self.reglages:
            if reglage.nom == nom:
                return reglage.valeur
        return None


def load_grid(nom: str, racine: Path | None = None) -> ExtractionGrid:
    """Lit, valide et copie la grille `nom` ; lève `ValeurRefusee` si elle ne l'est pas.

    Une grille invalide est refusée avec son motif (ligne et règle). La copie
    est relue sur le même chemin confiné et comparée à l'empreinte de la lecture :
    une grille modifiée entre les deux lectures est refusée plutôt que copiée
    incohérente. `racine` est la racine contenant `grilles/` (projet par défaut).
    """
    try:
        grille = read_grid(nom, base=racine)
    except GridUnreadable as erreur:
        raise ValeurRefusee(str(erreur)) from None
    if not grille.valid:
        raise ValeurRefusee(
            f"grille invalide ({nom}) : {grille.error.message} "
            f"[règle : {grille.error.rule}]"
        )
    try:
        octets = grid_path(nom, racine).read_bytes()
    except OSError:
        raise ValeurRefusee(f"grille illisible au moment de la copie : {nom}") from None
    if hashlib.sha256(octets).hexdigest() != grille.sha256:
        raise ValeurRefusee(
            f"grille modifiée pendant sa validation : {nom} (relancez la demande)"
        )
    try:
        copie = octets.decode("utf-8")
    except UnicodeDecodeError:
        raise ValeurRefusee(f"grille non décodable en UTF-8 : {nom}") from None
    message = system_message(grille)
    return ExtractionGrid(
        nom=nom,
        sha256=grille.sha256,
        titre=grille.title,
        copie=copie,
        schema=grid_schema(grille),
        message_systeme=message.text,
        version_consignes=message.version,
        nombre_cases=len(grille.fields),
    )


def read_source(donnees: Path | str, reference: str, rang: int) -> ExtractionSource:
    """Valide une source `identifiant:ordre` contre les résultats enregistrés.

    Lève `ValeurRefusee` en nommant la source si elle n'est pas un audio terminé
    avec un texte non vide : format erroné, identifiant sortant, exécution
    inconnue ou illisible, audio absent, en erreur ou non traité, résultat
    absent, illisible ou incohérent, texte vide ou contenant un marqueur de
    délimitation. Aucune écriture.
    """
    try:
        return _read_source(donnees, reference, rang)
    except ValeurRefusee as erreur:
        raise ValeurRefusee(f"source {reference!r} refusée : {erreur}") from None


def _read_source(donnees: Path | str, reference: str, rang: int) -> ExtractionSource:
    """Corps de `read_source`, sans le préfixe de nommage des refus."""
    try:
        identifiant, ordre = analyser_selection(reference)
    except ValeurRefusee:
        raise ValeurRefusee(
            "forme 'identifiant d'exécution:ordre d'audio' attendue"
        ) from None
    # `resoudre_resultat` renvoie un chemin résolu et refuse déjà un lien
    # symbolique sortant : `is_symlink()` sur ce chemin serait toujours faux.
    dossier = resoudre_resultat(identifiant, donnees)
    if not dossier.is_dir():
        raise ValeurRefusee("exécution de transcription inconnue")
    run = _json_object(dossier, NOM_FICHIER_EXECUTION, "exécution de transcription")
    if run.get("schema") != SCHEMA or run.get("identifiant") != identifiant:
        raise ValeurRefusee("exécution de transcription non interprétable")
    plans = run.get("audios")
    if not isinstance(plans, list):
        raise ValeurRefusee("exécution de transcription non interprétable")
    plan = next(
        (
            candidat
            for candidat in plans
            if isinstance(candidat, Mapping) and candidat.get("ordre") == ordre
        ),
        None,
    )
    if plan is None:
        raise ValeurRefusee(f"audio {ordre} absent de l'exécution de transcription")
    if plan.get("statut") != STATUT_OK:
        libelle = _REFUSED_STATUS_LABELS.get(plan.get("statut"), "statut inconnu")
        raise ValeurRefusee(f"audio non terminé ({libelle})")
    if not isinstance(plan.get("nom"), str) or not isinstance(plan.get("dossier"), str):
        raise ValeurRefusee("plan d'audio non interprétable")
    dossier_audio = resoudre_dans_racine(dossier, plan["dossier"])
    resultat = _json_object(dossier_audio, NOM_FICHIER_RESULTAT, "résultat de l'audio")
    if (
        resultat.get("schema") != SCHEMA
        or resultat.get("execution") != identifiant
        or resultat.get("ordre") != ordre
        or resultat.get("statut") != STATUT_OK
    ):
        raise ValeurRefusee("résultat de l'audio non interprétable")
    transcription = _mapping(resultat.get("transcription"))
    texte = transcription.get("texte")
    if not isinstance(texte, str) or not texte.strip():
        raise ValeurRefusee("texte transcrit vide")
    try:
        user_message(texte)
    except ValueError:
        raise ValeurRefusee(
            "texte contenant un marqueur de délimitation des consignes"
        ) from None
    audio = _mapping(resultat.get("audio"))
    modele = _mapping(resultat.get("modele"))
    moteur = _mapping(resultat.get("moteur"))
    empreinte_audio = audio.get("empreinte_sha256")
    return ExtractionSource(
        rang=rang,
        identifiant=identifiant,
        ordre=ordre,
        nom=plan["nom"],
        empreinte_audio=empreinte_audio if isinstance(empreinte_audio, str) else None,
        modele=_text_or_none(modele.get("identifiant")),
        moteur=_text_or_none(moteur.get("identifiant")),
        factice=resultat.get("factice") is True,
        texte=texte,
        empreinte_texte=hashlib.sha256(texte.encode("utf-8")).hexdigest(),
        caracteres=len(texte),
    )


class ExtractionConfiguration:
    """Formule et valide les demandes d'extraction, sans les lancer.

    Le constructeur ne fait aucune E/S : l'inventaire des modèles est lu à la
    demande par la fonction injectée, comme dans `ConfigurationExecutions`, à
    laquelle sont délégués les refus de modèle de transcription.
    """

    def __init__(
        self,
        dossier_data: Path | str,
        registre: RegistreMoteurs,
        inventaire_modeles: Callable[[], Sequence[ModeleLocal]],
        *,
        racine_grilles: Path | str | None = None,
    ) -> None:
        self._donnees = Path(dossier_data)
        self._registre = registre
        self._inventaire_modeles = inventaire_modeles
        self._racine_grilles = None if racine_grilles is None else Path(racine_grilles)
        self._transcription = ConfigurationExecutions(
            dossier_data, registre, inventaire_modeles
        )

    def modeles_proposables(self) -> tuple[ModelePropose, ...]:
        """Modèles d'extraction de l'inventaire et modèle synthétique du factice.

        Seules les familles de tâche d'extraction sont retenues ; une famille
        non qualifiée reste listée avec son motif, non sélectionnable (règle
        `motif_famille_non_executable` appliquée à la tâche d'extraction).
        """
        try:
            inventaire = tuple(self._inventaire_modeles())
        except (ValeurRefusee, OSError):
            inventaire = ()
        proposes: list[ModelePropose] = []
        for modele in inventaire:
            try:
                declaration = self._registre.obtenir(modele.moteur)
            except MoteurInconnu:
                continue
            famille = famille_declaree(declaration, modele.famille)
            if famille is None or famille.task != TASK_EXTRACTION:
                continue
            proposes.append(
                proposer_modele(
                    declaration,
                    famille,
                    cle=modele.cle,
                    identifiant=modele.identifiant,
                    id_resolu=modele.id_resolu,
                    commit=modele.commit,
                    fichier_gguf=modele.fichier_gguf,
                    tache=TASK_EXTRACTION,
                )
            )
        for declaration in self._registre.lister():
            if not declaration.factice:
                continue
            for famille in declaration.familles:
                if famille.task != TASK_EXTRACTION:
                    continue
                proposes.append(
                    proposer_modele(
                        declaration,
                        famille,
                        cle=CLES_MODELE_FACTICE[TASK_EXTRACTION],
                        identifiant=LIBELLE_MODELE_FACTICE,
                        id_resolu=LIBELLE_MODELE_FACTICE,
                        commit="aucun",
                        fichier_gguf=None,
                        synthetique=True,
                        tache=TASK_EXTRACTION,
                    )
                )
        return tuple(proposes)

    def valider(
        self,
        *,
        modele: str,
        grille: str,
        sources: Sequence[str],
        threads: str | int | None = None,
        reglages: Mapping[str, str] | None = None,
        moteur: str | None = None,
    ) -> ExtractionRequest:
        """Valide une demande et renvoie sa forme consommable ; sans effet de bord.

        L'ordre des contrôles suit la spécification : modèle prêt, moteur cohérent
        avec la référence, grille valide, sources, threads, réglages déclarés. Le
        premier refus est levé tel quel (`ValeurRefusee`).
        """
        proposition = self._ready_model(modele)
        if moteur is not None and moteur != proposition.moteur:
            raise ValeurRefusee(
                "moteur incompatible avec la référence du modèle : "
                f"{moteur!r} fourni, {proposition.moteur!r} déclaré par cette référence"
            )
        grille_validee = load_grid(grille, self._racine_grilles)
        sources_validees = self._sources(sources)
        nombre_threads = (
            threads_par_defaut() if threads is None else valider_threads(threads)
        )
        valeurs = valider_reglages(
            proposition.reglages, {} if reglages is None else reglages
        )
        return ExtractionRequest(
            modele=proposition,
            grille=grille_validee,
            sources=sources_validees,
            threads=nombre_threads,
            reglages=valeurs,
        )

    def _ready_model(self, reference: str) -> ModelePropose:
        """Résout une référence vers un modèle d'extraction exécutable.

        Un modèle de transcription est refusé en le nommant : il n'est pas un
        modèle d'extraction, même s'il est prêt.
        """
        moteur, cle = decouper_reference(reference)
        for propose in self.modeles_proposables():
            if propose.moteur == moteur and propose.cle == cle:
                if not propose.executable:
                    raise ValeurRefusee(
                        f"famille non exécutable : {reference!r} "
                        f"({propose.motif_non_executable})"
                    )
                return propose
        if any(
            propose.reference == reference
            for propose in self._transcription.modeles_proposables()
        ):
            raise ValeurRefusee(
                f"modèle de transcription : {reference!r} n'est pas un modèle "
                "d'extraction"
            )
        raise ValeurRefusee(
            f"modèle non prêt ou inconnu : {reference!r} (seuls les modèles "
            "d'extraction relus depuis un inventaire local cohérent sont proposés)"
        )

    def _sources(self, references: Sequence[str]) -> tuple[ExtractionSource, ...]:
        """Sources ordonnées : au moins une, chacune valide et non répétée.

        La répétition porte sur le couple normalisé (identifiant, ordre) :
        deux écritures de la même source, par exemple `:1` et `:01`, sont un
        doublon même si leurs écritures diffèrent. Le motif cite les deux
        écritures reçues.
        """
        if isinstance(references, str) or not references:
            raise ValeurRefusee(
                "aucune source sélectionnée : au moins une source "
                "'identifiant:ordre' est requise"
            )
        sources: list[ExtractionSource] = []
        vues: dict[tuple[str, int], str] = {}
        for rang, reference in enumerate(references, start=1):
            if not isinstance(reference, str):
                raise ValeurRefusee("source attendue sous la forme 'identifiant:ordre'")
            source = read_source(self._donnees, reference, rang)
            cle = (source.identifiant, source.ordre)
            if cle in vues:
                raise ValeurRefusee(
                    f"source en double : {vues[cle]!r} et {reference!r}"
                )
            vues[cle] = reference
            sources.append(source)
        return tuple(sources)


def sources_proposables(
    donnees: Path | str, entrees: Iterable[EntreeEmpreinte]
) -> tuple[ExtractionSource, ...]:
    """Transcriptions proposables comme sources, parmi celles de la consultation.

    `entrees` vient de `ConsultationResultats.groupes_par_empreinte` : seules les
    entrées au statut `ok` sont examinées, puis chacune est revalidée par
    `read_source`, la même règle que la demande. Une entrée refusée (texte vide,
    marqueur, résultat incohérent) n'est pas proposée. Le rang n'a pas de sens
    hors demande : il vaut 0. Aucune écriture.
    """
    proposables: list[ExtractionSource] = []
    for entree in entrees:
        if entree.statut != STATUT_OK:
            continue
        try:
            proposables.append(
                read_source(donnees, f"{entree.execution}:{entree.ordre}", rang=0)
            )
        except ValeurRefusee:
            continue
    return tuple(proposables)


def _json_object(dossier: Path, nom: str, nature: str) -> Mapping[str, Any]:
    """Objet JSON confiné dans `dossier`, ou `ValeurRefusee` sans contenu du fichier.

    Le fichier est résolu dans son dossier, comme en consultation des résultats :
    un `run.json` ou un `result.json` qui serait un lien symbolique sortant
    n'est pas lu, et le refus ne cite ni son contenu ni son chemin complet.
    """
    try:
        chemin = resoudre_dans_racine(dossier, nom)
    except ValeurRefusee:
        raise ValeurRefusee(f"{nature} hors du dossier autorisé") from None
    try:
        contenu = lire_json(chemin)
    except (JsonInvalide, OSError):
        raise ValeurRefusee(f"{nature} illisible") from None
    if contenu is None:
        raise ValeurRefusee(f"{nature} absent")
    if not isinstance(contenu, dict):
        raise ValeurRefusee(f"{nature} non interprétable")
    return contenu


def _mapping(valeur: Any) -> Mapping[str, Any]:
    """Sous-objet JSON, vide s'il n'est pas un objet."""
    return valeur if isinstance(valeur, Mapping) else {}


def _text_or_none(valeur: Any) -> str | None:
    """Texte non vide, ou `None` ; jamais une valeur inventée."""
    return valeur if isinstance(valeur, str) and valeur else None
