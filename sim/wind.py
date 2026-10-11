"""Wind velocity in the inertial frame, three tiers behind one interface
(architecture.md SS16; main.tex SSModels > Wind; roadmap.md Step 21).

Tier 1, "analytic" (constant direction + power-law shear + optional
deterministic turbulence), was implemented at Step 21. Tier 2, "sounding" (one
station's measured `(u, v)` profile, interpolated in altitude via
sim/soundings.py), was added at Step 22. Tier 3, "field" (N stations,
spatially interpolated, SS17), is added at this step (Step 23).

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

### Deterministic turbulence (Step 46, Dryden; architecture.md SS26)

`solve_ivp` evaluates its RHS at arbitrary, repeated, and sometimes-
rejected times, so the turbulence perturbation must be a **deterministic
function of its arguments alone** -- a fresh random draw per call would make
the RHS a non-function, destroying the adaptive solver's step-size control
and any reproducibility. It is therefore a frozen sum of sinusoids whose
frequencies/phases are drawn once from `np.random.default_rng(p.turbulence_seed)`
and cached per seed (`_turbulence_realization`, `@lru_cache`, same convention
as `thrust_curve._load_motor_curve`/`soundings.load_case`). This replaces
Step 21's placeholder (`_gust_realization`/`_gust`: half-normal random
weights, no altitude dependence, no spectrum -- see architecture.md SS26.1
for the full accounting) with the real MIL-F-8785C/MIL-HDBK-1797 Dryden
turbulence spectrum: altitude-dependent scale lengths and intensities, two
horizontal components (`u` along-wind, `v` cross-wind), amplitudes drawn
from the published PSD instead of an arbitrary draw.
`turbulence_model = "none"` (the default) skips the realization/RNG entirely
and returns exactly `(0.0, 0.0)`, so turbulence is off, not merely small.

Step 45 (Phase 2.8; models.tex SSGravity > Direction, eq. `h_true`;
architecture.md SS25): tier 1's `h` and tiers 2/3's `h_msl` now go through
`sim.gravity.altitude_agl`/`altitude_msl(y, p)` instead of the flat
`altitude_agl(y)` (tier 1) / inlined `-y[Z] + p.h0_m` (tiers 2/3) --
curvature-aware once `p.gravity_direction` is non-"parallel", bit-for-bit
unchanged under the default. Tiers 2/3 curve for the same reason
`sim/atmosphere.py`'s tiers 2/3 do: both read the *same* sounding file at
the *same* level, and re-referencing one to a curved altitude while the
other stayed flat would sample two different rows of one profile for one
state.
"""

import functools

import numpy as np

from sim.gravity import altitude_agl, altitude_msl


def _no_wind(t: float, y: np.ndarray, p) -> tuple[float, float]:
    """Tier 0, "none": zero wind (architecture.md SS16). The default --
    makes every prior Phase 1/2 result reproducible.
    """
    return (0.0, 0.0)


_M_PER_FT = 0.3048          # the international foot, exactly (not an approximation)
_W20_H_M = 20.0 * _M_PER_FT  # 6.096 m -- the MIL-spec reference height for W20
_H_LOW_FT = 1000.0           # top of the low-altitude regime        (MIL-F-8785C)
_H_HIGH_FT = 2000.0          # bottom of the isotropic free-atmosphere regime
_L_HIGH_FT = 1750.0          # isotropic scale length above _H_HIGH_FT (= 533.4 m)

_TURB_N = 64                 # superposed sinusoids per component (was _GUST_N = 8)
_TURB_PERIOD_MAX_S = 600.0   # longest period in the synthesis band  (omega ~ 0.01047 rad/s)
_TURB_PERIOD_MIN_S = 0.2     # shortest period in the synthesis band (omega ~ 31.42 rad/s)


def _mean_speed(h: float, p) -> float:
    """Tier 1's mean wind speed at altitude `h` AGL [m] -- the power-law
    shear profile, clamped below `p.wind_ref_h_m` rather than extrapolated
    to zero at the ground (architecture.md SS16).

    Extracted from `_analytic_wind` at Step 46 because the Dryden model
    needs the *same* profile evaluated at 20 ft (`_W20_H_M`) for `W20`
    (architecture.md SS26.3): one expression, one implementation, so a
    scenario cannot have two different mean winds. The expression is
    character-for-character Step 21's, so `_analytic_wind` is bitwise
    unchanged by the extraction.
    """
    h_ref = p.wind.ref_h_m
    return p.wind.ref_ms * (max(h, h_ref) / h_ref) ** p.wind.shear_exp


