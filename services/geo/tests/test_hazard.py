from datetime import UTC, datetime, timedelta, timezone

import numpy as np
import pytest

from shadowcast_geo.hazard import (
    Track,
    decay_inland,
    exposure,
    geodesics,
    holland_wind,
    radii_to_km,
    terrain_factor,
    track_position,
    willoughby_rmw_km,
    wind_at,
    wind_timeline,
)
from tests.conftest import START, make_fixes


def test_track_from_records(track: Track) -> None:
    assert track.times.dtype == np.dtype("datetime64[s]")
    assert track.times[0] == np.datetime64("2019-05-02T12:00:00")
    assert track.radii_km[64].shape == (4, 7)
    assert np.isnan(track.radii_km[64][1]).all()
    assert track.radii_km[34][0, 0] == 200.0


@pytest.mark.parametrize(
    ("asset", "expected_km", "expected_bearing"),
    [((19.0, 86.0), 111.2, 0.0), ((18.0, 87.0), 105.8, 90.0), ((17.0, 86.0), 111.2, 180.0)],
)
def test_geodesics(asset: tuple[float, float], expected_km: float, expected_bearing: float) -> None:
    distance, bearing = geodesics(np.array([asset[0]]), np.array([asset[1]]), np.array([18.0]), np.array([86.0]))

    assert distance.shape == (1, 1)
    assert distance[0, 0] == pytest.approx(expected_km, abs=0.5)
    assert bearing[0, 0] == pytest.approx(expected_bearing, abs=0.5)


def test_holland_wind_profile() -> None:
    distance = np.array([[30.0], [60.0], [300.0], [0.0]])

    wind = holland_wind(distance, np.array([100.0]), np.array([30.0]))[:, 0]

    assert wind[0] == pytest.approx(100.0)  # maximum at the radius of maximum wind
    assert wind[0] > wind[1] > wind[2] > 0
    assert wind[3] < wind[0]  # calm eye


def test_exposure_near_mid_far_and_missing_intensity(track: Track) -> None:
    lat, lon = np.array([19.5, 19.5, 19.5]), np.array([86.05, 86.4, 88.5])

    result = exposure(lat, lon, track)

    near, mid, far = range(3)
    assert result["band_kt"].tolist() == [64, 64, 0]
    # The eyewall passes over the near-track asset between 3-hourly fixes; densification must catch it.
    assert result["peak_wind_kt"][near] == pytest.approx(100.0, abs=0.5)
    assert result["peak_wind_kt"][near] > result["peak_wind_kt"][mid] > result["peak_wind_kt"][far]
    assert result["peak_time"][near] == np.datetime64("2019-05-02T19:30:00")
    assert result["closest_time"][near] == np.datetime64("2019-05-02T21:00:00")
    assert result["band_entry"][mid] == np.datetime64("2019-05-02T18:45:00")
    assert np.isnat(result["band_entry"][far])
    assert result["gale_arrival"][near] == result["gale_arrival"][mid] == track.times[0]  # gales from the first fix
    assert np.isnat(result["gale_arrival"][far])
    assert result["min_dist_km"][near] == pytest.approx(5.2, abs=0.2)

    calm = Track.from_records(make_fixes(vmax=float("nan")))
    assert np.isnan(exposure(lat[:1], lon[:1], calm)["peak_wind_kt"][0])


def test_densify(track: Track) -> None:
    dense = track.densify(15)

    assert dense.times.size == 73
    assert dense.times[1] == np.datetime64("2019-05-02T12:15:00")
    assert dense.lat[2] == pytest.approx(18.0 + 0.5 * 30 / 180)
    assert dense.times[-1] == track.times[-1]
    assert np.isnan(dense.radii_km[64][1]).all()
    assert dense.radii_km[34].shape == (4, 73)


def test_wind_timeline(track: Track) -> None:
    times, winds = wind_timeline(19.5, 86.4, track)

    assert times.size == winds.size == 73
    assert times[int(winds.argmax())] == np.datetime64("2019-05-02T21:00:00")


