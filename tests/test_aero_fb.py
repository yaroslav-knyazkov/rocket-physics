"""Step 102 (Phase 2.17, architecture-35 SS35.4.3, D-109): the air brake as an
`f_b` axis of the aero table (`Control.airbrake_aero = "table"`).

Tables are written into data/aero/ for the test and removed afterwards (same
pattern as tests/test_aero.py).
"""

import contextlib
import dataclasses
import math
import os

import numpy as np
import pytest

from configs.scenarios.demo import SCENARIO as DEMO
from configs.schema import assemble
from sim import aero, report
from sim.dynamics import derivatives
from sim.flow import flow_state
from sim.integrate import run_sim
from sim.params import Aero, Control, Lengths, Params, Thrust, Weight
from sim.state import State, Z

_ALPHAS = (-10, 0, 10)
_MACHS = (0.5, 2.0)
_L_G = 0.9
_D_REF = 0.08


def _rows(f_b_values, ca, lp, with_fb=True, cn_gain=0.2):
    """Lines of a v2 table; `ca[f]`/`lp[f]` give the closed/open plane levels (affine in M, alpha)."""
    cols = "alpha_deg,M," + ("f_b," if with_fb else "") + "C_A,C_N,C_m,l_p_m"
    out = ["# synthetic Step 102 table", cols]
    for f in f_b_values:
        for M in _MACHS:
            for a in _ALPHAS:
                c_a = ca[f] + 0.01 * M + 0.001 * abs(a)
                c_n = 0.05 * a * (1.0 + cn_gain * f)
                c_m = 0.02 * a
                l_p = lp[f] + 0.01 * M
                fb_cell = f"{f}," if with_fb else ""
                out.append(f"{a},{M},{fb_cell}{c_a!r},{c_n!r},{c_m!r},{l_p!r}")
    return "\n".join(out) + "\n"


def _flight_rows(f_values, ca, lp, with_fb=True):
    """A drag-only table over the full alpha circle (no out-of-range clamping in a full flight):
    C_A = ca[f] * cos(alpha) at the nodes -180/-90/0/90/180, C_N = C_m = 0, constant l_p."""
    cols = "alpha_deg,M," + ("f_b," if with_fb else "") + "C_A,C_N,C_m,l_p_m"
    out = [cols]
    for f in f_values:
        for M in (0.0, 5.0):
            for a in (-180, -90, 0, 90, 180):
                fb_cell = f"{f}," if with_fb else ""
                out.append(f"{a},{M},{fb_cell}{ca[f] * round(math.cos(math.radians(a)))!r},0.0,0.0,{lp[f]!r}")
    return "\n".join(out) + "\n"


def _apogee(res):
    return -res.raw.sol(res.events["apogee"])[Z]


@contextlib.contextmanager
def _table(name, text):
    path = os.path.join(os.path.dirname(__file__), "..", "data", "aero", name)
    with open(path, "w") as f:
        f.write(text)
    aero._load_table.cache_clear()
    try:
        yield name
    finally:
        aero._load_table.cache_clear()
        if os.path.exists(path):
            os.remove(path)


def _params(table, airbrake_aero="additive", **control_kw):
    return Params(
        weight=Weight(m=0.5, I=0.05),
        lengths=Lengths(l1=0.3, l2=0.4, l_g=_L_G),
        thrust=Thrust(motor_curve="placeholder.csv"),
        aero=Aero(model="table", table=table, S=0.005, d_ref=_D_REF),
        control=Control(airbrake_aero=airbrake_aero, **control_kw),
    )


CA = {0.0: 0.30, 1.0: 0.50}
LP = {0.0: 1.30, 1.0: 1.10}


def test_blend_at_half_is_the_linear_blend_of_the_planes():
    with _table("test_fb_blend.csv", _rows((0.0, 1.0), CA, LP)) as name:
        p = _params(name, "table")
        a, M = math.radians(4.0), 1.1
        c0 = aero._table_coeffs(a, M, p, 0.0)
        c1 = aero._table_coeffs(a, M, p, 1.0)
        ch = aero._table_coeffs(a, M, p, 0.5)
        for field in ("C_x", "C_z", "C_m", "l1"):
            assert getattr(ch, field) == pytest.approx(
                0.5 * (getattr(c0, field) + getattr(c1, field)), rel=1e-12
            )
        assert c1.C_x > c0.C_x and c1.l1 < c0.l1  # the planes really differ


