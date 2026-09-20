"""Thrust curve model: time-thrust table lookup via np.interp.

The public function `thrust(t, s, p)` returns the instantaneous thrust
magnitude [N] for the given time. It is called from `forces.thrust_body`
and has the same signature as all force models.

The curve is loaded from `data/motors/<motor_curve>.csv` where
<p.motor_curve> is the filename (without path) given in `Params`.
The CSV must have a header line and two columns: time [s], thrust [N].
Units are strict SI. The loader is @lru_cache; the array is stored
module-globally after first use.

For t < first time point: returns the first thrust point (allows
pre-ignition spike if desired). For t > last time point: returns 0.
This matches the roadmap requirement "zero after the last point" and
removes the hard-coded T_BURN hack from forces.py.
"""

import csv
import functools
import os

import numpy as np

# ----------------------------------------------------------------------
# Internal caching helpers
# ----------------------------------------------------------------------


@functools.lru_cache(maxsize=None)
def _load_motor_curve(curve_name: str) -> tuple[np.ndarray, np.ndarray]:
    """Read `data/motors/<curve_name>.csv` and return (times, thrust).

    The CSV is expected to have a comment/header line (starting with #)
    and then two columns: time [s], thrust [N].  Whitespace is allowed.
    Returns two 1D np.ndarray, sorted by time, with no duplicate times.
    """
    # Build absolute path from the repository root (this file's parent
    # directory is <repo>/sim/, so we go up one level to get the repo root).
    repo_root = os.path.dirname(os.path.dirname(__file__))
    csv_path = os.path.join(repo_root, "data", "motors", curve_name)

    times = []
    thrusts = []
    with open(csv_path, newline="") as f:
        reader = csv.reader(f)
        for row in reader:
            if not row or row[0].strip().startswith("#"):
                continue
            # Allow extra columns (e.g. units) – we only need the first two.
            t_str, f_str = row[0], row[1]
            times.append(float(t_str))
            thrusts.append(float(f_str))

    if not times:
        raise ValueError(f"No data found in motor curve '{curve_name}'")

    # Sort by time and remove duplicates (keep first occurrence)
    order = np.argsort(times)
    times = np.array(times)[order]
    thrusts = np.array(thrusts)[order]
    _, unique_idx = np.unique(times, return_index=True)
    times = times[unique_idx]
    thrusts = thrusts[unique_idx]

    return times, thrusts


# ----------------------------------------------------------------------
# Public API (matches the force-model seam in forces.py)
# ----------------------------------------------------------------------


def thrust(_t: float, _s, p) -> float:
    """Instantaneous thrust magnitude [N] for the current time.

    Returns zero when the time is after the last defined point in the
    curve, exactly as required by the roadmap.
    """
    if not p.motor_curve:
        # No curve defined -> zero thrust (safe default)
        return 0.0

    times, thrust_curves = _load_motor_curve(p.motor_curve)
    # np.interp handles extrapolation: values left of range return
    # `left`, values right of range return `right`.  We want the first
    # point for t < t[0] and 0.0 for t > t[-1].
    return float(
        np.interp(_t, times, thrust_curves, left=thrust_curves[0], right=0.0)
    )