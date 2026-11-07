"""Pleiades Flask application factory."""
from __future__ import annotations

import logging

from flask import Flask

from .config import Settings
from .db import DatabaseNotConfigured, init_pool
from .errors import register_error_handlers

log = logging.getLogger(__name__)


def create_app(settings: Settings | None = None, *, start_workers: bool = True, init_db: bool = True) -> Flask:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    settings = settings or Settings.from_env()

    app = Flask(__name__)
    app.config["SETTINGS"] = settings
    app.json.sort_keys = False

    register_error_handlers(app)

    if init_db:
        try:
            init_pool(settings)
        except DatabaseNotConfigured:
            log.warning("DATABASE_URL not set: API will run, but DB-backed routes will fail (see /api/health)")

    from .api import register_blueprints

    register_blueprints(app)

    if start_workers:
        from .workers.photo_analysis import init_worker

        init_worker(settings)

    return app
