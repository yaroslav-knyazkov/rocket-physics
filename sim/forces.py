"""Forces and moments, each returned in its *natural* frame (architecture.md
SS4, "the model-swap seam"). Every function has the final signature
`f(t, s, p) -> ...` from day one, so Phase 2 only ever rewrites a function
*body* here -- call sites in dynamics.py never change.

Phase 1: every force is a constant magnitude from `Params`, taken straight
from main.tex SSForces / SSMoments:

    W   = m*g*z_hat_g                       (gravity frame == inertial here)
    T   = T*x_hat_r                         (body frame)
    A_f = -A_x*x_hat_r - A_z*z_hat_r        (body frame)
    A_m = -A_m*y_hat_r                      (body frame, scalar about y)

Step 9 originally generalised `A_f` to `-A_x*u_hat - A_z*n_hat` (rotating it
into the relative-wind frame), driven by the actual relative wind / angle
of attack from sim/flow.py. `A_x`, `A_z` were still plain `Params`
constants at that point -- dynamic-pressure-based coefficients arrived in
Steps 12-13/25.

Step 35 (Phase 2.5) reverted that rotation: `C_A`/`C_N` (Step 25) are
body-axis (axial/normal) coefficients, matching the CFD/wind-tunnel data
convention they are extracted from, so their own `alpha`-dependence already
accounts for the relative wind -- rotating the resulting force through
`u_hat`/`n_hat` a second time was double-applying it. `A_f` is therefore
`-A_x*x_hat_r - A_z*z_hat_r` again, unconditionally (main.tex SSModels >
Aerodynamics). `flow.u_hat`/`flow.n_hat` are still computed in flow.py and
still used -- just to get `V`, `alpha`, `q` into the coefficient lookup, not
to redirect the force.

Step 10: `weight_inertial` dispatches its magnitude through
sim/gravity.py's `g(t, y, p)` (main.tex SSModels > Gravity;
architecture.md SS12/SS13) instead of the fixed `p.g`, so the gravity
model is selected by `p.gravity_model` and defaults to "constant", which
reproduces Phase 1 bit-for-bit.

Step 14: `thrust_body` now uses the thrust curve from sim/thrust_curve.py,
replacing the hard-coded T_BURN constant-thrust model.

Step 25: the "coefficients" regime's `C_A`/`C_N`/`C_m` are no longer
inline `Params`-constant formulas -- they are delegated to sim/aero.py,
which is table-driven (`p.aero_table`) with the exact same constant
formulas as the fallback (architecture.md SS19). Bit-for-bit unchanged
when `p.aero_table == ""` (the default).

Step 55 (Phase 2.11 rewrite pass, architecture-28-rewrite.md SS28.5):
`aero_force_body`/`aero_moment_y` no longer have their own `if/elif/else`
aero-model branch at all -- both call the single `aero.coefficients(t, s,
p, flow)` seam and read the `AeroCoeffs` bundle it returns (`C_x`, `C_z`,
`C_m`, `C_mq`), which itself dispatches on `p.aero.model` ("constant" |
"linearized" | "table"). `"linearized"` is bit-for-bit the old
"coefficients" regime; `"constant"`'s `C_x`/`C_z`/`C_m` are now true
dimensionless coefficients (the fix this step exists for -- see
sim/aero.py's module docstring), so `"constant"` is now `q`-scaled like
every other model, where it used to be a raw, atmosphere-independent
force. The pitch-damping term (Step 44, below) now applies identically
under all three models (architecture-28-rewrite.md SS28.5.3) instead of
being specific to the old "coefficients" regime.

Step 36: `weight_inertial`'s `m` is the current, possibly time-varying
mass (`s[M]`) once the variable-mass model is on (`p.m_d` set, main.tex
SSModels > Mass and moment of inertia) -- the fixed `p.m` otherwise,
bit-for-bit unchanged. `thrust_body`/`aero_force_body`/`aero_moment_y`
are untouched by Step 36 -- they depend on `t`/flow state, not directly
on mass.

Step 38: `weight_inertial` no longer assumes `z_hat_g = (0, 1)` inline --
it multiplies by `gravity.z_hat_g(t, s, p)` (main.tex SSModels > Gravity >
Direction; architecture.md SS23.1), which dispatches on
`p.gravity_direction` ("parallel", the default, returns exactly `(0, 1)`,
bit-for-bit unchanged; "radial" rotates it with downrange distance). This
is a direction-only change, orthogonal to the magnitude dispatch
`gravity.g` already performs.

Step 39: `thrust_body` gains a fixed nozzle cant `delta = p.thrust_misalign_deg`
(main.tex SSForces eq:thrust_vector; architecture.md SS23.2), returning
`T*(cos(delta), sin(delta))` instead of the on-axis `(T, 0.0)`. `delta = 0.0`
(the default) reproduces the on-axis vector bit-for-bit. dynamics.py needs
no change -- `_cross_y(aB, thrust)` was already written generically enough
to pick up the resulting moment (see that module's docstring).

Step 44: `aero_moment_y`'s "coefficients" regime gains a pitch-damping term
(analysis.tex SSDynamic stability; architecture.md SS24.4) -- see that
function's own docstring for the closed form and the division-free `V = 0`
note. `p.c_mq = 0.0` (the default) reproduces the pre-Step-44 `A_m`
bit-for-bit. The `"constant"` regime is untouched.

Step 48 (architecture.md SS27.2): `parachute_deployed` and
`parachute_drag_inertial`, a new natively-inertial force (same standing as
`weight_inertial`) for the recovery canopy. Unlike every aero force above,
it is deliberately NOT routed through the body axial/normal decomposition
-- a round canopy's drag opposes the relative wind vector, not the body's
nose direction, which under canopy may be frozen at any attitude
(dynamics.py's new branch). `parachute_deployed` is a pure function of
`(t, y, p)`, not a reference to the apogee *event* -- the RHS runs before
any event is finalised, so "has apogee happened" has to be reconstructed
from the state being integrated, not looked up from `Result.events`.

Step 49 (architecture.md SS27.3): `aero_force_body` gains one additive
term, `A_brake`, for a feedback-controlled airbrake -- see that function's
own docstring for the formula and the off-switch accounting. The
controller itself (a pure, memoryless P-control law on predicted apogee)
lives in the new `sim/control.py`, not here -- `forces.py` only consumes
`control.airbrake_deploy_fraction(t, s, p)`, the same arm's-length
relationship it already has with `gravity.py`/`thrust_curve.py`/`aero.py`.
"""

