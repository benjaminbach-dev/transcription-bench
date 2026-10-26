"""Formulaire d'exécution et demande validée, indépendants de Flask (tâche 6.2).

Ce service prépare et valide une **demande d'exécution** : un modèle prêt, une
sélection d'audios de la liste 6.1, le nombre de threads demandé et les réglages
applicables à la famille du modèle. Il ne lance rien : le job, le sous-processus
et le suivi relèvent de la tâche 6.3, qui consommera `DemandeExecution`. La page
GET et la prévisualisation POST de l'interface n'ont donc aucun effet de bord et
n'occupent pas le créneau d'opération longue.

Règles reprises des specs et du design :

- seuls les réglages **déclarés par la famille de l'adaptateur** sont proposés,
  chacun avec sa valeur par défaut. Aucun réglage n'est codé ici et aucune liste
  de réglages « habituels » n'est complétée : les quatre déclarations fournies
  n'exposent aujourd'hui aucun réglage, et la page le dit au lieu de simuler
  des options. Un champ de réglage non déclaré est refusé, jamais ignoré ;
- le nombre de threads demandé est un entier ≥ 1, proposé par défaut au nombre de
  cœurs physiques (`psutil.cpu_count(logical=False)`), à défaut de cœurs
  logiques, à défaut 1 (D6). Aucune valeur appliquée n'est affirmée ici : elle
  sera relue par l'adaptateur quand son API le permet (D6, tâches 8.x) ;
- les audios proposés sont ceux de la liste 6.1 **lisibles** ; une sélection
  vide, un nom absent de cette liste ou un doublon est refusé. L'ordre de la
  demande est celui de la sélection, car il fixe l'ordre de traitement (spec
  `benchmark-runs`) ;
- un modèle n'est proposé que s'il est prêt au sens de l'inventaire local 5.4,
  c'est-à-dire relu depuis un manifeste cohérent ; une référence inconnue ou non
  prête est refusée. La disponibilité effective de l'environnement du moteur est
  recontrôlée au lancement (tâche 6.3) ;
- une famille dont le runner refuserait la famille est affichée « non
  exécutable » avec son motif et n'est pas sélectionnable : la validation la
  refuse. Le motif vient de la règle unique
  `engines.declarations.motif_famille_non_executable`, celle du runner, pour ne
  jamais annoncer une capacité que le runner refuse ;
- pour toute déclaration `factice=True`, un **modèle synthétique** est proposé
  sans inventaire : clé constante, libellé « aucun modèle, textes et mesures
  simulés ». Il ne correspond à aucun fichier ; la tâche 6.3 lui passera un
  chemin fictif sous `data/`, car le runner exige un chemin non vide ;
- sans mécanisme natif déclaré (`Famille.duree_native` absente), l'exécution
  annonce le découpage en fenêtres fixes de 30 s sans recouvrement (D9). La
  constante est tenue égale à celle du runner (`engines.runner.FENETRE_SECONDES`)
  par un test, sans importer le runner dans le serveur. Un mécanisme natif
  déclaré rend la famille non exécutable (voir ci-dessus) : l'interface ne
  l'annonce donc jamais comme pris en charge.

Champs de formulaire : `modele`, `threads` et chaque `reglage_<nom>` sont
exigés **une seule fois**. Un champ répété est refusé (`ValeurRefusee`) plutôt
que résolu par la première ou la dernière valeur : aucune valeur ambiguë n'est
interprétée.

Limites assumées : la demande validée est une valeur en mémoire, non persistée ;
elle ne prouve ni que le modèle sera encore présent au lancement, ni que
l'environnement du moteur est intact. Ces contrôles appartiennent à 6.3. Ce
module ne fait aucune E/S lui-même : il lit l'inventaire et la liste des audios
par les fonctions injectées, déjà utilisées par les pages modèles et audios.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

import psutil

from engines.declarations import (
    TYPE_BOOLEEN,
    TYPE_CHOIX,
    TYPE_ENTIER,
    DeclarationAdaptateur,
    Famille,
    Reglage,
    motif_famille_non_executable,
)
from engines.registre import MoteurInconnu, RegistreMoteurs
from transcription_bench.audios import AudioListe, lister_audios
from transcription_bench.gestion_modeles import ModeleLocal
from transcription_bench.paths import ValeurRefusee

NOMBRE_THREADS_MINIMUM = 1
#: Durée des fenêtres fixes sans recouvrement, identique à `engines.runner`.
FENETRE_FIXE_SECONDES = 30.0
#: Préfixe des champs de réglage du formulaire (`reglage_<nom>`).
PREFIXE_CHAMP_REGLAGE = "reglage_"
#: Champs du formulaire qui ne peuvent être fournis qu'une seule fois.
CHAMPS_UNIQUES = ("modele", "threads")
SEPARATEUR_REFERENCE_MODELE = "/"
VALEUR_VRAIE = "oui"
VALEUR_FAUSSE = "non"

#: Libellé du modèle synthétique du moteur factice : aucun fichier, aucun poids.
LIBELLE_MODELE_FACTICE = "aucun modèle, textes et mesures simulés"
#: Clé constante du modèle synthétique (SHA-256 d'un texte fixe), distincte des
#: clés calculées depuis un inventaire.
CLE_MODELE_FACTICE = hashlib.sha256(b"modele-synthetique-factice").hexdigest()

_MOTIF_ENTIER = re.compile(r"-?[0-9]+", re.ASCII)
_MOTIF_CLE_MODELE = re.compile(r"[0-9a-f]{64}", re.ASCII)


def threads_par_defaut(
    compter_coeurs: Callable[..., int | None] | None = None,
) -> int:
    """Cœurs physiques via psutil, repli cœurs logiques, repli 1 (D6).

    psutil peut renvoyer `None` (comptage indisponible) : la valeur n'est alors
    ni inventée ni remplacée par un zéro, mais le repli documenté s'applique.
    `compter_coeurs` n'est fourni que par les tests.
    """
    compter = psutil.cpu_count if compter_coeurs is None else compter_coeurs
    for logique in (False, True):
        coeurs = compter(logical=logique)
        if isinstance(coeurs, int) and not isinstance(coeurs, bool):
            if coeurs >= NOMBRE_THREADS_MINIMUM:
                return coeurs
    return NOMBRE_THREADS_MINIMUM


def reglages_depuis_formulaire(champs: Mapping[str, str]) -> dict[str, str]:
    """Extrait les champs `reglage_<nom>` d'un formulaire, sans les interpréter.

    Les noms rendus sont ensuite confrontés aux seuls réglages déclarés par la
    famille : un nom inconnu est refusé par `ConfigurationExecutions.valider`.
    Un champ répété est refusé en amont par `refuser_champs_repetes`, sur la
    forme multi-valeurs brute du formulaire ; ce mapping, lui, ne peut pas en
    contenir.
    """
    return {
        nom[len(PREFIXE_CHAMP_REGLAGE) :]: valeur
        for nom, valeur in champs.items()
        if nom.startswith(PREFIXE_CHAMP_REGLAGE)
    }


def refuser_champs_repetes(champs: Iterable[tuple[str, str]]) -> None:
    """Refuse un champ `modele`, `threads` ou `reglage_*` fourni plusieurs fois.

    `champs` est la forme multi-valeurs du formulaire
    (`request.form.items(multi=True)`), où un nom peut donc apparaître plusieurs
    fois. Aucune valeur ambiguë n'est arbitrée par la première ou la dernière :
    le nom répété est refusé (`ValeurRefusee`) avec la liste des noms en double.
    Les autres champs (jeton anti-CSRF, audios répétés) ne sont pas concernés.
    """
    vus: set[str] = set()
    doubles: set[str] = set()
    for nom, _ in champs:
        if nom not in CHAMPS_UNIQUES and not nom.startswith(PREFIXE_CHAMP_REGLAGE):
            continue
        if nom in vus:
            doubles.add(nom)
        vus.add(nom)
    if doubles:
        raise ValeurRefusee(
            "champ fourni plusieurs fois : " + ", ".join(sorted(doubles))
        )


@dataclass(frozen=True)
class ModelePropose:
    """Modèle proposé à l'exécution, prêt ou non exécutable.

    `reglages` reprend, dans l'ordre de la déclaration, les réglages de la
    famille du modèle. `fenetre_fixe_secondes` vaut `None` quand la famille
    déclare un mécanisme natif d'audio long, et `FENETRE_FIXE_SECONDES` sinon ;
    une famille à mécanisme natif est justement non exécutable ici.
    `qualifiee` indique si la famille a été validée sur PC. `executable` résume
    la règle du runner : un modèle non exécutable est affiché avec son motif
    `motif_non_executable` et ne peut jamais être sélectionné ni validé.
    `synthetique` marque l'entrée du moteur factice, qui ne correspond à aucun
    modèle de l'inventaire et n'a donc ni commit ni fichier.
    """

    moteur: str
    nom_moteur: str
    cle: str
    identifiant: str
    id_resolu: str
    commit: str
    famille: str
    libelle_famille: str
    qualifiee: bool
    fichier_gguf: str | None
    reglages: tuple[Reglage, ...]
    fenetre_fixe_secondes: float | None
    executable: bool = True
    motif_non_executable: str | None = None
    synthetique: bool = False

    @property
    def reference(self) -> str:
        """Référence opaque transmise par le formulaire (`<moteur>/<clé>`)."""
        return f"{self.moteur}{SEPARATEUR_REFERENCE_MODELE}{self.cle}"


@dataclass(frozen=True)
class ReglageValide:
    """Réglage effectif d'une demande : nom déclaré et valeur typée."""

    nom: str
    valeur: int | bool | str


