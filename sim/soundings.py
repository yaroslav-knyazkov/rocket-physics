"""Sounding data: file format, loader, altitude interpolation, and
horizontal (tier-3) combination across stations (architecture.md SS17;
roadmap.md Steps 17 and 19).

This is the shared data layer for atmosphere tiers 2/3 (SS14) *and* wind
tiers 2/3 (SS16) -- one canonical file format, one loader, one altitude
interpolator, one horizontal-combination path, consumed by both
`sim/atmosphere.py` (Step 18/20+) and `sim/wind.py` (Step 22/23+). Nothing
in this module is wired into forces.py or dynamics.py yet -- both Step 17
and Step 19 are pure infrastructure (roadmap.md: "no physics changes in
this step").

Step 19 adds the tier-3 horizontal machinery towards the bottom of this
file (`ResampledCase`, `_resample_case`, `project_latlon`, `interp_field`,
`interp_field_at`) -- see that section's own docstring for the design.

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
from sim.state import X


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


# ----------------------------------------------------------------------
# Horizontal (tier-3) combination across stations (architecture.md SS17,
# "Interpolation in horizontal position"; roadmap.md Step 19).
#
# Pure infrastructure -- nothing below is wired into atmosphere.py/wind.py
# yet (that is Step 20/23). The public seam for those steps is
# `interp_field` (query from the rocket's own state vector `y`) and
# `interp_field_at` (query from an explicit tangent-plane point, used
# directly by the tests below and by any future along-track query).
#
# Design: resample every station in a case onto a common altitude grid at
# "load" time (cached per (case, grid_top_m, grid_step_m), since the grid
# itself is Params-settable -- SS17/SS19), giving arrays of shape
# (n_stations, n_levels). At query time, project stations and the query
# point into a launch-site-centred tangent plane, weight the stations
# (IDW or RBF), and combine with one dot product per quantity (weights
# depend only on horizontal position, not altitude -- SS17: "the whole
# horizontal step is one small dot product"). The combined grid profile is
# then wrapped back into a `Sounding`-shaped object and fed straight
# through `interp_altitude` above, reusing its altitude-interpolation
# *and* its outside-the-grid extrapolation behaviour for free (exactly
# the module's own instruction: "interpolate the combined profile in
# altitude exactly as tier 2").
# ----------------------------------------------------------------------


class ResampledCase(NamedTuple):
    """Every station of a case, resampled onto one common altitude grid.

    `T`, `ln_p`, `u`, `v` have shape `(n_stations, n_levels)`; `h` is the
    shared grid, `(n_levels,)`. `lat`/`lon` are the stations' own
    coordinates, `(n_stations,)` -- kept as raw degrees rather than
    pre-projected (E, N) because the tangent-plane origin
    (`p.lat0_deg`/`lon0_deg`/`R_e`) is a `Params` field, not a property of
    the case, and this object is cached on `(case, grid_top_m,
    grid_step_m)` only (architecture.md SS17/SS19) -- it must stay valid
    across calls with the same grid but a different launch site.
    """

    h: np.ndarray     # (n_levels,), m MSL, ascending
    lat: np.ndarray   # (n_stations,), deg
    lon: np.ndarray   # (n_stations,), deg
    T: np.ndarray     # (n_stations, n_levels), K
    ln_p: np.ndarray  # (n_stations, n_levels), ln(Pa)
    u: np.ndarray     # (n_stations, n_levels), m/s
    v: np.ndarray     # (n_stations, n_levels), m/s


@functools.lru_cache(maxsize=None)
def _resample_case(
    case: str, grid_top_m: float, grid_step_m: float
) -> ResampledCase:
    """Resample every station of `case` onto a common 0..grid_top_m
    altitude grid at grid_step_m spacing, reusing `interp_altitude` level
    by level -- no duplication of the T-linear/p-log-linear/u,v-linear
    interpolation rules or the below-bottom/above-top extrapolation rules,
    all of which stay in one place (`interp_altitude` above).

    Cached on `(case, grid_top_m, grid_step_m)`, not just `case`: the grid
    is `Params`-settable (architecture.md SS17/SS19), so two different
    `Params` using the same case but a different grid must not share a
    cache entry. `grid_top_m`/`grid_step_m` are plain floats, hashable.
    """
    stations = load_case(case)

    n_levels = int(round(grid_top_m / grid_step_m)) + 1
    h = np.linspace(0.0, grid_top_m, n_levels)

    n_stations = len(stations)
    T = np.empty((n_stations, n_levels))
    ln_p = np.empty((n_stations, n_levels))
    u = np.empty((n_stations, n_levels))
    v = np.empty((n_stations, n_levels))

    for i, snd in enumerate(stations):
        for j, level in enumerate(h):
            state = interp_altitude(snd, float(level))
            T[i, j] = state.T
            ln_p[i, j] = np.log(state.p)
            u[i, j] = state.u
            v[i, j] = state.v

    lat = np.array([s.lat for s in stations], dtype=float)
    lon = np.array([s.lon for s in stations], dtype=float)

    return ResampledCase(h=h, lat=lat, lon=lon, T=T, ln_p=ln_p, u=u, v=v)


def project_latlon(lat_deg: float, lon_deg: float, p) -> "tuple[float, float]":
    """Equirectangular tangent-plane projection of `(lat_deg, lon_deg)`,
    centred on the launch site `(p.lat0_deg, p.lon0_deg)` (architecture.md
    SS17): `E = R_e*cos(phi0)*d(lambda)`, `N = R_e*d(phi)`, with
    `d(lambda)`/`d(phi)` in radians. <0.1% error inside 100 km (SS17) --
    the accuracy of sounding data itself is orders of magnitude worse.

    Public mainly so callers (and the tests below) can place an arbitrary
    query point -- e.g. a station's own coordinates -- in the same frame
    the resampled grid and the rocket's ground position (`interp_field`)
    live in. Production callers (Step 20/23) use `interp_field` with the
    rocket's state vector instead; they never need this directly, since
    the rocket's own ground position is `(x*sin(A), x*cos(A))`, not a
    lat/lon (see `interp_field` below).
    """
    phi0 = np.radians(p.lat0_deg)
    dlat = np.radians(lat_deg - p.lat0_deg)
    dlon = np.radians(lon_deg - p.lon0_deg)
    E = p.R_e * np.cos(phi0) * dlon
    N = p.R_e * dlat
    return float(E), float(N)


def _combine(resampled: ResampledCase, E: float, N: float, p):
    """Weight every station in `resampled` at tangent-plane point `(E, N)`
    and combine their level arrays into one profile, dispatching on
    `p.horizontal_interp` (architecture.md SS17's table). Returns
    `(T, ln_p, u, v)`, each `(n_levels,)`.
    """
    phi0 = np.radians(p.lat0_deg)
    station_E = p.R_e * np.cos(phi0) * np.radians(resampled.lon - p.lon0_deg)
    station_N = p.R_e * np.radians(resampled.lat - p.lat0_deg)

    if p.horizontal_interp == "idw":
        # w_i ~ 1/(d_i^2 + eps^2), normalised -- architecture.md SS17.
        # eps > 0 always, so this is well-defined even when the query
        # point exactly coincides with a station (d_i = 0), and reduces
        # to weight 1.0 for the (only) station in a single-station case
        # regardless of eps.
        d2 = (station_E - E) ** 2 + (station_N - N) ** 2
        w = 1.0 / (d2 + p.idw_epsilon_m ** 2)
        w = w / w.sum()
        T = w @ resampled.T
        ln_p = w @ resampled.ln_p
        u = w @ resampled.u
        v = w @ resampled.v
    elif p.horizontal_interp == "rbf":
        # scipy.interpolate.RBFInterpolator, verified present in the
        # installed scipy 1.18.1 (architecture.md SS17). d can carry
        # several output columns at once (evaluated as one linear system
        # since the kernel only depends on the station coordinates, not
        # the values), so T/ln_p/u/v are stacked into one (n_stations,
        # 4*n_levels) array and combined with a single call.
        #
        # griddata/LinearNDInterpolator are explicitly rejected by
        # architecture.md SS17 (NaN outside the convex hull of the
        # stations -- a rocket's ground track routinely leaves a
        # two/three-station polygon). RBFInterpolator with the default
        # 'thin_plate_spline' kernel and degree needs >= 3 non-collinear
        # stations (scipy's own requirement for the degree-1 polynomial
        # term); with fewer, scipy raises ValueError -- not silently
        # papered over here, since the "idw" default already handles 1/2
        # stations and rbf is offered as an alternative, not a
        # replacement (architecture.md SS17's own table: rbf "needs >=
        # (degree+1) points").
        from scipy.interpolate import RBFInterpolator

        y = np.column_stack([station_E, station_N])
        n = resampled.h.size
        stacked = np.concatenate(
            [resampled.T, resampled.ln_p, resampled.u, resampled.v], axis=1
        )
        rbf = RBFInterpolator(y, stacked, kernel="thin_plate_spline", smoothing=0.0)
        combined = rbf(np.array([[E, N]]))[0]
        T, ln_p, u, v = combined[:n], combined[n:2 * n], combined[2 * n:3 * n], combined[3 * n:]
    else:
        raise KeyError(f"Unknown horizontal_interp: {p.horizontal_interp!r}")

    return T, ln_p, u, v


def interp_field_at(case: str, E: float, N: float, h: float, p) -> SoundingState:
    """Horizontal combination of every station in `case` at tangent-plane
    point `(E, N)` [m, launch-site-centred ENU -- see `project_latlon`],
    then altitude interpolation at `h` [m MSL] exactly as tier 2
    (`interp_altitude`).

    This is the low-level seam: callers that already have a tangent-plane
    point (this module's own tests, or a future along-track query) use
    this directly. `interp_field` below is the convenience wrapper for
    the common case of a rocket state vector, and is what Step 20's
    atmosphere tier 3 / Step 23's wind tier 3 actually call.
    """
    resampled = _resample_case(case, p.grid_top_m, p.grid_step_m)
    T, ln_p, u, v = _combine(resampled, E, N, p)

    combined = Sounding(
        station="<field>", lat=float("nan"), lon=float("nan"), elev=float("nan"),
        time_utc="", h=resampled.h, p=np.exp(ln_p), T=T, u=u, v=v,
    )
    return interp_altitude(combined, h)


def interp_field(case: str, y: np.ndarray, h: float, p) -> SoundingState:
    """Horizontal combination of every station in `case` at the rocket's
    own ground position, then altitude interpolation at `h` [m MSL]
    (architecture.md SS17). The ground position is `(x*sin(A), x*cos(A))`
    in the same launch-site-centred ENU tangent plane as the stations,
    with `x = y[X]` (downrange coordinate) and `A = p.azimuth_deg`.

    This is the direct seam for Step 20's atmosphere tier 3
    (`atmosphere.py`'s `"field"` variant) and Step 23's wind tier 3
    (`wind.py`'s `"field"` variant) -- both call this unchanged, per
    roadmap.md Step 23's note that tier 3 wind "reuses the Step 19
    weighting machinery unchanged".
    """
    A = np.radians(p.azimuth_deg)
    x = float(y[X])
    E = x * np.sin(A)
    N = x * np.cos(A)
    return interp_field_at(case, E, N, h, p)
