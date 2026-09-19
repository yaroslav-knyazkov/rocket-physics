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
    g: float = 9.80665  # gravitational acceleration [m/s^2], now read as g0 by gravity.py

    # force magnitudes -- Phase 1 constants, Phase 2 model outputs
    T: float = 0.0    # thrust magnitude [N]
    A_x: float = 0.0  # axial aero force magnitude [N]
    A_z: float = 0.0  # normal aero force magnitude [N]
    A_m: float = 0.0  # aero pitching moment magnitude [N*m]

    # model selection (architecture.md SS12)
    gravity_model: str = "constant"     # constant | linear | radial | wgs84
    atmosphere_model: str = "isa"       # isa | sounding | field

    # launch site / Earth (architecture.md SS13, SS15, SS17)
    R_e:         float = 6371000.0  # mean Earth radius [m] (linear & radial gravity)
    lat0_deg:    float = 0.0   # geodetic latitude of the launch site [deg] (wgs84 gravity)
    lon0_deg:    float = 0.0   # geodetic longitude of the launch site [deg] (station projection, tier 3)
    h0_m:        float = 0.0   # launch site elevation above MSL [m]
    azimuth_deg: float = 90.0  # direction of +x, degrees clockwise from North
