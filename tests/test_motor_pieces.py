"""Tests for `Airframe`, `Sections`, `Motor` and `_weight_from_pieces`
(Phase 2.16, Step 78, dev/docs/architecture-32-motor-separation.md SS32.2,
SS32.3).

Nothing is wired up here, by design (the same pattern Step 71 used for
`Rocket`/`LaunchSite`/`Weather`/`Scenario`): these types and this
function exist and are exercised standalone. `Rocket`, `Scenario` and
`assemble` are untouched -- Step 80 is the actual switch-over.

Covers SS32.3.3's gate in full: bit-for-bit pass-through (F4), a
hand-built two-lump composition, the SS32.3.5 exact endpoint inversion
(round-tripped), the real `Cesaroni_2060K570-17A.eng` fixture under
`mass_model="endpoints"` (SS32.3.1 F5's measured figures), the "isp"
model passing an explicit `I_sp` straight through, header-field
resolution and override precedence, the geometry defaults (half-length
centroids, uniform-cylinder inertia), `l_motor_fwd`/`l_motor_aft`
equivalence, both placement/precondition error messages, the three new
dataclasses being frozen, and that `import configs` still performs no
filesystem access (D-70) -- every currently-registered scenario stays on
the `mass_model="none"` pass-through path.
"""

from __future__ import annotations

import dataclasses
import math
import sys

import pytest

import sim.mass as mass
import sim.motor_file as motor_file
from configs.schema import Airframe, Motor, Sections, _weight_from_pieces
from sim.params import Thrust

G0 = 9.80665
_K570 = "Cesaroni_2060K570-17A.eng"  # data/motors/ -- SS32.3.1 F5's fixture


def _decompose_dry(airframe: Airframe, w) -> tuple[float, float, float]:
    """Invert the (airframe, casing) `combine()` to recover the casing's
    own GLOBAL (nose-tip) position and inertia from the composed
    `Weight` -- pure mass-weighted-centroid + parallel-axis algebra run
    backwards. `Weight` does not expose the casing lump directly, so
    several tests below use this to check internals through the public
    surface only."""
    m_c = w.m_d - airframe.m
    l_c = (w.l_d * w.m_d - airframe.m * airframe.l) / m_c
    I_c = w.I_d - airframe.I - airframe.m * (w.l_d - airframe.l) ** 2 - m_c * (w.l_d - l_c) ** 2
    return m_c, l_c, I_c


# ----------------------------------------------------------------------
# Pass-through (F4) -- case (0)
# ----------------------------------------------------------------------


def test_pass_through_is_bitwise():
    airframe = Airframe(m=1.5, I=0.08)
    w = _weight_from_pieces(airframe, Sections(), Motor(name="m"), G0)

    assert w.m_d is None
    # bit-identical, not merely close -- F4 is exactly why this must be an
    # explicit early return rather than combine() of one lump
    assert w.m is airframe.m
    assert w.I is airframe.I
    assert w.m == airframe.m
    assert w.I == airframe.I


# ----------------------------------------------------------------------
# A hand-built two-lump composition ("isp" model, explicit round numbers)
# ----------------------------------------------------------------------


