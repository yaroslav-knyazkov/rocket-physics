"""Aerodynamic coefficients C_x(alpha, M), C_z(alpha, M), C_m_code(alpha, M),
C_mq_code(alpha, M) and the CoP-to-CoG distance l1(alpha, M) -- an explicit
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
`"constant"`'s `C_x`/`C_z`/`C_m_code` used to be raw-Newton/Newton-metre
placeholders (`A_x`, `A_z`, `A_m`), the only aero model that ignored the
atmosphere entirely. They are now true dimensionless coefficients, scaled
by dynamic pressure and reference area/length exactly like the other two
models (`forces.py`'s `aero_force_body`/`aero_moment_y`) -- see
`_constant_coeffs` below.

The public seam is a single function, `coefficients(t, y, p, flow) ->
AeroCoeffs`, returning all five coefficients at once (axial-force,
normal-force, pitching-moment, pitch-damping, CoP-to-CoG distance) --
`AeroCoeffs`'s own docstring lists the fields. `C_A`/`C_N`/`C_m_code`/`C_mq_code`/
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

Step 99 (Phase 2.17, architecture-35 SS35.4.3, D-110/D-111): table v2. Exactly
one of `l1_m` (legacy arm CoP->CoG) or `l_p_m` (moment reference station from the
nose, `x_ref`; the arm is `l_p_m - l_g(t)` with `l_g` from `sim/mass.py`, or
`Lengths.l_g` with the mass model off) must be present. A `# cm_convention: code|standard` header line
(default `code`) declares the sign of `C_m`; `standard` is flipped on load.
The thrust-point arm keeps its legacy `-(l1 + l2)` expression, so a station
config must have `misalign_deg == 0` (`validate`). `data/aero/example.csv` is
unchanged; `example_v2.csv` is its v2 sibling.

Step 102 (Phase 2.17, D-109): an optional `f_b` column (air-brake deployment
fraction, rectangular `(f_b, M, alpha)` grid, axis starting at 0.0) lets the table
carry the brake's effect on `C_A`, `C_N`, `C_m` and the moment reference station `l_p_m`. It is read
only under `Control.airbrake_aero = "table"` (then the additive `q Cd S_max f_b` term
of `forces.py` is off); under the default `"additive"` the table is read at `f_b = 0`.
Order of operations: blend the two bracketing `f_b` planes (`_at_fb`, clamped at the
edges), then look up `(M, alpha)`, then -- beyond the alpha edge with
`table_oob = "jorgensen"` -- apply the large-alpha extension to the blended values.

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
`C_A`/`C_m_code`/`cop_l1` for one uniform interface -- the `"constant"`/
`"linearized"` models ignore `M` entirely (matching main.tex and the
pre-Step-25 formula exactly), and the `"table"` model is free to encode
`M`-dependence in `C_N` too if the data has it (real compressible
normal-force slopes do vary with Mach), without needing a second,
differently-shaped function.
"""

import functools
import re
import warnings
from typing import NamedTuple

import numpy as np

from sim import datafiles, mass
from sim.state import M as _IDX_M

# Step 99 (D-111): C_m sign conventions. "code" = the simulator's (positive C_m is
# nose-down, so a restoring moment has a positive dC_m/dalpha); "standard" = textbook
# (restoring = negative slope), converted to "code" at load/use.
CM_CONVENTIONS = ("code", "standard")
_CM_CONVENTION_RE = re.compile(r"^#\s*cm_convention\s*:\s*(\S+)\s*$")
_CM_CONVENTION_MENTION_RE = re.compile(r"cm[\s_\-]*convention", re.IGNORECASE)

# Step 93 (Phase 2.16, D-91/D-92, architecture-34 SS34.3): half-width of the
# nose-first plateau of the axial flow-direction factor. Step 118 (D-127,
# conventions-audit SS2 option c): outside this plateau the factor is now a
# cos^2-shaped (not linear) transition anchored at this same 85 deg edge --
# see axial_flow_factor's own docstring for the formula and the reasoning.
_COS_ALPHA0 = float(np.cos(np.radians(85.0)))

# Step 112 (D-120): large-alpha extension of the table model (Jorgensen).
TABLE_OOB_MODES = ("clamp", "jorgensen")

# Step 102 (D-109): how the air brake enters the aerodynamics (Control.airbrake_aero).
AIRBRAKE_AERO_MODES = ("additive", "table")

# Finite-length factor eta vs fineness lam = S_p / d_ref^2 (~ L/d). Source: Jorgensen NASA TR R-474
# Fig. 4 (digitized, +-0.005), low crossflow Mach. Linear interpolation, clamped outside [2, 40].
# NOT modelled: the rise of eta with crossflow Mach (-> ~1 supersonic).
_ETA_LAM = np.array([2.0, 4.0, 6.0, 8.0, 10.0, 12.0, 15.0, 20.0, 30.0, 40.0])
_ETA_VAL = np.array([0.577, 0.607, 0.643, 0.668, 0.685, 0.701, 0.724, 0.753, 0.795, 0.815])

