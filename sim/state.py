"""Simulation state vector.

Frame convention: single NED-like inertial frame, z DOWN (see params.py /
architecture.md SS2). Angles in radians.
"""

from typing import NamedTuple

import numpy as np


class State(NamedTuple):
    x: float      # inertial downrange position [m]
    z: float      # inertial position, DOWN-positive [m]  (altitude = -z)
    vx: float     # inertial velocity x [m/s]
    vz: float     # inertial velocity z, down-positive [m/s]
    theta: float  # pitch, rad, positive nose-up, from horizontal
    omega: float  # pitch rate dtheta/dt [rad/s]
    # Step 36 (roadmap.md, main.tex SSModels > Mass and moment of inertia):
    # instantaneous rocket mass [kg], dm/dt = -T_ref(t)/(I_sp*g0). Defaults
    # to 0.0 -- harmless, since dynamics.derivatives only reads this
    # component when `p.m_d` (the mass-model on/off gate, params.py) is
    # set; every scenario that leaves the mass model off (the default)
    # keeps using the fixed `p.m`/`p.I` exactly as before and never looks
    # at this field, so existing `State(...)` call sites that don't pass
    # `m=` are unaffected.
    m: float = 0.0
    # Step 109 (task-109-roll-reaction-wheel.md SS109.2; other-dynamics.tex
    # SSRoll and the reaction wheel): the decoupled roll degree of freedom.
    # Defaulted, like `m`, so every existing `State(...)` call site is
    # unaffected. UNLIKE `m`, these three are NOT always part of the flat
    # vector the integrator sees: `to_vector` below trims them off whenever
    # `p.roll.model == "none"` (the default), because scipy's RK45 error norm
    # is an RMS over the state vector and its *length* therefore changes the
    # accepted step sizes -- a zero-derivative 10th component would move every
    # pinned number in the suite (task-109 SS109.2.1 has the measurement).
    gamma: float = 0.0    # roll angle about x_hat_r [rad], right-hand rule
    omega_x: float = 0.0  # airframe roll rate dgamma/dt [rad/s]
    omega_w: float = 0.0  # wheel ABSOLUTE roll rate [rad/s] (not relative -- SS109.1.2)


# Index constants for the plain state vector the integrator sees, e.g.
# `dynamics.derivatives(t, y, p)` and event functions. Kept in sync with
# the field order of State above.
X, Z, VX, VZ, THETA, OMEGA, M = range(7)
# Step 109: the roll block. These three indices are valid ONLY while
# `p.roll.model != "none"`; on a 7-wide vector they are out of range, which is
# deliberate -- an accidental read fails loudly instead of returning garbage.
GAMMA, OMEGA_X, OMEGA_W = 7, 8, 9

N_BASE = 7   # width with the roll model off (the default)
N_ROLL = 10  # width with the roll model on


def width(p) -> int:
    """Length of the flat state vector `p` produces. Two values only, and the
    gate is a single string comparison (task-109 SS109.2.2)."""
    return N_ROLL if p.roll.model != "none" else N_BASE


def to_vector(s: State, p) -> np.ndarray:
    """Flatten a `State` into the vector `solve_ivp`/`_run_rk4` integrate.

    With `p.roll.model == "none"` (the default) the three roll fields are
    TRIMMED OFF, so a non-zero `s.gamma`/`s.omega_x`/`s.omega_w` is silently
    ignored -- exactly the contract `s.m` already has when `p.weight.m_d is
    None` ("the integrator never looks at this field"). Bit-for-bit identical
    to the `np.array(s0, dtype=float)` it replaces in that case: `np.asarray`
    of the first seven fields, same dtype, same values.
    """
    return np.asarray(tuple(s)[:width(p)], dtype=float)