import numpy as np

from sim import aero, control, gravity, thrust_curve
from sim.flow import flow_state
from sim.state import M, OMEGA, VX, VZ


def weight_inertial(t: float, s, p) -> np.ndarray:
    """W = m*g*z_hat_g, already in the inertial frame (main.tex SSForces).

    `g` is the model-selected magnitude from sim/gravity.py
    (`p.gravity_model`), not the raw `p.g` constant -- see the gravity.py
    docstring for the three variants implemented at Step 10.

    Step 36: `m` is the current, possibly time-varying mass -- `s[M]`
    (`state.M`) when the variable-mass model is on (`p.m_d` set), the
    fixed `p.m` otherwise (main.tex SSModels > Mass and moment of
    inertia; params.py's `m_d` on/off gate). Bit-for-bit `p.m` when the
    model is off, matching every other Phase 2 model-selection seam.

    Step 38: `z_hat_g` is the model-selected direction from
    sim/gravity.py (`p.gravity_direction`), not the fixed `(0, 1)` --
    see the gravity.py docstring for the two variants.
    """
    m = s[M] if p.weight.m_d is not None else p.weight.m
    return m * gravity.g(t, s, p) * gravity.z_hat_g(t, s, p)


def thrust_body(t: float, s, p, hold=None) -> np.ndarray:
    """T = T*(cos(delta)*x_hat_r + sin(delta)*z_hat_r) (main.tex SSForces
    eq:thrust_vector), body frame.

    Uses the thrust curve from sim/thrust_curve.py instead of a constant
    magnitude with hard-coded burn time. The thrust curve provides
    time-varying thrust and automatically cuts off when the curve ends
    (returns zero after the last defined point).

    Step 97 (C4, comment-only): sign convention -- positive `delta`
    (`p.lengths.misalign_deg`, formerly `thrust_misalign_deg`) tilts the
    thrust vector from `x_hat_r` toward `+z_hat_r`; with the thrust point
    aft of the CoG (`aB = -(l1+l2) x_hat_r`) the resulting pitching moment
    is `+(l1+l2)*T*sin(delta)` in the code's `_cross_y` convention. This
    is the code's own `delta`; the paper's `theta_t` is not asserted to
    share its sign.

    Step 39 (architecture.md SS23.2): `delta = p.thrust_misalign_deg`
    (converted to radians here, the same "degrees in Params, radians at
    first use" convention as `lat0_deg`/`azimuth_deg`/`wind_dir_deg`) is a
    fixed nozzle cant, not a commanded gimbal -- there is no control law.
    `delta = 0.0` (the default) gives back `(thrust, 0.0)` bit-for-bit,
    since `np.cos(0.0) == 1.0` and `np.sin(0.0) == 0.0` exactly.

    Step 59 (architecture-28-rewrite.md SS28.8): `hold` is accepted
    (default `None`) for the same "thread the full RHS chain now" reason
    as every other function in this module -- there is no registered
    sampled-data thrust/gimbal channel yet, so it is unused today.
    """
    thrust = thrust_curve.thrust(t, s, p)
    delta = np.radians(p.lengths.misalign_deg)
    return np.array([thrust * np.cos(delta), thrust * np.sin(delta)])


