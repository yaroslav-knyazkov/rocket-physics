"""projects/fx27/point/estimate.py -- thin fx27-local wrapper around
apps.optimization.apogee_targeting.solve (promoted dev/docs/architecture-39-
promote-apogee-target-solver.md, backlog B41), mirroring projects/fx27/
point/airbrake.py's wrapper of apps.optimization.airbrake_sizing.solve_cda.

Re-exports the two names fx27's own runs/ scripts
(runs/cspace_ideal_mass.py, runs/cspace_ideal_drag.py) and
tests/test_fx27_port.py import. `EstimateResult` is kept here as the
fx27-local alias of the promoted `ApogeeTargetResult` -- same shape, same
fields, SS38.5.4's original name -- not a separate type: nothing in this
project imports `EstimateResult` by name today (checked: only attribute
access on its instances, e.g. `res.required`/`res.reachable`), so the
alias exists purely so a future direct `from .estimate import
EstimateResult` import, if anyone ever writes one, keeps working under the
name this module always had.

These two functions remain the acceptance oracle for the fx27 port's
Option C decision (AC-3, architecture-38 SS38.9): `tests/test_fx27_port.py`
imports them through this same module path, unchanged.
"""

from apps.optimization.apogee_targeting.solve import ApogeeTargetResult as EstimateResult
from apps.optimization.apogee_targeting.solve import estimate_airframe_mass, estimate_cx

__all__ = ["EstimateResult", "estimate_airframe_mass", "estimate_cx"]
