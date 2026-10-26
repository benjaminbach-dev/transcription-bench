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
moteurs et des modèles sont réelles : elles lisent l'inventaire local et
délèguent les actions explicites aux services. Les autres pages n'existent pas
encore : elles sont servies comme pages provisoires explicites, sans simulation
de capacité absente et sans lien mort.
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
    TYPE_INSTALLATION,
    CreneauOccupe,
    CreneauOperations,
    ServiceArrete,
)
from transcription_bench.paths import (
    DOSSIERS_DATA,
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
        "audios",
        "Audios",
        "la liste et le décodage des audios relèvent de la tâche 6.1",
    ),
    PageProvisoire(
        "executions",
        "Exécutions",
        "le lancement et le suivi des exécutions relèvent des tâches 6.2 à 6.6",
    ),
    PageProvisoire(
        "resultats",
        "Résultats",
        "la consultation et la comparaison des résultats relèvent des tâches 7.1 et 7.2",
    ),
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
    """

    creneau: CreneauOperations
    preparer_dossiers: Callable[[Path], dict[str, Path]] = preparer_dossiers_data
    moteurs: InstallationMoteurs | None = None
    modeles: GestionModeles | None = None


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
    service_moteurs = services.moteurs or InstallationMoteurs(
        config.dossier_data, creer_registre_fourni(), services.creneau
    )
    service_modeles = services.modeles or GestionModeles(
        config.dossier_data,
        creer_registre_fourni(),
        services.creneau,
        service_moteurs,
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
        application, config, services, service_moteurs, service_modeles
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
        except CreneauOccupe:
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
