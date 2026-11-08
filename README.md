# Pleiades

Pleiades finds the best places to stargaze in Western New York. It combines light pollution, live Open-Meteo weather, moon and sun position, and elevation into a **Stargazing Score (0–100)**, which it draws on an interactive night-sky map. Stargazers upload photos of the sky. Gemini identifies the objects in each photo, and the community upvotes the best shots.

Built for UB Hacking 2026. See [Architecture.md](Architecture.md) for the full design.

Current integration status and verification: [INTEGRATION_HANDOFF.md](INTEGRATION_HANDOFF.md). The score map, spot details/charts, sky summary, location services and Explore in 3D now share selected observing context. Community photos are live on the map: upload, a story-style viewer with the AI analysis, and voting.

- `backend/`: Flask API, ingest and scoring jobs (Python 3.11+)
- `db/migrations/`: Tiger Data (TimescaleDB + PostGIS) schema
- `infra/`: nginx, systemd units, and the deploy script for the Vultr VM
- `frontend/`: React + MapLibre single-page app

## Backend quickstart

Prerequisites: Docker running Linux containers, Python 3.12+, and Node.js for the frontend. On Windows, install Docker Desktop and its WSL 2 prerequisite before `docker compose`; a Windows restart may be required. Keep an existing `.env` rather than copying over its credentials.

```bash
# 1. Database (local TimescaleDB + PostGIS; Tiger Cloud in prod) and photo storage
#    (local S3-compatible SeaweedFS; Vultr Object Storage in prod). See "Photo storage" below.
docker compose up -d db storage

# 2. Python env
cd backend
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
test -f ../.env || cp ../.env.example ../.env  # preserve existing credentials; edit a new file

# 3. Schema + dev data
.venv/bin/python -m app.migrate
.venv/bin/python -m app.ingest grid                  # load the committed real WNY grid

# 4. Data pipeline: astro, weather, then score
.venv/bin/python -m app.ingest all

# 5. API on http://localhost:5001/api (port set in backend/.flaskenv; add --port 5001 if that file is missing)
.venv/bin/flask --app app run --debug
curl localhost:5001/api/health
```

Windows PowerShell equivalent, after Docker Desktop is running:

```powershell
# Repository root; reuse the existing Python environment if already installed.
docker compose up -d db
py -3.12 -m venv backend/.venv
backend/.venv/Scripts/python.exe -m pip install -r backend/requirements-dev.txt
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
Set-Location backend
.venv/Scripts/python.exe -m app.migrate
.venv/Scripts/python.exe -m app.ingest bootstrap  # real grid -> astronomy -> live weather -> scores
.venv/Scripts/python.exe -m flask --app app --no-debug run --port 5001 --no-reload
```

Keep Flask running, then start the frontend in another terminal. `GET /api/scores/range` should return a forecast range, and `GET /api/scores` should contain scored cells. Photo storage can be unavailable while scores still work; `/api/health` may therefore report `degraded` for storage only.

### Photo storage

Browsers upload photos straight to object storage with presigned URLs. The API, thumbnail worker and map read them back through the same `VULTR_S3_*` settings.

