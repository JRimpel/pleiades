from __future__ import annotations

import io
import uuid
from datetime import datetime, timezone

import pytest
from PIL import Image

from app.ai import vision
from app.ai.types import VisionResult
from app.astro import ephemeris
from app.astro.types import CandidateObject
from app.repo import photos as photos_repo
from app.storage import s3
from app.workers import photo_analysis

UTC = timezone.utc
PID = uuid.UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")


def _jpeg() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (800, 600), (5, 5, 20)).save(buf, format="JPEG")
    return buf.getvalue()


@pytest.fixture
def env(monkeypatch):
    state = {
        "photo": {"id": PID, "s3_key": f"photos/{PID}.jpg", "thumb_key": None, "mime_type": "image/jpeg",
                  "lat": 42.1, "lon": -78.7, "taken_at": datetime(2026, 11, 7, 3, tzinfo=UTC),
                  "uploaded_at": datetime(2026, 11, 7, 4, tzinfo=UTC), "caption": "test",
                  "ai_status": "pending", "ai_attempts": 0},
        "attempts": 0, "puts": {}, "thumb": None, "result": None, "failed": None, "vision_calls": [],
    }
    monkeypatch.setattr(photo_analysis, "RETRY_DELAY_S", 0)
    monkeypatch.setattr(photos_repo, "get_for_processing", lambda pid: dict(state["photo"]) if pid == PID else None)

    def inc(pid):
        state["attempts"] += 1
        return state["attempts"]

    monkeypatch.setattr(photos_repo, "increment_attempts", inc)
    monkeypatch.setattr(photos_repo, "set_thumb", lambda pid, key: state.__setitem__("thumb", key))
    monkeypatch.setattr(photos_repo, "update_ai_result", lambda pid, **kw: state.__setitem__("result", kw))
    monkeypatch.setattr(photos_repo, "mark_failed", lambda pid, err: state.__setitem__("failed", err))
    monkeypatch.setattr(s3, "get_object_bytes", lambda key: _jpeg())
    monkeypatch.setattr(s3, "put_object", lambda key, data, ct: state["puts"].__setitem__(key, (data, ct)))
    monkeypatch.setattr(ephemeris, "visible_objects", lambda lat, lon, when: [
        CandidateObject(name="Jupiter", type="planet", alt_deg=40, az_deg=120, magnitude=-2.5)])
    return state


def _result(night=True):
    return VisionResult(is_night_sky=night, description="Jupiter over trees",
                        objects=[{"name": "Jupiter", "type": "planet", "confidence": 0.9}],
                        milky_way_visible=False, sky_quality=6, light_pollution_notes="glow to the north")


def test_process_photo_done(env, monkeypatch):
    def fake_analyze(data, mime, ctx):
        env["vision_calls"].append(ctx)
        return _result(True)

    monkeypatch.setattr(vision, "analyze_photo", fake_analyze)
    assert photo_analysis.process_photo(PID) == "done"
    assert env["thumb"] == f"thumbs/{PID}.jpg"
    data, ct = env["puts"][f"thumbs/{PID}.jpg"]
    assert ct == "image/jpeg" and data[:2] == b"\xff\xd8"
    ctx = env["vision_calls"][0]
    assert ctx.taken_at == env["photo"]["taken_at"] and ctx.candidates[0].name == "Jupiter"
    r = env["result"]
    assert r["status"] == "done" and r["sky_quality"] == 6 and r["objects"][0]["name"] == "Jupiter"
    assert env["failed"] is None and env["attempts"] == 1


def test_process_photo_rejected(env, monkeypatch):
    monkeypatch.setattr(vision, "analyze_photo", lambda d, m, c: _result(False))
    assert photo_analysis.process_photo(PID) == "rejected"
    assert env["result"]["status"] == "rejected"


def test_process_photo_uses_upload_time_without_taken_at(env, monkeypatch):
    env["photo"]["taken_at"] = None
    seen = {}
    monkeypatch.setattr(vision, "analyze_photo", lambda d, m, c: seen.setdefault("ctx", c) and _result())
    photo_analysis.process_photo(PID)
    assert seen["ctx"].taken_at == env["photo"]["uploaded_at"]


def test_process_photo_retries_then_succeeds(env, monkeypatch):
    calls = {"n": 0}

    def flaky(d, m, c):
        calls["n"] += 1
        if calls["n"] < 3:
            raise RuntimeError("503 from Gemini")
        return _result()

    monkeypatch.setattr(vision, "analyze_photo", flaky)
    assert photo_analysis.process_photo(PID) == "done"
    assert env["attempts"] == 3 and len(env["puts"]) == 1  # thumbnail made once


def test_process_photo_fails_after_max_attempts(env, monkeypatch):
    def always(d, m, c):
        raise RuntimeError("boom")

    monkeypatch.setattr(vision, "analyze_photo", always)
    assert photo_analysis.process_photo(PID) == "failed"
    assert env["attempts"] == photo_analysis.MAX_ATTEMPTS
    assert "RuntimeError: boom" in env["failed"] and env["result"] is None


def test_process_photo_skips_non_pending_and_missing(env, monkeypatch):
    monkeypatch.setattr(vision, "analyze_photo", lambda *a: pytest.fail("should not run"))
    env["photo"]["ai_status"] = "done"
    assert photo_analysis.process_photo(PID) is None
    assert photo_analysis.process_photo(uuid.UUID(int=1)) is None


def test_init_worker_survives_db_error(monkeypatch, settings):
    def broken(older_than):
        raise RuntimeError("db down")

    monkeypatch.setattr(photos_repo, "claim_stale_pending", broken)
    photo_analysis.init_worker(settings)  # must not raise
    photo_analysis.shutdown()


def test_init_worker_requeues_stale(monkeypatch, settings):
    submitted = []
    monkeypatch.setattr(photos_repo, "claim_stale_pending", lambda older_than: [PID])
    monkeypatch.setattr(photo_analysis, "submit", lambda pid: submitted.append(pid))
    photo_analysis.init_worker(settings)
    photo_analysis.shutdown()
    assert submitted == [PID]
