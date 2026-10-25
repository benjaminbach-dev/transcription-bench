"""Couche web locale du prototype : fabrique Flask et rendu Jinja2.

Les services (créneau d'opération, moteurs, stockage) restent extérieurs à
Flask ; ce paquet ne contient que la fabrique, les routes minces et les
templates `.html`.
"""

from __future__ import annotations

from transcription_bench.web.app import (
    ConfigApplication,
    ServicesApplication,
    create_app,
)

__all__ = ["ConfigApplication", "ServicesApplication", "create_app"]
