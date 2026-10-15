"""Tests for the Step 73 switch-over -- seeds split into pieces,
`configs.get` delegates to `configs.scenarios` (`docs/architecture-31-
config-separation.md` SS31.7/SS31.8 items 5, 7, 8).

The four pre-existing exact-equality pins in `tests/test_configs.py`
(unedited by this step) are the primary gate -- they prove `assemble`
reproduces every implicit default and that the derived `s0` is
bit-for-bit. This file adds the Step-73-specific checks the ticket
calls out: the `demo_75mm_airbrake` composition identity (today's
`derive({})` relation), a `notes`-string pin for all three seeds (what
`--list-configs` and App 5's table print), `get_scenario`'s piece-level
lookup, a flat `CONFIG`-only module still registering (SS31.8 #7), each
migrated rocket's groups against the independent reconstructions
already in the suite (SS31.8 #8), and every registered scenario still
flying (SS31.8 #5).
"""

import dataclasses
import math
import types

import pytest

import configs
import configs.rockets
import configs.scenarios
from apps.motor_selection.compare_motors import _demo_baseline
from configs.motors.cti_k570_isp import MOTOR as _CTI_K570_ISP_MOTOR
from configs.rockets import demo_75mm_k570
from configs.schema import Config, Scenario
from configs.sites import origin_msl
from configs.weather import isa_dry_calm
from sim.integrate import run_sim
from sim.state import M
from tests.test_configs import _toy_05kg_literal

# ----------------------------------------------------------------------
# demo_75mm_airbrake: today's `derive({})` relation, now a composition
# identity (SS31.7's "What each seed becomes" table).
# ----------------------------------------------------------------------


def test_demo_75mm_airbrake_params_equal_demo_75mm_params():
    assert configs.get("demo_75mm_airbrake").params == configs.get("demo_75mm").params


# ----------------------------------------------------------------------
# notes-string pins -- byte-for-byte identical to the pre-split flat
# `Config` literals, because `--list-configs` and App 5's comparison
# table print their first line (SS31.7).
# ----------------------------------------------------------------------


def test_toy_05kg_notes_pin_exactly():
    assert configs.get("toy_05kg").notes == (
        "run.py's / App 2's historical placeholder scenario: a generic "
        "small model-rocket scale, unchanged since Step 1/Step 4."
    )


def test_demo_75mm_notes_pin_exactly():
    assert configs.get("demo_75mm").notes == (
        "The architect's own synthetic 1.5 kg / 75 mm vehicle. Deliberately "
        "NOT run.py's 0.5 kg toy scenario: 338 N*s (the largest new fixture) "
        "on 0.5 kg gives an ideal delta-v of ~676 m/s (~Mach 2), where a "
        "constant C_x = 0.5 is not a defensible aerodynamic model and the "
        "ISA extrapolation ceiling starts to matter. 1.5 kg keeps every "
        "fixture subsonic (largest motor: ideal delta-v ~225 m/s before "
        "gravity/drag losses, <~ Mach 0.7) while still leaving the smallest "
        "motor just barely flyable -- itself informative. C_z = C_m = 0.0 "
        "makes this a vertical, attitude-frozen 1-D shot, the same "
        "simplification run.py and App 2 already carry, appropriate for a "
        "motor comparison (one variable at a time) and, per SS29.4.1/F5, "
        "the reason the ascent window is mandatory."
    )


def test_demo_75mm_airbrake_notes_pin_exactly():
    assert configs.get("demo_75mm_airbrake").notes == (
        "demo_75mm, unchanged, registered under its own name as App 4's "
        "(airbrake sizing) default vehicle. No control.airbrake_* override "
        "lives here: the app owns that group entirely at solve time "
        "(architecture-30 SS30.6), and the target apogee is a study input "
        "carried in apps/airbrake_sizing/targets.py, not a vehicle property."
    )


# ----------------------------------------------------------------------
# get_scenario -- the one additive API (SS31.6).
# ----------------------------------------------------------------------


def test_get_scenario_demo_75mm_returns_the_composition():
    scenario = configs.get_scenario("demo_75mm")
    assert isinstance(scenario, Scenario)
    assert scenario.rocket.name == "demo_75mm"
    assert scenario.site.name == "origin_msl"
    assert scenario.weather.name == "isa_dry_calm"


def test_get_scenario_unknown_name_raises_keyerror():
    with pytest.raises(KeyError):
        configs.get_scenario("nope")


