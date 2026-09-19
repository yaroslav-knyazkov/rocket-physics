"""Gravitational acceleration magnitude, four interchangeable models
(main.tex SSModels > Gravity; architecture.md SS12 "the dispatch-dict
extension of the SS4 seam", SS13 "sim/gravity.py -- four gravity models").

All variants return the scalar magnitude `g`; the direction is always the
fixed z_hat_g = z_hat_i (down) under the flat-Earth assumption, so
`forces.weight_inertial` becomes `[0, m*gravity.g(t, y, p)]` and nothing
else changes.

Step 10 implemented three of the four main.tex variants: "constant",
"linear", "radial". Step 11 (this step) adds the fourth, "wgs84" -- the
real-data variant (architecture.md SS13).

`p.g` is the Phase 1 constant, read here as `g0` -- the reference value at
h = 0 that every model reduces to.
"""

import numpy as np

from sim.flow import altitude_agl, altitude_msl


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


# WGS84 (Somigliana) normal-gravity constants, architecture.md SS13. These
# are published, closed-form WGS84 reference-ellipsoid constants (National
# Imagery and Mapping Agency, "Department of Defense World Geodetic System
# 1984", TR8350.2) -- not a fit, not a dataset file, no new dependency.
_WGS84_GE = 9.7803253359     # equatorial normal gravity [m/s^2]
_WGS84_K = 0.00193185265241  # Somigliana's formula constant
_WGS84_E2 = 0.00669437999013  # first eccentricity squared
_WGS84_A = 6378137.0         # semi-major axis [m]
_WGS84_F = 1.0 / 298.257223563  # flattening
_WGS84_M = 0.00344978650684  # omega^2*a^2*b/GM


def _g_wgs84(t: float, y: np.ndarray, p) -> float:
    """Somigliana normal gravity at the ellipsoid surface, gamma0(phi),
    plus the second-order free-air correction to height h_msl above the
    ellipsoid (architecture.md SS13):

        gamma0(phi) = ge*(1 + k*sin^2(phi)) / sqrt(1 - e^2*sin^2(phi))
        g(phi, h)   = gamma0 * [1 - (2/a)(1+f+m-2f*sin^2(phi))*h + (3/a^2)*h^2]

    phi = p.lat0_deg (the launch site latitude; under the flat-range
    assumption it does not change during the flight), h = h_msl =
    p.h0_m - z (architecture.md SS15 "Altitude conventions"). The
    ellipsoid/geoid distinction is ignored -- far below the model's own
    error here (architecture.md SS13).
    """
    phi = np.radians(p.lat0_deg)
    sin2phi = np.sin(phi) ** 2

    gamma0 = (
        _WGS84_GE
        * (1.0 + _WGS84_K * sin2phi)
        / np.sqrt(1.0 - _WGS84_E2 * sin2phi)
    )

    h = altitude_msl(y, p)
    correction = (
        1.0
        - (2.0 / _WGS84_A) * (1.0 + _WGS84_F + _WGS84_M - 2.0 * _WGS84_F * sin2phi) * h
        + (3.0 / _WGS84_A ** 2) * h ** 2
    )
    return float(gamma0 * correction)


# Module-private dispatch dict (architecture.md SS12): the public seam is
# the single `g(t, y, p)` function below; forces.weight_inertial never
# learns that variants exist. Not a plugin registry -- no registration API,
# unknown strings raise KeyError at the first RHS call (acceptable --
# architecture.md SS7 "no input validation").
_GRAVITY_MODELS = {
    "constant": _g_constant,
    "linear": _g_linear,
    "radial": _g_radial,
    "wgs84": _g_wgs84,
}


def g(t: float, y: np.ndarray, p) -> float:
    """Gravitational acceleration magnitude [m/s^2] (main.tex SSModels >
    Gravity), dispatching on `p.gravity_model`.
    """
    return _GRAVITY_MODELS[p.gravity_model](t, y, p)
