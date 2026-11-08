"""`python -m app.ingest explain`: pre-generate Gemini explanations for likely clicks.

Targets tonight's top spots and every curated spot, each at its best hour tonight, so the
spot panel opens with its explanation already cached. Runs after each score job.
Successes are cached; failures are logged and skipped. Calls are spaced by
EXPLAIN_WARM_INTERVAL_S and the batch stops at the first rate-limit (429) response; the next
run picks up whatever is still missing. Does nothing without a Gemini key.
"""
from __future__ import annotations

import logging
import time
from datetime import datetime

import psycopg
from google.genai import errors as genai_errors

from .. import spot_explanations
from ..ai import explain
from ..config import Settings
from ..db import close_pool
from ..repo import cells as cells_repo
from ..repo import forecasts as forecasts_repo
from ..repo import scores as scores_repo
from ..timeutil import current_night, local_day_window, utcnow

log = logging.getLogger(__name__)

TOP_N = 10

CURATED_BEST_SQL = """
SELECT n.cell_id, n.best_time
FROM cell_nightly_best n
JOIN grid_cells g ON g.id = n.cell_id
WHERE g.is_curated AND n.night >= %(start)s AND n.night < %(end)s AND n.best_time IS NOT NULL
ORDER BY n.cell_id
"""


def targets(conn: psycopg.Connection, settings: Settings, now: datetime) -> list[tuple[int, datetime]]:
    """(cell_id, hour) pairs to warm: tonight's top spots, then curated spots, de-duplicated."""
    night = current_night(now, settings.region_tz)
    start, end = local_day_window(night, settings.region_tz)
    top = scores_repo.best_for_night(night, settings.region_tz, None, None, TOP_N)
    curated = conn.execute(CURATED_BEST_SQL, {"start": start, "end": end}).fetchall()
    seen: set[tuple[int, datetime]] = set()
    out: list[tuple[int, datetime]] = []
    for row in [*({"cell_id": r["cell_id"], "best_time": r["valid_time"]} for r in top), *curated]:
        pair = (int(row["cell_id"]), row["best_time"])
        if pair[1] is not None and pair not in seen:
            seen.add(pair)
            out.append(pair)
    return out


def run(conn: psycopg.Connection, settings: Settings) -> int:
    if not explain.is_configured():
        log.info("explain: GEMINI_API_KEY/GEMINI_MODEL not set; skipping pre-warm")
        return 0
    generated = calls = 0
    try:
        pairs = targets(conn, settings, utcnow())
        for cell_id, hour in pairs:
            cell = cells_repo.get(cell_id)
            score = scores_repo.score_for(cell_id, hour)
            if cell is None or score is None or spot_explanations.is_cached(cell, hour, score):
                continue
            if calls and settings.explain_warm_interval_s > 0:
                time.sleep(settings.explain_warm_interval_s)
            calls += 1
            try:
                spot_explanations.generate_and_store(
                    cell, hour, score, forecasts_repo.latest_for(cell_id, hour), forecasts_repo.astro_at(hour))
                generated += 1
            except genai_errors.ClientError as e:
                if e.code == 429:
                    log.warning("explain: Gemini rate limit reached; stopping (next run continues)")
                    break
                log.warning("explain: cell %s at %s failed: %s", cell_id, hour.isoformat(), e)
            except Exception as e:  # noqa: BLE001 - one bad call shouldn't stop the batch
                log.warning("explain: cell %s at %s failed: %s", cell_id, hour.isoformat(), e)
        log.info("explain: generated %d of %d target explanation(s)", generated, len(pairs))
    finally:
        close_pool()
    return generated
