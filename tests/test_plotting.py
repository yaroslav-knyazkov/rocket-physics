"""Tests for the Step 27 model comparison sweep (`run.sweep`) and overlay
plot (`sim.plotting.plot_trajectory_overlay`) -- architecture.md SS12 ("the
payoff for the selection pattern"), roadmap.md Step 27.

Physics-sanity + smoke checks only, per this project's testing philosophy --
no fixtures, no conftest.py, plain `assert` + `math.isclose`.
"""

import math

import matplotlib

matplotlib.use("Agg")  # headless: this must run before pyplot is imported
# anywhere else in the process (run.py / sim.plotting both import
# matplotlib.pyplot at module scope) -- a non-interactive backend so the
# test suite never tries to pop a GUI window.

import matplotlib.figure
import numpy as np

from run import _flight_summary, sweep
from sim.gravity import altitude_agl, g
from sim.integrate import Result, run_sim
from sim.params import Aero, Gravity, Lengths, Params, Site, Thrust, Weight
from sim.params import replace as params_replace
from sim.plotting import (
    _dense_time_grid,
    plot_time_histories,
    plot_trajectory,
    plot_trajectory_overlay,
)
from sim.state import State, X, Z

# Same base scenario as run.py's own default (motor_curve="placeholder.csv",
# aero_model="constant" -- Phase 1 style constant axial drag), so the
# gravity sweep here reproduces the ~4.6 km apogee scale roadmap.md Step 27
# refers to.
_P = Params(
    weight=Weight(m=0.5, I=0.05),
    lengths=Lengths(l1=0.3, l2=0.4),
    thrust=Thrust(motor_curve="placeholder.csv"),
    aero=Aero(C_x=0.5, C_z=0.0, C_m=0.0),
)
_S0 = State(x=0.0, z=0.0, vx=0.0, vz=0.0, theta=math.pi / 2, omega=0.0)

# A minimal "coefficients" aero setup so the atmosphere is actually
# load-bearing on the trajectory (architecture.md SS12: "constant" ignores
# the atmosphere entirely) -- same setup tests/test_atmosphere.py's
# `_AERO_KW` uses for its own Step 18 ISA-vs-sounding trajectory checks.
_AERO_KW = dict(
    model="linearized",
    S=0.005,
    d_ref=0.08,
    C_A0=0.5,
    C_N_alpha=2.0,
    C_m_alpha=-0.5,
)


def test_sweep_produces_one_result_per_variant():
    variants = ("constant", "radial", "wgs84")
    results = sweep(_P, "gravity.model", variants, _S0)

    assert set(results.keys()) == set(variants)
    for value, d in results.items():
        assert isinstance(d["result"], Result)
        assert d["params"].gravity.model == value
        assert d["apogee_altitude"] > 0.0
        assert d["apogee_time"] > 0.0
        assert d["max_q"] > 0.0
        assert d["impact_time"] > d["apogee_time"]


def test_sweep_gravity_apogee_ordering_is_physically_predictable():
    """At this scenario's ~4.6 km apogee, gravity decreases with altitude
    for "radial"/"wgs84" (architecture.md SS13), so both give less
    deceleration on the way up than "constant" and so a higher apogee.
    "wgs84" additionally starts from a lower g0 at the equator (the default
    `lat0_deg=0.0`: `gamma0(0) = 9.7803253359 < p.g = 9.80665`), so it
    gives the highest apogee of the three -- a strict, predictable ordering,
    the same kind of directional check Step 10's own gravity tests used.
    """
    results = sweep(
        _P, "gravity.model", ("constant", "radial", "wgs84"), _S0
    )
    apogees = {k: v["apogee_altitude"] for k, v in results.items()}

    assert apogees["constant"] < apogees["radial"]
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
    base = params_replace(_P, {
        "site.h0_m": 380.0,
        "soundings.case": "example",
        **{f"aero.{k}": v for k, v in _AERO_KW.items()},
    })
    results = sweep(base, "atmosphere.model", ("isa", "sounding"), _S0)

    assert results["sounding"]["apogee_altitude"] > results["isa"]["apogee_altitude"]
    assert results["sounding"]["max_q"] < results["isa"]["max_q"]


