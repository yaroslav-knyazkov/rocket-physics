"""apps/sim/engine/atmosphere.py -- Local air state, three tiers behind one interface (architecture.md SS14;
main.tex SSModels > Atmosphere; roadmap.md Step 12).

Tier 1, "isa" (pure-formula International Standard Atmosphere), was
implemented at Step 12. Tier 2, "sounding" (one station's measured profile,
interpolated in altitude via sim/soundings.py), is added at Step 18. Tier 3,
"field" (N stations, spatially interpolated, SS17), is added at Step 20,
reusing Step 19's horizontal-combination machinery in sim/soundings.py.

Step 45 (Phase 2.8; models.tex SSGravity > Direction, eq. `h_true`;
architecture.md SS25): the three tiers' `h_msl` lookup now goes through
`sim.gravity.altitude_msl(y, p)` instead of the inlined flat
`-y[Z] + p.h0_m` -- curvature-aware once `p.gravity_direction` is non-
"parallel", bit-for-bit unchanged under the default. This module still must
NOT call `gravity.g()` (architecture.md SS14) -- the new import exists
solely for the surface-geometry seam, not the gravity magnitude.
"""

import math
from typing import NamedTuple

import numpy as np
from apps.sim.engine.gravity import altitude_msl


class AirState(NamedTuple):
    rho: float   # density [kg/m^3]
    p:   float   # static pressure [Pa]
    T:   float   # temperature [K]
    a:   float   # speed of sound [m/s]
    mu:  float   # dynamic viscosity [Pa*s]


# ISA physical constants (architecture.md SS14). Module-level, not Params
# fields -- these are constants of the ISA standard's own definition, not
# scenario knobs (architecture.md SS14: "not Params fields").
_R_D = 287.0528       # specific gas constant for dry air [J/(kg*K)]
_GAMMA = 1.4          # ratio of specific heats for air
_G_ISA = 9.80665      # ISA's own fixed gravity -- see _isa_air_state below
_MU_0 = 1.716e-5      # Sutherland reference viscosity [Pa*s]
_T_0 = 273.15         # Sutherland reference temperature [K]
_S_MU = 110.4         # Sutherland's constant for air [K]
_R_ISA = 6356766.0    # effective Earth radius used for geopotential altitude [m]

# B13 (roadmap.md; found during Phase 2.10 Step 48's verification): a hard
# clamp on the MSL altitude the ISA lapse-rate formula ever extrapolates
# over. Real ISA tables are only defined to ~86 km; `_LAYERS`' last entry is
# deliberately "used unbounded above its base" for any altitude a flight in
# this project's scope could reach (a few km), but `solve_ivp`'s adaptive-
# step error estimator can probe a trial state far outside any physical
# flight envelope (observed: ~700 km MSL, from a discontinuous force onset
# such as Step 48's parachute deployment) -- extrapolating the last layer's
# lapse rate that far gives a deeply negative temperature, and a negative
# base for a fractional power (`(T/T_b)**(-g/(L*R_d))`, Sutherland's
# `(T/T_0)**1.5`) raises `RuntimeWarning: invalid value encountered in
# scalar power` (a `nan`, not an exception -- `solve_ivp` discards the
# rejected trial step before the `nan` reaches an accepted sample, so this
# was never a correctness bug, only an avoidable warning). The clamp bounds
# are far outside any flight this project models (no scenario here reaches
# within two orders of magnitude of either bound), so this is bit-for-bit
# unchanged for every existing scenario and pinned test.
_H_MSL_MIN = -5000.0   # [m MSL] -- comfortably below any realistic ground elevation
_H_MSL_MAX = 86000.0   # [m MSL] -- the ISA standard's own upper validity limit

# Step 40: humid-air (virtual-temperature) density correction constants
# (main.tex SSModels > Atmosphere > Density; architecture.md SS23.3). Module-
# level, same rationale as _R_D above -- physical constants, not Params
# fields. _EPSILON is *computed* from _R_D/_R_V, never hard-coded as 0.622,
# so the two constants cannot drift apart.
_R_V = 461.5          # specific gas constant for water vapour [J/(kg*K)]
_EPSILON = _R_D / _R_V  # R_d/R_v ~= 0.6220

# 7-layer ISA table (architecture.md SS14): (base geopotential altitude
# H_b [m], lapse rate L [K/m], base temperature T_b [K], base pressure
# p_b [Pa]). Covers troposphere through mesosphere (H up to ~80 km); the
# last layer's formula is used unbounded above its base.
_LAYERS = (
    (0.0,     -0.0065, 288.15, 101325.0),
    (11000.0,  0.0,    216.65, 22632.06),
    (20000.0,  0.0010, 216.65, 5474.889),
    (32000.0,  0.0028, 228.65, 868.0187),
    (47000.0,  0.0,    270.65, 110.9063),
    (51000.0, -0.0028, 270.65, 66.93887),
    (71000.0, -0.0020, 214.65, 3.956420),
)


