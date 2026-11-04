"""tests/test_rockets_ideal_own.py -- tests for projects/fx27/campaigns/
cspace/rockets_ideal_own.py and generate_rockets_ideal_own.py
(dev/docs/architecture-41-fx27-idealized-regenerate.md SS41.8, Phase 2.23,
Step 148, D-176).

Does NOT touch tests/test_fx27_port.py (that file's own "ONLY test file
this port touches" boundary note) -- a new, separate step's test surface.

No numeric pin/oracle here. The 8 constants in rockets_ideal_own.py are
THIS project's own solver output, re-derived against rockets.py/
rockets_dm.py's current base figures -- they are EXPECTED TO DRIFT
whenever those base figures change (that drift is the entire point of
roadmap F2). Asserting a specific decimal value against any of them
would be a false pin; this file only checks assembly/wiring and the
write mechanism in isolation.

Hard constraint (repeated from the architecture doc): no test below may
call generate_rockets_ideal_own._solved_values() or .main() against the
real committed module -- every write-mechanism test targets a tmp_path
file or a synthetic in-memory string, never the real solver or the real
rockets_ideal_own.py path.

Same house style as test_fx27_port.py/test_apogee_targeting.py: plain
`assert`, no fixtures, no conftest.py.
"""

from __future__ import annotations

import math

import pytest

from apps.sim.schema import Scenario, assemble

from projects.fx27.campaigns.cspace import motors, rockets_ideal_own
from projects.fx27.campaigns.cspace.generate_rockets_ideal_own import (
    _rewrite_file,
    _substitute_constant,
)
from projects.fx27.campaigns.cspace.site import SITE
from projects.fx27.campaigns.cspace.weather import WEATHER
from projects.fx27.point.comparison import run_many
from projects.fx27.point.metrics import row_from_flight

# ----------------------------------------------------------------------
# 1. Assembly smoke tests -- mirrors test_fx27_port.py::test_cspace_
#    scenario_assembles, locally-built Scenario wrappers (SS41.7: the 8
#    new Rocket variants are NOT wired into SCENARIOS/SCENARIOS_DM).
# ----------------------------------------------------------------------

_VARIANTS: "dict[str, tuple]" = {
    "pro54_transition_ideal_own_mass": (
        rockets_ideal_own.PRO54_TRANSITION_IDEAL_OWN_MASS, motors.PRO54_2060K570,
    ),
    "pro54_transition_ideal_own_drag": (
        rockets_ideal_own.PRO54_TRANSITION_IDEAL_OWN_DRAG, motors.PRO54_2060K570,
    ),
    "pro75_ideal_own_mass": (
        rockets_ideal_own.PRO75_IDEAL_OWN_MASS, motors.PRO75_3419L645,
    ),
    "pro75_ideal_own_drag": (
        rockets_ideal_own.PRO75_IDEAL_OWN_DRAG, motors.PRO75_3419L645,
    ),
    "pro54_transition_dm_ideal_own_mass": (
        rockets_ideal_own.PRO54_TRANSITION_DM_IDEAL_OWN_MASS, motors.PRO54_2060K570,
    ),
    "pro54_transition_dm_ideal_own_drag": (
        rockets_ideal_own.PRO54_TRANSITION_DM_IDEAL_OWN_DRAG, motors.PRO54_2060K570,
    ),
    "pro75_dm_ideal_own_mass": (
        rockets_ideal_own.PRO75_DM_IDEAL_OWN_MASS, motors.PRO75_3419L645,
    ),
    "pro75_dm_ideal_own_drag": (
        rockets_ideal_own.PRO75_DM_IDEAL_OWN_DRAG, motors.PRO75_3419L645,
    ),
}

_ALL_EIGHT = _VARIANTS  # alias -- matches the architecture doc's naming


def _scenario_for(rocket_name: str) -> Scenario:
    rocket, motor = _VARIANTS[rocket_name]
    return Scenario(name=rocket_name, rocket=rocket, motor=motor, site=SITE, weather=WEATHER)


def test_all_eight_own_variants_are_present():
    assert set(_ALL_EIGHT) == {
        "pro54_transition_ideal_own_mass", "pro54_transition_ideal_own_drag",
        "pro75_ideal_own_mass", "pro75_ideal_own_drag",
        "pro54_transition_dm_ideal_own_mass", "pro54_transition_dm_ideal_own_drag",
        "pro75_dm_ideal_own_mass", "pro75_dm_ideal_own_drag",
    }


@pytest.mark.parametrize("rocket_name", sorted(_ALL_EIGHT))
def test_rocket_ideal_own_variant_assembles(rocket_name):
    cfg = assemble(_scenario_for(rocket_name))
    assert cfg.params.weight.m > 0.0
    assert cfg.params.weight.m_d is not None  # mass model is ON


# ----------------------------------------------------------------------
# 2. Write-mechanism unit tests, against _substitute_constant/_rewrite_
#    file directly -- pure string/tmp_path tests only. NEVER call
#    _solved_values()/main() (that would invoke the real solver and/or
#    overwrite the real committed module).
# ----------------------------------------------------------------------

