"""configs/scenarios/demo_75mm_k570.py -- the real CTI K570 flown on the
new 54 mm airframe (Phase 2.16, Step 81,
dev/docs/architecture-32-motor-separation.md SS32.2.3/SS32.3.3/SS32.3.4).

Pairs `configs.rockets.demo_75mm_k570.ROCKET` with
`configs.motors.cti_k570.MOTOR` -- the "endpoints" mass model, deriving
`I_sp` from the K570's own total impulse rather than a hand-entered
number (`cti_k570_isp.MOTOR` is the sibling motor for the D-59
"isp" vs "endpoints" equivalence check, `tests/test_config_migration.py`,
not this scenario's own motor) -- at `origin_msl`/`isa_dry_calm`, the same
"pin the defaults" site/weather pair every other demo scenario uses.
"""

from __future__ import annotations

from configs.motors.cti_k570 import MOTOR
from configs.rockets import demo_75mm_k570
from configs.schema import Config, Scenario
from configs.sites import origin_msl
from configs.weather import isa_dry_calm

SCENARIO = Scenario(
    name="demo_75mm_k570",
    rocket=demo_75mm_k570.ROCKET,
    motor=MOTOR,
    site=origin_msl.SITE,
    weather=isa_dry_calm.WEATHER,
    notes=(
        "A real vendor motor (Cesaroni K570), its own mass history read "
        "from its own RASP file, composed with an airframe that knows "
        "where the motor sits -- the mass model is ON from a config for "
        "the first time (SS32.3.3)."
    ),
)

# `assemble` seeds `s0.m` from the composed `weight.m` (D-76).
CONFIG: Config = SCENARIO.config
