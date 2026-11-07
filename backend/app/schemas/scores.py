from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from .common import ApiModel, ScoreLabel


class ScoreFeatureProperties(ApiModel):
    cell_id: int
    name: str | None = None
    score: float | None
    label: ScoreLabel | None
    bortle: int | None
    top_factor: str | None
    is_curated: bool


class ScoreFeature(ApiModel):
    type: Literal["Feature"] = "Feature"
    # Grid cells: Polygon (square of GRID_STEP_DEG). Curated spots: Point.
    geometry: dict[str, Any]
    properties: ScoreFeatureProperties


class ScoresResponse(ApiModel):
    """GeoJSON FeatureCollection plus metadata. `time` is the hour the scores are valid for."""

    type: Literal["FeatureCollection"] = "FeatureCollection"
    time: datetime
    features: list[ScoreFeature]


class ScoreRangeResponse(ApiModel):
    min_time: datetime | None
    max_time: datetime | None
    now: datetime


class BestSpot(ApiModel):
    cell_id: int
    name: str | None
    is_curated: bool
    lat: float
    lon: float
    score: float
    label: ScoreLabel | None
    bortle: int | None
    valid_time: datetime  # the hour of this score (hour of the best score when ranking a whole night)
    distance_km: float | None = None


class BestResponse(ApiModel):
    time: datetime | None  # null when ranking by tonight's nightly best
    night: str | None = None  # YYYY-MM-DD when ranking by nightly best
    spots: list[BestSpot]
