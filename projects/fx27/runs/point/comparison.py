"""projects/fx27/runs/point/comparison.py -- point-mass comparison run
script for both competitions (Phase 2.27 reorg, architecture-43 SS43.5).
Replaces 3 scripts:
  - runs/cspace/comparison.py        -> --case cspace       (default)
  - runs/cspace/comparison_dc_dm.py  -> --case cspace_dc_dm
  - runs/euroc/comparison.py         -> --case euroc

Run: python -m projects.fx27.runs.point.comparison [--case {cspace,cspace_dc_dm,euroc}] [--validity] [--show]
"""
from __future__ import annotations

import argparse
import warnings

from apps._shared.artifacts import ensure_dir, output_dir
from apps.sim.engine.mach_warning import MachRangeWarning, peak_mach

from projects.fx27.campaigns.cspace.scenarios import SCENARIOS as _CSPACE_SCENARIOS
from projects.fx27.campaigns.cspace.scenarios_dm import SCENARIOS_DM as _CSPACE_SCENARIOS_DM
from projects.fx27.campaigns.euroc.scenarios import generate_scenarios as _euroc_generate_scenarios
from projects.fx27.solvers.point.comparison import print_table, run_many, save_csv
from projects.fx27.solvers.point.metrics import row_from_flight
from projects.fx27.solvers.point.plots import (
    plot_displacement_comparison, plot_kinematics_comparison, show_if_requested,
)
from projects.fx27.solvers.point.validity import check_validity, print_validity


def _run_cspace(args: argparse.Namespace) -> None:
    """Body = old runs/cspace/comparison.py main(), unchanged (7 rows, 2 figures, 1 CSV)."""
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always", MachRangeWarning)
        runs = run_many(_CSPACE_SCENARIOS)
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

    show_if_requested(args.show)


def _run_cspace_dc_dm(args: argparse.Namespace) -> None:
    """Body = old runs/cspace/comparison_dc_dm.py main(), unchanged (14 rows, 2 figures, 1 CSV,
    2 warning notes: dc caveat + dm informational)."""
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


def _run_euroc(args: argparse.Namespace) -> None:
    """Body = old runs/euroc/comparison.py main(), unchanged (<=24 rows, CSV only, no figures,
    deferred-combinations line). args.show is accepted but unused here -- there is nothing to
    show, same as the old script never offering --show at all."""
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


_CASES = {"cspace": _run_cspace, "cspace_dc_dm": _run_cspace_dc_dm, "euroc": _run_euroc}


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--case", default="cspace", choices=sorted(_CASES))
    ap.add_argument(
        "--validity", action="store_true",
        help="also print Option C's measured error bound per scenario (SS38.5.7)",
    )
    ap.add_argument(
        "--show", action="store_true",
        help="also display the figures interactively (in addition to saving them; ignored for --case euroc)",
    )
    args = ap.parse_args(argv)
    _CASES[args.case](args)


if __name__ == "__main__":
    main()
