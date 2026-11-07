"""Scores, served from the continuous aggregates (and raw snapshots for drift)."""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

from ..db import get_conn
from ..geo import BBox
from ..timeutil import local_day_window

_POINT = "ST_SetSRID(ST_MakePoint(%(lon)s, %(lat)s), 4326)::geography"


def scores_at(hour: datetime, bbox: BBox) -> list[dict[str, Any]]:
    """Every cell in the bbox with its score at `hour` (score/factors are NULL if not scored)."""
    w, s, e, n = bbox.as_tuple()
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT g.id AS cell_id, g.name, g.is_curated, g.bortle,
                   ST_Y(g.geom::geometry) AS lat, ST_X(g.geom::geometry) AS lon,
                   s.score, s.factors
            FROM grid_cells g
            LEFT JOIN cell_hourly_score s ON s.cell_id = g.id AND s.bucket = %s
            WHERE g.geom && ST_MakeEnvelope(%s, %s, %s, %s, 4326)::geography
            ORDER BY g.is_curated, g.id
            """,
            (hour, w, s, e, n),
        ).fetchall()
    return [dict(r) for r in rows]


def score_range(since: datetime) -> tuple[datetime | None, datetime | None]:
    """First and last scored hour at or after `since`."""
    with get_conn() as conn:
        row = conn.execute(
            "SELECT min(bucket) AS min_time, max(bucket) AS max_time FROM cell_hourly_score WHERE bucket >= %s",
            (since,),
        ).fetchone()
    return (row["min_time"], row["max_time"]) if row else (None, None)


def _near_sql(near: tuple[float, float] | None, radius_km: float | None, params: dict[str, Any]) -> tuple[str, str]:
    """(distance select expr, where clause) for an optional proximity filter."""
    if near is None:
        return "NULL::double precision", ""
    params["lat"], params["lon"] = near
    where = ""
    if radius_km is not None:
        params["radius_m"] = radius_km * 1000.0
        where = f" AND ST_DWithin(g.geom, {_POINT}, %(radius_m)s)"
    return f"ST_Distance(g.geom, {_POINT}) / 1000.0", where


def best_at(hour: datetime, near: tuple[float, float] | None, radius_km: float | None,
            limit: int) -> list[dict[str, Any]]:
    params: dict[str, Any] = {"hour": hour, "limit": limit}
    dist, where = _near_sql(near, radius_km, params)
    sql = f"""
        SELECT g.id AS cell_id, g.name, g.is_curated, g.bortle,
               ST_Y(g.geom::geometry) AS lat, ST_X(g.geom::geometry) AS lon,
               s.score, s.bucket AS valid_time, {dist} AS distance_km
        FROM cell_hourly_score s
        JOIN grid_cells g ON g.id = s.cell_id
        WHERE s.bucket = %(hour)s{where}
        ORDER BY s.score DESC, g.is_curated DESC, g.id
        LIMIT %(limit)s
    """
    with get_conn() as conn:
        return [dict(r) for r in conn.execute(sql, params).fetchall()]


def best_for_night(night: date, tz: str, near: tuple[float, float] | None, radius_km: float | None,
                   limit: int) -> list[dict[str, Any]]:
    """Top cells by nightly best score. Night buckets start at local noon of `night`."""
    start, end = local_day_window(night, tz)
    params: dict[str, Any] = {"start": start, "end": end, "limit": limit}
    dist, where = _near_sql(near, radius_km, params)
    sql = f"""
        SELECT g.id AS cell_id, g.name, g.is_curated, g.bortle,
               ST_Y(g.geom::geometry) AS lat, ST_X(g.geom::geometry) AS lon,
               n.best_score AS score, n.best_time AS valid_time, {dist} AS distance_km
        FROM cell_nightly_best n
        JOIN grid_cells g ON g.id = n.cell_id
        WHERE n.night >= %(start)s AND n.night < %(end)s{where}
        ORDER BY n.best_score DESC, g.is_curated DESC, g.id
        LIMIT %(limit)s
    """
    with get_conn() as conn:
        return [dict(r) for r in conn.execute(sql, params).fetchall()]


def score_for(cell_id: int, hour: datetime) -> dict[str, Any] | None:
    """{score, nelm, factors, model_version, computed_at} for one cell-hour, or None."""
    with get_conn() as conn:
        row = conn.execute(
            "SELECT score, nelm, factors, model_version, computed_at "
            "FROM cell_hourly_score WHERE cell_id = %s AND bucket = %s",
            (cell_id, hour),
        ).fetchone()
    return dict(row) if row else None


def history(cell_id: int, start: datetime, end: datetime, tz: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """(hourly [{time, score, nelm}], nightly [{night (local date), best_score, best_time}]) in [start, end)."""
    with get_conn() as conn:
        hourly = conn.execute(
            "SELECT bucket AS time, score, nelm FROM cell_hourly_score "
            "WHERE cell_id = %s AND bucket >= %s AND bucket < %s ORDER BY bucket",
            (cell_id, start, end),
        ).fetchall()
        nightly = conn.execute(
            "SELECT (night AT TIME ZONE %s)::date AS night, best_score, best_time FROM cell_nightly_best "
            "WHERE cell_id = %s AND night >= %s AND night < %s ORDER BY night",
            (tz, cell_id, start - timedelta(days=1), end),
        ).fetchall()
    return [dict(r) for r in hourly], [dict(r) for r in nightly]


def drift(cell_id: int, start: datetime, end: datetime) -> list[dict[str, Any]]:
    """Every score revision for valid_time in [start, end), grouped by computed_at.

    Returns [{computed_at, model_version, points: [{valid_time, score}]}] ordered by computed_at.
    """
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT computed_at, model_version, valid_time, score FROM score_snapshots "
            "WHERE cell_id = %s AND valid_time >= %s AND valid_time < %s "
            "ORDER BY computed_at, valid_time",
            (cell_id, start, end),
        ).fetchall()
    revisions: list[dict[str, Any]] = []
    for r in rows:
        if not revisions or revisions[-1]["computed_at"] != r["computed_at"]:
            revisions.append({"computed_at": r["computed_at"], "model_version": r["model_version"], "points": []})
        revisions[-1]["points"].append({"valid_time": r["valid_time"], "score": r["score"]})
    return revisions