# UNVERIFIED: C_dn = 1.2 (constant, subsonic subcritical cylinder crossflow). Mach/Re dependence
# (transonic peak 1.6-2.0, supercritical drop) is out of scope (backlog B35). Field default: Aero.C_dn.
# UNVERIFIED: tail-first axial magnitude. Jorgensen uses a separate C_A(180 deg); its value is not
# verified here, so Aero.C_x180 == 0.0 falls back to C_x(0) of the table. The user should set it.


class AeroRangeWarning(UserWarning):
    """Table aero asked for an alpha outside the table under `table_oob='clamp'`."""


# Module-global once-per-run flag set: it is re-armed only by `reset_oob_warning()`, which
# `run_sim` calls at entry; a direct caller of `coefficients`/`derivatives` outside `run_sim`
# warns once per process per table unless it calls `reset_oob_warning()` itself.
_OOB_WARNED: set = set()


def reset_oob_warning() -> None:
    """Re-arm the once-per-run out-of-range warning (called at `run_sim` entry)."""
    _OOB_WARNED.clear()


def axial_flow_factor(alpha: float) -> float:
    """Flow-direction factor of the axial force. Let `r = cos(alpha) /
    cos(85 deg)`; `f = clip(r * |r|, -1, +1)` (D-92/D-127). Exactly `1.0`
    for `|alpha| <= 85 deg` (nose-first flight is bit-for-bit unchanged --
    `r >= 1` there, so `r*|r| >= 1` and the clip holds it at exactly `1.0`),
    `0` at `+-90 deg`, `-1` for `|alpha| >= 95 deg`: the axial force then
    points toward the nose, i.e. against the motion of a tail-first vehicle
    (architecture-34 SS34.3).

    Step 118 (D-127, conventions-audit SS2 option c): outside the plateau
    this is `cos^2`-shaped -- proportional to `(cos alpha / cos 85 deg)^2`,
    a squared ratio anchored at the plateau's own 85 deg edge so it stays
    exactly continuous there -- replacing the earlier, invented linear-in-
    `cos(alpha)` ramp. This is a renormalised cos^2 *family* curve, NOT
    Jorgensen's own two-anchor form (`C_A(0)*cos^2(alpha)` nose-first,
    `C_A(180)*cos^2(alpha)` tail-first, anchored at alpha=0/180 deg and
    needing a second, separately-measured constant, `Aero.C_x180`) -- this
    function stays a pure function of `alpha` alone, matching every call
    site's existing usage. See dev/docs/task-118-axial-cos2-hybrid.md
    SS118.5 for why that is a deliberate limitation, not an oversight.
    """
    r = float(np.cos(alpha)) / _COS_ALPHA0
    return min(1.0, max(-1.0, r * abs(r)))


def _table_axial_factor(table: "_AeroTable", alpha: float) -> float:
    """D-93: apply `axial_flow_factor` to a table's `C_A` only when its alpha
    grid stays strictly inside (-90, +90) deg; a table that covers reversed
    flow is authoritative and is not flipped a second time."""
    if table.alpha[0] > -np.pi / 2 and table.alpha[-1] < np.pi / 2:
        return axial_flow_factor(alpha)
    return 1.0


class _AeroTable(NamedTuple):
    M: np.ndarray       # (n_M,), ascending
    alpha: np.ndarray   # (n_alpha,), ascending, radians
    C_A: np.ndarray     # (n_M, n_alpha)
    C_N: np.ndarray     # (n_M, n_alpha)
    C_m_code: np.ndarray     # (n_M, n_alpha) -- always code sign (post `cm_convention` flip at load, Step 117/D-126)
    l1: "np.ndarray | None"   # (n_M, n_alpha), CoP-to-CoG distance [m]; None for a v2 (`l_p_m`) table
    C_mq_code: "np.ndarray | None"  # (n_M, n_alpha), pitch-damping derivative (always code sign, Step 117), or None when the column is absent
    l_p: "np.ndarray | None" = None  # (n_M, n_alpha), moment reference station from the nose [m] (`x_ref`); None for a legacy (`l1_m`) table
    # Step 102 (D-109): brake-fraction axis. `None` = no `f_b` column. Otherwise `f_b` is the ascending
    # grid (starting at 0.0), `planes[k]` the 2-D table at `f_b[k]`, and the arrays above are `planes[0]`.
    f_b: "np.ndarray | None" = None
    planes: "tuple | None" = None
    cm_convention: str = "code"  # Step 119 (D-128/B36): this table's own declared `# cm_convention:`
                                  # header value ("code" default, same as _load_table's own local
                                  # default). Used ONLY by _table_coeffs's scalar c_mq fallback, to
                                  # flip a user-supplied constant exactly as a c_mq *column* in this
                                  # same file would have been flipped. Every plane of a multi-f_b
                                  # table shares the same value (it is a per-file, not per-plane,
                                  # property) -- _at_fb's _replace() leaves it untouched, correctly.


