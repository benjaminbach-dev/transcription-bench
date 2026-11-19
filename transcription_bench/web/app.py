"""Fabrique Flask sans effets de bord, routes de consultation et pages d'erreur.

La fabrique ne prend aucun verrou d'instance, ne démarre ni serveur ni thread et
n'écrit aucun fichier : les tests peuvent créer l'application sans toucher aux
données réelles. Les routes valident la demande puis délèguent aux services
injectés ; le lancement HTTP (Waitress) relève de la CLI.

L'interface est en consultation seule (change `alleger-interface-web`, design D1) :
la CLI est la seule interface d'action. Les pages réelles sont Résultats, le détail
d'un résultat, l'aide des indicateurs, Comparaisons et l'historique complet des
exécutions (`/executions`, sans formulaire). `GET /` redirige vers Résultats. Les
anciennes pages d'action et leurs POST ne sont plus routés : ils répondent 404, et
toute méthode autre que GET et HEAD répond 405 sur une route existante, OPTIONS
compris.

Un hook `before_request` vérifie chaque requête avant toute lecture de corps : Host,
puis méthode.

Deux routes GET servent les ressources du paquet, jamais un dossier statique :
`/sumi.css` (copie figée de Sumi.css, MIT) et `/app.css` (complément du projet),
avec type explicite, `nosniff` et `no-cache`. Le chemin lu est construit depuis ce
module, jamais depuis la requête. Aucun script n'est servi (change
`alleger-interface-web`, D2) : `/app.js` répond 404.
Les réponses HTML portent une politique de sécurité des contenus stricte (D6, D2),
pages d'erreur comprises, sans `unsafe-inline` ni `unsafe-eval` ; elle ne remplace pas le contrôle
`Host`.

La page Résultats (tâche 1.4) regroupe les essais par empreinte
audio, tri commun appliqué dans chaque groupe, et renvoie vers l'historique
complet des exécutions dans la page Historique. Le détail d'une transcription : texte,
segments, métadonnées, mesures et marques, en lecture seule. Le détail
individuel (tâches 3.2 et 2.2) suit la même tête de lecture qu'une carte de comparaison
— le composant compact de valeurs puis le texte complet — avec l'annotation du pic mémoire
cumulatif, une mention de matériel différent ou non vérifié et les états
partiels visibles hors de tout accordéon fermé, chaque audio portant son ancre. La page de
comparaison (tâche 7.2) regroupe les transcriptions par empreinte SHA-256 du
fichier audio source et affiche côte à côte celles d'un même fichier, avec les
réglages effectifs qui diffèrent, les états, les marques et les mesures
principales. La liste des groupes se classe par temps, mémoire, CPU ou date
(tâche 2.1) selon un critère borné, refusé (400) s'il est inconnu ou répété ;
ses boutons de tri sont des boutons GET du formulaire de sélection, qui
transmettent aussi les cases cochées et l'empreinte de leur groupe. La route de
liste revalide ces sélections comme la comparaison (valeur, identité, groupe,
borne du nombre de paramètres) et refuse en 400 une empreinte forgée, une
sélection disparue ou venue d'un autre groupe ; la comparaison sélectionnée
garde l'ordre reçu. Une comparaison (tâches 3.1 et 2.2)
affiche une carte compacte par transcription — modèle, durée audio commune ou
propre à l'essai, temps, RAM, CPU, moteur, date et états — avec les meilleures
mesures de temps et de RAM signalées près des valeurs, puis le texte complet ;
« Ce qui diffère » et « Toutes les mesures et informations » restent accessibles
par détails. Lecture seule également : aucune route de résultats ne lance
d'inférence ni ne modifie un fichier.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from flask import Flask, Response, abort, redirect, render_template, request, url_for
from werkzeug.exceptions import HTTPException, MethodNotAllowed

from transcription_bench.consultation_resultats import (
    LIBELLES_TRI,
    REPERE_RTF,
    SELECTIONS_MAX_COMPARAISON,
    SEPARATEUR_SELECTION,
    TRI_RECENT,
    ConsultationResultats,
    GroupeEmpreinte,
    LectureResultatsImpossible,
    ResultatIntrouvable,
    ResultatNonInterpretable,
    analyser_selection,
    analyser_tri,
)
from transcription_bench.indicateurs_resultats import (
    formater_date_courte,
    formater_duree_premier_niveau,
    formater_memoire_premier_niveau,
    formater_pourcentage_premier_niveau,
)
from transcription_bench.paths import ValeurRefusee
from transcription_bench.web.results_help import RESULTS_HELP
from transcription_bench.web.vues_resultats import (
    vue_comparaison,
    vues_audios_detail,
    vues_groupes,
)

TYPE_FEUILLE = "text/css; charset=utf-8"
# Dossier des ressources locales du paquet (feuilles), jamais servi comme
# répertoire : chaque route lit un nom fixe décidé dans ce module.
DOSSIER_FEUILLES = Path(__file__).resolve().parent / "ressources"
NOM_FEUILLE_SUMI = "sumi.min.css"
NOM_FEUILLE_APP = "app.css"
# Design D6, puis D2 du change `alleger-interface-web` : aucun script (l'interface
# n'en a plus besoin), ni incorporé ni local ; styles et connexions restent limités
# à l'origine locale, sans frame ni base d'URL modifiable.
POLITIQUE_CONTENU = (
    "default-src 'self'; script-src 'none'; style-src 'self'; "
    "connect-src 'self'; img-src 'self'; object-src 'none'; "
    "form-action 'self'; frame-ancestors 'none'; base-uri 'none'"
)
CHAMP_SELECTION_COMPARAISON = "transcription"
CHAMP_TRI_CLASSEMENT = "tri"
# Groupe dont une liste conserve les cases cochées : une seule empreinte bornée,
# jamais un paramètre de redirection libre.
CHAMP_EMPREINTE_GROUPE = "empreinte"
HOTES_AUTORISES = ("127.0.0.1", "localhost")
METHODES_LECTURE = ("GET", "HEAD")

# Messages partagés avec la CLI (`commands.py`) : l'interface web ne les emploie
# plus (tâche 1.1 du change `alleger-interface-web`) ; leur déplacement est prévu
# avec la tâche 2.2.
MESSAGES_ACTION = {
    "dossiers-verifies": "Dossiers de données vérifiés.",
    "arret-demande": (
        "Arrêt de l'exécution demandé : les résultats d'audios déjà reçus sont "
        "conservés et les audios restants sont signalés non traités. Le créneau "
        "reste occupé jusqu'à la fin réelle du processus moteur."
    ),
    "arret-incomplet": (
        "Arrêt demandé, mais le processus moteur n'a pas pu être terminé, même "
        "après kill : il peut encore tourner. Le créneau reste occupé jusqu'à sa "
        "fin réelle et aucun résultat n'est publié avant."
    ),
    "verification-lancee": (
        "Vérification distante lancée : le résultat apparaîtra après actualisation."
    ),
    "telechargement-lance": (
        "Téléchargement lancé à la révision vérifiée : le modèle ne sera prêt "
        "qu'après succès complet."
    ),
    "modele-deja-present": "Ce modèle est déjà présent : aucun téléchargement n'a été lancé.",
    "modele-supprime": "Modèle local supprimé.",
}

MESSAGE_DOSSIER_AUDIO_INACCESSIBLE = (
    "Le dossier d'entrée n'a pas pu être lu : aucun audio n'est listé. "
    "Vérifiez qu'il s'agit d'un dossier accessible en lecture."
)


MESSAGES_ERREUR = {
    400: "Demande refusée : valeur invalide.",
    403: "Requête refusée : adresse invalide.",
    404: "Page introuvable.",
    405: "Méthode non autorisée pour cette adresse.",
    500: "Erreur interne du serveur.",
}

MESSAGE_ERREUR_GENERIQUE = "La requête n'a pas pu être traitée."

MESSAGE_RESULTATS_INACCESSIBLES = (
    "Le dossier des résultats n'a pas pu être lu : aucune exécution n'est listée. "
    "Vérifiez qu'il s'agit d'un dossier accessible en lecture."
)

MESSAGE_RESULTAT_NON_INTERPRETABLE = (
    "Résultat non interprétable : son fichier de suivi est illisible, d'un schéma "
    "inconnu ou incohérent. Le fichier n'a pas été modifié et aucune donnée n'est "
    "affichée."
)

MESSAGE_COMPARAISON_REFUSEE = (
    "Comparaison refusée : sélectionnez au moins deux transcriptions d'un même "
    "fichier audio, reconnues par la même empreinte SHA-256. Une sélection ne peut "
    "ni mélanger deux fichiers différents, ni désigner une transcription absente, "
    "ni porter un identifiant invalide. Aucun fichier n'a été modifié."
)

MESSAGE_TRI_REFUSE = (
    "Classement refusé : un seul critère parmi temps, ram, cpu et recent est "
    "accepté dans une même requête. Aucun fichier n'a été modifié."
)


@dataclass(frozen=True)
class ConfigApplication:
    """Paramètres d'exploitation connus de l'interface.

    `port` est le port d'écoute réel ; `dossier_data` est la racine des données
    déjà préparée par la CLI.
    """

    port: int
    dossier_data: Path


@dataclass(frozen=True)
class ServicesApplication:
    """Services injectés dans l'application, pour rester testables.

    `resultats` est le service de consultation des résultats (tâche 7.1),
    strictement en lecture ; s'il est absent, la fabrique en construit un sur le
    dossier de données, sans aucune E/S. Il est injectable pour rendre les
    lectures illisibles ou incohérentes testables. L'application ne reçoit aucun
    service d'action : créneau d'opération, supervision de moteur et préparation
    relèvent des commandes (change `alleger-interface-web`, D4).
    """

    resultats: ConsultationResultats | None = None


def create_app(config: ConfigApplication, services: ServicesApplication) -> Flask:
    """Construit l'application Flask, sans aucun effet de bord."""
    application = Flask(__name__, static_folder=None)
    application.config.update(
        DEBUG=False,
        PORT=config.port,
        DOSSIER_DATA=str(config.dossier_data),
    )
    # Initialiser Jinja après la configuration : FLASK_DEBUG ne doit pas
    # activer son rechargement automatique. Les formats détaillés restent inchangés.
    application.jinja_env.globals.update(
        formater_date_courte=formater_date_courte,
        formater_duree_premier_niveau=formater_duree_premier_niveau,
        formater_memoire_premier_niveau=formater_memoire_premier_niveau,
        formater_pourcentage_premier_niveau=formater_pourcentage_premier_niveau,
        # Source unique du texte d'aide des indicateurs (design D7) : le
        # gabarit `aide_resultats.html` ne fait que la rendre, échappée.
        results_help=RESULTS_HELP,
    )
    hotes = frozenset(f"{adresse}:{config.port}" for adresse in HOTES_AUTORISES)
    # Service absent : construit sur le dossier de données, sans aucune E/S.
    service_resultats = (
        ConsultationResultats(config.dossier_data)
        if services.resultats is None
        else services.resultats
    )

    @application.before_request
    def verifier_requete() -> None:
        _verifier_hote(hotes)
        _verifier_methode()

    @application.after_request
    def ajouter_politique_contenu(reponse: Response) -> Response:
        """Pose la CSP sur les réponses HTML, pages d'erreur réelles comprises.

        Le type est lu sur la réponse finale : un rendu Jinja, une page d'erreur
        404/405/500 et le corps d'une redirection sont tous du HTML. Les
        ressources locales (les feuilles) ne la reçoivent pas : elle décrit
        ce que le document peut charger, pas son propre type.
        """
        if reponse.mimetype == "text/html":
            reponse.headers["Content-Security-Policy"] = POLITIQUE_CONTENU
        return reponse

    _enregistrer_routes(application, service_resultats)
    _enregistrer_erreurs(application)
    return application


