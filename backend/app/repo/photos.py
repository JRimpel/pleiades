"""Photos and their AI analysis state."""
from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

import psycopg.errors
from psycopg.types.json import Jsonb

from ..db import get_conn
from ..geo import BBox

VISIBLE_STATUSES = ("pending", "done", "failed")  # only rejected (not a night-sky photo) is hidden; failed = AI unavailable


class PhotoExists(Exception):
    pass


def insert(*, photo_id: UUID, user_id: UUID, s3_key: str, mime_type: str | None, lat: float, lon: float,
           cell_id: int | None, taken_at: datetime | None, taken_at_source: str, caption: str | None,
           score_at_capture: float | None) -> UUID:
    try:
        with get_conn() as conn:
            row = conn.execute(
                """
                INSERT INTO photos (id, user_id, s3_key, mime_type, geom, cell_id, taken_at, taken_at_source,
                                    caption, score_at_capture)
                VALUES (%s, %s, %s, %s, ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                (photo_id, user_id, s3_key, mime_type, lon, lat, cell_id, taken_at, taken_at_source,
                 caption, score_at_capture),
            ).fetchone()
    except psycopg.errors.UniqueViolation as e:
        raise PhotoExists(s3_key) from e
    return row["id"]


_DETAIL_COLS = """
    p.id, u.username, p.s3_key, p.thumb_key, p.mime_type,
    ST_Y(p.geom::geometry) AS lat, ST_X(p.geom::geometry) AS lon, p.cell_id,
    p.taken_at, p.taken_at_source, p.uploaded_at, p.caption, p.score_at_capture,
    p.ai_status, p.ai_description, p.ai_objects, p.ai_sky_quality,
    p.ai_milky_way_visible, p.ai_light_pollution_notes, p.ai_attempts, p.vote_count
"""


def get_detail(photo_id: UUID) -> dict[str, Any] | None:
    with get_conn() as conn:
        row = conn.execute(
            f"SELECT {_DETAIL_COLS} FROM photos p JOIN users u ON u.id = p.user_id WHERE p.id = %s",
            (photo_id,),
        ).fetchone()
    return dict(row) if row else None


def list_markers(bbox: BBox, sort: str, limit: int) -> list[dict[str, Any]]:
    order = "p.vote_count DESC, p.uploaded_at DESC" if sort == "top" else "p.uploaded_at DESC"
    w, s, e, n = bbox.as_tuple()
    with get_conn() as conn:
        rows = conn.execute(
            f"""
            SELECT p.id, ST_Y(p.geom::geometry) AS lat, ST_X(p.geom::geometry) AS lon, p.thumb_key,
                   p.vote_count, p.taken_at, p.ai_status, p.ai_sky_quality
            FROM photos p
            WHERE p.ai_status = ANY(%s)
              AND p.geom && ST_MakeEnvelope(%s, %s, %s, %s, 4326)::geography
            ORDER BY {order}
            LIMIT %s
            """,
            (list(VISIBLE_STATUSES), w, s, e, n, limit),
        ).fetchall()
    return [dict(r) for r in rows]


def search(*, bbox: BBox | None = None, near: tuple[float, float] | None = None, radius_km: float | None = None,
           object_name: str | None = None, since: datetime | None = None, limit: int = 6) -> list[dict[str, Any]]:
    """Analyzed photos for the chat assistant, best-voted first. Every filter is optional."""
    where = ["p.ai_status = 'done'"]
    params: dict[str, Any] = {"limit": limit}
    if bbox is not None:
        params.update(zip(("w", "s", "e", "n"), bbox.as_tuple()))
        where.append("p.geom && ST_MakeEnvelope(%(w)s, %(s)s, %(e)s, %(n)s, 4326)::geography")
    if near is not None and radius_km is not None:
        params["lat"], params["lon"] = near
        params["radius_m"] = radius_km * 1000.0
        where.append("ST_DWithin(p.geom, ST_SetSRID(ST_MakePoint(%(lon)s, %(lat)s), 4326)::geography, %(radius_m)s)")
    if object_name:
        params["object"] = "%" + object_name.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        where.append("EXISTS (SELECT 1 FROM jsonb_array_elements(coalesce(p.ai_objects, '[]'::jsonb)) o "
                     "WHERE o->>'name' ILIKE %(object)s)")
    if since is not None:
        params["since"] = since
        where.append("coalesce(p.taken_at, p.uploaded_at) >= %(since)s")
    with get_conn() as conn:
        rows = conn.execute(
            f"""
            SELECT p.id, ST_Y(p.geom::geometry) AS lat, ST_X(p.geom::geometry) AS lon, p.cell_id, p.thumb_key,
                   p.taken_at, p.uploaded_at, p.caption, p.score_at_capture, p.ai_description, p.ai_objects,
                   p.ai_sky_quality, p.ai_milky_way_visible, p.vote_count
            FROM photos p
            WHERE {' AND '.join(where)}
            ORDER BY p.vote_count DESC, coalesce(p.taken_at, p.uploaded_at) DESC
            LIMIT %(limit)s
            """,
            params,
        ).fetchall()
    return [dict(r) for r in rows]


def delete_all() -> list[dict[str, Any]]:
    """Delete every photo (votes cascade). Returns the deleted rows' storage keys."""
    with get_conn() as conn:
        rows = conn.execute("DELETE FROM photos RETURNING s3_key, thumb_key").fetchall()
    return [dict(r) for r in rows]


def count_recent_uploads(user_id: UUID, since: datetime) -> int:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT count(*) AS n FROM photos WHERE user_id = %s AND uploaded_at >= %s", (user_id, since)
        ).fetchone()
    return int(row["n"])


