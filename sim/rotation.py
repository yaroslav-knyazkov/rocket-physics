"""Non-inertial (Coriolis) frame correction (main.tex SSModels > Non-inertial
frame corrections; latex/sections/models.tex SS"Non-inertial frame
corrections (Earth's rotation)"; architecture.md SS4/SS12 "the
model-selection seam"; roadmap.md Step 37).

Reinterpreting F_0 as Earth-fixed rather than inertial adds two fictitious
translational accelerations, `a_Coriolis = -2*Omega x v` and
`a_centrifugal = -Omega x (Omega x r)`. The WGS84 gravity model
(sim/gravity.py) already folds the *static* part of the centrifugal term
(the launch site's own `Omega x (Omega x R_0)`) into `gamma0(phi)`; what is
new here is the Coriolis term (velocity-dependent, i.e. genuinely new
physics for a moving rocket) plus the small *residual* centrifugal term
(position-dependent, `Omega^2*s - (Omega.s)*Omega` for the rocket's own
displacement `s` from the launch site).

### Scope decision (Option B, approved by the user after reviewing the
    architect's derivation)

Only the **in-plane Coriolis** term is implemented, gated by
`p.earth_rotation` (default `False`, reproducing every prior step
bit-for-bit -- same on/off-gate convention as `p.m_d`/`p.aero_table`/
`p.wind_model`). Two things are deliberately *not* done:

1. **The residual centrifugal term is not implemented** (Option D,
   rejected). models.tex's own numbers: it is bounded by
   `Omega^2*|s| ~= 5.3e-9 * |s|`, i.e. ~5e-5 m/s^2 even at `|s| = 10 km` --
   roughly three orders of magnitude below the Coriolis term -- and its
   *vertical* part risks double-counting against the WGS84 free-air
   correction (`m` in gravity.py's Somigliana formula), which already
   carries the launch-site centrifugal term. Not worth the double-counting
   risk for a correction this small.

2. **The out-of-plane (lateral, `y_hat_g`) Coriolis component is computed
   but never fed back into the state.** models.tex's own derivation
   ("Which component of Omega actually matters in 2D") shows the in-plane
   acceleration comes *entirely* from `Omega_y` (the flight-plane-normal
   component of Earth's angular velocity), while the in-plane components
   of Omega (`Omega_x`, `Omega_z`) produce a *purely lateral* acceleration
   -- of the same order as the retained term, sometimes larger, not a
   smallness argument. This model has no lateral degree of freedom to
   receive it (same closure already applied to the crosswind component
   `w_y` in sim/wind.py). `coriolis_lateral_diagnostic` below exposes that
   discarded component so a due-North/South launch (`chi = 0` or `180`
   deg, where the *retained* in-plane term is exactly zero) does not read
   as "no Coriolis effect here" -- the true effect there is maximal and
   entirely lateral, which the in-plane number alone would hide.

### Tangent-plane basis and Omega's components

Working in the flight-plane triad `(x_hat_g, y_hat_g, z_hat_g)` already
fixed by the launch heading `chi = p.azimuth_deg` and `z_hat_g` pointing
down (this project's frame convention), models.tex projects Earth's
angular velocity onto it (eq:omega_components):

    Omega = Omega*(cos(phi0)*cos(chi)*x_hat_g
                    - cos(phi0)*sin(chi)*y_hat_g
                    - sin(phi0)*z_hat_g)

with `phi0 = p.lat0_deg` (the same latitude sim/gravity.py's WGS84 model
reads) and `chi = p.azimuth_deg` (the same heading sim/wind.py's ENU
projection reads). The minus sign on the z-component is a bookkeeping
consequence of this project's z-down convention, not a new physical
effect: Omega points *up* out of the northern hemisphere.

### In-plane Coriolis term

Substituting `Omega_y = -Omega*cos(phi0)*sin(chi)` into the retained
in-plane bracket of `-2*Omega x v` gives (models.tex eq:coriolis_2d,
componentwise, `vx = x-dot` downrange, `vz = z-dot` down-positive):

    a_Coriolis,x = +2*Omega*cos(phi0)*sin(chi)*vz
    a_Coriolis,z = -2*Omega*cos(phi0)*sin(chi)*vx

Two classical checks (models.tex): a rocket rising vertically at the
equator on an Eastward heading (`phi0=0`, `chi=90`, `vz<0`) drifts West
(`a_x < 0`), the textbook counterpart of the eastward deflection of a
falling body; a body moving East (`vx>0`) gets `a_z<0`, i.e. upward -- the
Eoetvoes effect.

### Moment

Coriolis (and centrifugal) accelerations are body forces distributed in
exact proportion to mass, so their resultant acts at the CoG and
contributes *zero* moment about it (models.tex SS"Moment"). Neither term
below touches the rotational equation of motion (`domega/dt` in
sim/dynamics.py) or the moment arms `p.l1`/`p.l2` -- there is nothing here
for them to couple to.
"""

