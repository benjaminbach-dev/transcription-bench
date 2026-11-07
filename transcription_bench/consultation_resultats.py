"""Consultation des résultats enregistrés : liste et détail d'une transcription.

Tâches 7.1 et 7.2, format de stockage de D11. Ce module est **strictement en
lecture** : il ne crée, ne réécrit ni ne supprime aucun fichier, et n'appelle
aucun moteur.

**Source unique** : les exécutions sont relues dans `data/results/*/run.json` et
les transcriptions dans chaque `<n>-<audio>/result.json`. Les lectures passent
par `transcription_bench.stockage.lire_json`, qui prend le verrou commun de
stockage : une page ne lit pas un fichier pendant son remplacement atomique.

**Chemins contrôlés** : seuls les dossiers dont le nom a la forme d'un
identifiant produit par le programme sont interprétés ; un lien symbolique ou un
nom non conforme est ignoré à la liste et refusé au détail. Le dossier d'un audio
est résolu par `paths.resoudre_dans_racine`, qui refuse un chemin absolu, une
remontée `..` ou un lien sortant. Aucun accès hors de `data/results` n'est
possible.

**Refus explicites** : un `run.json` illisible, d'un `schema` inconnu,
incohérent avec son dossier ou portant un état hors des cinq états connus n'est
jamais interprété. La liste le présente comme non interprétable, sans lien, et le
détail répond par un refus (page 422), sans réécrire le fichier ni renvoyer 500.
Un dossier de résultat sans `run.json` (création interrompue) n'est pas une
exécution enregistrée : il est ignoré, comme le fait la récupération de 6.5.

**États et résultats partiels** : une exécution est affichée avec son état
(`running`, `completed`, `interrupted`, `abandoned`, `failed`) et marquée comme
partielle tant qu'elle n'est pas terminée. Les transcriptions déjà écrites
restent alors consultables et sont signalées comme partielles ; un audio sans
résultat est affiché comme non traité, jamais comme un texte vide ou une mesure
à zéro.

**Mesures** : une mesure absente (`null`, non numérique ou non finie) reste
absente et s'affiche « indisponible ». Le RTF est recalculé sur la durée
**décodée** par `resultats.calculer_rtf` : aucun RTF sur une durée nulle ou
absente, et le repère d'objectif (`REPERE_RTF`) n'exclut ni ne bloque jamais une
transcription plus lente.

**Marques** : les marques `factice`, `synthetique` et `mesures_simulees` sont
reprises telles quelles de `run.json` et de chaque `result.json`, et affichées
dans toutes les vues ; aucune n'est déduite.

**Comparaison (7.2)** : les transcriptions sont regroupées par l'empreinte
SHA-256 du fichier audio source, relue dans chaque `result.json`, et jamais par
le nom du fichier. Deux fichiers de même nom et d'empreintes différentes
forment donc deux groupes distincts, et une transcription dont l'empreinte est
absente ou invalide n'est jamais regroupée. Une comparaison ne réunit que des
transcriptions d'une même empreinte : toute sélection qui la mélangerait est
refusée, comme tout identifiant ou ordre hostile. Chaque entrée de groupe porte
les mesures de son audio, le matériel, la date et l'état consignés de l'essai :
ils restent lisibles sans le modèle local et ne sont jamais réécrits. Les
réglages demandés et les réglages effectifs de chaque audio sont comparés sur
leur valeur JSON brute — les valeurs formatées ne servent qu'à l'affichage :
listes et objets compris, une clé absente reste distincte d'une valeur
explicite nulle, et deux valeurs non finies restent distinctes entre elles.
Aucun diff de texte, aucun WER ni aucune référence ne sont calculés.

**Classement (2.1)** : les listes de résultats de chaque groupe audio se
classent par temps de transcription (défaut), pic mémoire, occupation CPU du
moteur ou date d'essai, sur les valeurs **non arrondies** de l'essai. Une valeur
absente ou incohérente vient après les valeurs valides, et les égalités sont
départagées par date décroissante (date inconnue en fin), puis identifiant
d'exécution décroissant et ordre audio croissant. Un critère inconnu ou fourni
plusieurs fois est refusé par `ValeurRefusee` ; la comparaison sélectionnée, elle,
garde l'ordre reçu, indépendamment de ce tri.

**Liste par audio (2.2)** : chaque transcription d'un groupe est une ligne
distincte, sans dédoublonnage : état, marques, date d'essai et réglages
distinctifs de ce résultat. Un réglage est distinctif quand sa valeur **brute**
diffère d'au moins une autre entrée de la même sous-liste ; une sous-liste d'une
seule entrée montre tous ses réglages consignés. Les résultats portant des
mesures simulées (`FACTICE`, `MESURES SIMULÉES`) forment une sous-liste séparée
dans chaque groupe audio : ils restent consultables et classables, mais ne
concourent jamais avec les mesures observées. `valeur_distinction` refuse en
outre toute distinction de performance à une mesure simulée ou à une exécution
partielle. Une transcription sans empreinte valide reste absente des groupes,
mais `lister` conserve toutes les exécutions de l'historique global, avec lien
vers leur détail.

**Cartes et synthèse (3.1)** : la comparaison sélectionnée expose, dans l'ordre
reçu, une carte par transcription : titre court (modèle, complété de
l'identifiant d'essai si deux cartes partagent le même modèle), trois
indicateurs de premier niveau (durée de transcription, pic mémoire du moteur
rapporté à la RAM totale consignée, occupation CPU moyenne rapportée aux
processeurs logiques consignés), annotation du pic mémoire cumulatif pour un
audio qui n'est pas le premier de sa demande, puis le texte complet. Une
synthèse décrit séparément les résultats observés les plus rapides et les moins
consommateurs de RAM, égalités comprises ; une mesure simulée ou un résultat
partiel est exclu de ces distinctions et nommé, et le CPU ne désigne aucun
vainqueur. `lignes` reste la matière exhaustive des détails, RTF et son repère
en détail compris.

**Détail individuel (3.2)** : le détail d'une exécution suit la même tête de
lecture qu'une carte de comparaison — trois indicateurs de premier niveau puis
le texte complet — avec les mêmes alertes visibles. Chaque audio transcrit
porte l'annotation de son pic mémoire cumulatif quand il n'est pas le premier de
sa demande, et une mention « matériel différent » ou « matériel non vérifié »
calculée sur les quatre champs requis (système d'exploitation, architecture,
processeurs logiques, RAM totale) comparés aux autres essais du même audio — et,
dans la comparaison, aux seules cartes comparées —, champ par champ : une
différence connue reste signalée même si un autre champ manque. Le nom du
processeur reste informatif et son absence seule ne déclenche rien. Les états
partiels, les erreurs et les marques restent hors de tout accordéon fermé. La
durée du lot n'est jamais présentée comme la durée d'un audio : la durée totale
de l'opération reste une mesure de l'exécution, dans ses propres détails.
"""

from __future__ import annotations

import json
import math
import re
from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from transcription_bench.indicateurs_resultats import formater_date_courte, ratio_cpu, ratio_ram
from transcription_bench.paths import (
    NOM_DOSSIER_RESULTATS,
    ValeurRefusee,
    resoudre_dans_racine,
    resoudre_resultat,
)
from transcription_bench.resultats import (
    ETAT_ABANDONNEE,
    ETAT_ECHOUEE,
    ETAT_EN_COURS,
    ETAT_INTERROMPUE,
    ETAT_TERMINEE,
    MOTIF_IDENTIFIANT,
    NOM_FICHIER_EXECUTION,
    NOM_FICHIER_RESULTAT,
    SCHEMA,
    STATUT_ERREUR,
    STATUT_NON_TRAITE,
    STATUT_OK,
    calculer_rtf,
)
from transcription_bench.stockage import JsonInvalide, lire_json

#: Repère d'objectif du RTF, affiché sans jamais bloquer ni exclure.
REPERE_RTF = 2

#: Empreinte SHA-256 d'un fichier audio source, en minuscules hexadécimales.
MOTIF_EMPREINTE = re.compile(r"[0-9a-f]{64}", re.ASCII)

#: Séparateur d'une sélection de comparaison : `identifiant:ordre`.
SEPARATEUR_SELECTION = ":"
_MOTIF_ORDRE = re.compile(r"[0-9]{1,6}", re.ASCII)

#: Nombre maximal de sélections `transcription` d'une même requête, pour la
#: comparaison comme pour la liste qui conserve les cases. Convention partagée :
#: appliquée avant analyse des valeurs de la liste et avant lecture des résultats
#: de la comparaison ; les doublons restent dédoublonnés sous cette borne.
SELECTIONS_MAX_COMPARAISON = 64

#: Critères de classement bornés des listes de résultats, avec leur libellé.
TRI_TEMPS = "temps"
TRI_RAM = "ram"
TRI_CPU = "cpu"
TRI_RECENT = "recent"
#: Tri par défaut : temps de transcription croissant.
TRI_DEFAUT = TRI_TEMPS
LIBELLES_TRI: dict[str, str] = {
    TRI_TEMPS: "Plus rapides",
    TRI_RAM: "Moins de RAM",
    TRI_CPU: "CPU le moins occupé",
    TRI_RECENT: "Plus récents",
}

#: Natures de cellule, qui décident du formatage dans le template.
NATURE_TEXTE = "texte"
NATURE_DETAIL = "detail"
NATURE_DUREE = "duree"
NATURE_OCTETS = "octets"
#: Texte transcrit, affiché tel quel dans un bloc préformaté, sans diff.
NATURE_TRANSCRIPTION = "transcription"
#: RTF, affiché avec le repère d'objectif non bloquant.
NATURE_RTF = "rtf"

LIBELLES_ETATS_EXECUTION: dict[str, str] = {
    ETAT_EN_COURS: "en cours",
    ETAT_TERMINEE: "terminée",
    ETAT_INTERROMPUE: "interrompue",
    ETAT_ABANDONNEE: "abandonnée",
    ETAT_ECHOUEE: "en échec",
}

LIBELLES_STATUTS_AUDIO: dict[str, str] = {
    STATUT_OK: "transcrit",
    STATUT_ERREUR: "erreur",
    STATUT_NON_TRAITE: "non traité",
}

#: Marques consignées, reprises telles quelles dans toutes les vues.
MARQUE_FACTICE = "FACTICE"
MARQUE_SYNTHETIQUE = "SYNTHÉTIQUE"
MARQUE_MESURES_SIMULEES = "MESURES SIMULÉES"
#: Marques qui signalent des mesures simulées, seules à ne jamais concourir avec
#: des mesures observées. `SYNTHÉTIQUE` seul ne suffit pas : un audio synthétique
#: peut être transcrit par un moteur réel, avec des mesures réelles.
MARQUES_MESURES_SIMULEES = frozenset({MARQUE_FACTICE, MARQUE_MESURES_SIMULEES})

MOTIF_NON_TRAITE = (
    "Audio non traité : aucun résultat n'a été enregistré (exécution non "
    "terminée, arrêt ou échec avant cet audio)"
)
MOTIF_RESULTAT_ABSENT = (
    "Aucun résultat enregistré pour cet audio : rien n'est affiché et aucune "
    "mesure n'est remplacée par zéro"
)
MOTIF_RESULTAT_ILLISIBLE = (
    "Résultat de l'audio illisible (JSON invalide ou fichier inaccessible) : "
    "rien n'est affiché et le fichier n'a pas été modifié"
)
MOTIF_DOSSIER_REFUSE = (
    "Dossier d'audio refusé (chemin hors du dossier de l'exécution) : aucun "
    "fichier n'est lu"
)
MOTIF_FICHIER_REFUSE = (
    "Fichier de résultat refusé (chemin hors du dossier de l'audio) : aucun "
    "fichier n'est lu"
)

#: Champs affichés, avec leur libellé et la conversion appliquée à la lecture.
#: Une valeur `None` s'affiche « indisponible » ; aucune n'est remplacée par 0.
CHAMPS_MODELE: tuple[tuple[str, str], ...] = (
    ("identifiant", "Identifiant demandé"),
    ("id_resolu", "Identifiant canonique"),
    ("commit", "Révision figée"),
    ("cle", "Clé locale"),
    ("fichier_gguf", "Variante GGUF"),
)
CHAMPS_MOTEUR: tuple[tuple[str, str], ...] = (
    ("identifiant", "Identifiant du moteur"),
    ("nom", "Nom du moteur"),
    ("empreinte_verrou", "Empreinte du verrou de dépendances du moteur"),
)
CHAMPS_MACHINE: tuple[tuple[str, str], ...] = (
    ("os", "Système d'exploitation"),
    ("version_os", "Version du système"),
    ("architecture", "Architecture"),
    ("processeur", "Processeur"),
    ("coeurs_physiques", "Cœurs physiques"),
    ("coeurs_logiques", "Cœurs logiques"),
    ("ram_totale_octets", "RAM totale (octets)"),
)

