"""Tests for configs/ (Step 63, roadmap.md,
`dev/docs/architecture-30-apps-4-5-and-configs.md` SS30.4/SS30.8).

Per SS30.8: the two exact-equality pins against `run.py`'s literal and
`apps.motor_selection.compare_motors._demo_baseline()` are the primary
checks (this is what makes a later migration, roadmap Step 69, a provable
no-op), then registry integrity, `derive`'s no-silent-reset property,
`Variant.apply`/`Config.with_variant` equivalence, every registered config
actually flying, and no circular import.
"""

import math
import subprocess
import sys
from pathlib import Path

import pytest

import configs
from apps.common import study_vehicle
from apps.motor_selection.compare_motors import _demo_baseline
from configs.schema import Config, Variant
from sim.integrate import run_sim
from sim.params import Aero, Lengths, Params, Thrust, Weight
from sim.state import State
from tests import config_variants

_PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _toy_05kg_literal() -> Params:
    """`run.py`'s own literal, reconstructed here (not imported -- `run.py`
    is a script, not a module this test should trigger `main()`-side
    effects from)."""
    return Params(
        weight=Weight(m=0.5, I=0.05),
        lengths=Lengths(l1=0.3, l2=0.4),
        thrust=Thrust(motor_curve="placeholder.csv"),
        aero=Aero(S=0.005, d_ref=0.08, C_x=0.5, C_z=0.0, C_m=0.0),
    )


def _toy_05kg_s0() -> State:
    return State(x=0.0, z=0.0, vx=0.0, vz=0.0, theta=math.pi / 2, omega=0.0)


def _study_75mm_literal() -> Params:
    """The study vehicle's numbers (apps/common/study_vehicle.py), typed out
    independently here so the pin below is a real one, not a tautology."""
    return Params(
        weight=Weight(m=1.5, I=0.08),
        lengths=Lengths(l1=0.3, l2=0.4),
        thrust=Thrust(motor_curve="placeholder.csv"),
        aero=Aero(S=0.00442, d_ref=0.075, l_ref=0.75, C_x=0.5, C_z=0.0, C_m=0.0),
    )


def _demo_75mm_s0() -> State:
    """`compare_motors.main()`'s own literal (identical to
    `tests/test_motor_selection.py`'s `_s0()`)."""
    return State(x=0.0, z=0.0, vx=0.0, vz=0.0, theta=math.pi / 2, omega=0.0)


# ----------------------------------------------------------------------
# The two exact-equality pins -- the primary checks (SS30.8)
# ----------------------------------------------------------------------


def test_toy_05kg_params_pin_run_py_literal_exactly():
    assert config_variants.TOY_05KG.params == _toy_05kg_literal()


def test_toy_05kg_s0_pins_run_py_literal_exactly():
    assert config_variants.TOY_05KG.s0 == _toy_05kg_s0()


def test_demo_75mm_params_pin_demo_baseline_exactly():
    assert study_vehicle.CONFIG.params == _study_75mm_literal()
    assert _demo_baseline() == _study_75mm_literal()


def test_demo_75mm_s0_pins_compare_motors_main_literal_exactly():
    assert study_vehicle.CONFIG.s0 == _demo_75mm_s0()


# ----------------------------------------------------------------------
# Registry integrity
# ----------------------------------------------------------------------


def test_registry_keys_equal_module_basenames():
    for mod in configs._MODULES:
        basename = mod.__name__.split(".")[-1]
        assert mod.CONFIG.name == basename
        assert basename in configs.CONFIGS
        assert configs.CONFIGS[basename] is mod.CONFIG


def test_registry_has_no_duplicate_names():
    all_names = [mod.CONFIG.name for mod in configs._MODULES]
    assert len(all_names) == len(set(all_names))
    assert len(configs.CONFIGS) == len(all_names)


def test_names_lists_every_registered_config():
    assert set(configs.names()) == set(configs.CONFIGS)


def test_get_unknown_name_raises_keyerror_listing_every_name():
    with pytest.raises(KeyError) as excinfo:
        configs.get("nope")
    message = str(excinfo.value)
    for name in configs.names():
        assert name in message


# ----------------------------------------------------------------------
# Config.derive -- the no-silent-reset property (SS29 F1)
# ----------------------------------------------------------------------


def test_derive_changes_exactly_the_named_fields():
    base = study_vehicle.CONFIG
    derived = base.derive(
        name="demo_75mm_heavier",
        overrides={"weight.m": 2.0, "aero.C_x": 0.6},
    )

    assert derived.params.weight.m == 2.0
    assert derived.params.aero.C_x == 0.6

    # Every other field of the touched groups is untouched.
    assert derived.params.weight.I == base.params.weight.I
    assert derived.params.weight.m_d == base.params.weight.m_d
    assert derived.params.aero.S == base.params.aero.S
    assert derived.params.aero.d_ref == base.params.aero.d_ref
    assert derived.params.aero.C_z == base.params.aero.C_z
    assert derived.params.aero.C_m == base.params.aero.C_m

    # Every untouched group, in full, is untouched.
    for group_name in ("lengths", "thrust", "gravity", "site", "atmosphere",
                       "soundings", "wind", "recovery", "control", "solver"):
        assert getattr(derived.params, group_name) == getattr(base.params, group_name)
    assert derived.params.g0 == base.params.g0


