"""Tests for controllers/ -- the flight-software package (Phase 2.17
Milestone M3, architecture-35-paper-alignment.md SS35.4.4, task-107-
sampled-laws-registry.md): the drag-aware predicted-apogee closed form,
the estimator stub, and the two registered sampled laws
(`proportional_drag`/`pi_apogee`).

`import controllers` (below) is REQUIRED before `"proportional_drag"`/
`"pi_apogee"` are resolvable through `run_sim` -- see controllers/
__init__.py's own docstring. Reuses tests.test_control's shared launch
scenario (`_launch_params`/`_launch_state`/`_LAUNCH_WEIGHT`/`_LAUNCH_AERO`)
via a plain cross-test-file import, the same house precedent
tests/test_step114_review_fixes.py already uses for
tests.test_scenario_sweep.LARGE.
"""

import dataclasses
import math

import numpy as np
import pytest
from scipy.integrate import solve_ivp

import controllers  # noqa: F401  (import-time side effect: registers the two laws below)
from controllers import estimator, laws
from sim import control
from sim.integrate import run_sim
from sim.params import with_solver
from sim.state import Z
from tests.test_control import _launch_params, _launch_state, _LAUNCH_AERO, _LAUNCH_WEIGHT


# ----------------------------------------------------------------------
# SS107.3.4: the closed-form predictor -- a pure-math oracle, no run_sim
# ----------------------------------------------------------------------


def test_drag_aware_predictor_matches_numerically_integrated_constant_k_coast():
    """The closed form equals a numerically integrated, constant-k,
    drag-only vertical coast to < 0.1% relative error -- a correctness
    check on the ALGEBRA (model-proposals.md line 88), not an end-to-end
    physics validation against the real, altitude-varying ISA density
    (SS107.3.4, item 2: that would make the two comparison inputs
    physically different and could not hit 0.1% for anything but a
    sub-10-metre coast)."""
    h0, v0, m, g, k = 0.0, 100.0, 0.5, 9.80665, 0.0008  # [kg/m], an arbitrary positive k

    def rhs(t, state):
        h, v = state
        return [v, -g - (k / m) * v * v]

    def v_zero(t, state):
        return state[1]
    v_zero.terminal = True
    v_zero.direction = -1

    sol = solve_ivp(rhs, (0.0, 20.0), [h0, v0], events=v_zero, rtol=1e-12, atol=1e-12)
    h_apogee_numeric = sol.y_events[0][0][0]

    h_apogee_closed = laws.drag_aware_predicted_apogee(h0, v0, g, m, k)
    assert abs(h_apogee_closed - h_apogee_numeric) / h_apogee_numeric < 0.001


def test_drag_aware_predictor_reduces_to_vacuum_limit_at_k_zero():
    """`k <= 0.0` is the exact vacuum-limit formula `h + v**2/(2*g)` --
    computed directly (the `if k <= 0.0` branch), not the log formula
    evaluated at k=0 (which would be a 0/0 division)."""
    h0, v0, g = 0.0, 80.0, 9.80665
    assert laws.drag_aware_predicted_apogee(h0, v0, g, m=1.0, k=0.0) == h0 + v0**2 / (2.0 * g)


def test_drag_aware_predictor_continuous_near_k_zero():
    """No discontinuity at the `k <= 0.0` branch boundary -- evaluating
    just above zero agrees with evaluating exactly at zero to a tight
    RELATIVE tolerance (a light sanity check, not a second oracle test).
    A relative, not absolute, tolerance: `math.log1p`-style cancellation
    at a vanishingly small `k*v**2/(m*g)` argument costs a few more ULPs
    than an absolute 1e-6 would allow at this magnitude of `h_a` -- a
    floating-point artefact of the straight `math.log(1+x)` call, not a
    discontinuity in the formula itself."""
    h0, v0, g, m = 0.0, 80.0, 9.80665, 1.0
    at_zero = laws.drag_aware_predicted_apogee(h0, v0, g, m, k=0.0)
    just_above = laws.drag_aware_predicted_apogee(h0, v0, g, m, k=1e-9)
    assert just_above == pytest.approx(at_zero, rel=1e-5)


# ----------------------------------------------------------------------
# controllers/estimator.py -- stub only (Step 108 replaces the body)
# ----------------------------------------------------------------------


def test_estimator_step_first_call_returns_zero_velocity():
    h_hat, v_hat, state = estimator.step(0.0, 100.0, None)
    assert (h_hat, v_hat) == (100.0, 0.0)
    assert state == estimator.EstimatorState(t_prev=0.0, h_prev=100.0)


