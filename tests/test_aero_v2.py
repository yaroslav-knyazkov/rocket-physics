"""Tests for Step 99 (Phase 2.17, architecture-35 SS35.4.3, D-110/D-111):
aero table v2 -- CP station `l_p_m` from the nose, `# cm_convention:` header.
"""

import contextlib
import math
import os

import numpy as np
import pytest

from sim import aero, mass
from sim.dynamics import derivatives
from sim.flow import flow_state
from sim.integrate import run_sim
from sim.params import Aero, Lengths, Params, Solver, Weight
from sim.state import M as IM
from sim.state import State

_AERO_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "aero")

_BODY = (
    "alpha_deg,M,C_A,C_N,C_m,{arm}\n"
    "-10,0.5,0.35,-0.5236,0.0873,{v}\n"
    "0,0.5,0.30,0.0,0.0,{v}\n"
    "10,0.5,0.35,0.5236,-0.0873,{v}\n"
    "-10,1.0,0.60,-0.6981,0.1396,{v}\n"
    "0,1.0,0.55,0.0,0.0,{v}\n"
    "10,1.0,0.60,0.6981,-0.1396,{v}\n"
)


@contextlib.contextmanager
def _table(name, text):
    path = os.path.join(_AERO_DIR, name)
    with open(path, "w") as f:
        f.write(text)
    aero._load_table.cache_clear()
    try:
        yield name
    finally:
        aero._load_table.cache_clear()
        if os.path.exists(path):
            os.remove(path)


def _v2_text(arm="l_p_m", v=1.1, header=""):
    return header + _BODY.format(arm=arm, v=v)


def _mass_params(table, **kw):
    return Params(
        weight=Weight(m=2.0, I=0.1, m_d=1.5, l_d=0.8, l_p=1.3, I_d=0.08, I_sp=200.0),
        lengths=Lengths(l1=0.0, l2=0.4),
        aero=Aero(model="table", S=0.01, d_ref=0.1, table=table),
        **kw,
    )


def _y(m, theta=math.pi / 2 - 0.05):
    return np.array(State(x=0.0, z=-50.0, vx=2.0, vz=-80.0, theta=theta, omega=0.0, m=m))


# ----------------------------------------------------------------------
# Loader
# ----------------------------------------------------------------------


def test_loader_rejects_both_arm_columns():
    text = (
        "alpha_deg,M,C_A,C_N,C_m,l1_m,l_p_m\n"
        "0,0.5,0.3,0.0,0.0,0.28,1.1\n"
        "10,0.5,0.35,0.5,-0.08,0.28,1.1\n"
    )
    with _table("test_v2_both.csv", text) as name:
        with pytest.raises(ValueError, match="l1_m"):
            aero._load_table(name)


def test_loader_rejects_neither_arm_column():
    text = "alpha_deg,M,C_A,C_N,C_m\n0,0.5,0.3,0.0,0.0\n10,0.5,0.35,0.5,-0.08\n"
    with _table("test_v2_neither.csv", text) as name:
        with pytest.raises(ValueError, match="l_p_m"):
            aero._load_table(name)


def test_loader_accepts_l_p_m_and_exposes_station():
    with _table("test_v2_lp.csv", _v2_text()) as name:
        t = aero._load_table(name)
        assert t.l_p is not None and t.l1 is None
        assert np.all(t.l_p == 1.1)


def test_cm_convention_standard_flips_exactly_and_default_is_code():
    with _table("test_v2_code.csv", _v2_text()) as n_default, \
         _table("test_v2_codeh.csv", _v2_text(header="# cm_convention: code\n")) as n_code, \
         _table("test_v2_std.csv", _v2_text(header="# cm_convention: standard\n")) as n_std:
        t_default = aero._load_table(n_default)
        t_code = aero._load_table(n_code)
        t_std = aero._load_table(n_std)
        assert np.array_equal(t_default.C_m_code, t_code.C_m_code)
        assert np.array_equal(t_std.C_m_code, -t_code.C_m_code)
        # nothing else changes
        assert np.array_equal(t_std.C_N, t_code.C_N)


def test_unknown_cm_convention_is_an_error():
    with _table("test_v2_badconv.csv", _v2_text(header="# cm_convention: bogus\n")) as name:
        with pytest.raises(ValueError, match="cm_convention"):
            aero._load_table(name)


# ----------------------------------------------------------------------
# Arm follows the CG
# ----------------------------------------------------------------------


