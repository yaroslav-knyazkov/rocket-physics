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


def test_unknown_gravity_model_raises_keyerror():
    """No input validation (architecture.md SS7/SS12): an unrecognised
    `gravity_model` string raises KeyError at the first RHS call, from the
    module-private dispatch dict.
    """
    p = dataclasses.replace(_P, gravity_model="not-a-real-model")
    with pytest.raises(KeyError):
        g(0.0, _y_at_altitude(0.0), p)
