from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone

import pytest

from app.repo import cells as cells_repo
from app.repo import photos as photos_repo
from app.repo import scores as scores_repo
from app.repo import votes as votes_repo
from app.storage import s3
from app.workers import photo_analysis

from .conftest import FAKE_USER, make_settings

UTC = timezone.utc
PID = uuid.UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
KEY = f"photos/{PID}.jpg"


# ---- presign -------------------------------------------------------------------------

def test_presign_requires_auth(client, auth_headers):
    assert client.post("/api/photos/presign", json={"content_type": "image/jpeg", "size": 10}).status_code == 401
    resp = client.post("/api/photos/presign", json={"content_type": "image/jpeg", "size": 10},
                       headers={"Authorization": "Bearer wrong"})
    assert resp.status_code == 401
    assert resp.get_json()["error"]["code"] == "unauthorized"


def test_presign_ok(client, auth_headers, monkeypatch):
    seen = {}

    def fake_presign(key, content_type, length):
        seen.update(key=key, content_type=content_type, length=length)
        return "https://example/upload", {"Content-Type": content_type}

    monkeypatch.setattr(s3, "presign_put", fake_presign)
    resp = client.post("/api/photos/presign", json={"content_type": "IMAGE/PNG", "size": 1234}, headers=auth_headers)
    assert resp.status_code == 200
    d = resp.get_json()
    assert re.fullmatch(r"photos/[0-9a-f-]{36}\.png", d["s3_key"])
    assert d == {"upload_url": "https://example/upload", "s3_key": seen["key"], "method": "PUT",
                 "headers": {"Content-Type": "image/png"}, "expires_in": s3.PRESIGN_PUT_EXPIRES}
    assert seen["length"] == 1234


@pytest.mark.parametrize("body,status,code", [
    ({"content_type": "image/gif", "size": 10}, 415, "unsupported_media_type"),
    ({"content_type": "image/jpeg", "size": 15 * 1024 * 1024 + 1}, 413, "file_too_large"),
    ({"content_type": "image/jpeg", "size": 0}, 400, "validation_error"),
    ({"content_type": "image/jpeg"}, 400, "validation_error"),
])
def test_presign_rejections(client, auth_headers, body, status, code):
    resp = client.post("/api/photos/presign", json=body, headers=auth_headers)
    assert resp.status_code == status
    assert resp.get_json()["error"]["code"] == code


def test_presign_without_storage(monkeypatch, auth_headers):
    from app import create_app

    app = create_app(make_settings(s3_access_key=""), start_workers=False, init_db=False)
    resp = app.test_client().post("/api/photos/presign", json={"content_type": "image/jpeg", "size": 10},
                                  headers=auth_headers)
    assert resp.status_code == 503


# ---- create ----------------------------------------------------------------------------

@pytest.fixture
def create_mocks(monkeypatch):
    state = {"recent": 0, "inserted": None, "submitted": [], "head": {"size": 2048, "content_type": "image/jpeg"}}
    monkeypatch.setattr(photos_repo, "count_recent_uploads", lambda uid, since: state["recent"])
    monkeypatch.setattr(s3, "head_object", lambda key: state["head"])
    monkeypatch.setattr(cells_repo, "nearest_cell", lambda lat, lon: 17)
    monkeypatch.setattr(scores_repo, "score_for", lambda cid, hour: {"score": 66.0} if cid == 17 else None)

    def fake_insert(**kw):
        state["inserted"] = kw
        return kw["photo_id"]

    monkeypatch.setattr(photos_repo, "insert", fake_insert)
    monkeypatch.setattr(photo_analysis, "submit", lambda pid: state["submitted"].append(pid))
    return state


def test_create_photo_with_exif_time(client, auth_headers, create_mocks):
    body = {"s3_key": KEY, "lat": 42.1, "lon": -78.7, "taken_at": "2026-11-07T03:12:00Z", "caption": "Pleiades!"}
    resp = client.post("/api/photos", json=body, headers=auth_headers)
    assert resp.status_code == 201
    assert resp.get_json() == {"id": str(PID), "ai_status": "pending"}
    ins = create_mocks["inserted"]
    assert ins["photo_id"] == PID and ins["user_id"] == FAKE_USER["id"] and ins["cell_id"] == 17
    assert ins["taken_at_source"] == "exif" and ins["score_at_capture"] == 66.0
    assert ins["mime_type"] == "image/jpeg" and ins["caption"] == "Pleiades!"
    assert create_mocks["submitted"] == [PID]


