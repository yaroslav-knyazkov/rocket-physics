"""Step 112 (Phase 2.17, D-120): large-alpha (Jorgensen) extension of the table
aero, opt-in via `Aero.table_oob = "jorgensen"`. Root cause and motivation:
dev/docs/diagnosis-rk45-v2-table.md (clamped C_N/C_m flip sign at alpha ~ 180 deg
-> sliding mode -> RK45 step collapse)."""

import dataclasses
import warnings

import numpy as np
import pytest

from configs.scenarios.demo import SCENARIO as DEMO
from configs.schema import assemble
from sim import aero, integrate
from sim.aero import AeroRangeWarning
from sim.integrate import run_sim
from sim.params import Aero, Recovery, Solver
from tests.test_scenario_sweep import LARGE

S_REF = 0.00229
D_REF = 0.054
S_P = 0.08
L_PC = 0.7
EVAL_CAP = 50_000
EVAL_CEILING = 20_000  # ticket: monkeypatched taper needed 2480, constant aero 1052


def _aero(**kw) -> Aero:
    base = dict(model="table", S=S_REF, d_ref=D_REF, table="example_v2.csv")
    base.update(kw)
    return Aero(**base)


def _jorg(**kw) -> Aero:
    return _aero(table_oob="jorgensen", S_p=S_P, l_pc=L_PC, **kw)


def _cfg(aero_group, *, t_max=200.0, chute=True, method="RK45"):
    rocket = dataclasses.replace(DEMO.rocket, aero=aero_group)
    if not chute:
        rocket = dataclasses.replace(rocket, recovery=Recovery(model="none"))
    scn = dataclasses.replace(DEMO, rocket=rocket, motor=LARGE, solver=Solver(method=method, t_max=t_max, dt=0.005))
    return assemble(scn)


def _params(aero_group):
    return _cfg(aero_group, t_max=20.0).params


def _flight(aero_group, **kw):
    cfg = _cfg(aero_group, **kw)
    n = [0]
    orig = integrate.derivatives

    def counted(*a, **k):
        n[0] += 1
        if n[0] > EVAL_CAP:
            raise RuntimeError(f"RHS evaluation cap {EVAL_CAP} exceeded (stall)")
        return orig(*a, **k)

    integrate.derivatives = counted
    try:
        res = run_sim(cfg.params, cfg.s0)
    finally:
        integrate.derivatives = orig
    return res, n[0]


# ----------------------------------------------------------------------
# 1. full flights under RK45
# ----------------------------------------------------------------------


@pytest.mark.parametrize("chute", [False, True])
def test_rk45_full_flight_reaches_ground_with_jorgensen(chute):
    res, nfev = _flight(_jorg(), chute=chute, t_max=400.0)  # canopy descent from ~1.2 km takes > 200 s
    assert res.events.get("ground") is not None
    assert nfev < EVAL_CEILING


# ----------------------------------------------------------------------
# 2. ascent equals clamp
# ----------------------------------------------------------------------


def test_ascent_matches_clamp():
    # Not bit-identical: on the pad the air-relative speed is ~1e-7 m/s and alpha = atan2(w, u)
    # is noise (often +-180 deg), so the first steps do leave the table. The flight itself agrees.
    ca, cb = _cfg(_aero(), t_max=15.0), _cfg(_jorg(), t_max=15.0)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", AeroRangeWarning)
        a = run_sim(ca.params, ca.s0)
    b = run_sim(cb.params, cb.s0)
    assert b.y[1, -1] == pytest.approx(a.y[1, -1], rel=1e-5)
    assert b.y[3, -1] == pytest.approx(a.y[3, -1], rel=1e-5)


# ----------------------------------------------------------------------
# helpers for coefficient-level tests
# ----------------------------------------------------------------------


def _coef(alpha, M, p):
    c = aero._table_coeffs(alpha, M, p)
    return np.array([c.C_x, c.C_z, c.C_m])


MACHS = [0.3, 0.8, 1.5]


@pytest.fixture(scope="module")
def pj():
    return _params(_jorg())


@pytest.fixture(scope="module")
def pc():
    return _params(_aero())


# ----------------------------------------------------------------------
# 3. continuity
# ----------------------------------------------------------------------


