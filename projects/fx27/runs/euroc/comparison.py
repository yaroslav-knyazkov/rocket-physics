"""projects/fx27/runs/euroc/comparison.py -- fx27 `runs/euroc/
point_comparison.py` equivalent, Variant A (dev/docs/architecture-38-
fx27-port.md SS38.5.3, #16): fx27's own column set over every runnable
`(config, motor)` combo (24 of 27 -- 3 deferred on not-yet-supplied motor
data, SS38.7.1), with the deferred list printed explicitly under the
table (AC-6: never silently absent).

Run: `python -m projects.fx27.runs.euroc.comparison [--validity]`.
"""

from __future__ import annotations

import argparse
import warnings

from apps._shared.artifacts import ensure_dir, output_dir
from apps.sim.engine.mach_warning import MachRangeWarning

from projects.fx27.campaigns.euroc.scenarios import generate_scenarios
from projects.fx27.point.comparison import print_table, run_many, save_csv
from projects.fx27.point.metrics import row_from_flight
from projects.fx27.point.validity import check_validity, print_validity


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--validity", action="store_true",
        help="also print Option C's measured error bound per scenario (SS38.5.7) -- "
        "costs 24 extra dense passes",
    )
    args = ap.parse_args(argv)

    scenarios, deferred = generate_scenarios()

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
