"""sim/mass.py -- the new module (Step 75, Phase 2.16).

docs/architecture-32-motor-separation.md SS32.3: this step is a PURE MOVE
of `sim/dynamics.py`'s three private mass-model helpers into
`propellant_mass`/`cog_position`/`moment_of_inertia` here, plus the new
`Lump`/`combine` assembly-time composition and the endpoint-model helpers
`total_impulse`/`isp_from_impulse`/`uniform_cylinder_I`.

The whole point of this step is that it is behaviour-preserving: the gate
is tests/test_dynamics.py's existing mass-model tests passing unedited
(they exercise the exact same expressions, now re-exported from here),
*and* that the new `combine()` agrees with the moved functions only to
~1e-15 relative, never bitwise (SS32.3.1 F3) -- a deliberate, measured,
documented difference, not a bug.
"""

import math

import pytest

from sim.mass import (
    Lump,
    combine,
    cog_position,
    isp_from_impulse,
    moment_of_inertia,
    propellant_mass,
    total_impulse,
    uniform_cylinder_I,
)
from sim.params import Params, Weight


def test_combine_one_lump_reproduces_it_to_1e15_relative_not_bitwise():
    """F4: `combine()` of a single lump is not an exact identity -- division
    by the lump's own mass can perturb `l` by an ULP, e.g. (measured in this
    repo) `m=1.5, l=0.4` gives `l_out == 0.4000000000000001`, not `0.4`
    exactly. So this test pins "agrees to 1e-15 relative", not "==".
    """
    lump = Lump(m=1.5, l=0.4, I=0.075)
    out = combine(lump)

    assert out.m == lump.m
    assert math.isclose(out.l, lump.l, rel_tol=1e-15)
    assert math.isclose(out.I, lump.I, rel_tol=1e-15)
    # bitwise equality is NOT claimed -- see the m=1.5, l=0.4 counterexample
    # above (F4). This repeats it directly so the point is self-contained:
    assert (lump.m * lump.l) / lump.m != lump.l
    assert (lump.m * lump.l) / lump.m == pytest.approx(lump.l, abs=0.0, rel=1e-15)


def test_combine_two_lumps_agrees_with_moved_functions_not_bitwise():
    """F3: `combine(dry, propellant)` computes the same l_B/I as
    `cog_position`/`moment_of_inertia`, to ~1e-15 relative -- a measured
    reassociation difference of ~2.1e-16 on a realistic case means bitwise
    equality must NOT be asserted here, only closeness.
    """
    m_d, l_d, I_d = 1.1, 0.62, 0.080
    m_p, l_p = 0.585, 0.78
    I_p = (I_d / m_d) * m_p

    p = Params(weight=Weight(m=m_d + m_p, I=0.0, m_d=m_d, l_d=l_d, l_p=l_p, I_d=I_d, I_sp=200.0))

    l_B_expected = cog_position(m_p, p)
    I_expected = moment_of_inertia(m_p, l_B_expected, p)

    dry = Lump(m=m_d, l=l_d, I=I_d)
    prop = Lump(m=m_p, l=l_p, I=I_p)
    combined = combine(dry, prop)

    assert math.isclose(combined.l, l_B_expected, rel_tol=1e-15)
    assert math.isclose(combined.I, I_expected, rel_tol=1e-15)
    # not claimed to be bitwise -- association order differs (F3)


def test_combine_is_order_independent():
    """math.fsum makes the composed result exactly independent of the
    order the lumps are passed in -- unlike a naive sum()-based reduction.
    """
    lumps = [Lump(m=1.1, l=0.62, I=0.080), Lump(m=0.585, l=0.78, I=0.045), Lump(m=0.3, l=0.1, I=0.01)]

    forward = combine(*lumps)
    reversed_order = combine(*reversed(lumps))
    shuffled = combine(lumps[1], lumps[2], lumps[0])

    assert reversed_order == forward
    assert shuffled == forward


def test_combine_zero_mass_returns_zero_lump_no_division_error():
    out = combine()
    assert out == Lump(m=0.0, l=0.0, I=0.0)

    out_two_zero = combine(Lump(m=0.0, l=1.0), Lump(m=0.0, l=-1.0))
    assert out_two_zero == Lump(m=0.0, l=0.0, I=0.0)


def test_uniform_cylinder_I_matches_hand_computation_for_k570_casing():
    """K570 casing: 54.0 mm diameter, 488.00 mm length (data/motors header)."""
    diameter_m = 54.0 / 1000.0
    length_m = 488.00 / 1000.0
    m = 0.695  # m_total - m_prop from the K570 header (F5)
    r = diameter_m / 2.0

    expected = m * (3.0 * r * r + length_m * length_m) / 12.0
    assert uniform_cylinder_I(m, length_m, diameter_m) == pytest.approx(expected, rel=1e-15)
    # sanity: hand-expanded form agrees too
    assert uniform_cylinder_I(m, length_m, diameter_m) == pytest.approx(
        0.695 * (3.0 * 0.027**2 + 0.488**2) / 12.0, rel=1e-12
    )


def test_isp_from_impulse_matches_k570_measured_figure():
    """F5: J=2062.223 N*s, m_prop=0.990 kg, g0=9.80665 -> I_sp_eff=212.4123 s."""
    assert isp_from_impulse(2062.223, 0.99, 9.80665) == pytest.approx(212.4123, abs=1e-4)


def test_total_impulse_matches_hand_integrated_trapezoid():
    """A small hand-built (t, F) curve, trapezoid-integrated by hand."""
    times = [0.0, 0.04, 0.1, 0.2]
    thrusts = [0.0, 892.67, 850.0, 600.0]

    expected = (
        0.5 * (times[1] - times[0]) * (thrusts[0] + thrusts[1])
        + 0.5 * (times[2] - times[1]) * (thrusts[1] + thrusts[2])
        + 0.5 * (times[3] - times[2]) * (thrusts[2] + thrusts[3])
    )

    assert total_impulse(times, thrusts) == pytest.approx(expected, rel=1e-15)


def test_propellant_mass_cog_position_moment_of_inertia_are_callable_directly():
    """The moved functions themselves, exercised at the new public names --
    complements tests/test_dynamics.py's own (unedited) coverage of the
    same expressions via the backward-compatible private aliases."""
    p = Params(weight=Weight(m=1.685, I=0.05, m_d=0.695, l_d=0.3, l_p=0.5, I_d=0.05, I_sp=200.0))

    m_p = propellant_mass(p.weight.m, p)
    assert m_p == pytest.approx(0.99, rel=1e-12)

    l_B = cog_position(m_p, p)
    assert p.weight.l_d < l_B < p.weight.l_p

    I = moment_of_inertia(m_p, l_B, p)
    assert I > p.weight.I_d
