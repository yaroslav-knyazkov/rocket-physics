"""Tests for the Step 27 model comparison sweep (`run.sweep`) and overlay
plot (`sim.plotting.plot_trajectory_overlay`) -- architecture.md SS12 ("the
payoff for the selection pattern"), roadmap.md Step 27.

Physics-sanity + smoke checks only, per this project's testing philosophy --
no fixtures, no conftest.py, plain `assert` + `math.isclose`.
"""

import dataclasses
import math

import matplotlib

matplotlib.use("Agg")  # headless: this must run before pyplot is imported
# anywhere else in the process (run.py / sim.plotting both import
# matplotlib.pyplot at module scope) -- a non-interactive backend so the
# test suite never tries to pop a GUI window.

import matplotlib.figure
import numpy as np

from run import sweep
from sim.gravity import g
from sim.integrate import Result, run_sim
from sim.params import Params
from sim.plotting import plot_trajectory_overlay
from sim.state import State

# Same base scenario as run.py's own default (motor_curve="placeholder.csv",
# aero_model="constant" -- Phase 1 style constant axial drag), so the
# gravity sweep here reproduces the ~4.6 km apogee scale roadmap.md Step 27
# refers to.
_P = Params(
    m=0.5, I=0.05, l1=0.3, l2=0.4, motor_curve="placeholder.csv",
    A_x=0.5, A_z=0.0, A_m=0.0,
)
_S0 = State(x=0.0, z=0.0, vx=0.0, vz=0.0, theta=math.pi / 2, omega=0.0)

# A minimal "coefficients" aero setup so the atmosphere is actually
# load-bearing on the trajectory (architecture.md SS12: "constant" ignores
# the atmosphere entirely) -- same setup tests/test_atmosphere.py's
# `_AERO_KW` uses for its own Step 18 ISA-vs-sounding trajectory checks.
_AERO_KW = dict(
    aero_model="coefficients",
    S=0.005,
    d_ref=0.08,
    C_A0=0.5,
    C_N_alpha=2.0,
    C_m_alpha=-0.5,
)


def test_sweep_produces_one_result_per_variant():
    variants = ("constant", "linear", "radial", "wgs84")
    results = sweep(_P, "gravity_model", variants, _S0)

    assert set(results.keys()) == set(variants)
    for value, d in results.items():
        assert isinstance(d["result"], Result)
        assert d["params"].gravity_model == value
        assert d["apogee_altitude"] > 0.0
        assert d["apogee_time"] > 0.0
        assert d["max_q"] > 0.0
        assert d["impact_time"] > d["apogee_time"]


def test_sweep_gravity_apogee_ordering_is_physically_predictable():
    """At this scenario's ~4.6 km apogee, gravity decreases with altitude
    for "linear"/"radial"/"wgs84" (architecture.md SS13), so all three give
    less deceleration on the way up than "constant" and so a higher apogee.
    "linear" and "radial" are near-identical this low (Step 10's own
    `test_linear_and_radial_agree_closely_at_10km` established this to
    ~1e-5 relative at 10 km, so well within 1e-3 at ~4.6 km). "wgs84"
    additionally starts from a lower g0 at the equator (the default
    `lat0_deg=0.0`: `gamma0(0) = 9.7803253359 < p.g = 9.80665`), so it
    gives the highest apogee of the four -- a strict, predictable ordering,
    the same kind of directional check Step 10's own gravity tests used.
    """
    results = sweep(
        _P, "gravity_model", ("constant", "linear", "radial", "wgs84"), _S0
    )
    apogees = {k: v["apogee_altitude"] for k, v in results.items()}

    assert apogees["constant"] < apogees["linear"]
    assert apogees["constant"] < apogees["radial"]
    assert math.isclose(apogees["linear"], apogees["radial"], rel_tol=1e-3)
    assert apogees["wgs84"] > apogees["radial"]


def test_sweep_atmosphere_isa_vs_sounding_shows_real_atmosphere_matters():
    """ISA vs. the real LKPR sounding (data/soundings/example, Step 17):
    LKPR's air is measurably less dense than ISA at its own elevation
    (tests/test_atmosphere.py's
    `test_sounding_real_example_density_lower_than_isa_at_station_elevation`),
    so a full trajectory launched from the station's own elevation
    (`h0_m=380.0`, matching LKPR's `elevation_m`) must show *less* drag with
    the real sounding than with ISA -- higher apogee, lower max-Q --
    roadmap.md Step 27's stated check: "ISA vs a real sounding shows where
    the real atmosphere matters".
    """
    base = dataclasses.replace(_P, h0_m=380.0, sounding_case="example", **_AERO_KW)
    results = sweep(base, "atmosphere_model", ("isa", "sounding"), _S0)

    assert results["sounding"]["apogee_altitude"] > results["isa"]["apogee_altitude"]
    assert results["sounding"]["max_q"] < results["isa"]["max_q"]


def test_gravity_divergence_grows_with_altitude():
    """roadmap.md Step 27's check: the four gravity models differ "by a
    predictable, small amount at a 3 km apogee and a visible one at
    100 km" -- a direct numeric check on `gravity.g`, the same kind Step
    10's own tests (tests/test_gravity.py) used, sampled at this scenario's
    actual apogee altitude (~4.6 km, per run.py's own printed summary) and
    at 100 km.
    """
    variants = ("constant", "linear", "radial", "wgs84")

    def _relative_spread(h: float) -> float:
        y = np.array(
            State(x=0.0, z=-h, vx=0.0, vz=0.0, theta=0.0, omega=0.0)
        )
        values = [
            g(0.0, y, dataclasses.replace(_P, gravity_model=v)) for v in variants
        ]
        return (max(values) - min(values)) / _P.g

    spread_low = _relative_spread(4609.2267)  # this scenario's own apogee
    spread_high = _relative_spread(100_000.0)

    # "small" at ~4.6 km: well under 1% relative.
    assert spread_low < 0.01
    # "visible" at 100 km: several times larger than the low-altitude
    # spread (measured: ~8x), not just marginally bigger.
    assert spread_high > 5.0 * spread_low


def test_plot_trajectory_overlay_returns_valid_figure_for_two_variants():
    r_const = run_sim(dataclasses.replace(_P, gravity_model="constant"), _S0)
    r_wgs84 = run_sim(dataclasses.replace(_P, gravity_model="wgs84"), _S0)

    fig = plot_trajectory_overlay({"constant": r_const, "wgs84": r_wgs84})

    assert isinstance(fig, matplotlib.figure.Figure)
    assert len(fig.axes) == 2
    for ax in fig.axes:
        assert len(ax.lines) == 2  # one line per variant
