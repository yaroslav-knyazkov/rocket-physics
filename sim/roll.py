"""Step 109 (task-109-roll-reaction-wheel.md; other-dynamics.tex SSRoll and
the reaction wheel): the decoupled 2D roll degree of freedom about x_hat_r,
and the reaction wheel that can drive it.

Why a new module and not `sim/control.py` (task-109 SS109.4, D-134):

1. `sim/control.py` already owns the airbrake end-to-end (laws, triggers,
   the sampled-law registry, the actuator model). Roll is a second,
   independent dispatch; this project's own rule is "one group per module
   that owns a dispatch" (`params.py`'s docstring), and `Params.roll`'s
   owner is this module.
2. Boundary isolation: Step 108 (parallel) touches `sim/sensors.py` and
   `controllers/estimator.py`, widening `sim/control.py`'s measurement
   path. This module must not import `sim.control` or `sim.sampling`, and
   does not need to.
3. The laws here are memoryless -- pure functions of `(t, y, p)`,
   re-evaluated at every RHS call, exactly like `control._proportional_
   airbrake`. A roll law *with* memory would register a sampled channel in
   `sim.sampling._CHANNELS`; that is deliberately deferred (task-109
   SS109.13), which is what keeps `sim/sampling.py` out of this step's
   file list.

Physics (task-109 SS109.1, other-dynamics.tex sec:roll): two bodies sharing
one axis, the airframe and the wheel.

    dgamma/dt = omega_x                                           (eq. 1 / eq:roll_kinematics)
    I_x,a * domega_x/dt = L_x - tau_w                              (eq. 2 / eq:roll_airframe)
    I_w * domega_w/dt = tau_w                                      (eq. 3 / eq:roll_wheel)

with `I_x,a = I_x - I_w` the airframe-alone inertia, `L_x` the aerodynamic
roll moment (SS109.1.5 / eq:roll_aero_moment), and `tau_w` the motor torque
applied TO THE WHEEL (Newton's third law: the airframe gets `-tau_w`). The
wheel's rate is integrated ABSOLUTE (`omega_w`, inertial), not relative to
the airframe -- D-132: this makes eq. 3 a standalone scalar ODE with no
`domega_x/dt` on its own right-hand side. The relative rate
`omega_w - omega_x` (what an encoder reads) and the wheel's own momentum
`h_w = I_w*(omega_w - omega_x)` are cheap derived quantities
(`wheel_momentum`/`wheel_saturated` below).

Decoupling from the pitch channel is exact within the planar assumption,
not an approximation -- task-109 SS109.1.4 and `assumptions.tex`'s Roll
item prove it: Euler's `(I_x - I_t)*r*p` pitch cross-term vanishes
identically at the planar model's `r == 0`, and the wheel's own
gyroscopic reaction torque points along z_hat_r (yaw), which this 2D model
has no axis for. What that hides is stated there, not here.
"""

from typing import Callable

from sim.state import GAMMA, OMEGA_W, OMEGA_X


def aero_moment_x(t, y, p, flow) -> float:
    """`L_x`, the aerodynamic roll moment (task-109 SS109.1.5;
    other-dynamics.tex eq:roll_aero_moment):

        L_x = -q*S*d_ref*(C_l + C_l_p*omega_x_hat),  omega_x_hat = omega_x*d_ref/(2*v_rel)

    Written division-free, exactly as `forces.aero_moment_y` already does
    for `c_mq` (sim/forces.py's own precedent): a literal
    `omega_x*d_ref/(2*v_rel)` intermediate evaluates to `0.0*inf = nan` at
    `v_rel = 0`, which every unperturbed flight hits at apogee. The damping
    term expands to `q*d_ref*omega_x_hat = 0.25*rho*v_rel*omega_x*d_ref^2`.

    `C_l = C_l_p = 0.0` (both defaults) makes `L_x` exactly `0.0` for every
    state -- the torque-free reaction-wheel case (eq:roll_exchange) is the
    model's own default behaviour, because nobody has roll coefficients for
    this airframe (the paper's own `\\restodo`).
    """
    return -(
        flow.q * p.aero.S * p.aero.d_ref * p.aero.C_l
        + 0.25 * flow.air.rho * flow.V * p.aero.S * p.aero.d_ref**2 * y[OMEGA_X] * p.aero.C_l_p
    )


def _no_torque(t, y, p) -> float:
    """`law = "none"` (the default): the wheel is present but never commanded.
    Together with the `C_l = C_l_p = 0.0` aero default this makes the model's
    default behaviour exactly the torque-free momentum exchange of
    eq:roll_exchange driven by the initial condition alone -- which is the
    right default, because it is the only roll behaviour this project has
    data for."""
    return 0.0


def _rate_null(t, y, p) -> float:
    """`law = "rate_null"`: null the airframe roll rate. tau_w = kd*omega_x.

    SIGN: eq. (2) is I_x_a*eps_x = L_x - tau_w, so a tau_w with the SAME sign
    as omega_x decelerates the airframe. kd > 0 damps; kd < 0 is a sign error
    the model will happily diverge on (no validation, params.py SS7)."""
    return p.roll.kd * y[OMEGA_X]