def test_create_photo_without_time(client, auth_headers, create_mocks):
    resp = client.post("/api/photos", json={"s3_key": KEY, "lat": 42.1, "lon": -78.7}, headers=auth_headers)
    assert resp.status_code == 201
    ins = create_mocks["inserted"]
    assert ins["taken_at"] is None and ins["taken_at_source"] == "upload_time" and ins["score_at_capture"] is None


def test_create_photo_user_time_source(client, auth_headers, create_mocks):
    body = {"s3_key": KEY, "lat": 42.1, "lon": -78.7, "taken_at": "2026-11-07T03:00:00Z", "taken_at_source": "user"}
    assert client.post("/api/photos", json=body, headers=auth_headers).status_code == 201
    assert create_mocks["inserted"]["taken_at_source"] == "user"


@pytest.mark.parametrize("body", [
    {"s3_key": "photos/../../etc/passwd", "lat": 42, "lon": -78},
    {"s3_key": "thumbs/" + str(PID) + ".jpg", "lat": 42, "lon": -78},
    {"s3_key": KEY, "lat": 142, "lon": -78},
    {"s3_key": KEY, "lat": 42, "lon": -78, "taken_at": "2099-01-01T00:00:00Z"},
    {"s3_key": KEY, "lat": 42, "lon": -78, "unexpected": 1},
])
def test_create_photo_bad_request(client, auth_headers, create_mocks, body):
    assert client.post("/api/photos", json=body, headers=auth_headers).status_code == 400
    assert create_mocks["inserted"] is None


def test_create_photo_upload_missing(client, auth_headers, create_mocks):
    create_mocks["head"] = None
    resp = client.post("/api/photos", json={"s3_key": KEY, "lat": 42.1, "lon": -78.7}, headers=auth_headers)
    assert resp.status_code == 400
    assert resp.get_json()["error"]["code"] == "upload_not_found"


def test_create_photo_too_large_after_upload(client, auth_headers, create_mocks):
    create_mocks["head"] = {"size": 16 * 1024 * 1024, "content_type": "image/jpeg"}
    resp = client.post("/api/photos", json={"s3_key": KEY, "lat": 42.1, "lon": -78.7}, headers=auth_headers)
    assert resp.status_code == 413


def test_create_photo_rate_limited(client, auth_headers, create_mocks):
    create_mocks["recent"] = 3  # uploads_per_hour = 3 in tests
    resp = client.post("/api/photos", json={"s3_key": KEY, "lat": 42.1, "lon": -78.7}, headers=auth_headers)
    assert resp.status_code == 429
    assert resp.get_json()["error"]["code"] == "rate_limited"


def test_create_photo_duplicate(client, auth_headers, create_mocks, monkeypatch):
    def dup(**kw):
        raise photos_repo.PhotoExists(kw["s3_key"])

    monkeypatch.setattr(photos_repo, "insert", dup)
    resp = client.post("/api/photos", json={"s3_key": KEY, "lat": 42.1, "lon": -78.7}, headers=auth_headers)
    assert resp.status_code == 409
    assert create_mocks["submitted"] == []


def test_create_photo_requires_auth(client):
    assert client.post("/api/photos", json={"s3_key": KEY, "lat": 42, "lon": -78}).status_code == 401


# ---- list / detail ----------------------------------------------------------------------

def test_list_photos(client, monkeypatch):
    seen = {}

    def fake_list(bbox, sort, limit):
        seen.update(bbox=bbox.as_tuple(), sort=sort, limit=limit)
        return [{"id": PID, "lat": 42.1, "lon": -78.7, "thumb_key": f"thumbs/{PID}.jpg", "vote_count": 4,
                 "taken_at": None, "ai_status": "done", "ai_sky_quality": 7},
                {"id": uuid.UUID(int=1), "lat": 42.2, "lon": -78.6, "thumb_key": None, "vote_count": 0,
                 "taken_at": None, "ai_status": "pending", "ai_sky_quality": None}]

    monkeypatch.setattr(photos_repo, "list_markers", fake_list)
    monkeypatch.setattr(s3, "object_url", lambda key: f"https://cdn/{key}" if key else None)
    resp = client.get("/api/photos?sort=top&limit=10&bbox=-79,42,-78,43")
    assert resp.status_code == 200
    photos = resp.get_json()["photos"]
    assert seen == {"bbox": (-79.0, 42.0, -78.0, 43.0), "sort": "top", "limit": 10}
    assert photos[0]["thumb_url"] == f"https://cdn/thumbs/{PID}.jpg" and photos[0]["vote_count"] == 4
    assert photos[1]["thumb_url"] is None


