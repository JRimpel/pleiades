# Pleiades Backend: Integration Guide

This guide is for the **AI/ML teammate**, the **frontend teammate**, and any coding agents working with them. It explains how to plug your part into the backend without reading every file. Read [Architecture.md](Architecture.md) for the product design and [README.md](README.md) for the short quickstart.

---

## 1. Ownership and ground rules

| Role | Owns | Does not touch |
|---|---|---|
| **A: Frontend** | `frontend/` | Anything under `backend/` |
| **B: Backend** | `backend/app/*` (except the seam bodies below), `backend/scripts/`, `backend/tests/`, `db/`, `infra/`, `docker-compose.yml`, `.env.example` | Seam function bodies |
| **C: AI/ML / Astro** | The **bodies** of the four seam files below, plus `data/` (grid and light-pollution preprocessing) | Routes, repo SQL, migrations, ingest jobs |

**Seam files (owned by role C).** Each one starts with an `OWNER: AI/ML` comment:

| File | Functions |
|---|---|
| `backend/app/scoring/model.py` | `score_batch`, `MODEL_VERSION` |
| `backend/app/astro/ephemeris.py` | `hourly_conditions`, `sky_events`, `night_summary`, `visible_objects` |
| `backend/app/ai/vision.py` | `analyze_photo` |
| `backend/app/ai/explain.py` | `explain_score` (keep `fallback_explanation` working) |

**Ground rules**
1. **Change function bodies, never signatures.** The backend imports these functions by name and module path.
2. **Contract files change only after a heads-up to the whole team:**
   - `backend/app/schemas/*.py`: the REST contract.
   - `backend/app/scoring/types.py`, `backend/app/astro/types.py`, `backend/app/ai/types.py`: the seam contracts.
3. **New tables or columns go in a new migration file** (see §8). Never edit a migration that has already been applied.
4. **Run `pytest` before pushing.** It has to pass offline, with no database and no network.
5. **Never commit `.env`.**

---

## 2. Architecture at a glance

```
Browser ──HTTPS──> nginx ──/api──> Flask (gunicorn) ──SQL──> Tiger Cloud (Postgres + TimescaleDB + PostGIS)
   │                                  │  └──> background photo workers ──> Gemini (vision)
   └──presigned PUT/GET──> Vultr Object Storage <──┘

systemd timers ──> python -m app.ingest {astro | weather | score} ──> Tiger Cloud
```

**Data pipeline** (each job writes to the DB and logs itself in `ingest_runs`):
1. **`ingest astro`** (daily) calls `ephemeris.hourly_conditions` and writes `astro_conditions`, then calls `ephemeris.sky_events` and writes `sky_events`.
2. **`ingest weather`** (every 3 h) fetches Open-Meteo for every `grid_cells` row and writes `weather_forecast`. Every revision is kept; nothing is overwritten.
3. **`score`** (hourly, and after each weather run):
   - Takes the latest forecast per cell-hour and joins in the cell data and astro conditions.
   - Calls `scoring.model.score_batch` and writes `score_snapshots`.
   - Refreshes the continuous aggregates `cell_hourly_score` and `cell_nightly_best`.
4. **API reads** come mostly from the continuous aggregates. Drift reads the raw `score_snapshots`.

**Photo pipeline:**
1. The browser presigns an upload, PUTs the file straight to Vultr, and then calls `POST /api/photos`.
2. The API inserts the row as `pending` and hands it to a background thread.
3. That thread downloads the original and writes a 512 px thumbnail.
4. It calls `ephemeris.visible_objects`, then `vision.analyze_photo`.
5. It updates the row to `done` or `rejected`.

---

## 3. AI/ML integration guide (role C)

The placeholders are deterministic and use no extra libraries, so the whole pipeline already runs. Replace them one at a time; everything else keeps working.

`backend/requirements.txt` already lists `skyfield` and `google-genai`. Add any other dependency you need there.

### 3.1 Scoring model: `app/scoring/model.py`

```python
MODEL_VERSION: int = 1
def score_batch(batch: FeatureBatch) -> ScoreBatch: ...
```

