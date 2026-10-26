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

Les mutations passent par le créneau unique injecté : la vérification des
dossiers s'exécute sous son verrou et est refusée (409) pendant une opération
longue, comme après le passage à l'arrêt (503). L'accueil affiche l'état du
créneau, les emplacements des dossiers, l'état des moteurs et des liens vers les
pages des moteurs, modèles, audios, exécutions et résultats. Les pages des
moteurs, des modèles, des audios et des exécutions sont réelles : elles lisent
l'inventaire, le dossier d'entrée local ou une demande de formulaire et
délèguent les actions explicites aux services. La page des audios ne décode
aucun signal : elle affiche la durée indicative du conteneur et les erreurs de
lecture par fichier, y compris les noms refusés, et signale un dossier d'entrée
inaccessible. La page des exécutions ne lance rien : elle prépare une
demande (modèle prêt, audios, threads, réglages déclarés) et la valide par le
service de la tâche 6.2, en indiquant que le lancement n'est pas disponible.
La page des résultats n'existe pas encore : elle est servie comme page
provisoire explicite, sans simulation de capacité absente et sans lien mort.
La page `/operation` n'affiche que l'instantané du créneau, sans lancer de
travail.
"""

from __future__ import annotations

import secrets
from collections.abc import Callable
from dataclasses import dataclass
from hmac import compare_digest
from pathlib import Path
from typing import NamedTuple

from flask import Flask, abort, redirect, render_template, request, url_for
from werkzeug.exceptions import HTTPException

from engines.registre import MoteurInconnu, creer_registre_fourni
from transcription_bench.audios import FORMATS_AUDIO, AudioListe, lister_audios
from transcription_bench.executions import (
    PREFIXE_CHAMP_REGLAGE,
    ConfigurationExecutions,
    DemandeExecution,
    refuser_champs_repetes,
    reglages_depuis_formulaire,
)
from transcription_bench.gestion_modeles import (
    GestionModeles,
    empreinte_verification,
)
from transcription_bench.moteurs import (
    ETAT_PRET,
    LIBELLES_ETATS_MOTEUR,
    EtatMoteur,
    InstallationIndisponible,
    InstallationMoteurs,
)
from transcription_bench.operations import (
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
    ValeurRefusee,
    preparer_dossiers_data,
)

LIMITE_CORPS_APPLICATION = 64 * 1024
NOM_CHAMP_JETON = "jeton_csrf"
TYPE_FORMULAIRE = "application/x-www-form-urlencoded"
HOTES_AUTORISES = ("127.0.0.1", "localhost")

MESSAGES_ACTION = {
    "dossiers-verifies": "Dossiers de données vérifiés.",
    "verification-lancee": (
        "Vérification distante lancée : le résultat apparaîtra après actualisation."
    ),
    "telechargement-lance": (
        "Téléchargement lancé à la révision vérifiée : le modèle ne sera prêt "
        "qu'après succès complet."
    ),
    "modele-deja-present": "Ce modèle est déjà présent : aucun téléchargement n'a été lancé.",
    "modele-supprime": "Modèle local supprimé ; les résultats déjà produits restent consultables.",
}


class PageProvisoire(NamedTuple):
    """Page annoncée par l'accueil mais dont la fonctionnalité n'existe pas.

    L'interface affiche honnêtement ces pages comme provisoires plutôt que de
    pointer vers des adresses inexistantes ou de simuler une capacité absente.
    """

    route: str
    titre: str
    description: str


PAGES_PROVISOIRES = (
    PageProvisoire(
        "resultats",
        "Résultats",
        "la consultation et la comparaison des résultats relèvent des tâches 7.1 et 7.2",
    ),
)

MESSAGE_LANCEMENT_NON_DISPONIBLE = (
    "Cette page prépare et valide une demande d'exécution, mais aucune exécution "
    "n'est démarrée : le lancement, le suivi et l'arrêt relèvent de la tâche 6.3."
)

MESSAGE_DOSSIER_AUDIO_INACCESSIBLE = (
    "Le dossier d'entrée n'a pas pu être lu : aucun audio n'est listé. "
    "Vérifiez qu'il s'agit d'un dossier accessible en lecture."
)

MESSAGE_MOTEURS_NON_INSTALLES = (
    "Aucun moteur n'est installé à ce stade ; le moteur factice est disponible "
    "sans installation, avec des textes et mesures simulés. Le lancement du "
    "serveur n'installe ni ne télécharge rien."
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

MESSAGE_SUPPRESSION_PENDANT_EXECUTION = (
    "Une exécution en cours empêche la suppression : les fichiers du modèle "
    "restent en place et les résultats déjà produits restent consultables."
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
    """

    creneau: CreneauOperations
    preparer_dossiers: Callable[[Path], dict[str, Path]] = preparer_dossiers_data
    moteurs: InstallationMoteurs | None = None
    modeles: GestionModeles | None = None
    lister_audios: Callable[[Path], tuple[AudioListe, ...]] = lister_audios
    executions: ConfigurationExecutions | None = None


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

    @application.context_processor
    def injecter_jeton() -> dict[str, object]:
        return {
            NOM_CHAMP_JETON: jeton,
            "pages_provisoires": PAGES_PROVISOIRES,
            "libelles_etats_moteur": LIBELLES_ETATS_MOTEUR,
        }

    @application.before_request
    def verifier_requete() -> None:
        _verifier_hote(hotes)
        if request.method == "POST":
            _verifier_post(jeton, origines)

    _enregistrer_routes(
        application,
        config,
        services,
        service_moteurs,
        service_modeles,
        service_executions,
    )
    _enregistrer_erreurs(application)
    return application


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