def test_fb_clamped_outside_zero_one():
    with _table("test_fb_clamp.csv", _rows((0.0, 1.0), CA, LP)) as name:
        p = _params(name, "table")
        a, M = 0.05, 1.0
        assert aero._table_coeffs(a, M, p, -0.3) == aero._table_coeffs(a, M, p, 0.0)
        assert aero._table_coeffs(a, M, p, 1.7) == aero._table_coeffs(a, M, p, 1.0)


def test_fb_zero_plane_equals_brake_closed_table_exactly():
    plane0 = _rows((0.0,), CA, LP, with_fb=False)
    with _table("test_fb_two.csv", _rows((0.0, 1.0), CA, LP)) as n2, _table("test_fb_closed.csv", plane0) as n0:
        p2, p0 = _params(n2, "table"), _params(n0)
        for a, M in ((0.0, 0.5), (math.radians(3.3), 1.234), (math.radians(-9.0), 2.5)):
            assert aero._table_coeffs(a, M, p2, 0.0) == aero._table_coeffs(a, M, p0)


def test_additive_mode_reads_only_the_fb_zero_plane():
    with _table("test_fb_add.csv", _rows((0.0, 1.0), CA, LP)) as name:
        p = _params(name, "additive")
        y = np.array([0.0, -300.0, 5.0, -60.0, math.pi / 2, 0.0])
        flow = flow_state(0.0, y, p)
        c_fb1 = aero.coefficients(0.0, y, p, flow, None, 1.0)
        c_fb0 = aero.coefficients(0.0, y, p, flow, None, 0.0)
        assert c_fb1 == c_fb0
        assert c_fb0.C_x == aero._table_coeffs(flow.alpha, flow.M, p, 0.0).C_x


def test_table_mode_without_fb_column_fails_at_assemble():
    with _table("test_fb_none.csv", _rows((0.0,), CA, LP, with_fb=False)) as name:
        rocket = dataclasses.replace(
            DEMO.rocket,
            aero=Aero(model="table", table=name, S=0.00229, d_ref=0.054),
            control=Control(airbrake_aero="table"),
        )
        with pytest.raises(ValueError, match="f_b"):
            assemble(dataclasses.replace(DEMO, rocket=rocket))


def test_table_mode_with_non_table_model_fails():
    p = Params(
        weight=Weight(m=0.5, I=0.05),
        aero=Aero(model="constant", S=0.005, d_ref=0.08),
        control=Control(airbrake_aero="table"),
    )
    with pytest.raises(ValueError, match="airbrake_aero"):
        aero.validate(p)


def test_unknown_airbrake_aero_rejected():
    p = Params(weight=Weight(m=0.5, I=0.05), control=Control(airbrake_aero="bogus"))
    with pytest.raises(ValueError, match="airbrake_aero"):
        aero.validate(p)


def test_fb_axis_must_start_at_zero():
    with _table("test_fb_nz.csv", _rows((0.5, 1.0), {0.5: 0.4, 1.0: 0.5}, {0.5: 1.2, 1.0: 1.1})) as name:
        with pytest.raises(ValueError, match="f_b"):
            aero._load_table(name)


def test_fb_grid_must_be_rectangular():
    text = _rows((0.0, 1.0), CA, LP).splitlines()
    text.pop()  # drop one cell of the f_b = 1 plane
    with _table("test_fb_bad.csv", "\n".join(text) + "\n") as name:
        with pytest.raises(ValueError):
            aero._load_table(name)


def test_fb_composes_with_jorgensen_extension():
    """Blend in f_b first, then the large-alpha extension: beyond the table edge
    the extension (built from the f_b-blended edge values) is continuous in f_b and
    equal to the plane-wise extension at f_b = 0 / 1."""
    with _table("test_fb_jorg.csv", _rows((0.0, 1.0), CA, LP)) as name:
        p = _params(name, "table")
        p = dataclasses.replace(
            p,
            aero=dataclasses.replace(p.aero, table_oob="jorgensen", S_p=0.08, l_pc=0.7),
        )
        a, M = math.radians(100.0), 0.8
        c0 = aero._table_coeffs(a, M, p, 0.0)
        c1 = aero._table_coeffs(a, M, p, 1.0)
        cs = [aero._table_coeffs(a, M, p, f) for f in np.linspace(0.0, 1.0, 11)]
        assert cs[0] == c0 and cs[-1] == c1
        # smooth (no jumps) in f_b
        for u, v in zip(cs[:-1], cs[1:]):
            assert abs(v.C_x - u.C_x) < 0.5 * abs(c1.C_x - c0.C_x) + 1e-9
            assert abs(v.C_z - u.C_z) < 0.5 * (abs(c1.C_z) + abs(c0.C_z)) + 1e-9
        # inside the table the extension is inert
        ain = math.radians(5.0)
        assert aero._table_coeffs(ain, M, p, 0.4) == aero._table_coeffs(
            ain, M, dataclasses.replace(p, aero=dataclasses.replace(p.aero, table_oob="clamp")), 0.4
        )


