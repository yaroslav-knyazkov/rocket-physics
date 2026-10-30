"""apps/sim/engine/plotting.py -- Result -> figures (architecture.md SS5, SS6).

Step 45 (Phase 2.8; architecture.md SS25.5): the plotted altitude is
`gravity.altitude_agl(y, r.params)`, not a re-typed `-y[Z]` -- this module
now *asks* `sim.gravity` for the altitude instead of knowing the flat
convention itself; the `-z` knowledge moved with the helper
(architecture.md SS25.3). Under the default `gravity_direction =
"parallel"` this is bitwise `-y[Z]`, unchanged from every prior step.
Degrees still only ever appear here (and in run.py inputs) -- theta/omega
stay in radians everywhere else.
"""

import numpy as np
import matplotlib.pyplot as plt

from apps.sim.engine.gravity import altitude_agl
from apps.sim.engine.integrate import Result
from apps.sim.engine.state import X, VX, VZ, THETA, OMEGA
from apps.sim.engine.state3d import R as R3D, Q as Q3D
from apps.sim.engine.quaternion import to_euler


def _dense_time_grid(r: Result, n: int = 500) -> np.ndarray:
    """Uniform time grid covering the whole recorded flight.

    Sampled from the dense output `r.raw.sol(t)` rather than the raw
    adaptive-step points in `r.y`/`r.t` -- the accepted RK45 steps are
    sparse and unevenly spaced, so the dense interpolant gives a smoother,
    more accurate curve for a time-history read-out (see the Step 2
    dense-output note in run.py for the same reasoning applied to the
    apogee altitude). The apogee event is non-terminal, so the dense
    interpolant is valid across the whole flight, including past apogee.
    """
    t_end = r.events["ground"]
    if t_end is None:
        t_end = r.t[-1]
    return np.linspace(0.0, t_end, n)


def plot_trajectory(r: Result):
    """Downrange x vs altitude AGL, i.e. the flight path (Step 7)."""
    t = _dense_time_grid(r)
    y = r.raw.sol(t)

    downrange = y[X]
    altitude = altitude_agl(y, r.params)

    fig, ax = plt.subplots(figsize=(8, 6))
    ax.plot(downrange, altitude)
    ax.set_xlabel("Downrange [m]")
    ax.set_ylabel("Altitude [m]")
    ax.set_title("Flight trajectory")
    ax.set_aspect("equal", adjustable="datalim")
    ax.grid(True)

    fig.tight_layout()
    return fig


def plot_trajectory_overlay(results: "dict[str, Result]", title: str = "Model comparison"):
    """Overlay several `Result`s on one figure, one line per model variant
    (architecture.md SS12, roadmap.md Step 27 -- "the payoff for the
    selection pattern"). `results` keys are the model-selection strings
    (e.g. the `p.gravity_model` values that produced each `Result`) and
    become the legend labels.

    Two panels, both built on `_dense_time_grid` like `plot_trajectory`/
    `plot_time_histories` above: the flight path (downrange vs altitude,
    left) and altitude vs time (right). Both are cheap once the dense
    interpolant is sampled per variant, and they answer different
    questions -- path shape vs. how quickly altitude is gained/lost --
    which matters for e.g. the gravity sweep, where the paths are nearly
    identical but the altitude-vs-time curves separate a little more
    visibly around apogee.

    Returns the `fig`, does not call `plt.show()` -- same convention as
    `plot_trajectory`/`plot_time_histories`.
    """
    fig, (ax_traj, ax_alt) = plt.subplots(1, 2, figsize=(14, 6))

    for label, r in results.items():
        t = _dense_time_grid(r)
        y = r.raw.sol(t)
        downrange = y[X]
        altitude = altitude_agl(y, r.params)

        ax_traj.plot(downrange, altitude, label=str(label))
        ax_alt.plot(t, altitude, label=str(label))

    ax_traj.set_xlabel("Downrange [m]")
    ax_traj.set_ylabel("Altitude [m]")
    ax_traj.set_title(f"{title}: flight path")
    ax_traj.set_aspect("equal", adjustable="datalim")
    ax_traj.grid(True)
    ax_traj.legend()

    ax_alt.set_xlabel("Time [s]")
    ax_alt.set_ylabel("Altitude [m]")
    ax_alt.set_title(f"{title}: altitude vs time")
    ax_alt.grid(True)
    ax_alt.legend()

    fig.tight_layout()
    return fig


