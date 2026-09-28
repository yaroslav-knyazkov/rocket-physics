"""Aerodynamic coefficients C_A(alpha, M), C_N(alpha, M), C_m(alpha, M), and
CoP travel l1(alpha, M) -- table-driven with `Params`-constant fallbacks
(architecture.md SS19; roadmap.md Step 25). Step 44 (architecture.md SS24.4)
adds a fifth, optional coefficient, `C_mq(alpha, M)` (pitch damping).

Table format (`data/aero/<config>.csv`, this module's own design -- SS19
leaves the exact column layout unspecified, unlike the sounding/motor
formats): a rectangular `(M, alpha)` grid, one row per grid point, in the
same comment-header-metadata + CSV-body style as `sim/thrust_curve.py` /
`sim/soundings.py` (no pandas, `numpy.genfromtxt` -- architecture.md SS17/
SS21, SS22 item 3):

    # free-form comment lines...
    alpha_deg,M,C_A,C_N,C_m,l1_m,c_mq
    -10,0.5,0.35,-0.5236,0.0873,0.28,5.0
    ...

Every `M` value in the file must repeat the exact same set of `alpha_deg`
values (a full rectangular grid) -- `_load_table` raises `ValueError` if
not. `l1_m` is the same physical quantity as `Params.l1` (the CoP-to-CoG
distance, architecture.md SS19 "CoP travel makes l1 a function of
(alpha, M)"), carried in the table so a single file supplies both the
force/moment coefficients and the moment-arm they act through. `c_mq` (Step
44) is the only *optional* column -- see `C_mq`'s own docstring for why an
absent column falls back to `Params.c_mq` rather than to `_AeroTable.C_mq
is None` being treated as a literal zero everywhere; every table committed
before Step 44 lacks it, so this must not change any existing table's
behaviour.

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
`forces.py`'s pre-Step-25 "coefficients" formulas to within the linear
model's own small-angle error (see the Phase 2.5 note just below):
    C_A   -> p.C_A0                       (constant, no alpha/M dependence)
    C_N   -> p.C_N_alpha * sin(alpha)     (main.tex's C_N_alpha*alpha, smoothed)
    C_m   -> p.C_m_alpha * sin(alpha)     (main.tex's C_m_alpha*alpha, smoothed)
    l1    -> p.l1                         (constant CoP-to-CoG distance)
    C_mq  -> p.c_mq                       (constant pitch-damping derivative, default 0.0 -- Step 44)

Phase 2.5 (after Step 35): `C_N`/`C_m`'s fallback uses `sin(alpha)` instead
of the raw `alpha` main.tex's linear formula literally specifies.
`sin(alpha) == alpha` to leading order for small alpha -- they differ by
<0.4% at 8.6 degrees (deg2rad(8.6) - sin(deg2rad(8.6)) / deg2rad(8.6)), well
inside this fallback's own small-angle-linearisation error -- so every
normal (small-alpha) trajectory is unaffected in any way that matters. The
reason for the change: raw `alpha = atan2(w, u)` is *discontinuous* at its
own branch cut (`u < 0`, `w` crossing zero), and an unperturbed, symmetric
flight coasting through `V = 0` at apogee with `theta` unchanged (no
restoring moment ever having engaged) lands exactly there -- floating-point
noise in `w` alone then flips `alpha` between +pi and -pi from one solver
evaluation to the next. With the raw-alpha formula that flips
`C_N`/`C_m`'s sign and (being unbounded) magnitude every RHS call, which
sent `solve_ivp`'s adaptive step control into a step-size collapse that did
not recover within any reasonable wall-clock time (observed: still not
converged after several minutes, on a scenario Step 34's code finished in
~1 second). A magnitude *clamp* on `alpha` was tried first and does not
fix this -- it only shrinks the jump, and any genuine discontinuity, however
small, still defeats an adaptive solver's local-smoothness assumption.
`sin(alpha)` removes the discontinuity itself: it has no branch cut, so it
passes through the `+-pi` crossing exactly as smoothly as everything else
in the model does. It is also arguably the more physically honest formula
at large `alpha` to begin with -- `sin(pi) = 0`, correctly zero net side
force flying exactly tail-first (by symmetry, for a body of revolution),
where the literal `C_N_alpha*alpha` formula gives a large, nonsensical
value instead. `atan2(w, u)` itself remains ill-defined at the single
physical point `u = w = 0`; that is inherent to using an angle at all and
is not, and cannot be, "fixed" -- `sin(alpha)` only ensures nothing built
from it blows up there.

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
    C_mq: "np.ndarray | None"  # (n_M, n_alpha), pitch-damping derivative, or None when the column is absent


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
    # Step 44 (architecture.md SS24.4): the c_mq column is optional -- every
    # table committed before this step lacks it, so "absent -> None" (and
    # C_mq()'s constant fallback below) must hold for bit-for-bit backward
    # compatibility. This is the only column handled this way; every other
    # column above is mandatory.
    C_mq_col = data["c_mq"].astype(float) if "c_mq" in data.dtype.names else None

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
        C_mq=_reshape(C_mq_col) if C_mq_col is not None else None,
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
    otherwise `p.C_N_alpha * sin(alpha)` (Step 13's `C_N_alpha*alpha`
    formula, smoothed at Phase 2.5 Step 35 -- see the module docstring's
    "no table configured" section for why).
    """
    if p.aero_table:
        table = _load_table(p.aero_table)
        return _table_lookup(table, alpha, M, table.C_N)
    return p.C_N_alpha * np.sin(alpha)


def C_m(alpha: float, M: float, p) -> float:
    """Pitching-moment coefficient (main.tex SSMoments' `A_m`, generalised
    per architecture.md SS19: `A_m = qS*d_ref*C_m(alpha, M)`).

    Table-driven when `p.aero_table` is set; otherwise `p.C_m_alpha *
    sin(alpha)` (Step 13's `C_m_alpha*alpha` formula, smoothed at Phase 2.5
    Step 35, same reasoning as `C_N` above).
    """
    if p.aero_table:
        table = _load_table(p.aero_table)
        return _table_lookup(table, alpha, M, table.C_m)
    return p.C_m_alpha * np.sin(alpha)


def C_mq(alpha: float, M: float, p) -> float:
    """Pitch-damping derivative (analysis.tex SSDynamic stability:
    c_m = c_m0 + alpha*c_m_alpha + q_hat*c_mq, q_hat = omega*d_ref/(2V)).

    Table-driven when `p.aero_table` is set AND the table has a `c_mq`
    column; otherwise the constant `p.c_mq` (default 0.0 -- inert). This
    is a deliberate exception to this module's usual "table wins
    completely" rule (see the module docstring's "no table configured"
    section for the rule as it applies to every other coefficient): every
    table committed before Step 44 lacks the column, so absent-column must
    fall back to `p.c_mq`, not to a literal `0.0`, for a user to be able to
    try a single constant damping value without regenerating a whole
    `(M, alpha)` grid (architecture.md SS24.4).

    SIGN: positive c_mq is DAMPING in this document's convention (positive
    C_m is a nose-down moment here -- architecture.md SS24.4), the
    opposite of the textbook C_mq < 0. Same flip C_m_alpha already
    carries.
    """
    if p.aero_table:
        table = _load_table(p.aero_table)
        if table.C_mq is not None:
            return _table_lookup(table, alpha, M, table.C_mq)
    return p.c_mq


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
