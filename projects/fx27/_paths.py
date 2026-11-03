"""projects/fx27/_paths.py -- absolute anchors for the fx27 motor CSV
corpus (dev/docs/architecture-38-fx27-port.md SS38.4.3) and (Part B,
dev/docs/architecture-40-fx27-campaigns-and-dm-drag.md SS40.4.1) the
cspace Mach-dependent aero-table CSVs.

`apps/sim/engine/datafiles.resolve` has three resolution rules for
`Thrust.motor_curve`: (1) absolute -> as-is, (2) a name containing a path
separator -> resolved against `os.getcwd()` AT CALL TIME, (3) a bare name
-> this library's own bundled `projects/examples/data/<kind>/`.
`projects/data/README.md` documents the cwd-relative form
("projects/data/motors/<campaign>/<file>") -- that works only when the
caller's cwd happens to be the repo root, which is a silent foot-gun for a
config *literal* imported from a test file or a script run from anywhere
else (R7, dev/docs/architecture-38-fx27-port.md SS38.10).

This module sidesteps rule 2 entirely by handing every `Thrust.motor_curve`
an ABSOLUTE path (rule 1), computed once from THIS module's own on-disk
location (`Path(__file__).resolve().parent`) rather than from the caller's
cwd. One module owns the anchor; no `cspace/motors.py`/`euroc/motors.py`
literal depends on cwd. Deliberate, documented deviation from
`projects/data/README.md`'s own convention (the personal-data doc; this
module's old citation of a since-deleted `projects/fx27/data/README.md`
stray duplicate was repointed here, SS40.2.3).
"""

from __future__ import annotations

from pathlib import Path

_HERE = Path(__file__).resolve().parent

MOTORS_CSPACE = _HERE / "campaigns" / "cspace" / "data" / "motors"
MOTORS_EUROC = _HERE / "campaigns" / "euroc" / "data" / "motors"
AERO_CSPACE = _HERE / "campaigns" / "cspace" / "data" / "aero"


def cspace_motor(filename: str) -> str:
    """Absolute path (as a `str`, what `Thrust.motor_curve` wants) to a
    cspace motor CSV under `campaigns/cspace/data/motors/`."""
    return str(MOTORS_CSPACE / filename)


def euroc_motor(filename: str) -> str:
    """Absolute path to a euroc motor CSV under
    `campaigns/euroc/data/motors/` (includes the 3 `-todo` stub files --
    callers decide whether to ever actually load one, see
    `campaigns/euroc/motors.py`'s `DEFERRED_MOTORS`)."""
    return str(MOTORS_EUROC / filename)


def cspace_aero(filename: str) -> str:
    """Absolute path to a cspace aero-table CSV under
    `campaigns/cspace/data/aero/` (dev/docs/architecture-40-fx27-
    campaigns-and-dm-drag.md SS40.4/SS40.5) -- same rationale as
    `cspace_motor`: an absolute path sidesteps `datafiles.resolve`'s
    cwd-relative rule 2, which is a silent foot-gun for a config literal
    imported from anywhere but the repo root."""
    return str(AERO_CSPACE / filename)
