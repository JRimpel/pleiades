"""Read-only Gemini endpoint diagnosis. Never output keys, headers, or raw errors."""
import json
import re
import sys
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
from app.config import get_settings


if __name__ == '__main__':
    settings = get_settings()
    report = {'key_present': bool(settings.gemini_api_key), 'model_present': bool(settings.gemini_model),
              'legacy_key_format': bool(re.fullmatch(r'AIza[A-Za-z0-9_-]{35}', settings.gemini_api_key)),
              'modern_auth_key_format': settings.gemini_api_key.startswith(('AQ.', 'AQ_'))}
    # Structural checks only: never print the credential, a prefix, or a suffix.
    report['key_contains_assignment_text'] = 'GEMINI_API_KEY=' in settings.gemini_api_key
    report['key_contains_whitespace'] = any(c.isspace() for c in settings.gemini_api_key)
    report['complete_google_key_tokens_found'] = len(re.findall(r'(?<![A-Za-z0-9_-])AIza[A-Za-z0-9_-]{35}(?![A-Za-z0-9_-])', settings.gemini_api_key))
    report['proxy_environment_present'] = bool(requests.utils.get_environ_proxies('https://generativelanguage.googleapis.com'))
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
            message = str(body.get('error', {}).get('message', 'Non-JSON upstream response'))
            report['message'] = re.sub(r'AIza[A-Za-z0-9_-]+', '[redacted]', message.replace(settings.gemini_api_key, '[redacted]'))[:300]
    except Exception as error:
        report['error_type'] = type(error).__name__
    print(json.dumps(report, indent=2))
