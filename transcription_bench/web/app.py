"""Fabrique Flask sans effets de bord, routes minces et pages d'erreur.

La fabrique ne prend aucun verrou d'instance, ne démarre ni serveur ni thread et
n'écrit aucun fichier : les tests peuvent créer l'application sans toucher aux
données réelles. Les routes valident la demande puis délèguent aux services
injectés ; le lancement HTTP (Waitress) relève de la CLI.

Le lot 3 ajoutera les protections de requête, le créneau d'opération et les
pages métier. Les pages actuelles restent volontairement limitées à ce qui est
réellement implémenté : aucun succès n'est affiché pour une fonction absente.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from flask import Flask, redirect, render_template, request, url_for
from werkzeug.exceptions import HTTPException

from transcription_bench.paths import DOSSIERS_DATA, preparer_dossiers_data

MESSAGES_ACTION = {
    "dossiers-verifies": "Dossiers de données vérifiés.",
}

MESSAGES_ERREUR = {
    404: "Page introuvable.",
    405: "Méthode non autorisée pour cette adresse.",
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
    application.config.update(
        DEBUG=False,
        PORT=config.port,
        DOSSIER_DATA=str(config.dossier_data),
    )
    _enregistrer_routes(application, config, services)
    _enregistrer_erreurs(application)
    return application


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
