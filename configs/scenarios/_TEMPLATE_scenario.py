r"""configs/scenarios/_TEMPLATE_scenario.py -- TEMPLATE, fill in your
own numbers (Step 72, dev/docs/architecture-31-config-separation.md
SS31.5).

This file is a blank `Scenario`: one named combination of a rocket, a
motor, a site, and a day's weather, plus the run-level groups nobody
reuses by name (gravity/solver/g0). It demonstrates the thing this
whole phase is for -- referencing named pieces **by import** instead
of re-specifying them every time.

This module is **never registered** -- it is deliberately absent from
`configs/scenarios/__init__.py`'s `_MODULES` tuple, and must stay
absent. It still imports cleanly on its own --
`python -c "import configs.scenarios._TEMPLATE_scenario"` must
succeed -- so the file does not silently rot; pinned by
`tests/test_config_registries.py` (SS31.8 #6).

Referencing pieces by import, once you have some registered, looks
like this:

    from configs.rockets.demo import ROCKET  # replace with your own once you have one

This template builds its placeholder rocket and motor inline below
instead, so the file stays self-contained; the site and weather pieces
below really exist (`configs.sites.origin_msl`,
`configs.weather.isa_dry_calm`), so those two imports are live, working
examples of the pattern.

A flat, whole-`Config` scenario module -- one `Config(...)` literal
with no `Rocket`/`Motor`/`LaunchSite`/`Weather`/`Scenario` pieces at
all, the shape the user's own `configs/_TEMPLATE_my_rocket.py` uses --
remains legal and registrable here, forever (SS31.5, SS31.8 #7): the
scenario registry only requires a module to expose `CONFIG: Config`;
`SCENARIO` below is optional metadata for anyone who wants the
piece-composed form instead. Splitting into pieces is not mandatory
just because this package exists.

To use this template:
  1. Fill in every `# REQ` field below (and build or
     import a real `Rocket` rather than the inline placeholder here,
     once you have one -- see configs/rockets/_TEMPLATE_rocket.py).
  2. Rename this file (and the `name="my_scenario"` string below) to
     whatever you want your scenario called.
  3. Add `from configs.scenarios import <your_module_name>` and one
     line to `configs/scenarios/__init__.py`'s `_MODULES` tuple.

Every field below is commented `# REQ|OPT, <unit or choices> -- <one
line>` (SS32.8): REQ = you must fill it in, OPT = leaving it alone gives
correct, intentional behaviour. Fields the template leaves at their
default are listed as commented-out lines -- uncomment one to set it.
The `rocket`, `motor`, `site` and `weather` pieces have their own
templates (and field tables); only the `Scenario` fields and the two
run-level groups it owns are tabled here. The aero model `table` is the
data-table model (see configs/rockets/_TEMPLATE_rocket.py).

### Scenario
| field    | REQ/OPT | unit / choices | default     | what it does |
|----------|---------|----------------|-------------|--------------|
| name     | REQ     | -              | --          | registry key; must equal the filename |
| rocket   | REQ     | Rocket piece   | --          | the airframe: configs/rockets/_TEMPLATE_rocket.py |
| motor    | REQ     | Motor piece    | --          | the motor: configs/motors/_TEMPLATE_motor.py |
| site     | REQ     | LaunchSite piece | --        | the launch site: configs/sites/_TEMPLATE_site.py |
| weather  | REQ     | Weather piece  | --          | the day's air: configs/weather/_TEMPLATE_weather.py |
| gravity  | OPT     | Gravity group  | Gravity()   | gravity model; default constant, parallel |
| solver   | OPT     | Solver group   | Solver()    | integrator and tolerances; default RK45 |
| g0       | OPT     | m/s^2          | 9.80665     | standard gravity, shared constant |
| s0       | OPT     | State          | None        | initial state; None -> on the pad, nose along the rail |
| overrides| OPT     | dict           | {}          | dotted-path tweaks applied after assembly, e.g. {"site.rail_angle_deg": 85.0} |
| notes    | OPT     | -              | ""          | provenance: what this combination is for |

### Gravity
| field          | REQ/OPT | unit / choices                 | default    | what it does |
|----------------|---------|--------------------------------|------------|--------------|
| model          | OPT     | constant \| radial \| wgs84    | "constant" | gravity magnitude model |
| direction      | OPT     | parallel \| radial \| elliptical | "parallel" | gravity direction model |
| R_e            | OPT     | m                              | 6371000.0  | mean Earth radius |
| earth_rotation | OPT     | bool                           | False      | in-plane Coriolis correction |

### Solver
| field          | REQ/OPT | unit / choices        | default | what it does |
|----------------|---------|-----------------------|---------|--------------|
| method         | OPT     | RK45 \| rk4 (or any scipy name) | "RK45" | integration method |
| rtol           | OPT     | -                     | 1e-08   | relative tolerance |
| atol           | OPT     | -                     | 1e-10   | absolute tolerance (state components have mixed units) |
| t_max          | OPT     | s                     | 300.0   | maximum simulated time |
| dt             | OPT     | s                     | 0.001   | step size; fixed-step path only |
| sample_rate_hz | OPT     | Hz                    | 0.0     | sampled-data mode rate; 0.0 = no sampled-data mode |
"""

