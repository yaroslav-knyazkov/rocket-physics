"""examples/worked_scenario.py's own smoke test (Phase 2.18, Step 122):
the file is genuinely executable (`cfg = assemble(DEMO_SCENARIO)`,
`run_sim`, a printed flight summary under `__main__`), not just
importable -- this is a permanent test, unlike
`tests/test_bridge_demo_scenario_equivalence.py` next to it.

Invoked as `python -m examples.worked_scenario` rather than by file path:
`examples/` has no `__init__.py` (the same implicit-namespace-package
convention `apps/` uses), so running the file directly by path would put
`examples/` itself on `sys.path` and break `import configs`/`import sim`
(see `apps/motor_selection/compare_motors.py`'s own docstring for the
same warning); `-m` resolves it as a package from the repo root instead.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_worked_scenario_runs_to_completion_and_prints_a_flight_summary():
    result = subprocess.run(
        [sys.executable, "-m", "examples.worked_scenario"],
        cwd=_PROJECT_ROOT,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, result.stderr
    assert "Apogee altitude:" in result.stdout
    assert "Burnout time:" in result.stdout
