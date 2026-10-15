"""configs/scenarios/demo.py -- the one demo: the real CTI K570 flown on the
new 54 mm airframe (Phase 2.16, Step 81, renamed `demo` at Step 89, D-80;
dev/docs/architecture-32-motor-separation.md SS32.2.3/SS32.3.3/SS32.3.4).

Pairs `configs.rockets.demo.ROCKET` with
`configs.motors.cti_k570.MOTOR` -- the "endpoints" mass model, deriving
`I_sp` from the K570's own total impulse rather than a hand-entered
number (`cti_k570_isp.MOTOR` is the sibling motor for the D-59
"isp" vs "endpoints" equivalence check, `tests/test_config_migration.py`,
not this scenario's own motor) -- at `origin_msl`/`isa_dry_calm`, the same
"pin the defaults" site/weather pair every other demo scenario uses.

Mach caveat (D-83): this K570 on a 1.5 kg airframe reaches roughly Mach
2.6 (apogee ~5.95 km), but the airframe's aero model is `"constant"`
(C_x = 0.5, not Mach-dependent), which is not credible above ~Mach 0.8.
The numbers are kept as built; a run that exceeds Mach 0.8 under a
Mach-independent drag model warns at run time (Step 92).
"""

from __future__ import annotations

from configs.motors.cti_k570 import MOTOR
from configs.rockets import demo
from configs.schema import Config, Scenario
from configs.sites import origin_msl
from configs.weather import isa_dry_calm

SCENARIO = Scenario(
    name="demo",
    rocket=demo.ROCKET,
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
