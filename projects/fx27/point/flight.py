"""projects/fx27/point/flight.py -- one flight: assemble + run_sim + stats
(fx27's `point/core.build_flight` + `flight_metrics`, dev/docs/
architecture-38-fx27-port.md SS38.5.1).

`(a)` direct calls into `apps.sim.schema.assemble` and
`apps.sim.engine.integrate.run_sim` -- `rail_length`/`inclination`/
`heading` are not arguments here because they live on the `Scenario`'s
own `LaunchSite` piece, which is the better factoring this port keeps.
"""

from __future__ import annotations

import dataclasses

from apps.sim.schema import Config, Scenario, assemble
from apps.sim.engine.integrate import Result, run_sim
from apps._shared.flight_stats import FlightStats, flight_stats


@dataclasses.dataclass(frozen=True)
class FlightRun:
    """Everything one `run()` call produces -- the config actually flown,
    the raw trajectory, and the ascent-window stats bundle."""

    cfg: Config
    result: Result
    stats: FlightStats


def run(scenario: Scenario) -> FlightRun:
    """`assemble(scenario) -> run_sim -> flight_stats`, fx27's
    `build_flight` + `flight_metrics` in three calls (SS38.5.1)."""
    cfg = assemble(scenario)
    result = run_sim(cfg.params, cfg.s0)
    stats = flight_stats(result, cfg.params)
    return FlightRun(cfg=cfg, result=result, stats=stats)
