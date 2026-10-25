"""Point d'injection de la récupération des exécutions antérieures.

La clôture effective d'une exécution restée `running` — terminaison vérifiée du
moteur survivant par PID et heure de création, passage en état `abandoned`,
audios non traités signalés — relève de la tâche 6.5 et n'est pas implémentée.
La CLI appelle donc ce point d'injection après le verrou d'instance et avant la
création de l'application.

La fonction par défaut ne fait aucune récupération et ne modifie aucun fichier :
elle refuse explicitement le démarrage si un `run.json` antérieur n'est pas dans
un état final reconnu, plutôt que de laisser croire à une reprise ou de laisser
l'application travailler sur un état douteux. Un démarrage sans résultat
antérieur, ou avec des résultats tous finaux, se poursuit normalement.

Hypothèse à réconcilier avec la tâche 6.4 : la clé d'état de `run.json` est
`etat`, avec les valeurs finales `completed`, `interrupted`, `failed` et
`abandoned`, et `running` pendant l'exécution. Un fichier illisible, non objet
ou sans état reconnu est traité comme non traitable, sans être réécrit.
"""

from __future__ import annotations

import json
from pathlib import Path

NOM_DOSSIER_RESULTATS = "results"
NOM_FICHIER_EXECUTION = "run.json"
CLE_ETAT = "etat"
ETAT_EN_COURS = "running"
ETATS_FINAUX = frozenset({"completed", "interrupted", "failed", "abandoned"})


class EtatAnterieurNonTraitable(RuntimeError):
    """Refus de démarrer : une exécution antérieure exige la tâche 6.5."""


def verifier_executions_anterieures(donnees: Path | str) -> None:
    """Refuse le démarrage si un résultat antérieur n'est pas dans un état final.

    Lecture seule : aucun `run.json` n'est créé, modifié ni supprimé. Les
    résultats finaux, y compris interrompus ou échoués, sont laissés tels quels.
    """
    dossier_resultats = Path(donnees) / NOM_DOSSIER_RESULTATS
    if not dossier_resultats.is_dir():
        return
    for run_json in sorted(dossier_resultats.glob(f"*/{NOM_FICHIER_EXECUTION}")):
        etat = _lire_etat(run_json)
        if etat in ETATS_FINAUX:
            continue
        if etat == ETAT_EN_COURS:
            detail = "exécution restée en cours"
        else:
            detail = f"état inconnu {etat!r}"
        raise EtatAnterieurNonTraitable(
            f"démarrage refusé : résultat antérieur non traitable ({detail}) : "
            f"{run_json}. La clôture automatique des exécutions abandonnées "
            "relève de la tâche 6.5 et n'est pas implémentée ; aucun fichier "
            "n'a été modifié. Traitez ce résultat manuellement avant de redémarrer."
        )


def _lire_etat(run_json: Path) -> str:
    """Lit la clé d'état de `run.json` ; toute anomalie est non traitable."""
    try:
        contenu = json.loads(run_json.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as erreur:
        raise EtatAnterieurNonTraitable(
            f"démarrage refusé : résultat antérieur illisible : {run_json} "
            f"({erreur}). Aucun fichier n'a été modifié."
        ) from None
    if not isinstance(contenu, dict):
        raise EtatAnterieurNonTraitable(
            f"démarrage refusé : résultat antérieur incohérent : {run_json} "
            "(objet JSON attendu). Aucun fichier n'a été modifié."
        )
    etat = contenu.get(CLE_ETAT)
    if not isinstance(etat, str) or not etat:
        raise EtatAnterieurNonTraitable(
            f"démarrage refusé : résultat antérieur incohérent : {run_json} "
            f"(clé {CLE_ETAT!r} absente ou invalide). Aucun fichier n'a été modifié."
        )
    return etat