def _reponse_ressource(nom_fichier: str, type_mime: str) -> Response:
    """Ressource locale figée du paquet, servie hors ligne avec des en-têtes fixes.

    Le fichier est désigné par une constante de ce module, jamais par la requête :
    aucune valeur reçue ne peut conduire à un autre fichier. Le type est posé
    explicitement, le type MIME deviné par le registre Windows n'étant pas fiable.
    """
    contenu = (DOSSIER_FEUILLES / nom_fichier).read_bytes()
    reponse = Response(contenu, status=200)
    reponse.headers["Content-Type"] = type_mime
    reponse.headers["X-Content-Type-Options"] = "nosniff"
    reponse.headers["Cache-Control"] = "no-cache"
    return reponse


def _verifier_hote(hotes: frozenset[str]) -> None:
    """Refuse toute requête dont l'en-tête `Host` n'est pas local, port compris."""
    if request.host not in hotes:
        abort(403)


def _verifier_methode() -> None:
    """Refuse toute méthode autre que GET et HEAD, avant la lecture d'un corps.

    Une route existante répond 405 avec l'en-tête `Allow`, y compris pour
    `OPTIONS` (réponse automatique de Flask écartée) ; une adresse inconnue
    répond 404. Aucune route ne reçoit donc de POST.
    """
    if request.method in METHODES_LECTURE:
        return
    if request.url_rule is not None or isinstance(
        request.routing_exception, MethodNotAllowed
    ):
        raise MethodNotAllowed(valid_methods=METHODES_LECTURE)
    abort(404)


