"""Offline Role C checks; run with backend/tests using the backend environment."""
import io
import sys
from dataclasses import fields
from datetime import date, datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'backend'))
sys.path.insert(0, str(ROOT / 'data'))

from app.ai import explain, vision
from app.ai.types import ExplainContext, Explanation, VisionContext, VisionResult
from app.astro import ephemeris
from app.astro.types import CandidateObject
from app.scoring.model import score_batch
from app.scoring.types import FeatureBatch
from atlas import artificial_to_mpsas
from train_calibration import fit_monotone

UTC = timezone.utc
WHEN = datetime(2026, 11, 8, 4, tzinfo=UTC)


def batch(n=1, **changes):
    defaults = dict(m_sky=21.5, bortle=3, elevation_m=0, cloud_low=0, cloud_mid=0, cloud_high=0,
                    cloud_total=0, visibility_m=24000, rh=60, dew_point_c=0, temp_c=8, wind_kmh=5,
                    precip_prob=0, sun_alt=-40, moon_alt=-10, moon_illum=0, moon_phase_deg=0)
    defaults.update(changes)
    values = {name: np.full(n, value, dtype=float) for name, value in defaults.items()}
    return FeatureBatch(cell_id=np.arange(n), valid_time=np.full(n, np.datetime64('2026-11-08T04:00:00')), **values)


def test_scoring_physical_direction_and_conservation():
    clear = score_batch(batch()).score[0]
    assert score_batch(batch(m_sky=18)).score[0] < clear
    assert score_batch(batch(cloud_low=100, cloud_total=100)).score[0] < clear / 5
    assert score_batch(batch(moon_alt=60, moon_illum=1)).score[0] < clear
    assert score_batch(batch(sun_alt=0)).score[0] == 0
    for overrides in ({}, {'cloud_low': 100}, {'sun_alt': -15}, {'moon_alt': 30, 'moon_illum': .8}):
        result = score_batch(batch(**overrides))
        assert abs(100 + sum(result.factors[0].values()) - result.score[0]) < 1e-8
        assert all(np.isfinite(list(result.factors[0].values())))


def test_missing_clouds_not_clear_and_shape_validation():
    clear = score_batch(batch()).score[0]
    assert score_batch(batch(cloud_low=np.nan, cloud_total=np.nan)).score[0] < clear
    assert np.isnan(score_batch(batch(sun_alt=np.nan)).score[0])
    broken = batch(2)
    broken.cloud_low = np.array([1])
    with pytest.raises(ValueError):
        score_batch(broken)
    assert len(score_batch(batch(0))) == 0


def test_scoring_out_of_range_and_monotonic_clouds():
    b = batch(101)
    b.cloud_low = np.arange(101, dtype=float)
    result = score_batch(b)
    assert (np.diff(result.score) <= 0).all()
    result = score_batch(batch(cloud_low=-100, cloud_mid=1000, moon_illum=4, elevation_m=np.inf))
    assert np.isfinite(result.score).all() and 0 <= result.score[0] <= 100


def test_trained_artifact_inference_and_reconciliation(monkeypatch):
    import json
    from app.scoring import model

    artifact = json.loads((ROOT / 'data/models/calibration.json').read_text())
    assert artifact['enabled'] and artifact['counts']['test'] >= 30
    assert artifact['test_learned']['mae_mag'] < artifact['test_physics']['mae_mag']
    monkeypatch.setattr(model, '_CALIBRATION', artifact)
    result = model.score_batch(batch())
    expected = artifact['intercept'] + artifact['slope'] * model._nelm(np.array([21.5]))[0]
    assert result.nelm[0] == pytest.approx(expected, abs=.01)
    assert result.score[0] == pytest.approx(100 * (expected - 1) / 6, abs=.1)
    assert abs(100 + sum(result.factors[0].values()) - result.score[0]) < 1e-8
    moon = model.score_batch(batch(moon_alt=60, moon_illum=1))
    assert moon.score[0] < result.score[0]


