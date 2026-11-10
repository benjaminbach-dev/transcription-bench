"""Source unique du texte d'aide des indicateurs, partagée web et CLI (D7).

Les textes vivent ici en **données simples** (sections, paragraphes,
définitions, listes, portions de texte en gras ou en code) ; le gabarit
`templates/aide_resultats.html` ne fait que les rendre, échappés par Jinja, en
conservant leur structure, et la commande « results explain » les imprime en
texte brut. Aucune copie parallèle : ce module est la seule source, les
exemples numériques sont produits par les formateurs de
`indicateurs_resultats`, les mêmes que les écrans, et le repère RTF vient de la
consultation. Le module n'importe ni Flask ni Jinja : la CLI peut l'utiliser
sans la couche web.

Structure des données :

- une portion (part) est un dictionnaire `{"kind": "text" | "strong" | "code",
  "text": str}` : `strong` et `code` désignent la mise en évidence du gabarit
  (`<strong>`, `<code>`), perdue sans dommage en texte brut ;
- un bloc est un dictionnaire `"paragraph"` (clé `parts`), `"definitions"`
  (clé `entries`, chaque entrée portant `term` et `definition`) ou `"list"`
  (clé `items`) ;
- une section porte un `title` et ses `blocks` ; `RESULTS_HELP` réunit le titre
  de la page, son introduction (`intro`) et les sections.

Les valeurs d'exemple (durées, mémoires, pourcentages, date) sont calculées à
l'import par les formateurs de premier niveau : elles suivent donc toute
évolution de ces formateurs, comme quand ils servaient le gabarit directement.
"""

from __future__ import annotations

from typing import Any

from transcription_bench.consultation_resultats import REPERE_RTF
from transcription_bench.indicateurs_resultats import (
    formater_date_courte,
    formater_duree_premier_niveau,
    formater_memoire_premier_niveau,
    formater_pourcentage_premier_niveau,
)

#: Titre de la page d'aide, repris par la commande « results explain ».
HELP_TITLE = "Comprendre les indicateurs"


def _part(kind: str, text: str) -> dict[str, str]:
    """Une portion de texte : son rôle et son texte, jamais de balise."""
    return {"kind": kind, "text": text}


def _text(text: str) -> dict[str, str]:
    return _part("text", text)


def _strong(text: str) -> dict[str, str]:
    return _part("strong", text)


def _code(text: str) -> dict[str, str]:
    return _part("code", text)


def _parts(*mixed: str | dict[str, str]) -> tuple[dict[str, str], ...]:
    """Portions d'une même ligne ; une chaîne nue devient une portion texte."""
    return tuple(_text(item) if isinstance(item, str) else item for item in mixed)


def _paragraph(*mixed: str | dict[str, str]) -> dict[str, Any]:
    return {"type": "paragraph", "parts": _parts(*mixed)}


def _definitions(
    *entries: tuple[str, str]
) -> dict[str, Any]:
    return {
        "type": "definitions",
        "entries": tuple(
            {"term": _parts(term), "definition": _parts(definition)}
            for term, definition in entries
        ),
    }


def _bullets(
    *items: tuple[str | dict[str, str], ...]
) -> dict[str, Any]:
    return {"type": "list", "items": tuple(_parts(*item) for item in items)}


def _section(title: str, *blocks: dict[str, Any]) -> dict[str, Any]:
    return {"title": title, "blocks": blocks}


