"""Demo-scenario physics pins, plus a few piece-level equality checks
(Phase 2.18 pivot, Step 125, D-137..D-142). Originally written for the
Step 73 registry switch-over (`configs.get` delegating to
`configs.scenarios`); the registry itself is now archived at
`dev/archive/configs-registry-2026-10/`, so every check here is sourced
from `apps.input.demo_scenario.DEMO_SCENARIO` (moved there from
`examples.worked_scenario` at Phase 2.19, Step 130) instead of
`configs.get`/`configs.rockets`/etc.

What is left: the headline demo-scenario physics pins (mass model on,
composed masses, the `I_sp_eff` SS32.3.4 F5 pin, station-convention
sanity, the burnout-mass-lands-on-`m_f` pin, the D-59 `endpoints`/`isp`
apogee-equivalence pin, the main-canopy landing-speed pin) and a few
piece-level equality checks against independent reconstructions already
in the suite (`study_vehicle`/`config_variants`) that never touched the
registry in the first place. Pure registry-mechanism tests (scenario
lookup by name, unknown-name KeyError, flat-`Config`-module registration,
"every registered scenario flies") were deleted with the registry --
Step 122's `tests/test_worked_scenario_example.py` smoke test already
proves the demo flies end-to-end.
"""

import math

import pytest

from apps.input import study_vehicle
from apps.input.demo_scenario import DEMO_SCENARIO
from apps.input.demo_scenario import rocket as _demo_rocket
from apps.input.demo_scenario import site as _demo_site
from apps.input.demo_scenario import weather as _demo_weather
from apps.optimization.motor_selection.compare_motors import _demo_baseline
from configs.schema import Scenario
from apps.sim.engine.integrate import run_sim
from apps.sim.engine.state import M
from tests import config_variants
from tests.test_configs import _toy_05kg_literal

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
    rocket = study_vehicle.ROCKET
    params = study_vehicle.CONFIG.params
    baseline = _demo_baseline()
    assert params.weight == baseline.weight
    assert rocket.lengths == baseline.lengths
    assert params.thrust == baseline.thrust
    assert rocket.aero == baseline.aero


def test_toy_05kg_rocket_groups_equal_toy_05kg_literal():
    """See `test_demo_75mm_rocket_groups_equal_demo_baseline`'s docstring
    -- same Step-80 retargeting of `weight`/`thrust`."""
    rocket = config_variants.TOY_05KG_ROCKET
    params = config_variants.TOY_05KG.params
    literal = _toy_05kg_literal()
    assert params.weight == literal.weight
    assert rocket.lengths == literal.lengths
    assert params.thrust == literal.thrust
    assert rocket.aero == literal.aero


@pytest.mark.parametrize("cfg", config_variants.ALL, ids=lambda c: c.name)
def test_every_test_variant_flies(cfg):
    """Keeps flight coverage of the tilted rail + analytic wind that the
    registry parametrisation used to give (Step 88, SS33.3.2)."""
    result = run_sim(cfg.params, cfg.s0)
    assert result.events["apogee"] is not None


# ----------------------------------------------------------------------
# Step 74 (SS31.12): demo_75mm_highland -- the same rocket piece flown
# from a different site, in different weather.
# ----------------------------------------------------------------------


def test_demo_75mm_highland_rocket_groups_equal_demo_75mm():
    """The proof that one vehicle now serves two sites with zero
    duplication -- the user's original request reduced to one
    assertion (SS31.12)."""
    highland = config_variants.HIGHLAND
    baseline = study_vehicle.CONFIG
    assert highland.params.weight == baseline.params.weight
    assert highland.params.lengths == baseline.params.lengths
    assert highland.params.thrust == baseline.params.thrust
    assert highland.params.aero == baseline.params.aero


def test_demo_75mm_highland_s0_theta_derives_from_the_tilted_rail():
    """D-51a's derivation doing real work for the first time: every
    other registered scenario's rail sits at the `Site` default
    (90.0 deg, reproducing `math.pi / 2` exactly, SS31.2 F6);
    `highland_1500m`'s rail is tilted to 85.0 deg."""
    assert config_variants.HIGHLAND.s0.theta == math.radians(85.0)


def test_demo_75mm_highland_site_and_weather_are_the_new_pieces():
    cfg = config_variants.HIGHLAND
    assert cfg.params.site.h0_m == 1500.0
    assert cfg.params.wind.model == "analytic"