def test_estimator_step_backward_difference_on_a_linear_ramp():
    """Three consecutive calls on a noiseless linear climb (`h_baro =
    10*t`): `v_hat == 10.0` exactly from the second call onward -- the
    stub's own "exact under an ideal sensor" claim."""
    state = None
    v_hats = []
    for t in (0.0, 1.0, 2.0):
        _, v_hat, state = estimator.step(t, 10.0 * t, state)
        v_hats.append(v_hat)
    assert v_hats[0] == 0.0
    assert v_hats[1] == 10.0
    assert v_hats[2] == 10.0


# ----------------------------------------------------------------------
# controllers/estimator.py -- the real alpha_beta filter (Step 108,
# task-108-sensors-estimator.md SS108.6, tests 8-13)
# ----------------------------------------------------------------------


def test_alpha_beta_first_call_returns_zero_velocity():
    from sim.params import Params, Weight

    p = Params(weight=Weight(m=0.5, I=0.05))  # default Control: estimator_alpha/beta at their defaults
    h_hat, v_hat, state = estimator.step(0.0, 100.0, None, model="alpha_beta", p=p)
    assert (h_hat, v_hat) == (100.0, 0.0)
    assert state == estimator.AlphaBetaState(t_prev=0.0, h_hat=100.0, v_hat=0.0)


def test_alpha_beta_converges_on_a_noiseless_constant_velocity_ramp():
    """`h(t) = h0 + v0*t`, fed exactly every tick: after enough ticks for
    the filter's own geometric transient to decay, `h_hat`/`v_hat`
    converge to `h(t)`/`v0` within a tight tolerance."""
    from sim.params import Control, Params, Weight

    h0, v0, dt = 10.0, 5.0, 0.1
    p = Params(weight=Weight(m=0.5, I=0.05), control=Control(estimator_alpha=0.5, estimator_beta=0.1667))
    state = None
    n_ticks = 200  # (1-alpha)**n << tolerance well before this
    for n in range(n_ticks):
        t = n * dt
        h_true = h0 + v0 * t
        h_hat, v_hat, state = estimator.step(t, h_true, state, model="alpha_beta", p=p)
    t_final = (n_ticks - 1) * dt
    assert h_hat == pytest.approx(h0 + v0 * t_final, abs=1e-6)
    assert v_hat == pytest.approx(v0, abs=1e-6)


def test_alpha_beta_attenuates_noise_relative_to_the_raw_sigma():
    """Many ticks of a KNOWN constant altitude plus i.i.d. Gaussian noise
    (known sigma): the filtered `h_hat` series has a materially smaller
    sample std than the raw noise sigma (loose, empirical bound -- not a
    pinned steady-state-variance formula, §108.2's own disclosure)."""
    from sim.params import Control, Params, Weight

    rng = np.random.default_rng(12345)
    sigma, dt, h_true = 2.0, 0.1, 500.0
    p = Params(weight=Weight(m=0.5, I=0.05), control=Control(estimator_alpha=0.5, estimator_beta=0.1667))
    state = None
    h_hats = []
    for n in range(2000):
        t = n * dt
        h_meas = h_true + rng.normal(0.0, sigma)
        h_hat, v_hat, state = estimator.step(t, h_meas, state, model="alpha_beta", p=p)
        h_hats.append(h_hat)
    # Discard the initial transient (first 50 ticks).
    tail = np.array(h_hats[50:])
    assert np.std(tail) < 0.7 * sigma


def test_estimator_step_three_positional_args_is_bit_identical_to_pre_ticket_stub():
    """`estimator.step(t, h, prev)` (3 positional args, no `model=`) is
    bit-identical to Step 107's pre-ticket behaviour; an explicit
    `model="stub", p=None` call gives the exact same result."""
    state = None
    for t, h in ((0.0, 0.0), (1.0, 10.0), (2.0, 20.0)):
        bare = estimator.step(t, h, state)
        explicit = estimator.step(t, h, state, model="stub", p=None)
        assert bare == explicit
        _, _, state = bare


def test_estimator_step_unknown_model_raises_value_error():
    with pytest.raises(ValueError):
        estimator.step(0.0, 100.0, None, model="not_a_real_model")