def _page_erreur(code: int, message: str) -> tuple[str, int]:
    """Réponse d'erreur HTML à message fixe, sans texte d'exception ni cible."""
    return render_template("erreur.html", code=code, message=message), code


def _lien_resultat(identifiant: str) -> str:
    """Adresse locale du détail d'une exécution, construite par la route fixe."""
    return url_for("resultat_detail", identifiant=identifiant)


def _identites_groupes(
    groupes: Sequence[GroupeEmpreinte],
) -> dict[str, frozenset[str]]:
    """Identités `exécution:ordre` des transcriptions réellement listées, par groupe."""
    return {
        groupe.empreinte: frozenset(
            f"{entree.execution}{SEPARATEUR_SELECTION}{entree.ordre}"
            for entree in groupe.entrees
        )
        for groupe in groupes
    }


def selections_liste(
    empreintes: Sequence[str],
    valeurs: Sequence[str],
    identites_par_groupe: Mapping[str, frozenset[str]],
) -> frozenset[str]:
    """Sélections cochées d'une liste, revalidées comme pour la comparaison.

    Une liste peut n'avoir aucune case cochée : `valeurs` vide avec l'empreinte
    du groupe donne un ensemble vide. Une empreinte fournie doit être unique et
    désigner un groupe réellement listé, même sans case cochée : un nom de
    groupe forgé est refusé (400 côté route). Dès qu'une sélection est présente,
    chaque valeur est décodée par `analyser_selection` puis doit désigner une
    transcription de ce groupe : une valeur invalide, une identité disparue ou
    une sélection d'un autre groupe est refusée par `ValeurRefusee`.

    La borne `SELECTIONS_MAX_COMPARAISON` s'applique au nombre de valeurs reçues,
    avant toute analyse, comme pour la comparaison ; une sélection répétée à
    l'identique reste dédoublonnée en deçà de cette borne, comme le fait déjà
    `ConsultationResultats.comparer`. Aucune valeur n'est devinée ni fusionnée
    avec un autre groupe.
    """
    if len(valeurs) > SELECTIONS_MAX_COMPARAISON:
        raise ValeurRefusee(
            f"sélections refusées : {SELECTIONS_MAX_COMPARAISON} au maximum par requête"
        )
    if len(empreintes) > 1:
        raise ValeurRefusee("une seule empreinte de groupe de sélection attendue")
    if not empreintes:
        if valeurs:
            raise ValeurRefusee(
                "sélection refusée : groupe de la sélection non identifié"
            )
        return frozenset()
    attendues = identites_par_groupe.get(empreintes[0])
    if attendues is None:
        raise ValeurRefusee(
            "sélection refusée : groupe inconnu, disparu ou hors des résultats listés"
        )
    cochees: set[str] = set()
    for valeur in valeurs:
        identifiant, ordre = analyser_selection(valeur)
        selection = f"{identifiant}{SEPARATEUR_SELECTION}{ordre}"
        if selection not in attendues:
            raise ValeurRefusee(
                "sélection refusée : transcription invalide, disparue ou hors du "
                "groupe demandé"
            )
        cochees.add(selection)
    return frozenset(cochees)


