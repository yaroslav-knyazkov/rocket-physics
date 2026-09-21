"""Aerodynamic coefficients C_A(alpha, M), C_N(alpha, M), C_m(alpha, M), and
CoP travel l1(alpha, M) -- table-driven with `Params`-constant fallbacks
(architecture.md SS19; roadmap.md Step 25).

Table format (`data/aero/<config>.csv`, this module's own design -- SS19
leaves the exact column layout unspecified, unlike the sounding/motor
formats): a rectangular `(M, alpha)` grid, one row per grid point, in the
same comment-header-metadata + CSV-body style as `sim/thrust_curve.py` /
`sim/soundings.py` (no pandas, `numpy.genfromtxt` -- architecture.md SS17/
SS21, SS22 item 3):

    # free-form comment lines...
    alpha_deg,M,C_A,C_N,C_m,l1_m
    -10,0.5,0.35,-0.5236,0.0873,0.28
    ...

Every `M` value in the file must repeat the exact same set of `alpha_deg`
values (a full rectangular grid) -- `_load_table` raises `ValueError` if
not. `l1_m` is the same physical quantity as `Params.l1` (the CoP-to-CoG
distance, architecture.md SS19 "CoP travel makes l1 a function of
(alpha, M)"), carried in the table so a single file supplies both the
force/moment coefficients and the moment-arm they act through.

Interpolation, in both dimensions, matches this project's established
"hold the edge value, never extrapolate" convention (`thrust_curve.py`
holds the first/zero value outside its time range; `soundings.py` holds
wind constant outside its altitude range): `M` is bracketed and clamped
at the grid edges (no extrapolation beyond the table's Mach range), and
within each bracketing `M` row, `alpha` is `np.interp`-ed (which already
clamps at its own edges). The two per-row values are then linearly
blended across the `M` bracket -- the same "interpolate within each row,
then combine" shape as `soundings.py`'s tier-3 combination.

No table configured (`p.aero_table == ""`, the default) -- every public
function below falls back to the plain `Params` constant, reproducing
`forces.py`'s pre-Step-25 "coefficients" formulas bit-for-bit:
    C_A   -> p.C_A0                  (constant, no alpha/M dependence)
    C_N   -> p.C_N_alpha * alpha
    C_m   -> p.C_m_alpha * alpha
    l1    -> p.l1                    (constant CoP-to-CoG distance)

Note on `C_N`'s signature: main.tex writes `C_N(alpha)` (no explicit `M`
dependence), but this module gives `C_N` the same `(alpha, M, p)` shape as
`C_A`/`C_m`/`cop_l1` for one uniform interface -- the constant-fallback
path still ignores `M` entirely (matching main.tex and the pre-Step-25
formula exactly), and the table path is free to encode `M`-dependence in
`C_N` too if the data has it (real compressible normal-force slopes do
vary with Mach), without needing a second, differently-shaped function.
"""

import functools
import os
from typing import NamedTuple

import numpy as np


class _AeroTable(NamedTuple):
    M: np.ndarray       # (n_M,), ascending
    alpha: np.ndarray   # (n_alpha,), ascending, radians
    C_A: np.ndarray     # (n_M, n_alpha)
    C_N: np.ndarray     # (n_M, n_alpha)
    C_m: np.ndarray     # (n_M, n_alpha)
    l1: np.ndarray      # (n_M, n_alpha), CoP-to-CoG distance [m]


@functools.lru_cache(maxsize=None)
def _load_table(name: str) -> _AeroTable:
    """Read `data/aero/<name>` into a rectangular `(M, alpha)` grid.

    Path resolution follows `sim/thrust_curve.py`'s `_load_motor_curve` /
    `sim/soundings.py`'s `load_case` convention: absolute path from the
    repo root (this file's parent directory is `<repo>/sim/`).
    """
    repo_root = os.path.dirname(os.path.dirname(__file__))
    path = os.path.join(repo_root, "data", "aero", name)

    data_lines = []
    with open(path) as f:
        for line in f:
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            data_lines.append(line)

    if not data_lines:
        raise ValueError(f"Aero table '{name}' has no data rows")

    data = np.atleast_1d(
        np.genfromtxt(data_lines, delimiter=",", names=True, dtype=float)
    )

    M_col = data["M"].astype(float)
    alpha_col = np.radians(data["alpha_deg"].astype(float))
    C_A_col = data["C_A"].astype(float)
    C_N_col = data["C_N"].astype(float)
    C_m_col = data["C_m"].astype(float)
    l1_col = data["l1_m"].astype(float)

    M_grid = np.unique(M_col)
    alpha_grid = np.unique(alpha_col)
    n_M = M_grid.size
    n_a = alpha_grid.size

    if M_col.size != n_M * n_a:
        raise ValueError(
            f"Aero table '{name}' is not a rectangular (M, alpha) grid: "
            f"{M_col.size} rows, expected {n_M} M-values * {n_a} alpha-"
            f"values = {n_M * n_a}"
        )

    def _reshape(col: np.ndarray) -> np.ndarray:
        grid = np.empty((n_M, n_a))
        for i, m in enumerate(M_grid):
            mask = M_col == m
            row_alpha = alpha_col[mask]
            order = np.argsort(row_alpha)
            if not np.allclose(row_alpha[order], alpha_grid):
                raise ValueError(
                    f"Aero table '{name}': the alpha grid at M={m} does not "
                    "match the other M rows -- every M value must repeat "
                    "the same set of alpha_deg values"
                )
            grid[i] = col[mask][order]
        return grid

    return _AeroTable(
        M=M_grid,
        alpha=alpha_grid,
        C_A=_reshape(C_A_col),
        C_N=_reshape(C_N_col),
        C_m=_reshape(C_m_col),
        l1=_reshape(l1_col),
    )


