"""Result -> figures (architecture.md SS5, SS6).

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

from sim.gravity import altitude_agl
from sim.integrate import Result
from sim.state import X, VX, VZ, THETA, OMEGA


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
