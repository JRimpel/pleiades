"""Chat assistant: tool dispatch, round limit and API errors, with a scripted fake Gemini (offline)."""
from __future__ import annotations

from datetime import date, datetime, timezone

import pytest
from google.genai import types

from app.ai import chat as chat_ai
from app.ai import chat_tools
from app.api import chat as chat_api
from app.config import Settings
from app.repo import cells as cells_repo
from app.repo import scores as scores_repo
from app.schemas.chat import ChatContext

UTC = timezone.utc
BEST_ROW = {"cell_id": 42, "name": "Allegany State Park", "is_curated": True, "bortle": 3, "lat": 42.1,
            "lon": -78.75, "score": 72.3, "valid_time": datetime(2026, 11, 9, 4, tzinfo=UTC), "distance_km": None}


def call_response(*calls: tuple[str, dict]) -> types.GenerateContentResponse:
    parts = [types.Part(function_call=types.FunctionCall(id=f"c{i}", name=n, args=a)) for i, (n, a) in enumerate(calls)]
    return types.GenerateContentResponse(candidates=[types.Candidate(content=types.Content(role="model", parts=parts))])


def text_response(text: str) -> types.GenerateContentResponse:
    return types.GenerateContentResponse(
        candidates=[types.Candidate(content=types.Content(role="model", parts=[types.Part(text=text)]))])