def plot_time_histories(r: Result):
    """Altitude, speed, pitch and pitch rate vs time (Step 3 + Step 7).

    theta/omega are converted from radians to degrees only here, per the
    units convention in params.py -- nothing internal ever sees degrees.
    """
    t = _dense_time_grid(r)
    y = r.raw.sol(t)

    altitude = altitude_agl(y, r.params)
    speed = np.hypot(y[VX], y[VZ])
    theta_deg = np.degrees(y[THETA])
    omega_deg = np.degrees(y[OMEGA])

    fig, ((ax_alt, ax_spd), (ax_theta, ax_omega)) = plt.subplots(
        2, 2, sharex=True, figsize=(10, 7)
    )

    ax_alt.plot(t, altitude)
    ax_alt.set_ylabel("Altitude [m]")
    ax_alt.set_title("Altitude vs time")
    ax_alt.grid(True)

    ax_spd.plot(t, speed)
    ax_spd.set_ylabel("Speed [m/s]")
    ax_spd.set_title("Speed vs time")
    ax_spd.grid(True)

    ax_theta.plot(t, theta_deg)
    ax_theta.set_xlabel("Time [s]")
    ax_theta.set_ylabel("Pitch theta [deg]")
    ax_theta.set_title("Pitch vs time")
    ax_theta.grid(True)

    ax_omega.plot(t, omega_deg)
    ax_omega.set_xlabel("Time [s]")
    ax_omega.set_ylabel("Pitch rate omega [deg/s]")
    ax_omega.set_title("Pitch rate vs time")
    ax_omega.grid(True)

    fig.tight_layout()
    return fig


# ----------------------------------------------------------------------
# Step 32 (Phase 3; architecture-37-step32-3d-integration-harness.md
# SS37.3/D-32.3, option O2): minimal additive 3D output. ADDITIVE ONLY --
# every function above is untouched. These three take a `Result` from
# `apps.sim.engine.integrate.run_sim_3d` (13-component state), never the
# 2D `run_sim` one; `_dense_time_grid` itself is layout-agnostic (reads
# only `r.events`/`r.t`/`r.raw.sol`), so it is reused verbatim.
# ----------------------------------------------------------------------


def plot_ground_track_3d(r: Result):
    """x-y ground track (D-32.3/O2). The acceptance artefact for a
    PLANAR run is a straight line along x with y exactly 0.0 -- itself a
    check (`tests/test_plotting3d.py` asserts the data series, not the
    figure)."""
    t = _dense_time_grid(r)
    y = r.raw.sol(t)
    x = y[R3D][0]
    y_lateral = y[R3D][1]

    fig, ax = plt.subplots(figsize=(8, 6))
    ax.plot(x, y_lateral)
    ax.set_xlabel("x [m]")
    ax.set_ylabel("y [m]")
    ax.set_title("Ground track")
    ax.set_aspect("equal", adjustable="datalim")
    ax.grid(True)

    fig.tight_layout()
    return fig


def plot_trajectory_3d(r: Result):
    """3D flight path (x, y, altitude AGL) -- the 3D-only twin of
    `plot_trajectory`. Altitude is `-z` directly, NOT routed through
    `gravity.altitude_agl` (which expects a 2D-shaped state): under the
    default `gravity_direction="parallel"` `altitude_agl` is exactly
    `-y[Z]` anyway (that function's own docstring), and `z` is the same
    down-positive inertial coordinate in both layouts, so this is exact
    for "parallel" and NOT attempted for the curved-ground variants --
    `run_sim_3d` is untested against curved gravity (out of scope, SS37.8:
    only `M_x = M_z = 0` planar aero is in scope for Step 32)."""
    t = _dense_time_grid(r)
    y = r.raw.sol(t)
    x = y[R3D][0]
    y_lateral = y[R3D][1]
    altitude = -y[R3D][2]

    fig = plt.figure(figsize=(9, 7))
    ax = fig.add_subplot(projection="3d")
    ax.plot(x, y_lateral, altitude)
    ax.set_xlabel("x [m]")
    ax.set_ylabel("y [m]")
    ax.set_zlabel("Altitude [m]")
    ax.set_title("3D flight trajectory")

    fig.tight_layout()
    return fig


def plot_attitude_history_3d(r: Result):
    """Yaw/pitch/roll time histories, degrees, from `quaternion.to_euler`
    (D-32.3/O2) -- the one place `to_euler`'s documented "plotting-style
    output only" contract (quaternion.py's own docstring, and D-32.9's
    restored guarantee) is exercised on purpose: this is presentation
    output, never read back into the integrated state."""
    t = _dense_time_grid(r)
    y = r.raw.sol(t)
    q = y[Q3D]

    n = q.shape[1]
    yaw = np.empty(n)
    pitch = np.empty(n)
    roll = np.empty(n)
    for i in range(n):
        yaw[i], pitch[i], roll[i] = to_euler(q[:, i])

    fig, (ax_yaw, ax_pitch, ax_roll) = plt.subplots(3, 1, sharex=True, figsize=(8, 9))

    ax_yaw.plot(t, np.degrees(yaw))
    ax_yaw.set_ylabel("Yaw [deg]")
    ax_yaw.set_title("Attitude history")
    ax_yaw.grid(True)

    ax_pitch.plot(t, np.degrees(pitch))
    ax_pitch.set_ylabel("Pitch [deg]")
    ax_pitch.grid(True)

    ax_roll.plot(t, np.degrees(roll))
    ax_roll.set_xlabel("Time [s]")
    ax_roll.set_ylabel("Roll [deg]")
    ax_roll.grid(True)

    fig.tight_layout()
    return fig
