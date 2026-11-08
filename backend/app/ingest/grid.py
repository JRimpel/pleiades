"""Load the static grid (light pollution, elevation, curated spots) into grid_cells.

Source is the committed data/wny_grid.geojson, built from the Falchi World Atlas 2015 by
data/build_grid.py. The 3 GB atlas raster is NOT needed here.

    python -m app.ingest grid            # load if grid_cells is empty, otherwise no-op
    python -m app.ingest grid --reset    # TRUNCATE grid_cells ... CASCADE, then load

--reset also deletes everything that references grid_cells (forecasts, scores, explanations,
photo cell links), so re-run astro/weather/score afterwards (`ingest bootstrap` does this).
"""
from __future__ import annotations

import json
import logging
import math
from pathlib import Path
from typing import Any

import psycopg

from ..config import Settings

log = logging.getLogger(__name__)

# WNY bounds (lon/lat), with a small tolerance for float noise on the grid edges.
BBOX = (-79.8, 42.0, -77.0, 43.4)
_EPS = 1e-6

INSERT_SQL = """
    INSERT INTO grid_cells (geom, name, is_curated, elevation_m, sky_brightness_mpsas, bortle)
    VALUES (ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography, %s, %s, %s, %s, %s)
"""

GridRow = tuple[float, float, Any, bool, Any, float, int]


class GridFileError(ValueError):
    """The grid GeoJSON is missing or malformed."""


def _finite(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def parse_features(collection: dict) -> list[GridRow]:
    """Validate a FeatureCollection and return insert rows (lon, lat, name, curated, elev, mpsas, bortle)."""
    if collection.get("type") != "FeatureCollection" or not isinstance(collection.get("features"), list):
        raise GridFileError("expected a GeoJSON FeatureCollection")
    features = collection["features"]
    if not features:
        raise GridFileError("grid GeoJSON has no features")

    rows: list[GridRow] = []
    seen: set[tuple[float, float, bool]] = set()
    for i, f in enumerate(features):
        geom = (f or {}).get("geometry") or {}
        props = (f or {}).get("properties") or {}
        if geom.get("type") != "Point":
            raise GridFileError(f"feature {i}: geometry must be a Point")
        coords = geom.get("coordinates") or []
        if len(coords) < 2 or not all(_finite(c) for c in coords[:2]):
            raise GridFileError(f"feature {i}: bad coordinates {coords!r}")
        lon, lat = float(coords[0]), float(coords[1])
        if not (BBOX[0] - _EPS <= lon <= BBOX[2] + _EPS and BBOX[1] - _EPS <= lat <= BBOX[3] + _EPS):
            raise GridFileError(f"feature {i}: ({lat}, {lon}) is outside the WNY bounding box")

        mpsas, bortle = props.get("sky_brightness_mpsas"), props.get("bortle")
        if not _finite(mpsas):
            raise GridFileError(f"feature {i}: sky_brightness_mpsas missing or not a number")
        if not _finite(bortle) or not 1 <= int(bortle) <= 9:
            raise GridFileError(f"feature {i}: bortle missing or not in 1..9")
        elev = props.get("elevation_m")
        if elev is not None and not _finite(elev):
            raise GridFileError(f"feature {i}: elevation_m is not a number")
        curated = bool(props.get("is_curated", False))
        name = props.get("name")
        if curated and not name:
            raise GridFileError(f"feature {i}: curated spot needs a name")

        key = (round(lon, 6), round(lat, 6), curated)
        if key in seen:
            raise GridFileError(f"feature {i}: duplicate point ({lat}, {lon})")
        seen.add(key)
        rows.append((lon, lat, name, curated, None if elev is None else float(elev), float(mpsas), int(bortle)))
    return rows


def load_file(path: str | Path) -> list[GridRow]:
    p = Path(path)
    if not p.is_file():
        raise GridFileError(f"grid file not found: {p} (set GRID_GEOJSON_PATH)")
    with p.open() as fh:
        return parse_features(json.load(fh))


def clear_aggregates(database_url: str) -> None:
    """Re-materialize both continuous aggregates over all time so buckets for deleted cells vanish."""
    # refresh_continuous_aggregate cannot run inside a transaction block.
    with psycopg.connect(database_url, autocommit=True) as conn:
        for view in ("cell_hourly_score", "cell_nightly_best"):
            conn.execute("CALL refresh_continuous_aggregate(%s, NULL, NULL)", (view,))


def run(conn: psycopg.Connection, settings: Settings, *, reset: bool = False) -> int:
    rows = load_file(settings.grid_geojson_path)  # validate before touching the DB
    n_curated = sum(1 for r in rows if r[3])

    existing = conn.execute("SELECT count(*) AS n FROM grid_cells").fetchone()["n"]
    if existing and not reset:
        log.info("grid: already loaded (%d cells); use --reset to replace", existing)
        conn.rollback()
        return 0

    if reset:
        log.warning("grid: TRUNCATE grid_cells RESTART IDENTITY CASCADE (%d existing cells)", existing)
        conn.execute("TRUNCATE grid_cells RESTART IDENTITY CASCADE")
    with conn.cursor() as cur:
        cur.executemany(INSERT_SQL, rows)
    conn.commit()
    log.info("grid: loaded %d cells (%d curated) from %s", len(rows), n_curated, settings.grid_geojson_path)

    if reset and existing:
        clear_aggregates(settings.database_url)
    return len(rows)
