"""Sign-check / algebraic tests for sim/gravity.py (architecture.md SS12,
SS13; main.tex SSModels > Gravity; roadmap.md Step 10).

Physics sanity checks only, per the project's testing philosophy -- no
fixtures, no conftest.py, plain `assert` + `math.isclose`.
"""

import dataclasses
import math

import numpy as np
import pytest

from sim.gravity import g
from sim.params import Params
from sim.state import State

_P = Params(m=0.5, I=0.05, l1=0.3, l2=0.4)


def _y_at_altitude(h: float) -> np.ndarray:
    """State vector at altitude h above the launch point (z = -h), all
    other components zero -- only altitude matters to gravity.g.
    """
    s = State(x=0.0, z=-h, vx=0.0, vz=0.0, theta=0.0, omega=0.0)
    return np.array(s)


def test_all_three_models_agree_at_h_zero():
    y0 = _y_at_altitude(0.0)
    g_const = g(0.0, y0, dataclasses.replace(_P, gravity_model="constant"))
    g_lin = g(0.0, y0, dataclasses.replace(_P, gravity_model="linear"))
    g_rad = g(0.0, y0, dataclasses.replace(_P, gravity_model="radial"))

    assert math.isclose(g_const, _P.g, rel_tol=1e-12)
    assert math.isclose(g_lin, _P.g, rel_tol=1e-12)
    assert math.isclose(g_rad, _P.g, rel_tol=1e-12)


def test_constant_reproduces_p_g_at_any_altitude():
    """"constant" ignores altitude entirely -- trivial but worth pinning
    down, since it is the default that every other Phase 2 step regression-
    tests against.
    """
    p = dataclasses.replace(_P, gravity_model="constant")
    for h in (0.0, 1650.7, 10_000.0, 100_000.0, -5.0):
        assert g(0.0, _y_at_altitude(h), p) == _P.g


def test_linear_and_radial_agree_closely_at_10km():
    """At h = 10 km (h/R_e ~ 1.6e-3), the linear model is the first-order
    Taylor expansion of the exact inverse-square law, so the truncation
    error is O((h/R_e)^2) ~ 2.5e-6 relative -- "~1e-6 relative" per
    roadmap.md Step 10's check, order of magnitude, not an exact bound.
    """
    y = _y_at_altitude(10_000.0)
    p_lin = dataclasses.replace(_P, gravity_model="linear")
    p_rad = dataclasses.replace(_P, gravity_model="radial")

    g_lin = g(0.0, y, p_lin)
    g_rad = g(0.0, y, p_rad)

    assert math.isclose(g_lin, g_rad, rel_tol=1e-5)


def test_linear_and_radial_diverge_visibly_at_100km():
    """At h = 100 km (h/R_e ~ 1.6e-2), the first-order truncation error is
    second-order in h/R_e, i.e. ~2.5e-4 relative -- well above the 10 km
    tolerance, so the two models must visibly disagree here.
    """
    y = _y_at_altitude(100_000.0)
    p_lin = dataclasses.replace(_P, gravity_model="linear")
    p_rad = dataclasses.replace(_P, gravity_model="radial")

    g_lin = g(0.0, y, p_lin)
    g_rad = g(0.0, y, p_rad)

    assert not math.isclose(g_lin, g_rad, rel_tol=1e-6)
    # Still close in absolute terms (a few 0.01 m/s^2), just not to 1e-6.
    assert math.isclose(g_lin, g_rad, rel_tol=1e-2)


def test_radial_decreases_monotonically_with_altitude():
    p = dataclasses.replace(_P, gravity_model="radial")
    altitudes = [0.0, 1_000.0, 10_000.0, 100_000.0, 1_000_000.0]
    values = [g(0.0, _y_at_altitude(h), p) for h in altitudes]
    assert all(a > b for a, b in zip(values, values[1:]))


def test_linear_goes_negative_above_half_earth_radius():
    """Documented, not guarded (architecture.md SS13): the linear model's
    formula is g0*(1 - 2h/R_e), which crosses zero at h = R_e/2.
    """
    p = dataclasses.replace(_P, gravity_model="linear")
    h = _P.R_e / 2.0 + 1.0
    assert g(0.0, _y_at_altitude(h), p) < 0.0


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


def test_unknown_gravity_model_raises_keyerror():
    """No input validation (architecture.md SS7/SS12): an unrecognised
    `gravity_model` string raises KeyError at the first RHS call, from the
    module-private dispatch dict.
    """
    p = dataclasses.replace(_P, gravity_model="not-a-real-model")
    with pytest.raises(KeyError):
        g(0.0, _y_at_altitude(0.0), p)
