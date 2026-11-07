from __future__ import annotations

from datetime import date, datetime, timezone

import numpy as np
import pytest

from app import geo, timeutil
from app.ai import explain, vision
from app.ai.types import ExplainContext, VisionContext
from app.astro import ephemeris
from app.auth import generate_token, hash_token
from app.errors import ApiError
from app.schemas.common import score_label, top_factor
from app.scoring import model
from app.scoring.types import FeatureBatch

UTC = timezone.utc


# ---- schemas helpers -------------------------------------------------------------------

@pytest.mark.parametrize("score,label", [(None, None), (0, "Poor"), (24.9, "Poor"), (25, "Fair"),
                                         (50, "Good"), (74.9, "Good"), (75, "Excellent"), (100, "Excellent")])
def test_score_label(score, label):
    assert score_label(score) == label


def test_top_factor():
    assert top_factor(None) is None
    assert top_factor({}) is None
    assert top_factor({"clouds": -38, "moon": -12, "elevation": 2}) == "clouds"
    assert top_factor({"clouds": 0, "elevation": 2}) is None


# ---- auth --------------------------------------------------------------------------------

def test_tokens():
    t1, t2 = generate_token(), generate_token()
    assert t1 != t2 and len(t1) >= 40
    assert hash_token(t1) == hash_token(t1) and len(hash_token(t1)) == 64 and hash_token(t1) != t1


# ---- geo ---------------------------------------------------------------------------------

def test_parse_bbox():
    assert geo.parse_bbox(None).as_tuple() == geo.WNY_BBOX
    assert geo.parse_bbox("-79,42,-78,43").as_tuple() == (-79, 42, -78, 43)


@pytest.mark.parametrize("value", ["1,2,3", "a,b,c,d", "-78,42,-79,43", "-79,43,-78,42", "-200,42,-78,43"])
def test_parse_bbox_errors(value):
    with pytest.raises(ApiError) as e:
        geo.parse_bbox(value)
    assert e.value.status == 400


def test_parse_latlon():
    assert geo.parse_latlon("42.9,-78.8") == (42.9, -78.8)
    assert geo.parse_latlon(None) is None
    for bad in ("42.9", "x,y", "91,0"):
        with pytest.raises(ApiError):
            geo.parse_latlon(bad)


def test_cell_polygon_closed_square():
    poly = geo.cell_polygon(42.9, -78.8, 0.1)
    ring = poly["coordinates"][0]
    assert poly["type"] == "Polygon" and ring[0] == ring[-1] and len(ring) == 5
    assert ring[0] == [-78.85, 42.85] and ring[2] == [-78.75, 42.95]


# ---- time --------------------------------------------------------------------------------

def test_parse_iso():
    assert timeutil.parse_iso("2026-11-08T03:25:00Z") == datetime(2026, 11, 8, 3, 25, tzinfo=UTC)
    assert timeutil.parse_iso("2026-11-08T03:25:00") == datetime(2026, 11, 8, 3, 25, tzinfo=UTC)
    assert timeutil.parse_iso("2026-11-07T22:25:00-05:00") == datetime(2026, 11, 8, 3, 25, tzinfo=UTC)
    assert timeutil.parse_iso(None) is None
    with pytest.raises(ApiError):
        timeutil.parse_iso("yesterday")


def test_night_window_standard_and_dst():
    # EST (UTC-5)
    assert timeutil.night_window(date(2026, 11, 7), "America/New_York") == (
        datetime(2026, 11, 7, 23, tzinfo=UTC), datetime(2026, 11, 8, 11, tzinfo=UTC))
    # DST ends 2026-11-01 02:00: starts in EDT (UTC-4), ends in EST (UTC-5)
    assert timeutil.night_window(date(2026, 10, 31), "America/New_York") == (
        datetime(2026, 10, 31, 22, tzinfo=UTC), datetime(2026, 11, 1, 11, tzinfo=UTC))
    # DST starts 2026-03-08: starts in EST, ends in EDT
    assert timeutil.night_window(date(2026, 3, 7), "America/New_York") == (
        datetime(2026, 3, 7, 23, tzinfo=UTC), datetime(2026, 3, 8, 10, tzinfo=UTC))