# ----------------------------------------------------------------------
# Step 81 (dev/docs/architecture-32-motor-separation.md SS32.2/SS32.3.3/
# SS32.3.4/SS32.5): demo -- a real CTI motor (its own mass
# history read from its own RASP file) composed with a mass-modelled
# airframe, the mass model ON from a config for the first time. The
# checks below are Step 81's own: the composition's actual numbers, the
# station-convention sanity check, and the headline burnout-mass claim
# (D-59) measured on a real curve rather than argued. Sourced from
# `apps.input.demo_scenario.DEMO_SCENARIO` since the Phase 2.18 pivot
# (Step 125; moved from `examples.worked_scenario` at Step 130) --
# field-identical to the former `configs.get("demo")` (Step 122's bridge
# test proved this before the registry was archived).
# ----------------------------------------------------------------------


def _demo_airframe():
    return _demo_rocket.airframe


def test_demo_mass_model_is_on():
    """The mass model is ON for the first time from a config (SS32.3.3)."""
    assert DEMO_SCENARIO.config.params.weight.m_d is not None


def test_demo_composed_masses():
    airframe = _demo_airframe()
    weight = DEMO_SCENARIO.config.params.weight
    # K570 header (SS32.3.1 F5): m_total=1.685 kg, m_prop=0.990 kg,
    # m_f = m_total - m_prop = 0.695 kg.
    assert weight.m == pytest.approx(airframe.m + 1.685, rel=1e-6)
    assert weight.m_d == pytest.approx(airframe.m + 0.695, rel=1e-6)


def test_demo_isp_eff_matches_f5():
    """`I_sp_eff = J/(m_prop*g0)` derived at assembly from the curve's own
    total impulse (SS32.3.4), matching F5's measured 212.41 s."""
    assert DEMO_SCENARIO.config.params.weight.I_sp == pytest.approx(212.41, abs=0.01)


def test_demo_stations_are_inside_the_airframe():
    """`l_d`/`l_p` (the composed dry-assembly and propellant nose-tip
    stations) both fall inside `[l_nose, L_total]` -- the station-
    convention sanity check (SS32.5)."""
    sections = _demo_rocket.sections
    weight = DEMO_SCENARIO.config.params.weight
    assert sections.l_nose <= weight.l_d <= sections.L_total
    assert sections.l_nose <= weight.l_p <= sections.L_total


def test_demo_burnout_mass_lands_on_m_f():
    """The headline assertion (SS32.3.4, D-59): the impulse-fraction-
    shaped 'endpoints' model consumes exactly `m_prop` over the whole
    curve, so the integrated state's mass at the end of the run lands on
    `m_f = m_total - m_prop` -- measured on the real K570 curve, not just
    argued. `thrust` (and hence `dm/dt`) is zero past burnout (the
    `(0.0, 0.0)` prepend plus the curve's own trailing zero, SS32.3.4), so
    mass stops changing at burnout and the LAST sample of a full run to
    ground impact is still the burnout mass."""
    airframe = _demo_airframe()
    cfg = DEMO_SCENARIO.config
    result = run_sim(cfg.params, cfg.s0)
    assert result.y[M][-1] == pytest.approx(airframe.m + 0.695, rel=1e-4)


def test_demo_isp_and_endpoints_motors_agree_on_apogee():
    """D-59's equivalence, end to end: the same airframe flown with
    `cti_k570` ('endpoints', `I_sp` derived from the curve's own total
    impulse) and `cti_k570_isp` ('isp', `I_sp` hand-entered to match)
    give apogees agreeing to ~0.1%."""
    cfg_endpoints = DEMO_SCENARIO.config

    scenario_isp = Scenario(
        name="_test_demo_isp",
        rocket=_demo_rocket,
        motor=config_variants.CTI_K570_ISP,
        site=_demo_site,
        weather=_demo_weather,
    )
    cfg_isp = scenario_isp.config

    result_endpoints = run_sim(cfg_endpoints.params, cfg_endpoints.s0)
    result_isp = run_sim(cfg_isp.params, cfg_isp.s0)

    apogee_endpoints = -result_endpoints.y[1].min()  # z is DOWN-positive; altitude = -z
    apogee_isp = -result_isp.y[1].min()
    assert apogee_endpoints == pytest.approx(apogee_isp, rel=1e-3)


def test_demo_lands_under_its_main_canopy():
    """Step 95 (D-97): the demo deploys one main canopy at apogee and lands
    at ~6 m/s (measured 5.97 m/s at t ~ 890.9 s)."""
    import warnings

    import numpy as np

    from apps.sim.engine.integrate import run_sim
    from apps.sim.engine.mach_warning import MachRangeWarning

    cfg = DEMO_SCENARIO.config
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", MachRangeWarning)
        r = run_sim(cfg.params, cfg.s0)
    assert r.events["ground"] is not None
    v_impact = float(np.hypot(r.y[2][-1], r.y[3][-1]))
    assert 5.5 <= v_impact <= 6.5
    assert abs(r.events["parachute_deploy"] - r.events["apogee"]) < 1e-6
