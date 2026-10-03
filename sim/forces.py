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
"""

import numpy as np

from sim import aero, gravity, thrust_curve
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
    m = s[M] if p.m_d is not None else p.m
    return m * gravity.g(t, s, p) * gravity.z_hat_g(t, s, p)


def thrust_body(t: float, s, p) -> np.ndarray:
    """T = T*(cos(delta)*x_hat_r + sin(delta)*z_hat_r) (main.tex SSForces
    eq:thrust_vector), body frame.

    Uses the thrust curve from sim/thrust_curve.py instead of a constant
    magnitude with hard-coded burn time. The thrust curve provides
    time-varying thrust and automatically cuts off when the curve ends
    (returns zero after the last defined point).

    Step 39 (architecture.md SS23.2): `delta = p.thrust_misalign_deg`
    (converted to radians here, the same "degrees in Params, radians at
    first use" convention as `lat0_deg`/`azimuth_deg`/`wind_dir_deg`) is a
    fixed nozzle cant, not a commanded gimbal -- there is no control law.
    `delta = 0.0` (the default) gives back `(thrust, 0.0)` bit-for-bit,
    since `np.cos(0.0) == 1.0` and `np.sin(0.0) == 0.0` exactly.
    """
    thrust = thrust_curve.thrust(t, s, p)
    delta = np.radians(p.thrust_misalign_deg)
    return np.array([thrust * np.cos(delta), thrust * np.sin(delta)])


def aero_force_body(t: float, s, p) -> np.ndarray:
    """A_f = -A_x*x_hat_r - A_z*z_hat_r (main.tex SSModels > Aerodynamics),
    body frame, unconditionally -- the Phase 1 form, for every alpha, not
    just alpha = 0.

    `A_x`, `A_z` are body-axis (axial/normal) coefficients: `flow.alpha`
    (from the actual relative wind, sim/flow.py) already drives `C_A(alpha,
    M)`/`C_N(alpha, M)` below, so the force itself is *not* additionally
    rotated through `flow.u_hat`/`flow.n_hat` (the relative-wind frame) --
    doing so would double-apply the alpha-dependence, since those
    coefficients are extracted in body axes to begin with (Step 35, Phase
    2.5; see main.tex SSModels > Relative wind and angle of attack for what
    `u_hat`/`n_hat` are used for instead: V, alpha, q).

    Step 13: two regimes:
      * "constant": use the constant magnitudes p.A_x, p.A_z (Phase 1 behaviour)
      * "coefficients": compute from dynamic pressure and coefficients:
            A_x = q * S * C_A(alpha, M)
            A_z = q * S * C_N(alpha, M)

    Step 25: `C_A`/`C_N` come from sim/aero.py, which is table-driven
    (`p.aero_table`) with `p.C_A0`/`p.C_N_alpha*sin(alpha)` as the fallback
    (the `sin`, not raw `alpha`, is Phase 2.5 Step 35 -- see aero.py's
    module docstring) -- matching the pre-Step-25 formulas above to within
    that fallback's own small-angle error when no table is configured.
    """
    flow = flow_state(t, s, p)
    if p.aero_model == "constant":
        A_x = p.A_x
        A_z = p.A_z
    elif p.aero_model == "coefficients":
        A_x = flow.q * p.S * aero.C_A(flow.alpha, flow.M, p)
        A_z = flow.q * p.S * aero.C_N(flow.alpha, flow.M, p)
    else:
        raise ValueError(f"Unknown aero_model: {p.aero_model}")
    return np.array([-A_x, -A_z])


def aero_moment_y(t: float, s, p) -> float:
    """A_m = -A_m*y_hat_r (main.tex SSMoments), scalar about y.

    Not used by dynamics.py yet -- theta/omega aren't integrated states
    until Step 6. Exposed now so that step just calls it.

    Step 13: two regimes:
      * "constant": use the constant magnitude p.A_m (Phase 1 behaviour)
      * "coefficients": compute from dynamic pressure and coefficients:
            A_m = q * S * d_ref * C_m(alpha, M)

    Step 25: `C_m` comes from sim/aero.py, table-driven (`p.aero_table`)
    with `p.C_m_alpha*alpha` as the fallback -- identical numbers to the
    pre-Step-25 formula above when no table is configured.

    Step 44 (analysis.tex SSDynamic stability; architecture.md SS24.4):
    the "coefficients" regime adds a pitch-damping term, `c_m += q_hat*c_mq`
    with `q_hat = omega*d_ref/(2V)`, i.e. `A_m += q*S*d_ref*q_hat*c_mq`.
    Written division-free below (algebraically identical):
    `q*d_ref*q_hat = (rho*V^2/2)*d_ref*(omega*d_ref/(2V)) = rho*V*omega*d_ref^2/4`
    -- NOT a literal `omega*d_ref/(2*V)` intermediate, which would produce
    `0.0*inf = nan` at `V = 0.0` (every unperturbed flight's apogee; see
    aero.py's module docstring for the precedent, Step 35's `atan2` branch
    cut). `c_mq = 0.0` (the default) makes this term exactly `0.0` for
    every state, bit-for-bit pre-Step-44 -- same pattern as `A_e`/
    `thrust_misalign_deg`. `"constant"` regime untouched: it has no `q`,
    `V` or `rho` in it by definition, and `C_m`/`C_mq` are not consulted
    there.
    """
    flow = flow_state(t, s, p)
    if p.aero_model == "constant":
        A_m = p.A_m
    elif p.aero_model == "coefficients":
        A_m = flow.q * p.S * p.d_ref * aero.C_m(flow.alpha, flow.M, p)
        A_m += 0.25 * flow.air.rho * flow.V * p.S * p.d_ref**2 * s[OMEGA] \
            * aero.C_mq(flow.alpha, flow.M, p)
    else:
        raise ValueError(f"Unknown aero_model: {p.aero_model}")
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
    if p.parachute_model == "none":
        return False
    if p.parachute_deploy_trigger == "timer":
        return t >= p.parachute_deploy_time
    # "apogee" (the default): y[VZ] > 0 means currently descending. On any
    # simple ballistic/drag trajectory this is true from apogee onward and
    # false before it -- a continuous, RHS-computable stand-in for "has
    # apogee happened yet", not a reference to the apogee *event* itself.
    # Known simplification: a pre-apogee transient dip (vz briefly positive
    # mid-boost on an unstable trajectory) would arm deployment early. Not a
    # concern for the nominal trajectories this project models; documented
    # here rather than guarded against, the same standing as B11.
    return y[VZ] > 0.0


def parachute_drag_inertial(t: float, s: np.ndarray, p) -> np.ndarray:
    """F_chute_i, inertial frame, (0,0) whenever not deployed -- natively
    inertial like weight_inertial, since a round canopy's drag does not
    depend on body attitude (architecture.md SS27.2).

    Standard quadratic drag, `F = -0.5*rho*Cd*S*|v_rel|*v_rel`, opposing
    `v_rel_i` exactly -- the vector form of `A = 0.5*rho*V^2*Cd*S`,
    splitting the `|v|*v` product (rather than `(0.5*rho*V^2*Cd*S)*v_hat`)
    to avoid a `0/0` direction at `V = 0`, the same precedent as
    `aero_moment_y`'s division-free pitch-damping term above.
    """
    if not parachute_deployed(t, s, p):
        return np.zeros(2)
    # Local import: circular-import avoidance, same precedent as flow.py's
    # own `_wind_inertial` (that module's docstring).
    from sim import wind

    flow = flow_state(t, s, p)
    v_rel_i = np.array([s[VX], s[VZ]]) - wind.wind_inertial(t, s, p)
    return -0.5 * flow.air.rho * p.parachute_Cd * p.parachute_S * flow.V * v_rel_i