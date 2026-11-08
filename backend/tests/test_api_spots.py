from __future__ import annotations

import time
from datetime import date, datetime, timezone

import pytest

from app import spot_explanations
from app.ai import explain
from app.ai.types import Explanation
from app.repo import cells as cells_repo
from app.repo import explanations as explanations_repo
from app.repo import forecasts as forecasts_repo
from app.repo import scores as scores_repo

UTC = timezone.utc
HOUR = datetime(2026, 11, 8, 3, tzinfo=UTC)
CELL = {"id": 42, "name": "Allegany State Park", "is_curated": True, "elevation_m": 650.0,
        "sky_brightness_mpsas": 21.6, "bortle": 3, "lat": 42.1, "lon": -78.75}
SCORE = {"score": 72.3, "nelm": 6.4, "factors": {"clouds": -12.0, "moon": -15.7, "elevation": 3.0},
         "model_version": 1, "computed_at": datetime(2026, 11, 7, 21, tzinfo=UTC)}
COND = {"fetched_at": datetime(2026, 11, 7, 21, tzinfo=UTC), "cloud_low": 5.0, "cloud_mid": 10.0,
        "cloud_high": 30.0, "cloud_total": 35.0, "visibility_m": 24000.0, "rh": 70.0, "dew_point_c": -2.0,
        "temp_c": 3.0, "wind_kmh": 8.0, "precip_prob": 0.0}
ASTRO = {"time": HOUR, "sun_alt": -45.0, "moon_alt": 20.0, "moon_illum": 0.6, "moon_phase_deg": 100.0}


KEY = (42, HOUR, 1)


@pytest.fixture
def spot_repos(monkeypatch):
    cache: dict = {}
    spot_explanations.clear_fallbacks()
    monkeypatch.setattr(cells_repo, "get", lambda cid: dict(CELL) if cid == 42 else None)
    monkeypatch.setattr(scores_repo, "score_for", lambda cid, hour: dict(SCORE) if hour == HOUR else None)
    monkeypatch.setattr(forecasts_repo, "latest_for", lambda cid, hour: dict(COND))
    monkeypatch.setattr(forecasts_repo, "astro_at", lambda hour: dict(ASTRO))
    monkeypatch.setattr(explanations_repo, "get", lambda cid, t, mv: cache.get((cid, t, mv)))

    def put(cid, t, mv, explained_score, summary, tips):
        cache[(cid, t, mv)] = {"summary": summary, "tips": tips, "explained_score": explained_score}

    monkeypatch.setattr(explanations_repo, "put", put)
    yield cache
    spot_explanations.clear_fallbacks()


@pytest.fixture
def gemini_on(monkeypatch):
    """Pretend Gemini is configured; tests supply explain_score."""
    monkeypatch.setattr(explain, "is_configured", lambda: True)


def test_spot_detail_never_waits_on_gemini(client, spot_repos, gemini_on, monkeypatch):
    monkeypatch.setattr(explain, "explain_score", lambda ctx: pytest.fail("detail must not call Gemini"))
    resp = client.get("/api/spots/42?time=2026-11-08T03:30:00Z")
    assert resp.status_code == 200
    d = resp.get_json()
    assert d["cell_id"] == 42 and d["name"] == "Allegany State Park"
    assert d["valid_time"] == "2026-11-08T03:00:00Z"
    assert d["score"] == 72.3 and d["label"] == "Good" and d["nelm"] == 6.4
    assert d["factors"]["moon"] == -15.7
    assert d["conditions"]["cloud_high"] == 30.0
    assert d["astro"]["moon_illum"] == 0.6
    assert d["explanation"] is None and d["explanation_pending"] is True


def test_spot_detail_includes_cached_explanation(client, spot_repos, gemini_on):
    spot_repos[KEY] = {"summary": "cached!", "tips": ["a"], "explained_score": 72.3}
    d = client.get("/api/spots/42?time=2026-11-08T03:00:00Z").get_json()
    assert d["explanation"] == {"summary": "cached!", "tips": ["a"]}
    assert d["explanation_pending"] is False


