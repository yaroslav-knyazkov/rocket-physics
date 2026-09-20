"""Relative wind, angle of attack, and altitude conventions (architecture.md
SS15; main.tex SS"Relative wind and angle of attack").

This is Step 9's slice of the eventual `Flow` -- `V`, `alpha`, `u_hat`,
`n_hat` only. architecture.md SS15 also specifies `q`, `M`, `Re` and `air`
fields, but those need sim/atmosphere.py, which does not exist until Step
12/13 (roadmap.md Step 13: "Flow gains air, q, M, Re"). Adding them now
would mean fabricating an atmosphere model out of turn, so `Flow` here is
the Step-9 subset; Step 13 extends it, it does not replace it.

Step 21: `_wind_inertial` now delegates to `sim.wind.wind_inertial`
(architecture.md SS16) instead of the inline zeros stub. Its default,
`p.wind_model == "none"`, still returns exactly zero, so every result
computed before this step is unchanged.
"""

from typing import NamedTuple

import numpy as np

from sim.frames import to_body
from sim.state import THETA, VX, VZ, Z
from sim.atmosphere import AirState, air_state


class Flow(NamedTuple):
    V: float          # |v_rel| [m/s]
    alpha: float      # angle of attack [rad], atan2(w, u)
    u_hat: np.ndarray  # (cos alpha, sin alpha) -- body-frame, main.tex u_hat
    n_hat: np.ndarray  # (-sin alpha, cos alpha) -- body-frame, main.tex n_hat
    air: AirState      # local air state (density, pressure, temperature, speed of sound, viscosity)
    q: float           # dynamic pressure [Pa]
    M: float           # Mach number [-]
    Re: float          # Reynolds number [-]


def _wind_inertial(t: float, y: np.ndarray, p) -> np.ndarray:
    """Wind velocity in the inertial frame, (w_x, w_z) -- delegates to
    sim.wind.wind_inertial (architecture.md SS16, roadmap.md Step 21).

    Imported locally, not at module level, to avoid a circular import:
    sim.wind imports sim.flow.altitude_agl (its power-law shear profile is
    referenced to altitude AGL), so sim.flow cannot import sim.wind at
    module scope -- same convention as sim.atmosphere's `_sounding_air_state`/
    `_field_air_state` importing sim.soundings locally for the same reason.

    Kept as a function (not inlined at the call site) so flow_state itself
    never changes when the wind model changes.
    """
    from sim import wind

    return wind.wind_inertial(t, y, p)


def flow_state(t: float, y: np.ndarray, p) -> Flow:
    """v_rel = to_body(v_i - v_w, theta); V = |v_rel|; alpha = atan2(w, u);
    u_hat, n_hat per main.tex SS"Relative wind and angle of attack".

    Degenerate case V = 0 (on the pad at t = 0): alpha = atan2(0, 0) = 0 in
    Python, no exception -- no guard needed (architecture.md SS15).
    """
    v_i = np.array([y[VX], y[VZ]])
    v_w = _wind_inertial(t, y, p)
    u, w = to_body(v_i - v_w, y[THETA])

    V = float(np.hypot(u, w))
    alpha = float(np.arctan2(w, u))
    u_hat = np.array([np.cos(alpha), np.sin(alpha)])
    n_hat = np.array([-np.sin(alpha), np.cos(alpha)])

    # Get air state from atmosphere model
    air = air_state(t, y, p)

    # Compute derived quantities
    q = 0.5 * air.rho * V**2
    M = V / air.a if air.a != 0.0 else 0.0
    Re = air.rho * V * p.l_ref / air.mu if air.mu != 0.0 else 0.0

    return Flow(V=V, alpha=alpha, u_hat=u_hat, n_hat=n_hat,
                air=air, q=q, M=M, Re=Re)


def altitude_agl(y: np.ndarray) -> float:
    """Height above the launch point, h = -z (main.tex SSGravity; z is
    down-positive, zero at the launch point -- architecture.md SS15
    "Altitude conventions").
    """
    return -y[Z]


def altitude_msl(y: np.ndarray, p) -> float:
    """Height above mean sea level, h_msl = p.h0_m - z.

    `p.h0_m` (the launch site's MSL elevation) is not yet a Params field --
    it arrives with the site block in Step 11 (architecture.md SS18).
    `getattr(..., 0.0)` mirrors that field's eventual default, so this
    function is already correct both before and after Step 11 lands, and
    reduces to `altitude_agl` exactly while `h0_m` is absent/zero
    (architecture.md SS15: "p.h0_m defaults to 0.0, which makes the two
    identical").
    """
    return altitude_agl(y) + getattr(p, "h0_m", 0.0)