def _isa_air_state(t: float, y: np.ndarray, p) -> AirState:
    """Tier 1: pure-formula ISA (main.tex SSModels > Atmosphere;
    architecture.md SS14).

    Geopotential altitude H = R_isa*h_msl/(R_isa + h_msl), then piecewise-
    linear temperature lapse, hydrostatic pressure, ideal-gas density,
    a = sqrt(gamma*R_d*T), Sutherland viscosity.

    `g_isa = 9.80665` is baked in as part of the ISA standard's own
    definition -- the pressure column is defined for a fixed g, not
    whatever gravity model the scenario selected -- so this must NOT call
    gravity.g() (architecture.md SS14, roadmap.md Step 12 "Careful").
    """
    # h_msl via gravity.altitude_msl (Step 45): curvature-aware, bit-for-bit
    # -y[Z] + h0_m under the default "parallel" gravity_direction.
    h_msl = altitude_msl(y, p)
    # B13: clamp before the lapse-rate extrapolation -- see the constants'
    # own comment above. A no-op for every realistic flight.
    h_msl = min(max(h_msl, _H_MSL_MIN), _H_MSL_MAX)
    H = _R_ISA * h_msl / (_R_ISA + h_msl)

    H_b, L, T_b, p_b = _LAYERS[0]
    for base_H, lapse, layer_T_b, layer_p_b in _LAYERS:
        if H < base_H:
            break
        H_b, L, T_b, p_b = base_H, lapse, layer_T_b, layer_p_b

    T = T_b + L * (H - H_b)
    if L != 0.0:
        press = p_b * (T / T_b) ** (-_G_ISA / (L * _R_D))
    else:
        press = p_b * np.exp(-_G_ISA * (H - H_b) / (_R_D * T_b))

    # Step 105 (architecture-35 SS35.4.1/SS35.4.5, dispersion hooks): a launch-day
    # temperature offset, applied AFTER the pressure profile (the lapse-rate/
    # hydrostatic formula above is untouched -- this models a day that is uniformly
    # hotter/colder than the standard atmosphere at the same pressure altitude, not a
    # different lapse rate). `== 0.0` (the default) is skipped entirely, not added as
    # 0.0, so every pinned flight is bit-for-bit unchanged.
    if p.atmosphere.dT_K != 0.0:
        T = T + p.atmosphere.dT_K

    rho = press / (_R_D * T)
    a = np.sqrt(_GAMMA * _R_D * T)
    mu = _MU_0 * (T / _T_0) ** 1.5 * (_T_0 + _S_MU) / (T + _S_MU)

    return AirState(
        rho=float(rho), p=float(press), T=float(T), a=float(a), mu=float(mu)
    )


def isa_pressure_altitude(p_Pa: float) -> float:
    """Inverse of `_isa_air_state`'s own pressure column: given a static
    pressure [Pa], returns h_msl [m] -- the altitude a barometric
    altimeter calibrated to the STANDARD ISA profile would report for
    that pressure, regardless of which atmosphere tier actually produced
    it (sim/sensors.py's own baro channel, Step 108).

    Algebraic inverse of the SAME `_LAYERS` table `_isa_air_state` reads
    (not a numerical root-find) -- so `isa_pressure_altitude(p)` for a `p`
    that came from `_isa_air_state(h).p` recovers `h` to float64 rounding,
    WITHIN one layer (sim/sensors.py's "all-zero sensor returns the
    truth" acceptance test relies on exactly this). `_isa_air_state`
    itself is untouched by this function -- deliberately duplicates the
    tiny forward-pressure core below rather than refactoring the pinned
    function to share it (same "duplicate, don't refactor a pinned path"
    call task-104/107 already made for their own near-identical copies).

    Clamped into the forward formula's own domain
    (`_H_MSL_MIN`/`_H_MSL_MAX`, B13) before inverting: a pressure outside
    `[_isa_pressure_core(_H_MSL_MAX), _isa_pressure_core(_H_MSL_MIN)]` is
    clamped to the nearer boundary first, so a pathological input cannot
    produce a NaN/log-of-negative. In this ticket's own call pattern
    (sim/sensors.py always feeds it a TRUE, noiseless pressure from
    `air_state`, never a noisy one -- noise is added in altitude space,
    AFTER this call, see §108.3.3) the clamp never actually triggers for
    any realistic flight; it exists so this function is safe to call on
    its own, as a public API, same defensive standing as B13 itself.
    """
    p_Pa = min(max(p_Pa, _ISA_P_AT_H_MSL_MAX), _ISA_P_AT_H_MSL_MIN)
    H_b, L, T_b, p_b = _LAYERS[0]
    for base_H, lapse, layer_T_b, layer_p_b in _LAYERS:
        if p_Pa > layer_p_b:   # haven't climbed into this layer yet (mirrors "if H < base_H: break")
            break
        H_b, L, T_b, p_b = base_H, lapse, layer_T_b, layer_p_b
    if L != 0.0:
        T = T_b * (p_Pa / p_b) ** (-L * _R_D / _G_ISA)
        H = H_b + (T - T_b) / L
    else:
        H = H_b - (_R_D * T_b / _G_ISA) * math.log(p_Pa / p_b)
    return float(_R_ISA * H / (_R_ISA - H))


