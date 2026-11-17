"""projects/fx27/solvers/point/estimate.py -- thin fx27-local wrapper around
apps.optimization.apogee_targeting.solve (promoted dev/docs/architecture-39-
promote-apogee-target-solver.md, backlog B41), mirroring projects/fx27/
point/airbrake.py's wrapper of apps.optimization.airbrake_sizing.solve_cda.

Re-exports three names fx27's own runs/ scripts
(runs/cspace/ideal_mass.py, runs/cspace/ideal_drag.py) and
tests/test_fx27_port.py import. `EstimateResult` is kept here as the
fx27-local alias of the promoted `ApogeeTargetResult` -- same shape, same
fields, SS38.5.4's original name -- not a separate type: nothing in this
project imports `EstimateResult` by name today (checked: only attribute
access on its instances, e.g. `res.required`/`res.reachable`), so the
alias exists purely so a future direct `from .estimate import
EstimateResult` import, if anyone ever writes one, keeps working under the
name this module always had.

`estimate_airframe_mass`/`estimate_cx` remain the acceptance oracle for the
fx27 port's Option C decision (AC-3, architecture-38 SS38.9):
`tests/test_fx27_port.py` imports them through this same module path,
unchanged. `estimate_cx_scale` (architecture-42 SS42.5) is the Mach-table
analogue of `estimate_cx`, added for `regenerate_ideal_own.py`'s B1
dm-drag constants and `runs/cspace/ideal_drag.py`'s new dm rows -- not
part of the AC-3 oracle itself (no fx27-solved dm figure exists to grade
it against, SS40.8).
"""

from apps.optimization.apogee_targeting.solve import ApogeeTargetResult as EstimateResult
from apps.optimization.apogee_targeting.solve import estimate_airframe_mass, estimate_cx, estimate_cx_scale

__all__ = ["EstimateResult", "estimate_airframe_mass", "estimate_cx", "estimate_cx_scale"]