@dataclass(frozen=True)
class DemandeExecution:
    """Demande d'exécution validée, consommée par le lancement (tâche 6.3).

    `audios` garde l'ordre de la sélection ; `threads` est le nombre **demandé**,
    jamais un nombre appliqué. `reglages` contient toutes les valeurs effectives,
    défauts compris, dans l'ordre de la déclaration. `fenetre_fixe_secondes`
    vaut `None` si la famille déclare un mécanisme natif d'audio long -- une telle
    famille n'est pas exécutable, donc une demande validée vaut toujours
    `FENETRE_FIXE_SECONDES`. `synthetique` signale la demande portant le modèle
    synthétique du moteur factice : aucun fichier de modèle n'existe, et la
    tâche 6.3 lui fournira un chemin fictif.
    """

    moteur: str
    cle: str
    identifiant: str
    id_resolu: str
    commit: str
    famille: str
    fichier_gguf: str | None
    audios: tuple[str, ...]
    threads: int
    reglages: tuple[ReglageValide, ...]
    fenetre_fixe_secondes: float | None
    synthetique: bool = False

    def reglage(self, nom: str) -> int | bool | str | None:
        """Valeur effective d'un réglage par son nom, ou `None` s'il est absent."""
        for reglage in self.reglages:
            if reglage.nom == nom:
                return reglage.valeur
        return None


