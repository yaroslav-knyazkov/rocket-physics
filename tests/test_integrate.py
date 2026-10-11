"""Tests for the burnout event added in sim/integrate.py (roadmap.md
Step 14). Physics/numerics sanity checks only, per the project's testing
philosophy -- no fixtures, no conftest.py, plain `assert` + `math.isclose`.
"""

import math

import numpy as np

from sim.integrate import _apogee_event, run_sim
from sim.params import (
    Aero, Atmosphere, Gravity, Lengths, Params, Site, Soundings, Thrust, Weight, Wind,
    with_solver,
)
from sim.state import State


# data/motors/placeholder.csv burns from t=0 (thrust=0) up through an
# ignition spike, a flat sustain, and a linear tail-off that reaches zero
# exactly at t=2.0 s -- see that file's header comment.
BURNOUT_EXPECTED = 2.0
BURNOUT_TOL = 0.05


def test_rk45_burnout_event_detected():
    """RK45's solve_ivp-based burnout event fires once, at the curve's
    tail-off-to-zero time, and not spuriously at t=0 (the curve starts at
    zero thrust and rises on ignition, which `direction=-1` excludes).
    """
    p = Params(
        weight=Weight(m=0.5, I=0.05),
        lengths=Lengths(l1=0.3, l2=0.4),
        thrust=Thrust(motor_curve="placeholder.csv"),
    )
    s0 = State(x=0.0, z=0.0, vx=0.0, vz=0.0, theta=math.pi / 2, omega=0.0)

    result = run_sim(p, s0)

    t_burnout = result.events["burnout"]
    assert t_burnout is not None
    assert math.isclose(t_burnout, BURNOUT_EXPECTED, abs_tol=BURNOUT_TOL)


def test_rk4_burnout_event_detected():
    """Same check for the hand-written fixed-step RK4 path (`method="rk4"`),
    which locates the burnout crossing by linear interpolation within the
    one step that straddles it (same approach as apogee/ground there).
    """
    p = Params(
        weight=Weight(m=0.5, I=0.05),
        lengths=Lengths(l1=0.3, l2=0.4),
        thrust=Thrust(motor_curve="placeholder.csv"),
    )
    s0 = State(x=0.0, z=0.0, vx=0.0, vz=0.0, theta=math.pi / 2, omega=0.0)

    result = run_sim(with_solver(p, method="rk4", dt=1e-3), s0)

    t_burnout = result.events["burnout"]
    assert t_burnout is not None
    assert math.isclose(t_burnout, BURNOUT_EXPECTED, abs_tol=BURNOUT_TOL)


def test_no_burnout_event_when_no_curve():
    """With no motor curve (`motor_curve=""`, thrust is zero throughout),
    thrust never goes from positive to negative, so the burnout event must
    never fire for either integrator.
    """
    p = Params(
        weight=Weight(m=0.5, I=0.05),
        lengths=Lengths(l1=0.3, l2=0.4),
        thrust=Thrust(motor_curve=""),
    )
    s0 = State(x=0.0, z=0.0, vx=0.0, vz=0.0, theta=math.pi / 2, omega=0.0)

    rk45 = run_sim(with_solver(p, t_max=5.0), s0)
    rk4 = run_sim(with_solver(p, method="rk4", t_max=5.0, dt=1e-3), s0)

    assert rk45.events["burnout"] is None
    assert rk4.events["burnout"] is None


# ---------------------------------------------------------------------
# Step 45 (Phase 2.8; architecture.md SS25.5): Result.params, the untouched
# apogee event, and the bit-for-bit regression under the default
# "parallel" gravity_direction.
# ---------------------------------------------------------------------


def test_result_params_is_p_on_both_integrator_paths():
    p = Params(
        weight=Weight(m=0.5, I=0.05),
        lengths=Lengths(l1=0.3, l2=0.4),
        thrust=Thrust(motor_curve="placeholder.csv"),
    )
    s0 = State(x=0.0, z=0.0, vx=0.0, vz=0.0, theta=math.pi / 2, omega=0.0)

    p_rk4 = with_solver(p, method="rk4", dt=1e-3)
    r_rk45 = run_sim(p, s0)
    r_rk4 = run_sim(p_rk4, s0)

    assert r_rk45.params is p
    assert r_rk4.params is p_rk4


def test_apogee_event_attributes_unchanged():
    """architecture.md SS25.8's hard line: `_apogee_event` stays
    `direction=1`, `terminal=False` -- Step 45 does not touch the event
    trigger, only the reported altitude value."""
    assert _apogee_event.direction == 1
    assert _apogee_event.terminal is False


# Tilted, curvature-exercising scenario (gravity_model="wgs84",
# atmosphere_model="isa" (default), aero_model="linearized",
# wind_model="analytic") under the default gravity_direction="parallel" --
# pinned final-state/event values captured from the pre-Step-45 code (the
# unedited repository, before sim/gravity.py/sim/flow.py/sim/atmosphere.py/
# sim/wind.py/sim/integrate.py were touched), proving the post-Step-45
# physics is bit-for-bit identical under the flat default (architecture.md
# SS25.6). x != 0 throughout, so a mistake in the flat branch of the new
# altitude_agl/altitude_msl call sites would show up here -- the vertical
# run.py scenario (x == 0 always) could not catch it.
_TILT_PARAMS = Params(
    weight=Weight(m=0.5, I=0.05),
    lengths=Lengths(l1=0.3, l2=0.4),
    thrust=Thrust(motor_curve="placeholder.csv"),
    aero=Aero(model="linearized", S=0.005, d_ref=0.08, C_A0=0.5, C_N_alpha=2.0, C_m_alpha=-0.5),
    gravity=Gravity(model="wgs84"),
    atmosphere=Atmosphere(model="isa"),
    wind=Wind(model="analytic", ref_ms=5.0, ref_h_m=10.0, shear_exp=0.143, dir_deg=45.0),
    site=Site(lat0_deg=50.0, azimuth_deg=90.0),
)
_TILT_S0 = State(x=0.0, z=0.0, vx=50.0, vz=0.0, theta=math.radians(80.0), omega=0.0)

