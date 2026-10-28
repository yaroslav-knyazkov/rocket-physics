r"""apps/input/demo_scenario.py -- the canonical "how do I build my own
rocket" reference (Phase 2.18, Step 122; moved here from
examples/worked_scenario.py at Phase 2.19, Step 130,
dev/docs/architecture-apps-sim-restructure.md Step 130 -- this literal
is library-adjacent input data, not a demo script, so it lives under
`apps/` rather than in `examples/`, which keeps only the thin runner
now).

This file replaces the value the five `configs/{rockets,sites,weather,
motors,scenarios}/_TEMPLATE_*.py` files used to carry: every field below
is commented `# REQ|OPT, <unit or choices> -- <one line>`, the same
crib-sheet convention those templates used (SS32.8) -- REQ = you must
supply a real number for your own vehicle, OPT = leaving it alone gives
correct, intentional behaviour (the library default, from `sim/params.py`).
Only the fields this worked example actually sets are annotated here; a
group left at its default entirely (`control`, `actuator`, `roll`,
`inertia`, `sensors`, `gravity`) is not constructed at all below -- see
`sim/params.py`'s own dataclasses for that group's full field table.

Unlike the old templates, this module is NOT registered anywhere and
there is no `_MODULES` tuple to add a line to -- the registry convention
this file replaces is being retired (D-139/D-140). Building your own
rocket is now: copy this file, rename `DEMO_SCENARIO`, edit the literal
values below, done -- no file-naming contract, no registration step, no
`configs/__init__.py` to keep in sync.

The values below are copied verbatim from the five files this worked
example demonstrates equivalence to (`tests/test_bridge_demo_scenario_
equivalence.py`, Step 122, deleted at Step 125 once it had nothing left
to bridge, was the proof, not just an assertion):

  - `configs/rockets/demo.py`      -> `rocket` below
  - `configs/motors/cti_k570.py`   -> `motor` below
  - `configs/sites/origin_msl.py`  -> `site` below
  - `configs/weather/isa_dry_calm.py` -> `weather` below
  - `configs/scenarios/demo.py`    -> `DEMO_SCENARIO` below

This is the real CTI K570 flown on a 54 mm airframe sized for it, mass
model ON ("endpoints", deriving `I_sp` from the motor file's own total
impulse rather than a hand-entered number), one main canopy at apogee,
at the placeholder `origin_msl`/`isa_dry_calm` site/weather pair every
demo in this project uses. See `configs/rockets/demo.py` and
`configs/motors/cti_k570.py`'s own module docstrings for the full
provenance of every number (where 0.00229 m^2, 1.10 m, etc. come from).

Step 123 wired `run.py` and friends to import `DEMO_SCENARIO` from here
(then from `examples/worked_scenario.py`, now from this module) instead
of going through the `configs.get("demo")` registry lookup.

Importable as `from apps.input.demo_scenario import DEMO_SCENARIO` (and
friends -- `rocket`, `motor`, `site`, `weather` are also exported, for
the callers that want the individual pieces). `examples/worked_scenario.py`
is the thin, directly-runnable copy of this file's `if __name__ ==
"__main__":` block -- run `python -m examples.worked_scenario` to
actually fly this scenario and print a summary; this module itself has
no `__main__` block.
"""

from __future__ import annotations

from apps.sim.schema import Airframe, LaunchSite, Motor, Rocket, Scenario, Sections, Weather
from apps.sim.engine.params import Aero, Atmosphere, Lengths, Recovery, Site, Solver, Soundings, Thrust, Wind

# ----------------------------------------------------------------------
# rocket -- configs/rockets/demo.py's ROCKET, field-for-field
# ----------------------------------------------------------------------

_airframe = Airframe(
    m=1.5,    # REQ, kg -- airframe mass, motor EXCLUDED (the motor piece carries its own)
    I=0.15,   # REQ, kg*m^2 -- pitch moment of inertia about the airframe's own CoG
    l=0.55,   # OPT, m -- airframe CoG station aft of the nose tip; REQ here because the
              #           paired motor below has mass_model != "none"
)

_lengths = Lengths(
    l1=0.3,  # REQ, m -- CoP-to-CoG distance (static margin lever arm); 0.0 is not usable
    l2=0.4,  # REQ, m -- CoP-to-thrust-point distance; 0.0 is not usable
)

_aero = Aero(
    S=0.00229,    # REQ, m^2 -- reference area; 54 mm body, pi*0.054^2/4 = 0.002290 m^2
    d_ref=0.054,  # REQ, m -- reference length (body diameter); 54 mm
    l_ref=1.10,   # OPT, m -- Reynolds reference length (NOT the moment length); 0.0 -> falls back to d_ref
    C_x=0.5,      # REQ, - -- axial-force (drag) coefficient, "constant" model
    C_z=0.0,      # OPT, - -- normal-force coefficient; 0.0 keeps flight vertical/1-D
    C_m=0.0,      # OPT, - -- pitching-moment coefficient; 0.0 = no moment
)

