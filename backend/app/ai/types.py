"""Contract between the backend and the Gemini modules. OWNER: shared."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from ..astro.types import CandidateObject


class VisionContext(BaseModel):
    lat: float
    lon: float
    taken_at: datetime
    candidates: list[CandidateObject]  # objects above the horizon (ephemeris grounding)
    caption: str | None = None


class VisionObject(BaseModel):
    name: str
    type: str
    confidence: float = Field(ge=0, le=1)


class VisionResult(BaseModel):
    is_night_sky: bool
    description: str
    objects: list[VisionObject]
    milky_way_visible: bool
    sky_quality: int = Field(ge=1, le=10)
    light_pollution_notes: str | None = None


class ExplainContext(BaseModel):
    cell_id: int
    spot_name: str | None
    valid_time: datetime
    local_time: str  # e.g. "Sat Nov 7, 11:00 PM"
    score: float
    nelm: float | None
    factors: dict[str, float]
    bortle: int | None
    sun_alt: float | None = None
    moon_alt: float | None = None
    moon_illum: float | None = None
    conditions: dict[str, Any] = Field(default_factory=dict)
    visible_planets: list[str] = Field(default_factory=list)


class Explanation(BaseModel):
    summary: str
    tips: list[str]