def _isa_pressure_core(h_msl: float) -> float:
    """Private, tiny DUPLICATE of `_isa_air_state`'s own h->pressure core
    (table walk + T + press, nothing else) -- used ONLY to compute the two
    module-level clamp-bound constants below, at import time. Exists so
    `isa_pressure_altitude`'s clamp bounds are derived from `_LAYERS`
    itself (self-consistent if the table ever changes) without importing
    anything from, or editing a single character of, `_isa_air_state`.
    """
    h_msl = min(max(h_msl, _H_MSL_MIN), _H_MSL_MAX)
    H = _R_ISA * h_msl / (_R_ISA + h_msl)
    H_b, L, T_b, p_b = _LAYERS[0]
    for base_H, lapse, layer_T_b, layer_p_b in _LAYERS:
        if H < base_H:
            break
        H_b, L, T_b, p_b = base_H, lapse, layer_T_b, layer_p_b
    T = T_b + L * (H - H_b)
    if L != 0.0:
        return p_b * (T / T_b) ** (-_G_ISA / (L * _R_D))
    return p_b * math.exp(-_G_ISA * (H - H_b) / (_R_D * T_b))


# Clamp bounds for isa_pressure_altitude's own input domain, derived once
# from _isa_pressure_core (above) rather than hardcoded literals.
_ISA_P_AT_H_MSL_MIN = _isa_pressure_core(_H_MSL_MIN)  # ~108008 Pa
_ISA_P_AT_H_MSL_MAX = _isa_pressure_core(_H_MSL_MAX)  # ~0.37 Pa


def sat_vapor_pressure(T_K: float) -> float:
    """Saturation vapour pressure at temperature `T_K` [K], Magnus/
    Alduchov-Eskridge formula (main.tex SSModels > Atmosphere > Density,
    eq:magnus; architecture.md SS23.3). Returns Pa.

    The `6.1094` coefficient is in hPa; the `100.0` factor converts to Pa
    -- "the one easy mistake here" per the spec, deliberately spelled out
    rather than folded into a re-derived constant. Accurate to <0.4% over
    -40..+50 degC; not extrapolated beyond that (no sounding needs it to
    be, per the spec's own note).
    """
    Tc = T_K - 273.15
    return 100.0 * 6.1094 * np.exp(17.625 * Tc / (Tc + 243.04))


def virtual_temperature(T: float, Td: float, p_Pa: float) -> float:
    """Virtual temperature: the temperature dry air would need to have the
    moist mixture's density at the same pressure (main.tex eq:virtual_
    temperature; architecture.md SS23.3). `T_v >= T` always.

    `Td` is clamped to `min(Td, T)` before computing the vapour pressure --
    a guard against noisy data implying supersaturation (Td > T is
    unphysical).
    """
    e = sat_vapor_pressure(min(Td, T))
    return T / (1.0 - (e / p_Pa) * (1.0 - _EPSILON))


def moist_density(p_Pa: float, T: float, Td: float) -> float:
    """Moist-air density via the virtual-temperature correction:
    rho = p/(R_d*T_v) (main.tex eq:virtual_temperature; architecture.md
    SS23.3). Always <= the dry-air density p/(R_d*T), since T_v >= T.
    """
    return p_Pa / (_R_D * virtual_temperature(T, Td, p_Pa))