def _angle_hold(t, y, p) -> float:
    """`law = "angle_hold"`: PD hold on the roll angle.
    tau_w = kp*(gamma - gamma_cmd) + kd*omega_x.

    SIGN: same reasoning as `_rate_null` -- a positive error (gamma above the
    command) needs a positive tau_w to produce a negative eps_x. kp, kd > 0.
    Memoryless by construction: no integral term, because an integral term
    needs the sampled/ZOH mode (sim/sampling.py) and that is out of this
    step's scope (task-109 SS109.13)."""
    return p.roll.kp * (y[GAMMA] - p.roll.gamma_cmd) + p.roll.kd * y[OMEGA_X]


# Module-private dispatch dict (same pattern as `control._AIRBRAKE_CONTROLLERS`).
_ROLL_LAWS: "dict[str, Callable]" = {"none": _no_torque, "rate_null": _rate_null, "angle_hold": _angle_hold}


def known_roll_models() -> "tuple[str, ...]":
    """The registered `p.roll.model` names. `sim.integrate.run_sim`'s eager-
    validation guard (task-109 SS109.7.2) calls this instead of hardcoding
    the set."""
    return ("none", "free", "wheel")


def known_roll_laws() -> "tuple[str, ...]":
    """The registered `p.roll.law` names -- same role as
    `known_roll_models()` above, read by `sim.integrate.run_sim`'s eager-
    validation guard."""
    return tuple(_ROLL_LAWS)


def airframe_inertia(p) -> float:
    """`I_x,a = I_x - I_w`, the airframe-alone axial inertia (task-109
    SS109.1.1). Never zero in a valid config: `run_sim` validates `I_x >
    I_w` eagerly (SS109.7.2) -- no second defensive guard here, a silent
    fallback would hide a config error in the one place it is cheapest to
    catch (SS109.4.4)."""
    return p.roll.I_x - p.roll.I_w


def wheel_torque(t, y, p, hold=None) -> float:
    """tau_w, the motor torque applied TO THE WHEEL about +x_hat_r, after both
    saturation limits (task-109 SS109.1.3).

    `hold` is accepted and ignored -- every law here is memoryless. The
    parameter exists so that adding a sampled roll channel later does not
    change this function's signature at its call site in sim/dynamics.py
    (the same reason `aero_moment_y` took `hold` before any law used it).
    """
    if p.roll.model != "wheel" or p.roll.I_w == 0.0:
        return 0.0                      # no wheel -> no reaction torque, exactly 0.0

    tau = _ROLL_LAWS[p.roll.law](t, y, p)

    # Torque limit, two-sided. `tau_max = inf` (the default) leaves `tau`
    # untouched -- min/max against inf is the identity, no branch needed.
    tau = max(-p.roll.tau_max, min(p.roll.tau_max, tau))

    # Speed limit, ONE-sided (SS109.1.3): at saturation the wheel can still be
    # braked back, only accelerated further is forbidden. A two-sided clamp
    # would lock the wheel at its limit for the rest of the flight.
    # `omega_w_max = inf` (the default) makes both comparisons False.
    omega_rel = y[OMEGA_W] - y[OMEGA_X]
    if omega_rel >= p.roll.omega_w_max and tau > 0.0:
        tau = 0.0
    elif omega_rel <= -p.roll.omega_w_max and tau < 0.0:
        tau = 0.0
    return tau


def wheel_momentum(y, p) -> float:
    """`h_w = I_w*(omega_w - omega_x)`, the wheel's momentum RELATIVE to the
    airframe (task-109 SS109.1.1/SS109.1.2) -- a derived quantity, not
    integrated state."""
    return p.roll.I_w * (y[OMEGA_W] - y[OMEGA_X])


def wheel_saturated(y, p) -> bool:
    """`|omega_w - omega_x| >= omega_w_max` -- whether the wheel has run out
    of relative-speed authority (task-109 SS109.1.3)."""
    return abs(y[OMEGA_W] - y[OMEGA_X]) >= p.roll.omega_w_max


def derivatives_roll(t, y, p, flow, hold=None):
    """(dgamma/dt, domega_x/dt, domega_w/dt) -- eqs. (1)-(3) of task-109 SS109.1.2.

    Called ONLY when `p.roll.model != "none"` (sim/dynamics.py's gate); the
    state vector is 10 wide there, so `y[GAMMA]`/`y[OMEGA_X]`/`y[OMEGA_W]` are
    in range. Never call it on a 7-wide vector.
    """
    L_x = aero_moment_x(t, y, p, flow)
    tau_w = wheel_torque(t, y, p, hold)
    d_omega_x = (L_x - tau_w) / airframe_inertia(p)
    # I_w == 0.0 is "no wheel": tau_w is already exactly 0.0 above, and the
    # wheel's own rate is held constant rather than dividing 0.0/0.0.
    d_omega_w = tau_w / p.roll.I_w if p.roll.I_w > 0.0 else 0.0
    return y[OMEGA_X], d_omega_x, d_omega_w
