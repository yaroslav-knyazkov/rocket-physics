"""projects/fx27/data/cspace/aero/drag_theory.py -- theoretical
(semi-empirical, Niskanen-thesis/OpenRocket method) C_D0(M) port
(dev/docs/architecture-45-fx27-theory-drag-port.md, "architecture-45"
below).

This module ports the physics of `temporary/drive-download-
20261117T190208Z-1-001/cd_mach_03_increase_D.m` (the CORRECTED source
file for `PRO54_TRANSITION_DM` -- architecture-45 SS2). It is a drop-in
ALTERNATIVE data source for the Mach-dependent drag table
`generate_dm_tables.py` already feeds `apps/sim/engine/aero.py`'s
`model="table"` loader -- see `generate_theory_drag_tables.py` for the
one-off generator that turns `compute_cd0`'s output into that table
format. This module itself is NOT imported at runtime by
`apps/sim/engine/` (that engine stays offline/deterministic,
CLAUDE.md "Профиль проекта"); it is only imported by
`generate_theory_drag_tables.py` (a one-off script) and by
`tests/test_fx27_drag_theory.py`.

Scope this stage (architecture-45 SS3/S6, user: "implement it only for
1 configuration for now"): `Geometry`/`compute_cd0` are fully generic
(work for a constant tube, a converging transition+boat-tail, or a
diverging flare rear body), but only ONE concrete `Geometry` instance
ships -- `PRO54_TRANSITION_GEOMETRY`. `PRO54_EQUAL_GEOMETRY`/
`PRO75_GEOMETRY` are deferred (same pattern, add later); `PRO75_GEOMETRY`
is additionally blocked on a file-mapping confirmation from the user
(SS2).

Mach-regime handling (SS4, decided): the source script's "paper" method
(M 0.1-0.75) is NOT ported -- it was a comparison baseline, never
exported downstream of the plot in the source. The OpenRocket/Niskanen
method is used across the ENTIRE 0.10-1.30 range (`_cd0_transonic`),
concatenated at M=1.30 with its own hand-extended supersonic branch
(`_cd0_supersonic`, M 1.30-3.00) -- continuous there by construction,
since both branches route every shared computation through the exact
same helper functions (see each function's own docstring below).

Known gap (SS6/T45-1, not fixed this stage): the boat-tail/flare
contribution (`_boattail_contribution`) has 3 geometric cases -- the
converging ("boat-tail base-drag law") case is a verbatim port of
`cd_mach_03_increase_D.m`'s own branch and is exercised/tested this
stage; the diverging ("flare wave-drag law via `_ormach_cone`") case's
exact formula lives only in `cd_mach_03_decrease_D.m`, which this stage
deliberately does not read (PRO75's own file mapping is UNCONFIRMED,
SS2) -- that branch raises `NotImplementedError` rather than guess at
an unverified formula. `PRO54_TRANSITION_GEOMETRY` never reaches it
(both its rear-body segments converge).
"""

from __future__ import annotations

import dataclasses
import math

import numpy as np
from scipy import integrate

# ---- constants shared by all 3 source MATLAB scripts (architecture-45 SS2) ----
_A_MOTOR_M2 = 0.0  # m^2 -- coasting (A_motor=0 in every source script)

# Stoney Von-Karman nose-wave-drag tables (thesis App. B), transonic (0.80-1.50)
# and the scripts' own hand-extended supersonic continuation (1.30-3.00).
_STONEY_M = np.array([0.80, 0.90, 0.95, 1.00, 1.05, 1.10, 1.20, 1.30, 1.50])
_STONEY_CD = np.array([0.00, 0.02, 0.05, 0.12, 0.17, 0.20, 0.21, 0.20, 0.18])
_STONEY_M_SUP = np.array([1.30, 1.50, 2.00, 2.50, 3.00])
_STONEY_CD_SUP = np.array([0.20, 0.18, 0.15, 0.13, 0.12])