def test_hand_built_two_lump_composition_matches_hand_computed_parallel_axis():
    airframe = Airframe(m=1.2, I=0.03, l=0.3)
    sections = Sections(l_motor_fwd=0.5)
    motor = Motor(
        name="hand",
        thrust=Thrust(motor_curve=_K570),  # not touched -- mass_model="isp", every field explicit
        mass_model="isp",
        I_sp=180.0,
        m_total=1.0,
        m_prop=0.4,
        length=0.5,
        diameter=0.05,
        l_case=0.2,
        l_prop=0.3,
        I_case=0.002,
        I_prop0=0.001,
    )

    w = _weight_from_pieces(airframe, sections, motor, G0)

    # hand computation, SS32.3.1 F2's two-step reduction, spelled out
    m_c = motor.m_total - motor.m_prop  # 0.6
    l_c_global = sections.l_motor_fwd + motor.l_case  # 0.7
    l_p_global = sections.l_motor_fwd + motor.l_prop  # 0.8

    M_d = airframe.m + m_c
    L_d = (airframe.m * airframe.l + m_c * l_c_global) / M_d
    I_D = airframe.I + airframe.m * (L_d - airframe.l) ** 2 + motor.I_case + m_c * (L_d - l_c_global) ** 2

    m_wet = M_d + motor.m_prop
    l_B = (M_d * L_d + motor.m_prop * l_p_global) / m_wet
    I_wet = I_D + M_d * (l_B - L_d) ** 2 + motor.I_prop0 + motor.m_prop * (l_B - l_p_global) ** 2

    assert w.m == pytest.approx(m_wet, rel=1e-12)
    assert w.I == pytest.approx(I_wet, rel=1e-12)
    assert w.m_d == pytest.approx(M_d, rel=1e-12)
    assert w.l_d == pytest.approx(L_d, rel=1e-12)
    assert w.I_d == pytest.approx(I_D, rel=1e-12)
    assert w.l_p == pytest.approx(l_p_global, rel=1e-12)
    assert w.I_sp == 180.0  # "isp" -- straight through, no impulse computation
    assert w.I_p_spec == pytest.approx(motor.I_prop0 / motor.m_prop, rel=1e-12)


# ----------------------------------------------------------------------
# The exact endpoint inversion (SS32.3.5), round-tripped
# ----------------------------------------------------------------------


def test_exact_inversion_round_trip_recovers_l_cog_0_and_I_0():
    """Build a `Motor` from `(l_cog_0, l_cog_f, I_0, I_f)` instead of
    `(l_prop, I_prop0)` directly, run the composition, and recover
    `l_cog_0`/`I_0` from the resulting `Weight` at `m_p = m_prop` (t=0,
    propellant fully loaded) -- proving the chart change (SS32.3.5) is
    lossless. Figures below are hand-derived (mass-weighted centroid +
    parallel axis) from motor-local casing (m_c=0.7, l_c=0.3, I_c=0.01)
    and propellant (m_p0=0.9, l_prop=0.2, I_prop0=0.02):
        l_cog_0 = (0.7*0.3 + 0.9*0.2) / 1.6 = 0.24375
        l_cog_f = 0.3
        I_0 = 0.01 + 0.7*(0.24375-0.3)**2 + 0.02 + 0.9*(0.24375-0.2)**2 = 0.033937499999999995
        I_f = 0.01
    """
    airframe = Airframe(m=2.0, I=0.3, l=0.4)
    sections = Sections(l_motor_fwd=0.6)
    motor = Motor(
        name="endpoint_param",
        thrust=Thrust(motor_curve=_K570),  # not touched -- mass_model="isp", masses given explicitly
        mass_model="isp",
        I_sp=200.0,
        m_total=1.6,
        m_prop=0.9,
        l_cog_0=0.24375,
        l_cog_f=0.3,
        I_0=0.033937499999999995,
        I_f=0.01,
    )

    w = _weight_from_pieces(airframe, sections, motor, G0)

    l_fwd = sections.l_motor_fwd
    m_c, l_c_global, I_c_global = _decompose_dry(airframe, w)
    l_prop_global = w.l_p
    I_prop0_global = w.I_p_spec * motor.m_prop

    l_cog_0_global = (m_c * l_c_global + motor.m_prop * l_prop_global) / motor.m_total
    recovered_l_cog_0 = l_cog_0_global - l_fwd
    recovered_l_cog_f = l_c_global - l_fwd
    recovered_I_0 = (
        I_c_global
        + m_c * (l_cog_0_global - l_c_global) ** 2
        + I_prop0_global
        + motor.m_prop * (l_cog_0_global - l_prop_global) ** 2
    )
    recovered_I_f = I_c_global

    assert recovered_l_cog_0 == pytest.approx(motor.l_cog_0, rel=1e-12)
    assert recovered_l_cog_f == pytest.approx(motor.l_cog_f, rel=1e-12)
    assert recovered_I_0 == pytest.approx(motor.I_0, rel=1e-12)
    assert recovered_I_f == pytest.approx(motor.I_f, rel=1e-12)