#: Champs du matériel consigné qui décident d'une mention « matériel différent »
#: ou « matériel non vérifié ». Le nom du processeur reste informatif : son
#: absence seule ne déclenche aucune alerte, et une différence connue reste
#: consultable dans les détails.
CHAMPS_MATERIEL_REQUIS: tuple[tuple[str, str], ...] = (
    ("os", "système d'exploitation"),
    ("architecture", "architecture"),
    ("coeurs_logiques", "processeurs logiques"),
    ("ram_totale_octets", "RAM totale"),
)
CHAMPS_PROGRAMME: tuple[tuple[str, str], ...] = (
    ("nom", "Programme"),
    ("version", "Version"),
    ("python", "Python"),
    ("empreinte_verrou", "Empreinte de uv.lock"),
    ("pyav", "PyAV"),
)
CHAMPS_PROCESSUS: tuple[tuple[str, str], ...] = (
    ("pid", "PID du moteur"),
    ("lance_a", "Lancé à"),
    ("code_sortie", "Code de sortie"),
)
CHAMPS_AUDIO: tuple[tuple[str, str], ...] = (
    ("nom", "Nom"),
    ("format", "Format"),
    ("taille_octets", "Taille (octets)"),
    ("empreinte_sha256", "Empreinte SHA-256"),
    ("duree_indicative_s", "Durée indicative (s)"),
    ("duree_decodee_s", "Durée décodée (s)"),
    ("echantillons", "Échantillons"),
)

#: Paire libellé / valeur affichable, sans objet imbriqué.
Paire = tuple[str, Any]


class LectureResultatsImpossible(RuntimeError):
    """Le dossier des résultats ne peut pas être listé (droits, E/S)."""


class ResultatIntrouvable(LookupError):
    """Aucune exécution enregistrée sous cet identifiant."""


class ResultatNonInterpretable(ValueError):
    """`run.json` illisible, d'un schéma inconnu ou incohérent : jamais interprété."""


@dataclass(frozen=True)
class ExecutionListee:
    """Ligne de la liste des exécutions, ou en-tête du détail.

    `exploitable` vaut `False` quand `run.json` n'a pas pu être interprété :
    seuls `identifiant` et `motif` sont alors renseignés ; aucune donnée n'est
    inventée et aucun lien de détail n'est proposé. `marques` vaut alors `None`
    (« indisponible »), à distinguer d'une exécution sans aucune marque (`()`).
    """

    identifiant: str
    etat: str | None
    libelle_etat: str
    cree_le: str | None
    modele: str | None
    moteur: str | None
    audios_traites: int | None
    audios_total: int | None
    duree_operation_s: float | None
    partiel: bool
    marques: tuple[str, ...] | None
    exploitable: bool
    motif: str | None


@dataclass(frozen=True)
class MesuresVue:
    """Mesures globales d'une exécution ; `None` = mesure indisponible."""

    duree_operation_s: float | None
    duree_processus_s: float | None
    duree_chargement_s: float | None
    pic_memoire_octets: int | None
    pic_memoire_partiel: bool | None


@dataclass(frozen=True)
class MesuresAudioVue:
    """Mesures d'une transcription ; `None` = mesure indisponible."""

    temps_decodage_s: float | None
    duree_transcription_s: float | None
    temps_cpu_s: float | None
    rtf: float | None
    pic_memoire_octets: int | None


@dataclass(frozen=True)
class IndicateursAudio:
    """Trois indicateurs de premier niveau d'un audio (tâches 3.1 et 3.2).

    Les valeurs brutes viennent de l'audio consigné et les ratios du matériel de
    son essai, jamais du poste qui consulte. `part_ram` et `occupation_cpu`
    valent `None` quand le ratio n'est pas interprétable (capacité absente,
    dénominateur nul ou ratio > 100 %), sans écraser la mesure brute
    disponible. Le formatage reste fait par le gabarit.
    """

    duree_transcription_s: float | int | None = None
    pic_memoire_octets: int | None = None
    ram_totale_octets: int | None = None
    temps_cpu_s: float | int | None = None
    part_ram: float | None = None
    occupation_cpu: float | None = None


def _indicateurs_audio(
    mesures: MesuresAudioVue | None, materiel: MaterielVue | None
) -> IndicateursAudio:
    """Indicateurs d'un audio, ratios compris, sans aucune valeur inventée.

    Utilisé par les cartes de comparaison et par le détail individuel : une même
    règle de lecture produit les deux vues. Une mesure absente reste `None` et
    aucune capacité locale n'est substituée au matériel consigné.
    """
    duree = None if mesures is None else mesures.duree_transcription_s
    pic = None if mesures is None else mesures.pic_memoire_octets
    temps_cpu = None if mesures is None else mesures.temps_cpu_s
    ram_totale = None if materiel is None else materiel.ram_totale_octets
    coeurs = None if materiel is None else materiel.coeurs_logiques
    return IndicateursAudio(
        duree_transcription_s=duree,
        pic_memoire_octets=pic,
        ram_totale_octets=ram_totale,
        temps_cpu_s=temps_cpu,
        part_ram=ratio_ram(pic, ram_totale),
        occupation_cpu=ratio_cpu(temps_cpu, duree, coeurs),
    )


@dataclass(frozen=True)
class MaterielVue:
    """Matériel consigné pour un essai ; `None` = valeur absente ou invalide.

    Ces valeurs viennent du `run.json` de l'exécution, jamais du poste qui
    consulte les résultats : elles servent aux ratios de lecture et à la
    détection d'un matériel différent. `os`, `architecture`, `coeurs_logiques`
    et `ram_totale_octets` sont les quatre champs requis pour cette détection ;
    `processeur` reste informatif et son absence seule n'est pas une alerte.
    Aucune valeur n'est remplacée par une mesure locale, ni par zéro.
    """

    os: str | None
    version_os: str | None
    architecture: str | None
    processeur: str | None
    coeurs_physiques: int | None
    coeurs_logiques: int | None
    ram_totale_octets: int | None


@dataclass(frozen=True)
class TimingsNatifVue:
    """Timings d'un appel natif, tels que transmis par le moteur.

    `unite` vient du moteur (`ms` ou `s`) et n'est jamais supposée. Une étape
    absente ou non finie reste `None` : aucune valeur n'est déduite d'une autre
    ni remplacée par zéro.
    """

    unite: str
    chargement: float | int | None
    mel: float | int | None
    encodage: float | int | None
    decodage: float | int | None


@dataclass(frozen=True)
class SegmentVue:
    """Segment horodaté fourni par le moteur.

    Une borne non finie (NaN, infini) est acceptée par le runner ; elle est
    conservée comme indisponible (`None`) sans masquer le texte du segment.
    """

    debut_s: float | None
    fin_s: float | None
    texte: str


@dataclass(frozen=True)
class TranscriptionVue:
    """Transcription relue dans le `result.json` d'un audio.

    `empreinte_sha256` est l'empreinte du fichier audio source, normalisée en
    minuscules ; elle vaut `None` quand la valeur consignée est absente ou n'a
    pas la forme d'un SHA-256. Les durées indicatives et décodées sont typées :
    une valeur absente ou non finie reste `None`, jamais zéro.

    Les réglages existent sous deux formes : `reglages` et `reglages_effectifs`
    sont les paires formatées pour l'affichage (listes et objets en JSON
    compact), tandis que `reglages_bruts` et `reglages_effectifs_bruts` gardent
    la valeur JSON telle qu'elle a été lue. La comparaison utilise les valeurs
    brutes : elle ne dépend donc jamais du formatage d'affichage.

    `timings_natifs` conserve les timings transmis par le moteur, un par appel
    natif et dans l'ordre des appels : ils varient par appel et ne sont jamais
    agrégés. Une transcription antérieure au champ n'en a aucun.
    """

    statut: str
    ecrit_le: str | None
    texte: str | None
    segments: tuple[SegmentVue, ...]
    marques: tuple[str, ...]
    audio: tuple[Paire, ...]
    empreinte_sha256: str | None
    duree_indicative_s: float | int | None
    duree_decodee_s: float | int | None
    mesures: MesuresAudioVue
    timings_natifs: tuple[TimingsNatifVue, ...]
    reglages: tuple[Paire, ...]
    reglages_bruts: Mapping[str, Any]
    reglages_effectifs: tuple[Paire, ...]
    reglages_effectifs_bruts: Mapping[str, Any]
    threads: tuple[Paire, ...]
    langue_imposee: str | None
    fenetre: tuple[Paire, ...]
    modele: tuple[Paire, ...]
    moteur: tuple[Paire, ...]
    famille: str | None
    erreur: str | None

    @property
    def simule_mesures(self) -> bool:
        """Vrai si une marque de mesures simulées est consignée pour ce résultat.

        Seules `FACTICE` et `MESURES SIMULÉES` comptent : `SYNTHÉTIQUE` seul ne
        dit rien du moteur ni des mesures, qui peuvent être réels.
        """
        return any(marque in MARQUES_MESURES_SIMULEES for marque in self.marques)


@dataclass(frozen=True)
class AudioVue:
    """Audio d'une exécution : transcription disponible ou motif d'absence.

    `indicateurs` porte les trois valeurs de premier niveau de cet audio (durée
    de transcription, pic mémoire, occupation CPU), jamais la durée du lot.
    `annotation_ram` signale un pic mémoire cumulatif quand cet audio n'est pas
    le premier de sa demande. `materiel_alerte` est la mention courte « matériel
    différent » ou « matériel non vérifié » calculée sur les quatre champs requis
    du matériel consigné ; `None` quand rien n'est à signaler et que le nom du
    processeur manque seul.
    """

    ordre: int
    nom: str
    dossier: str
    statut: str
    libelle_statut: str
    erreur: str | None
    partiel: bool
    motif_indisponible: str | None
    transcription: TranscriptionVue | None
    indicateurs: IndicateursAudio = IndicateursAudio()
    annotation_ram: str | None = None
    materiel_alerte: str | None = None


@dataclass(frozen=True)
class DetailExecutionVue:
    """Détail d'une exécution : métadonnées, mesures globales et audios."""

    execution: ExecutionListee
    fin: str | None
    erreur: str | None
    famille: str | None
    threads_demandes: Any
    threads_appliques: Any
    fenetre_fixe_s: Any
    reglages: tuple[Paire, ...]
    reglages_effectifs: tuple[Paire, ...]
    modele: tuple[Paire, ...]
    moteur: tuple[Paire, ...]
    versions_moteur: tuple[Paire, ...]
    machine: tuple[Paire, ...]
    programme: tuple[Paire, ...]
    processus: tuple[Paire, ...]
    mesures: MesuresVue
    audios: tuple[AudioVue, ...]
    partiel: bool
    libelle_modele: str = "modèle non consigné"

    @property
    def simule_mesures(self) -> bool:
        """Vrai si l'exécution porte une marque de mesures simulées.

        `SYNTHÉTIQUE` seul n'en fait pas partie : un audio synthétique peut être
        transcrit par un moteur réel, avec des mesures réelles.
        """
        marques = self.execution.marques or ()
        return any(marque in MARQUES_MESURES_SIMULEES for marque in marques)


@dataclass(frozen=True)
class EntreeEmpreinte:
    """Transcription rattachée à l'empreinte SHA-256 de son audio source.

    `partiel` signale une exécution non terminée ; `marques` réunit celles de
    l'exécution et celles du résultat, sans doublon et sans en déduire aucune.

    `mesures` sont celles de cet audio, telles que consignées dans son
    `result.json`. `materiel`, `date_essai` (le `cree_le` de l'exécution) et
    `etat` (l'état brut de l'exécution, en plus de `libelle_etat`) viennent du
    `run.json` : ils décrivent l'essai consigné, jamais le poste qui consulte,
    et restent disponibles même si le modèle local a été supprimé. Ces champs
    sont renseignés à la lecture pour un tri ou un ratio ultérieur ; aucune
    valeur n'est réécrite dans les fichiers de résultat.

    Les quatre champs de contexte ont une valeur par défaut pour qu'une entrée
    construite hors de ce module reste valide. À la lecture, `mesures` et
    `materiel` sont des objets dont les champs inconnus valent `None` ; une
    entrée construite manuellement peut aussi laisser ces objets à `None`.

    `reglages` reprend les réglages consignés de ce résultat, formatés pour
    l'affichage, tandis que `reglages_bruts` garde leurs valeurs JSON : c'est la
    valeur brute, et elle seule, qui décide quels réglages sont distinctifs dans
    une sous-liste. `reglages_distinctifs` est le sous-ensemble affiché : il est
    calculé à la lecture du groupe concerné, jamais réécrit dans les fichiers.

    `simule` est vrai dès qu'une marque de mesures simulées est consignée :
    aucune déduction n'est faite depuis la famille, le moteur ou le modèle.
    """

    execution: str
    ordre: int
    nom: str
    empreinte: str
    statut: str
    libelle_statut: str
    libelle_etat: str
    partiel: bool
    marques: tuple[str, ...]
    modele: str | None
    moteur: str | None
    mesures: MesuresAudioVue | None = None
    materiel: MaterielVue | None = None
    date_essai: str | None = None
    etat: str | None = None
    reglages: tuple[Paire, ...] = ()
    reglages_bruts: Mapping[str, Any] = field(default_factory=dict)
    reglages_distinctifs: tuple[Paire, ...] = ()
    # Variante GGUF consignée du modèle (`result.json`), `None` si absente.
    variante: str | None = None
    # Révision figée du modèle (`result.json`, « Révision figée »), `None` si absente.
    revision: str | None = None
    # Durée décodée de CET audio : jamais une durée commune supposée.
    duree_decodee_s: float | int | None = None
    # Mention de matériel comparée aux autres essais du même audio.
    materiel_alerte: str | None = None

    @property
    def indicateurs(self) -> IndicateursAudio:
        """Trois indicateurs de premier niveau de cet essai, ratios compris."""
        return _indicateurs_audio(self.mesures, self.materiel)

    @property
    def annotation_ram(self) -> str | None:
        """Annotation du pic mémoire cumulatif, `None` pour le premier audio."""
        return _annotation_ram(self.ordre)

    @property
    def simule(self) -> bool:
        """Vrai si le résultat ou son exécution porte des mesures simulées.

        La réponse vient uniquement des marques consignées : `FACTICE` ou
        `MESURES SIMULÉES`. `SYNTHÉTIQUE` seul ne suffit pas, et rien n'est
        déduit du moteur, de la famille ou des valeurs mesurées.
        """
        return any(marque in MARQUES_MESURES_SIMULEES for marque in self.marques)


