"""Fabrique Flask sans effets de bord, routes minces et pages d'erreur.

La fabrique ne prend aucun verrou d'instance, ne démarre ni serveur ni thread et
n'écrit aucun fichier : les tests peuvent créer l'application sans toucher aux
données réelles. Les routes valident la demande puis délèguent aux services
injectés ; le lancement HTTP (Waitress) relève de la CLI.

Un hook `before_request` global vérifie chaque requête avant toute action, dans
l'ordre Host, Origin, type de corps, taille puis jeton anti-CSRF ; il protège
aussi les routes inexistantes. Le jeton est propre à chaque `create_app` et
reste sans session ni cookie. Les pages restent volontairement limitées à ce qui
est réellement implémenté : aucun succès n'est affiché pour une fonction absente.

Trois routes GET servent les ressources du paquet, jamais un dossier statique :
`/sumi.css` (copie figée de Sumi.css, MIT), `/app.css` (complément du projet) et
`/app.js` (unique script local, chargé `defer`), avec type explicite, `nosniff` et
`no-cache`. Le chemin lu est construit depuis ce module, jamais depuis la requête.
Les réponses HTML portent une politique de sécurité des contenus stricte (D6),
pages d'erreur comprises, sans `unsafe-inline` ni `unsafe-eval` ; elle ne remplace
ni le contrôle `Host`, ni celui d'`Origin`, ni le jeton anti-CSRF.

Les mutations passent par le créneau unique injecté : la vérification des
dossiers s'exécute sous son verrou et est refusée (409) pendant une opération
longue, comme après le passage à l'arrêt (503). La navigation commune présente
six rubriques fixes — Résultats, Comparaisons, Exécutions, Modèles, Moteurs,
Audios — et `GET /` redirige vers Résultats (design D1). `GET /operation`
redirige vers la section `#operation` d'Exécutions sans transmettre de
paramètre de redirection libre : seuls les codes `arret-demande` et
`arret-incomplet` y sont traduits en message fixe. Les pages des moteurs, des
modèles, des audios et des exécutions sont réelles : elles lisent l'inventaire,
le dossier d'entrée local ou une demande de formulaire et délèguent les actions
explicites aux services. La page des audios ne décode aucun signal : elle
affiche la durée indicative du conteneur et les erreurs de lecture par fichier,
y compris les noms refusés, et signale un dossier d'entrée inaccessible. La
page des exécutions réunit l'opération longue en cours ou la dernière issue
(ancre `#operation`), la préparation unique d'une demande — un seul panneau
Modèle/Audio/Moteur (design D4) dont la sélection est une lecture GET sans
jeton — que le script local recharge sur changement de sélection, sans mutation
et avec les seules valeurs non sensibles encore applicables —, puis la
préparation appliquée et son formulaire POST protégé revalidé par le
service de la tâche 6.2 —, le bouton
de lancement qui démarre l'exécution dans le créneau global (tâche 6.3),
l'historique technique complet des exécutions en détail secondaire et les
diagnostics des dossiers de données. Une référence locale reste la source de
vérité : le moteur affiché en découle, ne le contredit jamais et n'est jamais
converti ; une sélection périmée ou incohérente rend un message borné avec le
statut 400, sans 500 ni valeur interprétée comme du HTML. Le résumé d'opération porte un abri de suivi
(`data-suivi-operation`) ; `GET /executions/etat` renvoie son état borné en JSON
`no-store` — type, état, cible, erreur et lien de résultat construit ici depuis
l'identifiant publié par l'exécution admise — jamais un PID, un jeton, une
transcription ni le journal brut. Le script local n'interroge cette route que
tant que l'opération est active, une requête à la fois, et le lien Actualiser
reste le repli sans JavaScript. Aucune route ne transmet d'objet Flask au
travail de fond. La page Résultats (tâche 1.4) regroupe les essais par empreinte
audio, tri commun appliqué dans chaque groupe, et renvoie vers l'historique
complet des exécutions dans Exécutions. Le détail d'une transcription : texte,
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

import json
import secrets
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from hmac import compare_digest
from pathlib import Path

from flask import Flask, Response, abort, redirect, render_template, request, url_for
from werkzeug.exceptions import HTTPException

from engines.registre import MoteurInconnu, creer_registre_fourni
from transcription_bench.audios import FORMATS_AUDIO, AudioListe, lister_audios
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
from transcription_bench.execution_moteur import (
    ARRET_AUCUN,
    ARRET_SURVIVANT,
    ExecutionImpossible,
    ExecutionMoteur,
)
from transcription_bench.executions import (
    PREFIXE_CHAMP_REGLAGE,
    SEPARATEUR_REFERENCE_MODELE,
    VALEUR_FAUSSE,
    VALEUR_VRAIE,
    ConfigurationExecutions,
    DemandeExecution,
    ModelePropose,
    PreparationExecution,
    refuser_champs_repetes,
    reglages_depuis_formulaire,
)
from transcription_bench.gestion_modeles import (
    GestionModeles,
    empreinte_verification,
)
from transcription_bench.indicateurs_resultats import (
    formater_date_courte,
    formater_duree_premier_niveau,
    formater_memoire_premier_niveau,
    formater_pourcentage_premier_niveau,
)
from transcription_bench.moteurs import (
    LIBELLES_ETATS_MOTEUR,
    InstallationIndisponible,
    InstallationMoteurs,
)
from transcription_bench.operations import (
    ETAT_EN_COURS,
    ETAT_LIBRE,
    LIBELLES_ETATS,
    LIBELLES_TYPES,
    TYPE_EXECUTION,
    TYPE_INSTALLATION,
    CreneauOccupe,
    CreneauOperations,
    ServiceArrete,
)
from transcription_bench.paths import (
    DOSSIERS_DATA,
    NOM_DOSSIER_AUDIO,
    NOM_DOSSIER_RESULTATS,
    ValeurRefusee,
    preparer_dossiers_data,
)
from transcription_bench.resultats import MOTIF_IDENTIFIANT
from transcription_bench.web.vues_modeles import (
    formater_taille_modele,
    vues_modeles_locaux,
)
from transcription_bench.web.vues_resultats import (
    vue_comparaison,
    vues_audios_detail,
    vues_groupes,
)

LIMITE_CORPS_APPLICATION = 64 * 1024
NOM_CHAMP_JETON = "jeton_csrf"
TYPE_FEUILLE = "text/css; charset=utf-8"
TYPE_SCRIPT = "text/javascript; charset=utf-8"
TYPE_JSON = "application/json; charset=utf-8"
# Dossier des ressources locales du paquet (feuilles et script), jamais servi
# comme répertoire : chaque route lit un nom fixe décidé dans ce module.
DOSSIER_FEUILLES = Path(__file__).resolve().parent / "ressources"
NOM_FEUILLE_SUMI = "sumi.min.css"
NOM_FEUILLE_APP = "app.css"
NOM_SCRIPT_APP = "app.js"
# Design D6 : tout est restreint à l'origine locale ; aucun script incorporé,
# aucune évaluation dynamique, aucune frame et aucune base d'URL modifiable.
POLITIQUE_CONTENU = (
    "default-src 'self'; script-src 'self'; style-src 'self'; "
    "connect-src 'self'; img-src 'self'; object-src 'none'; "
    "form-action 'self'; frame-ancestors 'none'; base-uri 'none'"
)
CHAMP_SELECTION_COMPARAISON = "transcription"
CHAMP_TRI_CLASSEMENT = "tri"
# Groupe dont une liste conserve les cases cochées : une seule empreinte bornée,
# jamais un paramètre de redirection libre.
CHAMP_EMPREINTE_GROUPE = "empreinte"
TYPE_FORMULAIRE = "application/x-www-form-urlencoded"
HOTES_AUTORISES = ("127.0.0.1", "localhost")

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


MESSAGE_LANCEMENT = (
    "Le bouton « Lancer l'exécution » revalide la demande, décode les audios puis "
    "démarre le moteur dans le créneau global d'opération ; la page Exécutions "
    "suit l'avancement et permet d'arrêter l'exécution. Une seule opération longue "
    "à la fois : une exécution en cours refuse toute autre demande. Les modèles "
    "prêts des familles prises en charge sont exécutables après installation "
    "explicite de leur moteur. Le moteur factice produit uniquement des textes "
    "et des mesures simulés."
)

# Design D1 : seul ce sous-ensemble borné d'actions d'arrêt est traduit par
# `GET /operation` en message local ; tout autre paramètre, dont un `next`
# libre, n'est pas répercuté.
ACTIONS_OPERATION = frozenset({"arret-demande", "arret-incomplet"})

MESSAGE_DOSSIER_AUDIO_INACCESSIBLE = (
    "Le dossier d'entrée n'a pas pu être lu : aucun audio n'est listé. "
    "Vérifiez qu'il s'agit d'un dossier accessible en lecture."
)

MESSAGES_ERREUR = {
    400: "Demande refusée : valeur ou action invalide.",
    403: "Requête refusée : adresse, origine ou jeton invalide.",
    404: "Page introuvable.",
    405: "Méthode non autorisée pour cette adresse.",
    409: "Une opération longue est déjà en cours : la demande a été refusée.",
    413: "Formulaire trop volumineux : 64 Kio au maximum.",
    415: "Type de formulaire non pris en charge : formulaire HTML attendu.",
    500: "Erreur interne du serveur.",
    503: "Le serveur est en cours d'arrêt : la demande a été refusée.",
}

MESSAGE_ERREUR_GENERIQUE = "La requête n'a pas pu être traitée."

MESSAGE_MOTEUR_NON_PRET = (
    "Le moteur demandé n'est pas prêt pour une exécution : installation explicite "
    "requise, ou interpréteur du moteur indisponible. Aucune exécution n'a été "
    "lancée."
)

MESSAGE_SUPPRESSION_PENDANT_EXECUTION = (
    "Une exécution en cours empêche la suppression : les fichiers du modèle "
    "restent en place et les résultats déjà produits restent consultables."
)

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

MESSAGE_PREPARATION_REFUSEE = (
    "Préparation refusée : un champ de sélection a été fourni plusieurs fois. "
    "Les choix par défaut sont proposés à la place ; appliquez une seule "
    "sélection à la fois."
)

MESSAGE_DEMANDE_REFUSEE = (
    "Demande refusée : un champ est invalide, inconnu ou fourni plusieurs "
    "fois ; aucune exécution n'a été lancée. Les choix encore valides sont "
    "repris ci-dessous, les autres reviennent à leurs valeurs par défaut."
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
    """Services appelés par les routes, injectés pour rester testables.

    `creneau` est l'unique créneau d'opération longue : la CLI le crée et
    l'injecte. Il n'est ni global au module ni construit par `create_app`.
    `moteurs` est le service d'installation ; s'il est absent, la fabrique en
    construit un avec les quatre déclarations fournies, sans aucune E/S.
    `modeles` est le service des modèles ; s'il est absent, la fabrique en
    construit un également, sans E/S ni client réseau.
    `lister_audios` produit la liste des audios d'entrée ; la valeur par défaut
    lit `data/audio` sans le créer, ce que les tests remplacent par un dossier
    temporaire ou une fonction factice.
    `executions` est le service des demandes d'exécution (tâche 6.2) ; s'il est
    absent, la fabrique en construit un avec les quatre déclarations fournies,
    l'inventaire du service des modèles et la liste d'audios ci-dessus, sans
    aucune E/S.
    `execution` est le service de lancement supervisé des exécutions (tâche
    6.3) ; s'il est absent, la fabrique en construit un avec le même registre et
    le service des moteurs, sans aucune E/S. La CLI l'injecte pour que la
    supervision d'arrêt du serveur (tâche 6.6) puisse terminer le moteur de
    l'exécution réellement en cours.
    `resultats` est le service de consultation des résultats (tâche 7.1),
    strictement en lecture ; s'il est absent, la fabrique en construit un sur le
    dossier de données, sans aucune E/S. Il est injectable pour rendre les
    lectures illisibles ou incohérentes testables.
    """

    creneau: CreneauOperations
    preparer_dossiers: Callable[[Path], dict[str, Path]] = preparer_dossiers_data
    moteurs: InstallationMoteurs | None = None
    modeles: GestionModeles | None = None
    lister_audios: Callable[[Path], tuple[AudioListe, ...]] = lister_audios
    executions: ConfigurationExecutions | None = None
    execution: ExecutionMoteur | None = None
    resultats: ConsultationResultats | None = None


def create_app(config: ConfigApplication, services: ServicesApplication) -> Flask:
    """Construit l'application Flask, sans aucun effet de bord."""
    application = Flask(__name__, static_folder=None)
    jeton = secrets.token_urlsafe(32)
    application.config.update(
        DEBUG=False,
        PORT=config.port,
        DOSSIER_DATA=str(config.dossier_data),
        MAX_CONTENT_LENGTH=LIMITE_CORPS_APPLICATION,
    )
    # Initialiser Jinja après la configuration : FLASK_DEBUG ne doit pas
    # activer son rechargement automatique. Les formats détaillés restent inchangés.
    application.jinja_env.globals.update(
        formater_date_courte=formater_date_courte,
        formater_duree_premier_niveau=formater_duree_premier_niveau,
        formater_memoire_premier_niveau=formater_memoire_premier_niveau,
        formater_pourcentage_premier_niveau=formater_pourcentage_premier_niveau,
        formater_taille_modele=formater_taille_modele,
    )
    application.extensions[NOM_CHAMP_JETON] = jeton
    hotes = frozenset(f"{adresse}:{config.port}" for adresse in HOTES_AUTORISES)
    origines = frozenset(f"http://{adresse_port}" for adresse_port in hotes)
    registre = creer_registre_fourni()
    service_moteurs = services.moteurs or InstallationMoteurs(
        config.dossier_data, registre, services.creneau
    )
    service_modeles = services.modeles or GestionModeles(
        config.dossier_data,
        registre,
        services.creneau,
        service_moteurs,
    )
    service_executions = services.executions or ConfigurationExecutions(
        config.dossier_data,
        registre,
        service_modeles.inventaire,
        lister=services.lister_audios,
    )
    service_execution = services.execution or ExecutionMoteur(
        config.dossier_data, registre, service_moteurs
    )
    service_resultats = services.resultats or ConsultationResultats(config.dossier_data)

    @application.context_processor
    def injecter_jeton() -> dict[str, object]:
        return {
            NOM_CHAMP_JETON: jeton,
            "libelles_etats_moteur": LIBELLES_ETATS_MOTEUR,
        }

    @application.before_request
    def verifier_requete() -> None:
        _verifier_hote(hotes)
        if request.method == "POST":
            _verifier_post(jeton, origines)

    @application.after_request
    def ajouter_politique_contenu(reponse: Response) -> Response:
        """Pose la CSP sur les réponses HTML, pages d'erreur réelles comprises.

        Le type est lu sur la réponse finale : un rendu Jinja, une page d'erreur
        404/405/500 et le corps d'une redirection sont tous du HTML. Les
        ressources locales (feuilles, script) ne la reçoivent pas : elle décrit
        ce que le document peut charger, pas son propre type.
        """
        if reponse.mimetype == "text/html":
            reponse.headers["Content-Security-Policy"] = POLITIQUE_CONTENU
        return reponse

    _enregistrer_routes(
        application,
        config,
        services,
        service_moteurs,
        service_modeles,
        service_executions,
        service_execution,
        service_resultats,
    )
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


