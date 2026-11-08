# Pleiades Backend: A Guide for New Developers

This guide assumes you have never seen this project before. It explains what Pleiades does, how the backend is organized, the handful of ideas you need to understand the code, and where to start reading. It is an orientation, not a reference. When you need exact details, go to:

- [README.md](README.md): quickstart commands.
- [Architecture.md](Architecture.md): the full product and system design, including the scoring math.
- [backend-documentation.md](backend-documentation.md): the integration contract, with every route, request and response shape, and seam function.

---

## 1. What Pleiades is

Pleiades helps people in **Western New York (WNY)** find the best place and time to go stargazing. It does two things:

1. **The score map.** It divides the region into a grid and gives every grid cell a **Stargazing Score from 0 to 100** for every hour of the next ~72 hours. The score combines:
   - light pollution
   - the weather forecast (clouds, haze, humidity)
   - the sun and moon positions
   - elevation

   A web map colors each cell by its score, and a time slider lets you scrub through the forecast.
2. **Community sky photos.** Users upload night-sky photos and pin them to the map. An AI model (Google Gemini) describes each photo and identifies the stars and planets in it. Other users can upvote or downvote photos.

Pleiades is a hackathon project (UB Hacking 2026) with three roles:

| Role | Owns |
|---|---|
| Frontend | The React + MapLibre web app in `frontend/`. The score map is built; see [frontend-documentation.md](frontend-documentation.md). |
| **Backend** | The API, database, data pipeline, storage, and deployment |
| AI/ML | The "smart" parts: the scoring model, the astronomy calculations, and the Gemini prompts |

**This document covers the backend.**

---

## 2. Tech stack at a glance

| Concern | Technology | Where you'll see it |
|---|---|---|
| Language | Python 3.11+ | `backend/` |
| Web framework | Flask, served in production by gunicorn | [backend/app/__init__.py](backend/app/__init__.py), [backend/app/api/](backend/app/api/) |
| Request/response validation | Pydantic v2 | [backend/app/schemas/](backend/app/schemas/) |
| Database | PostgreSQL with the **TimescaleDB** (time-series) and **PostGIS** (geospatial) extensions. "Tiger Data" / Tiger Cloud is the hosted version. | [db/migrations/](db/migrations/) |
| DB driver | `psycopg` 3 with a connection pool. Raw SQL, **no ORM**. | [backend/app/db.py](backend/app/db.py), [backend/app/repo/](backend/app/repo/) |
| Weather data | Open-Meteo (free forecast API) | [backend/app/ingest/openmeteo.py](backend/app/ingest/openmeteo.py) |
| Astronomy | `skyfield` (sun, moon, planets), implemented by the AI/ML role | [backend/app/astro/](backend/app/astro/) |
| AI | Google Gemini via `google-genai`, implemented by the AI/ML role. Live calls currently fail (HTTP 400), so explanations use the fallback text. | [backend/app/ai/](backend/app/ai/) |
| Photo storage | Vultr Object Storage (S3-compatible), accessed with `boto3` | [backend/app/storage/](backend/app/storage/) |
| Numerical work | NumPy | [backend/app/scoring/](backend/app/scoring/) |
| Hosting | One Vultr Linux VM: nginx in front, gunicorn for the API, systemd timers for scheduled jobs | [infra/](infra/) |
| Local DB | Docker Compose (TimescaleDB + PostGIS image) | [docker-compose.yml](docker-compose.yml) |

---

## 3. The big picture

The backend has two halves that share one database:

- **The API** answers requests from the browser.
- **The jobs** run on a schedule, pull in outside data, and compute scores.

```
                         ┌────────────────────── Vultr VM ──────────────────────┐
 Browser ──HTTPS──> nginx ──/api──> Flask API (gunicorn)                         │
    │                    │              │   └─ background threads: photo AI ─────┼──> Gemini
    │                    │              │                                        │
    │                    │   systemd timers ──> python -m app.ingest ... ────────┼──> Open-Meteo
    │                    └──────────────┼────────────────┼───────────────────────┘
    │                                   ▼                ▼
    │                         PostgreSQL + TimescaleDB + PostGIS
    │
    └──── presigned PUT/GET ────> Vultr Object Storage (photos, thumbnails)
```

