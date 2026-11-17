"""Tests for apps/optimization/apogee_targeting/ -- the generic apogee-
target root finder promoted from projects/fx27/point/estimate.py
(dev/docs/architecture-39-promote-apogee-target-solver.md, backlog B41).

Same testing philosophy as tests/test_airbrake_sizing.py: no fixtures, no
conftest.py, plain `assert` + `math.isclose`. Two tiers (SS39.6.2):

Tier 1 (5 tests) -- pure-logic, via `monkeypatch.setattr(solve,
"_apogee_for_scenario", <fake>)`. This replaces the one physics-touching
seam with a deterministic function, letting `scenario`/`param_setter` be
trivial placeholders (`param_setter=lambda s, x: x`, `scenario=None`) --
these run in milliseconds and exercise logic branches a real, monotonic
flight objective can never hit (an interior `None` apogee strictly inside
an otherwise-valid bracket).

Tier 2 (3 tests) -- real-physics regression, against
`apps.input.demo_scenario.DEMO_SCENARIO` (mass model ON). No fx27 data
involved: `apps/optimization/` tests should not need `projects/fx27`
fixtures. The third (`estimate_cx_scale`, architecture-42 SS42.5) flies a
`model="table"` variant of `DEMO_SCENARIO`'s rocket against a synthetic,
drag-only (`C_N=C_m=0`) Mach table -- same `_temp_table`/cache-clear
pattern `tests/test_scenario_sweep.py` already uses for its own synthetic
tables, and the same "drag-only table" invariant `rockets.py`'s dm
section relies on (Option C: a nonzero table `C_N`/`C_m` would reintroduce real pitch
dynamics `DEMO_SCENARIO`'s own aero was deliberately built without --
confirmed the hard way, see that test's own docstring).
"""

from __future__ import annotations

import contextlib
import dataclasses
import math
import os

import pytest

from apps.optimization.apogee_targeting import solve
from apps.optimization.apogee_targeting.solve import (
    estimate_airframe_mass,
    estimate_cx,
    estimate_cx_scale,
    solve_for_target_apogee,
)
from apps.input.demo_scenario import DEMO_SCENARIO
from apps.sim.engine import aero as _aero_module
from apps.sim.engine.params import Aero
from tests.datadir import AERO_DIR

# ----------------------------------------------------------------------
# Tier 1: pure-logic tests via monkeypatch on the one physics-touching seam
# ----------------------------------------------------------------------


def test_unreachable_target_above_max_clamps_to_hi_bound(monkeypatch):
    """fake apogee = identity (apogee_at(x) == x); target above both
    bounds -- must clamp to the hi bound, no exception."""
    monkeypatch.setattr(solve, "_apogee_for_scenario", lambda x: x)

    res = solve_for_target_apogee(
        scenario=None,
        param_setter=lambda s, x: x,
        baseline_value=0.0,
        bracket=(0.0, 10.0),
        target_apogee_agl=20.0,
    )

    assert res.reachable is False
    assert res.required == 10.0
    assert res.achieved_apogee_m == 10.0


def test_unreachable_target_below_min_clamps_to_lo_bound(monkeypatch):
    """Mirror of the above: target below both bounds clamps to lo."""
    monkeypatch.setattr(solve, "_apogee_for_scenario", lambda x: x)

    res = solve_for_target_apogee(
        scenario=None,
        param_setter=lambda s, x: x,
        baseline_value=0.0,
        bracket=(0.0, 10.0),
        target_apogee_agl=-5.0,
    )

    assert res.reachable is False
    assert res.required == 0.0
    assert res.achieved_apogee_m == 0.0


def test_bound_with_no_apogee_event_raises_valueerror(monkeypatch):
    """A `None` apogee at one of the two bracket endpoints must raise
    ValueError naming "never leaves the pad", not silently root-find."""

    def fake_apogee(x):
        return None if x == 0.0 else x

    monkeypatch.setattr(solve, "_apogee_for_scenario", fake_apogee)

    with pytest.raises(ValueError, match="never leaves the pad"):
        solve_for_target_apogee(
            scenario=None,
            param_setter=lambda s, x: x,
            baseline_value=0.0,
            bracket=(0.0, 10.0),
            target_apogee_agl=5.0,
        )


