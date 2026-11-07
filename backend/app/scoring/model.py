"""Stargazing score model.

OWNER: AI/ML (role C) — replace the body of `score_batch`, keep the signature and MODEL_VERSION semantics.

This is a PLACEHOLDER implementing a simplified version of Architecture §6.2 so the
backend pipeline runs end to end. Bump MODEL_VERSION whenever the model changes.
"""
from __future__ import annotations

import numpy as np

from .types import FeatureBatch, ScoreBatch

MODEL_VERSION: int = 1

_EPS = 1e-6


def _nelm(m_total: np.ndarray) -> np.ndarray:
    return 7.93 - 5.0 * np.log10(np.power(10.0, 4.316 - m_total / 5.0) + 1.0)


def _ramp(nelm: np.ndarray) -> np.ndarray:
    return np.clip((nelm - 4.0) / 3.0, 0.0, 1.0)


def score_batch(batch: FeatureBatch) -> ScoreBatch:
    def nz(a: np.ndarray, default: float) -> np.ndarray:
        return np.where(np.isnan(a), default, a).astype(float)

    m_sky = nz(batch.m_sky, 21.0)
    low = nz(batch.cloud_low, 0.0) / 100.0
    mid = nz(batch.cloud_mid, 0.0) / 100.0
    high = nz(batch.cloud_high, 0.0) / 100.0
    rh = nz(batch.rh, 60.0)
    vis = nz(batch.visibility_m, 24000.0)
    elev = nz(batch.elevation_m, 200.0)
    sun_alt = nz(batch.sun_alt, -90.0)
    moon_alt = nz(batch.moon_alt, -90.0)
    moon_illum = nz(batch.moon_illum, 0.0)

    g_sun = np.clip((-12.0 - sun_alt) / 6.0, 0.0, 1.0)
    t_cloud = (1 - 0.95 * low) * (1 - 0.70 * mid) * (1 - 0.35 * high)
    haze = (1 - 0.25 * np.clip((rh - 70.0) / 30.0, 0, 1)) * (1 - 0.25 * np.clip((20000.0 - vis) / 20000.0, 0, 1))
    b_elev = 1 + np.minimum(0.05, np.maximum(elev, 0) / 10000.0)

    # Crude moonlight: up to ~3 mag of sky brightening for a full moon at the zenith.
    moon_delta = 3.0 * moon_illum * np.sin(np.radians(np.clip(moon_alt, 0, 90)))
    nelm_dark = _nelm(m_sky)
    nelm = _nelm(m_sky - moon_delta)
    f_lp = _ramp(nelm_dark)
    f_moon = np.where(f_lp > _EPS, _ramp(nelm) / np.maximum(f_lp, _EPS), 1.0)

    score = np.clip(100.0 * g_sun * t_cloud * haze * b_elev * f_lp * f_moon, 0.0, 100.0)

    # Log-decompose: points lost by each multiplicative term, proportional to ln(term).
    terms = {
        "twilight": g_sun, "clouds": t_cloud, "haze": haze,
        "light_pollution": f_lp, "moon": f_moon,
    }
    logs = {k: np.log(np.clip(v, _EPS, 1.0)) for k, v in terms.items()}
    total_log = sum(logs.values())
    lost = np.maximum(100.0 - score / b_elev, 0.0)  # points lost before the elevation bonus
    bonus = score - score / b_elev

    factors: list[dict[str, float]] = []
    for i in range(len(batch)):
        denom = total_log[i]
        row = {
            k: (round(float(lost[i] * logs[k][i] / denom * -1.0), 1) if denom < -_EPS else 0.0)
            for k in terms
        }
        row["elevation"] = round(float(bonus[i]), 1)
        factors.append(row)

    return ScoreBatch(score=score.round(1), nelm=nelm.round(2), factors=factors)
