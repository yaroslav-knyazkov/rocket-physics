"""Tests for sim/control.py -- the feedback-control scaffold and the
apogee-targeting airbrake (architecture.md SS27.3; roadmap.md Phase 2.10
Step 49).

Physics sanity checks + a wiring regression, per the project's testing
philosophy -- no fixtures, no conftest.py, plain `assert` + `math.isclose`/
`numpy` comparisons. Same style precedent as tests/test_wind.py's
`_TURBULENCE_MODELS` dispatch tests and tests/test_dynamics.py's Step
47/48 rail/parachute off-switch tests.
"""

import math

import numpy as np

from sim import control, forces, thrust_curve
from sim.dynamics import derivatives
from sim.flow import flow_state
from sim.integrate import run_sim
from sim.params import Aero, Control, Lengths, Params, Thrust, Weight
from sim.state import State, OMEGA, VZ, Z

_MOTOR_CURVE = "placeholder.csv"  # data/motors/placeholder.csv

# Shared launch scenario: the module's own Step-8 cross-check scenario
# (also reused by the Step 47/48 rail/parachute off-switch tests), a
# vertical launch from rest under the placeholder motor curve with a
# constant body-axial drag. Reaches a real, well-separated apogee during
# an unpowered coast long enough to sample many points of (architecture.md
# SS27.3's "Check" list).
_LAUNCH_WEIGHT = Weight(m=0.5, I=0.05)
_LAUNCH_LENGTHS = Lengths(l1=0.3, l2=0.4)
_LAUNCH_THRUST = Thrust(motor_curve=_MOTOR_CURVE)
# Step 55 (architecture-28-rewrite.md SS28.5.4): "constant"'s C_x is now
# q-scaled (A_x = q*S*C_x), so S/d_ref are required for the "constant
# body-axial drag" this module's docstring describes to be anything but
# zero -- this scenario's own blast radius was missed by the Step 55
# ticket's original measurement (which counted only tests/test_forces.py,
# run.py and apps/), found by running this suite after the fix. Values
# match run.py's own placeholder scenario.
_LAUNCH_AERO = Aero(S=0.005, d_ref=0.08, C_x=0.5, C_z=0.0, C_m=0.0)


def _launch_params(**control_kw) -> Params:
    """The shared launch scenario (weight/lengths/thrust/aero groups) plus
    a `Control` group built from the airbrake kwargs passed by each test."""
    return Params(
        weight=_LAUNCH_WEIGHT, lengths=_LAUNCH_LENGTHS, thrust=_LAUNCH_THRUST,
        aero=_LAUNCH_AERO, control=Control(**control_kw),
    )


def _launch_state():
    return State(x=0.0, z=0.0, vx=0.0, vz=0.0, theta=math.pi / 2, omega=0.0)


# ----------------------------------------------------------------------
# "none" (the default) is the primary off switch
# ----------------------------------------------------------------------


def test_airbrake_deploy_fraction_is_zero_for_the_default_model():
    """`p.airbrake_model` defaults to `"none"`; `airbrake_deploy_fraction`
    must return exactly `0.0` for arbitrary `(t, y)` (architecture.md
    SS27.3) -- even states that would otherwise satisfy the "proportional"
    variant's activation gate.
    """
    p = Params(weight=Weight(m=0.5, I=0.05), lengths=Lengths(l1=0.3, l2=0.4))
    for t, y in [
        (0.0, np.zeros(6)),
        (12.0, np.array([100.0, -2000.0, 50.0, -80.0, math.pi / 2, 0.0])),
    ]:
        assert control.airbrake_deploy_fraction(t, y, p) == 0.0


def test_airbrake_none_leaves_derivatives_unaffected_by_other_airbrake_fields():
    """architecture.md SS27.3's first "Check" bullet: `airbrake_model =
    "none"` (the default) reproduces every prior step bit-for-bit --
    `derivatives` must be bit-for-bit identical regardless of
    `airbrake_kp`/`airbrake_target_apogee_m`/`airbrake_Cd`/
    `airbrake_S_max`, mirroring the "gated field is inert when off"
    property `test_earth_rotation_off_reproduces_derivatives_bit_for_bit`/
    `test_mass_model_off_reproduces_fixed_mass_bit_for_bit` already
    exercise for Step 36/37's own gates (tests/test_dynamics.py).
    """
    p_inert = _launch_params(airbrake_model="none")
    p_loaded = _launch_params(
        airbrake_model="none", airbrake_kp=5.0, airbrake_target_apogee_m=100.0,
        airbrake_Cd=2.0, airbrake_S_max=0.5,
    )
    # An unpowered, ascending state -- the window where "proportional"
    # would otherwise be active -- so this genuinely exercises the "none"
    # gate, not a state where the controller would be inert anyway.
    s = np.array(State(x=100.0, z=-2000.0, vx=50.0, vz=-80.0, theta=math.pi / 2, omega=0.0))

    dydt_inert = derivatives(10.0, s, p_inert)
    dydt_loaded = derivatives(10.0, s, p_loaded)
    assert np.array_equal(dydt_inert, dydt_loaded)


