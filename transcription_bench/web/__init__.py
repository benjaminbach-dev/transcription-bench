"""Couche web locale du prototype : fabrique Flask et rendu Jinja2.

Les services (créneau d'opération, moteurs, stockage) restent extérieurs à
Flask ; ce paquet ne contient que la fabrique, les routes minces et les
templates `.html`.
"""

from __future__ import annotations

from transcription_bench.web.app import (
    LIMITE_CORPS_APPLICATION,
    NOM_CHAMP_JETON,
    ConfigApplication,
    ServicesApplication,
    create_app,
)

__all__ = [
    "LIMITE_CORPS_APPLICATION",
    "NOM_CHAMP_JETON",
    "ConfigApplication",
    "ServicesApplication",
    "create_app",
]
