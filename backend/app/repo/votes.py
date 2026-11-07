"""Photo votes."""
from __future__ import annotations

from uuid import UUID

from ..db import get_conn


def set_vote(user_id: UUID, photo_id: UUID, value: int) -> int | None:
    """Upsert (value ±1) or delete (value 0) a vote, then recompute the photo's vote_count.

    Runs in one transaction with the photo row locked. Returns the new vote_count, or None if
    the photo does not exist.
    """
    with get_conn() as conn:
        if conn.execute("SELECT id FROM photos WHERE id = %s FOR UPDATE", (photo_id,)).fetchone() is None:
            return None
        if value == 0:
            conn.execute("DELETE FROM votes WHERE user_id = %s AND photo_id = %s", (user_id, photo_id))
        else:
            conn.execute(
                "INSERT INTO votes (user_id, photo_id, value) VALUES (%s, %s, %s) "
                "ON CONFLICT (user_id, photo_id) DO UPDATE SET value = EXCLUDED.value, created_at = now()",
                (user_id, photo_id, value),
            )
        row = conn.execute(
            "UPDATE photos SET vote_count = COALESCE((SELECT sum(value) FROM votes WHERE photo_id = %s), 0) "
            "WHERE id = %s RETURNING vote_count",
            (photo_id, photo_id),
        ).fetchone()
    return int(row["vote_count"])


def get_my_vote(user_id: UUID, photo_id: UUID) -> int:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT value FROM votes WHERE user_id = %s AND photo_id = %s", (user_id, photo_id)
        ).fetchone()
    return int(row["value"]) if row else 0
