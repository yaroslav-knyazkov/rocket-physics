"""apps/common/flight_stats.py -- the shared flight-stats reduction
(Step 64, roadmap.md; dev/docs/architecture-30-apps-4-5-and-configs.md SS30.5).

Moved verbatim out of `apps/motor_selection/compare_motors.py` (Step
61/62, `dev/docs/architecture-29-motor-selection.md` SS29.2-SS29.6), where it
was `MotorStats`/`flight_stats`. Promoted because App 3 was never the only
customer (SS30.2 F11): Apps 4/5 (airbrake `C_dA` determination, mass/drag
trade) want the exact same ascent-window reduction over a `Result`, and
three apps independently re-deriving the same numerics is precisely the
duplication this project pins against. `compare_motors.py` now re-exports
`FlightStats` as `MotorStats` so nothing downstream moves (SS30.2 F11,
`tests/test_motor_selection.py` imports `flight_stats` -- never
`MotorStats` -- so the rename is invisible to the existing suite).

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

from sim import dynamics, thrust_curve
from sim.flow import flow_state
from sim.gravity import altitude_agl
from sim.integrate import Result
from sim.params import Params
from sim.state import VX, VZ, X

# The house dense-grid size (sim/report.py, apps/cfd_conditions/
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

    q = np.array([flow_state(t, y_grid[:, i], p).q for i, t in enumerate(t_grid)])
    max_q = float(q.max())

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
    )