def aero_force_body(t: float, s, p, flow, hold=None, fb=None, c=None) -> np.ndarray:
    """A_f = -A_x*x_hat_r - A_z*z_hat_r (main.tex SSModels > Aerodynamics),
    body frame, unconditionally -- the Phase 1 form, for every alpha, not
    just alpha = 0.

    Step 56 (architecture-28-rewrite.md SS28.11, closing F8): `flow` is now
    a required parameter -- the caller's own `flow_state(t, s, p)` result --
    instead of this function recomputing it internally. `flow_state` is a
    pure, deterministic function of `(t, s, p)` alone (sim/flow.py; the
    Dryden turbulence realization it may call through is itself frozen per
    seed via `lru_cache`, so repeated calls with identical arguments return
    bit-identical results), so this is a pure call-count reduction -- the
    RHS now runs the atmosphere/wind models once per evaluation instead of
    redundantly recomputing the identical `Flow` bundle a second time here.

    `A_x`, `A_z` are body-axis (axial/normal) coefficients: `flow.alpha`
    (from the actual relative wind, sim/flow.py) already drives `C_A(alpha,
    M)`/`C_N(alpha, M)` below, so the force itself is *not* additionally
    rotated through `flow.u_hat`/`flow.n_hat` (the relative-wind frame) --
    doing so would double-apply the alpha-dependence, since those
    coefficients are extracted in body axes to begin with (Step 35, Phase
    2.5; see main.tex SSModels > Relative wind and angle of attack for what
    `u_hat`/`n_hat` are used for instead: V, alpha, q).

    Step 55 (architecture-28-rewrite.md SS28.5): `C_x`/`C_z` come from the
    single `aero.coefficients(t, s, p, flow)` bundle, dispatched on
    `p.aero.model` ("constant" | "linearized" | "table" -- sim/aero.py's
    module docstring):
            A_x = q * S * c.C_x
            A_z = q * S * c.C_z
    `"constant"` is now `q`-scaled like the other two models -- the bug
    fix this step exists for (sim/aero.py's module docstring); it used to
    be the raw, atmosphere-independent placeholder `p.A_x`/`p.A_z`.

    Step 49 (architecture.md SS27.3): an additive airbrake term,
    `A_brake = q*Cd_brake*S_max*deploy_fraction`, after the `aero_model`
    branch above, unconditionally -- a linear deployment-fraction-to-area
    model, `S_brake(f) = f*S_max`, the simplest model that needs no new
    geometry beyond this step's own `Params` fields. Routed through the
    body axial direction (`x_hat_r`, i.e. added into `A_x` before the
    final negation), unlike the parachute (Step 48): an airbrake is
    rigidly mounted to the body and shaped to add axial drag regardless of
    pitch, the opposite physical situation from the free-swinging canopy,
    which opposes the relative wind vector instead -- a deliberate
    difference in treatment, not an inconsistency between the two steps.
    `control.airbrake_deploy_fraction` dispatches on `p.airbrake_model`
    ("none", the default, returns `0.0` unconditionally); `p.airbrake_kp
    == 0.0` and `p.airbrake_S_max == 0.0` (also both defaults) are two
    further independent off switches -- any one alone makes `A_brake`
    exactly `0.0`, reproducing every prior step bit-for-bit.

    Step 59 (architecture-28-rewrite.md SS28.8): `hold` is an optional
    `sim.sampling.Hold`, default `None` -- every pre-Step-59 call site is
    unaffected, bit-for-bit. Passed through to `aero.coefficients` (so a
    future sampled coefficient controller sees it) and to
    `control.airbrake_deploy_fraction` (so a sampled run's airbrake term
    is the zero-order-held value for the current tick, not a fresh
    per-substep/per-stage evaluation of the continuous law).
    """
    # Step 102 (D-109): `fb` is the brake fraction, computed once per RHS call by
    # `dynamics.derivatives` and passed down; a direct caller may omit it.
    if fb is None:
        fb = control.airbrake_deploy_fraction(t, s, p, hold)
    if c is None:  # Step 114: `dynamics.derivatives` passes the bundle it already computed
        c = aero.coefficients(t, s, p, flow, hold, fb)
    A_x =flow.q * p.aero.S * c.C_x
    A_z = flow.q * p.aero.S * c.C_z
    if p.control.airbrake_aero == "table":
        # The brake's drag/normal force/moment/CP shift are inside the table's f_b
        # axis; no separate additive term and no extra flow-direction factor.
        return np.array([-A_x, -A_z])
    A_brake = flow.q * p.control.airbrake_Cd * p.control.airbrake_S_max * fb
    # Step 93 (D-94a): the brake is a body-axis axial drag too, so it follows
    # the same flow-direction factor as `C_x` (architecture-34 SS34.3).
    A_brake *= aero.axial_flow_factor(flow.alpha)
    return np.array([-(A_x + A_brake), -A_z])


