"""TEMPORARY bridge test -- DELETE at Step 125 (Phase 2.18 pivot,
dev/docs/pivot-configs-and-packaging-analysis.md SS5.2 step 3).

Proves `examples/worked_scenario.py`'s `DEMO_SCENARIO`, built with zero
reference to the `configs/*/` registry, assembles into EXACTLY the same
`Config` as `configs.get("demo")` -- the registry-backed
`configs/scenarios/demo.py` -- field by field, recursively, not
cherry-picked. This is the loud, specific alarm for a hand-transcription
slip in Step 122's Part A (a wrong literal copied from `configs/rockets/
demo.py`, `configs/motors/cti_k570.py`, `configs/sites/origin_msl.py` or
`configs/weather/isa_dry_calm.py` into `examples/worked_scenario.py`
would otherwise look like a silent physics regression later).

Once Step 125 archives the `configs/*/` registry this test has nothing
left to bridge -- `configs.get("demo")` will not exist any more -- so it
is deleted there, not kept around as permanent coverage. Do not weaken
these assertions to make them pass; a failure here means Part A's
hand-copy has a bug, go fix the copy.
"""

from __future__ import annotations

import dataclasses

import numpy as np
import pytest

import configs
from configs.schema import assemble
from examples.worked_scenario import DEMO_SCENARIO


def _walk_equal(a, b, path: str) -> None:
    """Recursive, field-by-field equality check with an exact dotted path
    on failure. Handles frozen dataclasses (`Params` and its nested
    groups) and `NamedTuple`s (`State`) by recursing into their fields;
    everything else is a leaf, compared with `np.array_equal` if either
    side is an array-like, plain `==` otherwise -- so a numpy array
    hiding behind an ambiguous `__eq__` can never silently short-circuit
    this check.
    """
    if dataclasses.is_dataclass(a) and not isinstance(a, type):
        assert dataclasses.is_dataclass(b) and not isinstance(b, type), (
            f"{path}: type mismatch, {type(a)!r} is a dataclass but {type(b)!r} is not"
        )
        assert type(a) is type(b), f"{path}: type mismatch {type(a)!r} != {type(b)!r}"
        for f in dataclasses.fields(a):
            _walk_equal(getattr(a, f.name), getattr(b, f.name), f"{path}.{f.name}")
        return

    if hasattr(a, "_fields") and hasattr(b, "_fields"):  # NamedTuple (State)
        assert type(a) is type(b), f"{path}: type mismatch {type(a)!r} != {type(b)!r}"
        for field_name in a._fields:
            _walk_equal(getattr(a, field_name), getattr(b, field_name), f"{path}.{field_name}")
        return

    if isinstance(a, np.ndarray) or isinstance(b, np.ndarray):
        assert np.array_equal(a, b), f"{path}: array mismatch, {a!r} != {b!r}"
        return

    assert a == b, f"{path}: {a!r} != {b!r}"


@pytest.fixture(scope="module")
def registry_config():
    return configs.get("demo")


@pytest.fixture(scope="module")
def worked_example_config():
    return assemble(DEMO_SCENARIO)


def test_params_field_by_field_equivalence(registry_config, worked_example_config):
    """`assemble(DEMO_SCENARIO).params == configs.get("demo").params`,
    walked recursively rather than trusted to a bare `==` -- `Params` and
    every nested group are frozen dataclasses of scalars/strings (no
    numpy arrays anywhere in `sim/params.py`), so a bare `==` would in
    fact be reliable here, but the walker is the one that names the exact
    dotted field path if Part A's hand-copy ever has a slip.
    """
    _walk_equal(worked_example_config.params, registry_config.params, "params")
    # Belt and braces: the structural `==` the dataclasses actually give us for free.
    assert worked_example_config.params == registry_config.params


def test_s0_field_by_field_equivalence(registry_config, worked_example_config):
    """`assemble(DEMO_SCENARIO).s0 == configs.get("demo").s0` -- `State`
    is a `NamedTuple` of scalars; same rigor as the `.params` check above.
    """
    _walk_equal(worked_example_config.s0, registry_config.s0, "s0")
    assert worked_example_config.s0 == registry_config.s0


def test_scenario_config_property_matches_assemble():
    """`Scenario.config` is a one-line `@property` wrapper around
    `assemble` (`configs/schema.py`) -- both access paths must agree,
    since `examples/worked_scenario.py` could reasonably be read via
    either `assemble(DEMO_SCENARIO)` or `DEMO_SCENARIO.config`.
    """
    via_property = DEMO_SCENARIO.config
    via_assemble = assemble(DEMO_SCENARIO)
    _walk_equal(via_property.params, via_assemble.params, "config.params")
    _walk_equal(via_property.s0, via_assemble.s0, "config.s0")
    assert via_property == via_assemble


def test_demo_scenario_notes_and_name_match_the_registry(registry_config, worked_example_config):
    """Not load-bearing for `sim/`, but a transcription slip in `name`/
    `notes` is exactly the kind of thing a cherry-picked test would miss."""
    assert worked_example_config.name == registry_config.name
    assert worked_example_config.notes == registry_config.notes
