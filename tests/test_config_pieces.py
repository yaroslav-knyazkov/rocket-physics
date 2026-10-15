"""Tests for the four piece types and `assemble` (Step 71, roadmap.md,
`dev/docs/architecture-31-config-separation.md` SS31.4/SS31.8).

Per SS31.8 #1 and #4: the structural one-owner guard for `assemble`'s
`Params(...)` call (implemented both behaviorally -- assembling
non-default pieces leaves no group at its default -- and directly, by
inspecting `assemble`'s own source for the keyword set of that call),
the override-ordering regression test (SS31.4's "overrides before s0"
rule, F5/D-51), the F6 measurement that a 90-degree rail derives exactly
`math.pi / 2`, an explicit `s0` passed through untouched, `Scenario.config`
carrying the scenario's own `name`/`notes`, and all four new dataclasses
being frozen.

Nothing here touches `configs/__init__.py` or the registry -- these
pieces are not wired up to anything yet, by design (Step 72).
"""

import ast
import dataclasses
import inspect
import math
import textwrap

import pytest

from configs.schema import Airframe, Config, LaunchSite, Motor, Rocket, Scenario, Sections, Weather, assemble
from sim.params import (
    Aero,
    Atmosphere,
    Control,
    Gravity,
    Lengths,
    Params,
    Recovery,
    Site,
    Solver,
    Soundings,
    Thrust,
    Weight,
    Wind,
)
from sim.state import State


def _minimal_rocket(name: str = "rocket") -> Rocket:
    return Rocket(name=name, airframe=Airframe(m=1.0, I=0.01))


def _minimal_motor(name: str = "motor") -> Motor:
    return Motor(name=name)


def _non_default_rocket() -> Rocket:
    """Every group non-default, so assembling this rocket can prove each
    one actually travelled from `Rocket` into `Params` (SS31.8 #1).

    `weight`/`thrust` moved off `Rocket` at Step 80 -- `_non_default_motor()`
    below covers `thrust`'s non-default case now; `weight` is DERIVED by
    `assemble`, not sourced from `Rocket` at all (SS32.3), so it is
    exercised by `_non_default_scenario`'s composed `Params.weight`
    instead of by a `Rocket` field."""
    return Rocket(
        name="non_default_rocket",
        airframe=Airframe(m=2.5, I=0.2),
        lengths=Lengths(l1=0.3, l2=0.4, u_B=0.01, u_C=0.02, misalign_deg=1.0),
        aero=Aero(model="linearized", S=0.01, d_ref=0.1, C_A0=0.05),
        recovery=Recovery(model="deploy", trigger="timer", deploy_time=5.0, Cd=1.0, S=1.0),
        control=Control(airbrake_model="proportional", airbrake_kp=0.5, airbrake_Cd=1.2, airbrake_S_max=0.01),
        sections=Sections(L_total=1.0, l_nose=0.2, l_fin_root_fwd=0.6, l_fin_root_aft=0.7),
    )


def _non_default_motor() -> Motor:
    """`Scenario.motor`'s non-default fixture (Step 80) -- mirrors
    `_non_default_rocket()`'s style. `mass_model` stays `"none"` (every
    existing seed's path, SS32.3.3 case 0) so assembling this motor
    still exercises the pass-through, not the full mass-model
    composition -- that is `tests/test_motor_pieces.py`'s job."""
    return Motor(
        name="non_default_motor",
        thrust=Thrust(motor_curve="motor.csv", A_e=0.001, p_ref=90000.0),
    )


def _non_default_site() -> LaunchSite:
    return LaunchSite(
        name="non_default_site",
        site=Site(lat0_deg=28.5, lon0_deg=-80.6, h0_m=3.0, azimuth_deg=45.0, L_rail=2.0, rail_angle_deg=70.0),
    )


def _non_default_weather() -> Weather:
    return Weather(
        name="non_default_weather",
        atmosphere=Atmosphere(model="sounding", humid_air=True),
        soundings=Soundings(case="2026-05-12_kkb"),
        wind=Wind(model="analytic", ref_ms=5.0, dir_deg=270.0),
    )


