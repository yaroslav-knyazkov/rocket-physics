"""configs/scenarios/demo_75mm.py -- the architect's own synthetic 1.5 kg
/ 75 mm scenario (Step 63, roadmap.md,
`dev/docs/architecture-30-apps-4-5-and-configs.md` SS30.4; split into a
`Scenario` composing the `demo_75mm` rocket piece at Step 73,
`dev/docs/architecture-31-config-separation.md` SS31.7).

The vehicle numbers (and the `thrust.motor_curve="placeholder.csv"`
judgment call -- see that module's docstring) live in
`configs/rockets/demo_75mm.py` now; this module pairs that piece with the
two "pin the defaults" pieces (`configs.sites.origin_msl`,
`configs.weather.isa_dry_calm`) and carries the scenario-level
provenance -- the `notes` string below is kept byte-for-byte identical
to the original flat `Config`'s, because `--list-configs` and App 5's
comparison table print its first line.

`s0` is omitted (derives "on the pad, nose along the rail" from
`origin_msl`'s default `rail_angle_deg=90.0`, SS31.4/D-51a) --
`tests/test_configs.py::test_demo_75mm_s0_pins_compare_motors_main_literal_exactly`
is what proves this reproduces the original `s0` bit-for-bit
(`math.radians(90.0) == math.pi / 2`, F6).
"""

from __future__ import annotations

from configs.rockets import demo_75mm
from configs.schema import Config, Scenario
from configs.sites import origin_msl
from configs.weather import isa_dry_calm

SCENARIO = Scenario(
    name="demo_75mm",
    rocket=demo_75mm.ROCKET,
    site=origin_msl.SITE,
    weather=isa_dry_calm.WEATHER,
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