# ----------------------------------------------------------------------
# The real Cesaroni_2060K570-17A.eng fixture, mass_model="endpoints"
# ----------------------------------------------------------------------


def test_endpoints_mass_model_real_k570_file_matches_measured_figures():
    """SS32.3.1 F5's measured figures: J=2062.223 N*s (the (0,0)-prepend
    reading), m_prop=0.990 kg -> I_sp_eff=212.4123 s; m_total=1.685 kg,
    m_f=0.695 kg. `Airframe(m=1.0, I=0.05, l=0.5)` / `Sections
    (l_motor_aft=1.0)` are round numbers chosen so the motor's own length
    (0.488 m, from the header) is what resolves the forward face."""
    airframe = Airframe(m=1.0, I=0.05, l=0.5)
    sections = Sections(l_motor_aft=1.0)
    motor = Motor(
        name="k570",
        thrust=Thrust(motor_curve=_K570),
        mass_model="endpoints",
        # every mass/geometry field left None -- all come from the header
    )

    w = _weight_from_pieces(airframe, sections, motor, G0)

    assert w.I_sp == pytest.approx(212.4123, abs=1e-3)
    assert w.m == pytest.approx(airframe.m + 1.685, abs=1e-6)
    assert w.m_d == pytest.approx(airframe.m + 0.695, abs=1e-6)


# ----------------------------------------------------------------------
# "isp" passes an explicit I_sp straight through, no impulse computation
# ----------------------------------------------------------------------


def test_isp_mass_model_explicit_I_sp_wins_no_impulse_computation(monkeypatch):
    def _boom(*args, **kwargs):
        raise AssertionError("isp_from_impulse must not be called for mass_model='isp'")

    monkeypatch.setattr(mass, "isp_from_impulse", _boom)

    airframe = Airframe(m=1.0, I=0.02, l=0.2)
    sections = Sections(l_motor_fwd=0.1)
    motor = Motor(
        name="isp_test",
        thrust=Thrust(motor_curve=_K570),
        mass_model="isp",
        I_sp=190.0,
        m_total=1.5,
        m_prop=0.6,
        length=0.4,
        diameter=0.06,
    )

    w = _weight_from_pieces(airframe, sections, motor, G0)
    assert w.I_sp == 190.0


# ----------------------------------------------------------------------
# Header fields filled from the file; explicit Motor fields override it
# ----------------------------------------------------------------------


def test_header_fields_left_none_are_filled_from_the_file():
    airframe = Airframe(m=1.0, I=0.05, l=0.5)
    sections = Sections(l_motor_aft=1.0)
    motor = Motor(name="k570_plain", thrust=Thrust(motor_curve=_K570), mass_model="endpoints")

    w = _weight_from_pieces(airframe, sections, motor, G0)

    # m_total/m_prop both came from the header (1.685, 0.99) -- same
    # figures as the dedicated fixture test above
    assert w.m == pytest.approx(airframe.m + 1.685, abs=1e-6)
    assert w.m_d == pytest.approx(airframe.m + 0.695, abs=1e-6)