_TILT_PINNED = {
    "RK45": dict(
        y_final=[634.8103836834275, -5.4817261840867104e-15, 59.61236937554152,
                 19.52923203571373, -0.3106550930107851, -0.2986216972287503, 0.0],
        t_final=5.393359857760246,
        events={"apogee": 2.6382969670047016, "ground": 5.393359857760246,
                "burnout": 1.9999999999955556},
    ),
    "rk4": dict(
        y_final=[634.8102578513177, 0.0, 59.61236364096141, 19.529231848850742,
                 -0.3106546467112906, -0.29862245176650026, 0.0],
        t_final=5.39335961920151,
        events={"apogee": 2.6382986765214778, "ground": 5.39335961920151,
                "burnout": 2.0009999999998906},
    ),
}

# Same scenario's aero/motor setup, but atmosphere_model/wind_model
# switched to tier 2 ("sounding"), the committed `example` case (LKPR),
# h0_m matching its elevation -- covers the tier-2 code path too
# (architecture.md SS25.9).
_TILT_SOUNDING_PARAMS = Params(
    weight=Weight(m=0.5, I=0.05),
    lengths=Lengths(l1=0.3, l2=0.4),
    thrust=Thrust(motor_curve="placeholder.csv"),
    aero=Aero(model="linearized", S=0.005, d_ref=0.08, C_A0=0.5, C_N_alpha=2.0, C_m_alpha=-0.5),
    atmosphere=Atmosphere(model="sounding"),
    wind=Wind(model="sounding"),
    soundings=Soundings(case="example"),
    site=Site(h0_m=380.0),
)

_TILT_SOUNDING_PINNED = {
    "RK45": dict(
        y_final=[787.754688433039, 4.003741782554471e-15, 48.82342057638281,
                 27.408071824539135, -0.5404909185805109, -0.13152735823982897, 0.0],
        t_final=7.384917372272603,
        events={"apogee": 3.4708868647803905, "ground": 7.384917372272603,
                "burnout": 1.9999999999955556},
    ),
    "rk4": dict(
        y_final=[787.7545563968736, 0.0, 48.82342798836863, 27.408066606348907,
                 -0.5404908148143166, -0.13153004089547823, 0.0],
        t_final=7.384916047480754,
        events={"apogee": 3.4708865903771247, "ground": 7.384916047480754,
                "burnout": 2.0009999999998906},
    ),
}


def test_tilted_run_bit_for_bit_under_parallel_both_integrators():
    """architecture.md SS25.9's headline regression check: a tilted
    (x != 0 throughout), every-altitude-consumer-exercising scenario
    (gravity_model="wgs84", atmosphere_model="isa", aero_model=
    "coefficients", wind_model="analytic"), under the default
    gravity_direction="parallel", reproduces the pre-Step-45 events/t/y
    bit-for-bit (`np.array_equal`), on both integrator paths."""
    p = _TILT_PARAMS

    r_rk45 = run_sim(p, _TILT_S0)
    pin = _TILT_PINNED["RK45"]
    assert np.array_equal(r_rk45.y[:, -1], np.array(pin["y_final"]))
    assert r_rk45.t[-1] == pin["t_final"]
    for key, val in pin["events"].items():
        assert r_rk45.events[key] == val

    r_rk4 = run_sim(with_solver(p, method="rk4", dt=1e-3), _TILT_S0)
    pin = _TILT_PINNED["rk4"]
    assert np.array_equal(r_rk4.y[:, -1], np.array(pin["y_final"]))
    assert r_rk4.t[-1] == pin["t_final"]
    for key, val in pin["events"].items():
        assert r_rk4.events[key] == val


def test_tilted_sounding_run_bit_for_bit_under_parallel_both_integrators():
    """Same regression, tier-2 atmosphere/wind (the committed `example`
    sounding case), covering the sounding call sites (architecture.md
    SS25.9's "repeat once with atmosphere_model=sounding + wind_model=
    sounding on the committed example case")."""
    p = _TILT_SOUNDING_PARAMS

    r_rk45 = run_sim(p, _TILT_S0)
    pin = _TILT_SOUNDING_PINNED["RK45"]
    assert np.array_equal(r_rk45.y[:, -1], np.array(pin["y_final"]))
    assert r_rk45.t[-1] == pin["t_final"]
    for key, val in pin["events"].items():
        assert r_rk45.events[key] == val

    r_rk4 = run_sim(with_solver(p, method="rk4", dt=1e-3), _TILT_S0)
    pin = _TILT_SOUNDING_PINNED["rk4"]
    assert np.array_equal(r_rk4.y[:, -1], np.array(pin["y_final"]))
    assert r_rk4.t[-1] == pin["t_final"]
    for key, val in pin["events"].items():
        assert r_rk4.events[key] == val
