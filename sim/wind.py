"""Wind velocity in the inertial frame, three tiers behind one interface
(architecture.md SS16; main.tex SSModels > Wind; roadmap.md Step 21).

Tier 1, "analytic" (constant direction + power-law shear + optional
deterministic gusts), was implemented at Step 21. Tier 2, "sounding" (one
station's measured `(u, v)` profile, interpolated in altitude via
sim/soundings.py), is added at this step (Step 22). Tier 3, "field" (N
stations, spatially interpolated, SS17), arrives at Step 23.

### The 2D projection limitation (architecture.md SS16)

Real wind is a horizontal vector; this simulator is planar (x downrange,
z down, no out-of-plane DOF until Phase 3). The launch azimuth
`p.azimuth_deg` (degrees clockwise from North, the direction of `+x`)
fixes the flight plane. With meteorological convention (`wdir` = the
direction the wind blows *from*, degrees clockwise from North):

    along-plane (downrange) component :  w_x = -W*cos(wdir - azimuth)
    cross-plane component             :  w_y = -W*sin(wdir - azimuth)   <- discarded in 2D
    vertical                          :  w_z = 0   (z is down; an updraft would be negative)

`wind_horizontal_enu` below returns both components; `wind_inertial`
discards `w_y`. This is a deliberate, documented modelling limitation --
representing crosswind weathercocking needs the out-of-plane degree of
freedom that only Phase 3 has (architecture.md SS16) -- not an oversight.

### Deterministic gusts

`solve_ivp` evaluates its RHS at arbitrary, repeated, and sometimes-
rejected times, so the gust perturbation must be a **deterministic
function of `t` alone** -- a fresh random draw per call would make the RHS
a non-function of `t`, destroying the adaptive solver's step-size control
and any reproducibility. It is therefore a frozen sum of sinusoids whose
frequencies/phases are drawn once from `np.random.default_rng(p.gust_seed)`
and cached per seed (`_gust_realization`, `@lru_cache`, same convention as
`thrust_curve._load_motor_curve`/`soundings.load_case`). `gust_sigma = 0.0`
(the default) skips the realization/RNG entirely and returns exactly
`0.0`, so gusts are off, not merely small.
"""

import functools

import numpy as np

from sim.flow import altitude_agl
from sim.state import Z


def _no_wind(t: float, y: np.ndarray, p) -> tuple[float, float]:
    """Tier 0, "none": zero wind (architecture.md SS16). The default --
    makes every prior Phase 1/2 result reproducible.
    """
    return (0.0, 0.0)


_GUST_N = 8  # number of superposed sinusoids in the frozen gust realization


@functools.lru_cache(maxsize=None)
def _gust_realization(seed: int):
    """Build the frozen `(omega_i, phi_i, weight_i)` triple once per
    `gust_seed`, cached so repeated calls at different `t` reuse the same
    realization instead of redrawing the RNG (architecture.md SS16:
    "realisation built lazily and cached per seed").

    Frequencies are log-spaced over a plausible atmospheric-gust band
    (periods from ~3 s to ~10 minutes) so no two components are near-
    degenerate; phases are uniform in `[0, 2*pi)`; weights are drawn from
    a half-normal shape (`abs` of a standard normal) and then normalised
    so `sum(weight_i**2) == 1` -- this makes `p.gust_sigma` approximately
    the resulting perturbation's standard deviation, a physically legible
    knob, regardless of `_GUST_N`.
    """
    rng = np.random.default_rng(seed)
    periods_s = np.geomspace(3.0, 600.0, _GUST_N)
    omegas = 2.0 * np.pi / periods_s
    phases = rng.uniform(0.0, 2.0 * np.pi, _GUST_N)
    weights = np.abs(rng.normal(0.0, 1.0, _GUST_N))
    weights = weights / np.sqrt(np.sum(weights ** 2))
    return omegas, phases, weights