def _verifier_post(jeton: str, origines: frozenset[str]) -> None:
    """Contrôle Origin, type, taille puis jeton, dans cet ordre."""
    origine = request.headers.get("Origin")
    if origine is not None and origine not in origines:
        abort(403)
    if request.mimetype != TYPE_FORMULAIRE:
        abort(415)
    if (request.content_length or 0) > LIMITE_CORPS_APPLICATION:
        abort(413)
    if not _jeton_valide(request.form.get(NOM_CHAMP_JETON, ""), jeton):
        abort(403)


def _jeton_valide(recu: str, attendu: str) -> bool:
    """Compare le jeton sans échouer sur des caractères non ASCII."""
    return compare_digest(recu.encode("utf-8", "replace"), attendu.encode("utf-8"))


def _etat_dossiers(config: ConfigApplication) -> list[dict[str, object]]:
    """Décrit les dossiers de données attendus, sans rien créer."""
    return [
        {
            "nom": nom,
            "chemin": config.dossier_data / nom,
            "existe": (config.dossier_data / nom).is_dir(),
        }
        for nom in DOSSIERS_DATA
    ]


def _message_action() -> str | None:
    """Traduit le code d'action reçu en message fixe, sans recopier de saisie."""
    return MESSAGES_ACTION.get(request.args.get("action", ""))