def test_explicit_m_prop_overrides_the_file_m_total_still_comes_from_file():
    airframe = Airframe(m=1.0, I=0.05, l=0.5)
    sections = Sections(l_motor_aft=1.0)
    motor = Motor(name="override_mprop", thrust=Thrust(motor_curve=_K570), mass_model="endpoints", m_prop=0.5)

    w = _weight_from_pieces(airframe, sections, motor, G0)

    # m_total still the file's 1.685 kg -- unaffected by the m_prop
    # override, because m = airframe.m + m_total regardless of split
    assert w.m == pytest.approx(airframe.m + 1.685, abs=1e-6)
    # but m_d/I_sp DO change: m_c = m_total(file) - m_prop(explicit)
    assert w.m_d == pytest.approx(airframe.m + (1.685 - 0.5), abs=1e-6)
    expected_I_sp = mass.isp_from_impulse(motor_file.load(_K570).total_impulse, 0.5, G0)
    assert w.I_sp == pytest.approx(expected_I_sp, rel=1e-9)
    assert w.I_sp != pytest.approx(212.4123, abs=1e-3)  # not the file's own m_prop figure


def test_explicit_m_total_overrides_the_file_m_prop_still_comes_from_file():
    airframe = Airframe(m=1.0, I=0.05, l=0.5)
    sections = Sections(l_motor_aft=1.0)
    motor = Motor(name="override_mtotal", thrust=Thrust(motor_curve=_K570), mass_model="endpoints", m_total=2.0)

    w = _weight_from_pieces(airframe, sections, motor, G0)

    assert w.m == pytest.approx(airframe.m + 2.0, abs=1e-6)
    assert w.m_d == pytest.approx(airframe.m + (2.0 - 0.99), abs=1e-6)  # m_prop still the file's 0.99 kg
    # m_prop unaffected by the m_total override -> I_sp unaffected too
    assert w.I_sp == pytest.approx(212.4123, abs=1e-3)


# ----------------------------------------------------------------------
# Geometry defaults: half-length centroids, uniform-cylinder inertia
# ----------------------------------------------------------------------


def test_geometry_left_none_defaults_to_half_length_and_uniform_cylinder():
    airframe = Airframe(m=1.0, I=0.02, l=0.2)
    sections = Sections(l_motor_fwd=0.0)  # l_fwd=0 -> motor-local == global
    motor = Motor(
        name="geom_defaults",
        thrust=Thrust(motor_curve=_K570),
        mass_model="isp",
        I_sp=200.0,
        m_total=1.5,
        m_prop=0.6,
        length=0.4,
        diameter=0.06,
        # l_case/l_prop/I_case/I_prop0 all left None
    )

    w = _weight_from_pieces(airframe, sections, motor, G0)
    m_c, l_c_global, I_c_global = _decompose_dry(airframe, w)

    assert l_c_global == pytest.approx(motor.length / 2.0, rel=1e-12)
    assert w.l_p == pytest.approx(motor.length / 2.0, rel=1e-12)
    assert I_c_global == pytest.approx(mass.uniform_cylinder_I(m_c, motor.length, motor.diameter), rel=1e-12)
    recovered_I_prop0 = w.I_p_spec * motor.m_prop
    assert recovered_I_prop0 == pytest.approx(
        mass.uniform_cylinder_I(motor.m_prop, motor.length, motor.diameter), rel=1e-12
    )


# ----------------------------------------------------------------------
# l_motor_fwd / l_motor_aft equivalence
# ----------------------------------------------------------------------


def test_l_motor_aft_places_motor_identically_to_equivalent_l_motor_fwd():
    airframe = Airframe(m=1.0, I=0.02, l=0.2)
    motor = Motor(
        name="aft_vs_fwd",
        thrust=Thrust(motor_curve=_K570),
        mass_model="isp",
        I_sp=200.0,
        m_total=1.5,
        m_prop=0.6,
        length=0.4,
        diameter=0.06,
    )

    w_fwd = _weight_from_pieces(airframe, Sections(l_motor_fwd=0.7), motor, G0)
    w_aft = _weight_from_pieces(airframe, Sections(l_motor_aft=0.7 + motor.length), motor, G0)

    for field in ("m", "I", "m_d", "l_d", "I_d", "l_p", "I_sp", "I_p_spec"):
        assert math.isclose(getattr(w_fwd, field), getattr(w_aft, field), rel_tol=1e-12)