The **jobs write** data, and the **API mostly reads** it. The two halves never call each other directly. They only communicate through the database. This is the most useful fact to keep in mind while you read the code.

---

## 4. Repository tour

```
pleiades/
├── README.md, Architecture.md, backend-documentation.md   # docs (read in that order)
├── .env.example            # every config variable; copy to .env (never commit .env)
├── docker-compose.yml      # local TimescaleDB + PostGIS
├── db/migrations/          # SQL schema, applied in order by app.migrate
├── infra/                  # nginx config, systemd units/timers, deploy.sh
└── backend/
    ├── requirements*.txt
    ├── scripts/seed_dev_grid.py   # synthetic fallback grid for offline work (the real grid is data/wny_grid.geojson)
    ├── tests/                     # pytest; offline by default
    └── app/                       # the Python package
```

Inside `backend/app/`:

| Path | What it does | Open first |
|---|---|---|
| `__init__.py` | `create_app()`, the **app factory**: builds the Flask app, sets up the DB pool, error handlers, routes, and the photo workers | [__init__.py](backend/app/__init__.py) |
| `config.py` | `Settings` dataclass loaded from environment variables | [config.py](backend/app/config.py) |
| `db.py` | Connection pool (`get_conn()` for the API) and `connect_direct()` for jobs | [db.py](backend/app/db.py) |
| `errors.py` | `ApiError` and the handlers that turn every error into the standard JSON shape | [errors.py](backend/app/errors.py) |
| `auth.py` | Bearer-token helpers and the `@require_auth` decorator | [auth.py](backend/app/auth.py) |
| `migrate.py` | Applies `db/migrations/*.sql` and records them in `schema_migrations` | [migrate.py](backend/app/migrate.py) |
| `geo.py`, `timeutil.py` | Small helpers: bounding boxes and GeoJSON shapes; UTC, hours, and "tonight" | |
| `api/` | **Flask blueprints**, one per area: `scores`, `spots`, `photos`, `users`, `sky`, `health`. Thin route handlers. | [api/scores.py](backend/app/api/scores.py) |
| `schemas/` | Pydantic models for every request and response. **This is the API contract** with the frontend. | [schemas/scores.py](backend/app/schemas/scores.py) |
| `repo/` | **All SQL lives here.** One module per area. The functions return plain dicts. | [repo/scores.py](backend/app/repo/scores.py) |
| `ingest/` | The jobs: `grid` (one-off load of `data/wny_grid.geojson`), `weather`, `astro`, `score`, and `bootstrap` (all four in order). The entry point is `python -m app.ingest`. | [ingest/__main__.py](backend/app/ingest/__main__.py) |
| `scoring/` | The scoring model (AI/ML seam) and its input/output types | [scoring/model.py](backend/app/scoring/model.py) |
| `astro/` | Sun, moon, planets, and sky events (AI/ML seam) | [astro/ephemeris.py](backend/app/astro/ephemeris.py) |
| `ai/` | Gemini photo analysis and score explanations (AI/ML seams) | [ai/vision.py](backend/app/ai/vision.py) |
| `storage/` | S3 presigned URLs, downloads, and thumbnail generation (Pillow) | [storage/s3.py](backend/app/storage/s3.py) |
| `workers/` | Background thread pool that analyzes uploaded photos | [workers/photo_analysis.py](backend/app/workers/photo_analysis.py) |

---

## 5. Key concepts

### 5.1 The grid and curated spots
The region (roughly lat 42.0–43.4, lon −79.8 to −77.0) is split into a **0.1° grid**, about 8–11 km per cell. Cells over Lake Erie and Lake Ontario are dropped. Each cell is a row in the `grid_cells` table, and its location is stored as a **PostGIS `geography` point** at the cell's center. The API draws each cell as a square around that point.

