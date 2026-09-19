"""Reference-value tests for sim/atmosphere.py's "isa" tier (architecture.md
SS14; main.tex SSModels > Atmosphere; roadmap.md Step 12).

Physics sanity checks against well-known ISA reference values, per the
project's testing philosophy -- no fixtures, no conftest.py, plain
`assert` + `math.isclose`.
"""

import dataclasses
import math

import numpy as np
import pytest

from sim.atmosphere import _R_ISA, air_state
from sim.params import Params
from sim.state import State

_P = Params(m=0.5, I=0.05, l1=0.3, l2=0.4)


def _y_at_altitude(h: float) -> np.ndarray:
    """State vector at altitude h above the launch point (z = -h), all
    other components zero -- only altitude matters to atmosphere.air_state.
    """
    s = State(x=0.0, z=-h, vx=0.0, vz=0.0, theta=0.0, omega=0.0)
    return np.array(s)


def _h_msl_for_geopotential(H: float) -> float:
    """Inverse of H = R_isa*h/(R_isa + h): the geometric h_msl that maps to
    a given geopotential altitude H. Needed because architecture.md SS14's
    layer table boundaries (e.g. H = 11000 m) are geopotential, while
    air_state's input is geometric h_msl -- the two differ by ~19 m at
    11 km, enough to move a geometric h_msl=11000 test point into the wrong
    layer. Used only to pin the layer table exactly in tests below.
    """
    return H * _R_ISA / (_R_ISA - H)


def test_sea_level_matches_isa_reference_values():
    """Standard ISA sea-level reference point (roadmap.md Step 12's check
    and the well-known textbook values)."""
    air = air_state(0.0, _y_at_altitude(0.0), _P)
    assert math.isclose(air.rho, 1.225, rel_tol=1e-3)
    assert math.isclose(air.p, 101325.0, rel_tol=1e-9)
    assert math.isclose(air.T, 288.15, rel_tol=1e-9)
    assert math.isclose(air.a, 340.29, rel_tol=1e-3)


def test_sea_level_sutherland_viscosity():
    """mu(288.15 K) = 1.789e-5 Pa*s (roadmap.md Step 12's check)."""
    air = air_state(0.0, _y_at_altitude(0.0), _P)
    assert math.isclose(air.mu, 1.789e-5, rel_tol=2e-3)


def test_tropopause_temperature_and_pressure():
    """At the geopotential H = 11 km (the troposphere/tropopause boundary),
    T = 216.65 K exactly (start of the isothermal layer) and
    p = 22632.06 Pa (architecture.md SS14's layer table; roadmap.md Step
    12's check). Uses the geometric h_msl that maps to H = 11000 m exactly,
    since air_state's input is geometric, not geopotential, altitude."""
    h_msl = _h_msl_for_geopotential(11000.0)
    air = air_state(0.0, _y_at_altitude(h_msl), _P)
    assert math.isclose(air.T, 216.65, rel_tol=1e-9)
    assert math.isclose(air.p, 22632.06, rel_tol=1e-4)


def test_tropopause_at_geometric_11km_shows_geopotential_correction():
    """At a *geometric* h_msl = 11000 m exactly (as opposed to geopotential
    H = 11000 m above), the geopotential correction
    (H = R_isa*h/(R_isa+h) < h) keeps H just under the 11 km boundary, so
    the point is still (barely) inside the troposphere's lapse layer and T
    is slightly above 216.65 K, not equal to it. Documents the distinction
    exercised by the two tests around it."""
    air = air_state(0.0, _y_at_altitude(11000.0), _P)
    assert air.T > 216.65
    assert math.isclose(air.T, 216.65, rel_tol=1e-3)


def test_20km_temperature_matches_layer_table():
    """T(20 km) = 216.65 K -- end of the isothermal tropopause layer, still
    the same temperature as its base (roadmap.md Step 12's check)."""
    air = air_state(0.0, _y_at_altitude(20000.0), _P)
    assert math.isclose(air.T, 216.65, rel_tol=1e-6)


def test_5000m_interpolates_within_troposphere_layer():
    """h_msl = 5000 m sits inside the troposphere's linear-lapse layer:
    T = 288.15 - 0.0065*H(5000) is within a fraction of a kelvin of the
    naive 255.65 K (the ~4 m geopotential-vs-geometric correction at this
    altitude), and rho/p/a/mu should all be strictly between their
    sea-level and tropopause values, showing the formula interpolates
    smoothly across the layer."""
    air = air_state(0.0, _y_at_altitude(5000.0), _P)
    air0 = air_state(0.0, _y_at_altitude(0.0), _P)
    air11 = air_state(0.0, _y_at_altitude(11000.0), _P)

    assert math.isclose(air.T, 255.65, rel_tol=1e-3)
    assert air11.rho < air.rho < air0.rho
    assert air11.p < air.p < air0.p
    assert air11.a < air.a < air0.a
    assert air11.mu < air.mu < air0.mu


def test_density_decreases_monotonically_with_altitude():
    """rho monotone decreasing to 80 km (roadmap.md Step 12's check),
    spanning all seven layers of the table."""
    altitudes = [0.0, 5_000.0, 11_000.0, 15_000.0, 20_000.0, 32_000.0,
                 47_000.0, 51_000.0, 71_000.0, 80_000.0]
    values = [air_state(0.0, _y_at_altitude(h), _P).rho for h in altitudes]
    assert all(a > b for a, b in zip(values, values[1:]))


def test_isa_ignores_gravity_model():
    """g_isa = 9.80665 is baked into the ISA formula and must not come from
    gravity.g() / p.gravity_model (architecture.md SS14, roadmap.md Step 12
    "Careful"): changing gravity_model must not change the air state."""
    h = 5000.0
    air_const = air_state(
        0.0, _y_at_altitude(h), dataclasses.replace(_P, gravity_model="constant")
    )
    air_wgs84 = air_state(
        0.0,
        _y_at_altitude(h),
        dataclasses.replace(_P, gravity_model="wgs84", lat0_deg=45.5),
    )
    assert air_const == air_wgs84


def test_h0_m_shifts_altitude_to_msl():
    """air_state uses h_msl = p.h0_m - z (architecture.md SS15), so a
    launch site elevated above sea level sees the atmosphere's conditions
    at the corresponding higher MSL altitude even at z = 0."""
    p_high = dataclasses.replace(_P, h0_m=5000.0)
    air_at_pad = air_state(0.0, _y_at_altitude(0.0), p_high)
    air_5000_sea = air_state(0.0, _y_at_altitude(5000.0), _P)
    assert math.isclose(air_at_pad.T, air_5000_sea.T, rel_tol=1e-9)
    assert math.isclose(air_at_pad.p, air_5000_sea.p, rel_tol=1e-9)


def test_unknown_atmosphere_model_raises_keyerror():
    """No input validation (architecture.md SS7/SS12): an unrecognised
    `atmosphere_model` string raises KeyError at the first call, from the
    module-private dispatch dict."""
    p = dataclasses.replace(_P, atmosphere_model="not-a-real-model")
    with pytest.raises(KeyError):
        air_state(0.0, _y_at_altitude(0.0), p)
