-- Pleiades: base schema (Architecture §8) plus backend additions marked "added".
CREATE EXTENSION IF NOT EXISTS timescaledb;
CREATE EXTENSION IF NOT EXISTS postgis;

-- Users: lightweight identity
CREATE TABLE users (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  username    text UNIQUE NOT NULL,
  token_hash  text NOT NULL,            -- sha256 of a random bearer token
  created_at  timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX users_token_hash_idx ON users (token_hash);  -- added

-- Static spatial grid + curated spots (loaded by data/build_grid.py)
CREATE TABLE grid_cells (
  id                   serial PRIMARY KEY,
  geom                 geography(Point, 4326) NOT NULL,
  name                 text,                 -- set for curated spots
  is_curated           boolean NOT NULL DEFAULT false,
  elevation_m          real,
  sky_brightness_mpsas real,                 -- mag/arcsec², natural + artificial
  bortle               smallint
);
CREATE INDEX grid_cells_geom_idx ON grid_cells USING gist (geom);

-- Weather forecasts: every revision kept (sensor log)
CREATE TABLE weather_forecast (
  valid_time   timestamptz NOT NULL,
  cell_id      int NOT NULL REFERENCES grid_cells(id),
  fetched_at   timestamptz NOT NULL,
  cloud_low    real, cloud_mid real, cloud_high real, cloud_total real,
  visibility_m real, rh real, dew_point_c real, temp_c real,
  wind_kmh     real, precip_prob real,
  PRIMARY KEY (cell_id, valid_time, fetched_at)
);
SELECT create_hypertable('weather_forecast', by_range('valid_time', INTERVAL '1 day'));

-- Sun / moon ephemeris (region centroid, hourly)
CREATE TABLE astro_conditions (
  time        timestamptz PRIMARY KEY,
  sun_alt     real, moon_alt real, moon_illum real, moon_phase_deg real
);
SELECT create_hypertable('astro_conditions', by_range('time', INTERVAL '7 days'));

-- Model output: every computation kept
CREATE TABLE score_snapshots (
  valid_time    timestamptz NOT NULL,
  cell_id       int NOT NULL REFERENCES grid_cells(id),
  computed_at   timestamptz NOT NULL,
  score         real NOT NULL,
  nelm          real,
  factors       jsonb,
  model_version smallint NOT NULL,
  PRIMARY KEY (cell_id, valid_time, computed_at)
);
SELECT create_hypertable('score_snapshots', by_range('valid_time', INTERVAL '1 day'));

-- Cached Gemini explanations
CREATE TABLE score_explanations (
  cell_id int, valid_time timestamptz, model_version smallint,
  summary text, tips jsonb, created_at timestamptz DEFAULT now(),
  PRIMARY KEY (cell_id, valid_time, model_version)
);

-- Photos + votes
CREATE TABLE photos (
  id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id          uuid NOT NULL REFERENCES users(id),
  s3_key           text NOT NULL UNIQUE,
  thumb_key        text,
  mime_type        text,                     -- added
  geom             geography(Point, 4326) NOT NULL,
  cell_id          int REFERENCES grid_cells(id),
  taken_at         timestamptz,
  taken_at_source  text,                     -- 'exif' | 'user' | 'upload_time'
  uploaded_at      timestamptz NOT NULL DEFAULT now(),
  caption          text,
  score_at_capture real,
  ai_status        text NOT NULL DEFAULT 'pending',   -- pending | done | failed | rejected
  ai_description   text,
  ai_objects       jsonb,
  ai_sky_quality   smallint,
  ai_milky_way_visible     boolean,          -- added
  ai_light_pollution_notes text,             -- added
  ai_attempts      smallint NOT NULL DEFAULT 0,       -- added
  ai_error         text,                     -- added
  ai_updated_at    timestamptz,              -- added
  vote_count       int NOT NULL DEFAULT 0,
  CONSTRAINT photos_ai_status_chk CHECK (ai_status IN ('pending', 'done', 'failed', 'rejected'))
);
CREATE INDEX photos_geom_idx ON photos USING gist (geom);
CREATE INDEX photos_user_uploaded_idx ON photos (user_id, uploaded_at DESC);    -- added: rate limit
CREATE INDEX photos_uploaded_idx ON photos (uploaded_at DESC);                  -- added: sort=recent
CREATE INDEX photos_votes_idx ON photos (vote_count DESC, uploaded_at DESC);    -- added: sort=top
CREATE INDEX photos_pending_idx ON photos (uploaded_at) WHERE ai_status = 'pending';  -- added: requeue

CREATE TABLE votes (
  user_id    uuid REFERENCES users(id),
  photo_id   uuid REFERENCES photos(id) ON DELETE CASCADE,
  value      smallint NOT NULL CHECK (value IN (-1, 1)),
  created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (user_id, photo_id)
);

-- Sky events (planets, ISS passes, meteor showers, moonrise/set)
CREATE TABLE sky_events (
  time     timestamptz NOT NULL,
  type     text NOT NULL,           -- 'iss_pass' | 'planet' | 'meteor_shower' | 'moonrise' ...
  name     text NOT NULL,
  details  jsonb
);
SELECT create_hypertable('sky_events', by_range('time', INTERVAL '7 days'));
CREATE UNIQUE INDEX sky_events_uniq_idx ON sky_events (type, name, time);  -- added: idempotent ingest

-- added: job run log (powers /health "last ingest" without scanning hypertables)
CREATE TABLE ingest_runs (
  id          bigserial PRIMARY KEY,
  job         text NOT NULL,               -- 'weather' | 'astro' | 'score'
  started_at  timestamptz NOT NULL,
  finished_at timestamptz,
  status      text NOT NULL,               -- 'running' | 'ok' | 'error'
  rows        int,
  details     jsonb
);
CREATE INDEX ingest_runs_job_idx ON ingest_runs (job, started_at DESC);