def test_current_night():
    tz = "America/New_York"
    assert timeutil.current_night(datetime(2026, 11, 8, 3, tzinfo=UTC), tz) == date(2026, 11, 7)  # 22:00 local
    assert timeutil.current_night(datetime(2026, 11, 8, 10, tzinfo=UTC), tz) == date(2026, 11, 7)  # 05:00 local
    assert timeutil.current_night(datetime(2026, 11, 8, 18, tzinfo=UTC), tz) == date(2026, 11, 8)  # 13:00 local


# ---- seam stub shapes (contract for the AI/ML teammate) -------------------------------------

def _batch(n=4) -> FeatureBatch:
    f = lambda v: np.full(n, v, dtype=float)  # noqa: E731
    return FeatureBatch(
        cell_id=np.arange(n), valid_time=np.array(["2026-11-08T04:00"] * n, dtype="datetime64[s]"),
        m_sky=np.array([21.8, 19.5, 21.0, np.nan]), bortle=f(4), elevation_m=f(500),
        cloud_low=np.array([0, 50, 10, np.nan]), cloud_mid=f(0), cloud_high=f(20), cloud_total=f(30),
        visibility_m=f(24000), rh=f(70), dew_point_c=f(0), temp_c=f(5), wind_kmh=f(10), precip_prob=f(0),
        sun_alt=np.array([-40, -40, -40, 10.0]), moon_alt=np.array([-10, -10, 40, 0.0]), moon_illum=f(0.8),
        moon_phase_deg=f(120),
    )


def test_score_batch_shapes():
    b = _batch()
    out = model.score_batch(b)
    assert len(out) == len(b) == len(out.factors) == out.nelm.shape[0]
    assert np.all((out.score >= 0) & (out.score <= 100)) and not np.any(np.isnan(out.score))
    assert all(isinstance(v, float) for row in out.factors for v in row.values())
    assert out.score[3] == 0  # daytime
    assert top_factor(out.factors[3]) == "twilight"
    assert isinstance(model.MODEL_VERSION, int)


def test_ephemeris_stub_shapes():
    start = datetime(2026, 11, 8, 0, tzinfo=UTC)
    hours = ephemeris.hourly_conditions(start, 72, 42.7, -78.4)
    assert len(hours) == 72 and hours[0].time == start
    assert all(-90 <= h.sun_alt <= 90 and 0 <= h.moon_illum <= 1 for h in hours)
    summary = ephemeris.night_summary(42.7, -78.4, date(2026, 11, 7), "America/New_York")
    assert summary.twilight.sunset < summary.twilight.astronomical_dusk < summary.twilight.astronomical_dawn
    events = ephemeris.sky_events(datetime(2026, 11, 1, tzinfo=UTC), datetime(2026, 11, 30, tzinfo=UTC), 42.7, -78.4)
    assert "Leonids" in {e.name for e in events}
    assert isinstance(ephemeris.visible_objects(42.7, -78.4, start), list)


def test_ai_stub_shapes():
    ctx = VisionContext(lat=42.7, lon=-78.4, taken_at=datetime(2026, 11, 8, 3, tzinfo=UTC), candidates=[])
    r = vision.analyze_photo(b"\xff\xd8", "image/jpeg", ctx)
    assert r.is_night_sky in (True, False) and 1 <= r.sky_quality <= 10
    e = explain.explain_score(ExplainContext(
        cell_id=1, spot_name=None, valid_time=ctx.taken_at, local_time="Sat Nov 7, 10:00 PM", score=40.0,
        nelm=5.5, factors={"moon": -30.0, "clouds": -10.0}, bortle=4))
    assert "40" in e.summary and any("moon" in t.lower() for t in e.tips)
