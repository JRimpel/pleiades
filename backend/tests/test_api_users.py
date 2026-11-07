from __future__ import annotations

import uuid

from app.auth import hash_token
from app.repo import users as users_repo


def test_create_user(client, monkeypatch):
    captured = {}

    def fake_create(username, token_hash):
        captured.update(username=username, token_hash=token_hash)
        return {"id": uuid.UUID(int=7), "username": username}

    monkeypatch.setattr(users_repo, "create", fake_create)
    resp = client.post("/api/users", json={"username": "orion_fan"})
    assert resp.status_code == 201
    data = resp.get_json()
    assert data["username"] == "orion_fan"
    assert data["user_id"] == str(uuid.UUID(int=7))
    assert captured["token_hash"] == hash_token(data["token"])  # only the hash is stored


def test_create_user_taken(client, monkeypatch):
    def taken(username, token_hash):
        raise users_repo.UsernameTaken(username)

    monkeypatch.setattr(users_repo, "create", taken)
    resp = client.post("/api/users", json={"username": "orion_fan"})
    assert resp.status_code == 409
    assert resp.get_json()["error"]["code"] == "username_taken"


def test_create_user_validation(client):
    for body in ({}, {"username": "ab"}, {"username": "has space"}, {"username": "x" * 40}, None):
        resp = client.post("/api/users", json=body)
        assert resp.status_code == 400, body
        assert resp.get_json()["error"]["code"] == "validation_error"


def test_unknown_route_is_json_404(client):
    resp = client.get("/api/nope")
    assert resp.status_code == 404
    assert resp.get_json()["error"]["code"] == "not_found"
