"""The full symmetric moment-of-inertia tensor and general Euler's
rotational equations of motion for the 3D rotational dynamics (Step 30,
task-30-3d-rotational-dynamics.md SS30.1-30.3; dev/docs/latex/sections-ai/
rocket-3d.tex SSsec:3d_inertia, SSsec:3d_admissibility, SSsec:3d_eom_rot).

A new, small, deep module (`codebase-design` vocabulary): narrow public
interface (`tensor`, `validate`, `omega_dot`), no state, no I/O, all the
sign and admissibility knowledge behind it. `sim.params.Inertia` is the
user-supplied group this module reads -- see its own docstring for the
sign convention and the relation to `Weight.I`/`Roll.I_x`.

SIGN CONVENTION (task-30 SS30.1.2; eq:inertia_integrals, eq:inertia_matrix;
rocket-3d.tex SSsec:conventions). Moments of inertia and products of
inertia are the *integrals*

    I_xx = INT (y^2+z^2) dm     I_yy = INT (x^2+z^2) dm     I_zz = INT (x^2+y^2) dm
    I_xy = INT x*y dm           I_xz = INT x*z dm           I_yz = INT y*z dm

(Hibbeler SS21.1-21.2; Stevens & Lewis ch.1; what a CAD mass-properties
report calls "products of inertia"), so the MATRIX this module assembles
carries minus signs off the diagonal:

    [  I_xx  -I_xy  -I_xz ]
    [ -I_xy   I_yy  -I_yz ]
    [ -I_xz  -I_yz   I_zz ]

The minus signs appear in exactly one place, `tensor()` below, and are
pinned by `tests/test_inertia.py`'s point-mass convention test (the test
that cannot pass if any sign anywhere in this module is wrong).
"""

import numpy as np


def tensor(ine) -> np.ndarray:
    """The 3x3 symmetric inertia matrix in body axes from a `sim.params.
    Inertia` group (task-30 SS30.1.2, SS30.3.1; eq:inertia_integrals,
    eq:inertia_matrix). THE ONLY place the product-of-inertia minus signs
    appear in this codebase.

    Symmetry is structural (the same six names are written twice below),
    so no symmetrisation step and no runtime symmetry check are needed --
    `tests/test_inertia.py` pins `np.array_equal(I, I.T)` once, so an
    edit that breaks the literal's symmetry fails immediately.

    Built fresh per call -- not cached on `Params` (that group holds
    inputs, not derived arrays, task-30 SS30.3.1).
    """
    return np.array([
        [ine.I_xx, -ine.I_xy, -ine.I_xz],
        [-ine.I_xy, ine.I_yy, -ine.I_yz],
        [-ine.I_xz, -ine.I_yz, ine.I_zz],
    ])