class ConfigurationExecutions:
    """Formule et valide les demandes d'exécution, sans les lancer.

    Le constructeur ne fait aucune E/S : l'inventaire des modèles et la liste
    des audios sont lus à l'affichage, par les fonctions injectées.
    """

    def __init__(
        self,
        dossier_data: Path | str,
        registre: RegistreMoteurs,
        inventaire_modeles: Callable[[], Sequence[ModeleLocal]],
        *,
        lister: Callable[[Path], tuple[AudioListe, ...]] = lister_audios,
        compter_threads: Callable[[], int] = threads_par_defaut,
    ) -> None:
        self._donnees = Path(dossier_data)
        self._registre = registre
        self._inventaire_modeles = inventaire_modeles
        self._lister = lister
        self._compter_threads = compter_threads

    def threads_par_defaut(self) -> int:
        """Nombre de threads proposé par défaut, jamais inférieur au minimum."""
        return max(NOMBRE_THREADS_MINIMUM, self._compter_threads())

    def modeles_proposables(self) -> tuple[ModelePropose, ...]:
        """Modèles de l'inventaire et modèle synthétique du moteur factice.

        Un modèle dont le moteur n'est pas enregistré ou dont la famille n'est
        pas déclarée par ce moteur n'est pas proposé : ses réglages applicables
        seraient inconnus. Les autres sont proposés avec `executable` à `False`
        et leur motif quand le runner refuserait la famille ; l'interface les
        affiche sans permettre de les sélectionner. Un inventaire illisible ou
        refusé n'apporte aucun modèle d'inventaire, mais n'empêche pas le modèle
        synthétique du moteur factice, qui ne le lit pas.

        Pour toute déclaration `factice=True`, une entrée synthétique est
        ajoutée après celles de l'inventaire : elle ne lit aucun fichier, porte
        une clé constante et le libellé `LIBELLE_MODELE_FACTICE`.
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
            famille = _famille_declaree(declaration, modele.famille)
            if famille is None:
                continue
            proposes.append(
                _proposer(
                    declaration,
                    famille,
                    cle=modele.cle,
                    identifiant=modele.identifiant,
                    id_resolu=modele.id_resolu,
                    commit=modele.commit,
                    fichier_gguf=modele.fichier_gguf,
                )
            )
        for declaration in self._registre.lister():
            if not declaration.factice:
                continue
            proposes.append(
                _proposer(
                    declaration,
                    declaration.familles[0],
                    cle=CLE_MODELE_FACTICE,
                    identifiant=LIBELLE_MODELE_FACTICE,
                    id_resolu=LIBELLE_MODELE_FACTICE,
                    commit="aucun",
                    fichier_gguf=None,
                    synthetique=True,
                )
            )
        return tuple(proposes)

    def audios_proposables(self) -> tuple[AudioListe, ...]:
        """Audios lisibles de la liste 6.1, dans son ordre alphabétique."""
        try:
            audios = tuple(self._lister(self._donnees))
        except (ValeurRefusee, OSError):
            return ()
        return tuple(audio for audio in audios if audio.erreur is None)

    def valider(
        self,
        *,
        modele: str,
        audios: Sequence[str],
        threads: str | int,
        reglages: Mapping[str, str],
    ) -> DemandeExecution:
        """Valide une demande de formulaire et renvoie sa forme consommable.

        Les contrôles s'enchaînent dans cet ordre : modèle prêt, audios de la
        liste, threads demandés, réglages déclarés. Lève `ValeurRefusee` au
        premier refus, sans effet de bord ni lancement.
        """
        propose = self._modele_prete(modele)
        noms = self._valider_audios(audios)
        nombre_threads = _valider_threads(threads)
        valeurs = _valider_reglages(propose.reglages, reglages)
        return DemandeExecution(
            moteur=propose.moteur,
            cle=propose.cle,
            identifiant=propose.identifiant,
            id_resolu=propose.id_resolu,
            commit=propose.commit,
            famille=propose.famille,
            fichier_gguf=propose.fichier_gguf,
            audios=noms,
            threads=nombre_threads,
            reglages=valeurs,
            fenetre_fixe_secondes=propose.fenetre_fixe_secondes,
            synthetique=propose.synthetique,
        )

    def _modele_prete(self, reference: str) -> ModelePropose:
        """Résout une référence vers un modèle proposé et exécutable.

        Un modèle non prêt, inconnu ou dont la famille n'est pas exécutable est
        refusé : l'interface peut l'afficher, jamais le valider.
        """
        moteur, cle = _decouper_reference(reference)
        for propose in self.modeles_proposables():
            if propose.moteur == moteur and propose.cle == cle:
                if not propose.executable:
                    raise ValeurRefusee(
                        f"famille non exécutable : {reference!r} "
                        f"({propose.motif_non_executable})"
                    )
                return propose
        raise ValeurRefusee(
            f"modèle non prêt ou inconnu : {reference!r} (seuls les modèles relus "
            "depuis un inventaire local cohérent sont proposés)"
        )

    def _valider_audios(self, audios: Sequence[str]) -> tuple[str, ...]:
        """Contrôle que chaque audio sélectionné est lisible et non répété."""
        if not audios:
            raise ValeurRefusee(
                "aucun audio sélectionné : au moins un audio lisible de la liste "
                "du dossier d'entrée est requis"
            )
        proposables = {audio.nom for audio in self.audios_proposables()}
        noms: list[str] = []
        for nom in audios:
            if not isinstance(nom, str) or nom not in proposables:
                raise ValeurRefusee(
                    f"audio hors de la liste du dossier d'entrée ou illisible : {nom!r}"
                )
            if nom in noms:
                raise ValeurRefusee(f"audio sélectionné en double : {nom!r}")
            noms.append(nom)
        return tuple(noms)


def _famille_declaree(
    declaration: DeclarationAdaptateur, identifiant: str
) -> Famille | None:
    """Famille déclarée par un moteur, ou `None` si elle ne l'est pas."""
    for famille in declaration.familles:
        if famille.identifiant == identifiant:
            return famille
    return None


