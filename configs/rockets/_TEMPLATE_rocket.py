r"""configs/rockets/_TEMPLATE_rocket.py -- TEMPLATE, fill in your own
numbers (Step 72, dev/docs/architecture-31-config-separation.md SS31.5).

This file is a blank `Rocket` piece: one airframe -- structure,
geometry, aerodynamics, and the recovery/control hardware bolted to
it, but NOT its motor (SS32.1) -- a `Rocket` no longer carries one as
of Step 80. Every field below is commented
`# REQ|OPT, <unit or choices> -- <one line>` (SS32.8): REQ = you must
fill it in, OPT = leaving it alone gives correct, intentional behaviour.
Fields the template leaves at their default are listed as commented-out
lines (`# name=default,  # OPT, ...`) -- uncomment one to set it. The
per-field tables at the end of this docstring list every field with its
default; `l1`/`l2` are the authoritative arms and `Sections` is
descriptive only (SS32.5, D-68).

To fill in your motor, see `configs/motors/_TEMPLATE_motor.py`
instead -- a motor is its own piece now, referenced from
`configs/scenarios/<your_scenario>.py`'s `Scenario.motor`, not from
this file.

This module is **never registered** -- it is deliberately absent from
`configs/rockets/__init__.py`'s `_MODULES` tuple, and must stay
absent: a half-finished draft rocket must not become real by merely
existing (the same explicit-tuple rule every registry in this project
follows). It still imports cleanly on its own --
`python -c "import configs.rockets._TEMPLATE_rocket"` must succeed --
so the file does not silently rot; pinned by
`tests/test_config_registries.py` (SS31.8 #6).

To use this template:
  1. Fill in every `# REQ` field below with your own numbers.
  2. Rename this file (and the `name="my_rocket"` string below) to
     whatever you want your rocket called.
  3. Add `from configs.rockets import <your_module_name>` and one line
     to `configs/rockets/__init__.py`'s `_MODULES` tuple.

The aero model `table` (the data-table model) reads `data/aero/<table>.csv`.

### Rocket
| field     | REQ/OPT | unit / choices | default     | what it does |
|-----------|---------|----------------|-------------|--------------|
| name      | REQ     | -              | --          | registry key; must equal the filename |
| airframe  | REQ     | Airframe group | --          | the vehicle without its motor: mass, MOI, CoG station |
| lengths   | OPT     | Lengths group  | Lengths()   | moment arms and offsets; l1/l2 are authoritative |
| aero      | OPT     | Aero group     | Aero()      | aerodynamic model and coefficients (S and d_ref are needed for any force) |
| recovery  | OPT     | Recovery group | Recovery()  | parachute model; default is no recovery |
| control   | OPT     | Control group  | Control()   | airbrake / aero-coefficient control; default is none |
| sections  | OPT     | Sections group | Sections()  | named airframe stations; descriptive except motor placement |
| notes     | OPT     | -              | ""          | provenance: where the numbers came from |

### Airframe
| field | REQ/OPT | unit / choices | default | what it does |
|-------|---------|----------------|---------|--------------|
| m     | REQ     | kg             | --      | airframe mass, motor excluded |
| I     | REQ     | kg*m^2         | --      | pitch MOI about the airframe's own CoG |
| l     | OPT     | m              | None    | airframe CoG station aft of the nose tip; REQ when the paired Motor has mass_model != "none" |

### Lengths
| field        | REQ/OPT | unit / choices | default | what it does |
|--------------|---------|----------------|---------|--------------|
| l1           | REQ     | m              | 0.0     | CoP to CoG distance (static-margin lever arm); 0.0 is not a usable value |
| l2           | REQ     | m              | 0.0     | CoP to thrust-point distance; 0.0 is not a usable value |
| u_B          | OPT     | m              | 0.0     | lateral offset of the CoG |
| u_C          | OPT     | m              | 0.0     | lateral offset of the thrust point |
| misalign_deg | OPT     | deg            | 0.0     | fixed nozzle cant (must be 0.0 with a CP station l_p / l_p_m) |
| l_g          | OPT     | m              | 0.0     | CoG station from the nose; read only with a CP station and no mass model (0.0 there is an error) |

### Sections
| field          | REQ/OPT | unit / choices | default | what it does |
|----------------|---------|----------------|---------|--------------|
| L_total        | OPT     | m              | 0.0     | overall length, nose tip to tail (descriptive) |
| l_nose         | OPT     | m              | 0.0     | nose cone length == station of the nose/body joint (descriptive) |
| l_fin_root_fwd | OPT     | m              | 0.0     | fin root leading-edge station (descriptive) |
| l_fin_root_aft | OPT     | m              | 0.0     | fin root trailing-edge station (descriptive) |
| l_motor_fwd    | OPT     | m              | None    | station of the motor's forward face; REQ (this or l_motor_aft) when mass_model != "none" |
| l_motor_aft    | OPT     | m              | None    | station of the motor's aft face; REQ (this or l_motor_fwd) when mass_model != "none" |
| tubes          | OPT     | -              | ()      | ((name, aft-end station m), ...), informational |
| notes          | OPT     | -              | ""      | where these dimensions came from |

### Aero
| field     | REQ/OPT | unit / choices                  | default    | what it does |
|-----------|---------|---------------------------------|------------|--------------|
| model     | OPT     | constant \| linearized \| table | "constant" | which coefficient model is active |
| S         | REQ     | m^2                             | 0.0        | reference area; 0.0 makes every aerodynamic force zero |
| d_ref     | REQ     | m                               | 0.0        | reference length for the moment and static margin |
| l_ref     | OPT     | m                               | 0.0        | Reynolds reference length (not the moment length) |
| C_x       | REQ     | -                               | 0.0        | axial-force (drag) coefficient; read when model == "constant" |
| C_z       | OPT     | -                               | 0.0        | normal-force coefficient; read when model == "constant" |
| C_m       | OPT     | -                               | 0.0        | pitching-moment coefficient; read when model == "constant" |
| C_A0      | OPT     | -                               | 0.0        | zero-alpha axial coefficient; read when model == "linearized" |
| C_N_alpha | OPT     | 1/rad                           | 0.0        | normal-force slope; read when model == "linearized" |
| C_m_alpha | OPT     | 1/rad                           | 0.0        | pitching-moment slope; read when model == "linearized" |
| table     | OPT     | filename under data/aero/       | ""         | coefficient table; read when model == "table" |
| c_mq      | OPT     | -                               | 0.0        | pitch-damping derivative, all three models |
| l_p       | OPT     | m                               | 0.0        | CoP station from the nose, constant/linearized models; arm = l_p - CoG(t); 0.0 = off (lengths.l1 is the arm) |
| cm_convention | OPT | code \| standard                | "code"     | C_m sign of the constant/linearized models (code: positive = nose-down; standard: textbook, flipped); a table declares `# cm_convention:` in its header |
| table_oob | OPT | clamp \| jorgensen              | "clamp"    | table model, alpha beyond the table: clamp = hold the edge value (legacy, warns once per run); jorgensen = large-alpha extension (needs v2 table with l_p_m, S_p, l_pc) |
| oob_blend_deg | OPT | deg                         | 10.0       | width of the blend band beyond the table edge; read when table_oob == "jorgensen" |
| S_p       | REQ     | m^2                             | 0.0        | planform area (about d_ref * body length); REQ iff table_oob == "jorgensen" |
| l_pc      | REQ     | m                               | 0.0        | planform-centroid station from the nose (about half the length, aft with fins); REQ iff table_oob == "jorgensen" |
| C_dn      | OPT     | -                               | 1.2        | crossflow drag coefficient of a cylinder (constant; UNVERIFIED, Mach/Re dependence not modelled) |
| eta       | OPT     | -                               | 0.0        | finite-length factor; 0.0 = from fineness S_p/d_ref^2 (Jorgensen TR R-474 Fig. 4) |
| C_x180    | OPT     | -                               | 0.0        | axial coefficient magnitude in tail-first flow; 0.0 = C_x(0) of the table (UNVERIFIED placeholder: a blunt base facing the flow is higher, set it) |
| S_base    | OPT     | m^2                             | 0.0        | base area of the potential term; 0.0 = S |

### Recovery
| field       | REQ/OPT | unit / choices   | default  | what it does |
|-------------|---------|------------------|----------|--------------|
| model       | OPT     | none \| deploy   | "none"   | parachute model; "none" = every field below inert |
| trigger     | OPT     | apogee \| timer  | "apogee" | what fires the deployment |
| deploy_time | OPT     | s                | 0.0      | deployment time; read only when trigger == "timer" |
| Cd          | OPT     | -                | 0.8      | canopy drag coefficient |
| S           | OPT     | m^2              | 0.0      | canopy reference area; 0.0 = inert even if model == "deploy" |

### Control
| field                    | REQ/OPT | unit / choices                              | default          | what it does |
|--------------------------|---------|---------------------------------------------|------------------|--------------|
| airbrake_model           | OPT     | none \| proportional                        | "none"           | airbrake controller; "none" = every field below inert |
| airbrake_target_apogee_m | OPT     | m                                           | 0.0              | target apogee the controller steers toward |
| airbrake_kp              | OPT     | 1/m                                         | 0.0              | proportional gain on predicted-apogee error (deployment fraction per metre) |
| airbrake_Cd              | OPT     | -                                           | 1.0              | airbrake drag coefficient |
| airbrake_S_max           | OPT     | m^2                                         | 0.0              | fully deployed airbrake area; 0.0 = inert |
| airbrake_trigger         | OPT     | after_burnout \| after_time \| after_apogee | "after_burnout"  | when the brake is allowed to act |
| airbrake_deploy_time     | OPT     | s                                           | 0.0              | read only when airbrake_trigger == "after_time" |
| aero_coeff_model         | OPT     | none                                        | "none"           | aero-coefficient control seam; "none" = identity |
| airbrake_aero            | OPT     | additive \| table                           | "additive"       | brake in the aerodynamics: additive axial term, or the aero table's f_b axis (needs an f_b column) |
"""