- **Called by:** `app/ingest/score.py`, once per run (hourly), with **every cell × hour** of the next ~72 h in a single batch (about 350 cells × 75 h ≈ 26k rows). Vectorize with NumPy; don't loop in Python where you can avoid it.
- **Input: `FeatureBatch`** (`app/scoring/types.py`). Every field is a NumPy array of shape `(N,)`, and **missing values are `NaN`**, never `None`.

| Field | Unit / meaning |
|---|---|
| `cell_id` | int64 |
| `valid_time` | `datetime64[s]`, UTC |
| `m_sky` | mag/arcsec², natural + artificial (higher = darker) |
| `bortle` | float |
| `elevation_m` | metres |
| `cloud_low`, `cloud_mid`, `cloud_high`, `cloud_total` | **percent, 0–100** |
| `visibility_m` | metres |
| `rh` | percent, 0–100 |
| `dew_point_c`, `temp_c` | °C |
| `wind_kmh` | km/h |
| `precip_prob` | percent, 0–100 |
| `sun_alt`, `moon_alt` | degrees (region centroid) |
| `moon_illum` | **fraction, 0–1** |
| `moon_phase_deg` | 0 = new, 180 = full |

- **Output: `ScoreBatch`**
  - `score`: shape `(N,)`, in **0–100**.
  - `nelm`: shape `(N,)`, the naked-eye limiting magnitude.
  - `factors`: a `list[dict[str, float]]` of length **N**. Each dict holds **points lost (negative) or gained (positive)** per factor.
  - Standard factor keys: `clouds`, `moon`, `light_pollution`, `haze`, `twilight`, `elevation`. The UI and `top_factor` use these. You may add keys.
- **Rules:**
  - Lengths must match, or the job fails with `ValueError`.
  - Rows whose score is `NaN`/`inf` are dropped, not stored.
  - **Bump `MODEL_VERSION` whenever the model's output changes.** It is stored on every snapshot and is part of the explanation cache key, so old and new scores stay comparable and old cached explanations aren't reused.
- **Test it:** `pytest tests/test_score_job.py` runs the real `score_batch` on fake rows, including `NaN`s, and checks the shapes, the score range, and the factor keys.

### 3.2 Ephemeris: `app/astro/ephemeris.py`

Types live in `app/astro/types.py`. `MoonInfo`, `Twilight`, `PlanetVisibility` and `NightSummary` are defined in `app/schemas/sky.py` and re-exported from there. **All datetimes are timezone-aware UTC.**

```python
def hourly_conditions(start: datetime, hours: int, lat: float, lon: float) -> list[AstroHour]
def sky_events(start: datetime, end: datetime, lat: float, lon: float) -> list[SkyEventRecord]
def night_summary(lat: float, lon: float, night: date, tz: str) -> NightSummary
def visible_objects(lat: float, lon: float, when: datetime) -> list[CandidateObject]
```

| Function | Caller | Notes |
|---|---|---|
| `hourly_conditions` | `ingest astro` (daily), at the region centroid (`REGION_CENTROID_LAT/LON`) | `start` is on the hour; return exactly `hours` rows, one per hour. Upserted on `time`. |
| `sky_events` | `ingest astro`, for the window `[now−6h, +8 days)` | `type` is one of `iss_pass`, `planet`, `meteor_shower`, `moonrise`, `moonset`, ... Upserted on `(type, name, time)`, so keep `name` stable for the same event. Put extra data (peak ZHR, ISS max altitude, ...) in `details`. |
| `night_summary` | `GET /api/sky-events`, on every request | `night` is the **local date the night starts on**; `tz` is `America/New_York`. Must be quick (well under ~200 ms); cache inside the module if needed. |
| `visible_objects` | The photo worker, once per photo | Return everything above the horizon at that time and place: planets, the Moon, and the curated bright stars and constellations. This list becomes the vision **candidates**. |

### 3.3 Vision: `app/ai/vision.py`

```python
def analyze_photo(image_bytes: bytes, mime_type: str, ctx: VisionContext) -> VisionResult
```

