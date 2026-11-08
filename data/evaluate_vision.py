"""Evaluate reviewed real photos with and without ephemeris grounding.

Manifest schema is in data/README.md. Labels never enter model prompts. Each
image must have reviewed labels and reliable capture coordinates/time. Outputs
are observations, not a claim of calibrated model confidence.
"""
import argparse
import json
import mimetypes
import sys
from datetime import datetime
from pathlib import Path
from time import perf_counter

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
from app.ai.explain import _generate_json
from app.ai.types import VisionContext, VisionResult
from app.ai.vision import analyze_photo
from app.astro.ephemeris import visible_objects


def compare(expected, actual):
    expected = {s.casefold() for s in expected}
    actual = {s.casefold() for s in actual}
    return {'tp': len(expected & actual), 'fp': len(actual - expected), 'fn': len(expected - actual)}


def run(manifest_path, output, dry_run=False):
    entries = json.loads(manifest_path.read_text(encoding='utf-8'))
    records = []
    for item in entries:
        if not item.get('reviewed') or not item.get('metadata_verified'):
            raise ValueError('All benchmark photos need reviewed labels and verified capture metadata')
        when = datetime.fromisoformat(item['taken_at'].replace('Z', '+00:00'))
        path = (manifest_path.parent / item['path']).resolve()
        if not path.is_file() or not item.get('source') or 'is_night_sky' not in item or 'objects' not in item:
            raise ValueError('Each photo needs an existing path, source, night-sky label and exhaustive object labels')
        candidates = visible_objects(item['lat'], item['lon'], when)
        context = VisionContext(lat=item['lat'], lon=item['lon'], taken_at=when, candidates=candidates)
        data = path.read_bytes()
        mime = mimetypes.guess_type(path)[0]
        record = {'id': item['id'], 'source': item['source'], 'ground_truth': {'is_night_sky': item['is_night_sky'], 'objects': item['objects']}}
        if dry_run:
            record['status'] = 'validated_only_no_model_calls'
            record['candidate_count'] = len(candidates)
            records.append(record)
            continue
        for mode in ('grounded', 'ungrounded'):
            started = perf_counter()
            try:
                if mode == 'grounded':
                    result = analyze_photo(data, mime, context)
                else:
                    # Same output schema and image. No time, place, candidates or labels.
                    result = _generate_json(
                        'Describe this night-sky photograph using visual evidence only. '
                        'Return is_night_sky=false for unrelated images. Identify objects only when convincing. '
                        'Prefer an empty objects list over guesses. Confidence is an uncalibrated assessment. '
                        'Keep description under 800 characters, notes under 300, and at most 15 objects. '
                        'Do not infer capture location or time. sky_quality is subjective photographic appearance.',
                        VisionResult, image_bytes=data, mime_type=mime, timeout_ms=20000)
                names = [o.name for o in result.objects if o.confidence >= .75] if result.is_night_sky else []
                record[mode] = {'status': 'success', 'seconds': round(perf_counter() - started, 3),
                                'night_sky_correct': result.is_night_sky == item['is_night_sky'],
                                'abstained': not names, 'counts': compare(item['objects'], names), 'predicted_objects': names}
            except Exception as error:
                record[mode] = {'status': 'failed', 'error_type': type(error).__name__,
                                'seconds': round(perf_counter() - started, 3)}
        records.append(record)
    report = {'kind': 'reviewed-photo evaluation', 'dry_run': dry_run, 'images': records, 'summary': {}}
    for mode in ('grounded', 'ungrounded'):
        successes = [r[mode] for r in records if r.get(mode, {}).get('status') == 'success']
        if successes:
            totals = {key: sum(r['counts'][key] for r in successes) for key in ('tp', 'fp', 'fn')}
            report['summary'][mode] = {**totals, 'successful_images': len(successes), 'failed_images': len(records) - len(successes),
                                       'precision': totals['tp'] / (totals['tp'] + totals['fp']) if totals['tp'] + totals['fp'] else None,
                                       'recall': totals['tp'] / (totals['tp'] + totals['fn']) if totals['tp'] + totals['fn'] else None,
                                       'abstentions': sum(r['abstained'] for r in successes),
                                       'night_sky_correct': sum(r['night_sky_correct'] for r in successes)}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'images': len(records), 'dry_run': dry_run, 'summary': report['summary']}, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('manifest', type=Path)
    parser.add_argument('--output', type=Path, default=ROOT / 'data/vision_evaluation.json')
    parser.add_argument('--dry-run', action='store_true', help='Validate metadata/files; no paid model calls')
    args = parser.parse_args()
    run(args.manifest, args.output, args.dry_run)
