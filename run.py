"""Entry point / scenario definition.

Step 1: no dynamics yet -- just build a Params and an initial State and
print them, to prove the scaffolding works.
"""

import math

from sim.params import Params
from sim.state import State


def main() -> None:
    # Placeholder values, small-model-rocket scale. Exact numbers do not
    # matter yet -- there is no dynamics module until Step 2.
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

    print(params)
    print(state0)


if __name__ == "__main__":
    main()
