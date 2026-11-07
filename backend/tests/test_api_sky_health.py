from __future__ import annotations

from contextlib import contextmanager
from datetime import date, datetime, timezone

from app.api import health as health_api
from app.astro import ephemeris
from app.repo import ingest_log
from app.repo import sky as sky_repo
from app.schemas.sky import MoonInfo, NightSummary, PlanetVisibility, Twilight
from app.storage import s3

UTC = timezone.utc


def test_sky_events(client, monkeypatch):
    seen = {}

    def fake_summary(lat, lon, night, tz):
        seen.update(lat=lat, lon=lon, night=night, tz=tz)
        return NightSummary(
            moon=MoonInfo(phase_deg=100.0, illumination=0.59, phase_name="Waxing Gibbous"),
            twilight=Twilight(astronomical_dusk=datetime(2026, 11, 7, 23, 40, tzinfo=UTC)),
            planets=[PlanetVisibility(name="Jupiter", max_alt_deg=55.0, magnitude=-2.6)],
        )

    def fake_events(start, end):
        seen.update(start=start, end=end)
        return [{"time": datetime(2026, 11, 8, 6, tzinfo=UTC), "type": "meteor_shower", "name": "Leonids",
                 "details": {"zhr": 15}}]

    monkeypatch.setattr(ephemeris, "night_summary", fake_summary)
    monkeypatch.setattr(sky_repo, "events_between", fake_events)
    resp = client.get("/api/sky-events?lat=42.9&lon=-78.9&date=2026-11-07")
    assert resp.status_code == 200
    d = resp.get_json()
    assert seen["night"] == date(2026, 11, 7) and seen["lat"] == 42.9
    # Local noon (EST) on Nov 7 -> 17:00Z, through noon Nov 8.
    assert seen["start"] == datetime(2026, 11, 7, 17, tzinfo=UTC)
    assert seen["end"] == datetime(2026, 11, 8, 17, tzinfo=UTC)
    assert d["moon"]["phase_name"] == "Waxing Gibbous"
    assert d["planets"][0]["name"] == "Jupiter"
    assert d["events"][0]["name"] == "Leonids"


def test_sky_events_defaults_use_stub(client, monkeypatch):
    monkeypatch.setattr(sky_repo, "events_between", lambda s, e: [])
    d = client.get("/api/sky-events").get_json()
    assert d["lat"] == 42.7 and d["lon"] == -78.4
    assert 0 <= d["moon"]["illumination"] <= 1


def test_sky_events_bad_params(client):
    assert client.get("/api/sky-events?lat=100").status_code == 400
    assert client.get("/api/sky-events?date=tomorrow").status_code == 400


def test_health_degraded_without_db(client, monkeypatch):
    from app.db import DatabaseNotConfigured

    def no_db(timeout=10.0):
        raise DatabaseNotConfigured("DATABASE_URL is not set")

    monkeypatch.setattr(health_api, "get_conn", no_db)
    monkeypatch.setattr(s3, "bucket_reachable", lambda: False)
    resp = client.get("/api/health")
    assert resp.status_code == 200
    d = resp.get_json()
    assert d["status"] == "degraded" and d["db"] is False and d["storage"] is False
    assert d["model_version"] >= 1


def test_health_ok(client, monkeypatch):
    class FakeConn:
        def execute(self, sql):
            return None

    @contextmanager
    def fake_get_conn(timeout=10.0):
        yield FakeConn()

    t = datetime(2026, 11, 7, 21, tzinfo=UTC)
    monkeypatch.setattr(health_api, "get_conn", fake_get_conn)
    monkeypatch.setattr(ingest_log, "last_success", lambda job: t if job == "weather" else None)
    monkeypatch.setattr(s3, "bucket_reachable", lambda: True)
    d = client.get("/api/health").get_json()
    assert d["status"] == "ok" and d["db"] and d["storage"]
    assert d["last_weather_fetch"] == "2026-11-07T21:00:00Z" and d["last_score_run"] is None
