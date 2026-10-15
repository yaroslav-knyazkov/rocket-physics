"""apps/airbrake_sizing/targets.py -- the study input literal (D-23 style,
`dev/docs/architecture-30-apps-4-5-and-configs.md` SS30.6).

A target apogee is a *mission requirement*, not a property of the vehicle:
the same `configs.demo_75mm_airbrake` gets re-solved against several
targets, so these `AirbrakeSpec`s live here, not in `configs/`.

Numbers below are sized against `configs.demo_75mm_airbrake` as it is
actually registered (Step 63): `demo_75mm` unchanged, flying
`thrust.motor_curve="placeholder.csv"` (162.75 N*s on 1.5 kg), **not** the
`synthetic_large.csv` swap `apps/motor_selection/motors.py` applies for its
own "I large" entry. SS30.2's F6/F7/F18/F19 tables were measured against
that heavier-motor swap (brake-closed apogee ~996.75 m, hence the
precedent's "650 m (65%)" and "deploy_time=4 s" illustrations) -- flown on
`demo_75mm_airbrake` as registered, the brake-closed apogee is instead
~372 m (`placeholder.csv`'s own, much smaller, impulse), so copying 650 m
verbatim would make the two solving specs below report "unreachable"
against this app's own default vehicle, which demonstrates nothing. This
file therefore follows `configs/demo_75mm_airbrake.py`'s own docstring
("a target apogee ~65% of the brake-closed apogee") against the *actual*
registered brake-closed apogee, not the F6/F18 measurement vehicle's —
flagged in the Step 66 developer report as a judgment call.

The four named specs (SS30.6.1's table, the one of each kind that table
distinguishes):
"""

from __future__ import annotations

from apps.airbrake_sizing.solve_cda import AirbrakeSpec

SPECS: "dict[str, AirbrakeSpec]" = {
    # The main case: size the brake for an apogee target, deployed at
    # burnout (t=2.0 s on this vehicle). 240 m is ~65% of the brake-closed
    # apogee (~372 m, measured against configs.demo_75mm_airbrake as
    # registered) -- the precedent's own target-selection convention
    # (F7: "65% of the brake-closed apogee"), just computed against this
    # app's actual default vehicle rather than the heavier F6/F18 swap.
    "burnout_240m": AirbrakeSpec(target_apogee_m=240.0, trigger="after_burnout"),
    # Timer-triggered avionics: same target, brake popped 4 s after launch
    # (burnout is at t=2.0 s, apogee at ~9.19 s brake-closed, so 4 s sits
    # comfortably in the post-burnout, pre-apogee window).
    "timer_240m": AirbrakeSpec(target_apogee_m=240.0, trigger="after_time", deploy_time_s=4.0),
    # The mirror solve (F18): the brake is already built -- C_dA =
    # 0.01171 m^2 is this same target's own "burnout_240m" answer, carried
    # here as a degenerate (lo == hi) cda_bounds pair -- WHEN do I pop it?
    # deploy_time_bounds=(0, 8) brackets the root comfortably below the
    # brake-closed apogee time (~9.19 s), avoiding F18's flat tail.
    "when_to_pop": AirbrakeSpec(
        target_apogee_m=240.0,
        trigger="after_time",
        solve_for="deploy_time",
        cda_bounds=(0.01171, 0.01171),
        deploy_time_bounds=(0.0, 8.0),
    ),
    # Report-only (F19): a post-apogee brake cannot be sized against an
    # apogee target -- the objective is flat by construction. target_apogee_m
    # is unused by evaluate_airbrake (no search runs) and is 0.0 here purely
    # so the field is not left meaningless-but-nonzero.
    "descent_demo": AirbrakeSpec(target_apogee_m=0.0, trigger="after_apogee", solve_for="none"),
}