def _page_erreur(code: int, message: str) -> tuple[str, int]:
    """Réponse d'erreur HTML à message fixe, sans texte d'exception ni cible."""
    return render_template("erreur.html", code=code, message=message), code


def _lien_resultat(identifiant: str) -> str:
    """Adresse locale du détail d'une exécution, construite par la route fixe."""
    return url_for("resultat_detail", identifiant=identifiant)


def _identifiant_resultat_valide(identifiant: str | None) -> bool:
    """Même identité bornée que le stockage et les routes de consultation."""
    return isinstance(identifiant, str) and bool(MOTIF_IDENTIFIANT.fullmatch(identifiant))


def _url_resultat(identifiant: str | None) -> str | None:
    """Adresse locale du résultat publié, ou `None` sans identifiant valide."""
    if not _identifiant_resultat_valide(identifiant):
        return None
    return _lien_resultat(str(identifiant))


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
    config: ConfigApplication,
    services: ServicesApplication,
    service_moteurs: InstallationMoteurs,
    service_modeles: GestionModeles,
    service_executions: ConfigurationExecutions,
    service_execution: ExecutionMoteur,
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

    @application.get("/app.js")
    def script_app() -> Response:
        """Unique script local, chargé `defer` par le squelette commun (D6)."""
        return _reponse_ressource(NOM_SCRIPT_APP, TYPE_SCRIPT)

    @application.get("/audios")
    def audios() -> str:
        # Une erreur d'accès au dossier n'empêche pas la page : elle est affichée
        # par un message fixe, sans détail d'exception, comme côté exécutions.
        try:
            liste = services.lister_audios(config.dossier_data)
        except (ValeurRefusee, OSError):
            liste = ()
            erreur_dossier = MESSAGE_DOSSIER_AUDIO_INACCESSIBLE
        else:
            erreur_dossier = None
        return render_template(
            "audios.html",
            audios=liste,
            formats=FORMATS_AUDIO,
            dossier=config.dossier_data / NOM_DOSSIER_AUDIO,
            erreur_dossier=erreur_dossier,
        )

    @application.get("/executions")
    def executions():
        """Préparation unique et suivi, en lecture seule (design D1, D4, D5).

        Les paramètres GET ne portent que des références locales, des noms
        d'audios et les réglages avancés **non sensibles** de la préparation
        déjà affichée (`source`, `threads`, `reglage_*`) : jamais le jeton
        anti-CSRF, jamais un nom hors de la liste blanche des réglages déclarés.
        Une valeur périmée ou incohérente est remplacée par le choix applicable
        avec un message borné et le statut de refus 400, sans 500 ni valeur
        interprétée comme du HTML. Un réglage seulement inapplicable est remis
        à son défaut et annoncé, sans refus. Aucun créneau d'action n'est
        sollicité : cette page ne lance, n'installe et ne télécharge rien.
        """
        erreur_preparation = None
        audio_unitaire_ignore = None
        audios_lot = request.args.getlist("audios_lot")
        audios_uniques = request.args.getlist("audios")
        # Tâche 4.3 : le lot facultatif porte un autre nom que l'audio unique,
        # et remplace celui-ci quand au moins une case est cochée. Aucun audio
        # n'est alors envoyé deux fois et le choix écarté est annoncé.
        audios_choisis = audios_lot or audios_uniques
        if audios_lot and audios_uniques and audios_uniques[0] not in audios_lot:
            # Seul un audio réellement lisible de l'inventaire local est nommé :
            # aucune valeur forgée n'est réaffichée, même échappée.
            candidat = audios_uniques[0]
            if any(
                audio.nom == candidat
                for audio in service_executions.audios_proposables()
            ):
                audio_unitaire_ignore = candidat
        try:
            refuser_champs_repetes(request.args.items(multi=True))
        except ValeurRefusee:
            erreur_preparation = MESSAGE_PREPARATION_REFUSEE
            preparation = service_executions.preparer()
        else:
            preparation = service_executions.preparer(
                modele=request.args.get("modele"),
                moteur=request.args.get("moteur"),
                audios=audios_choisis,
                source=request.args.get("source"),
                threads=request.args.get("threads"),
                reglages=reglages_depuis_formulaire(request.args),
            )
            if preparation is not None and preparation.notice is not None:
                erreur_preparation = preparation.notice
        rendu = _page_executions(
            service_executions,
            service_resultats,
            service_execution,
            services,
            config,
            preparation=preparation,
            erreur_preparation=erreur_preparation,
            audio_unitaire_ignore=audio_unitaire_ignore,
        )
        return (rendu, 400) if erreur_preparation is not None else rendu

    @application.get("/executions/etat")
    def etat_execution() -> Response:
        """État borné de l'opération longue, pour le suivi automatique (D5).

        Lecture seule et sans effet de bord : aucune mutation n'est exécutée et
        le créneau n'est jamais sollicité pour autre chose que son instantané.
        La charge ne contient que des champs fixes et bornés — type, état,
        cible, erreur et lien de résultat construit ici depuis l'identifiant
        validé — jamais un PID, le jeton anti-CSRF, une transcription ni le
        journal brut. La réponse n'est pas mise en cache.
        """
        instantane = services.creneau.instantane()
        identifiant = service_execution.identifiant_resultat(instantane.generation)
        libelle_type = (
            LIBELLES_TYPES[instantane.type_operation]
            if instantane.type_operation in LIBELLES_TYPES
            else None
        )
        charge = {
            "generation": instantane.generation,
            "etat": instantane.etat,
            "libelle_etat": LIBELLES_ETATS[instantane.etat],
            "type": instantane.type_operation,
            "libelle_type": libelle_type,
            "cible": instantane.cible,
            "erreur": instantane.erreur,
            "actif": instantane.etat == ETAT_EN_COURS,
            "url_resultat": _url_resultat(identifiant),
        }
        reponse = Response(json.dumps(charge, ensure_ascii=False), status=200)
        reponse.headers["Content-Type"] = TYPE_JSON
        reponse.headers["Cache-Control"] = "no-store"
        reponse.headers["X-Content-Type-Options"] = "nosniff"
        return reponse

    @application.post("/executions/verifier")
    def verifier_demande_execution():
        """Valide une demande d'exécution sans rien lancer ni rien persister.

        La page est rendue directement au lieu de rediriger en 303 : aucune
        action n'est acceptée ni consignée côté serveur, il n'y a donc rien à
        relire en GET et aucune valeur à conserver sans session. Un refus rend
        la page Exécutions en 400 avec un message fixe et une préparation
        reconstruite depuis les champs soumis : les choix encore valides sont
        repris, les autres sont remplacés et annoncés au lieu d'être perdus
        silencieusement (tâche 4.3, design D4).
        """
        try:
            refuser_champs_repetes(request.form.items(multi=True))
            demande = _demande_validee(service_executions)
        except ValeurRefusee:
            return _page_demande_refusee(
                service_executions,
                service_resultats,
                service_execution,
                services,
                config,
            )
        return _page_executions(
            service_executions,
            service_resultats,
            service_execution,
            services,
            config,
            demande,
            preparation=_preparation_de_la_demande(service_executions, demande),
        )

    @application.post("/executions/lancer")
    def lancer_execution():
        """Revalide la demande puis démarre l'exécution dans le créneau global.

        La demande est revalidée ici (modèle toujours prêt, audios et réglages
        toujours valides) et le moteur est recontrôlé : prêt au sens de
        l'inventaire local, sauf le moteur factice. Aucun objet Flask n'est
        transmis au travail de fond, qui ne reçoit que la demande validée.
        """
        try:
            refuser_champs_repetes(request.form.items(multi=True))
            demande = _demande_validee(service_executions)
            service_execution.verifier_lancable(demande)
        except ValeurRefusee:
            # Refus de la demande elle-même : rien n'est lancé, la page reprend
            # les choix encore valides au lieu de les laisser disparaître.
            return _page_demande_refusee(
                service_executions,
                service_resultats,
                service_execution,
                services,
                config,
            )
        except ExecutionImpossible:
            # Refus métier, distinct du refus de jeton : garder les choix valides.
            return _page_demande_refusee(
                service_executions, service_resultats, service_execution,
                services, config, statut=403, message=MESSAGE_MOTEUR_NON_PRET,
            )
        try:
            # Réservation posée avant l'admission : un arrêt demandé dans
            # l'intervalle n'est pas perdu, et `lancer` ne remet rien à zéro.
            service_execution.reserver()
        except ExecutionImpossible:
            return _page_demande_refusee(
                service_executions, service_resultats, service_execution,
                services, config, statut=409, message=MESSAGES_ERREUR[409],
            )
        try:
            services.creneau.demarrer(
                TYPE_EXECUTION,
                lambda travailleur: service_execution.lancer(demande, travailleur),
                cible=demande.identifiant,
            )
        except CreneauOccupe:
            service_execution.annuler_reservation()
            return _page_demande_refusee(
                service_executions, service_resultats, service_execution,
                services, config, statut=409, message=MESSAGES_ERREUR[409],
            )
        except ServiceArrete:
            service_execution.annuler_reservation()
            return _page_demande_refusee(
                service_executions, service_resultats, service_execution,
                services, config, statut=503, message=MESSAGES_ERREUR[503],
            )
        except BaseException:
            service_execution.annuler_reservation()
            raise
        return redirect(url_for("executions") + "#operation", code=303)

    @application.post("/executions/arreter")
    def arreter_execution():
        """Demande l'arrêt de l'exécution active, sans dépendre d'un contexte Flask.

        Sans exécution active (aucune opération, ou une autre opération longue),
        rien n'est arrêté et aucun message d'arrêt n'est affiché. Si le processus
        survit à `kill`, la page l'indique au lieu de laisser croire à un arrêt
        effectif.
        """
        arret = service_execution.arreter_execution()
        if arret == ARRET_AUCUN:
            return redirect(url_for("executions") + "#operation", code=303)
        if arret == ARRET_SURVIVANT:
            return redirect(
                url_for("executions", action="arret-incomplet") + "#operation",
                code=303,
            )
        return redirect(
            url_for("executions", action="arret-demande") + "#operation", code=303
        )

    @application.get("/modeles")
    def modeles() -> str:
        """Inventaire local d'abord, ajout secondaire après (tâche 5.1).

        L'inventaire des modèles prêts est le premier contenu fonctionnel de la
        page ; l'ajout (vérification puis téléchargement) vient ensuite. Chaque
        modèle prêt porte la référence locale déjà acceptée en GET par
        `/executions`, pour l'action « Utiliser », et l'état `actif` d'un modèle
        visé par l'opération en cours. Aucune lecture n'écrit de fichier.
        """
        resultat = service_modeles.dernier_resultat()
        try:
            inventaire = service_modeles.inventaire()
        except ValeurRefusee:
            inventaire = ()
        instantane = services.creneau.instantane()
        return render_template(
            "modeles.html",
            modeles=vues_modeles_locaux(inventaire, instantane),
            moteurs=service_modeles.moteurs_disponibles(),
            resultat=resultat,
            empreinte=(
                empreinte_verification(resultat)
                if resultat is not None and resultat.accepte
                else None
            ),
            instantane=instantane,
            libelles_types=LIBELLES_TYPES,
            message=_message_action(),
        )

    @application.post("/modeles/verifier")
    def verifier_modele():
        identifiant = request.form.get("identifiant", "")
        moteur = request.form.get("moteur", "")
        revision = request.form.get("revision", "").strip() or None
        fichier_gguf = request.form.get("fichier_gguf", "").strip() or None
        try:
            service_modeles.lancer_verification(
                identifiant,
                moteur,
                revision=revision,
                fichier_gguf=fichier_gguf,
            )
        except MoteurInconnu:
            abort(404)
        except ValeurRefusee:
            abort(400)
        except CreneauOccupe:
            abort(409)
        except ServiceArrete:
            abort(503)
        return redirect(url_for("modeles", action="verification-lancee"), code=303)

    @application.post("/modeles/telecharger")
    def telecharger_modele():
        empreinte = request.form.get("empreinte", "")
        try:
            lance = service_modeles.lancer_telechargement(empreinte)
        except ValeurRefusee:
            abort(400)
        except CreneauOccupe:
            abort(409)
        except ServiceArrete:
            abort(503)
        action = "telechargement-lance" if lance else "modele-deja-present"
        return redirect(url_for("modeles", action=action), code=303)

    @application.post("/modeles/supprimer")
    def supprimer_modele():
        moteur = request.form.get("moteur", "")
        cle = request.form.get("cle", "")
        try:
            service_modeles.supprimer(moteur, cle)
        except MoteurInconnu:
            abort(404)
        except ValeurRefusee:
            abort(400)
        except CreneauOccupe as refus:
            if refus.type_operation == TYPE_EXECUTION:
                # Message fixe : le type a été capturé au refus sous le verrou,
                # sans relire un état ultérieur ni recopier l'exception.
                return _page_erreur(409, MESSAGE_SUPPRESSION_PENDANT_EXECUTION)
            abort(409)
        except ServiceArrete:
            abort(503)
        return redirect(url_for("modeles", action="modele-supprime"), code=303)

    @application.get("/moteurs")
    def moteurs() -> str:
        return render_template(
            "moteurs.html",
            moteurs=service_moteurs.inventaire(),
            instantane=services.creneau.instantane(),
            libelles_types=LIBELLES_TYPES,
        )

    @application.post("/moteurs/<identifiant>/installer")
    def installer_moteur(identifiant: str):
        try:
            service_moteurs.verifier_installable(identifiant)
        except MoteurInconnu:
            abort(404)
        except (InstallationIndisponible, ValeurRefusee):
            abort(403)
        try:
            services.creneau.demarrer(
                TYPE_INSTALLATION,
                lambda travailleur: service_moteurs.installer(identifiant, travailleur),
                cible=identifiant,
            )
        except CreneauOccupe:
            abort(409)
        except ServiceArrete:
            abort(503)
        return redirect(url_for("executions") + "#operation", code=303)

    @application.get("/moteurs/<identifiant>/journal")
    def journal_moteur(identifiant: str) -> str:
        try:
            declaration = service_moteurs.declaration(identifiant)
            lignes = service_moteurs.lire_journal(identifiant)
        except MoteurInconnu:
            abort(404)
        except ValeurRefusee:
            abort(403)
        return render_template(
            "journal.html",
            moteur=declaration,
            lignes=lignes,
        )

    @application.get("/resultats")
    def resultats() -> str:
        """Résultats groupés par audio, avec accès à l'historique dans Exécutions.

        Le critère `tri` vaut `recent` par défaut et s'applique dans chaque groupe
        seulement ; un critère inconnu ou répété est refusé (400). L'historique
        complet des exécutions vit désormais dans Exécutions (tâche 3.1), où la
        page renvoie par un lien secondaire.
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

    @application.get("/operation")
    def operation() -> Response:
        """Ancien lien : redirection GET locale vers Exécutions (design D1).

        Seul un code d'action d'arrêt connu est traduit en message local ; tout
        autre paramètre reçu, dont un `next` libre, n'est pas répercuté.
        """
        action = request.args.get("action", "")
        if action in ACTIONS_OPERATION:
            destination = url_for("executions", action=action)
        else:
            destination = url_for("executions")
        return redirect(destination + "#operation", code=302)

    @application.post("/dossiers/verifier")
    def verifier_dossiers():
        try:
            services.creneau.executer_mutation(
                lambda: services.preparer_dossiers(config.dossier_data)
            )
        except CreneauOccupe:
            abort(409)
        except ServiceArrete:
            abort(503)
        return redirect(
            url_for("executions", action="dossiers-verifies") + "#diagnostics",
            code=303,
        )


def _demande_validee(service: ConfigurationExecutions) -> DemandeExecution:
    """Forme consommable du formulaire d'exécution, ou `ValeurRefusee`.

    Les champs sont lus depuis la requête courante : la route appelante les
    revalide donc entièrement, même si la page les a déjà affichés. Le champ
    `moteur` du panneau de préparation est revalidé avec la référence : fourni,
    il doit être celui qu'elle déclare.
    """
    return service.valider(
        modele=request.form.get("modele", ""),
        audios=request.form.getlist("audios"),
        threads=request.form.get("threads", ""),
        reglages=reglages_depuis_formulaire(request.form),
        moteur=request.form.get("moteur"),
    )


def _preparation_de_la_demande(
    service: ConfigurationExecutions, demande: DemandeExecution
) -> PreparationExecution:
    """Préparation affichée après une vérification, alignée sur la demande.

    La demande validée peut avoir été forgée ou soumise hors de la page : la
    préparation est recalculée depuis elle, par les mêmes règles que la page GET
    (référence source de vérité, audios lisibles, moteur cohérent). Les threads
    et les réglages effectifs de la demande sont repris, comme le fait le GET
    pour une préparation déjà affichée : vérifier ne remet donc pas les valeurs
    en cours à leurs défauts.
    """
    reference = f"{demande.moteur}{SEPARATEUR_REFERENCE_MODELE}{demande.cle}"
    return service.preparer(
        modele=reference,
        moteur=demande.moteur,
        audios=demande.audios,
        source=reference,
        threads=str(demande.threads),
        reglages={
            reglage.nom: _valeur_de_formulaire(reglage.valeur)
            for reglage in demande.reglages
        },
        autoriser_texte=True,  # valeurs vérifiées du POST, jamais une URL
        adapter_moteur=False,
    )


def _preparation_refusee(service: ConfigurationExecutions) -> PreparationExecution:
    """Préparation reconstruite depuis une demande POST refusée (tâche 4.3).

    La demande n'a pas été validée : ses champs sont relus ici sans aucune
    confiance et repassés par les mêmes règles que la page GET. Le modèle soumis
    sert d'origine aux réglages avancés, ce qui permet de reprendre les valeurs
    encore valides et de faire annoncer par le service tout ce qui est remplacé.
    Aucune valeur soumise n'est rendue telle quelle : seuls les choix résolus par
    l'inventaire local et les messages bornés du service apparaissent.
    """
    return service.preparer(
        modele=request.form.get("modele"),
        moteur=request.form.get("moteur"),
        audios=request.form.getlist("audios"),
        source=request.form.get("modele"),
        threads=request.form.get("threads"),
        reglages=reglages_depuis_formulaire(request.form),
        autoriser_texte=True,  # restitution locale d'un POST refusé
        adapter_moteur=False,
    )


def _page_demande_refusee(
    service: ConfigurationExecutions,
    service_resultats: ConsultationResultats,
    service_execution: ExecutionMoteur,
    services: ServicesApplication,
    config: ConfigApplication,
    *,
    statut: int = 400,
    message: str = MESSAGE_DEMANDE_REFUSEE,
) -> tuple[str, int]:
    """Refus métier d'une demande : vrai statut et préparation restituée.

    Le message fixe est complété par l'annonce bornée du service (modèle, audio
    ou réglage remplacé) ; aucune valeur soumise n'est reprise telle quelle et
    aucune exécution n'est lancée ni consignée.
    """
    preparation = _preparation_refusee(service)
    if preparation.notice is not None:
        message = f"{message} {preparation.notice}"
    return (
        _page_executions(
            service,
            service_resultats,
            service_execution,
            services,
            config,
            preparation=preparation,
            erreur_preparation=message,
        ),
        statut,
    )


def _valeur_de_formulaire(valeur: int | bool | str) -> str:
    """Valeur d'un réglage telle que le formulaire la transmet (oui ou non)."""
    if valeur is True:
        return VALEUR_VRAIE
    if valeur is False:
        return VALEUR_FAUSSE
    return str(valeur)


