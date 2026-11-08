"""Explicit live Gemini smoke: one explanation + synthetic non-sky rejection.

Never prints credentials or raw SDK exceptions. This is integration evidence,
not a real-photo recognition benchmark. Requires configured key and model.
"""
import io
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
from app.ai.explain import explain_score
from app.ai.types import ExplainContext, VisionContext
from app.ai.vision import analyze_photo
from app.config import get_settings


def safe_error(error):
    message = str(getattr(error, 'message', ''))
    key = get_settings().gemini_api_key
    if key:
        message = message.replace(key, '[redacted]')
    message = re.sub(r'AIza[A-Za-z0-9_-]+', '[redacted]', message)
    return {'error_type': type(error).__name__, 'code': getattr(error, 'code', None),
            'status': getattr(error, 'status', None), 'message': message[:400]}


def main():
    settings = get_settings()
    if not settings.gemini_api_key or not settings.gemini_model:
        print('Gemini configuration missing (values not printed).')
        return 2
    when = datetime(2026, 11, 8, 4, tzinfo=timezone.utc)
    report = {'kind': 'live integration smoke; synthetic input; not recognition accuracy', 'checks': {}}
    ctx = ExplainContext(cell_id=1, spot_name='Integration test spot', valid_time=when,
                         local_time='Sat Nov 7, 11:00 PM', score=40, nelm=5.5,
                         factors={'clouds': -35, 'moon': -15, 'light_pollution': -10}, bortle=4,
                         sun_alt=-35, moon_alt=20, moon_illum=.6, conditions={'cloud_total': 55})
    started = perf_counter()
    try:
        explanation = explain_score(ctx)
        report['checks']['explanation'] = {'status': 'success', 'seconds': round(perf_counter() - started, 3),
                                            'result': explanation.model_dump()}
    except Exception as error:
        report['checks']['explanation'] = {'status': 'failed', 'details': safe_error(error)}
    image = Image.new('RGB', (512, 320), 'white')
    draw = ImageDraw.Draw(image)
    draw.rectangle((30, 30, 150, 150), fill='red')
    draw.text((30, 200), 'Integration test card. Not a photograph of the sky.', fill='black')
    buffer = io.BytesIO()
    image.save(buffer, format='PNG')
    started = perf_counter()
    try:
        result = analyze_photo(buffer.getvalue(), 'image/png', VisionContext(
            lat=42.7, lon=-78.4, taken_at=when, candidates=[]))
        report['checks']['vision_non_sky'] = {'status': 'success' if not result.is_night_sky else 'unexpected_acceptance',
                                              'seconds': round(perf_counter() - started, 3), 'result': result.model_dump()}
    except Exception as error:
        report['checks']['vision_non_sky'] = {'status': 'failed', 'details': safe_error(error)}
    output = ROOT / 'data/live_gemini_report.json'
    output.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report, indent=2))
    return 0 if all(check['status'] == 'success' for check in report['checks'].values()) else 1


if __name__ == '__main__':
    raise SystemExit(main())