@dataclass(frozen=True)
class GroupeEmpreinte:
    """Transcriptions d'un même fichier audio, quelle que soit l'exécution.

    `noms` réunit les noms d'audios consignés par ces transcriptions : un même
    contenu déposé sous plusieurs noms apparaît donc dans un seul groupe.

    `entrees` conserve **toutes** les transcriptions du groupe, sans
    dédoublonnage : les résultats observés d'abord, puis ceux qui portent des
    mesures simulées, chacune des deux parties classée par le critère demandé.
    Les propriétés `entrees_reelles` et `entrees_simulees` donnent ces deux
    sous-listes dérivées : les mesures simulées y sont séparées des mesures
    observées et ne concourent jamais avec elles.
    """

    empreinte: str
    noms: tuple[str, ...]
    entrees: tuple[EntreeEmpreinte, ...]

    @property
    def entrees_reelles(self) -> tuple[EntreeEmpreinte, ...]:
        """Résultats observés, dans l'ordre de classement de leur sous-liste."""
        return tuple(entree for entree in self.entrees if not entree.simule)

    @property
    def entrees_simulees(self) -> tuple[EntreeEmpreinte, ...]:
        """Résultats à mesures simulées, classés à part des résultats réels."""
        return tuple(entree for entree in self.entrees if entree.simule)

    @property
    def duree_decodee_commune_s(self) -> float | int | None:
        """Durée décodée commune à tout le groupe, ou `None`.

        Une valeur n'est commune que si chaque essai la consigne à l'identique :
        une durée divergente ou partiellement absente ne donne jamais une fausse
        durée commune.
        """
        durees = {entree.duree_decodee_s for entree in self.entrees}
        return next(iter(durees)) if len(durees) == 1 else None

    @property
    def durees_divergentes(self) -> bool:
        """Vrai si les essais du groupe ne consignent pas tous la même durée."""
        return len({entree.duree_decodee_s for entree in self.entrees}) > 1


@dataclass(frozen=True)
class CelluleComparaison:
    """Valeur d'une cellule de comparaison.

    `presente` vaut `False` quand la clé est absente du fichier : une clé
    absente n'est pas une valeur explicite nulle, et cette distinction est
    conservée jusqu'à l'affichage. `valeur` est la valeur affichable (une liste
    ou un objet y sont déjà formatés en JSON compact), tandis que `brut` est la
    valeur JSON d'origine : c'est elle, et elle seule, qui décide si deux
    cellules diffèrent. Une liste `[0, 0.2]` ne peut donc pas être confondue
    avec la chaîne `"[0,0.2]"`, ni un objet avec sa représentation textuelle.
    """

    presente: bool
    valeur: Any
    brut: Any


@dataclass(frozen=True)
class LigneComparaison:
    """Ligne de la table de comparaison, une cellule par transcription.

    `nature` vaut `texte`, `transcription`, `duree`, `octets`, `rtf` ou
    `detail` (provenance technique exclue du résumé des différences) :
    le formatage reste fait par le template, qui ne reçoit aucune chaîne déjà
    formatée pour une mesure. Pour `transcription`, la cellule porte le texte
    transcrit, affiché dans un bloc préformaté et jamais comparé. `differents`
    vaut `True` dès qu'une cellule diffère des autres sur sa valeur brute.
    """

    libelle: str
    nature: str
    cellules: tuple[CelluleComparaison, ...]
    differents: bool


@dataclass(frozen=True)
class CarteComparaison:
    """Carte de premier niveau d'une transcription comparée (tâche 3.1).

    `libelle` est le titre court de la carte : le modèle consigné, complété de
    l'identifiant d'essai quand deux cartes portent le même modèle. Les trois
    indicateurs sont les valeurs **brutes** de l'essai, accompagnées des ratios
    calculés sur le matériel consigné : le formatage reste fait par le gabarit.
    `part_ram` et `occupation_cpu` valent `None` quand le ratio n'est pas
    interprétable (capacité absente, dénominateur nul ou ratio > 100 %), sans
    jamais écraser la mesure brute disponible.

    `annotation_ram` signale, pour un audio qui n'est pas le premier de sa
    demande, que le pic mémoire est cumulatif et peut provenir d'un audio
    précédent. `materiel_alerte` porte la mention « matériel différent » ou
    « matériel non vérifié » calculée sur les quatre champs requis, comparés
    **aux seules cartes comparées** et jamais à tout l'historique des essais :
    les valeurs restent ainsi visibles sans ouvrir les détails. `texte` est le
    texte transcrit tel quel, jamais comparé.
    """

    entree: EntreeEmpreinte
    libelle: str
    texte: str | None
    duree_transcription_s: float | int | None
    pic_memoire_octets: int | None
    ram_totale_octets: int | None
    temps_cpu_s: float | int | None
    part_ram: float | None
    occupation_cpu: float | None
    annotation_ram: str | None
    materiel_alerte: str | None = None
    erreur: str | None = None

    @property
    def indicateurs(self) -> IndicateursAudio:
        """Mêmes trois indicateurs, sous la forme partagée par les gabarits."""
        return IndicateursAudio(
            duree_transcription_s=self.duree_transcription_s,
            pic_memoire_octets=self.pic_memoire_octets,
            ram_totale_octets=self.ram_totale_octets,
            temps_cpu_s=self.temps_cpu_s,
            part_ram=self.part_ram,
            occupation_cpu=self.occupation_cpu,
        )


@dataclass(frozen=True)
class SyntheseComparaison:
    """Synthèse descriptive des mesures observées, sans score global.

    `plus_rapides` et `moins_de_ram` nomment les cartes de tête, égalités
    comprises ; un tuple vide signifie qu'aucune distinction n'est attribuée
    faute d'au moins deux mesures comparables. `exclues` nomme les cartes sans
    distinction de performance réelle : mesures simulées ou résultat partiel.
    Le CPU n'est jamais présenté comme un vainqueur.
    """

    plus_rapides: tuple[str, ...] = ()
    moins_de_ram: tuple[str, ...] = ()
    exclues: tuple[str, ...] = ()


@dataclass(frozen=True)
class ComparaisonVue:
    """Comparaison côte à côte de transcriptions d'un même fichier audio.

    `factice` et `partiel` signalent que la comparaison porte au moins une
    transcription factice ou issue d'une exécution non terminée.

    `cartes` porte, dans l'ordre reçu, les cartes de premier niveau : titre,
    trois indicateurs, annotation RAM conditionnelle et texte complet. `lignes`
    reste la matière exhaustive des détails (« Ce qui diffère » puis « Toutes
    les mesures et informations »), et `synthese` la description courte des
    temps et des pics mémoire observés.
    """

    empreinte: str
    noms: tuple[str, ...]
    colonnes: tuple[EntreeEmpreinte, ...]
    lignes: tuple[LigneComparaison, ...]
    factice: bool
    partiel: bool
    cartes: tuple[CarteComparaison, ...] = ()
    synthese: SyntheseComparaison = field(default_factory=SyntheseComparaison)


@dataclass(frozen=True)
class _Colonne:
    """Colonne de comparaison : entrée, transcription relue et mesures du lot."""

    entree: EntreeEmpreinte
    transcription: TranscriptionVue
    mesures: MesuresVue
    contexte: Mapping[str, Any] = field(default_factory=dict)


