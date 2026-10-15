"""Tests for the four piece-registry subpackages (Step 72,
dev/docs/architecture-31-config-separation.md SS31.5/SS31.7/SS31.8 #2, #3,
#6).

As of this step:
  - `configs.rockets._MODULES` is empty -- Step 73 moves `toy_05kg`/
    `demo_75mm` in, which is also what first populates its registry.
  - `configs.sites._MODULES` has exactly one entry, `origin_msl`.
  - `configs.weather._MODULES` has exactly one entry, `isa_dry_calm`.
  - `configs.scenarios._MODULES` is empty -- deliberately, for exactly
    this one commit (SS31.5); nothing delegates to it yet.

So the registry-integrity checks below are parametrised over
`rockets`, `sites`, `weather` only (`scenarios` is skipped with a
comment, since every one of those assertions is vacuous against an
empty registry) and are only *meaningfully* exercised for `sites`/
`weather` in this step -- `rockets` passes the same assertions
trivially (empty lists/dicts), which is still worth checking: an
empty registry answering `names()`/duplicate-check calls correctly is
part of its contract.

Phase 2.16, Step 79 (dev/docs/architecture-32-motor-separation.md SS32.2.1,
D-73) adds `configs.motors` to `_REGISTRIES` as a fourth entry (same
shape as `rockets`/`sites`/`weather` -- `scenarios` stays out of this
dict for the structural reason already noted below, its own attribute
being `CONFIG` rather than a piece type name) and widens every
parametrised check over it; its fresh-interpreter/template checks join
`scenarios`'s existing ones, making those two lists five-wide. No
existing assertion for `rockets`/`sites`/`weather`/`scenarios` changes.
"""

import importlib
import subprocess
import sys
from pathlib import Path

import pytest

import configs.motors
import configs.rockets
import configs.scenarios
import configs.sites
import configs.weather
from configs.schema import Airframe, Sections, _weight_from_pieces
from sim.params import Atmosphere, Site, Soundings, Wind
from tests import config_variants

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_G0 = 9.80665

# Each non-empty package, its registry dict, its name->piece attribute,
# and the exception-message noun used in its `get()`.
_REGISTRIES = {
    "rockets": (configs.rockets, configs.rockets.ROCKETS, "ROCKET"),
    "sites": (configs.sites, configs.sites.SITES, "SITE"),
    "weather": (configs.weather, configs.weather.WEATHER, "WEATHER"),
    "motors": (configs.motors, configs.motors.MOTORS, "MOTOR"),
}


# ----------------------------------------------------------------------
# Registry integrity (SS31.8 #2) -- parametrised over rockets/sites/
# weather; scenarios is skipped (its registry is deliberately empty
# this step, see module docstring above).
# ----------------------------------------------------------------------


@pytest.mark.parametrize("pkg_name", ["rockets", "sites", "weather", "motors"])
def test_registry_keys_equal_module_basenames(pkg_name):
    pkg, registry, attr = _REGISTRIES[pkg_name]
    for mod in pkg._MODULES:
        basename = mod.__name__.split(".")[-1]
        piece = getattr(mod, attr)
        assert piece.name == basename
        assert basename in registry
        assert registry[basename] is piece


@pytest.mark.parametrize("pkg_name", ["rockets", "sites", "weather", "motors"])
def test_registry_has_no_duplicate_names(pkg_name):
    pkg, registry, attr = _REGISTRIES[pkg_name]
    all_names = [getattr(mod, attr).name for mod in pkg._MODULES]
    assert len(all_names) == len(set(all_names))
    assert len(registry) == len(all_names)


@pytest.mark.parametrize("pkg_name", ["rockets", "sites", "weather", "motors"])
def test_names_lists_every_registered_piece(pkg_name):
    pkg, registry, _attr = _REGISTRIES[pkg_name]
    assert set(pkg.names()) == set(registry)


@pytest.mark.parametrize("pkg_name", ["rockets", "sites", "weather", "motors"])
def test_get_unknown_name_raises_keyerror_listing_every_name(pkg_name):
    pkg, _registry, _attr = _REGISTRIES[pkg_name]
    with pytest.raises(KeyError) as excinfo:
        pkg.get("nope")
    message = str(excinfo.value)
    for name in pkg.names():
        assert name in message


def test_scenarios_registry_is_populated_by_step_73():
    """SS31.5: `configs.scenarios._MODULES = ()` was deliberate for
    exactly one commit (Step 72) -- its own docstring at the time said
    plainly that "Step 73 moves the three seed configs under this
    package and is what first fills `_MODULES` in." This test's
    predecessor (`test_scenarios_registry_is_deliberately_empty_this_step`)
    pinned the Step-72 state; this one pins what replaces it, so the
    registry's behaviour stays covered across the step boundary instead
    of silently losing coverage. `configs.scenarios.get("anything")`
    still raises `KeyError` for an unregistered name -- registry
    machinery, not scenario content, is what this test is about, so it
    checks "at least the three Step-73 seeds are present" rather than
    pinning an exact set -- Step 74 (and any future scenario this
    project adds) grows this registry without this test needing an
    edit every time, which the first version of this test did not
    survive (it pinned an exact three-name set and broke the moment
    Step 74 added a fourth)."""
    assert configs.scenarios._MODULES != ()
    assert configs.scenarios.SCENARIOS != {}
    assert {"demo_75mm_k570"} <= set(configs.scenarios.names())
    with pytest.raises(KeyError):
        configs.scenarios.get("anything")


