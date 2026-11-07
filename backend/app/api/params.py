"""Query-string parsing helpers shared by blueprints."""
from __future__ import annotations

from datetime import datetime

from flask import request

from ..errors import bad_request
from ..timeutil import floor_hour, parse_iso, utcnow


def body() -> dict:
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else {}


def hour_arg(name: str = "time") -> datetime:
    """The requested hour (floored), defaulting to the current hour."""
    return floor_hour(parse_iso(request.args.get(name), field=name) or utcnow())


def int_arg(name: str, default: int, lo: int, hi: int) -> int:
    raw = request.args.get(name)
    if raw in (None, ""):
        return default
    try:
        value = int(raw)
    except ValueError as e:
        raise bad_request(f"'{name}' must be an integer") from e
    if not lo <= value <= hi:
        raise bad_request(f"'{name}' must be between {lo} and {hi}")
    return value


def float_arg(name: str, default: float | None, lo: float, hi: float) -> float | None:
    raw = request.args.get(name)
    if raw in (None, ""):
        return default
    try:
        value = float(raw)
    except ValueError as e:
        raise bad_request(f"'{name}' must be a number") from e
    if not lo <= value <= hi:
        raise bad_request(f"'{name}' must be between {lo} and {hi}")
    return value