def test_atlas_units_and_monotone_training():
    dark, urban, invalid = artificial_to_mpsas([0, 10, -1])
    assert dark == pytest.approx(22.001, abs=.01)
    assert 17 < urban < 18 and np.isnan(invalid)
    x = np.arange(100) / 20
    intercept, slope = fit_monotone(x, 1 + .8 * x)
    assert intercept == pytest.approx(1, abs=.02) and slope == pytest.approx(.8, abs=.01)
    assert fit_monotone(x, -x)[1] > 0


def test_astronomy_eclipse_and_solar_reference():
    # The 2024 April 8 eclipse supplies an independent new-Moon sanity check.
    hour = ephemeris.hourly_conditions(datetime(2024, 4, 8, 18, tzinfo=UTC), 1, 42.7, -78.4)[0]
    assert hour.moon_illum < .001
    assert abs(hour.sun_alt - hour.moon_alt) < 2
    equinox = ephemeris.hourly_conditions(datetime(2026, 3, 20, 12, tzinfo=UTC), 1, 0, 0)[0]
    assert equinox.sun_alt > 85
    with pytest.raises(ValueError):
        ephemeris.hourly_conditions(datetime(2026, 11, 8), 1, 42, -78)


def test_night_summary_dst_cache_and_candidates():
    summary = ephemeris.night_summary(42.7, -78.4, date(2026, 10, 31), 'America/New_York')
    twilight = summary.twilight
    assert twilight.sunset < twilight.astronomical_dusk < twilight.astronomical_dawn < twilight.sunrise
    assert twilight.sunrise.astimezone(__import__('zoneinfo').ZoneInfo('America/New_York')).date() == date(2026, 11, 1)
    summary.moon.phase_name = 'mutated'
    assert ephemeris.night_summary(42.7, -78.4, date(2026, 10, 31), 'America/New_York').moon.phase_name != 'mutated'
    candidates = ephemeris.visible_objects(42.7, -78.4, WHEN)
    assert all(0 < item.alt_deg <= 90 and 0 <= item.az_deg < 360 for item in candidates)
    polaris = next(item for item in candidates if item.name == 'Polaris')
    assert 41 < polaris.alt_deg < 44


def image_bytes():
    image = io.BytesIO()
    Image.new('RGB', (32, 32), (1, 2, 10)).save(image, format='PNG')
    return image.getvalue()


def test_vision_candidate_filter_and_non_sky(monkeypatch):
    ctx = VisionContext(lat=42.7, lon=-78.4, taken_at=WHEN, candidates=[
        CandidateObject(name='Jupiter', type='planet', alt_deg=30, az_deg=90),
        CandidateObject(name='Moon', type='moon', alt_deg=-10, az_deg=90)])
    raw = VisionResult(is_night_sky=True, description='Ambiguous sky', milky_way_visible=False, sky_quality=5,
                       objects=[{'name': 'Jupiter', 'type': 'star', 'confidence': .9},
                                {'name': 'Moon', 'type': 'moon', 'confidence': .99},
                                {'name': 'Sirius', 'type': 'star', 'confidence': .99},
                                {'name': 'Jupiter', 'type': 'planet', 'confidence': .99}])
    monkeypatch.setattr(vision, '_generate_json', lambda *args, **kwargs: raw)
    result = vision.analyze_photo(image_bytes(), 'image/png', ctx)
    assert [(o.name, o.type) for o in result.objects] == [('Jupiter', 'planet')]
    raw.is_night_sky = False
    assert vision.analyze_photo(image_bytes(), 'image/png', ctx).objects == []
    with pytest.raises((ValueError, OSError)):
        vision.analyze_photo(b'bad image', 'image/png', ctx)
    with pytest.raises(ValueError):
        vision.analyze_photo(image_bytes(), 'image/jpeg', ctx)


