"""Forces and moments, each returned in its *natural* frame (architecture.md
SS4, "the model-swap seam"). Every function has the final signature
`f(t, s, p) -> ...` from day one, so Phase 2 only ever rewrites a function
*body* here -- call sites in dynamics.py never change.

Phase 1: every force is a constant magnitude from `Params`, taken straight
from main.tex SSForces / SSMoments:

    W   = m*g*z_hat_g                       (gravity frame == inertial here)
    T   = T*x_hat_r                         (body frame)
    A_f = -A_x*x_hat_r - A_z*z_hat_r        (body frame)
    A_m = -A_m*y_hat_r                      (body frame, scalar about y)

Step 9: `A_f` is generalised to `-A_x*u_hat - A_z*n_hat` (main.tex
SS"Forces", updated), driven by the actual relative wind / angle of attack
from sim/flow.py rather than the fixed body axes. `A_x`, `A_z` are still
plain `Params` constants -- dynamic-pressure-based coefficients arrive in
Steps 12-13/25.

Step 10: `weight_inertial` dispatches its magnitude through
sim/gravity.py's `g(t, y, p)` (main.tex SSModels > Gravity;
architecture.md SS12/SS13) instead of the fixed `p.g`, so the gravity
model is selected by `p.gravity_model` and defaults to "constant", which
reproduces Phase 1 bit-for-bit.
"""

import numpy as np

from sim import gravity
from sim.flow import flow_state

# Hardcoded constant-thrust burn duration. There is no thrust-curve or
# burnout-event model yet (that arrives in Phase 2 / Step 11); this is the
# minimal "constant thrust for a fixed duration" needed to make the
# analytic apogee check in architecture.md/roadmap.md Step 2 computable at
# all. Lives here (rather than dynamics.py) because it gates `thrust_body`,
# the function that owns the cutoff behaviour.
T_BURN = 2.0  # [s]


def weight_inertial(t: float, s, p) -> np.ndarray:
    """W = m*g*z_hat_g, already in the inertial frame (main.tex SSForces).

    `g` is the model-selected magnitude from sim/gravity.py
    (`p.gravity_model`), not the raw `p.g` constant -- see the gravity.py
    docstring for the three variants implemented at Step 10.
    """
    return np.array([0.0, p.m * gravity.g(t, s, p)])


def thrust_body(t: float, s, p) -> np.ndarray:
    """T = T*x_hat_r (main.tex SSForces), body frame.

    Constant magnitude `p.T` while `t < T_BURN`, zero after -- see the
    `T_BURN` docstring above for why this cutoff exists at all. Step 11
    replaces this body with a real (time, thrust) curve; the cutoff-by-time
    logic goes away then, not before.
    """
    thrust = p.T if t < T_BURN else 0.0
    return np.array([thrust, 0.0])


def aero_force_body(t: float, s, p) -> np.ndarray:
    """A_f = -A_x*u_hat - A_z*n_hat (main.tex SSForces, generalised), body
    frame. `u_hat`/`n_hat` come from the actual relative wind (sim/flow.py),
    not the fixed body axes, so drag correctly opposes the flight direction
    even when it does not coincide with the nose (e.g. tail-first descent).
    At alpha = 0 (nose-first into the relative wind), u_hat = (1, 0) and
    n_hat = (0, 1), so this reduces exactly to the Phase 1 `(-A_x, -A_z)`.

    Step 13: two regimes:
      * "constant": use the constant magnitudes p.A_x, p.A_z (Phase 1 behaviour)
      * "coefficients": compute from dynamic pressure and coefficients:
            A_x = q * S * C_A0
            A_z = q * S * C_N_alpha * alpha
    """
    flow = flow_state(t, s, p)
    if p.aero_model == "constant":
        A_x = p.A_x
        A_z = p.A_z
    elif p.aero_model == "coefficients":
        A_x = flow.q * p.S * p.C_A0
        A_z = flow.q * p.S * p.C_N_alpha * flow.alpha
    else:
        raise ValueError(f"Unknown aero_model: {p.aero_model}")
    return -A_x * flow.u_hat - A_z * flow.n_hat


def aero_moment_y(t: float, s, p) -> float:
    """A_m = -A_m*y_hat_r (main.tex SSMoments), scalar about y.

    Not used by dynamics.py yet -- theta/omega aren't integrated states
    until Step 6. Exposed now so that step just calls it.

    Step 13: two regimes:
      * "constant": use the constant magnitude p.A_m (Phase 1 behaviour)
      * "coefficients": compute from dynamic pressure and coefficients:
            A_m = q * S * d_ref * C_m_alpha * alpha
    """
    flow = flow_state(t, s, p)
    if p.aero_model == "constant":
        A_m = p.A_m
    elif p.aero_model == "coefficients":
        A_m = flow.q * p.S * p.d_ref * p.C_m_alpha * flow.alpha
    else:
        raise ValueError(f"Unknown aero_model: {p.aero_model}")
    return -A_m