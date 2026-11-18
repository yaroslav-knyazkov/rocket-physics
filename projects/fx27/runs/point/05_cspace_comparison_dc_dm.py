"""projects/fx27/runs/point/05_cspace_comparison_dc_dm.py -- roadmap
General id 1.5 (see projects/fx27/_docs/roadmap.md). cspace point-mass
dc-vs-dm comparison run script (14 scenarios), extracted from the old
consolidated runs/point/comparison.py's `_run_cspace_dc_dm()` (Phase 2.27,
architecture-43 SS43.5), itself replacing the pre-Phase-2.27
runs/cspace/comparison_dc_dm.py.

Run: python -m projects.fx27.runs.point.05_cspace_comparison_dc_dm [--validity] [--show]
"""
from __future__ import annotations

import argparse
import warnings

from apps._shared.artifacts import ensure_dir, output_dir
from apps.sim.engine.mach_warning import MachRangeWarning, peak_mach

from projects.fx27.data.cspace.scenarios import SCENARIOS as _CSPACE_SCENARIOS
from projects.fx27.data.cspace.scenarios_dm import SCENARIOS_DM as _CSPACE_SCENARIOS_DM
from projects.fx27.solvers.point.comparison import print_table, run_many, save_csv
from projects.fx27.solvers.point.metrics import row_from_flight
from projects.fx27.solvers.point.plots import (
    plot_displacement_comparison, plot_kinematics_comparison, show_if_requested,
)
from projects.fx27.solvers.point.validity import check_validity, print_validity


def main(argv=None) -> None:
    """Body = old runs/cspace/comparison_dc_dm.py main(), unchanged (14 rows, 2 figures, 1 CSV,
    2 warning notes: dc caveat + dm informational)."""
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--validity", action="store_true",
        help="also print Option C's measured error bound per scenario (SS38.5.7)",
    )
    ap.add_argument(
        "--show", action="store_true",
        help="also display the figures interactively (in addition to saving them)",
    )
    args = ap.parse_args(argv)

    all_scenarios = {**_CSPACE_SCENARIOS, **_CSPACE_SCENARIOS_DM}

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always", MachRangeWarning)
        runs = run_many(all_scenarios)
    mach_warns = [w for w in caught if issubclass(w.category, MachRangeWarning)]

    rows = [row_from_flight(name, fr) for name, fr in runs.items()]
    print_table(rows, title="cspace dc-vs-dm comparison (14 rows)")

    if mach_warns:
        print(
            f"\nNOTE: {len(mach_warns)} dc row(s) exceeded Mach 0.8 under a Mach-blind "
            "drag model (C_x constant) -- those apogees are not credible above that point "
            "(SS38.4.4/R4, inherited from fx27)."
        )
    dm_supersonic = [
        name for name, fr in runs.items()
        if name in _CSPACE_SCENARIOS_DM and peak_mach(fr.result)[0] > 0.8
    ]
    if dm_supersonic:
        print(
            f"\nNOTE (informational, NOT a caveat): {len(dm_supersonic)} dm row(s) reached "
            f"Mach > 0.8 ({', '.join(dm_supersonic)}) -- their drag is Mach-dependent "
            "(aero.model=\"table\"), so this does not affect credibility."
        )

    if args.validity:
        for name, fr in runs.items():
            print_validity(name, check_validity(fr.result, fr.cfg.params))

    out_dir = ensure_dir(output_dir())
    csv_path = out_dir / "fx27_cspace_dc_dm_comparison.csv"
    disp_path = out_dir / "fx27_cspace_dc_dm_displacement.png"
    kin_path = out_dir / "fx27_cspace_dc_dm_kinematics.png"
    save_csv(rows, csv_path)

    results = {name: fr.result for name, fr in runs.items()}
    plot_displacement_comparison(results, title="cspace dc-vs-dm displacement comparison").savefig(disp_path)
    plot_kinematics_comparison(results, title="cspace dc-vs-dm kinematics comparison").savefig(kin_path)

    print(f"\nSaved {csv_path}")
    print(f"Saved {disp_path}")
    print(f"Saved {kin_path}")

    show_if_requested(args.show)


if __name__ == "__main__":
    main()