def test_airbrake_S_max_zero_is_an_independent_off_switch():
    """architecture.md SS27.3's second "Check" bullet: `airbrake_S_max =
    0.0` (also the default) is a second, independent off switch -- even
    with `airbrake_model = "proportional"` and a saturating gain/target
    that commands full deployment, `derivatives` stays bit-for-bit
    identical to the no-airbrake baseline when `S_max == 0.0`.
    """
    p_none = _launch_params(airbrake_model="none")
    p_prop_inert = _launch_params(
        airbrake_model="proportional", airbrake_kp=1000.0,  # saturating
        airbrake_target_apogee_m=0.0, airbrake_Cd=2.0, airbrake_S_max=0.0,
    )
    # Unpowered, ascending state: the activation gate is open, so this
    # genuinely exercises control.airbrake_deploy_fraction (confirmed
    # saturated below), not merely a branch that is gated off anyway.
    s = np.array(State(x=100.0, z=-2000.0, vx=50.0, vz=-80.0, theta=math.pi / 2, omega=0.0))
    assert control.airbrake_deploy_fraction(10.0, s, p_prop_inert) == 1.0  # saturated, not merely nonzero

    dydt_none = derivatives(10.0, s, p_none)
    dydt_prop_inert = derivatives(10.0, s, p_prop_inert)
    assert np.array_equal(dydt_none, dydt_prop_inert)


# ----------------------------------------------------------------------
# Directional regression: no closed form exists for a feedback-law-
# dependent trajectory (same standing as Step 25's aero-table checks)
# ----------------------------------------------------------------------


def test_proportional_airbrake_lowers_apogee_and_saturates_during_coast():
    """architecture.md SS27.3's third "Check" bullet: run the shared
    scenario once with `airbrake_model = "none"` and record its
    (unconstrained) apogee; run again with `"proportional"`, a large
    (saturating) `airbrake_kp`, and `airbrake_target_apogee_m` set well
    below the first run's apogee -- the second run's apogee must be lower,
    AND `airbrake_deploy_fraction` must reach exactly `1.0` (saturated, not
    merely "high") at some sampled point during the coast phase.
    """
    s0 = _launch_state()

    p_none = _launch_params(airbrake_model="none")
    r_none = run_sim(p_none, s0)
    apogee_t_none = r_none.events["apogee"]
    assert apogee_t_none is not None
    alt_none = -r_none.raw.sol(apogee_t_none)[Z]

    p_brake = _launch_params(
        airbrake_model="proportional", airbrake_kp=1.0,
        airbrake_target_apogee_m=alt_none - 1000.0,  # well below the unconstrained apogee
        airbrake_Cd=1.0, airbrake_S_max=0.05,
    )
    r_brake = run_sim(p_brake, s0)
    apogee_t_brake = r_brake.events["apogee"]
    burnout_t_brake = r_brake.events["burnout"]
    assert apogee_t_brake is not None and burnout_t_brake is not None
    alt_brake = -r_brake.raw.sol(apogee_t_brake)[Z]

    assert alt_brake < alt_none  # the brake did real work, not merely zero drag

    ts = np.linspace(burnout_t_brake + 0.01, apogee_t_brake - 0.01, 200)
    fracs = [control.airbrake_deploy_fraction(t, r_brake.raw.sol(t), p_brake) for t in ts]
    assert any(f == 1.0 for f in fracs)  # saturated at some sampled coast instant


def test_airbrake_deploy_fraction_is_zero_outside_the_activation_window():
    """architecture.md SS27.3's fourth "Check" bullet: `airbrake_deploy_
    fraction` is exactly `0.0` at every sample while `thrust > 0` (powered
    ascent) and at every sample once `y[VZ] >= 0` (past apogee) -- the
    activation-window gate actually gates. Uses the same saturating
    scenario as the test above (so the gate is proven against a
    controller that is demonstrably *not* inert elsewhere in the
    trajectory, not a controller that happens to never deploy at all).
    """
    s0 = _launch_state()
    p_brake = _launch_params(
        airbrake_model="proportional", airbrake_kp=1.0,
        airbrake_target_apogee_m=0.0,  # guarantees a positive error whenever active
        airbrake_Cd=1.0, airbrake_S_max=0.05,
    )
    r = run_sim(p_brake, s0)
    burnout_t = r.events["burnout"]
    apogee_t = r.events["apogee"]
    ground_t = r.events["ground"]
    assert burnout_t is not None and apogee_t is not None and ground_t is not None

    for t in np.linspace(0.0, burnout_t, 50):
        y = r.raw.sol(t)
        if thrust_curve.thrust(t, y, p_brake) > 0.0:
            assert control.airbrake_deploy_fraction(t, y, p_brake) == 0.0

    for t in np.linspace(apogee_t, ground_t, 50):
        y = r.raw.sol(t)
        if y[VZ] >= 0.0:
            assert control.airbrake_deploy_fraction(t, y, p_brake) == 0.0


