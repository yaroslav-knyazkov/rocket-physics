"""Result -> figures (architecture.md SS5, SS6).

The only module allowed to know altitude = -z (architecture.md SS2). Every
other module works in z-down inertial coordinates; this one flips the sign
purely for human-readable output.
"""

import numpy as np
import matplotlib.pyplot as plt

from sim.integrate import Result
from sim.state import Z, VZ


def plot_time_histories(r: Result):
    """Altitude and vertical speed vs time (Step 3: first plot).

    Sampled from the dense output `r.raw.sol(t)` on a uniform grid rather
    than the raw adaptive-step points in `r.y`/`r.t` -- the accepted RK45
    steps are sparse and unevenly spaced, so the dense interpolant gives a
    smoother, more accurate curve for a time-history read-out (see the
    Step 2 dense-output note in run.py for the same reasoning applied to
    the apogee altitude).
    """
    t_end = r.events["ground"]
    if t_end is None:
        t_end = r.t[-1]

    t = np.linspace(0.0, t_end, 500)
    y = r.raw.sol(t)

    altitude = -y[Z]
    vertical_speed = -y[VZ]  # z is down-positive; flip so "up" reads positive

    fig, (ax_alt, ax_vel) = plt.subplots(2, 1, sharex=True, figsize=(8, 6))

    ax_alt.plot(t, altitude)
    ax_alt.set_ylabel("Altitude [m]")
    ax_alt.set_title("Altitude vs time")
    ax_alt.grid(True)

    ax_vel.plot(t, vertical_speed)
    ax_vel.set_xlabel("Time [s]")
    ax_vel.set_ylabel("Vertical velocity [m/s]")
    ax_vel.set_title("Vertical velocity vs time")
    ax_vel.grid(True)

    fig.tight_layout()
    return fig
