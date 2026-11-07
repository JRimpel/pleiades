"""Open-Meteo client: batched multi-location hourly forecasts and elevations."""
from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Any, Iterator, Sequence, TypeVar

import requests

log = logging.getLogger(__name__)

FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
ELEVATION_URL = "https://api.open-meteo.com/v1/elevation"

# Order matters: maps 1:1 onto weather_forecast columns after (valid_time, cell_id, fetched_at).
HOURLY_VARS: tuple[str, ...] = (
    "cloud_cover_low",
    "cloud_cover_mid",
    "cloud_cover_high",
    "cloud_cover",
    "visibility",
    "relative_humidity_2m",
    "dew_point_2m",
    "temperature_2m",
    "wind_speed_10m",
    "precipitation_probability",
)

WEATHER_COLUMNS: tuple[str, ...] = (
    "valid_time", "cell_id", "fetched_at",
    "cloud_low", "cloud_mid", "cloud_high", "cloud_total",
    "visibility_m", "rh", "dew_point_c", "temp_c", "wind_kmh", "precip_prob",
)

BATCH_SIZE = 50
ELEVATION_BATCH_SIZE = 100
MAX_ATTEMPTS = 4
BACKOFF_BASE_S = 1.0
TIMEOUT_S = 30

T = TypeVar("T")


class OpenMeteoError(RuntimeError):
    pass


def chunks(seq: Sequence[T], size: int = BATCH_SIZE) -> Iterator[Sequence[T]]:
    if size <= 0:
        raise ValueError("size must be positive")
    for i in range(0, len(seq), size):
        yield seq[i:i + size]


def _fmt(values: Sequence[float]) -> str:
    return ",".join(f"{v:.4f}" for v in values)


def _get_json(session: requests.Session, url: str, params: dict[str, Any],
              *, sleep=time.sleep) -> Any:
    """GET with retries + exponential backoff on 429, 5xx and connection errors."""
    last_err: Exception | None = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            resp = session.get(url, params=params, timeout=TIMEOUT_S)
        except (requests.ConnectionError, requests.Timeout) as e:
            last_err = e
            log.warning("Open-Meteo connection error (attempt %d/%d): %s", attempt, MAX_ATTEMPTS, e)
        else:
            if resp.status_code == 200:
                return resp.json()
            if resp.status_code == 429 or resp.status_code >= 500:
                last_err = OpenMeteoError(f"HTTP {resp.status_code}: {resp.text[:200]}")
                log.warning("Open-Meteo HTTP %d (attempt %d/%d)", resp.status_code, attempt, MAX_ATTEMPTS)
            else:
                raise OpenMeteoError(f"HTTP {resp.status_code}: {resp.text[:500]}")
        if attempt < MAX_ATTEMPTS:
            sleep(BACKOFF_BASE_S * 2 ** (attempt - 1))
    raise OpenMeteoError(f"Open-Meteo request failed after {MAX_ATTEMPTS} attempts: {last_err}")


def normalize(payload: Any) -> list[dict[str, Any]]:
    """Multi-location responses are a JSON list; single-location responses are a dict."""
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        return [payload]
    raise OpenMeteoError(f"Unexpected Open-Meteo payload type: {type(payload).__name__}")


def fetch_batch(coords: Sequence[tuple[float, float]], forecast_hours: int,
                session: requests.Session | None = None, *, sleep=time.sleep) -> list[dict[str, Any]]:
    """Hourly forecast for up to ~50 (lat, lon) pairs in one request. Returns one dict per location."""
    session = session or requests.Session()
    params = {
        "latitude": _fmt([c[0] for c in coords]),
        "longitude": _fmt([c[1] for c in coords]),
        "hourly": ",".join(HOURLY_VARS),
        "timezone": "UTC",
        "timeformat": "unixtime",
        "wind_speed_unit": "kmh",
        "forecast_hours": forecast_hours,
    }
    locations = normalize(_get_json(session, FORECAST_URL, params, sleep=sleep))
    if len(locations) != len(coords):
        raise OpenMeteoError(f"Expected {len(coords)} locations, got {len(locations)}")
    return locations


def _num(values: list[Any] | None, i: int) -> float | None:
    if values is None or i >= len(values):
        return None
    v = values[i]
    return None if v is None else float(v)


def parse_response(payload: Any, cell_ids: Sequence[int], fetched_at: datetime) -> list[tuple]:
    """Convert a (multi-)location response into weather_forecast rows (WEATHER_COLUMNS order).

    `cell_ids[k]` is the cell for location k. Missing variables/values become None.
    """
    locations = normalize(payload)
    if len(locations) != len(cell_ids):
        raise OpenMeteoError(f"Got {len(locations)} locations for {len(cell_ids)} cells")
    rows: list[tuple] = []
    for cell_id, loc in zip(cell_ids, locations):
        hourly = loc.get("hourly") or {}
        times = hourly.get("time") or []
        series = [hourly.get(var) for var in HOURLY_VARS]
        for i, t in enumerate(times):
            if isinstance(t, (int, float)):
                valid_time = datetime.fromtimestamp(int(t), tz=timezone.utc)
            else:  # ISO string (if timeformat=iso8601 was used)
                valid_time = datetime.fromisoformat(str(t)).replace(tzinfo=timezone.utc)
            rows.append((valid_time, int(cell_id), fetched_at, *(_num(s, i) for s in series)))
    return rows


def fetch_elevations(coords: Sequence[tuple[float, float]], session: requests.Session | None = None,
                     *, sleep=time.sleep) -> list[float | None]:
    """Elevation (m) for each (lat, lon), batched 100 per request."""
    session = session or requests.Session()
    out: list[float | None] = []
    for batch in chunks(coords, ELEVATION_BATCH_SIZE):
        params = {"latitude": _fmt([c[0] for c in batch]), "longitude": _fmt([c[1] for c in batch])}
        data = _get_json(session, ELEVATION_URL, params, sleep=sleep)
        elev = data.get("elevation") or []
        if len(elev) != len(batch):
            raise OpenMeteoError(f"Expected {len(batch)} elevations, got {len(elev)}")
        out.extend(None if e is None else float(e) for e in elev)
    return out