def test_none_apogee_strictly_inside_bracket_does_not_crash(monkeypatch):
    """Deliberately non-physical: apogee is `None` everywhere except
    exactly at the two bracket bounds, forcing `brentq` to probe an
    interior `None` during the search. Must not raise; the bound-only
    reachability check already passes before the search starts."""
    lo, hi = 0.0, 10.0
    lo_apogee, hi_apogee = 0.0, 10.0

    def fake_apogee(x):
        if x == lo:
            return lo_apogee
        if x == hi:
            return hi_apogee
        return None

    monkeypatch.setattr(solve, "_apogee_for_scenario", fake_apogee)

    res = solve_for_target_apogee(
        scenario=None,
        param_setter=lambda s, x: x,
        baseline_value=0.0,
        bracket=(lo, hi),
        target_apogee_agl=5.0,
    )

    assert res.reachable is True


def test_converges_to_the_analytic_root_within_xtol(monkeypatch):
    """fake apogee is a known affine function of x; solve for a target
    inside the bracket's own apogee range and check the closed-form root
    is recovered within `xtol`. Also pins that `baseline`/`delta` are
    plumbed through from the `baseline_value` argument, unmodified."""
    lo, hi = 0.0, 100.0

    def fake_apogee(x):
        return 1000.0 - 2.0 * x

    monkeypatch.setattr(solve, "_apogee_for_scenario", fake_apogee)

    baseline_value = 7.0
    xtol = 1.0e-4
    res = solve_for_target_apogee(
        scenario=None,
        param_setter=lambda s, x: x,
        baseline_value=baseline_value,
        bracket=(lo, hi),
        target_apogee_agl=900.0,
        xtol=xtol,
    )

    analytic_root = 50.0  # 900 = 1000 - 2*x -> x = 50
    assert res.reachable is True
    assert math.isclose(res.required, analytic_root, abs_tol=10 * xtol)
    assert res.baseline == baseline_value
    assert math.isclose(res.delta, res.required - baseline_value)


# ----------------------------------------------------------------------
# Tier 2: real-physics regression against DEMO_SCENARIO (no fx27 data)
# ----------------------------------------------------------------------


def test_estimate_airframe_mass_on_demo_scenario_is_reachable_and_converges():
    """Regression guard against a future reintroduction of the
    `params.replace`-on-assembled-`Config` staleness bug (SS38.4.2): if a
    future edit swapped `Scenario -> assemble` for a post-hoc
    `params.replace`, `s0.m` would go stale and the search would no
    longer actually respond to the swept mass, so this test would stop
    converging (or converge to a physically wrong value)."""
    target_apogee_agl = 3000.0
    res = estimate_airframe_mass(DEMO_SCENARIO, target_apogee_agl=target_apogee_agl)

    assert res.reachable is True
    assert math.isclose(res.achieved_apogee_m, target_apogee_agl, abs_tol=1.0e-2)


def test_estimate_cx_on_demo_scenario_is_reachable_and_converges():
    """Same shape as the mass regression test, for `estimate_cx`."""
    target_apogee_agl = 3000.0
    res = estimate_cx(DEMO_SCENARIO, target_apogee_agl=target_apogee_agl)

    assert res.reachable is True
    assert math.isclose(res.achieved_apogee_m, target_apogee_agl, abs_tol=1.0e-2)