def test_derive_inherits_s0_unless_overridden():
    base = study_vehicle.CONFIG
    derived = base.derive(name="demo_75mm_x", overrides={"weight.m": 2.0})
    assert derived.s0 == base.s0

    new_s0 = State(x=0.0, z=0.0, vx=0.0, vz=0.0, theta=0.0, omega=0.0)
    derived_with_s0 = base.derive(name="demo_75mm_y", overrides={}, s0=new_s0)
    assert derived_with_s0.s0 == new_s0
    assert derived_with_s0.s0 != base.s0


def test_derive_does_not_mutate_the_original():
    base = study_vehicle.CONFIG
    base_params_before = base.params
    base_s0_before = base.s0
    base_name_before = base.name

    derived = base.derive(name="demo_75mm_z", overrides={"weight.m": 99.0})

    assert base.params == base_params_before
    assert base.s0 == base_s0_before
    assert base.name == base_name_before
    assert derived is not base
    assert derived.params is not base.params  # a new, independent Params


# ----------------------------------------------------------------------
# Variant.apply == Config.with_variant
# ----------------------------------------------------------------------


def test_variant_apply_equals_config_with_variant():
    base = study_vehicle.CONFIG
    variant = Variant(
        name="heavier",
        overrides={"weight.m": 2.0},
        notes="a heavier airframe, for test purposes",
    )

    via_with_variant = base.with_variant(variant)
    via_apply = variant.apply(base)

    assert via_with_variant == via_apply
    assert via_with_variant.name == "study_75mm+heavier"
    assert via_apply.name == "study_75mm+heavier"


# ----------------------------------------------------------------------
# Every registered config actually flies
# ----------------------------------------------------------------------


@pytest.mark.parametrize("name", configs.names())
def test_every_registered_config_flies(name):
    cfg = configs.get(name)
    result = run_sim(cfg.params, cfg.s0)
    assert result.events["apogee"] is not None


# ----------------------------------------------------------------------
# No circular import -- a fresh interpreter, as the *first* import
# ----------------------------------------------------------------------


def _run_fresh_interpreter(code: str) -> None:
    result = subprocess.run(
        [sys.executable, "-c", code], cwd=_PROJECT_ROOT,
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr


def test_import_configs_demo_first_has_no_circular_import():
    _run_fresh_interpreter("import configs.scenarios.demo\nprint(configs.scenarios.demo.CONFIG.name)\n")


def test_import_configs_package_first_has_no_circular_import():
    _run_fresh_interpreter("import configs\nprint(configs.names())\n")


# ----------------------------------------------------------------------
# Step 69 migration: the three former in-place literals are now
# registry lookups, not just numerically equal to one (SS30.3/SS30.4).
# `run.py` is a script (importing it would trigger `main()`'s side
# effects -- plots, CSVs, stdout), so these are source-level checks:
# the call site itself must read `configs.get(...)`, and the old
# Params/State literal must actually be gone, not merely byte-equal to
# one still sitting in the file.
# ----------------------------------------------------------------------

_RUN_PY = (_PROJECT_ROOT / "run.py").read_text()
_SELECT_CONDITIONS_PY = (
    _PROJECT_ROOT / "apps" / "cfd_conditions" / "select_conditions.py"
).read_text()
_COMPARE_MOTORS_PY = (
    _PROJECT_ROOT / "apps" / "motor_selection" / "compare_motors.py"
).read_text()


def test_run_py_sources_its_scenario_from_configs_get_demo():
    assert 'configs.get("demo")' in _RUN_PY
    # The former in-place literal is gone, not just duplicated.
    assert "Weight(" not in _RUN_PY
    assert "math.pi / 2" not in _RUN_PY


def test_select_conditions_py_sources_its_scenario_from_configs_get_demo():
    assert 'configs.get("demo")' in _SELECT_CONDITIONS_PY
    assert "Weight(" not in _SELECT_CONDITIONS_PY
    assert "math.pi / 2" not in _SELECT_CONDITIONS_PY


def test_demo_baseline_is_a_one_line_reexport_of_the_study_vehicle():
    assert 'return study_vehicle.CONFIG.params' in _COMPARE_MOTORS_PY
    # The former in-place literal (its own Weight/Lengths/Thrust/Aero
    # construction) is gone from this module entirely now.
    assert "Weight(m=1.5" not in _COMPARE_MOTORS_PY


def test_compare_motors_main_also_sources_s0_from_the_study_vehicle():
    assert 'study_vehicle.CONFIG' in _COMPARE_MOTORS_PY
    assert "math.pi / 2" not in _COMPARE_MOTORS_PY
