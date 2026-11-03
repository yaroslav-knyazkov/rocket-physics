"""projects/fx27/campaigns/euroc/scenarios.py -- `CANDIDATES` (config -> candidate
motor ids) and `generate_scenarios()` (dev/docs/architecture-38-fx27-port.md
SS38.5.3 Variant A, SS38.7.1): one `Scenario` per runnable `(airframe
config, candidate motor)` pair, named `"<config>/<motor id>"` (SS38.5.3
condition 2's naming convention, applied here too so the dict key stays
consistent between Variant A and the renamed `Motor` pieces Variant B
builds in `runs/euroc/sweep.py`).

27 candidate (config, motor) pairs total (fx27 data/euroc/motors.py's own
candidate table); 3 are excluded here because their motor is in
`euroc.motors.DEFERRED_MOTORS` (SS38.7.1) -- 24 runnable, returned
separately as `DEFERRED` so a caller cannot mistake the runnable count for
the full candidate set (AC-6).
"""

from __future__ import annotations

from apps.sim.schema import Scenario

from projects.fx27.campaigns.euroc.motors import DEFERRED_MOTORS, MOTORS
from projects.fx27.campaigns.euroc.rockets import ROCKETS
from projects.fx27.campaigns.euroc.site import SITE
from projects.fx27.campaigns.euroc.weather import WEATHER

# config name -> candidate motor ids (fx27 data/euroc/motors.py's own
# per-config candidate list). Where fx27 numbered candidates "<config>_<i+1>"
# (1-indexed) for a config with more than one candidate, this dict's
# iteration order preserves that same ordering.
CANDIDATES: "dict[str, tuple[str, ...]]" = {
    "pro54_2G": ("pro54-838J293",),
    "pro54_3G": ("pro54-1211J140",),
    "pro54_6GXL": ("pro54-3147L935",),
    "pro75_2G": ("pro75-2412K1085", "pro75-2430K661"),
    "pro75_3G": ("pro75-3618L995", "pro75-3683L851", "pro75-3727L1050"),
    "pro75_4G": (
        "pro75-4025L1355",
        "pro75-4864L2375",
        "pro75-4895L1395",
        "pro75-5015L1115",
        "pro75-5198M1101",
        "pro75-5506M1230",
    ),
    "pro75_5G": ("pro75-6026M1670", "pro75-6128M1810"),
    "pro75_6GXL": ("pro75-9977M2245",),
    "pro98_3G": ("pro98-7441M1060", "pro98-7450M2505", "pro98-7649M1290"),
    "pro98_4G": ("pro98-9876M1890", "pro98-9955M1450"),
    "pro98_6G": ("pro98-14200N3180", "pro98-15227N2501"),
    "pro98_6GXL": ("pro98-17790N4100", "pro98-17907N2540", "pro98-19318N3301"),
}


def generate_scenarios() -> "tuple[dict[str, Scenario], tuple[str, ...]]":
    """One `Scenario` per runnable `(config, motor)` pair, named
    `"<config>/<motor id>"`. Returns `(scenarios, deferred)`: `deferred`
    holds the same `"<config>/<motor id>"` names for every pair excluded
    because its motor is in `DEFERRED_MOTORS` (SS38.7.1/AC-6) -- printed
    by `runs/euroc/comparison.py` under the comparison table.
    """
    scenarios: "dict[str, Scenario]" = {}
    deferred: "list[str]" = []
    for config_name, motor_ids in CANDIDATES.items():
        rocket = ROCKETS[config_name]
        for motor_id in motor_ids:
            name = f"{config_name}/{motor_id}"
            if motor_id in DEFERRED_MOTORS:
                deferred.append(name)
                continue
            scenarios[name] = Scenario(
                name=name,
                rocket=rocket,
                motor=MOTORS[motor_id],
                site=SITE,
                weather=WEATHER,
                notes=f"euroc candidate: {config_name} airframe + {motor_id} motor (fx27 data/euroc/motors.py).",
            )
    return scenarios, tuple(deferred)
