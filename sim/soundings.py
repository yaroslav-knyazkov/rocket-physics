"""Sounding data: file format, loader, altitude interpolation
(architecture.md SS17; roadmap.md Step 17).

This is the shared data layer for atmosphere tiers 2/3 (SS14) *and* wind
tiers 2/3 (SS16) -- one canonical file format, one loader, one
interpolator, consumed by both `sim/atmosphere.py` (Step 18+) and
`sim/wind.py` (Step 22+). Nothing in this module is wired into forces.py
or dynamics.py yet -- this step is pure infrastructure (roadmap.md Step
17: "no physics changes in this step").

File format (architecture.md SS17):

    data/soundings/<case>/<station>_<YYYYMMDDHHMM>.csv

    # station: LKPR
    # lat_deg: 50.1008
    # lon_deg: 14.2600
    # elevation_m: 380
    # time_utc: 2026-05-01T12:00:00Z
    # source: ...
    h_msl_m,p_Pa,T_K,wdir_deg,wspd_ms
    380,96700,287.3,210,4.1
    ...

`#`-prefixed `key: value` metadata lines above a CSV header/body, parsed
with `line.split(':', 1)` -- no YAML, no sidecar JSON (architecture.md
SS17, an approval-gated decision, SS22 item 2). `h_msl_m` must be
strictly increasing. Empty fields load as NaN, so an atmosphere-only or
wind-only sounding is the same format with blank columns. Loaded with
`numpy.genfromtxt` -- no pandas (SS17/SS21, approval-gated, SS22 item 3).

Wind is converted from (`wdir_deg`, `wspd_ms`) to ENU (`u`, `v`) at load
time and never stored/interpolated as direction+speed past that point:
direction wraps at 360 deg, which is exactly why the format converts
immediately (architecture.md SS16 makes the same point about wind tiers
2/3). Standard meteorological convention: `wdir` is the direction the
wind blows *from*, degrees clockwise from North.
    u_east  = -wspd * sin(wdir_rad)
    v_north = -wspd * cos(wdir_rad)

Interpolation in altitude (architecture.md SS17's table, tier 2 -- single
station; tier 3's horizontal combination across stations is Step 19):
  T       linear in h
  p       linear in ln(p) vs h, then exponentiated back
  u, v    linear in h
  rho     derived, rho = p/(R_d*T) -- never interpolated independently
  a, mu   derived from interpolated T, same formulas as atmosphere.py

Outside the data range:
  below h[0]:  continue with the *sounding's own* local lapse rate from
               its first two points (not an ISA layer rate -- this may be
               real, non-standard data). A single-row sounding has no
               well-defined lapse rate; falls back to isothermal /
               constant-ln(p) (documented at the call site below).
  above h[-1]: continue with an ISA-*shaped* profile -- same layer
               structure and lapse rates as the standard ISA table in
               sim/atmosphere.py -- but re-anchored at the sounding's own
               top point (h_top, T_top, p_top) instead of the standard
               sea-level anchor, so T and p stay continuous at the seam
               (architecture.md SS17: "no density step at the seam").
Wind (u, v) is held constant at the edge value outside the data range on
both sides (architecture.md SS17: "wind is held constant at the edge
value"; np.interp's own default clamping behaviour already matches this).

This module imports several ISA physical constants and the layer table
directly from `sim.atmosphere` (`_R_D`, `_GAMMA`, `_G_ISA`, `_MU_0`,
`_T_0`, `_S_MU`, `_R_ISA`, `_LAYERS`) rather than redefining them: they
are module-private there, but this is a single-package project (no
external consumers of `sim.atmosphere`'s internals), and duplicating the
numbers would risk numeric drift between the ISA path and the sounding
path -- exactly the failure mode the architecture doc warns against
(SS17: "Reuse the physical constants already defined in
sim/atmosphere.py").
"""

import functools
import glob
import os
from typing import NamedTuple

import numpy as np

from sim import atmosphere


class Sounding(NamedTuple):
    station: str
    lat: float
    lon: float
    elev: float
    time_utc: str
    h: np.ndarray  # m MSL, ascending
    p: np.ndarray  # Pa (may be NaN)
    T: np.ndarray  # K (may be NaN)
    u: np.ndarray  # m/s ENU east component, derived at load time
    v: np.ndarray  # m/s ENU north component, derived at load time


