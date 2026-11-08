"""End-to-end pipeline against a real TimescaleDB + PostGIS database.

Skipped unless TEST_DATABASE_URL is set. Use a THROWAWAY database: the test resets grid_cells
with TRUNCATE ... CASCADE, which also clears forecasts, scores and photos.

    docker compose up -d db && docker compose exec db createdb -U postgres pleiades_test
    TEST_DATABASE_URL=postgres://postgres:password@localhost:5432/pleiades_test pytest -m db
"""
from __future__ import annotations

import os
from datetime import timedelta

import pytest

pytestmark = pytest.mark.db

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL", "")
if not TEST_DATABASE_URL:
    pytest.skip("TEST_DATABASE_URL not set", allow_module_level=True)

from app import create_app, db  # noqa: E402
from app.config import Settings  # noqa: E402
from app.ingest import astro as astro_job  # noqa: E402
from app.ingest import grid as grid_job  # noqa: E402
from app.ingest import openmeteo  # noqa: E402
from app.ingest import score as score_job  # noqa: E402
from app.ingest import weather as weather_job  # noqa: E402
from app.migrate import run as run_migrations  # noqa: E402
from app.timeutil import floor_hour, utcnow  # noqa: E402


@pytest.fixture(scope="module")
def settings() -> Settings:
    return Settings(database_url=TEST_DATABASE_URL, db_pool_min=1, db_pool_max=4)


@pytest.fixture(scope="module")
def pipeline(settings):
    """Migrate, load the real grid, ingest astro, insert synthetic weather (no network), score."""
    run_migrations(database_url=TEST_DATABASE_URL)

    with db.connect_direct(settings) as conn:
        n_cells = grid_job.run(conn, settings, reset=True)
        assert n_cells == 364
        counts = conn.execute(
            "SELECT count(*) AS n, count(*) FILTER (WHERE is_curated) AS curated FROM grid_cells").fetchone()
        assert (counts["n"], counts["curated"]) == (364, 8)
        assert grid_job.run(conn, settings) == 0  # idempotent: already loaded

        assert astro_job.run(conn, settings) > 0

        cells = weather_job.load_cells(conn)
        assert len(cells) == n_cells
        fetched_at = utcnow()
        start = floor_hour(fetched_at) - timedelta(hours=2)
        rows = []
        for cell_id, lat, lon in cells:
            for h in range(30):
                clear = (cell_id + h) % 4 != 0
                rows.append((
                    start + timedelta(hours=h), cell_id, fetched_at,
                    0.0 if clear else 80.0, 0.0, 10.0, 10.0 if clear else 85.0,
                    24000.0, 70.0, -2.0, 3.0, 8.0, 0.0,
                ))
        assert len(rows[0]) == len(openmeteo.WEATHER_COLUMNS)
        weather_job.copy_rows(conn, rows)
        conn.commit()

        n_scores = score_job.run(conn, settings, refresh=True)
        assert n_scores == n_cells * 30

        # Pick a dark hour inside the scored window for the API checks.
        dark = conn.execute(
            """
            SELECT time FROM astro_conditions
            WHERE time >= %s AND time < %s ORDER BY sun_alt ASC LIMIT 1
            """,
            (start + timedelta(hours=1), start + timedelta(hours=30)),
        ).fetchone()
        best_cell = conn.execute(
            "SELECT cell_id FROM cell_hourly_score WHERE bucket = %s ORDER BY score DESC LIMIT 1",
            (dark["time"],),
        ).fetchone()
    return {"dark_time": dark["time"], "cell_id": best_cell["cell_id"], "n_cells": n_cells}


@pytest.fixture(scope="module")
def client(settings, pipeline):
    db.close_pool()
    app = create_app(settings, start_workers=False)
    app.config["TESTING"] = True
    yield app.test_client()
    db.close_pool()


def test_migrations_are_idempotent(pipeline):
    assert run_migrations(database_url=TEST_DATABASE_URL) == 0


def test_health(client):
    resp = client.get("/api/health")
    body = resp.get_json()
    assert resp.status_code in (200, 503), body
    assert body["db"] is True
    assert body["last_score_run"] is None or isinstance(body["last_score_run"], str)


def test_scores(client, pipeline):
    t = pipeline["dark_time"].isoformat()
    resp = client.get("/api/scores", query_string={"time": t})
    assert resp.status_code == 200, resp.get_json()
    body = resp.get_json()
    assert body["type"] == "FeatureCollection"
    assert len(body["features"]) >= pipeline["n_cells"] - 10
    props = body["features"][0]["properties"]
    for key in ("cell_id", "score", "label", "bortle", "top_factor", "is_curated"):
        assert key in props
    kinds = {f["geometry"]["type"] for f in body["features"]}
    assert "Polygon" in kinds and "Point" in kinds  # grid cells + curated spots

    resp = client.get("/api/scores/range")
    assert resp.status_code == 200
    assert resp.get_json()["max_time"] is not None


def test_best(client, pipeline):
    t = pipeline["dark_time"].isoformat()
    resp = client.get("/api/best", query_string={"time": t, "near": "42.88,-78.87", "radius_km": 150, "limit": 5})
    assert resp.status_code == 200, resp.get_json()
    spots = resp.get_json()["spots"]
    assert 0 < len(spots) <= 5
    assert spots[0]["score"] >= spots[-1]["score"]


def test_spot_detail_history_drift(client, pipeline):
    cid, t = pipeline["cell_id"], pipeline["dark_time"]
    resp = client.get(f"/api/spots/{cid}", query_string={"time": t.isoformat()})
    assert resp.status_code == 200, resp.get_json()
    body = resp.get_json()
    assert body["cell_id"] == cid and body["score"] is not None
    assert body["factors"] and body["conditions"] is not None and body["astro"] is not None
    assert body["explanation"]["summary"]

    resp = client.get(f"/api/spots/{cid}/history",
                      query_string={"from": (t - timedelta(hours=6)).isoformat(),
                                    "to": (t + timedelta(hours=6)).isoformat()})
    assert resp.status_code == 200, resp.get_json()
    assert len(resp.get_json()["hourly"]) > 0

    from app.timeutil import current_night

    night = current_night(t, "America/New_York").isoformat()
    resp = client.get(f"/api/spots/{cid}/drift", query_string={"night": night})
    assert resp.status_code == 200, resp.get_json()
    assert resp.get_json()["cell_id"] == cid


def test_spot_not_found(client):
    assert client.get("/api/spots/999999").status_code == 404
