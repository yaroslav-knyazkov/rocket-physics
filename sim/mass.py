"""The mass model: m(t), l_B(t), I(t) -- the one place the
two-lumped-mass model and the rigid-lump composition live
(docs/architecture-32-motor-separation.md SS32.3; main.tex SSsec:mass).

Step 75 is a PURE MOVE of `sim/dynamics.py`'s `_propellant_mass`,
`_cog_position` and `_moment_of_inertia`, expressions unchanged
character for character -- see F3: an equivalent-but-reassociated form
differs by one ULP, and `sim/dynamics.py`'s path must stay bit-for-bit.
`combine()` below computes the same mathematics for the ASSEMBLY-time
composition (once per config, at import) and is deliberately NOT what
`moment_of_inertia` is implemented in terms of.
"""

import dataclasses
import math

import numpy as np


@dataclasses.dataclass(frozen=True)
class Lump:
    """One rigid body. `l` is a station: POSITIVE, aft of the reference
    point (the nose tip A for airframe/vehicle lumps, the motor's
    forward face for motor-local lumps). `I` is about its OWN centroid."""
    m: float               # kg
    l: float                # m
    I: float = 0.0          # kg*m^2


def combine(*lumps: Lump) -> Lump:
    """Mass-weighted centroid + parallel axis, exact for any number of
    rigid lumps whose positions are fixed relative to one another
    (SS32.3.1 F2). Assembly-time only -- NOT bit-for-bit equal to
    `moment_of_inertia` below (F3: the two compute the same mathematics
    but associate the floating-point sum in a different order, which
    was measured to differ by a relative ~2.1e-16 on a realistic
    two-lump case -- never expect bitwise agreement, only ~1e-15
    relative), and not an exact identity for a single lump either (F4:
    `(m*l)/m != l` for some real `(m, l)` pairs in this repo's own
    numbers, e.g. `m=1.5, l=0.4` gives `0.4000000000000001`), so callers
    that need pass-through must say so explicitly (an early return)
    rather than calling `combine()` with one argument."""
    M = math.fsum(k.m for k in lumps)
    if M == 0.0:
        return Lump(m=0.0, l=0.0, I=0.0)
    l = math.fsum(k.m * k.l for k in lumps) / M
    I = math.fsum(k.I + k.m * (l - k.l) ** 2 for k in lumps)
    return Lump(m=M, l=l, I=I)


# --- moved verbatim from sim/dynamics.py (Step 75) -------------------
def propellant_mass(m: float, p) -> float:
    """m_p(t) = m(t) - m_d (main.tex SSModels > Mass and moment of inertia),
    clamped at 0. The adaptive solver overshoots the true burnout
    zero-crossing by a floating-point sliver on either side (the same
    reason `integrate.py`'s `_burnout_event` needs its own epsilon shift)
    -- a stray negative `m_p` right after burnout would flip the sign of
    every term below instead of just settling at the dry-mass endpoint.
    """
    return max(m - p.weight.m_d, 0.0)


def cog_position(m_p: float, p) -> float:
    """l_B(t): mass-weighted centroid of the two-lumped-mass model -- dry
    structure (mass m_d, fixed centroid l_d) and remaining propellant
    (mass m_p, centroid l_p) -- main.tex SSModels > Mass and moment of
    inertia.
    """
    return (p.weight.m_d * p.weight.l_d + m_p * p.weight.l_p) / (p.weight.m_d + m_p)


def moment_of_inertia(m_p: float, l_B: float, p) -> float:
    """I(t): parallel-axis theorem, dry structure + remaining propellant,
    each shifted from its own centroid to the instantaneous CoG l_B(t)
    (main.tex SSModels > Mass and moment of inertia):

        I(t) = I_d + m_d*(l_B-l_d)^2 + I_p(t) + m_p*(l_B-l_p)^2

    `I_p(t)`, the remaining propellant's own moment of inertia about its
    own centroid, is main.tex's own placeholder `\\todo` ("uniform
    density, fixed shape" until the grain geometry is known) -- taken
    proportional to `m_p(t)` via the dry structure's own specific moment
    of inertia `I_d/m_d` (i.e. propellant assumed to have the same
    mass-normalised MOI/radius of gyration as the dry structure): the
    simplest closed form that needs no geometry constant beyond the four
    this step introduces (`m_d, l_d, l_p, I_d`). Revisit once real grain
    geometry is available (main.tex's own note).
    """
    I_p = (p.weight.I_d / p.weight.m_d) * m_p
    return p.weight.I_d + p.weight.m_d * (l_B - p.weight.l_d) ** 2 + I_p + m_p * (l_B - p.weight.l_p) ** 2


# --- new, for the endpoint mass model (SS32.3.4) ---------------------
def total_impulse(times, thrusts) -> float:
    """J = integral of T_ref dt over the curve AS THE SIMULATOR SEES IT
    (SS32.4): trapezoid over the loaded points, which already include the
    (0,0) prepend `sim/motor_file.py` applies to RASP records (F5)."""
    return float(np.trapezoid(thrusts, times))


def isp_from_impulse(J: float, m_prop: float, g0: float) -> float:
    """I_sp_eff = J / (m_prop * g0) -- the specific impulse that makes
    today's `dm/dt = -T_ref(t)/(I_sp*g0)` consume exactly `m_prop` over
    exactly this curve (SS32.3.4, D-59)."""
    return J / (m_prop * g0)


def uniform_cylinder_I(m: float, length: float, diameter: float) -> float:
    """Transverse MOI of a uniform solid cylinder about its own centroid,
    `m*(3r^2 + L^2)/12` -- the default motor casing/grain inertia when
    nothing better is known (D-67). B24 replaces this with real grain
    geometry; it is an over-estimate for a thin-walled casing and an
    under-estimate for a cored grain, both by O(r^2/L^2)."""
    r = 0.5 * diameter
    return m * (3.0 * r * r + length * length) / 12.0
