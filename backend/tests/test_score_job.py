from datetime import datetime, timedelta, timezone

import numpy as np

from app.ingest import score as score_job
from app.schemas.common import FACTOR_KEYS
from app.scoring import model

T0 = datetime(2026, 11, 8, 4, 0, tzinfo=timezone.utc)


def make_row(cell_id, hour, **overrides):
    row = {
        "cell_id": cell_id, "valid_time": T0 + timedelta(hours=hour),
        "m_sky": 21.5, "bortle": 4, "elevation_m": 450.0,
        "cloud_low": 10.0, "cloud_mid": 0.0, "cloud_high": 20.0, "cloud_total": 25.0,
        "visibility_m": 24000.0, "rh": 70.0, "dew_point_c": -2.0, "temp_c": 3.0,
        "wind_kmh": 8.0, "precip_prob": 0.0,
        "sun_alt": -40.0, "moon_alt": -10.0, "moon_illum": 0.3, "moon_phase_deg": 70.0,
    }
    row.update(overrides)
    return row


def rows():
    return [
        make_row(1, 0),
        make_row(1, 1, cloud_low=None, visibility_m=None),
        make_row(2, 0, m_sky=None, bortle=None, elevation_m=None),
        make_row(2, 1, sun_alt=5.0, moon_alt=30.0, moon_illum=0.9),
    ]


def test_build_feature_batch_types_and_nan():
    batch = score_job.build_feature_batch(rows())
    assert len(batch) == 4
    assert batch.cell_id.dtype == np.int64
    assert batch.valid_time.dtype == np.dtype("datetime64[s]")
    assert batch.valid_time[0] == np.datetime64("2026-11-08T04:00:00")
    assert np.isnan(batch.cloud_low[1]) and np.isnan(batch.visibility_m[1])
    assert np.isnan(batch.m_sky[2]) and np.isnan(batch.bortle[2]) and np.isnan(batch.elevation_m[2])
    for f in score_job.FLOAT_FIELDS:
        arr = getattr(batch, f)
        assert arr.dtype == np.float64 and arr.shape == (4,)


def test_naive_datetime_treated_as_utc():
    r = make_row(1, 0, valid_time=datetime(2026, 11, 8, 4, 0))
    assert score_job.build_feature_batch([r]).valid_time[0] == np.datetime64("2026-11-08T04:00:00")


def test_stub_model_end_to_end():
    batch = score_job.build_feature_batch(rows())
    result = model.score_batch(batch)
    score_job.validate_result(batch, result)
    assert np.all((result.score >= 0) & (result.score <= 100))
    assert result.score[3] == 0.0  # daytime
    assert result.score[0] > 50
    for f in result.factors:
        assert set(FACTOR_KEYS) <= set(f)

    out = score_job.snapshot_rows(batch, result, T0, model.MODEL_VERSION)
    assert len(out) == 4
    vt, cell_id, computed_at, score, nelm, factors, mv = out[0]
    assert vt == T0 and vt.tzinfo is not None
    assert cell_id == 1 and computed_at == T0 and mv == model.MODEL_VERSION
    assert isinstance(score, float) and isinstance(factors, str)
    assert len(score_job.SNAPSHOT_COLUMNS) == len(out[0])


def test_snapshot_rows_drop_non_finite_scores():
    batch = score_job.build_feature_batch(rows()[:2])
    result = model.score_batch(batch)
    result.score[1] = np.nan
    result.nelm[0] = np.nan
    out = score_job.snapshot_rows(batch, result, T0, 1)
    assert len(out) == 1 and out[0][4] is None


def test_validate_result_rejects_length_mismatch():
    batch = score_job.build_feature_batch(rows())
    result = model.score_batch(batch)
    result.factors = result.factors[:-1]
    try:
        score_job.validate_result(batch, result)
    except ValueError:
        pass
    else:
        raise AssertionError("expected ValueError")


def test_windows():
    now = datetime(2026, 11, 7, 21, 37, tzinfo=timezone.utc)
    start, end = score_job.score_window(now, 72)
    assert start == datetime(2026, 11, 7, 18, 0, tzinfo=timezone.utc)
    assert end == datetime(2026, 11, 10, 21, 0, tzinfo=timezone.utc)
    w = score_job.refresh_windows(start, end)
    assert w["cell_hourly_score"] == (start, end + timedelta(hours=1))
    ns, ne = w["cell_nightly_best"]
    assert ns == datetime(2026, 11, 6, tzinfo=timezone.utc)
    assert ne == datetime(2026, 11, 12, tzinfo=timezone.utc)
