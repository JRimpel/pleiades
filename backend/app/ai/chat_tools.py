"""OWNER: AI/ML. Tools the chat assistant can call. Each wraps the same repo/ephemeris code the REST API
uses, so the assistant answers from the data the map shows. Results are small JSON-able dicts with local
times already formatted, so the model never has to convert time zones.
"""
from __future__ import annotations

import json
import logging
import math
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable
from uuid import UUID
from zoneinfo import ZoneInfo

import requests
from google.genai import types

from ..astro import ephemeris
from ..config import Settings
from ..geo import WNY_BBOX, BBox
from ..repo import cells as cells_repo
from ..repo import forecasts as forecasts_repo
from ..repo import photos as photos_repo
from ..repo import scores as scores_repo
from ..repo import sky as sky_repo
from ..schemas.chat import ChatContext, ChatPhoto, ChatSpot
from ..schemas.common import score_label
from ..storage import s3
from ..timeutil import current_night, ensure_utc, floor_hour, night_window, utcnow

log = logging.getLogger(__name__)

GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"
GEOCODE_TIMEOUT_S = 4.0
# Places the geocoder returns must fall near the scored region (WNY plus a margin).
_W, _S, _E, _N = WNY_BBOX
GEOCODE_BOUNDS = (_W - 1.5, _S - 1.0, _E + 1.5, _N + 1.0)
VISIBLE_ALT_DEG = 20.0
_TOWNS_PATH = Path(__file__).resolve().parents[1] / "data" / "wny_towns.json"
_COMPASS = ("N", "NE", "E", "SE", "S", "SW", "W", "NW")
# Common names for catalog objects (ephemeris names are the values).
_ALIASES = {"big dipper": "Ursa Major", "great bear": "Ursa Major", "seven sisters": "Pleiades", "m45": "Pleiades",
            "andromeda": "Andromeda Galaxy", "m31": "Andromeda Galaxy", "m42": "Orion Nebula",
            "north star": "Polaris", "pole star": "Polaris", "orion's belt": "Alnilam", "the moon": "Moon"}


class ToolError(Exception):
    """A tool was called with unusable arguments; the message goes back to the model."""


@dataclass
class ToolState:
    """Per-request state: the user's app context and what the tools found (for the map)."""

    settings: Settings
    context: ChatContext
    spots: dict[int, ChatSpot] = field(default_factory=dict)
    photos: dict[UUID, ChatPhoto] = field(default_factory=dict)

    @property
    def zone(self) -> ZoneInfo:
        return ZoneInfo(self.settings.region_tz)

    def local(self, dt: datetime | None) -> str | None:
        if dt is None:
            return None
        t = ensure_utc(dt).astimezone(self.zone)
        return f"{t:%a %b} {t.day}, {t.hour % 12 or 12}:{t:%M %p}"  # portable: no %-d / %-I

    def add_spot(self, cell_id: int, name: str | None, lat: float, lon: float, score: float | None = None,
                 valid_time: datetime | None = None) -> None:
        existing = self.spots.get(cell_id)
        if existing is not None and score is None:
            return
        self.spots[cell_id] = ChatSpot(cell_id=cell_id, name=name, lat=lat, lon=lon,
                                       score=round(score, 1) if score is not None else None,
                                       label=score_label(score), valid_time=valid_time)


# ---- helpers -----------------------------------------------------------------------------

@lru_cache(maxsize=1)
def _towns() -> list[tuple[str, float, float]]:
    return [tuple(t) for t in json.loads(_TOWNS_PATH.read_text(encoding="utf-8"))]


def _km(a_lat: float, a_lon: float, b_lat: float, b_lon: float) -> float:
    p1, p2 = math.radians(a_lat), math.radians(b_lat)
    dp, dl = p2 - p1, math.radians(b_lon - a_lon)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * 6371.0088 * math.asin(math.sqrt(h))


def describe_location(lat: float, lon: float) -> str:
    """'5 mi SW of Naples', matching the frontend's naming of unnamed grid cells."""
    name, t_lat, t_lon = min(_towns(), key=lambda t: _km(t[1], t[2], lat, lon))
    miles = _km(t_lat, t_lon, lat, lon) / 1.609344
    if miles < 1:
        return f"In {name}"
    y = math.sin(math.radians(lon - t_lon)) * math.cos(math.radians(lat))
    x = (math.cos(math.radians(t_lat)) * math.sin(math.radians(lat))
         - math.sin(math.radians(t_lat)) * math.cos(math.radians(lat)) * math.cos(math.radians(lon - t_lon)))
    bearing = (math.degrees(math.atan2(y, x)) + 360) % 360
    return f"{round(miles)} mi {_COMPASS[round(bearing / 45) % 8]} of {name}"


