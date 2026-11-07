"""Ephemeris, sky events, and visible-object lists.

OWNER: AI/ML (role C) — replace function bodies with skyfield, keep signatures.

PLACEHOLDER: low-precision analytic approximations (sun within ~1°, moon very rough)
so the backend runs without skyfield/de421.bsp.
"""
from __future__ import annotations

import math
from datetime import date, datetime, timedelta, timezone

from .types import AstroHour, CandidateObject, MoonInfo, NightSummary, SkyEventRecord, Twilight

_UTC = timezone.utc
_SYNODIC_DAYS = 29.530588853
_KNOWN_NEW_MOON = datetime(2000, 1, 6, 18, 14, tzinfo=_UTC)


def _sun_alt(when: datetime, lat: float, lon: float) -> float:
    when = when.astimezone(_UTC)
    doy = when.timetuple().tm_yday
    hour = when.hour + when.minute / 60 + when.second / 3600
    g = 2 * math.pi / 365 * (doy - 1 + (hour - 12) / 24)
    decl = (0.006918 - 0.399912 * math.cos(g) + 0.070257 * math.sin(g) - 0.006758 * math.cos(2 * g)
            + 0.000907 * math.sin(2 * g) - 0.002697 * math.cos(3 * g) + 0.00148 * math.sin(3 * g))
    eqtime = 229.18 * (0.000075 + 0.001868 * math.cos(g) - 0.032077 * math.sin(g)
                       - 0.014615 * math.cos(2 * g) - 0.040849 * math.sin(2 * g))
    tst = hour * 60 + eqtime + 4 * lon
    ha = math.radians(tst / 4 - 180)
    phi = math.radians(lat)
    sin_alt = math.sin(phi) * math.sin(decl) + math.cos(phi) * math.cos(decl) * math.cos(ha)
    return math.degrees(math.asin(max(-1.0, min(1.0, sin_alt))))


def _moon_phase_deg(when: datetime) -> float:
    days = (when - _KNOWN_NEW_MOON).total_seconds() / 86400.0
    return (days % _SYNODIC_DAYS) / _SYNODIC_DAYS * 360.0


def _moon_alt(when: datetime, lat: float, lon: float) -> float:
    # The moon trails the sun by its phase angle in hour angle; declination ignored (placeholder).
    lag_hours = _moon_phase_deg(when) / 15.0
    utc = when.astimezone(_UTC)
    hour = (utc.hour + utc.minute / 60) - lag_hours
    ha = math.radians((hour * 15 + lon) - 180)
    sin_alt = math.cos(math.radians(lat)) * math.cos(ha)
    return math.degrees(math.asin(max(-1.0, min(1.0, sin_alt))))


def _illum(phase_deg: float) -> float:
    return (1 - math.cos(math.radians(phase_deg))) / 2


def _phase_name(phase_deg: float) -> str:
    names = ["New Moon", "Waxing Crescent", "First Quarter", "Waxing Gibbous",
             "Full Moon", "Waning Gibbous", "Last Quarter", "Waning Crescent"]
    return names[int(((phase_deg + 22.5) % 360) // 45)]


def hourly_conditions(start: datetime, hours: int, lat: float, lon: float) -> list[AstroHour]:
    """Sun/moon state for each hour in [start, start + hours) at (lat, lon). `start` is on the hour (UTC)."""
    out: list[AstroHour] = []
    for i in range(hours):
        t = start + timedelta(hours=i)
        phase = _moon_phase_deg(t)
        out.append(AstroHour(
            time=t,
            sun_alt=round(_sun_alt(t, lat, lon), 2),
            moon_alt=round(_moon_alt(t, lat, lon), 2),
            moon_illum=round(_illum(phase), 3),
            moon_phase_deg=round(phase, 1),
        ))
    return out


# Approximate peak dates (month, day) for major showers.
_SHOWERS = [
    ("Quadrantids", 1, 3, 120), ("Lyrids", 4, 22, 18), ("Eta Aquariids", 5, 6, 50),
    ("Perseids", 8, 12, 100), ("Orionids", 10, 21, 20), ("Southern Taurids", 11, 5, 5),
    ("Northern Taurids", 11, 12, 5), ("Leonids", 11, 17, 15), ("Geminids", 12, 14, 150),
]


def sky_events(start: datetime, end: datetime, lat: float, lon: float) -> list[SkyEventRecord]:
    """Events in [start, end): planet visibility, ISS passes, meteor-shower peaks, moonrise/set."""
    out: list[SkyEventRecord] = []
    for year in {start.year, end.year}:
        for name, month, day, zhr in _SHOWERS:
            peak = datetime(year, month, day, 6, 0, tzinfo=_UTC)
            if start <= peak < end:
                out.append(SkyEventRecord(time=peak, type="meteor_shower", name=name,
                                          details={"zhr": zhr, "peak": True}))
    return out


def night_summary(lat: float, lon: float, night: date, tz: str) -> NightSummary:
    """Moon, twilight times, and planet visibility for the night starting on local date `night`."""
    from zoneinfo import ZoneInfo

    local_noon = datetime(night.year, night.month, night.day, 12, tzinfo=ZoneInfo(tz)).astimezone(_UTC)
    samples = [local_noon + timedelta(minutes=5 * i) for i in range(24 * 12 + 1)]
    alts = [_sun_alt(t, lat, lon) for t in samples]

    def crossing(threshold: float, falling: bool) -> datetime | None:
        for i in range(1, len(alts)):
            a, b = alts[i - 1], alts[i]
            if (falling and a > threshold >= b) or (not falling and a < threshold <= b):
                return samples[i]
        return None

    midnight = local_noon + timedelta(hours=12)
    phase = _moon_phase_deg(midnight)
    return NightSummary(
        moon=MoonInfo(phase_deg=round(phase, 1), illumination=round(_illum(phase), 3), phase_name=_phase_name(phase)),
        twilight=Twilight(
            sunset=crossing(-0.833, True), civil_dusk=crossing(-6, True), nautical_dusk=crossing(-12, True),
            astronomical_dusk=crossing(-18, True), astronomical_dawn=crossing(-18, False), sunrise=crossing(-0.833, False),
        ),
        planets=[],
    )


def visible_objects(lat: float, lon: float, when: datetime) -> list[CandidateObject]:
    """Objects above the horizon at (lat, lon, when), used as grounding candidates for vision."""
    out: list[CandidateObject] = []
    moon_alt = _moon_alt(when, lat, lon)
    if moon_alt > 0:
        out.append(CandidateObject(name="Moon", type="moon", alt_deg=round(moon_alt, 1), az_deg=0.0, magnitude=-10.0))
    return out
