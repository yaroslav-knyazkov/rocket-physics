r"""examples/worked_scenario.py -- thin runnable wrapper around
`apps/input/demo_scenario.py` (Phase 2.19, Step 130,
dev/docs/architecture-apps-sim-restructure.md Step 130; the literal
itself used to live here -- see Step 122 -- and moved out to
`apps/input/demo_scenario.py` at this step, which removed the backwards
dependency of apps/ code reaching into examples/ for its demo scenario).

To build your own rocket: copy `apps/input/demo_scenario.py` (not this
file), rename `DEMO_SCENARIO`, edit the literal values -- see that
module's own docstring for the full REQ/OPT crib sheet on every field.

Run with `python -m examples.worked_scenario` from the repo root
(`examples/` has no `__init__.py`, the same implicit-namespace-package
convention `apps/` uses -- running this file directly by path instead
would put `examples/` on `sys.path` and break `import configs`/`import
sim`, see `apps/motor_selection/compare_motors.py`'s own docstring for
the same warning).
"""

from __future__ import annotations

from apps.input.demo_scenario import DEMO_SCENARIO
from configs.schema import assemble
from sim import report
from sim.integrate import run_sim

if __name__ == "__main__":
    cfg = assemble(DEMO_SCENARIO)
    result = run_sim(cfg.params, cfg.s0)
    report.print_run_summary(result, cfg.params, cfg.s0)