@pytest.mark.parametrize("M", MACHS)
def test_continuity_at_key_angles(pj, M):
    a_e = np.radians(10.0)
    delta = np.radians(pj.aero.oob_blend_deg)
    eps = 1e-7
    for a in [np.pi, np.pi / 2, a_e, a_e + delta]:
        for s in (+1.0, -1.0):
            x = s * a
            if abs(x) > np.pi - 2 * eps:
                lo, hi = x - s * eps, x - s * 2 * eps  # stay on this side of the wrap
                d = np.abs(_coef(lo, M, pj) - _coef(hi, M, pj))
            else:
                d = np.abs(_coef(x + eps, M, pj) - _coef(x, M, pj))
            assert np.all(d <= 400 * eps), (x, d)  # C_m slope at band end ~ 210/rad for this S_p/S


@pytest.mark.parametrize("M", MACHS)
def test_dense_scan_slope_bounded(pj, M):
    deg = np.arange(-17999, 18001) * 0.01
    vals = np.array([_coef(np.radians(a), M, pj) for a in deg])
    slope = np.abs(np.diff(vals, axis=0)) / np.radians(0.01)
    # C_z crossflow scale: eta*C_dn*S_p/S ~ 40 => max slope ~ 2x that
    assert slope[:, 0].max() < 20.0
    assert slope[:, 1].max() < 200.0
    assert slope[:, 2].max() < 400.0


@pytest.mark.parametrize("M", MACHS)
def test_tail_first_crossing_is_odd_and_vanishing(pj, M):
    prev = None
    for e_deg in (1.0, 0.1, 0.01, 1e-4):
        e = np.radians(e_deg)
        up = _coef(np.pi - e, M, pj)       # alpha just below +180
        dn = _coef(-np.pi + e, M, pj)      # alpha just above -180
        assert up[1] == pytest.approx(-dn[1], rel=1e-12, abs=1e-15)
        assert up[2] == pytest.approx(-dn[2], rel=1e-12, abs=1e-15)
        assert up[1] > 0.0
        mag = abs(up[1]) + abs(up[2])
        if prev is not None:
            assert mag < prev
        prev = mag
    assert prev < 1e-6
    # both sides of the wrap agree at exactly 180 deg
    assert np.allclose(_coef(np.pi, M, pj)[1:], 0.0, atol=1e-9)


# ----------------------------------------------------------------------
# 4. inside the table: jorgensen == clamp bitwise
# ----------------------------------------------------------------------


@pytest.mark.parametrize("M", MACHS)
def test_inside_table_bitwise_equal_to_clamp(pj, pc, M):
    for deg in np.linspace(-10.0, 10.0, 41):
        a = float(np.radians(deg))
        cj = aero._table_coeffs(a, M, pj)
        cc = aero._table_coeffs(a, M, pc)
        assert tuple(cj) == tuple(cc)


# ----------------------------------------------------------------------
# 5. symmetry in the extended region
# ----------------------------------------------------------------------


@pytest.mark.parametrize("M", MACHS)
def test_symmetry_extended_region(pj, M):
    for deg in np.arange(10.5, 180.0, 3.7):
        a = float(np.radians(deg))
        p_ = _coef(a, M, pj)
        n_ = _coef(-a, M, pj)
        assert n_[0] == pytest.approx(p_[0], abs=1e-12)
        assert n_[1] == pytest.approx(-p_[1], abs=1e-12)
        assert n_[2] == pytest.approx(-p_[2], abs=1e-12)


# ----------------------------------------------------------------------
# 6. analytic spot checks
# ----------------------------------------------------------------------


def test_analytic_at_90_deg(pj):
    M = 0.8
    eta = float(np.interp(S_P / D_REF**2, aero._ETA_LAM, aero._ETA_VAL))
    c = aero._table_coeffs(np.pi / 2, M, pj)
    assert c.C_x == pytest.approx(0.0, abs=1e-12)
    assert c.C_z == pytest.approx(eta * 1.2 * S_P / S_REF, rel=1e-12, abs=1e-9)


def test_analytic_axial_at_180_default_and_explicit():
    M = 0.8
    p_def = _params(_jorg())
    table = aero._load_table("example_v2.csv")
    x0 = aero._table_lookup(table, 0.0, M, table.C_A)
    assert aero._table_coeffs(np.pi, M, p_def).C_x == pytest.approx(-x0, rel=1e-12)
    p_exp = _params(_jorg(C_x180=1.1))
    assert aero._table_coeffs(np.pi, M, p_exp).C_x == pytest.approx(-1.1, rel=1e-12)