- **Called by:** `app/workers/photo_analysis.py`, in a **background thread pool** (`PHOTO_WORKERS` threads). Blocking is fine.
- **Input:**
  - The original image bytes.
  - `mime_type`: `image/jpeg`, `image/png` or `image/webp`.
  - `VisionContext{lat, lon, taken_at, candidates: list[CandidateObject], caption}`.
- **Output, and the `photos` column each field fills:**

| `VisionResult` field | Column |
|---|---|
| `is_night_sky` | `false` sets `ai_status = 'rejected'` (hidden from the map) |
| `description` | `ai_description` |
| `objects: list[{name, type, confidence 0–1}]` | `ai_objects` (jsonb) |
| `milky_way_visible` | `ai_milky_way_visible` |
| `sky_quality` (1–10) | `ai_sky_quality` |
| `light_pollution_notes` | `ai_light_pollution_notes` |

- **Rules:**
  - **Raise an exception on failure** (timeout, bad JSON, API error).
  - The worker makes **3 attempts** in total, then sets `ai_status = 'failed'` and stores the error in `ai_error`.
  - Don't swallow errors and return fake data.
  - Use the `GEMINI_API_KEY` and `GEMINI_MODEL` environment variables.
  - Filter out low-confidence objects yourself, or leave them in and the frontend can hide them.

### 3.4 Explanations: `app/ai/explain.py`

```python
def explain_score(ctx: ExplainContext) -> Explanation          # replace the body
def fallback_explanation(ctx: ExplainContext) -> Explanation   # keep: used on timeout or error
```

- **Called by:** `GET /api/spots/:id`, **synchronously** during the request. The call runs in a helper thread with an `EXPLAIN_TIMEOUT_S` timeout (default 8 s).
- **Input: `ExplainContext`**
  - Cell and spot name, `valid_time` plus a readable `local_time`.
  - `score`, `nelm`, `factors`, `bortle`.
  - `sun_alt`, `moon_alt`, `moon_illum`.
  - A `conditions` dict with the raw weather, and `visible_planets`.
- **Output:** `Explanation{summary: str, tips: list[str]}`.
- **Caching and fallback:**
  - On timeout or exception, the backend serves `fallback_explanation` and **does not cache it**.
  - Successful answers are cached in `score_explanations` per (cell, hour, `MODEL_VERSION`).

### 3.5 Grid preprocessing: `data/build_grid.py` → `grid_cells`

The backend never computes static cell data; it reads whatever is in `grid_cells`. The real grid has to follow these rules:

| Column | Meaning |
|---|---|
| `id` | serial. **Don't renumber after forecasts or photos exist**: other tables reference it. |
| `geom` | `ST_SetSRID(ST_MakePoint(lon, lat), 4326)::geography`, the **cell centre** |
| `name` | Set for curated spots only |
| `is_curated` | `true` for curated spots: drawn as **Points**, not grid squares |
| `elevation_m` | metres |
| `sky_brightness_mpsas` | mag/arcsec², natural + artificial |
| `bortle` | 1–9 |

- Grid squares are drawn as `±GRID_STEP_DEG/2` around each centre. The default is 0.1°; if you change the spacing, set `GRID_STEP_DEG` to match.
- Load the grid **before** the first `ingest weather` run.
- For local development, `python scripts/seed_dev_grid.py --no-elevation` builds a fake 356-cell grid plus 8 curated spots. Use it as a template.
- To replace a dev grid, use `--reset`. Add `--force` to also truncate the data that depends on it.

### 3.6 How to check your changes

```bash
cd backend && .venv/bin/python -m pytest -q        # offline; must pass
python -m app.ingest astro && python -m app.ingest score   # against a seeded DB
curl 'localhost:5000/api/spots/1'                  # see score, factors, explanation
curl 'localhost:5000/api/sky-events'               # see night_summary + events
```

---

## 4. Frontend integration guide (role A)

