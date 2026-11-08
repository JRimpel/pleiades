"""Grid loader: validation of the committed GeoJSON and load/no-op/reset behaviour (no DB)."""
from __future__ import annotations

import argparse
import json
from unittest import mock

import pytest

from app.config import DEFAULT_GRID_GEOJSON, Settings
from app.ingest import grid
from app.ingest.__main__ import _jobs, main


def feature(lon=-78.4, lat=42.7, **props):
    p = {"name": None, "is_curated": False, "elevation_m": 400.0, "sky_brightness_mpsas": 21.4, "bortle": 4}
    p.update(props)
    return {"type": "Feature", "geometry": {"type": "Point", "coordinates": [lon, lat]}, "properties": p}


def fc(*features):
    return {"type": "FeatureCollection", "features": list(features)}


# --- the committed file -------------------------------------------------------

def test_committed_grid_is_valid():
    rows = grid.load_file(DEFAULT_GRID_GEOJSON)
    assert len(rows) == 364
    curated = [r for r in rows if r[3]]
    assert len(curated) == 8
    assert all(r[2] for r in curated)
    assert any(r[2].startswith("Beaver Meadow") for r in curated)
    assert all(17.0 < r[5] < 22.5 for r in rows)


# --- validation ---------------------------------------------------------------

def test_parse_ok():
    rows = grid.parse_features(fc(feature(), feature(-78.5, 42.8, name="Spot", is_curated=True, elevation_m=None)))
    assert rows[0] == (-78.4, 42.7, None, False, 400.0, 21.4, 4)
    assert rows[1][2:5] == ("Spot", True, None)


@pytest.mark.parametrize("bad, msg", [
    ({"type": "Feature"}, "FeatureCollection"),
    (fc(), "no features"),
    (fc({**feature(), "geometry": {"type": "Polygon", "coordinates": []}}), "Point"),
    (fc(feature(lon=-80.5)), "outside"),
    (fc(feature(lat=44.0)), "outside"),
    (fc(feature(sky_brightness_mpsas=None)), "sky_brightness"),
    (fc(feature(sky_brightness_mpsas=float("nan"))), "sky_brightness"),
    (fc(feature(bortle=12)), "bortle"),
    (fc(feature(elevation_m="high")), "elevation"),
    (fc(feature(is_curated=True)), "name"),
    (fc(feature(), feature()), "duplicate"),
])
def test_parse_rejects(bad, msg):
    with pytest.raises(grid.GridFileError, match=msg):
        grid.parse_features(bad)


def test_same_point_curated_and_regular_is_allowed():
    rows = grid.parse_features(fc(feature(), feature(name="Spot", is_curated=True)))
    assert len(rows) == 2


def test_missing_file(tmp_path):
    with pytest.raises(grid.GridFileError, match="not found"):
        grid.load_file(tmp_path / "nope.geojson")


# --- run() --------------------------------------------------------------------

@pytest.fixture
def grid_file(tmp_path):
    path = tmp_path / "grid.geojson"
    path.write_text(json.dumps(fc(feature(), feature(-78.5, 42.8, name="Spot", is_curated=True))))
    return path


def fake_conn(existing: int):
    conn = mock.MagicMock()
    conn.execute.return_value.fetchone.return_value = {"n": existing}
    return conn


def sql_calls(conn):
    return [c.args[0] for c in conn.execute.call_args_list]


def test_run_loads_empty_table(grid_file):
    conn = fake_conn(0)
    s = Settings(database_url="postgres://x", grid_geojson_path=str(grid_file))
    with mock.patch.object(grid, "clear_aggregates") as clear:
        assert grid.run(conn, s) == 2
    cur = conn.cursor.return_value.__enter__.return_value
    sql, rows = cur.executemany.call_args.args
    assert "INSERT INTO grid_cells" in sql and len(rows) == 2
    assert not any("TRUNCATE" in q for q in sql_calls(conn))
    conn.commit.assert_called_once()
    clear.assert_not_called()


def test_run_noop_when_loaded(grid_file):
    conn = fake_conn(364)
    s = Settings(database_url="postgres://x", grid_geojson_path=str(grid_file))
    assert grid.run(conn, s) == 0
    conn.cursor.assert_not_called()
    conn.commit.assert_not_called()


def test_run_reset_truncates_and_clears_aggregates(grid_file):
    conn = fake_conn(364)
    s = Settings(database_url="postgres://x", grid_geojson_path=str(grid_file))
    with mock.patch.object(grid, "clear_aggregates") as clear:
        assert grid.run(conn, s, reset=True) == 2
    assert "TRUNCATE grid_cells RESTART IDENTITY CASCADE" in sql_calls(conn)
    clear.assert_called_once_with("postgres://x")


def test_run_validates_before_touching_db(tmp_path):
    bad = tmp_path / "bad.geojson"
    bad.write_text(json.dumps(fc(feature(lat=50.0))))
    conn = fake_conn(0)
    with pytest.raises(grid.GridFileError):
        grid.run(conn, Settings(grid_geojson_path=str(bad)), reset=True)
    conn.execute.assert_not_called()


# --- CLI ----------------------------------------------------------------------

def _names(argv):
    captured = {}

    def fake_run_job(name, fn, settings):
        captured.setdefault("names", []).append(name)
        return 0

    with mock.patch("app.ingest.__main__.run_job", side_effect=fake_run_job), \
         mock.patch("app.ingest.__main__.get_settings", return_value=Settings()):
        assert main(argv) == 0
    return captured["names"]


def test_cli_bootstrap_order():
    assert _names(["bootstrap"]) == ["grid", "astro", "weather", "score"]


def test_cli_all_order():
    assert _names(["all"]) == ["astro", "weather", "score", "explain"]


@pytest.mark.parametrize("argv, reset", [
    (["grid"], False), (["grid", "--reset"], True),
    (["bootstrap"], False), (["bootstrap", "--reset-grid"], True),
])
def test_cli_reset_flag_reaches_grid_run(argv, reset):
    ns = argparse.Namespace(job=argv[0], reset="--reset" in argv, reset_grid="--reset-grid" in argv)
    fn = dict(_jobs(ns))["grid"]
    with mock.patch.object(grid, "run", return_value=7) as run:
        assert fn(mock.sentinel.conn, mock.sentinel.settings) == 7
    assert run.call_args.kwargs["reset"] is reset
