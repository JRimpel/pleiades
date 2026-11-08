"""Read-only database readiness check; never prints connection strings or credentials."""
from __future__ import annotations

import json
import os
from pathlib import Path
import sys
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))

import psycopg
from dotenv import dotenv_values

INHERITED_DATABASE_URL = os.environ.get('DATABASE_URL')
from app.config import Settings


def main() -> None:
    settings = Settings.from_env()
    report = {'database_configured': bool(settings.database_url)}
    root = Path(__file__).resolve().parents[1]
    saved = dotenv_values(root / '.env').get('DATABASE_URL')
    report['project_file_matches_runtime'] = saved == settings.database_url
    report['inherited_database_override'] = bool(INHERITED_DATABASE_URL and INHERITED_DATABASE_URL != saved)
    report['project_file_targets_local_database'] = bool(saved and urlparse(saved).hostname in ('localhost', '127.0.0.1', '::1'))
    if not settings.database_url:
        print(json.dumps(report, indent=2))
        return
    try:
        target = urlparse(settings.database_url)
        report['local_database'] = target.hostname in ('localhost', '127.0.0.1', '::1')
        report['port'] = target.port or 5432
        with psycopg.connect(settings.database_url, connect_timeout=5) as conn:
            conn.execute('SET TRANSACTION READ ONLY')
            report['connected'] = True
            report['grid_table_present'] = conn.execute("SELECT to_regclass('grid_cells') IS NOT NULL").fetchone()[0]
            report['scores_view_present'] = conn.execute("SELECT to_regclass('cell_hourly_score') IS NOT NULL").fetchone()[0]
            if report['grid_table_present']:
                report['grid_cells'] = conn.execute('SELECT count(*) FROM grid_cells').fetchone()[0]
            if report['scores_view_present']:
                count, first, last = conn.execute('SELECT count(*), min(bucket), max(bucket) FROM cell_hourly_score').fetchone()
                report['score_rows'] = count
                report['first_score_hour'] = first.isoformat() if first else None
                report['last_score_hour'] = last.isoformat() if last else None
    except Exception as error:
        report['connected'] = report.get('connected', False)
        report['error_type'] = type(error).__name__
        report['sqlstate'] = getattr(error, 'sqlstate', None)
        message = str(error).lower()
        report['reason'] = next((label for fragment, label in [
            ('refused', 'connection_refused'), ('password authentication failed', 'authentication_failed'),
            ('could not translate host', 'hostname_resolution_failed'), ('getaddrinfo', 'hostname_resolution_failed'),
            ('timeout', 'connection_timeout'), ('timed out', 'connection_timeout'),
            ('does not exist', 'database_or_relation_missing'), ('ssl', 'tls_configuration'),
        ] if fragment in message), 'connection_or_query_failed')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