_sections = Sections(
    L_total=1.10,         # OPT, m -- overall length, nose tip to tail (descriptive)
    l_nose=0.25,          # OPT, m -- nose cone length == station of the nose/body joint (descriptive)
    l_fin_root_fwd=0.92,  # OPT, m -- fin root leading-edge station (descriptive)
    l_fin_root_aft=1.02,  # OPT, m -- fin root trailing-edge station (descriptive)
    l_motor_aft=1.10,     # OPT, m -- station of the motor's aft face; REQ (this or l_motor_fwd) here
                           #           because the paired motor has mass_model != "none"; aft-flush
                           #           install, the forward face resolves to L_total - motor.length
)

_recovery = Recovery(
    model="deploy",    # OPT, none | deploy -- one main canopy, the only recovery machinery sim/ has
    trigger="apogee",  # OPT, apogee | timer -- deploys once descending, after the pad guard
    Cd=0.8,             # OPT, - -- canopy drag coefficient; round canopy, typical vendor figure
    S=1.23,             # OPT, m^2 -- ~1.25 m flat-diameter round canopy (pi*1.25^2/4 = 1.227),
                         #            sized for ~6 m/s at sea level on the 2.195 kg burnt-out vehicle
)

rocket = Rocket(
    name="demo",             # REQ, - -- identifies this piece; rename for your own vehicle
    airframe=_airframe,       # REQ, Airframe group -- the vehicle without its motor
    lengths=_lengths,         # OPT, Lengths group -- moment arms; l1/l2 are authoritative
    aero=_aero,               # OPT, Aero group -- aerodynamic model and coefficients
    sections=_sections,       # OPT, Sections group -- named airframe stations
    recovery=_recovery,       # OPT, Recovery group -- parachute model
    # control, actuator, roll, inertia, sensors left at their library
    # defaults (every field inert) -- see sim/params.py for their full
    # field tables if you need an airbrake, roll DOF, 3D inertia tensor,
    # or sensor noise model.
)

# ----------------------------------------------------------------------
# motor -- configs/motors/cti_k570.py's MOTOR, field-for-field
# ----------------------------------------------------------------------

motor = Motor(
    name="cti_k570",  # REQ, - -- identifies this piece
    thrust=Thrust(  # REQ in practice, Thrust group -- owns Params.thrust whole: the curve file,
                     #                 nozzle exit area, reference pressure
        motor_curve="Cesaroni_2060K570-17A.eng",  # REQ, filename under examples/data/motors/ -- the real
                                                    #      vendor-published RASP file
    ),
    mass_model="endpoints",  # OPT, none | isp | endpoints -- "endpoints" derives I_sp from the
                              #       motor file's own total impulse rather than a hand-entered number
    # every mass/geometry field below left at its default (None) -- all come from the .eng header:
    # m_total, m_prop, length, diameter, l_case, l_prop, I_case, I_prop0, l_cog_0, l_cog_f, I_0, I_f
    notes=(
        "Cesaroni K570 (17A delay), real vendor-published RASP file "
        "(examples/data/motors/Cesaroni_2060K570-17A.eng). Measured/derived from "
        "the file itself (SS32.3.1 F5): I_sp_eff ~= 212.41 s, J ~= 2062.22 "
        "N*s (trapezoid over the loaded curve, including the (0,0) prepend "
        "sim/motor_file.py applies to RASP records), m_prop=0.990 kg, "
        "m_total=1.685 kg from the header's own fields 5/6."
    ),  # OPT, - -- provenance
)

# ----------------------------------------------------------------------
# site -- configs/sites/origin_msl.py's SITE, field-for-field
# ----------------------------------------------------------------------
#
# "lat 0, lon 0, sea level, no rail" -- honest that this is a placeholder,
# not a field anyone actually flies from. Every field below is spelled out
# explicitly (unlike configs/sites/origin_msl.py's bare `Site()`) so this
# worked example doubles as the crib sheet for every `Site` field -- the
# values are identical to `Site()`'s own library defaults either way.

