from __future__ import annotations

from flask import Blueprint, request

from ..config import current_settings
from ..geo import cell_polygon, parse_bbox, parse_latlon, point
from ..repo import scores as scores_repo
from ..schemas.common import score_label, top_factor
from ..schemas.scores import (BestResponse, BestSpot, ScoreFeature, ScoreFeatureProperties, ScoreRangeResponse,
                              ScoresResponse)
from ..timeutil import current_night, floor_hour, parse_iso, utcnow
from .params import float_arg, hour_arg, int_arg

bp = Blueprint("scores", __name__)


@bp.get("/scores")
def get_scores():
    settings = current_settings()
    hour = hour_arg()
    bbox = parse_bbox(request.args.get("bbox"))
    features = []
    for r in scores_repo.scores_at(hour, bbox):
        geometry = point(r["lat"], r["lon"]) if r["is_curated"] else cell_polygon(r["lat"], r["lon"], settings.grid_step_deg)
        props = ScoreFeatureProperties(
            cell_id=r["cell_id"], name=r["name"], score=r["score"], label=score_label(r["score"]),
            bortle=r["bortle"], top_factor=top_factor(r["factors"]), is_curated=r["is_curated"],
        )
        features.append(ScoreFeature(geometry=geometry, properties=props))
    return ScoresResponse(time=hour, features=features).model_dump(mode="json")


@bp.get("/scores/range")
def get_score_range():
    now = utcnow()
    min_time, max_time = scores_repo.score_range(floor_hour(now))
    return ScoreRangeResponse(min_time=min_time, max_time=max_time, now=now).model_dump(mode="json")


@bp.get("/best")
def get_best():
    settings = current_settings()
    near = parse_latlon(request.args.get("near"))
    radius_km = float_arg("radius_km", 60.0, 0.1, 1000.0) if near else None
    limit = int_arg("limit", 5, 1, 50)
    time_param = parse_iso(request.args.get("time"))

    if time_param is not None:
        hour = floor_hour(time_param)
        rows = scores_repo.best_at(hour, near, radius_km, limit)
        night = None
    else:
        hour = None
        night = current_night(utcnow(), settings.region_tz)
        rows = scores_repo.best_for_night(night, settings.region_tz, near, radius_km, limit)

    spots = [
        BestSpot(
            cell_id=r["cell_id"], name=r["name"], is_curated=r["is_curated"], lat=r["lat"], lon=r["lon"],
            score=r["score"], label=score_label(r["score"]), bortle=r["bortle"], valid_time=r["valid_time"],
            distance_km=round(r["distance_km"], 1) if r.get("distance_km") is not None else None,
        )
        for r in rows
    ]
    return BestResponse(time=hour, night=night.isoformat() if night else None, spots=spots).model_dump(mode="json")
