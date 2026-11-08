"""Ingest & scoring jobs (run by systemd timers).

    python -m app.ingest weather            # Open-Meteo forecast -> weather_forecast (every 3 h)
    python -m app.ingest astro              # ephemeris + sky events (daily)
    python -m app.ingest score [--no-refresh]  # scoring model -> score_snapshots (hourly)
    python -m app.ingest explain            # pre-generate Gemini explanations for tonight's top spots (after score)
    python -m app.ingest all                # astro, weather, score, explain
    python -m app.ingest grid [--reset]     # static grid from data/wny_grid.geojson (one-off)
    python -m app.ingest bootstrap [--reset-grid]  # grid, astro, weather, score (fresh DB / deploy)
"""
from __future__ import annotations

import argparse
import logging
import sys
from typing import Callable

import psycopg

from ..config import Settings, get_settings
from ..db import connect_direct
from ..repo import ingest_log
from ..timeutil import utcnow

log = logging.getLogger("app.ingest")

JobFn = Callable[[psycopg.Connection, Settings], int]


def run_job(name: str, fn: JobFn, settings: Settings) -> int:
    """Run one job inside an ingest_runs start/finish record. Returns the row count; re-raises on failure."""
    with connect_direct(settings) as conn:
        run_id = ingest_log.start(conn, name, utcnow())
        try:
            rows = fn(conn, settings)
        except Exception as e:
            conn.rollback()
            ingest_log.finish(conn, run_id, status="error", details={"error": f"{type(e).__name__}: {e}"[:1000]})
            raise
        ingest_log.finish(conn, run_id, status="ok", rows=rows)
        return rows


def _jobs(args: argparse.Namespace) -> list[tuple[str, JobFn]]:
    from . import astro, explain_warm, grid, score, weather

    def score_job(conn: psycopg.Connection, settings: Settings) -> int:
        return score.run(conn, settings, refresh=not getattr(args, "no_refresh", False))

    def grid_job(conn: psycopg.Connection, settings: Settings) -> int:
        return grid.run(conn, settings, reset=getattr(args, "reset", False) or getattr(args, "reset_grid", False))

    table: dict[str, JobFn] = {"weather": weather.run, "astro": astro.run, "score": score_job, "grid": grid_job,
                               "explain": explain_warm.run}
    if args.job == "all":
        return [(n, table[n]) for n in ("astro", "weather", "score", "explain")]
    if args.job == "bootstrap":
        return [(n, table[n]) for n in ("grid", "astro", "weather", "score")]
    return [(args.job, table[args.job])]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.ingest", description="Pleiades ingest & scoring jobs")
    sub = parser.add_subparsers(dest="job", required=True)
    sub.add_parser("weather", help="fetch Open-Meteo forecast for every grid cell")
    sub.add_parser("astro", help="compute hourly sun/moon conditions and sky events")
    p_score = sub.add_parser("score", help="run the scoring model over the forecast window")
    p_score.add_argument("--no-refresh", action="store_true", help="skip continuous-aggregate refresh")
    sub.add_parser("explain", help="pre-generate explanations for tonight's top and curated spots")
    p_all = sub.add_parser("all", help="astro, weather, score, then explain")
    p_all.add_argument("--no-refresh", action="store_true", help="skip continuous-aggregate refresh")
    p_grid = sub.add_parser("grid", help="load grid_cells from the committed grid GeoJSON (no-op if loaded)")
    p_grid.add_argument("--reset", action="store_true",
                        help="TRUNCATE grid_cells ... CASCADE first (also deletes forecasts, scores, explanations)")
    p_boot = sub.add_parser("bootstrap", help="grid, astro, weather, score: populate a fresh database")
    p_boot.add_argument("--reset-grid", action="store_true", help="replace the existing grid (see grid --reset)")
    p_boot.add_argument("--no-refresh", action="store_true", help="skip continuous-aggregate refresh")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    settings = get_settings()

    for name, fn in _jobs(args):
        log.info("job %s: starting", name)
        try:
            rows = run_job(name, fn, settings)
        except Exception:
            log.exception("job %s: failed", name)
            return 1
        log.info("job %s: ok (%d rows)", name, rows)
    return 0


if __name__ == "__main__":
    sys.exit(main())
