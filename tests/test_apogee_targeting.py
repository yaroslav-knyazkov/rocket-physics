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

Tier 2 (2 tests) -- real-physics regression, against
`apps.input.demo_scenario.DEMO_SCENARIO` (mass model ON). No fx27 data
involved: `apps/optimization/` tests should not need `projects/fx27`
fixtures.
"""

from __future__ import annotations

import math

import pytest

from apps.optimization.apogee_targeting import solve
from apps.optimization.apogee_targeting.solve import (
    estimate_airframe_mass,
    estimate_cx,
    solve_for_target_apogee,
)
from apps.input.demo_scenario import DEMO_SCENARIO

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
