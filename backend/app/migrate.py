"""Apply SQL migrations in db/migrations/ in filename order.

Usage: python -m app.migrate [--dry-run]

Each file is split into individual statements, executed one at a time in autocommit
mode (TimescaleDB continuous aggregates cannot be created inside a transaction or a
multi-statement query). A file is recorded in `schema_migrations` only after all of
its statements succeed.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .config import MIGRATIONS_DIR, get_settings


def split_sql(text: str) -> list[str]:
    """Split a SQL script into top-level statements.

    Respects single-quoted strings ('' escapes), double-quoted identifiers,
    dollar-quoted bodies ($$...$$ / $tag$...$tag$), `--` line comments and
    `/* */` block comments (nested). Comments are kept inside statements; statements
    that contain only whitespace/comments are dropped. Trailing semicolons are removed.
    """
    statements: list[str] = []
    buf: list[str] = []
    i, n = 0, len(text)
    has_code = False  # buffer contains something other than whitespace/comments

    def flush() -> None:
        nonlocal has_code
        stmt = "".join(buf).strip()
        if stmt and has_code:
            statements.append(stmt)
        buf.clear()
        has_code = False

    while i < n:
        c = text[i]
        nxt = text[i + 1] if i + 1 < n else ""

        if c == "-" and nxt == "-":
            j = text.find("\n", i)
            j = n if j == -1 else j + 1
            buf.append(text[i:j])
            i = j
            continue

        if c == "/" and nxt == "*":
            depth, j = 1, i + 2
            while j < n and depth:
                if text.startswith("/*", j):
                    depth += 1
                    j += 2
                elif text.startswith("*/", j):
                    depth -= 1
                    j += 2
                else:
                    j += 1
            buf.append(text[i:j])
            i = j
            continue

        if c in ("'", '"'):
            j = i + 1
            while j < n:
                if text[j] == c:
                    if j + 1 < n and text[j + 1] == c:  # doubled quote escape
                        j += 2
                        continue
                    j += 1
                    break
                j += 1
            buf.append(text[i:j])
            has_code = True
            i = j
            continue

        if c == "$":
            # Dollar quote: $tag$ where tag is empty or an identifier not starting with a digit.
            j = i + 1
            while j < n and (text[j].isalnum() or text[j] == "_"):
                j += 1
            tag_body = text[i + 1:j]
            if j < n and text[j] == "$" and not (tag_body[:1].isdigit()):
                tag = text[i:j + 1]
                end = text.find(tag, j + 1)
                end = n if end == -1 else end + len(tag)
                buf.append(text[i:end])
                has_code = True
                i = end
                continue
            buf.append(c)
            has_code = True
            i += 1
            continue

        if c == ";":
            flush()
            i += 1
            continue

        buf.append(c)
        if not c.isspace():
            has_code = True
        i += 1

    flush()
    return statements


def migration_files(directory: Path = MIGRATIONS_DIR) -> list[Path]:
    return sorted(p for p in directory.glob("*.sql") if p.is_file())


def run(dry_run: bool = False, directory: Path = MIGRATIONS_DIR, database_url: str | None = None) -> int:
    """Apply pending migrations. Returns the number of files applied (or that would be)."""
    files = migration_files(directory)
    if dry_run and not (database_url or get_settings().database_url):
        for f in files:
            stmts = split_sql(f.read_text())
            print(f"[dry-run] {f.name}: {len(stmts)} statements")
        return len(files)

    import psycopg
    from psycopg.rows import dict_row

    url = database_url or get_settings().database_url
    if not url:
        print("DATABASE_URL is not set", file=sys.stderr)
        raise SystemExit(2)

    applied_count = 0
    with psycopg.connect(url, autocommit=True, row_factory=dict_row) as conn:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations ("
            " filename text PRIMARY KEY, applied_at timestamptz NOT NULL DEFAULT now())"
        )
        done = {r["filename"] for r in conn.execute("SELECT filename FROM schema_migrations").fetchall()}
        for f in files:
            if f.name in done:
                print(f"  skip   {f.name} (already applied)")
                continue
            stmts = split_sql(f.read_text())
            if dry_run:
                print(f"  would apply {f.name}: {len(stmts)} statements")
                applied_count += 1
                continue
            print(f"  apply  {f.name}: {len(stmts)} statements")
            for k, stmt in enumerate(stmts, 1):
                try:
                    conn.execute(stmt)
                except Exception as e:
                    first_line = stmt.strip().splitlines()[0][:100]
                    print(f"  FAILED {f.name} statement {k}/{len(stmts)}: {first_line}\n    {e}", file=sys.stderr)
                    raise
            conn.execute("INSERT INTO schema_migrations (filename) VALUES (%s)", (f.name,))
            applied_count += 1
    print(f"Done: {applied_count} migration(s) {'pending' if dry_run else 'applied'}.")
    return applied_count


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.migrate", description=__doc__.splitlines()[0])
    parser.add_argument("--dry-run", action="store_true", help="show what would be applied")
    args = parser.parse_args(argv)
    try:
        run(dry_run=args.dry_run)
    except SystemExit:
        raise
    except Exception:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
