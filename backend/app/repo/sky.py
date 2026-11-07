"""Sky events (planets, ISS passes, meteor showers, ...)."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from ..db import get_conn


def events_between(start: datetime, end: datetime) -> list[dict[str, Any]]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT time, type, name, details FROM sky_events WHERE time >= %s AND time < %s ORDER BY time",
            (start, end),
        ).fetchall()
    return [dict(r) for r in rows]
