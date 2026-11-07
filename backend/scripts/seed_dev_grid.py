"""DEV ONLY: seed `grid_cells` with a synthetic Western New York grid + curated spots.

The real loader is data/build_grid.py (owned by AI/ML), which samples the Falchi
light-pollution atlas. This script exists so the backend can run end to end without it:

- 0.1° grid over lat 42.0–43.4, lon −79.8–−77.0 (~435 points).
- Points in Lake Erie / Lake Ontario are dropped with a CRUDE hand-drawn polygon test
  (good to a few km; some shoreline cells will be wrong).
- Sky brightness is synthesized from distance-weighted city glow (Walker's law,
  brightness ∝ population · distance^-2.5), clamped to 17.5–22.0 mag/arcsec².
- Elevation comes from the Open-Meteo Elevation API unless --no-elevation.

Usage (from backend/):
    python scripts/seed_dev_grid.py [--reset [--force]] [--no-elevation]
"""
from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import psycopg  # noqa: E402

from app.config import get_settings  # noqa: E402

LAT_MIN, LAT_MAX = 42.0, 43.4
LON_MIN, LON_MAX = -79.8, -77.0
STEP = 0.1

NATURAL_MPSAS = 22.0
MPSAS_MIN, MPSAS_MAX = 17.5, 22.0
GLOW_SCALE = 380.0  # calibrated so downtown Buffalo ≈ 17.8 mag/arcsec²

# (name, lat, lon, population incl. metro glow)
CITIES: list[tuple[str, float, float, float]] = [
    ("Buffalo", 42.886, -78.878, 1_100_000),
    ("Rochester", 43.157, -77.615, 1_050_000),
    ("Niagara Falls", 43.095, -79.057, 200_000),
    ("Jamestown", 42.097, -79.235, 50_000),
    ("Olean", 42.078, -78.430, 30_000),
]

# Crude lake outlines as (lon, lat) rings.
LAKE_ERIE: list[tuple[float, float]] = [
    (-79.90, 42.25), (-79.76, 42.27), (-79.33, 42.49), (-79.05, 42.70), (-78.90, 42.84),
    (-78.92, 42.89), (-79.25, 42.88), (-79.90, 42.85),
]
LAKE_ONTARIO: list[tuple[float, float]] = [
    (-79.90, 43.28), (-79.56, 43.21), (-79.07, 43.27), (-78.72, 43.35), (-78.20, 43.37),
    (-77.60, 43.27), (-77.00, 43.29), (-76.90, 43.29), (-76.90, 43.50), (-79.90, 43.50),
]

CURATED_SPOTS: list[tuple[str, float, float]] = [
    ("Beaver Meadow Audubon Center", 42.6678, -78.3864),
    ("Allegany State Park", 42.1000, -78.7470),
    ("Letchworth State Park", 42.5800, -78.0500),
    ("Chestnut Ridge Park", 42.7130, -78.7540),
    ("Darien Lakes State Park", 42.9090, -78.4250),
    ("Genesee Country Village & Museum", 42.9950, -77.8600),
    ("Zoar Valley Multiple Use Area", 42.4400, -78.9500),
    ("Hunters Creek County Park", 42.7650, -78.5300),
]


def point_in_polygon(lon: float, lat: float, ring: list[tuple[float, float]]) -> bool:
    inside = False
    j = len(ring) - 1
    for i in range(len(ring)):
        xi, yi = ring[i]
        xj, yj = ring[j]
        if (yi > lat) != (yj > lat) and lon < (xj - xi) * (lat - yi) / (yj - yi) + xi:
            inside = not inside
        j = i
    return inside


def is_water(lat: float, lon: float) -> bool:
    return point_in_polygon(lon, lat, LAKE_ERIE) or point_in_polygon(lon, lat, LAKE_ONTARIO)


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 6371.0 * 2 * math.asin(math.sqrt(a))


def sky_brightness(lat: float, lon: float) -> float:
    ratio = 0.0
    for _, clat, clon, pop in CITIES:
        d = haversine_km(lat, lon, clat, clon)
        ratio += GLOW_SCALE * (pop / 100_000) * (d + 3.0) ** -2.5
    m = NATURAL_MPSAS - 2.5 * math.log10(1.0 + ratio)
    return round(min(MPSAS_MAX, max(MPSAS_MIN, m)), 2)


