"""Prepare real atlas-derived WNY cells; optionally merge without deleting IDs.

The existing development script supplies grid geometry, rough lake masks, and
curated spot coordinates only. Its synthetic brightness function is never used.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import runpy
import sys
from pathlib import Path

import numpy as np

from atlas import sample_atlas

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))


def build(atlas_path, elevations=True):
    seed = runpy.run_path(str(ROOT / 'backend/scripts/seed_dev_grid.py'))
    cells = [(None, False, lat, lon) for lat, lon in seed['grid_points']()]
    cells += [(name, True, lat, lon) for name, lat, lon in seed['CURATED_SPOTS']]
    brightness = sample_atlas(atlas_path, [c[2] for c in cells], [c[3] for c in cells])
    if not np.isfinite(brightness).all():
        raise ValueError('Missing atlas samples: refusing to invent sky brightness')
    elevation = [None] * len(cells)
    if elevations:
        from app.ingest.openmeteo import fetch_elevations
        elevation = fetch_elevations([(lat, lon) for _, _, lat, lon in cells])
    features = []
    for (name, curated, lat, lon), m, elev in zip(cells, brightness, elevation):
        if elev is not None and not np.isfinite(elev):
            elev = None
        features.append({'type': 'Feature', 'geometry': {'type': 'Point', 'coordinates': [lon, lat]},
                         'properties': {'name': name, 'is_curated': curated, 'elevation_m': elev,
                                        'sky_brightness_mpsas': round(float(m), 4),
                                        'bortle': seed['bortle_from_mpsas'](float(m))}})
    return {'type': 'FeatureCollection', 'features': features,
            'metadata': {'atlas_doi': '10.5880/GFZ.1.4.2016.001', 'paper_doi': '10.1126/sciadv.1600377',
                         'license': 'CC BY-NC 4.0', 'raster_units': 'artificial mcd/m2',
                         'natural_background_mcd_m2': .171, 'grid_step_deg': .1,
                         'elevation_source': 'Open-Meteo' if elevations else 'not fetched',
                         'bortle': 'approximate brightness-derived class',
                         'geometry_limitations': 'Reuses rough development lake polygons; shoreline accuracy is limited.'}}


def merge(collection):
    """Update exact existing centres or add new cells, preserving referenced IDs."""
    import psycopg
    from app.config import get_settings

    url = get_settings().database_url
    if not url:
        raise ValueError('DATABASE_URL is required only with --load')
    with psycopg.connect(url) as conn:
        # Single transaction + table lock prevents duplicate centre insertion.
        conn.execute('LOCK TABLE grid_cells IN SHARE ROW EXCLUSIVE MODE')
        for feature in collection['features']:
            lon, lat = feature['geometry']['coordinates']
            p = feature['properties']
            existing = conn.execute('SELECT id FROM grid_cells WHERE is_curated=%s AND ST_DWithin(geom, ST_SetSRID(ST_MakePoint(%s,%s),4326)::geography,1)',
                                    (p['is_curated'], lon, lat)).fetchall()
            if len(existing) > 1:
                raise ValueError('Ambiguous duplicate grid centres; resolve before loading')
            if existing:
                conn.execute('UPDATE grid_cells SET name=COALESCE(%s,name), elevation_m=COALESCE(%s,elevation_m), sky_brightness_mpsas=%s, bortle=%s WHERE id=%s',
                             (p['name'], p['elevation_m'], p['sky_brightness_mpsas'], p['bortle'], existing[0][0]))
            else:
                conn.execute('INSERT INTO grid_cells (geom,name,is_curated,elevation_m,sky_brightness_mpsas,bortle) VALUES (ST_SetSRID(ST_MakePoint(%s,%s),4326)::geography,%s,%s,%s,%s,%s)',
                             (lon, lat, p['name'], p['is_curated'], p['elevation_m'], p['sky_brightness_mpsas'], p['bortle']))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--atlas', type=Path, default=ROOT / 'data/raw/World_Atlas_2015.tif')
    parser.add_argument('--output', type=Path, default=ROOT / 'data/wny_grid.geojson')
    parser.add_argument('--no-elevation', action='store_true')
    parser.add_argument('--load', action='store_true', help='Merge into configured DB without deleting existing rows/IDs')
    args = parser.parse_args()
    result = build(args.atlas, elevations=not args.no_elevation)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    if args.load:
        merge(result)
    print(f"Prepared {len(result['features'])} real atlas-derived cells: {args.output}")