def _gust(t: float, p) -> float:
    """Deterministic gust perturbation [m/s] added to `W(h)` below.

    `gust_sigma == 0.0` (the default) returns exactly `0.0` without
    touching the RNG or the realization at all -- gusts off entirely, not
    just small. Otherwise this is a repeatable, pure function of `t` and
    `p.gust_seed`/`p.gust_sigma` only: calling it twice with the same
    arguments is bit-for-bit identical (no per-call randomness).
    """
    if p.gust_sigma == 0.0:
        return 0.0
    omegas, phases, weights = _gust_realization(p.gust_seed)
    return float(p.gust_sigma * np.sum(weights * np.sin(omegas * t + phases)))


def _analytic_wind(t: float, y: np.ndarray, p) -> tuple[float, float]:
    """Tier 1: power-law shear + constant direction + optional deterministic
    gusts (architecture.md SS16):

        W(h) = W_ref*(max(h, h_ref)/h_ref)^shear_exp
        wdir = wind_dir_deg    (constant with altitude for tier 1)

    `h` is altitude AGL (`altitude_agl`, not MSL): a wind-shear profile is
    referenced to the local ground/roughness length, not to sea level, so
    using `h_msl` would shift the whole profile by the launch site's own
    elevation `h0_m` for no physical reason -- the power law describes the
    boundary layer above the terrain the rocket actually launches from.

    Clamped *below* `h_ref` rather than extrapolated toward zero at the
    ground (architecture.md SS16): for `h < h_ref`, `W(h) == W_ref`.

    The gust perturbation is added directly to `W(h)` and then clamped to
    be non-negative: `W(h)` is a wind *speed*, and a large negative gust
    on top of a small `W_ref` could otherwise drive the sum below zero,
    which has no physical meaning for a speed (it would silently flip the
    wind direction by 180 degrees instead of just weakening it). The clamp
    only ever engages when `gust_sigma` is comparable to or larger than
    `W_ref` itself; for `gust_sigma == 0.0` it is a no-op.
    """
    h = altitude_agl(y)
    h_ref = p.wind_ref_h_m
    W = p.wind_ref_ms * (max(h, h_ref) / h_ref) ** p.wind_shear_exp
    W = max(W + _gust(t, p), 0.0)

    delta = np.radians(p.wind_dir_deg - p.azimuth_deg)
    w_x = -W * np.cos(delta)
    w_y = -W * np.sin(delta)
    return (w_x, w_y)