@dataclasses.dataclass(frozen=True)
class Geometry:
    """Every geometry/physical constant the source scripts read, spelled
    out per-variant rather than factored into a shared-base-plus-override
    shape (architecture-45 SS3: a future change to one variant's fin
    geometry, say, must not risk silently changing another's through a
    shared mutable/partial default -- also keeps each instance directly
    diffable against its own `.m` file)."""

    # nose (shared across all 3 source scripts, but spelled out per instance)
    L: float  # m, nose length
    D1: float  # m, nose-base / forward-tube diameter (= SBT's reference diameter, always)
    haack_C: float  # Haack series shape param (0.0 = Von Karman, all 3 source scripts)
    # rear body (the ONE block that differs per variant -- SS2)
    L1: float
    D2: float
    L2: float
    Ltr: float
    Lbt: float
    D_fore: float
    D3: float
    # fins (shared)
    CR: float
    CT: float
    SS: float
    tf: float
    N: int
    sweep_len: float
    # lugs (shared)
    nB: int
    dB: float
    hB: float
    # flight condition (shared) -- v_design is carried through for provenance/
    # future design-point reporting only; compute_cd0 itself does not use it
    # (the source script's own M_design/fprintf design-point line is not part
    # of the ported C_D0(M) curve).
    h_alt_m: float
    v_design: float
    # OpenRocket-method inputs (shared)
    Rs: float = 20e-6
    fin_profile: str = "square"


@dataclasses.dataclass(frozen=True)
class _Derived:
    """Geometry-derived quantities that do not depend on Mach -- computed
    once per `compute_cd0` call, shared by both the transonic and
    supersonic branches."""

    SW: float
    SBT: float
    Lt: float
    FR: float
    c: float
    SF: float
    S_LL: float
    Gam_L: float
    fN: float
    rho: float
    mu: float
    a_air: float


# --- the 3 duplicated MATLAB local functions, collapsed to one copy each ---


def _ormach_blend(M: np.ndarray, sub_fn, sup_fn) -> np.ndarray:
    """Verbatim port of the source's `ormach_blend` local function: a
    linear (not smoothstep) blend between `sub_fn` and `sup_fn` across
    0.9 <= M <= 1.1, exact `sub_fn(0.9)`/`sup_fn(1.1)` at the two
    boundaries."""
    M = np.asarray(M, dtype=float)
    out = np.zeros_like(M)
    a = M <= 0.9
    b = M >= 1.1
    m = ~a & ~b
    out[a] = sub_fn(M[a])
    out[b] = sup_fn(M[b])
    w = (M[m] - 0.9) / 0.2
    out[m] = sub_fn(0.9) * (1 - w) + sup_fn(1.1) * w
    return out


def _ormach_qr(M: np.ndarray) -> np.ndarray:
    """Verbatim port of the source's `ormach_qr` local function (Eq. B.1/
    B.2 stagnation-pressure-ratio approximation): subsonic branch for
    `M < 1`, supersonic branch for `M >= 1` (note `M == 1.0` routes to the
    supersonic branch, per the source's own `s = M<1` test -- NOT a
    continuous join, a property of the source formulas themselves, see
    `tests/test_fx27_drag_theory.py`)."""
    M = np.asarray(M, dtype=float)
    q = np.zeros_like(M)
    s = M < 1.0
    q[s] = 1.0 + M[s] ** 2 / 4.0 + M[s] ** 4 / 40.0
    ns = ~s
    q[ns] = 1.84 - 0.76 / M[ns] ** 2 + 0.166 / M[ns] ** 4 + 0.035 / M[ns] ** 6
    return q


