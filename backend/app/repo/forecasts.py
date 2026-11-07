"""Raw weather forecasts and astro conditions."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from ..db import get_conn


def latest_for(cell_id: int, hour: datetime) -> dict[str, Any] | None:
    """The most recent forecast revision for one cell-hour."""
    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT fetched_at, cloud_low, cloud_mid, cloud_high, cloud_total, visibility_m,
                   rh, dew_point_c, temp_c, wind_kmh, precip_prob
            FROM weather_forecast
            WHERE cell_id = %s AND valid_time = %s
            ORDER BY fetched_at DESC LIMIT 1
            """,
            (cell_id, hour),
        ).fetchone()
    return dict(row) if row else None


def astro_at(hour: datetime) -> dict[str, Any] | None:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT time, sun_alt, moon_alt, moon_illum, moon_phase_deg FROM astro_conditions WHERE time = %s",
            (hour,),
        ).fetchone()
    return dict(row) if row else None
