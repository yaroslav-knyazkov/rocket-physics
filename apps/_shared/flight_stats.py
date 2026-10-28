"""apps/_shared/flight_stats.py -- the shared flight-stats reduction
(Step 64, roadmap.md; dev/docs/architecture-30-apps-4-5-and-configs.md SS30.5;
moved here from apps/common/flight_stats.py at Phase 2.19 Step 131,
dev/docs/architecture-apps-sim-restructure.md).

Moved verbatim out of `apps/optimization/motor_selection/compare_motors.py`
(Step 61/62, `dev/docs/architecture-29-motor-selection.md` SS29.2-SS29.6),
where it was `MotorStats`/`flight_stats`. Promoted because App 3 was never
the only customer (SS30.2 F11): Apps 4/5 (airbrake `C_dA` determination,
mass/drag trade) want the exact same ascent-window reduction over a
`Result`, and three apps independently re-deriving the same numerics is
precisely the duplication this project pins against. `compare_motors.py`
now re-exports `FlightStats` as `MotorStats` so nothing downstream moves
(SS30.2 F11, `tests/test_motor_selection.py` imports `flight_stats` --
never `MotorStats` -- so the rename is invisible to the existing suite).

Zero behavioural change from the Step 61/62 version: same ascent window,
same `dynamics.derivatives` re-evaluation for an exact acceleration, same
`sample_rate_hz` guard, same grid (2000-point ascent union 2000-point burn
refinement).

This file is the one home for four decisions made at Phase 2.12
(`dev/docs/architecture-29-motor-selection.md` SS29.10, D-19..D-22):

- **D-19 -- measurement window.** Ascent-only (launch -> apogee) for every
  kinematic/aerodynamic extremum except impact time/downrange, which are
  whole-flight by definition. This project's own scenarios can put max
  speed *during descent* (frozen nose-up attitude, real axial drag
  accelerating a tail-first fall, roadmap.md Step 55), so a whole-flight
  extremum would silently be reporting a descent artifact in the column
  meant to answer "how fast does this motor make my rocket go."
- **D-20 -- acceleration source.** Re-evaluate `dynamics.derivatives` on
  this module's own sampling grid for an exact inertial acceleration,
  rather than finite-differencing the velocity grid -- no differencing
  stencil, no smearing of the thrust curve's kinks. This is also why
  `p.solver.sample_rate_hz != 0.0` is refused (`_assert_derivatives_
  reconstructible`): a post-hoc re-evaluation cannot reconstruct a
  sampled-data run's per-tick zero-order hold (`sim/sampling.py`,
  roadmap.md Step 59).
- **D-21 -- acceleration semantics.** Inertial `|dv/dt|`, gravity
  included -- not the accelerometer-sensed variant (`accel_vector -
  gravity`), which is a different, also legitimate, number this file does
  not compute.
- **D-22 -- "avg velocity" definition.** Time-average of `|v|` over the
  ascent window, via a proper time integral (`np.trapezoid` over the
  non-uniform grid) rather than `speed.mean()`, which would be wrong by
  the ratio of the refined to the coarse grid spacing.
"""

from __future__ import annotations

import dataclasses

import numpy as np

from apps.sim.engine import dynamics, gravity, mass, thrust_curve
from apps.sim.engine.flow import flow_state
from apps.sim.engine.gravity import altitude_agl
from apps.sim.engine.integrate import Result
from apps.sim.engine.params import Params
from apps.sim.engine.report import combined_stability_slope_series
from apps.sim.engine.state import M, THETA, VX, VZ, X

# The house dense-grid size (sim/report.py, apps/analysis/cfd_conditions/
# select_conditions.py both use 2000-4000-point grids over the window they
# reduce) -- SS29.4.2.
_ASCENT_GRID_N = 2000
_BURN_GRID_N = 2000


@dataclasses.dataclass(frozen=True)
class FlightStats:
    """The per-motor stats bundle (architecture-29-motor-selection.md
    SS29.4). Every field is a float or None; None means "the flight never
    produced this event" (SS29.4.6 -- a motor too small to leave the pad is
    a legitimate study result, not an error)."""

    apogee_altitude: float | None    # m AGL, the ranking criterion
    apogee_time: float | None        # s
    max_velocity: float | None       # m/s, ascent window, inertial |v|
    avg_velocity: float | None       # m/s, time-average over the ascent window
    max_accel: float | None          # m/s^2, ascent window, inertial |dv/dt| incl. gravity
    max_accel_g: float | None        # max_accel / p.g0 [-]
    max_q: float | None              # Pa, ascent window
    total_impulse: float | None      # N*s, delivered, numerically integrated over the ascent
    burnout_time: float | None       # s, from result.events
    impact_time: float | None        # s, from result.events (full flight)
    downrange_impact: float | None   # m, at impact (full flight)
    # Step 100 (architecture-35 SS35.4.5): additive, defaulted so every existing
    # constructor call and positional use is unchanged.
    max_mach: float | None = None         # -, ascent window, max flow Mach
    rail_exit_speed: float | None = None  # m/s, inertial |v| at the rail_exit event (None: no rail)


