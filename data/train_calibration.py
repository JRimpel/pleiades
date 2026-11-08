"""Train a monotone dark-sky NELM calibration from real observations.

Run from repo root with the backend environment; see data/README.md.
No scikit-learn/pickle dependency. Only two fitted coefficients are deployed.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import sys
import zipfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from skyfield.api import wgs84

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
from app.astro.ephemeris import _resources  # noqa: E402
from app.scoring.model import _nelm  # noqa: E402
from atlas import sample_atlas  # noqa: E402

ARCHIVE_URL = 'https://datapub.gfz.de/download/10.5880.GFZ.1.4.2022.008-Mcvwue/2022-008_Kyba-et-al_GaN-code-and-data.zip'
MEMBER = 'GaN_code_and_data_with_license/data/GaN_2011-2022.8_clear_sky_night_only.csv'


def digest(path):
    h = hashlib.sha256()
    with open(path, 'rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def fit_monotone(x, y):
    # Ridge on slope toward 1; intercept unpenalized. Clamp to physical monotonicity.
    centered = x - x.mean()
    slope = float(np.clip((np.dot(centered, y - y.mean()) + 1) / (np.dot(centered, centered) + 1), .1, 2))
    return float(y.mean() - slope * x.mean()), slope


def metrics(y, predicted):
    error = np.asarray(predicted) - y
    return {'mae_mag': float(np.abs(error).mean()), 'rmse_mag': float(np.sqrt(np.mean(error ** 2))),
            'bias_mag': float(error.mean()), 'n': len(y)}


def prepare(archive, raster):
    rejected = Counter()
    records, seen = [], set()
    with zipfile.ZipFile(archive) as z:
        for row in csv.reader(io.StringIO(z.read(MEMBER).decode('utf-8-sig'))):
            try:
                ident, lat, lon, utc_date, utc_time, _, _, label, sqm, _, clouds, _, _ = row
                when = datetime.fromisoformat(utc_date + 'T' + utc_time).replace(tzinfo=timezone.utc)
                lat, lon, label = float(lat), float(lon), float(label)
                if not 2014 <= when.year <= 2017:
                    rejected['outside_2014_2017_atlas_window'] += 1
                    continue
                if clouds != 'clear' or not 1 <= label <= 7 or not -65 <= lat <= 75 or not -180 <= lon <= 180:
                    rejected['invalid_label_location_or_clouds'] += 1
                    continue
                # Authors warn that NELM paired with SQM can be automatically filled.
                if sqm.strip() and float(sqm) > 1:
                    rejected['sqm_pair_potential_automatic_label'] += 1
                    continue
                key = (round(lat, 4), round(lon, 4), when.isoformat())
                if key in seen:
                    rejected['duplicate_location_time'] += 1
                    continue
                seen.add(key)
                records.append({'id': ident, 'lat': lat, 'lon': lon, 'when': when, 'label': label})
            except (ValueError, IndexError):
                rejected['parse_error'] += 1
    if not records:
        raise ValueError('No usable observations')
    ts, eph = _resources()
    kept = []
    for offset in range(0, len(records), 512):
        part = records[offset:offset + 512]
        t = ts.from_datetimes([r['when'] for r in part])
        obs = (eph['earth'] + wgs84.latlon(np.array([r['lat'] for r in part]), np.array([r['lon'] for r in part]))).at(t)
        solar = obs.observe(eph['sun']).apparent().altaz()[0].degrees
        lunar = obs.observe(eph['moon']).apparent().altaz()[0].degrees
        for r, sun, moon in zip(part, solar, lunar):
            if sun < -18 and moon < -5:
                kept.append(r)
            else:
                rejected['sun_or_moon_not_dark'] += 1
    sky = sample_atlas(raster, [r['lat'] for r in kept], [r['lon'] for r in kept])
    final = []
    for record, brightness in zip(kept, sky):
        if np.isfinite(brightness) and 15 <= brightness <= 22.1:
            record['m_sky'] = float(brightness)
            # Block nearby observations together; no exact locations in the output manifest.
            record['group'] = f"{np.floor(record['lat'] / 2):.0f}:{np.floor(record['lon'] / 2):.0f}"
            final.append(record)
        else:
            rejected['invalid_atlas_sample'] += 1
    return final, dict(rejected)


def train(archive, raster, output):
    records, rejected = prepare(archive, raster)
    if len(records) < 100:
        raise ValueError('Need at least 100 usable observations for this experiment')
    x = _nelm(np.array([r['m_sky'] for r in records]))
    y = np.array([r['label'] for r in records])
    # Spatial blocks and dates are disjoint. Rows crossing either boundary are
    # embargoed, so neither a nearby site nor a repeated night leaks into test.
    groups = sorted({r['group'] for r in records})
    rng = np.random.default_rng(2026)
    rng.shuffle(groups)
    test_groups = set(groups[:max(1, len(groups) // 5)])
    train_mask = np.array([r['group'] not in test_groups and r['when'].year <= 2016 for r in records])
    test_mask = np.array([r['group'] in test_groups and r['when'].year == 2017 for r in records])
    if train_mask.sum() < 50 or test_mask.sum() < 30:
        raise ValueError('Insufficient disjoint spatial/temporal train and test samples')
    intercept, slope = fit_monotone(x[train_mask], y[train_mask])
    prediction = np.clip(intercept + slope * x[test_mask], 1, 7)
    baseline = metrics(y[test_mask], x[test_mask])
    learned = metrics(y[test_mask], prediction)
    constant = metrics(y[test_mask], np.full(test_mask.sum(), y[train_mask].mean()))
    bootstrap = np.random.default_rng(2027)
    differences = []
    test_block = np.array([r['group'] for r, flag in zip(records, test_mask) if flag])
    block_errors = []
    for group in sorted(set(test_block)):
        select = test_block == group
        block_errors.append((np.abs(prediction[select] - y[test_mask][select]) - np.abs(x[test_mask][select] - y[test_mask][select])).mean())
    for _ in range(1000):
        differences.append(float(np.mean(bootstrap.choice(block_errors, len(block_errors), replace=True))))
    ci = np.quantile(differences, [.025, .975]).tolist()
    report = {
        'schema_version': 1, 'model_version': 3, 'kind': 'monotone_affine_dark_nelm',
        'intercept': intercept, 'slope': slope, 'input_nelm_range': [float(x[train_mask].min()), float(x[train_mask].max())],
        'enabled': bool(learned['mae_mag'] < baseline['mae_mag'] and ci[1] < 0),
        'source_doi': '10.5880/GFZ.1.4.2022.008', 'source_url': ARCHIVE_URL, 'observations_license': 'CC BY 4.0',
        'atlas_doi': '10.5880/GFZ.1.4.2016.001', 'atlas_license': 'CC BY-NC 4.0',
        'archive_sha256': digest(archive), 'atlas_sha256': digest(raster),
        'features': ['physics_dark_nelm_from_atlas_mpsas'], 'target': 'observer_NELM_1_to_7',
        'selection': '2014-2017; clear; no SQM; computed sun<-18 deg and moon<-5 deg; unique location/time',
        'split': 'seed 2026; disjoint 2-degree spatial blocks; train 2014-2016; test 2017; cross-boundary rows embargoed',
        'counts': {'usable': len(records), 'train': int(train_mask.sum()), 'test': int(test_mask.sum()),
                   'embargoed': int((~(train_mask | test_mask)).sum()), 'spatial_blocks': len(groups)},
        'rejected': rejected, 'test_physics': baseline, 'test_learned': learned, 'test_training_mean': constant,
        'block_bootstrap_delta_mae_95_ci': ci,
        'limitations': ['Citizen-science labels are noisy and ordinal.', '2015 atlas does not measure current weather or 2026 light pollution.',
                       'Global held-out evaluation is not validation in WNY.', 'Moon/cloud corrections remain physics based.',
                       'Two-degree blocks can still share regional bias; confidence interval is exploratory.'],
    }
    output.mkdir(parents=True, exist_ok=True)
    (output / 'calibration.json').write_text(json.dumps(report, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    manifest = [{'observation_id': r['id'], 'year': r['when'].year,
                 'spatial_block_sha256': hashlib.sha256(r['group'].encode()).hexdigest(),
                 'split': 'train' if tr else 'test' if te else 'embargo'}
                for r, tr, te in zip(records, train_mask, test_mask)]
    (output / 'split_manifest.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({key: report[key] for key in ('enabled', 'counts', 'test_physics', 'test_learned', 'test_training_mean', 'block_bootstrap_delta_mae_95_ci')}, indent=2))
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive', type=Path, default=ROOT / 'data/raw/globe_at_night_2022.zip')
    parser.add_argument('--atlas', type=Path, default=ROOT / 'data/raw/World_Atlas_2015.tif')
    parser.add_argument('--output', type=Path, default=ROOT / 'data/models')
    args = parser.parse_args()
    train(args.archive, args.atlas, args.output)
