"""Cache of Gemini score explanations, keyed by (cell, hour, model_version), plus the score they describe."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from psycopg.types.json import Jsonb

from ..db import get_conn


def get(cell_id: int, valid_time: datetime, model_version: int) -> dict[str, Any] | None:
    """{summary, tips, explained_score} for one cell-hour, or None. Callers check explained_score."""
    with get_conn() as conn:
        row = conn.execute(
            "SELECT summary, tips, explained_score FROM score_explanations "
            "WHERE cell_id = %s AND valid_time = %s AND model_version = %s",
            (cell_id, valid_time, model_version),
        ).fetchone()
    if not row:
        return None
    return {"summary": row["summary"], "tips": list(row["tips"] or []), "explained_score": row["explained_score"]}


def put(cell_id: int, valid_time: datetime, model_version: int, explained_score: float,
        summary: str, tips: list[str]) -> None:
    """Store (or replace) the explanation for one cell-hour."""
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO score_explanations (cell_id, valid_time, model_version, explained_score, summary, tips) "
            "VALUES (%s, %s, %s, %s, %s, %s) "
            "ON CONFLICT (cell_id, valid_time, model_version) DO UPDATE SET "
            "explained_score = EXCLUDED.explained_score, summary = EXCLUDED.summary, "
            "tips = EXCLUDED.tips, created_at = now()",
            (cell_id, valid_time, model_version, explained_score, summary, Jsonb(tips)),
        )
