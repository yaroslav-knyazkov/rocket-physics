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


# Index constants for the plain 6-vector the integrator sees, e.g.
# `dynamics.derivatives(t, y, p)` and event functions. Kept in sync with
# the field order of State above.
X, Z, VX, VZ, THETA, OMEGA = range(6)
