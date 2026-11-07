"""REST API blueprints, all mounted under /api (Architecture §9)."""
from __future__ import annotations

from flask import Flask


def register_blueprints(app: Flask) -> None:
    from . import health, photos, scores, sky, spots, users

    for module in (users, scores, spots, photos, sky, health):
        app.register_blueprint(module.bp, url_prefix="/api")