def test_arm_equals_l_p_minus_cog_at_three_times_along_burn():
    with _table("test_v2_arm.csv", _v2_text()) as name:
        p = _mass_params(name)
        arms = []
        for m in (2.0, 1.75, 1.5):  # launch, mid-burn, burnout
            y = _y(m)
            flow = flow_state(0.0, y, p)
            l1 = aero.coefficients(0.0, y, p, flow).l1
            expected = 1.1 - mass.cog_position(mass.propellant_mass(m, p), p)
            assert l1 == pytest.approx(expected, abs=1e-12)
            arms.append(l1)
        assert len(set(arms)) == 3  # the arm actually moves with the CG


def test_arm_reaches_the_moment_equation():
    """dynamics uses the moving arm: omega_dot matches a closed-form -l1*A_z - A_m."""
    with _table("test_v2_dyn.csv", _v2_text()) as name:
        p = _mass_params(name)
        y = _y(1.8, theta=math.pi / 2 - 0.1)
        flow = flow_state(0.0, y, p)
        c = aero.coefficients(0.0, y, p, flow)
        l_B = mass.cog_position(mass.propellant_mass(1.8, p), p)
        I = mass.moment_of_inertia(mass.propellant_mass(1.8, p), l_B, p)
        A_z = flow.q * p.aero.S * c.C_z
        A_m = flow.q * p.aero.S * p.aero.d_ref * c.C_m_code
        expected = (-(1.1 - l_B) * A_z - A_m) / I
        assert derivatives(0.0, y, p)[5] == pytest.approx(expected, rel=1e-9)


def test_l_p_with_mass_model_off_uses_lengths_l_g():
    with _table("test_v2_lg.csv", _v2_text()) as name:
        p = Params(
            weight=Weight(m=0.5, I=0.05),
            lengths=Lengths(l2=0.4, l_g=0.9),
            aero=Aero(model="table", S=0.01, d_ref=0.1, table=name),
        )
        assert aero.cop_l1(0.0, 0.5, p) == pytest.approx(1.1 - 0.9, abs=1e-15)


def test_l_p_with_mass_model_off_and_no_l_g_fails_fast():
    with _table("test_v2_nolg.csv", _v2_text()) as name:
        p = Params(
            weight=Weight(m=0.5, I=0.05),
            lengths=Lengths(l2=0.4),
            aero=Aero(model="table", S=0.01, d_ref=0.1, table=name),
        )
        with pytest.raises(ValueError, match="l_g"):
            aero.validate(p)
        with pytest.raises(ValueError, match="l_g"):
            aero.cop_l1(0.0, 0.5, p)


def test_l_p_config_requires_zero_misalignment():
    with _table("test_v2_mis.csv", _v2_text()) as name:
        p = Params(
            weight=Weight(m=0.5, I=0.05),
            lengths=Lengths(l2=0.4, l_g=0.9, misalign_deg=0.5),
            aero=Aero(model="table", S=0.01, d_ref=0.1, table=name),
        )
        with pytest.raises(ValueError, match="misalign"):
            aero.validate(p)


def test_constant_model_l_p_and_cm_convention():
    p = Params(
        weight=Weight(m=0.5, I=0.05),
        lengths=Lengths(l2=0.4, l_g=0.9),
        aero=Aero(model="constant", S=0.01, d_ref=0.1, C_x=0.5, C_m=0.2,
                  l_p=1.2, cm_convention="standard"),
    )
    assert aero.cop_l1(0.0, 0.5, p) == pytest.approx(0.3, abs=1e-15)
    assert aero.C_m_code(0.0, 0.5, p) == -0.2


def test_constant_model_cm_convention_flips_scalar_c_mq():
    """Step 115 (conventions audit §1.3): a scalar `c_mq` must flip under
    `cm_convention="standard"` exactly like `C_m` does -- previously only a
    table's `c_mq` column was flipped there, leaving the scalar path a
    silent trap for a textbook-signed `c_mq` under "standard"."""
    p_std = Params(
        weight=Weight(m=0.5, I=0.05),
        lengths=Lengths(l2=0.4, l_g=0.9),
        aero=Aero(model="constant", S=0.01, d_ref=0.1, C_x=0.5, C_m=0.2,
                  c_mq=-5.0, cm_convention="standard"),
    )
    assert aero.C_mq_code(0.0, 0.5, p_std) == 5.0

    p_lin = Params(
        weight=Weight(m=0.5, I=0.05),
        lengths=Lengths(l2=0.4, l_g=0.9),
        aero=Aero(model="linearized", S=0.01, d_ref=0.1, C_A0=0.5, C_m_alpha=0.2,
                  c_mq=-5.0, cm_convention="standard"),
    )
    assert aero.C_mq_code(0.0, 0.5, p_lin) == 5.0

    p_code = Params(
        weight=Weight(m=0.5, I=0.05),
        lengths=Lengths(l2=0.4, l_g=0.9),
        aero=Aero(model="constant", S=0.01, d_ref=0.1, C_x=0.5, C_m=0.2, c_mq=-5.0),
    )
    assert aero.C_mq_code(0.0, 0.5, p_code) == -5.0  # "code" (default): unflipped


