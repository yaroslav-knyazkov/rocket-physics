"""configs/motors/_TEMPLATE_motor.py -- TEMPLATE, fill in your own numbers
(Phase 2.16, Step 79, dev/docs/architecture-32-motor-separation.md SS32.2.1).

This file is a blank `Motor` piece: one motor installation -- its thrust
curve, and its OWN mass / CoG / MOI history. Every field below is
commented `# REQ|OPT, <unit/choices> -- <one line>`, the SS32.8
documentation convention, written here first so Step 82's later pass has
nothing left to do to this file.

Geometry on a `Motor` is MOTOR-LOCAL: the origin is the motor's forward
(nose-ward) face and distances are POSITIVE aft (SS32.5) -- the same
sense the airframe uses from the nose tip A. That is what makes one
motor reusable across airframes: the rocket supplies the mounting
station (`Sections.l_motor_fwd`/`l_motor_aft`), the motor never knows
where it is installed.

This module is **never registered** -- it is deliberately absent from
`configs/motors/__init__.py`'s `_MODULES` tuple, and must stay absent: a
half-finished draft motor must not become real by merely existing (the
same explicit-tuple rule every registry in this project follows). It
still imports cleanly on its own --
`python -c "import configs.motors._TEMPLATE_motor"` must succeed -- so
the file does not silently rot; pinned by
`tests/test_config_registries.py` (SS31.8 #6).

To use this template:
  1. Fill in every `# <-- fill this in` field below with your own numbers.
  2. Rename this file (and the `name="my_motor"` string below) to
     whatever you want your motor called.
  3. Add `from configs.motors import <your_module_name>` and one line
     to `configs/motors/__init__.py`'s `_MODULES` tuple.

| field      | REQ/OPT | unit / choices           | default   | what it does |
|------------|---------|---------------------------|-----------|--------------|
| name       | REQ     | -                          | --        | registry key; must equal the filename |
| thrust     | REQ     | Thrust group               | Thrust()  | the curve file, nozzle exit area, reference pressure; owns `Params.thrust` whole |
| mass_model | OPT     | none / isp / endpoints    | "none"    | which m(t) model; "none" = constant mass, every field below inert |
| m_total    | OPT     | kg                         | None      | loaded mass at ignition (.eng header field 6); None -> read from the file's header |
| m_prop     | OPT     | kg                         | None      | propellant mass (.eng header field 5); None -> read from the file's header |
| I_sp       | OPT     | s                          | None      | specific impulse; REQ when mass_model == "isp", ignored otherwise |
| length     | OPT     | m                          | None      | overall length (.eng header field 3, mm); None -> read from the file's header |
| diameter   | OPT     | m                          | None      | casing diameter (.eng header field 2, mm); None -> read from the file's header |
| l_case     | OPT     | m                          | None      | casing centroid, motor-local; None -> length/2 |
| l_prop     | OPT     | m                          | None      | propellant centroid, motor-local; None -> length/2 |
| I_case     | OPT     | kg*m^2                     | None      | casing MOI about its own centroid; None -> uniform-cylinder default |
| I_prop0    | OPT     | kg*m^2                     | None      | propellant MOI about its own centroid at t=0; None -> uniform-cylinder default |
| l_cog_0    | OPT     | m                          | None      | motor-local CoG at ignition (endpoint form, SS32.3.5; alternative to l_prop/I_prop0) |
| l_cog_f    | OPT     | m                          | None      | motor-local CoG at burnout (endpoint form) |
| I_0        | OPT     | kg*m^2                     | None      | motor's own MOI at ignition, about its own CoG (endpoint form) |
| I_f        | OPT     | kg*m^2                     | None      | motor's own MOI at burnout, about its own CoG (endpoint form) |
| notes      | OPT     | -                          | ""        | provenance: vendor, datasheet, date, measured or estimated |
"""

from __future__ import annotations

from configs.schema import Motor
from sim.params import Thrust

MOTOR = Motor(
    name="my_motor",  # REQ, - -- registry key; rename to match the filename once you rename it

    thrust=Thrust(
        motor_curve="placeholder.csv",  # <-- fill this in: a filename under data/motors/,
        # optionally "<filename>#<designation>" for a multi-record RASP
        # library (sim/motor_file.py). Either pick one of the existing
        # files (placeholder.csv, synthetic_small/medium_long/
        # medium_punchy/large.csv, Cesaroni_2060K570-17A.eng) or drop
        # your own curve into data/motors/ and name it here.
    ),  # REQ, Thrust group -- owns Params.thrust whole: the curve file, nozzle exit area, reference pressure

    # --- which m(t) model is active (SS32.3.4) --------------------------
    mass_model="none",  # OPT, none | isp | endpoints -- "none" flies at constant mass (every field below inert)

    # --- masses ---------------------------------------------------------
    m_total=None,  # OPT, kg -- loaded mass at ignition; None -> read from the motor file's own header
    m_prop=None,  # OPT, kg -- propellant mass; None -> read from the motor file's own header, REQ for a bare .csv
    I_sp=None,  # OPT, s -- specific impulse; REQ when mass_model == "isp", ignored otherwise

    # --- the motor's own geometry, motor-local, positive aft -------------
    length=None,  # OPT, m -- overall length; None -> read from the motor file's own header
    diameter=None,  # OPT, m -- casing diameter; None -> read from the motor file's own header
    l_case=None,  # OPT, m -- casing centroid, motor-local; None -> length/2
    l_prop=None,  # OPT, m -- propellant centroid, motor-local; None -> length/2
    I_case=None,  # OPT, kg*m^2 -- casing MOI about its own centroid; None -> uniform-cylinder default
    I_prop0=None,  # OPT, kg*m^2 -- propellant MOI about its own centroid at t=0; None -> uniform-cylinder default

    # --- the user's endpoint parameterisation, SS32.3.5 (an alternative
    #     to l_prop / I_prop0 above; give one form OR the other) ---------
    l_cog_0=None,  # OPT, m -- motor-local CoG at ignition
    l_cog_f=None,  # OPT, m -- motor-local CoG at burnout
    I_0=None,  # OPT, kg*m^2 -- motor's own MOI at ignition, about its own CoG
    I_f=None,  # OPT, kg*m^2 -- motor's own MOI at burnout, about its own CoG

    notes=(
        "My actual motor -- <say where these numbers came from: measured, "
        "vendor datasheet, estimate, date>."
    ),  # OPT, - -- provenance: vendor, datasheet, date, measured or estimated
)