def _message_moteurs(moteurs: tuple[EtatMoteur, ...]) -> str:
    """Phrase d'accueil honnête selon l'inventaire local des moteurs réels."""
    prets = [moteur for moteur in moteurs if moteur.etat == ETAT_PRET and not moteur.factice]
    if prets:
        noms = ", ".join(moteur.nom for moteur in prets)
        return (
            f"Moteurs prêts : {noms}. Le lancement du serveur n'installe ni ne "
            "télécharge rien."
        )
    return MESSAGE_MOTEURS_NON_INSTALLES


def _enregistrer_routes(
    application: Flask,
    config: ConfigApplication,
    services: ServicesApplication,
    service_moteurs: InstallationMoteurs,
    service_modeles: GestionModeles,
    service_executions: ConfigurationExecutions,
) -> None:
    @application.get("/")
    def accueil() -> str:
        moteurs = service_moteurs.inventaire()
        return render_template(
            "accueil.html",
            dossiers=_etat_dossiers(config),
            message=_message_action(),
            instantane=services.creneau.instantane(),
            libelles_etats=LIBELLES_ETATS,
            libelles_types=LIBELLES_TYPES,
            moteurs=moteurs,
            message_moteurs=_message_moteurs(moteurs),
        )

    for page in PAGES_PROVISOIRES:
        _enregistrer_page_provisoire(application, page)

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
    def executions() -> str:
        return _page_executions(service_executions)

    @application.post("/executions/verifier")
    def verifier_demande_execution():
        """Valide une demande d'exécution sans rien lancer ni rien persister.

        La page est rendue directement au lieu de rediriger en 303 : aucune
        action n'est acceptée ni consignée côté serveur, il n'y a donc rien à
        relire en GET et aucune valeur à conserver sans session. Les refus
        restent des réponses 400 à message fixe.
        """
        try:
            refuser_champs_repetes(request.form.items(multi=True))
            demande = service_executions.valider(
                modele=request.form.get("modele", ""),
                audios=request.form.getlist("audios"),
                threads=request.form.get("threads", ""),
                reglages=reglages_depuis_formulaire(request.form),
            )
        except ValeurRefusee:
            abort(400)
        return _page_executions(service_executions, demande)

    @application.get("/modeles")
    def modeles() -> str:
        resultat = service_modeles.dernier_resultat()
        try:
            inventaire = service_modeles.inventaire()
        except ValeurRefusee:
            inventaire = ()
        return render_template(
            "modeles.html",
            modeles=inventaire,
            moteurs=service_modeles.moteurs_disponibles(),
            resultat=resultat,
            empreinte=(
                empreinte_verification(resultat)
                if resultat is not None and resultat.accepte
                else None
            ),
            instantane=services.creneau.instantane(),
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
        return redirect(url_for("operation"), code=303)

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

    @application.get("/operation")
    def operation() -> str:
        return render_template(
            "operation.html",
            instantane=services.creneau.instantane(),
            libelles_etats=LIBELLES_ETATS,
            libelles_types=LIBELLES_TYPES,
        )

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
        return redirect(url_for("accueil", action="dossiers-verifies"), code=303)


def _page_executions(
    service: ConfigurationExecutions, demande: DemandeExecution | None = None
) -> str:
    """Page du formulaire d'exécution, avec la demande validée éventuelle."""
    return render_template(
        "executions.html",
        modeles=service.modeles_proposables(),
        audios=service.audios_proposables(),
        threads_defaut=service.threads_par_defaut(),
        demande=demande,
        prefixe_reglage=PREFIXE_CHAMP_REGLAGE,
        message_lancement=MESSAGE_LANCEMENT_NON_DISPONIBLE,
    )


def _enregistrer_page_provisoire(application: Flask, page: PageProvisoire) -> None:
    """Déclare une page HTML provisoire, sans lecture ni écriture de données."""

    def page_provisoire() -> str:
        return render_template(
            "provisoire.html", titre=page.titre, description=page.description
        )

    application.add_url_rule(
        f"/{page.route}", endpoint=page.route, view_func=page_provisoire, methods=["GET"]
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