A few well-known stargazing locations, such as Allegany State Park, are **curated spots**. They live in the same table with `is_curated = true`, and the API returns them as map **Points** instead of squares.

Each cell has static attributes that never change:
- elevation
- sky brightness (light pollution), in **mag/arcsec²**: higher means darker, and ~22 is pristine
- **Bortle class**: a 1–9 darkness scale, where 1 is darkest

**Why it matters:** almost every table references `grid_cells.id`, so cell IDs must never be renumbered once data exists.

### 5.2 The Stargazing Score
For each cell and hour, the model estimates how many stars a person could actually see. It uses **NELM** (naked-eye limiting magnitude, the faintest star visible) and reduces it for clouds, haze, twilight, and moonlight. The result is a number from 0 to 100, plus a label: Excellent ≥ 75, Good ≥ 50, Fair ≥ 25, otherwise Poor.

Along with the score, the model returns a **factor breakdown**: how many points each cause cost or added, for example `{"clouds": -20, "moon": -12, "elevation": +2}`. The UI draws these as bars, and the `top_factor` field on the map is the biggest loss. The full math is in [Architecture.md §6](Architecture.md).

### 5.3 Time-series storage: keep every revision
Weather forecasts change every few hours. Most apps overwrite the old forecast. **Pleiades keeps every version.**

- `weather_forecast` is keyed by `(cell_id, valid_time, fetched_at)`:
  - `valid_time` is the hour being forecast.
  - `fetched_at` is when we asked for the forecast.
- `score_snapshots` works the same way, using `computed_at`.

This turns the database into a "sensor log." It lets the app answer questions like "how did tonight's predicted score change over the last two days?" (the `/spots/:id/drift` route).

These big, append-only, time-keyed tables are TimescaleDB **hypertables**. To you, a hypertable looks like a normal Postgres table. Behind the scenes it is split into time chunks, so time-range queries stay fast, and old chunks can be compressed or dropped by policy. See [db/migrations/003_policies.sql](db/migrations/003_policies.sql).

### 5.4 Continuous aggregates: precomputed read models
Because every revision is kept, the "current" score for a cell and hour is *the latest snapshot*. Computing that on every map request would be slow. Instead, TimescaleDB keeps two **continuous aggregates**, which are materialized views that refresh incrementally:

- `cell_hourly_score`: the freshest score per cell per hour. The map and time slider read from this.
- `cell_nightly_best`: the best score per cell per night, built on top of the hourly aggregate. The "Tonight's best spots" feature reads from this.

Both are defined in [db/migrations/002_aggregates.sql](db/migrations/002_aggregates.sql). The score job refreshes them right after it writes new snapshots.

### 5.5 Presigned uploads
Photos never pass through the Flask server. Instead:

1. The API generates a **presigned URL**: a short-lived URL that grants permission to upload one specific file to the storage bucket.
2. The browser uploads the file directly to that URL.

This keeps large uploads off our server. The presigned URL locks in the content type and size, so the browser must send exactly the headers the API returned.

### 5.6 Auth: bearer tokens
There are no passwords:

1. `POST /api/users {username}` returns a random **token**.
2. The browser stores the token and sends `Authorization: Bearer <token>` on routes that need a user (uploading and voting).

The database stores only a SHA-256 **hash** of the token, so a leaked database doesn't leak working tokens. See [auth.py](backend/app/auth.py).

### 5.7 Seams
The backend was built before the AI/ML work was done. To unblock everyone, the AI/ML entry points are **seams**: functions with fixed signatures that started with simple placeholder bodies, so the pipeline could run end to end early.

The AI/ML teammate has since replaced the bodies with real implementations: physics scoring v2, Skyfield astronomy, and Gemini vision and explanations. See [AI_ML_HANDOFF.md](AI_ML_HANDOFF.md). The seam mechanism still applies to any future change.

