"""Relative wind, angle of attack, and altitude conventions (architecture.md
SS15; main.tex SS"Relative wind and angle of attack").

This is Step 9's slice of the eventual `Flow` -- `V`, `alpha`, `u_hat`,
`n_hat` only. architecture.md SS15 also specifies `q`, `M`, `Re` and `air`
fields, but those need sim/atmosphere.py, which does not exist until Step
12/13 (roadmap.md Step 13: "Flow gains air, q, M, Re"). Adding them now
would mean fabricating an atmosphere model out of turn, so `Flow` here is
the Step-9 subset; Step 13 extends it, it does not replace it.

Wind is zero for now (`_wind_inertial` is an inline stub) -- Step 21 fills
in sim/wind.py for real.
"""

from typing import NamedTuple

import numpy as np

from sim.frames import to_body
from sim.state import THETA, VX, VZ, Z


class Flow(NamedTuple):
    V: float          # |v_rel| [m/s]
    alpha: float      # angle of attack [rad], atan2(w, u)
    u_hat: np.ndarray  # (cos alpha, sin alpha) -- body-frame, main.tex u_hat
    n_hat: np.ndarray  # (-sin alpha, cos alpha) -- body-frame, main.tex n_hat


def _wind_inertial(t: float, y: np.ndarray, p) -> np.ndarray:
    """Wind velocity in the inertial frame, (w_x, w_z). Always zero until
    Step 21 (roadmap.md Step 9: "a stub wind_inertial returning zeros, or
    inline zeros"). Kept as a function (not inlined at the call site) so the
    real sim/wind.py can replace this one call without touching flow_state.
    """
    return np.zeros(2)


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

    return Flow(V=V, alpha=alpha, u_hat=u_hat, n_hat=n_hat)


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