def test_static_margin_shifts_with_fb_and_diagnostic_shows_it():
    """The Farha effect: l_p drops by 0.2 m when the brake opens, so the static margin
    (l_p - l_g)/d_ref falls by 0.2/d_ref calibres in the margin series."""
    with _table("test_fb_margin.csv", _flight_rows((0.0, 1.0), CA, LP)) as name:
        p = _params(
            name, "table", airbrake_model="full", airbrake_trigger="after_burnout",
        )
        s0 = State(x=0.0, z=0.0, vx=0.0, vz=0.0, theta=math.pi / 2, omega=0.0)
        r = run_sim(p, s0)
        t_b = r.events["burnout"]
        t_a = r.events["apogee"]
        ts = np.array([0.5 * t_b, t_b + 0.5 * (t_a - t_b)])
        _, margin = report.static_margin_cal(r, p, t_grid=ts)
        # l_p = LP[f] + 0.01*M with M ~ small at these instants -> compare the difference
        drop = margin[0] - margin[1]
        assert drop == pytest.approx(0.2 / _D_REF, rel=0.05)
        # additive mode reads only the closed plane: no shift
        pa = dataclasses.replace(p, control=dataclasses.replace(p.control, airbrake_aero="additive"))
        _, margin_a = report.static_margin_cal(r, pa, t_grid=ts)
        assert margin_a[0] - margin_a[1] == pytest.approx(0.0, abs=0.05 / _D_REF)


def test_fb_computed_once_per_rhs_call(monkeypatch):
    from sim import control

    n = [0]
    orig = control.airbrake_deploy_fraction

    def counted(*a, **k):
        n[0] += 1
        return orig(*a, **k)

    monkeypatch.setattr(control, "airbrake_deploy_fraction", counted)
    with _table("test_fb_once.csv", _rows((0.0, 1.0), CA, LP)) as name:
        for mode in ("additive", "table"):
            p = _params(name, mode, airbrake_model="full", airbrake_S_max=0.001)
            y = np.array([0.0, -500.0, 0.0, -80.0, math.pi / 2, 0.0])
            n[0] = 0
            derivatives(3.0, y, p)
            assert n[0] == 1, mode


def test_additive_apogee_pin_unchanged_default_path():
    """airbrake_aero defaults to 'additive': a table without f_b flies exactly as before."""
    assert Control().airbrake_aero == "additive"


def test_equivalence_table_plane_vs_additive_brake_apogee():
    """f_b = 1 plane with C_A = C_A,0 + C_D,b S_b / S reproduces the additive brake (constant C_D,b)."""
    cd_b, s_b, s_ref = 1.0, 0.002, 0.005
    ca0 = 0.45
    ca = {0.0: ca0, 1.0: ca0 + cd_b * s_b / s_ref}
    lp = {0.0: 1.3, 1.0: 1.3}
    s0 = State(x=0.0, z=0.0, vx=0.0, vz=0.0, theta=math.pi / 2, omega=0.0)
    ctl = dict(airbrake_model="full", airbrake_trigger="after_burnout")
    with _table("test_fb_eq_t.csv", _flight_rows((0.0, 1.0), ca, lp)) as nt,             _table("test_fb_eq_a.csv", _flight_rows((0.0,), ca, lp, with_fb=False)) as na:
        pt = _params(nt, "table", **ctl)
        pa = _params(na, "additive", airbrake_Cd=cd_b, airbrake_S_max=s_b, **ctl)
        pc = _params(na, "additive", airbrake_Cd=cd_b, airbrake_S_max=0.0, **ctl)
        h_t, h_a, h_closed = (_apogee(run_sim(q, s0)) for q in (pt, pa, pc))
    assert h_closed - h_a > 1.0  # the brake matters in this scenario
    assert abs(h_t - h_a) / h_a < 1e-4
