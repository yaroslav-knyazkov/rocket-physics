"""Thrust curve model: time-thrust table lookup via np.interp, plus the
altitude pressure correction on top (roadmap.md Step 16).

The public function `thrust(t, s, p)` returns the instantaneous thrust
magnitude [N] for the given time. It is called from `forces.thrust_body`
and has the same signature as all force models.

The curve is loaded from `data/motors/<motor_curve>.csv` where
<p.motor_curve> is the filename (without path) given in `Params`.
The CSV must have a header line and two columns: time [s], thrust [N].
Units are strict SI. The loader is @lru_cache; the array is stored
module-globally after first use.

For t < first time point: returns the first thrust point (allows
pre-ignition spike if desired). For t > last time point: returns 0.
This matches the roadmap requirement "zero after the last point" and
removes the hard-coded T_BURN hack from forces.py.

Step 16: `thrust()` additionally applies `T(t,h) = T_ref(t) +
A_e*(p_ref - p_amb)` (main.tex SSModels > Thrust; architecture.md SS19),
where `T_ref(t)` is the raw curve lookup above, `p_amb` comes from
`sim.atmosphere.air_state(t, s, p).p`, and `A_e`/`p_ref` are `Params`
fields. `A_e` defaults to 0.0, which makes the correction term exactly
0.0 and reproduces Step 14's `T_ref(t)` bit-for-bit regardless of
`p_ref`.

Step 98 (architecture-35 SS35.4.2, D-112): `thrust_stand` = `k_J * T_curve(t / k_t)`
(impulse/time scatter, both default 1.0 = bit-identical), and `mass_flow`
computes `dm/dt` from the stand curve (independent of altitude and `A_e`).

Step 76 (architecture-32-motor-separation.md SS32.4): file formats and
header metadata now live in `sim/motor_file.py`, which `_load_motor_curve`
delegates to. `motor_curve` may still name a plain `.csv` (one record, no
metadata, unchanged byte for byte) or now also an `.eng`/`.rasp` RASP-format
file (optionally `"<filename>#<designation>"` to pick one record out of a
multi-record library); either way `_load_motor_curve` returns the same
`(times, thrusts)` shape it always has. A RASP record whose first data row
has `t > 0` gets an explicit `(0.0, 0.0)` point prepended by the RASP
reader -- see `sim/motor_file.py`'s docstring -- so `.eng`/`.rasp` curves
never fire the motor before their own data says it ignites.
"""

import functools

import numpy as np

from sim import atmosphere, motor_file

# ----------------------------------------------------------------------
# Internal caching helpers
# ----------------------------------------------------------------------


@functools.lru_cache(maxsize=None)
def _load_motor_curve(curve_name: str) -> tuple[np.ndarray, np.ndarray]:
    """Step 76: delegates to `sim.motor_file.load`, which now owns every
    format (`.csv`, `.eng`, `.rasp`) and the optional `#designation`
    fragment. For a `.csv` this is the same sort/de-duplicate/float path
    as before, moved into `sim/motor_file.py` verbatim -- the arrays
    handed to `np.interp` are bit-identical to pre-Step-76 behaviour.
    Kept `@functools.lru_cache`'d here too (on top of `motor_file.load`'s
    own cache) so a cache-clear of one module can't silently un-cache the
    other and so this function's cost model doesn't depend on which module
    happens to still be imported.
    """
    rec = motor_file.load(curve_name)
    return rec.times, rec.thrusts


# ----------------------------------------------------------------------
# Public API (matches the force-model seam in forces.py)
# ----------------------------------------------------------------------


def _curve(t: float, p) -> float:
    """`T_curve(t / k_t)` -- the raw motor-file lookup, time-scaled by
    `Thrust.k_t`. With `k_t == 1.0` the time argument is passed through
    untouched (bit-identical to the pre-Step-98 lookup). Returns 0.0 with
    no curve."""
    if not p.thrust.motor_curve:
        return 0.0
    times, thrust_curves = _load_motor_curve(p.thrust.motor_curve)
    if p.thrust.k_t != 1.0:
        t = t / p.thrust.k_t
    # np.interp: first point for t < t[0], 0.0 for t > t[-1].
    return float(np.interp(t, times, thrust_curves, left=thrust_curves[0], right=0.0))