def _assert_derivatives_reconstructible(p: Params) -> None:
    """Shared guard (F8): a post-hoc `dynamics.derivatives` re-evaluation on
    this module's own sampling grid cannot reconstruct a sampled-data run's
    per-tick zero-order hold (`sim/sampling.py`, roadmap.md Step 59), so
    `max_accel` would silently not be the acceleration that actually flew.
    Called both before `run_sim` (`evaluate_motor`/`compare_motors`'
    pre-flight pass, so this fails in a millisecond rather than after a
    full integration) and again in `flight_stats` itself (which is a public
    pure function and may be called directly on a `Result`/`Params` pair
    this module did not itself produce).
    """
    if p.solver.sample_rate_hz != 0.0:
        raise ValueError(
            f"p.solver.sample_rate_hz={p.solver.sample_rate_hz} is not "
            "supported here: a post-hoc dynamics.derivatives re-evaluation "
            "cannot reconstruct a sampled-data run's per-tick zero-order "
            "hold (sim/sampling.py, roadmap.md Step 59), so max_accel would "
            "not be the acceleration that actually flew "
            "(architecture-29-motor-selection.md F8)."
        )


def flight_stats(result: Result, p: Params) -> FlightStats:
    """Reduce one `Result` to the stats bundle (SS29.4).

    Two measurement windows, per-quantity, not per-table (SS29.4.1):
    `apogee_altitude`/`apogee_time` at the apogee event instant;
    `max_velocity`/`avg_velocity`/`max_accel`/`max_q`/`total_impulse` over
    the **ascent only** (launch to apogee) -- because this project's own
    scenarios can put max speed *during descent* (frozen nose-up attitude,
    real axial drag accelerating a tail-first fall, roadmap.md Step 55), so
    a whole-flight extremum here would be reporting that descent artifact
    in the column that is supposed to answer "how fast does this motor make
    my rocket go"; `burnout_time` from the event; `impact_time`/
    `downrange_impact` over the **whole flight** (they are end-of-flight
    quantities by definition). A useful side effect: the ranking and every
    ascent column are unaffected by the recovery configuration.

    Raises `ValueError` if `p.solver.sample_rate_hz != 0.0`: a post-hoc
    `dynamics.derivatives` re-evaluation on this function's own sampling
    grid cannot reconstruct a sampled-data run's per-tick zero-order hold
    (`sim/sampling.py`, roadmap.md Step 59), so `max_accel` would silently
    not be the acceleration that actually flew. `p.solver.method == "rk4"`
    is allowed, but its dense interpolant is piecewise-linear
    (`sim/integrate.py`'s `_LinearInterpolant`), so grid-sampled extrema
    are then only as good as `p.solver.dt`.
    """
    _assert_derivatives_reconstructible(p)

    burnout_time = result.events["burnout"]
    impact_time = result.events["ground"]
    t_apogee = result.events["apogee"]

    t_end = impact_time if impact_time is not None else result.t[-1]
    t_full_grid = np.linspace(0.0, t_end, _ASCENT_GRID_N)
    y_full_grid = result.raw.sol(t_full_grid)
    downrange_impact = (
        float(result.raw.sol(impact_time)[X])
        if impact_time is not None
        else float(y_full_grid[X, -1])
    )

    if t_apogee is None:
        # Degenerate flight (SS29.4.6): the motor never produced an apogee
        # event (too small to leave the pad, or never comes back down
        # inside t_max). Every ascent-window field is unknowable; the
        # whole-flight fields are still reported.
        return FlightStats(
            apogee_altitude=None,
            apogee_time=None,
            max_velocity=None,
            avg_velocity=None,
            max_accel=None,
            max_accel_g=None,
            max_q=None,
            total_impulse=None,
            burnout_time=burnout_time,
            impact_time=impact_time,
            downrange_impact=downrange_impact,
        )

    apogee_altitude = float(altitude_agl(result.raw.sol(t_apogee), p))

    t_rail = result.events.get("rail_exit")
    rail_exit_speed = None
    if t_rail is not None:
        y_rail = result.raw.sol(t_rail)
        rail_exit_speed = float(np.hypot(y_rail[VX], y_rail[VZ]))

    # The ascent grid: the house 2000-point grid over [0, t_apogee], unioned
    # with a second 2000-point grid over [0, t_burnout] -- a motor's
    # ignition spike (~50 ms) would otherwise be under-sampled by a uniform
    # grid over a multi-second ascent (SS29.4.2). np.union1d sorts and
    # de-duplicates, giving a single strictly increasing, non-uniform grid.
    t_grid = np.linspace(0.0, t_apogee, _ASCENT_GRID_N)
    if burnout_time is not None and 0.0 < burnout_time < t_apogee:
        t_grid = np.union1d(t_grid, np.linspace(0.0, burnout_time, _BURN_GRID_N))
    y_grid = result.raw.sol(t_grid)

    speed = np.hypot(y_grid[VX], y_grid[VZ])
    max_velocity = float(speed.max())
    # Time-average over a non-uniform grid must be a proper time integral,
    # not speed.mean() (which would be wrong by the ratio of the refined to
    # the coarse spacing) -- np.trapezoid, not np.trapz (removed in numpy
    # 2.x, architecture-29-motor-selection.md F11).
    avg_velocity = float(np.trapezoid(speed, t_grid) / (t_grid[-1] - t_grid[0]))

    # Exact inertial acceleration: re-evaluate the RHS the integrator
    # itself saw, rather than finite-differencing the velocity grid (F7) --
    # no differencing stencil, no smearing of the thrust curve's kinks.
    dydt = np.array([dynamics.derivatives(t, y_grid[:, i], p) for i, t in enumerate(t_grid)])
    accel = np.hypot(dydt[:, VX], dydt[:, VZ])
    max_accel = float(accel.max())
    max_accel_g = max_accel / p.g0

    flows = [flow_state(t, y_grid[:, i], p) for i, t in enumerate(t_grid)]
    q = np.array([f.q for f in flows])
    max_q = float(q.max())
    max_mach = float(max(f.M for f in flows))

    T = np.array([thrust_curve.thrust(t, y_grid[:, i], p) for i, t in enumerate(t_grid)])
    total_impulse = float(np.trapezoid(T, t_grid))

    return FlightStats(
        apogee_altitude=apogee_altitude,
        apogee_time=float(t_apogee),
        max_velocity=max_velocity,
        avg_velocity=avg_velocity,
        max_accel=max_accel,
        max_accel_g=max_accel_g,
        max_q=max_q,
        total_impulse=total_impulse,
        burnout_time=burnout_time,
        impact_time=impact_time,
        downrange_impact=downrange_impact,
        max_mach=max_mach,
        rail_exit_speed=rail_exit_speed,
    )


