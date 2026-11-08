"""Score explanations for a spot-hour: cache lookup, bounded Gemini generation and fallbacks.

Shared by the API (`/spots/<id>` reads, `/spots/<id>/explanation` generates) and the
`ingest explain` pre-warm job.

Caching:
- Gemini answers are stored in `score_explanations` with the score they describe. They stay valid
  across hourly re-scores while the (rounded) score is unchanged, and are regenerated when it moves.
- When Gemini times out or fails, the deterministic template is remembered in-process for
  FALLBACK_TTL_S so repeat clicks are instant and a failing API isn't hammered. Templates are
  never written to the database.
- With no Gemini key configured the template is served directly (and not stored).
"""
from __future__ import annotations

import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from .ai import explain
from .ai.types import ExplainContext, Explanation
from .config import current_settings
from .repo import explanations as explanations_repo

log = logging.getLogger(__name__)

# Shared pool so a slow LLM call can be abandoned after a timeout.
_pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix="explain")

FALLBACK_TTL_S = 600.0
_fallbacks: dict[tuple, tuple[float, Explanation]] = {}
_fallbacks_lock = threading.Lock()


def _key(cell: dict, hour: datetime, score: dict) -> tuple:
    return (cell["id"], hour, int(score["model_version"]), round(float(score["score"])))


def _stored(cell: dict, hour: datetime, score: dict) -> Explanation | None:
    """The stored explanation if it was written for this (rounded) score."""
    row = explanations_repo.get(cell["id"], hour, int(score["model_version"]))
    if not row or row.get("explained_score") is None:
        return None
    if round(float(row["explained_score"])) != round(float(score["score"])):
        return None
    return Explanation(summary=row["summary"], tips=row["tips"])


def _recent_fallback(key: tuple) -> Explanation | None:
    now = time.monotonic()
    with _fallbacks_lock:
        for k in [k for k, (expires, _) in _fallbacks.items() if expires <= now]:
            del _fallbacks[k]
        entry = _fallbacks.get(key)
    return entry[1] if entry else None


def _remember_fallback(key: tuple, value: Explanation) -> None:
    with _fallbacks_lock:
        _fallbacks[key] = (time.monotonic() + FALLBACK_TTL_S, value)


def clear_fallbacks() -> None:
    with _fallbacks_lock:
        _fallbacks.clear()


def local_time_label(t: datetime, tz: str) -> str:
    local = t.astimezone(ZoneInfo(tz))
    hour12 = local.hour % 12 or 12
    return f"{local:%a %b} {local.day}, {hour12}:{local:%M} {'AM' if local.hour < 12 else 'PM'}"


def build_context(cell: dict, hour: datetime, score: dict, conditions: dict | None,
                  astro: dict | None) -> ExplainContext:
    settings = current_settings()
    return ExplainContext(
        cell_id=cell["id"], spot_name=cell["name"], valid_time=hour,
        local_time=local_time_label(hour, settings.region_tz), score=float(score["score"]),
        nelm=score.get("nelm"), factors=score.get("factors") or {}, bortle=cell.get("bortle"),
        sun_alt=(astro or {}).get("sun_alt"), moon_alt=(astro or {}).get("moon_alt"),
        moon_illum=(astro or {}).get("moon_illum"),
        conditions={k: v for k, v in (conditions or {}).items() if k != "fetched_at"},
    )


def ready(cell: dict, hour: datetime, score: dict, conditions: dict | None,
          astro: dict | None) -> Explanation | None:
    """An explanation that costs no LLM call, or None if one must be generated."""
    cached = _stored(cell, hour, score)
    if cached is not None:
        return cached
    if not explain.is_configured():
        return explain.fallback_explanation(build_context(cell, hour, score, conditions, astro))
    return _recent_fallback(_key(cell, hour, score))


def _store(cell: dict, hour: datetime, score: dict, result: Explanation) -> None:
    try:
        explanations_repo.put(cell["id"], hour, int(score["model_version"]), float(score["score"]),
                              result.summary, result.tips)
    except Exception as e:  # noqa: BLE001 - caching is best-effort
        log.warning("Could not cache explanation: %s", e)


def get_or_generate(cell: dict, hour: datetime, score: dict, conditions: dict | None,
                    astro: dict | None) -> Explanation:
    """Cached explanation, or a fresh Gemini one bounded by EXPLAIN_TIMEOUT_S (template on failure)."""
    hit = ready(cell, hour, score, conditions, astro)
    if hit is not None:
        return hit

    ctx = build_context(cell, hour, score, conditions, astro)
    key = _key(cell, hour, score)
    try:
        result = _pool.submit(explain.explain_score, ctx).result(timeout=current_settings().explain_timeout_s)
    except FutureTimeout:
        log.warning("explain_score timed out for cell %s", cell["id"])
        fallback = explain.fallback_explanation(ctx)
        _remember_fallback(key, fallback)
        return fallback
    except Exception as e:  # noqa: BLE001 - fall back to the template
        log.warning("explain_score failed for cell %s: %s", cell["id"], e)
        fallback = explain.fallback_explanation(ctx)
        _remember_fallback(key, fallback)
        return fallback

    _store(cell, hour, score, result)
    return result


def generate_and_store(cell: dict, hour: datetime, score: dict, conditions: dict | None,
                       astro: dict | None) -> Explanation:
    """Synchronous generation for batch jobs. Raises on Gemini failure; stores only successes."""
    result = explain.explain_score(build_context(cell, hour, score, conditions, astro))
    _store(cell, hour, score, result)
    return result


def is_cached(cell: dict, hour: datetime, score: dict[str, Any]) -> bool:
    return _stored(cell, hour, score) is not None
