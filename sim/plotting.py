"""Result -> figures (architecture.md SS5, SS6).

The only module allowed to know altitude = -z (architecture.md SS2). Every
other module works in z-down inertial coordinates; this one flips the sign
purely for human-readable output. Likewise, degrees only ever appear here
(and in run.py inputs) -- theta/omega stay in radians everywhere else.
"""

import numpy as np
import matplotlib.pyplot as plt

from sim.integrate import Result
from sim.state import X, Z, VX, VZ, THETA, OMEGA


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
    """Downrange x vs altitude (-z), i.e. the flight path (Step 7)."""
    t = _dense_time_grid(r)
    y = r.raw.sol(t)

    downrange = y[X]
    altitude = -y[Z]

    fig, ax = plt.subplots(figsize=(8, 6))
    ax.plot(downrange, altitude)
    ax.set_xlabel("Downrange [m]")
    ax.set_ylabel("Altitude [m]")
    ax.set_title("Flight trajectory")
    ax.set_aspect("equal", adjustable="datalim")
    ax.grid(True)

    fig.tight_layout()
    return fig


def plot_time_histories(r: Result):
    """Altitude, speed, pitch and pitch rate vs time (Step 3 + Step 7).

    theta/omega are converted from radians to degrees only here, per the
    units convention in params.py -- nothing internal ever sees degrees.
    """
    t = _dense_time_grid(r)
    y = r.raw.sol(t)

    altitude = -y[Z]
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