| Seam | Used by |
|---|---|
| `scoring/model.py` → `score_batch` | the score job |
| `astro/ephemeris.py` → `hourly_conditions`, `sky_events`, `night_summary`, `visible_objects` | the astro job, `/api/sky-events`, the photo worker |
| `ai/vision.py` → `analyze_photo` | the photo worker |
| `ai/explain.py` → `explain_score` | `/api/spots/:id` |

Each seam file starts with an `OWNER: AI/ML` comment, and its input and output types live in the package's `types.py`. **Don't change seam signatures.** [backend-documentation.md §3](backend-documentation.md) is the full contract.

---

## 6. How data moves

### 6.1 The scheduled pipeline
Each job is a CLI command run by a systemd timer (see [infra/](infra/)). You can also run them by hand.

| Order | Command | Production schedule | Reads | Writes |
|---|---|---|---|---|
| 1 | `python -m app.ingest astro` | daily at 12:00 UTC, and 2 min after boot | `astro.ephemeris` | `astro_conditions`, `sky_events` |
| 2 | `python -m app.ingest weather` | every 3 h at :05 | `grid_cells`, Open-Meteo API | `weather_forecast` (new revision) |
| 3 | `python -m app.ingest score` | hourly at :15, and right after each weather run | latest forecast + `astro_conditions` + `grid_cells` | `score_snapshots`, then refreshes both aggregates |

`python -m app.ingest all` runs these three in order. On a fresh database, use `python -m app.ingest bootstrap` instead. It first runs `ingest grid`, which loads the real grid from `data/wny_grid.geojson` and does nothing once loaded, then astro, weather, and score.

Every run is wrapped by `run_job()` in [ingest/__main__.py](backend/app/ingest/__main__.py), which records it in the `ingest_runs` table with status `ok` or `error`. `/api/health` uses that table to report when data was last refreshed.

The score job ([ingest/score.py](backend/app/ingest/score.py)) is the most interesting one:
1. It loads every cell × hour in the forecast window, about 26k rows.
2. It packs them into NumPy arrays (a `FeatureBatch`).
3. It calls `score_batch` once.
4. It validates the output and bulk-inserts it with `COPY`.

### 6.2 The photo pipeline
```
Browser                         API                              Background worker
───────                         ───                              ─────────────────
POST /photos/presign  ───────>  returns upload_url + s3_key
PUT file to upload_url ──────>  (goes straight to Vultr storage)
POST /photos {s3_key, lat, …} > inserts row, ai_status=pending ─> 1. download original
                                returns 201 {id}                  2. write 512px thumbnail
GET /photos/:id (poll ~2s)                                        3. visible_objects(lat, lon, time)
   until status ≠ pending                                         4. analyze_photo(image, candidates)
                                                                  5. status = done | rejected
```

**Grounding:** step 3 computes which planets and bright stars were actually above the horizon at that time and place. The worker passes that list to Gemini as the only allowed candidates, which reduces made-up answers.

The final status depends on the result:
- `rejected`: Gemini says the photo isn't a night sky. The photo is hidden from the map.
- `failed`: every attempt raised an error. There are **3 attempts**, with backoff between them.

On startup, the worker also re-queues photos that have been `pending` for more than 10 minutes. This recovers from a server restart in the middle of an analysis. See [workers/photo_analysis.py](backend/app/workers/photo_analysis.py).

---

## 7. Tracing one request: `GET /api/scores`

Following one request through the code is the fastest way to learn the layering. This is the route that draws the map.

1. **App setup.** [create_app()](backend/app/__init__.py) builds the Flask app, then:
   - loads `Settings`
   - registers error handlers
   - opens the DB pool
   - calls `register_blueprints()` in [api/__init__.py](backend/app/api/__init__.py), which mounts every blueprint under `/api`
