from __future__ import annotations

from datetime import datetime
from typing import Literal

from .common import ApiModel


class HealthResponse(ApiModel):
    status: Literal["ok", "degraded"]
    db: bool
    storage: bool
    last_weather_fetch: datetime | None
    last_score_run: datetime | None
    model_version: int