@functools.lru_cache(maxsize=None)
def _turbulence_realization(seed: int):
    """The frozen part of the realization: the frequency grid and the two
    independent phase sets (architecture.md SS26.6). Cached per seed, same
    convention as the Step-21 `_gust_realization` it replaces.

    Only the PHASES are random. The frequencies are a deterministic
    log-spaced grid, exactly as in Step 21 -- a seed needs to decorrelate
    realizations, and independent phases do that; randomising the grid as
    well would only make the pinned numbers depend on 64 more draws.

    `domegas` are the bin widths of the geometric grid, taken between
    geometric-mean bin edges: with ratio `r = (w[-1]/w[0])**(1/(N-1))`, bin
    `i` spans `w_i/sqrt(r) .. w_i*sqrt(r)`, so `dw_i = w_i*(sqrt(r) -
    1/sqrt(r))` and the bins tile `[w_0/sqrt(r), w_-1*sqrt(r)]` with no gap
    and no overlap. `sum(domegas)` therefore equals that span exactly (to
    roundoff), which makes `sum(Phi_i*dw_i)` a genuine Riemann sum of
    `integral Phi dw` -- the property SS26.6's amplitude formula rests on.

    DRAW ORDER IS PART OF THE SPEC: `phases_u` first, then `phases_v`, from
    one `default_rng(seed)`. Swapping them changes every pinned number in
    SS26.11 while breaking no invariant -- which is exactly why it is pinned.
    """
    periods_s = np.geomspace(_TURB_PERIOD_MAX_S, _TURB_PERIOD_MIN_S, _TURB_N)
    omegas = 2.0 * np.pi / periods_s
    r = (omegas[-1] / omegas[0]) ** (1.0 / (_TURB_N - 1))
    domegas = omegas * (np.sqrt(r) - 1.0 / np.sqrt(r))
    rng = np.random.default_rng(seed)
    phases_u = rng.uniform(0.0, 2.0 * np.pi, _TURB_N)
    phases_v = rng.uniform(0.0, 2.0 * np.pi, _TURB_N)
    return omegas, domegas, phases_u, phases_v


def _dryden_scales(h: float, p) -> tuple[float, float]:
    """`(L_u, sigma_u)` in **metres** and **m/s** at altitude `h` AGL
    [metres] -- the MIL-F-8785C/MIL-HDBK-1797 horizontal scale length and
    intensity (architecture.md SS26.2/SS26.5; research note SS3).

    `L_v == L_u` and `sigma_v == sigma_u` in this model, so one pair serves
    both horizontal components. The vertical (`w`) component is out of
    scope (backlog B7, architecture.md SS26.10).

    Units: the MIL formulas are in feet. `h` is converted to feet ONCE here;
    the `0.177 + 0.000823*h_ft` bracket is dimensionless but only with `h`
    in feet, `L` comes out in feet and is converted back, and `sigma` needs
    no conversion because the formula is linear in `W20` (SS26.2's table).
    """
    h_ft = max(h, 0.0) / _M_PER_FT   # clamp: a negative h would give a negative L
    sigma_w = 0.1 * _mean_speed(_W20_H_M, p)      # = 0.1*W20, already m/s

    def _low(hf: float) -> tuple[float, float]:
        bracket = 0.177 + 0.000823 * hf
        return hf / bracket ** 1.2, sigma_w / bracket ** 0.4   # (L [ft], sigma [m/s])

    if h_ft <= _H_LOW_FT:
        L_ft, sigma = _low(h_ft)
    elif h_ft >= _H_HIGH_FT:
        L_ft, sigma = _L_HIGH_FT, p.wind.turbulence_sigma_high_ms
    else:
        # MIL-F-8785C leaves 1000-2000 ft undefined; implementors fill it
        # with a linear interpolation of the PARAMETERS between the two
        # regimes' boundary values (research note SS3.5). At exactly
        # 1000 ft the bracket is 0.177 + 0.823 == 1.0 exactly, so the low
        # anchor is L = 1000 ft and sigma = 0.1*W20 with no arithmetic.
        L_lo, sigma_lo = _low(_H_LOW_FT)
        f = (h_ft - _H_LOW_FT) / (_H_HIGH_FT - _H_LOW_FT)
        L_ft = (1.0 - f) * L_lo + f * _L_HIGH_FT
        sigma = (1.0 - f) * sigma_lo + f * p.wind.turbulence_sigma_high_ms

    return L_ft * _M_PER_FT, sigma


def _no_turbulence(t: float, h: float, p) -> tuple[float, float]:
    """Tier-1 turbulence model "none" (the default): no perturbation at
    all. Returns exact zeros without building a realization or touching the
    RNG -- turbulence off, not merely small, the same off-switch standard
    Step 21's `gust_sigma == 0.0` set (architecture.md SS26.3).
    """
    return (0.0, 0.0)