site = LaunchSite(
    name="origin_msl",  # REQ, - -- identifies this piece
    site=Site(  # REQ, Site group -- latitude, longitude, elevation, azimuth, rail
        lat0_deg=0.0,          # REQ, deg -- launch site latitude; 0.0 = placeholder
        lon0_deg=0.0,          # REQ, deg -- launch site longitude; 0.0 = placeholder
        h0_m=0.0,              # REQ, m -- launch site elevation above MSL
        azimuth_deg=90.0,      # OPT, deg -- direction of +x (downrange), clockwise from North
        L_rail=0.0,            # OPT, m -- launch rail/rod length; 0.0 = no rail modelled
        rail_angle_deg=90.0,   # OPT, deg -- rail elevation from horizontal; 90.0 = vertical
    ),
)

# ----------------------------------------------------------------------
# weather -- configs/weather/isa_dry_calm.py's WEATHER, field-for-field
# ----------------------------------------------------------------------
#
# ISA, dry air, no wind, no sounding case. As with `site` above, every
# field is spelled out explicitly here (unlike isa_dry_calm.py's bare
# `Weather(name="isa_dry_calm")`) purely so this file is a complete crib
# sheet; the values are identical to the library defaults either way.

weather = Weather(
    name="isa_dry_calm",  # REQ, - -- identifies this piece
    atmosphere=Atmosphere(  # OPT, Atmosphere group -- atmosphere model; default is dry ISA
        model="isa",       # OPT, isa | sounding | field -- "isa" needs no sounding data at all
        humid_air=False,   # OPT, bool -- False = dry-air ISA
        dT_K=0.0,          # OPT, K -- ISA launch-day temperature offset; 0.0 = off
    ),
    soundings=Soundings(  # OPT, Soundings group -- sounding case and interpolation grid; inert while model == "isa"
        case="",                  # OPT, folder under data/soundings/ -- "" = unused while model == "isa"
        horizontal_interp="idw",  # OPT, idw | rbf -- horizontal interpolation
        grid_top_m=30000.0,       # OPT, m -- top of the interpolation grid
        grid_step_m=100.0,        # OPT, m -- vertical grid step
        idw_epsilon_m=500.0,      # OPT, m -- IDW smoothing length
    ),
    wind=Wind(  # OPT, Wind group -- wind and turbulence; default is no wind
        model="none",                  # OPT, none | analytic | sounding | field -- "none" = no wind
        ref_ms=0.0,                    # OPT, m/s -- reference wind speed
        dir_deg=0.0,                   # OPT, deg -- meteorological direction: from North, clockwise
        ref_h_m=10.0,                  # OPT, m -- height ref_ms is measured at
        shear_exp=0.143,               # OPT, - -- power-law shear exponent, "analytic" model only
        turbulence_model="none",       # OPT, none | dryden -- turbulence model
        turbulence_sigma_high_ms=0.0,  # OPT, m/s -- turbulence intensity (sigma)
        turbulence_ref_speed_ms=100.0, # OPT, m/s -- turbulence reference speed
        turbulence_seed=0,             # OPT, - -- RNG seed for the turbulence model
    ),
)

# ----------------------------------------------------------------------
# DEMO_SCENARIO -- configs/scenarios/demo.py's SCENARIO, field-for-field
# ----------------------------------------------------------------------
#
# Pairs the real CTI K570 ("endpoints" mass model) with the 54 mm
# airframe above, at the origin_msl/isa_dry_calm site/weather pair.
#
# Mach caveat: this K570 on a 1.5 kg airframe reaches roughly Mach 1.75 on
# the ascent (apogee ~5.95 km), but the airframe's aero model is
# "constant" (C_x = 0.5, not Mach-dependent), which is not credible above
# ~Mach 0.8. The numbers are kept as built; a run that exceeds Mach 0.8
# under a Mach-independent drag model warns at run time.
#
# Recovery: one main canopy at apogee (see `rocket` above); a real flight
# to this altitude would use drogue + main (dual deploy), which `sim/`
# cannot model yet (backlog B29). The canopy descent from ~5.9 km takes
# ~860 s (apogee at ~30 s, ground at ~891 s total flight time), hence the
# longer `t_max` below.

DEMO_SCENARIO = Scenario(
    name="demo",                  # REQ, - -- identifies this scenario
    rocket=rocket,                 # REQ, Rocket piece
    motor=motor,                   # REQ, Motor piece
    site=site,                     # REQ, LaunchSite piece
    weather=weather,               # REQ, Weather piece
    solver=Solver(t_max=1200.0),   # OPT, Solver group -- canopy descent from ~5.9 km takes ~860 s;
                                    #      the default 300 s would stop mid-air
    notes=(
        "A real vendor motor (Cesaroni K570), its own mass history read "
        "from its own RASP file, composed with an airframe that knows "
        "where the motor sits -- the mass model is ON from a config for "
        "the first time (SS32.3.3)."
    ),  # OPT, - -- provenance: what this combination is for
)
