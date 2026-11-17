"""projects/fx27/data/cspace/airbrake_data.py -- loads the hand-entered
airbrake hardware CSVs under airbrake/ (dev/docs/task-152-fx27-point-
controller-rung1.md S4). Fx27-owned, small, NOT a reuse of apps/sim/engine/
aero.py's private 2D-table loader (different table shape, see that
module's own docstring for why).
"""

from __future__ import annotations

import dataclasses

import numpy as np

from projects.fx27._paths import cspace_airbrake

_REQUIRED_COLUMNS = ("M", "cd_brake", "area_design_m2")


@dataclasses.dataclass(frozen=True)
class AirbrakeHardware:
    """One rocket family's own airbrake hardware curve -- `M` ascending,
    `cd_brake`/`area_design_m2` the same length. A length-1 table IS the
    constant case: `cd_at`/`area_at` use `np.interp`, which returns the
    sole value for every query when `xp` has length 1 -- no special-casing
    needed in this class or in any caller."""

    M: np.ndarray
    cd_brake: np.ndarray
    area_design_m2: np.ndarray

    def cd_at(self, mach: float) -> float:
        return float(np.interp(mach, self.M, self.cd_brake))

    def area_at(self, mach: float) -> float:
        return float(np.interp(mach, self.M, self.area_design_m2))

    def cda_at(self, mach: float) -> float:
        return self.cd_at(mach) * self.area_at(mach)


def load_airbrake_hardware(path: str) -> AirbrakeHardware:
    """Parse one hardware CSV: strip `#` comment lines (same convention as
    aero.py's loader), require the header + >=1 data row, require ascending
    M (silently-wrong `np.interp` otherwise -- a QA check, not decoration),
    require every value finite."""
    data_lines = []
    with open(path) as f:
        for line in f:
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            data_lines.append(line)
    if len(data_lines) < 2:
        raise ValueError(f"Airbrake hardware file '{path}' has no data rows")
    header = [h.strip() for h in data_lines[0].split(",")]
    missing = [c for c in _REQUIRED_COLUMNS if c not in header]
    if missing:
        raise ValueError(f"Airbrake hardware file '{path}': missing column(s) {missing}")
    data = np.atleast_1d(np.genfromtxt(data_lines, delimiter=",", names=True, dtype=float))
    for col in data.dtype.names:
        if not np.all(np.isfinite(data[col])):
            raise ValueError(f"Airbrake hardware file '{path}': column {col!r} has a non-finite value")
    M = data["M"].astype(float)
    if np.any(np.diff(M) <= 0.0) and M.size > 1:
        raise ValueError(f"Airbrake hardware file '{path}': M column must be strictly ascending")
    return AirbrakeHardware(
        M=M, cd_brake=data["cd_brake"].astype(float), area_design_m2=data["area_design_m2"].astype(float),
    )


PRO54_TRANSITION_AIRBRAKE = load_airbrake_hardware(cspace_airbrake("pro54-transition-airbrake.csv"))
PRO75_AIRBRAKE = load_airbrake_hardware(cspace_airbrake("pro75-airbrake.csv"))