# ----------------------------------------------------------------------
# Step 137 (Phase 2.17, dev/docs/task-136-137-point-mass-flight-path-angle.md
# TBD-1/SS8.1): point-mass flight-path-angle diagnostic over an already-
# simulated `Result`.
#
# Pure post-processing, additive -- NOT a new `State` component, NOT a new
# `p.solver.method`, NOT a change to `apps/sim/engine/dynamics.py` (ticket
# SS8.3/SS8.4). Every quantity below is read off `result.raw.sol(t_grid)`
# and existing public engine functions (`dynamics.derivatives`, `gravity.g`,
# `flow_state`, `report.combined_stability_slope_series`, `mass.*`), the
# same "re-evaluate the RHS the integrator itself saw" idiom `flight_stats`
# above already uses for `max_accel` -- so the numeric pins this module's
# sibling function feeds are untouched by construction.
#
# Notation (ticket SS4.1): `theta_v = atan2(-vz, vx)` is the INERTIAL
# flight-path angle, positive climbing (paper's z-down convention, SS4.1:
# "climbing (v_z<0) gives theta_v>0"). `theta_v_dot_pointmass =
# -(g/V)*cos(theta_v)` is eq:flightpath_rate (ticket SS4.4), the point-mass
# model's own prediction of that rate under assumptions A1-A5 (no lift,
# thrust aligned with v, flat Earth, no rotational DOF, still air). In
# still air, `alpha = theta_r - theta_v` exactly (ticket SS4.7), so
# `still_air_residual = theta - alpha - theta_v` is an EXACT identity (0,
# not approximately 0) whenever there is no wind -- this is the real test
# of SS4.7, not a tolerance-fudge (ticket SS8.1 #2). It is undefined (not
# "approximately 0") at the single degenerate instant `V == 0` (on the pad,
# before any velocity exists), exactly as `flow_state`'s own docstring
# already documents for `alpha` itself ("Degenerate case V = 0 ... alpha =
# atan2(0, 0) = 0, no exception needed") -- callers checking the identity
# should exclude `V <= 0` samples, the same way this diagnostic's own
# `lambda_ratio` excludes `V <= 0` from a real ratio.
# ----------------------------------------------------------------------

