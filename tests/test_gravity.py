"""Sign-check / algebraic tests for sim/gravity.py (architecture.md SS12,
SS13; main.tex SSModels > Gravity; roadmap.md Step 10).

Physics sanity checks only, per the project's testing philosophy -- no
fixtures, no conftest.py, plain `assert` + `math.isclose`.
"""

import dataclasses
import math

import numpy as np
import pytest

from sim.gravity import _R_chi, curvature_radius, g, z_hat_g
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


# ---------------------------------------------------------------------
# Step 41 (Phase 2.7): elliptical gravity direction (architecture.md
# SS24.1), the osculating-sphere radius of curvature R_chi(phi0, chi) and
# the "elliptical" z_hat_g variant built from it.
# ---------------------------------------------------------------------


def test_parallel_and_radial_reproduce_prior_z_hat_g_bit_for_bit():
    """Step 41 must not move either pre-existing direction variant:
    "parallel" never touches the new code at all, and "radial" evaluates
    the *same expression on the same operands* (`y[X]/p.R_e`) through the
    new shared `_dir_curved`, so both are checked bit-for-bit
    (`np.array_equal`), not merely "close", at several `x`/`R_e` combos.
    """
    for x in (0.0, 1e3, 1e4, 1e5):
        for R_e in (6371000.0, 1000.0):
            p_par = dataclasses.replace(_P, gravity_direction="parallel", R_e=R_e)
            p_rad = dataclasses.replace(_P, gravity_direction="radial", R_e=R_e)
            y = _y_at_downrange(x)

            z_par = z_hat_g(0.0, y, p_par)
            z_rad = z_hat_g(0.0, y, p_rad)

            assert np.array_equal(z_par, np.array([0.0, 1.0]))
            phi = x / R_e
            assert np.array_equal(z_rad, np.array([-np.sin(phi), np.cos(phi)]))


def test_R_chi_matches_meridional_radius_at_chi_zero():
    """R_chi(phi0, chi=0 -- due North) is exactly M(phi0), the meridional
    radius of curvature (architecture.md SS24.1's pinned table), since
    cos^2(0)=1, sin^2(0)=0 collapses the Euler formula to 1/(1/M) = M."""
    for lat0_deg, expected_M in ((0.0, 6335439.3273), (50.0, 6372955.9257), (90.0, 6399593.6258)):
        p = dataclasses.replace(_P, lat0_deg=lat0_deg, azimuth_deg=0.0)
        assert math.isclose(_R_chi(p), expected_M, rel_tol=1e-8)


def test_R_chi_matches_prime_vertical_radius_at_chi_90():
    """R_chi(phi0, chi=90 -- due East) is exactly N(phi0), the prime-
    vertical radius of curvature (architecture.md SS24.1's pinned table)."""
    for lat0_deg, expected_N in ((0.0, 6378137.0000), (50.0, 6390702.0442), (90.0, 6399593.6258)):
        p = dataclasses.replace(_P, lat0_deg=lat0_deg, azimuth_deg=90.0)
        assert math.isclose(_R_chi(p), expected_N, rel_tol=1e-8)


def test_R_chi_is_azimuth_independent_at_the_pole():
    """At the pole M(90) == N(90) exactly (sin^2(90) = 1 in both formulas
    collapses to the same value), so R_chi must not depend on chi there."""
    p0 = dataclasses.replace(_P, lat0_deg=90.0, azimuth_deg=0.0)
    for chi in (0.0, 30.0, 45.0, 90.0, 180.0, 270.0):
        p = dataclasses.replace(_P, lat0_deg=90.0, azimuth_deg=chi)
        assert math.isclose(_R_chi(p), _R_chi(p0), rel_tol=1e-12)


def test_curvature_radius_dispatch():
    """`curvature_radius(p)` is the public accessor the "elliptical"
    z_hat_g/ground-depth constructions share: `None` for "parallel",
    `p.R_e` for "radial" (unchanged), `_R_chi(p)` for "elliptical"."""
    p_par = dataclasses.replace(_P, gravity_direction="parallel", R_e=6371000.0)
    p_rad = dataclasses.replace(_P, gravity_direction="radial", R_e=6371000.0)
    p_ell = dataclasses.replace(_P, gravity_direction="elliptical", lat0_deg=50.0, azimuth_deg=90.0)

    assert curvature_radius(p_par) is None
    assert curvature_radius(p_rad) == p_rad.R_e
    assert math.isclose(curvature_radius(p_ell), _R_chi(p_ell), rel_tol=1e-15)