class ConsultationResultats:
    """Lectures des résultats d'un dossier de données, sans aucune écriture.

    `donnees` est la racine `data/` ; le dossier des résultats est
    `donnees/results`. Les méthodes ne lèvent pour un fichier de résultat
    qu'aux endroits prévus : la liste ne lève jamais pour une exécution
    illisible, et le détail lève `ResultatNonInterpretable`.
    """

    def __init__(self, donnees: Path | str) -> None:
        self._donnees = Path(donnees)

    @property
    def dossier_resultats(self) -> Path:
        """Dossier des résultats attendu, qu'il existe ou non."""
        return self._donnees / NOM_DOSSIER_RESULTATS

    def lister(self) -> tuple[ExecutionListee, ...]:
        """Exécutions enregistrées, des plus récentes aux plus anciennes.

        L'ordre suit l'identifiant, qui commence par l'horodatage de création.
        Un dossier au nom non conforme, un lien symbolique ou un dossier sans
        `run.json` est ignoré. Une exécution dont le `run.json` est illisible,
        d'un schéma inconnu ou incohérent est listée comme non interprétable,
        sans empêcher l'affichage des autres. Lève `LectureResultatsImpossible`
        si le dossier des résultats existe mais ne peut pas être parcouru.
        """
        entrees = self._entrees_resultats()
        executions: list[ExecutionListee] = []
        for entree in entrees:
            if not MOTIF_IDENTIFIANT.fullmatch(entree.name):
                continue
            try:
                lecture = self._lire(entree.name)
            except ResultatIntrouvable:
                continue
            except ValeurRefusee:
                # Nom ou lien sortant : ce n'est pas une exécution enregistrée.
                continue
            except ResultatNonInterpretable as refus:
                executions.append(_execution_non_interpretable(entree.name, str(refus)))
                continue
            if lecture is not None:
                executions.append(_resume(lecture[1]))
        return tuple(executions)

    def detail(self, identifiant: str) -> DetailExecutionVue:
        """Détail d'une exécution, transcriptions déjà écrites comprises.

        Lève `ValeurRefusee` pour un identifiant de chemin hostile,
        `ResultatIntrouvable` s'il n'y a pas d'exécution enregistrée sous ce
        nom, et `ResultatNonInterpretable` si son `run.json` n'est pas
        interprétable. Aucun fichier n'est modifié dans tous les cas.

        Les audios portent leurs trois indicateurs, l'annotation du pic mémoire
        cumulatif et une mention de matériel calculée sur les quatre champs
        requis, comparés aux autres essais du même audio quand ils existent :
        cette lecture supplémentaire, en lecture seule, ne rend jamais la page
        illisible et n'écrit aucun fichier.
        """
        lecture = self._lire(identifiant)
        if lecture is None:
            raise ResultatIntrouvable(f"exécution inconnue : {identifiant!r}")
        dossier, contenu = lecture
        execution = _resume(contenu)
        demande = _mapping(contenu.get("demande"))
        modele = _mapping(demande.get("modele"))
        moteur = _mapping(contenu.get("moteur"))
        mesure = _mapping(contenu.get("mesures"))
        effectifs = _mapping(contenu.get("effectifs"))
        partiel = contenu["etat"] != ETAT_TERMINEE
        materiel = _materiel(contenu)
        autres = self._materiels_par_empreinte(identifiant)
        return DetailExecutionVue(
            execution=execution,
            fin=_texte(contenu.get("fin")),
            erreur=_texte(contenu.get("erreur")),
            famille=_texte(demande.get("famille")),
            threads_demandes=_entier(demande.get("threads_demandes")),
            threads_appliques=_entier(effectifs.get("threads_appliques")),
            fenetre_fixe_s=_nombre(demande.get("fenetre_fixe_secondes")),
            reglages=_paires_reglages(demande.get("reglages")),
            reglages_effectifs=_paires_reglages(effectifs.get("reglages_effectifs")),
            modele=_paires(modele, CHAMPS_MODELE),
            moteur=_paires(moteur, CHAMPS_MOTEUR),
            versions_moteur=_paires_versions(moteur.get("versions")),
            machine=_paires(_mapping(contenu.get("machine")), CHAMPS_MACHINE),
            programme=_paires_programme(_mapping(contenu.get("programme"))),
            processus=_paires(
                _mapping(contenu.get("processus_moteur")), CHAMPS_PROCESSUS
            ),
            mesures=_mesures_execution(mesure),
            audios=tuple(
                _audio(dossier, plan, partiel=partiel, materiel=materiel, autres=autres)
                for plan in contenu["audios"]
            ),
            partiel=partiel,
            libelle_modele=_libelle_modele(execution.modele),
        )

    def _materiels_par_empreinte(
        self, sauf: str | None = None
    ) -> dict[str, tuple[MaterielVue, ...]]:
        """Matériel consigné des autres essais, par empreinte d'audio source.

        Sert au détail individuel pour signaler un matériel différent ou non
        vérifié sur le même audio. L'essai `sauf` est ignoré : son matériel est
        déjà connu de l'appelant. Une empreinte absente ou invalide n'est jamais
        devinée ; un dossier des résultats illisible rend seulement la
        comparaison indisponible, sans faire échouer la page et sans écriture.
        """
        try:
            executions = tuple(self._executions_interpretables())
        except LectureResultatsImpossible:
            return {}
        materiels: dict[str, list[MaterielVue]] = {}
        for dossier, contenu in executions:
            if dossier.name == sauf:
                continue
            materiel = _materiel(contenu)
            for plan in contenu["audios"]:
                transcription, _motif = _lire_transcription(dossier, plan)
                if transcription is None:
                    continue
                empreinte = transcription.empreinte_sha256
                if empreinte is None:
                    continue
                materiels.setdefault(empreinte, []).append(materiel)
        return {cle: tuple(valeurs) for cle, valeurs in materiels.items()}

    def groupes_par_empreinte(
        self, tri: str = TRI_DEFAUT
    ) -> tuple[GroupeEmpreinte, ...]:
        """Transcriptions regroupées par empreinte SHA-256 de l'audio source.

        Une transcription n'est groupée que si son `result.json` est
        interprétable et consigne une empreinte valide : un résultat absent, une
        empreinte absente ou d'une autre forme n'apparaît dans aucun groupe et
        n'est donc jamais comparable. Deux fichiers de même nom et d'empreintes
        différentes forment deux groupes distincts. Les groupes sont ordonnés par
        leur essai le plus récent, quel que soit `tri` : le critère ne classe que
        les essais à l'intérieur de chaque groupe. Une exécution refusée est
        ignorée. Chaque groupe conserve toutes ses transcriptions, sans
        dédoublonnage : les résultats observés d'abord, puis les mesures
        simulées, chacun des deux ensembles classé par `tri` (`temps` par défaut)
        selon `trier_entrees`.

        Lève `ValeurRefusee` pour un critère de classement inconnu, et
        `LectureResultatsImpossible` si le dossier des résultats existe mais ne
        peut pas être parcouru.
        """
        if tri not in LIBELLES_TRI:
            raise ValeurRefusee(
                "tri refusé : critère inconnu (temps, ram, cpu ou recent attendu)"
            )
        groupes: dict[str, list[EntreeEmpreinte]] = {}
        for dossier, contenu in self._executions_interpretables():
            execution = _resume(contenu)
            materiel = _materiel(contenu)
            for plan in contenu["audios"]:
                transcription, _motif = _lire_transcription(dossier, plan)
                if transcription is None:
                    continue
                empreinte = transcription.empreinte_sha256
                if empreinte is None:
                    continue
                groupes.setdefault(empreinte, []).append(
                    _entree(execution, plan, transcription, empreinte, materiel)
                )
        groupes_recents = sorted(
            groupes.items(), key=lambda paire: _cle_recence(paire[1]), reverse=True
        )
        return tuple(
            GroupeEmpreinte(
                empreinte=empreinte,
                noms=tuple(sorted({entree.nom for entree in entrees})),
                entrees=_entrees_du_groupe(_avec_alerte_materiel(entrees), tri),
            )
            for empreinte, entrees in groupes_recents
        )

    def comparer(
        self, empreinte: str, selections: Sequence[tuple[str, int]]
    ) -> ComparaisonVue:
        """Comparaison côte à côte de transcriptions d'une même empreinte.

        `selections` est une suite de couples `(identifiant d'exécution, ordre
        d'audio)`, tels que décodés par `analyser_selection` ; un doublon est
        retiré. Au-delà de `SELECTIONS_MAX_COMPARAISON` valeurs reçues, la
        comparaison est refusée avant toute lecture. Lève `ValeurRefusee` si
        l'empreinte demandée n'est pas un
        SHA-256 valide, si moins de deux transcriptions distinctes sont
        sélectionnées, si une transcription sélectionnée n'a pas d'empreinte
        valide ou si son empreinte diffère de celle demandée : aucun mélange de
        fichiers audio n'est comparé. Lève `ResultatIntrouvable` si une
        sélection ne désigne pas une transcription enregistrée, et
        `ResultatNonInterpretable` si un fichier de suivi concerné est refusé.
        Aucun fichier n'est modifié.
        """
        empreinte_valide = _empreinte(empreinte)
        if empreinte_valide is None:
            raise ValeurRefusee("empreinte SHA-256 invalide : comparaison refusée")
        if len(selections) > SELECTIONS_MAX_COMPARAISON:
            raise ValeurRefusee(
                f"sélections refusées : {SELECTIONS_MAX_COMPARAISON} au maximum par "
                "comparaison"
            )
        choix: list[tuple[str, int]] = []
        for selection in selections:
            if selection not in choix:
                choix.append(selection)
        if len(choix) < 2:
            raise ValeurRefusee(
                "au moins deux transcriptions différentes sont nécessaires"
            )
        colonnes = tuple(
            self._colonne_comparaison(identifiant, ordre, empreinte_valide)
            for identifiant, ordre in choix
        )
        entrees = tuple(colonne.entree for colonne in colonnes)
        cartes = _cartes_comparaison(colonnes)
        return ComparaisonVue(
            empreinte=empreinte_valide,
            noms=tuple(sorted({entree.nom for entree in entrees})),
            colonnes=entrees,
            lignes=_lignes_comparaison(colonnes),
            factice=any("FACTICE" in entree.marques for entree in entrees),
            partiel=any(entree.partiel for entree in entrees),
            cartes=cartes,
            synthese=_synthese_comparaison(cartes),
        )

    # -- lecture -------------------------------------------------------------

    def _executions_interpretables(self) -> Iterator[tuple[Path, Mapping[str, Any]]]:
        """Exécutions dont `run.json` est interprétable, les autres ignorées."""
        for entree in self._entrees_resultats():
            if not MOTIF_IDENTIFIANT.fullmatch(entree.name):
                continue
            try:
                lecture = self._lire(entree.name)
            except (ResultatIntrouvable, ResultatNonInterpretable, ValeurRefusee):
                continue
            if lecture is not None:
                yield lecture

    def _colonne_comparaison(
        self, identifiant: str, ordre: int, empreinte: str
    ) -> _Colonne:
        """Colonne d'une sélection, refusée si elle mélange les empreintes."""
        lecture = self._lire(identifiant)
        if lecture is None:
            raise ResultatIntrouvable(f"exécution inconnue : {identifiant!r}")
        dossier, contenu = lecture
        plan = next(
            (candidat for candidat in contenu["audios"] if candidat["ordre"] == ordre),
            None,
        )
        if plan is None:
            raise ResultatIntrouvable(
                f"audio {ordre} inconnu dans l'exécution {identifiant!r}"
            )
        transcription, _motif = _lire_transcription(dossier, plan)
        if transcription is None:
            raise ResultatIntrouvable(
                f"aucun résultat enregistré pour l'audio {ordre} de {identifiant!r}"
            )
        if transcription.empreinte_sha256 is None:
            raise ValeurRefusee(
                "empreinte SHA-256 absente ou invalide : comparaison refusée"
            )
        if transcription.empreinte_sha256 != empreinte:
            raise ValeurRefusee(
                "empreintes différentes : la comparaison ne mélange pas deux "
                "fichiers audio"
            )
        return _Colonne(
            entree=_entree(
                _resume(contenu), plan, transcription, empreinte, _materiel(contenu)
            ),
            transcription=transcription,
            mesures=_mesures_execution(_mapping(contenu.get("mesures"))),
            contexte=contenu,
        )

    def _entrees_resultats(self) -> tuple[Path, ...]:
        """Entrées du dossier des résultats, des plus récentes aux plus anciennes.

        Lève `LectureResultatsImpossible` si le dossier existe mais ne peut pas
        être parcouru ; renvoie un tuple vide s'il n'existe pas encore.
        """
        try:
            return tuple(
                sorted(
                    self.dossier_resultats.iterdir(),
                    key=lambda entree: entree.name,
                    reverse=True,
                )
            )
        except FileNotFoundError:
            return ()
        except OSError as erreur:
            raise LectureResultatsImpossible(
                f"dossier des résultats illisible : {_message(erreur)}"
            ) from None

    def _lire(self, identifiant: str) -> tuple[Path, Mapping[str, Any]] | None:
        """Lit et valide `run.json` ; `None` s'il n'existe pas.

        Lève `ValeurRefusee` pour une forme de chemin refusée,
        `ResultatIntrouvable` si le dossier n'est pas une exécution enregistrée
        (absent, lien symbolique ou nom non conforme), et
        `ResultatNonInterpretable` pour un contenu illisible ou incohérent.
        """
        if not isinstance(identifiant, str) or not identifiant:
            raise ValeurRefusee("identifiant de résultat attendu sous forme de texte")
        dossier = resoudre_resultat(identifiant, self._donnees)
        if not MOTIF_IDENTIFIANT.fullmatch(identifiant):
            raise ResultatIntrouvable(f"exécution inconnue : {identifiant!r}")
        entree = dossier.parent / identifiant
        if entree.is_symlink() or not entree.is_dir():
            raise ResultatIntrouvable(f"exécution inconnue : {identifiant!r}")
        try:
            # Le fichier lui-même est confiné : un `run.json` qui serait un lien
            # sortant n'est pas lu.
            chemin = resoudre_dans_racine(dossier, NOM_FICHIER_EXECUTION)
        except ValeurRefusee:
            raise ResultatNonInterpretable(
                "run.json hors du dossier de l'exécution"
            ) from None
        try:
            contenu = lire_json(chemin)
        except JsonInvalide:
            raise ResultatNonInterpretable("run.json illisible (JSON invalide)") from None
        except OSError:
            raise ResultatNonInterpretable("run.json inaccessible") from None
        if contenu is None:
            return None
        _valider_execution(contenu, identifiant)
        return dossier, contenu


# -- comparaison : sélection, entrées et lignes -------------------------------


def analyser_selection(texte: str) -> tuple[str, int]:
    """Décode une sélection de comparaison `identifiant:ordre`.

    Refuse par `ValeurRefusee` toute autre forme : chemin absolu, séparateur
    Windows, remontée `..`, identifiant hors du format produit par le programme
    ou ordre non numérique. La sélection n'est jamais interprétée avant ce
    contrôle, et la résolution de chemin reste faite par `resoudre_resultat`.
    """
    if not isinstance(texte, str):
        raise ValeurRefusee("sélection de comparaison attendue sous forme de texte")
    identifiant, separateur, ordre = texte.partition(SEPARATEUR_SELECTION)
    if not separateur or SEPARATEUR_SELECTION in ordre:
        raise ValeurRefusee(
            "sélection refusée : forme 'identifiant d'exécution:ordre d'audio' attendue"
        )
    if not MOTIF_IDENTIFIANT.fullmatch(identifiant):
        raise ValeurRefusee("sélection refusée : identifiant d'exécution invalide")
    if not _MOTIF_ORDRE.fullmatch(ordre) or int(ordre) < 1:
        raise ValeurRefusee("sélection refusée : ordre d'audio invalide")
    return identifiant, int(ordre)


def analyser_tri(valeurs: Sequence[str] | str, defaut: str = TRI_DEFAUT) -> str:
    """Critère de classement demandé, borné aux quatre critères connus.

    Une demande absente vaut `defaut` (temps de transcription par défaut ; la
    page Résultats emploie `recent`). Un critère inconnu, vide ou fourni
    plusieurs fois est refusé par `ValeurRefusee` : la lecture ne choisit jamais
    un critère parmi plusieurs et ne devine rien.
    """
    demandes = (valeurs,) if isinstance(valeurs, str) else tuple(valeurs)
    if not demandes:
        return defaut
    if len(demandes) > 1:
        raise ValeurRefusee("tri refusé : un seul critère de classement attendu")
    if demandes[0] not in LIBELLES_TRI:
        raise ValeurRefusee(
            "tri refusé : critère inconnu (temps, ram, cpu ou recent attendu)"
        )
    return demandes[0]


def trier_entrees(
    entrees: Sequence[EntreeEmpreinte], tri: str = TRI_DEFAUT
) -> tuple[EntreeEmpreinte, ...]:
    """Entrées classées par `tri`, avec un départage stable et documenté.

    Le tri porte sur les valeurs consignées et **non arrondies** : durées et
    pics bruts, ratio CPU recalculé. Une valeur absente ou incohérente (`None`,
    non numérique, non finie, ratio non interprétable) vient après
    les valeurs valides. Les égalités sont départagées par date d'essai
    décroissante (date inconnue après les dates connues), puis identifiant
    d'exécution décroissant et ordre audio croissant. `recent` classe par date
    décroissante avec le même départage. La séquence reçue n'est pas modifiée.

    Lève `ValeurRefusee` pour un critère hors des quatre admis.
    """
    if tri not in LIBELLES_TRI:
        raise ValeurRefusee(
            "tri refusé : critère inconnu (temps, ram, cpu ou recent attendu)"
        )
    ordonnees = sorted(entrees, key=lambda entree: entree.ordre)
    # Tris stables successifs, du départage le moins prioritaire au plus
    # prioritaire : identifiant, date, puis critère (ou date seule pour `recent`).
    ordonnees.sort(key=lambda entree: entree.execution, reverse=True)
    ordonnees.sort(key=lambda entree: _horodatage(entree.date_essai), reverse=True)
    if tri != TRI_RECENT:
        ordonnees.sort(key=lambda entree: _cle_classement(entree, tri))
    return tuple(ordonnees)


