"""Mappings de la page Résultats, attendus par `composants.html` (tâche 1.4).

Ce module ne lit aucun fichier et n'écrit rien : il transforme les groupes et
essais du service de consultation en dictionnaires simples. Les valeurs
restent brutes ; les formats de premier niveau sont appliqués par le gabarit.

Le contrat d'une ligne est celui de `resultat_compact` : `modele`, `lien`,
`variante`, `moteur`, `date_essai`, `indicateurs`, `annotation_ram`,
`materiel_alerte`, `etats` et `duree_audio`. `duree_audio` n'est renseigné que
pour un groupe dont les durées divergent : chaque ligne indique alors la sienne,
sans durée commune inventée. `selection` est l'identité `exécution:ordre`
attendue par la comparaison.

La page Comparaisons ajoute une case de sélection par ligne :
`champ_selection` nomme le champ du formulaire et `cochees` réunit les
sélections revalidées par la route. Une ligne ne reçoit alors une clé `case`
(nom du champ, valeur, libellé accessible, état coché) que dans ce cadre ; la
page Résultats n'en produit aucune.

`vue_comparaison` produit le mapping de la comparaison sélectionnée : en-tête
d'audio (durée commune ou divergente) et cartes compactes avec distinction de
temps et de RAM. `vues_audios_detail` produit le résumé compact de chaque audio
du détail individuel. Les deux réutilisent `vue_ligne` et le composant compact
de `composants.html`, sans recopier les mesures.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

from transcription_bench.consultation_resultats import (
    SEPARATEUR_SELECTION,
    AudioVue,
    ComparaisonVue,
    DetailExecutionVue,
    EntreeEmpreinte,
    GroupeEmpreinte,
    distinctions_comparaison,
)
from transcription_bench.indicateurs_resultats import (
    formater_date_courte,
    formater_duree_premier_niveau,
)
from transcription_bench.resultats import ETAT_TERMINEE, STATUT_OK

#: Longueur de l'empreinte affichée en titre de groupe : assez pour distinguer
#: deux fichiers de même nom ; l'empreinte complète reste dans un détail.
LONGUEUR_EMPREINTE_COURTE = 8

#: Longueur de la révision affichée quand des essais ne se distinguent que par elle.
LONGUEUR_REVISION_COURTE = 7
REVISION_NON_CONSIGNEE = "non consignée"

#: Libellés courts des distinctions de performance, affichés près des valeurs.
DISTINCTION_TEMPS = "meilleur temps"
DISTINCTION_RAM = "meilleure RAM"
EGALITE = " (égalité)"


def vues_groupes(
    groupes: Sequence[GroupeEmpreinte],
    lien: Callable[[str], str],
    champ_selection: str | None = None,
    cochees: Sequence[str] = (),
) -> list[dict[str, Any]]:
    """Un mapping par groupe d'audio, dans l'ordre reçu du service.

    Le préfixe d'empreinte est commun à la page : il s'allonge seulement si deux
    empreintes distinctes partagent le même préfixe court. Avec
    `champ_selection`, chaque ligne porte aussi sa case de sélection, cochée si
    son identité figure dans `cochees`.
    """
    longueur = longueur_empreintes([groupe.empreinte for groupe in groupes])
    return [
        vue_groupe(groupe, lien, longueur, champ_selection, cochees)
        for groupe in groupes
    ]


def longueur_empreintes(empreintes: Sequence[str]) -> int:
    """Plus petite longueur (au moins 8) qui distingue les empreintes distinctes."""
    distinctes = set(empreintes)
    longueur = LONGUEUR_EMPREINTE_COURTE
    while (
        len({empreinte[:longueur] for empreinte in distinctes}) < len(distinctes)
        and longueur < 64
    ):
        longueur += 1
    return longueur


def vue_groupe(
    groupe: GroupeEmpreinte,
    lien: Callable[[str], str],
    longueur: int,
    champ_selection: str | None = None,
    cochees: Sequence[str] = (),
) -> dict[str, Any]:
    """Titre, durée commune ou divergente, puis essais observés et simulés."""
    divergentes = groupe.durees_divergentes
    return {
        "nom": ", ".join(groupe.noms) or None,
        "empreinte": groupe.empreinte,
        "empreinte_courte": groupe.empreinte[:longueur],
        "duree_audio_s": groupe.duree_decodee_commune_s,
        "durees_divergentes": divergentes,
        "reelles": [
            vue_ligne(
                entree, lien, divergentes, groupe.entrees, champ_selection, cochees
            )
            for entree in groupe.entrees_reelles
        ],
        "simulees": [
            vue_ligne(
                entree, lien, divergentes, groupe.entrees, champ_selection, cochees
            )
            for entree in groupe.entrees_simulees
        ],
    }


def vue_ligne(
    entree: EntreeEmpreinte,
    lien: Callable[[str], str],
    duree_propre: bool,
    voisines: Sequence[EntreeEmpreinte] | None = None,
    champ_selection: str | None = None,
    cochees: Sequence[str] = (),
) -> dict[str, Any]:
    """Une ligne de résultat : cinq valeurs, date secondaire et états visibles.

    Les états gardent les écarts qui comptent sans ouvrir le détail : statut
    du résultat, état de l'exécution si elle n'est pas terminée, puis marques
    consignées telles quelles. Une case de sélection n'est ajoutée que si un
    `champ_selection` est fourni.
    """
    selection = f"{entree.execution}{SEPARATEUR_SELECTION}{entree.ordre}"
    ligne = {
        "modele": modele_court(entree.modele, voisines or (entree,)),
        # Le détail ancre chaque audio : un essai de lot ouvre le bon résumé.
        "lien": f"{lien(entree.execution)}#audio-{entree.ordre}",
        "variante": entree.variante,
        "revision": revision_ligne(entree, voisines or (entree,)),
        "moteur": entree.moteur,
        "date_essai": entree.date_essai,
        "indicateurs": entree.indicateurs,
        "annotation_ram": entree.annotation_ram,
        "materiel_alerte": entree.materiel_alerte,
        "etats": etats_ligne(entree),
        "duree_audio": (
            f"Audio : {formater_duree_premier_niveau(entree.duree_decodee_s)}"
            if duree_propre
            else None
        ),
        "selection": selection,
    }
    if champ_selection:
        ligne["case"] = {
            "nom": champ_selection,
            "valeur": selection,
            "libelle": (
                f"Sélectionner {entree.modele or 'modèle non consigné'}, "
                f"audio {entree.ordre}, {formater_date_courte(entree.date_essai)}"
            ),
            "coche": selection in frozenset(cochees),
        }
    return ligne


def vue_comparaison(
    comparaison: ComparaisonVue, lien: Callable[[str], str]
) -> dict[str, Any]:
    """Mapping de la comparaison sélectionnée : en-tête audio et cartes compactes.

    L'en-tête porte la durée décodée **commune** aux essais comparés ; quand
    elle diverge, aucune durée commune n'est inventée et chaque carte affiche
    la sienne. Les cartes reprennent le composant compact des listes (modèle,
    temps, RAM, CPU, moteur, date, états) puis le texte complet.

    Les distinctions de temps et de RAM viennent de `distinctions_comparaison`,
    la même règle que la synthèse descriptive : seules des mesures réelles et
    complètes concourent, égalités comprises, sans distinction de CPU, de
    mesure simulée ni de résultat partiel.
    """
    meilleurs_temps, meilleures_ram = distinctions_comparaison(comparaison.cartes)
    durees = {carte.entree.duree_decodee_s for carte in comparaison.cartes}
    divergentes = len(durees) > 1
    cartes: list[dict[str, Any]] = []
    for index, carte in enumerate(comparaison.cartes):
        ligne = vue_ligne(carte.entree, lien, divergentes, comparaison.colonnes)
        ligne.pop("selection", None)
        # Garder le nom court désambiguïsé par variante/révision et date du
        # composant : le libellé historique peut inclure l'identifiant complet
        # de l'essai en cas de dates identiques, réservé aux détails.
        ligne["texte"] = carte.texte
        ligne["erreur"] = carte.erreur
        # Ces mentions sont calculées entre cartes comparées par la vue de
        # comparaison : `vue_ligne` ne peut pas les déduire de la seule entrée.
        ligne["materiel_alerte"] = carte.materiel_alerte
        ligne["distinction_temps"] = _libelle_distinction(
            DISTINCTION_TEMPS, index in meilleurs_temps, len(meilleurs_temps) > 1
        )
        ligne["distinction_ram"] = _libelle_distinction(
            DISTINCTION_RAM, index in meilleures_ram, len(meilleures_ram) > 1
        )
        cartes.append(ligne)
    return {
        "noms": ", ".join(comparaison.noms) or None,
        "empreinte": comparaison.empreinte,
        "empreinte_courte": comparaison.empreinte[:LONGUEUR_EMPREINTE_COURTE],
        "duree_audio_s": next(iter(durees)) if len(durees) == 1 else None,
        "durees_divergentes": divergentes,
        "cartes": cartes,
    }


def _libelle_distinction(base: str, present: bool, egalite: bool) -> str | None:
    """Libellé court d'une distinction, ou `None` quand elle n'est pas attribuée."""
    if not present:
        return None
    return f"{base}{EGALITE}" if egalite else base


def vues_audios_detail(detail: DetailExecutionVue) -> list[dict[str, Any]]:
    """Un résumé compact par audio du détail individuel, dans l'ordre consigné.

    Chaque élément porte l'`audio` d'origine, pour les segments et les mesures
    détaillées, et un `resume` de premier niveau construit avec le même contrat
    que les lignes de liste. La durée indiquée est celle de cet audio, jamais
    celle du lot, et le résumé n'existe que pour un audio réellement transcrit.
    """
    return [
        {"audio": audio, "resume": _resume_audio(detail, audio)}
        for audio in detail.audios
    ]


def _resume_audio(
    detail: DetailExecutionVue, audio: AudioVue
) -> dict[str, Any] | None:
    """Résumé compact d'un audio : aucun résumé inventé sans transcription."""
    transcription = audio.transcription
    if transcription is None:
        return None
    return {
        "modele": detail.libelle_modele,
        "lien": None,
        "moteur": detail.execution.moteur,
        "date_essai": detail.execution.cree_le,
        "variante": None,
        "revision": None,
        "indicateurs": audio.indicateurs,
        "annotation_ram": audio.annotation_ram,
        "materiel_alerte": audio.materiel_alerte,
        # Statut et résultat partiel restent dans le titre de l'audio : les
        # répéter ici ajouterait un second état sur la même ligne.
        "etats": [],
        "duree_audio": (
            "Audio : "
            f"{formater_duree_premier_niveau(transcription.duree_decodee_s)}"
        ),
    }


