import re

from app.config import MIGRATIONS_DIR
from app.migrate import migration_files, split_sql


def test_split_basic_and_empty():
    assert split_sql("SELECT 1; SELECT 2;") == ["SELECT 1", "SELECT 2"]
    assert split_sql(";;  \n ; ") == []
    assert split_sql("SELECT 1") == ["SELECT 1"]


def test_split_respects_quotes_and_identifiers():
    sql = "INSERT INTO t VALUES ('a;b', 'it''s; fine'); SELECT \"weird;col\" FROM t;"
    assert split_sql(sql) == [
        "INSERT INTO t VALUES ('a;b', 'it''s; fine')",
        'SELECT "weird;col" FROM t',
    ]


def test_split_respects_comments():
    sql = """
    -- leading comment; with semicolon
    SELECT 1; -- trailing; comment
    /* block; comment /* nested; */ still; */
    SELECT 2;
    -- only a comment;
    """
    stmts = split_sql(sql)
    assert len(stmts) == 2
    assert stmts[0].endswith("SELECT 1")
    assert "SELECT 2" in stmts[1]


def test_split_respects_dollar_quotes():
    sql = """
    CREATE FUNCTION f() RETURNS int AS $$ BEGIN RETURN 1; END; $$ LANGUAGE plpgsql;
    DO $body$ BEGIN PERFORM 1; PERFORM $$x;y$$; END $body$;
    SELECT $1::int;
    """
    stmts = split_sql(sql)
    assert len(stmts) == 3
    assert stmts[0].startswith("CREATE FUNCTION") and stmts[0].endswith("LANGUAGE plpgsql")
    assert stmts[1].startswith("DO $body$") and stmts[1].endswith("END $body$")
    assert stmts[2] == "SELECT $1::int"


def _strip(sql: str) -> str:
    sql = re.sub(r"--[^\n]*", "", sql)
    sql = re.sub(r"'(?:[^']|'')*'", "''", sql)
    return sql


STATEMENT_START = re.compile(r"^\s*(CREATE|SELECT|ALTER|INSERT|DROP)\b", re.I | re.M)


def test_real_migrations():
    files = migration_files(MIGRATIONS_DIR)
    names = [f.name for f in files]
    assert names[:3] == ["001_init.sql", "002_aggregates.sql", "003_policies.sql"]
    counts = {f.name: len(split_sql(f.read_text())) for f in files}
    assert counts["001_init.sql"] == 25
    assert counts["002_aggregates.sql"] == 2
    assert counts["003_policies.sql"] == 7
    for f in files:
        for stmt in split_sql(f.read_text()):
            body = _strip(stmt)
            assert ";" not in body, f"{f.name}: embedded semicolon in {stmt[:80]!r}"
            # Each piece starts exactly one top-level statement (sub-selects are indented / inline).
            # (A continuous aggregate legitimately contains a line-leading SELECT.)
            starts = list(STATEMENT_START.finditer(body))
            assert starts, stmt[:120]
            assert len(starts) == 1 or body.lstrip().upper().startswith("CREATE MATERIALIZED VIEW"), stmt[:120]
