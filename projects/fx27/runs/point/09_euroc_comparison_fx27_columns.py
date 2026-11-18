"""projects/fx27/runs/point/09_euroc_comparison_fx27_columns.py --
roadmap General id 1.9 (see projects/fx27/_docs/roadmap.md). euroc
point-mass comparison run script (<=24 runnable combos, CSV only, no
figures), extracted from the old consolidated runs/point/comparison.py's
`_run_euroc()` (Phase 2.27, architecture-43 SS43.5), itself replacing the
pre-Phase-2.27 runs/euroc/comparison.py.

Run: python -m projects.fx27.runs.point.09_euroc_comparison_fx27_columns [--validity]
"""
from __future__ import annotations

import argparse
import warnings

from apps._shared.artifacts import ensure_dir, output_dir
from apps.sim.engine.mach_warning import MachRangeWarning

from projects.fx27.data.euroc.scenarios import generate_scenarios as _euroc_generate_scenarios
from projects.fx27.solvers.point.comparison import print_table, run_many, save_csv
from projects.fx27.solvers.point.metrics import row_from_flight
from projects.fx27.solvers.point.validity import check_validity, print_validity


def main(argv=None) -> None:
    """Body = old runs/euroc/comparison.py main(), unchanged (<=24 rows, CSV only, no figures,
    deferred-combinations line). No --show here -- there is nothing to show, same as the old
    pre-consolidation euroc script never offering --show at all (euroc is never plotted)."""
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--validity", action="store_true",
        help="also print Option C's measured error bound per scenario (SS38.5.7)",
    )
    args = ap.parse_args(argv)

    scenarios, deferred = _euroc_generate_scenarios()

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always", MachRangeWarning)
        runs = run_many(scenarios)
    mach_warns = [w for w in caught if issubclass(w.category, MachRangeWarning)]

    rows = [row_from_flight(name, fr) for name, fr in runs.items()]
    print_table(rows, title=f"euroc point-mass comparison ({len(rows)} runnable combos)")

    if mach_warns:
        print(
            f"\nNOTE: {len(mach_warns)} of {len(rows)} scenarios exceeded Mach 0.8 under a "
            "Mach-independent drag model (C_x constant) -- those apogees are not credible "
            "above that point (SS38.4.4/R4, inherited from fx27)."
        )

    print(f"\n{len(deferred)} combination(s) deferred, motor data not ready: {', '.join(deferred)}")

    if args.validity:
        for name, fr in runs.items():
            print_validity(name, check_validity(fr.result, fr.cfg.params))

    out_dir = ensure_dir(output_dir())
    csv_path = out_dir / "fx27_euroc_comparison.csv"
    save_csv(rows, csv_path)
    print(f"\nSaved {csv_path}")


if __name__ == "__main__":
    main()