def _ormach_cone(M: np.ndarray, se: float) -> np.ndarray:
    """Verbatim port of the source's `ormach_cone` local function
    (conical-nose wave-drag closed form, thesis App. B.4-B.6): a power
    law below M=1, a cubic spline fit to match value+slope at both M=1
    and the hinge Mach `Mh=1.3`, and the closed-form high-Mach branch
    above `Mh`. Not called by `compute_cd0` for `PRO54_TRANSITION_GEOMETRY`
    (its nose-wave drag uses the Stoney-table path, `useStoney=true` in
    every source script) -- kept as a direct port because the source
    scripts define it as a shared local function and
    `tests/test_fx27_drag_theory.py` exercises its own hinge-continuity
    independently of geometry."""
    gam = 1.4
    M = np.asarray(M, dtype=float)
    C1 = se
    s1 = 4.0 / (gam + 1.0) * (1.0 - 0.5 * C1)
    Mh = 1.3
    Ch = 2.1 * se**2 + 0.5 * se / math.sqrt(Mh**2 - 1.0)
    sh = -0.5 * se * Mh * (Mh**2 - 1.0) ** (-1.5)
    A = np.array(
        [
            [1.0, 1.0, 1.0, 1.0],
            [0.0, 1.0, 2.0, 3.0],
            [1.0, Mh, Mh**2, Mh**3],
            [0.0, 1.0, 2.0 * Mh, 3.0 * Mh**2],
        ]
    )
    rhs = np.array([C1, s1, Ch, sh])
    pc = np.linalg.solve(A, rhs)
    C = np.zeros_like(M)
    lo = M < 1.0
    mid = (M >= 1.0) & (M < Mh)
    hi = M >= Mh
    b = s1 / C1
    a = C1
    C[lo] = a * M[lo] ** b
    C[mid] = pc[0] + pc[1] * M[mid] + pc[2] * M[mid] ** 2 + pc[3] * M[mid] ** 3
    C[hi] = 2.1 * se**2 + 0.5 * se / np.sqrt(M[hi] ** 2 - 1.0)
    return C


# --- geometry-derived helpers ---


def _nose_wetted_area(L: float, D1: float, haack_C: float) -> float:
    """Wetted area of the Haack-series nose (source: numeric `integral`
    over the nose surface-of-revolution profile `y(x)`), verbatim port
    via `scipy.integrate.quad`. `max(f, realmin)` in the source (avoids a
    0/0 at the nose tip x=0, where both the numerator `sin(theta)` and
    `f` vanish together) is ported as `max(f, tiny)`."""
    R = D1 / 2.0
    tiny = np.finfo(float).tiny

    def theta(x):
        return np.arccos(1.0 - 2.0 * x / L)

    def f(x):
        th = theta(x)
        return th - np.sin(2.0 * th) / 2.0 + haack_C * np.sin(th) ** 3

    def y(x):
        return (R / math.sqrt(math.pi)) * np.sqrt(np.maximum(f(x), 0.0))

    def dydx(x):
        th = theta(x)
        fx = np.maximum(f(x), tiny)
        return (
            (R / math.sqrt(math.pi))
            * np.sin(th)
            * (2.0 + 3.0 * haack_C * np.cos(th))
            / (L * np.sqrt(fx))
        )

    def T(x):
        return 2.0 * math.pi * y(x) * np.sqrt(1.0 + dydx(x) ** 2)

    sw_n, _ = integrate.quad(T, 0.0, L, limit=200)
    return sw_n


def _isa_atmosphere(h_alt_m: float) -> tuple[float, float, float, float]:
    """ISA temperature/density/viscosity/speed-of-sound at `h_alt_m`,
    verbatim port of the source's inline formulas (not a general ISA
    model -- no layering above the troposphere, matches the source
    exactly)."""
    T_air = 288.15 - 0.0065 * h_alt_m
    rho = 101325.0 * (T_air / 288.15) ** 5.2559 / (287.05 * T_air)
    mu = 1.458e-6 * T_air**1.5 / (T_air + 110.4)
    a_air = math.sqrt(1.4 * 287.05 * T_air)
    return T_air, rho, mu, a_air


