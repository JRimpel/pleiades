from __future__ import annotations

from datetime import date, datetime

from .common import ApiModel, ScoreLabel


class Conditions(ApiModel):
    """Raw weather for the hour, from the latest forecast revision."""

    fetched_at: datetime
    cloud_low: float | None = None
    cloud_mid: float | None = None
    cloud_high: float | None = None
    cloud_total: float | None = None
    visibility_m: float | None = None
    rh: float | None = None
    dew_point_c: float | None = None
    temp_c: float | None = None
    wind_kmh: float | None = None
    precip_prob: float | None = None


class AstroSnapshot(ApiModel):
    time: datetime
    sun_alt: float | None
    moon_alt: float | None
    moon_illum: float | None
    moon_phase_deg: float | None


class ExplanationOut(ApiModel):
    summary: str
    tips: list[str]


class SpotDetail(ApiModel):
    cell_id: int
    name: str | None
    is_curated: bool
    lat: float
    lon: float
    elevation_m: float | None
    sky_brightness_mpsas: float | None
    bortle: int | None
    valid_time: datetime
    score: float | None
    label: ScoreLabel | None
    nelm: float | None
    factors: dict[str, float] | None
    model_version: int | None
    computed_at: datetime | None
    conditions: Conditions | None
    astro: AstroSnapshot | None
    explanation: ExplanationOut | None
    # True when a score exists but its explanation must be fetched from /spots/<id>/explanation.
    explanation_pending: bool = False


class HistoryPoint(ApiModel):
    time: datetime
    score: float
    nelm: float | None = None


class NightlyBest(ApiModel):
    night: date
    best_score: float
    best_time: datetime | None = None


class SpotHistory(ApiModel):
    cell_id: int
    from_time: datetime
    to_time: datetime
    hourly: list[HistoryPoint]
    nightly: list[NightlyBest]


class DriftPoint(ApiModel):
    valid_time: datetime
    score: float


class DriftRevision(ApiModel):
    computed_at: datetime
    model_version: int
    peak_score: float
    points: list[DriftPoint]


class SpotDrift(ApiModel):
    cell_id: int
    night: date
    window_start: datetime
    window_end: datetime
    revisions: list[DriftRevision]
