"""psycopg 3 connection pool.

The pool is created lazily so the app can boot (and report "db down" on /health)
even when DATABASE_URL is missing or the database is unreachable.
"""
from __future__ import annotations

import logging
import threading
from contextlib import contextmanager
from typing import Iterator

import psycopg
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from .config import Settings, get_settings

log = logging.getLogger(__name__)

_pool: ConnectionPool | None = None
_lock = threading.Lock()


class DatabaseNotConfigured(RuntimeError):
    pass


def init_pool(settings: Settings | None = None) -> ConnectionPool:
    global _pool
    settings = settings or get_settings()
    with _lock:
        if _pool is not None:
            return _pool
        if not settings.database_url:
            raise DatabaseNotConfigured("DATABASE_URL is not set")
        _pool = ConnectionPool(
            conninfo=settings.database_url,
            min_size=settings.db_pool_min,
            max_size=settings.db_pool_max,
            kwargs={"row_factory": dict_row, "autocommit": False},
            open=False,
            name="pleiades",
        )
        # Don't block boot waiting for the DB; connections are made on demand.
        _pool.open(wait=False)
        return _pool


def get_pool() -> ConnectionPool:
    return _pool if _pool is not None else init_pool()


def close_pool() -> None:
    global _pool
    with _lock:
        if _pool is not None:
            _pool.close()
            _pool = None


@contextmanager
def get_conn(timeout: float = 10.0) -> Iterator[psycopg.Connection]:
    """Borrow a connection. Commits on success, rolls back on exception."""
    with get_pool().connection(timeout=timeout) as conn:
        yield conn


def connect_direct(settings: Settings | None = None) -> psycopg.Connection:
    """A standalone connection for CLI jobs and migrations (no pool)."""
    settings = settings or get_settings()
    if not settings.database_url:
        raise DatabaseNotConfigured("DATABASE_URL is not set")
    return psycopg.connect(settings.database_url, row_factory=dict_row)
