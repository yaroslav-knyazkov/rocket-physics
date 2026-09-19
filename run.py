"""Entry point / scenario definition.

Step 4: vertical flight under gravity, constant thrust and a constant axial
aerodynamic force (thrust cuts off after sim.forces.T_BURN -- see that
module's docstring for why).

Step 7: full Phase 1 output -- trajectory + pitch plots and a printed flight
summary.
"""

import math

import numpy as np
import matplotlib.pyplot as plt

from sim.integrate import run_sim
from sim.params import Params
from sim.plotting import plot_time_histories, plot_trajectory
from sim.state import State, X, Z, VX, VZ, THETA, OMEGA


def main() -> None:
    # Placeholder values, small-model-rocket scale (unchanged from Step 1).
    params = Params(
        m=0.5,      # 0.5 kg dry+propellant mass
        I=0.05,     # kg*m^2, rough estimate for a small rocket
        l1=0.3,     # m, CoP -> CoG distance
        l2=0.4,     # m, CoP -> thrust point distance
        T=50.0,     # N, placeholder thrust
        A_x=0.5,    # N, placeholder axial aero force
        A_z=0.0,    # N, placeholder normal aero force
        A_m=0.0,    # N*m, placeholder aero pitching moment
    )

    # At rest on the pad, pointing straight up (theta = pi/2, nose-up
    # from horizontal), z = 0 at the launch point.
    state0 = State(x=0.0, z=0.0, vx=0.0, vz=0.0, theta=math.pi / 2, omega=0.0)

    result = run_sim(params, state0)

    apogee_time = result.events["apogee"]
    impact_time = result.events["ground"]
    # Evaluate the dense interpolant exactly at the apogee event time
    # rather than taking -min(z) over the adaptive-step samples: RK45's
    # accepted steps rarely land exactly on the apogee, so a raw min()
    # under-estimates it. dense_output=True gives us that interpolant.
    apogee_altitude = -result.raw.sol(apogee_time)[Z]

    # Max speed and downrange-at-impact: sample the dense interpolant on a
    # fine uniform grid over the whole recorded flight (apogee is a
    # non-terminal event, so the interpolant is valid past it too) rather
    # than relying on the sparse adaptive-step points in result.t/result.y.
    t_end = impact_time if impact_time is not None else result.t[-1]
    t_grid = np.linspace(0.0, t_end, 2000)
    y_grid = result.raw.sol(t_grid)
    speed = np.hypot(y_grid[VX], y_grid[VZ])
    max_speed = speed.max()

    if impact_time is not None:
        downrange_impact = result.raw.sol(impact_time)[X]
    else:
        downrange_impact = y_grid[X, -1]

    print(params)
    print(state0)
    print(f"Apogee altitude:     {apogee_altitude:.4f} m")
    print(f"Apogee time:         {apogee_time:.4f} s")
    print(f"Max speed:           {max_speed:.4f} m/s")
    print(f"Impact time:         {impact_time:.4f} s")
    print(f"Downrange at impact: {downrange_impact:.4f} m")

    fig_traj = plot_trajectory(result)
    fig_hist = plot_time_histories(result)
    # Always save to files -- this may run in a non-interactive/headless
    # context (e.g. no display), where plt.show() would either do nothing
    # or raise. Saving PNGs guarantees usable artifacts either way.
    fig_traj.savefig("trajectory.png")
    fig_hist.savefig("time_histories.png")
    print("Saved plots to trajectory.png and time_histories.png")

    # Optional one-line CSV dump (architecture.md SS7 "Persistence") for
    # diffing runs -- time, x, z, theta, omega on the same fine grid used
    # above for the summary stats.
    np.savetxt(
        "trajectory.csv",
        np.column_stack(
            [t_grid, y_grid[X], y_grid[Z], y_grid[THETA], y_grid[OMEGA]]
        ),
        delimiter=",",
        header="t,x,z,theta,omega",
        comments="",
    )
    print("Saved trajectory.csv")

    try:
        plt.show()
    except Exception:
        pass


if __name__ == "__main__":
    main()
