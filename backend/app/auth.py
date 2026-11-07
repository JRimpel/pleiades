"""Lightweight bearer-token auth.

Tokens are random strings handed to the client once; only their sha256 is stored.
"""
from __future__ import annotations

import hashlib
import secrets
from functools import wraps
from typing import Callable, TypeVar

from flask import g, request

from .errors import unauthorized

F = TypeVar("F", bound=Callable)


def generate_token() -> str:
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def bearer_token_from_request() -> str | None:
    header = request.headers.get("Authorization", "")
    scheme, _, value = header.partition(" ")
    if scheme.lower() != "bearer" or not value.strip():
        return None
    return value.strip()


def require_auth(fn: F) -> F:
    """Resolve the bearer token to a user and expose it as `g.user` ({id, username})."""

    @wraps(fn)
    def wrapper(*args, **kwargs):
        from .repo import users as users_repo  # local import: keeps auth importable without DB

        token = bearer_token_from_request()
        if not token:
            raise unauthorized()
        user = users_repo.get_by_token_hash(hash_token(token))
        if user is None:
            raise unauthorized()
        g.user = user
        return fn(*args, **kwargs)

    return wrapper  # type: ignore[return-value]


def optional_user() -> dict | None:
    """The user for a valid bearer token, or None (never raises for missing/invalid tokens)."""
    from .repo import users as users_repo

    token = bearer_token_from_request()
    if not token:
        return None
    return users_repo.get_by_token_hash(hash_token(token))
