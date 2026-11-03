"""projects/fx27/runs/cspace/comparison.py -- fx27 `runs/cspace/
point_comparison.py` equivalent (dev/docs/architecture-38-fx27-port.md
SS38.5.2, #12): the 7-row comparison table (3 base rockets + 4 ideal
variants) + both comparison figures.

Collects `MachRangeWarning`s (SS38.4.4/R4) into one printed summary line
rather than letting the 7 raw warnings scatter across the table -- the
warnings are correct (constant `C_x=0.5` is not credible past Mach 0.8)
and are surfaced, not suppressed.

Run: `python -m projects.fx27.runs.cspace.comparison [--validity]`.
"""

from __future__ import annotations

import argparse
import warnings

from apps._shared.artifacts import ensure_dir, output_dir
from apps.sim.engine.mach_warning import MachRangeWarning

from projects.fx27.campaigns.cspace.scenarios import SCENARIOS
from projects.fx27.point.comparison import print_table, run_many, save_csv
from projects.fx27.point.metrics import row_from_flight
from projects.fx27.point.plots import plot_displacement_comparison, plot_kinematics_comparison
from projects.fx27.point.validity import check_validity, print_validity


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--validity", action="store_true",
        help="also print Option C's measured error bound per scenario (SS38.5.7)",
    )
    args = ap.parse_args(argv)

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always", MachRangeWarning)
        runs = run_many(SCENARIOS)
    mach_warns = [w for w in caught if issubclass(w.category, MachRangeWarning)]

    rows = [row_from_flight(name, fr) for name, fr in runs.items()]
    print_table(rows, title="cspace point-mass comparison (7 rows)")

    if mach_warns:
        print(
            f"\nNOTE: {len(mach_warns)} of {len(rows)} scenarios exceeded Mach 0.8 under a "
            "Mach-independent drag model (C_x constant) -- those apogees are not credible "
            "above that point (SS38.4.4/R4, inherited from fx27)."
        )

    if args.validity:
        for name, fr in runs.items():
            print_validity(name, check_validity(fr.result, fr.cfg.params))

    out_dir = ensure_dir(output_dir())
    csv_path = out_dir / "fx27_cspace_comparison.csv"
    disp_path = out_dir / "fx27_cspace_displacement.png"
    kin_path = out_dir / "fx27_cspace_kinematics.png"
    save_csv(rows, csv_path)

    results = {name: fr.result for name, fr in runs.items()}
    plot_displacement_comparison(results, title="cspace displacement comparison").savefig(disp_path)
    plot_kinematics_comparison(results, title="cspace kinematics comparison").savefig(kin_path)

    print(f"\nSaved {csv_path}")
    print(f"Saved {disp_path}")
    print(f"Saved {kin_path}")


if __name__ == "__main__":
    main()