def test_gravity_divergence_grows_with_altitude():
    """roadmap.md Step 27's check: the gravity models differ "by a
    predictable, small amount at a 3 km apogee and a visible one at
    100 km" -- a direct numeric check on `gravity.g`, the same kind Step
    10's own tests (tests/test_gravity.py) used, sampled at this scenario's
    actual apogee altitude (~4.6 km, per run.py's own printed summary) and
    at 100 km. ("linear" removed at Phase 2.5 Step 34.)
    """
    variants = ("constant", "radial", "wgs84")

    def _relative_spread(h: float) -> float:
        y = np.array(
            State(x=0.0, z=-h, vx=0.0, vz=0.0, theta=0.0, omega=0.0)
        )
        values = [
            g(0.0, y, params_replace(_P, {"gravity.model": v})) for v in variants
        ]
        return (max(values) - min(values)) / _P.g0

    spread_low = _relative_spread(4609.2267)  # this scenario's own apogee
    spread_high = _relative_spread(100_000.0)

    # "small" at ~4.6 km: well under 1% relative.
    assert spread_low < 0.01
    # "visible" at 100 km: several times larger than the low-altitude
    # spread (measured: ~8x), not just marginally bigger.
    assert spread_high > 5.0 * spread_low


def test_plot_trajectory_overlay_returns_valid_figure_for_two_variants():
    r_const = run_sim(params_replace(_P, {"gravity.model": "constant"}), _S0)
    r_wgs84 = run_sim(params_replace(_P, {"gravity.model": "wgs84"}), _S0)

    fig = plot_trajectory_overlay({"constant": r_const, "wgs84": r_wgs84})

    assert isinstance(fig, matplotlib.figure.Figure)
    assert len(fig.axes) == 2
    for ax in fig.axes:
        assert len(ax.lines) == 2  # one line per variant


# ---------------------------------------------------------------------
# Step 45 (Phase 2.8; architecture.md SS25.5): the reported/plotted
# altitude becomes `gravity.altitude_agl(y, r.params)`, bit-for-bit
# unchanged under the default `gravity_direction="parallel"`.
# ---------------------------------------------------------------------

# A tilted (x != 0 throughout) scenario, reused across the checks below --
# the vertical run.py default (x == 0 always) cannot distinguish a
# converted from an unconverted call site (architecture.md SS25.5).
_TILT_S0 = State(x=0.0, z=0.0, vx=50.0, vz=0.0, theta=math.radians(80.0), omega=0.0)
_TILT_AERO_KW = dict(
    model="linearized", S=0.005, d_ref=0.08, C_A0=0.5,
    C_N_alpha=2.0, C_m_alpha=-0.5,
)


def test_plotted_altitude_bit_for_bit_under_parallel():
    """architecture.md SS25.6/SS25.9: under the default
    `gravity_direction="parallel"`, `plot_trajectory`/`plot_time_histories`/
    `plot_trajectory_overlay`'s altitude series are bitwise what they were
    pre-Step-45 -- pulled off the returned figure (`ax.lines[i].get_ydata()`)
    and compared against `-y[Z]`-style reference arrays built the old way,
    on the same dense grid `_dense_time_grid` produces.
    """
    p = params_replace(_P, {
        "gravity.model": "wgs84",
        "site.lat0_deg": 50.0,
        **{f"aero.{k}": v for k, v in _TILT_AERO_KW.items()},
    })
    r = run_sim(p, _TILT_S0)

    t = _dense_time_grid(r)
    y = r.raw.sol(t)
    expected = -y[Z]  # the pre-Step-45 formula, on the same operand

    fig_traj = plot_trajectory(r)
    assert np.array_equal(fig_traj.axes[0].lines[0].get_ydata(), expected)

    fig_hist = plot_time_histories(r)
    assert np.array_equal(fig_hist.axes[0].lines[0].get_ydata(), expected)

    fig_overlay = plot_trajectory_overlay({"only": r})
    assert np.array_equal(fig_overlay.axes[0].lines[0].get_ydata(), expected)
    assert np.array_equal(fig_overlay.axes[1].lines[0].get_ydata(), expected)