def _proposer(
    declaration: DeclarationAdaptateur,
    famille: Famille,
    *,
    cle: str,
    identifiant: str,
    id_resolu: str,
    commit: str,
    fichier_gguf: str | None,
    synthetique: bool = False,
) -> ModelePropose:
    """Construit une proposition avec la règle d'exécutabilité du runner."""
    motif = motif_famille_non_executable(declaration, famille)
    return ModelePropose(
        moteur=declaration.identifiant,
        nom_moteur=declaration.nom,
        cle=cle,
        identifiant=identifiant,
        id_resolu=id_resolu,
        commit=commit,
        famille=famille.identifiant,
        libelle_famille=famille.libelle,
        qualifiee=famille.qualifiee,
        fichier_gguf=fichier_gguf,
        reglages=famille.reglages,
        fenetre_fixe_secondes=(
            None if famille.duree_native is not None else FENETRE_FIXE_SECONDES
        ),
        executable=motif is None,
        motif_non_executable=motif,
        synthetique=synthetique,
    )


def _decouper_reference(reference: str) -> tuple[str, str]:
    """Sépare `<moteur>/<clé>` et refuse toute autre forme."""
    if not isinstance(reference, str):
        raise ValeurRefusee("référence de modèle attendue sous forme de texte")
    moteur, separateur, cle = reference.partition(SEPARATEUR_REFERENCE_MODELE)
    if not moteur or not separateur or not _MOTIF_CLE_MODELE.fullmatch(cle):
        raise ValeurRefusee(
            "référence de modèle invalide : '<moteur>/<clé de 64 caractères "
            "hexadécimaux>' attendue"
        )
    return moteur, cle


