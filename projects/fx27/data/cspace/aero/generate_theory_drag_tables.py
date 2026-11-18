#!/usr/bin/env python
"""projects/fx27/data/cspace/aero/generate_theory_drag_tables.py -- ONE-OFF
generator (dev/docs/architecture-45-fx27-theory-drag-port.md SS3/S6
T45-2). Run manually once; NOT imported at runtime; NOT exercised by
pytest.

Unlike `generate_dm_tables.py` (which ports an EXTERNAL sibling-repo
`Mach,Cd` inventory CSV verbatim), this generator computes `C_D0(M)`
from FIRST-PRINCIPLES THEORY -- the Niskanen thesis / OpenRocket
semi-empirical method, M 0.10-1.30, hand-extended supersonic 1.30-3.00
(`drag_theory.compute_cd0`, itself a port of
`temporary/drive-download-20261117T190208Z-1-001/cd_mach_03_increase_D.m`
-- architecture-45 S1/S2/S4/S5). Kept in a separate module from
`generate_dm_tables.py` so the two provenances are never blurred
together in one file (architecture-45 SS3) -- the same reasoning this
codebase already applies to keeping `regenerate_ideal_own.py` and
`generate_dm_tables.py` as two separate one-off scripts.

Writes the existing `apps/sim/engine/aero.py` v1 table format
(`alpha_deg,M,C_A,C_N,C_m,l1_m`, same shape as `generate_dm_tables.py`'s
own `_convert_one`): two bogus alpha_deg rows per Mach value (-89, +89
deg, IDENTICAL C_A at both), C_N=C_m=0.0 at every point, l1_m=1.0 (the
same DYNAMICALLY INERT placeholder convention `generate_dm_tables.py`
uses).

Output is SIDE-BY-SIDE with the existing `pro54-transition-drag.csv`
(architecture-45 SS5 Option A) -- it does NOT overwrite it. A separate,
future decision (after the user reviews the delta -- see
`tests/test_fx27_drag_theory.py`'s delta-report test) decides whether to
ever promote this theory table to replace the sibling-ported one.

Scope this stage: one `(name, Geometry)` pair only
(`PRO54_TRANSITION_GEOMETRY`) -- `main()` loops over a list so adding
`PRO54_EQUAL_GEOMETRY`/`PRO75_GEOMETRY` later (once shipped in
`drag_theory.py`) is a one-line addition, not a rewrite.

Run once, from the repo root:
    python -m projects.fx27.data.cspace.aero.generate_theory_drag_tables
Output is committed -- same rationale as `generate_dm_tables.py`'s own
static committed output, not a runtime transform.
"""

from __future__ import annotations

import csv
from pathlib import Path

from projects.fx27.data.cspace.aero import drag_theory

_HERE = Path(__file__).resolve().parent

# (output CSV filename, Geometry instance) -- one entry this stage (architecture-45 S6 T45-2).
# PRO54_EQUAL_GEOMETRY / PRO75_GEOMETRY: future additions, once shipped in drag_theory.py
# (PRO75_GEOMETRY additionally blocked on a file-mapping confirmation -- SS2).
_TARGETS = (
    ("pro54-transition-drag-theory.csv", drag_theory.PRO54_TRANSITION_GEOMETRY),
)


def _write_one(dst: Path, geo: drag_theory.Geometry) -> None:
    M_grid, cd0_grid = drag_theory.compute_cd0(geo)
    with open(dst, "w", newline="") as f:
        f.write(
            "# Mach-dependent C_A(M), THEORY-derived (Niskanen thesis / OpenRocket\n"
            "# semi-empirical method, M 0.10-1.30, hand-extended supersonic 1.30-3.00) --\n"
            "# ported from temporary/drive-download-20261117T190208Z-1-001/\n"
            "# cd_mach_03_increase_D.m via projects/fx27/data/cspace/aero/drag_theory.py.\n"
            "# dev/docs/architecture-45-fx27-theory-drag-port.md SS1/S2/S4/S5. NOT the same\n"
            "# provenance as generate_dm_tables.py's output (that ports an EXTERNAL\n"
            "# sibling-repo inventory CSV, not first-principles theory) -- a side-by-side\n"
            "# comparison variant (SS5 Option A), not a replacement for the existing\n"
            "# pro54-transition-drag.csv / pro54_transition_dm.\n"
            "# C_N=C_m=0.0 at every point (Option C invariant); l1_m=1.0 is the same inert\n"
            "# placeholder cspace/rockets.py's _LENGTHS.l1 uses; two alpha rows per Mach\n"
            "# (-89, +89 deg, identical C_A) are the minimum rectangular (M, alpha) grid\n"
            "# apps/sim/engine/aero.py's loader accepts.\n"
        )
        w = csv.writer(f)
        w.writerow(["alpha_deg", "M", "C_A", "C_N", "C_m", "l1_m"])
        for m, cd0 in zip(M_grid, cd0_grid):
            for alpha in (-89.0, 89.0):
                w.writerow([alpha, round(float(m), 2), float(cd0), 0.0, 0.0, 1.0])


def main() -> None:
    for name, geo in _TARGETS:
        _write_one(_HERE / name, geo)
        print(f"wrote {_HERE / name}")


if __name__ == "__main__":
    main()