def _non_default_scenario() -> Scenario:
    return Scenario(
        name="non_default_scenario",
        rocket=_non_default_rocket(),
        motor=_non_default_motor(),
        site=_non_default_site(),
        weather=_non_default_weather(),
        gravity=Gravity(model="wgs84", direction="radial", earth_rotation=True),
        solver=Solver(method="rk4", rtol=1e-6, atol=1e-8, t_max=100.0, dt=0.01, sample_rate_hz=10.0),
    )


# ----------------------------------------------------------------------
# SS31.8 #1 -- the structural one-owner test, two ways
# ----------------------------------------------------------------------

_GROUP_DEFAULTS = {
    "lengths": Lengths(),
    "thrust": Thrust(),
    "aero": Aero(),
    "recovery": Recovery(),
    "control": Control(),
    "site": Site(),
    "atmosphere": Atmosphere(),
    "soundings": Soundings(),
    "wind": Wind(),
    "gravity": Gravity(),
    "solver": Solver(),
}


def test_assemble_leaves_no_group_at_its_default():
    """Behavioral proof: assembling a scenario built entirely from
    non-default pieces must leave no group of the resulting `Params`
    equal to its own dataclass default -- i.e. every one of the twelve
    groups actually came from a piece, not a silent default."""
    sc = _non_default_scenario()
    p = sc.config.params

    # `weight` has no no-argument default to compare against (it is the
    # one required group); check it landed as given instead.
    assert p.weight == Weight(m=2.5, I=0.2)

    for group_name, default_value in _GROUP_DEFAULTS.items():
        group_value = getattr(p, group_name)
        assert group_value != default_value, (
            f"Params.{group_name} equals its own dataclass default -- "
            f"assemble did not source it from a piece"
        )


def test_assemble_params_call_keyword_set_equals_params_fields_exactly():
    """More precise structural pin: parse `assemble`'s own source for the
    `Params(...)` call site and assert its keyword set is exactly
    `{f.name for f in dataclasses.fields(Params)}` -- pinning the
    one-owner invariant directly rather than only behaviorally."""
    source = textwrap.dedent(inspect.getsource(assemble))
    tree = ast.parse(source)

    call_node = None
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "Params":
            call_node = node
            break
    assert call_node is not None, "assemble() has no Params(...) call to inspect"

    keyword_names = {kw.arg for kw in call_node.keywords}
    assert keyword_names == {f.name for f in dataclasses.fields(Params)}


# ----------------------------------------------------------------------
# SS31.8 #4 -- override ordering, and F6's exact-90-degree derivation
# ----------------------------------------------------------------------


def test_override_applies_before_s0_is_derived():
    """The ordering regression test: a `site.rail_angle_deg` override
    must move the derived `s0.theta` with it (F5, D-51)."""
    sc = Scenario(
        name="override_test",
        rocket=_minimal_rocket(),
        motor=_minimal_motor(),
        site=LaunchSite(name="site"),  # default rail_angle_deg == 90.0
        weather=Weather(name="weather"),
        overrides={"site.rail_angle_deg": 85.0},
        s0=None,
    )
    assert sc.config.s0.theta == math.radians(85.0)


def test_s0_none_with_default_90_degree_rail_is_exactly_pi_over_2():
    """F6, measured not assumed: `math.radians(90.0)` is bit-for-bit
    `math.pi / 2`, so the default `LaunchSite` derives the same `s0`
    every existing seed config used."""
    assert math.radians(90.0) == math.pi / 2

    sc = Scenario(
        name="default_rail",
        rocket=_minimal_rocket(),
        motor=_minimal_motor(),
        site=LaunchSite(name="site"),
        weather=Weather(name="weather"),
    )
    assert sc.config.s0.theta == math.pi / 2