def thrust_stand(t: float, p) -> float:
    """`T_0(t) = (k_J / k_t) * T_curve(t / k_t)` -- the stand thrust (Step 98,
    architecture-35 SS35.4.2): total impulse is exactly `k_J * J` and burnout
    is at `k_t * t_b` (independent knobs). The multiplication is skipped when
    both are 1.0, so the defaults reproduce the raw lookup bit-for-bit."""
    T = _curve(t, p)
    if p.thrust.k_J != 1.0 or p.thrust.k_t != 1.0:
        T = (p.thrust.k_J / p.thrust.k_t) * T
    return T


def thrust_stand_array(t: np.ndarray, p) -> np.ndarray:
    """Vectorised `thrust_stand` over an array of times (Step 114); element-wise
    the same arithmetic as the scalar function. Zeros with no curve."""
    t = np.asarray(t, dtype=float)
    if not p.thrust.motor_curve:
        return np.zeros_like(t)
    times, thrust_curves = _load_motor_curve(p.thrust.motor_curve)
    tt = t / p.thrust.k_t if p.thrust.k_t != 1.0 else t
    T = np.interp(tt, times, thrust_curves, left=thrust_curves[0], right=0.0)
    if p.thrust.k_J != 1.0 or p.thrust.k_t != 1.0:
        T = (p.thrust.k_J / p.thrust.k_t) * T
    return T


def mass_flow(t: float, p) -> float:
    """`dm/dt = -T_curve(t / k_t) / (k_t * I_sp * g0)` [kg/s] (Step 98, D-112).

    Computed from the stand curve, so independent of altitude and `A_e`
    (the pressure-thrust term changes the thrust, not the propellant flow);
    the amplitude is NOT scaled by `k_J` (same propellant for any impulse
    scatter) while the time scale `k_t` stretches the burn, so the burned
    mass stays `J / (I_sp g0)`. Equivalently `-T_0 / (k_J * I_sp * g0)`:
    the effective I_sp of the scattered motor scales with `k_J`. Does not apply the dry-mass floor (that
    lives in `dynamics.derivatives`)."""
    T = _curve(t, p)
    if p.thrust.k_t != 1.0:
        T = T / p.thrust.k_t
    return -T / (p.weight.I_sp * p.g0)


def thrust(_t: float, _s, p) -> float:
    """Instantaneous thrust magnitude [N] for the current time, including
    the Step 16 altitude pressure correction.

    Returns zero when the time is after the last defined point in the
    curve, exactly as required by the roadmap.

    Step 16: on top of the raw curve lookup `T_ref(t)`, adds
    `A_e*(p_ref - p_amb)` (main.tex SSModels > Thrust; architecture.md
    SS19) -- the standard nozzle-exit pressure-thrust term: a curve
    measured at sea level (`p_ref`) produces more net thrust once the
    ambient pressure `p_amb` the nozzle exit is pushing against drops
    with altitude.

    The correction is only applied while `T_ref(t) > 0`, i.e. while the
    motor is actually flowing. `T_ref(t) == 0` means either pre-ignition
    or post-burnout (or no curve at all); in either case there is no
    chamber pressure at the nozzle exit, so `A_e*(p_ref - p_amb)` has no
    physical thrust to modify and applying it anyway would manufacture a
    nonzero "thrust" from ambient pressure alone -- silently breaking the
    clean zero-after-burnout cutoff that Step 14's own check and the
    `_burnout_event` in integrate.py both depend on.

    `A_e == 0.0` (the default) short-circuits before touching the
    atmosphere model at all, so this reduces to exactly `T_ref(t)` --
    bit-for-bit identical to Step 14 -- regardless of `p_ref` or the
    selected `atmosphere_model`.
    """
    if not p.thrust.motor_curve:
        # No curve defined -> zero thrust (safe default)
        return 0.0

    # Step 98: `T_ref` is the stand thrust `T_0 = k_J * T_curve(t / k_t)`
    # (identical to the raw lookup at the default k_J = k_t = 1.0).
    T_ref = thrust_stand(_t, p)

    if p.thrust.A_e == 0.0 or T_ref <= 0.0:
        return T_ref

    p_amb = atmosphere.air_state(_t, _s, p).p
    return T_ref + p.thrust.A_e * (p.thrust.p_ref - p_amb)