def _derive(geo: Geometry) -> _Derived:
    sw_n = _nose_wetted_area(geo.L, geo.D1, geo.haack_C)
    Lslant = math.sqrt(geo.Ltr**2 + ((geo.D1 - geo.D2) / 2.0) ** 2)
    Lslant_bt = math.sqrt(geo.Lbt**2 + ((geo.D_fore - geo.D3) / 2.0) ** 2)
    SW_BT = (
        math.pi * geo.D1 * geo.L1
        + math.pi * geo.D2 * geo.L2
        + math.pi * ((geo.D1 + geo.D2) / 2.0) * Lslant
        + math.pi * ((geo.D_fore + geo.D3) / 2.0) * Lslant_bt
    )
    SW = SW_BT + sw_n
    SBT = (math.pi / 4.0) * geo.D1**2
    Lt = geo.L + geo.L1 + geo.Ltr + geo.L2 + geo.Lbt
    Dmax = max(geo.D1, geo.D2, geo.D3, geo.D_fore)  # architecture-45 SS2/SS3: unified FR formula
    FR = Lt / Dmax
    c = (geo.CR + geo.CT) / 2.0
    SF = geo.N * c * geo.SS
    S_LL = geo.nB * geo.dB * geo.hB
    Gam_L = math.atan(geo.sweep_len / geo.SS)
    fN = geo.L / geo.D1
    _T_air, rho, mu, a_air = _isa_atmosphere(geo.h_alt_m)
    return _Derived(
        SW=SW, SBT=SBT, Lt=Lt, FR=FR, c=c, SF=SF, S_LL=S_LL,
        Gam_L=Gam_L, fN=fN, rho=rho, mu=mu, a_air=a_air,
    )


# --- Mach-dependent component formulas (shared by transonic/supersonic) ---


def _skin_friction(M: np.ndarray, geo: Geometry, d: _Derived) -> np.ndarray:
    """CD_fric (Eq. 3.77-3.85). ONE implementation shared by both regimes:
    the source's separately-written supersonic skin-friction block (`Cf_
    turb_corr_sup`/`Cf_rough_corr_sup`, no blend) is algebraically
    identical to this transonic formula's `_ormach_blend` evaluated at any
    M >= 1.1 (`_ormach_blend`'s own `b = M>=1.1` branch returns `sup_fn(M)`
    exactly) -- and `_cd0_supersonic` only ever calls this with M >= 1.30,
    so the two source blocks collapse into one function without
    approximation."""
    v = M * d.a_air
    Re = d.rho * v * d.Lt / d.mu
    Cf_turb = 1.0 / (1.5 * np.log(Re) - 5.6) ** 2
    Cf_turb = np.where(Re < 1e4, 1.48e-2, Cf_turb)
    Re_crit = 51.0 * (geo.Rs / d.Lt) ** (-1.039)
    Cf_rough = 0.032 * (geo.Rs / d.Lt) ** 0.2
    fac_turb = _ormach_blend(M, lambda m: 1.0 - 0.1 * m**2, lambda m: 1.0 / (1.0 + 0.15 * m**2) ** 0.58)
    fac_rough = _ormach_blend(M, lambda m: 1.0 - 0.1 * m**2, lambda m: 1.0 / (1.0 + 0.18 * m**2))
    Cfc = Cf_turb * fac_turb
    rough = Re > Re_crit
    Cfc = np.where(rough, np.maximum(Cf_rough * fac_rough, Cf_turb * fac_turb), Cfc)
    return Cfc * ((1.0 + 1.0 / (2.0 * d.FR)) * d.SW + (1.0 + 2.0 * geo.tf / d.c) * (2.0 * d.SF)) / d.SBT


def _cd_stag(M: np.ndarray) -> np.ndarray:
    """CD_stag (Eq. B.1/B.2): `0.85 * _ormach_qr(M)`."""
    return 0.85 * _ormach_qr(M)


def _cd_base(M: np.ndarray) -> np.ndarray:
    """CD_base (Eq. 3.94): `0.12+0.13*M^2` for M<1, `0.25/M` for M>=1.
    Shared by both regimes -- `_cd0_supersonic` only calls this with
    M >= 1.30, which always routes through the M>=1 branch, matching the
    source's separately-written `CD_base_sup = 0.25./M_sup` exactly."""
    M = np.asarray(M, dtype=float)
    out = np.zeros_like(M)
    sb = M < 1.0
    out[sb] = 0.12 + 0.13 * M[sb] ** 2
    out[~sb] = 0.25 / M[~sb]
    return out


