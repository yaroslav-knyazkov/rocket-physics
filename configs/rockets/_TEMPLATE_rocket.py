"""configs/rockets/_TEMPLATE_rocket.py -- TEMPLATE, fill in your own
numbers (Step 72, docs/architecture-31-config-separation.md SS31.5).

This file is a blank `Rocket` piece: one airframe -- structure,
geometry, aerodynamics, and the recovery/control hardware bolted to
it, but NOT its motor (SS32.1) -- a `Rocket` no longer carries one as
of Step 80. Every field below is commented with its unit, its meaning,
and the consequence of leaving it at the placeholder value.

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
  1. Fill in every `# <-- fill this in` field below with your own numbers.
  2. Rename this file (and the `name="my_rocket"` string below) to
     whatever you want your rocket called.
  3. Add `from configs.rockets import <your_module_name>` and one line
     to `configs/rockets/__init__.py`'s `_MODULES` tuple.
"""

from __future__ import annotations

from configs.schema import Airframe, Rocket
from sim.params import Aero, Control, Lengths, Recovery

ROCKET = Rocket(
    name="my_rocket",  # <-- rename this string to match the filename once you rename it

    airframe=Airframe(
        m=1.5,        # <-- fill this in: TOTAL mass at liftoff (dry + full propellant), kg
        I=0.08,       # <-- fill this in: pitch moment of inertia about the CoG, kg*m^2
        # Leave l=None (the default) unless you are pairing this
        # airframe with a mass-modelled motor (mass_model != "none",
        # configs/motors/_TEMPLATE_motor.py) -- that needs l plus a
        # Sections.l_motor_fwd/l_motor_aft below. A bare m/I pair
        # treats mass as constant through the whole flight, which is
        # fine for a first pass and is what every demo rocket does
        # today.
    ),

    lengths=Lengths(
        l1=0.3,       # <-- fill this in: CoP-to-CoG distance, metres (static margin lever arm)
        l2=0.4,       # <-- fill this in: CoP-to-thrust-point distance, metres
        # u_B, u_C, misalign_deg default to 0.0 -- leave them unless
        # you specifically want to model a lateral CoG/thrust offset
        # or a fixed nozzle cant.
    ),

    # sections left at its default (Sections()) -- fill it in (see
    # configs/schema.py's Sections docstring) only if you are pairing
    # this airframe with a mass-modelled motor, which needs
    # l_motor_fwd/l_motor_aft to place the motor along the airframe.

    aero=Aero(
        # "constant" model: true, q-scaled coefficients (not raw
        # Newtons) -- S and d_ref are required for any nonzero
        # force/moment at all.
        S=0.00442,    # <-- fill this in: reference area, m^2 (pi * d^2 / 4 for body diameter d)
        d_ref=0.075,  # <-- fill this in: reference length, m (your body diameter is the usual choice)
        C_x=0.5,      # <-- fill this in: axial-force (drag) coefficient [-]
        C_z=0.0,      # <-- normal-force coefficient [-] (0.0 keeps flight vertical/1-D)
        C_m=0.0,      # <-- pitching-moment coefficient [-]
        # If you have a real drag number (CFD, RASAero, OpenRocket, or
        # App 4's own output once you've sized an airbrake) put it in
        # C_x. Leaving C_z=C_m=0.0 is the same "attitude-frozen,
        # vertical shot" simplification every current rocket uses --
        # fine for a first cut; switch aero.model to "linearized" or
        # "table" later if you need alpha-dependent coefficients.
    ),

    recovery=Recovery(
        model="none",        # <-- none | deploy; "none" means every field below is inert
        trigger="apogee",    # <-- apogee | timer; read only once model != "none"
        deploy_time=0.0,     # <-- s; read only when trigger == "timer"
        Cd=0.8,               # <-- canopy drag coefficient [-]; read only once model != "none"
        S=0.0,                 # <-- canopy reference area, m^2; 0.0 = inert even if model == "deploy"
        # Leave this whole group at its defaults for a no-recovery
        # vehicle (what every current demo rocket does); fill it in
        # once you actually want a parachute deployment event.
    ),

    control=Control(
        airbrake_model="none",  # <-- none | proportional; "none" means every field below is inert
        # Leave this whole group at its defaults unless you are
        # modelling an airbrake (apps/airbrake_sizing/); App 4 fills
        # this in for you from a sizing run rather than hand-editing it.
    ),

    notes=(
        "My actual rocket -- <say where these numbers came from: measured, "
        "vendor datasheet, estimate, date>."
    ),
)