def _spot_name(name: str | None, lat: float, lon: float) -> str:
    """The display name the map uses: a curated spot's name, or e.g. '3 mi E of Alexander'."""
    return name or describe_location(lat, lon)


def _resolve_time(state: ToolState, value: Any) -> datetime | None:
    """A model-supplied hour. Naive values are local to the region (the model speaks local time)."""
    if value in (None, ""):
        return None
    try:
        dt = datetime.fromisoformat(str(value).strip().replace("Z", "+00:00"))
    except ValueError as e:
        raise ToolError(f"time must be ISO-8601, got {value!r}") from e
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=state.zone)
    return floor_hour(ensure_utc(dt))


def _parse_date(value: Any) -> date | None:
    if value in (None, ""):
        return None
    try:
        return date.fromisoformat(str(value).strip()[:10])
    except ValueError as e:
        raise ToolError(f"date must be YYYY-MM-DD, got {value!r}") from e


def _night(state: ToolState, value: Any) -> date:
    return _parse_date(value) or current_night(utcnow(), state.settings.region_tz)


def _num(args: dict, key: str, lo: float, hi: float) -> float | None:
    raw = args.get(key)
    if raw is None:
        return None
    try:
        value = float(raw)
    except (TypeError, ValueError) as e:
        raise ToolError(f"{key} must be a number") from e
    if not lo <= value <= hi:
        raise ToolError(f"{key} must be between {lo} and {hi}")
    return value


def _near(state: ToolState, args: dict) -> tuple[float, float] | None:
    lat, lon = _num(args, "lat", -90, 90), _num(args, "lon", -180, 180)
    if (lat is None) != (lon is None):
        raise ToolError("give both lat and lon, or neither")
    return (lat, lon) if lat is not None else None


def _observer(state: ToolState, args: dict) -> tuple[float, float]:
    near = _near(state, args)
    if near:
        return near
    if state.context.location:
        return state.context.location.lat, state.context.location.lon
    return state.settings.centroid_lat, state.settings.centroid_lon


# ---- tools -------------------------------------------------------------------------------

def find_place(state: ToolState, args: dict) -> dict:
    name = str(args.get("name") or "").strip()
    if not 2 <= len(name) <= 80:
        raise ToolError("name must be 2-80 characters")
    matches = []
    for cell in cells_repo.find_by_name(name):
        state.add_spot(cell["id"], cell["name"], cell["lat"], cell["lon"])
        matches.append({"name": cell["name"], "lat": round(cell["lat"], 4), "lon": round(cell["lon"], 4),
                        "cell_id": cell["id"], "is_curated_spot": cell["is_curated"], "bortle": cell["bortle"],
                        "source": "pleiades spot"})
    if matches:
        return {"matches": matches}

    key = name.lower().removesuffix(", ny").removesuffix(" ny").strip()
    towns = [t for t in _towns() if t[0].lower() == key] or [t for t in _towns() if t[0].lower().startswith(key)]
    places = [{"name": t[0], "lat": t[1], "lon": t[2], "source": "town list"} for t in towns[:3]]
    if not places:
        places = _geocode(name)
    for place in places:
        place["nearest_cell_id"] = cells_repo.nearest_cell(place["lat"], place["lon"])
    if not places:
        return {"matches": [], "note": f"No place called {name!r} was found in or near Western New York."}
    return {"matches": places}


def _geocode(name: str) -> list[dict]:
    try:
        resp = requests.get(GEOCODE_URL, params={"name": name, "count": 10, "language": "en", "format": "json"},
                            timeout=GEOCODE_TIMEOUT_S)
        resp.raise_for_status()
        results = resp.json().get("results") or []
    except (requests.RequestException, ValueError) as e:
        log.warning("chat geocode failed for %r: %s", name, e)
        return []
    w, s, e, n = GEOCODE_BOUNDS
    out = []
    for r in results:
        lat, lon = r.get("latitude"), r.get("longitude")
        if lat is None or lon is None or not (w <= lon <= e and s <= lat <= n):
            continue
        label = ", ".join(x for x in (r.get("name"), r.get("admin1")) if x)
        out.append({"name": label, "lat": round(lat, 4), "lon": round(lon, 4), "source": "geocoder"})
        if len(out) == 3:
            break
    return out