def test_proportional_drag_and_pi_apogee_run_with_alpha_beta_estimator():
    """SS107.10-style "law called once per tick with `prev` state"
    smoke test, now with `estimator_model="alpha_beta"` set on the
    `Control` fixture -- both laws run without error and thread state
    across ticks."""
    p = _launch_params(
        airbrake_model="proportional_drag", airbrake_kp=0.001, airbrake_target_apogee_m=500.0,
        estimator_model="alpha_beta",
    )
    state = None
    for t, h in ((0.0, 0.0), (0.1, 1.0), (0.2, 2.0)):
        cmd, state = laws.proportional_drag(t, control.Measurement(h_baro=h), p, state)
    assert isinstance(state.est, estimator.AlphaBetaState)
    assert state.est.t_prev == 0.2

    p_pi = _launch_params(
        airbrake_model="pi_apogee", airbrake_kp=0.001, airbrake_ki=0.0005,
        airbrake_target_apogee_m=500.0, estimator_model="alpha_beta",
    )
    state_pi = None
    for t, h in ((0.0, 0.0), (0.1, 1.0), (0.2, 2.0)):
        cmd, state_pi = laws.pi_apogee(t, control.Measurement(h_baro=h), p_pi, state_pi)
    assert isinstance(state_pi.est, estimator.AlphaBetaState)


# ----------------------------------------------------------------------
# controllers/laws.py -- proportional_drag / pi_apogee, called directly
# (not through run_sim), so each law's own pure/stateful behaviour is
# tested independently of the registry/dispatch wiring tests/test_control.py
# already owns.
# ----------------------------------------------------------------------


def test_proportional_drag_zero_gain_keeps_cmd_at_zero_and_updates_state():
    """`airbrake_kp=0.0`: `cmd == 0.0` every call, but the estimator
    still advances -- "the estimator always runs when the law is called"
    design."""
    p = _launch_params(airbrake_model="proportional_drag", airbrake_kp=0.0, airbrake_target_apogee_m=500.0)
    state = None
    for t, h in ((0.0, 0.0), (0.1, 1.0), (0.2, 2.0)):
        cmd, state = laws.proportional_drag(t, control.Measurement(h_baro=h), p, state)
        assert cmd == 0.0
    assert state.est is not None
    assert state.est.t_prev == 0.2
    assert state.est.h_prev == 2.0


def test_proportional_drag_matches_proportional_structure_at_zero_k():
    """With the onboard drag model left at its defaults (`k == 0`),
    `proportional_drag`'s own predicted apogee reduces to the vacuum-limit
    formula; its `cmd` output matches a hand-computed
    `clip(kp*(h + v_hat**2/(2g) - target), 0, 1)` value."""
    kp, target, g0 = 0.0005, 100.0, 9.80665
    p = _launch_params(airbrake_model="proportional_drag", airbrake_kp=kp, airbrake_target_apogee_m=target)
    state = None
    _, state = laws.proportional_drag(0.0, control.Measurement(h_baro=100.0), p, state)
    cmd1, state = laws.proportional_drag(1.0, control.Measurement(h_baro=110.0), p, state)

    v_hat = 10.0  # (110.0 - 100.0) / 1.0
    h_a = 110.0 + v_hat**2 / (2.0 * g0)
    expected = float(np.clip(kp * (h_a - target), 0.0, 1.0))
    assert cmd1 == pytest.approx(expected, rel=1e-12)


def test_pi_apogee_integral_accumulates_error_over_dt_and_resets_at_first_tick():
    """A constant `h_baro` (so `v_hat == 0.0` and `h_a` stays constant,
    isolating the integral term from the estimator): `integral` grows by
    `error*dt` each tick, with `0.0` contribution at the very first call
    (`dt == 0.0` there)."""
    # target < h_a (== h_baro == 0.0 here) so error stays POSITIVE throughout --
    # a negative error at cmd == 0.0 would trip the anti-windup's own
    # saturated_low branch (cmd <= 0.0 and error < 0.0) and freeze the
    # integral at 0.0 for the wrong reason (coincidental zero gain, not a
    # genuine low-rail saturation); this test isolates plain accumulation.
    ki, target = 0.001, -50.0
    p = _launch_params(airbrake_model="pi_apogee", airbrake_kp=0.0, airbrake_ki=ki, airbrake_target_apogee_m=target)
    state = None
    integrals = []
    for t_k in (0.0, 1.0, 2.0):
        _, state = laws.pi_apogee(t_k, control.Measurement(h_baro=0.0), p, state)
        integrals.append(state.integral)

    error = 0.0 - target  # h_a == h_baro == 0.0 (v_hat == 0.0 throughout, k == 0)
    assert integrals[0] == 0.0  # first tick: dt == 0.0, no contribution
    assert integrals[1] == pytest.approx(error * 1.0)
    assert integrals[2] == pytest.approx(integrals[1] + error * 1.0)


