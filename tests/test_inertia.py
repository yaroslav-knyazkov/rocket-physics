"""Tests for Step 30 (task-30-3d-rotational-dynamics.md): the full
symmetric inertia tensor and general Euler's rotational equations of
motion (sim/inertia.py).

Written test-first (`tdd` skill): test 2 (the point-mass convention
check) is written before anything downstream relies on the sign
convention being right -- SS30.9 calls it "the single most important
test in this ticket", because it fails if any sign anywhere in
SS30.1.2/`sim.inertia.tensor` is wrong, independent of this module's own
algebra.

Physics sanity check, per the project's testing philosophy -- no
fixtures, no conftest.py, plain `assert` + `numpy.allclose`/`math.isclose`
(tests/test_dynamics3d.py's own module docstring).
"""

import math

import numpy as np
import pytest

from apps.sim.schema import Airframe, LaunchSite, Motor, Rocket, Scenario, Weather, assemble
from apps.sim.engine import inertia
from apps.sim.engine.params import Inertia, Roll


# ----------------------------------------------------------------------
# 1-2: the sign convention itself
# ----------------------------------------------------------------------


def test_tensor_is_symmetric_and_carries_the_minus_signs():
    """task-30 SS30.1.2/SS30.3.1, eq:inertia_matrix: the off-diagonal
    entries are the NEGATED products of inertia."""
    ine = Inertia(model="tensor", I_xx=1.0, I_yy=2.0, I_zz=3.0, I_xy=0.1, I_xz=0.2, I_yz=0.3)
    I = inertia.tensor(ine)
    expected = np.array([
        [1.0, -0.1, -0.2],
        [-0.1, 2.0, -0.3],
        [-0.2, -0.3, 3.0],
    ])
    assert np.array_equal(I, expected)
    assert np.array_equal(I, I.T)


def test_tensor_matches_the_mass_integral_for_three_point_masses():
    """THE CONVENTION PIN (task-30 SS30.9 #2) -- the single most
    important test in this ticket. Three point masses at hand-chosen
    asymmetric positions; the six tensor components are computed here by
    EXPLICIT SUMMATION of the eq:inertia_integrals definitions (not by
    calling `sim.inertia.tensor`), and `tensor(ine) @ omega` is checked
    against `sum(m * (r x (omega x r)))` computed independently with
    `np.cross` (eq:inertia_pd's own H = INT r x (omega x r) dm). This
    fails if ANY sign anywhere in SS30.1.2 is wrong, regardless of
    whether `sim.inertia`'s own algebra agrees with itself."""
    masses = [0.4, 0.25, 0.35]
    positions = [
        np.array([0.3, 0.02, -0.01]),
        np.array([-0.2, -0.05, 0.03]),
        np.array([0.05, 0.01, 0.08]),
    ]

    I_xx = sum(m * (r[1] ** 2 + r[2] ** 2) for m, r in zip(masses, positions))
    I_yy = sum(m * (r[0] ** 2 + r[2] ** 2) for m, r in zip(masses, positions))
    I_zz = sum(m * (r[0] ** 2 + r[1] ** 2) for m, r in zip(masses, positions))
    I_xy = sum(m * r[0] * r[1] for m, r in zip(masses, positions))
    I_xz = sum(m * r[0] * r[2] for m, r in zip(masses, positions))
    I_yz = sum(m * r[1] * r[2] for m, r in zip(masses, positions))

    ine = Inertia(model="tensor", I_xx=I_xx, I_yy=I_yy, I_zz=I_zz, I_xy=I_xy, I_xz=I_xz, I_yz=I_yz)
    I = inertia.tensor(ine)

    for omega in [
        np.array([1.0, 0.0, 0.0]),
        np.array([0.0, 1.0, 0.0]),
        np.array([0.0, 0.0, 1.0]),
        np.array([0.7, -0.4, 0.9]),
        np.array([-1.3, 0.6, 0.2]),
    ]:
        H_direct = sum(
            m * np.cross(r, np.cross(omega, r)) for m, r in zip(masses, positions)
        )
        H_matrix = I @ omega
        assert np.allclose(H_matrix, H_direct, rtol=1e-12, atol=1e-13)


# ----------------------------------------------------------------------
# 3-10: validate()
# ----------------------------------------------------------------------


def test_validate_accepts_a_slender_axisymmetric_airframe():
    """task-30 SS30.9 #3: the demo-airframe order of magnitude."""
    ine = Inertia(model="tensor", I_xx=5.47e-4, I_yy=0.15, I_zz=0.15)
    inertia.validate(ine)  # must not raise