def best_spots(state: ToolState, args: dict) -> dict:
    near = _near(state, args)
    radius = _num(args, "radius_km", 1, 400) or (60.0 if near else None)
    limit = int(_num(args, "limit", 1, 8) or 5)
    hour = _resolve_time(state, args.get("time"))
    if hour is not None:
        rows = scores_repo.best_at(hour, near, radius, limit)
        scope = f"the hour starting {state.local(hour)}"
    else:
        night = _night(state, args.get("night"))
        rows = scores_repo.best_for_night(night, state.settings.region_tz, near, radius, limit)
        scope = f"each spot's best hour on the night of {night.isoformat()}"
    spots = []
    for r in rows:
        state.add_spot(r["cell_id"], r["name"], r["lat"], r["lon"], r["score"], r["valid_time"])
        spots.append({
            "cell_id": r["cell_id"], "name": _spot_name(r["name"], r["lat"], r["lon"]),
            "is_curated_spot": r["is_curated"], "score": round(r["score"], 1), "label": score_label(r["score"]),
            "best_time_local": state.local(r["valid_time"]), "bortle": r["bortle"],
            "distance_km": round(r["distance_km"], 1) if r.get("distance_km") is not None else None,
        })
    result: dict[str, Any] = {"ranked_by": scope, "spots": spots}
    if not spots:
        result["note"] = "No scores exist for that time or area (the forecast covers about the next 72 hours)."
    return result


def spot_conditions(state: ToolState, args: dict) -> dict:
    try:
        cell_id = int(args.get("cell_id"))
    except (TypeError, ValueError) as e:
        raise ToolError("cell_id must be an integer") from e
    cell = cells_repo.get(cell_id)
    if cell is None:
        raise ToolError(f"no spot with cell_id {cell_id}")
    explicit = _resolve_time(state, args.get("time"))
    hour = explicit or floor_hour(state.context.time or utcnow())
    score = scores_repo.score_for(cell_id, hour)
    cond = forecasts_repo.latest_for(cell_id, hour)
    astro = forecasts_repo.astro_at(hour)

    night = current_night(hour, state.settings.region_tz)
    start, end = night_window(night, state.settings.region_tz)
    hourly, _ = scores_repo.history(cell_id, start, end, state.settings.region_tz)
    # The map chip shows the asked-for hour, or else tonight's best hour (what "is tonight good?" means).
    best = max(hourly, key=lambda r: r["score"]) if hourly and explicit is None else None
    if best is not None:
        state.add_spot(cell_id, cell["name"], cell["lat"], cell["lon"], best["score"], best["time"])
    else:
        state.add_spot(cell_id, cell["name"], cell["lat"], cell["lon"], score["score"] if score else None,
                       hour if score else None)

    result: dict[str, Any] = {
        "cell_id": cell_id, "name": _spot_name(cell["name"], cell["lat"], cell["lon"]),
        "is_curated_spot": cell["is_curated"], "bortle": cell["bortle"], "elevation_m": cell["elevation_m"],
        "sky_brightness_mpsas": cell["sky_brightness_mpsas"], "hour_local": state.local(hour),
        "score": round(score["score"], 1) if score else None,
        "label": score_label(score["score"]) if score else None,
        "nelm_estimate": score["nelm"] if score else None,
        "factor_points": score["factors"] if score else None,
        "tonight_hourly_scores": [{"local": state.local(r["time"]), "score": round(r["score"], 1)} for r in hourly],
    }
    if cond:
        result["weather"] = {k: cond[k] for k in ("cloud_total", "cloud_low", "cloud_mid", "cloud_high",
                                                  "visibility_m", "rh", "temp_c", "wind_kmh", "precip_prob")}
    if astro:
        result["astro"] = {"sun_alt_deg": astro["sun_alt"], "moon_alt_deg": astro["moon_alt"],
                           "moon_illumination": astro["moon_illum"]}
    if score is None:
        result["note"] = "No score for this hour; the forecast covers about the next 72 hours."
    return result


