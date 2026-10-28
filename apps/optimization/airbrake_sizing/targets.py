"""apps/optimization/airbrake_sizing/targets.py -- the study input
literal (D-23 style, `dev/docs/architecture-30-apps-4-5-and-configs.md`
SS30.6; moved here from apps/airbrake_sizing/targets.py at Phase 2.19
Step 131, dev/docs/architecture-apps-sim-restructure.md).

A target apogee is a *mission requirement*, not a property of the vehicle:
the same default vehicle (`configs.demo`) gets re-solved against several
targets, so these `AirbrakeSpec`s live here, not in `configs/`.

Numbers below are sized against `configs.demo` (Phase 2.16, Step 90,
dev/docs/architecture-33-configs-one-demo.md SS33.4.4): a real Cesaroni
K570 on a 54 mm airframe, mass model ON. Its brake-closed apogee is
~5947 m, burnout at 3.59 s, brake-closed apogee time ~29.6 s, so the
targets follow the precedent's own convention (F7: "~65% of the
brake-closed apogee"): 3850 m. The earlier 372 m / 9.19 s / burnout-2.0 s
narrative belonged to the former constant-mass `demo_75mm_airbrake`
vehicle, which is gone. NOTE (D-83): the demo's aero model is
`"constant"` and the flight is supersonic, so these are wiring/behaviour
numbers, not credible drag predictions. The demo now carries a main
canopy at apogee (Step 95, D-97), so `descent_demo` below descends under it
(and its brake) to `t_max` instead of falling ballistically.

The four named specs (SS30.6.1's table, the one of each kind that table
distinguishes):
"""

from __future__ import annotations

from apps.optimization.airbrake_sizing.solve_cda import AirbrakeSpec

SPECS: "dict[str, AirbrakeSpec]" = {
    # The main case: size the brake for an apogee target, deployed at
    # burnout (t=3.59 s on this vehicle). 3850 m is ~65% of the
    # brake-closed apogee (~5947 m, measured against configs.demo).
    "burnout_3850m": AirbrakeSpec(target_apogee_m=3850.0, trigger="after_burnout"),
    # Timer-triggered avionics: same target, brake popped 8 s after launch
    # (burnout is at t=3.59 s, apogee at ~29.6 s brake-closed, so 8 s sits
    # comfortably in the post-burnout, pre-apogee window).
    "timer_3850m": AirbrakeSpec(target_apogee_m=3850.0, trigger="after_time", deploy_time_s=8.0),
    # The mirror solve (F18): the brake is already built -- C_dA =
    # 0.0016 m^2 is this same target's own "burnout_3850m" answer (2 s.f.),
    # carried here as a degenerate (lo == hi) cda_bounds pair -- WHEN do I
    # pop it? deploy_time_bounds=(0, 25) brackets the root comfortably below
    # the brake-closed apogee time (~29.6 s), avoiding F18's flat tail.
    "when_to_pop": AirbrakeSpec(
        target_apogee_m=3850.0,
        trigger="after_time",
        solve_for="deploy_time",
        cda_bounds=(0.0016, 0.0016),
        deploy_time_bounds=(0.0, 25.0),
    ),
    # Report-only (F19): a post-apogee brake cannot be sized against an
    # apogee target -- the objective is flat by construction. target_apogee_m
    # is unused by evaluate_airbrake (no search runs) and is 0.0 here purely
    # so the field is not left meaningless-but-nonzero.
    "descent_demo": AirbrakeSpec(target_apogee_m=0.0, trigger="after_apogee", solve_for="none"),
}
