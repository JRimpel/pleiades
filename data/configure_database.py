"""Save a PostgreSQL connection URI using hidden local input; no network requests."""
from __future__ import annotations

import getpass
from pathlib import Path
import re
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]


def replace_database_url(text: str, uri: str) -> str:
    assignment = "DATABASE_URL='" + uri.replace('\\', '\\\\').replace("'", "\\'") + "'"
    result = []
    inserted = False
    for line in text.splitlines():
        if re.match(r'^\s*(?:export\s+)?DATABASE_URL\s*=', line):
            if not inserted:
                result.append(assignment)
                inserted = True
        else:
            result.append(line)
    if not inserted:
        result.append(assignment)
    return '\n'.join(result) + '\n'


def main() -> int:
    uri = getpass.getpass('Paste the PostgreSQL connection URI (typing hidden): ').strip()
    try:
        parsed = urlparse(uri)
        valid = parsed.scheme in ('postgres', 'postgresql') and parsed.hostname and parsed.path.strip('/')
        _ = parsed.port
    except ValueError:
        valid = False
    if not valid or any(character.isspace() for character in uri):
        print('Expected a postgres:// or postgresql:// connection URI. Nothing was changed.')
        return 2
    path = ROOT / '.env'
    existing = path.read_text(encoding='utf-8-sig') if path.exists() else ''
    path.write_text(replace_database_url(existing, uri), encoding='utf-8')
    print('Saved DATABASE_URL privately in the project .env. Restart the API to use it.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