def aero_moment_y(t: float, s, p, flow, hold=None, fb=None, c=None) -> float:
    """A_m = -A_m*y_hat_r (main.tex SSMoments), scalar about y.

    Not used by dynamics.py yet -- theta/omega aren't integrated states
    until Step 6. Exposed now so that step just calls it.

    Step 56 (architecture-28-rewrite.md SS28.11, closing F8): `flow` is now
    a required parameter, the caller's own `flow_state(t, s, p)` result --
    see `aero_force_body`'s docstring for why reusing it is bit-for-bit.

    Step 55 (architecture-28-rewrite.md SS28.5): `C_m`/`C_mq` come from the
    single `aero.coefficients(t, s, p, flow)` bundle, dispatched on
    `p.aero.model` ("constant" | "linearized" | "table" -- sim/aero.py's
    module docstring):
            A_m = q * S * d_ref * c.C_m

    The pitch-damping term (Step 44; analysis.tex SSDynamic stability;
    architecture.md SS24.4), `c_m += q_hat*c_mq` with `q_hat =
    omega*d_ref/(2V)`, i.e. `A_m += q*S*d_ref*q_hat*c_mq`, now applies
    identically under all three models (architecture-28-rewrite.md
    SS28.5.3) -- it used to be specific to the old "coefficients" regime,
    but pitch damping is a property of the airframe, not of how the
    static coefficients happen to be supplied. Written division-free
    below (algebraically identical):
    `q*d_ref*q_hat = (rho*V^2/2)*d_ref*(omega*d_ref/(2V)) = rho*V*omega*d_ref^2/4`
    -- NOT a literal `omega*d_ref/(2*V)` intermediate, which would produce
    `0.0*inf = nan` at `V = 0.0` (every unperturbed flight's apogee; see
    aero.py's module docstring for the precedent, Step 35's `atan2` branch
    cut). `c_mq = 0.0` (the default) makes this term exactly `0.0` for
    every state, bit-for-bit pre-Step-44 -- same pattern as `A_e`/
    `thrust_misalign_deg`.

    Step 59 (architecture-28-rewrite.md SS28.8): `hold` is an optional
    `sim.sampling.Hold`, default `None` -- every pre-Step-59 call site is
    unaffected, bit-for-bit. Passed through to `aero.coefficients` only
    (same reasoning as `aero_force_body`'s docstring).

    Step 102 (D-109): `fb` is the brake fraction (see `aero_force_body`); only read
    under `Control.airbrake_aero == "table"`, where an omitted `fb` is computed here.
    """
    if fb is None:
        fb = control.airbrake_deploy_fraction(t, s, p, hold) if p.control.airbrake_aero == "table" else 0.0
    if c is None:
        c = aero.coefficients(t, s, p, flow, hold, fb)
    A_m =flow.q * p.aero.S * p.aero.d_ref * c.C_m
    A_m += 0.25 * flow.air.rho * flow.V * p.aero.S * p.aero.d_ref**2 * s[OMEGA] * c.C_mq
    return -A_m


