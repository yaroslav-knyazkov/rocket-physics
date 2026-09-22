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

Step 9 originally generalised `A_f` to `-A_x*u_hat - A_z*n_hat` (rotating it
into the relative-wind frame), driven by the actual relative wind / angle
of attack from sim/flow.py. `A_x`, `A_z` were still plain `Params`
constants at that point -- dynamic-pressure-based coefficients arrived in
Steps 12-13/25.

Step 35 (Phase 2.5) reverted that rotation: `C_A`/`C_N` (Step 25) are
body-axis (axial/normal) coefficients, matching the CFD/wind-tunnel data
convention they are extracted from, so their own `alpha`-dependence already
accounts for the relative wind -- rotating the resulting force through
`u_hat`/`n_hat` a second time was double-applying it. `A_f` is therefore
`-A_x*x_hat_r - A_z*z_hat_r` again, unconditionally (main.tex SSModels >
Aerodynamics). `flow.u_hat`/`flow.n_hat` are still computed in flow.py and
still used -- just to get `V`, `alpha`, `q` into the coefficient lookup, not
to redirect the force.

Step 10: `weight_inertial` dispatches its magnitude through
sim/gravity.py's `g(t, y, p)` (main.tex SSModels > Gravity;
architecture.md SS12/SS13) instead of the fixed `p.g`, so the gravity
model is selected by `p.gravity_model` and defaults to "constant", which
reproduces Phase 1 bit-for-bit.

Step 14: `thrust_body` now uses the thrust curve from sim/thrust_curve.py,
replacing the hard-coded T_BURN constant-thrust model.

Step 25: the "coefficients" regime's `C_A`/`C_N`/`C_m` are no longer
inline `Params`-constant formulas -- they are delegated to sim/aero.py,
which is table-driven (`p.aero_table`) with the exact same constant
formulas as the fallback (architecture.md SS19). Bit-for-bit unchanged
when `p.aero_table == ""` (the default).
"""

import numpy as np

from sim import aero, gravity, thrust_curve
from sim.flow import flow_state


def weight_inertial(t: float, s, p) -> np.ndarray:
    """W = m*g*z_hat_g, already in the inertial frame (main.tex SSForces).

    `g` is the model-selected magnitude from sim/gravity.py
    (`p.gravity_model`), not the raw `p.g` constant -- see the gravity.py
    docstring for the three variants implemented at Step 10.
    """
    return np.array([0.0, p.m * gravity.g(t, s, p)])


def thrust_body(t: float, s, p) -> np.ndarray:
    """T = T*x_hat_r (main.tex SSForces), body frame.

    Now uses the thrust curve from sim/thrust_curve.py instead of a
    constant magnitude with hard-coded burn time. The thrust curve
    provides time-varying thrust and automatically cuts off when the
    curve ends (returns zero after the last defined point).
    """
    thrust = thrust_curve.thrust(t, s, p)
    return np.array([thrust, 0.0])


def aero_force_body(t: float, s, p) -> np.ndarray:
    """A_f = -A_x*x_hat_r - A_z*z_hat_r (main.tex SSModels > Aerodynamics),
    body frame, unconditionally -- the Phase 1 form, for every alpha, not
    just alpha = 0.

    `A_x`, `A_z` are body-axis (axial/normal) coefficients: `flow.alpha`
    (from the actual relative wind, sim/flow.py) already drives `C_A(alpha,
    M)`/`C_N(alpha, M)` below, so the force itself is *not* additionally
    rotated through `flow.u_hat`/`flow.n_hat` (the relative-wind frame) --
    doing so would double-apply the alpha-dependence, since those
    coefficients are extracted in body axes to begin with (Step 35, Phase
    2.5; see main.tex SSModels > Relative wind and angle of attack for what
    `u_hat`/`n_hat` are used for instead: V, alpha, q).

    Step 13: two regimes:
      * "constant": use the constant magnitudes p.A_x, p.A_z (Phase 1 behaviour)
      * "coefficients": compute from dynamic pressure and coefficients:
            A_x = q * S * C_A(alpha, M)
            A_z = q * S * C_N(alpha, M)

    Step 25: `C_A`/`C_N` come from sim/aero.py, which is table-driven
    (`p.aero_table`) with `p.C_A0`/`p.C_N_alpha*sin(alpha)` as the fallback
    (the `sin`, not raw `alpha`, is Phase 2.5 Step 35 -- see aero.py's
    module docstring) -- matching the pre-Step-25 formulas above to within
    that fallback's own small-angle error when no table is configured.
    """
    flow = flow_state(t, s, p)
    if p.aero_model == "constant":
        A_x = p.A_x
        A_z = p.A_z
    elif p.aero_model == "coefficients":
        A_x = flow.q * p.S * aero.C_A(flow.alpha, flow.M, p)
        A_z = flow.q * p.S * aero.C_N(flow.alpha, flow.M, p)
    else:
        raise ValueError(f"Unknown aero_model: {p.aero_model}")
    return np.array([-A_x, -A_z])


def aero_moment_y(t: float, s, p) -> float:
    """A_m = -A_m*y_hat_r (main.tex SSMoments), scalar about y.

    Not used by dynamics.py yet -- theta/omega aren't integrated states
    until Step 6. Exposed now so that step just calls it.

    Step 13: two regimes:
      * "constant": use the constant magnitude p.A_m (Phase 1 behaviour)
      * "coefficients": compute from dynamic pressure and coefficients:
            A_m = q * S * d_ref * C_m(alpha, M)

    Step 25: `C_m` comes from sim/aero.py, table-driven (`p.aero_table`)
    with `p.C_m_alpha*alpha` as the fallback -- identical numbers to the
    pre-Step-25 formula above when no table is configured.
    """
    flow = flow_state(t, s, p)
    if p.aero_model == "constant":
        A_m = p.A_m
    elif p.aero_model == "coefficients":
        A_m = flow.q * p.S * p.d_ref * aero.C_m(flow.alpha, flow.M, p)
    else:
        raise ValueError(f"Unknown aero_model: {p.aero_model}")
    return -A_m