from __future__ import annotations

import dataclasses
from datetime import datetime, timezone

import pytest
from google.genai import errors as genai_errors

from app.ai import explain
from app.ai.types import Explanation
from app.ingest import explain_warm
from app.repo import cells as cells_repo
from app.repo import explanations as explanations_repo
from app.repo import forecasts as forecasts_repo
from app.repo import scores as scores_repo

UTC = timezone.utc
H1 = datetime(2026, 11, 8, 3, tzinfo=UTC)
H2 = datetime(2026, 11, 8, 5, tzinfo=UTC)
COMPUTED = datetime(2026, 11, 7, 21, tzinfo=UTC)
MV = 1


class FakeConn:
    def __init__(self, rows):
        self.rows = rows

    def execute(self, sql, params=None):
        return self

    def fetchall(self):
        return self.rows


@pytest.fixture
def warm(monkeypatch, settings):
    store: dict = {}
    calls: list = []
    top = [{"cell_id": 1, "valid_time": H1}, {"cell_id": 2, "valid_time": H2}]
    curated = [{"cell_id": 2, "best_time": H2}, {"cell_id": 3, "best_time": H1}]  # cell 2 duplicates a top spot
    monkeypatch.setattr(scores_repo, "best_for_night", lambda *a, **kw: top)
    monkeypatch.setattr(cells_repo, "get", lambda cid: {"id": cid, "name": f"Spot {cid}", "bortle": 3})
    monkeypatch.setattr(scores_repo, "score_for", lambda cid, hour: {
        "score": 50.0 + cid, "nelm": 6.0, "factors": {"clouds": -10.0}, "model_version": 1, "computed_at": COMPUTED})
    monkeypatch.setattr(forecasts_repo, "latest_for", lambda cid, hour: None)
    monkeypatch.setattr(forecasts_repo, "astro_at", lambda hour: None)
    monkeypatch.setattr(explanations_repo, "get", lambda cid, t, mv: store.get((cid, t, mv)))
    monkeypatch.setattr(explanations_repo, "put", lambda cid, t, mv, sc, summary, tips: store.__setitem__(
        (cid, t, mv), {"summary": summary, "tips": tips, "explained_score": sc}))
    sleeps: list = []
    monkeypatch.setattr(explain_warm.time, "sleep", sleeps.append)
    monkeypatch.setattr(explain_warm, "close_pool", lambda: None)
    monkeypatch.setattr(explain, "is_configured", lambda: True)

    def fake_explain(ctx):
        calls.append((ctx.cell_id, ctx.valid_time))
        return Explanation(summary=f"warm {ctx.cell_id}", tips=[])

    monkeypatch.setattr(explain, "explain_score", fake_explain)
    return {"conn": FakeConn(curated), "store": store, "calls": calls, "sleeps": sleeps,
            "settings": dataclasses.replace(settings, explain_warm_interval_s=30.0)}


def test_targets_are_deduplicated_in_priority_order(warm):
    pairs = explain_warm.targets(warm["conn"], warm["settings"], H1)
    assert pairs == [(1, H1), (2, H2), (3, H1)]


def test_run_generates_paces_and_skips_cached(warm):
    warm["store"][(1, H1, MV)] = {"summary": "already", "tips": [], "explained_score": 51.0}
    assert explain_warm.run(warm["conn"], warm["settings"]) == 2
    assert warm["calls"] == [(2, H2), (3, H1)]
    assert warm["store"][(3, H1, MV)]["summary"] == "warm 3"
    assert warm["store"][(3, H1, MV)]["explained_score"] == 53.0
    assert warm["sleeps"] == [30.0]  # spaced between calls, not before the first


def test_run_regenerates_when_score_changed(warm):
    warm["store"][(1, H1, MV)] = {"summary": "old", "tips": [], "explained_score": 40.0}
    explain_warm.run(warm["conn"], warm["settings"])
    assert warm["store"][(1, H1, MV)]["summary"] == "warm 1"


def test_run_stops_at_rate_limit(warm, monkeypatch):
    def limited(ctx):
        warm["calls"].append(ctx.cell_id)
        raise genai_errors.ClientError(429, {"error": {"code": 429, "message": "quota", "status": "RESOURCE_EXHAUSTED"}})

    monkeypatch.setattr(explain, "explain_score", limited)
    assert explain_warm.run(warm["conn"], warm["settings"]) == 0
    assert warm["calls"] == [1]


def test_run_continues_after_a_failure(warm, monkeypatch):
    def flaky(ctx):
        if ctx.cell_id == 1:
            raise RuntimeError("gemini down")
        return Explanation(summary="ok", tips=[])

    monkeypatch.setattr(explain, "explain_score", flaky)
    assert explain_warm.run(warm["conn"], warm["settings"]) == 2
    assert (1, H1, MV) not in warm["store"]


def test_run_without_gemini_does_nothing(warm, monkeypatch):
    monkeypatch.setattr(explain, "is_configured", lambda: False)
    assert explain_warm.run(warm["conn"], warm["settings"]) == 0
    assert warm["calls"] == [] and warm["store"] == {}
