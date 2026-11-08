from io import StringIO
from pathlib import Path
import sys

from dotenv import dotenv_values

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from configure_database import replace_database_url


def test_database_update_preserves_other_settings_and_removes_duplicates():
    original = '# keep this comment\nDATABASE_URL=old\nGEMINI_MODEL=test-model\nexport DATABASE_URL=duplicate\n'
    uri = 'postgresql://test:example%23password@db.example.invalid:5432/pleiades?sslmode=require'
    updated = replace_database_url(original, uri)
    assert updated.count('DATABASE_URL=') == 1
    assert '# keep this comment' in updated
    values = dotenv_values(stream=StringIO(updated))
    assert values['DATABASE_URL'] == uri
    assert values['GEMINI_MODEL'] == 'test-model'
