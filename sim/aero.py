"""Aerodynamic coefficients C_x(alpha, M), C_z(alpha, M), C_m(alpha, M),
C_mq(alpha, M) and the CoP-to-CoG distance l1(alpha, M) -- an explicit
three-way model dispatch (architecture-28-rewrite.md SS28.5; supersedes the
table-vs-constant-fallback shape of roadmap.md Step 25 / architecture.md
SS19, and Step 44's `c_mq` scaffold, SS24.4).

Step 55 (Phase 2.11 rewrite pass): `p.aero.model` is now the *sole*
selector -- `"constant" | "linearized" | "table"` -- the same
dispatch-dict shape `wind.py`'s `_MODELS`/`_TURBULENCE_MODELS` and
`gravity.py`'s two dicts already use (architecture.md SS12). Previously,
`p.aero_model in {"constant", "coefficients"}` and `p.aero_table` (a
filename, empty = off) were two uncoordinated selectors for the same
thing: a table could be configured while `aero_model == "constant"` and
be silently ignored, or `dynamics.py`'s `cop_l1` call could read the table
while `forces.py`'s force/moment calls used the constant fallback instead
(architecture-28-rewrite.md's F2 finding -- two different models disagreeing
about the CoP location they themselves jointly determine). Folding both
selectors into one `model` string removes that whole class of bug by
construction: there is now exactly one call (`coefficients`, below) that
produces all five derived quantities together, and whichever model is
selected, it is the only one producing them.

This also closes the `"constant"` model's own bug the rewrite exists to
fix (architecture-28-rewrite.md, "Confirmed bug, user-identified"):
`"constant"`'s `C_x`/`C_z`/`C_m` used to be raw-Newton/Newton-metre
placeholders (`A_x`, `A_z`, `A_m`), the only aero model that ignored the
atmosphere entirely. They are now true dimensionless coefficients, scaled
by dynamic pressure and reference area/length exactly like the other two
models (`forces.py`'s `aero_force_body`/`aero_moment_y`) -- see
`_constant_coeffs` below.

The public seam is a single function, `coefficients(t, y, p, flow) ->
AeroCoeffs`, returning all five coefficients at once (axial-force,
normal-force, pitching-moment, pitch-damping, CoP-to-CoG distance) --
`AeroCoeffs`'s own docstring lists the fields. `C_A`/`C_N`/`C_m`/`C_mq`/
`cop_l1`, the pre-Step-55 per-coefficient public functions, are kept as
thin wrappers around the same dispatch (architecture-28-rewrite.md D-7),
so the existing unit tests and call sites that read one coefficient at a
time keep their `(alpha, M, p)` signature unchanged.

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
not. `l1_m` is the same physical quantity as `Params.lengths.l1` (the
CoP-to-CoG distance, architecture.md SS19 "CoP travel makes l1 a function
of (alpha, M)"), carried in the table so a single file supplies both the
force/moment coefficients and the moment-arm they act through. `c_mq`
(Step 44) is the only *optional* column -- see `_table_coeffs`'s own
docstring for why an absent column falls back to `Params.aero.c_mq`
rather than to a literal zero everywhere; every table committed before
Step 44 lacks it, so this must not change any existing table's behaviour.

Interpolation, in both dimensions, matches this project's established
"hold the edge value, never extrapolate" convention (`thrust_curve.py`
holds the first/zero value outside its time range; `soundings.py` holds
wind constant outside its altitude range): `M` is bracketed and clamped
at the grid edges (no extrapolation beyond the table's Mach range), and
within each bracketing `M` row, `alpha` is `np.interp`-ed (which already
clamps at its own edges). The two per-row values are then linearly
blended across the `M` bracket -- the same "interpolate within each row,
then combine" shape as `soundings.py`'s tier-3 combination. This loader/
interpolation machinery (`_load_table`, `_bracket_M`, `_table_lookup`) is
untouched by Step 55 -- only *when* it is called changed: on
`p.aero.model == "table"` now, not on `p.aero.table` being non-empty.

Note on `C_N`'s signature: main.tex writes `C_N(alpha)` (no explicit `M`
dependence), but this module gives `C_N` the same `(alpha, M, p)` shape as
`C_A`/`C_m`/`cop_l1` for one uniform interface -- the `"constant"`/
`"linearized"` models ignore `M` entirely (matching main.tex and the
pre-Step-25 formula exactly), and the `"table"` model is free to encode
`M`-dependence in `C_N` too if the data has it (real compressible
normal-force slopes do vary with Mach), without needing a second,
differently-shaped function.
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
    # _table_coeffs's constant fallback below) must hold for bit-for-bit
    # backward compatibility. This is the only column handled this way;
    # every other column above is mandatory.
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


# ----------------------------------------------------------------------
# The unified seam (architecture-28-rewrite.md SS28.5.1): one bundle, one
# dispatch dict.
# ----------------------------------------------------------------------


class AeroCoeffs(NamedTuple):
    C_x: float    # axial-force coefficient      (today's C_A)
    C_z: float    # normal-force coefficient     (today's C_N)
    C_m: float    # pitching-moment coefficient
    C_mq: float   # pitch-damping derivative
    l1: float     # CoP(D)-to-CoG(B) distance [m]


def _constant_coeffs(alpha: float, M: float, p) -> AeroCoeffs:
    """`"constant"`: fixed inputs, independent of both `alpha` and `M` --
    the cheapest model, for first-cut sizing and for isolating one effect
    at a time in a comparison sweep (models.tex SSAerodynamics >
    Coefficients).

    Step 55's actual fix: `C_x`/`C_z`/`C_m` are true dimensionless
    coefficients now, not raw Newton/Newton-metre placeholders -- the
    force/moment they produce is still multiplied by dynamic pressure and
    the reference area/length in `forces.py`'s `aero_force_body`/
    `aero_moment_y`, exactly like the other two models. What is frozen
    under this model is the *coefficients*, not the resulting force: the
    force itself still varies over the flight through `q = 0.5*rho*V^2`.
    """
    return AeroCoeffs(
        C_x=p.aero.C_x,
        C_z=p.aero.C_z,
        C_m=p.aero.C_m,
        C_mq=p.aero.c_mq,
        l1=p.lengths.l1,
    )


def _linearized_coeffs(alpha: float, M: float, p) -> AeroCoeffs:
    """`"linearized"`: a single linear slope in `alpha` about the
    zero-`alpha` condition, `M`-independent, bit-for-bit today's (pre-
    Step-55) `"coefficients"` regime.

    Phase 2.5 (after Step 35): `C_z`/`C_m`'s formula uses `sin(alpha)`
    instead of the raw `alpha` main.tex's linear formula literally
    specifies. `sin(alpha) == alpha` to leading order for small alpha --
    they differ by <0.4% at 8.6 degrees (deg2rad(8.6) - sin(deg2rad(8.6)) /
    deg2rad(8.6)), well inside this model's own small-angle-linearisation
    error -- so every normal (small-alpha) trajectory is unaffected in any
    way that matters. The reason for the change: raw `alpha =
    atan2(w, u)` is *discontinuous* at its own branch cut (`u < 0`, `w`
    crossing zero), and an unperturbed, symmetric flight coasting through
    `V = 0` at apogee with `theta` unchanged (no restoring moment ever
    having engaged) lands exactly there -- floating-point noise in `w`
    alone then flips `alpha` between +pi and -pi from one solver
    evaluation to the next. With the raw-alpha formula that flips
    `C_z`/`C_m`'s sign and (being unbounded) magnitude every RHS call,
    which sent `solve_ivp`'s adaptive step control into a step-size
    collapse that did not recover within any reasonable wall-clock time
    (observed: still not converged after several minutes, on a scenario
    Step 34's code finished in ~1 second). A magnitude *clamp* on `alpha`
    was tried first and does not fix this -- it only shrinks the jump, and
    any genuine discontinuity, however small, still defeats an adaptive
    solver's local-smoothness assumption. `sin(alpha)` removes the
    discontinuity itself: it has no branch cut, so it passes through the
    `+-pi` crossing exactly as smoothly as everything else in the model
    does. It is also arguably the more physically honest formula at large
    `alpha` to begin with -- `sin(pi) = 0`, correctly zero net side force
    flying exactly tail-first (by symmetry, for a body of revolution),
    where the literal `C_N_alpha*alpha` formula gives a large, nonsensical
    value instead. `atan2(w, u)` itself remains ill-defined at the single
    physical point `u = w = 0`; that is inherent to using an angle at all
    and is not, and cannot be, "fixed" -- `sin(alpha)` only ensures
    nothing built from it blows up there.
    """
    return AeroCoeffs(
        C_x=p.aero.C_A0,
        C_z=p.aero.C_N_alpha * np.sin(alpha),
        C_m=p.aero.C_m_alpha * np.sin(alpha),
        C_mq=p.aero.c_mq,
        l1=p.lengths.l1,
    )


def _table_coeffs(alpha: float, M: float, p) -> AeroCoeffs:
    """`"table"`: `C_A, C_N, C_m` and `l1` read from `p.aero.table`
    (`data/aero/<name>`, this module's own format -- see the module
    docstring), interpolated at run time (bracket-and-clamp in `M`,
    `np.interp` in `alpha`, then blend -- `_table_lookup`).

    `C_mq` (Step 44, architecture.md SS24.4): table-driven only when the
    table has a `c_mq` column, otherwise the constant `p.aero.c_mq` --
    SIGN: positive c_mq is DAMPING in this document's convention (positive
    `C_m` is a nose-down moment here), the opposite of the textbook
    `C_mq < 0`, the same flip `C_m_alpha` already carries. This is a
    deliberate exception to this model's usual "table wins completely"
    rule: every table committed before Step 44 lacks the column, so an
    absent column must fall back to `p.aero.c_mq`, not to a literal `0.0`,
    for a user to be able to try a single constant damping value without
    regenerating a whole `(M, alpha)` grid.

    Step 55: `l1` now comes out of this same bundle as the force/moment
    coefficients, closing the pre-existing leak (architecture-28-rewrite.md
    F2) where `dynamics.py`'s CoP-arm lookup and `forces.py`'s force/
    moment lookup could independently disagree about whether a table was
    in effect.
    """
    table = _load_table(p.aero.table)
    if table.C_mq is not None:
        C_mq = _table_lookup(table, alpha, M, table.C_mq)
    else:
        C_mq = p.aero.c_mq
    return AeroCoeffs(
        C_x=_table_lookup(table, alpha, M, table.C_A),
        C_z=_table_lookup(table, alpha, M, table.C_N),
        C_m=_table_lookup(table, alpha, M, table.C_m),
        C_mq=C_mq,
        l1=_table_lookup(table, alpha, M, table.l1),
    )


_AERO_MODELS = {
    "constant": _constant_coeffs,
    "linearized": _linearized_coeffs,
    "table": _table_coeffs,
}


def coefficients(t: float, y: np.ndarray, p, flow, hold=None) -> AeroCoeffs:
    """The one public seam: all five aero coefficients at once, dispatched
    on `p.aero.model` (architecture-28-rewrite.md SS28.5.1) -- the same
    `_MODELS[key](...)` shape `gravity.py`/`wind.py` already use
    (architecture.md SS12). An unknown `p.aero.model` string raises
    `KeyError` at this call, this project's established convention for
    every other model-selection dict (no input validation, architecture.md
    SS12/SS20) -- matching `gravity_model="linear"`'s removal at Step 34.

    Step 57 (architecture-28-rewrite.md SS28.6): after the base model is
    computed, `control.aero_coeff_delta(t, y, p, flow, base)` is called
    through, letting a controller (airbrake coefficient modulation,
    eventually guidance) override or perturb `C_x`/`C_z`/`C_m`/`l1` as a
    function of vehicle state -- this is the single choke point, so every
    downstream consumer (forces.py's axial force, normal force, static
    moment and damping term, and dynamics.py's CoP moment arm) sees one
    consistent, controlled coefficient set, rather than needing the
    perturbation applied at each of those call sites separately (the exact
    leak Step 55/F2 closed -- see `sim/control.py`'s module docstring for
    the full plug-in contract). `p.control.aero_coeff_model = "none"` (the
    default) makes this an identity pass-through, bit-for-bit every prior
    step -- `_no_aero_delta` returns `base` itself unchanged.

    Step 59 (architecture-28-rewrite.md SS28.8): `hold` is an optional
    `sim.sampling.Hold`, default `None` -- passed straight through to
    `control.aero_coeff_delta`, which is itself the single choke point for
    any future sampled-data coefficient controller (see that function's
    own docstring for why it is not forwarded any further yet).
    """
    base = _AERO_MODELS[p.aero.model](flow.alpha, flow.M, p)
    # Local import: circular-import avoidance -- sim.control imports
    # AeroCoeffs (this module) at module level for its own type hints, so
    # this module must not import sim.control at module-load time. Same
    # precedent as sim/flow.py's `_wind_inertial` / sim/forces.py's
    # `parachute_drag_inertial` deferring their own `from sim import wind`
    # for the identical reason.
    from sim import control

    return control.aero_coeff_delta(t, y, p, flow, base, hold)


# ----------------------------------------------------------------------
# Thin per-coefficient wrappers (architecture-28-rewrite.md D-7), kept so
# existing call sites/tests that read one coefficient at a time keep their
# pre-Step-55 `(alpha, M, p)` signature unchanged.
# ----------------------------------------------------------------------


def C_A(alpha: float, M: float, p) -> float:
    """Axial-force coefficient (models.tex: `A_x = qSC_x`, `C_x == C_A`).
    See `coefficients`/`AeroCoeffs` for the full dispatch this wraps."""
    return _AERO_MODELS[p.aero.model](alpha, M, p).C_x


def C_N(alpha: float, M: float, p) -> float:
    """Normal-force coefficient (models.tex: `A_z = qSC_z`, `C_z == C_N`).
    See `coefficients`/`AeroCoeffs` for the full dispatch this wraps."""
    return _AERO_MODELS[p.aero.model](alpha, M, p).C_z


def C_m(alpha: float, M: float, p) -> float:
    """Pitching-moment coefficient (models.tex: `A_m = qSd_ref*C_m`).
    See `coefficients`/`AeroCoeffs` for the full dispatch this wraps."""
    return _AERO_MODELS[p.aero.model](alpha, M, p).C_m


def C_mq(alpha: float, M: float, p) -> float:
    """Pitch-damping derivative (analysis.tex SSDynamic stability).
    See `coefficients`/`AeroCoeffs` for the full dispatch this wraps,
    and `_table_coeffs`'s docstring for the sign convention and the
    optional-column fallback."""
    return _AERO_MODELS[p.aero.model](alpha, M, p).C_mq


def cop_l1(alpha: float, M: float, p) -> float:
    """CoP-to-CoG distance [m] -- the same quantity as `Params.lengths.l1`,
    now a function of `(alpha, M)` only under the `"table"` model
    (architecture.md SS19: "CoP travel makes l1 a function of (alpha, M),
    which couples straight back into the moment"). See `coefficients`/
    `AeroCoeffs` for the full dispatch this wraps."""
    return _AERO_MODELS[p.aero.model](alpha, M, p).l1
