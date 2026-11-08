from __future__ import annotations

from datetime import timedelta

from flask import Blueprint, request

from .. import spot_explanations
from ..config import current_settings
from ..errors import bad_request, not_found
from ..repo import cells as cells_repo
from ..repo import forecasts as forecasts_repo
from ..repo import scores as scores_repo
from ..schemas.common import score_label
from ..schemas.spots import (AstroSnapshot, Conditions, DriftPoint, DriftRevision, ExplanationOut, HistoryPoint,
                             NightlyBest, SpotDetail, SpotDrift, SpotHistory)
from ..timeutil import current_night, night_window, parse_date, parse_iso, utcnow
from .params import hour_arg

bp = Blueprint("spots", __name__)

MAX_HISTORY_DAYS = 31


def _require_cell(cell_id: int) -> dict:
    cell = cells_repo.get(cell_id)
    if cell is None:
        raise not_found(f"Spot {cell_id} not found")
    return cell


@bp.get("/spots/<int:cell_id>")
def get_spot(cell_id: int):
    """Spot detail from the database only. A not-yet-generated explanation is left to
    `/spots/<id>/explanation` (`explanation_pending`), so this never waits on Gemini."""
    cell = _require_cell(cell_id)
    hour = hour_arg()
    score = scores_repo.score_for(cell_id, hour)
    conditions = forecasts_repo.latest_for(cell_id, hour)
    astro = forecasts_repo.astro_at(hour)
    explanation = spot_explanations.ready(cell, hour, score, conditions, astro) if score else None

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
        explanation_pending=score is not None and explanation is None,
    )
    return detail.model_dump(mode="json")


@bp.get("/spots/<int:cell_id>/explanation")
def get_spot_explanation(cell_id: int):
    """Plain-language explanation of one cell-hour's score (Gemini, bounded by EXPLAIN_TIMEOUT_S)."""
    cell = _require_cell(cell_id)
    hour = hour_arg()
    score = scores_repo.score_for(cell_id, hour)
    if score is None:
        raise not_found(f"Spot {cell_id} has no score at {hour.isoformat()}")
    conditions = forecasts_repo.latest_for(cell_id, hour)
    astro = forecasts_repo.astro_at(hour)
    result = spot_explanations.get_or_generate(cell, hour, score, conditions, astro)
    return ExplanationOut(summary=result.summary, tips=result.tips).model_dump(mode="json")


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
