"""apps/common/artifacts.py -- the shared output-directory helper (Step
64, roadmap.md; dev/docs/architecture-30-apps-4-5-and-configs.md SS30.5).

`output_dir()` is `Path.cwd() / "output"`, both `apps/cfd_conditions/
select_conditions.py` and `apps/motor_selection/compare_motors.py` used
to hand-roll separately (as `_OUTPUT_DIR`/`OUTPUT_DIR`, each anchored off
its own `__file__` instead). Defined once here so a future app (or a
future migration of the existing two) has one place to import it from.

Per Step 64's scope: `compare_motors.py` is the only existing app switched
over to this constant in this step; `select_conditions.py` keeps its own
`_OUTPUT_DIR` unedited (that migration, if wanted, is a later step, not
this one -- Step 64 promotes the shared layer out of App 3 without
touching App 2).

Step 127 (Phase 2.19, dev/docs/architecture-apps-sim-restructure.md
SS4.4/SS5): the above was `__file__`-anchored (`Path(__file__).parents[2]
/ "output"`), which freezes a path relative to *this module's own
location on disk* -- fine today, but after a later step moves this file,
that anchor would keep pointing at the old tree, silently. `output_dir()`
is now a function, not a module-level constant, precisely so it reads
`Path.cwd()` at call time (every call, not once at import time): a
constant would freeze whatever the *importing* process's cwd happened to
be the first time this module was imported, which is the same kind of
staleness, just one step removed. Every known call site has been
converted to call it instead of reading a constant (see
`apps/motor_selection/{compare_motors,scenario_sweep}.py`,
`apps/weight_aero_tradeoff/{trade_surface,compare_configs}.py`,
`apps/airbrake_sizing/solve_cda.py`, `apps/cfd_conditions/
select_conditions.py`) -- no deprecated alias needed.
"""

from __future__ import annotations

from pathlib import Path


def output_dir() -> Path:
    """`Path.cwd() / "output"`, resolved fresh on every call (never
    cached, never anchored to this module's own `__file__`) -- the
    repo's conventional place for generated artifacts (plots, CSVs),
    kept out of the repo root and gitignored wholesale (.gitignore)."""
    return Path.cwd() / "output"


def ensure_dir(path: Path) -> Path:
    """`path.mkdir(exist_ok=True)`, returning `path` so a call can be
    chained into the expression that needs it (`ensure_dir(output_dir())
    / "foo.csv"`)."""
    path.mkdir(exist_ok=True)
    return path