def test_proportional_airbrake_takes_intermediate_values_for_a_modest_gain():
    """architecture.md SS27.3's fifth "Check" bullet: a small/modest gain
    (`airbrake_kp` small, `airbrake_target_apogee_m` close to the
    unconstrained apogee) makes `deploy_fraction` take on values strictly
    between `0` and `1` somewhere during the coast, not purely bang-bang
    -- confirming the law is genuinely proportional, not accidentally
    saturating everywhere.

    Step 55 (architecture-28-rewrite.md SS28.5.4): re-pinned. This
    scenario's unconstrained apogee used to be ~4609 m back when
    `_LAUNCH_AERO`'s `C_x` was an unscaled 0.5 N placeholder; with real,
    `q`-scaled drag it is ~666.5 m (verified numerically) -- `kp`/
    `target_apogee_m` below are re-chosen (not merely rescaled) so the
    deployment fraction genuinely lands strictly between 0 and 1 without
    saturating, confirmed by the same numerical search this project's
    other feedback-law-dependent scenarios use (no closed form exists
    here, same standing as Step 25's aero-table checks, this module's own
    docstring).
    """
    s0 = _launch_state()
    p = _launch_params(
        airbrake_model="proportional", airbrake_kp=0.0005,
        airbrake_target_apogee_m=650.0,  # close to, but below, the ~666.5 m unconstrained apogee
        airbrake_Cd=1.0, airbrake_S_max=0.05,
    )
    r = run_sim(p, s0)
    burnout_t = r.events["burnout"]
    apogee_t = r.events["apogee"]
    assert burnout_t is not None and apogee_t is not None

    ts = np.linspace(burnout_t + 0.01, apogee_t - 0.01, 500)
    fracs = [control.airbrake_deploy_fraction(t, r.raw.sol(t), p) for t in ts]

    assert any(0.0 < f < 1.0 for f in fracs)  # a genuine proportional region
    assert not any(f == 1.0 for f in fracs)   # this modest gain never saturates


# ----------------------------------------------------------------------
# Step 57 (architecture-28-rewrite.md SS28.6): the control-coefficient
# seam -- structure only, identity by default. No controller is written
# here; this proves a locally-registered, test-only dummy variant's
# delta actually reaches the four consumers the single choke point
# inside aero.coefficients exists to keep consistent -- the exact
# F2-style leak Step 55 closed, which this seam must not reopen.
# ----------------------------------------------------------------------

# A scenario with a nonzero q (so the coefficient deltas below produce a
# nonzero force/moment) and u_B = 0.0 (Lengths' default): with no lateral
# CoG offset, dynamics.py's M_aero = _cross_y(aA, aero_force) reduces to
# exactly `l1 * F_z` (aA = (-l1, 0.0); _cross_y(a, b) = -(a_x*b_z -
# a_z*b_x)), so an l1-only delta's effect on domega/dt is cleanly
# separable from the C_x/C_z/C_m/C_mq checks below, not entangled with
# them. `thrust=Thrust()` (motor_curve="") keeps thrust exactly 0.0, so
# M_thrust is unaffected by anything this test perturbs.
_SEAM_SCENARIO = dict(
    weight=Weight(m=0.5, I=0.05),
    lengths=Lengths(l1=0.3, l2=0.4),
    thrust=Thrust(),
    aero=Aero(model="constant", S=0.005, d_ref=0.08, C_x=0.5, C_z=0.3, C_m=0.1, c_mq=2.0),
)


def _seam_state() -> np.ndarray:
    return np.array(State(x=0.0, z=-500.0, vx=40.0, vz=-10.0, theta=math.pi / 2, omega=0.3))


