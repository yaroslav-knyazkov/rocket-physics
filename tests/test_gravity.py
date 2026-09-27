"""Sign-check / algebraic tests for sim/gravity.py (architecture.md SS12,
SS13; main.tex SSModels > Gravity; roadmap.md Step 10).

Physics sanity checks only, per the project's testing philosophy -- no
fixtures, no conftest.py, plain `assert` + `math.isclose`.
"""

import dataclasses
import math

import numpy as np
import pytest

from sim.gravity import g, z_hat_g
from sim.params import Params
from sim.state import State

_P = Params(m=0.5, I=0.05, l1=0.3, l2=0.4)


def _y_at_altitude(h: float) -> np.ndarray:
    """State vector at altitude h above the launch point (z = -h), all
    other components zero -- only altitude matters to gravity.g.
    """
    s = State(x=0.0, z=-h, vx=0.0, vz=0.0, theta=0.0, omega=0.0)
    return np.array(s)


def _y_at_downrange(x: float) -> np.ndarray:
    """State vector at downrange position x, all other components zero --
    only x matters to gravity.z_hat_g's "radial" variant.
    """
    s = State(x=x, z=0.0, vx=0.0, vz=0.0, theta=0.0, omega=0.0)
    return np.array(s)


def test_both_models_agree_at_h_zero():
    y0 = _y_at_altitude(0.0)
    g_const = g(0.0, y0, dataclasses.replace(_P, gravity_model="constant"))
    g_rad = g(0.0, y0, dataclasses.replace(_P, gravity_model="radial"))

    assert math.isclose(g_const, _P.g, rel_tol=1e-12)
    assert math.isclose(g_rad, _P.g, rel_tol=1e-12)


def test_constant_reproduces_p_g_at_any_altitude():
    """"constant" ignores altitude entirely -- trivial but worth pinning
    down, since it is the default that every other Phase 2 step regression-
    tests against.
    """
    p = dataclasses.replace(_P, gravity_model="constant")
    for h in (0.0, 1650.7, 10_000.0, 100_000.0, -5.0):
        assert g(0.0, _y_at_altitude(h), p) == _P.g


def test_radial_decreases_monotonically_with_altitude():
    p = dataclasses.replace(_P, gravity_model="radial")
    altitudes = [0.0, 1_000.0, 10_000.0, 100_000.0, 1_000_000.0]
    values = [g(0.0, _y_at_altitude(h), p) for h in altitudes]
    assert all(a > b for a, b in zip(values, values[1:]))


def test_wgs84_matches_equatorial_gravity_at_equator_sea_level():
    """gamma0(0) = ge = 9.7803253359 m/s^2 exactly (sin(0) = 0 kills both
    the Somigliana correction and the free-air term at h = 0).
    """
    p = dataclasses.replace(_P, gravity_model="wgs84", lat0_deg=0.0, h0_m=0.0)
    assert math.isclose(g(0.0, _y_at_altitude(0.0), p), 9.7803253359, rel_tol=1e-9)


def test_wgs84_matches_polar_gravity_at_pole_sea_level():
    """gamma0(90deg) = ge*(1+k)/sqrt(1-e^2) = gp = 9.8321849378 m/s^2, the
    published WGS84 polar normal gravity (architecture.md SS13).
    """
    p = dataclasses.replace(_P, gravity_model="wgs84", lat0_deg=90.0, h0_m=0.0)
    assert math.isclose(g(0.0, _y_at_altitude(0.0), p), 9.8321849378, rel_tol=1e-6)


def test_wgs84_mid_latitude_near_standard_gravity():
    """roadmap.md Step 11's check: ~9.80665 near 45.5 deg latitude at sea
    level (the WGS84 ellipsoid is defined so its normal gravity crosses the
    "standard gravity" g0 value close to 45.5 deg, not exactly 45 deg)."""
    p = dataclasses.replace(_P, gravity_model="wgs84", lat0_deg=45.5, h0_m=0.0)
    assert math.isclose(g(0.0, _y_at_altitude(0.0), p), 9.80665, rel_tol=2e-4)


