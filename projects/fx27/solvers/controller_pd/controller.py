"""projects/fx27/solvers/controller_pd/controller.py -- fx27's Rung-1 closed-loop
airbrake demo: ideal actuator, noiseless sensors, one Tier-1 sampled law
(apps.control.flight_software.laws), assembled on top of one of fx27's own
cspace scenarios and a HAND-ENTERED airbrake hardware data file
(data/cspace/airbrake/*.csv, via data/cspace/airbrake_data.py)
-- NOT `solvers/point/ideal_open_airbrake.py`'s own live sizing solve. That solver
stays a separate, user-driven "what area do I need" tool; its output is
meant to be read by a human and hand-copied into the hardware CSV once
accepted, not consumed programmatically here (dev/docs/task-152-fx27-
point-controller-rung1.md S4).
"""

from __future__ import annotations

import dataclasses

import apps.control.flight_software  # noqa: F401  (import-time side effect: registers the Tier-1 laws)
from apps.control.flight_software import harness
from apps.sim.schema import Config, Scenario, assemble

from projects.fx27.data.cspace.airbrake_data import AirbrakeHardware

DEFAULT_LAW = "proportional_drag"          # the simpler Tier-1 law (no ki term)
DEFAULT_SAMPLE_RATE_HZ = 20.0              # matches tests/test_harness.py's own _closed_loop_params default
DEFAULT_MACH_REF = 0.3                     # subsonic post-burnout/coast regime -- see S4 for why a single ref Mach


@dataclasses.dataclass(frozen=True)
class Rung1Demo:
    """Everything one Rung-1 closed-loop run produced: the scenario actually
    flown, the assembled Config, the hardware data row(s) it was resolved
    from, and the harness's own flat metrics."""

    scenario: Scenario
    cfg: Config
    hardware: AirbrakeHardware
    harness: harness.HarnessResult


def build_rung1_scenario(
    scenario: Scenario,
    hardware: AirbrakeHardware,
    *,
    law: str = DEFAULT_LAW,
    kp: float,
    ki: float = 0.0,
    target_apogee_m: float,
    mach_ref: float = DEFAULT_MACH_REF,
    sample_rate_hz: float = DEFAULT_SAMPLE_RATE_HZ,
    estimator_model: str = "stub",
) -> Scenario:
    """`scenario` plus the Rung-1 `Control` overrides and a sampled solver
    (`Scenario.overrides`, SS schema.py:396-398 -- does NOT touch
    `scenario.rocket`). `Actuator`/`Sensors` are left at their library
    defaults (already the Rung-1 case: ideal actuator, noiseless sensors --
    see S0). `hardware.cd_at(mach_ref)`/`.area_at(mach_ref)` collapse the
    data file's own M-indexed row(s) to the single constant pair `Control`
    actually takes (S0's `Control.airbrake_Cd`/`airbrake_S_max` note) --
    this is a no-op (exact passthrough) when the CSV has exactly one row,
    by construction of `np.interp` (S4).
    """
    cfg = assemble(scenario)  # only to read cfg.params.aero/weight below
    onboard_CdA0 = cfg.params.aero.S * cfg.params.aero.C_x
    cd = hardware.cd_at(mach_ref)
    area = hardware.area_at(mach_ref)
    control_overrides = {
        "control.airbrake_model": law,
        "control.airbrake_target_apogee_m": target_apogee_m,
        "control.airbrake_kp": kp,
        "control.airbrake_ki": ki,
        "control.airbrake_Cd": cd,
        "control.airbrake_S_max": area,
        "control.onboard_mass": cfg.params.weight.m,
        "control.onboard_CdA0": onboard_CdA0,
        "control.onboard_CdA_brake": cd * area,
        "control.estimator_model": estimator_model,
    }
    overrides = {**scenario.overrides, **control_overrides}
    return dataclasses.replace(
        scenario,
        overrides=overrides,
        # method="rk4" is REQUIRED alongside sample_rate_hz>0.0 (not just this
        # ticket's own choice): apps/sim/engine/integrate.py's run_sim rejects
        # a plain adaptive "RK45" solver under a zero-order-hold boundary
        # (architecture-28-rewrite.md SS28.8.2) -- same idiom
        # tests/test_harness.py:80's own with_solver(method="rk4", ...) uses.
        # fx27's SCENARIOS dict leaves Solver at its library default
        # (method="RK45"), so this override is load-bearing here, not a
        # no-op.
        solver=dataclasses.replace(scenario.solver, method="rk4", sample_rate_hz=sample_rate_hz),
    )


def run_rung1_demo(
    scenario: Scenario,
    hardware: AirbrakeHardware,
    *,
    target_apogee_m: float = 2500.0,
    law: str = DEFAULT_LAW,
    kp: float,
    ki: float = 0.0,
    mach_ref: float = DEFAULT_MACH_REF,
    sample_rate_hz: float = DEFAULT_SAMPLE_RATE_HZ,
) -> Rung1Demo:
    """`build_rung1_scenario` wires `hardware`'s own Cd/area plus a Tier-1
    law into a sampled-data `Scenario`; `harness.run_closed_loop` flies it.
    `hardware` is the CALLER's responsibility to pick (S2's own
    scenario-name -> hardware-file mapping) -- this function does not look
    it up by rocket name itself, keeping it a pure function of its
    arguments. `kp` has no safe library-wide default (depends on target/
    mass scale) -- caller must pass one; see S5 note on picking it
    empirically.
    """
    rung1_scenario = build_rung1_scenario(
        scenario, hardware, law=law, kp=kp, ki=ki, target_apogee_m=target_apogee_m,
        mach_ref=mach_ref, sample_rate_hz=sample_rate_hz,
    )
    cfg = assemble(rung1_scenario)
    result = harness.run_closed_loop(cfg.params, cfg.s0)
    return Rung1Demo(scenario=rung1_scenario, cfg=cfg, hardware=hardware, harness=result)


def print_rung1_report(demo: Rung1Demo, config_name: "str | None" = None) -> None:
    """Target vs. achieved apogee, error, actuator saturation/travel, plus
    the resolved hardware numbers actually flown (read back from
    `demo.cfg.params.control`, the already-assembled scalars -- not
    re-derived) -- same print-report shape as `solvers/point/
    ideal_open_airbrake.py::print_brake_report`."""
    m = demo.harness.metrics
    c = demo.cfg.params.control
    label = config_name or demo.scenario.name
    print(f"Rung-1 closed loop: {label}")
    print(f"  target apogee              {c.airbrake_target_apogee_m:.1f} m")
    print(f"  achieved apogee            {m['apogee_m']:.1f} m")
    print(f"  apogee error               {m['apogee_error_m']:+.1f} m")
    print(f"  actuator saturation        {m['actuator_saturation_fraction']:.2%}")
    print(f"  actuator travel            {m['actuator_travel']:.3f}")
    print(f"  brake Cd (hardware file)   {c.airbrake_Cd:.3f}")
    print(f"  brake area (hardware file) {c.airbrake_S_max:.6f} m^2")