### 4.1 Basics
- **Base path:** `/api`.
  - In development, Vite proxies `/api` to `http://localhost:5000`.
  - In production, nginx serves the build and proxies `/api` on the same origin, so **no CORS is needed**.
- **JSON everywhere.** All timestamps are **ISO-8601 UTC**. Send `time` values the same way; naive timestamps are treated as UTC.
- **Auth:**
  1. `POST /api/users {username}` returns `{user_id, username, token}`.
  2. Store the token in `localStorage`.
  3. Send `Authorization: Bearer <token>` on routes marked ✔.
  - There is no login: the token is the identity.
- **Score labels:** Excellent ≥ 75, Good ≥ 50, Fair ≥ 25, Poor below that. The backend sends `label` alongside `score`; always show both.
- **Errors** always look like this:

```json
{"error": {"code": "validation_error", "message": "Invalid request", "details": [{"loc": ["lat"], "msg": "...", "type": "..."}]}}
```

| HTTP | `code` | When |
|---|---|---|
| 400 | `bad_request` | Bad query parameter (time, bbox, sort, ...) |
| 400 | `validation_error` | Body failed validation (`details` lists the fields). **Unknown body fields are rejected.** |
| 400 | `upload_not_found` | `POST /photos` before the PUT to storage finished |
| 401 | `unauthorized` | Missing or invalid token on a ✔ route |
| 404 | `not_found` | Unknown spot or photo |
| 409 | `username_taken`, `photo_exists` | Duplicate username / same upload registered twice |
| 413 | `file_too_large` | Over 15 MB |
| 415 | `unsupported_media_type` | Not JPEG/PNG/WebP |
| 429 | `rate_limited` | More than `UPLOADS_PER_HOUR` (20) uploads in an hour |
| 503 | `storage_unavailable` | Server has no storage configured |

### 4.2 Route reference

| Method | Route | Auth | Query / body |
|---|---|---|---|
| POST | `/users` | – | `{username}`: 3–32 chars, `[A-Za-z0-9_.-]` |
| GET | `/scores` | – | `time` (default: current hour), `bbox=w,s,e,n` (default: WNY) |
| GET | `/scores/range` | – | – |
| GET | `/best` | – | `time`, `near=lat,lon`, `radius_km` (default 60, used only with `near`), `limit` (default 5, max 50) |
| GET | `/spots/:cell_id` | – | `time` (default: current hour) |
| GET | `/spots/:cell_id/history` | – | `from` (default −7 days), `to` (default +72 h); max 31 days |
| GET | `/spots/:cell_id/drift` | – | `night=YYYY-MM-DD` (default: tonight) |
| GET | `/sky-events` | – | `lat`, `lon` (default: region centre), `date=YYYY-MM-DD` (default: tonight) |
| POST | `/photos/presign` | ✔ | `{content_type, size}` |
| POST | `/photos` | ✔ | `{s3_key, lat, lon, taken_at?, taken_at_source?: "exif"\|"user", caption? (≤500)}` |
| GET | `/photos` | – | `bbox`, `sort=recent\|top` (default `recent`), `limit` (default 200, max 500) |
| GET | `/photos/:id` | optional | A valid token fills in `my_vote`; an invalid token is treated as anonymous |
| POST | `/photos/:id/vote` | ✔ | `{value: 1 \| -1 \| 0}`; `0` removes your vote |
| GET | `/health` | – | Always HTTP 200; check `status` |

**"Tonight"** means the local night that starts on today's date in New York time. Before local noon, it means *last* night.

### 4.3 Response shapes (abridged)

`GET /api/scores` returns a GeoJSON FeatureCollection, plus the hour it is for:
```json
{
  "type": "FeatureCollection",
  "time": "2026-11-08T03:00:00Z",
  "features": [
    {"type": "Feature",
     "geometry": {"type": "Polygon", "coordinates": [[[-78.85,42.85],[-78.75,42.85],[-78.75,42.95],[-78.85,42.95],[-78.85,42.85]]]},
     "properties": {"cell_id": 117, "name": null, "score": 34.5, "label": "Fair", "bortle": 7, "top_factor": "light_pollution", "is_curated": false}},
    {"type": "Feature",
     "geometry": {"type": "Point", "coordinates": [-78.3864, 42.6678]},
     "properties": {"cell_id": 360, "name": "Beaver Meadow Audubon Center", "score": 71.2, "label": "Good", "bortle": 3, "top_factor": "moon", "is_curated": true}}
  ]
}
```
- **Grid cells are Polygons, curated spots are Points.** Style them as two layers.
- `score` and `label` are `null` when a cell has no score for that hour (for example, beyond the forecast window).