_SYNTHETIC_SOURCE = """\
HEADER_CONSTANT = 1.0
FOO_BAR = 2.5000          # PLACEHOLDER
BAZ_QUX = 7.0000          # PLACEHOLDER
TRAILER_CONSTANT = 3.0
"""


def test_substitute_constant_replaces_the_named_line_only():
    out = _substitute_constant(_SYNTHETIC_SOURCE, "FOO_BAR", 9.1234)

    lines = out.splitlines()
    assert lines[1] == "FOO_BAR = 9.1234"
    # every other line byte-for-byte identical to the input
    assert lines[0] == "HEADER_CONSTANT = 1.0"
    assert lines[2] == "BAZ_QUX = 7.0000          # PLACEHOLDER"
    assert lines[3] == "TRAILER_CONSTANT = 3.0"


def test_substitute_constant_raises_if_name_not_found_exactly_once():
    zero_match_source = "SOME_OTHER_NAME = 1.0\n"
    with pytest.raises(RuntimeError, match="found 0"):
        _substitute_constant(zero_match_source, "FOO_BAR", 1.0)

    two_match_source = "FOO_BAR = 1.0\nFOO_BAR = 2.0\n"
    with pytest.raises(RuntimeError, match="found 2"):
        _substitute_constant(two_match_source, "FOO_BAR", 1.0)


def test_rewrite_file_round_trips_through_tmp_path(tmp_path):
    synthetic_module = tmp_path / "rockets_ideal_own_fake.py"
    synthetic_module.write_text(
        '"""synthetic module, same shape as the real generated block."""\n'
        "\n"
        "PRO54_TRANSITION_IDEAL_OWN_MASS_KG = 1.0000\n"
        "PRO54_TRANSITION_IDEAL_OWN_DRAG_CX = 2.0000\n"
        "PRO75_IDEAL_OWN_MASS_KG = 3.0000\n"
        "PRO75_IDEAL_OWN_DRAG_CX = 4.0000\n"
        "PRO54_TRANSITION_DM_IDEAL_OWN_MASS_KG = 5.0000\n"
        "PRO54_TRANSITION_DM_IDEAL_OWN_DRAG_CX_SCALE = 6.0000\n"
        "PRO75_DM_IDEAL_OWN_MASS_KG = 7.0000\n"
        "PRO75_DM_IDEAL_OWN_DRAG_CX_SCALE = 8.0000\n"
        "\n"
        "# a Rocket construction below, untouched by the rewrite\n"
        "SOME_ROCKET = object()\n",
        encoding="utf-8",
    )
    before = synthetic_module.read_text(encoding="utf-8")

    new_values = {
        "PRO54_TRANSITION_IDEAL_OWN_MASS_KG": 11.1111,
        "PRO54_TRANSITION_IDEAL_OWN_DRAG_CX": 12.2222,
        "PRO75_IDEAL_OWN_MASS_KG": 13.3333,
        "PRO75_IDEAL_OWN_DRAG_CX": 14.4444,
        "PRO54_TRANSITION_DM_IDEAL_OWN_MASS_KG": 15.5555,
        "PRO54_TRANSITION_DM_IDEAL_OWN_DRAG_CX_SCALE": 16.6666,
        "PRO75_DM_IDEAL_OWN_MASS_KG": 17.7777,
        "PRO75_DM_IDEAL_OWN_DRAG_CX_SCALE": 18.8888,
    }
    _rewrite_file(synthetic_module, new_values)

    after_lines = synthetic_module.read_text(encoding="utf-8").splitlines()
    before_lines = before.splitlines()

    for name, value in new_values.items():
        expected = f"{name} = {value:.4f}"
        assert expected in after_lines

    # every non-targeted line (docstring, blank lines, the trailing
    # comment + Rocket construction) is untouched.
    targeted_names = set(new_values)
    for before_line, after_line in zip(before_lines, after_lines):
        name = before_line.split(" = ", 1)[0]
        if name not in targeted_names:
            assert before_line == after_line


# ----------------------------------------------------------------------
# 3. Plausibility checks (not a numeric pin) -- one dc, one dm
#    representative case, same style as test_fx27_port.py's own
#    test_dm_scenario_apogee_is_plausible_against_its_dc_namesake.
# ----------------------------------------------------------------------

_PLAUSIBILITY_BAND_M = (1500.0, 6000.0)


@pytest.mark.parametrize("rocket_name", ["pro75_ideal_own_mass", "pro75_dm_ideal_own_drag"])
def test_committed_variant_apogee_is_plausible(rocket_name):
    """Wiring sanity check only, NOT a solver-accuracy check (SS41.8 #3):
    a wildly different apogee than the generous band below would indicate
    the wrong field was overridden, a typo'd bracket, or a stale
    regenerate run -- not a tight numeric regression."""
    scenario = _scenario_for(rocket_name)
    runs = run_many({rocket_name: scenario})
    row = row_from_flight(rocket_name, runs[rocket_name])

    assert row.apogee_agl is not None
    assert math.isfinite(row.apogee_agl)
    lo, hi = _PLAUSIBILITY_BAND_M
    assert lo <= row.apogee_agl <= hi