@pytest.mark.parametrize(
    ("when", "expected_lat"),
    [
        (START + timedelta(hours=1, minutes=30), 18.25),
        ((START + timedelta(hours=3)).astimezone(timezone(timedelta(hours=5, minutes=30))), 18.5),
        ((START + timedelta(hours=6)).replace(tzinfo=None), 19.0),
        (START - timedelta(hours=1), None),
        (START + timedelta(days=2), None),
    ],
)
def test_track_position(track: Track, when: datetime, expected_lat: float | None) -> None:
    position = track_position(track, when)

    if expected_lat is None:
        assert position is None
    else:
        assert position is not None
        assert position["lat"] == pytest.approx(expected_lat)
        assert position["vmax_kt"] == 100.0


def test_wind_at(track: Track) -> None:
    lat, lon = np.array([19.5, 25.0]), np.array([86.05, 86.0])

    inside = wind_at(lat, lon, track, START + timedelta(hours=7, minutes=30))  # eyewall over the first asset
    outside = wind_at(lat, lon, track, datetime(2020, 1, 1, tzinfo=UTC))

    assert inside[0] > 90  # eyewall
    assert inside[1] < 20  # ~600 km away
    assert outside.tolist() == [0.0, 0.0]


def test_willoughby_rmw_km() -> None:
    rmw = willoughby_rmw_km(np.array([40.0, 100.0, 100.0]), np.array([20.0, 20.0, -20.0]))

    assert rmw[0] == pytest.approx(46.4 * np.exp(-0.0155 * 40 / 1.943844 + 0.0169 * 20))
    assert rmw[0] > rmw[1]  # stronger storms have tighter cores
    assert rmw[1] == rmw[2]  # symmetric in latitude


def test_radii_to_km() -> None:
    assert radii_to_km([10.0, None, float("nan"), 0.0]) == [18.5, None, None, 0.0]


def test_decay_inland_caps_only_after_landfall() -> None:
    fixes = make_fixes()  # 100 kt throughout, fixes every 3 h from START
    landfall = START + timedelta(hours=6)

    decayed = decay_inland(fixes, landfall)

    assert [f["vmax_kt"] for f in decayed[:3]] == [100.0, 100.0, 100.0]  # up to and including landfall
    # 3 h after landfall: 26.7 + (0.9 * 100 - 26.7) * exp(-0.095 * 3)
    assert decayed[3]["vmax_kt"] == pytest.approx(74.3, abs=0.1)
    assert decayed[3]["vmax_kt"] > decayed[4]["vmax_kt"] > decayed[6]["vmax_kt"] > 26.7
    assert decay_inland(fixes, START - timedelta(days=1)) is fixes  # landfall outside the track


def test_decay_inland_keeps_best_track_values_that_decay_faster() -> None:
    fixes = [{**fix, "vmax_kt": 20.0} if i else fix for i, fix in enumerate(make_fixes())]

    assert [f["vmax_kt"] for f in decay_inland(fixes, START)] == [100.0] + [20.0] * 6


@pytest.mark.parametrize(("roughness", "expected"), [(0.0002, 1.0), (0.05, 0.723), (0.5, 0.481), (float("nan"), 0.765)])
def test_terrain_factor(roughness: float, expected: float) -> None:
    assert terrain_factor(np.array([roughness]))[0] == pytest.approx(expected, abs=0.002)


def test_terrain_factor_scales_every_hazard_view(track: Track) -> None:
    lat, lon = np.array([19.5, 19.5]), np.array([86.4, 86.4])
    factor = np.array([1.0, 0.5])
    when = START + timedelta(hours=9)

    peak = exposure(lat, lon, track, factor)["peak_wind_kt"]
    now = wind_at(lat, lon, track, when, factor)
    _, timeline = wind_timeline(19.5, 86.4, track, 0.5)

    assert peak[1] == pytest.approx(peak[0] / 2)
    assert now[1] == pytest.approx(now[0] / 2)
    assert np.nanmax(timeline) == pytest.approx(peak[1])
