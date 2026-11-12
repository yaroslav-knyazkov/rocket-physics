#!/usr/bin/env python
"""projects/fx27/campaigns/cspace/regenerate_ideal_own.py -- ONE-OFF
regenerate script (architecture-42 SS42.4, renamed/retargeted from
generate_rockets_ideal_own.py, architecture-41 SS41.5, roadmap F2
approach (b)). Run manually whenever rockets.py/rockets_dm.py's base dry
mass or C_x change (e.g. once real CAD/CFD data lands). NOT imported at
runtime; NOT exercised by pytest's collection (its pure string-substitution
helper is unit-tested directly in tests/test_regenerate_ideal_own.py --
the solver calls themselves are not re-run under pytest, see that file's
own docstring).

Computes the 8 solved constants rockets_ideal.py's Section B1 hand-types
(2 configs [pro54_transition, pro75] x 2 base-types [dc, dm] x 2
quantities [mass, drag]), target apogee 3000 m AGL, via
apps/optimization/apogee_targeting/solve.py against this project's own
SCENARIOS/SCENARIOS_DM (campaigns/cspace/scenarios.py,
campaigns/cspace/scenarios_dm.py), then rewrites rockets_ideal.py's own
8 named Section-B1 constant lines in place (regex-anchored by name) --
nothing else in that file is touched.

GUARDRAIL (explicit, not just by convention): this script's only write
target is _TARGET below, hardcoded to rockets_ideal.py -- there is no
code path, flag, or argument that points it anywhere else. It does
import rockets_dm.py (via scenarios_dm.SCENARIOS_DM) to build its dm
solver INPUTS -- that is a read of the dm BASE rockets' current dry
mass/C_x, which still lives in rockets_dm.py after SS42.3's trim (now the
*only* thing left in that file), never of rockets_ideal.py's own Section
A oracle or Section B2 fx27-dm provenance constants, and never produces a
write back to rockets_dm.py. It never writes a byte outside its own
8-key Section-B1 slice, by construction (SS42.4): `_rewrite_file` only
ever calls `_substitute_constant(source, name, value)` for `name` drawn
from `_solved_values()`'s 8 keys -- Section A's 4 oracle names and
Section B2's 4 fx27-dm provenance names are never in that dict, so they
are structurally unreachable by this script, not merely "written not to
touch them". `_substitute_constant`'s own `n != 1` guard (raises if a
name's line isn't found exactly once) is unchanged and still the second
line of defense if rockets_ideal.py ever drifts out of the expected
shape.

Run (from the repo root -- a bare `python path/to/this_file.py` puts the
script's own directory on sys.path[0] instead of the repo root, which
breaks the `apps.*`/`projects.*` absolute imports above with
ModuleNotFoundError; `-m` is required, same convention as every runs/*
entry point):
    python -m projects.fx27.campaigns.cspace.regenerate_ideal_own
"""

from __future__ import annotations

import re
from pathlib import Path

from apps.optimization.apogee_targeting.solve import estimate_airframe_mass, estimate_cx, estimate_cx_scale
from projects.fx27.campaigns.cspace.scenarios import SCENARIOS
from projects.fx27.campaigns.cspace.scenarios_dm import SCENARIOS_DM

TARGET_APOGEE_M = 3000.0
_TARGET = Path(__file__).resolve().parent / "rockets_ideal.py"


def _solved_values() -> "dict[str, float]":
    dc_t, dc_75 = SCENARIOS["pro54_transition"], SCENARIOS["pro75"]
    dm_t, dm_75 = SCENARIOS_DM["pro54_transition_dm"], SCENARIOS_DM["pro75_dm"]
    return {
        "PRO54_TRANSITION_IDEAL_OWN_MASS_KG": estimate_airframe_mass(dc_t, target_apogee_agl=TARGET_APOGEE_M).required,
        "PRO54_TRANSITION_IDEAL_OWN_DRAG_CX": estimate_cx(dc_t, target_apogee_agl=TARGET_APOGEE_M).required,
        "PRO75_IDEAL_OWN_MASS_KG": estimate_airframe_mass(dc_75, target_apogee_agl=TARGET_APOGEE_M).required,
        "PRO75_IDEAL_OWN_DRAG_CX": estimate_cx(dc_75, target_apogee_agl=TARGET_APOGEE_M).required,
        "PRO54_TRANSITION_DM_IDEAL_OWN_MASS_KG": estimate_airframe_mass(dm_t, target_apogee_agl=TARGET_APOGEE_M).required,
        "PRO54_TRANSITION_DM_IDEAL_OWN_DRAG_CX_SCALE": estimate_cx_scale(
            dm_t, target_apogee_agl=TARGET_APOGEE_M
        ).required,
        "PRO75_DM_IDEAL_OWN_MASS_KG": estimate_airframe_mass(dm_75, target_apogee_agl=TARGET_APOGEE_M).required,
        "PRO75_DM_IDEAL_OWN_DRAG_CX_SCALE": estimate_cx_scale(dm_75, target_apogee_agl=TARGET_APOGEE_M).required,
    }


def _substitute_constant(source: str, name: str, value: float) -> str:
    """Pure string transform -- no file I/O -- so tests/test_regenerate_ideal_own.py
    can unit-test it directly against synthetic strings/tmp_path files,
    never against the real committed module."""
    pattern = re.compile(rf"^{re.escape(name)} = .+$", re.MULTILINE)
    n = len(pattern.findall(source))
    if n != 1:
        raise RuntimeError(
            f"regenerate_ideal_own: expected exactly 1 line matching "
            f"{name!r}, found {n} -- refusing to write (module structure "
            "drifted from what this script expects; fix rockets_ideal.py "
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