# A synthetic, DRAG-ONLY Mach table (C_N=C_m=0 at every grid point -- the same
# Option C invariant `projects/fx27/data/cspace/rockets.py`'s dm section relies on
# for its own Mach-dependent variants) for the `estimate_cx_scale` regression
# below. C_A is held flat at 0.5 (DEMO_SCENARIO's own baseline constant C_x)
# purely so the table-model flight's apogee timing is the same order as the
# existing two Tier-2 tests' ~30 s, not because the shape of C_A(M) matters to
# what this test checks (`estimate_cx_scale` solving for a `cx_scale`
# multiplier, not the table's own curve).
#
# A non-drag-only table (nonzero C_N/C_m) was tried first and found to
# destabilize DEMO_SCENARIO's rocket almost immediately after leaving the
# rail (`AeroRangeWarning`, alpha outside the table's covered range within
# the first ~5 s of a 1200 s flight) -- DEMO_SCENARIO's own aero was
# deliberately built with C_z=C_m=0 ("keeps flight vertical/1-D", that
# module's own docstring), so reintroducing a real pitching moment via the
# table is a second, unrelated instability, not the Mach-table-cx_scale
# behavior this test means to exercise. Same `_temp_table` pattern as
# `tests/test_scenario_sweep.py`'s own synthetic tables (`_LOW_M_TABLE`).
_DRAG_ONLY_TABLE = """# cm_convention: standard
alpha_deg,M,C_A,C_N,C_m,l_p_m
-10,0.0,0.50,0.0,0.0,0.0
0,0.0,0.50,0.0,0.0,0.0
10,0.0,0.50,0.0,0.0,0.0
-10,3.0,0.50,0.0,0.0,0.0
0,3.0,0.50,0.0,0.0,0.0
10,3.0,0.50,0.0,0.0,0.0
"""


@contextlib.contextmanager
def _temp_table(name, text):
    path = os.path.join(AERO_DIR, name)
    with open(path, "w") as f:
        f.write(text)
    _aero_module._load_table.cache_clear()
    try:
        yield name
    finally:
        _aero_module._load_table.cache_clear()
        # Tolerate the file already being gone: this repo's data/ tree lives under a
        # cloud-synced folder (CLAUDE.md "Yandex.Disk" note), and a create-then-remove
        # this close together was observed, during this step's own testing, to
        # occasionally race with the sync client and raise FileNotFoundError here even
        # though nothing in this process removed it early -- the actual goal ("no stray
        # file left behind") is already satisfied either way, so a missing file at
        # cleanup time is not a test failure.
        try:
            os.remove(path)
        except FileNotFoundError:
            pass


def test_estimate_cx_scale_on_table_scenario_is_reachable_and_converges():
    """`estimate_cx_scale` (architecture-42 SS42.5) mirrors `estimate_cx`
    but drives `Scenario.overrides["aero.cx_scale"]` instead of
    `"aero.C_x"` -- the Mach-table analogue, needed because a
    `model="table"` `Aero` has no single `C_x` to solve for. Built on a
    `model="table"` variant of `DEMO_SCENARIO`'s own rocket, against the
    synthetic drag-only table above -- no fx27 fixtures needed,
    `apps/optimization/` tests should not depend on `projects/fx27`."""
    with _temp_table("test_apogee_targeting_drag_only.csv", _DRAG_ONLY_TABLE) as tbl:
        table_rocket = dataclasses.replace(
            DEMO_SCENARIO.rocket,
            aero=Aero(model="table", S=DEMO_SCENARIO.rocket.aero.S, d_ref=DEMO_SCENARIO.rocket.aero.d_ref, table=tbl),
        )
        # C_N=C_m=0 above keeps this flight exactly vertical (alpha stays 0 throughout,
        # same invariant `rockets.py`'s dm section relies on), so -- unlike a nonzero-moment table
        # -- the full DEMO_SCENARIO solver (t_max=1200 s, canopy descent included) is safe
        # to fly unmodified; no RK45-stall regime (dev/docs/diagnosis-rk45-v2-table.md) to
        # avoid here.
        table_scenario = dataclasses.replace(DEMO_SCENARIO, rocket=table_rocket)

        # 4000 m, not the other two Tier-2 tests' 3000 m: at this table's C_A=0.5,
        # the default cx_scale_bracket (0.0, 2.0) only reaches apogees in
        # [~3654 m, ~5947 m] (measured) -- 3000 m falls outside that range, so
        # this target is chosen to actually be bracketed, not copied by rote.
        target_apogee_agl = 4000.0
        res = estimate_cx_scale(table_scenario, target_apogee_agl=target_apogee_agl)

    assert res.reachable is True
    assert math.isclose(res.achieved_apogee_m, target_apogee_agl, abs_tol=1.0e-2)
