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
"""

import numpy as np

# Hardcoded constant-thrust burn duration. There is no thrust-curve or
# burnout-event model yet (that arrives in Phase 2 / Step 11); this is the
# minimal "constant thrust for a fixed duration" needed to make the
# analytic apogee check in architecture.md/roadmap.md Step 2 computable at
# all. Lives here (rather than dynamics.py) because it gates `thrust_body`,
# the function that owns the cutoff behaviour.
T_BURN = 2.0  # [s]


def weight_inertial(t: float, s, p) -> np.ndarray:
    """W = m*g*z_hat_g, already in the inertial frame (main.tex SSForces)."""
    return np.array([0.0, p.m * p.g])


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
    """A_f = -A_x*x_hat_r - A_z*z_hat_r (main.tex SSForces), body frame."""
    return np.array([-p.A_x, -p.A_z])


def aero_moment_y(t: float, s, p) -> float:
    """A_m = -A_m*y_hat_r (main.tex SSMoments), scalar about y.

    Not used by dynamics.py yet -- theta/omega aren't integrated states
    until Step 6. Exposed now so that step just calls it.
    """
    return -p.A_m