2. **Route.** `get_scores()` in [api/scores.py](backend/app/api/scores.py) runs and does three things:
   - `hour_arg()` from [api/params.py](backend/app/api/params.py) parses `?time=` and rounds it down to the hour. If the parameter is missing, it uses the current hour.
   - `parse_bbox()` from [geo.py](backend/app/geo.py) parses `?bbox=`. If the parameter is missing, it uses the whole region.
   - Bad input raises `bad_request(...)`, which is an `ApiError`.
3. **Repo / SQL.** `scores_repo.scores_at(hour, bbox)` in [repo/scores.py](backend/app/repo/scores.py):
   - Gets a pooled connection with `get_conn()`.
   - Selects `grid_cells` inside the bounding box using the PostGIS `&&` operator.
   - LEFT JOINs `cell_hourly_score` for that hour. Unscored cells still come back, with `score = NULL`.
   - Returns a list of dicts.
4. **Shaping the response.** Back in the route, each row becomes a GeoJSON feature:
   - Curated spots become Points and grid cells become Polygons.
   - The Pydantic models `ScoreFeatureProperties`, `ScoreFeature`, and `ScoresResponse` from [schemas/scores.py](backend/app/schemas/scores.py) build the payload.
   - `score_label()` and `top_factor()` fill in the derived fields.
5. **Serialization.** The route returns `ScoresResponse(...).model_dump(mode="json")`, and Flask sends it as JSON.
6. **Errors.** Any `ApiError` or Pydantic `ValidationError` raised along the way is caught by the handlers in [errors.py](backend/app/errors.py). They return `{"error": {"code", "message", "details"}}` with the right HTTP status. An unexpected exception becomes a 500 with code `internal_error`.

Every other route follows the same **route → repo → schema** pattern.

---

## 8. Conventions to follow

- **SQL goes in `repo/` only.** Routes parse input, call repo functions, and build Pydantic responses. Nothing else.
- **`schemas/` is a team contract.** The frontend codes against it. Change it only after telling the team.
- **Never change seam signatures**, or the types in `scoring/types.py`, `astro/types.py`, and `ai/types.py`, without the same heads-up.
- **Schema changes go in a new migration file**, for example `db/migrations/004_something.sql`. Never edit a migration that has already been applied.
- **Errors:** raise `ApiError` (or `bad_request`, `not_found`, `unauthorized`). Don't build error JSON by hand.
- **Settings:** add new ones to `config.py` *and* `.env.example`.
  - Inside a request, read them with `current_settings()`.
  - In jobs, use `get_settings()`.
- **Time:** everything is timezone-aware **UTC**. Convert to `America/New_York` only for "which night is it" logic, using the helpers in [timeutil.py](backend/app/timeutil.py).
- **Tests run offline.** API tests use the `client` fixture from [tests/conftest.py](backend/tests/conftest.py), which builds the app with no DB, and **monkeypatch the repo function**. See `test_scores_geojson` in [tests/test_api_scores.py](backend/tests/test_api_scores.py) for the pattern. Tests that need a real database are marked `db` and run only when you ask for them with `-m db`.

---

## 9. Running it locally (short version)

```bash
docker compose up -d db                       # local TimescaleDB + PostGIS
cd backend && python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
cp ../.env.example ../.env                    # defaults point at the docker DB
.venv/bin/python -m app.migrate               # create tables
.venv/bin/python -m app.ingest bootstrap      # real grid -> astro -> weather -> score
.venv/bin/flask --app app run --debug         # http://localhost:5001/api/health (port from backend/.flaskenv)
.venv/bin/python -m pytest -q                 # offline tests
cd ../frontend && npm ci && npm run dev       # map at http://localhost:5173 (proxies /api to :5001)
```

Flask runs on port **5001**, set by `FLASK_RUN_PORT` in `backend/.flaskenv` (macOS AirPlay occupies 5000). That file is not committed yet. If yours is missing, add `--port 5001` to the `flask run` command.

