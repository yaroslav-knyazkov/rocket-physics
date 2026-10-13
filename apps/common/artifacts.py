"""apps/common/artifacts.py -- the shared output-directory helper (Step
64, roadmap.md; docs/architecture-30-apps-4-5-and-configs.md SS30.5).

`OUTPUT_DIR` is the `Path(__file__).parents[2] / "output"` both
`apps/cfd_conditions/select_conditions.py` and
`apps/motor_selection/compare_motors.py` hand-roll separately (as
`_OUTPUT_DIR`, module-local). Defined once here so a future app (or a
future migration of the existing two) has one place to import it from.

Per Step 64's scope: `compare_motors.py` is the only existing app switched
over to this constant in this step; `select_conditions.py` keeps its own
`_OUTPUT_DIR` unedited (that migration, if wanted, is a later step, not
this one -- Step 64 promotes the shared layer out of App 3 without
touching App 2).
"""

from __future__ import annotations

from pathlib import Path

OUTPUT_DIR = Path(__file__).parents[2] / "output"


def ensure_dir(path: Path) -> Path:
    """`path.mkdir(exist_ok=True)`, returning `path` so a call can be
    chained into the expression that needs it (`ensure_dir(OUTPUT_DIR) /
    "foo.csv"`)."""
    path.mkdir(exist_ok=True)
    return path