# ---- background analysis -------------------------------------------------------------

def get_for_processing(photo_id: UUID) -> dict[str, Any] | None:
    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT id, s3_key, thumb_key, mime_type, ST_Y(geom::geometry) AS lat, ST_X(geom::geometry) AS lon,
                   taken_at, uploaded_at, caption, ai_status, ai_attempts
            FROM photos WHERE id = %s
            """,
            (photo_id,),
        ).fetchone()
    return dict(row) if row else None


def increment_attempts(photo_id: UUID) -> int:
    with get_conn() as conn:
        row = conn.execute(
            "UPDATE photos SET ai_attempts = ai_attempts + 1, ai_updated_at = now() WHERE id = %s "
            "RETURNING ai_attempts",
            (photo_id,),
        ).fetchone()
    return int(row["ai_attempts"]) if row else 0


def set_thumb(photo_id: UUID, thumb_key: str) -> None:
    with get_conn() as conn:
        conn.execute("UPDATE photos SET thumb_key = %s WHERE id = %s", (thumb_key, photo_id))


def update_ai_result(photo_id: UUID, *, status: str, description: str | None, objects: list[dict[str, Any]],
                     sky_quality: int | None, milky_way_visible: bool | None,
                     light_pollution_notes: str | None) -> None:
    with get_conn() as conn:
        conn.execute(
            """
            UPDATE photos SET ai_status = %s, ai_description = %s, ai_objects = %s, ai_sky_quality = %s,
                   ai_milky_way_visible = %s, ai_light_pollution_notes = %s, ai_error = NULL,
                   ai_updated_at = now()
            WHERE id = %s
            """,
            (status, description, Jsonb(objects), sky_quality, milky_way_visible, light_pollution_notes, photo_id),
        )


def mark_failed(photo_id: UUID, error: str) -> None:
    with get_conn() as conn:
        conn.execute(
            "UPDATE photos SET ai_status = 'failed', ai_error = %s, ai_updated_at = now() WHERE id = %s",
            (error[:1000], photo_id),
        )


def claim_stale_pending(older_than: datetime, limit: int = 100) -> list[UUID]:
    """Atomically claim pending photos whose analysis looks abandoned (e.g. the worker died).

    Claiming bumps ai_updated_at, so concurrent gunicorn workers don't requeue the same photo.
    """
    with get_conn() as conn:
        rows = conn.execute(
            """
            UPDATE photos SET ai_updated_at = now()
            WHERE id IN (
                SELECT id FROM photos
                WHERE ai_status = 'pending' AND uploaded_at < %s
                  AND (ai_updated_at IS NULL OR ai_updated_at < %s)
                ORDER BY uploaded_at LIMIT %s
                FOR UPDATE SKIP LOCKED
            )
            RETURNING id
            """,
            (older_than, older_than, limit),
        ).fetchall()
    return [r["id"] for r in rows]
