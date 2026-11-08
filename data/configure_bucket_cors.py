"""Allow browser uploads to the photo bucket from the app's origin(s).

Browsers PUT photos straight to object storage with presigned URLs, so the bucket needs
a CORS rule for the site's origin. Run once per bucket (it is idempotent: it replaces the
bucket's CORS configuration with this one rule):

    backend/.venv/bin/python data/configure_bucket_cors.py https://pleiades.example.com
    backend/.venv/bin/python data/configure_bucket_cors.py --check

Uses the same VULTR_S3_* settings as the API. Never prints credentials. The local
SeaweedFS service in docker-compose already allows any origin and doesn't need this.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))

from botocore.exceptions import ClientError  # noqa: E402

from app.config import current_settings  # noqa: E402
from app.storage import s3  # noqa: E402


def cors_rules(origins: list[str]) -> dict:
    return {'CORSRules': [{
        'AllowedOrigins': origins,
        'AllowedMethods': ['PUT', 'GET', 'HEAD'],
        'AllowedHeaders': ['Content-Type'],
        'ExposeHeaders': ['ETag'],
        'MaxAgeSeconds': 3600,
    }]}


def valid_origin(value: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme not in ('http', 'https') or not parsed.netloc or parsed.path not in ('', '/'):
        raise argparse.ArgumentTypeError(f'{value!r} is not an origin like https://example.com')
    return f'{parsed.scheme}://{parsed.netloc}'


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('origins', nargs='*', type=valid_origin, help='site origin(s) allowed to upload')
    parser.add_argument('--check', action='store_true', help='print the current CORS rules and exit')
    args = parser.parse_args()

    settings = current_settings()
    if not settings.s3_configured:
        print('Storage is not configured: set VULTR_S3_ENDPOINT, ACCESS_KEY, SECRET_KEY and BUCKET.', file=sys.stderr)
        return 2
    client = s3.client()
    bucket = settings.s3_bucket

    if args.check:
        try:
            print(json.dumps(client.get_bucket_cors(Bucket=bucket).get('CORSRules', []), indent=2))
        except ClientError as e:
            if e.response.get('Error', {}).get('Code') == 'NoSuchCORSConfiguration':
                print('[]  (no CORS configuration)')
            else:
                raise
        return 0

    if not args.origins:
        parser.error('give at least one origin, or --check')
    client.put_bucket_cors(Bucket=bucket, CORSConfiguration=cors_rules(args.origins))
    print(f'Bucket {bucket!r} now allows uploads from: {", ".join(args.origins)}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
