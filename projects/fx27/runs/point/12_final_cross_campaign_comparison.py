"""projects/fx27/runs/point/12_final_cross_campaign_comparison.py --
roadmap General id 1.12 (see projects/fx27/_docs/roadmap.md). Final
cross-campaign comparison -- a thin orchestrator that runs cspace (dc),
cspace (dc+dm), and euroc one after another, so a single invocation
gives "the full picture" once configurations are locked in (S46.7's
reading (b), confirmed by the user: this id earns its own file because
no single existing id reports all three campaigns together).

Imports `01_cspace_comparison_dc`, `05_cspace_comparison_dc_dm`, and
`09_euroc_comparison_fx27_columns` as modules via `importlib` (not a
source-level `from ... import main` statement, which would be a
SyntaxError -- a module name starting with a digit is not a valid
Python identifier in import-statement syntax, even though `python -m`
and `importlib.import_module` resolve it fine as a plain dotted string)
and calls each one's own `main()` in sequence, printing a one-line
banner between each so the three sections are easy to tell apart in the
combined console output.

This script owns its own `--validity`/`--show` flags rather than letting
the three sub-scripts fall back to parsing the real `sys.argv`: each
sub-`main(argv)` is called with an explicit, per-section argv list built
from this script's own parsed flags, since 09 (euroc) has no `--show`
flag at all (euroc is never plotted) -- passing it `--show` would raise
argparse's unrecognized-argument `SystemExit` and abort the run after
the first two sections already printed.

Run: `python -m projects.fx27.runs.point.12_final_cross_campaign_comparison [--validity] [--show]`.
"""

from __future__ import annotations

import argparse
import importlib

_SECTIONS = (
    ("cspace (dc)", "projects.fx27.runs.point.01_cspace_comparison_dc", True),
    ("cspace (dc+dm)", "projects.fx27.runs.point.05_cspace_comparison_dc_dm", True),
    ("euroc", "projects.fx27.runs.point.09_euroc_comparison_fx27_columns", False),
)


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--validity", action="store_true",
        help="also print Option C's measured error bound per scenario (SS38.5.7), forwarded to all 3 sections",
    )
    ap.add_argument(
        "--show", action="store_true",
        help="also display the figures interactively (forwarded to the cspace sections only; "
        "euroc is never plotted and has no --show flag)",
    )
    args = ap.parse_args(argv)

    for label, module_name, supports_show in _SECTIONS:
        print(f"\n===== {label} =====")
        sub_argv = []
        if args.validity:
            sub_argv.append("--validity")
        if args.show and supports_show:
            sub_argv.append("--show")
        module = importlib.import_module(module_name)
        module.main(sub_argv)


if __name__ == "__main__":
    main()