def test_spot_detail_ignores_explanation_written_for_a_different_score(client, spot_repos, gemini_on):
    spot_repos[KEY] = {"summary": "stale", "tips": [], "explained_score": 60.0}
    d = client.get("/api/spots/42?time=2026-11-08T03:00:00Z").get_json()
    assert d["explanation"] is None and d["explanation_pending"] is True


def test_spot_detail_keeps_explanation_when_rounded_score_unchanged(client, spot_repos, gemini_on):
    spot_repos[KEY] = {"summary": "same", "tips": [], "explained_score": 72.1}  # re-score 72.1 -> 72.3
    d = client.get("/api/spots/42?time=2026-11-08T03:00:00Z").get_json()
    assert d["explanation"]["summary"] == "same"


def test_spot_detail_ignores_rows_from_before_explained_score(client, spot_repos, gemini_on):
    spot_repos[KEY] = {"summary": "legacy", "tips": [], "explained_score": None}
    d = client.get("/api/spots/42?time=2026-11-08T03:00:00Z").get_json()
    assert d["explanation_pending"] is True


def test_spot_detail_without_gemini_serves_template_uncached(client, spot_repos):
    d = client.get("/api/spots/42?time=2026-11-08T03:00:00Z").get_json()
    assert "72" in d["explanation"]["summary"] and d["explanation_pending"] is False
    assert KEY not in spot_repos  # templates are never stored


def test_explanation_generates_and_caches(client, spot_repos, gemini_on, monkeypatch):
    monkeypatch.setattr(explain, "explain_score", lambda ctx: Explanation(summary=f"live {ctx.score}", tips=["t"]))
    resp = client.get("/api/spots/42/explanation?time=2026-11-08T03:00:00Z")
    assert resp.status_code == 200
    assert resp.get_json() == {"summary": "live 72.3", "tips": ["t"]}
    assert spot_repos[KEY]["summary"] == "live 72.3"
    d = client.get("/api/spots/42?time=2026-11-08T03:00:00Z").get_json()
    assert d["explanation"]["summary"] == "live 72.3" and d["explanation_pending"] is False


def test_explanation_cache_hit(client, spot_repos, gemini_on, monkeypatch):
    spot_repos[KEY] = {"summary": "cached!", "tips": ["a"], "explained_score": 72.3}
    monkeypatch.setattr(explain, "explain_score", lambda ctx: pytest.fail("should use cache"))
    d = client.get("/api/spots/42/explanation?time=2026-11-08T03:00:00Z").get_json()
    assert d == {"summary": "cached!", "tips": ["a"]}


def test_explanation_error_falls_back_uncached_and_is_remembered(client, spot_repos, gemini_on, monkeypatch):
    calls = []

    def boom(ctx):
        calls.append(ctx)
        raise RuntimeError("gemini down")

    monkeypatch.setattr(explain, "explain_score", boom)
    d = client.get("/api/spots/42/explanation?time=2026-11-08T03:00:00Z").get_json()
    assert "72" in d["summary"]
    assert KEY not in spot_repos  # fallbacks are not stored in the database
    again = client.get("/api/spots/42/explanation?time=2026-11-08T03:00:00Z").get_json()
    assert again == d and len(calls) == 1  # served from the short in-process fallback cache
    detail = client.get("/api/spots/42?time=2026-11-08T03:00:00Z").get_json()
    assert detail["explanation"] == d and detail["explanation_pending"] is False


def test_explanation_timeout(client, spot_repos, gemini_on, monkeypatch, app):
    calls = []

    def slow(ctx):
        calls.append(ctx)
        time.sleep(2.0)
        return Explanation(summary="late", tips=[])

    monkeypatch.setattr(explain, "explain_score", slow)
    started = time.monotonic()
    d = client.get("/api/spots/42/explanation?time=2026-11-08T03:00:00Z").get_json()
    assert time.monotonic() - started < 1.9  # explain_timeout_s = 1.0 in tests
    assert d["summary"] != "late"
    started = time.monotonic()
    client.get("/api/spots/42/explanation?time=2026-11-08T03:00:00Z")
    assert time.monotonic() - started < 0.5 and len(calls) == 1