def modele_court(modele: str | None, voisines: Sequence[EntreeEmpreinte]) -> str | None:
    """Nom du modèle sans organisation, sauf homonymes du même groupe.

    Deux identifiants distincts qui n'ont que le même dernier segment gardent
    leur identifiant complet : aucun nom n'est fusionné. Un modèle absent reste
    absent.
    """
    if not modele:
        return None
    court = modele.rsplit("/", 1)[-1]
    complets = {
        voisine.modele
        for voisine in voisines
        if voisine.modele and voisine.modele.rsplit("/", 1)[-1] == court
    }
    return modele if len(complets) > 1 else court


def revision_ligne(
    entree: EntreeEmpreinte, voisines: Sequence[EntreeEmpreinte]
) -> str | None:
    """Révision courte, seulement si l'essai n'est pas distinguable autrement.

    Elle n'apparaît que lorsqu'un autre essai du groupe partage le même modèle,
    la même variante et le même moteur. Une révision non consignée est alors dite
    telle quelle, jamais remplacée par une valeur inventée.
    """
    cle = (entree.modele, entree.variante, entree.moteur)
    revisions = {
        voisine.revision or None
        for voisine in voisines
        if (voisine.modele, voisine.variante, voisine.moteur) == cle
    }
    if len(revisions) < 2:
        return None
    if not entree.revision:
        return REVISION_NON_CONSIGNEE
    connues = revisions - {None}
    longueur = LONGUEUR_REVISION_COURTE
    while len({revision[:longueur] for revision in connues}) < len(connues):
        longueur += 1
    return entree.revision[:longueur]


def etats_ligne(entree: EntreeEmpreinte) -> list[str]:
    """Libellés courts des états d'un essai, dans un ordre stable."""
    etats: list[str] = []
    if entree.statut != STATUT_OK:
        etats.append(entree.libelle_statut)
    if entree.etat != ETAT_TERMINEE:
        etats.append(entree.libelle_etat)
    etats.extend(entree.marques)
    return etats