def parachute_deployed(t: float, y: np.ndarray, p) -> bool:
    """Has the recovery canopy deployed by now -- a pure function of
    `(t, y, p)`, never a lookup of the apogee *event* itself (architecture.md
    SS27.2): the RHS runs before any event is finalised, so it cannot read
    `Result.events`, and "has apogee happened" has to be reconstructed from
    the state actually being integrated.

    `p.parachute_model == "none"` (the default) is the primary off switch --
    always `False`, reproducing every prior step bit-for-bit.
    """
    if p.recovery.model == "none":
        return False
    if p.recovery.trigger == "timer":
        return t >= p.recovery.deploy_time
    # "apogee" (the default): y[VZ] > 0 means currently descending. On any
    # simple ballistic/drag trajectory this is true from apogee onward and
    # false before it -- a continuous, RHS-computable stand-in for "has
    # apogee happened yet", not a reference to the apogee *event* itself.
    # Known simplification: a pre-apogee transient dip (vz briefly positive
    # mid-boost on an unstable trajectory) would arm deployment early. Not a
    # concern for the nominal trajectories this project models; documented
    # here rather than guarded against, the same standing as B11.
    # Step 94 (D-94b): same 0.1 s pad guard as `_apogee_event` -- a rest start
    # with T(0) < mg sags tail-first for ~ms (vz > 0) and must not arm the chute.
    if t < 0.1:
        return False
    return y[VZ] > 0.0


def parachute_drag_inertial(t: float, s: np.ndarray, p, hold=None) -> np.ndarray:
    """F_chute_i, inertial frame, (0,0) whenever not deployed -- natively
    inertial like weight_inertial, since a round canopy's drag does not
    depend on body attitude (architecture.md SS27.2).

    Standard quadratic drag, `F = -0.5*rho*Cd*S*|v_rel|*v_rel`, opposing
    `v_rel_i` exactly -- the vector form of `A = 0.5*rho*V^2*Cd*S`,
    splitting the `|v|*v` product (rather than `(0.5*rho*V^2*Cd*S)*v_hat`)
    to avoid a `0/0` direction at `V = 0`, the same precedent as
    `aero_moment_y`'s division-free pitch-damping term above.

    Step 59 (architecture-28-rewrite.md SS28.8): `hold` is an optional
    `sim.sampling.Hold`, default `None` -- every pre-Step-59 call site is
    unaffected, bit-for-bit. Threaded through to `flow_state`/
    `wind.wind_inertial` only (no recovery-model sampled channel is
    registered today).
    """
    if not parachute_deployed(t, s, p):
        return np.zeros(2)
    # Local import: circular-import avoidance, same precedent as flow.py's
    # own `_wind_inertial` (that module's docstring).
    from sim import wind

    flow = flow_state(t, s, p, hold)
    v_rel_i = np.array([s[VX], s[VZ]]) - wind.wind_inertial(t, s, p, hold)
    return -0.5 * flow.air.rho * p.recovery.Cd * p.recovery.S * flow.V * v_rel_i