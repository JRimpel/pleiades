from __future__ import annotations

from datetime import date, datetime
from typing import Any

from .common import ApiModel


class MoonInfo(ApiModel):
    phase_deg: float  # 0 = new, 180 = full
    illumination: float  # 0..1
    phase_name: str  # e.g. "Waxing Gibbous"
    rise: datetime | None = None
    set: datetime | None = None


class Twilight(ApiModel):
    sunset: datetime | None = None
    civil_dusk: datetime | None = None
    nautical_dusk: datetime | None = None
    astronomical_dusk: datetime | None = None
    astronomical_dawn: datetime | None = None
    sunrise: datetime | None = None


class PlanetVisibility(ApiModel):
    name: str
    rise: datetime | None = None
    set: datetime | None = None
    max_alt_deg: float | None = None
    magnitude: float | None = None


class NightSummary(ApiModel):
    """Per-location summary for one night. Produced by the astro seam (AI/ML)."""

    moon: MoonInfo
    twilight: Twilight
    planets: list[PlanetVisibility]


class SkyEventOut(ApiModel):
    time: datetime
    type: str  # 'iss_pass' | 'planet' | 'meteor_shower' | 'moonrise' | ...
    name: str
    details: dict[str, Any] | None = None


class SkyEventsResponse(ApiModel):
    date: date
    lat: float
    lon: float
    moon: MoonInfo
    twilight: Twilight
    planets: list[PlanetVisibility]
    events: list[SkyEventOut]
