#!/usr/bin/env python
"""projects/fx27/campaigns/cspace/generate_rockets_ideal_own.py -- ONE-OFF
regenerate script (architecture-41 SS41.5, roadmap F2 approach (b)). Run
manually whenever rockets.py/rockets_dm.py's base dry mass or C_x change
(e.g. once real CAD/CFD data lands). NOT imported at runtime; NOT
exercised by pytest's collection (its pure string-substitution helper is
unit-tested directly in tests/test_rockets_ideal_own.py -- the solver
calls themselves are not re-run under pytest, see that file's own
docstring).

Computes the 8 solved constants rockets_ideal_own.py hand-types
(2 configs [pro54_transition, pro75] x 2 base-types [dc, dm] x 2
quantities [mass, drag]), target apogee 3000 m AGL, via
apps/optimization/apogee_targeting/solve.py against this project's own
SCENARIOS/SCENARIOS_DM (campaigns/cspace/scenarios.py,
campaigns/cspace/scenarios_dm.py), then rewrites rockets_ideal_own.py's
own 8 named constant lines in place (regex-anchored by name) -- nothing
else in that file is touched.

GUARDRAIL (explicit, not just by convention): this script's only write
target is _TARGET below, HARDCODED to rockets_ideal_own.py -- there is
no code path, flag, or argument that points it anywhere else. It does
import rockets_dm.py (via scenarios_dm.SCENARIOS_DM) to build its dm
solver INPUTS -- that is a read of the dm BASE rockets' current dry
mass/C_x, not of rockets_dm.py's own _IDEAL_ constants, and never
produces a write back to that file or to rockets_ideal.py. Those two
modules hold the AC-3 oracle (tests/test_fx27_port.py) and a frozen
ported arithmetic record respectively -- never open either for writing,
from this script or any other.

Run (from the repo root -- a bare `python path/to/this_file.py` puts the
script's own directory on sys.path[0] instead of the repo root, which
breaks the `apps.*`/`projects.*` absolute imports above with
ModuleNotFoundError; `-m` is required, same convention as every runs/*
entry point):
    python -m projects.fx27.campaigns.cspace.generate_rockets_ideal_own
"""

from __future__ import annotations

import dataclasses
import re
from pathlib import Path

from apps.optimization.apogee_targeting.solve import (
    estimate_airframe_mass,
    estimate_cx,
    solve_for_target_apogee,
)
from projects.fx27.campaigns.cspace.scenarios import SCENARIOS
from projects.fx27.campaigns.cspace.scenarios_dm import SCENARIOS_DM

TARGET_APOGEE_M = 3000.0
_TARGET = Path(__file__).resolve().parent / "rockets_ideal_own.py"
_CX_SCALE_BRACKET = (0.0, 2.0)  # SS41.3 -- same shape as estimate_cx's own default bracket


def _with_cx_scale(scenario, x: float):
    return dataclasses.replace(scenario, overrides={**scenario.overrides, "aero.cx_scale": x})


def _solved_values() -> "dict[str, float]":
    dc_t, dc_75 = SCENARIOS["pro54_transition"], SCENARIOS["pro75"]
    dm_t, dm_75 = SCENARIOS_DM["pro54_transition_dm"], SCENARIOS_DM["pro75_dm"]
    return {
        "PRO54_TRANSITION_IDEAL_OWN_MASS_KG": estimate_airframe_mass(dc_t, target_apogee_agl=TARGET_APOGEE_M).required,
        "PRO54_TRANSITION_IDEAL_OWN_DRAG_CX": estimate_cx(dc_t, target_apogee_agl=TARGET_APOGEE_M).required,
        "PRO75_IDEAL_OWN_MASS_KG": estimate_airframe_mass(dc_75, target_apogee_agl=TARGET_APOGEE_M).required,
        "PRO75_IDEAL_OWN_DRAG_CX": estimate_cx(dc_75, target_apogee_agl=TARGET_APOGEE_M).required,
        "PRO54_TRANSITION_DM_IDEAL_OWN_MASS_KG": estimate_airframe_mass(dm_t, target_apogee_agl=TARGET_APOGEE_M).required,
        "PRO54_TRANSITION_DM_IDEAL_OWN_DRAG_CX_SCALE": solve_for_target_apogee(
            dm_t, _with_cx_scale, dm_t.rocket.aero.cx_scale, _CX_SCALE_BRACKET, TARGET_APOGEE_M
        ).required,
        "PRO75_DM_IDEAL_OWN_MASS_KG": estimate_airframe_mass(dm_75, target_apogee_agl=TARGET_APOGEE_M).required,
        "PRO75_DM_IDEAL_OWN_DRAG_CX_SCALE": solve_for_target_apogee(
            dm_75, _with_cx_scale, dm_75.rocket.aero.cx_scale, _CX_SCALE_BRACKET, TARGET_APOGEE_M
        ).required,
    }


def _substitute_constant(source: str, name: str, value: float) -> str:
    """Pure string transform -- no file I/O -- so tests/test_rockets_ideal_own.py
    can unit-test it directly against synthetic strings/tmp_path files,
    never against the real committed module."""
    pattern = re.compile(rf"^{re.escape(name)} = .+$", re.MULTILINE)
    n = len(pattern.findall(source))
    if n != 1:
        raise RuntimeError(
            f"generate_rockets_ideal_own: expected exactly 1 line matching "
            f"{name!r}, found {n} -- refusing to write (module structure "
            "drifted from what this script expects; fix rockets_ideal_own.py "
            "by hand before re-running)."
        )
    return pattern.sub(f"{name} = {value:.4f}", source, count=1)


def _rewrite_file(path: Path, values: "dict[str, float]") -> None:
    source = path.read_text(encoding="utf-8")
    for name, value in values.items():
        source = _substitute_constant(source, name, value)
    path.write_text(source, encoding="utf-8")


def main() -> None:
    values = _solved_values()
    _rewrite_file(_TARGET, values)
    for name, value in values.items():
        print(f"{name} = {value:.4f}")
    print(f"wrote {_TARGET}")


if __name__ == "__main__":
    main()