def _load_table_impl(path: str) -> _AeroTable:
    data_lines = []
    cm_convention = "code"
    seen_convention = False
    with open(path) as f:
        for line in f:
            stripped = line.strip()
            if not stripped:
                continue
            if stripped.startswith("#"):
                m_conv = _CM_CONVENTION_RE.match(stripped)
                if not m_conv and _CM_CONVENTION_MENTION_RE.search(stripped):
                    # QA-1: a near-miss (trailing text, '=', other case) must never be a
                    # silent no-op -- that would leave a textbook-sign table unflipped.
                    raise ValueError(
                        f"Aero table '{path}': malformed cm_convention line {stripped!r} "
                        f"(expected exactly '# cm_convention: <{'|'.join(CM_CONVENTIONS)}>')"
                    )
                if m_conv:
                    if seen_convention:
                        raise ValueError(
                            f"Aero table '{path}': cm_convention declared more than once"
                        )
                    seen_convention = True
                    cm_convention = m_conv.group(1)
                continue
            data_lines.append(line)
    if cm_convention not in CM_CONVENTIONS:
        raise ValueError(
            f"Aero table '{path}': unknown cm_convention {cm_convention!r} "
            f"(expected one of {CM_CONVENTIONS})"
        )

    if len(data_lines) < 2:  # empty file, or a header with no rows
        raise ValueError(f"Aero table '{path}' has no data rows")

    header = [h.strip() for h in data_lines[0].split(",")]
    dups = sorted({h for h in header if header.count(h) > 1})
    if dups:  # QA-2: genfromtxt would silently rename the later column and ignore it
        raise ValueError(f"Aero table '{path}': duplicate column header(s) {dups}")
    missing = [c for c in ("alpha_deg", "M", "C_A", "C_N", "C_m") if c not in header]
    if missing:  # QA-10
        raise ValueError(f"Aero table '{path}': missing required column(s) {missing}")

    data = np.atleast_1d(
        np.genfromtxt(data_lines, delimiter=",", names=True, dtype=float)
    )
    for col in data.dtype.names:  # QA-3: NaN / non-numeric / empty cell
        if not np.all(np.isfinite(data[col])):
            raise ValueError(f"Aero table '{path}': column {col!r} has a non-finite or non-numeric value")

    M_col = data["M"].astype(float)
    alpha_col = np.radians(data["alpha_deg"].astype(float))
    C_A_col = data["C_A"].astype(float)
    C_N_col = data["C_N"].astype(float)
    C_m_col = data["C_m"].astype(float)
    if cm_convention == "standard":  # D-111: textbook sign -> the code's (positive = nose-down)
        C_m_col = -C_m_col
    # Step 99 (D-110/D-111): exactly one arm column -- `l1_m` (legacy CoP-to-CoG arm)
    # xor `l_p_m` (moment reference station from the nose, `x_ref`; the arm is then l_p_m - CoG(t)).
    has_l1 = "l1_m" in data.dtype.names
    has_lp = "l_p_m" in data.dtype.names
    if has_l1 == has_lp:
        raise ValueError(
            f"Aero table '{path}': give exactly one of the columns 'l1_m' and "
            f"'l_p_m' (got {'both' if has_l1 else 'neither'})"
        )
    l1_col = data["l1_m"].astype(float) if has_l1 else None
    l_p_col = data["l_p_m"].astype(float) if has_lp else None
    # Step 44 (architecture.md SS24.4): the c_mq column is optional -- every
    # table committed before this step lacks it, so "absent -> None" (and
    # _table_coeffs's constant fallback below) must hold for bit-for-bit
    # backward compatibility. This is the only column handled this way;
    # every other column above is mandatory.
    C_mq_col = data["c_mq"].astype(float) if "c_mq" in data.dtype.names else None
    if C_mq_col is not None and cm_convention == "standard":
        # Step 114: the textbook C_mq < 0 (damping) -> the code's sign (positive = damping),
        # the same flip as C_m above.
        C_mq_col = -C_mq_col

    M_grid = np.unique(M_col)
    alpha_grid = np.unique(alpha_col)
    n_M = M_grid.size
    n_a = alpha_grid.size

    # Step 102 (D-109): optional `f_b` column -> one (M, alpha) plane per brake fraction.
    fb_col = data["f_b"].astype(float) if "f_b" in data.dtype.names else None
    fb_grid = np.unique(fb_col) if fb_col is not None else None
    n_fb = 1 if fb_grid is None else fb_grid.size

    if M_col.size != n_fb * n_M * n_a:
        axes = "(M, alpha)" if fb_grid is None else "(f_b, M, alpha)"
        raise ValueError(
            f"Aero table '{path}' is not a rectangular {axes} grid: "
            f"{M_col.size} rows, expected {n_fb * n_M * n_a}"
        )
    if fb_grid is not None and (fb_grid[0] != 0.0 or n_fb < 2):
        raise ValueError(
            f"Aero table '{path}': the f_b axis must start at 0.0 (brake closed) "
            f"and have at least two values, got {fb_grid.tolist()}"
        )

    def _plane(rows: np.ndarray) -> _AeroTable:
        """One `(M, alpha)` plane out of the rows selected by the boolean `rows`."""

        def _reshape(col: np.ndarray) -> np.ndarray:
            grid = np.empty((n_M, n_a))
            for i, m in enumerate(M_grid):
                mask = (M_col == m) & rows
                row_alpha = alpha_col[mask]
                order = np.argsort(row_alpha)
                if row_alpha.size != n_a or not np.allclose(row_alpha[order], alpha_grid):
                    raise ValueError(
                        f"Aero table '{path}': the alpha grid at M={m} does not "
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
            C_m_code=_reshape(C_m_col),
            l1=_reshape(l1_col) if l1_col is not None else None,
            C_mq_code=_reshape(C_mq_col) if C_mq_col is not None else None,
            l_p=_reshape(l_p_col) if l_p_col is not None else None,
            cm_convention=cm_convention,  # Step 119/B36: the enclosing _load_table's already-
                                           # parsed, already-validated local variable (line 246) --
                                           # no new parsing, just carrying the existing value through.
        )

    if fb_grid is None:
        return _plane(np.ones(M_col.shape, dtype=bool))
    planes = tuple(_plane(fb_col == f) for f in fb_grid)
    # The top-level arrays are the brake-closed plane (f_b = 0): the additive-brake mode reads them.
    return planes[0]._replace(f_b=fb_grid, planes=planes)


