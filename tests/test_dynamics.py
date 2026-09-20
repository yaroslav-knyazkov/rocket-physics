"""Cross-check that RK4 (sim/integrate.py's `method="rk4"`) and RK45
(`method="RK45"`, the default) agree on the flight of the same scenario
(roadmap.md Step 8).

This is the test that proves sim/dynamics.py is genuinely solver-agnostic:
both paths call `derivatives(t, y, p)` with no special-casing, and only
differ in how they step through time. It is a physics/numerics sanity
check, not a unit test of a single function -- per the project's testing
philosophy, no fixtures, no conftest.py, plain `assert` + `math.isclose`.
"""

import math

from sim.integrate import run_sim
from sim.params import Params
from sim.state import State, Z


def test_rk4_agrees_with_rk45_on_apogee_and_impact():
    """Same scenario as run.py's placeholder: the placeholder motor curve
    (Step 14) plus a constant axial drag, vertical launch from rest.

    Note (Step 14): this used to set `T=50.0` (Phase 1's constant-thrust
    magnitude). `motor_curve` now fully owns thrust (`forces.thrust_body`
    no longer reads `p.T` at all -- see sim/thrust_curve.py), so a `T=...`
    value alone would silently mean *zero* thrust for the whole flight,
    not "a different thrust profile". That degenerate scenario also makes
    this specific cross-check impractically slow: with nothing to
    overcome gravity, the flight runs the full default `t_max` and RK4's
    fixed dt=1e-4 grid turns into millions of steps in a pure-Python loop.
    Using the real placeholder curve keeps both the physics and the
    runtime representative of an actual flight.

    Tolerance rationale: RK4 here has no event location, only a fixed dt
    grid refined by linear interpolation across the one step that
    straddles each event (see `_run_rk4`'s docstring) -- so its event
    times and apogee altitude are grid-resolution-limited, not exact.
    Measured directly (this scenario, dt=1e-4 s): apogee time differs by
    ~3.2e-5 s, impact time by ~5.9e-5 s, apogee altitude by ~8.7e-3 m from
    RK45's values. The tolerances below (1e-3 s, 5e-2 m) sit comfortably
    above those measured differences while still being tight enough that
    an actual dynamics.py bug (a sign error, a missing term) -- which
    would show up as a difference many orders of magnitude larger, not a
    grid-resolution artifact -- would fail this test.
    """
    p = Params(m=0.5, I=0.05, l1=0.3, l2=0.4, motor_curve="placeholder.csv", A_x=0.5, A_z=0.0, A_m=0.0)
    s0 = State(x=0.0, z=0.0, vx=0.0, vz=0.0, theta=math.pi / 2, omega=0.0)

    rk45 = run_sim(p, s0, method="RK45")
    rk4 = run_sim(p, s0, method="rk4", dt=1e-4)

    apogee_rk45 = rk45.events["apogee"]
    apogee_rk4 = rk4.events["apogee"]
    impact_rk45 = rk45.events["ground"]
    impact_rk4 = rk4.events["ground"]

    assert apogee_rk45 is not None and apogee_rk4 is not None
    assert impact_rk45 is not None and impact_rk4 is not None

    alt_rk45 = -rk45.raw.sol(apogee_rk45)[Z]
    alt_rk4 = -rk4.raw.sol(apogee_rk4)[Z]

    assert math.isclose(apogee_rk4, apogee_rk45, abs_tol=1e-3)
    assert math.isclose(impact_rk4, impact_rk45, abs_tol=1e-3)
    assert math.isclose(alt_rk4, alt_rk45, abs_tol=5e-2)