class SoundingState(NamedTuple):
    """Everything a consumer (atmosphere.py's "sounding" tier, wind.py's
    "sounding" tier) needs from one altitude query of one Sounding."""

    p:   float  # Pa
    T:   float  # K
    rho: float  # kg/m^3
    a:   float  # m/s, speed of sound
    mu:  float  # Pa*s, dynamic viscosity
    u:   float  # m/s, ENU east wind component
    v:   float  # m/s, ENU north wind component


# ----------------------------------------------------------------------
# Loading
# ----------------------------------------------------------------------


def _load_sounding_file(path: str) -> Sounding:
    """Parse one `<station>_<YYYYMMDDHHMM>.csv` sounding file.

    Metadata: `#`-prefixed `key: value` lines above the header, parsed
    with `line.split(':', 1)` (architecture.md SS17 -- deliberately no
    YAML/JSON parser). Table: loaded with `np.genfromtxt`, comment lines
    stripped first so genfromtxt's column-count inference (from the
    header row) isn't confused by them.
    """
    meta = {}
    data_lines = []
    with open(path) as f:
        for line in f:
            stripped = line.strip()
            if not stripped:
                continue
            if stripped.startswith("#"):
                key, _, value = stripped[1:].partition(":")
                meta[key.strip()] = value.strip()
            else:
                data_lines.append(line)

    data = np.atleast_1d(
        np.genfromtxt(data_lines, delimiter=",", names=True, dtype=float)
    )

    h = data["h_msl_m"].astype(float)
    p = data["p_Pa"].astype(float)
    T = data["T_K"].astype(float)
    wdir = data["wdir_deg"].astype(float)
    wspd = data["wspd_ms"].astype(float)

    if h.size > 1 and not np.all(np.diff(h) > 0):
        raise ValueError(f"{path}: h_msl_m must be strictly increasing")

    wdir_rad = np.radians(wdir)
    u = -wspd * np.sin(wdir_rad)
    v = -wspd * np.cos(wdir_rad)

    return Sounding(
        station=meta.get("station", ""),
        lat=float(meta.get("lat_deg", "nan")),
        lon=float(meta.get("lon_deg", "nan")),
        elev=float(meta.get("elevation_m", "nan")),
        time_utc=meta.get("time_utc", ""),
        h=h, p=p, T=T, u=u, v=v,
    )


@functools.lru_cache(maxsize=None)
def load_case(case: str) -> "tuple[Sounding, ...]":
    """Load every `*.csv` in `data/soundings/<case>/` into a tuple of
    `Sounding`. Cached so a case is read from disk once per process
    (architecture.md SS17: "Params holds names and paths; modules hold
    the loaded data, cached" -- same rule as `thrust_curve._load_motor_curve`).

    Path resolution follows `sim/thrust_curve.py`'s `_load_motor_curve`
    convention: absolute path from the repo root (this file's parent
    directory is `<repo>/sim/`, so one level up is the repo root).
    """
    repo_root = os.path.dirname(os.path.dirname(__file__))
    case_dir = os.path.join(repo_root, "data", "soundings", case)
    paths = sorted(glob.glob(os.path.join(case_dir, "*.csv")))

    if not paths:
        raise FileNotFoundError(
            f"No sounding files found for case '{case}' in {case_dir}"
        )

    return tuple(_load_sounding_file(path) for path in paths)


# ----------------------------------------------------------------------
# ISA-anchored extrapolation above the sounding's top data point
# ----------------------------------------------------------------------
#
# Reuses sim.atmosphere's own layer-crossing algorithm (_isa_air_state),
# but re-anchored at the sounding's top point instead of the standard
# sea-level anchor -- see the module docstring for why T/mu/etc constants
# are imported directly rather than duplicated.

_R_D = atmosphere._R_D
_GAMMA = atmosphere._GAMMA
_G_ISA = atmosphere._G_ISA
_MU_0 = atmosphere._MU_0
_T_0 = atmosphere._T_0
_S_MU = atmosphere._S_MU
_R_ISA = atmosphere._R_ISA
_LAYERS = atmosphere._LAYERS


def _geopotential(h_msl: float) -> float:
    """Geometric MSL altitude -> geopotential altitude, same formula as
    `sim.atmosphere._isa_air_state` (H = R_isa*h/(R_isa+h))."""
    return _R_ISA * h_msl / (_R_ISA + h_msl)


def _isa_layer_lapse(H: float) -> float:
    """Lapse rate of the standard ISA layer containing geopotential
    altitude H -- same table lookup `_isa_air_state` performs, reused
    here only for the lapse-rate value (the layer *structure* is assumed
    to still apply above the sounding's data, per architecture.md SS17;
    the layer's absolute T_b/p_b are not used -- they come from the
    re-anchored walk in `_isa_anchored_state` below instead)."""
    L = _LAYERS[0][1]
    for base_H, lapse, _, _ in _LAYERS:
        if H < base_H:
            break
        L = lapse
    return L


