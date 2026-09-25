"""Simulation state vector.

Frame convention: single NED-like inertial frame, z DOWN (see params.py /
architecture.md SS2). Angles in radians.
"""

from typing import NamedTuple


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

# Index constants for the plain state vector the integrator sees, e.g.
# `dynamics.derivatives(t, y, p)` and event functions. Kept in sync with
# the field order of State above.
X, Z, VX, VZ, THETA, OMEGA, M = range(7)
