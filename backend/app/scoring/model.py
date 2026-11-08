"""OWNER: AI/ML. Vectorized, versioned observing-condition index.

Moonlight is a zenith proxy; target separation is unavailable in this contract.
Factor points are ordered counterfactual differences, not causal attributions.
"""
from __future__ import annotations

from dataclasses import fields
import json
import os
from pathlib import Path

import numpy as np

from .types import FeatureBatch, ScoreBatch

_CALIBRATION = None
if os.environ.get('PLEIADES_USE_CALIBRATION', '').lower() in ('1', 'true', 'yes'):
    _path = Path(__file__).resolve().parents[3] / 'data/models/calibration.json'
    _CALIBRATION = json.loads(_path.read_text(encoding='utf-8'))
    if (_CALIBRATION.get('kind') != 'monotone_affine_dark_nelm' or not _CALIBRATION.get('enabled')
            or _CALIBRATION.get('schema_version') != 1 or _CALIBRATION.get('model_version') != 3
            or not np.isfinite([_CALIBRATION['intercept'], _CALIBRATION['slope']]).all()
            or not .1 <= _CALIBRATION['slope'] <= 2):
        raise ValueError('Calibration artifact is invalid or did not pass its evaluation gate')
MODEL_VERSION: int = 3 if _CALIBRATION else 2


def _nelm(m_total: np.ndarray) -> np.ndarray:
    return 7.93 - 5.0 * np.log10(np.power(10.0, 4.316 - m_total / 5.0) + 1.0)


def _ramp(nelm: np.ndarray) -> np.ndarray:
    return np.clip((nelm - 4.0) / 3.0, 0.0, 1.0)


def score_batch(batch: FeatureBatch) -> ScoreBatch:
    """Score N cell-hours; missing solar altitude yields an unstorable NaN.

    Unknown clouds default to 60%, never clear. Unknown sky brightness uses a
    Bortle estimate if available, otherwise a conservative 18 mag/arcsec².
    Attribution order: light pollution, calibration, moon, clouds, haze, twilight, elevation.
    Values reconcile to score minus 100 and depend on this declared order.
    """
    n = len(batch)
    for field in fields(batch):
        if np.asarray(getattr(batch, field.name)).shape != (n,):
            raise ValueError(f'{field.name} must have shape ({n},)')

    def clean(value, default, lo, hi):
        value = np.asarray(value, dtype=float)
        return np.clip(np.where(np.isfinite(value), value, default), lo, hi)

    bortle = clean(batch.bortle, 8, 1, 9)
    approximate_sky = np.interp(bortle, [1, 2, 3, 4, 5, 6, 7, 8, 9],
                                [22, 21.8, 21.5, 21.0, 20.3, 19.5, 18.8, 18, 17])
    m_sky = clean(batch.m_sky, approximate_sky, 12, 22)
    total = clean(batch.cloud_total, 60, 0, 100)
    low = clean(batch.cloud_low, total, 0, 100) / 100
    mid = clean(batch.cloud_mid, 0, 0, 100) / 100
    high = clean(batch.cloud_high, 0, 0, 100) / 100
    rh = clean(batch.rh, 80, 0, 100)
    vis = clean(batch.visibility_m, 10000, 0, 100000)
    elev = clean(batch.elevation_m, 0, 0, 9000)
    sun = clean(batch.sun_alt, np.nan, -90, 90)
    moon_alt = clean(batch.moon_alt, 45, -90, 90)
    illumination = clean(batch.moon_illum, 1, 0, 1)
    cloud = (1 - .95 * low) * (1 - .70 * mid) * (1 - .35 * high)
    haze = (1 - .25 * np.clip((rh - 70) / 30, 0, 1)) * (1 - .35 * np.clip((20000 - vis) / 20000, 0, 1))
    spread = np.asarray(batch.temp_c) - np.asarray(batch.dew_point_c)
    haze *= 1 - .10 * np.where(np.isfinite(spread), np.clip((3 - spread) / 3, 0, 1), 0)
    twilight = np.clip((-12 - sun) / 6, 0, 1)
    elevation = 1 + np.minimum(.05, elev / 10000)

    # Simplified Krisciunas-Schaefer (PASP 103, 1033, 1991), zenith sky.
    # alpha: lunar phase angle (0 full); rho: angular distance to zenith.
    alpha = np.degrees(np.arccos(np.clip(2 * illumination - 1, -1, 1)))
    rho = 90 - np.clip(moon_alt, 0, 90)
    extinction = .172 + .10 * np.clip((rh - 70) / 30, 0, 1) + .15 * np.clip((20000 - vis) / 20000, 0, 1)
    airmass = 1 / np.sqrt(1 - .96 * np.sin(np.radians(90 - np.clip(moon_alt, 0, 90))) ** 2)
    intensity = 10 ** (-.4 * (3.84 + .026 * alpha + 4e-9 * alpha ** 4))
    scatter = 10 ** 5.36 * (1.06 + np.cos(np.radians(rho)) ** 2) + 10 ** (6.15 - rho / 40)
    moon_nl = scatter * intensity * 10 ** (-.4 * extinction * airmass) * (1 - 10 ** (-.4 * extinction))
    moon_nl *= np.clip(moon_alt / 5, 0, 1)
    dark_nl = 34.08 * np.exp(20.7233 - .92104 * m_sky)
    m_total = (20.7233 - np.log((dark_nl + moon_nl) / 34.08)) / .92104
    nelm = _nelm(m_total)

    dark_nelm = _nelm(m_sky)
    dark_score = 100 * _ramp(dark_nelm)
    moon_score = 100 * _ramp(nelm)
    calibrated_score = dark_score.copy()
    if _CALIBRATION:
        # The learned labels span NELM 1–7. Preserve the original physics index
        # separately; learned mode explicitly maps that observed scale to 0–100.
        lo, hi = _CALIBRATION['input_nelm_range']
        supported = np.isfinite(batch.m_sky) & (dark_nelm >= lo) & (dark_nelm <= hi)
        calibrated_dark = np.clip(_CALIBRATION['intercept'] + _CALIBRATION['slope'] * dark_nelm, 1, 7)
        corrected_nelm = np.clip(calibrated_dark - (dark_nelm - nelm), 1, 7)
        calibrated_score = np.where(supported, 100 * (calibrated_dark - 1) / 6, dark_score)
        moon_score = np.where(supported, 100 * (corrected_nelm - 1) / 6, moon_score)
        nelm = np.where(supported, corrected_nelm, nelm)
    stages = [np.full(n, 100.0), dark_score, calibrated_score, moon_score]
    stages.append(stages[-1] * cloud)
    stages.append(stages[-1] * haze)
    stages.append(stages[-1] * twilight)
    stages.append(np.clip(stages[-1] * elevation, 0, 100))
    score = np.round(stages[-1], 1)
    names = ('light_pollution', 'calibration', 'moon', 'clouds', 'haze', 'twilight', 'elevation')
    deltas = np.diff(np.stack(stages), axis=0)
    factors = []
    for i in range(n):
        if not np.isfinite(score[i]):
            factors.append({key: 0.0 for key in names})
            continue
        row = {key: round(float(deltas[j, i]), 2) for j, key in enumerate(names)}
        row['elevation'] = round(row['elevation'] + float(score[i] - 100 - sum(row.values())), 2)
        factors.append(row)
    return ScoreBatch(score=score, nelm=np.round(nelm, 2), factors=factors)
