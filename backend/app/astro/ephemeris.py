"""OWNER: AI/ML. Offline Skyfield ephemeris with bounded night-summary cache.

DE421 is installed by skyfield-data. No function downloads kernels or catalogs.
Rise/set and twilight use interpolated five-minute samples (approximate times).
"""
from __future__ import annotations

import os
from datetime import date, datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
from skyfield import almanac
from skyfield.api import Star, load, load_file, wgs84
from skyfield_data import __file__ as _data_init

from .types import AstroHour, CandidateObject, MoonInfo, NightSummary, PlanetVisibility, SkyEventRecord, Twilight

_UTC = timezone.utc
_PLANETS = {'Mercury': 'mercury', 'Venus': 'venus', 'Mars': 'mars',
            'Jupiter': 'jupiter barycenter', 'Saturn': 'saturn barycenter',
            'Uranus': 'uranus barycenter', 'Neptune': 'neptune barycenter'}
# Rounded J2000 positions (hours/degrees), for candidate generation, not astrometry.
_STARS = [
    ('Sirius', 6.7525, -16.7161, -1.46), ('Canopus', 6.3992, -52.6957, -.74),
    ('Arcturus', 14.2610, 19.1824, -.05), ('Vega', 18.6156, 38.7837, .03),
    ('Capella', 5.2782, 45.9980, .08), ('Rigel', 5.2423, -8.2016, .13),
    ('Procyon', 7.6550, 5.2250, .34), ('Betelgeuse', 5.9195, 7.4071, .5),
    ('Altair', 19.8464, 8.8683, .76), ('Aldebaran', 4.5987, 16.5093, .85),
    ('Spica', 13.4199, -11.1613, .97), ('Antares', 16.4901, -26.4320, 1.06),
    ('Pollux', 7.7553, 28.0262, 1.14), ('Fomalhaut', 22.9608, -29.6222, 1.16),
    ('Deneb', 20.6905, 45.2803, 1.25), ('Regulus', 10.1395, 11.9672, 1.35),
    ('Castor', 7.5767, 31.8883, 1.58), ('Bellatrix', 5.4189, 6.3497, 1.64),
    ('Alnilam', 5.6036, -1.2019, 1.69), ('Alnitak', 5.6793, -1.9426, 1.74),
    ('Alioth', 12.9005, 55.9598, 1.76), ('Dubhe', 11.0621, 61.7510, 1.79),
    ('Mirfak', 3.4054, 49.8612, 1.79), ('Alkaid', 13.7923, 49.3133, 1.86),
    ('Polaris', 2.5303, 89.2641, 1.98), ('Hamal', 2.1196, 23.4624, 2.0),
    ('Denebola', 11.8177, 14.5721, 2.14), ('Mizar', 13.3987, 54.9254, 2.23),
    ('Merak', 11.0307, 56.3824, 2.37), ('Phecda', 11.8972, 53.6948, 2.44),
]
_CLUSTERS = [('Pleiades', 3.79, 24.12, 1.6), ('Andromeda Galaxy', .712, 41.269, 3.44),
             ('Orion Nebula', 5.588, -5.391, 4.0)]
# Constellations are extended; these anchors only indicate a potentially visible region.
_CONSTELLATIONS = [('Orion', 5.6, 2), ('Cassiopeia', 1, 60), ('Ursa Major', 11.5, 55),
                   ('Cygnus', 20.5, 42), ('Lyra', 18.6, 36), ('Taurus', 4.6, 18),
                   ('Gemini', 7.1, 24), ('Leo', 10.7, 15)]


def _utc(when):
    if when.tzinfo is None or when.utcoffset() is None:
        raise ValueError('Astronomy requires timezone-aware timestamps')
    return when.astimezone(_UTC)


def _location(lat, lon):
    if not np.isfinite([lat, lon]).all() or not -90 <= lat <= 90 or not -180 <= lon <= 180:
        raise ValueError('Invalid latitude/longitude')
    return wgs84.latlon(lat, lon)