def bortle_from_mpsas(m: float) -> int:
    for threshold, cls in ((21.99, 1), (21.89, 2), (21.69, 3), (20.49, 4), (19.50, 5),
                           (18.94, 6), (18.38, 7), (17.80, 8)):
        if m >= threshold:
            return cls
    return 9


def grid_points() -> list[tuple[float, float]]:
    n_lat = int(round((LAT_MAX - LAT_MIN) / STEP)) + 1
    n_lon = int(round((LON_MAX - LON_MIN) / STEP)) + 1
    pts = []
    for i in range(n_lat):
        lat = round(LAT_MIN + i * STEP, 4)
        for j in range(n_lon):
            lon = round(LON_MIN + j * STEP, 4)
            if not is_water(lat, lon):
                pts.append((lat, lon))
    return pts


def build_rows(elevations: bool) -> list[tuple]:
    """(name, is_curated, lat, lon, elevation_m, sky_brightness_mpsas, bortle)."""
    cells = [(None, False, lat, lon) for lat, lon in grid_points()]
    cells += [(name, True, lat, lon) for name, lat, lon in CURATED_SPOTS]
    elev: list[float | None] = [None] * len(cells)
    if elevations:
        from app.ingest.openmeteo import fetch_elevations

        elev = fetch_elevations([(lat, lon) for _, _, lat, lon in cells])
    rows = []
    for (name, curated, lat, lon), e in zip(cells, elev):
        m = sky_brightness(lat, lon)
        rows.append((name, curated, lat, lon, e, m, bortle_from_mpsas(m)))
    return rows


REFERENCING_TABLES = ("weather_forecast", "score_snapshots", "photos")


def reset(conn: psycopg.Connection, force: bool) -> None:
    referenced = [t for t in REFERENCING_TABLES
                  if conn.execute(f"SELECT EXISTS (SELECT 1 FROM {t} WHERE cell_id IS NOT NULL) AS e").fetchone()[0]]
    if referenced and not force:
        raise SystemExit(f"Refusing to reset: rows in {', '.join(referenced)} reference grid_cells. "
                         "Re-run with --force to TRUNCATE ... CASCADE (deletes that data too).")
    if force:
        conn.execute("TRUNCATE grid_cells RESTART IDENTITY CASCADE")
    else:
        conn.execute("DELETE FROM grid_cells")
        conn.execute("SELECT setval(pg_get_serial_sequence('grid_cells', 'id'), 1, false)")


def seed(database_url: str, *, do_reset: bool = False, force: bool = False, elevations: bool = True) -> int:
    with psycopg.connect(database_url) as conn:
        if do_reset:
            reset(conn, force)
        else:
            n = conn.execute("SELECT count(*) FROM grid_cells").fetchone()[0]
            if n:
                raise SystemExit(f"grid_cells already has {n} rows; use --reset to replace them.")
        rows = build_rows(elevations)
        with conn.cursor() as cur:
            cur.executemany(
                """
                INSERT INTO grid_cells (geom, name, is_curated, elevation_m, sky_brightness_mpsas, bortle)
                VALUES (ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography, %s, %s, %s, %s, %s)
                """,
                [(lon, lat, name, curated, e, m, b) for name, curated, lat, lon, e, m, b in rows],
            )
        conn.commit()
    return len(rows)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="DEV ONLY: seed grid_cells with a synthetic WNY grid")
    parser.add_argument("--reset", action="store_true", help="delete existing grid_cells first")
    parser.add_argument("--force", action="store_true", help="with --reset: TRUNCATE ... CASCADE dependent data")
    parser.add_argument("--no-elevation", action="store_true", help="skip the Open-Meteo elevation lookup")
    parser.add_argument("--database-url", default=None, help="defaults to DATABASE_URL")
    args = parser.parse_args(argv)

    url = args.database_url or get_settings().database_url
    if not url:
        print("DATABASE_URL is not set", file=sys.stderr)
        return 2
    n = seed(url, do_reset=args.reset, force=args.force, elevations=not args.no_elevation)
    print(f"Seeded {n} grid cells ({len(CURATED_SPOTS)} curated).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