def _sounding_wind(t: float, y: np.ndarray, p) -> tuple[float, float]:
    """Tier 2: one station's measured `(u, v)` profile, interpolated in
    altitude (architecture.md SS16, SS17; roadmap.md Step 22).

    Single-station only -- loads `p.sounding_case` via
    `sim.soundings.load_case` and always uses its first station, the same
    convention `sim.atmosphere._sounding_air_state`/`_field_air_state`
    established for Steps 18/20: a case folder with more than one file is
    a tier-3 ("field") concern, arriving unchanged at Step 23.

    Same `h_msl` convention as the atmosphere tiers, h_msl = -y[Z] +
    p.h0_m -- *not* `altitude_agl` like tier 1's power-law shear profile
    above. A measured sounding is a set of altitude-MSL rows tied to a
    real station; re-referencing it to the launch site's AGL altitude
    would shift every row by `p.h0_m` for no physical reason, exactly the
    argument `_analytic_wind`'s docstring makes in the opposite direction
    for a shear profile anchored to the local ground.

    ### Projection: ENU (u, v) -> flight-plane axes

    `soundings.interp_altitude` returns wind as ENU components `(u, v)` =
    (East, North) -- a different representation from tier 1's
    (`wind_dir_deg`, `wind_ref_ms`) speed/direction pair, so the
    flight-plane projection has to be re-derived from first principles
    rather than reused as-is.

    The flight plane's downrange axis `+x_hat` points along the launch
    azimuth `A = p.azimuth_deg` (degrees clockwise from North), so in ENU
    coordinates `+x_hat = (sin A, cos A)` (A=0 -> North = (0, 1); A=90 ->
    East = (1, 0)). The out-of-plane axis `+y_hat`, `x_hat` rotated -90
    deg (clockwise) to match tier 1's own `w_y` sign below, is
    `(cos A, -sin A)`. Projecting the ENU wind vector `(u, v)` onto each
    with a plain dot product:

        w_along = u*sin(A) + v*cos(A)      (dot with x_hat)
        w_cross = u*cos(A) - v*sin(A)      (dot with y_hat)

    Consistency check against tier 1's `w_x = -W*cos(wdir - azimuth)` /
    `w_y = -W*sin(wdir - azimuth)` (architecture.md SS16): substituting
    tier 1's own ENU conversion (soundings.py's docstring), u =
    -W*sin(wdir), v = -W*cos(wdir), into `w_along` above:

        w_along = -W*sin(wdir)*sin(A) - W*cos(wdir)*cos(A)
                = -W*(sin(wdir)*sin(A) + cos(wdir)*cos(A))
                = -W*cos(wdir - A)                              [cos(a-b) identity]

    which is exactly tier 1's `w_x`. Same substitution into `w_cross`:

        w_cross = -W*sin(wdir)*cos(A) + W*cos(wdir)*sin(A)
                = -W*(sin(wdir)*cos(A) - cos(wdir)*sin(A))
                = -W*sin(wdir - A)                              [sin(a-b) identity]

    which is exactly tier 1's `w_y`. So the two tiers agree on the same
    physical projection, expressed in each tier's own native wind
    representation.
    """
    # Imported here, not at module level, same circular-import reason as
    # sim.atmosphere's `_sounding_air_state`/`_field_air_state`: this
    # module would otherwise need sim.soundings at import time, and
    # sim.soundings imports sim.atmosphere for its shared ISA constants.
    from sim import soundings

    h_msl = -y[Z] + getattr(p, "h0_m", 0.0)
    snd = soundings.load_case(p.sounding_case)[0]
    state = soundings.interp_altitude(snd, h_msl)

    A = np.radians(p.azimuth_deg)
    w_along = state.u * np.sin(A) + state.v * np.cos(A)
    w_cross = state.u * np.cos(A) - state.v * np.sin(A)
    return (float(w_along), float(w_cross))


# Module-private dispatch dict (architecture.md SS12), same pattern as
# sim/gravity.py's `_GRAVITY_MODELS` / sim/atmosphere.py's `_MODELS`: the
# public seam is `wind_inertial`/`wind_horizontal_enu`; callers never learn
# tiers exist. Unknown strings raise KeyError at the first call -- no input
# validation (architecture.md SS7). Entries return `(w_along, w_cross)` --
# the flight-plane-decomposed horizontal wind -- so both public functions
# below can be built from the same table.
_MODELS = {
    "none": _no_wind,
    "analytic": _analytic_wind,
    "sounding": _sounding_wind,
}


def wind_horizontal_enu(t: float, y: np.ndarray, p) -> tuple[float, float]:
    """Horizontal wind decomposed into the flight-plane axes,
    `(w_along, w_cross)`: `w_along` is the downrange (`+x`) component,
    `w_cross` is the out-of-plane component that this 2D simulator cannot
    use yet but Phase 3 can, unchanged (architecture.md SS16). Dispatches
    on `p.wind_model`.
    """
    return _MODELS[p.wind_model](t, y, p)


def wind_inertial(t: float, y: np.ndarray, p) -> np.ndarray:
    """Wind velocity in F_0 as `(w_x, w_z)`, z DOWN-positive (architecture.md
    SS16). `w_z` is always `0.0` -- vertical wind (updrafts/downdrafts) is
    out of scope for every tier here. The cross-plane component from
    `wind_horizontal_enu` is computed and discarded, per the 2D-projection
    limitation documented above.
    """
    w_x, _w_cross = wind_horizontal_enu(t, y, p)
    return np.array([w_x, 0.0])
