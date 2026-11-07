from __future__ import annotations

import logging

from flask import Blueprint

from ..db import get_conn
from ..repo import ingest_log
from ..schemas.health import HealthResponse
from ..scoring import model
from ..storage import s3

log = logging.getLogger(__name__)

bp = Blueprint("health", __name__)


def _check_db() -> tuple[bool, object, object]:
    try:
        with get_conn(timeout=2.0) as conn:
            conn.execute("SELECT 1")
        return True, ingest_log.last_success("weather"), ingest_log.last_success("score")
    except Exception as e:  # noqa: BLE001 - health check reports, never raises
        log.warning("health: database check failed: %s", e)
        return False, None, None


@bp.get("/health")
def health():
    db_ok, last_weather, last_score = _check_db()
    storage_ok = s3.bucket_reachable()
    resp = HealthResponse(
        status="ok" if db_ok and storage_ok else "degraded",
        db=db_ok, storage=storage_ok, last_weather_fetch=last_weather, last_score_run=last_score,
        model_version=model.MODEL_VERSION,
    )
    return resp.model_dump(mode="json"), 200