#: Aide complète : titre, introduction, sections. Source du gabarit
#: `aide_resultats.html` et de la commande « results explain » (design D7).
RESULTS_HELP: dict[str, Any] = {
    "title": HELP_TITLE,
    "intro": _parts(
        "Cette aide explique les trois repères des cartes à partir des valeurs "
        "consignées, sans rien mesurer sur l'ordinateur qui consulte."
    ),
    "sections": (
        _section(
            "Durée, mémoire et occupation CPU",
            _definitions(
                (
                    "Transcription",
                    "Temps passé par le moteur pour transcrire cet audio, mesuré "
                    "autour de ses fenêtres de transcription. Ce n'est ni la durée "
                    "du fichier audio, ni la durée totale du lot, qui comprend "
                    "aussi le chargement du modèle, les attentes et l'écriture des "
                    "résultats.",
                ),
                (
                    "Mémoire max",
                    "Pic de mémoire résidente du processus moteur relevé après cet "
                    "audio, rapporté à la RAM totale consignée. Le pic est "
                    "cumulatif : il inclut le chargement du modèle, ses "
                    "bibliothèques et ses tampons, et il peut donc provenir d'un "
                    "audio précédent du même lot. Aucune marge restante n'est "
                    "calculée et le pic du serveur n'y est pas ajouté.",
                ),
                (
                    "CPU du moteur",
                    "Occupation moyenne du seul processus moteur, threads compris, "
                    "pendant la transcription de cet audio. 100 % désigne tous les "
                    "processeurs logiques visibles par le système de l'essai. Ce "
                    "n'est ni la charge de l'ordinateur, ni une mesure d'énergie, "
                    "ni la difficulté du calcul, ni une mesure de fluidité. Les "
                    "limites d'interprétation des pourcentages sont détaillées "
                    "dans « Contexte de l'ordinateur ».",
                ),
            ),
        ),
        _section(
            "Calcul des ratios",
            _paragraph(
                "Le CPU moyen vaut ",
                _strong(
                    "100 × temps CPU ÷ (durée de transcription × processeurs "
                    "logiques consignés)"
                ),
                ". La part de mémoire vaut ",
                _strong("100 × pic mémoire ÷ RAM totale consignée"),
                ". Les deux capacités viennent du matériel enregistré avec "
                "l'essai, jamais de l'ordinateur qui consulte la page. Un "
                "résultat ancien est recalculé à la lecture, sans réécrire ses "
                "fichiers.",
            ),
            _paragraph(
                "Un ratio supérieur à 100 % n'est pas retenu : il reste "
                "indisponible et n'est jamais ramené à 100 %, car les bornes CPU "
                "et de durée ne sont pas parfaitement simultanées et les compteurs "
                "peuvent être grossiers. Une valeur absente, un booléen, un nombre "
                "non fini, une valeur négative, un dénominateur nul ou une "
                "capacité manquante rendent aussi le ratio indisponible, jamais "
                "zéro. Un zéro réellement mesuré reste affiché comme zéro. Une "
                "carte indique « non interprétable » quand la mesure brute existe "
                "mais que le ratio ne peut pas être calculé."
            ),
        ),
        _section(
            "Formats affichés",
            _paragraph(
                "Les durées passent des secondes aux minutes puis aux heures : ",
                _code(formater_duree_premier_niveau(97)),
                " pour 97 secondes. La mémoire est exprimée en Mo et Go décimaux, "
                "avec 1 Mo = 10⁶ octets et 1 Go = 10⁹ octets : ",
                _code(formater_memoire_premier_niveau(2_400_000_000)),
                " et ",
                _code(formater_memoire_premier_niveau(16_000_000_000)),
                " pour 2,4 Go et 16 Go. Les pourcentages sont entiers : ",
                _code(formater_pourcentage_premier_niveau(15)),
                ".",
            ),
            _paragraph(
                "Une petite valeur strictement positive n'est jamais arrondie à "
                "zéro : elle s'affiche avec une borne, par exemple ",
                _code(formater_duree_premier_niveau(0.04)),
                ", ",
                _code(formater_memoire_premier_niveau(50_000)),
                " ou ",
                _code(formater_pourcentage_premier_niveau(0.4)),
                ". Les cartes montrent une date courte, par exemple ",
                _code(formater_date_courte("2024-01-02T03:04:05+00:00")),
                " : l'horodatage complet et sa précision restent consultables "
                "dans les détails.",
            ),
        ),
        _section(
            "Matériel consigné et pic cumulatif",
            _paragraph(
                "Quatre champs décident d'une mention de matériel : système "
                "d'exploitation, architecture, processeurs logiques et RAM "
                "totale. Une différence connue sur l'un d'eux affiche « matériel "
                "différent », même si un autre champ manque ; un champ absent "
                "affiche « matériel non vérifié ». Le nom du processeur est "
                "informatif : son absence seule ne déclenche aucune mention. Des "
                "métadonnées identiques ne prouvent jamais l'identité de la "
                "machine. Une ligne ne nomme que les champs en écart : ces règles "
                "générales ne sont pas répétées sur chaque résultat."
            ),
            _paragraph(
                "Le pic de mémoire est relevé sur le processus du moteur et "
                "n'est pas isolé par audio : pour tout audio qui n'est pas le "
                "premier de sa demande, la mention courte « pic cumulatif » "
                "rappelle qu'il peut provenir d'un audio précédent, même si "
                "celui-ci a échoué. La durée totale de l'opération, affichée "
                "dans les détails, comprend le décodage, le chargement, "
                "l'inférence et l'écriture : ce n'est jamais la durée d'un audio."
            ),
        ),
        _section(
            "Distinctions et comparaison",
            _paragraph(
                "Dans une comparaison, la meilleure valeur observée de temps et "
                "de RAM reçoit un libellé court juste après sa mesure, « meilleur "
                "temps » ou « meilleure RAM », égalités comprises. Aucun "
                "paragraphe de synthèse ne désigne un vainqueur ; le CPU ne "
                "reçoit aucune distinction, car une occupation plus faible n'est "
                "pas un meilleur résultat, et les mesures simulées ou partielles "
                "n'en reçoivent jamais. « Ce qui diffère » et « Toutes les mesures "
                "et informations » restent accessibles sans répéter le texte "
                "transcrit."
            ),
        ),
        _section(
            "Informations facultatives du détail",
            _paragraph(
                "La langue imposée est dite « non consignée » quand aucune n'a "
                "été relue du moteur : une famille sans choix de langue ou une "
                "information absente ne donne jamais une valeur inventée. Les "
                "timings natifs transmis par un moteur restent facultatifs : leur "
                "absence est signalée sans être un défaut, et un relevé par appel "
                "n'est ni agrégé ni converti. Un pic mémoire partiel reste le "
                "dernier relevé transmis, pas le pic final d'une exécution "
                "terminée."
            ),
        ),
        _section(
            "Marques factices, mesures simulées et audio synthétique",
            _bullets(
                (
                    _strong("FACTICE"),
                    " et ",
                    _strong("MESURES SIMULÉES"),
                    " signalent un moteur factice ou des valeurs simulées : "
                    "textes et mesures ne sont pas représentatifs d'un PC et ne "
                    "disent rien de la qualité médicale d'une transcription.",
                ),
                (
                    _strong("SYNTHÉTIQUE"),
                    " signale un audio ou un texte de test produit localement. Il "
                    "peut être transcrit par un vrai moteur, avec des mesures "
                    "réelles : cette marque seule n'affirme ni moteur factice, ni "
                    "mesures simulées.",
                ),
            ),
            _paragraph(
                "Les résultats à mesures simulées restent consultables et "
                "comparables, mais ils sont classés à part des résultats observés "
                "et ne reçoivent aucune distinction de performance."
            ),
        ),
        _section(
            "Fichiers de résultats, valeurs brutes et absences",
            _paragraph(
                "Les transcriptions sont regroupées par l'empreinte SHA-256 du "
                "fichier audio source, relue dans chaque résultat et jamais par "
                "son nom : deux fichiers de même nom et d'empreintes différentes "
                "ne sont jamais comparés, et un même contenu déposé sous deux "
                "noms reste dans un seul groupe. Une empreinte absente ou "
                "invalide n'est jamais regroupée ; le résultat reste dans "
                "l'historique complet des exécutions."
            ),
            _paragraph(
                "Une différence se décide sur la valeur brute des fichiers : les "
                "réglages demandés et effectifs sont comparés sur leur JSON "
                "complet, listes et objets compris, et une valeur formatée pour "
                "l'affichage ne décide jamais d'une différence. Deux nombres non "
                "finis (",
                _code("NaN"),
                ", ",
                _code("Infinity"),
                ", ",
                _code("-Infinity"),
                ") ou une valeur nulle peuvent s'afficher de la même façon tout "
                "en restant différents sur les données brutes.",
            ),
            _paragraph(
                "« non consigné » signifie que la clé est absente du fichier de "
                "résultat ; « indisponible » qu'elle est consignée mais nulle ou "
                "non finie ; « non mesuré » qu'aucune mesure n'existe pour cet "
                "indicateur. Aucune de ces absences n'est remplacée par zéro, et "
                "aucune page ne réécrit un fichier de résultat."
            ),
        ),
        _section(
            "RTF de référence",
            _paragraph(
                "Le RTF vaut la durée de transcription divisée par la durée "
                "décodée de l'audio ; il est recalculé à la lecture et jamais "
                "repris tel quel du fichier. Le repère d'objectif est ",
                str(REPERE_RTF),
                " : il n'exclut aucune transcription et n'en marque aucune en "
                "échec, même lorsque le RTF le dépasse largement. Sans durée "
                "décodée mesurée, aucun RTF n'est calculé.",
            ),
        ),
        _section(
            "Lecture seule, classements et historique",
            _bullets(
                (
                    "Les pages Résultats, Comparaisons et le détail ne lancent "
                    "aucune inférence, ne modifient aucun fichier et n'établissent "
                    "ni score global, ni WER, ni diff textuel automatique : les "
                    "textes sont affichés tels quels et restent à relire en "
                    "écoutant l'audio.",
                ),
                (
                    "Chaque liste de résultats se classe sur les valeurs non "
                    "arrondies : Résultats s'ouvre sur les essais les plus "
                    "récents, Comparaisons sur les temps de transcription "
                    "croissants. Les libellés « Plus récents », « Plus rapides », "
                    "« Moins de RAM » et « CPU le moins occupé » ordonnent les "
                    "essais à l'intérieur de chaque audio, jamais les audios "
                    "entre eux ; une valeur absente passe en fin et les égalités "
                    "sont départagées par date, identifiant puis ordre audio. "
                    "Dans Comparaisons, changer de classement transmet et "
                    "conserve les cases cochées, sans JavaScript ; une "
                    "comparaison accepte jusqu'à 64 sélections d'un même audio.",
                ),
                (
                    "La comparaison sélectionnée garde l'ordre reçu et n'applique "
                    "aucun tri de colonnes. L'historique des exécutions reste "
                    "complet, y compris les échecs et les résultats sans empreinte "
                    "valide.",
                ),
            ),
        ),
        _section(
            "Contexte de l'ordinateur",
            _paragraph(
                "Le détail et la comparaison sélectionnée ouvrent un bloc "
                "secondaire repliable « Contexte de l'ordinateur » : le CPU total "
                "moyen pendant la transcription de l'audio, la RAM disponible "
                "après cet audio avec sa capacité totale au même instant, puis le "
                "relevé pris juste après le chargement du modèle. Ces valeurs "
                "restent à part des indicateurs du moteur et ne servent à aucun "
                "classement."
            ),
            _paragraph(
                "Le CPU total inclut les autres programmes de l'ordinateur : il "
                "ne décrit pas le seul moteur, et d'autres logiciels ont pu "
                "l'occuper pendant l'essai. La mémoire disponible est une "
                "estimation du système à un instant donné, relevée juste après "
                "l'audio : ce n'est ni le minimum resté pendant la transcription, "
                "ni une consommation attribuée à la transcription. Le relevé après "
                "chargement et le relevé après audio décrivent deux instants "
                "distincts : ils ne se soustraient pas et ne donnent aucune marge "
                "restante."
            ),
            _paragraph(
                "Les pourcentages reposent sur les ressources visibles par le "
                "système : processeurs logiques, hyperthreading, quotas système, "
                "affinités, conteneurs et machines virtuelles limitent ce qu'ils "
                "représentent. Un quota, une affinité ou une ressource "
                "virtualisée n'est jamais une capacité matérielle garantie. Une "
                "observation décrit le contexte de cet essai, sur un ordinateur "
                "partagé ou virtualisé : elle n'est ni une propriété du modèle, "
                "ni une garantie de rapidité ou de fluidité, ni une garantie de "
                "confort d'usage, ni une preuve de performance sur un autre "
                "ordinateur. Sans observation, ou face à un objet écarté avant "
                "écriture, illisible ou d'une version inconnue, le bloc affiche "
                "« non mesuré » : aucune valeur n'est alors déduite du pic "
                "mémoire du moteur ni du CPU du moteur."
            ),
        ),
        _section(
            "Limites d'interprétation",
            _bullets(
                (
                    "Un CPU peu occupé ne veut pas dire un texte meilleur, plus "
                    "rapide ou plus fluide. La durée et la mémoire se lisent "
                    "séparément.",
                ),
                (
                    "La mémoire est un pic cumulatif, pas une mesure isolée par "
                    "audio ; le pic peut avoir été atteint pendant le chargement "
                    "du modèle ou un audio précédent.",
                ),
                (
                    "Ces valeurs sont des mesures observées une seule fois par "
                    "essai, sans intervalle d'incertitude, sans garantie de "
                    "performance et sans score global de qualité ou d'efficacité.",
                ),
                (
                    "Une mesure absente affiche « non mesuré » et un résultat "
                    "partiel est signalé comme tel ; une absence n'est jamais "
                    "remplacée par zéro.",
                ),
            ),
        ),
    ),
}