# ----------------------------------------------------------------------
# The two preconditions raise, naming the field(s)
# ----------------------------------------------------------------------


def _mass_modelled_motor() -> Motor:
    return Motor(
        name="precondition_motor",
        thrust=Thrust(motor_curve=_K570),
        mass_model="isp",
        I_sp=200.0,
        m_total=1.5,
        m_prop=0.6,
        length=0.4,
        diameter=0.06,
    )


def test_neither_l_motor_fwd_nor_aft_given_raises_naming_both_fields():
    airframe = Airframe(m=1.0, I=0.02, l=0.2)
    with pytest.raises(ValueError) as exc:
        _weight_from_pieces(airframe, Sections(), _mass_modelled_motor(), G0)
    assert "l_motor_fwd" in str(exc.value)
    assert "l_motor_aft" in str(exc.value)


def test_both_l_motor_fwd_and_aft_given_raises_naming_both_fields():
    airframe = Airframe(m=1.0, I=0.02, l=0.2)
    sections = Sections(l_motor_fwd=0.1, l_motor_aft=0.6)
    with pytest.raises(ValueError) as exc:
        _weight_from_pieces(airframe, sections, _mass_modelled_motor(), G0)
    assert "l_motor_fwd" in str(exc.value)
    assert "l_motor_aft" in str(exc.value)


def test_airframe_l_none_raises_naming_the_field():
    airframe = Airframe(m=1.0, I=0.02)  # l left None
    sections = Sections(l_motor_fwd=0.1)
    with pytest.raises(ValueError) as exc:
        _weight_from_pieces(airframe, sections, _mass_modelled_motor(), G0)
    assert "airframe.l" in str(exc.value)


# ----------------------------------------------------------------------
# All three new dataclasses are frozen
# ----------------------------------------------------------------------


def test_airframe_is_frozen():
    a = Airframe(m=1.0, I=0.01)
    with pytest.raises(dataclasses.FrozenInstanceError):
        a.m = 2.0


def test_sections_is_frozen():
    s = Sections()
    with pytest.raises(dataclasses.FrozenInstanceError):
        s.L_total = 1.0


def test_motor_is_frozen():
    m = Motor(name="x")
    with pytest.raises(dataclasses.FrozenInstanceError):
        m.name = "y"


# ----------------------------------------------------------------------
# import configs performs NO filesystem access (D-70)
# ----------------------------------------------------------------------


def test_import_configs_performs_no_filesystem_access(monkeypatch):
    """Every currently-registered scenario stays on `mass_model="none"`'s
    pass-through path (case 0), which never reaches `sim.motor_file` --
    so patching `load`/`records` to blow up and re-importing the whole
    `configs` package tree from scratch must not trip them."""

    def _boom(*args, **kwargs):
        raise AssertionError("sim.motor_file touched during configs import")

    monkeypatch.setattr(motor_file, "load", _boom)
    monkeypatch.setattr(motor_file, "records", _boom)

    for name in list(sys.modules):
        if name == "configs" or name.startswith("configs."):
            del sys.modules[name]

    import configs as fresh_configs

    assert set(fresh_configs.names()) == {
        "demo_75mm",
        "demo_75mm_airbrake",
        "demo_75mm_highland",
        "toy_05kg",
    }
    for name in fresh_configs.names():
        fresh_configs.get(name)  # exercises assemble() for every registered scenario/config


def test_configs_names_unchanged_nothing_wired_up_yet():
    """SS32.1: this step adds types and a function, nothing is wired up --
    the registry is exactly Step 74's four names."""
    import configs

    assert set(configs.names()) == {
        "demo_75mm",
        "demo_75mm_airbrake",
        "demo_75mm_highland",
        "toy_05kg",
    }
