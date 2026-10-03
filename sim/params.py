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
    # Step 46: Dryden turbulence (MIL-F-8785C / MIL-HDBK-1797) for tier-1
    # gusts (architecture.md SS26; latex/research/dryden_turbulence_model.md).
    # Same "unset = bit-for-bit reproduces every prior step" gate convention
    # as `wind_model`/`aero_model`: "none" (the default) means wind.py never
    # builds a realization, never touches the RNG, and `_analytic_wind`
    # returns exactly the mean-profile decomposition. Orthogonal to
    # `wind_model` in the same sense `gravity_direction` is orthogonal to
    # `gravity_model` (architecture.md SS23.1): a second dispatch inside one
    # module, not a product of names -- and the seam a von Karman variant
    # would slot into later with no other change (SS26.13).
    # TIER 1 ONLY. Tiers 2/3 ("sounding"/"field") ignore it entirely, exactly
    # as they ignore today's gusts (SS26.10).
    turbulence_model: str = "none"           # none | dryden

    # Isotropic turbulence intensity above 2000 ft AGL [m/s]. MIL-F-8785C
    # gives no closed form here -- only a probability-of-exceedance chart --
    # so this is set by the user per scenario (the user's own decision, see
    # the research note SS5), not looked up and not a light/moderate/severe
    # preset. 0.0 means "no turbulence above 2000 ft AGL", which also tapers
    # the 1000-2000 ft transition band to zero; it is a legitimate setting,
    # not an error, and the low-altitude band is still driven by W20 (SS26.5).
    turbulence_sigma_high_ms: float = 0.0

    # The single constant airspeed `V` used for the Taylor frozen-turbulence
    # conversion `omega = V*Omega`, for the whole flight [m/s]. A DELIBERATE
    # SIMPLIFICATION with a documented limitation (architecture.md SS26.9):
    # this rocket's true airspeed spans 0 to supersonic, and a realization
    # that tracked it would make the solver's RHS a non-function of its own
    # arguments (SS26.8). Must be > 0 when turbulence_model != "none"; the
    # default is a representative mid-flight airspeed for a small sounding
    # rocket, to be set per scenario, NOT a value with any authority.
    turbulence_ref_speed_ms: float = 100.0

    # RNG seed for the frozen phase draw (architecture.md SS26.8). Renamed
    # from Step 21's `gust_seed` so the family reads as one group; the
    # quantity and its role are unchanged.
    turbulence_seed: int = 0

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

    # Step 43: lateral (off-axis) offsets of the CoG (B) and the thrust point (C)
    # from the body axis, measured along +z_hat_r (towards the belly), metres.
    # rocket-2d.tex SSGeometry: AB = -l_B*x_hat_r - u_B*z_hat_r, likewise AC with
    # u_C; u_D == 0 by definition. As-built manufacturing quantities to be swept,
    # not functions of the flight state -- the same standing as
    # thrust_misalign_deg. 0.0 (the default) recovers the on-axis geometry
    # bit-for-bit.
    u_B: float = 0.0   # lateral offset of the centre of gravity [m]
    u_C: float = 0.0   # lateral offset of the thrust application point [m]

    # Step 44: pitch-damping derivative (analysis.tex SSDynamic stability;
    # architecture.md SS24.4). Scaffold only -- 0.0 (the default) makes the
    # damping term exactly zero, bit-for-bit every prior step, with no separate
    # on/off flag (the A_e/thrust_misalign_deg pattern). SIGN: positive c_mq is
    # DAMPING here, because positive C_m is a nose-DOWN moment in this
    # document's convention -- the same flip that makes c_m_alpha > 0 the
    # statically stable sign. Supplying a real value (measurement, unsteady CFD,
    # or the strip estimate 2*C_N_alpha*(l1/d_ref)^2) is future work, not this
    # step. Overridden per (alpha, M) by an optional `c_mq` column in
    # `aero_table`, when one is present.
    c_mq: float = 0.0   # pitch-damping derivative dC_m/d(q_hat) [-]

    # Step 47: launch rail constraint (architecture.md SS27.1). While the
    # rocket's travel along the rail is less than `L_rail`, the rail buttons
    # mechanically react every transverse force component and prevent
    # rotation -- the rocket can only slide, not pitch or drift sideways
    # (dynamics.py's `on_rail`/`rail_distance`). Same "unset sentinel
    # disables the model" convention as `aero_table`/`wind_model`/`m_d`:
    # `L_rail = 0.0` (the default) is the off switch -- `rail_distance` is
    # 0 at t=0, so `0 < 0.0` is false and the rocket is never on the rail,
    # reproducing every prior step bit-for-bit. `rail_angle_deg` is the
    # rail's fixed mount angle (independent of, but meant to be set
    # consistent with, the launch `State.theta` the scenario supplies);
    # default 90.0 (vertical) matches every existing scenario's
    # `theta = pi/2`.
    L_rail: float = 0.0          # launch rail length [m]; 0.0 = off, unconstrained from t=0
    rail_angle_deg: float = 90.0  # rail elevation from horizontal [deg]; direction of e_rail

    # Step 48: recovery / parachute (architecture.md SS27.2). Once deployed,
    # `dtheta/dt = domega/dt = 0` (the same "a mechanical constraint freezes
    # the attitude state" mechanism as the rail above, re-used rather than
    # invented) and the canopy drag is computed directly in the inertial
    # frame (sim/forces.py's `parachute_drag_inertial`), not routed through
    # the body axial/normal decomposition -- a round canopy's drag opposes
    # the relative wind vector, not the body's nose direction. Two
    # independent off switches, same belt-and-suspenders style as
    # `turbulence_sigma_high_ms`/`A_e`: `parachute_model = "none"` (the
    # default) is the primary one -- `forces.parachute_deployed` returns
    # `False` unconditionally, so `dynamics.py`'s new branch never
    # activates. `parachute_S = 0.0` (also the default) is a second,
    # independent one -- even if `parachute_model == "deploy"`, zero
    # reference area makes the chute force exactly zero. Either alone
    # reproduces every prior step bit-for-bit.
    parachute_model: str = "none"              # none | deploy
    parachute_deploy_trigger: str = "apogee"   # apogee | timer
    parachute_deploy_time: float = 0.0         # [s], used only when trigger == "timer"
    parachute_Cd: float = 0.8                  # [-], typical flat-circular canopy; override per design
    parachute_S: float = 0.0                   # [m^2] canopy reference area; 0.0 = inert even if deployed