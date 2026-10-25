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
"""

from __future__ import annotations

import secrets
from collections.abc import Callable
from dataclasses import dataclass
from hmac import compare_digest
from pathlib import Path

from flask import Flask, abort, redirect, render_template, request, url_for
from werkzeug.exceptions import HTTPException

from transcription_bench.paths import DOSSIERS_DATA, preparer_dossiers_data

LIMITE_CORPS_APPLICATION = 64 * 1024
NOM_CHAMP_JETON = "jeton_csrf"
TYPE_FORMULAIRE = "application/x-www-form-urlencoded"
HOTES_AUTORISES = ("127.0.0.1", "localhost")

MESSAGES_ACTION = {
    "dossiers-verifies": "Dossiers de données vérifiés.",
}

MESSAGES_ERREUR = {
    403: "Requête refusée : adresse, origine ou jeton invalide.",
    404: "Page introuvable.",
    405: "Méthode non autorisée pour cette adresse.",
    413: "Formulaire trop volumineux : 64 Kio au maximum.",
    415: "Type de formulaire non pris en charge : formulaire HTML attendu.",
    500: "Erreur interne du serveur.",
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
    """Services appelés par les routes, injectés pour rester testables."""

    preparer_dossiers: Callable[[Path], dict[str, Path]] = preparer_dossiers_data


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

    @application.context_processor
    def injecter_jeton() -> dict[str, str]:
        return {NOM_CHAMP_JETON: jeton}

    @application.before_request
    def verifier_requete() -> None:
        _verifier_hote(hotes)
        if request.method == "POST":
            _verifier_post(jeton, origines)

    _enregistrer_routes(application, config, services)
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


def _enregistrer_routes(
    application: Flask,
    config: ConfigApplication,
    services: ServicesApplication,
) -> None:
    @application.get("/")
    def accueil() -> str:
        return render_template(
            "accueil.html",
            dossiers=_etat_dossiers(config),
            message=_message_action(),
        )

    @application.post("/dossiers/verifier")
    def verifier_dossiers():
        services.preparer_dossiers(config.dossier_data)
        return redirect(url_for("accueil", action="dossiers-verifies"), code=303)


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
