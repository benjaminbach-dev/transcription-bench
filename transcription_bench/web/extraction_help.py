"""Source unique du texte d'aide des indicateurs d'extraction (D9, tâche 4.2).

Même principe que `results_help.py` : les textes vivent ici en **données
simples** (sections, paragraphes, définitions, listes, portions de texte en
gras ou en code), lues par la commande « extract explain » et, plus tard, par
le gabarit de la page `/extractions/aide` (tâche 4.3, non construite ici).
Aucune copie parallèle de ces textes ailleurs ; aucune logique de rendu HTML
ni Jinja dans ce module, pour que la CLI puisse l'utiliser seule.

Mêmes structures de blocs que `results_help.py` (portion, paragraphe,
définitions, liste, section) : les petites fonctions de construction sont
reprises ici à l'identique plutôt que partagées, pour ne pas toucher ce
module existant hors du périmètre de la tâche.
"""

from __future__ import annotations

from typing import Any

#: Titre de la page d'aide, repris par la commande « extract explain ».
HELP_TITLE = "Comprendre les indicateurs d'extraction"


def _part(kind: str, text: str) -> dict[str, str]:
    return {"kind": kind, "text": text}


def _text(text: str) -> dict[str, str]:
    return _part("text", text)


def _strong(text: str) -> dict[str, str]:
    return _part("strong", text)


def _code(text: str) -> dict[str, str]:
    return _part("code", text)


def _parts(*mixed: str | dict[str, str]) -> tuple[dict[str, str], ...]:
    return tuple(_text(item) if isinstance(item, str) else item for item in mixed)


def _paragraph(*mixed: str | dict[str, str]) -> dict[str, Any]:
    return {"type": "paragraph", "parts": _parts(*mixed)}


def _definitions(*entries: tuple[str, str]) -> dict[str, Any]:
    return {
        "type": "definitions",
        "entries": tuple(
            {"term": _parts(term), "definition": _parts(definition)}
            for term, definition in entries
        ),
    }


def _bullets(*items: tuple[str | dict[str, str], ...]) -> dict[str, Any]:
    return {"type": "list", "items": tuple(_parts(*item) for item in items)}


def _section(title: str, *blocks: dict[str, Any]) -> dict[str, Any]:
    return {"title": title, "blocks": blocks}


