import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
import requests

from app.ingest import openmeteo

FIXTURE = Path(__file__).parent / "fixtures" / "openmeteo_multi.json"
FETCHED_AT = datetime(2026, 11, 7, 21, 0, tzinfo=timezone.utc)


@pytest.fixture
def payload():
    return json.loads(FIXTURE.read_text())


def test_parse_response_shape_and_order(payload):
    rows = openmeteo.parse_response(payload, [11, 22], FETCHED_AT)
    assert len(rows) == 2 * 3
    assert all(len(r) == len(openmeteo.WEATHER_COLUMNS) for r in rows)
    first = rows[0]
    assert first[0] == datetime.fromtimestamp(1794027600, tz=timezone.utc)
    assert first[0].tzinfo is not None
    assert first[1] == 11
    assert first[2] == FETCHED_AT
    # cloud_low, cloud_mid, cloud_high, cloud_total, visibility_m, rh, dew_point_c, temp_c, wind_kmh, precip_prob
    assert first[3:] == (10.0, 0.0, 35.0, 40.0, 24140.0, 71.0, -1.2, 3.8, 12.4, 0.0)
    assert [r[1] for r in rows] == [11, 11, 11, 22, 22, 22]


def test_parse_response_none_handling(payload):
    rows = openmeteo.parse_response(payload, [11, 22], FETCHED_AT)
    assert rows[2][-1] is None  # precipitation_probability null
    assert rows[3][7] is None   # visibility null for location 2, hour 0
    # A variable missing entirely becomes None for every hour.
    del payload[0]["hourly"]["wind_speed_10m"]
    rows = openmeteo.parse_response(payload, [11, 22], FETCHED_AT)
    assert all(r[11] is None for r in rows[:3])
    assert rows[3][11] == 6.1


def test_single_location_dict_is_normalized(payload):
    rows = openmeteo.parse_response(payload[0], [5], FETCHED_AT)
    assert len(rows) == 3 and {r[1] for r in rows} == {5}


def test_parse_response_count_mismatch(payload):
    with pytest.raises(openmeteo.OpenMeteoError):
        openmeteo.parse_response(payload, [1], FETCHED_AT)


def test_chunks():
    assert [list(c) for c in openmeteo.chunks(list(range(7)), 3)] == [[0, 1, 2], [3, 4, 5], [6]]
    assert list(openmeteo.chunks([], 50)) == []
    assert len(list(openmeteo.chunks(list(range(356)), 50))) == 8
    with pytest.raises(ValueError):
        list(openmeteo.chunks([1], 0))


class FakeResponse:
    def __init__(self, status, body=None):
        self.status_code = status
        self._body = body
        self.text = json.dumps(body) if body is not None else "error"

    def json(self):
        return self._body


class FakeSession:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def get(self, url, params=None, timeout=None):
        self.calls.append((url, params))
        r = self.responses.pop(0)
        if isinstance(r, Exception):
            raise r
        return r


def test_fetch_batch_params_and_success(payload):
    session = FakeSession([FakeResponse(200, payload)])
    out = openmeteo.fetch_batch([(42.9, -78.9), (42.1, -78.7)], 72, session, sleep=lambda s: None)
    assert len(out) == 2
    url, params = session.calls[0]
    assert url == openmeteo.FORECAST_URL
    assert params["latitude"] == "42.9000,42.1000"
    assert params["longitude"] == "-78.9000,-78.7000"
    assert params["hourly"].split(",") == list(openmeteo.HOURLY_VARS)
    assert params["timezone"] == "UTC" and params["timeformat"] == "unixtime"
    assert params["wind_speed_unit"] == "kmh" and params["forecast_hours"] == 72


def test_fetch_batch_retries_then_succeeds(payload):
    sleeps = []
    session = FakeSession([
        FakeResponse(429), requests.ConnectionError("boom"), FakeResponse(503), FakeResponse(200, payload),
    ])
    out = openmeteo.fetch_batch([(42.9, -78.9), (42.1, -78.7)], 72, session, sleep=sleeps.append)
    assert len(out) == 2
    assert len(session.calls) == 4
    assert sleeps == [1.0, 2.0, 4.0]


def test_fetch_batch_gives_up_after_max_attempts():
    session = FakeSession([FakeResponse(500)] * openmeteo.MAX_ATTEMPTS)
    with pytest.raises(openmeteo.OpenMeteoError):
        openmeteo.fetch_batch([(42.9, -78.9)], 72, session, sleep=lambda s: None)
    assert len(session.calls) == openmeteo.MAX_ATTEMPTS


def test_fetch_batch_does_not_retry_client_errors():
    session = FakeSession([FakeResponse(400, {"error": True, "reason": "bad"})])
    with pytest.raises(openmeteo.OpenMeteoError):
        openmeteo.fetch_batch([(42.9, -78.9)], 72, session, sleep=lambda s: None)
    assert len(session.calls) == 1


def test_fetch_elevations_batches():
    coords = [(42.0 + i * 0.001, -78.0) for i in range(150)]
    session = FakeSession([
        FakeResponse(200, {"elevation": [100.0] * 100}),
        FakeResponse(200, {"elevation": [200.0] * 50}),
    ])
    out = openmeteo.fetch_elevations(coords, session, sleep=lambda s: None)
    assert len(out) == 150 and out[0] == 100.0 and out[-1] == 200.0
    assert session.calls[0][0] == openmeteo.ELEVATION_URL
