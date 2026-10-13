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

import types

import pytest

import configs
import configs.rockets
import configs.scenarios
from apps.motor_selection.compare_motors import _demo_baseline
from configs.schema import Config, Scenario
from sim.integrate import run_sim
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
    rocket = configs.rockets.get("demo_75mm")
    baseline = _demo_baseline()
    assert rocket.weight == baseline.weight
    assert rocket.lengths == baseline.lengths
    assert rocket.thrust == baseline.thrust
    assert rocket.aero == baseline.aero


def test_toy_05kg_rocket_groups_equal_toy_05kg_literal():
    rocket = configs.rockets.get("toy_05kg")
    literal = _toy_05kg_literal()
    assert rocket.weight == literal.weight
    assert rocket.lengths == literal.lengths
    assert rocket.thrust == literal.thrust
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
