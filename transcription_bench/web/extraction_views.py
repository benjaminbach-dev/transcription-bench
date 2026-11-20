"""Routes de consultation des extractions (D9), sans action ni écriture.

Les lectures, les tris, les états et le confinement restent ceux du service
partagé avec la CLI. Les paramètres GET ne servent jamais à construire un chemin.
"""

from __future__ import annotations

from collections.abc import Sequence

from flask import Flask, abort, render_template, request

from transcription_bench.consultation_resultats import (
    LIBELLES_TRI,
    LectureResultatsImpossible,
    ResultatIntrouvable,
    ResultatNonInterpretable,
    analyser_selection,
    analyser_tri,
)
from transcription_bench.extraction_consultation import (
    MAX_SELECTIONS,
    ExtractionConsultation,
    Group,
)
from transcription_bench.paths import ValeurRefusee

SELECTION_FIELD = "extraction"
GROUP_FIELD = "groupe"
SORT_FIELD = "tri"
COMPARISON_REFUSED = (
    "Comparaison refusée : sélectionnez de 2 à 6 extractions différentes du même "
    "groupe, sans mélanger extractions factices et réelles. Les identifiants et "
    "rangs doivent désigner des sources publiées et comparables. Aucun fichier "
    "n'a été modifié."
)
SORT_REFUSED = (
    "Classement refusé : un seul critère parmi temps, ram, cpu et recent est "
    "accepté dans une même requête. Aucun fichier n'a été modifié."
)
UNREADABLE_RESULTS = (
    "Le dossier des extractions n'a pas pu être lu. Vérifiez qu'il s'agit "
    "d'un dossier accessible en lecture."
)
UNINTERPRETABLE_RESULT = (
    "Extraction non interprétable : son fichier de suivi est illisible, d'un "
    "schéma inconnu ou incohérent. Aucun fichier n'a été modifié."
)


def _error(code: int, message: str):
    return render_template("erreur.html", code=code, message=message), code


def _checked_selections(groups: Sequence[Group]) -> frozenset[str]:
    """Conserve les cases lors du tri, y compris zéro ou une sélection.

    Même analyse des identités et borne que le service ; une sélection disparue,
    hors groupe ou mêlant mesures simulées et réelles n'est jamais répercutée.
    La comparaison finale applique elle-même la borne basse de deux.
    """
    keys = request.args.getlist(GROUP_FIELD)
    values = request.args.getlist(SELECTION_FIELD)
    if len(keys) > 1 or len(values) > MAX_SELECTIONS:
        raise ValeurRefusee("nombre de paramètres refusé")
    if not keys:
        if values:
            raise ValeurRefusee("groupe manquant")
        return frozenset()
    group = next((group for group in groups if group.key == keys[0]), None)
    if group is None:
        raise ValeurRefusee("groupe inconnu")
    entries = {entry.selection: entry for entry in group.entries}
    checked: set[str] = set()
    simulated: set[bool] = set()
    for value in values:
        run_id, rank = analyser_selection(value)
        selection = f"{run_id}:{rank}"
        if selection not in entries:
            raise ValeurRefusee("sélection hors groupe")
        checked.add(selection)
        simulated.add(entries[selection].simulated)
    if len(simulated) > 1:
        raise ValeurRefusee("extractions factices et réelles mêlées")
    return frozenset(checked)


def register_extraction_routes(application: Flask, service: ExtractionConsultation) -> None:
    """Enregistre uniquement des pages GET/HEAD ; les protections sont communes."""

    def listing(selecting: bool):
        try:
            sort = analyser_tri(request.args.getlist(SORT_FIELD), defaut="recent")
        except ValeurRefusee:
            return _error(400, SORT_REFUSED)
        try:
            groups = service.groups(sort)
        except LectureResultatsImpossible:
            return _error(500, UNREADABLE_RESULTS)
        try:
            checked = _checked_selections(groups) if selecting else frozenset()
        except ValeurRefusee:
            return _error(400, COMPARISON_REFUSED)
        return render_template(
            "extractions.html",
            groups=groups,
            selecting=selecting,
            checked=checked,
            sort=sort,
            sort_options=tuple(LIBELLES_TRI.items()),
            selection_field=SELECTION_FIELD,
            group_field=GROUP_FIELD,
        )

    @application.get("/extractions")
    def extractions():
        return listing(False)

    @application.get("/extractions/aide")
    def extraction_help():
        return render_template("extraction_help.html")

    @application.get("/extractions/comparaison")
    def extraction_comparisons():
        return listing(True)

    @application.get("/extractions/comparaison/<key>")
    def extraction_comparison(key: str):
        try:
            # Le formulaire de sélection transmet aussi sa clé. Elle doit, si
            # présente, être unique et identique à la clé de la route.
            keys = request.args.getlist(GROUP_FIELD)
            if keys and keys != [key]:
                raise ValeurRefusee("groupe incohérent")
            comparison = service.compare(key, request.args.getlist(SELECTION_FIELD))
        except ValeurRefusee:
            return _error(400, COMPARISON_REFUSED)
        except ResultatIntrouvable:
            abort(404)
        except ResultatNonInterpretable:
            return _error(422, UNINTERPRETABLE_RESULT)
        except LectureResultatsImpossible:
            return _error(500, UNREADABLE_RESULTS)
        return render_template("extraction_comparison.html", comparison=comparison)

    @application.get("/extractions/<run_id>")
    def extraction_detail(run_id: str):
        try:
            detail = service.detail(run_id)
        except ValeurRefusee:
            abort(400)
        except ResultatIntrouvable:
            abort(404)
        except ResultatNonInterpretable:
            return _error(422, UNINTERPRETABLE_RESULT)
        except LectureResultatsImpossible:
            return _error(500, UNREADABLE_RESULTS)
        return render_template("extraction_detail.html", detail=detail)
