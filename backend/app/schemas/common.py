from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

ScoreLabel = Literal["Excellent", "Good", "Fair", "Poor"]

# Keys used in the `factors` breakdown (points lost/gained per factor). The AI/ML model
# may add keys; the frontend should render unknown keys generically.
FACTOR_KEYS: tuple[str, ...] = ("clouds", "moon", "light_pollution", "haze", "twilight", "elevation")


def score_label(score: float | None) -> ScoreLabel | None:
    if score is None:
        return None
    if score >= 75:
        return "Excellent"
    if score >= 50:
        return "Good"
    if score >= 25:
        return "Fair"
    return "Poor"


def top_factor(factors: dict[str, float] | None) -> str | None:
    """The factor that cost the most points (most negative value), or None if nothing was lost."""
    if not factors:
        return None
    key, value = min(factors.items(), key=lambda kv: kv[1])
    return key if value < 0 else None


class ApiModel(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class ErrorDetail(BaseModel):
    code: str
    message: str
    details: object | None = None


class ErrorResponse(BaseModel):
    error: ErrorDetail