_load_table_cached = functools.lru_cache(maxsize=None)(_load_table_impl)


def _load_table(name: str) -> _AeroTable:
    """Read `data/aero/<name>` into a rectangular `(M, alpha)` grid.

    `name` is resolved via `sim.datafiles.resolve` ("aero") before the
    lookup, and the cache sits on the *resolved* absolute path, not the
    raw `name` string -- a cwd-relative name is never served a stale
    resolution across a change of working directory between two calls
    with the same string (see `sim/datafiles.py`'s docstring).
    """
    path = datafiles.resolve(name, "aero")
    return _load_table_cached(path)


_load_table.cache_clear = _load_table_cached.cache_clear


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


def _at_fb(table: _AeroTable, fb: float) -> _AeroTable:
    """The 2-D `(M, alpha)` table at brake fraction `fb` (Step 102, D-109): the two bracketing
    `f_b` planes blended linearly, clamped at both ends (no extrapolation, like M). A table
    without an `f_b` column is returned as is; at a plane's own `f_b` (and beyond the edges) the
    plane is returned untouched, so `f_b = 0` is exactly the brake-closed table. Interpolation is
    linear in the grid values, so blending the grids equals blending the looked-up coefficients;
    doing it on the grids lets the alpha extension (`_jorgensen_extend`) see the blended edge values."""
    planes = table.planes
    if planes is None:
        return table
    grid = table.f_b
    if fb <= grid[0]:
        return planes[0]
    if fb >= grid[-1]:
        return planes[-1]
    j = int(np.searchsorted(grid, fb))
    if fb == grid[j]:  # exactly on a grid node: the stored plane, no re-blend / allocation
        return planes[j]
    lo, hi = planes[j - 1], planes[j]
    w = (fb - grid[j - 1]) / (grid[j] - grid[j - 1])

    def _mix(a, b):
        return None if a is None else a + w * (b - a)

    return lo._replace(
        C_A=_mix(lo.C_A, hi.C_A), C_N=_mix(lo.C_N, hi.C_N), C_m_code=_mix(lo.C_m_code, hi.C_m_code),
        l1=_mix(lo.l1, hi.l1), C_mq_code=_mix(lo.C_mq_code, hi.C_mq_code), l_p=_mix(lo.l_p, hi.l_p),
    )


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
    C_m_code: float    # pitching-moment coefficient, ALWAYS code sign (post-dispatch/post-`_cm_to_code`;
                        # Step 117/D-126 rename -- do not read this as the declared `cm_convention`,
                        # it is already flipped to the code's convention regardless of input).
    C_mq_code: float   # pitch-damping derivative, same always-code-sign guarantee as C_m_code.
    l1: float     # CoP(D)-to-CoG(B) distance [m]


def _cm_to_code(C_m: float, p) -> float:
    """Step 99 (D-111): apply `Aero.cm_convention` to a constant/linearized
    `C_m`; "code" (default) returns it untouched (bit-for-bit legacy)."""
    conv = p.aero.cm_convention
    if conv == "code":
        return C_m
    if conv == "standard":
        return -C_m
    raise ValueError(f"Aero.cm_convention {conv!r} not in {CM_CONVENTIONS}")


def _arm_or_station(p) -> float:
    """Constant/linearized models: `Aero.l_p` (a moment reference station, turned into an
    arm by `_resolve_arm`) when set, else the legacy arm `Lengths.l1`."""
    return p.aero.l_p if p.aero.l_p > 0.0 else p.lengths.l1


def uses_l_p(p) -> bool:
    """True when the moment reference is given as a station from the nose (`x_ref`, an `l_p_m` table,
    or `Aero.l_p > 0` under constant/linearized) rather than as the arm `l1`.

    Known limitation (not fixed here): `Aero.l_p == 0.0` also means "off" for constant/linearized
    models, so a user cannot express "my moment reference station is the nose tip" there even though
    it is the most common CFD convention -- a v2 table does not have this problem (`l_p_m = 0.0` is a
    normal station value, only the scalar `Aero.l_p` field collides with its own off-switch)."""
    if p.aero.model == "table":
        return _load_table(p.aero.table).l_p is not None
    return p.aero.l_p > 0.0