def _dryden_turbulence(t: float, h: float, p) -> tuple[float, float]:
    """`(u, v)` [m/s]: the along-wind and cross-wind Dryden turbulence
    components at time `t` and altitude `h` AGL [m] (architecture.md SS26).

    A frozen sum of sinusoids, `sigma * sum_i w_i*sin(omega_i*t + phi_i)`,
    with the SHAPE of the weights taken from the Dryden PSD instead of the
    Step-21 half-normal draw:

        k_i = Phi(omega_i) * domega_i        (energy in bin i)
        w_i = sqrt(2*k_i / sum_j k_j)        => sum_i w_i**2 == 2 exactly
                                             => Var[u] == sigma**2 exactly

    The `sqrt(2*Phi*domega)` of textbook random-phase spectral synthesis,
    renormalised by `sum k` so the realised variance is EXACTLY `sigma**2`
    rather than the 81-98 % of it that the finite band captures
    (architecture.md SS26.6 pins the capture fraction and argues the
    choice). Note that the constant prefactors `2L/(pi*V)` and `L/(pi*V)`
    cancel in `k_i/sum k`; they are written out anyway so the code visibly
    matches the cited formula, and SS26.12 asserts the cancellation.

    `sigma**2` IS LEFT OUT of `k_u`/`k_v` below -- it is a common factor and
    cancels in `k_i/sum k` just as the prefactors do, and leaving it out
    keeps `sigma` appearing exactly once, in the final line. The consequence
    for testing, stated because it is the easy mistake: `k_u.sum()` IS the
    capture fraction `integral_band Phi_u dw / sigma_u**2` directly -- do NOT
    divide it by `sigma**2` again when comparing against SS26.11's pinned
    capture table.

    The weights depend on altitude (through `L`, and on `V`), so they are
    recomputed per call and CANNOT live in the `lru_cache` -- only the grid
    and the phases are frozen. That is not a determinism problem: `h` is a
    function of the state, exactly like the mean profile's own `W(h)`
    (architecture.md SS26.8).
    """
    omegas, domegas, phases_u, phases_v = _turbulence_realization(p.wind.turbulence_seed)
    L, sigma = _dryden_scales(h, p)
    V = p.wind.turbulence_ref_speed_ms

    x2 = (L * omegas / V) ** 2
    k_u = (2.0 * L / (np.pi * V)) / (1.0 + x2) * domegas
    k_v = (L / (np.pi * V)) * (1.0 + 3.0 * x2) / (1.0 + x2) ** 2 * domegas
    sum_u, sum_v = k_u.sum(), k_v.sum()
    if sum_u <= 0.0 or sum_v <= 0.0:
        # Only reachable at h <= 0, where the MIL formula gives L == 0 and
        # the whole spectrum collapses to zero energy (sigma stays finite,
        # so this is a genuine 0/0 and must be guarded, not relied on).
        return (0.0, 0.0)

    w_u = np.sqrt(2.0 * k_u / sum_u)
    w_v = np.sqrt(2.0 * k_v / sum_v)
    u = sigma * float(np.sum(w_u * np.sin(omegas * t + phases_u)))
    v = sigma * float(np.sum(w_v * np.sin(omegas * t + phases_v)))
    return (u, v)


# Module-private dispatch dict (architecture.md SS12), nested inside tier 1
# the same way `_GRAVITY_DIRECTIONS` sits beside `_GRAVITY_MODELS` (SS23.1):
# orthogonal to `_MODELS` below, not a product of names. Unknown strings
# raise KeyError at the first call -- no input validation (SS7).
_TURBULENCE_MODELS = {
    "none": _no_turbulence,
    "dryden": _dryden_turbulence,
}


def _analytic_wind(t: float, y: np.ndarray, p) -> tuple[float, float]:
    """Tier 1: power-law shear + constant direction + optional Dryden
    turbulence (architecture.md SS16, SS26):

        W(h) = W_ref*(max(h, h_ref)/h_ref)^shear_exp
        wdir = wind_dir_deg    (constant with altitude for tier 1)

    `h` is altitude AGL (`altitude_agl`, not MSL): a wind-shear profile is
    referenced to the local ground/roughness length, not to sea level, so
    using `h_msl` would shift the whole profile by the launch site's own
    elevation `h0_m` for no physical reason -- the power law describes the
    boundary layer above the terrain the rocket actually launches from.

    Clamped *below* `h_ref` rather than extrapolated toward zero at the
    ground (architecture.md SS16): for `h < h_ref`, `W(h) == W_ref`.

    The turbulence perturbation is now a VECTOR, `(u, v)` along/across the
    mean wind direction (architecture.md SS26.7), composed with `ê_u =
    (-cos d, -sin d)` and `ê_v = (sin d, -cos d)` (`ê_u` rotated +90 deg in
    the `(x, y)` plane):

        (w_x, w_y) = (W + u)*ê_u + v*ê_v

    which reduces to Step 21's `-(W + delta)*cos/sin d` exactly when `v ==
    0`. The non-negativity clamp Step 21 applied to `W + delta` is GONE:
    perturbing a vector along `ê_u` makes a negative `W + u` the correct
    physical statement that the gust has reversed the local flow, not a
    silent 180-degree flip to be protected against (architecture.md
    SS26.7 item 3).
    """
    h = altitude_agl(y, p)
    W = _mean_speed(h, p)
    u, v = _TURBULENCE_MODELS[p.wind.turbulence_model](t, h, p)

    delta = np.radians(p.wind.dir_deg - p.site.azimuth_deg)
    cos_d, sin_d = np.cos(delta), np.sin(delta)
    w_x = -(W + u) * cos_d + v * sin_d
    w_y = -(W + u) * sin_d - v * cos_d
    return (w_x, w_y)


