"""projects/fx27/runs/cspace/comparison_dc_dm.py -- dc-vs-dm side-by-side
comparison (dev/docs/architecture-40-fx27-campaigns-and-dm-drag.md SS40.6):
all 14 rows (scenarios.SCENARIOS's existing 7 + scenarios_dm.SCENARIOS_DM's
new 7), one table + the two existing comparison figures (point/plots.py
already treats every "<family>_dm" name as its own family/colour, SS40.4,
so the dc/dm pairs land side by side with no point/ change).

Unlike runs/cspace/comparison.py's single Mach-warning summary line (every
dc row uses aero.model="constant", so a Mach>0.8 flight always warns),
this script's dm rows use aero.model="table" and are EXEMPT from
MachRangeWarning (apps/sim/engine/mach_warning.py: "table" is Mach-aware
by construction, _MACH_INDEPENDENT_MODELS = ("constant", "linearized")) --
the printed summary is split into a dc caveat line and a dm informational
line so a reader does not read "Mach > 0.8" as a caveat for the rows where
it specifically is not one.

Run: `python -m projects.fx27.runs.cspace.comparison_dc_dm [--validity]`.
"""

from __future__ import annotations

import argparse
import warnings

from apps._shared.artifacts import ensure_dir, output_dir
from apps.sim.engine.mach_warning import MachRangeWarning, peak_mach

from projects.fx27.campaigns.cspace.scenarios import SCENARIOS
from projects.fx27.campaigns.cspace.scenarios_dm import SCENARIOS_DM
from projects.fx27.point.comparison import print_table, run_many, save_csv
from projects.fx27.point.metrics import row_from_flight
from projects.fx27.point.plots import plot_displacement_comparison, plot_kinematics_comparison
from projects.fx27.point.validity import check_validity, print_validity

_ALL = {**SCENARIOS, **SCENARIOS_DM}


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--validity", action="store_true",
        help="also print Option C's measured error bound per scenario (SS38.5.7)",
    )
    args = ap.parse_args(argv)

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always", MachRangeWarning)
        runs = run_many(_ALL)
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
        if name in SCENARIOS_DM and peak_mach(fr.result)[0] > 0.8
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


if __name__ == "__main__":
    main()
