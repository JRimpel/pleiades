"""Fetch real weather for three WNY spots and exercise scoring without a DB.

Local fixture ordinals are not database IDs. Stored output is a timestamped
integration artifact, not an API replacement or an always-current forecast.
"""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
from app.astro.ephemeris import hourly_conditions
from app.ingest.openmeteo import WEATHER_COLUMNS, fetch_batch, parse_response
from app.ingest.score import build_feature_batch, validate_result
from app.scoring import model


def main():
    grid = json.loads((ROOT / 'data/wny_grid.geojson').read_text())
    names = ['Allegany State Park', 'Beaver Meadow Audubon Center', 'Chestnut Ridge Park']
    spots = [next(f for f in grid['features'] if f['properties']['name'] == name) for name in names]
    coords = [(f['geometry']['coordinates'][1], f['geometry']['coordinates'][0]) for f in spots]
    fetched = datetime.now(timezone.utc)
    payload = fetch_batch(coords, 24)
    weather = [dict(zip(WEATHER_COLUMNS, row)) for row in parse_response(payload, [1, 2, 3], fetched)]
    rows = []
    for ordinal, feature in enumerate(spots, 1):
        local = [row for row in weather if row['cell_id'] == ordinal]
        if not local:
            raise ValueError('Empty live forecast')
        lat, lon = coords[ordinal - 1]
        astro = {a.time: a for a in hourly_conditions(local[0]['valid_time'], len(local), lat, lon)}
        p = feature['properties']
        for row in local:
            a = astro[row['valid_time']]
            rows.append({**row, 'm_sky': p['sky_brightness_mpsas'], 'bortle': p['bortle'],
                         'elevation_m': p['elevation_m'], **a.model_dump(exclude={'time'})})
    batch = build_feature_batch(rows)
    result = model.score_batch(batch)
    validate_result(batch, result)
    report = {'fetched_at': fetched.isoformat(), 'weather_source': 'Open-Meteo live Forecast API',
              'static_source': grid['metadata'], 'model_version': model.MODEL_VERSION,
              'note': 'fixture ordinals are not database cell IDs; exact per-spot ephemeris used', 'points': []}
    for row, score, nelm, factors in zip(rows, result.score, result.nelm, result.factors):
        report['points'].append({'spot_name': names[row['cell_id'] - 1], 'valid_time': row['valid_time'].isoformat(),
                                 'score': float(score), 'nelm': float(nelm), 'factors': factors,
                                 'cloud_total': row['cloud_total'], 'sun_alt': row['sun_alt'],
                                 'moon_alt': row['moon_alt'], 'moon_illum': row['moon_illum']})
    (ROOT / 'data/live_weather_report.json').write_text(json.dumps(report, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    print(json.dumps({'spots': names, 'scored_hours': len(rows), 'model_version': model.MODEL_VERSION,
                      'fetched_at': fetched.isoformat()}, indent=2))


if __name__ == '__main__':
    main()