def test_validate_accepts_an_off_principal_axis_tensor():
    """task-30 SS30.9 #4: small non-zero products of inertia on top of
    test 3's accepted tensor -- the user's chosen generality actually
    works."""
    ine = Inertia(
        model="tensor", I_xx=5.47e-4, I_yy=0.15, I_zz=0.15,
        I_xy=1e-5, I_xz=1e-5, I_yz=1e-5,
    )
    inertia.validate(ine)  # must not raise


def test_validate_rejects_a_singular_tensor():
    with pytest.raises(ValueError):
        inertia.validate(Inertia(model="tensor"))  # all-zero
    with pytest.raises(ValueError):
        inertia.validate(Inertia(model="tensor", I_xx=0.0, I_yy=1.0, I_zz=1.0))


def test_validate_rejects_a_negative_eigenvalue():
    """`[[1,-2],[-2,1]]` (the I_xx/I_yy/I_xy block) has eigenvalues 3, -1
    -- a product of inertia large enough to push a principal moment
    negative, even though every diagonal entry alone is positive."""
    ine = Inertia(model="tensor", I_xx=1.0, I_yy=1.0, I_xy=2.0)
    with pytest.raises(ValueError):
        inertia.validate(ine)


def test_validate_rejects_a_triangle_inequality_violation():
    """`diag(1, 1, 10)` is positive definite and still corresponds to no
    real body (task-30 SS30.1.5, rocket-3d.tex SSsec:3d_admissibility's
    own example)."""
    ine = Inertia(model="tensor", I_xx=1.0, I_yy=1.0, I_zz=10.0)
    with pytest.raises(ValueError):
        inertia.validate(ine)


def test_validate_bounds_the_transverse_split_by_the_axial_moment():
    """task-30 SS30.1.5/SS30.9 #8's ceiling: |I_yy - I_zz| <= I_xx
    (eq:inertia_transverse_bound). The message must name `I_xx`.

    NOTE on the concrete numbers: the ticket's own worked example
    (`I_xx=5.0e-4`, rejected at `I_zz=0.1504`, accepted at `I_zz=0.1503`)
    does not actually straddle the derived boundary -- both
    `|0.150-0.1504|=4e-4` and `|0.150-0.1503|=3e-4` are `<= I_xx=5e-4`,
    so BOTH are admissible by eq:inertia_transverse_bound; the ticket's
    "accepted" example is correct but its "rejected" one is not. This
    test keeps the ticket's accepted boundary case verbatim and replaces
    only the rejected one with a value that actually crosses the derived
    ceiling, so the test still exercises exactly the condition SS30.1.5
    derives (not the ticket's un-derived example numbers)."""
    bad = Inertia(model="tensor", I_xx=5.0e-4, I_yy=0.150, I_zz=0.1510)  # diff 1.0e-3 > I_xx
    with pytest.raises(ValueError, match="I_xx"):
        inertia.validate(bad)

    good = Inertia(model="tensor", I_xx=5.0e-4, I_yy=0.150, I_zz=0.1503)  # diff 3.0e-4 <= I_xx
    inertia.validate(good)  # must not raise


def test_validate_is_a_noop_when_model_is_none():
    ine = Inertia(model="none", I_xx=-1.0, I_yy=-5.0, I_zz=100.0)  # deliberately absurd
    inertia.validate(ine)  # must not raise


def test_validate_rejects_an_unknown_model():
    with pytest.raises(ValueError) as excinfo:
        inertia.validate(Inertia(model="diagonal"))
    msg = str(excinfo.value)
    assert "diagonal" in msg
    assert "none" in msg
    assert "tensor" in msg


# ----------------------------------------------------------------------
# 11-13: omega_dot()
# ----------------------------------------------------------------------


def test_omega_dot_reduces_to_the_axisymmetric_component_form():
    """task-30 SS30.1.4/SS30.9 #11, `eq:eom_rot_3d_axisym`: compare
    against the three scalar equations of that label, written out
    independently here (not calling `omega_dot`)."""
    I_a, I_t = 0.02, 0.15
    I = inertia.tensor(Inertia(model="tensor", I_xx=I_a, I_yy=I_t, I_zz=I_t))

    cases = [
        (np.array([0.3, -0.2, 0.5]), np.array([0.1, -0.05, 0.02])),
        (np.array([-0.4, 0.6, -0.1]), np.array([0.0, 0.03, -0.07])),
        (np.array([1.2, -0.8, 0.3]), np.array([0.2, 0.1, -0.15])),
    ]
    for omega, M in cases:
        wx, wy, wz = omega
        Mx, My, Mz = M
        expected = np.array([
            Mx / I_a,
            (My + (I_t - I_a) * wz * wx) / I_t,
            (Mz - (I_t - I_a) * wx * wy) / I_t,
        ])
        got = inertia.omega_dot(I, omega, M)
        assert np.allclose(got, expected, rtol=1e-12, atol=1e-12)


