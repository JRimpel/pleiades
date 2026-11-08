import pytest
from psycopg import OperationalError
from psycopg_pool import PoolTimeout

from app.db import DatabaseNotConfigured
from app.repo import scores


@pytest.mark.parametrize('error_type', [DatabaseNotConfigured, PoolTimeout, OperationalError])
def test_unavailable_database_is_a_sanitized_service_error(client, monkeypatch, error_type):
    def unavailable(*args, **kwargs):
        raise error_type('private connection details must not reach the browser')

    monkeypatch.setattr(scores, 'score_range', unavailable)
    response = client.get('/api/scores/range')
    assert response.status_code == 503
    assert response.json == {'error': {'code': 'database_unavailable',
                                      'message': 'The backend cannot connect to its database.'}}
