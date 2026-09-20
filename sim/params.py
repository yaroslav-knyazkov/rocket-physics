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

    # Step 13: aerodynamic model parameters
    S: float = 0.0      # reference area [m^2]
    d_ref: float = 0.0  # reference diameter [m]
    l_ref: float = 0.0  # reference length [m] (for Reynolds number)
    C_A0: float = 0.0   # axial force coefficient at zero angle of attack
    C_N_alpha: float = 0.0  # normal force coefficient slope [1/rad]
    C_m_alpha: float = 0.0  # pitching moment coefficient slope [1/rad]
    aero_model: str = "constant"  # "constant" or "coefficients"

    # model selection (architecture.md SS12)
    gravity_model: str = "constant"     # constant | linear | radial | wgs84
    atmosphere_model: str = "isa"       # isa | sounding | field

    # launch site / Earth (architecture.md SS13, SS15, SS17)
    R_e:         float = 6371000.0  # mean Earth radius [m] (linear & radial gravity)
    lat0_deg:    float = 0.0   # geodetic latitude of the launch site [deg] (wgs84 gravity)
    lon0_deg:    float = 0.0   # geodetic longitude of the launch site [deg] (station projection, tier 3)
    h0_m:        float = 0.0   # launch site elevation above MSL [m]
    azimuth_deg: float = 90.0  # direction of +x, degrees clockwise from North

    # Step 18: atmosphere/wind tier 2/3 sounding data (architecture.md SS17)
    sounding_case: str = ""  # case folder under data/soundings/; "" = unused unless atmosphere_model/wind_model select "sounding"/"field"

    # Step 19: horizontal (tier 3) station combination (architecture.md SS17)
    horizontal_interp: str = "idw"     # idw | rbf -- station combination method
    grid_top_m: float = 30000.0        # common altitude grid for tier-3 resampling [m MSL]
    grid_step_m: float = 100.0         # grid spacing [m]
    idw_epsilon_m: float = 500.0       # IDW singularity-avoidance term [m]

    # thrust (architecture.md SS19)
    motor_curve: str = ""  # file under data/motors/; "" = no curve, zero thrust

    # Step 16: altitude pressure correction on thrust (architecture.md SS19)
    A_e: float = 0.0        # nozzle exit area [m^2]; 0.0 = correction is inert
    p_ref: float = 101325.0  # ambient pressure the curve was measured at [Pa]

    # Step 21: wind tier 1, analytic model (architecture.md SS16, SS18)
    wind_model: str = "none"    # none | analytic | sounding | field
    wind_ref_ms: float = 0.0    # reference wind speed W_ref at wind_ref_h_m [m/s]
    wind_dir_deg: float = 0.0   # meteorological wind direction (from North, clockwise) [deg]
    wind_ref_h_m: float = 10.0  # reference height for wind_ref_ms / the shear power law [m]
    wind_shear_exp: float = 0.143  # power-law shear exponent, ~= 1/7
    gust_sigma: float = 0.0     # gust perturbation scale [m/s]; 0.0 = gusts off entirely
    gust_seed: int = 0          # RNG seed for the frozen gust realization