def cg_station(y, p) -> float:
    """CoG station from the nose tip [m] at state `y`: `mass.cog_position` of
    the remaining propellant when the mass model is on (`y=None` -> launch
    mass), else the constant `Lengths.l_g` (fail-fast when it is unset)."""
    if p.weight.m_d is None:
        if p.lengths.l_g <= 0.0:
            raise ValueError(
                "a moment reference station (Aero.l_p / table l_p_m) with the mass model off "
                "needs Lengths.l_g > 0 (CoG station from the nose)"
            )
        return p.lengths.l_g
    m = p.weight.m if y is None else y[_IDX_M]
    return mass.cog_position(mass.propellant_mass(m, p), p)


def _resolve_arm(base: "AeroCoeffs", y, p) -> "AeroCoeffs":
    """Turn a moment reference station into the CoP-reference-to-CoG arm `l_p - l_g(t)` (Step 99,
    D-110); legacy configs pass through untouched (same object)."""
    if not uses_l_p(p):
        return base
    return base._replace(l1=base.l1 - cg_station(y, p))


def validate(p) -> None:
    """Fail-fast checks for the Step-99 aero options, called from
    `configs.schema.assemble` (and usable directly): known `cm_convention`;
    with a CP station, a CoG station when the mass model is off, and no
    nozzle cant (the thrust arm keeps its legacy `-(l1 + l2)` expression, which
    is meaningless for station configs -- on-axis thrust has zero moment, so
    `misalign_deg` must be 0)."""
    if p.aero.cm_convention not in CM_CONVENTIONS:
        raise ValueError(
            f"Aero.cm_convention {p.aero.cm_convention!r} not in {CM_CONVENTIONS}"
        )
    if p.aero.l_p < 0.0:
        raise ValueError(f"Aero.l_p must be >= 0 (0.0 = off), got {p.aero.l_p}")
    if p.aero.l_ref < 0.0:  # QA-10: negative Reynolds length gives a negative Re
        raise ValueError(f"Aero.l_ref must be >= 0 (0.0 = use d_ref), got {p.aero.l_ref}")
    if p.aero.model == "table" and p.aero.table:
        _load_table(p.aero.table)  # surfaces loader errors early
    _validate_airbrake_aero(p)
    _validate_table_oob(p)
    if uses_l_p(p):
        cg_station(None, p)
        if p.lengths.misalign_deg != 0.0:
            raise ValueError(
                "a moment reference station (l_p / l_p_m) requires Lengths.misalign_deg == 0: "
                "the thrust-point arm is not derived for station configs"
            )


def _validate_airbrake_aero(p) -> None:
    """Step 102 (D-109): `Control.airbrake_aero` is a known mode; `table` has an `f_b` table."""
    mode = p.control.airbrake_aero
    if mode not in AIRBRAKE_AERO_MODES:
        raise ValueError(f"Control.airbrake_aero {mode!r} not in {AIRBRAKE_AERO_MODES}")
    if mode == "additive":
        return
    if p.aero.model != "table" or not p.aero.table:
        raise ValueError(
            "Control.airbrake_aero='table' requires Aero.model == 'table' with a table that has an f_b column"
        )
    if _load_table(p.aero.table).f_b is None:
        raise ValueError(
            f"Control.airbrake_aero='table' needs an f_b column; table '{p.aero.table}' has none"
        )


def _validate_table_oob(p) -> None:
    """Step 112 (112.4): `table_oob` is a known mode; `jorgensen` has what it needs."""
    a = p.aero
    if a.table_oob not in TABLE_OOB_MODES:
        raise ValueError(f"Aero.table_oob {a.table_oob!r} not in {TABLE_OOB_MODES}")
    if a.table_oob == "clamp":
        return
    if a.model != "table":
        raise ValueError("Aero.table_oob='jorgensen' requires Aero.model == 'table'")
    if not uses_l_p(p):
        raise ValueError(
            "Aero.table_oob='jorgensen' needs a v2 table with an l_p_m column "
            "(a legacy l1_m table carries an arm, not a station)"
        )
    t = _load_table(a.table)
    if not (t.alpha[0] < 0.0 < t.alpha[-1]):
        raise ValueError("Aero.table_oob='jorgensen' needs a two-sided table (alpha[0] < 0 < alpha[-1])")
    min_edge = np.radians(2.0)
    if min(abs(t.alpha[0]), abs(t.alpha[-1])) < min_edge:
        raise ValueError(
            "Aero.table_oob='jorgensen' needs both table alpha edges at |alpha| >= 2 deg: the "
            "extension scales the edge C_m_code by Z(alpha)/Z(alpha_edge) with Z = sin(2a)cos(a/2), "
            "which vanishes at 0, so a near-zero edge amplifies it without bound"
        )
    lim = np.radians(80.0)
    if t.alpha[-1] >= lim or t.alpha[0] <= -lim:
        raise ValueError("Aero.table_oob='jorgensen' needs both table alpha edges below 80 deg")
    for name, ok in (
        ("S > 0", a.S > 0.0),
        ("d_ref > 0", a.d_ref > 0.0),
        ("S_p > 0", a.S_p > 0.0),
        ("l_pc > 0", a.l_pc > 0.0),
        ("oob_blend_deg > 0", a.oob_blend_deg > 0.0),
        ("C_dn >= 0", a.C_dn >= 0.0),
        ("0 <= eta <= 1", 0.0 <= a.eta <= 1.0),
        ("C_x180 >= 0", a.C_x180 >= 0.0),
        ("S_base >= 0", a.S_base >= 0.0),
    ):
        if not ok:
            raise ValueError(f"Aero.table_oob='jorgensen' requires {name}")


