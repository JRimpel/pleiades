from __future__ import annotations

import logging
import threading
import time
from collections import deque

from flask import Blueprint, request

from ..ai import chat as chat_ai
from ..ai.explain import is_configured
from ..config import current_settings
from ..errors import ApiError
from ..schemas.chat import ChatRequest
from .params import body

log = logging.getLogger(__name__)

bp = Blueprint("chat", __name__)

WINDOW_S = 60.0
_hits: dict[str, deque[float]] = {}
_hits_lock = threading.Lock()


def _rate_limit(key: str, per_minute: int) -> None:
    """Sliding one-minute window per client, in process memory (fine for one small deployment)."""
    now = time.monotonic()
    with _hits_lock:
        if len(_hits) > 10_000:  # forget idle clients so the map can't grow without bound
            for k in [k for k, q in _hits.items() if not q or now - q[-1] > WINDOW_S]:
                del _hits[k]
        hits = _hits.setdefault(key, deque())
        while hits and now - hits[0] > WINDOW_S:
            hits.popleft()
        if len(hits) >= per_minute:
            retry = max(1, int(WINDOW_S - (now - hits[0])) + 1)
            raise ApiError(429, "rate_limited", f"Too many questions. Try again in {retry} s.",
                           {"retry_after_s": retry})
        hits.append(now)


def _client_key() -> str:
    """The caller's IP. Behind the local nginx (infra/nginx.conf), trust only the hop nginx appended."""
    addr = request.remote_addr or "unknown"
    forwarded = request.headers.get("X-Forwarded-For", "")
    if addr in ("127.0.0.1", "::1") and forwarded:
        return forwarded.split(",")[-1].strip() or addr
    return addr


def reset_rate_limits() -> None:
    with _hits_lock:
        _hits.clear()


@bp.post("/chat")
def post_chat():
    settings = current_settings()
    req = ChatRequest.model_validate(body())
    if not is_configured():
        raise ApiError(503, "chat_unavailable", "The assistant needs GEMINI_API_KEY and GEMINI_MODEL on the server")
    _rate_limit(_client_key(), settings.chat_per_minute)
    try:
        resp = chat_ai.chat(req.messages, req.context)
    except Exception as e:  # noqa: BLE001 - any Gemini/SDK failure becomes one friendly error
        log.warning("chat failed: %s: %s", type(e).__name__, e)
        raise ApiError(502, "chat_failed", "The assistant couldn't answer just now. Please try again.") from e
    return resp.model_dump(mode="json")