def test_wgs84_decreases_with_altitude():
    """Free-air correction: g must decrease as h_msl increases, at fixed
    latitude (architecture.md SS13's second-order correction, leading term
    -2h/a)."""
    p = dataclasses.replace(_P, gravity_model="wgs84", lat0_deg=45.0, h0_m=0.0)
    altitudes = [0.0, 1_000.0, 10_000.0, 30_000.0]
    values = [g(0.0, _y_at_altitude(h), p) for h in altitudes]
    assert all(a > b for a, b in zip(values, values[1:]))


def test_wgs84_agrees_with_radial_to_1e4_relative_over_0_to_30km():
    """roadmap.md Step 11's check: the wgs84 altitude dependence matches
    `radial` to ~1e-4 relative over 0-30 km (both models correct the same
    g0-at-h=0 reference by a comparable inverse-square-like falloff)."""
    p_wgs = dataclasses.replace(_P, gravity_model="wgs84", lat0_deg=45.5, h0_m=0.0)
    p_rad = dataclasses.replace(_P, gravity_model="radial", g=9.80665)
    for h in (0.0, 1_000.0, 10_000.0, 30_000.0):
        g_wgs = g(0.0, _y_at_altitude(h), p_wgs)
        g_rad = g(0.0, _y_at_altitude(h), p_rad)
        assert math.isclose(g_wgs, g_rad, rel_tol=1e-3)


def test_wgs84_h0_m_offsets_altitude_msl():
    """h_msl = p.h0_m - z (architecture.md SS15): a launch site elevated
    above MSL sees a *lower* g at z = 0 than one at MSL, matching the h0_m
    metres of extra free-air correction."""
    p_sea = dataclasses.replace(_P, gravity_model="wgs84", lat0_deg=45.0, h0_m=0.0)
    p_high = dataclasses.replace(_P, gravity_model="wgs84", lat0_deg=45.0, h0_m=2000.0)
    y0 = _y_at_altitude(0.0)
    assert g(0.0, y0, p_high) < g(0.0, y0, p_sea)


def test_z_hat_g_parallel_is_the_fixed_up_vector_regardless_of_downrange_position():
    """"parallel" (the default, main.tex SSModels > Gravity > Direction) is
    z_hat_g = (0, 1) for every x -- the direction is frozen at the launch
    site's own local vertical, so it must not read y[X] at all.
    """
    p = dataclasses.replace(_P, gravity_direction="parallel")
    for x in (0.0, 1e3, 1e5, 1e6):
        z = z_hat_g(0.0, _y_at_downrange(x), p)
        assert np.array_equal(z, np.array([0.0, 1.0]))


def test_z_hat_g_radial_matches_parallel_at_zero_downrange_and_has_unit_norm():
    """"radial" (main.tex eq:zhat_g_rotated) reduces to the parallel vector
    exactly at x = 0 (phi = 0), and stays a unit vector for every phi --
    it is a rigid rotation of the launch-point basis, never a rescaling.
    """
    p = dataclasses.replace(_P, gravity_direction="radial")

    z0 = z_hat_g(0.0, _y_at_downrange(0.0), p)
    assert z0[0] == 0.0
    assert z0[1] == 1.0

    for x in (1e3, 1e4, 1e5, 1e6):
        z = z_hat_g(0.0, _y_at_downrange(x), p)
        assert math.isclose(np.linalg.norm(z), 1.0, rel_tol=0.0, abs_tol=1e-12)


def test_unknown_gravity_model_raises_keyerror():
    """No input validation (architecture.md SS7/SS12): an unrecognised
    `gravity_model` string raises KeyError at the first RHS call, from the
    module-private dispatch dict.
    """
    p = dataclasses.replace(_P, gravity_model="not-a-real-model")
    with pytest.raises(KeyError):
        g(0.0, _y_at_altitude(0.0), p)
