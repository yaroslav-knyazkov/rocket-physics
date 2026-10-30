"""tests/datadir.py -- the test-side mirror of `sim/datafiles.py`'s
`_BUNDLED` anchor (Phase 2.19, Step 129, dev/docs/architecture-apps-sim-
restructure.md SS4.4/SS5).

`sim/datafiles.py` is the library-side source of truth for where the
bundled motor/aero/soundings fixtures live (bare-name lookups, rule 3 of
that module's docstring); this module is the equivalent test-side
constant, so that no test file hand-rolls its own
`os.path.join(os.path.dirname(__file__), "..", "projects", "examples",
"data", ...)` relative to this repo's test directory. `tests/test_layering.py::
test_g5_bundled_data_anchor_matches_sim_datafiles` keeps the two from
drifting apart.
"""

from __future__ import annotations

import os

_REPO_ROOT = os.path.dirname(os.path.dirname(__file__))

DATA = os.path.join(_REPO_ROOT, "projects", "examples", "data")
MOTORS_DIR = os.path.join(DATA, "motors")
AERO_DIR = os.path.join(DATA, "aero")
SOUNDINGS_DIR = os.path.join(DATA, "soundings")
