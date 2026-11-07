"""Static grid cells and curated spots."""
from __future__ import annotations

from typing import Any

from ..db import get_conn

CELL_COLS = (
    "g.id, g.name, g.is_curated, g.elevation_m, g.sky_brightness_mpsas, g.bortle, "
    "ST_Y(g.geom::geometry) AS lat, ST_X(g.geom::geometry) AS lon"
)


def get(cell_id: int) -> dict[str, Any] | None:
    with get_conn() as conn:
        row = conn.execute(f"SELECT {CELL_COLS} FROM grid_cells g WHERE g.id = %s", (cell_id,)).fetchone()
    return dict(row) if row else None


def nearest_cell(lat: float, lon: float) -> int | None:
    """Id of the grid cell or curated spot nearest to (lat, lon), via the GiST KNN operator."""
    with get_conn() as conn:
        row = conn.execute(
            "SELECT id FROM grid_cells "
            "ORDER BY geom <-> ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography LIMIT 1",
            (lon, lat),
        ).fetchone()
    return int(row["id"]) if row else None
