"""Job run log (`ingest_runs`). Written by ingest jobs, read by /health."""
from __future__ import annotations

from datetime import datetime
from typing import Any

import psycopg
from psycopg.types.json import Jsonb

from ..db import get_conn


def start(conn: psycopg.Connection, job: str, started_at: datetime) -> int:
    row = conn.execute(
        "INSERT INTO ingest_runs (job, started_at, status) VALUES (%s, %s, 'running') RETURNING id",
        (job, started_at),
    ).fetchone()
    conn.commit()
    return int(row["id"])


def finish(conn: psycopg.Connection, run_id: int, *, status: str, rows: int | None = None,
           details: dict[str, Any] | None = None) -> None:
    conn.execute(
        "UPDATE ingest_runs SET finished_at = now(), status = %s, rows = %s, details = %s WHERE id = %s",
        (status, rows, Jsonb(details) if details is not None else None, run_id),
    )
    conn.commit()


def last_success(job: str) -> datetime | None:
    """`finished_at` of the most recent successful run of `job`."""
    with get_conn() as conn:
        row = conn.execute(
            "SELECT finished_at FROM ingest_runs WHERE job = %s AND status = 'ok' "
            "ORDER BY started_at DESC LIMIT 1",
            (job,),
        ).fetchone()
    return row["finished_at"] if row else None