def test_explanation_without_score_is_404(client, spot_repos):
    resp = client.get("/api/spots/42/explanation?time=2026-11-09T03:00:00Z")
    assert resp.status_code == 404


def test_spot_without_score(client, spot_repos):
    d = client.get("/api/spots/42?time=2026-11-09T03:00:00Z").get_json()
    assert d["score"] is None and d["label"] is None and d["explanation"] is None
    assert d["explanation_pending"] is False


def test_spot_404(client, spot_repos):
    for path in ("/api/spots/7", "/api/spots/7/history", "/api/spots/7/drift", "/api/spots/7/explanation"):
        resp = client.get(path)
        assert resp.status_code == 404, path
        assert resp.get_json()["error"]["code"] == "not_found"


def test_spot_history(client, spot_repos, monkeypatch):
    seen = {}

    def fake_history(cid, start, end, tz):
        seen.update(cid=cid, start=start, end=end, tz=tz)
        return ([{"time": HOUR, "score": 50.0, "nelm": 6.0}],
                [{"night": date(2026, 11, 7), "best_score": 81.0, "best_time": HOUR}])

    monkeypatch.setattr(scores_repo, "history", fake_history)
    resp = client.get("/api/spots/42/history?from=2026-11-01T00:00:00Z&to=2026-11-09T00:00:00Z")
    assert resp.status_code == 200
    d = resp.get_json()
    assert seen["start"] == datetime(2026, 11, 1, tzinfo=UTC) and seen["tz"] == "America/New_York"
    assert d["hourly"] == [{"time": "2026-11-08T03:00:00Z", "score": 50.0, "nelm": 6.0}]
    assert d["nightly"][0] == {"night": "2026-11-07", "best_score": 81.0, "best_time": "2026-11-08T03:00:00Z"}


def test_spot_history_bad_range(client, spot_repos):
    assert client.get("/api/spots/42/history?from=2026-11-09T00:00:00Z&to=2026-11-01T00:00:00Z").status_code == 400
    assert client.get("/api/spots/42/history?from=2026-01-01T00:00:00Z&to=2026-11-01T00:00:00Z").status_code == 400


def test_spot_drift(client, spot_repos, monkeypatch):
    seen = {}
    c1, c2 = datetime(2026, 11, 7, 12, tzinfo=UTC), datetime(2026, 11, 7, 15, tzinfo=UTC)

    def fake_drift(cid, start, end):
        seen.update(start=start, end=end)
        return [
            {"computed_at": c1, "model_version": 1, "points": [{"valid_time": HOUR, "score": 40.0},
                                                                {"valid_time": HOUR.replace(hour=4), "score": 55.0}]},
            {"computed_at": c2, "model_version": 1, "points": [{"valid_time": HOUR, "score": 60.0}]},
        ]

    monkeypatch.setattr(scores_repo, "drift", fake_drift)
    d = client.get("/api/spots/42/drift?night=2026-11-07").get_json()
    # 18:00 EST (UTC-5) -> 23:00Z; 06:00 EST next day -> 11:00Z
    assert d["window_start"] == "2026-11-07T23:00:00Z" and d["window_end"] == "2026-11-08T11:00:00Z"
    assert seen["start"] == datetime(2026, 11, 7, 23, tzinfo=UTC)
    assert [r["peak_score"] for r in d["revisions"]] == [55.0, 60.0]
    assert len(d["revisions"][0]["points"]) == 2


def test_spot_drift_bad_night(client, spot_repos):
    assert client.get("/api/spots/42/drift?night=11-07-2026").status_code == 400