def test_pi_apogee_anti_windup_freezes_integral_while_saturated_in_the_same_direction():
    """A large, sustained positive error saturates `cmd` at `1.0`;
    `integral` stops growing once saturated (two consecutive post-
    saturation values are equal), then genuinely resumes moving again
    once `error` is driven negative (desaturating the INTEGRATION, even
    though `cmd` itself may still read `1.0` for one more tick while the
    integral drains -- the anti-windup condition gates on `error`'s own
    sign, not on `cmd` having visibly come off its rail yet)."""
    ki = 10.0
    target = -100.0  # error = h_a - target = 0.0 - (-100.0) = 100.0 while h_baro == 0.0
    p = _launch_params(airbrake_model="pi_apogee", airbrake_kp=0.0, airbrake_ki=ki, airbrake_target_apogee_m=target)
    state = None
    integrals = []
    cmd = None
    for t_k in (0.0, 1.0, 2.0, 3.0):
        cmd, state = laws.pi_apogee(t_k, control.Measurement(h_baro=0.0), p, state)
        integrals.append(state.integral)
    assert cmd == 1.0  # genuinely saturated
    assert integrals[-1] == integrals[-2]  # frozen across two consecutive saturated ticks

    frozen = integrals[-1]
    p_reversed = dataclasses.replace(p, control=dataclasses.replace(p.control, airbrake_target_apogee_m=1.0e6))
    _, state = laws.pi_apogee(4.0, control.Measurement(h_baro=0.0), p_reversed, state)
    assert state.integral != frozen  # integration resumed once error flipped sign


# ----------------------------------------------------------------------
# Integration-level: run_sim with a registered sampled law
# ----------------------------------------------------------------------


def test_sampled_law_state_resets_between_independent_run_sim_calls():
    """The SAME scenario run twice (`airbrake_model="pi_apogee"`, two
    separate `run_sim(p, s0)` calls, fresh `p` each time) produces
    IDENTICAL apogee results -- the direct proof that no module-level
    mutable default leaks state between independent runs."""
    s0 = _launch_state()

    def _make_params():
        p = _launch_params(
            airbrake_model="pi_apogee", airbrake_kp=0.001, airbrake_ki=0.0005,
            airbrake_target_apogee_m=500.0, airbrake_Cd=1.0, airbrake_S_max=0.05,
            onboard_mass=_LAUNCH_WEIGHT.m, onboard_CdA0=_LAUNCH_AERO.S * _LAUNCH_AERO.C_x,
        )
        return with_solver(p, method="rk4", sample_rate_hz=20.0)

    r1 = run_sim(_make_params(), s0)
    r2 = run_sim(_make_params(), s0)
    apogee_t1, apogee_t2 = r1.events["apogee"], r2.events["apogee"]
    assert apogee_t1 is not None and apogee_t2 is not None
    alt1 = -r1.raw.sol(apogee_t1)[Z]
    alt2 = -r2.raw.sol(apogee_t2)[Z]
    assert alt1 == alt2


def test_proportional_drag_open_loop_sanity_ideal_sensor_ideal_actuator():
    """Roadmap acceptance bullet: with an ideal sensor (`_ideal_
    measurement`) and an ideal actuator (the default), `proportional_
    drag` lowers the apogee below the unconstrained ("none") baseline and
    lands within a loosely-bounded distance of the target -- "the
    controller's own steady-state error", not an exact hit (same style as
    `test_proportional_airbrake_lowers_apogee_and_saturates_during_coast`'s
    own loose assertions)."""
    s0 = _launch_state()
    p_none = _launch_params(airbrake_model="none")
    r_none = run_sim(p_none, s0)
    apogee_t_none = r_none.events["apogee"]
    assert apogee_t_none is not None
    alt_none = -r_none.raw.sol(apogee_t_none)[Z]

    target = 500.0  # well below alt_none (~666.5 m)
    p = with_solver(
        _launch_params(
            airbrake_model="proportional_drag", airbrake_kp=0.001,
            airbrake_target_apogee_m=target, airbrake_Cd=1.0, airbrake_S_max=0.05,
            onboard_mass=_LAUNCH_WEIGHT.m, onboard_CdA0=_LAUNCH_AERO.S * _LAUNCH_AERO.C_x,
            onboard_rho0=1.225,
        ),
        method="rk4", sample_rate_hz=20.0,
    )
    r = run_sim(p, s0)
    apogee_t = r.events["apogee"]
    assert apogee_t is not None
    alt = -r.raw.sol(apogee_t)[Z]

    assert alt < alt_none  # the controller did real work
    assert abs(alt - target) < 50.0  # loosely bounded: the P-only steady-state error, not an exact hit


