"""Mappings de la page Résultats, attendus par `composants.html` (tâche 1.4).

Ce module ne lit aucun fichier et n'écrit rien : il transforme les groupes et
essais du service de consultation en dictionnaires simples. Les valeurs
restent brutes ; les formats de premier niveau sont appliqués par le gabarit.

Le contrat d'une ligne est celui de `resultat_compact` : `modele`, `lien`,
`variante`, `moteur`, `date_essai`, `indicateurs`, `annotation_ram`,
`materiel_alerte`, `etats` et `duree_audio`. `duree_audio` n'est renseigné que
pour un groupe dont les durées divergent : chaque ligne indique alors la sienne,
sans durée commune inventée.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

from transcription_bench.consultation_resultats import EntreeEmpreinte, GroupeEmpreinte
from transcription_bench.indicateurs_resultats import formater_duree_premier_niveau
from transcription_bench.resultats import ETAT_TERMINEE, STATUT_OK

#: Longueur de l'empreinte affichée en titre de groupe : assez pour distinguer
#: deux fichiers de même nom ; l'empreinte complète reste dans un détail.
LONGUEUR_EMPREINTE_COURTE = 8

#: Longueur de la révision affichée quand des essais ne se distinguent que par elle.
LONGUEUR_REVISION_COURTE = 7
REVISION_NON_CONSIGNEE = "non consignée"


def vues_groupes(
    groupes: Sequence[GroupeEmpreinte], lien: Callable[[str], str]
) -> list[dict[str, Any]]:
    """Un mapping par groupe d'audio, dans l'ordre reçu du service.

    Le préfixe d'empreinte est commun à la page : il s'allonge seulement si deux
    empreintes distinctes partagent le même préfixe court.
    """
    longueur = longueur_empreintes([groupe.empreinte for groupe in groupes])
    return [vue_groupe(groupe, lien, longueur) for groupe in groupes]


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
    groupe: GroupeEmpreinte, lien: Callable[[str], str], longueur: int
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
            vue_ligne(entree, lien, divergentes, groupe.entrees)
            for entree in groupe.entrees_reelles
        ],
        "simulees": [
            vue_ligne(entree, lien, divergentes, groupe.entrees)
            for entree in groupe.entrees_simulees
        ],
    }


def vue_ligne(
    entree: EntreeEmpreinte,
    lien: Callable[[str], str],
    duree_propre: bool,
    voisines: Sequence[EntreeEmpreinte] | None = None,
) -> dict[str, Any]:
    """Une ligne de résultat : cinq valeurs, date secondaire et états visibles.

    Les états gardent les écarts qui comptent sans ouvrir le détail : statut
    du résultat, état de l'exécution si elle n'est pas terminée, puis marques
    consignées telles quelles.
    """
    return {
        "modele": modele_court(entree.modele, voisines or (entree,)),
        "lien": lien(entree.execution),
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