def valeur_distinction(entree: EntreeEmpreinte, tri: str) -> float | None:
    """Valeur utilisable pour une distinction de performance réelle.

    Une mesure simulée (`FACTICE`, `MESURES SIMULÉES`) ou un résultat partiel ne
    reçoit **jamais** de distinction de performance réelle, quelle que soit la
    valeur consignée : `None` est alors renvoyé. Ces entrées restent consultables
    et classables par ailleurs, et leur état reste visible. Sinon, la valeur est
    celle, non arrondie, du critère de mesure demandé.

    Lève `ValeurRefusee` pour un critère inconnu ou pour `recent` : une date
    d'essai n'est pas une mesure de performance.
    """
    if tri not in LIBELLES_TRI:
        raise ValeurRefusee(
            "distinction refusée : critère inconnu (temps, ram ou cpu attendu)"
        )
    if tri == TRI_RECENT:
        raise ValeurRefusee(
            "distinction refusée : une date n'est pas une mesure de performance"
        )
    if entree.simule or entree.partiel:
        return None
    return _valeur_classement(entree, tri)


def _horodatage(valeur: Any) -> tuple[int, float]:
    """Clé de date triable avec `reverse=True` : connue (`1`) avant inconnue.

    Une date connue est convertie en horodatage pour comparer des fuseaux
    différents ; une date absente, non textuelle ou non ISO reste inconnue
    (`0`) et passe donc après les dates connues. Aucune date n'est inventée.
    """
    if not isinstance(valeur, str):
        return (0, 0.0)
    try:
        date = datetime.fromisoformat(valeur)
    except ValueError:
        return (0, 0.0)
    if date.tzinfo is None:
        date = date.replace(tzinfo=timezone.utc)
    try:
        return (1, date.timestamp())
    except (OverflowError, OSError, ValueError):
        return (0, 0.0)


def _cle_classement(entree: EntreeEmpreinte, tri: str) -> tuple[int, float]:
    """Clé du critère : valeurs valides d'abord, absentes ou incohérentes après."""
    valeur = _valeur_classement(entree, tri)
    return (1, 0.0) if valeur is None else (0, valeur)


def _valeur_classement(entree: EntreeEmpreinte, tri: str) -> float | None:
    """Valeur non arrondie du critère, ou `None` si elle n'est pas interprétable.

    Le temps de transcription et le pic mémoire doivent être positifs ou nuls ; le ratio CPU vient de `ratio_cpu` et reste `None` quand une
    capacité consignée manque ou que le ratio dépasse 100 %. Le matériel lu est
    celui de l'essai, jamais celui du poste qui consulte.
    """
    mesures = entree.mesures
    if mesures is None:
        return None
    if tri == TRI_TEMPS:
        return _mesure_triable(mesures.duree_transcription_s)
    if tri == TRI_RAM:
        return _mesure_triable(mesures.pic_memoire_octets)
    if tri != TRI_CPU:
        return None
    coeurs = None if entree.materiel is None else entree.materiel.coeurs_logiques
    ratio = ratio_cpu(mesures.temps_cpu_s, mesures.duree_transcription_s, coeurs)
    return None if ratio is None else float(ratio)


def _mesure_triable(valeur: Any) -> float | None:
    """Nombre fini triable, ou `None` : booléens, NaN, infinis et négatifs exclus."""
    if isinstance(valeur, bool) or not isinstance(valeur, (int, float)):
        return None
    try:
        nombre = float(valeur)
    except OverflowError:
        return None
    if not math.isfinite(nombre) or nombre < 0:
        return None
    return nombre


def _entree(
    execution: ExecutionListee,
    plan: Mapping[str, Any],
    transcription: TranscriptionVue,
    empreinte: str,
    materiel: MaterielVue | None = None,
) -> EntreeEmpreinte:
    """Entrée de comparaison d'une transcription déjà relue.

    Les mesures sont celles de cet audio et le matériel celui de l'essai :
    rien n'est déduit du poste courant ni d'un autre audio de l'exécution. Les
    réglages consignés de ce résultat sont repris pour l'affichage et pour le
    calcul ultérieur des réglages distinctifs de sa sous-liste.
    """
    reglages, reglages_bruts = _reglages_entree(transcription)
    return EntreeEmpreinte(
        execution=execution.identifiant,
        ordre=plan["ordre"],
        nom=plan["nom"],
        empreinte=empreinte,
        statut=transcription.statut,
        libelle_statut=LIBELLES_STATUTS_AUDIO[transcription.statut],
        libelle_etat=execution.libelle_etat,
        partiel=execution.partiel,
        # Marques de l'exécution puis du résultat, sans doublon et sans déduction.
        marques=tuple(dict.fromkeys(execution.marques + transcription.marques)),
        modele=execution.modele,
        moteur=execution.moteur,
        mesures=transcription.mesures,
        materiel=materiel,
        date_essai=execution.cree_le,
        etat=execution.etat,
        reglages=reglages,
        reglages_bruts=reglages_bruts,
        variante=_champ(transcription.modele, "Variante GGUF"),
        revision=_texte(_champ(transcription.modele, "Révision figée")),
        duree_decodee_s=transcription.duree_decodee_s,
    )


def _cle_recence(entrees: Sequence[EntreeEmpreinte]) -> tuple[tuple[int, float], str]:
    """Clé d'un groupe : son essai le plus récent, puis l'identifiant d'exécution.

    Sert à ordonner les groupes indépendamment du critère de classement interne.
    """
    recent = max(
        entrees, key=lambda entree: (_horodatage(entree.date_essai), entree.execution)
    )
    return _horodatage(recent.date_essai), recent.execution


def _avec_alerte_materiel(
    entrees: Sequence[EntreeEmpreinte],
) -> tuple[EntreeEmpreinte, ...]:
    """Entrées d'un même audio, chacune avec sa mention de matériel.

    La mention compare le matériel de l'essai aux seuls autres essais du même
    audio, comme le détail individuel ; aucun matériel local n'est substitué.
    """
    return tuple(
        replace(
            entree,
            materiel_alerte=_alerte_materiel(
                entree.materiel,
                [autre.materiel for autre in entrees if autre is not entree],
            ),
        )
        for entree in entrees
    )


def _entrees_du_groupe(
    entrees: Sequence[EntreeEmpreinte], tri: str
) -> tuple[EntreeEmpreinte, ...]:
    """Entrées d'un groupe : résultats observés puis mesures simulées.

    Chaque partie est classée par `tri` et ne mélange jamais mesures simulées et
    mesures observées. Les réglages distinctifs sont calculés **dans** chaque
    partie : un réglage n'est donc jamais déclaré distinctif à cause d'une entrée
    de l'autre sous-liste. Les entrées sont conservées toutes, sans
    dédoublonnage.
    """
    classees = trier_entrees(entrees, tri)
    reelles = _entrees_reglages_distinctifs(
        tuple(entree for entree in classees if not entree.simule)
    )
    simulees = _entrees_reglages_distinctifs(
        tuple(entree for entree in classees if entree.simule)
    )
    return reelles + simulees


def _reglages_entree(
    transcription: TranscriptionVue,
) -> tuple[tuple[Paire, ...], dict[str, Any]]:
    """Réglages consignés d'un résultat, avec leurs valeurs brutes.

    La famille, la variante GGUF, les threads et la langue imposée précèdent les
    réglages demandés, défauts compris ; les autres réglages effectifs restent
    consultables dans le détail. Une clé absente n'apparaît pas, mais une clé
    explicitement nulle ou non finie est conservée. Les valeurs affichées sont formatées comme ailleurs,
    mais la comparaison des réglages distinctifs porte sur les valeurs brutes,
    jamais sur ces chaînes.
    """
    paires: list[Paire] = []
    bruts: dict[str, Any] = {}
    for libelle, valeur in (
        ("Famille", transcription.famille),
        ("Variante GGUF", _champ(transcription.modele, "Variante GGUF")),
        ("Threads demandés", _champ(transcription.threads, "Threads demandés")),
        ("Threads appliqués", _champ(transcription.threads, "Threads appliqués")),
        ("Langue imposée", transcription.langue_imposee),
    ):
        if valeur is None:
            continue
        paires.append((libelle, valeur))
        bruts[libelle] = valeur
    for nom, valeur in transcription.reglages:
        libelle = f"Réglage demandé : {nom}"
        paires.append((libelle, valeur))
        bruts[libelle] = transcription.reglages_bruts.get(nom)
    return tuple(paires), bruts


def _entrees_reglages_distinctifs(
    entrees: Sequence[EntreeEmpreinte],
) -> tuple[EntreeEmpreinte, ...]:
    """Entrées avec leurs réglages distinctifs, calculés dans leur sous-liste.

    Une sous-liste d'une seule entrée n'a rien à comparer : tous ses réglages
    consignés sont utiles et deviennent distinctifs. Dès deux entrées, seuls les
    réglages dont la valeur **brute** diffère d'au moins une autre entrée sont
    retenus : un réglage commun n'est pas répété. Une clé absente compte comme
    distincte d'une valeur explicite nulle, et deux valeurs non finies restent
    distinctes entre elles ; l'affichage formaté ne décide jamais.
    """
    if len(entrees) <= 1:
        return tuple(
            replace(entree, reglages_distinctifs=entree.reglages)
            for entree in entrees
        )
    libelles = sorted(
        {libelle for entree in entrees for libelle, _valeur in entree.reglages}
    )
    differents = {
        libelle
        for libelle in libelles
        if len({_forme_reglage(entree, libelle) for entree in entrees}) > 1
    }
    return tuple(
        replace(
            entree,
            reglages_distinctifs=tuple(
                (libelle, valeur)
                for libelle, valeur in entree.reglages
                if libelle in differents
            ),
        )
        for entree in entrees
    )


def _forme_reglage(entree: EntreeEmpreinte, libelle: str) -> str:
    """Forme comparable d'un réglage : « absente », ou JSON brut trié."""
    if libelle not in entree.reglages_bruts:
        return "absente"
    return json.dumps(
        entree.reglages_bruts[libelle], ensure_ascii=False, sort_keys=True
    )


#: État et marques, toujours affichés en premières lignes de la table.
_CHAMPS_ETAT: tuple[tuple[str, Callable[[_Colonne], Any]], ...] = (
    ("Statut du résultat", lambda colonne: colonne.entree.libelle_statut),
    ("État de l'exécution", lambda colonne: colonne.entree.libelle_etat),
    ("Résultats partiels", lambda colonne: colonne.entree.partiel),
    ("Marques", lambda colonne: _texte_marques(colonne.entree.marques)),
)

#: Configuration comparée ligne par ligne, avec la valeur lue par colonne.
#: `None` reste « indisponible » ; une clé absente est traitée à part.
_CHAMPS_CONFIGURATION: tuple[tuple[str, Callable[[_Colonne], Any]], ...] = (
    (
        "Modèle demandé",
        lambda colonne: _champ(colonne.transcription.modele, "Identifiant demandé"),
    ),
    (
        "Modèle canonique",
        lambda colonne: _champ(colonne.transcription.modele, "Identifiant canonique"),
    ),
    (
        "Révision figée",
        lambda colonne: _champ(colonne.transcription.modele, "Révision figée"),
    ),
    (
        "Variante GGUF",
        lambda colonne: _champ(colonne.transcription.modele, "Variante GGUF"),
    ),
    ("Famille", lambda colonne: colonne.transcription.famille),
    (
        "Moteur",
        lambda colonne: _champ(
            colonne.transcription.moteur, "Identifiant du moteur"
        ),
    ),
    (
        "Nom du moteur",
        lambda colonne: _champ(colonne.transcription.moteur, "Nom du moteur"),
    ),
    (
        "Threads demandés",
        lambda colonne: _champ(colonne.transcription.threads, "Threads demandés"),
    ),
    (
        "Threads appliqués",
        lambda colonne: _champ(colonne.transcription.threads, "Threads appliqués"),
    ),
    ("Langue imposée", lambda colonne: colonne.transcription.langue_imposee),
    (
        "Durée de fenêtre (s)",
        lambda colonne: _champ(
            colonne.transcription.fenetre, "Durée de fenêtre (s)"
        ),
    ),
    (
        "Découpage",
        lambda colonne: _champ(
            colonne.transcription.fenetre, "Méthode de découpage"
        ),
    ),
    (
        "Nombre de fenêtres",
        lambda colonne: _champ(colonne.transcription.fenetre, "Nombre de fenêtres"),
    ),
)