@lru_cache(maxsize=1)
def _resources():
    path = Path(os.environ.get('PLEIADES_EPHEMERIS_PATH') or Path(_data_init).parent / 'data' / 'de421.bsp')
    if not path.is_file():
        raise RuntimeError('Ephemeris missing: install skyfield-data or set PLEIADES_EPHEMERIS_PATH')
    return load.timescale(builtin=True), load_file(str(path))


def _phase_name(phase_deg):
    names = ['New Moon', 'Waxing Crescent', 'First Quarter', 'Waxing Gibbous',
             'Full Moon', 'Waning Gibbous', 'Last Quarter', 'Waning Crescent']
    return names[int(((phase_deg + 22.5) % 360) // 45)]


def hourly_conditions(start: datetime, hours: int, lat: float, lon: float) -> list[AstroHour]:
    start = _utc(start)
    site = _location(lat, lon)
    if not isinstance(hours, int) or not 0 <= hours <= 24 * 366:
        raise ValueError('hours must be an integer from 0 to 8784')
    if not hours:
        return []
    ts, eph = _resources()
    times = [start + timedelta(hours=i) for i in range(hours)]
    t = ts.from_datetimes(times)
    obs = (eph['earth'] + site).at(t)
    sun = obs.observe(eph['sun']).apparent().altaz()[0].degrees
    moon = obs.observe(eph['moon']).apparent().altaz()[0].degrees
    phase = almanac.moon_phase(eph, t).degrees % 360
    illumination = almanac.fraction_illuminated(eph, 'moon', t)
    return [AstroHour(time=dt, sun_alt=round(float(s), 3), moon_alt=round(float(m), 3),
                      moon_illum=round(float(i), 5), moon_phase_deg=round(float(p), 3))
            for dt, s, m, i, p in zip(times, sun, moon, illumination, phase)]


def _crossings(times, values, threshold):
    shifted = np.asarray(values) - threshold
    result = []
    for i in np.flatnonzero((shifted[:-1] > 0) != (shifted[1:] > 0)):
        fraction = -shifted[i] / (shifted[i + 1] - shifted[i])
        result.append((times[i] + (times[i + 1] - times[i]) * float(fraction), bool(shifted[i + 1] > 0)))
    return result


def sky_events(start: datetime, end: datetime, lat: float, lon: float) -> list[SkyEventRecord]:
    start, end = _utc(start), _utc(end)
    site = _location(lat, lon)
    if end <= start or end - start > timedelta(days=32):
        raise ValueError('Event window must be positive and no longer than 32 days')
    ts, eph = _resources()
    # Skyfield finds physical Moon rise/set events.
    times, rising = almanac.find_discrete(ts.from_datetime(start), ts.from_datetime(end),
                                         almanac.risings_and_settings(eph, eph['moon'], site, radius_degrees=.25))
    events = [SkyEventRecord(time=t.utc_datetime(), type='moonrise' if up else 'moonset',
                           name='Moonrise' if up else 'Moonset',
                           details={'lat': lat, 'lon': lon, 'source': 'Skyfield DE421'})
            for t, up in zip(times, rising)]
    # Verified 2026 prediction; never repeat a year's peak as an exact future date.
    peak = datetime(2026, 11, 17, 23, 45, tzinfo=_UTC)
    if start <= peak < end:
        events.append(SkyEventRecord(time=peak, type='meteor_shower', name='Leonids',
                                    details={'predicted_peak': True, 'source': 'https://www.imo.net/files/meteor-shower/cal2026.pdf',
                                             'note': 'Predicted annual maximum; local observed rates vary.'}))
    return sorted(events, key=lambda event: event.time)


@lru_cache(maxsize=256)
def _night_cached(lat, lon, night, tz, kernel_path):
    zone = ZoneInfo(tz)
    local_noon = datetime(night.year, night.month, night.day, 12, tzinfo=zone)
    start = local_noon.astimezone(_UTC)
    end = (local_noon + timedelta(days=1)).astimezone(_UTC)
    times = [start + timedelta(minutes=5 * i) for i in range(int((end - start).total_seconds() / 300) + 1)]
    ts, eph = _resources()
    t = ts.from_datetimes(times)
    observer = eph['earth'] + _location(lat, lon)
    obs = observer.at(t)
    solar_alt = obs.observe(eph['sun']).apparent().altaz()[0].degrees

    def first(values, threshold, up):
        return next((when for when, rising in _crossings(times, values, threshold) if rising == up), None)

    twilight = Twilight(sunset=first(solar_alt, -.8333, False), sunrise=first(solar_alt, -.8333, True),
                        civil_dusk=first(solar_alt, -6, False), nautical_dusk=first(solar_alt, -12, False),
                        astronomical_dusk=first(solar_alt, -18, False), astronomical_dawn=first(solar_alt, -18, True))
    midnight = datetime.combine(night + timedelta(days=1), datetime.min.time(), tzinfo=zone).astimezone(_UTC)
    mt = ts.from_datetime(midnight)
    phase = float(almanac.moon_phase(eph, mt).degrees % 360)
    lunar = obs.observe(eph['moon']).apparent()
    moon_alt, _, moon_distance = lunar.altaz()
    # Refraction plus Moon semidiameter; no terrain horizon is modeled.
    lunar_threshold = -.5667 - np.degrees(np.arcsin(1737.4 / moon_distance.km))
    moon = MoonInfo(phase_deg=round(phase, 3), illumination=round(float(almanac.fraction_illuminated(eph, 'moon', mt)), 5),
                    phase_name=_phase_name(phase), rise=first(moon_alt.degrees, lunar_threshold, True),
                    set=first(moon_alt.degrees, lunar_threshold, False))
    planets = []
    dark = solar_alt < -6
    for name, key in _PLANETS.items():
        apparent = obs.observe(eph[key]).apparent()
        alt = apparent.altaz()[0].degrees
        visible = dark & (alt > 0)
        if not visible.any():
            continue
        planets.append(PlanetVisibility(name=name, rise=first(alt, -.5667, True), set=first(alt, -.5667, False),
                                         max_alt_deg=round(float(alt[visible].max()), 1)))
    return NightSummary(moon=moon, twilight=twilight, planets=planets)


def night_summary(lat: float, lon: float, night: date, tz: str) -> NightSummary:
    _location(lat, lon)
    return _night_cached(lat, lon, night, tz, os.environ.get('PLEIADES_EPHEMERIS_PATH', '')).model_copy(deep=True)


def visible_objects(lat: float, lon: float, when: datetime) -> list[CandidateObject]:
    ts, eph = _resources()
    t = ts.from_datetime(_utc(when))
    observer = (eph['earth'] + _location(lat, lon)).at(t)
    candidates = []

    def add(name, kind, target, magnitude=None):
        alt, az, _ = observer.observe(target).apparent().altaz()
        if alt.degrees > 0:
            candidates.append(CandidateObject(name=name, type=kind, alt_deg=round(float(alt.degrees), 2),
                                              az_deg=round(float(az.degrees), 2), magnitude=magnitude))

    add('Moon', 'moon', eph['moon'])
    for name, key in _PLANETS.items():
        add(name, 'planet', eph[key])
    for name, ra, dec, mag in _STARS:
        add(name, 'star', Star(ra_hours=ra, dec_degrees=dec), mag)
    for name, ra, dec, mag in _CLUSTERS:
        kind = 'cluster' if name == 'Pleiades' else 'galaxy' if name == 'Andromeda Galaxy' else 'nebula'
        add(name, kind, Star(ra_hours=ra, dec_degrees=dec), mag)
    for name, ra, dec in _CONSTELLATIONS:
        add(name, 'constellation', Star(ra_hours=ra, dec_degrees=dec))
    return candidates
