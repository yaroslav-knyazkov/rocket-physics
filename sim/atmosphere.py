"""Local air state, three tiers behind one interface (architecture.md SS14;
main.tex SSModels > Atmosphere; roadmap.md Step 12).

Only tier 1, "isa" (pure-formula International Standard Atmosphere), is
implemented this step. Tiers 2/3 ("sounding", "field" -- measured profiles,
SS17) come later; the `_MODELS` dispatch dict below already has the shape
they will plug into (architecture.md SS12: "the same pattern applies
verbatim to atmosphere.py").

`air_state` is not wired into flow.py/forces.py/dynamics.py yet -- that is
Step 13 (roadmap.md Step 12: "No force changes in this step -- the
atmosphere is not wired into anything yet").
"""

from typing import NamedTuple

import numpy as np

from sim.flow import altitude_msl


class AirState(NamedTuple):
    rho: float   # density [kg/m^3]
    p:   float   # static pressure [Pa]
    T:   float   # temperature [K]
    a:   float   # speed of sound [m/s]
    mu:  float   # dynamic viscosity [Pa*s]


# ISA physical constants (architecture.md SS14). Module-level, not Params
# fields -- these are constants of the ISA standard's own definition, not
# scenario knobs (architecture.md SS14: "not Params fields").
_R_D = 287.0528       # specific gas constant for dry air [J/(kg*K)]
_GAMMA = 1.4          # ratio of specific heats for air
_G_ISA = 9.80665      # ISA's own fixed gravity -- see _isa_air_state below
_MU_0 = 1.716e-5      # Sutherland reference viscosity [Pa*s]
_T_0 = 273.15         # Sutherland reference temperature [K]
_S_MU = 110.4         # Sutherland's constant for air [K]
_R_ISA = 6356766.0    # effective Earth radius used for geopotential altitude [m]

# 7-layer ISA table (architecture.md SS14): (base geopotential altitude
# H_b [m], lapse rate L [K/m], base temperature T_b [K], base pressure
# p_b [Pa]). Covers troposphere through mesosphere (H up to ~80 km); the
# last layer's formula is used unbounded above its base.
_LAYERS = (
    (0.0,     -0.0065, 288.15, 101325.0),
    (11000.0,  0.0,    216.65, 22632.06),
    (20000.0,  0.0010, 216.65, 5474.889),
    (32000.0,  0.0028, 228.65, 868.0187),
    (47000.0,  0.0,    270.65, 110.9063),
    (51000.0, -0.0028, 270.65, 66.93887),
    (71000.0, -0.0020, 214.65, 3.956420),
)


def _isa_air_state(t: float, y: np.ndarray, p) -> AirState:
    """Tier 1: pure-formula ISA (main.tex SSModels > Atmosphere;
    architecture.md SS14).

    Geopotential altitude H = R_isa*h_msl/(R_isa + h_msl), then piecewise-
    linear temperature lapse, hydrostatic pressure, ideal-gas density,
    a = sqrt(gamma*R_d*T), Sutherland viscosity.

    `g_isa = 9.80665` is baked in as part of the ISA standard's own
    definition -- the pressure column is defined for a fixed g, not
    whatever gravity model the scenario selected -- so this must NOT call
    gravity.g() (architecture.md SS14, roadmap.md Step 12 "Careful").
    """
    h_msl = altitude_msl(y, p)
    H = _R_ISA * h_msl / (_R_ISA + h_msl)

    H_b, L, T_b, p_b = _LAYERS[0]
    for base_H, lapse, layer_T_b, layer_p_b in _LAYERS:
        if H < base_H:
            break
        H_b, L, T_b, p_b = base_H, lapse, layer_T_b, layer_p_b

    T = T_b + L * (H - H_b)
    if L != 0.0:
        press = p_b * (T / T_b) ** (-_G_ISA / (L * _R_D))
    else:
        press = p_b * np.exp(-_G_ISA * (H - H_b) / (_R_D * T_b))

    rho = press / (_R_D * T)
    a = np.sqrt(_GAMMA * _R_D * T)
    mu = _MU_0 * (T / _T_0) ** 1.5 * (_T_0 + _S_MU) / (T + _S_MU)

    return AirState(
        rho=float(rho), p=float(press), T=float(T), a=float(a), mu=float(mu)
    )


# Module-private dispatch dict (architecture.md SS12), same pattern as
# sim/gravity.py's `_GRAVITY_MODELS`: the public seam is `air_state`;
# callers never learn tiers exist. Unknown strings raise KeyError at the
# first call -- no input validation (architecture.md SS7).
_MODELS = {
    "isa": _isa_air_state,
}


def air_state(t: float, y: np.ndarray, p) -> AirState:
    """Local air state (main.tex SSModels > Atmosphere; architecture.md
    SS14), dispatching on `p.atmosphere_model`. All five fields come from
    the same (T, p) pair in one call, to avoid recomputing the layer
    lookup/interpolation per quantity and to keep them thermodynamically
    consistent (architecture.md SS14).
    """
    return _MODELS[p.atmosphere_model](t, y, p)