_FLIGHTPATH_GRID_N = 2000  # the house dense-grid size (see _ASCENT_GRID_N above, SS29.4.2)


def flight_path_angle(vx, vz):
    """`theta_v = atan2(-vz, vx)` [rad] -- the inertial flight-path angle,
    positive climbing (ticket SS4.1). Vectorised: `vx`/`vz` may be scalars
    or arrays of equal shape."""
    return np.arctan2(-np.asarray(vz, dtype=float), np.asarray(vx, dtype=float))


@dataclasses.dataclass(frozen=True)
class PointMassFlightPath:
    """The Step 137 diagnostic bundle (ticket SS8.1, TBD-1), one array per
    field, all sampled on the same `t` grid. `lambda_ratio` holds `NaN`
    wherever it is not a well-defined real number (ticket's own "else
    None" clause, ticket SS8.1 item 4) -- see `point_mass_flightpath`'s
    docstring for exactly which samples that is."""

    t: np.ndarray                      # [s]
    V: np.ndarray                      # [m/s], inertial speed |v|
    theta_v: np.ndarray                 # [rad], atan2(-vz, vx), positive climbing
    theta_v_dot_actual: np.ndarray      # [rad/s], exact, from the known a_i (dynamics.derivatives)
    theta_v_dot_pointmass: np.ndarray   # [rad/s], -(g/V)*cos(theta_v), eq:flightpath_rate
    lambda_ratio: np.ndarray            # [-], (g/V)/omega_n; NaN where omega_n is not available
    still_air_residual: np.ndarray      # [rad], theta - alpha - theta_v, wrapped to (-pi, pi]