from __future__ import annotations

from configs.schema import Airframe, Rocket
from sim.params import Aero, Control, Lengths, Recovery

ROCKET = Rocket(
    name="my_rocket",  # REQ, - -- registry key; rename to match the filename once you rename it

    airframe=Airframe(  # REQ, Airframe group -- the vehicle without its motor
        m=1.5,        # REQ, kg -- airframe mass, motor EXCLUDED (the motor piece carries its own)
        I=0.08,       # REQ, kg*m^2 -- pitch moment of inertia about the airframe's own CoG
        # Leave l=None (the default) unless you are pairing this
        # airframe with a mass-modelled motor (mass_model != "none",
        # configs/motors/_TEMPLATE_motor.py) -- that needs l plus a
        # Sections.l_motor_fwd/l_motor_aft below. A bare m/I pair
        # treats mass as constant through the whole flight, which is
        # fine for a first pass and is what every demo rocket does
        # today.
        # l=None,     # OPT, m -- airframe CoG station aft of the nose tip; REQ when the motor has mass_model != "none"
    ),

    lengths=Lengths(  # OPT, Lengths group -- moment arms; l1/l2 are authoritative (Sections below is descriptive)
        l1=0.3,       # REQ, m -- CoP-to-CoG distance (static margin lever arm); 0.0 is not usable
        l2=0.4,       # REQ, m -- CoP-to-thrust-point distance; 0.0 is not usable
        # u_B, u_C, misalign_deg default to 0.0 -- leave them unless
        # you specifically want to model a lateral CoG/thrust offset
        # or a fixed nozzle cant.
        # u_B=0.0,           # OPT, m -- lateral offset of the CoG; 0.0 = on the axis
        # u_C=0.0,           # OPT, m -- lateral offset of the thrust point; 0.0 = on the axis
        # misalign_deg=0.0,  # OPT, deg -- fixed nozzle cant; 0.0 = thrust along the axis (must be 0.0 with an aero l_p / l_p_m CP station)
        # l_g=0.0,           # OPT, m -- CoG station from the nose tip; read only with an aero CP station (l_p / l_p_m) and NO mass model; 0.0 there is an error
    ),

    # sections left at its default (Sections()) -- fill it in (see
    # configs/schema.py's Sections docstring) only if you are pairing
    # this airframe with a mass-modelled motor, which needs
    # l_motor_fwd/l_motor_aft to place the motor along the airframe.
    # sections=Sections(  # OPT, Sections group -- named stations, all positive aft of the nose tip; descriptive except the motor station
    #     L_total=0.0,         # OPT, m -- overall length, nose tip to tail
    #     l_nose=0.0,          # OPT, m -- nose cone length == station of the nose/body joint
    #     l_fin_root_fwd=0.0,  # OPT, m -- fin root leading-edge station
    #     l_fin_root_aft=0.0,  # OPT, m -- fin root trailing-edge station
    #     l_motor_fwd=None,    # OPT, m -- station of the motor's forward face; REQ (this or l_motor_aft) with a mass-modelled motor
    #     l_motor_aft=None,    # OPT, m -- station of the motor's aft face; REQ (this or l_motor_fwd) with a mass-modelled motor
    #     tubes=(),            # OPT, - -- ((name, aft-end station m), ...), informational
    #     notes="",            # OPT, - -- where these dimensions came from
    # ),

    aero=Aero(  # OPT, Aero group -- aerodynamic model; S and d_ref are needed for any nonzero force
        # "constant" model: true, q-scaled coefficients (not raw
        # Newtons) -- S and d_ref are required for any nonzero
        # force/moment at all.
        # model="constant",  # OPT, constant | linearized | table -- active model; "table" is the data-table model (data/aero/<table>.csv)
        S=0.00442,    # REQ, m^2 -- reference area (pi * d^2 / 4 for body diameter d); 0.0 zeroes every force
        d_ref=0.075,  # REQ, m -- reference length (your body diameter is the usual choice)
        # l_ref=0.0,  # OPT, m -- Reynolds reference length (NOT the moment length); 0.0 = unset
        C_x=0.5,      # REQ, - -- axial-force (drag) coefficient, "constant" model
        C_z=0.0,      # OPT, - -- normal-force coefficient, "constant" model; 0.0 keeps flight vertical/1-D
        C_m=0.0,      # OPT, - -- pitching-moment coefficient, "constant" model; 0.0 = no moment
        # If you have a real drag number (CFD, RASAero, OpenRocket, or
        # App 4's own output once you've sized an airbrake) put it in
        # C_x. Leaving C_z=C_m=0.0 is the same "attitude-frozen,
        # vertical shot" simplification every current rocket uses --
        # fine for a first cut; switch aero.model to "linearized" or
        # "table" later if you need alpha-dependent coefficients.
        # C_A0=0.0,        # OPT, - -- zero-alpha axial coefficient, "linearized" model only
        # C_N_alpha=0.0,   # OPT, 1/rad -- normal-force slope, "linearized" model only
        # C_m_alpha=0.0,   # OPT, 1/rad -- pitching-moment slope, "linearized" model only
        # table="",        # OPT, filename under data/aero/ -- coefficient table, "table" model only
        # c_mq=0.0,        # OPT, - -- pitch-damping derivative, all three models; 0.0 = undamped
        # l_p=0.0,         # OPT, m -- CoP station from the nose tip, "constant"/"linearized" models; arm = l_p - CoG(t); 0.0 = off (lengths.l1 is the arm). A table gives its own l_p_m column instead of l1_m
        # cm_convention="code",  # OPT, code | standard -- C_m sign of the "constant"/"linearized" models; "code": positive C_m = nose-down; "standard": textbook, flipped on use. A table declares `# cm_convention:` in its header
        # table_oob="clamp",  # OPT, clamp | jorgensen -- "table" model, alpha beyond the table: clamp = hold the edge value (legacy, warns once per run); jorgensen = large-alpha extension
        # oob_blend_deg=10.0,  # OPT, deg -- width of the blend band beyond the table edge; "jorgensen" only
        # S_p=0.0,         # REQ, m^2 -- planform area, about d_ref * body length; required iff table_oob="jorgensen"
        # l_pc=0.0,        # REQ, m -- planform-centroid station from the nose; required iff table_oob="jorgensen"
        # C_dn=1.2,        # OPT, - -- crossflow drag coefficient of a cylinder, constant (UNVERIFIED; no Mach/Re dependence)
        # eta=0.0,         # OPT, - -- finite-length factor; 0.0 = derived from fineness S_p/d_ref^2
        # C_x180=0.0,      # OPT, - -- axial coefficient magnitude, tail-first flow; 0.0 = table C_x(0) (UNVERIFIED placeholder, set it)
        # S_base=0.0,      # OPT, m^2 -- base area of the potential term; 0.0 = S
    ),

    recovery=Recovery(  # OPT, Recovery group -- parachute; default is no recovery
        model="none",        # OPT, none | deploy -- "none" means every field below is inert
        trigger="apogee",    # OPT, apogee | timer -- what fires deployment; read only once model != "none"
        deploy_time=0.0,     # OPT, s -- deployment time; read only when trigger == "timer"
        Cd=0.8,              # OPT, - -- canopy drag coefficient; read only once model != "none"
        S=0.0,               # OPT, m^2 -- canopy reference area; 0.0 = inert even if model == "deploy"
        # Leave this whole group at its defaults for a no-recovery
        # vehicle (what every current demo rocket does); fill it in
        # once you actually want a parachute deployment event.
    ),

    control=Control(  # OPT, Control group -- airbrake; default is no control
        airbrake_model="none",  # OPT, none | proportional -- "none" means every field below is inert
        # Leave this whole group at its defaults unless you are
        # modelling an airbrake (apps/airbrake_sizing/); App 4 fills
        # this in for you from a sizing run rather than hand-editing it.
        # airbrake_target_apogee_m=0.0,        # OPT, m -- target apogee the controller steers toward
        # airbrake_kp=0.0,                     # OPT, 1/m -- gain on predicted-apogee error (deployment fraction per metre); 0.0 = inert
        # airbrake_Cd=1.0,                     # OPT, - -- airbrake drag coefficient
        # airbrake_S_max=0.0,                  # OPT, m^2 -- fully deployed airbrake area; 0.0 = inert
        # airbrake_trigger="after_burnout",    # OPT, after_burnout | after_time | after_apogee -- when the brake may act
        # airbrake_deploy_time=0.0,            # OPT, s -- read only when airbrake_trigger == "after_time"
        # aero_coeff_model="none",             # OPT, none -- aero-coefficient control seam; "none" = identity
        # airbrake_aero="additive",            # OPT, additive | table -- brake via additive term or the table's f_b axis
    ),

    notes=(
        "My actual rocket -- <say where these numbers came from: measured, "
        "vendor datasheet, estimate, date>."
    ),  # OPT, - -- provenance: where the numbers came from
)