from __future__ import annotations

from configs.schema import Airframe, Motor, Rocket, Scenario
from configs.sites import origin_msl
from configs.weather import isa_dry_calm
from sim.params import Thrust

# Normally you would import a registered rocket piece, e.g.:
#     from configs.rockets.demo import ROCKET  # <-- replace with your own once you have one
# This template builds a minimal placeholder rocket and motor inline
# instead. See configs/rockets/_TEMPLATE_rocket.py and
# configs/motors/_TEMPLATE_motor.py for every field, with comments.
_placeholder_rocket = Rocket(
    name="my_rocket",                  # REQ, - -- rename to match whatever rocket you actually use
    airframe=Airframe(m=1.5, I=0.08),  # REQ, Airframe group -- see _TEMPLATE_rocket.py for the full field set
)

_placeholder_motor = Motor(
    name="my_motor",  # REQ, - -- rename to match whatever motor you actually use
    thrust=Thrust(motor_curve="placeholder.csv"),  # REQ, Thrust group -- motor_curve names a file under data/motors/ (see _TEMPLATE_motor.py)
)

SCENARIO = Scenario(
    name="my_scenario",  # REQ, - -- registry key; rename to match the filename once you rename it

    rocket=_placeholder_rocket,    # REQ, Rocket piece -- your own Rocket, built inline or imported
    motor=_placeholder_motor,      # REQ, Motor piece -- your own Motor, see configs/motors/_TEMPLATE_motor.py
    site=origin_msl.SITE,          # REQ, LaunchSite piece -- swap for your own LaunchSite once you have one
    weather=isa_dry_calm.WEATHER,  # REQ, Weather piece -- swap for your own Weather once you have one

    # gravity, solver, g0 default to the constant/RK45/9.80665 trio
    # every demo scenario uses -- leave them unless you specifically
    # need a different integrator, tolerance, or gravity model.
    # gravity=Gravity(),  # OPT, Gravity group -- gravity model; default constant magnitude, parallel direction
    # solver=Solver(),    # OPT, Solver group -- integrator and tolerances; default RK45
    # g0=9.80665,         # OPT, m/s^2 -- standard gravity, shared constant

    overrides={},  # OPT, dict -- dotted-path tweaks applied AFTER assembly, e.g. {"site.rail_angle_deg": 85.0}
    # s0 defaults to None, which derives "on the pad, nose along the
    # rail" from site.rail_angle_deg (SS31.4) -- leave it unless you
    # need a non-pad initial state.
    # s0=None,  # OPT, State -- initial state; None = on the pad, nose along the rail

    notes=(
        "My actual scenario -- <say what this combination is for and "
        "where the numbers came from>."
    ),  # OPT, - -- provenance: what this combination is for and where the numbers came from
)

CONFIG = SCENARIO.config