`GET /api/scores/range` returns `{"min_time": "...", "max_time": "...", "now": "..."}`. Use it to set the bounds of the time slider.

`GET /api/best`:
- **Without** `time`, it ranks tonight's nightly best: `"time": null, "night": "2026-11-07"`. Here each spot's `valid_time` is the hour of its best score.
- **With** `time`, it ranks that hour: `"night": null`.

```json
{"time": null, "night": "2026-11-07",
 "spots": [{"cell_id": 361, "name": "Allegany State Park", "is_curated": true, "lat": 42.1, "lon": -78.75,
            "score": 88.0, "label": "Excellent", "bortle": 2, "valid_time": "2026-11-08T07:00:00Z", "distance_km": null}]}
```
`distance_km` is set only when you pass `near`.

`GET /api/spots/:id`:
```json
{"cell_id": 361, "name": "Allegany State Park", "is_curated": true, "lat": 42.1, "lon": -78.75,
 "elevation_m": 640, "sky_brightness_mpsas": 21.7, "bortle": 2,
 "valid_time": "2026-11-08T03:00:00Z", "score": 62.0, "label": "Good", "nelm": 6.1,
 "factors": {"clouds": -20.5, "moon": -12.0, "light_pollution": -6.0, "haze": -1.5, "twilight": 0.0, "elevation": 2.0},
 "model_version": 1, "computed_at": "...",
 "conditions": {"fetched_at": "...", "cloud_low": 10, "cloud_mid": 5, "cloud_high": 40, "cloud_total": 45,
                "visibility_m": 24000, "rh": 72, "dew_point_c": -1, "temp_c": 4, "wind_kmh": 9, "precip_prob": 5},
 "astro": {"time": "...", "sun_alt": -48.2, "moon_alt": 22.0, "moon_illum": 0.78, "moon_phase_deg": 125.0},
 "explanation": {"summary": "...", "tips": ["..."]}}
```
- `factors` are points lost (negative) or gained (positive). Draw them as bars.
- `score`, `factors` and `explanation` are `null` when that hour has no score.
- This route can take a few seconds when the explanation isn't cached yet, so show a skeleton loader.

`GET /api/spots/:id/history` returns `{cell_id, from_time, to_time, hourly: [{time, score, nelm}], nightly: [{night: "YYYY-MM-DD", best_score, best_time}]}`.

`GET /api/spots/:id/drift` returns `{cell_id, night, window_start, window_end, revisions: [{computed_at, model_version, peak_score, points: [{valid_time, score}]}]}`.
- Each revision is one forecast run. Plotting `peak_score` against `computed_at` shows how the prediction changed.
- The night window is 18:00 to 06:00 local time.

`GET /api/sky-events`:
```json
{"date": "2026-11-07", "lat": 42.7, "lon": -78.4,
 "moon": {"phase_deg": 125.0, "illumination": 0.78, "phase_name": "Waxing Gibbous", "rise": null, "set": null},
 "twilight": {"sunset": "...", "civil_dusk": "...", "nautical_dusk": "...", "astronomical_dusk": "...", "astronomical_dawn": "...", "sunrise": "..."},
 "planets": [{"name": "Jupiter", "rise": "...", "set": "...", "max_alt_deg": 55.0, "magnitude": -2.5}],
 "events": [{"time": "...", "type": "meteor_shower", "name": "Leonids", "details": {"zhr": 15, "peak": true}}]}
```
Moon rise/set and the planet list are empty until role C replaces the placeholder astro module.