def test_list_photos_bad_sort(client):
    assert client.get("/api/photos?sort=best").status_code == 400
    assert client.get("/api/photos?limit=9999").status_code == 400


DETAIL = {
    "id": PID, "username": "stargazer", "s3_key": KEY, "thumb_key": f"thumbs/{PID}.jpg", "mime_type": "image/jpeg",
    "lat": 42.1, "lon": -78.7, "cell_id": 17, "taken_at": datetime(2026, 11, 7, 3, 12, tzinfo=UTC),
    "taken_at_source": "exif", "uploaded_at": datetime(2026, 11, 7, 4, tzinfo=UTC), "caption": None,
    "score_at_capture": 66.0, "ai_status": "done", "ai_description": "Orion rising",
    "ai_objects": [{"name": "Jupiter", "type": "planet", "confidence": 0.86}], "ai_sky_quality": 7,
    "ai_milky_way_visible": False, "ai_light_pollution_notes": None, "ai_attempts": 1, "vote_count": 3,
}


def test_get_photo_anonymous(client, monkeypatch):
    monkeypatch.setattr(photos_repo, "get_detail", lambda pid: dict(DETAIL) if pid == PID else None)
    monkeypatch.setattr(s3, "object_url", lambda key: f"https://cdn/{key}" if key else None)
    d = client.get(f"/api/photos/{PID}").get_json()
    assert d["url"] == f"https://cdn/{KEY}" and d["ai_objects"][0]["name"] == "Jupiter"
    assert d["my_vote"] is None


def test_get_photo_with_my_vote(client, auth_headers, monkeypatch):
    monkeypatch.setattr(photos_repo, "get_detail", lambda pid: dict(DETAIL))
    monkeypatch.setattr(s3, "object_url", lambda key: None)
    monkeypatch.setattr(votes_repo, "get_my_vote", lambda uid, pid: -1)
    assert client.get(f"/api/photos/{PID}", headers=auth_headers).get_json()["my_vote"] == -1
    # An invalid token is treated as anonymous, not rejected.
    d = client.get(f"/api/photos/{PID}", headers={"Authorization": "Bearer nope"}).get_json()
    assert d["my_vote"] is None


def test_get_photo_404(client, monkeypatch):
    monkeypatch.setattr(photos_repo, "get_detail", lambda pid: None)
    assert client.get(f"/api/photos/{PID}").status_code == 404
    assert client.get("/api/photos/not-a-uuid").status_code == 404


# ---- votes ------------------------------------------------------------------------------

def test_vote_flow(client, auth_headers, monkeypatch):
    votes: dict = {}

    def fake_set_vote(uid, pid, value):
        if pid != PID:
            return None
        if value == 0:
            votes.pop(uid, None)
        else:
            votes[uid] = value
        return sum(votes.values())

    monkeypatch.setattr(votes_repo, "set_vote", fake_set_vote)
    url = f"/api/photos/{PID}/vote"
    assert client.post(url, json={"value": 1}, headers=auth_headers).get_json() == \
        {"photo_id": str(PID), "vote_count": 1, "my_vote": 1}
    assert client.post(url, json={"value": -1}, headers=auth_headers).get_json()["vote_count"] == -1
    assert client.post(url, json={"value": 0}, headers=auth_headers).get_json()["vote_count"] == 0
    assert client.post(url, json={"value": 2}, headers=auth_headers).status_code == 400
    assert client.post(url, json={"value": 1}).status_code == 401
    assert client.post(f"/api/photos/{uuid.UUID(int=9)}/vote", json={"value": 1}, headers=auth_headers).status_code == 404
