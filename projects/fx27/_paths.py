"""projects/fx27/_paths.py -- absolute anchors for the fx27 motor CSV
corpus (dev/docs/architecture-38-fx27-port.md SS38.4.3).

`apps/sim/engine/datafiles.resolve` has three resolution rules for
`Thrust.motor_curve`: (1) absolute -> as-is, (2) a name containing a path
separator -> resolved against `os.getcwd()` AT CALL TIME, (3) a bare name
-> this library's own bundled `projects/examples/data/<kind>/`.
`projects/fx27/data/README.md` documents the cwd-relative form
("projects/data/motors/<campaign>/<file>") -- that works only when the
caller's cwd happens to be the repo root, which is a silent foot-gun for a
config *literal* imported from a test file or a script run from anywhere
else (R7, dev/docs/architecture-38-fx27-port.md SS38.10).

This module sidesteps rule 2 entirely by handing every `Thrust.motor_curve`
an ABSOLUTE path (rule 1), computed once from THIS module's own on-disk
location (`Path(__file__).resolve().parent`) rather than from the caller's
cwd. One module owns the anchor; no `cspace/motors.py`/`euroc/motors.py`
literal depends on cwd. Deliberate, documented deviation from
`projects/fx27/data/README.md`'s own convention.
"""

from __future__ import annotations

from pathlib import Path

_HERE = Path(__file__).resolve().parent

MOTORS_CSPACE = _HERE / "data" / "motors" / "cspace"
MOTORS_EUROC = _HERE / "data" / "motors" / "euroc-sweep"


def cspace_motor(filename: str) -> str:
    """Absolute path (as a `str`, what `Thrust.motor_curve` wants) to a
    cspace motor CSV under `data/motors/cspace/`."""
    return str(MOTORS_CSPACE / filename)


def euroc_motor(filename: str) -> str:
    """Absolute path to a euroc-sweep motor CSV under
    `data/motors/euroc-sweep/` (includes the 3 `-todo` stub files --
    callers decide whether to ever actually load one, see
    `euroc/motors.py`'s `DEFERRED_MOTORS`)."""
    return str(MOTORS_EUROC / filename)