def test_aero_coeff_delta_reaches_all_four_consumers():
    """A test-only `aero_coeff_delta` variant, registered locally into
    `control._AERO_COEFF_CONTROLLERS` the same way tests/test_wind.py's
    `test_none_model_full_trajectory_matches_pre_wind_stub_bit_for_bit`
    monkeypatches `flow._wind_inertial` (save nothing to restore here --
    the key is new, so the `finally` block just deletes it; no
    fixture/conftest precedent exists in this suite to extend instead,
    this module's own docstring: "no fixtures, no conftest.py").

    Perturbs all five `AeroCoeffs` fields by known amounts via
    `base._replace(...)` -- exactly the shape control.py's own docstring
    prescribes for a real controller -- and checks each of the four
    consumers moves by exactly the closed-form delta its own docstring
    formula predicts (forces.py's `aero_force_body`/`aero_moment_y`;
    dynamics.py's CoP arm, isolated with its own l1-only variant so it is
    not entangled with the C_x/C_z/C_m/C_mq checks).
    """
    dC_x, dC_z, dC_m, dC_mq, dl1 = 0.2, 0.15, 0.05, 1.0, 0.1

    def _delta_all(t, y, p, flow, base):
        return base._replace(
            C_x=base.C_x + dC_x, C_z=base.C_z + dC_z, C_m=base.C_m + dC_m,
            C_mq=base.C_mq + dC_mq, l1=base.l1 + dl1,
        )

    def _delta_l1_only(t, y, p, flow, base):
        return base._replace(l1=base.l1 + dl1)

    assert "test_s57_all" not in control._AERO_COEFF_CONTROLLERS
    assert "test_s57_l1_only" not in control._AERO_COEFF_CONTROLLERS
    control._AERO_COEFF_CONTROLLERS["test_s57_all"] = _delta_all
    control._AERO_COEFF_CONTROLLERS["test_s57_l1_only"] = _delta_l1_only
    try:
        p_none = Params(control=Control(aero_coeff_model="none"), **_SEAM_SCENARIO)
        p_all = Params(control=Control(aero_coeff_model="test_s57_all"), **_SEAM_SCENARIO)
        y = _seam_state()
        t = 10.0
        # flow_state does not read p.control at all, so computing it once
        # from p_none and reusing it for p_all is bit-for-bit identical to
        # recomputing it from p_all (same precedent as forces.py's/
        # dynamics.py's own single flow_state(t, y, p) call per RHS, Step 56).
        flow = flow_state(t, y, p_none)

        # (1)+(2) axial/normal force: A_x = q*S*C_x, A_z = q*S*C_z (no
        # airbrake term: airbrake_S_max = 0.0, the default), aero_force_body
        # returns (-A_x, -A_z).
        Fx_none, Fz_none = forces.aero_force_body(t, y, p_none, flow)
        Fx_all, Fz_all = forces.aero_force_body(t, y, p_all, flow)
        assert math.isclose(Fx_all - Fx_none, -flow.q * p_none.aero.S * dC_x, rel_tol=1e-9)
        assert math.isclose(Fz_all - Fz_none, -flow.q * p_none.aero.S * dC_z, rel_tol=1e-9)

        # (3) pitching moment + pitch damping: A_m = q*S*d_ref*C_m +
        # 0.25*rho*V*S*d_ref^2*omega*C_mq (sim/forces.py's aero_moment_y
        # docstring); aero_moment_y returns -A_m.
        M_none = forces.aero_moment_y(t, y, p_none, flow)
        M_all = forces.aero_moment_y(t, y, p_all, flow)
        expected_dM = -(
            flow.q * p_none.aero.S * p_none.aero.d_ref * dC_m
            + 0.25 * flow.air.rho * flow.V * p_none.aero.S * p_none.aero.d_ref**2 * y[OMEGA] * dC_mq
        )
        assert math.isclose(M_all - M_none, expected_dM, rel_tol=1e-9)

        # (4) dynamics.py's CoP arm l1, isolated: only l1 differs between
        # these two params (C_x/C_z/C_m/C_mq are the unperturbed base), so
        # the entire derivatives()[OMEGA] difference is l1's own
        # contribution via M_aero = l1*F_z, not entangled with (1)-(3).
        p_l1_only = Params(control=Control(aero_coeff_model="test_s57_l1_only"), **_SEAM_SCENARIO)
        dydt_none = derivatives(t, y, p_none)
        dydt_l1 = derivatives(t, y, p_l1_only)
        expected_d_omega_dot = (dl1 * Fz_none) / p_none.weight.I
        assert math.isclose(dydt_l1[OMEGA] - dydt_none[OMEGA], expected_d_omega_dot, rel_tol=1e-9)
        assert dydt_l1[OMEGA] != dydt_none[OMEGA]  # genuinely moved, not a no-op
    finally:
        del control._AERO_COEFF_CONTROLLERS["test_s57_all"]
        del control._AERO_COEFF_CONTROLLERS["test_s57_l1_only"]
