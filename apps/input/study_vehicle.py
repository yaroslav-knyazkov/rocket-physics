"""apps/input/study_vehicle.py -- the constant-mass study vehicle (Phase
2.16, Step 86, dev/docs/architecture-33-configs-one-demo.md SS33.3.1, D-79;
moved here from apps/common/study_vehicle.py at Phase 2.19 Step 131,
dev/docs/architecture-apps-sim-restructure.md).

The 1.5 kg / 75 mm vehicle that Apps 3 and 5 (and the tests of Apps 3/4/5)
study. It is a STUDY INPUT, the same kind as
`apps/optimization/motor_selection/motors.py::MOTORS`,
`apps/analysis/weight_aero_tradeoff/scenarios.py::SCENARIOS` and
`apps/optimization/airbrake_sizing/targets.py::SPECS`: it is not registered
in `configs/`, not listed by `--list-configs`, and not a template for users.

Provenance (carried over from the former `configs/rockets/demo_75mm.py` and
`configs/motors/placeholder.py`): copied number-for-number, including its
justifying docstring, from `apps/optimization/motor_selection/
compare_motors.py`'s `_demo_baseline()` (D-26, user-approved at Step 62).
The mass model is OFF
(`m_d=None`, constant mass): the motor is `Thrust(motor_curve=
"placeholder.csv")`, "replaced per entry; never read as-is", since every
App-3 caller overrides `thrust.motor_curve` per `MotorEntry` before running.
It still flies on its own (162.75 N*s on 1.5 kg clears the pad easily).
Do NOT change `motor_curve` to `"synthetic_large.csv"`: the exact-equality
pin in `tests/test_schema.py` depends on it staying `"placeholder.csv"`.
`sections` is left at its default -- no measured section geometry.

`s0` is omitted (derives "on the pad, nose along the rail" from
`origin_msl`'s default `rail_angle_deg=90.0`, `math.radians(90.0) ==
math.pi / 2`).
"""

from __future__ import annotations

from apps.sim.schema import Airframe, Config, LaunchSite, Motor, Rocket, Scenario, Weather
from apps.sim.engine.params import Aero, Lengths, Site, Thrust

# Step 124 (Phase 2.18, D-139/CLI-1): inlined, not imported from
# `configs/sites/origin_msl.py` / `configs/weather/isa_dry_calm.py` (the
# registry subpackages this app no longer needs). Both are still
# argument-free (`Site()`, bare `Weather(name=...)`), matching those two
# modules' own deliberate choice to track `sim/params.py`'s defaults
# rather than freeze them (see those modules' docstrings) -- this is a
# literal copy of that choice, not a new one.
_ORIGIN_MSL_SITE = LaunchSite(name="origin_msl", site=Site())
_ISA_DRY_CALM_WEATHER = Weather(name="isa_dry_calm")

ROCKET = Rocket(
    name="study_75mm",
    airframe=Airframe(m=1.5, I=0.08),              # launch mass, mass model OFF (m_d=None)
    lengths=Lengths(l1=0.3, l2=0.4),
    # sections left at its default -- no measured section geometry for
    # this rocket.
    aero=Aero(
        S=0.00442, d_ref=0.075, l_ref=0.75,        # 75 mm body: S = pi*d^2/4 = 0.004418 m^2
        C_x=0.5, C_z=0.0, C_m=0.0,
    ),
)

MOTOR = Motor(
    name="placeholder",
    thrust=Thrust(motor_curve="placeholder.csv"),  # replaced per entry; never read as-is
    # mass_model left at its default "none" -- constant-mass flight.
)

SCENARIO = Scenario(
    name="study_75mm",
    rocket=ROCKET,
    motor=MOTOR,
    site=_ORIGIN_MSL_SITE,
    weather=_ISA_DRY_CALM_WEATHER,
    notes=(
        "The architect's own synthetic 1.5 kg / 75 mm vehicle. Deliberately "
        "NOT run.py's 0.5 kg toy scenario: 338 N*s (the largest new fixture) "
        "on 0.5 kg gives an ideal delta-v of ~676 m/s (~Mach 2), where a "
        "constant C_x = 0.5 is not a defensible aerodynamic model and the "
        "ISA extrapolation ceiling starts to matter. 1.5 kg keeps every "
        "fixture subsonic (largest motor: ideal delta-v ~225 m/s before "
        "gravity/drag losses, <~ Mach 0.7) while still leaving the smallest "
        "motor just barely flyable -- itself informative. C_z = C_m = 0.0 "
        "makes this a vertical, attitude-frozen 1-D shot, the same "
        "simplification run.py and App 2 already carry, appropriate for a "
        "motor comparison (one variable at a time) and, per SS29.4.1/F5, "
        "the reason the ascent window is mandatory."
    ),
)

CONFIG: Config = SCENARIO.config