def _sounding_wind(t: float, y: np.ndarray, p) -> tuple[float, float]:
    """Tier 2: one station's measured `(u, v)` profile, interpolated in
    altitude (architecture.md SS16, SS17; roadmap.md Step 22).

    Single-station only -- loads `p.sounding_case` via
    `sim.soundings.load_case` and always uses its first station, the same
    convention `sim.atmosphere._sounding_air_state`/`_field_air_state`
    established for Steps 18/20: a case folder with more than one file is
    a tier-3 ("field") concern, arriving unchanged at Step 23.

    Same `h_msl` convention as the atmosphere tiers, `altitude_msl(y, p)`
    (Step 45) -- *not* `altitude_agl` like tier 1's power-law shear profile
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

    h_msl = altitude_msl(y, p)
    snd = soundings.load_case(p.soundings.case)[0]
    state = soundings.interp_altitude(snd, h_msl)

    A = np.radians(p.site.azimuth_deg)
    w_along = state.u * np.sin(A) + state.v * np.cos(A)
    w_cross = state.u * np.cos(A) - state.v * np.sin(A)
    return (float(w_along), float(w_cross))


def _field_wind(t: float, y: np.ndarray, p) -> tuple[float, float]:
    """Tier 3: N stations, spatially interpolated (architecture.md SS16,
    SS17; roadmap.md Step 23).

    Same `h_msl` convention as `_sounding_wind` above (`altitude_msl(y, p)`,
    not `altitude_agl`). Delegates the horizontal combination
    *and* altitude interpolation to `sim.soundings.interp_field` (Step
    19) -- the same call `sim.atmosphere._field_air_state` makes for
    Step 20 -- then reuses `_sounding_wind`'s own ENU -> flight-plane
    projection unchanged on the returned `u`/`v`. A single-station case
    reduces `interp_field`'s weighting to 1.0 for that station (Step 19's
    own guarantee), so this tier then reproduces `_sounding_wind` above
    exactly -- roadmap.md Step 23's first stated check.
    """
    # Imported here, not at module level, same circular-import reason as
    # `_sounding_wind` above.
    from sim import soundings

    h_msl = altitude_msl(y, p)
    state = soundings.interp_field(p.soundings.case, y, h_msl, p)

    A = np.radians(p.site.azimuth_deg)
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
    "field": _field_wind,
}


def wind_horizontal_enu(t: float, y: np.ndarray, p) -> tuple[float, float]:
    """Horizontal wind decomposed into the flight-plane axes,
    `(w_along, w_cross)`: `w_along` is the downrange (`+x`) component,
    `w_cross` is the out-of-plane component that this 2D simulator cannot
    use yet but Phase 3 can, unchanged (architecture.md SS16). Dispatches
    on `p.wind_model`.
    """
    return _MODELS[p.wind.model](t, y, p)


def wind_inertial(t: float, y: np.ndarray, p, hold=None) -> np.ndarray:
    """Wind velocity in F_0 as `(w_x, w_z)`, z DOWN-positive (architecture.md
    SS16). `w_z` is always `0.0` -- vertical wind (updrafts/downdrafts) is
    out of scope for every tier here. The cross-plane component from
    `wind_horizontal_enu` is computed and discarded, per the 2D-projection
    limitation documented above.

    Step 59 (architecture-28-rewrite.md SS28.8): `hold` is accepted
    (default `None`) but unused -- B11's future landing site (a turbulence
    realization evaluated once per tick at the true instantaneous
    airspeed, filter state carried in `hold`'s `prev`). No turbulence
    change is made here; this is plumbing only, per this step's own scope
    limit.
    """
    w_x, _w_cross = wind_horizontal_enu(t, y, p)
    return np.array([w_x, 0.0])
