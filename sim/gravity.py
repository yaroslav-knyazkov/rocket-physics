"""Gravitational acceleration magnitude and direction (main.tex SSModels >
Gravity; architecture.md SS12 "the dispatch-dict extension of the SS4
seam", SS13 "sim/gravity.py -- gravity models", SS23.1 "non-parallel
gravity").

Magnitude and direction are two orthogonal dispatches, selected
independently by `p.gravity_model` and `p.gravity_direction`: any
magnitude variant may be combined with either direction variant.
`forces.weight_inertial` is `m*gravity.g(t, y, p)*gravity.z_hat_g(t, y, p)`.

Step 10 implemented the magnitude side, "constant" and "radial" (plus
"linear", removed at Phase 2.5 Step 34 -- it was strictly dominated by
"radial": a first-order truncation of the same inverse-square law that
goes negative above h = R_e/2, for no accuracy or cost advantage). Step 11
added "wgs84" -- the real-data magnitude variant (architecture.md SS13).

Step 38 (Phase 2.5) added the direction dispatch: "parallel" (the
default), the fixed z_hat_g = z_hat_i = (0, 1) every prior step used
under the flat-Earth assumption, or "radial", which rotates the local
vertical with downrange distance (main.tex eq:zhat_g_rotated,
architecture.md SS23.1): `phi = x/R_e`,
`z_hat_g(phi) = (-sin(phi), cos(phi))`.

Step 41 (Phase 2.7) adds a third direction value, "elliptical" (models.tex
SSGravity > Direction, paragraph "Construction (elliptical)"; architecture.md
SS24.1): the WGS84 ellipsoid normal, replaced near the launch point by its
osculating sphere in the flight-plane azimuth `chi` (Euler/Meusnier radius of
curvature `R_chi(phi0, chi)`). "radial" and "elliptical" now share one
`_dir_curved(t, y, p)` body, differing only in which radius
`curvature_radius(p)` returns for `p.gravity_direction` -- `p.R_e` for
"radial" (the *same* expression with the *same* operands as before, hence
bit-for-bit), `_R_chi(p)` for "elliptical". `phi0`/`chi` reuse `p.lat0_deg`/
`p.azimuth_deg` (already the WGS84 latitude used by `_g_wgs84` and the flight-
plane heading used by `wind.py`/`soundings.py`/`rotation.py`) -- no new
`Params` fields.

Step 42 (Phase 2.7) adds `ground_depth(t, y, p)` beside the direction
dispatch above (models.tex SSGravity > Direction, "Ground and impact
condition", eq. `h_true`; architecture.md SS24.2): the curved-ground
generalisation of `y[Z]` that `sim/integrate.py`'s ground-impact event now
reads, reusing this module's `curvature_radius(p)` seam.

Step 45 (Phase 2.8) adds `altitude_agl(y, p)`/`altitude_msl(y, p)` beside
`ground_depth` (models.tex SSGravity > Direction, eq. `h_true`;
architecture.md SS25), moved here from `sim/flow.py` (SS25.3) so this
module is self-contained (numpy + `sim.state` only) and sits at the bottom
of the import stack. `altitude_agl` is exactly `-ground_depth(0.0, y, p)`
-- one unary minus, no re-typed trigonometry -- so `_g_radial`/`_g_wgs84`
below, the atmosphere/wind tiers (`sim/atmosphere.py`, `sim/wind.py`) and
the reported/plotted altitude (`run.py`, `sim/plotting.py`) all now read
the curved altitude once a non-parallel `p.gravity_direction` is active,
promoting roadmap Backlog B8 in full. Prior to this step `_g_radial`/
`_g_wgs84` deliberately kept reading the flat `h = -z` even under a curved
direction model; that gap is what Step 45 closes.

`p.g` is the Phase 1 constant, read here as `g0` -- the reference value at
h = 0 that every magnitude model reduces to.
"""

import numpy as np

from sim.state import X, Z


def _g_constant(t: float, y: np.ndarray, p) -> float:
    """g = g0 (Phase 1 baseline). Bit-for-bit reproduces Phase 1."""
    return p.g0