def _constant_coeffs(alpha: float, M: float, p) -> AeroCoeffs:
    """`"constant"`: fixed inputs, independent of both `alpha` and `M` --
    the cheapest model, for first-cut sizing and for isolating one effect
    at a time in a comparison sweep (models.tex SSAerodynamics >
    Coefficients).

    Step 55's actual fix: `C_x`/`C_z`/`C_m_code` are true dimensionless
    coefficients now, not raw Newton/Newton-metre placeholders -- the
    force/moment they produce is still multiplied by dynamic pressure and
    the reference area/length in `forces.py`'s `aero_force_body`/
    `aero_moment_y`, exactly like the other two models. What is frozen
    under this model is the *coefficients*, not the resulting force: the
    force itself still varies over the flight through `q = 0.5*rho*V^2`.

    Step 93 (D-91, architecture-34 SS34.3): `C_x` is a constant *magnitude*
    whose sign follows the flow, `C_x * axial_flow_factor(alpha)` -- tail-
    first, the axial force opposes the motion instead of accelerating it.
    `C_z`/`C_m_code` are deliberately unchanged (D-95).
    """
    return AeroCoeffs(
        C_x=p.aero.C_x * axial_flow_factor(alpha),
        C_z=p.aero.C_z,
        C_m_code=_cm_to_code(p.aero.C_m, p),
        C_mq_code=_cm_to_code(p.aero.c_mq, p),
        l1=_arm_or_station(p),
    )


def _linearized_coeffs(alpha: float, M: float, p) -> AeroCoeffs:
    """`"linearized"`: a single linear slope in `alpha` about the
    zero-`alpha` condition, `M`-independent, bit-for-bit today's (pre-
    Step-55) `"coefficients"` regime.

    Phase 2.5 (after Step 35): `C_z`/`C_m_code`'s formula uses `sin(alpha)`
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
    `C_z`/`C_m_code`'s sign and (being unbounded) magnitude every RHS call,
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

    Step 93 (D-91, architecture-34 SS34.3): `C_x = C_A0 *
    axial_flow_factor(alpha)`, so the axial force opposes the flow
    tail-first (bit-for-bit unchanged for `|alpha| <= 85 deg`).
    """
    return AeroCoeffs(
        C_x=p.aero.C_A0 * axial_flow_factor(alpha),
        C_z=p.aero.C_N_alpha * np.sin(alpha),
        C_m_code=_cm_to_code(p.aero.C_m_alpha * np.sin(alpha), p),
        C_mq_code=_cm_to_code(p.aero.c_mq, p),
        l1=_arm_or_station(p),
    )


