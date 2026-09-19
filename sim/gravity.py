"""Gravitational acceleration magnitude, three interchangeable models
(main.tex SSModels > Gravity; architecture.md SS12 "the dispatch-dict
extension of the SS4 seam", SS13 "sim/gravity.py -- four gravity models").

All variants return the scalar magnitude `g`; the direction is always the
fixed z_hat_g = z_hat_i (down) under the flat-Earth assumption, so
`forces.weight_inertial` becomes `[0, m*gravity.g(t, y, p)]` and nothing
else changes.

This step implements three of the four main.tex variants: "constant",
"linear", "radial". The fourth ("wgs84", the real-data variant) arrives in
Step 11 (architecture.md SS13).

`p.g` is the Phase 1 constant, read here as `g0` -- the reference value at
h = 0 that every model reduces to.
"""

import numpy as np

from sim.flow import altitude_agl


def _g_constant(t: float, y: np.ndarray, p) -> float:
    """g = g0 (Phase 1 baseline). Bit-for-bit reproduces Phase 1."""
    return p.g


def _g_linear(t: float, y: np.ndarray, p) -> float:
    """g0*(1 - 2h/R_e) -- first-order expansion of the inverse-square law.

    Goes negative above h = R_e/2; physically irrelevant here, documented
    not guarded (architecture.md SS13).
    """
    h = altitude_agl(y)
    return p.g * (1.0 - 2.0 * h / p.R_e)


def _g_radial(t: float, y: np.ndarray, p) -> float:
    """g0*(R_e/(R_e+h))^2 -- exact for a spherical, non-rotating Earth."""
    h = altitude_agl(y)
    return p.g * (p.R_e / (p.R_e + h)) ** 2


# Module-private dispatch dict (architecture.md SS12): the public seam is
# the single `g(t, y, p)` function below; forces.weight_inertial never
# learns that variants exist. Not a plugin registry -- no registration API,
# unknown strings raise KeyError at the first RHS call (acceptable --
# architecture.md SS7 "no input validation").
_GRAVITY_MODELS = {
    "constant": _g_constant,
    "linear": _g_linear,
    "radial": _g_radial,
}


def g(t: float, y: np.ndarray, p) -> float:
    """Gravitational acceleration magnitude [m/s^2] (main.tex SSModels >
    Gravity), dispatching on `p.gravity_model`.
    """
    return _GRAVITY_MODELS[p.gravity_model](t, y, p)