# ----------------------------------------------------------------------
# No circular import ×5 -- fresh interpreter, each subpackage imported
# first (SS31.8 #3, mirroring tests/test_configs.py:197-210; `motors`
# joins at Step 79, dev/docs/architecture-32-motor-separation.md SS32.2.1).
# ----------------------------------------------------------------------


def _run_fresh_interpreter(code: str) -> None:
    result = subprocess.run(
        [sys.executable, "-c", code], cwd=_PROJECT_ROOT,
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize(
    "module_path,expr",
    [
        ("configs.rockets._TEMPLATE_rocket", "configs.rockets._TEMPLATE_rocket.ROCKET.name"),
        ("configs.sites._TEMPLATE_site", "configs.sites._TEMPLATE_site.SITE.name"),
        ("configs.weather._TEMPLATE_weather", "configs.weather._TEMPLATE_weather.WEATHER.name"),
        ("configs.scenarios._TEMPLATE_scenario", "configs.scenarios._TEMPLATE_scenario.SCENARIO.name"),
        ("configs.motors._TEMPLATE_motor", "configs.motors._TEMPLATE_motor.MOTOR.name"),
    ],
)
def test_import_template_first_has_no_circular_import(module_path, expr):
    _run_fresh_interpreter(f"import {module_path}\nprint({expr})\n")


# ----------------------------------------------------------------------
# SS31.8 #6 -- every TEMPLATE module imports cleanly, exposes its
# expected object, and that object's name is absent from the registry.
# ----------------------------------------------------------------------


@pytest.mark.parametrize(
    "module_path,attr,pkg_name",
    [
        ("configs.rockets._TEMPLATE_rocket", "ROCKET", "rockets"),
        ("configs.sites._TEMPLATE_site", "SITE", "sites"),
        ("configs.weather._TEMPLATE_weather", "WEATHER", "weather"),
        ("configs.motors._TEMPLATE_motor", "MOTOR", "motors"),
    ],
)
def test_template_imports_cleanly_and_is_absent_from_its_registry(module_path, attr, pkg_name):
    mod = importlib.import_module(module_path)
    piece = getattr(mod, attr)
    pkg, _registry, _attr = _REGISTRIES[pkg_name]
    assert piece.name not in pkg.names()


def test_scenario_template_imports_cleanly_and_is_absent_from_its_registry():
    mod = importlib.import_module("configs.scenarios._TEMPLATE_scenario")
    assert mod.SCENARIO.name not in configs.scenarios.names()
    assert mod.CONFIG.name not in configs.scenarios.names()


# ----------------------------------------------------------------------
# The two "pin the defaults" pieces really do just inherit
# sim/params.py's own defaults (SS31.7).
# ----------------------------------------------------------------------


def test_origin_msl_site_equals_bare_site_default():
    assert configs.sites.get("origin_msl").site == Site()


def test_isa_dry_calm_weather_equals_bare_defaults():
    weather = configs.weather.get("isa_dry_calm")
    assert weather.atmosphere == Atmosphere()
    assert weather.soundings == Soundings()
    assert weather.wind == Wind()


# ----------------------------------------------------------------------
# Phase 2.16, Step 79 (dev/docs/architecture-32-motor-separation.md SS32.2.1,
# D-73) -- the `configs.motors` seed set itself.
# ----------------------------------------------------------------------


def test_cti_k570_motor_curve_is_the_real_eng_file():
    assert configs.motors.get("cti_k570").thrust.motor_curve == "Cesaroni_2060K570-17A.eng"


def test_cti_k570_and_cti_k570_isp_compositions_agree_d59_equivalence():
    """D-59: the same real curve under `mass_model="endpoints"`
    (`cti_k570`, every mass field derived from the `.eng` header) and
    under `mass_model="isp"` (`cti_k570_isp`, `I_sp` hand-entered to
    match `cti_k570`'s own measured `I_sp_eff` to 2 decimal places)
    must compose to the same `m`/`m_d`/`l_d`/`I_d`/`I_sp` against a
    common `Airframe`/`Sections`, agreeing to 1e-3 relative -- the
    cheapest possible check on the claim that the two models are just
    two different ways of specifying one mass history."""
    airframe = Airframe(m=1.0, I=0.05, l=0.5)
    sections = Sections(l_motor_aft=1.0)

    w_endpoints = _weight_from_pieces(airframe, sections, configs.motors.get("cti_k570"), _G0)
    w_isp = _weight_from_pieces(airframe, sections, config_variants.CTI_K570_ISP, _G0)

    for field in ("m", "m_d", "l_d", "I_d", "I_sp"):
        a = getattr(w_endpoints, field)
        b = getattr(w_isp, field)
        assert a == pytest.approx(b, rel=1e-3), f"{field}: {a!r} vs {b!r}"
