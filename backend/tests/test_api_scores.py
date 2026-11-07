from __future__ import annotations

from datetime import date, datetime, timezone

from app.repo import scores as scores_repo

UTC = timezone.utc
HOUR = datetime(2026, 11, 8, 3, tzinfo=UTC)


def _row(cell_id, lat, lon, score, curated=False, factors=None):
    return {"cell_id": cell_id, "name": "Beaver Meadow" if curated else None, "is_curated": curated, "bortle": 4,
            "lat": lat, "lon": lon, "score": score, "factors": factors}


def test_scores_geojson(client, monkeypatch):
    seen = {}

    def fake_scores_at(hour, bbox):
        seen.update(hour=hour, bbox=bbox.as_tuple())
        return [
            _row(1, 42.9, -78.8, 34.5, factors={"clouds": -10, "light_pollution": -40, "elevation": 1}),
            _row(2, 42.7, -78.3, None),
            _row(3, 42.6, -78.4, 80.0, curated=True, factors={"clouds": 0, "moon": 0}),
        ]

    monkeypatch.setattr(scores_repo, "scores_at", fake_scores_at)
    resp = client.get("/api/scores?time=2026-11-08T03:25:00Z&bbox=-79,42.5,-78,43")
    assert resp.status_code == 200
    fc = resp.get_json()
    assert fc["type"] == "FeatureCollection"
    assert fc["time"] == "2026-11-08T03:00:00Z"
    assert seen == {"hour": HOUR, "bbox": (-79.0, 42.5, -78.0, 43.0)}

    cell, unscored, curated = fc["features"]
    assert cell["geometry"]["type"] == "Polygon"
    ring = cell["geometry"]["coordinates"][0]
    assert ring[0] == [-78.85, 42.85] and ring[2] == [-78.75, 42.95] and ring[0] == ring[-1]
    assert cell["properties"] == {"cell_id": 1, "name": None, "score": 34.5, "label": "Fair", "bortle": 4,
                                  "top_factor": "light_pollution", "is_curated": False}
    assert unscored["properties"]["score"] is None and unscored["properties"]["label"] is None
    assert curated["geometry"] == {"type": "Point", "coordinates": [-78.4, 42.6]}
    assert curated["properties"]["label"] == "Excellent"
    assert curated["properties"]["top_factor"] is None


def test_scores_bad_params(client):
    assert client.get("/api/scores?time=not-a-time").status_code == 400
    assert client.get("/api/scores?bbox=1,2,3").status_code == 400
    assert client.get("/api/scores?bbox=-78,42,-79,43").status_code == 400


def test_score_range(client, monkeypatch):
    monkeypatch.setattr(scores_repo, "score_range", lambda since: (HOUR, datetime(2026, 11, 11, 3, tzinfo=UTC)))
    data = client.get("/api/scores/range").get_json()
    assert data["min_time"] == "2026-11-08T03:00:00Z"
    assert data["max_time"] == "2026-11-11T03:00:00Z"
    assert "now" in data


def _best_row(cell_id, score, distance=None):
    return {"cell_id": cell_id, "name": None, "is_curated": False, "bortle": 3, "lat": 42.1, "lon": -78.7,
            "score": score, "valid_time": HOUR, "distance_km": distance}


def test_best_at_time_with_near(client, monkeypatch):
    seen = {}

    def fake_best_at(hour, near, radius_km, limit):
        seen.update(hour=hour, near=near, radius_km=radius_km, limit=limit)
        return [_best_row(5, 91.2, 12.345), _best_row(6, 70.0, 30.0)]

    monkeypatch.setattr(scores_repo, "best_at", fake_best_at)
    resp = client.get("/api/best?time=2026-11-08T03:00:00Z&near=42.88,-78.87&radius_km=40&limit=2")
    assert resp.status_code == 200
    data = resp.get_json()
    assert seen == {"hour": HOUR, "near": (42.88, -78.87), "radius_km": 40.0, "limit": 2}
    assert data["time"] == "2026-11-08T03:00:00Z" and data["night"] is None
    assert [s["cell_id"] for s in data["spots"]] == [5, 6]
    assert data["spots"][0]["distance_km"] == 12.3
    assert data["spots"][0]["label"] == "Excellent"


def test_best_tonight_defaults(client, monkeypatch):
    seen = {}

    def fake_best_for_night(night, tz, near, radius_km, limit):
        seen.update(night=night, tz=tz, near=near, radius_km=radius_km, limit=limit)
        return [_best_row(5, 88.0)]

    monkeypatch.setattr(scores_repo, "best_for_night", fake_best_for_night)
    data = client.get("/api/best").get_json()
    assert isinstance(seen["night"], date)
    assert seen["near"] is None and seen["radius_km"] is None and seen["limit"] == 5
    assert data["time"] is None and data["night"] == seen["night"].isoformat()
    assert data["spots"][0]["distance_km"] is None


def test_best_bad_params(client):
    assert client.get("/api/best?limit=0").status_code == 400
    assert client.get("/api/best?limit=abc").status_code == 400
    assert client.get("/api/best?near=42.9").status_code == 400
    assert client.get("/api/best?near=95,-78").status_code == 400
    assert client.get("/api/best?near=42.9,-78.8&radius_km=-5").status_code == 400