The app starts even without a database or storage configured. In that case `/api/health` reports `degraded`, and DB-backed routes return 500. Photo uploads need real S3 credentials. The [README](README.md) has the full instructions, including how to run the integration tests safely.

---

## 10. Suggested reading order for day one

1. [README.md](README.md), then skim [Architecture.md](Architecture.md) §1–5.
2. [db/migrations/001_init.sql](db/migrations/001_init.sql): the tables are the clearest map of the domain.
3. [backend/app/__init__.py](backend/app/__init__.py) and [config.py](backend/app/config.py).
4. The `GET /api/scores` trace from §7, then [tests/test_api_scores.py](backend/tests/test_api_scores.py).
5. [ingest/__main__.py](backend/app/ingest/__main__.py) → [ingest/score.py](backend/app/ingest/score.py) → [scoring/model.py](backend/app/scoring/model.py).
6. [api/photos.py](backend/app/api/photos.py) → [workers/photo_analysis.py](backend/app/workers/photo_analysis.py).
7. [backend-documentation.md](backend-documentation.md) as a reference whenever you touch a route or seam.

---

## 11. Glossary

| Term | Meaning |
|---|---|
| **App factory** | A function (`create_app`) that builds and configures the Flask app on demand, so tests can create one with different settings. |
| **Blueprint** | A Flask group of related routes, registered on the app with a URL prefix. |
| **Bortle class** | A 1–9 scale of night-sky darkness. 1 is a pristine dark site, 9 is an inner city. |
| **mag/arcsec²** | Unit of sky surface brightness. It is logarithmic, and **higher is darker**. |
| **NELM** | Naked-eye limiting magnitude: the faintest star you can see. ~6.5+ is a dark sky. |
| **Ephemeris** | Calculated positions of the sun, moon, and planets at a given time and place. |
| **Hypertable** | A TimescaleDB table automatically split into time chunks, which enables fast time queries, compression, and retention. |
| **Continuous aggregate** | A TimescaleDB materialized view that refreshes incrementally as new data arrives. |
| **PostGIS / `geography`** | The Postgres geospatial extension. `geography` columns store lat/lon points and support distance and bounding-box queries. |
| **Presigned URL** | A temporary URL that lets the holder upload or download one object in a storage bucket without credentials. |
| **Bearer token** | A secret string sent in the `Authorization` header. Whoever has it is treated as that user. |
| **Seam** | A function boundary with a fixed signature, whose body one teammate replaces (it starts as a placeholder) without changing anyone else's code. |
| **Revision** | One fetched forecast or one score computation. Pleiades keeps all of them. |

---

## 12. Current status and known gaps

- **The database path is verified.** `pytest -m db` passes (6/6) against TimescaleDB 2.31 + PostGIS. A local `ingest bootstrap --reset-grid` loaded the real 364-cell grid and scored 26,208 cell-hours.
- **The AI/ML seams are implemented** (see [AI_ML_HANDOFF.md](AI_ML_HANDOFF.md)), but **live Gemini calls fail with HTTP 400**. Explanations fall back to template text, and photo analysis cannot finish.
- **`cell_nightly_best` needs a recent TimescaleDB (about 2.13+)** because it uses a time-zone-aware daily bucket. TimescaleDB 2.2x+ also requires the hourly and nightly aggregates to share a time zone and offset. See [backend-documentation.md §9](backend-documentation.md).
- **The real grid exists.** `data/build_grid.py` produced `data/wny_grid.geojson`, which `ingest grid` loads. [scripts/seed_dev_grid.py](backend/scripts/seed_dev_grid.py) is now only a synthetic offline fallback.
- **Frontend:** the score map, with its hour slider, calls `/api/scores` and `/api/scores/range`. The spot panel, photos, and voting aren't built yet. See [frontend-documentation.md](frontend-documentation.md).
- **The integration tests truncate tables.** Always point `TEST_DATABASE_URL` at a throwaway database.

For the full list, see [backend-documentation.md §9](backend-documentation.md).
