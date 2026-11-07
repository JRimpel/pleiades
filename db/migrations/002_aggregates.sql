-- Continuous aggregates over score_snapshots (Architecture §8, "Tiger Data features used").
-- NOTE: CREATE MATERIALIZED VIEW ... WITH (timescaledb.continuous) cannot run inside a
-- transaction; app.migrate runs each statement in autocommit mode.

-- Freshest score per cell-hour. Backs the map, the time slider, /best and /spots.
CREATE MATERIALIZED VIEW cell_hourly_score
WITH (timescaledb.continuous, timescaledb.materialized_only = false) AS
SELECT
  cell_id,
  time_bucket(INTERVAL '1 hour', valid_time) AS bucket,
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