`GET /api/photos` returns `{photos: [{id, lat, lon, thumb_url, vote_count, taken_at, ai_status, ai_sky_quality}]}`.
- Rejected and failed photos are left out.
- Pending photos are included, and may have `thumb_url: null`.

`GET /api/photos/:id` returns:
- `id`, `username`, `url`, `thumb_url`, `lat`, `lon`, `cell_id`
- `taken_at`, `taken_at_source` (`exif|user|upload_time`), `uploaded_at`, `caption`, `score_at_capture`
- `ai_status` (`pending|done|failed|rejected`), `ai_description`, `ai_objects: [{name, type, confidence}]`
- `ai_sky_quality`, `ai_milky_way_visible`, `ai_light_pollution_notes`
- `vote_count`, `my_vote`

The image URLs are either public or presigned for 1 hour, so don't cache them for long.

`GET /api/health` returns `{status: "ok"|"degraded", db, storage, last_weather_fetch, last_score_run, model_version}`.

### 4.4 Upload flow (step by step)

```
1. User picks a file. Read GPS and capture time with exifr; if there's no GPS, ask the user to drop a pin.
2. POST /api/photos/presign  {content_type: file.type, size: file.size}
      -> {upload_url, s3_key, method: "PUT", headers: {"Content-Type": ...}, expires_in: 900}
3. PUT file to upload_url with EXACTLY `headers` (they're part of the signature; a different
   Content-Type or size gives a 403 from storage). Use XHR if you want a progress bar.
4. POST /api/photos  {s3_key, lat, lon, taken_at?, taken_at_source?, caption?}
      -> 201 {id, ai_status: "pending"}
5. Poll GET /api/photos/:id every ~2 s until ai_status != "pending"
      done -> show AI results;  rejected -> "doesn't look like a night sky";  failed -> graceful error.
```
- Without `taken_at`, the backend uses the upload time (`taken_at_source: "upload_time"`) and `score_at_capture` stays null.
- When you send `taken_at`, `taken_at_source` defaults to `"exif"`. Send `"user"` if the user typed the time.

### 4.5 Voting
- `POST /photos/:id/vote {value}` returns `{photo_id, vote_count, my_vote}`. Sending the same value again is harmless; `0` clears your vote.
- On a 401, show the one-screen username prompt, create the user, and retry.

---

## 5. Running locally

```bash
cp .env.example .env                       # set DATABASE_URL (docker default is fine)
docker compose up -d db                    # TimescaleDB + PostGIS on :5432
cd backend
python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m app.migrate            # applies db/migrations/*.sql (use --dry-run to preview)
.venv/bin/python scripts/seed_dev_grid.py  # add --no-elevation to skip the network
.venv/bin/python -m app.ingest all         # astro -> weather -> score
.venv/bin/flask --app app run --debug      # http://localhost:5000/api/health
.venv/bin/python -m pytest -q              # offline tests
TEST_DATABASE_URL=postgres://postgres:password@localhost:5432/pleiades_test .venv/bin/python -m pytest -m db
```
- The app **boots without a database or storage**: `/api/health` then reports `degraded`, and DB-backed routes return 500. This lets the frontend start early.
- Photo uploads need real Vultr credentials, or another S3-compatible service set through `VULTR_S3_*`.

---

## 6. Data model cheat sheet

All migrations are in `db/migrations/`.

| Object | Kind | What it holds |
|---|---|---|
| `grid_cells` | table | Static cells and curated spots: location, elevation, sky brightness, Bortle (§3.5) |
| `weather_forecast` | hypertable | **Every** forecast revision, keyed by `(cell_id, valid_time, fetched_at)` |
| `astro_conditions` | hypertable | Hourly sun/moon at the region centroid |
| `score_snapshots` | hypertable | **Every** model run, keyed by `(cell_id, valid_time, computed_at)`, with `factors` and `model_version` |
| `cell_hourly_score` | continuous aggregate | Freshest score per cell-hour (`last(score, computed_at)`). Backs the map and the slider. |
| `cell_nightly_best` | hierarchical continuous aggregate | Best score per cell per local noon-to-noon night |
| `score_explanations` | table | Cached Gemini explanations |
| `users`, `photos`, `votes` | tables | Identity, uploads with their AI results, up/down votes |
| `sky_events` | hypertable | Meteor showers, ISS passes, planets, moonrise/set |
| `ingest_runs` | table | Job log; powers `/health` |
| `schema_migrations` | table | Applied migration files |

