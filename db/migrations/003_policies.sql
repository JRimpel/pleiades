-- Refresh, compression and retention policies (Architecture §8).

-- Scores are forecasts, so materialize into the future (end_offset NULL = no upper bound).
-- The score job also calls refresh_continuous_aggregate() right after each run.
SELECT add_continuous_aggregate_policy('cell_hourly_score',
  start_offset => INTERVAL '3 days', end_offset => NULL, schedule_interval => INTERVAL '30 minutes');
SELECT add_continuous_aggregate_policy('cell_nightly_best',
  start_offset => INTERVAL '7 days', end_offset => NULL, schedule_interval => INTERVAL '1 hour');

-- Compression (columnstore) for chunks older than 7 days.
ALTER TABLE weather_forecast SET (
  timescaledb.compress,
  timescaledb.compress_segmentby = 'cell_id',
  timescaledb.compress_orderby = 'valid_time DESC, fetched_at DESC'
);
SELECT add_compression_policy('weather_forecast', INTERVAL '7 days');

ALTER TABLE score_snapshots SET (
  timescaledb.compress,
  timescaledb.compress_segmentby = 'cell_id',
  timescaledb.compress_orderby = 'valid_time DESC, computed_at DESC'
);
SELECT add_compression_policy('score_snapshots', INTERVAL '7 days');

-- Drop raw forecast revisions after 30 days; scores and aggregates are kept.
SELECT add_retention_policy('weather_forecast', INTERVAL '30 days');