def validate(ine, roll=None) -> None:
    """Fail-fast physical-admissibility check for an inertia tensor
    (task-30 SS30.1.5, SS30.8; eq:inertia_pd, eq:inertia_triangle,
    eq:inertia_ellipsoid, eq:inertia_transverse_bound). Raises
    `ValueError` naming the offending condition and the value(s) that
    triggered it. A no-op when `ine.model == "none"`.

    The two conditions checked -- positive definiteness and the triangle
    inequalities on the principal moments -- are together NECESSARY AND
    SUFFICIENT for the tensor to be realisable by some real mass
    distribution (task-30 SS30.1.5, eq:inertia_ellipsoid): there is no
    false-positive risk being traded away by checking eagerly here.

    `roll`, if given (a `sim.params.Roll` group), is cross-checked against
    `ine.I_xx` per task-30 SS30.8.3 check 4: `Roll.I_x` and `Inertia.I_xx`
    are the same physical quantity (axial MOI about x_hat_r, reaction
    wheel included and locked -- `Roll.I_x`'s own docstring) reached by
    two independent config paths, and a config that disagrees with itself
    about it is a bug nobody would find by reading two different files.
    Inert (no-op) whenever `roll is None` or `roll.model == "none"` --
    true for every config that sets only one of the two groups, which is
    every config that exists today.

    Called once, at config-assembly time (`configs/schema.py::assemble`,
    the SS109.7.2 eager-validation convention), not per RHS call --
    `sim.inertia.omega_dot` itself does not validate.
    """
    if ine.model == "none":
        return
    if ine.model != "tensor":
        raise ValueError(
            f"inertia.model={ine.model!r} is not a recognised inertia "
            "model; the legal values are 'none' and 'tensor'."
        )

    I = tensor(ine)
    eigvals = np.linalg.eigvalsh(I)  # ascending, real (I is symmetric)
    l1, l2, l3 = eigvals
    tol = 1e-12 * float(np.trace(I))  # absorbs eigensolver round-off only (SS30.8.3 notes)

    # Deliberately NO tolerance here, unlike the triangle check below --
    # task-30 SS30.8.3's own table gives this condition as the hard
    # `min(eigvalsh(I)) <= 0` (no `tol` term), while check 3 is explicitly
    # `< -tol`. Not an inconsistency: a `-tol`-forgiving version here would
    # ACCEPT an exactly singular tensor (eigenvalue == 0.0, e.g. an all-zero
    # or diag(0, 1, 1) tensor) as "admissible", which test 5
    # (test_validate_rejects_a_singular_tensor) requires to raise. The
    # eigensolver round-off this guards against in the triangle check is of
    # order 1e-16*trace(I); a tensor whose TRUE smallest eigenvalue is that
    # close to zero is itself numerically singular for omega_dot's own
    # np.linalg.solve (SS30.3.2), so treating it as inadmissible here is the
    # intended, conservative behaviour, not a bug to paper over with `tol`.
    if l1 <= 0.0:
        raise ValueError(
            f"inertia tensor is not positive definite (smallest principal "
            f"moment of inertia is {l1:.6g} kg*m^2, <= 0); a real rigid "
            "body's three principal moments of inertia must all be "
            "strictly positive (task-30 SS30.1.5a, eq:inertia_pd)."
        )

    triangle_slack = l1 + l2 - l3
    if triangle_slack < -tol:
        msg = (
            "inertia tensor fails the triangle inequality: the three "
            f"principal moments of inertia are ({l1:.6g}, {l2:.6g}, "
            f"{l3:.6g}) kg*m^2, so the smallest two sum to less than the "
            f"largest (l1 + l2 - l3 = {triangle_slack:.6g} < 0) -- no real "
            "mass distribution can produce this tensor (task-30 SS30.1.5b, "
            "eq:inertia_triangle)."
        )
        # SS30.1.5's I_xx <= |I_yy - I_zz| ceiling holds in ANY orthonormal
        # body frame (eq:inertia_transverse_bound derives from
        # eq:inertia_triangle directly on the raw diagonal entries, not
        # only on principal axes) -- so this is always a valid, additional
        # diagnostic to report whenever it is the one actually violated,
        # and it is the message a user is actually likely to hit.
        if abs(ine.I_yy - ine.I_zz) > ine.I_xx + tol:
            msg += (
                f" In particular, |I_yy - I_zz| <= I_xx must hold "
                f"(task-30 SS30.1.5, eq:inertia_transverse_bound): "
                f"I_xx={ine.I_xx:.6g}, I_yy={ine.I_yy:.6g}, "
                f"I_zz={ine.I_zz:.6g} kg*m^2, so |I_yy - I_zz| = "
                f"{abs(ine.I_yy - ine.I_zz):.6g} kg*m^2."
            )
        raise ValueError(msg)

    if roll is not None and roll.model != "none":
        scale = max(abs(roll.I_x), abs(ine.I_xx))
        if abs(roll.I_x - ine.I_xx) > 1e-9 * scale:
            raise ValueError(
                f"inertia tensor disagrees with the roll degree of "
                f"freedom's axial MOI: roll.I_x={roll.I_x:.6g} kg*m^2 != "
                f"inertia.I_xx={ine.I_xx:.6g} kg*m^2, but both are the "
                "same physical quantity -- the vehicle's axial moment of "
                "inertia about x_hat_r, reaction wheel included and "
                "locked (Roll.I_x's own docstring) -- reached by two "
                "independent config paths (task-30 SS30.8.3 check 4)."
            )


def omega_dot(I: np.ndarray, omega: np.ndarray, M: np.ndarray) -> np.ndarray:
    """Euler's rotational equation of motion, general form (task-30
    SS30.1.3, SS30.3.2; eq:eom_rot_3d, eq:eom_rot_3d_expanded;
    eq:eom_rot_3d_axisym for the axisymmetric reduction):

        omega_dot = I^-1 (M - omega x (I @ omega))

    `I` is body axes, constant (task-30 SS30.1.3 precondition 1: no 3D
    variable-mass model exists, so I is not I(t) here). `omega`/`M` are
    body-frame 3-vectors.

    The cross product is written out component-wise rather than via
    `np.cross`, matching `sim.quaternion.q_dot`'s own explicit style
    (and avoiding `np.cross`'s per-call overhead on a 3-vector).

    `np.linalg.solve`, not a precomputed/cofactor inverse (task-30 D-30.9):
    correctness first, and a slender airframe's tensor has a condition
    number of order I_yy/I_xx ~ 300 (rocket-3d.tex SSsec:3d_eom_rot) --
    fine for LU, worse for an explicit inverse.

    Does NOT validate `I`/`omega`/`M` -- `validate()` (already run by
    `configs/schema.py::assemble`, SS30.8.2) guarantees a validated `I` is
    non-singular, so `solve` cannot raise in a validated run; per-RHS-call
    validation is exactly the cost this project's eager-validation
    convention exists to avoid (task-109 SS109.7.2).
    """
    wx, wy, wz = omega
    Hx, Hy, Hz = I @ omega
    rhs = np.array([
        M[0] - (wy * Hz - wz * Hy),
        M[1] - (wz * Hx - wx * Hz),
        M[2] - (wx * Hy - wy * Hx),
    ])
    return np.linalg.solve(I, rhs)