def test_get_scenario_returns_none_for_a_flat_config_only_module(monkeypatch):
    """SS31.8 #7: a flat, whole-`Config` module (no `SCENARIO`) still
    registers through the scenario registry's own keying logic, and
    `get_scenario` returns `None` for it rather than raising."""
    flat_config = Config(name="_test_flat_scenario", params=_demo_baseline(),
                          s0=configs.get("demo_75mm").s0, notes="a flat test module")
    flat_module = types.SimpleNamespace(
        __name__="configs.scenarios._test_flat_scenario",
        CONFIG=flat_config,
    )
    assert not hasattr(flat_module, "SCENARIO")

    monkeypatch.setattr(
        configs.scenarios, "_MODULES",
        configs.scenarios._MODULES + (flat_module,),
    )
    monkeypatch.setitem(configs.scenarios.SCENARIOS, flat_config.name, flat_config)

    assert configs.get("_test_flat_scenario") is flat_config
    assert configs.get_scenario("_test_flat_scenario") is None


# ----------------------------------------------------------------------
# Piece-level slice equality against the independent reconstructions
# already in the suite (SS31.8 #8).
# ----------------------------------------------------------------------


def test_demo_75mm_rocket_groups_equal_demo_baseline():
    """`weight`/`thrust` moved off `Rocket` at Step 80 (SS32.2.3) --
    `rocket.weight`/`rocket.thrust` no longer exist, so these two groups
    are read off the assembled `Config.params` instead, which is a
    strengthening: it now tests the composition's output (the derived
    `weight`, and `thrust` sourced from `Scenario.motor`), not a piece's
    raw field."""
    rocket = configs.rockets.get("demo_75mm")
    params = configs.get("demo_75mm").params
    baseline = _demo_baseline()
    assert params.weight == baseline.weight
    assert rocket.lengths == baseline.lengths
    assert params.thrust == baseline.thrust
    assert rocket.aero == baseline.aero


def test_toy_05kg_rocket_groups_equal_toy_05kg_literal():
    """See `test_demo_75mm_rocket_groups_equal_demo_baseline`'s docstring
    -- same Step-80 retargeting of `weight`/`thrust`."""
    rocket = configs.rockets.get("toy_05kg")
    params = configs.get("toy_05kg").params
    literal = _toy_05kg_literal()
    assert params.weight == literal.weight
    assert rocket.lengths == literal.lengths
    assert params.thrust == literal.thrust
    assert rocket.aero == literal.aero


# ----------------------------------------------------------------------
# Every registered scenario still flies (SS31.8 #5) -- the existing
# check, now parametrised over the scenario registry (same registry
# `configs.names()` already delegates to).
# ----------------------------------------------------------------------


@pytest.mark.parametrize("name", configs.names())
def test_every_registered_scenario_flies(name):
    cfg = configs.get(name)
    result = run_sim(cfg.params, cfg.s0)
    assert result.events["apogee"] is not None


# ----------------------------------------------------------------------
# Step 74 (SS31.12): demo_75mm_highland -- the same rocket piece flown
# from a different site, in different weather. Note:
# `test_every_registered_scenario_flies` above is parametrised over
# `configs.names()`, so it already picks up `demo_75mm_highland` with no
# edit to that test -- its parametrised case count rises by one (four
# registered scenarios instead of three), which is expected, not an
# anomaly (SS31.12's own Check list says so explicitly).
# ----------------------------------------------------------------------


def test_demo_75mm_highland_rocket_groups_equal_demo_75mm():
    """The proof that one vehicle now serves two sites with zero
    duplication -- the user's original request reduced to one
    assertion (SS31.12)."""
    highland = configs.get("demo_75mm_highland")
    baseline = configs.get("demo_75mm")
    assert highland.params.weight == baseline.params.weight
    assert highland.params.lengths == baseline.params.lengths
    assert highland.params.thrust == baseline.params.thrust
    assert highland.params.aero == baseline.params.aero


def test_demo_75mm_highland_s0_theta_derives_from_the_tilted_rail():
    """D-51a's derivation doing real work for the first time: every
    other registered scenario's rail sits at the `Site` default
    (90.0 deg, reproducing `math.pi / 2` exactly, SS31.2 F6);
    `highland_1500m`'s rail is tilted to 85.0 deg."""
    assert configs.get("demo_75mm_highland").s0.theta == math.radians(85.0)


def test_demo_75mm_highland_site_and_weather_are_the_new_pieces():
    cfg = configs.get("demo_75mm_highland")
    assert cfg.params.site.h0_m == 1500.0
    assert cfg.params.wind.model == "analytic"