def test_omega_dot_reduces_to_the_2d_scalar_equation():
    """task-30 SS30.1.6/SS30.9 #12, `eq:eom_rot_3d_axisym`'s pitch line at
    `omega_x = omega_z = 0` -> `eq:eom_rot` itself: diagonal tensor,
    planar omega/M -> `domega/dt == M_y/I_yy` with x and z EXACTLY `0.0`."""
    I_t = 0.08
    I = inertia.tensor(Inertia(model="tensor", I_xx=0.001, I_yy=I_t, I_zz=I_t))
    omega = np.array([0.0, 0.3, 0.0])
    M = np.array([0.0, 0.05, 0.0])
    got = inertia.omega_dot(I, omega, M)
    assert got[0] == 0.0
    assert got[2] == 0.0
    assert math.isclose(got[1], M[1] / I_t, rel_tol=1e-12)


def _rk4_step(f, y, dt):
    """Classical fixed-step RK4 (same standard update as
    sim.integrate._run_rk4's own docstring), re-implemented here as a
    small, generic, state-shape-agnostic stepper -- no reusable one
    exists outside the 2D-state-specific `_run_rk4` (task-30 SS30.10.2:
    the project's own fixed-step rk4 is version-stable, unlike scipy's
    adaptive RK45, D-77)."""
    k1 = f(y)
    k2 = f(y + dt / 2.0 * k1)
    k3 = f(y + dt / 2.0 * k2)
    k4 = f(y + dt * k3)
    return y + dt / 6.0 * (k1 + 2.0 * k2 + 2.0 * k3 + k4)


def test_torque_free_motion_conserves_angular_momentum_and_energy():
    """THE GYROSCOPIC-TERM SIGN CHECK (task-30 SS30.9 #13, SS30.10.2). A
    fully asymmetric, admissible tensor (three distinct diagonal values
    AND non-zero products), non-zero 3-axis omega0, M = 0; integrate with
    the project's own fixed-step rk4 over 10s and assert `norm(I*omega)`
    and `0.5*omega.(I*omega)` are both constant to ~1e-9 relative. A sign
    error in any cross term breaks at least one of the two."""
    ine = Inertia(
        model="tensor", I_xx=0.05, I_yy=0.06, I_zz=0.065,
        I_xy=0.002, I_xz=0.0015, I_yz=0.001,
    )
    inertia.validate(ine)  # confirm the hand-picked tensor is admissible
    I = inertia.tensor(ine)

    omega = np.array([0.5, -0.3, 0.8])
    M = np.zeros(3)
    H0 = I @ omega
    Hnorm0 = np.linalg.norm(H0)
    KE0 = 0.5 * omega @ H0

    def f(w):
        return inertia.omega_dot(I, w, M)

    dt = 1e-4
    n_steps = int(round(10.0 / dt))
    max_dH = 0.0
    max_dKE = 0.0
    for _ in range(n_steps):
        omega = _rk4_step(f, omega, dt)
        H = I @ omega
        max_dH = max(max_dH, abs(np.linalg.norm(H) - Hnorm0) / Hnorm0)
        max_dKE = max(max_dKE, abs(0.5 * omega @ H - KE0) / abs(KE0))

    assert max_dH < 1e-9
    assert max_dKE < 1e-9


# ----------------------------------------------------------------------
# 14: the Roll.I_x cross-check, via assemble()
# ----------------------------------------------------------------------


def test_validate_rejects_a_tensor_that_disagrees_with_roll_I_x():
    """task-30 SS30.8.3 check 4, via `apps.sim.schema.assemble` (SS30.9
    #14): `Roll.I_x` and `Inertia.I_xx` are the same physical quantity
    (axial MOI, wheel included and locked) reached by two independent
    config paths; a config that disagrees with itself about it is
    rejected."""
    rocket = Rocket(
        name="rocket",
        airframe=Airframe(m=1.0, I=0.01),
        roll=Roll(model="free", I_x=0.02),
        inertia=Inertia(model="tensor", I_xx=0.021, I_yy=0.15, I_zz=0.1505),
    )
    sc = Scenario(
        name="scenario",
        rocket=rocket,
        motor=Motor(name="motor"),
        site=LaunchSite(name="site"),
        weather=Weather(name="weather"),
    )
    with pytest.raises(ValueError, match="I_x"):
        assemble(sc)
