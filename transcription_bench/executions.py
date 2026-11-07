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

Champs de formulaire : `modele`, `moteur`, `threads` et chaque
`reglage_<nom>` sont exigés **une seule fois**. Un champ répété est refusé
(`ValeurRefusee`) plutôt que résolu par la première ou la dernière valeur :
aucune valeur ambiguë n'est interprétée. Le panneau de préparation (design D4)
se lit d'abord en GET, avec les seules références locales et les noms d'audios
(`preparer`), puis se soumet en POST avec le jeton anti-CSRF. Le champ `moteur`
ne remplace jamais la référence : fourni, il doit être celui qu'elle déclare, et
il est revalidé comme le reste au lancement.

Extension bornée du GET (design D4, tâche 4.2) : pour conserver les réglages
avancés d'une préparation déjà affichée, la lecture accepte aussi `source`
(référence de la préparation d'origine), `threads` et les `reglage_<nom>`
qu'elle proposait. Ce sont des valeurs **non sensibles** : jamais le jeton
anti-CSRF, jamais un nom hors de la liste blanche des réglages déclarés, aucune
écriture. Le service vérifie que `source` désigne une ressource proposable et
que sa famille est celle de la cible ; il ne reporte aucune valeur homonyme
d'une autre famille, il revalide chaque valeur avec les règles du POST et il
distingue un refus borné (`notice`, valeur inconnue ou non attribuable) d'un
repli annoncé (`reinitialisation`, valeurs remplacées par leurs défauts).

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
    TYPE_TEXTE,
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
#: Champs du formulaire qui ne peuvent être fournis qu'une seule fois. `source`
#: ne circule qu'en GET (référence de la préparation d'origine) : la répéter
#: rendrait l'attribution des réglages ambiguë, elle est donc refusée aussi.
CHAMPS_UNIQUES = ("modele", "moteur", "threads", "source")
SEPARATEUR_REFERENCE_MODELE = "/"
VALEUR_VRAIE = "oui"
VALEUR_FAUSSE = "non"

#: Libellé du modèle synthétique du moteur factice : aucun fichier, aucun poids.
LIBELLE_MODELE_FACTICE = "aucun modèle, textes et mesures simulés"

#: Messages bornés d'une préparation GET : une valeur de requête périmée,
#: incohérente ou incomplète est remplacée par un choix applicable, et le
#: remplacement est annoncé au lieu d'être silencieux (design D4).
MESSAGE_MODELE_REINITIALISE = (
    "Modèle choisi introuvable, périmé ou non exécutable : les choix par défaut "
    "sont proposés à la place."
)
MESSAGE_MOTEUR_INCOHERENT = (
    "Moteur incompatible avec la référence du modèle : le moteur déclaré par "
    "cette référence est retenu."
)
MESSAGE_MOTEUR_ADAPTE = (
    "Moteur changé : le premier modèle exécutable de ce moteur est sélectionné."
)
MESSAGE_AUDIO_INCOHERENT = (
    "Audio choisi absent de la liste des audios lisibles ou fourni deux fois : "
    "seuls les audios lisibles sont conservés."
)
#: Annonce neutre (bandeau `reinitialisation`, page rendue en 200) et non un
#: refus : la demande nommait un modèle sans audio, le défaut s'applique.
MESSAGE_AUDIO_AUCUN = (
    "Aucun audio n'était sélectionné dans la demande : le premier audio lisible "
    "est retenu par défaut."
)

#: Messages bornés de la conservation des réglages avancés (design D4) : les
#: valeurs transmises en GET viennent du formulaire préparé ; elles ne sont
#: retenues que pour la famille de la préparation d'origine, revalidées comme
#: au POST. `notice` refuse, `reinitialisation` annonce un repli.
MESSAGE_REGLAGES_SANS_SOURCE = (
    "Réglages avancés refusés : la préparation d'origine de ces valeurs n'est "
    "pas identifiée. Les valeurs par défaut sont proposées."
)
MESSAGE_REGLAGES_AUTRE_FAMILLE = (
    "Réglages avancés réinitialisés : la famille du modèle a changé, les "
    "valeurs précédentes ne s'appliquent plus."
)
MESSAGE_REGLAGES_INVALIDES = (
    "Réglages avancés partiellement réinitialisés : les valeurs transmises "
    "n'étaient pas toutes applicables, elles sont remplacées par leurs valeurs "
    "par défaut."
)
MESSAGE_REGLAGES_REINITIALISES = (
    "Réglages avancés revenus à leurs valeurs par défaut : aucune valeur "
    "conservable n'a été transmise."
)
MESSAGE_THREADS_REINITIALISES = (
    "Threads demandés revenus à la valeur par défaut : aucune valeur n'a été "
    "transmise."
)
MESSAGE_TEXTE_NON_CONSERVE = (
    "Réglages textuels revenus à leur valeur par défaut : aucun texte libre "
    "n'est conservé dans une URL."
)
MESSAGE_REGLAGE_INCONNU = (
    "Réglage non déclaré par la famille du modèle : demande refusée."
)

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
class PreparationExecution:
    """Choix appliqués d'une préparation unique Modèle/Audio/Moteur (D4).

    `modele` est la référence locale source de vérité, ou `None` quand aucun
    modèle exécutable n'est proposable (`applicable` vaut alors faux et la page
    remplace les contrôles inapplicables). `moteur` en découle et ne peut jamais
    la contredire. `audios` garde l'ordre reçu et ne contient que des audios
    lisibles. `notice` est un message borné, ou `None` quand la requête ne
    demandait rien ou que tout a été retenu tel quel : une valeur périmée est
    remplacée par un choix applicable et le remplacement annoncé.

    `threads` et `reglages` sont les valeurs effectives du panneau, défauts
    compris : conservées depuis la préparation d'origine par le GET quand elles
    restent applicables (design D4), sinon remplacées par leurs défauts.
    `reinitialisation` annonce alors ce repli, message borné distinct de
    `notice` : un repli est une information, une valeur non attribuable ou
    inconnue est un refus.
    """

    modele: ModelePropose | None
    moteur: str | None
    audios: tuple[str, ...]
    notice: str | None = None
    threads: int | None = None
    reglages: tuple[tuple[Reglage, int | bool | str], ...] = ()
    reinitialisation: str | None = None

    @property
    def applicable(self) -> bool:
        """Vrai si un modèle exécutable et au moins un audio sont retenus."""
        return self.modele is not None and bool(self.audios)

    @property
    def reference(self) -> str | None:
        """Référence de la préparation appliquée (`<moteur>/<clé>`), ou None."""
        return None if self.modele is None else self.modele.reference


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

    def preparer(
        self,
        *,
        modele: str | None = None,
        moteur: str | None = None,
        audios: Sequence[str] = (),
        source: str | None = None,
        threads: str | None = None,
        reglages: Mapping[str, str] | None = None,
        autoriser_texte: bool = False,
        adapter_moteur: bool = True,
    ) -> PreparationExecution:
        """Résout une préparation GET, sans effet de bord ni jeton (D4).

        Reçoit des références locales, des noms d'audios et des réglages non
        sensibles attribuables à une préparation, jamais un jeton : lecture seule. Le résultat n'est pas applicable
        (`applicable` faux) quand aucun modèle exécutable ou aucun audio lisible
        n'est disponible, pour que la page remplace les contrôles inapplicables.

        Une valeur périmée ou incohérente n'échoue pas : elle est remplacée par
        le choix applicable (modèle par défaut, moteur déclaré par la référence,
        audios lisibles) et le remplacement est consigné dans `notice`, message
        fixe et borné, que la route GET présente avec le statut de refus 400.
        Une simple omission — aucun audio nommé alors que le modèle l'est — est
        au contraire un choix incomplet, pas une valeur périmée : le repli sur
        le premier audio lisible est annoncé dans `reinitialisation`, bandeau
        neutre rendu en 200, pour que l'action « Utiliser » de la page Modèles
        (tâche 5.1) mène à une préparation sans encart d'erreur. Le moteur demandé ne peut jamais
        contredire la référence : celle-ci reste la source de vérité.

        `source`, `threads` et `reglages` étendent cette lecture aux réglages
        avancés (tâche 4.2) : ils ne viennent que d'une préparation déjà affichée
        et restent des valeurs non sensibles. Seuls les réglages déclarés par la
        famille de `source` sont attribuables ; aucune valeur homonyme d'une
        autre famille n'est reportée. Une valeur inconnue ou non attribuable est
        refusée (`notice`), une valeur seulement inapplicable est remplacée et
        annoncée (`reinitialisation`). `autoriser_texte` est réservé au rendu
        d'un POST : le GET ne conserve jamais de texte libre dans ses URL.
        """
        proposes = self.modeles_proposables()
        executables = tuple(propose for propose in proposes if propose.executable)
        lisibles = self.audios_proposables()
        notices: list[str] = []
        annonce_audio: str | None = None
        changement_moteur = None
        choisi: ModelePropose | None = None
        if modele is not None:
            choisi = next(
                (propose for propose in executables if propose.reference == modele),
                None,
            )
            if choisi is None:
                notices.append(MESSAGE_MODELE_REINITIALISE)
        if choisi is None and executables:
            choisi = executables[0]
        noms_lisibles = {audio.nom for audio in lisibles}
        gardes: list[str] = []
        for nom in audios:
            if isinstance(nom, str) and nom in noms_lisibles and nom not in gardes:
                gardes.append(nom)
        if len(gardes) != len(audios):
            notices.append(MESSAGE_AUDIO_INCOHERENT)
        if not gardes and lisibles:
            if modele is not None:
                # Omission d'audio, pas valeur périmée : annonce neutre (200),
                # jamais l'encart d'erreur réservé aux valeurs nommées invalides.
                annonce_audio = MESSAGE_AUDIO_AUCUN
            gardes.append(lisibles[0].nom)
        if choisi is not None and moteur is not None and moteur != choisi.moteur:
            compatible = next(
                (propose for propose in executables if propose.moteur == moteur), None
            )
            if (adapter_moteur and source is not None and modele == source
                    and compatible is not None):
                # Repli HTML : seul le moteur a changé depuis la préparation.
                choisi = compatible
                changement_moteur = MESSAGE_MOTEUR_ADAPTE
            else:
                notices.append(MESSAGE_MOTEUR_INCOHERENT)
        valeurs_threads = self.threads_par_defaut()
        valeurs_reglages: tuple[tuple[Reglage, int | bool | str], ...] = ()
        reinitialisation = annonce_audio
        if choisi is not None:
            retenues = _retenir_valeurs(
                choisi,
                proposes=proposes,
                source=source,
                threads=threads,
                reglages=reglages or {},
                threads_par_defaut=valeurs_threads,
                autoriser_texte=autoriser_texte,
            )
            valeurs_threads = retenues.threads
            valeurs_reglages = retenues.reglages
            reinitialisation = " ".join(
                texte
                for texte in (
                    changement_moteur,
                    retenues.reinitialisation,
                    reinitialisation,
                )
                if texte
            ) or None
            if retenues.notice is not None:
                notices.append(retenues.notice)
        return PreparationExecution(
            modele=choisi,
            moteur=None if choisi is None else choisi.moteur,
            audios=tuple(gardes),
            notice=" ".join(notices) or None,
            threads=valeurs_threads,
            reglages=valeurs_reglages,
            reinitialisation=reinitialisation,
        )

    def valider(
        self,
        *,
        modele: str,
        audios: Sequence[str],
        threads: str | int,
        reglages: Mapping[str, str],
        moteur: str | None = None,
    ) -> DemandeExecution:
        """Valide une demande de formulaire et renvoie sa forme consommable.

        Les contrôles s'enchaînent dans cet ordre : modèle prêt, moteur cohérent
        avec la référence, audios de la liste, threads demandés, réglages
        déclarés. Lève `ValeurRefusee` au premier refus, sans effet de bord ni
        lancement. `moteur` est le champ du panneau de préparation : quand il est
        fourni, il doit être celui de la référence ; la référence reste la source
        de vérité et un moteur qui la contredit est refusé, jamais réinterprété.
        """
        propose = self._modele_prete(modele)
        if moteur is not None and moteur != propose.moteur:
            raise ValeurRefusee(
                "moteur incompatible avec la référence du modèle : "
                f"{moteur!r} fourni, {propose.moteur!r} déclaré par cette référence"
            )
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


@dataclass(frozen=True)
class _ValeursRetenues:
    """Valeurs effectives du panneau après conservation ou repli (tâche 4.2)."""

    threads: int
    reglages: tuple[tuple[Reglage, int | bool | str], ...]
    notice: str | None = None
    reinitialisation: str | None = None


def _retenir_valeurs(
    cible: ModelePropose,
    *,
    proposes: Sequence[ModelePropose],
    source: str | None,
    threads: str | None,
    reglages: Mapping[str, str],
    threads_par_defaut: int,
    autoriser_texte: bool = False,
) -> _ValeursRetenues:
    """Réglages avancés d'une préparation GET, conservés ou remis aux défauts.

    Les valeurs transmises viennent de la préparation déjà affichée (`source`).
    Aucune n'est attribuée sans origine identifiée : sans `source` proposable,
    elles sont refusées (`notice`) plutôt que devinées. Les réglages ne sont
    conservés que pour la famille de `source` — même moteur et même famille, ce
    qui couvre une révision ou une variante —, ce qui interdit tout report de
    valeurs homonymes entre deux familles ; une autre famille remet les valeurs
    à leurs défauts et l'annonce. Chaque valeur conservée est revalidée avec les
    règles du POST ; les threads, indépendants de la famille, suivent la même
    règle. Les défauts déclarés restent toujours applicables.
    """
    defauts = tuple((reglage, reglage.defaut) for reglage in cible.reglages)
    valeurs = {reglage.nom: reglage.defaut for reglage in cible.reglages}
    origine = _propose_par_reference(proposes, source)
    if origine is None:
        if reglages or threads is not None:
            return _ValeursRetenues(
                threads_par_defaut, defauts, notice=MESSAGE_REGLAGES_SANS_SOURCE
            )
        return _ValeursRetenues(threads_par_defaut, defauts)
    valeurs_threads = threads_par_defaut
    invalides = False
    if threads is not None:
        try:
            valeurs_threads = _valider_threads(threads)
        except ValeurRefusee:
            invalides = True
    annonces: list[str] = []
    declares_origine = {reglage.nom: reglage for reglage in origine.reglages}
    if set(reglages) - set(declares_origine):
        return _ValeursRetenues(
            threads_par_defaut, defauts, notice=MESSAGE_REGLAGE_INCONNU
        )
    if threads is None:
        # Repli HTML : les copies du GET restent désactivées, la valeur
        # demandée n'est pas transmise.
        annonces.append(MESSAGE_THREADS_REINITIALISES)
    if reglages:
        if (origine.moteur, origine.famille) != (cible.moteur, cible.famille):
            annonces.append(MESSAGE_REGLAGES_AUTRE_FAMILLE)
        else:
            declares = {reglage.nom: reglage for reglage in cible.reglages}
            textes_ignores = False
            for nom, brut in reglages.items():
                if declares[nom].type_valeur == TYPE_TEXTE and not autoriser_texte:
                    # Un texte libre ne voyage jamais dans une URL de GET.
                    textes_ignores = True
                    continue
                try:
                    valeurs[nom] = _valeur_reglage(declares[nom], brut)
                except ValeurRefusee:
                    invalides = True
            if textes_ignores:
                annonces.append(MESSAGE_TEXTE_NON_CONSERVE)
    elif origine.reglages:
        # Aucune valeur transmise alors que la préparation d'origine en
        # proposait : le formulaire de sélection ne les transmet pas (repli HTML).
        annonces.append(MESSAGE_REGLAGES_REINITIALISES)
    if invalides:
        annonces.append(MESSAGE_REGLAGES_INVALIDES)
    return _ValeursRetenues(
        valeurs_threads,
        tuple((reglage, valeurs[reglage.nom]) for reglage in cible.reglages),
        reinitialisation=" ".join(annonces) or None,
    )


def _propose_par_reference(
    proposes: Sequence[ModelePropose], reference: str | None
) -> ModelePropose | None:
    """Modèle proposable désigné par une référence complète, sinon `None`."""
    if reference is None:
        return None
    try:
        moteur, cle = _decouper_reference(reference)
    except ValeurRefusee:
        return None
    for propose in proposes:
        if propose.moteur == moteur and propose.cle == cle:
            return propose
    return None


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