def _fin_le_rounded(M: np.ndarray) -> np.ndarray:
    """CD_LEr (Eq. 3.89-3.91): fin leading-edge drag for the 'rounded'/
    'airfoil' fin profiles. Shared by both regimes (always M>=1 for the
    supersonic branch's own calls, matching its separately-written
    `CD_LEr_sup` formula exactly)."""
    M = np.asarray(M, dtype=float)
    out = np.zeros_like(M)
    i1 = M < 0.9
    i2 = (M >= 0.9) & (M < 1.0)
    i3 = M >= 1.0
    out[i1] = (1.0 - M[i1] ** 2) ** (-0.417) - 1.0
    out[i2] = 1.0 - 1.785 * (M[i2] - 0.9)
    out[i3] = 1.214 - 0.502 / M[i3] ** 2 + 0.1095 / M[i3] ** 4
    return out


def _nose_wave_transonic(Mo: np.ndarray, fN: float) -> np.ndarray:
    """CD_nose, transonic (App. B, `useStoney=true` path): Stoney-table
    interpolation over 0.80-1.50, shape-corrected by `expo = log(fN+1)/
    log(4)` (Eq. B.9); below the table's own M=0.80 floor, the source
    overwrites with a power-law fit matched to `nose_f`'s own value+slope
    at M=0.80 (or 0.0 outright if that value is <= 0, which IS the case
    for this table: `_STONEY_CD[0] == 0.00` exactly, so `C_lo == 0` always,
    for any Geometry sharing this module's fixed Stoney table)."""
    expo = math.log(fN + 1.0) / math.log(4.0)

    def nose_f(Mq: np.ndarray) -> np.ndarray:
        Mq = np.atleast_1d(np.asarray(Mq, dtype=float))
        stoney = np.interp(Mq, _STONEY_M, _STONEY_CD)
        qr = _cd_stag(Mq)
        return qr * (stoney / qr) ** expo

    M_lo = float(_STONEY_M[0])
    C_lo = float(nose_f(M_lo)[0])
    CD_nose = nose_f(Mo)
    below = Mo < M_lo
    if C_lo <= 0.0:
        CD_nose[below] = 0.0
    else:
        s_lo = (float(nose_f(M_lo + 1e-3)[0]) - C_lo) / 1e-3
        b_lo = s_lo * M_lo / C_lo
        a_lo = C_lo / M_lo**b_lo
        CD_nose[below] = a_lo * Mo[below] ** b_lo
    return CD_nose


def _nose_wave_supersonic(M_sup: np.ndarray, fN: float) -> np.ndarray:
    """CD_nose, supersonic (`useStoneySupersonic=true` path): same `expo`
    shape-correction as the transonic branch, against the hand-extended
    1.30-3.00 Stoney table -- no extrapolation needed since M_sup's own
    range (1.30-3.00) exactly matches the table's own range."""
    expo = math.log(fN + 1.0) / math.log(4.0)
    CD3 = np.interp(M_sup, _STONEY_M_SUP, _STONEY_CD_SUP)
    qr = _cd_stag(M_sup)
    return qr * (CD3 / qr) ** expo