def point_mass_flightpath(result: Result, p: Params, t_grid=None) -> PointMassFlightPath:
    """The Step 137 diagnostic (ticket SS8.1, TBD-1): `theta_v(t)`, its
    actual and point-mass-predicted rate, the validity ratio `Lambda(t)`,
    and the still-air consistency residual -- over `result`'s own dense
    interpolant (`result.raw.sol`), the same `_ASCENT_GRID_N`-style dense
    grid every other reduction in this module uses, but over the WHOLE
    recorded flight (launch to impact, or `result.t[-1]` if the flight
    never reaches the ground) rather than the ascent-only window `flight_
    stats` uses (SS29.4.1's D-19 window choice does not apply here -- this
    diagnostic is about where the point-mass model holds, which is as
    interesting during descent/canopy as during ascent).

    `t_grid`, if given, overrides the default dense grid (e.g. to zoom
    into one phase of the flight); must be sorted ascending.

    Raises `ValueError` under the same `p.solver.sample_rate_hz != 0.0`
    guard as `flight_stats` (`_assert_derivatives_reconstructible`) --
    `theta_v_dot_actual` re-evaluates `dynamics.derivatives` exactly like
    `flight_stats.max_accel` does, so the same zero-order-hold caveat
    applies.

    `lambda_ratio` (ticket SS5, SS8.1 #4): `Lambda = (g/V) / omega_n`,
    `omega_n = sqrt(-M_alpha)`, with

        M_alpha(t) = (q(t) * p.aero.S / I(t)) * combined_stability_slope_series(t)

    -- `combined_stability_slope_series` (`sim/report.py`, already verified
    machinery) computes exactly the bracket `d/dalpha[(l_g-l_p)*C_z -
    d_ref*C_m_code]` the paper's own `M_alpha` (`analysis.tex:173-175`)
    multiplies by `qS/I`; `I(t)` is the same instantaneous-or-fixed moment
    of inertia `dynamics.derivatives` itself uses (fixed `p.weight.I` with
    the mass model off, `mass.moment_of_inertia(...)` with it on). This is
    read off `result`'s OWN simulated flight, not a separate linearisation
    pass -- the paper's `M_alpha` is in general time-varying (aerodynamic
    stiffness scales with dynamic pressure, unlike a mechanical pendulum's
    structural one), and that time dependence is exactly what makes
    `Lambda` degrade at low `V` (ticket SS5's two caveats) within one
    flight, not just across different vehicles.

    `lambda_ratio[i]` is `NaN` (ticket's "else None", translated to the
    array-of-floats shape this diagnostic returns) whenever:
      - `V[i] <= 0` (division by zero -- on the pad, before launch), or
      - `M_alpha(t_i) >= 0` (no real `omega_n`: either the aero model has
        no alpha-slope at all, e.g. `aero.model == "constant"`'s literal
        alpha-independence -- `p.aero.d_ref`/`p.aero.S` being "present"
        is NOT sufficient on its own, a constant-coefficient model's
        `M_alpha` is identically 0 regardless of static margin -- or the
        airframe is genuinely statically unstable at that instant).
    This is the ticket's own "do not fabricate a value when the static-
    margin machinery isn't present for a given scenario" (SS8.1 #4),
    applied literally: `DEMO_SCENARIO`'s `aero.model == "constant"` makes
    `lambda_ratio` `NaN` everywhere for that scenario (see
    `tests/test_point_mass_flightpath.py`'s own finding on this) --
    `Lambda` needs an alpha-dependent aero model (`"linearized"` or
    `"table"`) to be a meaningful number at all.
    """
    _assert_derivatives_reconstructible(p)

    if t_grid is None:
        impact_time = result.events.get("ground")
        t_end = impact_time if impact_time is not None else float(result.t[-1])
        t_grid = np.linspace(0.0, t_end, _FLIGHTPATH_GRID_N)
    t_grid = np.asarray(t_grid, dtype=float)
    y_grid = result.raw.sol(t_grid)

    vx = y_grid[VX]
    vz = y_grid[VZ]
    theta = y_grid[THETA]
    V = np.hypot(vx, vz)
    theta_v = flight_path_angle(vx, vz)

    # Exact a_i re-evaluation (same idiom as flight_stats' max_accel above):
    # theta_v_dot_actual = d/dt atan2(-vz, vx) = (vz*ax - vx*az) / V^2.
    dydt = np.array([dynamics.derivatives(t, y_grid[:, i], p) for i, t in enumerate(t_grid)])
    ax = dydt[:, VX]
    az = dydt[:, VZ]
    g_vals = np.array([gravity.g(t, y_grid[:, i], p) for i, t in enumerate(t_grid)])

    flows = [flow_state(t, y_grid[:, i], p) for i, t in enumerate(t_grid)]
    alpha = np.array([f.alpha for f in flows])
    q_vals = np.array([f.q for f in flows])

    with np.errstate(divide="ignore", invalid="ignore"):
        V2 = np.where(V > 0.0, V, np.nan)
        theta_v_dot_actual = (vz * ax - vx * az) / V2**2
        theta_v_dot_pointmass = -(g_vals / V2) * np.cos(theta_v)

    residual = theta - alpha - theta_v
    # Wrap to (-pi, pi]: theta (y[THETA]) is not bounded like atan2's
    # output, so a flight that pitches past +-pi would otherwise show a
    # spurious +-2*pi offset in an otherwise-exact identity.
    residual = np.mod(residual + np.pi, 2.0 * np.pi) - np.pi

    _, combined_slope = combined_stability_slope_series(result, p, t_grid)
    I_vals = np.empty(t_grid.size)
    for i, t in enumerate(t_grid):
        if p.weight.m_d is None:
            I_vals[i] = p.weight.I
        else:
            m_p = mass.propellant_mass(float(y_grid[M, i]), p)
            l_B = mass.cog_position(m_p, p)
            I_vals[i] = mass.moment_of_inertia(m_p, l_B, p)

    with np.errstate(divide="ignore", invalid="ignore"):
        m_alpha = q_vals * p.aero.S / I_vals * combined_slope
        omega_n_sq = -m_alpha
        valid = (omega_n_sq > 0.0) & (V > 0.0)
        omega_n = np.sqrt(np.where(valid, omega_n_sq, 1.0))
        lambda_ratio = np.where(valid, (g_vals / np.where(V > 0.0, V, 1.0)) / omega_n, np.nan)

    return PointMassFlightPath(
        t=t_grid,
        V=V,
        theta_v=theta_v,
        theta_v_dot_actual=theta_v_dot_actual,
        theta_v_dot_pointmass=theta_v_dot_pointmass,
        lambda_ratio=lambda_ratio,
        still_air_residual=residual,
    )
