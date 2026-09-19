"""Simulation parameters.

Units: strict SI throughout (kg, m, s, N, N*m). Angles are in radians
internally; degrees only ever appear at the edges (run.py inputs, plot
labels).

Frame convention (see architecture.md SS2): a single NED-like inertial
frame with z pointing DOWN. This makes main.tex's W = m*g*z_hat_g literally
true with g > 0. Altitude is -z; nothing in the physics ever refers to
"altitude" directly.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Params:
    """Every symbol from main.tex, as a constant (Phase 1)."""

    # inertia & geometry (main.tex SSGeometry)
    m: float   # mass [kg]
    I: float   # pitch moment of inertia about CoG a [kg*m^2]
    l1: float  # |Aa|, CoP -> CoG distance [m]
    l2: float  # |AB|, CoP -> thrust point distance [m]

    # environment
    g: float = 9.80665  # gravitational acceleration [m/s^2]

    # force magnitudes -- Phase 1 constants, Phase 2 model outputs
    T: float = 0.0    # thrust magnitude [N]
    A_x: float = 0.0  # axial aero force magnitude [N]
    A_z: float = 0.0  # normal aero force magnitude [N]
    A_m: float = 0.0  # aero pitching moment magnitude [N*m]