def test_pi_apogee_open_loop_sanity_reduces_steady_state_error_vs_proportional_drag():
    """Same scenario, same `kp`, `pi_apogee` adds a nonzero `airbrake_ki`:
    its FINAL apogee error (vs target) is smaller in MAGNITUDE than
    `proportional_drag`'s own -- the textbook "integral action removes
    P-only steady-state error" property, a comparative (not absolute)
    assertion so it does not depend on hand-tuned gains hitting an exact
    number."""
    s0 = _launch_state()
    kp, target = 0.001, 500.0
    common = dict(
        airbrake_kp=kp, airbrake_target_apogee_m=target, airbrake_Cd=1.0, airbrake_S_max=0.05,
        onboard_mass=_LAUNCH_WEIGHT.m, onboard_CdA0=_LAUNCH_AERO.S * _LAUNCH_AERO.C_x, onboard_rho0=1.225,
    )

    p_drag = with_solver(
        _launch_params(airbrake_model="proportional_drag", **common), method="rk4", sample_rate_hz=20.0,
    )
    p_pi = with_solver(
        _launch_params(airbrake_model="pi_apogee", airbrake_ki=0.0005, **common), method="rk4", sample_rate_hz=20.0,
    )

    r_drag = run_sim(p_drag, s0)
    r_pi = run_sim(p_pi, s0)
    t_drag, t_pi = r_drag.events["apogee"], r_pi.events["apogee"]
    assert t_drag is not None and t_pi is not None
    alt_drag = -r_drag.raw.sol(t_drag)[Z]
    alt_pi = -r_pi.raw.sol(t_pi)[Z]

    err_drag = abs(alt_drag - target)
    err_pi = abs(alt_pi - target)
    assert err_pi < err_drag


def test_full_traceability_comparison_table():
    """Roadmap acceptance artifact (§107.10 test 22): apogee for
    none/full/proportional/proportional_drag/pi_apogee on the nominal
    demo flight, printed as a simple comparison table and asserted into
    the one ordering the roadmap names: `none`'s apogee is the highest of
    the five (every controlled variant does real work)."""
    s0 = _launch_state()

    def _apogee(p):
        r = run_sim(p, s0)
        t = r.events["apogee"]
        assert t is not None
        return -r.raw.sol(t)[Z]

    target = 500.0
    rows = {
        "none": _apogee(_launch_params(airbrake_model="none")),
        "full": _apogee(_launch_params(
            airbrake_model="full", airbrake_trigger="after_burnout", airbrake_Cd=1.0, airbrake_S_max=0.05,
        )),
        "proportional": _apogee(_launch_params(
            airbrake_model="proportional", airbrake_kp=0.0003, airbrake_target_apogee_m=target,
            airbrake_Cd=1.0, airbrake_S_max=0.05,
        )),
        "proportional_drag": _apogee(with_solver(
            _launch_params(
                airbrake_model="proportional_drag", airbrake_kp=0.001, airbrake_target_apogee_m=target,
                airbrake_Cd=1.0, airbrake_S_max=0.05, onboard_mass=_LAUNCH_WEIGHT.m,
                onboard_CdA0=_LAUNCH_AERO.S * _LAUNCH_AERO.C_x, onboard_rho0=1.225,
            ),
            method="rk4", sample_rate_hz=20.0,
        )),
        "pi_apogee": _apogee(with_solver(
            _launch_params(
                airbrake_model="pi_apogee", airbrake_kp=0.001, airbrake_ki=0.0005,
                airbrake_target_apogee_m=target, airbrake_Cd=1.0, airbrake_S_max=0.05,
                onboard_mass=_LAUNCH_WEIGHT.m, onboard_CdA0=_LAUNCH_AERO.S * _LAUNCH_AERO.C_x, onboard_rho0=1.225,
            ),
            method="rk4", sample_rate_hz=20.0,
        )),
    }

    print("\nStep 107 comparison table (nominal demo flight, apogee in m):")
    for name, alt in rows.items():
        print(f"  {name:<18s} {alt:9.3f}")

    for name, alt in rows.items():
        if name != "none":
            assert alt < rows["none"]
