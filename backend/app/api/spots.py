from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from flask import Blueprint, request

from ..ai import explain
from ..ai.types import ExplainContext, Explanation
from ..config import current_settings
from ..errors import bad_request, not_found
from ..repo import cells as cells_repo
from ..repo import explanations as explanations_repo
from ..repo import forecasts as forecasts_repo
from ..repo import scores as scores_repo
from ..schemas.common import score_label
from ..schemas.spots import (AstroSnapshot, Conditions, DriftPoint, DriftRevision, ExplanationOut, HistoryPoint,
                             NightlyBest, SpotDetail, SpotDrift, SpotHistory)
from ..timeutil import current_night, night_window, parse_date, parse_iso, utcnow
from .params import hour_arg

log = logging.getLogger(__name__)

bp = Blueprint("spots", __name__)

# Shared pool for explanation calls so a slow LLM can be abandoned after a timeout.
_explain_pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix="explain")

MAX_HISTORY_DAYS = 31


def _require_cell(cell_id: int) -> dict:
    cell = cells_repo.get(cell_id)
    if cell is None:
        raise not_found(f"Spot {cell_id} not found")
    return cell


def _local_time_label(t: datetime, tz: str) -> str:
    local = t.astimezone(ZoneInfo(tz))
    hour12 = local.hour % 12 or 12
    return f"{local:%a %b} {local.day}, {hour12}:{local:%M} {'AM' if local.hour < 12 else 'PM'}"


def _explanation(cell: dict, hour: datetime, score: dict, conditions: dict | None, astro: dict | None) -> Explanation:
    settings = current_settings()
    model_version = int(score["model_version"])
    cached = explanations_repo.get(cell["id"], hour, model_version)
    if cached:
        return Explanation(**cached)

    ctx = ExplainContext(
        cell_id=cell["id"], spot_name=cell["name"], valid_time=hour,
        local_time=_local_time_label(hour, settings.region_tz), score=float(score["score"]),
        nelm=score.get("nelm"), factors=score.get("factors") or {}, bortle=cell.get("bortle"),
        sun_alt=(astro or {}).get("sun_alt"), moon_alt=(astro or {}).get("moon_alt"),
        moon_illum=(astro or {}).get("moon_illum"),
        conditions={k: v for k, v in (conditions or {}).items() if k != "fetched_at"},
    )
    try:
        result = _explain_pool.submit(explain.explain_score, ctx).result(timeout=settings.explain_timeout_s)
    except FutureTimeout:
        log.warning("explain_score timed out for cell %s", cell["id"])
        return explain.fallback_explanation(ctx)
    except Exception as e:  # noqa: BLE001 - fall back to the template
        log.warning("explain_score failed for cell %s: %s", cell["id"], e)
        return explain.fallback_explanation(ctx)

    try:
        explanations_repo.put(cell["id"], hour, model_version, result.summary, result.tips)
    except Exception as e:  # noqa: BLE001 - caching is best-effort
        log.warning("Could not cache explanation: %s", e)
    return result


@bp.get("/spots/<int:cell_id>")
def get_spot(cell_id: int):
    cell = _require_cell(cell_id)
    hour = hour_arg()
    score = scores_repo.score_for(cell_id, hour)
    conditions = forecasts_repo.latest_for(cell_id, hour)
    astro = forecasts_repo.astro_at(hour)
    explanation = _explanation(cell, hour, score, conditions, astro) if score else None

    detail = SpotDetail(
        cell_id=cell["id"], name=cell["name"], is_curated=cell["is_curated"], lat=cell["lat"], lon=cell["lon"],
        elevation_m=cell["elevation_m"], sky_brightness_mpsas=cell["sky_brightness_mpsas"], bortle=cell["bortle"],
        valid_time=hour,
        score=score["score"] if score else None,
        label=score_label(score["score"]) if score else None,
        nelm=score["nelm"] if score else None,
        factors=score["factors"] if score else None,
        model_version=score["model_version"] if score else None,
        computed_at=score["computed_at"] if score else None,
        conditions=Conditions(**conditions) if conditions else None,
        astro=AstroSnapshot(**astro) if astro else None,
        explanation=ExplanationOut(summary=explanation.summary, tips=explanation.tips) if explanation else None,
    )
    return detail.model_dump(mode="json")


@bp.get("/spots/<int:cell_id>/history")
def get_spot_history(cell_id: int):
    settings = current_settings()
    _require_cell(cell_id)
    now = utcnow()
    start = parse_iso(request.args.get("from"), field="from") or now - timedelta(days=7)
    end = parse_iso(request.args.get("to"), field="to") or now + timedelta(hours=settings.forecast_hours)
    if start >= end:
        raise bad_request("'from' must be before 'to'")
    if end - start > timedelta(days=MAX_HISTORY_DAYS):
        raise bad_request(f"Range must be at most {MAX_HISTORY_DAYS} days")

    hourly, nightly = scores_repo.history(cell_id, start, end, settings.region_tz)
    resp = SpotHistory(
        cell_id=cell_id, from_time=start, to_time=end,
        hourly=[HistoryPoint(time=r["time"], score=r["score"], nelm=r.get("nelm")) for r in hourly],
        nightly=[NightlyBest(night=r["night"], best_score=r["best_score"], best_time=r.get("best_time")) for r in nightly],
    )
    return resp.model_dump(mode="json")


@bp.get("/spots/<int:cell_id>/drift")
def get_spot_drift(cell_id: int):
    settings = current_settings()
    _require_cell(cell_id)
    night = parse_date(request.args.get("night"), field="night") or current_night(utcnow(), settings.region_tz)
    start, end = night_window(night, settings.region_tz)
    revisions = [
        DriftRevision(
            computed_at=rev["computed_at"], model_version=rev["model_version"],
            peak_score=max(p["score"] for p in rev["points"]),
            points=[DriftPoint(valid_time=p["valid_time"], score=p["score"]) for p in rev["points"]],
        )
        for rev in scores_repo.drift(cell_id, start, end)
        if rev["points"]
    ]
    resp = SpotDrift(cell_id=cell_id, night=night, window_start=start, window_end=end, revisions=revisions)
    return resp.model_dump(mode="json")
