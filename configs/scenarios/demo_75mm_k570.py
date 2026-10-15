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

import dataclasses

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

# `_pad_state` (configs/schema.py) does not yet set the derived `s0.m`
# from the composed `weight.m` -- an open backlog item
# (dev/docs/architecture-32-motor-separation.md SS32.10, "backlog candidates
# this phase opens": "s0.m derived from weight.m"). Every scenario
# registered so far leaves `m_d=None`, so `y[M]` is never read and
# `s0.m`'s harmless `0.0` default never mattered; this is the first
# scenario whose mass model is ON, so it is also the first that needs
# the initial state's own mass populated, or integration starts the
# propellant mass at a large negative number instead of `weight.m`
# (SS32.3.3 point 2: `Weight.m` is the loaded, t=0 vehicle mass). Patched
# here, locally -- not in `configs/schema.py`, out of this ticket's
# boundaries -- by taking `_pad_state`'s own derived `s0` (rail-angle
# theta included) and filling in the one field it leaves at its default.
# `State` is a `NamedTuple` (`sim/state.py`), not a dataclass, so its own
# `._replace` does the job -- `dataclasses.replace` only applies to `_config`.
_config = SCENARIO.config
CONFIG: Config = dataclasses.replace(
    _config, s0=_config.s0._replace(m=_config.params.weight.m)
)
