"""Offline runtime benchmark and seam examples; no DB or Gemini credentials needed."""
import json
import argparse
import os
import sys
from dataclasses import fields
from datetime import date, datetime, timezone
from pathlib import Path
from time import perf_counter

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--trained', action='store_true')
    args = parser.parse_args()
    os.environ['PLEIADES_USE_CALIBRATION'] = '1' if args.trained else '0'
sys.path.insert(0, str(ROOT / 'backend'))
from app.astro import ephemeris
from app.ingest.score import build_feature_batch, snapshot_rows, validate_result
from app.scoring import model


def run():
    start = datetime(2026, 11, 8, 0, tzinfo=timezone.utc)
    before = perf_counter()
    astro = ephemeris.hourly_conditions(start, 72, 42.7, -78.4)
    astro_ms = (perf_counter() - before) * 1000
    grid = json.loads((ROOT / 'data/wny_grid.geojson').read_text())
    rows = []
    # Weather is an explicitly synthetic clear-sky fixture, not a live forecast.
    for cell_id, feature in enumerate(grid['features'], 1):
        p = feature['properties']
        for hour in astro:
            rows.append(dict(cell_id=cell_id, valid_time=hour.time, m_sky=p['sky_brightness_mpsas'],
                             bortle=p['bortle'], elevation_m=p['elevation_m'],
                             cloud_low=0, cloud_mid=0, cloud_high=0, cloud_total=0, rh=60,
                             visibility_m=24000, temp_c=8, dew_point_c=0, wind_kmh=5, precip_prob=0,
                             **hour.model_dump(exclude={'time'})))
    batch = build_feature_batch(rows)
    before = perf_counter()
    scored = model.score_batch(batch)
    score_ms = (perf_counter() - before) * 1000
    validate_result(batch, scored)
    stored = snapshot_rows(batch, scored, start, model.MODEL_VERSION)
    before = perf_counter()
    night = ephemeris.night_summary(42.7, -78.4, date(2026, 11, 7), 'America/New_York')
    cold_ms = (perf_counter() - before) * 1000
    before = perf_counter()
    ephemeris.night_summary(42.7, -78.4, date(2026, 11, 7), 'America/New_York')
    warm_ms = (perf_counter() - before) * 1000
    candidates = ephemeris.visible_objects(42.7, -78.4, start)
    reference_sun = np.array([hour.sun_alt for hour in astro])
    reference_moon = np.array([hour.moon_alt for hour in astro])
    reference_gate = np.clip((-12 - reference_sun) / 6, 0, 1)
    corner_errors = []
    for lat, lon in ((42, -79.8), (42, -77), (43.4, -79.8), (43.4, -77)):
        local = ephemeris.hourly_conditions(start, 72, lat, lon)
        local_sun = np.array([hour.sun_alt for hour in local])
        corner_errors.append({'lat': lat, 'lon': lon,
                              'max_sun_alt_difference_deg': float(np.max(np.abs(local_sun - reference_sun))),
                              'max_moon_alt_difference_deg': float(np.max(np.abs(np.array([h.moon_alt for h in local]) - reference_moon))),
                              'max_twilight_gate_difference': float(np.max(np.abs(np.clip((-12 - local_sun) / 6, 0, 1) - reference_gate)))})
    report = {'model_version': model.MODEL_VERSION, 'conditions': 'synthetic clear weather; real atlas + computed ephemeris',
              'cells': len(grid['features']), 'rows': len(rows), 'snapshot_rows': len(stored),
              'score_ms': round(score_ms, 2), 'astro_72h_ms': round(astro_ms, 2),
              'night_summary_cold_ms': round(cold_ms, 2), 'night_summary_warm_ms': round(warm_ms, 2),
              'finite_scores': bool(np.isfinite(scored.score).all()),
              'max_factor_reconciliation_error': float(max(abs(100 + sum(f.values()) - s) for f, s in zip(scored.factors, scored.score))),
              'centroid_validation_hourly_corners': corner_errors,
              'night_summary': night.model_dump(mode='json'), 'example_candidates': [c.model_dump() for c in candidates]}
    output = ROOT / f'data/runtime_report_v{model.MODEL_VERSION}.json'
    output.write_text(json.dumps(report, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    print(json.dumps({key: value for key, value in report.items() if key not in ('night_summary', 'example_candidates')}, indent=2))


if __name__ == '__main__':
    run()
