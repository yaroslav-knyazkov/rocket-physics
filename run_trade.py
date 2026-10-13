"""run_trade.py -- entry point 5 of 5: weight vs aero (roadmap.md Steps
67-68; docs/architecture-30-apps-4-5-and-configs.md SS30.3).

Thin root-level wrapper (D-29): `apps/weight_aero_tradeoff/` keeps its
own `python -m apps.weight_aero_tradeoff.trade_surface` invocation and
its own `main(argv)` (architecture.md SS30.7.1); this file is the front
door `python run_trade.py` adds on top, not a second implementation.

`--mode` picks which of App 5's two deliverables (D-38, both modes,
surface first) to run:

- `"surface"` (the default) -- mode (b), the 2-D weight-vs-aero trade
  surface and its iso-apogee exchange rate (Step 67, this step). Forwards
  every other argument (`--config`, `--list-configs`, ...) unchanged to
  `apps.weight_aero_tradeoff.trade_surface.main`, which owns that
  parsing itself (`apps/common/cli.py`) -- this wrapper only adds
  `--mode` on top, it does not re-implement `--config`.
- `"compare"` -- mode (a), the named-scenario comparison
  (`compare_configs.py`). **Not built in this step** (Step 68): selecting
  it raises `NotImplementedError` naming the step that will add it,
  rather than silently doing nothing.
"""

from __future__ import annotations

import argparse


def main(argv: "list[str] | None" = None) -> None:
    parser = argparse.ArgumentParser(
        description="App 5: weight-vs-aero trade-off (run_trade.py)",
    )
    parser.add_argument(
        "--mode",
        choices=("surface", "compare"),
        default="surface",
        help="'surface' (default, Step 67): the 2-D weight-vs-aero trade "
        "surface and its exchange rate. 'compare' (Step 68, not yet "
        "built): named-scenario side-by-side comparison.",
    )
    args, remaining = parser.parse_known_args(argv)

    if args.mode == "compare":
        raise NotImplementedError(
            "run_trade.py --mode compare is App 5 mode (a), named-scenario "
            "comparison (apps/weight_aero_tradeoff/compare_configs.py) -- "
            "not implemented yet (roadmap.md Step 68). Use --mode surface "
            "(the default) for the trade surface."
        )

    from apps.weight_aero_tradeoff.trade_surface import main as surface_main

    surface_main(remaining)


if __name__ == "__main__":
    main()
