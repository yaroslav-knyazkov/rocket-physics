"""The demo-scenario pipeline's own smoke test (Phase 2.18, Step 122;
rewritten at Phase 2.20, Step 139 when `examples/worked_scenario.py` --
the thin, pre-built `__main__` wrapper this test used to invoke via
subprocess -- was retired along with every other pre-built entry script
in the repo, same rationale as the root `run_*.py` deletions, D-139/
D-140): the pipeline is genuinely executable end-to-end
(`assemble(DEMO_SCENARIO)` -> `run_sim` -> a printed flight summary),
not just importable -- this is a permanent test, unlike
`tests/test_bridge_demo_scenario_equivalence.py` next to it.

Runs in-process now (no `subprocess`/`sys.executable`, no `python -m`
resolution to prove): calls `assemble`/`run_sim`/`report.
print_run_summary` directly and asserts on `capsys.readouterr().out`
instead of a subprocess's captured stdout. Same two assertions on the
real printed output as before the rewrite.
"""

from __future__ import annotations

from apps.input.demo_scenario import DEMO_SCENARIO
from apps.sim.schema import assemble
from apps.sim.engine import report
from apps.sim.engine.integrate import run_sim


def test_worked_scenario_runs_to_completion_and_prints_a_flight_summary(capsys):
    cfg = assemble(DEMO_SCENARIO)
    result = run_sim(cfg.params, cfg.s0)
    report.print_run_summary(result, cfg.params, cfg.s0)

    out = capsys.readouterr().out
    assert "Apogee altitude:" in out
    assert "Burnout time:" in out