def _hydrostatic_step(p_b: float, T_b: float, T: float, L: float, dH: float) -> float:
    """One ISA hydrostatic step within a single layer -- identical formula
    to `sim.atmosphere._isa_air_state`'s pressure formula, factored out so
    it can be applied both when walking forward through re-anchored layer
    boundaries and at the final query point."""
    if L != 0.0:
        return p_b * (T / T_b) ** (-_G_ISA / (L * _R_D))
    return p_b * np.exp(-_G_ISA * dH / (_R_D * T_b))


def _isa_anchored_state(H: float, H_top: float, T_top: float, p_top: float):
    """T, p at geopotential altitude `H >= H_top`, continuing the same
    layer-crossing structure as the standard ISA table but anchored at
    (H_top, T_top, p_top) instead of the standard sea-level anchor
    (architecture.md SS17: "an ISA-shaped profile anchored at the top
    data point ... so T and p are continuous at the seam").

    Walks the standard ISA layer boundaries strictly above H_top,
    re-deriving each boundary's own (T, p) by propagating forward from
    the anchor with the *current* segment's lapse rate (not the standard
    table's own T_b/p_b, which belong to a different absolute anchor) --
    then adopts the next layer's lapse rate from there. This is exactly
    what `sim.atmosphere._isa_air_state`'s loop does starting from sea
    level; here it starts mid-layer, at the sounding's own top point.
    """
    H_b, T_b, p_b = H_top, T_top, p_top
    L = _isa_layer_lapse(H_top)

    for base_H, lapse, _, _ in _LAYERS:
        if base_H <= H_top:
            continue
        if H < base_H:
            break
        T_at_b = T_b + L * (base_H - H_b)
        p_at_b = _hydrostatic_step(p_b, T_b, T_at_b, L, base_H - H_b)
        H_b, T_b, p_b, L = base_H, T_at_b, p_at_b, lapse

    T = T_b + L * (H - H_b)
    p = _hydrostatic_step(p_b, T_b, T, L, H - H_b)
    return T, p


# ----------------------------------------------------------------------
# Public interpolation seam (tier 2 -- single station; tier 3's
# horizontal combination across stations is Step 19)
# ----------------------------------------------------------------------


def interp_altitude(snd: Sounding, h: float) -> SoundingState:
    """Interpolate one `Sounding` to a single MSL altitude `h` [m],
    returning p, T, derived rho/a/mu, and interpolated u, v
    (architecture.md SS17's interpolation table).

    In-range: T and (u, v) linear in h; p linear in ln(p) vs h, then
    exponentiated back. Out of range: see the module docstring
    ("Outside the data range").
    """
    h_arr = snd.h
    n = h_arr.size

    if h < h_arr[0]:
        if n >= 2:
            dh = h_arr[1] - h_arr[0]
            L = (snd.T[1] - snd.T[0]) / dh
            k = (np.log(snd.p[1]) - np.log(snd.p[0])) / dh
        else:
            # Degenerate single-row sounding: no second point to derive a
            # lapse rate from. Sane, non-crashing fallback: isothermal /
            # constant ln(p) below the (only) data point.
            L = 0.0
            k = 0.0
        T = snd.T[0] + L * (h - h_arr[0])
        p = snd.p[0] * np.exp(k * (h - h_arr[0]))
        u = float(snd.u[0])
        v = float(snd.v[0])
    elif h > h_arr[-1]:
        H_top = _geopotential(h_arr[-1])
        H = _geopotential(h)
        T, p = _isa_anchored_state(H, H_top, snd.T[-1], snd.p[-1])
        u = float(snd.u[-1])
        v = float(snd.v[-1])
    else:
        T = float(np.interp(h, h_arr, snd.T))
        p = float(np.exp(np.interp(h, h_arr, np.log(snd.p))))
        u = float(np.interp(h, h_arr, snd.u))
        v = float(np.interp(h, h_arr, snd.v))

    T = float(T)
    p = float(p)
    rho = p / (_R_D * T)
    a = np.sqrt(_GAMMA * _R_D * T)
    mu = _MU_0 * (T / _T_0) ** 1.5 * (_T_0 + _S_MU) / (T + _S_MU)

    return SoundingState(
        p=p, T=T, rho=float(rho), a=float(a), mu=float(mu), u=u, v=v
    )
