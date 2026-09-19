"""Entry point / scenario definition.

Step 4: vertical flight under gravity, constant thrust and a constant axial
aerodynamic force (thrust cuts off after sim.forces.T_BURN -- see that
module's docstring for why).
"""

import math

import matplotlib.pyplot as plt

from sim.integrate import run_sim
from sim.params import Params
from sim.plotting import plot_time_histories
from sim.state import State, Z


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

    print(params)
    print(state0)
    print(f"Apogee altitude: {apogee_altitude:.4f} m")
    print(f"Apogee time:     {apogee_time:.4f} s")
    print(f"Impact time:     {impact_time:.4f} s")

    fig = plot_time_histories(result)
    # Always save to a file -- this may run in a non-interactive/headless
    # context (e.g. no display), where plt.show() would either do nothing
    # or raise. Saving a PNG guarantees a usable artifact either way.
    fig.savefig("output.png")
    print("Saved plot to output.png")
    try:
        plt.show()
    except Exception:
        pass


if __name__ == "__main__":
    main()
