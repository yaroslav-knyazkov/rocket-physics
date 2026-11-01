"""projects/fx27/point/metrics.py -- `Row`, fx27's 9-key
`flight_metrics` column set reduced from a `FlightRun` (dev/docs/
architecture-38-fx27-port.md SS38.5.1/SS38.5.2/SS38.2.9).

All 8 fx27 flight metrics are covered by
`apps._shared.flight_stats.FlightStats` (SS38.2.9); the two non-flight
keys (`mass`, `total_mass`) are read straight off the assembled
`Params.weight` group, not re-derived.
"""

from __future__ import annotations

import dataclasses

from .flight import FlightRun


@dataclasses.dataclass(frozen=True)
class Row:
    name: str
    mass: "float | None"  # kg, dry (Params.weight.m_d; falls back to m if the mass model were off)
    total_mass: "float | None"  # kg, wet (Params.weight.m)
    apogee_agl: "float | None"  # m -- fx27's apogee_agl; already AGL (gravity.altitude_agl)
    apogee_time: "float | None"  # s -- fx27's apogee_time
    max_speed: "float | None"  # m/s -- fx27's max_speed, ascent window
    max_acceleration: "float | None"  # m/s^2 -- fx27's max_acceleration
    max_mach: "float | None"  # -- fx27's max_mach
    out_of_rail_velocity: "float | None"  # m/s -- fx27's out_of_rail_velocity; None when no rail


def row_from_flight(name: str, fr: FlightRun) -> Row:
    """Reduce one `FlightRun` to fx27's column set, under `name` (the
    comparison-table key -- the scenario name, not necessarily the
    `Rocket` piece's own `.name`)."""
    w = fr.cfg.params.weight
    s = fr.stats
    dry = w.m_d if w.m_d is not None else w.m
    return Row(
        name=name,
        mass=dry,
        total_mass=w.m,
        apogee_agl=s.apogee_altitude,
        apogee_time=s.apogee_time,
        max_speed=s.max_velocity,
        max_acceleration=s.max_accel,
        max_mach=s.max_mach,
        out_of_rail_velocity=s.rail_exit_speed,
    )
