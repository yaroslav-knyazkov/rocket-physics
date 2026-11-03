#!/usr/bin/env python
"""projects/fx27/campaigns/cspace/data/aero/generate_dm_tables.py -- ONE-OFF
generator (dev/docs/architecture-40-fx27-campaigns-and-dm-drag.md SS40.5).
Run manually once; NOT imported at runtime; NOT exercised by pytest.

Reads fx27's own bare `Mach,Cd` curve (rocketpy's own power_off_drag/
power_on_drag CSV convention: no header, 121 rows, Mach 0..3.0 step 0.025)
and reshapes it into this project's apps/sim/engine/aero.py v1 table
format (alpha_deg,M,C_A,C_N,C_m,l1_m -- a rectangular (M, alpha) grid):
two bogus alpha_deg rows per Mach value (-89, +89 deg, IDENTICAL C_A at
both -- comfortably inside the engine's strict (-90, +90) deg bound, wide
enough that a real flight's alpha never leaves the table and triggers
AeroRangeWarning's edge-hold path -- the minimum rectangular grid
_load_table_impl accepts is 2 points, SS40.3.3; only the span widened),
C_N=C_m=0.0 at every point (Option C invariant), l1_m=1.0 (the same
DYNAMICALLY INERT placeholder cspace/rockets.py's _LENGTHS.l1 already
uses). No c_mq column -- the dm Rocket's own Aero.c_mq=0.0 fallback,
carried through unedited from its dc sibling by dataclasses.replace,
already gives the same answer a c_mq column full of zeros would.

Run once, from anywhere (paths below are absolute):
    python projects/fx27/campaigns/cspace/data/aero/generate_dm_tables.py
Output is committed -- SS40.3.3's rationale for a generated static file,
not a runtime transform.
"""

from __future__ import annotations

import csv
from pathlib import Path

_HERE = Path(__file__).resolve().parent

# Absolute path to the sibling repo's own source curves (orchestrator's inventory,
# same provenance convention as projects/fx27/README.md's "Provenance" section).
_SIBLING_AERO_DIR = Path(r"D:\Projects - Ongoing\fx27\simulation\import\aerodynamics\cspace")

_SOURCES = ("pro54-transition-drag.csv", "pro54-equal-drag.csv", "pro75-drag.csv")


def _convert_one(src: Path, dst: Path) -> None:
    with open(src, newline="") as f:
        mach_cd = [(float(m), float(cd)) for m, cd in csv.reader(f) if m.strip()]
    with open(dst, "w", newline="") as f:
        f.write(
            f"# Mach-dependent C_A(M), ported from fx27's own rocketpy power_off_drag/"
            f"power_on_drag curve ({src.name}, orchestrator's inventory of the sibling "
            "repo, 2026-11) -- dev/docs/architecture-40-fx27-campaigns-and-dm-drag.md SS40.5.\n"
            "# C_N=C_m=0.0 at every point (Option C invariant); l1_m=1.0 is the same inert\n"
            "# placeholder cspace/rockets.py's _LENGTHS.l1 uses; two alpha rows per Mach\n"
            "# (-89, +89 deg, identical C_A) are the minimum rectangular (M, alpha) grid\n"
            "# apps/sim/engine/aero.py's loader accepts, widened to comfortably inside the\n"
            "# engine's strict (-90, +90) deg bound so a real flight's alpha never leaves\n"
            "# the table (avoids AeroRangeWarning's edge-hold path; numerically a no-op\n"
            "# either way since both grid points carry the identical C_A).\n"
        )
        w = csv.writer(f)
        w.writerow(["alpha_deg", "M", "C_A", "C_N", "C_m", "l1_m"])
        for m, cd in mach_cd:
            for alpha in (-89.0, 89.0):
                w.writerow([alpha, m, cd, 0.0, 0.0, 1.0])


def main() -> None:
    for name in _SOURCES:
        _convert_one(_SIBLING_AERO_DIR / name, _HERE / name)
        print(f"wrote {_HERE / name}")


if __name__ == "__main__":
    main()