def test_plot_trajectory_overlay_reads_each_variants_own_params():
    """architecture.md SS25.9: `Result.params` is read *per line*, not
    once -- two `Result`s built from the *same* underlying trajectory
    (t/y/events/raw identical) but deliberately different `params`
    (`gravity_direction`) must draw two different altitude series, and
    each must match `altitude_agl` computed with its own `params`
    directly -- isolating the "params read per line" wiring from any
    physics difference between the two runs.
    """
    p_par = params_replace(_P, {"gravity.direction": "parallel"})
    r = run_sim(p_par, _TILT_S0)

    p_rad = params_replace(_P, {"gravity.direction": "radial", "gravity.R_e": 6371000.0})
    r_relabelled = Result(t=r.t, y=r.y, events=r.events, raw=r.raw, params=p_rad)

    fig = plot_trajectory_overlay({"parallel": r, "radial": r_relabelled})
    y_par = fig.axes[1].lines[0].get_ydata()
    y_rad = fig.axes[1].lines[1].get_ydata()
    t = fig.axes[1].lines[0].get_xdata()

    assert not np.array_equal(y_par, y_rad)

    y_hist = r.raw.sol(t)
    assert np.array_equal(y_par, altitude_agl(y_hist, p_par))
    assert np.array_equal(y_rad, altitude_agl(y_hist, p_rad))


def test_flight_summary_apogee_altitude_equals_helper_directly():
    """architecture.md SS25.9: `_flight_summary(result, p)["apogee_altitude"]`
    equals `altitude_agl(result.raw.sol(t_apogee), p)` exactly, for all
    three direction models, on a tilted (x != 0) run."""
    weight = Weight(m=0.5, I=0.05)
    lengths = Lengths(l1=0.3, l2=0.4)
    thrust = Thrust(motor_curve="placeholder.csv")
    aero = Aero(**_TILT_AERO_KW)
    site = Site(lat0_deg=50.0, azimuth_deg=90.0)
    for direction in ("parallel", "radial", "elliptical"):
        p = Params(
            weight=weight, lengths=lengths, thrust=thrust, aero=aero, site=site,
            gravity=Gravity(direction=direction, R_e=6371000.0),
        )
        result = run_sim(p, _TILT_S0)
        summary = _flight_summary(result, p)
        t_apogee = result.events["apogee"]
        expected = altitude_agl(result.raw.sol(t_apogee), p)
        assert summary["apogee_altitude"] == expected


def test_apogee_altitude_geometric_magnitude_for_tilted_radial_run():
    """architecture.md SS25.9's "Geometric magnitude" check, and the
    separate assertion `main()`'s inline apogee-altitude copy needs
    (architecture.md SS25.5): `main()` does not call `_flight_summary`, so
    its own expression -- `altitude_agl(result.raw.sol(apogee_time), p)`,
    mirrored verbatim here (`main()` itself writes plot/CSV files and
    prints, so it is not structured for isolated invocation) -- is
    exercised on a tilted "radial" run, where it differs from the flat
    value, unlike the committed vertical `run.py` scenario where the two
    coincide and a missed conversion would be invisible.

    For the run's own apogee state `y_a`, `apogee_altitude - (-y_a[Z])`
    equals the closed form `x*sin(phi) - z*cos(phi) - R*(1-cos(phi)) + z`
    exactly, is strictly positive, and is within a few percent of
    `x_a**2 / (2*R_e)` (the small-angle approximation).
    """
    R_e = 6371000.0
    p = Params(
        weight=Weight(m=0.5, I=0.05),
        lengths=Lengths(l1=0.3, l2=0.4),
        thrust=Thrust(motor_curve="placeholder.csv"),
        aero=Aero(**_TILT_AERO_KW),
        gravity=Gravity(direction="radial", R_e=R_e),
    )
    result = run_sim(p, _TILT_S0)

    apogee_time = result.events["apogee"]
    y_a = result.raw.sol(apogee_time)
    apogee_altitude = altitude_agl(y_a, p)  # main()'s own expression

    x_a, z_a = y_a[X], y_a[Z]
    phi = x_a / R_e
    closed_form = x_a * math.sin(phi) - z_a * math.cos(phi) - R_e * (1.0 - math.cos(phi)) + z_a
    diff = apogee_altitude - (-z_a)
    approx = x_a ** 2 / (2.0 * R_e)

    assert math.isclose(diff, closed_form, rel_tol=1e-9)
    assert diff > 0.0
    assert math.isclose(diff, approx, rel_tol=0.05)


def test_reported_altitude_is_agl_not_msl_with_h0_m():
    """architecture.md SS25.9's guard: with `h0_m=380.0`, the reported/
    plotted altitude at `z=0` (the pad, `t=0`) is `0.0`, not `380.0` --
    the check against `altitude_msl` being wired in by mistake, which
    would silently raise every LKPR-sweep curve by 380 m."""
    p = params_replace(_P, {"site.h0_m": 380.0})
    result = run_sim(p, _S0)

    altitude = plot_trajectory(result).axes[0].lines[0].get_ydata()
    assert math.isclose(altitude[0], 0.0, abs_tol=1e-9)