def _boattail_contribution(cd_base: np.ndarray, geo: Geometry, SBT: float) -> np.ndarray:
    """Boat-tail/flare pressure-drag contribution (Eq. 3.88), summed over
    the rocket's 2 rear-body diameter-change segments (transition+
    boat-tail for every geometry shipped so far -- this loop itself is
    geometry-generic, architecture-45 SS3/T45-1). `cd_base` is the
    regime's own CD_base array (transonic or supersonic, computed by the
    caller via `_cd_base`).

    3-way branch per architecture-45 T45-1 (the "fullest" version across
    the 3 source scripts):
      - `fore > aft` (converging): boat-tail base-drag law -- verbatim
        port of `cd_mach_03_increase_D.m`'s own branch, the ONLY case
        `PRO54_TRANSITION_GEOMETRY` exercises (tested).
      - `fore < aft` (diverging/flare): wave-drag law via `_ormach_cone`
        -- its exact formula lives only in `cd_mach_03_decrease_D.m`,
        deliberately NOT read this stage (PRO75's file mapping is
        UNCONFIRMED, SS2). Raises `NotImplementedError` rather than guess
        at an unverified formula; `PRO54_TRANSITION_GEOMETRY` never
        reaches this branch (both its rear-body segments converge). Port
        the real formula from `cd_mach_03_decrease_D.m` before adding
        `PRO75_GEOMETRY`.
      - `fore == aft`: no diameter change, zero contribution.
    """
    bt_fore = (geo.D1, geo.D_fore)
    bt_aft = (geo.D2, geo.D3)
    bt_len = (geo.Ltr, geo.Lbt)
    total = np.zeros_like(cd_base)
    for fore, aft, length in zip(bt_fore, bt_aft, bt_len):
        if fore > aft:
            gam = length / (fore - aft)
            if gam < 1.0:
                fg = 1.0
            elif gam < 3.0:
                fg = (3.0 - gam) / 2.0
            else:
                fg = 0.0
            total = total + fg * cd_base * (math.pi / 4.0) * (fore**2 - aft**2) / SBT
        elif fore < aft:
            raise NotImplementedError(
                "diverging-flare boattail branch (bt_fore < bt_aft) is not yet "
                "ported -- its exact wave-drag-via-_ormach_cone formula lives "
                "only in cd_mach_03_decrease_D.m, which architecture-45 keeps "
                "out of scope this stage (PRO75's own file mapping is "
                "UNCONFIRMED, SS2). PRO54_TRANSITION_GEOMETRY never reaches "
                "this branch -- port the real formula before adding "
                "PRO75_GEOMETRY."
            )
        # else: fore == aft -- no diameter change, zero contribution (implicit)
    return total


def _fin_pressure_drag(
    cd_stag: np.ndarray, cd_base: np.ndarray, cd_le_rounded: np.ndarray, geo: Geometry, d: _Derived
) -> np.ndarray:
    """CD_finP (Eq. 3.89-3.93), fin-profile `switch` ported as an
    if/elif/else (source: 'square'/'rounded'/'airfoil')."""
    if geo.fin_profile == "square":
        cd_le, cd_te = cd_stag, cd_base
    elif geo.fin_profile == "rounded":
        cd_le, cd_te = cd_le_rounded, 0.5 * cd_base
    elif geo.fin_profile == "airfoil":
        cd_le, cd_te = cd_le_rounded, np.zeros_like(cd_base)
    else:
        raise ValueError(
            f"fin_profile must be 'square', 'rounded', or 'airfoil' (got {geo.fin_profile!r})"
        )
    return (cd_le * math.cos(d.Gam_L) ** 2 + cd_te) * (geo.N * geo.tf * geo.SS) / d.SBT


def _cd0_transonic(Mo: np.ndarray, geo: Geometry, d: _Derived) -> np.ndarray:
    """OpenRocket/Niskanen method, M 0.10-1.30 (source `CD0_or`, "ADDED BY
    CLAUDE" section, steps 1-6). The ONLY method used in this range
    (architecture-45 SS4: the source's separate "paper" method, M
    0.1-0.75, is NOT ported -- it was a comparison baseline, never
    exported in the source)."""
    CD_fric = _skin_friction(Mo, geo, d)
    CD_stag = _cd_stag(Mo)
    CD_base = _cd_base(Mo)
    CD_nose = _nose_wave_transonic(Mo, d.fN)
    CD_bt = _boattail_contribution(CD_base, geo, d.SBT)
    CD_b = CD_base * ((math.pi / 4.0) * geo.D3**2 - _A_MOTOR_M2) / d.SBT
    CD_le_rounded = _fin_le_rounded(Mo)
    CD_finP = _fin_pressure_drag(CD_stag, CD_base, CD_le_rounded, geo, d)
    CD_LL = CD_stag * d.S_LL / d.SBT
    return CD_fric + CD_nose + CD_bt + CD_b + CD_finP + CD_LL


