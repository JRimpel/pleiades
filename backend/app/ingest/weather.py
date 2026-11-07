"""`python -m app.ingest weather`: fetch the hourly forecast for every cell and append it as a new revision."""
from __future__ import annotations

import logging
import time

import psycopg
import requests

from ..config import Settings
from ..timeutil import utcnow
from . import openmeteo

log = logging.getLogger(__name__)

SLEEP_BETWEEN_CALLS_S = 0.5


def load_cells(conn: psycopg.Connection) -> list[tuple[int, float, float]]:
    rows = conn.execute(
        "SELECT id, ST_Y(geom::geometry) AS lat, ST_X(geom::geometry) AS lon FROM grid_cells ORDER BY id"
    ).fetchall()
    return [(int(r["id"]), float(r["lat"]), float(r["lon"])) for r in rows]


def copy_rows(conn: psycopg.Connection, rows: list[tuple]) -> int:
    cols = ", ".join(openmeteo.WEATHER_COLUMNS)
    with conn.cursor() as cur:
        with cur.copy(f"COPY weather_forecast ({cols}) FROM STDIN") as copy:
            for row in rows:
                copy.write_row(row)
    return len(rows)


def run(conn: psycopg.Connection, settings: Settings, *, session: requests.Session | None = None,
        sleep=time.sleep) -> int:
    cells = load_cells(conn)
    if not cells:
        log.warning("grid_cells is empty; nothing to fetch")
        return 0
    session = session or requests.Session()
    fetched_at = utcnow()
    total = 0
    batches = list(openmeteo.chunks(cells, openmeteo.BATCH_SIZE))
    for k, batch in enumerate(batches):
        if k:
            sleep(SLEEP_BETWEEN_CALLS_S)
        coords = [(lat, lon) for _, lat, lon in batch]
        payload = openmeteo.fetch_batch(coords, settings.forecast_hours, session)
        rows = openmeteo.parse_response(payload, [cid for cid, _, _ in batch], fetched_at)
        total += copy_rows(conn, rows)
        log.info("weather batch %d/%d: %d rows", k + 1, len(batches), len(rows))
    conn.commit()
    log.info("weather ingest: %d rows for %d cells (fetched_at=%s)", total, len(cells), fetched_at.isoformat())
    return total