#: Mesures principales comparées, avec leur nature de formatage.
_MESURES_COMPAREES: tuple[tuple[str, str, Callable[[_Colonne], Any]], ...] = (
    (
        "Durée totale de l'opération",
        NATURE_DUREE,
        lambda colonne: colonne.mesures.duree_operation_s,
    ),
    (
        "Durée du processus moteur",
        NATURE_DUREE,
        lambda colonne: colonne.mesures.duree_processus_s,
    ),
    (
        "Durée de chargement du modèle",
        NATURE_DUREE,
        lambda colonne: colonne.mesures.duree_chargement_s,
    ),
    (
        "Pic de mémoire de l'exécution",
        NATURE_OCTETS,
        lambda colonne: colonne.mesures.pic_memoire_octets,
    ),
    (
        "Pic de mémoire de l'exécution partiel",
        NATURE_TEXTE,
        lambda colonne: colonne.mesures.pic_memoire_partiel,
    ),
    (
        "Durée décodée (référence du RTF)",
        NATURE_DUREE,
        lambda colonne: colonne.transcription.duree_decodee_s,
    ),
    (
        "Durée indicative du fichier",
        NATURE_DUREE,
        lambda colonne: colonne.transcription.duree_indicative_s,
    ),
    (
        "Temps de décodage (serveur)",
        NATURE_DUREE,
        lambda colonne: colonne.transcription.mesures.temps_decodage_s,
    ),
    (
        "Durée de transcription",
        NATURE_DUREE,
        lambda colonne: colonne.transcription.mesures.duree_transcription_s,
    ),
    (
        "Temps CPU consommé",
        NATURE_DUREE,
        lambda colonne: colonne.transcription.mesures.temps_cpu_s,
    ),
    (
        "RTF (durée de transcription / durée décodée)",
        NATURE_RTF,
        lambda colonne: colonne.transcription.mesures.rtf,
    ),
    (
        "Pic de mémoire du moteur (audio)",
        NATURE_OCTETS,
        lambda colonne: colonne.transcription.mesures.pic_memoire_octets,
    ),
)


def _lignes_comparaison(colonnes: Sequence[_Colonne]) -> tuple[LigneComparaison, ...]:
    """Lignes de la table : état, textes, configuration puis mesures.

    Les textes transcrits sont affichés tels quels, une colonne par
    transcription, et ne sont jamais comparés entre eux : aucun diff textuel,
    aucun WER et aucune référence ne sont calculés.

    Les réglages demandés (validés, défauts compris) et les réglages effectifs
    sont comparés sur l'union des clés de chaque audio. La comparaison porte sur
    la valeur JSON brute : listes, objets, `null`, `NaN`, `Infinity` et
    `-Infinity` restent distincts, et une valeur formatée pour l'affichage ne
    peut jamais être confondue avec la donnée d'origine.
    """
    affiches_demandes = [dict(colonne.transcription.reglages) for colonne in colonnes]
    affiches_effectifs = [
        dict(colonne.transcription.reglages_effectifs) for colonne in colonnes
    ]
    bruts_demandes = [colonne.transcription.reglages_bruts for colonne in colonnes]
    bruts_effectifs = [
        colonne.transcription.reglages_effectifs_bruts for colonne in colonnes
    ]
    noms_demandes = sorted({nom for bruts in bruts_demandes for nom in bruts})
    noms_effectifs = sorted({nom for bruts in bruts_effectifs for nom in bruts})
    lignes = [
        _ligne(
            libelle,
            NATURE_TEXTE,
            _cellules([extraire(colonne) for colonne in colonnes]),
        )
        for libelle, extraire in _CHAMPS_ETAT
    ]
    # Le texte est la matière comparée : il précède la configuration. Il n'est
    # jamais marqué « différent » pour ne suggérer aucun diff caractère à
    # caractère.
    lignes.append(
        LigneComparaison(
            libelle="Texte transcrit",
            nature=NATURE_TRANSCRIPTION,
            cellules=_cellules(
                [colonne.transcription.texte for colonne in colonnes]
            ),
            differents=False,
        )
    )
    lignes.extend(
        _ligne(
            libelle,
            NATURE_TEXTE,
            _cellules([extraire(colonne) for colonne in colonnes]),
        )
        for libelle, extraire in _CHAMPS_CONFIGURATION
    )
    lignes.extend(
        _ligne(
            f"Réglage demandé : {nom}",
            NATURE_TEXTE,
            _cellules_reglages(affiches_demandes, bruts_demandes, nom),
        )
        for nom in noms_demandes
    )
    lignes.extend(
        _ligne(
            f"Réglage effectif : {nom}",
            NATURE_TEXTE,
            _cellules_reglages(affiches_effectifs, bruts_effectifs, nom),
        )
        for nom in noms_effectifs
    )
    lignes.extend(
        _ligne(
            libelle,
            nature,
            _cellules([extraire(colonne) for colonne in colonnes]),
        )
        for libelle, nature, extraire in _MESURES_COMPAREES
    )
    # Provenance de l'essai déjà lu : matériel, versions et fichiers restent
    # consultables ici, sans imposer de quitter la comparaison. Les clés
    # absentes restent distinctes des valeurs explicitement nulles.
    for section, champs in (
        ("machine", CHAMPS_MACHINE),
        ("programme", CHAMPS_PROGRAMME + (("ffmpeg", "FFmpeg"),)),
        ("moteur", (("versions", "Versions du moteur"),
                    ("empreinte_verrou", "Empreinte du verrou du moteur"))),
        ("processus_moteur", CHAMPS_PROCESSUS),
    ):
        bruts = [_mapping(colonne.contexte.get(section)) for colonne in colonnes]
        affiches = [
            {cle: _valeur_reglage(valeur) for cle, valeur in brut.items()}
            for brut in bruts
        ]
        for cle, libelle in champs:
            nature = NATURE_DETAIL if section == "processus_moteur" else NATURE_TEXTE
            lignes.append(_ligne(libelle, nature,
                                 _cellules_reglages(affiches, bruts, cle)))
    for attribut, prefixe in (("audio", "Fichier audio"),
                             ("modele", "Modèle")):
        libelles = dict.fromkeys(
            libelle for colonne in colonnes
            for libelle, _valeur in getattr(colonne.transcription, attribut)
        )
        for libelle in libelles:
            if attribut == "modele" and libelle != "Clé locale":
                continue  # Identifiants, révision et variante déjà comparés.
            if attribut == "audio" and libelle in (
                "Durée indicative (s)", "Durée décodée (s)"
            ):
                continue  # Ces durées figurent déjà dans les mesures.
            lignes.append(_ligne(
                f"{prefixe} : {libelle}", NATURE_TEXTE,
                _cellules([_champ(getattr(colonne.transcription, attribut), libelle)
                           for colonne in colonnes]),
            ))
    for libelle, extraire in (
        ("Segments horodatés", lambda c: [
            {"debut_s": s.debut_s, "fin_s": s.fin_s, "texte": s.texte}
            for s in c.transcription.segments]),
        ("Timings natifs", lambda c: [vars(t) for t in c.transcription.timings_natifs]),
    ):
        valeurs = [extraire(colonne) for colonne in colonnes]
        cellules = tuple(
            CelluleComparaison(True, _valeur_reglage(valeur), valeur)
            for valeur in valeurs
        )
        # Les segments contiennent du texte : consultation seulement, jamais
        # un diff des transcriptions ou de leur découpage.
        lignes.append(
            LigneComparaison(libelle, NATURE_DETAIL, cellules, False)
            if libelle == "Segments horodatés"
            else _ligne(libelle, NATURE_DETAIL, cellules)
        )
    return tuple(lignes)


def _cartes_comparaison(
    colonnes: Sequence[_Colonne],
) -> tuple[CarteComparaison, ...]:
    """Cartes de premier niveau, dans l'ordre reçu de la sélection.

    Chaque carte reçoit les trois indicateurs de son audio, les ratios calculés
    sur le matériel **consigné** de son essai et son texte complet. Les réglages
    distinctifs sont calculés entre les cartes comparées, sur leurs valeurs
    brutes, comme pour les listes par audio ; un réglage commun n'est pas répété.
    La mention de matériel compare les quatre champs requis aux seules autres
    cartes comparées, jamais à tout l'historique. Aucun fichier n'est modifié et
    aucune valeur locale n'est substituée.
    """
    entrees = _entrees_reglages_distinctifs(
        tuple(colonne.entree for colonne in colonnes)
    )
    libelles = _libelles_carte(entrees)
    materiels = tuple(entree.materiel for entree in entrees)
    cartes: list[CarteComparaison] = []
    for position, (colonne, entree, libelle) in enumerate(
        zip(colonnes, entrees, libelles, strict=True)
    ):
        indicateurs = _indicateurs_audio(entree.mesures, entree.materiel)
        autres = tuple(
            materiel
            for index, materiel in enumerate(materiels)
            if index != position
        )
        cartes.append(
            CarteComparaison(
                entree=entree,
                libelle=libelle,
                texte=colonne.transcription.texte,
                erreur=colonne.transcription.erreur,
                duree_transcription_s=indicateurs.duree_transcription_s,
                pic_memoire_octets=indicateurs.pic_memoire_octets,
                ram_totale_octets=indicateurs.ram_totale_octets,
                temps_cpu_s=indicateurs.temps_cpu_s,
                part_ram=indicateurs.part_ram,
                occupation_cpu=indicateurs.occupation_cpu,
                annotation_ram=_annotation_ram(entree.ordre),
                materiel_alerte=_alerte_materiel(entree.materiel, autres),
            )
        )
    return tuple(cartes)


def _libelle_modele(modele: str | None) -> str:
    """Titre court d'un modèle : son dernier segment, sans chemin d'identifiant.

    Un identifiant de modèle peut contenir un préfixe (`orga/modele`) : seul le
    dernier segment est affiché en titre, l'identifiant complet restant dans les
    détails. Un modèle absent n'est jamais inventé.
    """
    if not modele:
        return "modèle non consigné"
    return modele.rsplit("/", 1)[-1]


def _libelles_carte(entrees: Sequence[EntreeEmpreinte]) -> tuple[str, ...]:
    """Titres courts des cartes : modèle consigné, désambiguïsé si répété.

    Deux cartes du même modèle sont distinguées par la date courte ; si les
    dates se confondent ou manquent, l'identifiant de l'essai reste nécessaire.
    Aucun nom de modèle n'est inventé quand il est absent.
    """
    bases = [_libelle_modele(entree.modele) for entree in entrees]
    dates = [formater_date_courte(entree.date_essai) for entree in entrees]
    libelles = []
    for base, date, entree in zip(bases, dates, entrees, strict=True):
        if bases.count(base) == 1:
            libelles.append(base)
        elif entree.date_essai and sum(
            autre_base == base and autre_date == date
            for autre_base, autre_date in zip(bases, dates, strict=True)
        ) == 1 and date != "date non consignée":
            libelles.append(f"{base} ({date})")
        else:
            audio = (
                f", audio {entree.ordre}"
                if sum(autre.execution == entree.execution for autre in entrees) > 1
                else ""
            )
            libelles.append(f"{base} (essai {entree.execution}{audio})")
    return tuple(libelles)


def _annotation_ram(ordre: int) -> str | None:
    """Annotation du pic mémoire cumulatif, ou `None` pour le premier audio.

    Le premier audio de la demande n'en porte pas ; tout autre audio voit son
    pic signalé comme cumulatif, même si un audio précédent a échoué, car le
    pic est relevé sur le processus du moteur et inclut son chargement. Un ordre
    non vérifiable indique que le pic n'est pas isolé par audio.
    """
    if ordre == 1:
        return None
    if ordre > 1:
        return (
            "Pic mémoire cumulatif du lot : il peut provenir d'un audio précédent "
            "et inclut le chargement du modèle."
        )
    return "Pic mémoire non isolé par audio : il n'est pas attribuable à ce seul audio."


def _alerte_materiel(
    materiel: MaterielVue | None, autres: Sequence[MaterielVue | None]
) -> str | None:
    """Mention courte de matériel différent ou non vérifié pour un audio.

    Seuls les quatre champs requis (système d'exploitation, architecture,
    processeurs logiques, RAM totale) décident, **champ par champ** : le nom du
    processeur reste informatif, son absence seule ne déclenche donc aucune
    alerte, et une différence connue sur ce seul champ reste consultable dans
    les détails.

    Un champ connu des deux côtés et différent donne une différence signalée,
    même si un autre champ requis manque : une valeur inconnue ne masque jamais
    une différence connue. Un champ dont la valeur manque chez cet essai ou chez
    un essai comparé, sans différence connue sur ce champ, donne une mention
    « non vérifié » (des métadonnées identiques ne prouvent jamais l'identité
    d'une machine). Sans essai comparé, seuls les champs manquants de cet essai
    sont signalés : aucune comparaison n'est inventée.
    """
    differents: list[str] = []
    inconnus: list[str] = []
    for champ, libelle in CHAMPS_MATERIEL_REQUIS:
        valeur = None if materiel is None else getattr(materiel, champ)
        if valeur is None:
            inconnus.append(libelle)
            continue
        different = False
        inconnu = False
        for autre in autres:
            autre_valeur = None if autre is None else getattr(autre, champ)
            if autre_valeur is None:
                inconnu = True
            elif autre_valeur != valeur:
                different = True
        # Une différence connue prime sur l'inconnu du même champ : elle reste
        # signalée même si un autre essai ne consigne pas cette valeur.
        if different:
            differents.append(libelle)
        elif inconnu:
            inconnus.append(libelle)
    return _mention_materiel(differents, inconnus)