def _cd0_supersonic(M_sup: np.ndarray, geo: Geometry, d: _Derived) -> np.ndarray:
    """Hand-extended supersonic branch, M 1.30-3.00 (source `CD0_sup`,
    "1.3-3 SUPERSONIC" section). Continuous with `_cd0_transonic` at
    M=1.30 by construction: every component formula here is the SAME
    shared helper `_cd0_transonic` calls (see each helper's own
    docstring), so evaluating both at M=1.30 gives bit-identical results,
    not merely numerically close ones."""
    CD_fric = _skin_friction(M_sup, geo, d)
    CD_stag = _cd_stag(M_sup)
    CD_base = _cd_base(M_sup)
    CD_nose = _nose_wave_supersonic(M_sup, d.fN)
    CD_bt = _boattail_contribution(CD_base, geo, d.SBT)
    CD_b = CD_base * ((math.pi / 4.0) * geo.D3**2 - _A_MOTOR_M2) / d.SBT
    CD_le_rounded = _fin_le_rounded(M_sup)
    CD_finP = _fin_pressure_drag(CD_stag, CD_base, CD_le_rounded, geo, d)
    CD_LL = CD_stag * d.S_LL / d.SBT
    return CD_fric + CD_nose + CD_bt + CD_b + CD_finP + CD_LL


def compute_cd0(geo: Geometry) -> tuple[np.ndarray, np.ndarray]:
    """Returns (M_grid, cd0_grid), M_grid = 0.10..3.00 step 0.01 (291 pts),
    ascending, continuous. 0.10-1.30: OpenRocket/Niskanen method (thesis
    Eq. 3.77-3.97, App. B) -- the ONLY method used in this range (SS4).
    1.30-3.00: the supersonic extension, continuous with the 1.30
    boundary by construction (both branches are the same formula shape
    there, SS4). Geometry-generic: works for a constant tube, a
    converging transition+boat-tail, or a diverging flare rear body for
    the skin-friction/nose/base/fin/rail-button components; the boat-tail/
    flare component itself has a known gap for the diverging case, see
    `_boattail_contribution`."""
    d = _derive(geo)
    Mo = np.round(np.linspace(0.10, 1.30, 121), 2)
    M_sup = np.round(np.linspace(1.30, 3.00, 171), 2)
    cd0_or = _cd0_transonic(Mo, geo, d)
    cd0_sup = _cd0_supersonic(M_sup, geo, d)
    # drop _cd0_supersonic's own duplicate M=1.30 row, keep _cd0_transonic's (SS6/T45-1)
    M_grid = np.concatenate([Mo, M_sup[1:]])
    cd0_grid = np.concatenate([cd0_or, cd0_sup[1:]])
    return M_grid, cd0_grid


# PRO54_EQUAL_GEOMETRY (cd_mach_03_same.m) and PRO75_GEOMETRY (cd_mach_03_
# decrease_D.m, mapping UNCONFIRMED -- SS2) are deferred: same pattern, add
# later, do not add PRO75_GEOMETRY before the user confirms the file mapping.
PRO54_TRANSITION_GEOMETRY = Geometry(
    L=0.30,  # m -- nose length
    D1=0.08,  # m -- forward-tube diameter (SBT's reference diameter)
    haack_C=0.0,  # Von Karman nose (all 3 source scripts)
    L1=0.85,  # m -- forward tube at D1
    D2=0.059,  # m -- converging transition's aft diameter
    L2=0.336,  # m -- tube at D2
    Ltr=0.10,  # m -- transition length, D1 -> D2
    Lbt=0.0361,  # m -- boat-tail length, D_fore -> D3
    D_fore=0.0572,  # m -- boat-tail forward diameter
    D3=0.0483,  # m -- boat-tail aft diameter
    CR=0.10,  # m -- fin root chord
    CT=0.10,  # m -- fin tip chord
    SS=0.08,  # m -- fin semi-span
    tf=0.0025,  # m -- fin thickness
    N=3,  # fin count
    sweep_len=0.0577,  # m -- fin leading-edge sweep distance
    nB=2,  # rail button count
    dB=0.01,  # m -- rail button diameter
    hB=0.008,  # m -- rail button height above the airframe
    h_alt_m=2601.0 / 2.0,  # m -- mid-flight altitude
    v_design=2601.0 / 23.1,  # m/s -- apogee / time-to-apogee (not used by compute_cd0 itself)
)
