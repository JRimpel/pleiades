"""Contract between the backend score job and the AI/ML scoring model.

OWNER: shared. Changing these types needs a heads-up to backend (role B).

All arrays in a FeatureBatch have the same shape (N,), where one row = one (cell, hour).
Missing weather values are NaN (never None).
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np


@dataclass
class FeatureBatch:
    cell_id: np.ndarray          # int64
    valid_time: np.ndarray       # datetime64[s] (UTC)
    # static, per cell
    m_sky: np.ndarray            # mag/arcsec^2, natural + artificial (higher = darker)
    bortle: np.ndarray           # float (NaN if unknown)
    elevation_m: np.ndarray
    # weather (Open-Meteo units)
    cloud_low: np.ndarray        # % 0..100
    cloud_mid: np.ndarray        # % 0..100
    cloud_high: np.ndarray       # % 0..100
    cloud_total: np.ndarray      # % 0..100
    visibility_m: np.ndarray     # metres
    rh: np.ndarray               # % 0..100
    dew_point_c: np.ndarray
    temp_c: np.ndarray
    wind_kmh: np.ndarray
    precip_prob: np.ndarray      # % 0..100
    # astro (region centroid, per hour)
    sun_alt: np.ndarray          # degrees
    moon_alt: np.ndarray         # degrees
    moon_illum: np.ndarray       # 0..1
    moon_phase_deg: np.ndarray   # 0 = new, 180 = full

    def __len__(self) -> int:
        return int(self.cell_id.shape[0])


@dataclass
class ScoreBatch:
    score: np.ndarray                          # float, 0..100, shape (N,)
    nelm: np.ndarray                           # float, naked-eye limiting magnitude, shape (N,)
    factors: list[dict[str, float]] = field(default_factory=list)  # len N; points lost(-)/gained(+) per factor

    def __len__(self) -> int:
        return int(self.score.shape[0])