import numpy as np

from sim.state import VX, VZ

OMEGA_EARTH = 7.2921e-5  # Earth's angular velocity magnitude [rad/s] (WGS84/IERS)


def omega_components(p) -> tuple[float, float, float]:
    """`(Omega_x, Omega_y, Omega_z)`: Earth's angular velocity projected onto
    the flight-plane triad `(x_hat_g, y_hat_g, z_hat_g)` at the launch site
    (models.tex eq:omega_components -- see module docstring).

    `Omega_x^2 + Omega_y^2 + Omega_z^2 == Omega^2` for every `phi0`, `chi`
    (a pure change of basis) -- exercised directly by
    tests/test_dynamics.py.
    """
    phi0 = np.radians(p.lat0_deg)
    chi = np.radians(p.azimuth_deg)
    omega_x = OMEGA_EARTH * np.cos(phi0) * np.cos(chi)
    omega_y = -OMEGA_EARTH * np.cos(phi0) * np.sin(chi)
    omega_z = -OMEGA_EARTH * np.sin(phi0)
    return float(omega_x), float(omega_y), float(omega_z)


def coriolis_inplane(t: float, y: np.ndarray, p) -> np.ndarray:
    """In-plane Coriolis acceleration `[a_x, a_z]` (models.tex
    eq:coriolis_2d -- see module docstring), the only part of
    `-2*Omega x v` that survives the 2D closure. `t` is accepted, unused,
    for the same `f(t, s, p)` signature every other model-selection
    function in this codebase uses (architecture.md SS4).

    Added to the translational acceleration by sim/dynamics.py only when
    `p.earth_rotation` is `True`; harmless (but wasted) to call otherwise.
    """
    phi0 = np.radians(p.lat0_deg)
    chi = np.radians(p.azimuth_deg)
    k = 2.0 * OMEGA_EARTH * np.cos(phi0) * np.sin(chi)
    vx, vz = y[VX], y[VZ]
    a_x = k * vz
    a_z = -k * vx
    return np.array([a_x, a_z])


def coriolis_lateral_diagnostic(t: float, y: np.ndarray, p) -> float:
    """The out-of-plane (`y_hat_g`) component of `-2*Omega x v` that the 2D
    closure discards (models.tex eq:coriolis_split, second bracket):

        a_Coriolis,y = -2*(Omega_z*vx - Omega_x*vz)

    **Not** fed back into the state or any force/acceleration sum -- this
    is a genuinely 2D model with no lateral degree of freedom to receive
    it (module docstring, point 2). Exposed purely as a labeled diagnostic,
    the same "compute a physically meaningful quantity on demand, outside
    the RHS" convention run.py's max-Q uses (`sim.flow.flow_state(...).q`,
    looped over a dense time grid by `run.py._flight_summary`) -- this
    value is never written into `state.py`'s `State` or
    `sim.integrate.Result`.

    Callable unconditionally, regardless of `p.earth_rotation` -- it is
    informational only and never changes the trajectory, so there is no
    reason to gate it behind the same flag that gates the in-plane
    correction. In particular it is generically *nonzero* exactly where
    `coriolis_inplane` is zero (`chi = 0`/`180` deg, or `phi0 = +-90` deg,
    where `Omega_y = 0` but `Omega_x`, `Omega_z` are not both zero) --
    that is the whole point of the diagnostic (module docstring, point 2):
    a due-North/South launch must not read as "no Coriolis effect here".
    """
    omega_x, _omega_y, omega_z = omega_components(p)
    vx, vz = y[VX], y[VZ]
    return float(-2.0 * (omega_z * vx - omega_x * vz))