def test_explicit_s0_is_passed_through_untouched():
    explicit_s0 = State(x=1.0, z=-2.0, vx=3.0, vz=4.0, theta=0.123, omega=0.5)
    sc = Scenario(
        name="explicit_s0",
        rocket=_minimal_rocket(),
        motor=_minimal_motor(),
        site=LaunchSite(name="site", site=Site(rail_angle_deg=45.0)),
        weather=Weather(name="weather"),
        s0=explicit_s0,
    )
    assert sc.config.s0 is explicit_s0


# ----------------------------------------------------------------------
# Scenario.config -- the plain @property wiring
# ----------------------------------------------------------------------


def test_scenario_config_returns_config_with_the_scenarios_own_name_and_notes():
    sc = Scenario(
        name="my_scenario",
        rocket=_minimal_rocket(),
        motor=_minimal_motor(),
        site=LaunchSite(name="site"),
        weather=Weather(name="weather"),
        notes="test notes for my_scenario",
    )
    cfg = sc.config
    assert isinstance(cfg, Config)
    assert cfg.name == "my_scenario"
    assert cfg.notes == "test notes for my_scenario"


# ----------------------------------------------------------------------
# All four new dataclasses are frozen
# ----------------------------------------------------------------------


def test_rocket_is_frozen():
    r = _minimal_rocket()
    with pytest.raises(dataclasses.FrozenInstanceError):
        r.name = "changed"


def test_launch_site_is_frozen():
    site = LaunchSite(name="site")
    with pytest.raises(dataclasses.FrozenInstanceError):
        site.name = "changed"


def test_weather_is_frozen():
    weather = Weather(name="weather")
    with pytest.raises(dataclasses.FrozenInstanceError):
        weather.name = "changed"


def test_scenario_is_frozen():
    sc = Scenario(
        name="scenario",
        rocket=_minimal_rocket(),
        motor=_minimal_motor(),
        site=LaunchSite(name="site"),
        weather=Weather(name="weather"),
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        sc.name = "changed"


# ----------------------------------------------------------------------
# D-76 -- assemble() seeds s0.m from the composed mass (Step 85)
# ----------------------------------------------------------------------


def _mass_on_motor() -> Motor:
    """An "isp" motor with every mass field explicit (the K570 file is only read for its curve)."""
    return Motor(
        name="mass_on",
        thrust=Thrust(motor_curve="Cesaroni_2060K570-17A.eng"),
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


def _mass_scenario(motor: Motor, **kwargs) -> Scenario:
    return Scenario(
        name="mass_scenario",
        rocket=Rocket(
            name="rocket",
            airframe=Airframe(m=1.2, I=0.03, l=0.3),
            sections=Sections(l_motor_fwd=0.5),
        ),
        motor=motor,
        site=LaunchSite(name="site"),
        weather=Weather(name="weather"),
        **kwargs,
    )


def test_mass_on_derived_s0_gets_the_composed_mass():
    config = _mass_scenario(_mass_on_motor()).config
    assert config.params.weight.m_d is not None
    assert config.s0.m == config.params.weight.m
    assert config.s0.m > 0.0


def test_mass_on_explicit_s0_without_m_is_filled():
    explicit = State(x=1.0, z=-2.0, vx=3.0, vz=4.0, theta=0.123, omega=0.5)
    config = _mass_scenario(_mass_on_motor(), s0=explicit).config
    assert config.s0.m == config.params.weight.m
    assert config.s0._replace(m=0.0) == explicit


def test_mass_on_explicit_s0_with_nonzero_m_is_kept():
    explicit = State(x=0.0, z=0.0, vx=0.0, vz=0.0, theta=1.0, omega=0.0, m=2.5)
    config = _mass_scenario(_mass_on_motor(), s0=explicit).config
    assert config.s0.m == 2.5


def test_mass_model_switched_on_by_override_fills_s0_from_overridden_params():
    sc = _mass_scenario(_minimal_motor(), overrides={"weight.m_d": 0.8, "weight.m": 1.5})
    config = sc.config
    assert config.params.weight.m_d == 0.8
    assert config.s0.m == 1.5


def test_mass_off_s0_mass_stays_zero():
    config = _mass_scenario(_minimal_motor()).config
    assert config.params.weight.m_d is None
    assert config.s0.m == 0.0
