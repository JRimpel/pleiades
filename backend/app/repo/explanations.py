"""Cache of Gemini score explanations, keyed by (cell, hour, model_version)."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from psycopg.types.json import Jsonb

from ..db import get_conn


def get(cell_id: int, valid_time: datetime, model_version: int) -> dict[str, Any] | None:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT summary, tips FROM score_explanations "
            "WHERE cell_id = %s AND valid_time = %s AND model_version = %s",
            (cell_id, valid_time, model_version),
        ).fetchone()
    return {"summary": row["summary"], "tips": list(row["tips"] or [])} if row else None


def put(cell_id: int, valid_time: datetime, model_version: int, summary: str, tips: list[str]) -> None:
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO score_explanations (cell_id, valid_time, model_version, summary, tips) "
            "VALUES (%s, %s, %s, %s, %s) ON CONFLICT DO NOTHING",
            (cell_id, valid_time, model_version, summary, Jsonb(tips)),
        )
