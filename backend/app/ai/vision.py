"""Gemini vision analysis of uploaded sky photos.

OWNER: AI/ML (role C) — replace the body, keep the signature.
Called from a background thread; may block. Raise on failure (the worker retries).

PLACEHOLDER: returns a neutral result without calling Gemini.
"""
from __future__ import annotations

from .types import VisionContext, VisionObject, VisionResult


def analyze_photo(image_bytes: bytes, mime_type: str, ctx: VisionContext) -> VisionResult:
    objects = [VisionObject(name=c.name, type=c.type, confidence=0.5) for c in ctx.candidates if c.type == "moon"]
    return VisionResult(
        is_night_sky=True,
        description="Placeholder analysis: AI vision is not wired up yet.",
        objects=objects,
        milky_way_visible=False,
        sky_quality=5,
        light_pollution_notes=None,
    )