class FakeGemini:
    """Replays scripted responses and records each request's contents and config."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.requests: list[dict] = []
        self.models = self

    def generate_content(self, *, model, contents, config):
        self.requests.append({"contents": list(contents), "config": config})
        return self.responses.pop(0) if len(self.responses) > 1 else self.responses[0]


@pytest.fixture
def gemini(monkeypatch):
    chat_api.reset_rate_limits()
    monkeypatch.setattr(chat_ai, "is_configured", lambda: True)
    monkeypatch.setattr(chat_api, "is_configured", lambda: True)

    def install(*responses):
        fake = FakeGemini(responses)
        monkeypatch.setattr(chat_ai, "_client", lambda key, timeout: fake)
        return fake

    yield install
    chat_api.reset_rate_limits()


def ask(client, text="Best spot tonight?", **context):
    return client.post("/api/chat", json={"messages": [{"role": "user", "content": text}], "context": context})


def test_tool_results_ground_the_reply_and_spots(client, gemini, monkeypatch):
    seen = {}

    def best_for_night(night, tz, near, radius_km, limit):
        seen.update(night=night, near=near, radius_km=radius_km)
        return [dict(BEST_ROW)]

    monkeypatch.setattr(scores_repo, "best_for_night", best_for_night)
    fake = gemini(call_response(("best_spots", {"lat": 42.89, "lon": -78.88})),
                  text_response("Head to Allegany State Park around 11 PM: score 72, Good."))

    resp = ask(client, location={"lat": 42.89, "lon": -78.88}, time="2026-11-09T04:00:00Z")
    assert resp.status_code == 200, resp.get_json()
    d = resp.get_json()
    assert d["reply"].startswith("Head to Allegany")
    assert d["tool_calls"] == [{"name": "best_spots", "args": {"lat": 42.89, "lon": -78.88}}]
    assert d["spots"] == [{"cell_id": 42, "name": "Allegany State Park", "lat": 42.1, "lon": -78.75, "score": 72.3,
                           "label": "Good", "valid_time": "2026-11-09T04:00:00Z"}]
    assert seen["near"] == (42.89, -78.88) and seen["radius_km"] == 60.0

    # The second request echoes the model's call and carries our tool result back.
    second = fake.requests[1]["contents"]
    assert second[1].parts[0].function_call.name == "best_spots"
    result = second[2].parts[0].function_response
    assert result.id == "c0" and result.response["result"]["spots"][0]["score"] == 72.3
    assert result.response["result"]["spots"][0]["best_time_local"] == "Sun Nov 8, 11:00 PM"
    # The app context reaches the model as data in the system instruction.
    system = fake.requests[0]["config"].system_instruction
    assert "In Buffalo" in system and "Sun Nov 8, 11:00 PM" in system


def test_round_limit_forces_a_text_answer(client, gemini, monkeypatch):
    monkeypatch.setattr(scores_repo, "best_for_night", lambda *a: [])
    # A model that would call tools forever; the final round (tools disabled) answers in text.
    fake = gemini(*[call_response(("best_spots", {}))] * chat_ai.MAX_TOOL_ROUNDS, text_response("No scores yet."))

    d = ask(client).get_json()
    assert d["reply"] == "No scores yet."
    assert len(fake.requests) == chat_ai.MAX_TOOL_ROUNDS + 1
    modes = [r["config"].tool_config.function_calling_config.mode for r in fake.requests]
    assert modes[-1] == types.FunctionCallingConfigMode.NONE
    assert all(m == types.FunctionCallingConfigMode.AUTO for m in modes[:-1])
    assert len(d["tool_calls"]) == chat_ai.MAX_TOOL_ROUNDS and d["spots"] == []


def test_every_call_gets_a_response_even_past_the_per_turn_cap(client, gemini, monkeypatch):
    monkeypatch.setattr(scores_repo, "best_for_night", lambda *a: [])
    many = [("best_spots", {})] * (chat_ai.MAX_CALLS_PER_ROUND + 2)
    fake = gemini(call_response(*many), text_response("ok"))
    d = ask(client).get_json()
    responses = fake.requests[1]["contents"][2].parts
    assert len(responses) == len(many)
    assert "skipped" in responses[-1].function_response.response["result"]["error"]
    assert len(d["tool_calls"]) == chat_ai.MAX_CALLS_PER_ROUND


def test_unknown_tool_and_bad_args_go_back_to_the_model(client, gemini):
    fake = gemini(call_response(("drop_tables", {}), ("spot_conditions", {"cell_id": "abc"})), text_response("Sorry."))
    assert ask(client).status_code == 200
    results = [p.function_response.response["result"] for p in fake.requests[1]["contents"][2].parts]
    assert results[0] == {"error": "unknown tool 'drop_tables'"}
    assert results[1] == {"error": "cell_id must be an integer"}


def test_unconfigured_gemini_is_503(client):
    resp = ask(client)
    assert resp.status_code == 503 and resp.get_json()["error"]["code"] == "chat_unavailable"


def test_gemini_failure_is_502(client, gemini, monkeypatch):
    class Boom:
        models = property(lambda self: self)

        def generate_content(self, **kw):
            raise RuntimeError("upstream 500")

    monkeypatch.setattr(chat_ai, "_client", lambda key, timeout: Boom())
    resp = ask(client)
    assert resp.status_code == 502 and resp.get_json()["error"]["code"] == "chat_failed"


@pytest.mark.parametrize("payload", [
    {"messages": []},
    {"messages": [{"role": "assistant", "content": "hi"}]},
    {"messages": [{"role": "user", "content": "x" * 1001}]},
    {"messages": [{"role": "user", "content": "hi"}], "context": {"viewport": {"west": 1, "south": 0, "east": 0, "north": 1}}},
])
def test_invalid_requests_are_400(client, gemini, payload):
    assert client.post("/api/chat", json=payload).status_code == 400


def test_rate_limit_per_client(client, gemini):
    gemini(text_response("Clear skies!"))
    for _ in range(10):
        assert ask(client).status_code == 200
    resp = ask(client)
    assert resp.status_code == 429 and resp.get_json()["error"]["code"] == "rate_limited"
    # Another client behind the same nginx has its own window.
    other = client.post("/api/chat", json={"messages": [{"role": "user", "content": "hi"}]},
                        headers={"X-Forwarded-For": "203.0.113.9"})
    assert other.status_code == 200


# ---- tools, called directly ------------------------------------------------------------

@pytest.fixture
def state():
    return chat_tools.ToolState(settings=Settings(), context=ChatContext())


def test_when_visible_orion_uses_the_real_ephemeris(state):
    result = chat_tools.dispatch(state, "when_visible", {"object_name": "orion", "night": "2026-11-08",
                                                         "lat": 42.89, "lon": -78.88})
    assert result["found"] is True and result["object"] == "Orion"
    # Orion is a late-evening object in November: up well before dawn, not at dusk.
    assert result["first_hour_above_20deg"].startswith(("Sun Nov 8, 10", "Sun Nov 8, 11", "Mon Nov 9, 12"))
    assert all(h["alt_deg"] > 0 for h in result["hours_above_horizon"])


def test_when_visible_aliases_and_misses(state):
    assert chat_tools.dispatch(state, "when_visible", {"object_name": "Big Dipper", "night": "2026-11-08"})["object"] == "Ursa Major"
    miss = chat_tools.dispatch(state, "when_visible", {"object_name": "Leonids", "night": "2026-11-08"})
    assert miss["found"] is False and "Leo" in miss["catalog_objects_up_that_night"]


def test_find_place_falls_back_to_the_town_list(state, monkeypatch):
    monkeypatch.setattr(cells_repo, "find_by_name", lambda name, limit=3: [])
    monkeypatch.setattr(cells_repo, "nearest_cell", lambda lat, lon: 7)
    monkeypatch.setattr(chat_tools, "_geocode", lambda name: pytest.fail("towns should answer first"))
    result = chat_tools.dispatch(state, "find_place", {"name": "Ellicottville, NY"})
    assert result["matches"][0]["name"] == "Ellicottville" and result["matches"][0]["nearest_cell_id"] == 7


def test_describe_location_matches_frontend_naming():
    assert chat_tools.describe_location(42.89, -78.88) == "In Buffalo"
    # Hamburg (42.72, -78.83) is the nearest listed town to this point.
    assert chat_tools.describe_location(42.75, -78.82) == "2 mi N of Hamburg"


def test_naive_tool_times_are_local(state, monkeypatch):
    seen = {}
    monkeypatch.setattr(scores_repo, "best_at", lambda hour, *a: seen.setdefault("hour", hour) and [])
    chat_tools.dispatch(state, "best_spots", {"time": "2026-11-08T23:00"})
    assert seen["hour"] == datetime(2026, 11, 9, 4, tzinfo=UTC)
    assert chat_tools._night(state, "2026-11-08") == date(2026, 11, 8)
