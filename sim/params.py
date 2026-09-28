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
from typing import Optional


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

    # Step 25: aero coefficients as functions of (alpha, M) (architecture.md
    # SS19; sim/aero.py). "" = no table; the constants above (and the
    # constant p.l1 CoP-to-CoG distance) are used as-is, reproducing every
    # pre-Step-25 "coefficients" result bit-for-bit.
    aero_table: str = ""  # file under data/aero/; "" = use the constants above

    # model selection (architecture.md SS12)
    gravity_model: str = "constant"     # constant | radial | wgs84
    atmosphere_model: str = "isa"       # isa | sounding | field

    # Step 38: non-parallel gravity direction (main.tex SSModels > Gravity >
    # Direction; architecture.md SS23.1). Orthogonal to `gravity_model`
    # above -- that dispatch is the *magnitude*, this one is the
    # *direction*, and any magnitude may combine with any direction.
    # "parallel" (the default) is today's fixed z_hat_g = (0, 1): bit-for-
    # bit every prior step. "radial" rotates the local vertical with
    # downrange distance (main.tex eq:zhat_g_rotated), phi = x/R_e.
    # Step 41 (Phase 2.7; architecture.md SS24.1) adds "elliptical": the
    # WGS84 ellipsoid normal via its osculating sphere in the flight-plane
    # azimuth, phi = x/R_chi(lat0_deg, azimuth_deg) -- reuses those two
    # existing fields (the launch site's one latitude/heading), no new
    # `Params` fields.
    gravity_direction: str = "parallel"  # parallel | radial | elliptical

    # launch site / Earth (architecture.md SS13, SS15, SS17)
    R_e:         float = 6371000.0  # mean Earth radius [m] (radial gravity)
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

    # Step 36: variable mass -- CoG and moment-of-inertia travel (main.tex
    # SSModels > Mass and moment of inertia). `m_d` is the single on/off
    # gate, the same "unset sentinel disables the new model" convention as
    # `aero_table`/`motor_curve` (""), `wind_model` ("none"): `None` (the
    # default) reproduces every prior step bit-for-bit -- `m` stays fixed
    # at `p.m`, `I` stays fixed at `p.I`, `state.M` is carried along
    # unused. Setting `m_d` switches on the two-lumped-mass model
    # (dry structure at `l_d`, remaining propellant at `l_p`): `m` becomes
    # the integrated mass state, `dm/dt = -T_ref(t)/(I_sp*g0)`, and
    # `l_B(t)`, `I(t)` are recomputed every RHS call from it
    # (dynamics.py). `p.m` is then only the *initial* (wet) mass used to
    # seed `state.m` -- not read by the moment/translational equations
    # anymore.
    m_d: Optional[float] = None  # dry (burnout) mass [kg]; None = mass model off
    l_d: float = 0.0   # dry structure's centroid, distance from the nose [m]
    l_p: float = 0.0   # propellant centroid, distance from the nose [m] (main.tex's grain-geometry \todo placeholder: held constant)
    I_d: float = 0.0   # dry structure's own moment of inertia about l_d [kg*m^2]
    I_sp: float = 0.0  # specific impulse [s], for dm/dt = -T_ref(t)/(I_sp*g0)

    # Step 37: non-inertial (Coriolis) frame correction (main.tex SSModels >
    # Non-inertial frame corrections; sim/rotation.py). Same "unset =
    # bit-for-bit reproduces every prior step" gate convention as
    # `m_d`/`aero_table`/`wind_model`: `False` (the default) means
    # dynamics.py never calls sim.rotation.coriolis_inplane at all. `True`
    # adds the in-plane Coriolis acceleration only -- the residual
    # centrifugal term and the out-of-plane Coriolis component are
    # deliberately not folded into the physics (see sim/rotation.py's
    # module docstring for why); `lat0_deg`/`azimuth_deg` above (already
    # used by gravity.py's WGS84 model and wind.py's ENU projection) are
    # reused as-is -- no new parameter beyond this one flag.
    earth_rotation: bool = False

    # Step 39: thrust-axis misalignment (main.tex SSForces eq:thrust_vector;
    # architecture.md SS23.2). Same "unset = bit-for-bit reproduces every
    # prior step" convention as `A_e`/`aero_table`/`wind_model`/`m_d`: 0.0
    # (the default) makes `thrust_body` return exactly `(T, 0.0)`, since
    # `np.cos(0.0) == 1.0` and `np.sin(0.0) == 0.0` bitwise. A nonzero value
    # is a fixed, small (manufacturing-grade, ~0.1-1.0 deg) nozzle cant, not
    # a commanded gimbal angle -- there is no control law here.
    thrust_misalign_deg: float = 0.0  # fixed nozzle cant delta [deg], + toward +z_hat_r

    # Step 40: humid-air density -- virtual-temperature correction (main.tex
    # SSModels > Atmosphere > Density; architecture.md SS23.3). Same "unset =
    # bit-for-bit reproduces every prior step" convention as `earth_rotation`/
    # `m_d`/`wind_model`: `False` (the default) means `_sounding_air_state`/
    # `_field_air_state` never even evaluate `moist_density`, `rho` stays the
    # dry `p/(R_d*T)` from `sim.soundings.interp_altitude`. `True` applies
    # the correction wherever the sounding/field data has a finite dewpoint
    # (`Td_K` column); with no dewpoint data the fallback is dry air, level
    # by level, so the flag is safe to leave on. Tier "isa" is never
    # affected -- the ISA is dry air by definition (architecture.md SS14's
    # `g_isa` argument, reused here).
    humid_air: bool = False