"""Tests for the four piece-registry subpackages (Step 72,
docs/architecture-31-config-separation.md SS31.5/SS31.7/SS31.8 #2, #3,
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
"""

import importlib
import subprocess
import sys
from pathlib import Path

import pytest

import configs.rockets
import configs.scenarios
import configs.sites
import configs.weather
from sim.params import Atmosphere, Site, Soundings, Wind

_PROJECT_ROOT = Path(__file__).resolve().parents[1]

# Each non-empty package, its registry dict, its name->piece attribute,
# and the exception-message noun used in its `get()`.
_REGISTRIES = {
    "rockets": (configs.rockets, configs.rockets.ROCKETS, "ROCKET"),
    "sites": (configs.sites, configs.sites.SITES, "SITE"),
    "weather": (configs.weather, configs.weather.WEATHER, "WEATHER"),
}


# ----------------------------------------------------------------------
# Registry integrity (SS31.8 #2) -- parametrised over rockets/sites/
# weather; scenarios is skipped (its registry is deliberately empty
# this step, see module docstring above).
# ----------------------------------------------------------------------


@pytest.mark.parametrize("pkg_name", ["rockets", "sites", "weather"])
def test_registry_keys_equal_module_basenames(pkg_name):
    pkg, registry, attr = _REGISTRIES[pkg_name]
    for mod in pkg._MODULES:
        basename = mod.__name__.split(".")[-1]
        piece = getattr(mod, attr)
        assert piece.name == basename
        assert basename in registry
        assert registry[basename] is piece


@pytest.mark.parametrize("pkg_name", ["rockets", "sites", "weather"])
def test_registry_has_no_duplicate_names(pkg_name):
    pkg, registry, attr = _REGISTRIES[pkg_name]
    all_names = [getattr(mod, attr).name for mod in pkg._MODULES]
    assert len(all_names) == len(set(all_names))
    assert len(registry) == len(all_names)


@pytest.mark.parametrize("pkg_name", ["rockets", "sites", "weather"])
def test_names_lists_every_registered_piece(pkg_name):
    pkg, registry, _attr = _REGISTRIES[pkg_name]
    assert set(pkg.names()) == set(registry)


@pytest.mark.parametrize("pkg_name", ["rockets", "sites", "weather"])
def test_get_unknown_name_raises_keyerror_listing_every_name(pkg_name):
    pkg, _registry, _attr = _REGISTRIES[pkg_name]
    with pytest.raises(KeyError) as excinfo:
        pkg.get("nope")
    message = str(excinfo.value)
    for name in pkg.names():
        assert name in message


def test_scenarios_registry_is_deliberately_empty_this_step():
    """SS31.5: `configs.scenarios._MODULES = ()` for exactly this one
    commit -- nothing delegates to it until Step 73. The registry
    machinery still works correctly against the empty tuple."""
    assert configs.scenarios._MODULES == ()
    assert configs.scenarios.SCENARIOS == {}
    assert configs.scenarios.names() == []
    with pytest.raises(KeyError):
        configs.scenarios.get("anything")


# ----------------------------------------------------------------------
# No circular import ×4 -- fresh interpreter, each subpackage imported
# first (SS31.8 #3, mirroring tests/test_configs.py:197-210).
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
