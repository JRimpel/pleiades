"""`python -m app.ingest score`: run the scoring model over every cell × hour of the forecast window.

Joins the latest forecast revision, the astro conditions and static cell data, calls the
AI/ML model (`app.scoring.model.score_batch`), appends results to `score_snapshots`, and
refreshes the continuous aggregates for the affected window.
"""
from __future__ import annotations

import json
import logging
import math
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping, Sequence

import numpy as np
import psycopg

from .. import scoring
from ..config import Settings
from ..scoring import model as scoring_model  # noqa: F401  (ensures the module is loaded)
from ..scoring.types import FeatureBatch, ScoreBatch
from ..timeutil import floor_hour, utcnow

log = logging.getLogger(__name__)

# FeatureBatch field -> row key produced by FEATURE_SQL.
FLOAT_FIELDS: tuple[str, ...] = (
    "m_sky", "bortle", "elevation_m",
    "cloud_low", "cloud_mid", "cloud_high", "cloud_total",
    "visibility_m", "rh", "dew_point_c", "temp_c", "wind_kmh", "precip_prob",
    "sun_alt", "moon_alt", "moon_illum", "moon_phase_deg",
)

FEATURE_SQL = """
SELECT w.cell_id, w.valid_time,
       g.sky_brightness_mpsas AS m_sky, g.bortle, g.elevation_m,
       w.cloud_low, w.cloud_mid, w.cloud_high, w.cloud_total,
       w.visibility_m, w.rh, w.dew_point_c, w.temp_c, w.wind_kmh, w.precip_prob,
       a.sun_alt, a.moon_alt, a.moon_illum, a.moon_phase_deg
FROM (
  SELECT DISTINCT ON (cell_id, valid_time) *
  FROM weather_forecast
  WHERE valid_time >= %(start)s AND valid_time <= %(end)s
  ORDER BY cell_id, valid_time, fetched_at DESC
) w
JOIN grid_cells g ON g.id = w.cell_id
JOIN astro_conditions a ON a.time = w.valid_time
ORDER BY w.cell_id, w.valid_time
"""

MISSING_ASTRO_SQL = """
SELECT count(DISTINCT w.valid_time) AS n
FROM weather_forecast w
WHERE w.valid_time >= %(start)s AND w.valid_time <= %(end)s
  AND NOT EXISTS (SELECT 1 FROM astro_conditions a WHERE a.time = w.valid_time)
"""

SNAPSHOT_COLUMNS = ("valid_time", "cell_id", "computed_at", "score", "nelm", "factors", "model_version")


def score_window(now: datetime, forecast_hours: int) -> tuple[datetime, datetime]:
    start = floor_hour(now) - timedelta(hours=3)
    end = floor_hour(now) + timedelta(hours=forecast_hours)
    return start, end


def _to_float(v: Any) -> float:
    return math.nan if v is None else float(v)


def _to_dt64(v: datetime) -> np.datetime64:
    if v.tzinfo is not None:
        v = v.astimezone(timezone.utc).replace(tzinfo=None)
    return np.datetime64(v, "s")


def build_feature_batch(rows: Sequence[Mapping[str, Any]]) -> FeatureBatch:
    """Pure: DB rows (dicts) -> FeatureBatch. None -> NaN; valid_time -> datetime64[s] (UTC)."""
    n = len(rows)
    cols: dict[str, np.ndarray] = {
        "cell_id": np.fromiter((int(r["cell_id"]) for r in rows), dtype=np.int64, count=n),
        "valid_time": np.array([_to_dt64(r["valid_time"]) for r in rows], dtype="datetime64[s]"),
    }
    for f in FLOAT_FIELDS:
        cols[f] = np.fromiter((_to_float(r.get(f)) for r in rows), dtype=np.float64, count=n)
    return FeatureBatch(**cols)


def validate_result(batch: FeatureBatch, result: ScoreBatch) -> None:
    n = len(batch)
    if result.score.shape != (n,) or result.nelm.shape != (n,) or len(result.factors) != n:
        raise ValueError(
            f"score_batch returned mismatched lengths: score={result.score.shape} "
            f"nelm={result.nelm.shape} factors={len(result.factors)} expected={n}"
        )


def snapshot_rows(batch: FeatureBatch, result: ScoreBatch, computed_at: datetime, model_version: int) -> list[tuple]:
    """Rows for COPY into score_snapshots. Rows with a non-finite score are dropped."""
    out: list[tuple] = []
    for i in range(len(batch)):
        score = float(result.score[i])
        if not math.isfinite(score):
            continue
        nelm = float(result.nelm[i])
        valid_time = batch.valid_time[i].astype("datetime64[s]").astype(datetime).replace(tzinfo=timezone.utc)
        out.append((
            valid_time,
            int(batch.cell_id[i]),
            computed_at,
            score,
            nelm if math.isfinite(nelm) else None,
            json.dumps(result.factors[i]),
            model_version,
        ))
    return out


def copy_snapshots(conn: psycopg.Connection, rows: list[tuple]) -> None:
    cols = ", ".join(SNAPSHOT_COLUMNS)
    with conn.cursor() as cur:
        with cur.copy(f"COPY score_snapshots ({cols}) FROM STDIN") as copy:
            for row in rows:
                copy.write_row(row)


def refresh_windows(start: datetime, end: datetime) -> dict[str, tuple[datetime, datetime]]:
    """Refresh windows for each continuous aggregate.

    The hourly CAGG only materializes buckets fully inside the window, so extend the end by
    an hour. The nightly CAGG has 1-day (local noon-to-noon) buckets: widen to whole UTC
    days with a day of margin on each side.
    """
    hourly = (start, end + timedelta(hours=1))
    day_start = start.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=1)
    day_end = end.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=2)
    return {"cell_hourly_score": hourly, "cell_nightly_best": (day_start, day_end)}


def refresh_aggregates(database_url: str, start: datetime, end: datetime) -> None:
    # refresh_continuous_aggregate cannot run inside a transaction block.
    with psycopg.connect(database_url, autocommit=True) as conn:
        for view, (s, e) in refresh_windows(start, end).items():
            log.info("refreshing %s for [%s, %s)", view, s.isoformat(), e.isoformat())
            conn.execute("CALL refresh_continuous_aggregate(%s, %s, %s)", (view, s, e))


def run(conn: psycopg.Connection, settings: Settings, *, refresh: bool = True) -> int:
    now = utcnow()
    start, end = score_window(now, settings.forecast_hours)
    params = {"start": start, "end": end}

    missing = conn.execute(MISSING_ASTRO_SQL, params).fetchone()
    if missing and missing["n"]:
        log.warning("%d forecast hour(s) have no astro_conditions and will be skipped (run `ingest astro`)",
                    missing["n"])

    rows = conn.execute(FEATURE_SQL, params).fetchall()
    if not rows:
        log.warning("no forecast rows in [%s, %s]; nothing to score", start.isoformat(), end.isoformat())
        conn.rollback()
        return 0

    batch = build_feature_batch(rows)
    result = scoring.model.score_batch(batch)
    validate_result(batch, result)

    model_version = int(scoring.model.MODEL_VERSION)
    out = snapshot_rows(batch, result, now, model_version)
    dropped = len(batch) - len(out)
    if dropped:
        log.warning("dropped %d row(s) with non-finite scores", dropped)
    copy_snapshots(conn, out)
    conn.commit()
    log.info("score: %d snapshots (model_version=%d, computed_at=%s)", len(out), model_version, now.isoformat())

    if refresh and out:
        refresh_aggregates(settings.database_url, start, end)
    return len(out)