def _enregistrer_routes(
    application: Flask,
    service_resultats: ConsultationResultats,
) -> None:
    @application.get("/")
    def accueil() -> Response:
        """Entrée directe : l'accueil historique n'est plus une rubrique (D1).

        La redirection est locale et ne transmet aucun paramètre reçu : aucun
        `next` libre n'est répercuté.
        """
        return redirect(url_for("resultats"), code=302)

    @application.get("/sumi.css")
    def feuille_sumi() -> Response:
        """Copie figée de Sumi.css, servie depuis le paquet, sans réseau."""
        return _reponse_ressource(NOM_FEUILLE_SUMI, TYPE_FEUILLE)

    @application.get("/app.css")
    def feuille_app() -> Response:
        """Feuille complémentaire du projet, chargée après Sumi.css."""
        return _reponse_ressource(NOM_FEUILLE_APP, TYPE_FEUILLE)

    @application.get("/executions")
    def executions() -> str:
        """Historique complet des exécutions, en lecture seule (tâche 1.1).

        Toutes les exécutions enregistrées, y compris les échecs, les interruptions
        et les résultats non interprétables, des plus récentes aux plus anciennes.
        Aucun formulaire ni action : le lancement relève des commandes du programme.
        """
        try:
            executions_enregistrees = service_resultats.lister()
        except LectureResultatsImpossible:
            executions_enregistrees = ()
            erreur_historique = MESSAGE_RESULTATS_INACCESSIBLES
        else:
            erreur_historique = None
        return render_template(
            "executions.html",
            executions=executions_enregistrees,
            erreur_historique=erreur_historique,
            dossier=service_resultats.dossier_resultats,
        )

    @application.get("/resultats")
    def resultats() -> str:
        """Résultats groupés par audio, avec accès à l'historique complet.

        Le critère `tri` vaut `recent` par défaut et s'applique dans chaque groupe
        seulement ; un critère inconnu ou répété est refusé (400). L'historique
        complet des exécutions vit désormais dans la page Historique (tâche 3.1),
        atteinte par un lien secondaire.
        """
        try:
            tri = analyser_tri(
                request.args.getlist(CHAMP_TRI_CLASSEMENT), defaut=TRI_RECENT
            )
        except ValeurRefusee:
            return _page_erreur(400, MESSAGE_TRI_REFUSE)
        try:
            groupes = service_resultats.groupes_par_empreinte(tri)
        except LectureResultatsImpossible:
            groupes = ()
            erreur_dossier = MESSAGE_RESULTATS_INACCESSIBLES
        else:
            erreur_dossier = None
        return render_template(
            "resultats.html",
            groupes=vues_groupes(groupes, _lien_resultat),
            erreur_dossier=erreur_dossier,
            tri=tri,
            criteres_tri=tuple(LIBELLES_TRI.items()),
            repere_rtf=REPERE_RTF,
        )

    @application.get("/resultats/<identifiant>")
    def resultat_detail(identifiant: str):
        """Détail en lecture seule d'une exécution et de ses transcriptions."""
        try:
            detail = service_resultats.detail(identifiant)
        except ValeurRefusee:
            abort(400)
        except ResultatIntrouvable:
            abort(404)
        except ResultatNonInterpretable:
            return _page_erreur(422, MESSAGE_RESULTAT_NON_INTERPRETABLE)
        return render_template(
            "resultat.html",
            detail=detail,
            vues_audios=vues_audios_detail(detail),
            repere_rtf=REPERE_RTF,
        )

    @application.get("/resultats/aide")
    def aide_resultats() -> str:
        """Aide locale fixe : indicateurs, ratios, formats, fichiers et limites.

        Route GET fixe, distincte de la route dynamique `/resultats/<identifiant>` :
        aucune donnée de résultat n'est lue et aucune entrée de menu n'est ajoutée.
        """
        return render_template("aide_resultats.html", repere_rtf=REPERE_RTF)

    @application.get("/resultats/comparaison")
    def comparaisons() -> str:
        """Groupes de transcriptions par empreinte, listes classées par `tri`.

        Les cases de sélection sont dans le formulaire du groupe ; les boutons de
        tri sont des boutons GET de ce formulaire (`name=tri` du `formaction` de
        liste) qui transmettent aussi les cases cochées et l'empreinte du groupe.
        La route revalide `tri` et ces sélections comme la comparaison : un
        critère inconnu ou répété, une empreinte absente ou non listée et une
        sélection invalide, disparue ou d'un autre groupe valent 400.
        """
        try:
            tri = analyser_tri(request.args.getlist(CHAMP_TRI_CLASSEMENT))
        except ValeurRefusee:
            return _page_erreur(400, MESSAGE_TRI_REFUSE)
        try:
            groupes = service_resultats.groupes_par_empreinte(tri)
        except LectureResultatsImpossible:
            groupes = ()
            erreur_dossier = MESSAGE_RESULTATS_INACCESSIBLES
        else:
            erreur_dossier = None
        cochees = frozenset()
        if erreur_dossier is None:
            try:
                cochees = selections_liste(
                    request.args.getlist(CHAMP_EMPREINTE_GROUPE),
                    request.args.getlist(CHAMP_SELECTION_COMPARAISON),
                    _identites_groupes(groupes),
                )
            except ValeurRefusee:
                return _page_erreur(400, MESSAGE_COMPARAISON_REFUSEE)
        return render_template(
            "comparaisons.html",
            groupes=vues_groupes(
                groupes,
                _lien_resultat,
                champ_selection=CHAMP_SELECTION_COMPARAISON,
                cochees=cochees,
            ),
            erreur_dossier=erreur_dossier,
            champ_tri=CHAMP_TRI_CLASSEMENT,
            champ_empreinte=CHAMP_EMPREINTE_GROUPE,
            tri=tri,
            criteres_tri=tuple(LIBELLES_TRI.items()),
        )

    @application.get("/resultats/comparaison/<empreinte>")
    def comparaison(empreinte: str):
        """Comparaison côte à côte, limitée à une seule empreinte audio."""
        try:
            selections = tuple(
                analyser_selection(valeur)
                for valeur in request.args.getlist(CHAMP_SELECTION_COMPARAISON)
            )
            vue = service_resultats.comparer(empreinte, selections)
        except ValeurRefusee:
            return _page_erreur(400, MESSAGE_COMPARAISON_REFUSEE)
        except ResultatIntrouvable:
            abort(404)
        except ResultatNonInterpretable:
            return _page_erreur(422, MESSAGE_RESULTAT_NON_INTERPRETABLE)
        return render_template(
            "comparaison.html",
            comparaison=vue,
            entete_audio=vue_comparaison(vue, _lien_resultat),
            repere_rtf=REPERE_RTF,
        )


def _enregistrer_erreurs(application: Flask) -> None:
    @application.errorhandler(HTTPException)
    def gerer_erreur_http(erreur: HTTPException):
        code = erreur.code or 500
        reponse = erreur.get_response()
        reponse.set_data(
            render_template(
                "erreur.html",
                code=code,
                message=MESSAGES_ERREUR.get(code, MESSAGE_ERREUR_GENERIQUE),
            )
        )
        reponse.headers["Content-Type"] = "text/html; charset=utf-8"
        return reponse
