"""configs/scenarios/toy_05kg.py -- run.py's / App 2's historical
placeholder scenario (Step 63, roadmap.md,
`dev/docs/architecture-30-apps-4-5-and-configs.md` SS30.4; split into a
`Scenario` composing the `toy_05kg` rocket piece at Step 73,
`dev/docs/architecture-31-config-separation.md` SS31.7).

The vehicle numbers live in `configs/rockets/toy_05kg.py` now; this module
pairs that piece with the two "pin the defaults" pieces
(`configs.sites.origin_msl`, `configs.weather.isa_dry_calm`) and carries
the scenario-level provenance -- the `notes` string below is kept
byte-for-byte identical to the original flat `Config`'s, because
`--list-configs` and App 5's comparison table print its first line.

`s0` is omitted (derives "on the pad, nose along the rail" from
`origin_msl`'s default `rail_angle_deg=90.0`, SS31.4/D-51a) --
`tests/test_configs.py::test_toy_05kg_s0_pins_run_py_literal_exactly`
is what proves this reproduces the original `s0` bit-for-bit
(`math.radians(90.0) == math.pi / 2`, F6).
"""

from __future__ import annotations

from configs.rockets import toy_05kg
from configs.schema import Config, Scenario
from configs.sites import origin_msl
from configs.weather import isa_dry_calm

SCENARIO = Scenario(
    name="toy_05kg",
    rocket=toy_05kg.ROCKET,
    site=origin_msl.SITE,
    weather=isa_dry_calm.WEATHER,
    notes=(
        "run.py's / App 2's historical placeholder scenario: a generic "
        "small model-rocket scale, unchanged since Step 1/Step 4."
    ),
)

CONFIG: Config = SCENARIO.config