def test_z_hat_g_elliptical_unit_norm_and_exact_at_zero_downrange():
    """`z_hat_g` for "elliptical" is a unit vector for every phi, and
    exactly `(0.0, 1.0)` at x=0 (phi=0) -- same properties Step 38 pinned
    for "radial"."""
    p = dataclasses.replace(_P, gravity_direction="elliptical", lat0_deg=50.0, azimuth_deg=90.0)

    z0 = z_hat_g(0.0, _y_at_downrange(0.0), p)
    assert z0[0] == 0.0
    assert z0[1] == 1.0

    for x in (1e3, 1e4, 1e5, 1e6):
        z = z_hat_g(0.0, _y_at_downrange(x), p)
        assert math.isclose(np.linalg.norm(z), 1.0, rel_tol=0.0, abs_tol=1e-12)


def test_elliptical_vs_radial_matches_pinned_delta_phi_at_10km():
    """architecture.md SS24.1's pinned refinement, phi0=50, chi=90, x=10km:
    Delta_phi = x*(1/R_e - 1/R_chi) = 4.839e-6 rad, and the downrange
    gravity component -g*sin(phi) moves from -1.539263e-2 to
    -1.534518e-2 m/s^2 (a 0.31% refinement of a small term)."""
    lat0_deg, azimuth_deg, x = 50.0, 90.0, 10_000.0
    p_rad = dataclasses.replace(_P, gravity_direction="radial", lat0_deg=lat0_deg,
                                 azimuth_deg=azimuth_deg, R_e=6371000.0)
    p_ell = dataclasses.replace(_P, gravity_direction="elliptical", lat0_deg=lat0_deg,
                                 azimuth_deg=azimuth_deg)

    phi_rad = x / p_rad.R_e
    phi_ell = x / _R_chi(p_ell)
    # Delta_phi = x*(1/R_e - 1/R_chi) = phi_rad - phi_ell (R_chi > R_e here,
    # so the elliptical phi is the smaller one).
    assert math.isclose(phi_rad - phi_ell, 4.839e-6, rel_tol=1e-3)

    g0 = _P.g  # gravity_model="constant" (the default): g is exactly p.g
    downrange_rad = -g0 * math.sin(phi_rad)
    downrange_ell = -g0 * math.sin(phi_ell)
    assert math.isclose(downrange_rad, -1.539263e-2, rel_tol=1e-5)
    assert math.isclose(downrange_ell, -1.534518e-2, rel_tol=1e-5)


def test_elliptical_direction_ignores_R_e():
    """architecture.md SS24.1: "p.R_e is not read by the elliptical
    direction" -- sweeping R_e must not move an "elliptical" z_hat_g."""
    p_a = dataclasses.replace(_P, gravity_direction="elliptical", lat0_deg=50.0,
                               azimuth_deg=90.0, R_e=6371000.0)
    p_b = dataclasses.replace(_P, gravity_direction="elliptical", lat0_deg=50.0,
                               azimuth_deg=90.0, R_e=1000.0)
    y = _y_at_downrange(10_000.0)
    assert np.array_equal(z_hat_g(0.0, y, p_a), z_hat_g(0.0, y, p_b))


def test_radial_direction_ignores_lat0_and_azimuth():
    """The flip side of the check above: sweeping `lat0_deg`/`azimuth_deg`
    (the two quantities "elliptical" reads) must not move a "radial"
    z_hat_g -- the two dispatches stay orthogonal."""
    p_a = dataclasses.replace(_P, gravity_direction="radial", R_e=6371000.0,
                               lat0_deg=0.0, azimuth_deg=0.0)
    p_b = dataclasses.replace(_P, gravity_direction="radial", R_e=6371000.0,
                               lat0_deg=50.0, azimuth_deg=90.0)
    y = _y_at_downrange(10_000.0)
    assert np.array_equal(z_hat_g(0.0, y, p_a), z_hat_g(0.0, y, p_b))


def test_unknown_gravity_direction_raises_keyerror():
    """Same "no silent flat fallback" property `test_unknown_gravity_model_
    raises_keyerror` exercises for the magnitude dispatch."""
    p = dataclasses.replace(_P, gravity_direction="not-a-real-direction")
    with pytest.raises(KeyError):
        z_hat_g(0.0, _y_at_downrange(0.0), p)