def _valider_threads(valeur: str | int) -> int:
    """Entier ≥ 1 strictement interprété, sans accepter de valeur approximative."""
    if isinstance(valeur, bool):
        raise ValeurRefusee(
            f"nombre de threads demandé invalide : {valeur!r} (entier ≥ 1 attendu)"
        )
    if isinstance(valeur, int):
        nombre = valeur
    elif isinstance(valeur, str):
        texte = valeur.strip()
        if not _MOTIF_ENTIER.fullmatch(texte):
            raise ValeurRefusee(
                f"nombre de threads demandé invalide : {valeur!r} (entier ≥ 1 attendu)"
            )
        nombre = int(texte)
    else:
        raise ValeurRefusee(
            f"nombre de threads demandé invalide : {valeur!r} (entier ≥ 1 attendu)"
        )
    if nombre < NOMBRE_THREADS_MINIMUM:
        raise ValeurRefusee(
            f"nombre de threads demandé invalide : {valeur!r} (entier ≥ 1 attendu)"
        )
    return nombre


def _valider_reglages(
    declares: Sequence[Reglage], valeurs: Mapping[str, str]
) -> tuple[ReglageValide, ...]:
    """Valeurs effectives des seuls réglages déclarés, défauts compris.

    Un nom absent de la déclaration est refusé : le service n'ignore jamais un
    champ inconnu et n'ajoute aucun réglage de sa propre initiative.
    """
    connus = {reglage.nom for reglage in declares}
    inconnus = sorted(set(valeurs) - connus)
    if inconnus:
        raise ValeurRefusee(
            "réglage non déclaré par la famille du modèle : " + ", ".join(inconnus)
        )
    effectifs: list[ReglageValide] = []
    for reglage in declares:
        if reglage.nom in valeurs:
            valeur = _valeur_reglage(reglage, valeurs[reglage.nom])
        else:
            valeur = reglage.defaut
        effectifs.append(ReglageValide(reglage.nom, valeur))
    return tuple(effectifs)


def _valeur_reglage(reglage: Reglage, brut: str) -> int | bool | str:
    """Interprète une valeur de formulaire selon le type déclaré du réglage."""
    texte = brut.strip() if isinstance(brut, str) else brut
    if reglage.type_valeur == TYPE_ENTIER:
        if not isinstance(texte, str) or not _MOTIF_ENTIER.fullmatch(texte):
            raise ValeurRefusee(
                f"réglage {reglage.nom!r} invalide : {brut!r} (entier attendu)"
            )
        return int(texte)
    if reglage.type_valeur == TYPE_BOOLEEN:
        if texte == VALEUR_VRAIE:
            return True
        if texte == VALEUR_FAUSSE:
            return False
        raise ValeurRefusee(
            f"réglage {reglage.nom!r} invalide : {brut!r} "
            f"({VALEUR_VRAIE} ou {VALEUR_FAUSSE} attendu)"
        )
    if reglage.type_valeur == TYPE_CHOIX:
        if texte not in reglage.valeurs:
            raise ValeurRefusee(
                f"réglage {reglage.nom!r} invalide : {brut!r} "
                f"(valeurs possibles : {', '.join(reglage.valeurs)})"
            )
        return texte
    if not isinstance(texte, str):
        raise ValeurRefusee(
            f"réglage {reglage.nom!r} invalide : {brut!r} (texte attendu)"
        )
    return texte
