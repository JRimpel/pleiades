"""Safely replace the runtime Gemini key using hidden terminal input.

No network requests, secret output, or command-line credential arguments.
"""
from __future__ import annotations

import getpass
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def replace_key(text: str, key: str) -> str:
    """Replace duplicate assignments without touching unrelated configuration."""
    lines = text.splitlines()
    result = []
    inserted = False
    for line in lines:
        if re.match(r'^\s*(?:export\s+)?GEMINI_API_KEY\s*=', line):
            if not inserted:
                result.append('GEMINI_API_KEY=' + key)
                inserted = True
        else:
            result.append(line)
    if not inserted:
        result.append('GEMINI_API_KEY=' + key)
    return '\n'.join(result) + '\n'


def main():
    key = getpass.getpass('Paste only the Google AI Studio API key (typing hidden): ').strip()
    # Auth keys can use newer formats. Do not reject them based on a legacy prefix.
    if not key or any(c.isspace() for c in key) or not key.isascii() or '=' in key[:16]:
        print('Expected a single key value without whitespace or an assignment. Nothing was changed.')
        return 2
    path = ROOT / '.env'
    existing = path.read_text(encoding='utf-8-sig') if path.exists() else ''
    path.write_text(replace_key(existing, key), encoding='utf-8')
    print('Saved GEMINI_API_KEY in the ignored project .env. No API request made. Restart running app/job processes after verification.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
