# Pleiades

Pleiades finds the best places to stargaze in Western New York. It combines light pollution, live Open-Meteo weather, moon and sun position, and elevation into a **Stargazing Score (0–100)**, which it draws on an interactive night-sky map. Stargazers upload photos of the sky. Gemini identifies the objects in each photo, and the community upvotes the best shots.

Built for UB Hacking 2026. See [Architecture.md](Architecture.md) for the full design.

- `backend/`: Flask API, ingest and scoring jobs (Python 3.11+)
- `db/migrations/`: Tiger Data (TimescaleDB + PostGIS) schema
- `infra/`: nginx, systemd units, and the deploy script for the Vultr VM
- `frontend/`: React + MapLibre single-page app

## Backend quickstart

```bash
# 1. Database (local TimescaleDB + PostGIS; Tiger Cloud in prod)
docker compose up -d db

# 2. Python env
cd backend
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
cp ../.env.example ../.env          # then edit; DATABASE_URL defaults to the docker DB

# 3. Schema + dev data
.venv/bin/python -m app.migrate
.venv/bin/python scripts/seed_dev_grid.py            # add --no-elevation to skip the Open-Meteo call

# 4. Data pipeline: astro, weather, then score
.venv/bin/python -m app.ingest all

# 5. API on http://localhost:5001/api (port set in backend/.flaskenv; add --port 5001 if that file is missing)
.venv/bin/flask --app app run --debug
curl localhost:5001/api/health
```

### Tests

```bash
cd backend
.venv/bin/python -m pytest                        # unit + API tests (no DB or network needed)
TEST_DATABASE_URL=postgres://postgres:password@localhost:5432/pleiades_test \
  .venv/bin/python -m pytest -m db                 # integration tests against a real TimescaleDB
```

The integration tests run migrations, seed, and the jobs against `TEST_DATABASE_URL`. Point it at a throwaway database, for example after `docker compose exec db createdb -U postgres pleiades_test`.

### Jobs

| Command | Schedule (prod) | What it does |
|---|---|---|
| `python -m app.ingest weather` | every 3 h | Open-Meteo 72 h forecast for every cell. Each run is appended as a new revision. |
| `python -m app.ingest astro` | daily | Hourly sun/moon conditions and upcoming sky events. |
| `python -m app.ingest score [--no-refresh]` | hourly, plus after each weather run | Scoring model into `score_snapshots`, then refreshes the continuous aggregates. |
| `python -m app.ingest all` | — | Runs astro, weather, then score. |

Every run is logged in `ingest_runs`, and `/api/health` reports the last successful one.

### Deploy (Vultr)

On the VM, clone to `/opt/pleiades`, create `/opt/pleiades/.env`, and run `sudo /opt/pleiades/infra/deploy.sh`. It pulls the code, builds, migrates, installs the systemd units and timers, and restarts the API. Then run `sudo certbot --nginx -d <host>` for TLS.

## AI/ML seams

The backend calls the following functions. Their current bodies are **placeholders** that let the pipeline run end to end. The AI/ML owner replaces the bodies but keeps the signatures; the shared types live in each package's `types.py`.

| File | Function | Called by |
|---|---|---|
| `backend/app/scoring/model.py` | `score_batch(FeatureBatch) -> ScoreBatch`, `MODEL_VERSION` | `ingest score` |
| `backend/app/astro/ephemeris.py` | `hourly_conditions`, `sky_events` | `ingest astro` |
| `backend/app/astro/ephemeris.py` | `night_summary` | `/api/sky-events` |
| `backend/app/astro/ephemeris.py` | `visible_objects` | photo worker (vision grounding) |
| `backend/app/ai/vision.py` | `analyze_photo(bytes, mime, VisionContext) -> VisionResult` | photo worker |
| `backend/app/ai/explain.py` | `explain_score(ExplainContext) -> Explanation` | `/api/spots/:id` (cached, with timeout fallback) |

`backend/scripts/seed_dev_grid.py` is a dev-only stand-in for `data/build_grid.py`, which samples the real light-pollution atlas.