def test_legacy_aero_defaults_unchanged():
    p = Params(weight=Weight(m=0.5, I=0.05), lengths=Lengths(l1=0.3, l2=0.4),
               aero=Aero(model="constant", C_m=0.2))
    assert aero.cop_l1(0.0, 0.5, p) == 0.3
    assert aero.C_m_code(0.0, 0.5, p) == 0.2
    aero.validate(p)  # nothing to complain about


# ----------------------------------------------------------------------
# Legacy example.csv is bit-identical (D-110 pin)
# ----------------------------------------------------------------------


def _legacy_params():
    return Params(
        weight=Weight(m=0.5, I=0.05),
        lengths=Lengths(l1=0.3, l2=0.4),
        aero=Aero(model="table", S=0.02, d_ref=0.08, table="example.csv", c_mq=0.5),
        solver=Solver(method="rk4", dt=0.01, t_max=3.0),
    )


def test_legacy_example_csv_derivatives_bit_identical():
    y = np.array(State(x=0.0, z=-100.0, vx=5.0, vz=-120.0, theta=math.pi / 2 - 0.15, omega=0.2))
    expected = [5.0, -120.0, 95.19213317699983, 141.38487260008193, 0.2, 303.41429748339385, 0.0]
    assert derivatives(0.0, y, _legacy_params()).tolist() == expected


def test_legacy_example_csv_flight_bit_identical():
    r = run_sim(_legacy_params(),
                State(x=0.0, z=0.0, vx=3.0, vz=-150.0, theta=math.pi / 2 - 0.1, omega=0.0))
    assert r.y[:, -1].tolist() == [
        4.104792032233924, -175.22328478629953, 0.8120291748612422,
        -21.230410008383114, 1.5328499845326253, -0.010647435014111114, 0.0,
    ]
    assert float(r.t[-1]) == 3.0


# ----------------------------------------------------------------------
# Shipped v2 table
# ----------------------------------------------------------------------


def _v2_example_params(convention_flip=False):
    # example_v2.csv declares `standard`; flipping = overriding the declaration is
    # done by loading a copy with the other header (see the report tests).
    return Params(
        weight=Weight(m=0.5, I=0.05),
        lengths=Lengths(l2=0.4, l_g=0.9),
        aero=Aero(model="table", S=0.02, d_ref=0.08, table="example_v2.csv", c_mq=0.5),
        solver=Solver(method="rk4", dt=0.01, t_max=3.0),
    )


def test_example_v2_matches_legacy_geometry_and_converts_cm():
    t_old = aero._load_table("example.csv")
    t_new = aero._load_table("example_v2.csv")
    assert t_new.l1 is None
    assert np.allclose(t_new.l_p - 0.9, t_old.l1, atol=1e-12)
    # legacy file kept its (textbook-sign) C_m; v2 declares `standard`, so it is flipped
    assert np.array_equal(t_new.C_m_code, -t_old.C_m_code)
    assert np.array_equal(t_new.C_N, t_old.C_N)


def _short_flight_alpha(table):
    """|alpha| at t = 0.02 s of a 0.1 s flight from a 0.1 rad attitude offset."""
    p = Params(
        weight=Weight(m=0.5, I=0.05),
        lengths=Lengths(l2=0.4, l_g=0.9),
        aero=Aero(model="table", S=0.02, d_ref=0.08, table=table, c_mq=0.5),
        solver=Solver(method="rk4", dt=0.001, t_max=0.1),
    )
    aero.validate(p)
    r = run_sim(p, State(x=0.0, z=0.0, vx=3.0, vz=-150.0, theta=math.pi / 2 - 0.1, omega=0.0))
    assert np.max(np.abs(r.y[5])) < 8.0  # omega stays bounded
    return abs(flow_state(0.0, r.y[:, 20], p).alpha)


def test_example_v2_flies_stable():
    """QA-8: discriminates the declared (restoring) `standard` table from the same table
    with the C_m convention flipped (anti-restoring): the former must pull the attitude
    offset back measurably faster (measured |alpha| 0.0088 vs 0.0132 rad, ratio 0.67)."""
    with open(os.path.join(_AERO_DIR, "example_v2.csv")) as f:
        text = f.read()
    assert "# cm_convention: standard" in text
    flipped = text.replace("# cm_convention: standard", "# cm_convention: code")
    with _table("zz_example_v2_flipped.csv", flipped) as name:
        a_flipped = _short_flight_alpha(name)
    a_stable = _short_flight_alpha("example_v2.csv")
    assert a_stable < 0.8 * a_flipped
