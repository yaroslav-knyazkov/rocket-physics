"""projects/fx27/runs/cspace_point.py -- fx27 `runs/cspace/point.py`
equivalent (dev/docs/architecture-38-fx27-port.md SS38.5.1, #11): one
flight, summary + trajectory + time-history plots.

No 3D trajectory plot here: this engine's 2D model has no 3D state, and
with no wind the fx27 flight was planar anyway, so the 3D figure there
carried no information `plot_trajectory` doesn't already have
(SS38.5.1/SS38.13's rejected-options table).

Run: `python -m projects.fx27.runs.cspace_point [--scenario NAME]
[--validity]`.
"""

from __future__ import annotations

import argparse

from apps._shared.artifacts import ensure_dir, output_dir
from apps.sim.engine.plotting import plot_time_histories, plot_trajectory
from apps.sim.engine.report import print_run_summary

from projects.fx27.cspace.scenarios import SCENARIOS
from projects.fx27.point.flight import run as run_flight
from projects.fx27.point.validity import check_validity, print_validity


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--scenario", default="pro75", choices=sorted(SCENARIOS))
    ap.add_argument(
        "--validity", action="store_true",
        help="also print Option C's measured error bound (SS38.5.7) -- costs an extra dense pass",
    )
    args = ap.parse_args(argv)

    fr = run_flight(SCENARIOS[args.scenario])
    print_run_summary(fr.result, fr.cfg.params, fr.cfg.s0)

    if args.validity:
        print_validity(args.scenario, check_validity(fr.result, fr.cfg.params))

    out_dir = ensure_dir(output_dir())
    traj_path = out_dir / f"fx27_cspace_{args.scenario}_trajectory.png"
    hist_path = out_dir / f"fx27_cspace_{args.scenario}_time_histories.png"
    plot_trajectory(fr.result).savefig(traj_path)
    plot_time_histories(fr.result).savefig(hist_path)
    print(f"\nSaved {traj_path}")
    print(f"Saved {hist_path}")


if __name__ == "__main__":
    main()
