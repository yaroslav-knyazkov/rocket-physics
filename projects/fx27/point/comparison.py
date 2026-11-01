"""projects/fx27/point/comparison.py -- fx27's `point_comparison.
evaluate_rockets` + `print_table` (dev/docs/architecture-38-fx27-port.md
SS38.5.2/SS38.5.3 Variant A): one loop over `flight.run` + `metrics.
row_from_flight`, reused verbatim by both the cspace 7-row table and the
euroc 24-row table.

Deliberately NOT `apps.optimization.motor_selection.compare_motors.
compare_motors` -- that refuses a mass-model-on baseline (SS38.2.6/
SS38.4.2), and the mass model must be ON for fx27 parity. This is the
single most important "don't reuse that" in the port (SS38.5.2).
"""

from __future__ import annotations

import csv
from pathlib import Path

from apps.sim.schema import Scenario

from .flight import FlightRun, run as run_flight
from .metrics import Row, row_from_flight


def run_many(scenarios: "dict[str, Scenario]") -> "dict[str, FlightRun]":
    """One flight per scenario -- the shared pass every caller needing
    both the table rows and the raw `Result`s (for the comparison plots)
    should use, rather than flying each scenario twice."""
    return {name: run_flight(sc) for name, sc in scenarios.items()}


def evaluate_scenarios(scenarios: "dict[str, Scenario]") -> "list[Row]":
    """`fx27.point_comparison.evaluate_rockets`: one `Row` per scenario,
    in the dict's own iteration order."""
    return [row_from_flight(name, fr) for name, fr in run_many(scenarios).items()]


def _f(x, spec: str) -> str:
    return "      -" if x is None else format(x, spec)


def print_table(rows: "list[Row]", title: str = "fx27 point-mass comparison") -> None:
    """Fixed-width printed table, the house style
    (`apps.optimization.motor_selection.scenario_sweep.print_table`'s
    idiom copied in spirit, not in code -- the column sets differ,
    SS38.5.2)."""
    head = (
        f"{'name':<32}{'m_dry[kg]':>11}{'m_wet[kg]':>11}{'apogee[m]':>11}"
        f"{'t_apo[s]':>10}{'vmax[m/s]':>11}{'amax[m/s2]':>12}{'Mmax':>7}{'vrail[m/s]':>12}"
    )
    print(f"\n{title}:")
    print(head)
    print("-" * len(head))
    for r in rows:
        print(
            f"{r.name:<32}{_f(r.mass, '11.3f')}{_f(r.total_mass, '11.3f')}{_f(r.apogee_agl, '11.1f')}"
            f"{_f(r.apogee_time, '10.2f')}{_f(r.max_speed, '11.1f')}{_f(r.max_acceleration, '12.1f')}"
            f"{_f(r.max_mach, '7.2f')}{_f(r.out_of_rail_velocity, '12.1f')}"
        )


def save_csv(rows: "list[Row]", path: Path) -> None:
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(
            (
                "name", "mass", "total_mass", "apogee_agl", "apogee_time",
                "max_speed", "max_acceleration", "max_mach", "out_of_rail_velocity",
            )
        )
        for r in rows:
            w.writerow(
                (
                    r.name, r.mass, r.total_mass, r.apogee_agl, r.apogee_time,
                    r.max_speed, r.max_acceleration, r.max_mach, r.out_of_rail_velocity,
                )
            )
