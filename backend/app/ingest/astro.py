"""`python -m app.ingest astro`: sun/moon ephemeris per hour + upcoming sky events."""
from __future__ import annotations

import logging
from datetime import timedelta

import psycopg
from psycopg.types.json import Jsonb

from ..astro import ephemeris
from ..config import Settings
from ..timeutil import floor_hour, utcnow

log = logging.getLogger(__name__)


def run(conn: psycopg.Connection, settings: Settings) -> int:
    start = floor_hour(utcnow()) - timedelta(hours=6)
    hours = settings.forecast_hours + 12
    lat, lon = settings.centroid_lat, settings.centroid_lon

    conditions = ephemeris.hourly_conditions(start, hours, lat, lon)
    with conn.cursor() as cur:
        cur.executemany(
            """
            INSERT INTO astro_conditions (time, sun_alt, moon_alt, moon_illum, moon_phase_deg)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (time) DO UPDATE SET
              sun_alt = EXCLUDED.sun_alt, moon_alt = EXCLUDED.moon_alt,
              moon_illum = EXCLUDED.moon_illum, moon_phase_deg = EXCLUDED.moon_phase_deg
            """,
            [(h.time, h.sun_alt, h.moon_alt, h.moon_illum, h.moon_phase_deg) for h in conditions],
        )

    events = ephemeris.sky_events(start, start + timedelta(days=8), lat, lon)
    if events:
        with conn.cursor() as cur:
            cur.executemany(
                """
                INSERT INTO sky_events (time, type, name, details) VALUES (%s, %s, %s, %s)
                ON CONFLICT (type, name, time) DO UPDATE SET details = EXCLUDED.details
                """,
                [(e.time, e.type, e.name, Jsonb(e.details) if e.details is not None else None) for e in events],
            )
    conn.commit()
    log.info("astro ingest: %d hourly rows, %d sky events", len(conditions), len(events))
    return len(conditions) + len(events)