def when_visible(state: ToolState, args: dict) -> dict:
    name = str(args.get("object_name") or "").strip()
    if not name:
        raise ToolError("object_name is required")
    lat, lon = _observer(state, args)
    night = _night(state, args.get("night"))
    start, end = night_window(night, state.settings.region_tz)
    summary = ephemeris.night_summary(lat, lon, night, state.settings.region_tz)

    # Sample every hour of the night; each sample lists the catalog objects above the horizon.
    samples = []
    t = start
    while t <= end:
        samples.append((t, {obj.name: obj for obj in ephemeris.visible_objects(lat, lon, t)}))
        t += timedelta(hours=1)
    known = sorted({n for _, objs in samples for n in objs})
    key = name.lower().removeprefix("the ").strip()
    key = _ALIASES.get(key, key).lower()
    matched = (next((n for n in known if n.lower() == key), None)
               or next((n for n in known if key in n.lower()), None))
    hours = [{"local": state.local(t), "alt_deg": round(objs[matched].alt_deg),
              "direction": _COMPASS[round(objs[matched].az_deg / 45) % 8]}
             for t, objs in samples if matched in objs]
    if matched is None:
        return {"found": False, "note": f"{name!r} is not in the catalog or never rises above the horizon that night.",
                "catalog_objects_up_that_night": sorted(known)}
    good = [h for h in hours if h["alt_deg"] >= VISIBLE_ALT_DEG]
    return {
        "found": True, "object": matched, "night": night.isoformat(),
        "observer": {"lat": round(lat, 3), "lon": round(lon, 3)},
        "hours_above_horizon": hours,
        "first_hour_above_20deg": good[0]["local"] if good else None,
        "last_hour_above_20deg": good[-1]["local"] if good else None,
        "astronomical_dusk": state.local(summary.twilight.astronomical_dusk),
        "astronomical_dawn": state.local(summary.twilight.astronomical_dawn),
        "note": "Altitudes are for 6 PM-6 AM local; only hours with the Sun below the horizon are useful.",
    }


def sky_tonight(state: ToolState, args: dict) -> dict:
    lat, lon = _observer(state, args)
    night = _night(state, args.get("night"))
    summary = ephemeris.night_summary(lat, lon, night, state.settings.region_tz)
    start, end = night_window(night, state.settings.region_tz)
    tw = summary.twilight
    events = sky_repo.events_between(start - timedelta(hours=6), end + timedelta(hours=6))
    return {
        "night": night.isoformat(),
        "moon": {"phase": summary.moon.phase_name, "illumination_pct": round(summary.moon.illumination * 100),
                 "rise": state.local(summary.moon.rise), "set": state.local(summary.moon.set)},
        "twilight": {"sunset": state.local(tw.sunset), "astronomical_dusk": state.local(tw.astronomical_dusk),
                     "astronomical_dawn": state.local(tw.astronomical_dawn), "sunrise": state.local(tw.sunrise)},
        "planets": [{"name": p.name, "rise": state.local(p.rise), "set": state.local(p.set),
                     "max_alt_deg": p.max_alt_deg} for p in summary.planets],
        "events": [{"name": e["name"], "type": e["type"], "local": state.local(e["time"]),
                    "details": e.get("details")} for e in events][:10],
    }


def search_photos(state: ToolState, args: dict) -> dict:
    near = _near(state, args)
    radius = _num(args, "radius_km", 1, 400) or (25.0 if near else None)
    days = _num(args, "days", 1, 3650)
    limit = int(_num(args, "limit", 1, 6) or 4)
    bbox = None
    if args.get("in_view") and state.context.viewport:
        v = state.context.viewport
        bbox = BBox(v.west, v.south, v.east, v.north)
    rows = photos_repo.search(bbox=bbox, near=near, radius_km=radius,
                              object_name=(str(args.get("object_name") or "").strip() or None),
                              since=utcnow() - timedelta(days=days) if days else None, limit=limit)
    photos = []
    for r in rows:
        objects = [o["name"] for o in (r["ai_objects"] or []) if isinstance(o, dict) and o.get("name")]
        description = (r["ai_description"] or "")[:300] or None
        state.photos[r["id"]] = ChatPhoto(
            id=r["id"], lat=r["lat"], lon=r["lon"], thumb_url=s3.object_url(r["thumb_key"]),
            taken_at=r["taken_at"], description=description, objects=objects,
        )
        photos.append({
            "photo_id": str(r["id"]), "place": describe_location(r["lat"], r["lon"]),
            "taken_local": state.local(r["taken_at"]), "caption": r["caption"], "ai_description": description,
            "identified_objects": objects, "ai_sky_quality_1to10": r["ai_sky_quality"],
            "milky_way_visible": r["ai_milky_way_visible"],
            "pleiades_score_at_capture": r["score_at_capture"], "votes": r["vote_count"],
        })
    result: dict[str, Any] = {"photos": photos}
    if not photos:
        result["note"] = "No analyzed community photos match."
    return result


# ---- registry ----------------------------------------------------------------------------