#: Aide complète : titre, introduction, sections. Source de la commande
#: « extract explain » et du futur gabarit `/extractions/aide` (design D9).
EXTRACTION_HELP: dict[str, Any] = {
    "title": HELP_TITLE,
    "intro": _parts(
        "Cette aide définit les indicateurs d'une extraction à partir des "
        "valeurs consignées, sans rien mesurer sur l'ordinateur qui consulte."
    ),
    "sections": (
        _section(
            "Tokens, délai et vitesses",
            _definitions(
                (
                    "Tokens entrée / sortie",
                    "Nombre de tokens du prompt soumis au modèle (grille, "
                    "transcription et consignes) et nombre de tokens produits "
                    "en réponse. Ce n'est ni un nombre de mots, ni une mesure "
                    "de qualité.",
                ),
                (
                    "Délai avant le premier token",
                    "Temps écoulé entre l'envoi du prompt et la réception du "
                    "premier token généré : lecture du prompt et calcul du "
                    "premier token compris. Le chargement du modèle est "
                    "mesuré séparément.",
                ),
                (
                    "Durée de génération",
                    "Temps passé à produire les tokens de sortie, du premier au "
                    "dernier, sans le temps de lecture du prompt ni le "
                    "chargement du modèle.",
                ),
                (
                    "Vitesse de génération",
                    "Nombre de tokens de sortie moins un, divisé par la durée "
                    "entre le premier et le dernier token. Elle est absente "
                    "si moins de deux tokens ont été produits. Une vitesse "
                    "plus élevée ne dit rien de la qualité de la grille remplie.",
                ),
                (
                    "Vitesse de lecture estimée",
                    "Nombre de tokens d'entrée divisé par le délai avant le "
                    "premier token. C'est une estimation : ce délai inclut "
                    "aussi le calcul du premier token, pas seulement la lecture.",
                ),
                (
                    "Durée d'extraction",
                    "Temps total consacré à cette source : lecture du prompt, "
                    "génération, détokenisation et validation comprises, hors "
                    "chargement du modèle.",
                ),
            ),
        ),
        _section(
            "Mémoire et CPU du moteur",
            _definitions(
                (
                    "Mémoire max",
                    "Pic de mémoire résidente du processus moteur, rapporté à "
                    "la RAM totale consignée de la machine d'extraction. "
                    "Comme pour la transcription, ce pic peut provenir du "
                    "chargement du modèle ou d'une source précédente du même "
                    "lot.",
                ),
                (
                    "CPU du moteur",
                    "Occupation moyenne du seul processus moteur, threads "
                    "compris, pendant l'extraction de cette source. 100 % "
                    "désigne tous les processeurs logiques visibles par le "
                    "système de l'essai ; ce n'est ni la charge de "
                    "l'ordinateur ni une mesure de difficulté ou d'énergie.",
                ),
            ),
        ),
        _section(
            "Conformité : une mesure de forme, pas de contenu",
            _paragraph(
                "La ",
                _strong("conformité"),
                " indique seulement que la sortie du modèle respecte le "
                "schéma attendu de la grille (clés, types, listes) : elle ne "
                "mesure ni l'exactitude des informations extraites, ni leur "
                "pertinence médicale. Une source ",
                _strong("non conforme"),
                " a produit une sortie qui ne respecte pas ce schéma ou a "
                "atteint la limite de tokens de sortie ; une "
                "source ",
                _strong("en erreur"),
                " a échoué avant ou pendant la génération ; une source ",
                _strong("non traitée"),
                " ne dispose d'aucun résultat publié, notamment après une "
                "interruption avant la publication.",
            ),
            _paragraph(
                "Une grille bien remplie et conforme au schéma n'est "
                "jamais une preuve d'exactitude médicale : la vérification du "
                "contenu appartient à un humain ou à un agent local, "
                "extérieur à ce programme, qui relit la grille à côté de la "
                "transcription source."
            ),
        ),
        _section(
            "Factices, mesures simulées et extractions non comparables",
            _bullets(
                (
                    _strong("FACTICE"),
                    " et ",
                    _strong("MESURES SIMULÉES"),
                    " signalent un moteur d'extraction factice ou des valeurs "
                    "simulées : la grille remplie et ses mesures ne sont pas "
                    "représentatives d'un modèle réel.",
                ),
                (
                    _strong("SOURCE FACTICE"),
                    " signale seulement une transcription source factice. "
                    "Les mesures d'un moteur réel restent des mesures réelles.",
                ),
                (
                    "Une comparaison ne mélange jamais une extraction factice "
                    "et une extraction réelle, et ne porte que sur des "
                    "extractions d'un même groupe (même texte source, même "
                    "grille et même schéma généré).",
                ),
            ),
        ),
        _section(
            "Regroupement, lecture seule et historique",
            _paragraph(
                "Les extractions sont regroupées par le triplet des "
                "empreintes du texte source, de la grille copiée et du "
                "schéma généré : deux extractions d'une même source avec des "
                "grilles différentes n'entrent jamais dans le même groupe et "
                "ne peuvent pas être comparées. Une version de consignes "
                "différente au sein d'un même groupe est signalée, jamais "
                "séparée."
            ),
            _paragraph(
                "Aucune consultation d'extraction ne modifie de fichier, "
                "n'accède au réseau ni ne calcule de score de qualité ou de "
                "classement de modèle : les meilleures valeurs observées de "
                "durée et de mémoire peuvent être signalées, comme pour les "
                "transcriptions, jamais un meilleur modèle. L'historique "
                "conserve toutes les extractions enregistrées, y compris en "
                "erreur, non conformes ou non traitées."
            ),
        ),
    ),
}
