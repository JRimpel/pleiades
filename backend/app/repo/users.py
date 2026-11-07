"""Users and bearer-token lookup."""
from __future__ import annotations

from typing import Any

import psycopg.errors

from ..db import get_conn


class UsernameTaken(Exception):
    pass


def create(username: str, token_hash: str) -> dict[str, Any]:
    """Insert a user. Raises UsernameTaken if the username already exists."""
    try:
        with get_conn() as conn:
            row = conn.execute(
                "INSERT INTO users (username, token_hash) VALUES (%s, %s) RETURNING id, username",
                (username, token_hash),
            ).fetchone()
    except psycopg.errors.UniqueViolation as e:
        raise UsernameTaken(username) from e
    return dict(row)


def get_by_token_hash(token_hash: str) -> dict[str, Any] | None:
    """{id, username} for the token, or None."""
    with get_conn() as conn:
        row = conn.execute(
            "SELECT id, username FROM users WHERE token_hash = %s", (token_hash,)
        ).fetchone()
    return dict(row) if row else None