_S = types.Schema
_T = types.Type
_STR, _NUM, _INT, _BOOL = _S(type=_T.STRING), _S(type=_T.NUMBER), _S(type=_T.INTEGER), _S(type=_T.BOOLEAN)


def _obj(props: dict[str, types.Schema], required: list[str] | None = None) -> types.Schema:
    return _S(type=_T.OBJECT, properties=props, required=required or [])


def _desc(schema: types.Schema, text: str) -> types.Schema:
    return schema.model_copy(update={"description": text})


_LAT = _desc(_NUM, "Latitude (decimal degrees).")
_LON = _desc(_NUM, "Longitude (decimal degrees).")
_TIME = _desc(_STR, "Local hour as ISO-8601 without offset, e.g. 2026-11-08T23:00. Omit for the default.")
_NIGHT = _desc(_STR, "Local date the night starts on, YYYY-MM-DD. Omit for tonight.")

DECLARATIONS = [
    types.FunctionDeclaration(
        name="find_place",
        description="Resolve a place name (park, spot, town, landmark) in Western New York to coordinates and, "
                    "for Pleiades spots, a cell_id. Call this before using a place the user names.",
        parameters=_obj({"name": _desc(_STR, "The place name, e.g. 'Letchworth' or 'Ellicottville'.")}, ["name"]),
    ),
    types.FunctionDeclaration(
        name="best_spots",
        description="Top-scoring stargazing spots from the Pleiades forecast. Without time, ranks each spot by "
                    "its best hour of the night. With lat/lon, limits to a radius around that point.",
        parameters=_obj({"time": _TIME, "night": _NIGHT, "lat": _LAT, "lon": _LON,
                         "radius_km": _desc(_NUM, "Search radius around lat/lon (default 60)."),
                         "limit": _desc(_INT, "1-8, default 5.")}),
    ),
    types.FunctionDeclaration(
        name="spot_conditions",
        description="Score, factor breakdown, weather, and tonight's hourly scores for one spot (cell_id).",
        parameters=_obj({"cell_id": _desc(_INT, "Spot id from find_place, best_spots or the app context."),
                         "time": _TIME}, ["cell_id"]),
    ),
    types.FunctionDeclaration(
        name="when_visible",
        description="Hour-by-hour altitude and direction of a sky object (constellation, bright star, planet, "
                    "Moon, Pleiades, Andromeda Galaxy, Orion Nebula) through the night.",
        parameters=_obj({"object_name": _desc(_STR, "e.g. 'Orion', 'Jupiter', 'Vega'."), "night": _NIGHT,
                         "lat": _LAT, "lon": _LON}, ["object_name"]),
    ),
    types.FunctionDeclaration(
        name="sky_tonight",
        description="Moon phase and rise/set, twilight times, visible planets and sky events (meteor showers) "
                    "for a night.",
        parameters=_obj({"night": _NIGHT, "lat": _LAT, "lon": _LON}),
    ),
    types.FunctionDeclaration(
        name="search_photos",
        description="Community night-sky photos with their AI analysis. Filter by an identified object, by "
                    "distance from a point, by the user's current map view, or by recency.",
        parameters=_obj({"object_name": _desc(_STR, "Identified object, e.g. 'Orion' or 'Moon'."),
                         "lat": _LAT, "lon": _LON, "radius_km": _desc(_NUM, "Default 25."),
                         "in_view": _desc(_BOOL, "Only photos inside the user's current map view."),
                         "days": _desc(_NUM, "Only photos from the last N days."),
                         "limit": _desc(_INT, "1-6, default 4.")}),
    ),
]

TOOLS: dict[str, Callable[[ToolState, dict], dict]] = {
    "find_place": find_place, "best_spots": best_spots, "spot_conditions": spot_conditions,
    "when_visible": when_visible, "sky_tonight": sky_tonight, "search_photos": search_photos,
}


def dispatch(state: ToolState, name: str, args: dict | None) -> dict:
    """Run one tool. Bad arguments and data errors come back as {'error': ...} so the model can recover."""
    fn = TOOLS.get(name)
    if fn is None:
        return {"error": f"unknown tool {name!r}"}
    try:
        return _jsonable(fn(state, dict(args or {})))
    except ToolError as e:
        return {"error": str(e)}
    except Exception as e:  # noqa: BLE001 - one failing tool shouldn't sink the whole answer
        log.exception("chat tool %s failed", name)
        return {"error": f"{name} is temporarily unavailable ({type(e).__name__})"}


def _jsonable(value: Any) -> Any:
    return json.loads(json.dumps(value, default=str, allow_nan=False))
