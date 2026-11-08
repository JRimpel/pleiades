"""Read-only Gemini endpoint diagnosis. Never output keys, headers, or raw errors."""
import json
import argparse
import re
import sys
from pathlib import Path

import requests
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
from app.config import get_settings


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--probe-model', help='Optional small generateContent request; not a model-setting change')
    args = parser.parse_args()
    settings = get_settings()
    report = {'key_present': bool(settings.gemini_api_key), 'model_present': bool(settings.gemini_model),
              'legacy_key_format': bool(re.fullmatch(r'AIza[A-Za-z0-9_-]{35}', settings.gemini_api_key)),
              'modern_auth_key_format': settings.gemini_api_key.startswith(('AQ.', 'AQ_'))}
    # Structural checks only: never print the credential, a prefix, or a suffix.
    report['key_contains_assignment_text'] = 'GEMINI_API_KEY=' in settings.gemini_api_key
    report['key_contains_whitespace'] = any(c.isspace() for c in settings.gemini_api_key)
    report['complete_google_key_tokens_found'] = len(re.findall(r'(?<![A-Za-z0-9_-])AIza[A-Za-z0-9_-]{35}(?![A-Za-z0-9_-])', settings.gemini_api_key))
    report['proxy_environment_present'] = bool(requests.utils.get_environ_proxies('https://generativelanguage.googleapis.com'))
    stored_key = dotenv_values(ROOT / '.env', encoding='utf-8-sig').get('GEMINI_API_KEY')
    report['runtime_matches_project_env_key'] = bool(stored_key) and stored_key == settings.gemini_api_key
    try:
        response = requests.get('https://generativelanguage.googleapis.com/v1beta/models',
                                headers={'x-goog-api-key': settings.gemini_api_key}, timeout=10)
        report['http_status'] = response.status_code
        report['content_type'] = response.headers.get('Content-Type')
        try:
            body = response.json()
        except ValueError:
            body = {}
        if response.ok:
            names = [m['name'] for m in body.get('models', [])]
            report['configured_model_available'] = 'models/' + settings.gemini_model in names
            report['flash_models'] = [n for n in names if 'flash' in n][:12]
        else:
            error = body.get('error', {})
            report['api_status'] = error.get('status')
            report['error_reasons'] = [d.get('reason') for d in error.get('details', []) if isinstance(d, dict) and d.get('reason')]
            message = str(body.get('error', {}).get('message', 'Non-JSON upstream response'))
            report['message'] = re.sub(r'AIza[A-Za-z0-9_-]+', '[redacted]', message.replace(settings.gemini_api_key, '[redacted]'))[:300]
    except Exception as error:
        report['error_type'] = type(error).__name__
    if args.probe_model:
        if not re.fullmatch(r'gemini-[A-Za-z0-9._-]+', args.probe_model):
            raise ValueError('Invalid model ID')
        try:
            response = requests.post(
                'https://generativelanguage.googleapis.com/v1beta/models/' + args.probe_model + ':generateContent',
                headers={'x-goog-api-key': settings.gemini_api_key},
                json={'contents': [{'parts': [{'text': 'Reply only: OK'}]}]}, timeout=15)
            try:
                payload = response.json()
            except ValueError:
                payload = {}
            report['generation_probe'] = {'model': args.probe_model, 'http_status': response.status_code,
                                          'content_type': response.headers.get('Content-Type')}
            error = payload.get('error', {})
            report['generation_probe']['api_status'] = error.get('status')
            report['generation_probe']['error_reasons'] = [d.get('reason') for d in error.get('details', [])
                                                          if isinstance(d, dict) and d.get('reason')]
            # Avoid raw response data or exception strings; neither is needed here.
            report['generation_probe']['success'] = response.ok and bool(payload.get('candidates'))
        except Exception as error:
            report['generation_probe'] = {'error_type': type(error).__name__}
    print(json.dumps(report, indent=2))