def _moteurs_proposes(
    modeles: Sequence[ModelePropose],
) -> tuple[tuple[str, str, str], ...]:
    """Triplets (moteur, nom, référence) des moteurs proposables, uniques.

    Le moteur d'un modèle n'est pas un second choix indépendant : ce sélecteur
    ne sert qu'à rendre le moteur attendu lisible et présélectionné (D4). La
    référence jointe est la première du moteur dans l'ordre des modèles : elle
    permet au script local de choisir un modèle réellement compatible quand
    l'utilisateur ne change que le moteur, sans inventer de combinaison ni
    convertir aucun format. Aucune valeur sensible n'y figure.
    """
    proposes: dict[str, tuple[str, str]] = {}
    for modele in modeles:
        proposes.setdefault(modele.moteur, (modele.nom_moteur, modele.reference))
    return tuple(
        (identifiant, nom_moteur, reference)
        for identifiant, (nom_moteur, reference) in proposes.items()
    )


def _page_executions(
    service: ConfigurationExecutions,
    service_resultats: ConsultationResultats,
    service_execution: ExecutionMoteur,
    services: ServicesApplication,
    config: ConfigApplication,
    demande: DemandeExecution | None = None,
    *,
    preparation: PreparationExecution | None = None,
    erreur_preparation: str | None = None,
    audio_unitaire_ignore: str | None = None,
) -> str:
    """Page d'exécutions : opération, préparation, historique et diagnostics.

    L'opération longue vient en tête avec l'ancre `#operation`, la préparation
    unique Modèle/Audio/Moteur (design D4) ensuite, puis l'historique technique
    complet (`#historique`) et les diagnostics de dossiers (`#diagnostics`).
    Aucune lecture n'écrit de fichier. L'identité de l'opération est lue avant le
    lien de résultat : `identifiant_resultat` ne renvoie que l'identifiant publié
    par cette opération admise, jamais celui d'un essai antérieur.
    """
    instantane = services.creneau.instantane()
    url_resultat = _url_resultat(
        service_execution.identifiant_resultat(instantane.generation)
    )
    try:
        executions_enregistrees = service_resultats.lister()
    except LectureResultatsImpossible:
        executions_enregistrees = ()
        erreur_historique = MESSAGE_RESULTATS_INACCESSIBLES
    else:
        erreur_historique = None
    modeles = service.modeles_proposables()
    executables = tuple(modele for modele in modeles if modele.executable)
    if preparation is None:
        preparation = service.preparer()
    lot_actif = bool(request.args.getlist("audios_lot")) or len(preparation.audios) > 1
    audios = service.audios_proposables()
    ordre_lot = {nom: index for index, nom in enumerate(preparation.audios)}
    audios_lot_ordonnes = (
        sorted(audios, key=lambda audio: ordre_lot.get(audio.nom, len(ordre_lot)))
        if lot_actif else audios
    )
    return render_template(
        "executions.html",
        modeles=modeles,
        modeles_executables=executables,
        modeles_non_executables=tuple(
            modele for modele in modeles if not modele.executable
        ),
        moteurs_proposes=_moteurs_proposes(executables),
        preparation=preparation,
        erreur_preparation=erreur_preparation,
        audio_unitaire_ignore=audio_unitaire_ignore,
        lot_actif=lot_actif,
        audios=audios,
        audios_lot_ordonnes=audios_lot_ordonnes,
        demande=demande,
        prefixe_reglage=PREFIXE_CHAMP_REGLAGE,
        message_lancement=MESSAGE_LANCEMENT,
        instantane=instantane,
        libelles_etats=LIBELLES_ETATS,
        libelles_types=LIBELLES_TYPES,
        operation_active=instantane.etat == ETAT_EN_COURS,
        execution_active=(
            instantane.etat == ETAT_EN_COURS
            and instantane.type_operation == TYPE_EXECUTION
        ),
        url_resultat=url_resultat,
        operation_visible=(
            instantane.etat != ETAT_LIBRE
            or bool(instantane.journal)
            or instantane.erreur is not None
        ),
        message=_message_action(),
        executions=executions_enregistrees,
        erreur_historique=erreur_historique,
        dossier=service_resultats.dossier_resultats,
        dossiers=_etat_dossiers(config),
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
