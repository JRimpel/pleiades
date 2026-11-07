"""Contract between the backend and the astro (skyfield) module. OWNER: shared."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel

from ..schemas.sky import MoonInfo, NightSummary, PlanetVisibility, Twilight  # re-exported

__all__ = ["AstroHour", "SkyEventRecord", "CandidateObject", "MoonInfo", "NightSummary", "PlanetVisibility", "Twilight"]


class AstroHour(BaseModel):
    """One row of `astro_conditions` (region centroid)."""

    time: datetime  # UTC, on the hour
    sun_alt: float
    moon_alt: float
    moon_illum: float  # 0..1
    moon_phase_deg: float  # 0 = new, 180 = full


class SkyEventRecord(BaseModel):
    """One row of `sky_events`."""

    time: datetime
    type: str  # 'iss_pass' | 'planet' | 'meteor_shower' | 'moonrise' | 'moonset' | ...
    name: str
    details: dict[str, Any] | None = None


class CandidateObject(BaseModel):
    """An object above the horizon at a photo's time/place; used to ground the vision model."""

    name: str
    type: str  # 'planet' | 'moon' | 'star' | 'constellation' | 'cluster' | ...
    alt_deg: float
    az_deg: float
    magnitude: float | None = None