def _bracket_M(M_grid: np.ndarray, M: float) -> "tuple[int, int, float]":
    """Index of the M row below/above the query, and the blend weight
    `w` such that the result is `row_lo + w*(row_hi - row_lo)`. Clamped
    at the grid edges -- no extrapolation beyond the table's Mach range
    (this module's docstring, "hold the edge value")."""
    if M <= M_grid[0]:
        return 0, 0, 0.0
    if M >= M_grid[-1]:
        last = M_grid.size - 1
        return last, last, 0.0
    i_hi = int(np.searchsorted(M_grid, M))
    i_lo = i_hi - 1
    w = (M - M_grid[i_lo]) / (M_grid[i_hi] - M_grid[i_lo])
    return i_lo, i_hi, w


def _table_lookup(table: _AeroTable, alpha: float, M: float, grid: np.ndarray) -> float:
    """Bracket in M (clamped), np.interp in alpha within each bracketing
    row, then linearly blend the two rows across the M bracket."""
    i_lo, i_hi, w = _bracket_M(table.M, M)
    val_lo = np.interp(alpha, table.alpha, grid[i_lo])
    val_hi = np.interp(alpha, table.alpha, grid[i_hi])
    return float(val_lo + w * (val_hi - val_lo))


def C_A(alpha: float, M: float, p) -> float:
    """Axial-force coefficient (main.tex SSForces: `A_x = qSC_A(alpha, M)`).

    Table-driven when `p.aero_table` is set; otherwise the constant
    `p.C_A0` (Step 13's "coefficients" formula, unchanged).
    """
    if p.aero_table:
        table = _load_table(p.aero_table)
        return _table_lookup(table, alpha, M, table.C_A)
    return p.C_A0


def C_N(alpha: float, M: float, p) -> float:
    """Normal-force coefficient (main.tex SSForces: `A_z = qSC_N(alpha)`).

    Table-driven when `p.aero_table` is set (the table may vary `C_N`
    with `M` too -- see the module docstring's note on this signature);
    otherwise `p.C_N_alpha * alpha` (Step 13's formula, unchanged).
    """
    if p.aero_table:
        table = _load_table(p.aero_table)
        return _table_lookup(table, alpha, M, table.C_N)
    return p.C_N_alpha * alpha


def C_m(alpha: float, M: float, p) -> float:
    """Pitching-moment coefficient (main.tex SSMoments' `A_m`, generalised
    per architecture.md SS19: `A_m = qS*d_ref*C_m(alpha, M)`).

    Table-driven when `p.aero_table` is set; otherwise `p.C_m_alpha *
    alpha` (Step 13's formula, unchanged).
    """
    if p.aero_table:
        table = _load_table(p.aero_table)
        return _table_lookup(table, alpha, M, table.C_m)
    return p.C_m_alpha * alpha


def cop_l1(alpha: float, M: float, p) -> float:
    """CoP-to-CoG distance [m] -- the same quantity as `Params.l1`, now a
    function of `(alpha, M)` when a table is configured (architecture.md
    SS19: "CoP travel makes l1 a function of (alpha, M), which couples
    straight back into the moment").

    Table-driven when `p.aero_table` is set; otherwise the constant
    `p.l1`, which is exactly `dynamics.py`'s pre-Step-25 behaviour.
    """
    if p.aero_table:
        table = _load_table(p.aero_table)
        return _table_lookup(table, alpha, M, table.l1)
    return p.l1