def _mention_materiel(
    differents: Sequence[str], inconnus: Sequence[str]
) -> str | None:
    """Formulation courte de la mention de matériel, ou `None` sans écart.

    La mention reste locale : elle nomme les seuls champs en écart, sans
    explication générale répétée sur chaque ligne. Les règles communes (quatre
    champs requis, absence de preuve d'identité des machines) figurent une seule
    fois dans l'aide locale et dans la note de la comparaison.
    """
    if not differents and not inconnus:
        return None
    morceaux: list[str] = []
    if differents:
        morceaux.append(f"Matériel différent sur {_liste_francaise(differents)}")
    if inconnus:
        morceaux.append(f"matériel non vérifié pour {_liste_francaise(inconnus)}")
    mention = " ; ".join(morceaux) + "."
    return mention[0].upper() + mention[1:]


def _liste_francaise(elements: Sequence[str]) -> str:
    """Éléments joints en français : « a », « a et b », « a, b et c »."""
    if len(elements) == 1:
        return elements[0]
    return f"{', '.join(elements[:-1])} et {elements[-1]}"


def distinctions_comparaison(
    cartes: Sequence[CarteComparaison],
) -> tuple[frozenset[int], frozenset[int]]:
    """Indices des cartes de tête en temps et en pic mémoire, sans score global.

    Seules les mesures réelles de résultats complets concourent : une mesure
    simulée (`FACTICE`, `MESURES SIMULÉES`) ou un résultat partiel ne reçoit
    aucune distinction de performance réelle, quelle que soit sa valeur. Une
    mesure absente ou incohérente (négative, non finie, non numérique) ne
    concourt pas et moins de deux valeurs comparables n'attribuent aucune tête.
    Les égalités sont conservées ; le CPU n'a jamais de tête, car moins
    l'occuper n'est pas aller plus vite.

    Ce calcul unique sert la synthèse descriptive et les libellés courts
    affichés près des valeurs : une même règle produit les deux lectures.
    """
    temps: list[tuple[int, float]] = []
    ram: list[tuple[int, float]] = []
    for index, carte in enumerate(cartes):
        entree = carte.entree
        if entree.simule or entree.partiel:
            continue
        valeur_temps = valeur_distinction(entree, TRI_TEMPS)
        valeur_ram = valeur_distinction(entree, TRI_RAM)
        if valeur_temps is not None:
            temps.append((index, valeur_temps))
        if valeur_ram is not None:
            ram.append((index, valeur_ram))
    return (_indices_minimaux(temps), _indices_minimaux(ram))


def _indices_minimaux(mesures: Sequence[tuple[int, float]]) -> frozenset[int]:
    """Indices des valeurs minimales, égalités comprises.

    Moins de deux mesures comparables n'attribuent aucune tête : une valeur
    unique n'est pas une comparaison, et une mesure absente ne concourt pas.
    """
    if len(mesures) < 2:
        return frozenset()
    minimum = min(valeur for _index, valeur in mesures)
    return frozenset(index for index, valeur in mesures if valeur == minimum)


def _synthese_comparaison(
    cartes: Sequence[CarteComparaison],
) -> SyntheseComparaison:
    """Synthèse des temps et des pics mémoire observés, sans score global.

    Les têtes et les exclusions viennent de `distinctions_comparaison`, donc des
    mêmes règles que les libellés courts : une mesure simulée ou partielle est
    nommée comme exclue, une mesure absente n'est jamais remplacée par zéro et
    les égalités restent comprises.
    """
    meilleurs_temps, meilleures_ram = distinctions_comparaison(cartes)
    return SyntheseComparaison(
        plus_rapides=tuple(
            carte.libelle
            for index, carte in enumerate(cartes)
            if index in meilleurs_temps
        ),
        moins_de_ram=tuple(
            carte.libelle
            for index, carte in enumerate(cartes)
            if index in meilleures_ram
        ),
        exclues=tuple(
            carte.libelle
            for carte in cartes
            if carte.entree.simule or carte.entree.partiel
        ),
    )


def _ligne(
    libelle: str, nature: str, cellules: Sequence[CelluleComparaison]
) -> LigneComparaison:
    """Ligne de comparaison, marquée dès qu'une cellule diffère des autres."""
    return LigneComparaison(
        libelle=libelle,
        nature=nature,
        cellules=tuple(cellules),
        differents=len({_canonique(cellule) for cellule in cellules}) > 1,
    )


def _canonique(cellule: CelluleComparaison) -> str:
    """Forme comparable d'une cellule : absente, ou JSON brut trié.

    La comparaison porte sur `brut`, jamais sur la valeur formatée pour
    l'affichage. Le JSON trié suffit à distinguer les cas utiles : `1` et
    `1.0`, `true` et `1`, une liste et la chaîne qui la représente, `null` et
    une clé absente. `json.dumps` garde `NaN`, `Infinity` et `-Infinity`
    distincts au lieu de les ramener à `null`.
    """
    if not cellule.presente:
        return "absente"
    return json.dumps(cellule.brut, ensure_ascii=False, sort_keys=True)


def _cellules(valeurs: Sequence[Any]) -> tuple[CelluleComparaison, ...]:
    """Cellules présentes : la valeur brute est aussi la valeur affichée."""
    return tuple(
        CelluleComparaison(presente=True, valeur=valeur, brut=valeur)
        for valeur in valeurs
    )


def _cellules_reglages(
    affiches: Sequence[Mapping[str, Any]],
    bruts: Sequence[Mapping[str, Any]],
    nom: str,
) -> tuple[CelluleComparaison, ...]:
    """Cellules d'un réglage : valeur affichée formatée, valeur brute à part."""
    return tuple(
        CelluleComparaison(
            presente=nom in brut,
            valeur=affiche.get(nom),
            brut=brut.get(nom),
        )
        for affiche, brut in zip(affiches, bruts, strict=True)
    )


def _champ(paires: Sequence[Paire], libelle: str) -> Any:
    """Valeur d'une paire déjà construite, ou `None` si le libellé est absent."""
    for nom, valeur in paires:
        if nom == libelle:
            return valeur
    return None


def _texte_marques(marques: Sequence[str]) -> str:
    """Marques affichées en une ligne ; « aucune » n'en invente aucune."""
    return ", ".join(marques) if marques else "aucune"


# -- validation du suivi d'exécution -----------------------------------------


def _valider_execution(contenu: Any, identifiant: str) -> None:
    """Vérifie ce que la consultation interprète : schéma, état, audios.

    Seuls les champs réellement lus sont contrôlés. Un contenu refusé n'est
    jamais réécrit ; les messages ne recopient aucune valeur du fichier.
    """
    if not isinstance(contenu, Mapping):
        raise ResultatNonInterpretable("objet JSON attendu")
    schema = contenu.get("schema")
    if type(schema) is not int or schema != SCHEMA:
        raise ResultatNonInterpretable(
            f"schéma non pris en charge (schéma {SCHEMA} attendu)"
        )
    if contenu.get("identifiant") != identifiant:
        raise ResultatNonInterpretable("identifiant incohérent avec le dossier")
    etat = contenu.get("etat")
    if not isinstance(etat, str) or etat not in LIBELLES_ETATS_EXECUTION:
        raise ResultatNonInterpretable("état d'exécution inconnu")
    audios = contenu.get("audios")
    if not isinstance(audios, list):
        raise ResultatNonInterpretable("clé 'audios' absente ou invalide")
    for plan in audios:
        if not isinstance(plan, Mapping):
            raise ResultatNonInterpretable("plan d'audio invalide")
        ordre = plan.get("ordre")
        if type(ordre) is not int or ordre < 1:
            raise ResultatNonInterpretable("ordre d'audio invalide")
        if not isinstance(plan.get("nom"), str):
            raise ResultatNonInterpretable("nom d'audio invalide")
        dossier = plan.get("dossier")
        if not isinstance(dossier, str) or not dossier:
            raise ResultatNonInterpretable("dossier d'audio invalide")
        statut = plan.get("statut")
        if not isinstance(statut, str) or statut not in LIBELLES_STATUTS_AUDIO:
            raise ResultatNonInterpretable("statut d'audio inconnu")


# -- vues --------------------------------------------------------------------


def _execution_non_interpretable(identifiant: str, motif: str) -> ExecutionListee:
    """Ligne de liste pour un `run.json` refusé : aucun fait n'est inventé."""
    return ExecutionListee(
        identifiant=identifiant,
        etat=None,
        libelle_etat="non interprétable",
        cree_le=None,
        modele=None,
        moteur=None,
        audios_traites=None,
        audios_total=None,
        duree_operation_s=None,
        partiel=False,
        marques=None,
        exploitable=False,
        motif=motif,
    )


def _mesures_execution(mesure: Mapping[str, Any]) -> MesuresVue:
    """Mesures globales d'une exécution ; une mesure absente reste `None`."""
    return MesuresVue(
        duree_operation_s=_nombre(mesure.get("duree_operation_s")),
        duree_processus_s=_nombre(mesure.get("duree_processus_s")),
        duree_chargement_s=_nombre(mesure.get("duree_chargement_s")),
        pic_memoire_octets=_entier(mesure.get("pic_memoire_octets")),
        pic_memoire_partiel=_booleen(mesure.get("pic_memoire_partiel")),
    )


def _materiel(contenu: Mapping[str, Any]) -> MaterielVue:
    """Matériel consigné d'une exécution ; un champ douteux reste `None`.

    La lecture suit les mêmes conversions que le détail : un texte vide, un
    entier non strict (`8.0`, `True`) ou un objet ne deviennent jamais une
    capacité. Aucune valeur n'est complétée par le matériel local.
    """
    machine = _mapping(contenu.get("machine"))
    return MaterielVue(
        os=_texte(machine.get("os")),
        version_os=_texte(machine.get("version_os")),
        architecture=_texte(machine.get("architecture")),
        processeur=_texte(machine.get("processeur")),
        coeurs_physiques=_entier(machine.get("coeurs_physiques")),
        coeurs_logiques=_entier(machine.get("coeurs_logiques")),
        ram_totale_octets=_entier(machine.get("ram_totale_octets")),
    )


def _resume(contenu: Mapping[str, Any]) -> ExecutionListee:
    """Ligne de liste (ou en-tête du détail) d'un `run.json` déjà validé."""
    demande = _mapping(contenu.get("demande"))
    modele = _mapping(demande.get("modele"))
    moteur = _mapping(contenu.get("moteur"))
    mesure = _mapping(contenu.get("mesures"))
    plans = contenu["audios"]
    etat = contenu["etat"]
    return ExecutionListee(
        identifiant=contenu["identifiant"],
        etat=etat,
        libelle_etat=LIBELLES_ETATS_EXECUTION[etat],
        cree_le=_texte(contenu.get("cree_le")),
        modele=_texte(modele.get("identifiant")) or _texte(modele.get("id_resolu")),
        moteur=_texte(moteur.get("nom")) or _texte(moteur.get("identifiant")),
        audios_traites=sum(1 for plan in plans if plan["statut"] != STATUT_NON_TRAITE),
        audios_total=len(plans),
        duree_operation_s=_nombre(mesure.get("duree_operation_s")),
        partiel=etat != ETAT_TERMINEE,
        marques=_marques(contenu),
        exploitable=True,
        motif=None,
    )


def _audio(
    dossier_execution: Path,
    plan: Mapping[str, Any],
    *,
    partiel: bool,
    materiel: MaterielVue | None = None,
    autres: Mapping[str, Sequence[MaterielVue]] | None = None,
) -> AudioVue:
    """Audio d'une exécution : transcription relue, ou motif d'absence.

    Les trois indicateurs viennent des mesures de cet audio et du matériel de
    son essai ; la durée du lot n'est jamais présentée comme celle de l'audio.
    L'annotation du pic mémoire suit l'ordre de l'audio dans sa demande, et la
    mention de matériel compare les quatre champs requis aux autres essais du
    même audio (`autres`, par empreinte) : aucune valeur locale n'est
    substituée et rien n'est écrit.
    """
    transcription, motif = _lire_transcription(dossier_execution, plan)
    if transcription is None and plan["statut"] == STATUT_NON_TRAITE:
        motif = MOTIF_NON_TRAITE
    # Le `result.json` fait foi pour son propre audio : `run.json` est réécrit
    # après lui, il peut donc être en retard d'un instant sur une exécution en
    # cours. Sans résultat, c'est le statut du suivi qui est affiché.
    statut = plan["statut"] if transcription is None else transcription.statut
    indicateurs = _indicateurs_audio(
        None if transcription is None else transcription.mesures, materiel
    )
    annotation_ram = None
    materiel_alerte = None
    if transcription is not None:
        annotation_ram = _annotation_ram(plan["ordre"])
        empreinte = transcription.empreinte_sha256
        candidats = (
            ()
            if autres is None or empreinte is None
            else autres.get(empreinte, ())
        )
        materiel_alerte = _alerte_materiel(materiel, candidats)
    return AudioVue(
        ordre=plan["ordre"],
        nom=plan["nom"],
        dossier=plan["dossier"],
        statut=statut,
        libelle_statut=LIBELLES_STATUTS_AUDIO[statut],
        erreur=_texte(plan.get("erreur")),
        partiel=partiel and transcription is not None,
        motif_indisponible=motif,
        transcription=transcription,
        indicateurs=indicateurs,
        annotation_ram=annotation_ram,
        materiel_alerte=materiel_alerte,
    )


