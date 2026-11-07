from __future__ import annotations

from datetime import timedelta

from flask import Blueprint, request

from ..astro import ephemeris
from ..config import current_settings
from ..geo import validate_latlon
from ..repo import sky as sky_repo
from ..schemas.sky import SkyEventOut, SkyEventsResponse
from ..timeutil import current_night, local_day_window, parse_date, utcnow
from .params import float_arg

bp = Blueprint("sky", __name__)


@bp.get("/sky-events")
def get_sky_events():
    settings = current_settings()
    lat = float_arg("lat", settings.centroid_lat, -90, 90)
    lon = float_arg("lon", settings.centroid_lon, -180, 180)
    validate_latlon(lat, lon)
    night = parse_date(request.args.get("date")) or current_night(utcnow(), settings.region_tz)

    summary = ephemeris.night_summary(lat, lon, night, settings.region_tz)

    # Events for the local noon-to-noon "night" starting on `night`.
    day_start, _ = local_day_window(night, settings.region_tz)
    start, end = day_start + timedelta(hours=12), day_start + timedelta(hours=36)
    events = [SkyEventOut(time=e["time"], type=e["type"], name=e["name"], details=e["details"])
              for e in sky_repo.events_between(start, end)]

    resp = SkyEventsResponse(date=night, lat=lat, lon=lon, moon=summary.moon, twilight=summary.twilight,
                             planets=summary.planets, events=events)
    return resp.model_dump(mode="json")