def _sounding_air_state(t: float, y: np.ndarray, p) -> AirState:
    """Tier 2: one station's measured profile, interpolated in altitude
    (architecture.md SS14, SS17; roadmap.md Step 18).

    Single-station only -- loads `p.sounding_case` via
    `sim.soundings.load_case` and always uses its first station. A case
    folder containing more than one file is a tier-3 ("field") concern
    (multi-station horizontal combination, Step 20); here the rest are
    silently ignored, same as tier 3 reproducing tier 2 exactly with a
    single station (roadmap.md Step 20's check).

    Same `h_msl` convention as `_isa_air_state` above (`altitude_msl(y, p)`,
    Step 45), then `sim.soundings.interp_altitude` does the actual lookup
    (Step 17); its `p`/`T`/`rho`/`a`/`mu` fields are repackaged into
    `AirState` as-is -- `u`/`v` (wind) are dropped, that is wind.py's
    concern (Step 22), not atmosphere's.

    Step 40: if `p.humid_air` is set and the interpolated dewpoint is
    finite, `rho` is replaced with the virtual-temperature-corrected
    `moist_density(state.p, state.T, state.Td)`; otherwise (flag off, or a
    sounding with no `Td_K` data) `rho` stays the dry value from
    `interp_altitude`. `a`/`mu` are never corrected (architecture.md
    SS23.3, main.tex SSDensity's "what is deliberately left dry").
    """
    # Imported here, not at module level, to avoid a circular import:
    # sim.soundings imports sim.atmosphere (for the shared ISA constants
    # and layer table used in its above-top extrapolation).
    from apps.sim.engine import soundings

    h_msl = altitude_msl(y, p)
    snd = soundings.load_case(p.soundings.case)[0]
    state = soundings.interp_altitude(snd, h_msl)

    rho = state.rho
    if p.atmosphere.humid_air and np.isfinite(state.Td):
        rho = moist_density(state.p, state.T, state.Td)

    return AirState(
        rho=rho, p=state.p, T=state.T, a=state.a, mu=state.mu
    )


def _field_air_state(t: float, y: np.ndarray, p) -> AirState:
    """Tier 3: N stations, spatially interpolated (architecture.md SS14,
    SS17; roadmap.md Step 20).

    Same `h_msl` convention as `_isa_air_state`/`_sounding_air_state` above
    (`altitude_msl(y, p)`, Step 45). Delegates the actual work to
    `sim.soundings.interp_field` (Step 19), which combines every station
    in `p.sounding_case` horizontally at the rocket's current ground
    position -- `(x*sin(A), x*cos(A))` with `x = y[X]` and
    `A = p.azimuth_deg` -- via `p.horizontal_interp` (idw/rbf), then
    interpolates the combined profile in altitude exactly as tier 2. Its
    `p`/`T`/`rho`/`a`/`mu` fields are repackaged into `AirState` as-is,
    same as tier 2 -- `u`/`v` (wind) are dropped, that is wind.py's
    concern (Step 23), not atmosphere's. Same Step 40 humid-air correction
    as `_sounding_air_state` above (`p.humid_air` gate, dry fallback when
    the combined dewpoint is not finite).

    This is the first atmosphere model whose output depends on `y[X]`
    (the rocket's horizontal ground position), not just `y[Z]`: tiers 1
    and 2 above only ever read altitude.

    A case folder with a single station reduces `interp_field`'s (default,
    IDW) weighting to weight 1.0 for that one station (Step 19's own
    guarantee), so this tier then reproduces `_sounding_air_state` above
    exactly -- roadmap.md Step 20's stated check. (RBF instead needs >= 3
    non-collinear stations, per `sim.soundings._combine`'s own docstring,
    so it does not apply to the single-station case.)
    """
    # Imported here, not at module level, same circular-import reason as
    # `_sounding_air_state` above.
    from apps.sim.engine import soundings

    h_msl = altitude_msl(y, p)
    state = soundings.interp_field(p.soundings.case, y, h_msl, p)

    rho = state.rho
    if p.atmosphere.humid_air and np.isfinite(state.Td):
        rho = moist_density(state.p, state.T, state.Td)

    return AirState(
        rho=rho, p=state.p, T=state.T, a=state.a, mu=state.mu
    )


# Module-private dispatch dict (architecture.md SS12), same pattern as
# sim/gravity.py's `_GRAVITY_MODELS`: the public seam is `air_state`;
# callers never learn tiers exist. Unknown strings raise KeyError at the
# first call -- no input validation (architecture.md SS7).
_MODELS = {
    "isa": _isa_air_state,
    "sounding": _sounding_air_state,
    "field": _field_air_state,
}


def air_state(t: float, y: np.ndarray, p) -> AirState:
    """Local air state (main.tex SSModels > Atmosphere; architecture.md
    SS14), dispatching on `p.atmosphere_model`. All five fields come from
    the same (T, p) pair in one call, to avoid recomputing the layer
    lookup/interpolation per quantity and to keep them thermodynamically
    consistent (architecture.md SS14).
    """
    return _MODELS[p.atmosphere.model](t, y, p)