def _table_coeffs(alpha: float, M: float, p, fb: float = 0.0) -> AeroCoeffs:
    """`"table"`: `C_A, C_N, C_m_code` and `l1` read from `p.aero.table`
    (`data/aero/<name>`, this module's own format -- see the module
    docstring), interpolated at run time (bracket-and-clamp in `M`,
    `np.interp` in `alpha`, then blend -- `_table_lookup`).

    `C_mq_code` (Step 44, architecture.md SS24.4): table-driven only when the
    table has a `c_mq` column, otherwise the constant `p.aero.c_mq` --
    SIGN: positive c_mq is DAMPING in this document's convention (positive
    `C_m_code` is a nose-down moment here), the opposite of the textbook
    `C_mq < 0`, the same flip `C_m_alpha` already carries. This is a
    deliberate exception to this model's usual "table wins completely"
    rule: every table committed before Step 44 lacks the column, so an
    absent column must fall back to `p.aero.c_mq`, not to a literal `0.0`,
    for a user to be able to try a single constant damping value without
    regenerating a whole `(M, alpha)` grid.

    Step 119 (D-128/B36): when the column is absent, the fallback scalar is flipped by the
    TABLE's own declared `cm_convention` (not `Params.aero.cm_convention`, which this field's own
    docstring scopes to the constant/linearized models only) -- the fallback stands in for a
    missing column, so it is interpreted exactly as a column would have been.

    Step 55: `l1` now comes out of this same bundle as the force/moment
    coefficients, closing the pre-existing leak (architecture-28-rewrite.md
    F2) where `dynamics.py`'s CoP-arm lookup and `forces.py`'s force/
    moment lookup could independently disagree about whether a table was
    in effect.

    Step 93 (D-91/D-93, architecture-34 SS34.3): `C_A` is multiplied by
    `axial_flow_factor(alpha)` iff the table's alpha grid stays inside
    (-90, +90) deg (`_table_axial_factor`); a table covering reversed flow
    is authoritative and used as is.

    Step 102 (D-109): `fb` is the air-brake deployment fraction. A table with an
    `f_b` column is first blended in `f_b` (`_at_fb`), then looked up in `(M, alpha)`,
    then -- beyond the alpha edge, `table_oob='jorgensen'` -- extended; the brake's
    effect is inside the table (no separate axial-flow factor). `fb=0.0` / no column
    -> the 2-D table itself.
    """
    table = _at_fb(_load_table(p.aero.table), fb)
    if table.C_mq_code is not None:
        C_mq_code = _table_lookup(table, alpha, M, table.C_mq_code)
    elif table.cm_convention == "standard":
        # Step 119 (D-128/B36): the table has no c_mq column of its own -- the scalar fallback
        # must respect the SAME convention the table declares, exactly as a c_mq *column* in
        # this same file would have been flipped at load time (lines ~297-300 above). Mirrors
        # the textbook-C_mq<0 -> code-sign flip documented there.
        C_mq_code = -p.aero.c_mq
    else:
        C_mq_code = p.aero.c_mq
    clamped = AeroCoeffs(
        C_x=_table_lookup(table, alpha, M, table.C_A) * _table_axial_factor(table, alpha),
        C_z=_table_lookup(table, alpha, M, table.C_N),
        C_m_code=_table_lookup(table, alpha, M, table.C_m_code),
        C_mq_code=C_mq_code,
        # Step 99: legacy table -> the arm itself; v2 table -> the CP station
        # (turned into an arm by `_resolve_arm`, which knows the CoG).
        l1=_table_lookup(table, alpha, M, table.l1 if table.l1 is not None else table.l_p),
    )
    # Step 112 (D-120): outside the table's alpha range the lookup clamps; opt into the extension.
    if table.alpha[0] <= alpha <= table.alpha[-1]:
        return clamped
    if p.aero.table_oob == "jorgensen":
        return _jorgensen_extend(clamped, table, alpha, M, p)
    if p.aero.table not in _OOB_WARNED:
        _OOB_WARNED.add(p.aero.table)
        warnings.warn(
            f"Aero table '{p.aero.table}' covers alpha in [{np.degrees(table.alpha[0]):g}, "
            f"{np.degrees(table.alpha[-1]):g}] deg; the flight left it and the edge values are held. "
            "Set Aero.table_oob='jorgensen'; RK45 can stall in tail-first descent "
            "(dev/docs/diagnosis-rk45-v2-table.md).",
            AeroRangeWarning,
            stacklevel=2,
        )
    return clamped


def _Z(a: float) -> float:
    """Potential-flow shape sin(2a) cos(a/2): odd, zero at 0, +-90, +-180 deg."""
    return float(np.sin(2.0 * a) * np.cos(0.5 * a))


def _jorgensen_extend(clamped: AeroCoeffs, table: _AeroTable, alpha: float, M: float, p) -> AeroCoeffs:
    """Step 112 (D-120, architecture-35 SS35.6 / 112.2): smooth blend of the clamped coefficients
    into Jorgensen's large-alpha model beyond the table edge. `C_mq_code` and `l1` stay the clamped
    lookups. Model choices (not paper-verified): smoothstep blend over `oob_blend_deg`; sign of
    the potential term above 90 deg follows the printed `sin(2a)cos(a/2)` (negative there)."""
    ap = p.aero
    a_e = table.alpha[-1] if alpha > 0.0 else table.alpha[0]
    tau = min((abs(alpha) - abs(a_e)) / np.radians(ap.oob_blend_deg), 1.0)
    w = tau * tau * (3.0 - 2.0 * tau)

    # axial: x0 cos^2 nose-first, -x180 cos^2 tail-first (flow-direction sign built in)
    x0 = _table_lookup(table, 0.0, M, table.C_A)
    x180 = ap.C_x180 if ap.C_x180 > 0.0 else x0
    c2 = float(np.cos(alpha)) ** 2
    Cx_J = x0 * c2 if abs(alpha) <= 0.5 * np.pi else -x180 * c2

    S = ap.S
    eta = ap.eta if ap.eta > 0.0 else float(np.interp(ap.S_p / ap.d_ref**2, _ETA_LAM, _ETA_VAL))
    s_base = ap.S_base if ap.S_base > 0.0 else S
    sa = float(np.sin(alpha))
    Cz_cf = eta * ap.C_dn * (ap.S_p / S) * sa * abs(sa)
    Cz_J = (s_base / S) * _Z(alpha) + Cz_cf

    # moment: table residual continued with the potential shape + arm correction of the crossflow
    cm_e = _table_lookup(table, a_e, M, table.C_m_code)
    lp_e = _table_lookup(table, a_e, M, table.l_p)
    Cm_J = cm_e * _Z(alpha) / _Z(a_e) + (ap.l_pc - lp_e) * Cz_cf / ap.d_ref

    return clamped._replace(
        C_x=(1.0 - w) * clamped.C_x + w * Cx_J,
        C_z=(1.0 - w) * clamped.C_z + w * Cz_J,
        C_m_code=(1.0 - w) * clamped.C_m_code + w * Cm_J,
    )