def _g_radial(t: float, y: np.ndarray, p) -> float:
    """g0*(R_e/(R_e+h))^2 -- exact for a spherical, non-rotating Earth.

    `h = altitude_agl(y, p)` (Step 45): under a curved `p.gravity_direction`
    this reads the curved-ground altitude, not the flat `-z` -- `p.R_e`
    itself stays the geocentric falloff radius unchanged (architecture.md
    SS25.2: `p.R_e` and `curvature_radius(p)` are different quantities,
    never substituted for one another).

    Informational (conventions audit SS8.3), not a bug: this uses AGL while
    the sibling `_g_wgs84` below uses `altitude_msl` -- for a site with
    `Site.h0_m != 0` the two models disagree about the reference radius by
    `h0_m` (~3e-4 g per 1000 m). There is no single "standard" radial model
    to match here (it is itself an idealisation), so this is a documented
    internal inconsistency, not a fix: switching to `altitude_msl` would
    move pins for every `gravity.model = "radial"` scenario with a nonzero
    site elevation, for a correction far below this model's own fidelity.
    """
    h = altitude_agl(y, p)
    return p.g0 * (p.gravity.R_e / (p.gravity.R_e + h)) ** 2


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
    altitude_msl(y, p) (Step 45, architecture.md SS25.3) -- under a curved
    `p.gravity_direction` this is the curved-ground MSL altitude, not the
    flat `p.h0_m - z`. The ellipsoid/geoid distinction is ignored -- far
    below the model's own error here (architecture.md SS13).
    """
    phi = np.radians(p.site.lat0_deg)
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
    "radial": _g_radial,
    "wgs84": _g_wgs84,
}


def g(t: float, y: np.ndarray, p) -> float:
    """Gravitational acceleration magnitude [m/s^2] (main.tex SSModels >
    Gravity), dispatching on `p.gravity_model`.
    """
    return _GRAVITY_MODELS[p.gravity.model](t, y, p)


def _dir_parallel(t: float, y: np.ndarray, p) -> np.ndarray:
    """z_hat_g fixed at the launch site's own local vertical for the whole
    flight (main.tex SSModels > Gravity > Direction) -- today's behaviour,
    unconditionally, for every prior step and the default here.
    """
    return np.array([0.0, 1.0])


def _R_chi(p) -> float:
    """Osculating-sphere radius of curvature in the flight-plane azimuth
    `chi` (Euler/Meusnier), models.tex SSGravity > Direction, "Construction
    (elliptical)"; architecture.md SS24.1. Reuses `_WGS84_A`/`_WGS84_E2`
    (already defined above for `_g_wgs84`) -- no second copy of those
    constants.

        M(phi)   = a_e*(1-e^2) / (1-e^2*sin^2(phi))^1.5   # meridional radius
        N(phi)   = a_e / sqrt(1-e^2*sin^2(phi))            # prime-vertical radius
        R_chi    = 1 / (cos^2(chi)/M(phi0) + sin^2(chi)/N(phi0))

    `phi0 = p.lat0_deg` (the launch site's WGS84 geodetic latitude, the same
    quantity `_g_wgs84` uses), `chi = p.azimuth_deg` (the flight-plane
    heading, the same quantity `wind.py`/`soundings.py`/`rotation.py` use).
    """
    phi0 = np.radians(p.site.lat0_deg)
    chi = np.radians(p.site.azimuth_deg)
    s2 = np.sin(phi0) ** 2
    M = _WGS84_A * (1.0 - _WGS84_E2) / (1.0 - _WGS84_E2 * s2) ** 1.5
    N = _WGS84_A / np.sqrt(1.0 - _WGS84_E2 * s2)
    return float(1.0 / (np.cos(chi) ** 2 / M + np.sin(chi) ** 2 / N))


# Curvature radius of the ground/vertical construction, per direction model
# (architecture.md SS24.1). `None` == flat: the launch-point tangent plane,
# no curvature at all. Same dispatch-dict convention as
# `_GRAVITY_MODELS`/`_GRAVITY_DIRECTIONS`, so an unknown `gravity_direction`
# raises KeyError here too.
_CURVATURE_RADII = {
    "parallel":   lambda p: None,
    "radial":     lambda p: p.gravity.R_e,
    "elliptical": _R_chi,
}


def curvature_radius(p) -> "float | None":
    """Radius of the sphere the local vertical (and, from Step 42, the
    ground) is constructed on, per `p.gravity_direction`. `None` for the
    flat "parallel" model (architecture.md SS24.1)."""
    return _CURVATURE_RADII[p.gravity.direction](p)


def _dir_curved(t: float, y: np.ndarray, p) -> np.ndarray:
    """z_hat_g rotated with downrange distance, on a sphere of radius
    `curvature_radius(p)` (main.tex eq:zhat_g_rotated, `phi = x/R`) -- a
    rigid rotation of the launch-point basis, unit norm for every `phi`,
    reducing to `_dir_parallel` at `phi = 0`. Shared by "radial" (where
    `curvature_radius(p)` returns `p.R_e`, so `phi = y[X]/p.R_e` is the
    *same expression with the same operands* as the pre-Step-41 `_dir_radial`
    -- bit-for-bit) and "elliptical" (where it returns `_R_chi(p)`).
    """
    phi = y[X] / curvature_radius(p)
    return np.array([-np.sin(phi), np.cos(phi)])


# Module-private dispatch dict, same convention as `_GRAVITY_MODELS` above:
# the public seam is `z_hat_g(t, y, p)`, orthogonal to `g(t, y, p)` -- any
# magnitude may combine with any direction.
_GRAVITY_DIRECTIONS = {
    "parallel": _dir_parallel,
    "radial": _dir_curved,      # was _dir_radial
    "elliptical": _dir_curved,
}


def z_hat_g(t: float, y: np.ndarray, p) -> np.ndarray:
    """Unit vector for the local gravity ("down") direction (main.tex
    SSModels > Gravity > Direction), dispatching on `p.gravity_direction`.
    """
    return _GRAVITY_DIRECTIONS[p.gravity.direction](t, y, p)


def ground_depth(t: float, y: np.ndarray, p) -> "float | np.ndarray":
    """Signed depth of the rocket below the ground surface, DOWN-positive --
    the curved-ground generalisation of `y[Z]` (models.tex SSGravity >
    Direction, eq:h_true, negated: architecture.md SS24.2). Negative in
    flight, zero at impact, increasing through zero as the rocket descends,
    for *every* direction model -- so `integrate._ground_event` keeps
    `direction = 1`, `terminal = True` unchanged; substituting `h_true`
    itself (up-positive, falling through zero) without also flipping the
    event's sign convention would make it hunt for the rocket leaving the
    ground upward and never terminate.

    `R = curvature_radius(p)` is `None` for "parallel" -- the flat
    launch-point tangent plane, where `ground_depth` returns `y[Z]`
    unchanged, with no arithmetic performed on that path at all: bit-for-bit.
    For "radial"/"elliptical", with `phi = y[X]/R`:

        ground_depth = z*cos(phi) - x*sin(phi) + R*(1 - cos(phi))

    which is exactly `z` at `x = 0` (`cos 0 = 1`, `sin 0 = 0`,
    `R*(1-1) = 0`, bitwise).

    The `R is None` branch is mandatory, not a stylistic shortcut: `h_true`
    only degenerates to `-z` in the limit `R -> infinity`, never at the
    code's finite `p.R_e` -- and passing `float("inf")` is not a substitute,
    since `inf*(1 - cos(phi))` at `phi = 0` is `inf*0.0 = nan`.
    """
    R = curvature_radius(p)
    if R is None:                 # "parallel": flat launch-point tangent plane
        return y[Z]               # returned unchanged -- bit-for-bit
    phi = y[X] / R
    return y[Z] * np.cos(phi) - y[X] * np.sin(phi) + R * (1.0 - np.cos(phi))


def altitude_agl(y: np.ndarray, p) -> "float | np.ndarray":
    """Height above the ground, up-positive -- `h_true` (models.tex
    SSGravity > Direction, eq:h_true; architecture.md SS25).

    Exactly `-ground_depth(t, y, p)`: one construction, one implementation,
    so the altitude the models read and the surface the impact event finds
    can never disagree. `ground_depth` ignores `t` (the reference surface
    does not move), so the `0.0` below is a placeholder, not a time.

    Under the default `gravity_direction = "parallel"` this is `-y[Z]`
    bitwise -- the pre-Step-45 `flow.altitude_agl(y)`, on the same operand
    (architecture.md SS25.6).

    Vectorises unchanged over a `(6, N)` state-history array (`ground_depth`
    is pure elementwise numpy): `y[Z]`/`y[X]` become length-`N` rows and
    `np.cos`/`np.sin` broadcast, giving a length-`N` result. This is
    load-bearing for `sim/plotting.py` (architecture.md SS25.5) -- do not
    narrow this annotation back to `float`.
    """
    return -ground_depth(0.0, y, p)


def altitude_msl(y: np.ndarray, p) -> "float | np.ndarray":
    """Height above mean sea level, `h_agl + p.h0_m`.

    Unchanged in form from the pre-Step-45 `flow.altitude_msl`: the MSL
    surface is concentric with the reference surface, `h0_m` below it, so
    the offset is exactly `h0_m` on a curved surface as on a flat one.
    Curvature reaches it entirely through `altitude_agl` above -- this
    function has no curvature code of its own.
    """
    return altitude_agl(y, p) + getattr(p.site, "h0_m", 0.0)