# ----------------------------------------------------------------------
# Step 81 (docs/architecture-32-motor-separation.md SS32.2/SS32.3.3/
# SS32.3.4/SS32.5): demo_75mm_k570 -- a real CTI motor (its own mass
# history read from its own RASP file) composed with a mass-modelled
# airframe, the mass model ON from a config for the first time.
# `test_every_registered_scenario_flies` above already exercises this
# scenario with no edit (its parametrised case count rises to five,
# expected, not an anomaly, per that test's own Step-74 note above). The
# checks below are Step 81's own: the composition's actual numbers, the
# station-convention sanity check, and the headline burnout-mass claim
# (D-59) measured on a real curve rather than argued.
# ----------------------------------------------------------------------


def _demo_75mm_k570_airframe():
    return configs.rockets.get("demo_75mm_k570").airframe


def test_demo_75mm_k570_mass_model_is_on():
    """The mass model is ON for the first time from a config (SS32.3.3)."""
    assert configs.get("demo_75mm_k570").params.weight.m_d is not None


def test_demo_75mm_k570_composed_masses():
    airframe = _demo_75mm_k570_airframe()
    weight = configs.get("demo_75mm_k570").params.weight
    # K570 header (SS32.3.1 F5): m_total=1.685 kg, m_prop=0.990 kg,
    # m_f = m_total - m_prop = 0.695 kg.
    assert weight.m == pytest.approx(airframe.m + 1.685, rel=1e-6)
    assert weight.m_d == pytest.approx(airframe.m + 0.695, rel=1e-6)


def test_demo_75mm_k570_isp_eff_matches_f5():
    """`I_sp_eff = J/(m_prop*g0)` derived at assembly from the curve's own
    total impulse (SS32.3.4), matching F5's measured 212.41 s."""
    assert configs.get("demo_75mm_k570").params.weight.I_sp == pytest.approx(212.41, abs=0.01)


def test_demo_75mm_k570_stations_are_inside_the_airframe():
    """`l_d`/`l_p` (the composed dry-assembly and propellant nose-tip
    stations) both fall inside `[l_nose, L_total]` -- the station-
    convention sanity check (SS32.5)."""
    sections = demo_75mm_k570.ROCKET.sections
    weight = configs.get("demo_75mm_k570").params.weight
    assert sections.l_nose <= weight.l_d <= sections.L_total
    assert sections.l_nose <= weight.l_p <= sections.L_total


def test_demo_75mm_k570_burnout_mass_lands_on_m_f():
    """The headline assertion (SS32.3.4, D-59): the impulse-fraction-
    shaped 'endpoints' model consumes exactly `m_prop` over the whole
    curve, so the integrated state's mass at the end of the run lands on
    `m_f = m_total - m_prop` -- measured on the real K570 curve, not just
    argued. `thrust` (and hence `dm/dt`) is zero past burnout (the
    `(0.0, 0.0)` prepend plus the curve's own trailing zero, SS32.3.4), so
    mass stops changing at burnout and the LAST sample of a full run to
    ground impact is still the burnout mass."""
    airframe = _demo_75mm_k570_airframe()
    cfg = configs.get("demo_75mm_k570")
    result = run_sim(cfg.params, cfg.s0)
    assert result.y[M][-1] == pytest.approx(airframe.m + 0.695, rel=1e-4)


def test_demo_75mm_k570_isp_and_endpoints_motors_agree_on_apogee():
    """D-59's equivalence, end to end: the same airframe flown with
    `cti_k570` ('endpoints', `I_sp` derived from the curve's own total
    impulse) and `cti_k570_isp` ('isp', `I_sp` hand-entered to match)
    give apogees agreeing to ~0.1%."""
    cfg_endpoints = configs.get("demo_75mm_k570")

    scenario_isp = Scenario(
        name="_test_demo_75mm_k570_isp",
        rocket=demo_75mm_k570.ROCKET,
        motor=_CTI_K570_ISP_MOTOR,
        site=origin_msl.SITE,
        weather=isa_dry_calm.WEATHER,
    )
    cfg_isp = scenario_isp.config
    # SS32.10 backlog ("s0.m derived from weight.m", not yet implemented
    # in `configs/schema.py::_pad_state`): same local patch
    # `configs/scenarios/demo_75mm_k570.py` applies to its own `CONFIG`,
    # needed here too since this scenario is built ad hoc, not registered.
    cfg_isp = dataclasses.replace(cfg_isp, s0=cfg_isp.s0._replace(m=cfg_isp.params.weight.m))

    result_endpoints = run_sim(cfg_endpoints.params, cfg_endpoints.s0)
    result_isp = run_sim(cfg_isp.params, cfg_isp.s0)

    apogee_endpoints = -result_endpoints.y[1].min()  # z is DOWN-positive; altitude = -z
    apogee_isp = -result_isp.y[1].min()
    assert apogee_endpoints == pytest.approx(apogee_isp, rel=1e-3)