**Local development.** `docker compose up -d storage` runs [SeaweedFS](https://github.com/seaweedfs/seaweedfs) on `localhost:8333`. It creates the `pleiades-photos` bucket on startup and allows browser uploads from any origin. MinIO's prebuilt images are no longer published, which is why SeaweedFS is used. Point the API at it in `.env`, then restart Flask:

```bash
VULTR_S3_ENDPOINT=http://localhost:8333
VULTR_S3_REGION=us-east-1
VULTR_S3_ACCESS_KEY=pleiades-dev          # dev-only, from infra/dev-storage/s3.json
VULTR_S3_SECRET_KEY=pleiades-dev-secret
VULTR_S3_BUCKET=pleiades-photos
VULTR_S3_PUBLIC_BASE=                     # empty: photos are served with 1 h presigned URLs
```

`/api/health` should then report `"storage": true`. Photos persist in the `pleiades-photos` Docker volume.

**Production (Vultr Object Storage).** Set the real endpoint (for example `https://ewr1.vultrobjects.com`), region `ewr1`, keys and bucket in the VM's `.env`. Then allow uploads from the site's origin once per bucket:

```bash
backend/.venv/bin/python data/configure_bucket_cors.py https://<your-host>
backend/.venv/bin/python data/configure_bucket_cors.py --check   # show the current rules
```

Photo analysis needs a working `GEMINI_API_KEY`. Without one, or when the quota is used up, photos still appear on the map, marked "AI analysis unavailable". Only photos Gemini judges not to be night-sky pictures are hidden.

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

The backend calls these implemented functions through stable shared types. Physics scoring v2, optional trained calibration v3, Skyfield astronomy, and Gemini vision/explanations are documented in [AI_ML_HANDOFF.md](AI_ML_HANDOFF.md). The 3D viewer and deterministic score explanations remain usable without Gemini.

| File | Function | Called by |
|---|---|---|
| `backend/app/scoring/model.py` | `score_batch(FeatureBatch) -> ScoreBatch`, `MODEL_VERSION` | `ingest score` |
| `backend/app/astro/ephemeris.py` | `hourly_conditions`, `sky_events` | `ingest astro` |
| `backend/app/astro/ephemeris.py` | `night_summary` | `/api/sky-events` |
| `backend/app/astro/ephemeris.py` | `visible_objects` | photo worker (vision grounding) |
| `backend/app/ai/vision.py` | `analyze_photo(bytes, mime, VisionContext) -> VisionResult` | photo worker |
| `backend/app/ai/explain.py` | `explain_score(ExplainContext) -> Explanation` | `/api/spots/:id` (cached, with timeout fallback) |

`backend/scripts/seed_dev_grid.py` is a dev-only stand-in for `data/build_grid.py`, which samples the real light-pollution atlas.

## Frontend quickstart

Stop an existing Vite server with **Ctrl+C before running `npm ci`**, especially on Windows. A running server can lock Rolldown's native `.node` file and cause `EPERM: unlink`. After dependency installation, start Vite again.

```powershell
cd frontend
npm ci
npm run dev
```

Vite forwards `/api` to `http://127.0.0.1:5001`; run Flask separately with `--port 5001`. Override with `API_PROXY_TARGET` (or the older `PLEIADES_DEV_API_TARGET`). Production nginx still forwards to Gunicorn on port 8000.

Select a map spot or Tonight's best, choose a forecast hour, then use **Explore in 3D**. The viewer uses that spot/time; without a selected spot it uses an available in-region GPS fix or the WNY center. The sky panel and darkness ticks follow the same local night.

The explorer has **263 objects**, including 73 constellations that rise at least partly from WNY and all 110 Messier targets. Every card has a local 2D thumbnail. Search, category filters and batches of 24 make the atlas navigable. Visibility is the default sort: above-horizon estimates first, unknown next, below-horizon last; name sorting is also available. Fixed objects use approximate catalog-based altitude estimates, while planets/Moon use the matching backend rise/set summary. These estimates do not guarantee an observable view. Models start rotating automatically with **Pause rotation / Resume rotation**, including under reduced motion per the user's explicit preference. The atlas and viewer use local assets and do not require Gemini.

The optional **Visible tonight** switch starts off and combines with search/category filters before sorting and pagination. It means above the horizon sometime during the entire selected local night, rather than at the slider hour. It uses matched astronomical dusk/dawn, with sunset/sunrise as a fallback; missing or stale night information produces an explanation and no matches while the switch is on. Unknown visibility is excluded. Card statuses and default sorting still refer to the selected hour. No new endpoint or Gemini call is required.

For integration, read [frontend/EXPLORE_3D_HANDOFF.md](frontend/EXPLORE_3D_HANDOFF.md) first for the component contract, asset-generation order, scientific limits and test coverage. [frontend/README.md](frontend/README.md) gives runnable frontend setup and verification commands; [INTEGRATION_HANDOFF.md](INTEGRATION_HANDOFF.md) records full-stack status. Latest frontend verification: production build, **10 unit tests** and **17 browser tests** passed. Lint was not rerun for the atlas/sort update; run `npm run lint` when changing code. Install browser binaries with `npm run test:browser:install` before browser checks.