_AERO_MODELS = {
    "constant": _constant_coeffs,
    "linearized": _linearized_coeffs,
    "table": _table_coeffs,
}


def _dispatch(alpha: float, M: float, p, fb: float = 0.0) -> AeroCoeffs:
    """The model dispatch; `fb` reaches only the table model, and only under
    `Control.airbrake_aero == "table"` (Step 102)."""
    model_fn = _AERO_MODELS[p.aero.model]
    if p.aero.model == "table":
        return model_fn(alpha, M, p, fb if p.control.airbrake_aero == "table" else 0.0)
    return model_fn(alpha, M, p)


def coefficients(t: float, y: np.ndarray, p, flow, hold=None, fb: float = 0.0) -> AeroCoeffs:
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
    eventually guidance) override or perturb `C_x`/`C_z`/`C_m_code`/`l1` as a
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

    Step 102 (D-109): `fb` is the brake deployment fraction, computed once per RHS
    call by the caller (`dynamics.derivatives`). It selects the `f_b` plane of a table
    only under `Control.airbrake_aero == "table"`; otherwise (default) it is ignored
    and an `f_b` table is read at `f_b = 0`.
    """
    # Step 99 (D-110): a CP given as a station from the nose becomes the arm
    # `l_p - l_g(t)` here (the CoG moves with the burn); legacy: pass-through.
    base = _resolve_arm(_dispatch(flow.alpha, flow.M, p, fb), y, p)
    # Step 105 (architecture-35 SS35.4.1/SS35.4.5, dispersion hooks): applied here,
    # after every model dispatch and the station-to-arm resolution, so it scales the
    # SAME C_x every actual force/moment consumer (forces.py, dynamics.py) reads through
    # this seam. The `C_A()` thin wrapper below dispatches the model directly, bypassing
    # this seam entirely (same as it already bypasses `_resolve_arm`/`control.aero_coeff_
    # delta` above) -- it is NOT scaled by `cx_scale`, deliberately: nothing in sim/ calls
    # it to compute a force (only tests and report.py's C_m_code slope diagnostic use these
    # per-coefficient wrappers; see `C_A`'s own module-level comment, architecture-28-
    # rewrite.md D-7). `== 1.0` (the default) is skipped entirely, not multiplied by 1.0,
    # so every pinned flight is bit-for-bit unchanged.
    if p.aero.cx_scale != 1.0:
        base = base._replace(C_x=base.C_x * p.aero.cx_scale)
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


def C_N(alpha: float, M: float, p, fb: float = 0.0) -> float:
    """Normal-force coefficient (models.tex: `A_z = qSC_z`, `C_z == C_N`).
    See `coefficients`/`AeroCoeffs` for the full dispatch this wraps.
    Step 116: optional brake fraction `fb` (read only under `airbrake_aero="table"`),
    the same as `C_m_code` -- needed so `sim/report.py`'s derived-CP/combined-stability
    diagnostics (D-125) read the brake-blended plane, not always the closed one."""
    return _dispatch(alpha, M, p, fb).C_z


def C_m_code(alpha: float, M: float, p, fb: float = 0.0) -> float:
    """Pitching-moment coefficient, ALWAYS in the code's sign convention (models.tex:
    `A_m = qSd_ref*C_m`, but see Step 117/D-126 -- this value is already flipped to code
    sign regardless of the declared `cm_convention`; it is not the textbook-sign `C_m`).
    See `coefficients`/`AeroCoeffs` for the full dispatch this wraps.
    Step 102: optional brake fraction `fb` (read only under `airbrake_aero="table"`)."""
    return _dispatch(alpha, M, p, fb).C_m_code


def C_mq_code(alpha: float, M: float, p) -> float:
    """Pitch-damping derivative, ALWAYS in the code's sign convention (analysis.tex
    SSDynamic stability; Step 117/D-126 rename, same guarantee as `C_m_code`).
    See `coefficients`/`AeroCoeffs` for the full dispatch this wraps,
    and `_table_coeffs`'s docstring for the sign convention and the
    optional-column fallback."""
    return _AERO_MODELS[p.aero.model](alpha, M, p).C_mq_code


def cop_l1(alpha: float, M: float, p) -> float:
    """CoP-to-CoG distance [m] -- the same quantity as `Params.lengths.l1`,
    now a function of `(alpha, M)` only under the `"table"` model
    (architecture.md SS19: "CoP travel makes l1 a function of (alpha, M),
    which couples straight back into the moment"). See `coefficients`/
    `AeroCoeffs` for the full dispatch this wraps. Step 99: for a CP-station
    config the CoG is taken at launch mass (no state here); use
    `coefficients(...)` for the arm at a given state."""
    return _resolve_arm(_AERO_MODELS[p.aero.model](alpha, M, p), None, p).l1