Policies:
- Compression after 7 days on `weather_forecast` and `score_snapshots`.
- Raw forecast revisions are dropped after 30 days.
- The aggregates refresh every 30–60 minutes, and also right after each score run.

---

## 7. Jobs and deploy

| Unit | Schedule | Command |
|---|---|---|
| `pleiades-ingest-astro.timer` | Daily 12:00 UTC, plus 2 min after boot | `python -m app.ingest astro` |
| `pleiades-ingest-weather.timer` | Every 3 h at :05 (00:05, 03:05, ...) | `python -m app.ingest weather`, then starts a score run |
| `pleiades-score.timer` | Hourly at :15 | `python -m app.ingest score` |
| `pleiades-api.service` | Always on | gunicorn `gthread` on `127.0.0.1:8000` |

- **Deploy:** run `infra/deploy.sh` on the VM. It runs `git pull`, builds the frontend, installs the backend dependencies, runs `migrate`, installs the systemd units, and restarts the API.
- **Configuration:** see `.env.example` for the full list. The main variables:
  - Database and AI: `DATABASE_URL`, `GEMINI_API_KEY`, `GEMINI_MODEL`.
  - Storage: `VULTR_S3_ENDPOINT/ACCESS_KEY/SECRET_KEY/BUCKET`, plus optional `VULTR_S3_PUBLIC_BASE`.
  - Region and grid: `REGION_TZ`, `GRID_STEP_DEG`, `REGION_CENTROID_LAT/LON`, `FORECAST_HOURS`.
  - Limits: `MAX_UPLOAD_BYTES`, `UPLOADS_PER_HOUR`, `PHOTO_WORKERS`, `EXPLAIN_TIMEOUT_S`.

---

## 8. Changing the backend safely

- **New migration:** add `db/migrations/00N_description.sql`.
  - `app.migrate` splits each file into statements and runs each one in autocommit mode, which continuous aggregates require.
  - A file is recorded as applied only after every statement in it succeeds.
- **SQL lives in `app/repo/`.** Routes stay thin.
- **New route:**
  1. Add the Pydantic request and response models to `app/schemas/`.
  2. Add a repo function.
  3. Add the route to the right blueprint in `app/api/`. New blueprints are registered in `app/api/__init__.py`.
  4. Return `Model(...).model_dump(mode="json")` and raise `ApiError` for errors.
  5. Add a test in `tests/test_api_*.py` that monkeypatches the repo function.
- **Settings:**
  - Add new settings to `app/config.py` and `.env.example`.
  - Inside requests, read them with `current_settings()`.
  - In jobs, use `get_settings()`.

---

## 9. Known gaps and risks

1. **No SQL has run against a real database yet.** Docker was off during development, so the 112 offline tests mock the database. The first `docker compose up` followed by `pytest -m db` is the real check.
2. **The `cell_nightly_best` aggregate** uses a time-zone-aware 1-day bucket with a 12 h offset. That needs a recent TimescaleDB (about 2.13+; Tiger Cloud should be fine). If creating it fails, switch to a UTC bucket with an `origin` at local noon.
3. **Stale hourly scores between refreshes:** future buckets of `cell_hourly_score` are materialized, so a new score revision shows up only after a refresh. The score job refreshes straight after each run; this only matters if that refresh fails.
4. **The placeholder astro is approximate.** The sun is within about 1°. The moon altitude is crude, and moonrise/set and planets are empty. Moon-related scores aren't realistic until role C replaces it.
5. **The placeholder vision and explanation** return neutral or template text.
6. **The integration test truncates its tables.** Always point `TEST_DATABASE_URL` at a throwaway database.
7. **Nothing is committed to git yet.**