def test_gemini_single_attempt_timeout_and_validation(monkeypatch):
    settings = SimpleNamespace(gemini_api_key='test-only', gemini_model='test-model', explain_timeout_s=8)
    monkeypatch.setattr(explain, 'current_settings', lambda: settings)
    calls = {}

    class Client:
        def __init__(self, **kwargs):
            calls['options'] = kwargs['http_options']
            self.models = self

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def generate_content(self, **kwargs):
            calls['request'] = kwargs
            return SimpleNamespace(text='{"summary":"A test summary","tips":[]}')

    monkeypatch.setattr(explain.genai, 'Client', Client)
    result = explain._generate_json('test prompt', Explanation)
    assert result.summary == 'A test summary'
    assert calls['options'].timeout == 10_000 and calls['options'].retry_options.attempts == 1
    assert calls['request']['config'].response_mime_type == 'application/json'
    ctx = ExplainContext(cell_id=1, spot_name=None, valid_time=WHEN, local_time='Test night',
                         score=12, nelm=4, factors={}, bortle=None)
    explain.explain_score(ctx)
    assert calls['options'].timeout == 10_000  # Provider minimum even with an 8s caller budget.
    settings.explain_timeout_s = 12
    explain.explain_score(ctx)
    assert calls['options'].timeout == 11_750


def test_explanation_fallback_and_configured_failure(monkeypatch):
    ctx = ExplainContext(cell_id=1, spot_name=None, valid_time=WHEN, local_time='Test night',
                         score=12, nelm=4, factors={}, bortle=None)
    assert 'Poor' in explain.fallback_explanation(ctx).summary
    monkeypatch.setattr(explain, 'current_settings', lambda: SimpleNamespace(gemini_api_key='test', gemini_model='test', explain_timeout_s=8))

    def fail(*args, **kwargs):
        raise TimeoutError('simulated timeout')

    monkeypatch.setattr(explain, '_generate_json', fail)
    with pytest.raises(TimeoutError):
        explain.explain_score(ctx)


def test_vision_evaluation_label_isolation(tmp_path, monkeypatch):
    import json
    import evaluate_vision

    photo = tmp_path / 'photo.png'
    photo.write_bytes(image_bytes())
    manifest = tmp_path / 'manifest.json'
    entry = {'id': 'one', 'path': 'photo.png', 'source': 'local test fixture', 'lat': 42.7, 'lon': -78.4,
             'taken_at': WHEN.isoformat(), 'reviewed': True, 'metadata_verified': True,
             'is_night_sky': True, 'objects': ['Jupiter']}
    manifest.write_text(json.dumps([entry]))
    seen = []
    result = VisionResult(is_night_sky=True, description='Test sky', objects=[],
                          milky_way_visible=False, sky_quality=5)

    def grounded(data, mime, ctx):
        assert not hasattr(ctx, 'objects')
        seen.append('grounded')
        return result

    def ungrounded(prompt, *args, **kwargs):
        assert 'Jupiter' not in prompt
        seen.append('ungrounded')
        return result

    monkeypatch.setattr(evaluate_vision, 'analyze_photo', grounded)
    monkeypatch.setattr(evaluate_vision, '_generate_json', ungrounded)
    output = tmp_path / 'report.json'
    evaluate_vision.run(manifest, output)
    report = json.loads(output.read_text())
    assert seen == ['grounded', 'ungrounded']
    assert report['summary']['grounded']['fn'] == 1
    assert report['summary']['grounded']['precision'] is None
    entry['metadata_verified'] = False
    manifest.write_text(json.dumps([entry]))
    with pytest.raises(ValueError):
        evaluate_vision.run(manifest, output)


def test_safe_key_configuration_preserves_other_settings():
    from configure_gemini import replace_key

    text = 'GEMINI_MODEL=chosen-model\nGEMINI_API_KEY=old\nOTHER_SETTING=keep\nexport GEMINI_API_KEY=duplicate\n'
    result = replace_key(text, 'test-only-placeholder')
    assert result.count('GEMINI_API_KEY=') == 1
    assert 'GEMINI_MODEL=chosen-model\n' in result and 'OTHER_SETTING=keep\n' in result
