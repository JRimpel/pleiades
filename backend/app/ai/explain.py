"""Gemini plain-English explanation of a score.

OWNER: AI/ML (role C) — replace the body, keep the signature.
The backend enforces a timeout and caches results per (cell, hour, model_version);
on error/timeout it falls back to `fallback_explanation`.

PLACEHOLDER: template text, no Gemini call.
"""
from __future__ import annotations

from .types import ExplainContext, Explanation

_NAMES = {
    "clouds": "cloud cover", "moon": "moonlight", "light_pollution": "light pollution",
    "haze": "haze and humidity", "twilight": "twilight", "elevation": "elevation",
}


def fallback_explanation(ctx: ExplainContext) -> Explanation:
    losses = sorted(((k, v) for k, v in ctx.factors.items() if v < 0), key=lambda kv: kv[1])
    if not losses:
        summary = f"Excellent conditions around {ctx.local_time}: score {ctx.score:.0f}/100."
    else:
        worst = ", ".join(f"{_NAMES.get(k, k)} ({v:.0f} pts)" for k, v in losses[:2])
        summary = f"Score {ctx.score:.0f}/100 around {ctx.local_time}. Biggest losses: {worst}."
    tips: list[str] = []
    keys = {k for k, _ in losses[:2]}
    if "moon" in keys:
        tips.append("Wait for moonset or aim away from the Moon.")
    if "clouds" in keys:
        tips.append("Use the time slider to find a clearer hour.")
    if "light_pollution" in keys:
        tips.append("Try a spot farther from Buffalo or Rochester.")
    if "twilight" in keys:
        tips.append("Come after astronomical dusk for the darkest sky.")
    return Explanation(summary=summary, tips=tips)


def explain_score(ctx: ExplainContext) -> Explanation:
    return fallback_explanation(ctx)