def _lire_transcription(
    dossier_execution: Path, plan: Mapping[str, Any]
) -> tuple[TranscriptionVue | None, str | None]:
    """Transcription d'un audio, ou motif d'indisponibilité fixe."""
    try:
        dossier_audio = resoudre_dans_racine(dossier_execution, plan["dossier"])
    except ValeurRefusee:
        return None, MOTIF_DOSSIER_REFUSE
    try:
        chemin = resoudre_dans_racine(dossier_audio, NOM_FICHIER_RESULTAT)
    except ValeurRefusee:
        return None, MOTIF_FICHIER_REFUSE
    try:
        contenu = lire_json(chemin)
    except (JsonInvalide, OSError):
        return None, MOTIF_RESULTAT_ILLISIBLE
    if contenu is None:
        return None, MOTIF_RESULTAT_ABSENT
    try:
        return _vue_transcription(contenu, dossier_execution.name, plan), None
    except ResultatNonInterpretable as refus:
        return None, f"Résultat non interprétable : {refus}"


def _vue_transcription(
    contenu: Any, execution: str, plan: Mapping[str, Any]
) -> TranscriptionVue:
    """Vue d'un `result.json`, confiné et identifié avec son plan d'audio.

    Refuse un schéma inconnu, un statut inconnu ou un résultat qui ne décrit pas
    cet audio de cette exécution : une transcription n'est jamais attribuée à un
    autre audio.
    """
    if not isinstance(contenu, Mapping):
        raise ResultatNonInterpretable("objet JSON attendu")
    schema = contenu.get("schema")
    if type(schema) is not int or schema != SCHEMA:
        raise ResultatNonInterpretable(
            f"schéma non pris en charge (schéma {SCHEMA} attendu)"
        )
    statut = contenu.get("statut")
    if not isinstance(statut, str) or statut not in LIBELLES_STATUTS_AUDIO:
        raise ResultatNonInterpretable("statut de résultat inconnu")
    if contenu.get("execution") != execution:
        raise ResultatNonInterpretable("exécution incohérente avec le dossier")
    ordre = contenu.get("ordre")
    if type(ordre) is not int or ordre != plan["ordre"]:
        raise ResultatNonInterpretable("ordre incohérent avec le suivi de l'exécution")
    if contenu.get("nom") != plan["nom"]:
        raise ResultatNonInterpretable("nom incohérent avec le suivi de l'exécution")
    if contenu.get("dossier") != plan["dossier"]:
        raise ResultatNonInterpretable("dossier incohérent avec le suivi de l'exécution")
    transcription = _mapping(contenu.get("transcription"))
    mesures = _mapping(contenu.get("mesures"))
    duree_transcription = _nombre(mesures.get("duree_transcription_s"))
    audio = _mapping(contenu.get("audio"))
    modele = _mapping(contenu.get("modele"))
    duree_decodee = _nombre(audio.get("duree_decodee_s"))
    return TranscriptionVue(
        statut=statut,
        ecrit_le=_texte(contenu.get("ecrit_le")),
        texte=_texte_brut(transcription.get("texte")),
        segments=_segments(transcription.get("segments")),
        marques=_marques(contenu),
        audio=_paires(audio, CHAMPS_AUDIO),
        empreinte_sha256=_empreinte(audio.get("empreinte_sha256")),
        duree_indicative_s=_nombre(audio.get("duree_indicative_s")),
        duree_decodee_s=duree_decodee,
        mesures=MesuresAudioVue(
            temps_decodage_s=_nombre(mesures.get("temps_decodage_s")),
            duree_transcription_s=duree_transcription,
            temps_cpu_s=_nombre(mesures.get("temps_cpu_s")),
            # RTF recalculé sur la durée décodée : jamais sur l'indicative, et
            # jamais sur une durée nulle ou absente.
            rtf=calculer_rtf(duree_transcription, duree_decodee),
            pic_memoire_octets=_entier(mesures.get("pic_memoire_octets")),
        ),
        timings_natifs=_timings_natifs(contenu.get("timings_natifs")),
        reglages=_paires_reglages(contenu.get("reglages")),
        reglages_bruts=_mapping(contenu.get("reglages")),
        reglages_effectifs=_paires_reglages(contenu.get("reglages_effectifs")),
        reglages_effectifs_bruts=_mapping(contenu.get("reglages_effectifs")),
        threads=_paires(
            _mapping(contenu.get("threads")),
            (("demandes", "Threads demandés"), ("appliques", "Threads appliqués")),
        ),
        langue_imposee=_texte(contenu.get("langue_imposee")),
        fenetre=_paires(
            _mapping(contenu.get("fenetre")),
            (
                ("duree_s", "Durée de fenêtre (s)"),
                ("decoupage", "Méthode de découpage"),
                ("nb_fenetres", "Nombre de fenêtres"),
            ),
        ),
        modele=_paires(modele, CHAMPS_MODELE),
        moteur=_paires(_mapping(contenu.get("moteur")), CHAMPS_MOTEUR),
        famille=_texte(modele.get("famille")),
        erreur=_texte(contenu.get("erreur")),
    )


def _timings_natifs(valeur: Any) -> tuple[TimingsNatifVue, ...]:
    """Timings natifs par appel ; une entrée illisible est écartée.

    Cette information est facultative : un `result.json` antérieur au champ n'a
    aucune entrée et reste interprétable. Une entrée sans unité ou mal formée
    est ignorée plutôt que de rendre toute la transcription indisponible ; une
    étape absente ou non finie reste `None`, jamais zéro.
    """
    if not isinstance(valeur, list):
        return ()
    timings: list[TimingsNatifVue] = []
    for entree in valeur:
        if not isinstance(entree, Mapping):
            continue
        unite = entree.get("unite")
        if not isinstance(unite, str) or not unite:
            continue
        timings.append(
            TimingsNatifVue(
                unite=unite,
                chargement=_nombre(entree.get("load_ms")),
                mel=_nombre(entree.get("mel_ms")),
                encodage=_nombre(entree.get("encode_ms")),
                decodage=_nombre(entree.get("decode_ms")),
            )
        )
    return tuple(timings)


def _segments(valeur: Any) -> tuple[SegmentVue, ...]:
    """Segments horodatés ; une forme inattendue est refusée.

    Le runner accepte des bornes non finies (NaN, infini). Elles ne sont ni un
    texte ni une mesure à masquer : la borne devient `None` (indisponible) et le
    texte du segment reste affiché. Une borne non numérique, un segment qui
    n'est pas un objet ou un texte absent restent refusés.
    """
    if valeur is None:
        return ()
    if not isinstance(valeur, list):
        raise ResultatNonInterpretable("segments invalides")
    segments: list[SegmentVue] = []
    for segment in valeur:
        if not isinstance(segment, Mapping):
            raise ResultatNonInterpretable("segment invalide")
        debut = segment.get("debut_s")
        fin = segment.get("fin_s")
        texte = _texte_brut(segment.get("texte"))
        if not _numerique(debut) or not _numerique(fin) or texte is None:
            raise ResultatNonInterpretable("segment invalide")
        segments.append(
            SegmentVue(debut_s=_position(debut), fin_s=_position(fin), texte=texte)
        )
    return tuple(segments)


def _marques(contenu: Mapping[str, Any]) -> tuple[str, ...]:
    """Marques explicitement consignées, reprises sans être déduites."""
    marques = []
    if contenu.get("factice") is True:
        marques.append(MARQUE_FACTICE)
    if contenu.get("synthetique") is True:
        marques.append(MARQUE_SYNTHETIQUE)
    if contenu.get("mesures_simulees") is True:
        marques.append(MARQUE_MESURES_SIMULEES)
    return tuple(marques)


def _paires(
    contenu: Mapping[str, Any], champs: Sequence[tuple[str, str]]
) -> tuple[Paire, ...]:
    """Paires libellé / valeur d'un sous-objet, valeurs non affichables retirées."""
    return tuple(
        (libelle, _scalaire(contenu.get(cle))) for cle, libelle in champs
    )


def _paires_programme(programme: Mapping[str, Any]) -> tuple[Paire, ...]:
    """Métadonnées du programme, version de FFmpeg comprise (objet imbriqué)."""
    paires = _paires(programme, CHAMPS_PROGRAMME)
    ffmpeg = _mapping(programme.get("ffmpeg"))
    return paires + (("FFmpeg", _texte(ffmpeg.get("version"))),)


def _paires_reglages(valeur: Any) -> tuple[Paire, ...]:
    """Réglages d'un objet JSON, triés par nom, sans perdre listes ni objets.

    **Affichage seulement** : la comparaison lit `reglages_bruts` et
    `reglages_effectifs_bruts`, jamais ces paires formatées. Un réglage comme la
    température faster-whisper est une liste : il est affiché en JSON compact,
    échappé par Jinja comme le reste. Une valeur absente ou un nombre non fini
    au premier niveau reste « indisponible » ; un nombre non fini imbriqué
    devient `null` dans le texte JSON, jamais `NaN`. Ce formatage peut donc
    rapprocher deux valeurs brutes différentes : il ne décide d'aucune
    différence.
    """
    contenu = _mapping(valeur)
    return tuple(
        (nom, _valeur_reglage(reglage)) for nom, reglage in sorted(contenu.items())
    )


def _paires_versions(valeur: Any) -> tuple[Paire, ...]:
    """Versions relues du moteur, triées par module."""
    contenu = _mapping(valeur)
    return tuple(
        (module, _texte(version)) for module, version in sorted(contenu.items())
    )


# -- conversions -------------------------------------------------------------


def _mapping(valeur: Any) -> Mapping[str, Any]:
    """Sous-objet JSON, vide s'il n'a pas la forme attendue."""
    return valeur if isinstance(valeur, Mapping) else {}


def _valeur_reglage(valeur: Any) -> Any:
    """Valeur de réglage affichable : scalaire, ou JSON compact d'une liste/objet."""
    if isinstance(valeur, (Mapping, list, tuple)):
        return json.dumps(
            _sans_non_finis(valeur),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    return _scalaire(valeur)


def _sans_non_finis(valeur: Any) -> Any:
    """Copie compatible JSON : un nombre non fini devient `null`, jamais `NaN`."""
    if valeur is None or isinstance(valeur, (bool, str)) or type(valeur) is int:
        return valeur
    if isinstance(valeur, float):
        return valeur if math.isfinite(valeur) else None
    if isinstance(valeur, Mapping):
        return {
            str(cle): _sans_non_finis(sous_valeur)
            for cle, sous_valeur in valeur.items()
        }
    if isinstance(valeur, (list, tuple)):
        return [_sans_non_finis(element) for element in valeur]
    return None


def _scalaire(valeur: Any) -> Any:
    """Valeur affichable sans objet imbriqué ; `None` si elle n'en est pas une."""
    if isinstance(valeur, (str, bool)) or type(valeur) is int:
        return valeur
    if isinstance(valeur, float):
        return valeur if math.isfinite(valeur) else None
    return None


def _texte(valeur: Any) -> str | None:
    """Texte non vide, ou `None` (métadonnée indisponible)."""
    return valeur if isinstance(valeur, str) and valeur.strip() else None


def _texte_brut(valeur: Any) -> str | None:
    """Texte tel quel, y compris vide ; `None` si ce n'est pas un texte."""
    return valeur if isinstance(valeur, str) else None


def _empreinte(valeur: Any) -> str | None:
    """Empreinte SHA-256 en minuscules hexadécimales, ou `None` si invalide.

    Seule la casse est normalisée : une valeur absente, d'une autre longueur ou
    contenant d'autres caractères n'est jamais considérée comme une empreinte.
    """
    if not isinstance(valeur, str):
        return None
    empreinte = valeur.lower()
    return empreinte if MOTIF_EMPREINTE.fullmatch(empreinte) else None


def _numerique(valeur: Any) -> bool:
    """Nombre au sens JSON (entier ou flottant, fini ou non), hors booléens."""
    return isinstance(valeur, (int, float)) and not isinstance(valeur, bool)


def _position(valeur: Any) -> float | None:
    """Horodatage en secondes, ou `None` si la valeur est non finie."""
    nombre = _nombre(valeur)
    return None if nombre is None else float(nombre)


def _nombre(valeur: Any) -> float | int | None:
    """Nombre fini, ou `None` : NaN, infini et booléens ne sont pas des mesures."""
    if isinstance(valeur, bool) or not isinstance(valeur, (int, float)):
        return None
    try:
        return valeur if math.isfinite(valeur) else None
    except OverflowError:
        return None


def _entier(valeur: Any) -> int | None:
    """Entier strict, ou `None`."""
    return valeur if type(valeur) is int else None


def _booleen(valeur: Any) -> bool | None:
    """Booléen strict, ou `None`."""
    return valeur if isinstance(valeur, bool) else None


def _message(erreur: BaseException) -> str:
    """Texte court d'une erreur, sans message vide."""
    texte = str(erreur).strip()
    return texte if texte else type(erreur).__name__
