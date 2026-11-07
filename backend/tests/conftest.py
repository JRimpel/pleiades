"""Shared fixtures. Nothing here touches a database or the network."""
from __future__ import annotations

import uuid

import pytest

from app import create_app
from app.auth import hash_token
from app.config import Settings
from app.repo import users as users_repo
from app.storage import s3

GOOD_TOKEN = "good-token"
FAKE_USER = {"id": uuid.UUID("11111111-1111-1111-1111-111111111111"), "username": "stargazer"}


def make_settings(**overrides) -> Settings:
    values = dict(
        database_url="",
        s3_endpoint="https://s3.us-east-1.amazonaws.com",
        s3_region="us-east-1",
        s3_access_key="testing",
        s3_secret_key="testing",
        s3_bucket="pleiades-test",
        public_app_origin="http://localhost:5173",
        uploads_per_hour=3,
        explain_timeout_s=1.0,
    )
    values.update(overrides)
    return Settings(**values)


@pytest.fixture
def settings() -> Settings:
    return make_settings()


@pytest.fixture
def app(settings):
    s3.reset_client()
    flask_app = create_app(settings, start_workers=False, init_db=False)
    flask_app.config.update(TESTING=True)
    yield flask_app
    s3.reset_client()


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def fake_user() -> dict:
    return dict(FAKE_USER)


@pytest.fixture
def auth_headers(monkeypatch) -> dict[str, str]:
    """Bearer headers for FAKE_USER; any other token is rejected."""
    monkeypatch.setattr(
        users_repo, "get_by_token_hash",
        lambda h: dict(FAKE_USER) if h == hash_token(GOOD_TOKEN) else None,
    )
    return {"Authorization": f"Bearer {GOOD_TOKEN}"}