def test_moment_arm_correction(pj):
    M, a = 0.8, np.radians(60.0)
    table = aero._load_table("example_v2.csv")
    a_e = table.alpha[-1]
    lp_e = aero._table_lookup(table, a_e, M, table.l_p)
    cm_e = aero._table_lookup(table, a_e, M, table.C_m)
    eta = float(np.interp(S_P / D_REF**2, aero._ETA_LAM, aero._ETA_VAL))
    c_zcf = eta * 1.2 * (S_P / S_REF) * np.sin(a) * abs(np.sin(a))
    z = lambda x: np.sin(2 * x) * np.cos(x / 2)  # noqa: E731
    expect = cm_e * z(a) / z(a_e) + (L_PC - lp_e) * c_zcf / D_REF
    assert aero._table_coeffs(a, M, pj).C_m == pytest.approx(expect, rel=1e-12)


def test_eta_table_matches_research_note():
    """Step 115 (conventions audit §9.1, QA-9): `_ETA_LAM`/`_ETA_VAL` are a
    third-party hand digitisation of Jorgensen TR R-474 Fig. 4 (circular
    cylinder, Re_n = 88,000; HPR Sim crate `hpr_aero::crossflow`),
    transcribed in dev/docs/latex/research/jorgensen-params-findings.md §1.
    Every existing test rebuilds `eta` FROM `_ETA_LAM`/`_ETA_VAL`, so an
    accidental table edit would otherwise pass silently -- pin the 10
    `(L/d, eta)` points the code actually carries against that same 10-point
    subset of the research note's 12-point transcription (the note also has
    L/d = 25 -> 0.775 and L/d = 35 -> 0.805, which `_ETA_LAM`/`_ETA_VAL` do
    not include; this test does not newly introduce those two points, only
    pins the ones that already exist in the code), plus the note's own
    cross-check against Jorgensen's primary-source Fig. 6 (M_n = 0 start
    values "about 0.68 and 0.70" at L/d 10/12, matching the digitised
    0.685/0.701)."""
    lam_note_subset = np.array([2.0, 4.0, 6.0, 8.0, 10.0, 12.0, 15.0, 20.0, 30.0, 40.0])
    eta_note_subset = np.array([0.577, 0.607, 0.643, 0.668, 0.685, 0.701, 0.724, 0.753, 0.795, 0.815])
    assert aero._ETA_LAM == pytest.approx(lam_note_subset, abs=1e-9)
    assert aero._ETA_VAL == pytest.approx(eta_note_subset, abs=1e-9)

    eta_10 = float(np.interp(10.0, aero._ETA_LAM, aero._ETA_VAL))
    eta_12 = float(np.interp(12.0, aero._ETA_LAM, aero._ETA_VAL))
    assert eta_10 == pytest.approx(0.68, abs=0.01)
    assert eta_12 == pytest.approx(0.70, abs=0.01)


def test_explicit_eta_and_s_base_are_used():
    M, a = 0.8, np.radians(90.0)
    p = _params(_jorg(eta=0.5, S_base=2 * S_REF))
    c = aero._table_coeffs(a, M, p)
    assert c.C_z == pytest.approx(0.5 * 1.2 * S_P / S_REF, rel=1e-12, abs=1e-9)
    a2 = np.radians(45.0)
    c2 = aero._table_coeffs(a2, M, p)
    pot = 2.0 * np.sin(2 * a2) * np.cos(a2 / 2)
    cf = 0.5 * 1.2 * (S_P / S_REF) * np.sin(a2) ** 2
    assert c2.C_z == pytest.approx(pot + cf, rel=1e-12)


# ----------------------------------------------------------------------
# 7. default clamp is the legacy expression
# ----------------------------------------------------------------------


@pytest.mark.parametrize("deg", [-170.0, -30.0, -10.0, 0.0, 4.0, 10.0, 11.0, 90.0, 180.0])
def test_clamp_default_equals_legacy_expression(pc, deg):
    a, M = float(np.radians(deg)), 0.8
    assert pc.aero.table_oob == "clamp"
    t = aero._load_table(pc.aero.table)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", AeroRangeWarning)
        c = aero._table_coeffs(a, M, pc)
    assert c.C_x == aero._table_lookup(t, a, M, t.C_A) * aero._table_axial_factor(t, a)
    assert c.C_z == aero._table_lookup(t, a, M, t.C_N)
    assert c.C_m == aero._table_lookup(t, a, M, t.C_m)
    assert c.l1 == aero._table_lookup(t, a, M, t.l_p)


