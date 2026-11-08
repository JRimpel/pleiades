-- Continuous aggregates over score_snapshots (Architecture §8, "Tiger Data features used").
-- NOTE: CREATE MATERIALIZED VIEW ... WITH (timescaledb.continuous) cannot run inside a
-- transaction; app.migrate runs each statement in autocommit mode.

-- This file is only run while unrecorded in schema_migrations, so dropping first lets a
-- partially applied run (e.g. statement 1 succeeded, statement 2 failed) be retried.
DROP MATERIALIZED VIEW IF EXISTS cell_nightly_best;
DROP MATERIALIZED VIEW IF EXISTS cell_hourly_score;

-- Freshest score per cell-hour. Backs the map, the time slider, /best and /spots.
-- The timezone and 12 h offset have no effect on 1-hour buckets (they still start on the
-- hour), but TimescaleDB 2.2x+ requires a hierarchical aggregate to use the same timezone
-- and offset as its parent, and cell_nightly_best needs both.
CREATE MATERIALIZED VIEW cell_hourly_score
WITH (timescaledb.continuous, timescaledb.materialized_only = false) AS
SELECT
  cell_id,
  time_bucket(INTERVAL '1 hour', valid_time, 'America/New_York', "offset" => INTERVAL '12 hours') AS bucket,
  last(score, computed_at)         AS score,
  last(nelm, computed_at)          AS nelm,
  last(factors, computed_at)       AS factors,
  last(model_version, computed_at) AS model_version,
  max(computed_at)                 AS computed_at
FROM score_snapshots
GROUP BY cell_id, bucket
WITH NO DATA;

-- Hierarchical: best score per cell per night. A "night" is a local noon-to-noon day
-- in America/New_York, labeled by the date it starts on.
CREATE MATERIALIZED VIEW cell_nightly_best
WITH (timescaledb.continuous, timescaledb.materialized_only = false) AS
SELECT
  cell_id,
  time_bucket(INTERVAL '1 day', bucket, 'America/New_York', "offset" => INTERVAL '12 hours') AS night,
  max(score)          AS best_score,
  last(bucket, score) AS best_time
FROM cell_hourly_score
GROUP BY cell_id, night
WITH NO DATA;