# ----------------------------------------------------------------------
# 8. clamp-mode warning
# ----------------------------------------------------------------------


def _count_range_warnings(fn):
    with warnings.catch_warnings(record=True) as rec:
        warnings.simplefilter("always")
        fn()
    return [w for w in rec if issubclass(w.category, AeroRangeWarning)]


def test_clamp_warns_once_per_run(pc):
    aero.reset_oob_warning()

    def calls():
        for _ in range(3):
            aero._table_coeffs(np.radians(100.0), 0.8, pc)

    w = _count_range_warnings(calls)
    assert len(w) == 1
    msg = str(w[0].message)
    assert "example_v2.csv" in msg and "jorgensen" in msg
    # in range: silent, even after reset
    aero.reset_oob_warning()
    assert _count_range_warnings(lambda: aero._table_coeffs(np.radians(5.0), 0.8, pc)) == []


def test_jorgensen_is_silent(pj):
    aero.reset_oob_warning()
    assert _count_range_warnings(lambda: aero._table_coeffs(np.radians(100.0), 0.8, pj)) == []


def test_run_sim_resets_warning_state():
    aero.reset_oob_warning()
    pc_ = _params(_aero())
    cfg = _cfg(_jorg(), t_max=1.0, method="rk4")  # jorgensen: the run itself never arms the flag
    assert len(_count_range_warnings(lambda: aero._table_coeffs(np.radians(100.0), 0.8, pc_))) == 1
    assert _count_range_warnings(lambda: aero._table_coeffs(np.radians(100.0), 0.8, pc_)) == []
    run_sim(cfg.params, cfg.s0)  # run_sim entry re-arms it
    assert len(_count_range_warnings(lambda: aero._table_coeffs(np.radians(100.0), 0.8, pc_))) == 1


# ----------------------------------------------------------------------
# 9. validate
# ----------------------------------------------------------------------


def _expect_invalid(**kw):
    with pytest.raises(ValueError):
        aero.validate(_params(_jorg(**kw)))


def test_validate_accepts_good_jorgensen(pj):
    aero.validate(pj)


def test_validate_rules():
    with pytest.raises(ValueError):
        aero.validate(_params(_aero(table_oob="nonsense")))
    for kw in (
        dict(oob_blend_deg=0.0),
        dict(C_dn=-0.1),
        dict(eta=1.5),
        dict(eta=-0.1),
        dict(C_x180=-1.0),
        dict(S_base=-1.0),
    ):
        _expect_invalid(**kw)
    with pytest.raises(ValueError):  # S_p required
        aero.validate(_params(_aero(table_oob="jorgensen", l_pc=L_PC)))
    with pytest.raises(ValueError):  # l_pc required
        aero.validate(_params(_aero(table_oob="jorgensen", S_p=S_P)))


def test_validate_jorgensen_needs_table_model():
    with pytest.raises(ValueError):
        _params(Aero(model="constant", S=S_REF, d_ref=D_REF, table_oob="jorgensen", S_p=S_P, l_pc=L_PC))


def test_validate_rejects_legacy_arm_table():
    with pytest.raises(ValueError):
        _params(_jorg(table="example.csv"))


def test_validate_rejects_one_sided_and_wide_tables():
    from tests.test_scenario_sweep import _temp_table

    one_sided = (
        "alpha_deg,M,C_A,C_N,C_m,l_p_m\n"
        "0,0.5,0.3,0.0,0.0,1.2\n10,0.5,0.35,0.5,-0.08,1.2\n"
    )
    wide = (
        "alpha_deg,M,C_A,C_N,C_m,l_p_m\n"
        "-85,0.5,0.3,-1.0,0.1,1.2\n0,0.5,0.3,0.0,0.0,1.2\n85,0.5,0.3,1.0,-0.1,1.2\n"
    )
    for name, text in (("test_oob_onesided.csv", one_sided), ("test_oob_wide.csv", wide)):
        with _temp_table(name, text):
            with pytest.raises(ValueError):
                _params(_jorg(table=name))
